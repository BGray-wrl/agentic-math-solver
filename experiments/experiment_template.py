#!/usr/bin/env python3
"""
Experiment template for the agentic math-solving pipeline.

Copy this file, rename it with a descriptive name + date, and edit the
configuration section. Everything below the "--- Template machinery ---"
line should rarely need changes.

Usage:
    uv run experiments/<your_experiment>.py --mock      # smoke test
    uv run experiments/<your_experiment>.py             # real run
    uv run experiments/<your_experiment>.py --retry <results.json>  # re-run failures
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
# CONFIGURATION — edit this section for each experiment
# ============================================================================

EXPERIMENT_NAME = "template"
"""Short slug used in output filenames. Override per experiment."""

DESCRIPTION = """
Hypothesis: <what you expect to find>
Variables:
  Independent: <what changes>
  Dependent:   <what is measured>
  Controlled:  <what is held fixed>
"""

# --- Models ---

MODELS = [
    "openrouter/nvidia/nemotron-3-super-120b-a12b",
    "openrouter/deepseek/deepseek-v3.2",
]
"""Generator (and optionally verifier/reviser) models to compare."""

JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"
"""Model used for judging. Kept separate from generator models."""

# --- Problems ---

def select_problems(all_rows: list[dict]) -> dict[str, dict]:
    """Filter and return {problem_id: row_dict} from the CSV.

    Override this to change which problems are included.
    Each returned value must have keys: text, solution, level, category.
    """
    problems = {}
    for row in all_rows:
        pid   = row["Problem ID"]
        level = row.get("Level", "")
        # --- EDIT THIS FILTER ---
        if level == "IMO-medium":
            problems[pid] = {
                "text":     row["Problem"],
                "solution": row.get("Solution", ""),
                "level":    level,
                "category": "PB-Advanced" if pid.startswith("PB-Advanced") else "PB-Basic",
            }
    return problems

# --- Pipeline mode ---

PIPELINE_MODE = "full"
"""
'generate'  — generator + judge only (fastest, cheapest)
'full'      — generator → verify ↔ revise loop → judge (3-4x cost)
"""

USE_GROUND_TRUTH = True
"""
True  → Mode A judging (0-7 score, requires ground-truth solution in CSV)
False → Mode B judging (incorrect/partial/almost/correct classification)
"""

# --- Seeds / metrics ---

SEEDS = [42]
"""One seed per entry. len(SEEDS) determines pass@k."""

PASS_THRESHOLD = 6
"""Minimum score (out of 7) to count as 'passed'. Only used with ground-truth."""

# --- Pipeline parameters ---

ITERATIONS = 3
"""Max verify/revise rounds. Only used when PIPELINE_MODE='full'."""

MAX_TOKENS     = 32000
MAX_TOKENS_JUDGE = 4096

# --- Execution ---

MAX_WORKERS    = 16
TRIAL_TIMEOUT  = 900
"""Per-trial timeout in seconds. Full pipeline needs more than generate-only."""

LITELLM_TIMEOUT = 540
"""HTTP-level request timeout for litellm. Should be < TRIAL_TIMEOUT."""


# ============================================================================
# --- Template machinery (edit below here only if you need a new pattern) ---
# ============================================================================

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Mode B score map (only used when USE_GROUND_TRUTH=False)
SCORE_MAP = {"correct": 3, "almost": 2, "partial": 1, "incorrect": 0}


def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _now():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------

def parse_gt_score(verdict: str) -> int:
    """Extract integer score from Mode A verdict (<points>N out of 7</points>).

    Falls back to CLASSIFICATION tag if <points> is missing (judge sometimes
    outputs Mode B format even when ground truth is provided).
    """
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m:
        return int(m.group(1))
    # Fallback: map CLASSIFICATION to approximate score
    classif_map = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif_map.items():
        if f"CLASSIFICATION: {label}" in verdict:
            return score
    return 0


def parse_classification(verdict: str) -> str:
    """Extract label from Mode B verdict (CLASSIFICATION: ...)."""
    for label in ("correct", "almost", "partial", "incorrect"):
        if f"CLASSIFICATION: {label}" in verdict:
            return label
    lower = verdict.lower()
    for label in ("correct", "almost", "partial", "incorrect"):
        if label in lower:
            return label
    return "incorrect"


# ---------------------------------------------------------------------------
# Problem loading
# ---------------------------------------------------------------------------

def load_problems_from_csv() -> dict[str, dict]:
    """Load CSV, delegate filtering to select_problems()."""
    rows = []
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return select_problems(rows)


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Single trial
# ---------------------------------------------------------------------------

def run_trial(
    problem_id: str,
    problem: dict,
    model: str,
    seed: int,
    prompts: dict[str, str],
    log_path: Path,
    log_lock: threading.Lock,
    mock: bool = False,
) -> dict:
    """Run one trial. Returns a result dict with full text (no truncation)."""
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

    # --- Generate ---
    print(f"{tag} generate", flush=True)
    solution = generate(
        problem=problem["text"], system=prompts["generator"], model=model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{tag} generate done ({len(solution)} chars, {round(time.time()-ts_start,1)}s)", flush=True)

    # --- Verify / Revise loop (only in full mode) ---
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

    # --- Judge ---
    gt = problem["solution"] if USE_GROUND_TRUTH else None
    judge_prompt = prompts["judge_gt"] if gt else prompts["judge_nogt"]
    print(f"{tag} judge {'(GT)' if gt else '(no GT)'}", flush=True)
    verdict_text = judge(
        problem=problem["text"], candidate=solution, ground_truth=gt,
        system=judge_prompt, model=JUDGE_MODEL,
        max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
        extract_prompt=prompts["extract_score"],
    )

    # --- Score ---
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
        "problem_id":     problem_id,
        "level":          problem["level"],
        "category":       problem.get("category", ""),
        "model":          model,
        "seed":           seed,
        "score":          score,
        "passed":         passed,
        "iterations_run": len(loop_log),
        "stopped_early":  stopped_early,
        "elapsed_s":      elapsed,
        "final_solution": solution,
        "verdict":        verdict_text,
        "loop_log":       loop_log,
    }


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

def run_all(problems, prompts, args) -> tuple[list[dict], Path]:
    """Run all trials with ThreadPoolExecutor. Returns (results, log_path)."""
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


# ---------------------------------------------------------------------------
# Retry mode
# ---------------------------------------------------------------------------

def run_retry(source_path: str, problems, prompts, args) -> tuple[list[dict], Path]:
    """Re-run only credit/timeout failures from a previous results JSON."""
    with open(source_path, encoding="utf-8") as f:
        original = json.load(f)

    retry_keys = []
    for r in original["all_results"]:
        err = r.get("error", "")
        if "402" in err or "Insufficient credits" in err or "requires more credits" in err:
            retry_keys.append((r["problem_id"], r["model"], r["seed"]))

    if not retry_keys:
        print("No retriable (402) failures found.")
        return original["all_results"], Path("/dev/null")

    print(f"Retrying {len(retry_keys)} failed trials:")
    for pid, model, seed in retry_keys:
        print(f"  {pid}  {model.split('/')[-1]}  seed={seed}")
    print()

    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    def _run(pid, model, seed):
        return run_trial(pid, problems[pid], model, seed, prompts, log_path, log_lock, args.mock)

    retry_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, *t): t for t in retry_keys}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * len(retry_keys)):
            pid, model, seed = futs[fut]
            try:
                retry_results[(pid, model, seed)] = fut.result(timeout=TRIAL_TIMEOUT)
            except Exception as e:
                ms = model.split("/")[-1]
                print(f"[{_ts()}] RETRY FAILED [{pid}|{ms}|seed={seed}]: {e}", flush=True)
                retry_results[(pid, model, seed)] = {
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid].get("category", ""), "model": model,
                    "seed": seed, "score": None, "passed": False,
                    "iterations_run": None, "stopped_early": None,
                    "elapsed_s": 0, "final_solution": None, "verdict": None,
                    "loop_log": [], "error": str(e),
                }

    merged = []
    for r in original["all_results"]:
        key = (r["problem_id"], r["model"], r["seed"])
        merged.append(retry_results.pop(key, r))

    print(f"Merged {len(retry_results)} retried entries into original results.\n")
    return merged, log_path


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(all_results: list[dict], problems: dict, log_path: Path, args):
    """Print summary tables and save JSON."""
    problem_ids = sorted(problems.keys())
    pass_k      = len(SEEDS)
    max_score   = 7 if USE_GROUND_TRUTH else 3

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    model_stats = {}
    for model in MODELS:
        ms    = model.split("/")[-1]
        valid = [r for r in all_results if r["model"] == model and r["score"] is not None]
        scores = [r["score"] for r in valid]

        # pass@k: per problem, did at least one seed pass?
        passk = []
        for pid in problem_ids:
            pid_r = [r for r in valid if r["problem_id"] == pid]
            if pid_r:
                passk.append(any(r["passed"] for r in pid_r))
        passk_rate = float(np.mean(passk)) if passk else 0.0

        iters   = [r["iterations_run"] for r in valid if r.get("iterations_run") is not None]
        stopped = sum(1 for r in valid if r.get("stopped_early"))

        if USE_GROUND_TRUTH:
            dist = {k: sum(1 for s in scores if s == k) for k in range(8)}
            dist_str = "  ".join(f"{k}/7:{v}" for k, v in dist.items() if v > 0)
        else:
            dist = {lab: sum(1 for r in valid if parse_classification(r.get("verdict","")) == lab)
                    for lab in SCORE_MAP}
            dist_str = "/".join(str(dist.get(l,0)) for l in ("correct","almost","partial","incorrect"))

        model_stats[model] = {
            "mean_score":  round(float(np.mean(scores)), 3) if scores else 0.0,
            "std_score":   round(float(np.std(scores)), 3) if scores else 0.0,
            "passk_rate":  round(passk_rate, 3),
            "passk_count": sum(passk),
            "passk_total": len(passk),
            "n_valid":     len(valid),
            "n_errors":    sum(1 for r in all_results if r["model"] == model and r.get("error")),
            "mean_iters":  round(float(np.mean(iters)), 2) if iters else 0.0,
            "stopped_early_n": stopped,
            "distribution": dist,
        }

        print(f"\n{ms}")
        print(f"  Mean score:    {model_stats[model]['mean_score']:.3f} ± {model_stats[model]['std_score']:.3f}  (n={len(valid)})")
        print(f"  pass@{pass_k}:      {passk_rate:.1%}  ({sum(passk)}/{len(passk)})")
        if PIPELINE_MODE == "full":
            print(f"  Avg iters:     {model_stats[model]['mean_iters']:.2f}  (stopped early: {stopped}/{len(valid)})")
        print(f"  Distribution:  {dist_str}")
        if model_stats[model]["n_errors"]:
            print(f"  Errors:        {model_stats[model]['n_errors']}")

    # Per-level breakdown
    levels = sorted({r["level"] for r in all_results if r.get("level")})
    if len(levels) > 1:
        for level in levels:
            print(f"\n--- {level} ---")
            for model in MODELS:
                ms = model.split("/")[-1]
                lr = [r for r in all_results if r["model"] == model and r["level"] == level and r["score"] is not None]
                if lr:
                    s = [r["score"] for r in lr]
                    pk = []
                    for pid in problem_ids:
                        pr = [r for r in lr if r["problem_id"] == pid]
                        if pr:
                            pk.append(any(r["passed"] for r in pr))
                    print(f"  {ms:<45}  mean={np.mean(s):.2f}±{np.std(s):.2f}  pass@{pass_k}={np.mean(pk):.1%}  ({sum(pk)}/{len(pk)})")

    # Per-problem table
    print(f"\n--- Per-problem scores ---")
    col_w = 24
    hdr = f"  {'Problem':<26}{'Level':<14}" + "".join(f"{m.split('/')[-1][:col_w]:<{col_w+2}}" for m in MODELS)
    print(hdr)
    print("  " + "-" * (40 + (col_w + 2) * len(MODELS)))
    for pid in problem_ids:
        row = f"  {pid:<26}{problems[pid]['level']:<14}"
        for model in MODELS:
            rs = [r for r in all_results if r["model"] == model and r["problem_id"] == pid and r["score"] is not None]
            if rs:
                scores_str = "/".join(str(r["score"]) for r in sorted(rs, key=lambda x: x["seed"]))
                flag = "✓" if any(r["passed"] for r in rs) else "✗"
                cell = f"{flag} [{scores_str}]"
                if PIPELINE_MODE == "full" and len(rs) == 1:
                    cell += f" i={rs[0]['iterations_run']}"
            else:
                cell = "error"
            row += f"{cell:<{col_w+2}}"
        print(row)

    # --- Save ---
    output = {
        "experiment":      EXPERIMENT_NAME,
        "description":     DESCRIPTION.strip(),
        "date":            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pipeline_mode":   PIPELINE_MODE,
        "ground_truth":    USE_GROUND_TRUTH,
        "mock":            args.mock,
        "seeds":           SEEDS,
        "iterations":      ITERATIONS if PIPELINE_MODE == "full" else 0,
        "pass_threshold":  PASS_THRESHOLD,
        "problems":        problem_ids,
        "models":          MODELS,
        "judge_model":     JUDGE_MODEL,
        "model_stats":     model_stats,
        "all_results":     all_results,
    }

    suffix   = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=f"Experiment: {EXPERIMENT_NAME}")
    parser.add_argument("--mock", action="store_true", help="Smoke test with canned responses")
    parser.add_argument("--retry", metavar="JSON", help="Re-run 402 failures from a previous results file")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems_from_csv()
    problem_ids = sorted(problems.keys())

    prompts = {
        "generator":     load_prompt("generator.md"),
        "judge_gt":      load_prompt("judge_gt.md"),
        "judge_nogt":    load_prompt("judge_nogt.md"),
        "extract_score": load_prompt("extract_score.md"),
    }
    if PIPELINE_MODE == "full":
        prompts["verifier"] = load_prompt("verifier.md")
        prompts["reviser"]  = load_prompt("reviser.md")

    # Header
    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Mode: {PIPELINE_MODE}  |  GT: {USE_GROUND_TRUTH}  |  Seeds: {SEEDS}  |  Iters: {ITERATIONS}")
    print(f"Problems: {len(problem_ids)}  |  Models: {len(MODELS)}  |  Total trials: {len(problem_ids) * len(MODELS) * len(SEEDS)}")
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
