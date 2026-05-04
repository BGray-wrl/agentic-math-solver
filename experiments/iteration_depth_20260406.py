#!/usr/bin/env python3
"""
Iteration depth scaling experiment (v3 — parallel).

Hypothesis: More verify/revise iterations improve scores, but with diminishing returns.

Variables:
  Independent: number of verify/revise iterations (0, 1, 2, 4, 6)
  Dependent:   score (0-7), pass rate, verifier early-stop rate
  Controlled:  model, problem set, seed, judge

Design: 2 models × 6 devset problems × 5 iteration counts × 1 seed = 60 trials.
Uses 1 idea branch (not 3) to keep judge calls cheap: 60 judge calls total.
Parallelizes with multiprocessing (not threading — avoids import-lock deadlock).

Usage:
    uv run experiments/iteration_depth_20260406.py --mock
    uv run experiments/iteration_depth_20260406.py
    uv run experiments/iteration_depth_20260406.py --workers 4
    uv run experiments/iteration_depth_20260406.py --resume experiments/results/iteration_depth_v3_PARTIAL_*.json
"""

from __future__ import annotations

import os
import sys
import csv
import json
import re
import time
import random
import argparse
import multiprocessing
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Use OPENROUTER_API_KEY_2 since primary key is maxed
key2 = os.getenv("OPENROUTER_API_KEY_2")
if key2:
    os.environ["OPENROUTER_API_KEY"] = key2

# ============================================================================
# CONFIGURATION
# ============================================================================

EXPERIMENT_NAME = "iteration_depth_v3"

MODELS = [
    "openrouter/deepseek/deepseek-v3.2",
    "openrouter/openai/gpt-oss-120b",
]

IDEATOR     = "openrouter/google/gemini-3.1-flash-lite-preview"
JUDGE_MODEL = "gemini/gemini-3-flash-preview"
NUM_IDEAS   = 1          # 1 branch → 1 judge call per trial (cheap)
ITER_COUNTS = [0, 1, 2, 4, 6]
SEEDS       = [42]       # 1 seed → 60 trials total
PASS_THRESHOLD  = 6
MAX_TOKENS      = 32000
MAX_TOKENS_JUDGE = 32000
LITELLM_TIMEOUT = 540

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
# Worker function — runs in a child process
# ============================================================================

