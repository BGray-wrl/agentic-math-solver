"""Split results/dataset_20260505.jsonl into 3 thematic bucket sub-datasets.

Buckets (each gets its own subdir under results/, mirroring the layout used by
results/answerbench_calibration_20260506/):

  architecture_20260506/  cross-mode, cross-model architecture comparison
  scaling_20260506/       best-of-N curves with bootstrap-resampled pass@n
  roleswap_20260506/      cross-model role-assignment matrix

Each bucket dir contains:
  trials.jsonl         — long-format rows, one JSON object per line
  trials.csv           — flat tabular view, canonical judge column = v4flash
  summary.csv          — wide aggregate, one row per group key
  data_dictionary.md   — column-by-column schema doc
  report.md            — narrative findings

Inputs: results/dataset_20260505.jsonl (the master union archive).
No new inference is performed — this is a pure transform.

Cross-cutting enrichments:
  difficulty  (int 0-5) + difficulty_label + difficulty_provenance
              from experiments/difficulty_20260506.py
  reasoning   ∈ {"default", "max", "min"} — the user's intended semantics:
              every row was either default, max-effort, or min-effort.
              "min" is reserved (no in-scope row uses it today).
  is_26_research (bool) — True for the 10 problems in the 2026 research-tier
              set (renamed from is_special_10).
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).parent.parent
MASTER = ROOT / "results" / "dataset_20260505.jsonl"
RESULTS = ROOT / "results"

sys.path.insert(0, str(ROOT / "experiments"))
from difficulty_20260506 import LABELS as D_LABELS, annotate as diff_annotate, FRONTIER_DIFFICULTY  # noqa: E402

PASS_THRESHOLD = 6


# ============================================================================
# Reasoning labelling — see plan: reasoning ∈ {default, max, min}
# ============================================================================
REASONING_OVERRIDES = {
    "phase1_reasoning":   "max",
    "roleswap_reasoning": "max",
    "scaling_reasoning":  "max",
    "gpt5_nano_pass3":    "max",
}


def reasoning_for(experiment: str) -> str:
    return REASONING_OVERRIDES.get(experiment, "default")


# ============================================================================
# Helpers
# ============================================================================
def model_short(model: str | None) -> str:
    if not model:
        return ""
    return model.split("/")[-1]


def _judge_score(j: dict | None, key: str) -> int | None:
    if not j:
        return None
    sub = j.get(key) or {}
    s = sub.get("score")
    return int(s) if isinstance(s, int) else None


def enrich(row: dict) -> dict:
    """Add cross-cutting fields. Returns a new shallow copy."""
    pid = row["problem_id"]
    ann = diff_annotate(pid, row.get("level"))
    out = dict(row)
    out["difficulty"] = ann["difficulty"]
    out["difficulty_label"] = ann["difficulty_label"]
    out["difficulty_provenance"] = ann["difficulty_provenance"]
    out["reasoning"] = reasoning_for(row["experiment"])
    out["is_26_research"] = pid in FRONTIER_DIFFICULTY
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in columns})


def safe_mean(xs):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 4) if xs else None


def safe_pstdev(xs):
    xs = [x for x in xs if x is not None]
    return round(pstdev(xs), 4) if len(xs) >= 2 else 0.0 if xs else None


def pass_rate(scores, threshold=PASS_THRESHOLD):
    valid = [s for s in scores if s is not None]
    if not valid:
        return None
    return round(sum(1 for s in valid if s >= threshold) / len(valid), 4)


# ============================================================================
# Master-row loader (with enrichment)
# ============================================================================
def load_master() -> list[dict]:
    rows = []
    with MASTER.open() as f:
        for line in f:
            rows.append(enrich(json.loads(line)))
    return rows


# ============================================================================
# Bucket 1 — architecture
# ============================================================================
ARCH_EXPS = {"phase1", "phase1_reasoning", "phase2", "phase3", "gpt5_nano_pass3"}

ARCH_TRIALS_CSV_COLS = [
    "experiment", "source_experiment", "mode", "condition",
    "model_short", "model_id", "reasoning",
    "problem_id", "level", "difficulty", "difficulty_label", "is_26_research",
    "v4flash_score", "v4flash_pass",
    "v4pro_score", "gemini_score",
    "pass_at_1_v4flash",
    "n_branches", "cost_usd", "elapsed_s", "error",
]

ARCH_SUMMARY_CSV_COLS = [
    "source_experiment", "mode", "model_short", "reasoning",
    "n_trials", "n_valid_v4flash",
    "mean_score_v4flash", "pass_rate_v4flash",
    "mean_score_pre_imo", "mean_score_imo", "mean_score_research",
    "research_solves",
    "mean_cost_usd",
]


def architecture_bucket(rows: list[dict]) -> dict:
    """Build the architecture bucket. Returns dict with rows/csvs/summary."""
    arch_rows = [r for r in rows if r["experiment"] in ARCH_EXPS]

    # Normalise mode column.
    # Master schema:
    #   phase1 condition ∈ {generate, full, seed_generate}
    #   phase1_reasoning condition ∈ {generate, full, seed_full, seed_generate}
    #   phase2 condition = seed_full
    #   phase3 condition = seed_full
    #   gpt5_nano_pass3 condition = pass3_xhigh -> mode "generate" (it is pass@3)
    def _mode_of(r):
        if r["experiment"] == "gpt5_nano_pass3":
            return "generate"
        return r["condition"]

    out_jsonl = []
    out_csv = []

    for r in arch_rows:
        mode = _mode_of(r)
        # derive pass@1 from branches[0] for generate-mode rows
        p1 = None
        bs = r.get("branches") or []
        if mode == "generate" and bs:
            p1 = _judge_score(bs[0].get("judges"), "v4flash")

        v4f = _judge_score(r.get("judges"), "v4flash")
        v4p = _judge_score(r.get("judges"), "v4pro")
        gem = _judge_score(r.get("judges"), "gemini")

        flat = {
            "experiment": "architecture",
            "source_experiment": r["experiment"],
            "mode": mode,
            "condition": r["condition"],
            "model_id": r["model"],
            "model_short": model_short(r["model"]),
            "reasoning": r["reasoning"],
            "problem_id": r["problem_id"],
            "level": r.get("level"),
            "difficulty": r["difficulty"],
            "difficulty_label": r["difficulty_label"],
            "difficulty_provenance": r.get("difficulty_provenance"),
            "is_26_research": r["is_26_research"],
            "v4flash_score": v4f,
            "v4flash_pass": (v4f >= PASS_THRESHOLD) if v4f is not None else None,
            "v4pro_score": v4p,
            "gemini_score": gem,
            "pass_at_1_v4flash": p1,
            "n_branches": len(bs),
            "cost_usd": r.get("cost_usd"),
            "elapsed_s": r.get("elapsed_s"),
            "error": r.get("error"),
        }
        out_csv.append(flat)

        # JSONL row keeps everything: enriched fields + nested branches/judges/mode_extras.
        jr = dict(r)
        jr["mode"] = mode
        jr["pass_at_1_v4flash"] = p1
        out_jsonl.append(jr)

    # Summary
    groups = defaultdict(list)
    for fr in out_csv:
        key = (fr["source_experiment"], fr["mode"], fr["model_short"], fr["reasoning"])
        groups[key].append(fr)

    summary_rows = []
    for (src, mode, ms, rsn), grp in sorted(groups.items()):
        scores = [g["v4flash_score"] for g in grp]
        valid = [s for s in scores if s is not None]
        pre_imo = [g["v4flash_score"] for g in grp if g["difficulty"] == 0]
        imo = [g["v4flash_score"] for g in grp if g["difficulty"] == 1]
        research = [g["v4flash_score"] for g in grp if (g["difficulty"] or 0) >= 2]
        research_solves = sum(1 for g in grp if (g["difficulty"] or 0) >= 2
                              and g["v4flash_score"] is not None
                              and g["v4flash_score"] >= PASS_THRESHOLD)
        summary_rows.append({
            "source_experiment": src,
            "mode": mode,
            "model_short": ms,
            "reasoning": rsn,
            "n_trials": len(grp),
            "n_valid_v4flash": len(valid),
            "mean_score_v4flash": safe_mean(scores),
            "pass_rate_v4flash": pass_rate(scores),
            "mean_score_pre_imo": safe_mean(pre_imo),
            "mean_score_imo": safe_mean(imo),
            "mean_score_research": safe_mean(research),
            "research_solves": research_solves,
            "mean_cost_usd": safe_mean([g["cost_usd"] for g in grp]),
        })

    return {
        "trials_jsonl": out_jsonl,
        "trials_csv": out_csv,
        "summary": summary_rows,
    }


# ============================================================================
# Bucket 2 — scaling (with bootstrap resampling)
# ============================================================================
SCALING_EXPS = {"scaling", "scaling_reasoning", "scaling_v4flash"}
N_VALUES = (1, 3, 5, 7)

SCALING_TRIALS_CSV_COLS = [
    "experiment", "source_experiment", "model_short", "model_id", "reasoning",
    "problem_id", "level", "difficulty", "difficulty_label", "is_26_research",
    "n", "branches_available", "subsets_used",
    "pass_at_n_mean_v4flash", "pass_at_n_std_v4flash",
    "pass_at_n_pass_rate_v4flash",
    "pass_at_n_mean_v4pro", "pass_at_n_std_v4pro",
    "pass_at_n_mean_gemini", "pass_at_n_std_gemini",
]

SCALING_SUMMARY_CSV_COLS = [
    "source_experiment", "model_short", "reasoning", "n",
    "n_problems",
    "mean_pass_at_n_v4flash", "std_pass_at_n_v4flash",
    "pass_rate_v4flash",
    "mean_score_imo", "mean_score_research", "research_solves",
]


def _resample_pass_at_n(branch_scores: list[int | None], n: int) -> tuple[float | None, float | None, int]:
    """Exhaustive enumeration of all C(M, n) size-n subsets.

    Returns (mean of max-score, pop-std of max-score, n_subsets).
    Subsets containing any None score are skipped to avoid biasing toward 0;
    if that drops us below 1 valid subset we return (None, None, 0).
    """
    M = len(branch_scores)
    if n > M or M == 0:
        return (None, None, 0)
    maxes = []
    for combo in combinations(range(M), n):
        sub = [branch_scores[i] for i in combo]
        if any(s is None for s in sub):
            continue
        maxes.append(max(sub))
    if not maxes:
        return (None, None, 0)
    if len(maxes) == 1:
        return (round(float(maxes[0]), 4), 0.0, 1)
    return (round(mean(maxes), 4), round(pstdev(maxes), 4), len(maxes))


def scaling_bucket(rows: list[dict]) -> dict:
    """Build the scaling bucket. One row per (experiment, model, problem, n)."""
    sc_rows = [r for r in rows if r["experiment"] in SCALING_EXPS]

    out_jsonl = []
    out_csv = []

    for r in sc_rows:
        bs = r.get("branches") or []
        v4f = [_judge_score(b.get("judges"), "v4flash") for b in bs]
        v4p = [_judge_score(b.get("judges"), "v4pro")    for b in bs]
        gem = [_judge_score(b.get("judges"), "gemini")   for b in bs]

        for n in N_VALUES:
            mean_f, std_f, k_subs = _resample_pass_at_n(v4f, n)
            mean_p, std_p, _      = _resample_pass_at_n(v4p, n)
            mean_g, std_g, _      = _resample_pass_at_n(gem, n)

            # pass-rate at threshold 6, computed by checking how many subsets'
            # max-score is >= threshold (equivalent to fraction of subsets that "pass").
            pr = None
            if k_subs > 0:
                hits = 0
                tot = 0
                for combo in combinations(range(len(bs)), n):
                    sub = [v4f[i] for i in combo]
                    if any(s is None for s in sub):
                        continue
                    tot += 1
                    if max(sub) >= PASS_THRESHOLD:
                        hits += 1
                pr = round(hits / tot, 4) if tot else None

            jrow = {
                "experiment": "scaling",
                "source_experiment": r["experiment"],
                "model_id": r["model"],
                "model_short": model_short(r["model"]),
                "reasoning": r["reasoning"],
                "problem_id": r["problem_id"],
                "level": r.get("level"),
                "difficulty": r["difficulty"],
                "difficulty_label": r["difficulty_label"],
                "difficulty_provenance": r.get("difficulty_provenance"),
                "is_26_research": r["is_26_research"],
                "n": n,
                "branches_available": len(bs),
                "subsets_used": k_subs,
                "pass_at_n_mean_v4flash": mean_f,
                "pass_at_n_std_v4flash": std_f,
                "pass_at_n_pass_rate_v4flash": pr,
                "pass_at_n_mean_v4pro": mean_p,
                "pass_at_n_std_v4pro": std_p,
                "pass_at_n_mean_gemini": mean_g,
                "pass_at_n_std_gemini": std_g,
                "branch_scores_v4flash": v4f,
                "branch_scores_v4pro": v4p,
                "branch_scores_gemini": gem,
            }
            out_jsonl.append(jrow)
            out_csv.append(jrow)  # CSV writer will pick the flat columns it needs

    # Summary: group by (source_experiment, model_short, reasoning, n) over all problems.
    groups = defaultdict(list)
    for r in out_csv:
        key = (r["source_experiment"], r["model_short"], r["reasoning"], r["n"])
        groups[key].append(r)

    summary_rows = []
    for (src, ms, rsn, n), grp in sorted(groups.items()):
        means = [g["pass_at_n_mean_v4flash"] for g in grp]
        prs = [g["pass_at_n_pass_rate_v4flash"] for g in grp if g["pass_at_n_pass_rate_v4flash"] is not None]
        imo = [g["pass_at_n_mean_v4flash"] for g in grp if g["difficulty"] == 1]
        research = [g["pass_at_n_mean_v4flash"] for g in grp if (g["difficulty"] or 0) >= 2]
        research_solves = sum(1 for g in grp
                              if (g["difficulty"] or 0) >= 2
                              and g["pass_at_n_mean_v4flash"] is not None
                              and g["pass_at_n_mean_v4flash"] >= PASS_THRESHOLD)
        summary_rows.append({
            "source_experiment": src,
            "model_short": ms,
            "reasoning": rsn,
            "n": n,
            "n_problems": len(grp),
            "mean_pass_at_n_v4flash": safe_mean(means),
            "std_pass_at_n_v4flash": safe_pstdev(means),
            "pass_rate_v4flash": round(mean(prs), 4) if prs else None,
            "mean_score_imo": safe_mean(imo),
            "mean_score_research": safe_mean(research),
            "research_solves": research_solves,
        })

    return {
        "trials_jsonl": out_jsonl,
        "trials_csv": out_csv,
        "summary": summary_rows,
    }


# ============================================================================
# Bucket 3 — roleswap
# ============================================================================
ROLESWAP_EXPS = {"roleswap", "roleswap_reasoning", "flex_cross_ideator"}

ROLESWAP_TRIALS_CSV_COLS = [
    "experiment", "source_experiment", "subclass", "condition", "reasoning",
    "ideator_model", "generator_model", "verifier_model", "reviser_model",
    "model_short", "model_id",
    "problem_id", "level", "difficulty", "difficulty_label", "is_26_research",
    "v4flash_score", "v4flash_pass",
    "v4pro_score", "gemini_score",
    "n_branches", "cost_usd", "elapsed_s", "error",
]

ROLESWAP_SUMMARY_CSV_COLS = [
    "subclass", "condition", "reasoning",
    "ideator_model", "generator_model", "verifier_model", "reviser_model",
    "n_problems", "n_valid_v4flash",
    "mean_score_v4flash", "pass_rate_v4flash",
    "mean_score_imo", "mean_score_research",
    "research_solves",
    "mean_cost_usd",
]


def roleswap_bucket(rows: list[dict]) -> dict:
    rs_rows = [r for r in rows if r["experiment"] in ROLESWAP_EXPS]

    out_jsonl = []
    out_csv = []

    for r in rs_rows:
        me = r.get("mode_extras") or {}
        if r["experiment"] in ("roleswap", "roleswap_reasoning"):
            subclass = "oss_gemma_8cell"
            roles = me.get("roles") or {}
            ideator = roles.get("ideator")
            generator = roles.get("generator")
            verifier = roles.get("verifier")
            reviser = roles.get("reviser")
        elif r["experiment"] == "flex_cross_ideator":
            subclass = "ideator_strength"
            ideator = me.get("ideator_model")
            generator = "openrouter/deepseek/deepseek-v4-flash"
            verifier = generator
            reviser = generator
        else:
            subclass = None
            ideator = generator = verifier = reviser = None

        v4f = _judge_score(r.get("judges"), "v4flash")
        v4p = _judge_score(r.get("judges"), "v4pro")
        gem = _judge_score(r.get("judges"), "gemini")
        bs = r.get("branches") or []

        flat = {
            "experiment": "roleswap",
            "source_experiment": r["experiment"],
            "subclass": subclass,
            "condition": r["condition"],
            "reasoning": r["reasoning"],
            "ideator_model": ideator,
            "generator_model": generator,
            "verifier_model": verifier,
            "reviser_model": reviser,
            "model_id": r["model"],
            "model_short": model_short(r["model"]),
            "problem_id": r["problem_id"],
            "level": r.get("level"),
            "difficulty": r["difficulty"],
            "difficulty_label": r["difficulty_label"],
            "difficulty_provenance": r.get("difficulty_provenance"),
            "is_26_research": r["is_26_research"],
            "v4flash_score": v4f,
            "v4flash_pass": (v4f >= PASS_THRESHOLD) if v4f is not None else None,
            "v4pro_score": v4p,
            "gemini_score": gem,
            "n_branches": len(bs),
            "cost_usd": r.get("cost_usd"),
            "elapsed_s": r.get("elapsed_s"),
            "error": r.get("error"),
        }
        out_csv.append(flat)

        jr = dict(r)
        jr["subclass"] = subclass
        jr["ideator_model"] = ideator
        jr["generator_model"] = generator
        jr["verifier_model"] = verifier
        jr["reviser_model"] = reviser
        out_jsonl.append(jr)

    # Summary
    groups = defaultdict(list)
    for fr in out_csv:
        key = (fr["subclass"], fr["condition"], fr["reasoning"],
               fr["ideator_model"], fr["generator_model"],
               fr["verifier_model"], fr["reviser_model"])
        groups[key].append(fr)

    summary_rows = []
    for key, grp in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        scores = [g["v4flash_score"] for g in grp]
        valid = [s for s in scores if s is not None]
        imo = [g["v4flash_score"] for g in grp if g["difficulty"] == 1]
        research = [g["v4flash_score"] for g in grp if (g["difficulty"] or 0) >= 2]
        research_solves = sum(1 for g in grp if (g["difficulty"] or 0) >= 2
                              and g["v4flash_score"] is not None
                              and g["v4flash_score"] >= PASS_THRESHOLD)
        summary_rows.append({
            "subclass": key[0], "condition": key[1], "reasoning": key[2],
            "ideator_model": key[3], "generator_model": key[4],
            "verifier_model": key[5], "reviser_model": key[6],
            "n_problems": len(grp),
            "n_valid_v4flash": len(valid),
            "mean_score_v4flash": safe_mean(scores),
            "pass_rate_v4flash": pass_rate(scores),
            "mean_score_imo": safe_mean(imo),
            "mean_score_research": safe_mean(research),
            "research_solves": research_solves,
            "mean_cost_usd": safe_mean([g["cost_usd"] for g in grp]),
        })

    return {
        "trials_jsonl": out_jsonl,
        "trials_csv": out_csv,
        "summary": summary_rows,
    }


# ============================================================================
# Doc generation
# ============================================================================
def _difficulty_distribution(csv_rows):
    c = Counter(r.get("difficulty") for r in csv_rows)
    return ", ".join(f"d={k}: {n}" for k, n in sorted(c.items(), key=lambda kv: (kv[0] is None, kv[0])))


def _reasoning_distribution(csv_rows):
    c = Counter(r.get("reasoning") for r in csv_rows)
    return ", ".join(f"{k}: {n}" for k, n in sorted(c.items()))


def _exp_distribution(csv_rows, key="source_experiment"):
    c = Counter(r.get(key) for r in csv_rows)
    return ", ".join(f"{k}: {n}" for k, n in sorted(c.items()))


def write_arch_dict(path: Path) -> None:
    path.write_text("""# Architecture Bucket — Data Dictionary

