#!/usr/bin/env python3
"""
v4-flash third-judge regrade across all in-scope 0-7 experiments.

Adds a deepseek-v4-flash judge column on top of every (trial / branch) cell
that already carries gemini-3-flash and/or deepseek-v4-pro scores.  Output is
one JSON file per call, deterministic path, idempotent (re-runs skip cells
with valid scores already on disk).

Hardened call config (per memory feedback_v4pro_judge_calls.md):
  - max_tokens=131072
  - extra_body={"reasoning": {"max_tokens": 100000}}
  - reasoning_content fallback when content is empty

Usage
  uv run experiments/regrade_all_v4flash_20260505.py --mock
  uv run experiments/regrade_all_v4flash_20260505.py --smoke
  uv run experiments/regrade_all_v4flash_20260505.py --max-cost 100
  uv run experiments/regrade_all_v4flash_20260505.py --max-cost 100 --experiments phase1
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import litellm
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from problemset_70 import load_70_problems  # noqa: E402

load_dotenv()
KEY = os.getenv("OPENROUTER_API_KEY_seedgen")
if not KEY:
    raise SystemExit("OPENROUTER_API_KEY_seedgen not set in .env")

ROOT = Path(__file__).parent.parent
PROMPTS = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"

# v4-flash @ $0.28/Mtok input + output (single price tier on OpenRouter)
JUDGE = "openrouter/deepseek/deepseek-v4-flash"
JUDGE_PRICE = 0.28
MAX_TOKENS = 131072
REASONING_BUDGET = 100000
TIMEOUT = 1800
DEFAULT_WORKERS = 40

OUT_DIR_NAME = "v4flash_judge_20260505"
OUT_ROOT = RESULTS_DIR / OUT_DIR_NAME

# Source run dirs
PHASE1_DIR    = RESULTS_DIR / "seed_ideas_full_compare_20260504_20260504_101225"
PHASE2_DIR    = RESULTS_DIR / "seed_full_phase2_20260504_20260505_002924"
PHASE3_DIR    = RESULTS_DIR / "seed_full_v4flash_phase3_20260505_20260505_021635"
ROLESWAP_DIR  = RESULTS_DIR / "seed_full_role_swap_20260505_20260505_032032"
SCALING_DIR   = RESULTS_DIR / "scaling_oss_gemma_20260505_20260505_033250"

# ============================================================================
# Manifest item — the unit of work for the regrade pool
# ============================================================================

@dataclass(frozen=True)
class Item:
    experiment:  str         # phase1 | phase2 | phase3 | roleswap | scaling
    condition:   str         # mode (generate/full/seed_generate/seed_full) OR roleswap label
    model:       str         # full openrouter id (or empty for roleswap which has no per-trial model)
    problem_id:  str
    scope:       str         # "trial" | "branch"
    branch_id:   str         # "" for trial; for branch: "k0".."k6" or "idea0".."idea2"
    candidate:   str         # solution text to judge
    out_path:    Path        # where the result JSON should be written


def _short(m: str) -> str:
    return m.split("/")[-1] if m else "_no_model"


def _sol_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16] if s else "empty"


# ============================================================================
# Manifest collectors — one per experiment layout
# ============================================================================

def collect_phase1(problems: dict) -> list[Item]:
    items: list[Item] = []
    if not PHASE1_DIR.exists():
        print(f"[WARN] phase1 dir missing: {PHASE1_DIR}")
        return items
    for mode in ("generate", "full", "seed_generate"):
        for model_dir in sorted((PHASE1_DIR / mode).iterdir() if (PHASE1_DIR / mode).exists() else []):
            if not model_dir.is_dir(): continue
            for trial_path in sorted(model_dir.glob("*.json")):
                pid = trial_path.stem
                try:
                    t = json.load(open(trial_path))
                except Exception:
                    continue
                if t.get("error") or not t.get("best_solution"):
                    continue
                model = t["model"]

                # Trial-level (best_solution)
                items.append(Item(
                    experiment="phase1", condition=mode, model=model, problem_id=pid,
                    scope="trial", branch_id="",
                    candidate=t["best_solution"],
                    out_path=OUT_ROOT / "phase1" / mode / _short(model) / f"{pid}__trial.json",
                ))

                # Per-branch only for generate / seed_generate (full's branch == trial)
                if mode == "full":
                    continue
                for b in t.get("branches", []) or []:
                    if mode == "generate":
                        bid = f"k{b.get('k', 0)}"
                        cand = b.get("solution") or ""
                    else:  # seed_generate
                        bid = f"idea{b.get('idea_idx', 0)}"
                        cand = b.get("solution") or ""
                    if not cand: continue
                    items.append(Item(
                        experiment="phase1", condition=mode, model=model, problem_id=pid,
                        scope="branch", branch_id=bid, candidate=cand,
                        out_path=OUT_ROOT / "phase1" / mode / _short(model) / f"{pid}__{bid}.json",
                    ))
    return items


def collect_phase2(problems: dict) -> list[Item]:
    items: list[Item] = []
    base = PHASE2_DIR / "seed_full"
    if not base.exists():
        print(f"[WARN] phase2 dir missing: {base}")
        return items
    for model_dir in sorted(base.iterdir()):
        if not model_dir.is_dir(): continue
        for trial_path in sorted(model_dir.glob("*.json")):
            pid = trial_path.stem
            try:
                t = json.load(open(trial_path))
            except Exception:
                continue
            if t.get("error") or not t.get("best_solution"):
                continue
            model = t["model"]

            items.append(Item(
                experiment="phase2", condition="seed_full", model=model, problem_id=pid,
                scope="trial", branch_id="", candidate=t["best_solution"],
                out_path=OUT_ROOT / "phase2" / _short(model) / f"{pid}__trial.json",
            ))
            for b in t.get("branches", []) or []:
                bid = f"idea{b.get('idea_idx', 0)}"
                cand = b.get("final_solution") or b.get("solution") or ""
                if not cand: continue
                items.append(Item(
                    experiment="phase2", condition="seed_full", model=model, problem_id=pid,
                    scope="branch", branch_id=bid, candidate=cand,
                    out_path=OUT_ROOT / "phase2" / _short(model) / f"{pid}__{bid}.json",
                ))
    return items


def collect_phase3(problems: dict) -> list[Item]:
    items: list[Item] = []
    base = PHASE3_DIR / "seed_full" / "deepseek-v4-flash"
    if not base.exists():
        print(f"[WARN] phase3 dir missing: {base}")
        return items
    for trial_path in sorted(base.glob("*.json")):
        pid = trial_path.stem
        try:
            t = json.load(open(trial_path))
        except Exception:
            continue
        if t.get("error") or not t.get("best_solution"):
            continue
        model = t["model"]

        items.append(Item(
            experiment="phase3", condition="seed_full", model=model, problem_id=pid,
            scope="trial", branch_id="", candidate=t["best_solution"],
            out_path=OUT_ROOT / "phase3" / f"{pid}__trial.json",
        ))
        for b in t.get("branches", []) or []:
            bid = f"idea{b.get('idea_idx', 0)}"
            cand = b.get("final_solution") or b.get("solution") or ""
            if not cand: continue
            items.append(Item(
                experiment="phase3", condition="seed_full", model=model, problem_id=pid,
                scope="branch", branch_id=bid, candidate=cand,
                out_path=OUT_ROOT / "phase3" / f"{pid}__{bid}.json",
            ))
    return items


def collect_roleswap(problems: dict) -> list[Item]:
    items: list[Item] = []
    base = ROLESWAP_DIR / "trials"
    if not base.exists():
        print(f"[WARN] roleswap dir missing: {base}")
        return items
    for cond_dir in sorted(base.iterdir()):
        if not cond_dir.is_dir(): continue
        condition = cond_dir.name
        for trial_path in sorted(cond_dir.glob("*.json")):
            pid = trial_path.stem
            try:
                t = json.load(open(trial_path))
            except Exception:
                continue
            if t.get("error") or not t.get("best_solution"):
                continue
            # roleswap trials have no top-level "model" — store the roles dict instead
            roles = t.get("roles") or {}
            primary = roles.get("generator") or ""

            items.append(Item(
                experiment="roleswap", condition=condition, model=primary, problem_id=pid,
                scope="trial", branch_id="", candidate=t["best_solution"],
                out_path=OUT_ROOT / "roleswap" / condition / f"{pid}__trial.json",
            ))
            for b in t.get("branches", []) or []:
                bid = f"idea{b.get('idea_idx', 0)}"
                cand = b.get("final_solution") or b.get("solution") or ""
                if not cand: continue
                items.append(Item(
                    experiment="roleswap", condition=condition, model=primary, problem_id=pid,
                    scope="branch", branch_id=bid, candidate=cand,
                    out_path=OUT_ROOT / "roleswap" / condition / f"{pid}__{bid}.json",
                ))
    return items


def collect_scaling(problems: dict) -> list[Item]:
    items: list[Item] = []
    base = SCALING_DIR / "trials"
    if not base.exists():
        print(f"[WARN] scaling dir missing: {base}")
        return items
    for model_dir in sorted(base.iterdir()):
        if not model_dir.is_dir(): continue
        model_short = model_dir.name
        for trial_path in sorted(model_dir.glob("*.json")):
            pid = trial_path.stem
            try:
                t = json.load(open(trial_path))
            except Exception:
                continue
            model = t.get("model", "")
            for b in t.get("branches", []) or []:
                k = b.get("k")
                cand = b.get("solution") or ""
                if k is None or not cand: continue
                bid = f"k{k}"
                items.append(Item(
                    experiment="scaling", condition="best_of_n", model=model,
                    problem_id=pid, scope="branch", branch_id=bid, candidate=cand,
                    out_path=OUT_ROOT / "scaling" / model_short / f"{pid}__{bid}.json",
                ))
    return items


COLLECTORS = {
    "phase1":   collect_phase1,
    "phase2":   collect_phase2,
    "phase3":   collect_phase3,
    "roleswap": collect_roleswap,
    "scaling":  collect_scaling,
}


# ============================================================================
# Idempotency: skip items whose output already exists with a parsed score
# ============================================================================

def already_done(out_path: Path) -> bool:
    if not out_path.exists():
        return False
    try:
        d = json.load(open(out_path))
    except Exception:
        return False
    return d.get("v4flash_score") is not None and d.get("has_tag", False)


# ============================================================================
# Score parsing
# ============================================================================

def parse_score(text: str) -> tuple[int | None, bool]:
    """Return (score, has_tag).  has_tag means the canonical <points>X out of 7</points> was emitted."""
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text or "", re.I)
    if m:
        return int(m.group(1)), True
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text or "", re.I)
    if m:
        return int(m.group(1)), False
    return None, False


# ============================================================================
# Cost tracking
# ============================================================================

class CostTracker:
    def __init__(self, cap: float | None):
        self.cap = cap
        self.cum = 0.0
        self._lock = threading.Lock()
        self._aborted = False
        self.in_tokens = 0
        self.out_tokens = 0

    def add(self, cost: float, in_tok: int, out_tok: int) -> None:
        with self._lock:
            self.cum += cost
            self.in_tokens += in_tok
            self.out_tokens += out_tok
            if self.cap is not None and self.cum >= self.cap and not self._aborted:
                self._aborted = True
                print(
                    f"[KILLSWITCH] cum cost ${self.cum:.2f} >= cap ${self.cap}. "
                    f"No new tasks will be submitted; in-flight tasks will finish.",
                    flush=True,
                )

    def aborted(self) -> bool:
        with self._lock:
            return self._aborted


# ============================================================================
# Worker
# ============================================================================

JUDGE_PROMPT_CACHE: str | None = None
def get_judge_prompt() -> str:
    global JUDGE_PROMPT_CACHE
    if JUDGE_PROMPT_CACHE is None:
        JUDGE_PROMPT_CACHE = (PROMPTS / "judge_gt.md").read_text(encoding="utf-8").strip()
    return JUDGE_PROMPT_CACHE


def regrade_one(item: Item, problems: dict, tracker: CostTracker, mock: bool) -> dict:
    pid = item.problem_id
    prob = problems.get(pid)
    if not prob:
        return {"item": item, "error": f"unknown problem_id {pid}"}

    user = (get_judge_prompt()
            .replace("{problem}", prob["text"])
            .replace("{ground_truth}", prob["ground_truth"])
            .replace("{candidate}", item.candidate))

    t0 = time.time()
    if mock:
        text = "<points>4 out of 7</points>\nMock verdict."
        in_tok, out_tok = 5000, 500
        score, has_tag = parse_score(text)
        cost = 0.0
        elapsed = 0.01
        status = "mock"
    else:
        try:
            resp = litellm.completion(
                model=JUDGE,
                messages=[{"role": "user", "content": user}],
                max_tokens=MAX_TOKENS,
                extra_body={"reasoning": {"max_tokens": REASONING_BUDGET}},
                api_key=KEY,
                timeout=TIMEOUT,
            )
            msg = resp.choices[0].message
            text = msg.content
            if not text:
                text = getattr(msg, "reasoning_content", "") or ""
            usage = getattr(resp, "usage", None)
            in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
            out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
            score, has_tag = parse_score(text)
            cost = JUDGE_PRICE * (in_tok + out_tok) / 1_000_000
            tracker.add(cost, in_tok, out_tok)
            elapsed = round(time.time() - t0, 1)
            status = "ok" if has_tag else ("salvage" if score is not None else "parse_failed")
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            return {"item": item, "error": str(e), "elapsed_s": elapsed}

    record = {
        "experiment":    item.experiment,
        "condition":     item.condition,
        "model":         item.model,
        "problem_id":    pid,
        "scope":         item.scope,
        "branch_id":     item.branch_id,
        "candidate_hash": _sol_hash(item.candidate),
        "candidate_len": len(item.candidate),
        "v4flash_score": score,
        "v4flash_verdict": text,
        "has_tag":       has_tag,
        "in_tokens":     in_tok,
        "out_tokens":    out_tok,
        "cost_usd":      round(cost, 6),
        "elapsed_s":     elapsed,
        "status":        status,
        "completed_at":  datetime.now(timezone.utc).isoformat(),
    }
    item.out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = item.out_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    tmp.replace(item.out_path)

    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] {item.experiment:<8} {item.condition:<14} "
        f"{_short(item.model)[:18]:<18} {pid:<28} {item.scope:<6} {item.branch_id:<6} "
        f"score={score!s:<4} tag={'Y' if has_tag else 'N'} ${cost:.4f} cum=${tracker.cum:.2f} "
        f"out={out_tok:>5} {elapsed}s",
        flush=True,
    )
    return record


# ============================================================================
# Main runner
# ============================================================================

def run(items: list[Item], problems: dict, tracker: CostTracker, workers: int, mock: bool) -> None:
    pending = [it for it in items if not already_done(it.out_path)]
    skipped = len(items) - len(pending)
    print(f"\nTotal items: {len(items)}  pending: {len(pending)}  already-done: {skipped}\n", flush=True)
    if not pending:
        return

    completed = 0
    last_print = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        for it in pending:
            if tracker.aborted():
                print(f"[KILLSWITCH] not submitting remaining {len(pending) - len(futs)} items", flush=True)
                break
            futs[ex.submit(regrade_one, it, problems, tracker, mock)] = it

        for fut in concurrent.futures.as_completed(futs):
            completed += 1
            try:
                fut.result()
            except Exception as e:
                print(f"  worker exception: {e}", flush=True)
            now = time.time()
            if completed % 25 == 0 or (now - last_print) > 60:
                print(
                    f"[progress] {completed}/{len(pending)}  cum=${tracker.cum:.2f}  "
                    f"in={tracker.in_tokens:,} out={tracker.out_tokens:,}",
                    flush=True,
                )
                last_print = now


def audit(items: list[Item]) -> None:
    """Post-run audit: count parse failures across the saved JSONs."""
    n_total = 0; n_ok = 0; n_salvage = 0; n_parse_fail = 0; n_error = 0; n_missing = 0
    for it in items:
        if not it.out_path.exists():
            n_missing += 1
            continue
        try:
            d = json.load(open(it.out_path))
        except Exception:
            n_error += 1
            continue
        n_total += 1
        if d.get("status") == "ok": n_ok += 1
        elif d.get("status") == "salvage": n_salvage += 1
        elif d.get("status") == "parse_failed": n_parse_fail += 1
        else: n_error += 1
    print("\n" + "="*70)
    print("AUDIT")
    print("="*70)
    print(f"  total items:       {len(items)}")
    print(f"  saved:             {n_total}")
    print(f"  ok (has tag):      {n_ok}")
    print(f"  salvage (regex):   {n_salvage}")
    print(f"  parse_failed:      {n_parse_fail}")
    print(f"  error/unparseable: {n_error}")
    print(f"  missing/skipped:   {n_missing}")
    rate = (n_parse_fail + n_error) / max(n_total, 1) * 100
    print(f"  parse-failure rate: {rate:.2f}%")


# ============================================================================
# CLI
# ============================================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true", help="No API calls; emit fake records.")
    p.add_argument("--smoke", action="store_true", help="Real API; ~10 cells across all experiments.")
    p.add_argument("--max-cost", type=float, default=None, help="Cumulative cost killswitch.")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    p.add_argument("--experiments", nargs="+",
                   default=list(COLLECTORS.keys()),
                   choices=list(COLLECTORS.keys()),
                   help="Subset of experiments to regrade.")
    args = p.parse_args()

    print(f"Output dir: {OUT_ROOT}")
    print(f"Experiments: {args.experiments}")
    if args.max_cost:
        print(f"Cost cap:    ${args.max_cost}")
    print(f"Workers:     {args.workers}")
    print(f"Mock:        {args.mock}    Smoke: {args.smoke}\n")

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    problems = load_70_problems()

    items: list[Item] = []
    for exp in args.experiments:
        sub = COLLECTORS[exp](problems)
        items.extend(sub)
        print(f"  {exp:<10} -> {len(sub)} items")

    if args.smoke:
        # Sample 2 trial-level items per experiment for a quick real-API smoke
        smoke: list[Item] = []
        for exp in args.experiments:
            sub = [it for it in items if it.experiment == exp and it.scope == "trial"]
            smoke.extend(sub[:2])
        items = smoke
        print(f"\n[SMOKE MODE] reduced to {len(items)} items")

    tracker = CostTracker(args.max_cost)
    run(items, problems, tracker, args.workers, args.mock)
    audit(items)
    print(
        f"\nFinal cum cost: ${tracker.cum:.2f}  "
        f"tokens in={tracker.in_tokens:,} out={tracker.out_tokens:,}",
    )


if __name__ == "__main__":
    main()
