#!/usr/bin/env python3
"""
validate_research_solves_20260507.py

Multi-judge cascade validation of the R26 strict-judge solves cited in v4 paper §5.5.
Builds the confidence ladder:  v4-flash  ->  v4-pro  ->  GPT-5.4-nano-xhigh.

Inputs
  - results/architecture_20260506/trials.jsonl   (R26 strict solves; final_solution inline)
  - results/scaling_20260506/trials.jsonl        (cell-level scaling rows; branch text NOT here)
  - results/dataset_20260505.jsonl               (master upstream of buckets; branch[].final_solution)

Pipeline
  Stage 1 (v4-pro):  for every cell that scored >=6 under v4-flash OR v4-pro,
                     re-grade with deepseek-v4-pro UNLESS that exact cell already has
                     a v4-pro grade >=6 (in which case keep the existing grade).
                     Mark "v4pro_validated" if the (existing or new) v4-pro score >=6.
  Stage 2 (nano):    for every v4pro_validated cell, additionally grade with
                     openai/gpt-5.4-nano at reasoning_effort="high" (xhigh per repo
                     nomenclature; OpenRouter accepts "high" for that model).

Outputs (under repo-root, per CLAUDE.md results convention):
  results/validate_research_solves_20260507/
    trials.jsonl     # one row per (cell, judge) call (incl. cached existing v4-pro grades)
    trials.csv       # same, csv form
    summary.csv      # one row per cell with the full ladder verdict
    report.md        # markdown report w/ ladder counts and per-problem tables

Usage:
    uv run experiments/validate_research_solves_20260507.py --mock
    uv run experiments/validate_research_solves_20260507.py
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import re
import sys
import threading
import time
import traceback
from collections import defaultdict, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import litellm
from dotenv import load_dotenv

# ----- Paths -----
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

PROMPTS_DIR = ROOT / "prompts" / "pipeline"
ARCH_JSONL  = ROOT / "results" / "architecture_20260506" / "trials.jsonl"
SCAL_JSONL  = ROOT / "results" / "scaling_20260506"      / "trials.jsonl"
MASTER_JSONL= ROOT / "results" / "dataset_20260505.jsonl"
OUT_DIR     = ROOT / "results" / "validate_research_solves_20260507"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR     = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ----- Models / pricing -----
V4PRO_MODEL = "openrouter/deepseek/deepseek-v4-pro"
NANO_MODEL  = "openrouter/openai/gpt-5.4-nano"
# Price per token (USD) — from results/answerbench_calibration_20260506/pricing_snapshot.json
PRICE = {
    V4PRO_MODEL: {"prompt": 4.35e-07, "completion": 8.7e-07},
    NANO_MODEL:  {"prompt": 2.0e-07,  "completion": 1.25e-06},
}

NANO_REASONING_EFFORT = "high"   # OpenRouter calls this "high"; repo nomenclature is "xhigh"

# ----- Limits -----
MAX_WORKERS    = 12
MAX_TOKENS_OUT = 65536
LITELLM_TIMEOUT = 1500
HARD_COST_CAP_USD = 15.0

# ----- Env / keys -----
load_dotenv(ROOT / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY_draft_exps") or os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise SystemExit("Neither OPENROUTER_API_KEY_draft_exps nor OPENROUTER_API_KEY set in .env")

# ============================================================================
# Cell construction
# ============================================================================

def gscore(r: dict, judge_key: str):
    j = r.get("judges") or {}
    s = (j.get(judge_key) or {}).get("score")
    return s

def jverdict(r: dict, judge_key: str) -> str | None:
    j = r.get("judges") or {}
    return (j.get(judge_key) or {}).get("verdict")

def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()[:16]

# Scaling cells we expect (from analysis_v4_output / verified by inspection)
SCALING_CELLS = [
    ("deepseek-v4-flash",      "erdos-1051",              "default", "scaling_v4flash"),
    ("deepseek-v4-flash",      "erdos-659",               "default", "scaling_v4flash"),
    ("deepseek-v4-flash",      "first-proof-10-official", "default", "scaling_v4flash"),
    ("deepseek-v4-flash",      "first-proof-6-official",  "default", "scaling_v4flash"),
    ("gemma-4-31b-it",         "first-proof-10-official", "max",     "scaling_reasoning"),
    ("gpt-oss-120b",           "first-proof-10-official", "max",     "scaling_reasoning"),
]

def build_cells() -> list[dict]:
    """Return the list of cells to validate.
    Each cell has all fields needed for grading + reporting.
    """
    arows = [json.loads(l) for l in open(ARCH_JSONL, encoding="utf-8")]
    drows = [json.loads(l) for l in open(MASTER_JSONL, encoding="utf-8")]

    # Master index: (model_short, problem_id, experiment) -> row
    master_index: dict[tuple, dict] = {}
    for r in drows:
        short = r["model"].split("/")[-1]
        master_index[(short, r["problem_id"], r.get("experiment"))] = r

    cells: list[dict] = []

    # --- Architecture cells: each row that meets the strict threshold ---
    for r in arows:
        if not r.get("is_26_research"): continue
        v4f = gscore(r, "v4flash")
        v4p = gscore(r, "v4pro")
        if (v4f is None or v4f < 6) and (v4p is None or v4p < 6): continue
        text = r.get("final_solution") or ""
        cells.append({
            "bucket":             "architecture",
            "problem_id":         r["problem_id"],
            "difficulty":         r.get("difficulty"),
            "difficulty_label":   r.get("difficulty_label"),
            "model_short":        r["model"].split("/")[-1],
            "model_id":           r["model"],
            "mode":               r.get("mode") or "",
            "mode_or_n":          r.get("mode") or "",
            "reasoning":          r.get("reasoning") or "default",
            "source_experiment":  r.get("experiment") or "",
            "condition":          r.get("condition") or "",
            "branch_idx":         None,
            "orig_v4flash_score": v4f,
            "orig_v4pro_score":   v4p,
            "orig_v4pro_verdict": jverdict(r, "v4pro"),
            "proof_text":         text,
            "problem_text":       r.get("problem_text") or "",
            "ground_truth":       r.get("ground_truth") or "",
            "solution_text_hash": text_hash(text),
        })

    # --- Scaling cells: per-branch with v4flash >= 6 (no per-branch v4pro grade exists) ---
    for short, pid, reas, src_exp in SCALING_CELLS:
        key = (short, pid, src_exp)
        if key not in master_index:
            print(f"[WARN] master row missing for scaling cell {key}")
            continue
        mr = master_index[key]
        for bidx, b in enumerate(mr.get("branches") or []):
            j = b.get("judges") or {}
            v4f = (j.get("v4flash") or {}).get("score")
            if v4f is None or v4f < 6: continue
            sol = b.get("final_solution") or b.get("solution") or ""
            cells.append({
                "bucket":             "scaling",
                "problem_id":         pid,
                "difficulty":         mr.get("difficulty"),
                "difficulty_label":   mr.get("difficulty_label"),
                "model_short":        short,
                "model_id":           mr["model"],
                "mode":               "best_of_n",
                "mode_or_n":          f"best_of_n_branch{bidx}",
                "reasoning":          reas,
                "source_experiment":  src_exp,
                "condition":          mr.get("condition") or "",
                "branch_idx":         bidx,
                "orig_v4flash_score": v4f,
                "orig_v4pro_score":   None,
                "orig_v4pro_verdict": None,
                "proof_text":         sol,
                "problem_text":       mr.get("problem_text") or "",
                "ground_truth":       mr.get("ground_truth") or "",
                "solution_text_hash": text_hash(sol),
            })

    return cells

# ============================================================================
# Judge-call infrastructure
# ============================================================================

JUDGE_PROMPT_TEMPLATE = (PROMPTS_DIR / "judge_gt.md").read_text(encoding="utf-8")

def build_user_prompt(problem: str, ground_truth: str, candidate: str) -> str:
    return (JUDGE_PROMPT_TEMPLATE
            .replace("{problem}",      problem)
            .replace("{ground_truth}", ground_truth)
            .replace("{candidate}",    candidate))

POINTS_RE = re.compile(r"<points>\s*(\d+)\s*out of 7\s*</points>", re.I)
ALT_RE    = re.compile(r"\b([0-7])\s*(?:/\s*7|out of 7)", re.I)
def parse_score(text: str) -> int:
    if not text: return 0
    m = POINTS_RE.search(text)
    if m: return int(m.group(1))
    m = ALT_RE.search(text)
    if m: return int(m.group(1))
    classif = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif.items():
        if f"CLASSIFICATION: {label}" in text: return score
    return 0


class CostTracker:
    def __init__(self, cap):
        self.cap = cap
        self._cost = 0.0
        self._lock = threading.Lock()
        self._aborted = False
    def add(self, dollars):
        with self._lock:
            self._cost += dollars
            if self._cost >= self.cap and not self._aborted:
                self._aborted = True
                print(f"[!!] HARD COST CAP hit: ${self._cost:.2f} >= ${self.cap}", flush=True)
    @property
    def total(self):
        with self._lock: return self._cost
    @property
    def aborted(self):
        with self._lock: return self._aborted


def call_judge(model: str, user_prompt: str, *, reasoning_effort: str | None = None,
               extra_body: dict | None = None, timeout: int = LITELLM_TIMEOUT,
               retries: int = 1, backoff: float = 5.0):
    """Make a single judge call. Returns (text, usage_dict, elapsed_s).

    Hardening notes (per repo MEMORY):
      - v4-pro returns its answer in `reasoning_content` when `content` is empty.
        Always fall back if content is None/empty.
      - For v4-pro/nano, allow the model plenty of reasoning tokens via extra_body.
    """
    last = None
    t0 = time.time()
    for att in range(retries + 1):
        try:
            kwargs = dict(
                model=model,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=MAX_TOKENS_OUT,
                api_key=API_KEY,
                timeout=timeout,
            )
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
            if extra_body:
                kwargs["extra_body"] = extra_body
            resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message  # type: ignore
            text = getattr(msg, "content", None)
            if not text:
                text = getattr(msg, "reasoning_content", "") or ""
            usage = getattr(resp, "usage", None)
            return text, {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
            }, round(time.time() - t0, 2)
        except Exception as e:
            last = e
            msg = str(e)
            if "402" in msg or "Insufficient credits" in msg or "Key limit exceeded" in msg:
                raise
            if att < retries:
                time.sleep(backoff * (2 ** att))
    raise last  # type: ignore


def estimate_cost(model: str, usage: dict) -> float:
    p = PRICE.get(model, {})
    return (usage.get("prompt_tokens", 0) * p.get("prompt", 0)
            + usage.get("completion_tokens", 0) * p.get("completion", 0))


# ============================================================================
# Per-cell evaluation
# ============================================================================

def grade_one(cell: dict, judge_kind: str, mock: bool) -> dict:
    """Run a single judge call against a cell. judge_kind in {"v4pro","nano"}."""
    rec = {
        "problem_id":       cell["problem_id"],
        "difficulty":       cell["difficulty"],
        "difficulty_label": cell["difficulty_label"],
        "model_short":      cell["model_short"],
        "mode_or_n":        cell["mode_or_n"],
        "reasoning":        cell["reasoning"],
        "source_experiment":cell["source_experiment"],
        "branch_idx":       cell["branch_idx"],
        "judge":            f"{judge_kind}_validation",
        "judge_model":      V4PRO_MODEL if judge_kind == "v4pro" else NANO_MODEL,
        "score":            None,
        "verdict_text":     None,
        "cost_usd":         0.0,
        "elapsed_s":        0.0,
        "error":            None,
        "original_v4flash_score": cell["orig_v4flash_score"],
        "original_v4pro_score":   cell["orig_v4pro_score"],
        "solution_text_hash":     cell["solution_text_hash"],
        "in_tokens":        None,
        "out_tokens":       None,
        "from_cache":       False,
        "completed_at":     datetime.now(timezone.utc).isoformat(),
    }
    if mock:
        rec["score"] = 7
        rec["verdict_text"] = "<points>7 out of 7</points> [MOCK]"
        rec["cost_usd"] = 0.0
        rec["elapsed_s"] = 0.0
        return rec

    if not cell["proof_text"]:
        rec["error"] = "empty_proof_text"
        return rec
    if not cell["problem_text"] or not cell["ground_truth"]:
        rec["error"] = "missing_problem_text_or_ground_truth"
        return rec

    user = build_user_prompt(cell["problem_text"], cell["ground_truth"], cell["proof_text"])
    if judge_kind == "v4pro":
        try:
            text, usage, elapsed = call_judge(
                V4PRO_MODEL, user,
                # Per MEMORY: v4-pro needs an explicit reasoning budget so it doesn't
                # run dry before emitting the <points> line.
                extra_body={"reasoning": {"max_tokens": 32768}},
                timeout=LITELLM_TIMEOUT,
                retries=1,
            )
        except Exception as e:
            rec["error"] = f"v4pro_call_failed: {e}"
            rec["elapsed_s"] = round(time.time() - 0, 2)  # not meaningful here
            return rec
    elif judge_kind == "nano":
        try:
            text, usage, elapsed = call_judge(
                NANO_MODEL, user,
                reasoning_effort=NANO_REASONING_EFFORT,
                timeout=LITELLM_TIMEOUT,
                retries=1,
            )
        except Exception as e:
            rec["error"] = f"nano_call_failed: {e}"
            rec["elapsed_s"] = round(time.time() - 0, 2)
            return rec
    else:
        rec["error"] = f"unknown_judge_kind: {judge_kind}"
        return rec

    rec["score"]        = parse_score(text)
    rec["verdict_text"] = text
    rec["cost_usd"]     = round(estimate_cost(rec["judge_model"], usage), 6)
    rec["elapsed_s"]    = elapsed
    rec["in_tokens"]    = usage["prompt_tokens"]
    rec["out_tokens"]   = usage["completion_tokens"]
    return rec


# ============================================================================
# Reporting
# ============================================================================

def write_jsonl(path: Path, rows: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def write_csv(path: Path, rows: list[dict], cols: list[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows: w.writerow(r)


def build_summary_rows(cells: list[dict], judge_records: list[dict]) -> list[dict]:
    """One row per cell with full ladder verdict."""
    # Index judge records by (cell unique key, judge_kind)
    def cell_key(r):
        return (r["problem_id"], r["model_short"], r["mode_or_n"], r["reasoning"],
                r["source_experiment"], r["branch_idx"])

    by_cell: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for r in judge_records:
        kind = "v4pro" if r["judge"] == "v4pro_validation" else "nano"
        by_cell[cell_key(r)][kind] = r

    rows = []
    for c in cells:
        ck = (c["problem_id"], c["model_short"], c["mode_or_n"], c["reasoning"],
              c["source_experiment"], c["branch_idx"])
        v4p_rec  = by_cell[ck].get("v4pro")
        nano_rec = by_cell[ck].get("nano")

        v4pro_score = (v4p_rec["score"] if v4p_rec else c["orig_v4pro_score"])
        v4pro_validated = (v4pro_score is not None and v4pro_score >= 6)
        nano_score  = nano_rec["score"] if nano_rec else None
        nano_validated = (nano_score is not None and nano_score >= 6)

        rows.append({
            "problem_id":      c["problem_id"],
            "difficulty":      c["difficulty"],
            "difficulty_label":c["difficulty_label"],
            "model_short":     c["model_short"],
            "mode_or_n":       c["mode_or_n"],
            "reasoning":       c["reasoning"],
            "source_experiment": c["source_experiment"],
            "branch_idx":      c["branch_idx"],
            "had_v4flash_solve": (c["orig_v4flash_score"] is not None and c["orig_v4flash_score"] >= 6),
            "had_v4pro_solve":   (c["orig_v4pro_score"]   is not None and c["orig_v4pro_score"]   >= 6),
            "v4pro_score":     v4pro_score,
            "v4pro_validated": v4pro_validated,
            "v4pro_source":    "cached_existing" if (v4p_rec is None and v4pro_score is not None) else ("regrade_call" if v4p_rec else "no_call"),
            "nano_score":      nano_score,
            "nano_validated":  nano_validated,
            "solution_text_hash": c["solution_text_hash"],
        })
    return rows


def write_report(out_path: Path, cells: list[dict], summary: list[dict],
                 judge_records: list[dict], total_cost: float, args):
    """Write a markdown report mirroring v4 §5.5."""
    n_v4f_solves = sum(1 for s in summary if s["had_v4flash_solve"])
    n_orig_v4p   = sum(1 for s in summary if s["had_v4pro_solve"])
    n_v4p_valid  = sum(1 for s in summary if s["v4pro_validated"])
    n_nano_valid = sum(1 for s in summary if s["nano_validated"])

    arch_summary = [s for s in summary if any(c["bucket"]=="architecture" and c["problem_id"]==s["problem_id"]
                                              and c["model_short"]==s["model_short"]
                                              and c["mode_or_n"]==s["mode_or_n"]
                                              and c["reasoning"]==s["reasoning"]
                                              and c["source_experiment"]==s["source_experiment"]
                                              and c["branch_idx"]==s["branch_idx"] for c in cells)]
    sc_summary   = [s for s in summary if s not in arch_summary]

    def cnt(rows, key):
        return sum(1 for r in rows if r[key])

    lines = []
    lines.append(f"# R26 Strict-Solve Cascade Validation\n")
    lines.append(f"_Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}; mode={'MOCK' if args.mock else 'REAL'}_\n")
    lines.append("")
    lines.append("## Headline ladder")
    lines.append("")
    lines.append(f"- **Stage 0 (v4-flash strict)**: {n_v4f_solves} R26 cells solved (v4-flash score ≥6)")
    lines.append(f"- **Stage 1 (v4-pro validation)**: {n_v4p_valid} cells survive (v4-pro score ≥6)")
    lines.append(f"- **Stage 2 (GPT-5.4-nano-xhigh validation)**: {n_nano_valid} cells survive all three rungs")
    lines.append("")
    lines.append(f"Existing v4-pro ≥6 grades present before re-grading: **{n_orig_v4p}**.")
    lines.append("")
    lines.append(f"Total candidate cells evaluated (v4-flash≥6 OR v4-pro≥6): **{len(summary)}**")
    lines.append(f"Total judge-call cost: **${total_cost:.4f}**")
    lines.append("")

    # Per-bucket
    lines.append("## Per-bucket counts")
    lines.append("")
    lines.append("| Bucket        | Cells | v4flash≥6 | v4pro≥6 (orig) | v4pro validated | nano validated |")
    lines.append("|---------------|-------|-----------|----------------|------------------|-----------------|")
    lines.append(f"| architecture  | {len(arch_summary):5} | {cnt(arch_summary,'had_v4flash_solve'):9} | {cnt(arch_summary,'had_v4pro_solve'):14} | {cnt(arch_summary,'v4pro_validated'):16} | {cnt(arch_summary,'nano_validated'):15} |")
    lines.append(f"| scaling       | {len(sc_summary):5}   | {cnt(sc_summary,'had_v4flash_solve'):9} | {cnt(sc_summary,'had_v4pro_solve'):14} | {cnt(sc_summary,'v4pro_validated'):16} | {cnt(sc_summary,'nano_validated'):15} |")
    lines.append("")

    # Per-problem table
    lines.append("## Per-problem ladder (counts of cells)")
    lines.append("")
    lines.append("| problem_id | v4flash≥6 | v4pro validated | nano validated |")
    lines.append("|------------|-----------|------------------|-----------------|")
    by_pid = defaultdict(list)
    for s in summary: by_pid[s["problem_id"]].append(s)
    for pid in sorted(by_pid):
        rows = by_pid[pid]
        lines.append(f"| {pid} | {cnt(rows,'had_v4flash_solve')} | {cnt(rows,'v4pro_validated')} | {cnt(rows,'nano_validated')} |")
    lines.append("")

    # Per-model table
    lines.append("## Per-model ladder (counts of cells)")
    lines.append("")
    lines.append("| model_short | v4flash≥6 | v4pro validated | nano validated |")
    lines.append("|-------------|-----------|------------------|-----------------|")
    by_mod = defaultdict(list)
    for s in summary: by_mod[s["model_short"]].append(s)
    for m in sorted(by_mod):
        rows = by_mod[m]
        lines.append(f"| {m} | {cnt(rows,'had_v4flash_solve')} | {cnt(rows,'v4pro_validated')} | {cnt(rows,'nano_validated')} |")
    lines.append("")

    # Cells surviving all 3 rungs
    survivors = [s for s in summary if s["had_v4flash_solve"] and s["v4pro_validated"] and s["nano_validated"]]
    lines.append(f"## Cells surviving all three rungs (v4flash≥6 ∧ v4pro≥6 ∧ nano≥6): {len(survivors)}")
    lines.append("")
    lines.append("| problem_id | model_short | mode_or_n | reasoning | source | v4flash | v4pro | nano |")
    lines.append("|------------|-------------|-----------|-----------|--------|---------|-------|------|")
    for s in sorted(survivors, key=lambda r: (r["problem_id"], r["model_short"], r["mode_or_n"])):
        # find orig v4flash from cell
        v4f_orig = next((c["orig_v4flash_score"] for c in cells
                         if (c["problem_id"], c["model_short"], c["mode_or_n"], c["reasoning"],
                             c["source_experiment"], c["branch_idx"])
                         == (s["problem_id"], s["model_short"], s["mode_or_n"], s["reasoning"],
                             s["source_experiment"], s["branch_idx"])), None)
        lines.append(f"| {s['problem_id']} | {s['model_short']} | {s['mode_or_n']} | {s['reasoning']} | {s['source_experiment']} | {v4f_orig} | {s['v4pro_score']} | {s['nano_score']} |")
    lines.append("")

    # Disagreements: cells with v4flash≥6 but v4pro<6 or v4pro≥6 but nano<6
    flash_pro_disagree = [s for s in summary if s["had_v4flash_solve"] and not s["v4pro_validated"]]
    pro_nano_disagree  = [s for s in summary if s["v4pro_validated"] and s["nano_score"] is not None and s["nano_score"] < 6]
    lines.append(f"## Disagreements")
    lines.append("")
    lines.append(f"- v4flash passed but v4pro rejected: **{len(flash_pro_disagree)}**")
    lines.append(f"- v4pro validated but nano rejected: **{len(pro_nano_disagree)}**")
    lines.append("")
    if flash_pro_disagree:
        lines.append("### v4flash≥6 but v4pro<6")
        lines.append("")
        lines.append("| problem_id | model_short | mode_or_n | reasoning | source | v4flash | v4pro |")
        lines.append("|------------|-------------|-----------|-----------|--------|---------|-------|")
        for s in sorted(flash_pro_disagree, key=lambda r: (r["problem_id"], r["model_short"])):
            v4f_orig = next((c["orig_v4flash_score"] for c in cells
                             if (c["problem_id"], c["model_short"], c["mode_or_n"], c["reasoning"],
                                 c["source_experiment"], c["branch_idx"])
                             == (s["problem_id"], s["model_short"], s["mode_or_n"], s["reasoning"],
                                 s["source_experiment"], s["branch_idx"])), None)
            lines.append(f"| {s['problem_id']} | {s['model_short']} | {s['mode_or_n']} | {s['reasoning']} | {s['source_experiment']} | {v4f_orig} | {s['v4pro_score']} |")
        lines.append("")
    if pro_nano_disagree:
        lines.append("### v4pro validated but nano<6")
        lines.append("")
        lines.append("| problem_id | model_short | mode_or_n | reasoning | source | v4pro | nano |")
        lines.append("|------------|-------------|-----------|-----------|--------|-------|------|")
        for s in sorted(pro_nano_disagree, key=lambda r: (r["problem_id"], r["model_short"])):
            lines.append(f"| {s['problem_id']} | {s['model_short']} | {s['mode_or_n']} | {s['reasoning']} | {s['source_experiment']} | {s['v4pro_score']} | {s['nano_score']} |")
        lines.append("")

    lines.append("## Methodology notes")
    lines.append("")
    lines.append(f"- Stage 1 judge: `{V4PRO_MODEL}` (extra reasoning_max_tokens=32768; reasoning_content fallback).")
    lines.append(f"- Stage 2 judge: `{NANO_MODEL}` with `reasoning_effort='{NANO_REASONING_EFFORT}'` (xhigh in repo nomenclature).")
    lines.append(f"- Judge prompt: `prompts/pipeline/judge_gt.md` (output restricted to {{0,1,6,7}}).")
    lines.append(f"- Pass threshold: score ≥ 6 (counts both 'almost' (6) and 'correct' (7)).")
    lines.append(f"- For architecture cells already showing v4-pro ≥6 in the bucket data, the existing grade is reused; only cells without a passing v4-pro grade were re-graded ({sum(1 for r in judge_records if r['judge']=='v4pro_validation')} re-grade calls).")
    lines.append(f"- Stage 2 is run for every v4pro-validated cell (including those whose v4-pro grade was pre-existing).")
    lines.append(f"- Scaling cells: validated at the per-branch level (each branch with v4flash ≥6 = one cell).")
    lines.append("")
    lines.append("Source data:")
    lines.append("- `results/architecture_20260506/trials.jsonl`")
    lines.append("- `results/scaling_20260506/trials.jsonl`")
    lines.append("- `results/dataset_20260505.jsonl` (used to look up scaling branch text)")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ============================================================================
# Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="Smoke test, no API calls.")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--skip-preflight-call", action="store_true",
                    help="Skip the single test grading call (use only when iterating).")
    args = ap.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    print("="*80)
    print("validate_research_solves_20260507")
    print("="*80)
    print(f"v4-pro judge: {V4PRO_MODEL}")
    print(f"nano  judge:  {NANO_MODEL}  reasoning_effort={NANO_REASONING_EFFORT}")
    print(f"Workers: {args.workers}    Cost cap: ${HARD_COST_CAP_USD}")
    print(f"Output dir: {OUT_DIR}")
    print(f"Mode: {'MOCK' if args.mock else 'REAL'}")
    print()

    # ---- Step 1: build candidate cell list ----
    cells = build_cells()
    print(f"Built {len(cells)} candidate cells.")
    arch_n = sum(1 for c in cells if c["bucket"]=="architecture")
    sc_n   = sum(1 for c in cells if c["bucket"]=="scaling")
    print(f"  architecture: {arch_n}")
    print(f"  scaling:      {sc_n}")

    # Confirm proof_text non-empty
    empty_text = [c for c in cells if not c["proof_text"]]
    if empty_text:
        print(f"\n[!!] {len(empty_text)} cells have empty proof_text:")
        for c in empty_text:
            print(f"    {c['bucket']:12} {c['problem_id']:30} {c['model_short']:25} mode={c['mode_or_n']}")
        # Skip these; do not abort.
    else:
        print("All cells have non-empty proof_text. ")

    # Decide which cells need v4-pro re-grading
    need_v4pro = [c for c in cells if not (c["orig_v4pro_score"] is not None and c["orig_v4pro_score"] >= 6)]
    have_v4pro = [c for c in cells if (c["orig_v4pro_score"] is not None and c["orig_v4pro_score"] >= 6)]
    print(f"\nStage 1 (v4-pro):")
    print(f"  cells already passing under v4-pro: {len(have_v4pro)} (no re-call)")
    print(f"  cells needing v4-pro re-grade:      {len(need_v4pro)}")

    # Print full cell list for human readability
    print("\n--- Candidate cell list ---")
    for i, c in enumerate(cells):
        v4p_disp = f"{c['orig_v4pro_score']}" if c['orig_v4pro_score'] is not None else "—"
        print(f"  [{i:02}] {c['bucket']:12} {c['problem_id']:30} {c['model_short']:25} "
              f"mode={c['mode_or_n']:25} reas={c['reasoning']:8} src={c['source_experiment']:20} "
              f"v4f={c['orig_v4flash_score']} v4p={v4p_disp}")

    if args.mock:
        print("\n[MOCK] Skipping API calls; producing mock outputs.")
        all_judge_records = []
        for c in need_v4pro:
            all_judge_records.append(grade_one(c, "v4pro", mock=True))
        # Pretend all v4pro cells pass; nano calls fire on every cell (have_v4pro + need_v4pro that mock-pass = all)
        for c in cells:
            all_judge_records.append(grade_one(c, "nano", mock=True))
        cost_tracker = CostTracker(HARD_COST_CAP_USD)
        write_outputs(cells, all_judge_records, cost_tracker.total, args)
        return

    # ---- Step 2: pre-flight test grading on a known-passing cell ----
    if not args.skip_preflight_call:
        # Find an architecture cell that has both v4flash>=6 and v4pro>=6 (existing) — use that for the smoke test
        test_cell = next((c for c in cells if c["orig_v4flash_score"] and c["orig_v4flash_score"] >= 6
                          and c["orig_v4pro_score"] is not None and c["orig_v4pro_score"] >= 6), None)
        if test_cell is None:
            test_cell = cells[0]
        print(f"\n--- Pre-flight: single v4-pro test grade on {test_cell['problem_id']} / {test_cell['model_short']} ---")
        t0 = time.time()
        rec = grade_one(test_cell, "v4pro", mock=False)
        dt = round(time.time() - t0, 1)
        if rec["error"]:
            print(f"[!!] Pre-flight v4-pro call FAILED: {rec['error']}")
            print("Aborting. Inspect error above before retrying.")
            sys.exit(2)
        print(f"  v4-pro returned score={rec['score']} in {dt}s, "
              f"in={rec['in_tokens']} out={rec['out_tokens']} ${rec['cost_usd']:.4f}")
        print(f"  verdict head: {(rec['verdict_text'] or '')[:200]!r}")

        print(f"\n--- Pre-flight: single nano test grade on the same cell ---")
        t0 = time.time()
        rec_nano = grade_one(test_cell, "nano", mock=False)
        dt = round(time.time() - t0, 1)
        if rec_nano["error"]:
            print(f"[!!] Pre-flight nano call FAILED: {rec_nano['error']}")
            print("Aborting.")
            sys.exit(2)
        print(f"  nano returned score={rec_nano['score']} in {dt}s, "
              f"in={rec_nano['in_tokens']} out={rec_nano['out_tokens']} ${rec_nano['cost_usd']:.4f}")
        print(f"  verdict head: {(rec_nano['verdict_text'] or '')[:200]!r}")

        # Capture these as our first two real records (avoid re-spending on the test cell)
        preflight_records = [rec, rec_nano]
        cost_tracker = CostTracker(HARD_COST_CAP_USD)
        cost_tracker.add(rec["cost_usd"])
        cost_tracker.add(rec_nano["cost_usd"])
    else:
        preflight_records = []
        cost_tracker = CostTracker(HARD_COST_CAP_USD)

    # ---- Step 3: parallelize remaining v4-pro then nano calls ----
    all_judge_records: list[dict] = list(preflight_records)
    log_lock = threading.Lock()

    # Build the work list
    # Stage 1: every cell in need_v4pro (minus the preflight test cell if it was v4pro)
    preflight_keys = set()
    for r in preflight_records:
        preflight_keys.add((r["problem_id"], r["model_short"], r["mode_or_n"],
                            r["reasoning"], r["source_experiment"], r["branch_idx"], r["judge"]))

    def cell_judge_key(c, kind): return (c["problem_id"], c["model_short"], c["mode_or_n"],
                                         c["reasoning"], c["source_experiment"], c["branch_idx"],
                                         f"{kind}_validation")

    v4pro_jobs = [c for c in need_v4pro if cell_judge_key(c, "v4pro") not in preflight_keys]
    print(f"\nStage 1: dispatching {len(v4pro_jobs)} v4-pro re-grade calls (workers={args.workers})...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(grade_one, c, "v4pro", False): c for c in v4pro_jobs}
        completed = 0
        for fut in concurrent.futures.as_completed(futs):
            completed += 1
            c = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                rec = {
                    "problem_id":  c["problem_id"], "model_short": c["model_short"],
                    "mode_or_n":   c["mode_or_n"],  "reasoning":   c["reasoning"],
                    "source_experiment": c["source_experiment"], "branch_idx": c["branch_idx"],
                    "judge":       "v4pro_validation",
                    "judge_model": V4PRO_MODEL, "score": None, "verdict_text": None,
                    "cost_usd":    0.0, "elapsed_s": 0.0,
                    "error":       f"future_exception: {e}",
                    "original_v4flash_score": c["orig_v4flash_score"],
                    "original_v4pro_score":   c["orig_v4pro_score"],
                    "solution_text_hash":     c["solution_text_hash"],
                    "in_tokens": None, "out_tokens": None, "from_cache": False,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            with log_lock:
                all_judge_records.append(rec)
                cost_tracker.add(rec.get("cost_usd") or 0.0)
                print(f"  [{completed:02}/{len(v4pro_jobs):02}] v4pro {c['problem_id']:30} "
                      f"{c['model_short']:25} -> score={rec['score']}  "
                      f"cum=${cost_tracker.total:.3f}", flush=True)
            if cost_tracker.aborted:
                print("[!!] Cost cap hit during Stage 1; cancelling remaining v4-pro futures.", flush=True)
                for f in futs:
                    if not f.done(): f.cancel()
                break

    # Build summary so we know which cells are validated
    interim_summary = build_summary_rows(cells, all_judge_records)
    nano_targets = []
    interim_by_key = {(s["problem_id"], s["model_short"], s["mode_or_n"], s["reasoning"],
                       s["source_experiment"], s["branch_idx"]): s for s in interim_summary}
    for c in cells:
        ck = (c["problem_id"], c["model_short"], c["mode_or_n"], c["reasoning"],
              c["source_experiment"], c["branch_idx"])
        s = interim_by_key.get(ck)
        if s is None: continue
        if s["v4pro_validated"]:
            nano_targets.append(c)

    nano_jobs = [c for c in nano_targets if cell_judge_key(c, "nano") not in preflight_keys]

    print(f"\nStage 2: {len(nano_targets)} cells are v4pro-validated; "
          f"dispatching {len(nano_jobs)} nano grade calls (preflight already covered "
          f"{len(nano_targets) - len(nano_jobs)}).")

    if cost_tracker.aborted:
        print("[!!] Skipping Stage 2 because cost cap was hit.", flush=True)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(grade_one, c, "nano", False): c for c in nano_jobs}
            completed = 0
            for fut in concurrent.futures.as_completed(futs):
                completed += 1
                c = futs[fut]
                try:
                    rec = fut.result()
                except Exception as e:
                    rec = {
                        "problem_id":  c["problem_id"], "model_short": c["model_short"],
                        "mode_or_n":   c["mode_or_n"],  "reasoning":   c["reasoning"],
                        "source_experiment": c["source_experiment"], "branch_idx": c["branch_idx"],
                        "judge":       "nano_validation",
                        "judge_model": NANO_MODEL, "score": None, "verdict_text": None,
                        "cost_usd":    0.0, "elapsed_s": 0.0,
                        "error":       f"future_exception: {e}",
                        "original_v4flash_score": c["orig_v4flash_score"],
                        "original_v4pro_score":   c["orig_v4pro_score"],
                        "solution_text_hash":     c["solution_text_hash"],
                        "in_tokens": None, "out_tokens": None, "from_cache": False,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                with log_lock:
                    all_judge_records.append(rec)
                    cost_tracker.add(rec.get("cost_usd") or 0.0)
                    print(f"  [{completed:02}/{len(nano_jobs):02}] nano  {c['problem_id']:30} "
                          f"{c['model_short']:25} -> score={rec['score']}  "
                          f"cum=${cost_tracker.total:.3f}", flush=True)
                if cost_tracker.aborted:
                    print("[!!] Cost cap hit during Stage 2; cancelling remaining nano futures.", flush=True)
                    for f in futs:
                        if not f.done(): f.cancel()
                    break

    print(f"\nDone. Total cost: ${cost_tracker.total:.4f}  Records: {len(all_judge_records)}")
    write_outputs(cells, all_judge_records, cost_tracker.total, args)


def write_outputs(cells, judge_records, total_cost, args):
    # ---- Output: trials.jsonl + trials.csv ----
    write_jsonl(OUT_DIR / "trials.jsonl", judge_records)
    cols = ["problem_id","difficulty","difficulty_label","model_short","mode_or_n","reasoning",
            "source_experiment","branch_idx","judge","judge_model","score",
            "original_v4flash_score","original_v4pro_score",
            "cost_usd","elapsed_s","in_tokens","out_tokens","error","solution_text_hash",
            "completed_at"]
    write_csv(OUT_DIR / "trials.csv", judge_records, cols)

    # ---- Summary CSV ----
    summary = build_summary_rows(cells, judge_records)
    sum_cols = ["problem_id","difficulty","difficulty_label","model_short","mode_or_n","reasoning",
                "source_experiment","branch_idx","had_v4flash_solve","had_v4pro_solve",
                "v4pro_score","v4pro_validated","v4pro_source","nano_score","nano_validated",
                "solution_text_hash"]
    write_csv(OUT_DIR / "summary.csv", summary, sum_cols)

    # ---- Report.md ----
    write_report(OUT_DIR / "report.md", cells, summary, judge_records, total_cost, args)

    print(f"\nOutputs:")
    print(f"  {OUT_DIR / 'trials.jsonl'}")
    print(f"  {OUT_DIR / 'trials.csv'}")
    print(f"  {OUT_DIR / 'summary.csv'}")
    print(f"  {OUT_DIR / 'report.md'}")


if __name__ == "__main__":
    main()