def run_trial_worker(args_tuple):
    """Top-level function for multiprocessing. Returns result dict."""
    (problem_id, problem, model, seed, n_iters, prompts,
     log_path, mock, api_key) = args_tuple

    # Set API key in child process
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key

    import litellm
    litellm.request_timeout = LITELLM_TIMEOUT

    # Import pipeline inside worker to avoid pickling issues
    from pipeline import generate, verify, revise, judge, make_logger, ideate

    logger = make_logger(str(log_path))

    np.random.seed(seed)
    random.seed(seed)

    model_short = model.split("/")[-1][:15]
    tag = f"[{_ts()}] [{problem_id}|{model_short}|s={seed}|i={n_iters}]"
    t0 = time.time()

    try:
        # Ideation
        ideas = ideate(
            problem=problem["text"], system=prompts["ideator"],
            model=IDEATOR, max_tokens=4096, logger=logger,
            num_ideas=NUM_IDEAS, mock=mock,
        )
        idea = ideas[0] if ideas else {"name": "direct", "description": "Solve directly."}

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

            solution = revise(
                problem=problem["text"], solution=solution, critique=critique,
                system=prompts["reviser"], model=model, max_tokens=MAX_TOKENS,
                logger=logger, iteration=i+1, mock=mock,
            )

        verdict_text = judge(
            problem=problem["text"], candidate=solution,
            ground_truth=problem["solution"],
            system=prompts["judge_gt"], model=JUDGE_MODEL,
            max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
            extract_prompt=prompts["extract_score"],
        )
        score = parse_gt_score(verdict_text)

    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} ERROR: {e}", flush=True)
        return {
            "problem_id": problem_id,
            "level": problem["level"],
            "model": model,
            "seed": seed,
            "n_iters": n_iters,
            "best_score": None,
            "passed": False,
            "elapsed_s": elapsed,
            "error": str(e),
        }

    elapsed = round(time.time() - t0, 2)
    passed = score >= PASS_THRESHOLD
    print(f"{tag} → score={score}/7 iters_run={iters_run} early={stopped_early} {elapsed:.0f}s", flush=True)

    return {
        "problem_id": problem_id,
        "level": problem["level"],
        "model": model,
        "seed": seed,
        "n_iters": n_iters,
        "best_score": score,
        "passed": passed,
        "iters_run": iters_run,
        "stopped_early": stopped_early,
        "elapsed_s": elapsed,
        "best_solution": solution,
        "best_verdict": verdict_text,
    }


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Iteration depth experiment v3 (parallel)")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--resume", type=str, default=None)
    args = parser.parse_args()

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

    api_key = os.environ.get("OPENROUTER_API_KEY", "")

    # Build trial list
    trials = [
        (pid, model, seed, n_iters)
        for pid in pids
        for model in MODELS
        for seed in SEEDS
        for n_iters in ITER_COUNTS
    ]
    total = len(trials)

    # Resume support
    all_results = []
    completed_keys = set()
    if args.resume:
        with open(args.resume) as f:
            prev = json.load(f)
        for r in prev.get("all_results", []):
            all_results.append(r)
            completed_keys.add((r["problem_id"], r["model"], r["seed"], r["n_iters"]))
        print(f"Resumed {len(completed_keys)} completed trials from {args.resume}", flush=True)

    remaining = [(pid, model, seed, ni) for pid, model, seed, ni in trials
                 if (pid, model, seed, ni) not in completed_keys]

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Problems: {len(pids)}  Models: {len(MODELS)}  Seeds: {len(SEEDS)}  Iter counts: {ITER_COUNTS}")
    print(f"Total trials: {total}  Remaining: {len(remaining)}  Workers: {args.workers}")
    print(f"Models: {', '.join(m.split('/')[-1] for m in MODELS)}")
    print(f"Judge: {JUDGE_MODEL}  (num_ideas={NUM_IDEAS} → {total} judge calls total)")
    if args.mock:
        print("[MOCK MODE]")
    print(flush=True)

    ts = _now()
    partial_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_PARTIAL_{ts}.json"
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{ts}.jsonl"

    # Build args tuples for workers
    worker_args = [
        (pid, problems[pid], model, seed, n_iters, prompts, log_path, args.mock, api_key)
        for pid, model, seed, n_iters in remaining
    ]

    t_start = time.time()

    def save_partial():
        _save_results(all_results, pids, args.mock, t_start, partial_path)

    n_workers = 1 if args.mock else args.workers

    with multiprocessing.Pool(processes=n_workers) as pool:
        for result in pool.imap_unordered(run_trial_worker, worker_args):
            all_results.append(result)
            completed = len(all_results)
            elapsed_min = (time.time() - t_start) / 60
            print(f"[{_ts()}] Progress: {completed}/{total} ({elapsed_min:.1f} min elapsed)", flush=True)

            if completed % 5 == 0:
                save_partial()

    # Final save
    total_elapsed = round((time.time() - t_start) / 60, 1)
    suffix = "_mock" if args.mock else ""
    final_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{ts}{suffix}.json"
    _save_results(all_results, pids, args.mock, t_start, final_path)

    if partial_path.exists():
        partial_path.unlink()

    _print_report(all_results, pids, total_elapsed)
    print(f"\nResults: {final_path}")
    print(f"Log:     {log_path}")


def _save_results(all_results, pids, mock, t_start, path):
    total_elapsed = round((time.time() - t_start) / 60, 1)
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
        "mock": mock,
        "total_elapsed_min": total_elapsed,
        "all_results": all_results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def _print_report(all_results, pids, total_elapsed):
    print(f"\n{'='*70}")
    print(f"ITERATION DEPTH RESULTS  ({total_elapsed} min total)")
    print(f"{'='*70}\n")

    for model in MODELS:
        ms = model.split("/")[-1]
        print(f"\n{ms}:")
        print(f"  {'Iters':<8} {'Mean':<10} {'Pass':<10} {'Early Stop':<12} {'Mean Time'}")
        print(f"  {'-'*55}")

        for n_iters in ITER_COUNTS:
            rs = [r for r in all_results
                  if r["model"] == model and r.get("n_iters") == n_iters
                  and r.get("best_score") is not None]
            if not rs:
                print(f"  {n_iters:<8} (no data)")
                continue

            scores = [r["best_score"] for r in rs]
            mean = np.mean(scores)
            passed = sum(r["passed"] for r in rs)
            early = sum(1 for r in rs if r.get("stopped_early"))
            elapsed = np.mean([r["elapsed_s"] for r in rs])
            print(f"  {n_iters:<8} {mean:.2f}/7    {passed}/{len(rs)}       "
                  f"{early}/{len(rs)} early     {elapsed:.0f}s")

    print(f"\n--- Per-problem (score by iteration count) ---")
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
                row += f"{rs[0]['best_score'] if rs else 'err':<8}"
            print(row)


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    main()
