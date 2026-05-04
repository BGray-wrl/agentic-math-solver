#!/usr/bin/env python3
"""
Exploratory test of two new cheap models:
  - qwen/qwen3.6-plus:free
  - google/gemma-4-31b-it

Generate-only mode on 5 IMO-easy problems, no ground truth, single seed.
Goal: get a feel for output quality, format, and any errors.

Usage:
    uv run experiments/new_models_explore_20260405.py --mock
    uv run experiments/new_models_explore_20260405.py
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

EXPERIMENT_NAME = "new_models_explore_20260405"

DESCRIPTION = """
Hypothesis: Get a baseline feel for qwen3.6-plus:free and gemma-4-31b-it on easy math problems.
Variables:
  Independent: model (qwen3.6-plus:free vs gemma-4-31b-it)
  Dependent:   classification (correct/almost/partial/incorrect), output quality
  Controlled:  problems (5 IMO-easy), seed (42), generate-only mode
"""

# --- Models ---

MODELS = [
    "openrouter/qwen/qwen3.6-plus:free",
    "openrouter/google/gemma-4-31b-it",
]

JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"

# --- Problems ---

SAMPLE_PROBLEM_IDS = ["PB-Basic-001", "PB-Basic-003", "PB-Basic-004", "PB-Basic-005", "PB-Basic-009"]

def select_problems(all_rows: list[dict]) -> dict[str, dict]:
    problems = {}
    for row in all_rows:
        pid = row["Problem ID"]
        if pid in SAMPLE_PROBLEM_IDS:
            problems[pid] = {
                "text":     row["Problem"],
                "solution": row.get("Solution", ""),
                "level":    row.get("Level", ""),
                "category": row.get("Category", ""),
            }
    return problems

# --- Pipeline mode ---

PIPELINE_MODE = "generate"
USE_GROUND_TRUTH = False

# --- Seeds / metrics ---

SEEDS = [42]
PASS_THRESHOLD = 6

# --- Pipeline parameters ---

ITERATIONS = 0
MAX_TOKENS       = 16000
MAX_TOKENS_JUDGE = 2048

# --- Execution ---

MAX_WORKERS   = 8
TRIAL_TIMEOUT = 300
LITELLM_TIMEOUT = 240


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
    classif_map = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif_map.items():
        if f"CLASSIFICATION: {label}" in verdict:
            return score
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
    problem_id: str,
    problem: dict,
    model: str,
    seed: int,
    prompts: dict[str, str],
    log_path: Path,
    log_lock: threading.Lock,
    mock: bool = False,
) -> dict:
    from pipeline import generate, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    model_short = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{model_short}|seed={seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    ts_start = time.time()

    print(f"{tag} generate", flush=True)
    solution = generate(
        problem=problem["text"], system=prompts["generator"], model=model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{tag} generate done ({len(solution)} chars, {round(time.time()-ts_start,1)}s)", flush=True)

    print(f"{tag} judge (no GT)", flush=True)
    verdict_text = judge(
        problem=problem["text"], candidate=solution, ground_truth=None,
        system=prompts["judge_nogt"], model=JUDGE_MODEL,
        max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
        extract_prompt=prompts["extract_score"],
    )

    label  = parse_classification(verdict_text)
    score  = SCORE_MAP[label]
    passed = label == "correct"

    elapsed = round(time.time() - ts_start, 2)
    print(f"{tag} → label={label} score={score} pass={passed} {elapsed}s", flush=True)

    return {
        "problem_id":     problem_id,
        "level":          problem["level"],
        "category":       problem.get("category", ""),
        "model":          model,
        "seed":           seed,
        "score":          score,
        "label":          label,
        "passed":         passed,
        "iterations_run": 0,
        "stopped_early":  False,
        "elapsed_s":      elapsed,
        "final_solution": solution,
        "verdict":        verdict_text,
        "loop_log":       [],
    }


def run_all(problems, prompts, args) -> tuple[list[dict], Path]:
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
                traceback.print_exc()
                all_results.append({
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid].get("category", ""), "model": model,
                    "seed": seed, "score": None, "label": None, "passed": False,
                    "iterations_run": None, "stopped_early": None,
                    "elapsed_s": 0, "final_solution": None, "verdict": None,
                    "loop_log": [], "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    return all_results, log_path


def report(all_results: list[dict], problems: dict, log_path: Path, args):
    problem_ids = sorted(problems.keys())

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

        dist = {lab: sum(1 for r in valid if r.get("label") == lab)
                for lab in SCORE_MAP}
        dist_str = "  ".join(f"{l}:{dist[l]}" for l in ("correct","almost","partial","incorrect") if dist[l] > 0)

        model_stats[model] = {
            "mean_score": round(float(np.mean(scores)), 3) if scores else 0.0,
            "std_score":  round(float(np.std(scores)), 3) if scores else 0.0,
            "passk_rate": round(passk_rate, 3),
            "n_valid":    len(valid),
            "n_errors":   sum(1 for r in all_results if r["model"] == model and r.get("error")),
            "distribution": dist,
        }

        print(f"\n{ms}")
        print(f"  Mean score:   {model_stats[model]['mean_score']:.3f} ± {model_stats[model]['std_score']:.3f}  (n={len(valid)})")
        print(f"  pass@1:       {passk_rate:.1%}  ({sum(passk)}/{len(passk)})")
        print(f"  Distribution: {dist_str}")
        if model_stats[model]["n_errors"]:
            print(f"  Errors:       {model_stats[model]['n_errors']}")

    print(f"\n--- Per-problem labels ---")
    col_w = 22
    hdr = f"  {'Problem':<26}{'Level':<14}" + "".join(f"{m.split('/')[-1][:col_w]:<{col_w+2}}" for m in MODELS)
    print(hdr)
    print("  " + "-" * (40 + (col_w + 2) * len(MODELS)))
    for pid in problem_ids:
        row = f"  {pid:<26}{problems[pid]['level']:<14}"
        for model in MODELS:
            rs = [r for r in all_results if r["model"] == model and r["problem_id"] == pid]
            if rs and rs[0].get("label"):
                label = rs[0]["label"]
                flag  = "✓" if rs[0]["passed"] else "✗"
                cell  = f"{flag} {label}"
            elif rs and rs[0].get("error"):
                cell = "error"
            else:
                cell = "—"
            row += f"{cell:<{col_w+2}}"
        print(row)

    output = {
        "experiment":    EXPERIMENT_NAME,
        "description":   DESCRIPTION.strip(),
        "date":          datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pipeline_mode": PIPELINE_MODE,
        "ground_truth":  USE_GROUND_TRUTH,
        "mock":          args.mock,
        "seeds":         SEEDS,
        "problems":      problem_ids,
        "models":        MODELS,
        "judge_model":   JUDGE_MODEL,
        "model_stats":   model_stats,
        "all_results":   all_results,
    }

    suffix   = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


def main():
    parser = argparse.ArgumentParser(description=f"Experiment: {EXPERIMENT_NAME}")
    parser.add_argument("--mock", action="store_true", help="Smoke test with canned responses")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems_from_csv()
    problem_ids = sorted(problems.keys())

    prompts = {
        "generator":     load_prompt("generator.md"),
        "judge_nogt":    load_prompt("judge_nogt.md"),
        "extract_score": load_prompt("extract_score.md"),
    }

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Mode: {PIPELINE_MODE}  |  GT: {USE_GROUND_TRUTH}  |  Seeds: {SEEDS}")
    print(f"Problems: {len(problem_ids)}  |  Models: {len(MODELS)}  |  Total trials: {len(problem_ids) * len(MODELS) * len(SEEDS)}")
    if args.mock:
        print("[MOCK MODE]")
    print()

    all_results, log_path = run_all(problems, prompts, args)
    report(all_results, problems, log_path, args)


if __name__ == "__main__":
    main()
