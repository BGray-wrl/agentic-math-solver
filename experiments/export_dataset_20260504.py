#!/usr/bin/env python3
"""
Export the seed-ideas Phase 1 + judge-regrade results as a single dataset.

Schema (one record per (problem, model, mode) — 70 × 6 × 3 = 1260 rows):

  Problem
    problem_id, problem_text, ground_truth, category, level, source, is_special_10
  Trial
    model, mode (generate | full | seed_generate)
    started_at, completed_at, elapsed_s, cost_usd, error (null if ok)
  Final solution & both judges' results on it
    final_solution      : full text of best_solution from Phase 1 (v4-pro picked)
    v4pro_score         : 0-7 (or null)
    v4pro_verdict       : full judge text (or null)
    gemini_score        : 0-7 (or null)
    gemini_verdict      : full judge text (or null)
  Branches (one entry per branch — empty for full mode where there's only 1)
    For generate (k=0,1,2): {k, solution, v4_score, v4_verdict, gemini_score, gemini_verdict}
    For seed_generate (3 ideas): {idea_idx, idea, solution, v4_score, v4_verdict,
                                   gemini_score, gemini_verdict}
    For full (1 branch): {k=0, initial_solution, final_solution, v4_score, v4_verdict,
                          loop_log, stopped_early, gemini_score, gemini_verdict}

NAs are explicit (None / null) — we never invent data. Trials that errored have null
solutions / scores / verdicts plus an "error" field.

Output: JSONL at experiments/results/dataset_20260504.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from problemset_70 import load_70_problems, SPECIAL_10  # noqa: E402

PHASE1   = ROOT / "experiments" / "results" / "seed_ideas_full_compare_20260504_20260504_101225"
REGRADE  = ROOT / "experiments" / "results" / "regrade_gemini_20260504_20260504_221221"
BRANCH   = ROOT / "experiments" / "results" / "regrade_branches_gemini_20260504_20260504_222334"

OUT = ROOT / "experiments" / "results" / "dataset_20260504.jsonl"

MODELS_ORD = [
    "openrouter/openai/gpt-oss-120b",
    "openrouter/google/gemma-4-31b-it",
    "openrouter/google/gemini-3-flash-preview",
    "openrouter/deepseek/deepseek-v4-flash",
    "openrouter/deepseek/deepseek-v4-pro",
    "openrouter/qwen/qwen3.6-35b-a3b",
]
MODES = ("generate", "full", "seed_generate")


def short(m): return m.split("/")[-1]


def load_phase1_trial(mode, model, pid):
    """Return the raw Phase 1 trial dict, or None if not on disk."""
    p = PHASE1 / mode / short(model) / f"{pid}.json"
    if not p.exists(): return None
    try: return json.load(open(p))
    except Exception: return None


def load_regrade(mode, model, pid):
    """Return gemini's score/verdict on best_solution from the full regrade dir.
    Returns (score, verdict) or (None, None)."""
    p = REGRADE / mode / short(model) / f"{pid}.json"
    if not p.exists(): return None, None
    try:
        r = json.load(open(p))
        if r.get("error") or r.get("gemini_score") is None:
            return None, None
        return r["gemini_score"], r.get("gemini_verdict")
    except Exception:
        return None, None


def load_branch_regrade(mode, model, pid, k):
    """Return (gemini_score, gemini_verdict) from branch regrade, or (None, None)."""
    p = BRANCH / mode / short(model) / f"{pid}__k{k}.json"
    if not p.exists(): return None, None
    try:
        r = json.load(open(p))
        if r.get("error") or r.get("gemini_score") is None:
            return None, None
        return r["gemini_score"], r.get("gemini_verdict")
    except Exception:
        return None, None


def build_branch_record(mode, branch, model, pid):
    """Decorate a Phase 1 branch dict with gemini score/verdict from branch regrade."""
    if mode == "generate":
        k = branch.get("k", 0)
        gs, gv = load_branch_regrade(mode, model, pid, k)
        return {
            "k":             k,
            "solution":      branch.get("solution"),
            "v4_score":      branch.get("score"),
            "v4_verdict":    branch.get("verdict"),
            "gemini_score":  gs,
            "gemini_verdict": gv,
        }
    elif mode == "seed_generate":
        idx = branch.get("idea_idx", 0)
        gs, gv = load_branch_regrade(mode, model, pid, idx)
        return {
            "idea_idx":      idx,
            "idea":          branch.get("idea"),
            "solution":      branch.get("solution"),
            "v4_score":      branch.get("score"),
            "v4_verdict":    branch.get("verdict"),
            "gemini_score":  gs,
            "gemini_verdict": gv,
        }
    elif mode == "full":
        # Only one branch in full mode. The trial-level regrade IS the only judge of
        # the final_solution. There's no per-branch regrade for full mode.
        return {
            "k":                0,
            "initial_solution": branch.get("initial_solution"),
            "final_solution":   branch.get("final_solution"),
            "v4_score":         branch.get("score"),
            "v4_verdict":       branch.get("verdict"),
            "loop_log":         branch.get("loop_log", []),
            "stopped_early":    branch.get("stopped_early"),
        }
    return {}


def build_record(problem_id, problem, model, mode):
    """Build one dataset record. Returns a dict (with explicit nulls for missing data)."""
    trial = load_phase1_trial(mode, model, problem_id)
    gem_score, gem_verdict = load_regrade(mode, model, problem_id)

    rec = {
        # --- Problem ---
        "problem_id":      problem_id,
        "problem_text":    problem["text"],
        "ground_truth":    problem["ground_truth"],
        "category":        problem.get("category"),
        "level":           problem.get("level"),
        "source":          problem.get("source"),
        "is_special_10":   problem_id in SPECIAL_10,
        # --- Trial id ---
        "model":           model,
        "mode":            mode,
        # --- Trial metadata ---
        "started_at":      trial.get("started_at") if trial else None,
        "completed_at":    trial.get("completed_at") if trial else None,
        "elapsed_s":       trial.get("elapsed_s") if trial else None,
        "cost_usd":        trial.get("cost_usd") if trial else None,
        "error":           trial.get("error") if trial else "trial_missing",
        # --- Final solution + both judges ---
        "final_solution":  trial.get("best_solution") if trial else None,
        "v4pro_score":     trial.get("score") if trial and not trial.get("error") else None,
        "v4pro_verdict":   trial.get("best_verdict") if trial and not trial.get("error") else None,
        "gemini_score":    gem_score,
        "gemini_verdict":  gem_verdict,
        # --- Branches (per-branch judge data) ---
        "branches":        [],
        # --- Mode-specific extras (e.g. ideas) ---
        "mode_extras":     trial.get("mode_extras") if trial else None,
    }
    if trial and not trial.get("error"):
        for b in trial.get("branches", []):
            rec["branches"].append(build_branch_record(mode, b, model, problem_id))

    # If trial succeeded but error was None earlier, normalize to None
    if rec["error"] is None:
        rec.pop("error")
    return rec


def main():
    problems = load_70_problems()
    pids = sorted(problems.keys())

    print(f"Building dataset: {len(pids)} problems × {len(MODELS_ORD)} models × {len(MODES)} modes "
          f"= {len(pids) * len(MODELS_ORD) * len(MODES)} expected rows")

    n_total = 0
    n_with_v4 = 0
    n_with_gemini = 0
    n_with_branch_gemini = 0
    n_errors = 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for pid in pids:
            for model in MODELS_ORD:
                for mode in MODES:
                    rec = build_record(pid, problems[pid], model, mode)
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_total += 1
                    if rec.get("v4pro_score") is not None: n_with_v4 += 1
                    if rec.get("gemini_score") is not None: n_with_gemini += 1
                    if rec.get("error"): n_errors += 1
                    n_with_branch_gemini += sum(
                        1 for b in rec["branches"] if b.get("gemini_score") is not None
                    )

    print(f"\nWrote {n_total} rows → {OUT}")
    print(f"  rows with v4pro_score:           {n_with_v4}")
    print(f"  rows with gemini_score:          {n_with_gemini}")
    print(f"  rows with errors / null trials:  {n_errors}")
    print(f"  branch entries with gemini_score: {n_with_branch_gemini}")

    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"  file size: {size_mb:.1f} MB")

    # Brief schema dump for the first record (without huge text fields)
    print(f"\nSchema (first record, text fields truncated):")
    with open(OUT) as f:
        first = json.loads(f.readline())
    for k, v in first.items():
        if isinstance(v, str) and len(v) > 80:
            print(f"  {k}: <str len={len(v)}>")
        elif isinstance(v, list):
            print(f"  {k}: <list len={len(v)}>")
        elif isinstance(v, dict):
            print(f"  {k}: <dict keys={list(v.keys())[:5]}>")
        else:
            print(f"  {k}: {v!r}")


if __name__ == "__main__":
    main()
