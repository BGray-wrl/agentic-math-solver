#!/usr/bin/env python3
"""
Experiment: Full pipeline on hard/open problems — fast models.
Date: 2026-03-27
Problems: erdos-659, ramsey-hypergraphs
Models: nemotron-120b, qwen3.5-flash, gemini-3-flash, gpt-5.4-mini
Pipeline: full (generate → verify ↔ revise → judge), 3 iterations, pass@1
Judge: gemini-3-flash-preview with ground truth (0–7)
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
import traceback
import concurrent.futures
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402


# ============================================================================
# CONFIGURATION
# ============================================================================

EXPERIMENT_NAME = "full_pipeline_hard_fast"

DESCRIPTION = """
Full pipeline (generate → verify ↔ revise → judge) on two hard/open problems
(erdos-659, ramsey-hypergraphs) with four faster models. Baseline from
generate-only showed only gpt-5.4-mini scoring >0. Testing whether the
verify/revise loop helps any model make progress.
"""

MODELS = [
    "openrouter/nvidia/nemotron-3-super-120b-a12b",
    "openrouter/qwen/qwen3.5-flash-02-23",
    "gemini/gemini-3-flash-preview",
    "openai/gpt-5.4-mini",
]

JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"

PROBLEM_IDS = ["erdos-659", "ramsey-hypergraphs"]

def select_problems(all_rows: list[dict]) -> dict[str, dict]:
    problems = {}
    for row in all_rows:
        pid = row["Problem ID"]
        if pid in PROBLEM_IDS:
            problems[pid] = {
                "text":     row["Problem"],
                "solution": row.get("Solution", ""),
                "level":    row.get("Level", ""),
                "category": row.get("Category", ""),
            }
    return problems

PIPELINE_MODE = "full"
USE_GROUND_TRUTH = True
SEEDS = [42]
PASS_THRESHOLD = 6
ITERATIONS = 3
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 4096
MAX_WORKERS = 8
TRIAL_TIMEOUT = 900
LITELLM_TIMEOUT = 600


# ============================================================================
# --- Template machinery ---
# ============================================================================

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SCORE_MAP = {"correct": 3, "almost": 2, "partial": 1, "incorrect": 0}


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
    return 0


def parse_classification(verdict: str) -> str:
    for label in ("correct", "almost", "partial", "incorrect"):
        if f"CLASSIFICATION: {label}" in verdict:
            return label
    lower = verdict.lower()
    for label in ("correct", "almost", "partial", "incorrect"):
        if label in lower:
            return label
    return "incorrect"


def load_problems_from_csv() -> dict[str, dict]:
    rows = []
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return select_problems(rows)


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def run_trial(
    problem_id: str, problem: dict, model: str, seed: int,
    prompts: dict[str, str], log_path: Path, log_lock: threading.Lock,
    mock: bool = False,
) -> dict:
    from pipeline import generate, verify, revise, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    model_short = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{model_short}|seed={seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    ts_start = time.time()
    loop_log = []

    print(f"{tag} generate", flush=True)
    solution = generate(
        problem=problem["text"], system=prompts["generator"], model=model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{tag} generate done ({len(solution)} chars, {round(time.time()-ts_start,1)}s)", flush=True)

    stopped_early = False
    if PIPELINE_MODE == "full":
        for i in range(ITERATIONS):
            print(f"{tag} verify iter={i+1}", flush=True)
            critique = verify(
                problem=problem["text"], solution=solution, system=prompts["verifier"],
                model=model, max_tokens=MAX_TOKENS, logger=logger, iteration=i+1, mock=mock,
            )
            if "VERDICT: correct" in critique:
                print(f"{tag} verifier satisfied at iter={i+1}", flush=True)
                stopped_early = True
                loop_log.append({"iteration": i+1, "verdict": "correct",
                                  "critique": critique, "solution": solution})
                break

            print(f"{tag} revise iter={i+1}", flush=True)
            new_solution = revise(
                problem=problem["text"], solution=solution, critique=critique,
                system=prompts["reviser"], model=model, max_tokens=MAX_TOKENS,
                logger=logger, iteration=i+1, mock=mock,
            )
            loop_log.append({"iteration": i+1, "verdict": "issues_found",
                              "critique": critique, "solution_before": solution,
                              "solution_after": new_solution})
            solution = new_solution
            print(f"{tag} revised ({len(solution)} chars, {round(time.time()-ts_start,1)}s)", flush=True)

    gt = problem["solution"] if USE_GROUND_TRUTH else None
    print(f"{tag} judge {'(GT)' if gt else '(no GT)'}", flush=True)
    verdict_text = judge(
        problem=problem["text"], candidate=solution, ground_truth=gt,
        system=prompts["judge"], model=JUDGE_MODEL,
        max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
    )

    if USE_GROUND_TRUTH:
        score  = parse_gt_score(verdict_text)
        passed = score >= PASS_THRESHOLD
    else:
        label  = parse_classification(verdict_text)
        score  = SCORE_MAP[label]
        passed = label == "correct"

    elapsed = round(time.time() - ts_start, 2)
    print(f"{tag} → score={score} pass={passed} iters={len(loop_log)} early={stopped_early} {elapsed}s", flush=True)

    return {
        "problem_id": problem_id, "level": problem["level"],
        "category": problem.get("category", ""), "model": model,
        "seed": seed, "score": score, "passed": passed,
        "iterations_run": len(loop_log), "stopped_early": stopped_early,
        "elapsed_s": elapsed, "final_solution": solution,
        "verdict": verdict_text, "loop_log": loop_log,
    }


def run_all(problems, prompts, args):
    problem_ids = sorted(problems.keys())
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    trials = [(pid, m, s) for pid in problem_ids for m in MODELS for s in SEEDS]
    total  = len(trials)
    print(f"Submitting {total} trials (max_workers={MAX_WORKERS})\n", flush=True)

    all_results = []
    completed   = 0

    def _run(pid, model, seed):
        return run_trial(pid, problems[pid], model, seed, prompts, log_path, log_lock, args.mock)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, *t): t for t in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid, model, seed = futs[fut]
            completed += 1
            try:
                all_results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = model.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{ms}|seed={seed}]: {e}", flush=True)
                all_results.append({
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid].get("category", ""), "model": model,
                    "seed": seed, "score": None, "passed": False,
                    "iterations_run": None, "stopped_early": None,
                    "elapsed_s": 0, "final_solution": None, "verdict": None,
                    "loop_log": [], "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    return all_results, log_path


def report(all_results, problems, log_path, args):
    problem_ids = sorted(problems.keys())
    pass_k = len(SEEDS)

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    model_stats = {}
    for model in MODELS:
        ms    = model.split("/")[-1]
        valid = [r for r in all_results if r["model"] == model and r["score"] is not None]
        scores = [r["score"] for r in valid]

        passk = []
        for pid in problem_ids:
            pid_r = [r for r in valid if r["problem_id"] == pid]
            if pid_r:
                passk.append(any(r["passed"] for r in pid_r))
        passk_rate = float(np.mean(passk)) if passk else 0.0

        iters   = [r["iterations_run"] for r in valid if r.get("iterations_run") is not None]
        stopped = sum(1 for r in valid if r.get("stopped_early"))

        dist = {k: sum(1 for s in scores if s == k) for k in range(8)}
        dist_str = "  ".join(f"{k}/7:{v}" for k, v in dist.items() if v > 0)

        model_stats[model] = {
            "mean_score": round(float(np.mean(scores)), 3) if scores else 0.0,
            "std_score": round(float(np.std(scores)), 3) if scores else 0.0,
            "passk_rate": round(passk_rate, 3),
            "passk_count": sum(passk),
            "passk_total": len(passk),
            "n_valid": len(valid),
            "n_errors": sum(1 for r in all_results if r["model"] == model and r.get("error")),
            "mean_iters": round(float(np.mean(iters)), 2) if iters else 0.0,
            "stopped_early_n": stopped,
            "distribution": dist,
        }

        print(f"\n{ms}")
        print(f"  Mean score:    {model_stats[model]['mean_score']:.3f} ± {model_stats[model]['std_score']:.3f}  (n={len(valid)})")
        print(f"  pass@{pass_k}:      {passk_rate:.1%}  ({sum(passk)}/{len(passk)})")
        print(f"  Avg iters:     {model_stats[model]['mean_iters']:.2f}  (stopped early: {stopped}/{len(valid)})")
        print(f"  Distribution:  {dist_str}")
        if model_stats[model]["n_errors"]:
            print(f"  Errors:        {model_stats[model]['n_errors']}")

    # Per-problem table
    print(f"\n--- Per-problem scores ---")
    col_w = 24
    hdr = f"  {'Problem':<26}{'Level':<20}" + "".join(f"{m.split('/')[-1][:col_w]:<{col_w+2}}" for m in MODELS)
    print(hdr)
    print("  " + "-" * (46 + (col_w + 2) * len(MODELS)))
    for pid in problem_ids:
        row = f"  {pid:<26}{problems[pid]['level']:<20}"
        for model in MODELS:
            rs = [r for r in all_results if r["model"] == model and r["problem_id"] == pid and r["score"] is not None]
            if rs:
                scores_str = "/".join(str(r["score"]) for r in sorted(rs, key=lambda x: x["seed"]))
                flag = "✓" if any(r["passed"] for r in rs) else "✗"
                cell = f"{flag} [{scores_str}] i={rs[0]['iterations_run']}"
            else:
                cell = "error"
            row += f"{cell:<{col_w+2}}"
        print(row)

    # Save
    output = {
        "experiment": EXPERIMENT_NAME,
        "description": DESCRIPTION.strip(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pipeline_mode": PIPELINE_MODE,
        "ground_truth": USE_GROUND_TRUTH,
        "mock": args.mock,
        "seeds": SEEDS,
        "iterations": ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
        "problems": problem_ids,
        "models": MODELS,
        "judge_model": JUDGE_MODEL,
        "model_stats": model_stats,
        "all_results": all_results,
    }

    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


def main():
    parser = argparse.ArgumentParser(description=f"Experiment: {EXPERIMENT_NAME}")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems_from_csv()
    prompts = {
        "generator": load_prompt("generator.md"),
        "verifier":  load_prompt("verifier.md"),
        "reviser":   load_prompt("reviser.md"),
        "judge":     load_prompt("judge.md"),
    }

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Mode: {PIPELINE_MODE}  |  GT: {USE_GROUND_TRUTH}  |  Seeds: {SEEDS}  |  Iters: {ITERATIONS}")
    print(f"Problems: {list(problems.keys())}  |  Models: {[m.split('/')[-1] for m in MODELS]}")
    print(f"Total trials: {len(problems) * len(MODELS) * len(SEEDS)}")
    if args.mock:
        print("[MOCK MODE]")
    print()

    all_results, log_path = run_all(problems, prompts, args)
    report(all_results, problems, log_path, args)


if __name__ == "__main__":
    main()
