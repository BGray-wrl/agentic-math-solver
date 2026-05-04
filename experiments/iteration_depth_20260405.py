#!/usr/bin/env python3
"""
Iteration depth scaling experiment.

Hypothesis: More verify/revise iterations improve scores, but with diminishing returns.
             We want to find where the curve flattens to know if 6 iterations (v2 design)
             is justified vs 2-3.

Variables:
  Independent: number of verify/revise iterations (0, 1, 2, 4, 6)
  Dependent:   score (0-7), pass rate, verifier early-stop rate
  Controlled:  model, problem set, seed, judge

Design: 2 models × 6 devset problems × 5 iteration counts × 2 seeds = 120 trials.
Uses seed ideas (3 ideas per trial, best-of-3) since that's our intended pipeline.

Usage:
    uv run experiments/iteration_depth_20260405.py --mock
    uv run experiments/iteration_depth_20260405.py
"""

from __future__ import annotations

import sys
import csv
import json
import re
import time
import random
import argparse
import threading
import concurrent.futures
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402

# ============================================================================
# CONFIGURATION
# ============================================================================

EXPERIMENT_NAME = "iteration_depth"

# Models: DS and OSS (cheap, well-characterized from prior experiments)
MODELS = [
    "openrouter/deepseek/deepseek-v3.2",
    "openrouter/openai/gpt-oss-120b",
]

IDEATOR = "openrouter/google/gemini-3.1-flash-lite-preview"
JUDGE_MODEL = "gemini/gemini-3-flash-preview"
NUM_IDEAS = 3

# Iteration counts to test
ITER_COUNTS = [0, 1, 2, 4, 6]

SEEDS = [42, 123]
PASS_THRESHOLD = 6
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 8
TRIAL_TIMEOUT = 1200  # generous for 6-iteration runs
LITELLM_TIMEOUT = 540

