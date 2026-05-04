#!/usr/bin/env python3
"""
Dev-set baseline v2 — fast models, hardened prompts.

6 fast models × 6 dev-set problems × 2 modes (generate-only + full pipeline).
Runs generate-only first, then full pipeline.

Usage:
    uv run experiments/devset_baseline_fast_20260327.py --mock
    uv run experiments/devset_baseline_fast_20260327.py
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
from devset import select_devset, DEV_SET

# ============================================================================
# CONFIGURATION
# ============================================================================

EXPERIMENT_NAME = "devset_baseline_fast"

DESCRIPTION = """
Baseline v2 with hardened judge (DeepMind-style, mode-specific prompts,
extraction fallback) and adversarial verifier. 6 fast models on the 6-problem
dev set, both generate-only and full pipeline modes.
"""

MODELS = [
    "openai/gpt-5.4-mini",
    "gemini/gemini-3-flash-preview",
    "openrouter/qwen/qwen3.5-flash-02-23",
    "openrouter/openai/gpt-oss-120b",
    "openrouter/deepseek/deepseek-v3.2",
    "openrouter/google/gemini-3.1-flash-lite-preview",
]

JUDGE_MODEL = "gemini/gemini-3-flash-preview"

USE_GROUND_TRUTH = True
SEEDS = [42]
PASS_THRESHOLD = 6
ITERATIONS = 3
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 12
TRIAL_TIMEOUT = 900
LITELLM_TIMEOUT = 540

# ============================================================================
# Machinery
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


def load_problems():
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return select_devset(rows)


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def run_trial(
    problem_id, problem, model, seed, prompts, log_path, log_lock,
    pipeline_mode, mock=False,
):
    from pipeline import generate, verify, revise, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    ms = model.split("/")[-1]
    tag = f"[{_ts()}] [{pipeline_mode}|{problem_id}|{ms}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()
    loop_log = []

    # Generate
    print(f"{tag} generate", flush=True)
    solution = generate(
        problem=problem["text"], system=prompts["generator"], model=model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{tag} generate done ({len(solution)} chars, {time.time()-t0:.1f}s)", flush=True)

    # Verify/Revise loop (full mode only)
    stopped_early = False
    if pipeline_mode == "full":
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
            print(f"{tag} revised ({len(solution)} chars, {time.time()-t0:.1f}s)", flush=True)

    # Judge
    gt = problem["solution"]
    judge_prompt = prompts["judge_gt"] if gt else prompts["judge_nogt"]
    print(f"{tag} judge", flush=True)
    verdict_text = judge(
        problem=problem["text"], candidate=solution, ground_truth=gt,
        system=judge_prompt, model=JUDGE_MODEL,
        max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
        extract_prompt=prompts["extract_score"],
    )

    score = parse_gt_score(verdict_text)
    passed = score >= PASS_THRESHOLD
    elapsed = round(time.time() - t0, 2)
    print(f"{tag} → score={score}/7 pass={passed} iters={len(loop_log)} early={stopped_early} {elapsed}s", flush=True)

    return {
        "problem_id": problem_id,
        "level": problem["level"],
        "category": problem.get("category", ""),
        "role": problem.get("role", ""),
        "model": model,
        "seed": seed,
        "pipeline_mode": pipeline_mode,
        "score": score,
        "passed": passed,
        "iterations_run": len(loop_log),
        "stopped_early": stopped_early,
        "elapsed_s": elapsed,
        "final_solution": solution,
        "verdict": verdict_text,
        "loop_log": loop_log,
    }


def run_mode(pipeline_mode, problems, prompts, mock):
    """Run all trials for one mode. Returns list of results."""
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    trials = [(pid, m, s) for pid in sorted(problems) for m in MODELS for s in SEEDS]
    total = len(trials)
    print(f"\n{'='*60}")
    print(f"  MODE: {pipeline_mode.upper()}  ({total} trials)")
    print(f"{'='*60}\n", flush=True)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {
            ex.submit(run_trial, pid, problems[pid], model, seed, prompts,
                      log_path, log_lock, pipeline_mode, mock): (pid, model, seed)
            for pid, model, seed in trials
        }
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid, model, seed = futs[fut]
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = model.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{ms}]: {e}", flush=True)
                results.append({
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid].get("category", ""),
                    "role": problems[pid].get("role", ""),
                    "model": model, "seed": seed, "pipeline_mode": pipeline_mode,
                    "score": None, "passed": False, "iterations_run": None,
                    "stopped_early": None, "elapsed_s": 0, "final_solution": None,
                    "verdict": None, "loop_log": [], "error": str(e),
                })
    return results


def print_comparison(all_results, problems):
    """Print side-by-side generate vs full pipeline table."""
    pids = sorted(problems.keys())

    print(f"\n{'='*120}")
    print("DEV SET BASELINE — FAST MODELS")
    print(f"{'='*120}\n")

    # Per-model summary by mode
    for model in MODELS:
        ms = model.split("/")[-1]
        print(f"\n{ms}:")
        for mode in ("generate", "full"):
            valid = [r for r in all_results if r["model"] == model
                     and r["pipeline_mode"] == mode and r["score"] is not None]
            if not valid:
                print(f"  {mode:10s}  (no results)")
                continue
            scores = [r["score"] for r in valid]
            n_pass = sum(1 for r in valid if r["passed"])
            n_err = sum(1 for r in all_results if r["model"] == model
                        and r["pipeline_mode"] == mode and r.get("error"))
            mean = np.mean(scores)
            errs = f"  errors={n_err}" if n_err else ""
            print(f"  {mode:10s}  mean={mean:.2f}/7  pass={n_pass}/{len(valid)}{errs}")

    # Per-problem comparison table
    col_w = 14
    print(f"\n{'─'*140}")
    hdr = f"  {'Problem':<20} {'Role':<20}"
    for model in MODELS:
        ms = model.split("/")[-1][:col_w]
        hdr += f"  {ms:>{col_w}s}"
    print(hdr)

    for mode in ("generate", "full"):
        print(f"\n  ── {mode.upper()} ──")
        for pid in pids:
            role = problems[pid].get("role", "")[:18]
            row = f"  {pid:<20} {role:<20}"
            for model in MODELS:
                r = [x for x in all_results if x["problem_id"] == pid
                     and x["model"] == model and x["pipeline_mode"] == mode]
                if r and r[0]["score"] is not None:
                    s = r[0]["score"]
                    e = r[0].get("stopped_early", False)
                    mark = "✓" if r[0]["passed"] else "✗"
                    early = "e" if e else ""
                    cell = f"{mark}{s}/7{early}"
                elif r and r[0].get("error"):
                    cell = "ERR"
                else:
                    cell = "—"
                row += f"  {cell:>{col_w}s}"
            print(row)

    # Delta table
    print(f"\n  ── DELTA (full − generate) ──")
    for pid in pids:
        role = problems[pid].get("role", "")[:18]
        row = f"  {pid:<20} {role:<20}"
        for model in MODELS:
            gen = [x for x in all_results if x["problem_id"] == pid
                   and x["model"] == model and x["pipeline_mode"] == "generate"
                   and x["score"] is not None]
            full = [x for x in all_results if x["problem_id"] == pid
                    and x["model"] == model and x["pipeline_mode"] == "full"
                    and x["score"] is not None]
            if gen and full:
                d = full[0]["score"] - gen[0]["score"]
                cell = f"{d:+d}" if d != 0 else "0"
            else:
                cell = "—"
            row += f"  {cell:>{col_w}s}"
        print(row)

    print()


def main():
    parser = argparse.ArgumentParser(description="Dev set baseline — fast models")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()
    print(f"Dev set: {len(problems)} problems  |  Models: {len(MODELS)}")
    print(f"Total trials: {len(problems) * len(MODELS) * len(SEEDS) * 2} (generate + full)")
    for pid, p in sorted(problems.items()):
        print(f"  {pid:<20s}  {p['level']:<18s}  {p.get('role','')}")

    prompts = {
        "generator":     load_prompt("generator.md"),
        "verifier":      load_prompt("verifier.md"),
        "reviser":       load_prompt("reviser.md"),
        "judge_gt":      load_prompt("judge_gt.md"),
        "judge_nogt":    load_prompt("judge_nogt.md"),
        "extract_score": load_prompt("extract_score.md"),
    }

    # Run generate-only first (faster), then full pipeline
    gen_results = run_mode("generate", problems, prompts, args.mock)
    full_results = run_mode("full", problems, prompts, args.mock)

    all_results = gen_results + full_results

    print_comparison(all_results, problems)

    # Save
    ts = _now()
    suffix = "_mock" if args.mock else ""
    output = {
        "experiment": EXPERIMENT_NAME,
        "description": DESCRIPTION.strip(),
        "date": datetime.now(timezone.utc).isoformat(),
        "models": MODELS,
        "judge_model": JUDGE_MODEL,
        "seeds": SEEDS,
        "iterations": ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
        "mock": args.mock,
        "dev_set": {pid: DEV_SET[pid] for pid in sorted(problems)},
        "all_results": all_results,
    }
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {out_path}")


if __name__ == "__main__":
    main()