Cross-mode, cross-model architecture comparison. Sources: phase1, phase1_reasoning,
phase2, phase3, gpt5_nano_pass3 from `results/dataset_20260505.jsonl`.

## Files

- **`trials.jsonl`** — long format, one JSON object per trial. Carries enriched
  rows from the master JSONL (judges{}, branches[], mode_extras), plus the new
  `mode`, `reasoning`, `difficulty`, `is_26_research`, and `pass_at_1_v4flash`
  fields.
- **`trials.csv`** — flat tabular view, canonical judge column = v4flash. Nested
  fields are in the JSONL only.
- **`summary.csv`** — wide aggregate, one row per (source_experiment, mode,
  model_short, reasoning).

## `trials.csv` columns

| Column | Type | Meaning |
|---|---|---|
| `experiment` | str | Always `architecture` for this bucket. |
| `source_experiment` | str | Origin in master: `phase1` / `phase1_reasoning` / `phase2` / `phase3` / `gpt5_nano_pass3`. |
| `mode` | str | Architecture mode: `generate` / `seed_generate` / `full` / `seed_full`. For `gpt5_nano_pass3` (originally `pass3_xhigh`) we normalize to `generate` since it's a pass@3 baseline. |
| `condition` | str | Original master `condition` value (raw). For most rows `mode == condition`; for gpt5_nano_pass3, `condition='pass3_xhigh'` and `mode='generate'`. |
| `model_short` | str | Last path segment, e.g. `gpt-oss-120b`. |
| `model_id` | str | Full OpenRouter model id. |
| `reasoning` | str | One of `default` / `max` / `min`. See README. |
| `problem_id` | str | e.g. `PB-Advanced-001`, `erdos-397`, `ramsey-hypergraphs`. |
| `level` | str | Native ProofBench label or frontier-novelty tag (preserved for granular analysis). |
| `difficulty` | int (0-5) | Unified frontier-emphasis scale. See `experiments/difficulty_20260506.py`. |
| `difficulty_label` | str | Human-readable mirror, e.g. `competition-hard`. |
| `is_26_research` | bool | True for the 10 problems in the 2026 research-tier set. |
| `v4flash_score` | int (0-7) or null | **Canonical judge.** From `judges.v4flash.score` in master. |
| `v4flash_pass` | bool or null | `v4flash_score >= 6`. Null when score is null. |
| `v4pro_score` | int (0-7) or null | Audit judge. |
| `gemini_score` | int (0-7) or null | Audit judge. |
| `pass_at_1_v4flash` | int (0-7) or null | For `mode='generate'` only: v4flash judge score on `branches[0]`. **Correlated with the trial-level pass@3 score** (it is the first sample of pass@3, NOT an independent draw). Surfaces the pass@1→pass@3 delta visually. Null for non-generate rows. |
| `n_branches` | int | Number of branches in the original master row. |
| `cost_usd` | float or null | Wall-cost from master row. |
| `elapsed_s` | float or null | Wall-time from master row. |
| `error` | str or null | Non-null if the trial errored. |