# ============================================================================
# Paths and helpers
# ============================================================================

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def _now():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def parse_gt_score(verdict: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m:
        return int(m.group(1))
    classif_map = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif_map.items():
        if f"CLASSIFICATION: {label}" in verdict:
            return score
    return 0


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def load_devset():
    from devset import DEV_SET_IDS
    problems = {}
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid = row["Problem ID"]
            if pid in DEV_SET_IDS:
                problems[pid] = {
                    "text":     row["Problem"],
                    "solution": row.get("Solution", ""),
                    "level":    row.get("Level", ""),
                    "category": row.get("Category", ""),
                }
    return problems


# ============================================================================
# Ideation cache (shared across all conditions for same problem+seed)
# ============================================================================

_idea_cache = {}
_idea_cache_lock = threading.Lock()


def get_ideas(problem_id, problem_text, seed, prompts, logger, log_lock, mock):
    """Get or create ideas for a (problem, seed) pair. Cached to avoid redundant calls."""
    key = (problem_id, seed)
    with _idea_cache_lock:
        if key in _idea_cache:
            return _idea_cache[key]

    from pipeline import ideate

    np.random.seed(seed)
    random.seed(seed)

    def _log(*a):
        with log_lock:
            logger(*a)

    ideas = ideate(
        problem=problem_text, system=prompts["ideator"],
        model=IDEATOR, max_tokens=4096, logger=_log,
        num_ideas=NUM_IDEAS, mock=mock,
    )
    ideas = ideas[:NUM_IDEAS]

    with _idea_cache_lock:
        _idea_cache[key] = ideas
    return ideas


# ============================================================================
# Single trial: run N ideas as branches, best-of-N with variable iterations
# ============================================================================

def run_trial(
    problem_id, problem, model, seed, n_iters, prompts,
    log_path, log_lock, mock=False,
):
    """Run one trial: ideate → N parallel branches → judge best."""
    from pipeline import generate, verify, revise, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    model_short = model.split("/")[-1][:15]
    tag = f"[{_ts()}] [{problem_id}|{model_short}|s={seed}|i={n_iters}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # Get ideas (cached)
    ideas = get_ideas(problem_id, problem["text"], seed, prompts, logger, log_lock, mock)

    # Run each idea as a branch
    def run_branch(idea):
        gen_prompt = prompts["generator_seeded"].replace(
            "{idea}", f"**{idea['name']}**: {idea['description']}"
        )
        solution = generate(
            problem=problem["text"], system=gen_prompt, model=model,
            max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
        )

        iters_run = 0
        stopped_early = False

        for i in range(n_iters):
            critique = verify(
                problem=problem["text"], solution=solution, system=prompts["verifier"],
                model=model, max_tokens=MAX_TOKENS, logger=logger,
                iteration=i+1, mock=mock,
            )
            iters_run += 1

            if "VERDICT: correct" in critique:
                stopped_early = True
                break

            new_solution = revise(
                problem=problem["text"], solution=solution, critique=critique,
                system=prompts["reviser"], model=model, max_tokens=MAX_TOKENS,
                logger=logger, iteration=i+1, mock=mock,
            )
            solution = new_solution

        return {
            "idea": idea["name"],
            "solution": solution,
            "iters_run": iters_run,
            "stopped_early": stopped_early,
        }

    # Parallelize branches
    branch_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_IDEAS) as ex:
        futs = [ex.submit(run_branch, idea) for idea in ideas]
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT):
            branch_results.append(fut.result(timeout=TRIAL_TIMEOUT))

    # Judge all branches, pick best
    best_score = -1
    best_branch = None

    for br in branch_results:
        gt = problem["solution"]
        judge_prompt = prompts["judge_gt"]
        verdict_text = judge(
            problem=problem["text"], candidate=br["solution"], ground_truth=gt,
            system=judge_prompt, model=JUDGE_MODEL,
            max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
            extract_prompt=prompts["extract_score"],
        )
        score = parse_gt_score(verdict_text)
        br["score"] = score
        br["verdict"] = verdict_text

        if score > best_score:
            best_score = score
            best_branch = br

    elapsed = round(time.time() - t0, 2)
    branch_scores = [br["score"] for br in branch_results]
    mean_branch = round(np.mean(branch_scores), 2)

    print(f"{tag} → best={best_score}/7 branches={branch_scores} mean={mean_branch} {elapsed:.0f}s", flush=True)

    return {
        "problem_id": problem_id,
        "level": problem["level"],
        "model": model,
        "seed": seed,
        "n_iters": n_iters,
        "best_score": best_score,
        "mean_branch_score": mean_branch,
        "branch_scores": branch_scores,
        "passed": best_score >= PASS_THRESHOLD,
        "elapsed_s": elapsed,
        "branches": [{k: v for k, v in br.items() if k != "solution" and k != "verdict"}
                     for br in branch_results],
        "best_branch_idea": best_branch["idea"] if best_branch else None,
        "best_solution": best_branch["solution"] if best_branch else None,
        "best_verdict": best_branch["verdict"] if best_branch else None,
    }


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Iteration depth scaling experiment")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_devset()
    pids = sorted(problems.keys())

    prompts = {
        "generator":        load_prompt("generator.md"),
        "generator_seeded": load_prompt("generator_seeded.md"),
        "ideator":          load_prompt("ideator.md"),
        "verifier":         load_prompt("verifier.md"),
        "reviser":          load_prompt("reviser.md"),
        "judge_gt":         load_prompt("judge_gt.md"),
        "judge_nogt":       load_prompt("judge_nogt.md"),
        "extract_score":    load_prompt("extract_score.md"),
    }

    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    # Build trial list: problem × model × seed × n_iters
    trials = [
        (pid, model, seed, n_iters)
        for pid in pids
        for model in MODELS
        for seed in SEEDS
        for n_iters in ITER_COUNTS
    ]
    total = len(trials)

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Problems: {len(pids)}  Models: {len(MODELS)}  Seeds: {len(SEEDS)}  Iter counts: {ITER_COUNTS}")
    print(f"Total trials: {total}  (ideas cached per problem+seed)")
    if args.mock:
        print("[MOCK MODE]")
    print()

    all_results = []
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for trial in trials:
            pid, model, seed, n_iters = trial
            fut = ex.submit(
                run_trial, pid, problems[pid], model, seed, n_iters,
                prompts, log_path, log_lock, args.mock,
            )
            futs[fut] = trial

        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid, model, seed, n_iters = futs[fut]
            completed += 1
            try:
                all_results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = model.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{ms}|s={seed}|i={n_iters}]: {e}", flush=True)
                all_results.append({
                    "problem_id": pid, "level": problems[pid]["level"],
                    "model": model, "seed": seed, "n_iters": n_iters,
                    "best_score": None, "passed": False,
                    "elapsed_s": 0, "error": str(e),
                })
            if completed % 10 == 0:
                print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    print(f"\n{'='*70}")
    print("ITERATION DEPTH RESULTS")
    print(f"{'='*70}\n")

    for model in MODELS:
        ms = model.split("/")[-1]
        print(f"\n{ms}:")
        print(f"  {'Iters':<8} {'Mean':<10} {'Pass':<10} {'Stopped Early':<15} {'Mean Time'}")
        print(f"  {'-'*55}")

        for n_iters in ITER_COUNTS:
            rs = [r for r in all_results
                  if r["model"] == model and r.get("n_iters") == n_iters and r.get("best_score") is not None]
            if not rs:
                print(f"  {n_iters:<8} (no data)")
                continue

            scores = [r["best_score"] for r in rs]
            mean = np.mean(scores)
            passed = sum(r["passed"] for r in rs)
            total_n = len(rs)
            elapsed = np.mean([r["elapsed_s"] for r in rs])

            # Count early stops across all branches
            early = 0
            total_branches = 0
            for r in rs:
                for br in r.get("branches", []):
                    total_branches += 1
                    if br.get("stopped_early"):
                        early += 1

            print(f"  {n_iters:<8} {mean:.2f}/7    {passed}/{total_n}       "
                  f"{early}/{total_branches} branches   {elapsed:.0f}s")

    # Per-problem breakdown
    print(f"\n--- Per-problem (best_score by iteration count) ---")
    for model in MODELS:
        ms = model.split("/")[-1]
        print(f"\n{ms}:")
        header = f"  {'Problem':<20}" + "".join(f"{'i='+str(n):<8}" for n in ITER_COUNTS)
        print(header)
        print(f"  {'-'*60}")

        for pid in pids:
            row = f"  {pid:<20}"
            for n_iters in ITER_COUNTS:
                rs = [r for r in all_results
                      if r["model"] == model and r["problem_id"] == pid
                      and r.get("n_iters") == n_iters and r.get("best_score") is not None]
                if rs:
                    scores = [r["best_score"] for r in rs]
                    row += f"{'/'.join(str(s) for s in scores):<8}"
                else:
                    row += f"{'err':<8}"
            print(row)

    # Save
    ts = _now()
    suffix = "_mock" if args.mock else ""
    output = {
        "experiment": EXPERIMENT_NAME,
        "date": datetime.now(timezone.utc).isoformat(),
        "models": MODELS,
        "ideator": IDEATOR,
        "judge_model": JUDGE_MODEL,
        "iter_counts": ITER_COUNTS,
        "seeds": SEEDS,
        "num_ideas": NUM_IDEAS,
        "problems": pids,
        "mock": args.mock,
        "all_results": all_results,
    }
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
