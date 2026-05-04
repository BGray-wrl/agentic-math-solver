#!/usr/bin/env python3
"""
Experiment: Cross-model verify/revise loop — diversity hypothesis
Date: 2026-03-27
Hypothesis: Cross-model critique (generator A + critic B) outperforms self-critique
            (generator A + critic A) because different model families catch different
            error classes.

Variables:
  Independent: (generator_model, critic_model) pairing
  Dependent:   pass@1 (score >= 6/7), mean score
  Controlled:  problems (18 IMO-medium), judge model (gemini-3-flash), seed [42],
               iterations (3), max_tokens (32000), prompts

Conditions (cross-model):
  A: generator=deepseek,  critic=nemotron
  B: generator=nemotron,  critic=deepseek

Same-model baselines (from full_pipeline_imo_medium_pass1_20260327_031130.json):
  Nemotron-self: 26.7% pass@1 (4/15 valid), mean 1.93/7
  DeepSeek-self: 33.3% pass@1 (5/15 valid), mean 2.60/7

Usage:
    uv run experiments/cross_model_pipeline_20260327.py --mock
    uv run experiments/cross_model_pipeline_20260327.py
    uv run experiments/cross_model_pipeline_20260327.py --retry experiments/results/<prev>.json
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

EXPERIMENT_NAME = "cross_model_pipeline_20260327"

DESCRIPTION = """
Hypothesis: Cross-model critique (generator A + critic B) outperforms self-critique
because different model families surface different error classes and reduce
blind-spot overlap.
Variables:
  Independent: (generator_model, critic_model) pairing — both cross-model combos
  Dependent:   pass@1 (score >= 6/7), mean score/7
  Controlled:  18 IMO-medium problems, gemini-3-flash judge (GT mode), seed=[42],
               iterations=3, max_tokens=32000, same prompts