## `summary.csv` columns

| Column | Meaning |
|---|---|
| `source_experiment`, `mode`, `model_short`, `reasoning` | Group key. |
| `n_trials` | Rows in this group. |
| `n_valid_v4flash` | Rows with non-null v4flash_score. |
| `mean_score_v4flash` | Mean over valid v4flash scores (0-7). |
| `pass_rate_v4flash` | Fraction with v4flash_score ≥ 6. |
| `mean_score_pre_imo` | Mean v4flash on difficulty=0 rows. |
| `mean_score_imo` | Mean v4flash on difficulty=1 rows. |
| `mean_score_research` | Mean v4flash on difficulty ≥ 2 rows. |
| `research_solves` | Count of difficulty ≥ 2 rows that scored ≥ 6. |
| `mean_cost_usd` | Mean of per-row cost_usd. |

## Coverage matrix (mode × model)

See `report.md` for the full coverage table. Brief: Phase 1 covers 6 models on
generate / seed_generate / full (NOT seed_full); seed_full only comes from
Phase 2 (gpt-oss + gemma), Phase 3 (v4-flash), and phase1_reasoning (gpt-oss +
gemma reasoning=max). gpt5_nano_pass3 is a 1-cell asymmetric extension on the
generate axis only (gpt-5.4-nano @ reasoning=max).

## Loading recipes

```python
import pandas as pd
df = pd.read_csv("results/architecture_20260506/trials.csv")
# Phase 1 cross-model means at v4-flash judge:
g = df[df.source_experiment == "phase1"].groupby(["model_short", "mode"]).v4flash_score.mean()
```
""")


def write_scaling_dict(path: Path) -> None:
    path.write_text("""# Scaling Bucket — Data Dictionary

Best-of-N scaling curves with **bootstrap-resampled pass@n** instead of nested
prefix pass@n. Sources: scaling, scaling_reasoning, scaling_v4flash from
`results/dataset_20260505.jsonl`.

## Why bootstrap?

The master scaling experiments computed pass@n as `max(scores[:n])` — a
deterministic prefix of branches sorted by k. This makes pass@1 ⊂ pass@3 ⊂
pass@5 ⊂ pass@7, so per-problem trajectories are monotonic by construction and
understate the variance of the estimator. We replace this with **exhaustive
enumeration** of all C(M, n) size-n subsets per (model, problem) and report the
mean and standard deviation of `max(score over subset)`. This is unbiased and
the std is the right error bar.

For M=7 (scaling, scaling_v4flash), n=1/3/5/7 enumerates 7/35/21/1 subsets.
For M=9 (scaling_reasoning), n=1/3/5/7 enumerates 9/84/126/36 subsets.