"""

# --- Models ---

DEEPSEEK  = "openrouter/deepseek/deepseek-v3.2"
NEMOTRON  = "openrouter/nvidia/nemotron-3-super-120b-a12b"
JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"

# Each condition is (label, generator_model, critic_model)
CONDITIONS = [
    ("deepseek-gen_nemotron-critic", DEEPSEEK,  NEMOTRON),
    ("nemotron-gen_deepseek-critic", NEMOTRON,  DEEPSEEK),
]

# --- Problems ---

def select_problems(all_rows: list[dict]) -> dict[str, dict]:
    problems = {}
    for row in all_rows:
        pid   = row["Problem ID"]
        level = row.get("Level", "")
        if level == "IMO-medium":
            problems[pid] = {
                "text":     row["Problem"],
                "solution": row.get("Solution", ""),
                "level":    level,
                "category": "PB-Advanced" if pid.startswith("PB-Advanced") else "PB-Basic",
            }
    return problems

# --- Pipeline mode ---

PIPELINE_MODE    = "full"
USE_GROUND_TRUTH = True

# --- Seeds / metrics ---

SEEDS          = [42]
PASS_THRESHOLD = 6

# --- Pipeline parameters ---

ITERATIONS       = 3
MAX_TOKENS       = 32000
MAX_TOKENS_JUDGE = 4096

# --- Execution ---

MAX_WORKERS   = 16
TRIAL_TIMEOUT = 900
LITELLM_TIMEOUT = 540


# ============================================================================
# Template machinery
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


# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Problem / prompt loading
# ---------------------------------------------------------------------------

def load_problems_from_csv() -> dict[str, dict]:
    rows = []
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return select_problems(rows)


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Single trial — accepts separate generator + critic models
# ---------------------------------------------------------------------------

def run_trial(
    problem_id: str,
    problem: dict,
    condition_label: str,
    generator_model: str,
    critic_model: str,
    seed: int,
    prompts: dict[str, str],
    log_path: Path,
    log_lock: threading.Lock,
    mock: bool = False,
) -> dict:
    """Run one trial with distinct generator and critic (verifier/reviser) models."""
    from pipeline import generate, verify, revise, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    gen_short  = generator_model.split("/")[-1]
    crit_short = critic_model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{condition_label}|seed={seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    ts_start = time.time()
    loop_log = []

    # --- Generate (uses generator_model) ---
    print(f"{tag} generate ({gen_short})", flush=True)
    solution = generate(
        problem=problem["text"], system=prompts["generator"], model=generator_model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{tag} generate done ({len(solution)} chars, {round(time.time()-ts_start,1)}s)", flush=True)

    # --- Verify / Revise loop (uses critic_model) ---
    stopped_early = False
    for i in range(ITERATIONS):
        print(f"{tag} verify iter={i+1} ({crit_short})", flush=True)
        critique = verify(
            problem=problem["text"], solution=solution, system=prompts["verifier"],
            model=critic_model, max_tokens=MAX_TOKENS, logger=logger, iteration=i+1, mock=mock,
        )
        if "VERDICT: correct" in critique:
            print(f"{tag} verifier satisfied at iter={i+1}", flush=True)
            stopped_early = True
            loop_log.append({"iteration": i+1, "verdict": "correct",
                              "critique": critique, "solution": solution})
            break

        print(f"{tag} revise iter={i+1} ({crit_short})", flush=True)
        new_solution = revise(
            problem=problem["text"], solution=solution, critique=critique,
            system=prompts["reviser"], model=critic_model, max_tokens=MAX_TOKENS,
            logger=logger, iteration=i+1, mock=mock,
        )
        loop_log.append({"iteration": i+1, "verdict": "issues_found",
                          "critique": critique, "solution_before": solution,
                          "solution_after": new_solution})
        solution = new_solution
        print(f"{tag} revised ({len(solution)} chars, {round(time.time()-ts_start,1)}s)", flush=True)

    # --- Judge (always gemini, with ground truth) ---
    gt = problem["solution"] if USE_GROUND_TRUTH else None
    print(f"{tag} judge {'(GT)' if gt else '(no GT)'}", flush=True)
    verdict_text = judge(
        problem=problem["text"], candidate=solution, ground_truth=gt,
        system=prompts["judge"], model=JUDGE_MODEL,
        max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
    )

    # --- Score ---
    score  = parse_gt_score(verdict_text)
    passed = score >= PASS_THRESHOLD

    elapsed = round(time.time() - ts_start, 2)
    print(f"{tag} -> score={score} pass={passed} iters={len(loop_log)} early={stopped_early} {elapsed}s", flush=True)

    return {
        "problem_id":      problem_id,
        "level":           problem["level"],
        "category":        problem.get("category", ""),
        "condition":       condition_label,
        "generator_model": generator_model,
        "critic_model":    critic_model,
        # Keep a "model" field matching template convention so retry logic works
        "model":           condition_label,
        "seed":            seed,
        "score":           score,
        "passed":          passed,
        "iterations_run":  len(loop_log),
        "stopped_early":   stopped_early,
        "elapsed_s":       elapsed,
        "final_solution":  solution,
        "verdict":         verdict_text,
        "loop_log":        loop_log,
    }


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

def run_all(problems, prompts, args) -> tuple[list[dict], Path]:
    problem_ids = sorted(problems.keys())
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    # Enumerate (pid, condition_label, gen_model, crit_model, seed)
    trials = [
        (pid, label, gen, crit, seed)
        for pid in problem_ids
        for (label, gen, crit) in CONDITIONS
        for seed in SEEDS
    ]
    total = len(trials)
    print(f"Submitting {total} trials  (max_workers={MAX_WORKERS})\n", flush=True)

    all_results = []
    completed   = 0

    def _run(pid, label, gen, crit, seed):
        return run_trial(pid, problems[pid], label, gen, crit, seed,
                         prompts, log_path, log_lock, args.mock)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, *t): t for t in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid, label, gen, crit, seed = futs[fut]
            completed += 1
            try:
                all_results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                print(f"[{_ts()}] FAILED [{pid}|{label}|seed={seed}]: {e}", flush=True)
                all_results.append({
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid].get("category", ""),
                    "condition": label, "generator_model": gen, "critic_model": crit,
                    "model": label,
                    "seed": seed, "score": None, "passed": False,
                    "iterations_run": None, "stopped_early": None,
                    "elapsed_s": 0, "final_solution": None, "verdict": None,
                    "loop_log": [], "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    return all_results, log_path


# ---------------------------------------------------------------------------
# Retry mode (402 / credits failures)
# ---------------------------------------------------------------------------

def run_retry(source_path: str, problems, prompts, args) -> tuple[list[dict], Path]:
    with open(source_path, encoding="utf-8") as f:
        original = json.load(f)

    retry_keys = []
    for r in original["all_results"]:
        err = r.get("error", "")
        if "402" in err or "Insufficient credits" in err or "requires more credits" in err:
            retry_keys.append((r["problem_id"], r["condition"],
                                r["generator_model"], r["critic_model"], r["seed"]))

    if not retry_keys:
        print("No retriable (402) failures found.")
        return original["all_results"], Path("/dev/null")

    print(f"Retrying {len(retry_keys)} failed trials:")
    for pid, label, gen, crit, seed in retry_keys:
        print(f"  {pid}  {label}  seed={seed}")
    print()

    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    def _run(pid, label, gen, crit, seed):
        return run_trial(pid, problems[pid], label, gen, crit, seed,
                         prompts, log_path, log_lock, args.mock)

    retry_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, *t): t for t in retry_keys}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * len(retry_keys)):
            pid, label, gen, crit, seed = futs[fut]
            try:
                retry_results[(pid, label, seed)] = fut.result(timeout=TRIAL_TIMEOUT)
            except Exception as e:
                print(f"[{_ts()}] RETRY FAILED [{pid}|{label}|seed={seed}]: {e}", flush=True)
                retry_results[(pid, label, seed)] = {
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid].get("category", ""),
                    "condition": label, "generator_model": gen, "critic_model": crit,
                    "model": label,
                    "seed": seed, "score": None, "passed": False,
                    "iterations_run": None, "stopped_early": None,
                    "elapsed_s": 0, "final_solution": None, "verdict": None,
                    "loop_log": [], "error": str(e),
                }

    merged = []
    for r in original["all_results"]:
        key = (r["problem_id"], r["condition"], r["seed"])
        merged.append(retry_results.pop(key, r))

    print(f"Merged retry entries into original results.\n")
    return merged, log_path


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(all_results: list[dict], problems: dict, log_path: Path, args):
    problem_ids = sorted(problems.keys())
    pass_k      = len(SEEDS)

    # Baselines from previous same-model experiment
    baselines = {
        "nemotron-self": {"pass1_rate": 0.267, "pass1_count": 4,  "pass1_total": 15, "mean_score": 1.933},
        "deepseek-self": {"pass1_rate": 0.333, "pass1_count": 5,  "pass1_total": 15, "mean_score": 2.600},
    }

    print("\n" + "=" * 72)
    print("RESULTS SUMMARY — Cross-Model Pipeline Experiment")
    print("=" * 72)

    condition_labels = [label for label, _, _ in CONDITIONS]
    condition_stats  = {}

    for label, gen_model, crit_model in CONDITIONS:
        gen_short  = gen_model.split("/")[-1]
        crit_short = crit_model.split("/")[-1]

        valid  = [r for r in all_results if r["condition"] == label and r["score"] is not None]
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

        condition_stats[label] = {
            "generator_model": gen_model,
            "critic_model":    crit_model,
            "mean_score":      round(float(np.mean(scores)), 3) if scores else 0.0,
            "std_score":       round(float(np.std(scores)),  3) if scores else 0.0,
            "passk_rate":      round(passk_rate, 3),
            "passk_count":     sum(passk),
            "passk_total":     len(passk),
            "n_valid":         len(valid),
            "n_errors":        sum(1 for r in all_results if r["condition"] == label and r.get("error")),
            "mean_iters":      round(float(np.mean(iters)), 2) if iters else 0.0,
            "stopped_early_n": stopped,
            "distribution":    dist,
        }

        print(f"\nCondition: {label}")
        print(f"  Generator: {gen_short}  |  Critic: {crit_short}")
        print(f"  Mean score:    {condition_stats[label]['mean_score']:.3f} +/- {condition_stats[label]['std_score']:.3f}  (n={len(valid)})")
        print(f"  pass@{pass_k}:      {passk_rate:.1%}  ({sum(passk)}/{len(passk)})")
        print(f"  Avg iters:     {condition_stats[label]['mean_iters']:.2f}  (stopped early: {stopped}/{len(valid)})")
        print(f"  Distribution:  {dist_str}")
        if condition_stats[label]["n_errors"]:
            print(f"  Errors:        {condition_stats[label]['n_errors']}")

    # Comparison table vs baselines
    print("\n" + "-" * 72)
    print("COMPARISON vs SAME-MODEL BASELINES (prev experiment, 15 valid problems)")
    print(f"  {'Condition':<40}  {'pass@1':>6}  {'mean/7':>6}")
    print(f"  {'-'*40}  {'------':>6}  {'------':>6}")

    print(f"  {'nemotron-self (baseline)' :<40}  {baselines['nemotron-self']['pass1_rate']:>5.1%}  {baselines['nemotron-self']['mean_score']:>6.3f}")
    print(f"  {'deepseek-self (baseline)' :<40}  {baselines['deepseek-self']['pass1_rate']:>5.1%}  {baselines['deepseek-self']['mean_score']:>6.3f}")
    for label in condition_labels:
        s = condition_stats[label]
        print(f"  {label:<40}  {s['passk_rate']:>5.1%}  {s['mean_score']:>6.3f}")

    # Per-problem table
    print(f"\n--- Per-problem scores (score/7, i=iters) ---")
    col_w = 28
    hdr  = f"  {'Problem':<26}{'Level':<14}"
    hdr += "".join(f"{c[:col_w]:<{col_w+2}}" for c in condition_labels)
    print(hdr)
    print("  " + "-" * (40 + (col_w + 2) * len(condition_labels)))

    for pid in problem_ids:
        row = f"  {pid:<26}{problems[pid]['level']:<14}"
        for label in condition_labels:
            rs = [r for r in all_results if r["condition"] == label
                  and r["problem_id"] == pid and r["score"] is not None]
            if rs:
                scores_str = "/".join(str(r["score"]) for r in sorted(rs, key=lambda x: x["seed"]))
                flag = "+" if any(r["passed"] for r in rs) else "-"
                cell = f"{flag}[{scores_str}] i={rs[0]['iterations_run']}"
            else:
                cell = "error"
            row += f"{cell:<{col_w+2}}"
        print(row)

    # Save
    output = {
        "experiment":       EXPERIMENT_NAME,
        "description":      DESCRIPTION.strip(),
        "date":             datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pipeline_mode":    PIPELINE_MODE,
        "ground_truth":     USE_GROUND_TRUTH,
        "mock":             args.mock,
        "seeds":            SEEDS,
        "iterations":       ITERATIONS,
        "pass_threshold":   PASS_THRESHOLD,
        "problems":         problem_ids,
        "conditions":       [{"label": l, "generator": g, "critic": c} for l, g, c in CONDITIONS],
        "judge_model":      JUDGE_MODEL,
        "condition_stats":  condition_stats,
        "baselines":        baselines,
        "all_results":      all_results,
    }

    suffix   = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=f"Experiment: {EXPERIMENT_NAME}")
    parser.add_argument("--mock",  action="store_true", help="Smoke test with canned responses")
    parser.add_argument("--retry", metavar="JSON", help="Re-run 402 failures from a previous results file")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problems    = load_problems_from_csv()
    problem_ids = sorted(problems.keys())

    prompts = {
        "generator": load_prompt("generator.md"),
        "verifier":  load_prompt("verifier.md"),
        "reviser":   load_prompt("reviser.md"),
        "judge":     load_prompt("judge.md"),
    }

    n_conditions = len(CONDITIONS)
    n_trials     = len(problem_ids) * n_conditions * len(SEEDS)
    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Mode: {PIPELINE_MODE}  |  GT: {USE_GROUND_TRUTH}  |  Seeds: {SEEDS}  |  Iters: {ITERATIONS}")
    print(f"Problems: {len(problem_ids)}  |  Conditions: {n_conditions}  |  Total trials: {n_trials}")
    for label, gen, crit in CONDITIONS:
        print(f"  [{label}]  gen={gen.split('/')[-1]}  crit={crit.split('/')[-1]}")
    if args.mock:
        print("[MOCK MODE]")
    print()

    if args.retry:
        all_results, log_path = run_retry(args.retry, problems, prompts, args)
    else:
        all_results, log_path = run_all(problems, prompts, args)

    report(all_results, problems, log_path, args)


if __name__ == "__main__":
    main()