## Files

- **`trials.jsonl`** — one row per (source_experiment, model, problem, n).
  Carries `branch_scores_v4flash` etc. so any bespoke n-enumeration is
  reproducible.
- **`trials.csv`** — flat tabular view.
- **`summary.csv`** — one row per (source_experiment, model_short, reasoning, n)
  aggregating across problems.

## `trials.csv` columns

| Column | Type | Meaning |
|---|---|---|
| `experiment` | str | Always `scaling`. |
| `source_experiment` | str | `scaling` / `scaling_reasoning` / `scaling_v4flash`. |
| `model_short`, `model_id` | str | Model. |
| `reasoning` | str | `default` for `scaling` and `scaling_v4flash`; `max` for `scaling_reasoning` (it ran with reasoning='high', the user's max-effort choice for those models). |
| `problem_id`, `level`, `difficulty`, `difficulty_label`, `is_26_research` | — | See architecture data dictionary. |
| `n` | int | Subset size for pass@n: one of 1, 3, 5, 7. |
| `branches_available` | int | Total branches generated for this (model, problem). 7 or 9. |
| `subsets_used` | int | C(branches_available, n). |
| `pass_at_n_mean_v4flash` | float or null | Mean of `max(branch v4flash score over subset)` across all C(M,n) subsets. **Canonical metric.** |
| `pass_at_n_std_v4flash` | float or null | Population std of the same. |
| `pass_at_n_pass_rate_v4flash` | float or null | Fraction of subsets whose max-score ≥ 6 (i.e., the "would the trial pass at this n" rate). |
| `pass_at_n_mean_v4pro`, `pass_at_n_std_v4pro` | float | Same for v4pro judge (only `scaling` source has v4pro inline; others null). |
| `pass_at_n_mean_gemini`, `pass_at_n_std_gemini` | float | Same for gemini judge (only `scaling` source has gemini inline; others null). |

## `summary.csv` columns

| Column | Meaning |
|---|---|
| `source_experiment`, `model_short`, `reasoning`, `n` | Group key. |
| `n_problems` | Number of problems in this group at this n. |
| `mean_pass_at_n_v4flash` | Mean across problems of `pass_at_n_mean_v4flash`. |
| `std_pass_at_n_v4flash` | Population std across problems (between-problem variability). |
| `pass_rate_v4flash` | Mean across problems of `pass_at_n_pass_rate_v4flash`. |
| `mean_score_imo` | Restricted to difficulty=1 problems. |
| `mean_score_research` | Restricted to difficulty ≥ 2 problems. |
| `research_solves` | Count of difficulty ≥ 2 problems with mean score ≥ 6 at this n. |

## Loading recipes

```python
import pandas as pd
df = pd.read_csv("results/scaling_20260506/trials.csv")
import seaborn as sns
sns.lineplot(data=df, x="n", y="pass_at_n_mean_v4flash",
             hue="model_short", style="reasoning")
```
""")


def write_roleswap_dict(path: Path) -> None:
    path.write_text("""# Roleswap Bucket — Data Dictionary

Cross-model role-assignment comparison. Sources: roleswap, roleswap_reasoning,
flex_cross_ideator from `results/dataset_20260505.jsonl`.

## Subclasses

| Subclass | Source experiments | Conditions | Roles varied |
|---|---|---|---|
| `oss_gemma_8cell` | roleswap, roleswap_reasoning | random_run1, random_run2, x_ideate_oss, x_ideate_gemma, x_revise_oss, x_revise_gemma, x_verify_oss, x_verify_gemma | gpt-oss-120b vs gemma-4-31b-it across ideator/generator/verifier/reviser; "x_*" = swap that one role to the other model |
| `ideator_strength` | flex_cross_ideator | self_v4flash, vp_v4flash, mini_v4flash | v4-flash held in gen+verify+revise; ideator varied across {v4-flash, v4-pro, gpt-5.4-mini@xhigh} |

**Problem-set asymmetry**: `oss_gemma_8cell` runs on the 70-problem benchmark.
`ideator_strength` runs on a different subset (20 random PB-Advanced problems).
Cross-subclass analysis must filter to overlapping problem IDs.

## Files

- **`trials.jsonl`** — one row per trial, with role columns + subclass.
- **`trials.csv`** — flat tabular view.
- **`summary.csv`** — one row per
  (subclass, condition, reasoning, ideator, generator, verifier, reviser).

## `trials.csv` columns

| Column | Type | Meaning |
|---|---|---|
| `experiment` | str | Always `roleswap`. |
| `source_experiment` | str | `roleswap` / `roleswap_reasoning` / `flex_cross_ideator`. |
| `subclass` | str | `oss_gemma_8cell` or `ideator_strength`. |
| `condition` | str | Original condition label from master. |
| `reasoning` | str | `default` / `max`. |
| `ideator_model`, `generator_model`, `verifier_model`, `reviser_model` | str | Full OpenRouter IDs. |
| `model_short`, `model_id` | str | The trial's "primary" model (the generator). |
| `problem_id`, `level`, `difficulty`, `difficulty_label`, `is_26_research` | — | See architecture data dictionary. |
| `v4flash_score` | int (0-7) or null | Canonical judge. |
| `v4flash_pass`, `v4pro_score`, `gemini_score`, `n_branches`, `cost_usd`, `elapsed_s`, `error` | — | See architecture data dictionary. |

## `summary.csv` columns

| Column | Meaning |
|---|---|
| `subclass`, `condition`, `reasoning`, `ideator_model`, `generator_model`, `verifier_model`, `reviser_model` | Group key. |
| `n_problems` | Rows in this group. |
| `n_valid_v4flash` | Rows with non-null v4flash_score. |
| `mean_score_v4flash` | Mean over valid v4flash scores. |
| `pass_rate_v4flash` | Fraction with v4flash_score ≥ 6. |
| `mean_score_imo` | Mean on difficulty=1 rows. |
| `mean_score_research` | Mean on difficulty ≥ 2 rows. |
| `research_solves` | Count of difficulty ≥ 2 rows that scored ≥ 6. |
| `mean_cost_usd` | Mean of per-row cost_usd. |

## Loading recipes

```python
import pandas as pd
df = pd.read_csv("results/roleswap_20260506/trials.csv")
oss_gemma = df[df.subclass == "oss_gemma_8cell"]
oss_gemma.groupby("condition").v4flash_score.mean().sort_values()
```
""")


# ============================================================================
# Reports — written from already-built data (compact narrative)
# ============================================================================
def fmt(x, prec=2):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{prec}f}"
    return str(x)


def write_arch_report(path: Path, csv_rows, summary_rows) -> None:
    n = len(csv_rows)
    diff_dist = _difficulty_distribution(csv_rows)
    rsn_dist = _reasoning_distribution(csv_rows)
    src_dist = _exp_distribution(csv_rows)

    # mode-by-mode v4flash means (averaged over rows)
    by_mode = defaultdict(list)
    for r in csv_rows:
        if r["v4flash_score"] is not None:
            by_mode[r["mode"]].append(r["v4flash_score"])
    mode_table = "\n".join(
        f"| {m} | {len(by_mode[m])} | {fmt(safe_mean(by_mode[m]))} | {fmt(pass_rate(by_mode[m]))} |"
        for m in ("generate", "seed_generate", "full", "seed_full")
        if m in by_mode
    )

    # delta pass@1 -> pass@3 (architecture column-only): generate-mode rows only
    deltas = []
    for r in csv_rows:
        if r["mode"] == "generate" and r["pass_at_1_v4flash"] is not None and r["v4flash_score"] is not None:
            deltas.append(r["v4flash_score"] - r["pass_at_1_v4flash"])
    delta_str = f"mean Δ = +{safe_mean(deltas):.2f} (n={len(deltas)})" if deltas else "no eligible rows"

    # research-solves leaderboard at v4flash
    by_group = defaultdict(int)
    by_group_n = defaultdict(int)
    for r in csv_rows:
        if (r["difficulty"] or 0) >= 2:
            key = (r["model_short"], r["mode"], r["reasoning"])
            by_group_n[key] += 1
            if r["v4flash_score"] is not None and r["v4flash_score"] >= PASS_THRESHOLD:
                by_group[key] += 1
    leaders = sorted(by_group.items(), key=lambda kv: -kv[1])[:10]
    leader_table = "\n".join(
        f"| {ms} | {mode} | {rsn} | {hits}/{by_group_n[(ms, mode, rsn)]} |"
        for (ms, mode, rsn), hits in leaders
    ) or "| (no research solves at v4flash≥6) | — | — | — |"

    path.write_text(f"""# Architecture Bucket — Report

**{n} trial rows** combining 5 source experiments into a unified architecture
comparison. Canonical judge: deepseek-v4-flash (the recommended judge per the
gradingbench audit, r=0.76 with humans).

## Coverage

- **Source experiments:** {src_dist}
- **Difficulty distribution:** {diff_dist}
- **Reasoning distribution:** {rsn_dist}

## Mode-level means under v4-flash

| Mode | n | mean score (0-7) | pass rate (≥6) |
|---|---:|---:|---:|
{mode_table}

## Pass@1 → pass@3 lift (generate mode only)

`pass_at_1_v4flash` is the v4-flash score on `branches[0]` of pass@3. **It is
the first sample, NOT an independent draw**, so this is a within-trial delta
visualizing the architecture's incremental gain from emitting more samples,
not a clean independent-pass@1 comparison.

{delta_str}

## Research-tier (difficulty ≥ 2) solve leaders at v4flash ≥ 6

| Model | Mode | Reasoning | research solves / opportunities |
|---|---|---|---:|
{leader_table}

## Asymmetry callouts

- **Phase 3** is 1 model × 1 mode (deepseek-v4-flash × seed_full only). Kept as
  a posterity check on a strong judge-tier model running its own pipeline; not
  a primary axis of comparison.
- **gpt5_nano_pass3** is 1 model × 1 mode (gpt-5.4-nano × pass@3 with
  `reasoning_effort='xhigh'`, normalized to `mode='generate'`). Different model
  family from the rest — extends the pass@3 axis but isn't a like-for-like
  comparison with Phase 1's 6 models.

## Coverage matrix (mode × model)

Phase 1 covers 6 models on `generate` / `seed_generate` / `full` only (NO
seed_full). `seed_full` data comes from Phase 2 (gpt-oss + gemma), Phase 3
(v4-flash), and `phase1_reasoning` (gpt-oss + gemma at reasoning=max).

| Mode | Default-reasoning models | Reasoning=max models | Asymmetric |
|---|---|---|---|
| generate | 6 (Phase 1) | gpt-oss + gemma | gpt-5.4-nano (1 cell) |
| seed_generate | 6 (Phase 1) | gpt-oss + gemma | — |
| full | 6 (Phase 1) | gpt-oss + gemma | — |
| seed_full | 3 (gpt-oss, gemma, v4-flash) | gpt-oss + gemma | — |
""")


def write_scaling_report(path: Path, csv_rows, summary_rows) -> None:
    n = len(csv_rows)
    src_dist = _exp_distribution(csv_rows)
    rsn_dist = _reasoning_distribution(csv_rows)

    # Mean pass@n curve, by source_experiment + reasoning
    curve_rows = defaultdict(dict)  # key=(src, model_short, rsn) -> n -> mean
    for s in summary_rows:
        curve_rows[(s["source_experiment"], s["model_short"], s["reasoning"])][s["n"]] = s["mean_pass_at_n_v4flash"]

    curve_md = "| source | model | reasoning | n=1 | n=3 | n=5 | n=7 |\n|---|---|---|---:|---:|---:|---:|\n"
    for k, vals in sorted(curve_rows.items()):
        src, ms, rsn = k
        curve_md += f"| {src} | {ms} | {rsn} | {fmt(vals.get(1))} | {fmt(vals.get(3))} | {fmt(vals.get(5))} | {fmt(vals.get(7))} |\n"

    path.write_text(f"""# Scaling Bucket — Report

**{n} trial rows** = (model, problem, n) cells across 3 source experiments,
with bootstrap-resampled pass@n.

## Coverage

- **Source experiments:** {src_dist}
- **Reasoning distribution:** {rsn_dist}

## Headline scaling curves (v4-flash judge)

Mean across-problems of `pass_at_n_mean_v4flash`. Each cell is exhaustively
enumerated over C(M, n) subsets of the available branches.

{curve_md}

## Methodology note

The original scaling experiments stored branches sorted by k=0..6 and computed
pass@n as `max(scores[:n])` — a deterministic prefix. We replace this with
**exhaustive enumeration of all C(M, n) size-n subsets** per (model, problem):

| M (branches) | n=1 | n=3 | n=5 | n=7 |
|---:|---:|---:|---:|---:|
| 7  | 7   | 35  | 21  | 1   |
| 9  | 9   | 84  | 126 | 36  |

Per-problem pass@n is the mean over all subsets of `max(score over subset)`;
the population std is the right error bar. This is unbiased and avoids the
correlated-trajectory artifact of the nested estimator.

The `pass_at_n_pass_rate_v4flash` column reports the fraction of subsets
whose max-score ≥ 6, i.e. how often the trial would "pass" at this n.

## How to read the std columns

`std_pass_at_n_v4flash` in `summary.csv` is the std **across problems** of
each problem's subset-mean. It tells you between-problem variability of the
scaling estimate at this n. The within-problem subset std is in
`pass_at_n_std_v4flash` per row of `trials.csv`.
""")


def write_roleswap_report(path: Path, csv_rows, summary_rows) -> None:
    n = len(csv_rows)
    src_dist = _exp_distribution(csv_rows)
    rsn_dist = _reasoning_distribution(csv_rows)
    sub_dist = Counter(r["subclass"] for r in csv_rows)

    # 8-cell condition means at v4flash, split by reasoning
    by_cond = defaultdict(list)
    for r in csv_rows:
        if r["subclass"] == "oss_gemma_8cell" and r["v4flash_score"] is not None:
            key = (r["condition"], r["reasoning"])
            by_cond[key].append(r["v4flash_score"])

    cond_md = "| condition | reasoning | n | mean | pass rate |\n|---|---|---:|---:|---:|\n"
    for (cond, rsn), scs in sorted(by_cond.items()):
        cond_md += f"| {cond} | {rsn} | {len(scs)} | {fmt(safe_mean(scs))} | {fmt(pass_rate(scs))} |\n"

    # ideator_strength means
    by_id_cond = defaultdict(list)
    for r in csv_rows:
        if r["subclass"] == "ideator_strength" and r["v4flash_score"] is not None:
            by_id_cond[(r["condition"], r["ideator_model"])].append(r["v4flash_score"])

    id_md = "| condition | ideator_model | n | mean | pass rate |\n|---|---|---:|---:|---:|\n"
    for (cond, im), scs in sorted(by_id_cond.items()):
        id_md += f"| {cond} | {im} | {len(scs)} | {fmt(safe_mean(scs))} | {fmt(pass_rate(scs))} |\n"

    path.write_text(f"""# Roleswap Bucket — Report

**{n} trial rows** combining roleswap + roleswap_reasoning + flex_cross_ideator
into a single cross-model role-assignment comparison.

## Coverage

- **Source experiments:** {src_dist}
- **Reasoning distribution:** {rsn_dist}
- **Subclass distribution:** {dict(sub_dist)}

## Subclass: oss_gemma_8cell

8 conditions × 2 reasoning settings (default / max). Random-baseline
(`random_run1`, `random_run2`) plus 6 single-role-swap conditions.

{cond_md}

## Subclass: ideator_strength

3 conditions, all on a 20-problem PB-Advanced subset (NOT the full 70).
v4-flash held fixed in generator + verifier + reviser; only the ideator varies.

{id_md}

**Caveat:** `ideator_strength` runs on a different problem set than the
`oss_gemma_8cell` subclass. To compare across subclasses you must filter to
overlapping `problem_id`s.

## Reading the role columns

For each trial row, `ideator_model` / `generator_model` / `verifier_model` /
`reviser_model` give the model assigned to that pipeline role. In
`oss_gemma_8cell`, the `condition` label tells you which single role was
swapped: e.g. `x_ideate_oss` means the ideator is `gpt-oss-120b` and all other
roles are `gemma-4-31b-it`. `random_run1` / `random_run2` are seeded
random-assignment baselines.
""")


# ============================================================================
# Main
# ============================================================================
def main():
    print("Loading master JSONL...")
    master = load_master()
    print(f"  {len(master)} rows loaded")
    print(f"  reasoning distribution: {Counter(r['reasoning'] for r in master)}")
    print(f"  is_26_research: {sum(1 for r in master if r['is_26_research'])}")

    # Bucket 1 — architecture
    print("\nBucket 1 — architecture...")
    arch = architecture_bucket(master)
    arch_dir = RESULTS / "architecture_20260506"
    arch_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(arch_dir / "trials.jsonl", arch["trials_jsonl"])
    write_csv(arch_dir / "trials.csv", arch["trials_csv"], ARCH_TRIALS_CSV_COLS)
    write_csv(arch_dir / "summary.csv", arch["summary"], ARCH_SUMMARY_CSV_COLS)
    write_arch_dict(arch_dir / "data_dictionary.md")
    write_arch_report(arch_dir / "report.md", arch["trials_csv"], arch["summary"])
    print(f"  -> {len(arch['trials_jsonl'])} trial rows, {len(arch['summary'])} summary rows")

    # Bucket 2 — scaling
    print("\nBucket 2 — scaling...")
    sc = scaling_bucket(master)
    sc_dir = RESULTS / "scaling_20260506"
    sc_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(sc_dir / "trials.jsonl", sc["trials_jsonl"])
    write_csv(sc_dir / "trials.csv", sc["trials_csv"], SCALING_TRIALS_CSV_COLS)
    write_csv(sc_dir / "summary.csv", sc["summary"], SCALING_SUMMARY_CSV_COLS)
    write_scaling_dict(sc_dir / "data_dictionary.md")
    write_scaling_report(sc_dir / "report.md", sc["trials_csv"], sc["summary"])
    print(f"  -> {len(sc['trials_jsonl'])} trial rows, {len(sc['summary'])} summary rows")

    # Bucket 3 — roleswap
    print("\nBucket 3 — roleswap...")
    rs = roleswap_bucket(master)
    rs_dir = RESULTS / "roleswap_20260506"
    rs_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(rs_dir / "trials.jsonl", rs["trials_jsonl"])
    write_csv(rs_dir / "trials.csv", rs["trials_csv"], ROLESWAP_TRIALS_CSV_COLS)
    write_csv(rs_dir / "summary.csv", rs["summary"], ROLESWAP_SUMMARY_CSV_COLS)
    write_roleswap_dict(rs_dir / "data_dictionary.md")
    write_roleswap_report(rs_dir / "report.md", rs["trials_csv"], rs["summary"])
    print(f"  -> {len(rs['trials_jsonl'])} trial rows, {len(rs['summary'])} summary rows")

    print("\nDone.")


if __name__ == "__main__":
    main()
