#!/usr/bin/env python3
"""
Pass@3 follow-up to new_models_compare_20260504.

Same setup, but 3 seeds per (model, problem) and dropping the two slowest
models (deepseek-v4-pro, qwen3.6-plus). Goal: get a more reliable mean and
pass@3 number for the cost-effective tier in <10 min wall-clock.

6 models × 6 problems × 3 seeds = 108 trials.

Usage:
    uv run experiments/new_models_pass3_20260504.py --mock
    uv run experiments/new_models_pass3_20260504.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import itertools
import json
import os
import random
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402

from devset import select_devset, DEV_SET  # noqa: E402

# ============================================================================
# Configuration
# ============================================================================

EXPERIMENT_NAME = "new_models_pass3_20260504"

# Models to test, with user-supplied prices ($/M tokens, blended).
# Dropping deepseek-v4-pro and qwen3.6-plus per user request (slow / pricey).
NEW_MODELS = [
    ("openrouter/qwen/qwen3.6-35b-a3b",       1.00),
    ("openrouter/qwen/qwen3.6-flash",         1.50),
    ("openrouter/google/gemma-4-31b-it",      0.38),
    ("openrouter/deepseek/deepseek-v4-flash", 0.28),
]

BASELINE_MODELS = [
    ("openrouter/google/gemini-3-flash-preview", 3.00),
    ("openrouter/deepseek/deepseek-v3.2",        0.378),
]

ALL_MODELS = NEW_MODELS + BASELINE_MODELS
PRICE_PER_MTOKEN = {m: p for m, p in ALL_MODELS}

JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"

SEEDS = [42, 0, 1]
PASS_THRESHOLD = 6  # ≥6/7 counts as pass

MAX_TOKENS_GEN   = 16000
MAX_TOKENS_JUDGE = 16000

# 108 trials, 3 keys, ~60 workers — try to fit each trial into 1-2 waves
MAX_WORKERS     = 60
TRIAL_TIMEOUT   = 540
LITELLM_TIMEOUT = 480

# ============================================================================
# Paths and key rotation
# ============================================================================

ROOT = Path(__file__).parent.parent
PROMPTS_DIR    = ROOT / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
BENCHMARKS_CSV = ROOT / "benchmarks" / "combined-benchmarks.csv"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


load_dotenv()
KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_X2"),
] if k]
if not KEYS:
    raise SystemExit("No OPENROUTER_API_KEY* found in .env")

_key_iter = itertools.cycle(KEYS)
_key_lock = threading.Lock()
def next_key() -> str:
    with _key_lock:
        return next(_key_iter)


# ============================================================================
# LLM call
# ============================================================================

def call_model(model, system, prompt, max_tokens, retries=2, backoff=4.0):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_err = None
    for attempt in range(retries + 1):
        key = next_key()
        try:
            resp = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                api_key=key,
                timeout=LITELLM_TIMEOUT,
            )
            content = resp.choices[0].message.content  # type: ignore
            if content is None:
                content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
            if content is None:
                raise ValueError(f"Model {model} returned None content")
            usage = getattr(resp, "usage", None)
            usage_dict = {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
            }
            return content, usage_dict
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1} failed: {e}, retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


# ============================================================================
# Score parsing
# ============================================================================

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


def load_problems() -> dict:
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return select_devset(rows)


# ============================================================================
# Single trial
# ============================================================================

def run_trial(problem_id, problem, model, seed, prompts, mock):
    np.random.seed(seed)
    random.seed(seed)
    ms = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{ms}|seed={seed}]"
    t0 = time.time()

    if mock:
        time.sleep(0.01)
        return _mk_result(problem_id, problem, model, seed,
                          score=7, gen_text="mock", verdict="mock",
                          gen_usage={"prompt_tokens":100,"completion_tokens":50,"total_tokens":150},
                          judge_usage={"prompt_tokens":200,"completion_tokens":30,"total_tokens":230},
                          gen_elapsed=0.01, judge_elapsed=0.01, elapsed_total=0.01)

    print(f"{tag} generate", flush=True)
    gen_t0 = time.time()
    try:
        gen_text, gen_usage = call_model(model, prompts["generator"], problem["text"], MAX_TOKENS_GEN)
        gen_elapsed = round(time.time() - gen_t0, 2)
        print(f"{tag} gen {gen_elapsed}s in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']}", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} GEN FAILED: {e} ({elapsed}s)", flush=True)
        return _err(problem_id, problem, model, seed, str(e), elapsed)

    judge_prompt = (prompts["judge_gt"]
                    .replace("{problem}", problem["text"])
                    .replace("{ground_truth}", problem["solution"])
                    .replace("{candidate}", gen_text))
    judge_t0 = time.time()
    try:
        judge_text, judge_usage = call_model(JUDGE_MODEL, None, judge_prompt, MAX_TOKENS_JUDGE)
        judge_elapsed = round(time.time() - judge_t0, 2)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} JUDGE FAILED: {e} ({elapsed}s)", flush=True)
        return _err(problem_id, problem, model, seed, f"judge: {e}", elapsed,
                    gen_text=gen_text, gen_usage=gen_usage, gen_elapsed=gen_elapsed)

    score = parse_gt_score(judge_text)
    elapsed_total = round(time.time() - t0, 2)
    print(f"{tag} → score={score}/7 total={elapsed_total}s", flush=True)
    return _mk_result(problem_id, problem, model, seed, score, gen_text, judge_text,
                      gen_usage, judge_usage, gen_elapsed, judge_elapsed, elapsed_total)


def _mk_result(pid, problem, model, seed, score, gen_text, verdict,
               gen_usage, judge_usage, gen_elapsed, judge_elapsed, elapsed_total):
    price = PRICE_PER_MTOKEN.get(model)
    est_cost = round(price * gen_usage["total_tokens"] / 1_000_000, 6) if price else None
    return {
        "problem_id":      pid,
        "level":           problem["level"],
        "category":        problem.get("category", ""),
        "role":            problem.get("role", ""),
        "model":           model,
        "seed":            seed,
        "score":           score,
        "passed":          score >= PASS_THRESHOLD,
        "elapsed_s":       elapsed_total,
        "gen_elapsed_s":   gen_elapsed,
        "judge_elapsed_s": judge_elapsed,
        "gen_usage":       gen_usage,
        "judge_usage":     judge_usage,
        "est_cost_usd":    est_cost,
        "final_solution":  gen_text,
        "verdict":         verdict,
    }


def _err(pid, problem, model, seed, err, elapsed,
         gen_text=None, gen_usage=None, gen_elapsed=None):
    return {
        "problem_id":     pid,
        "level":          problem["level"],
        "category":       problem.get("category", ""),
        "role":           problem.get("role", ""),
        "model":          model,
        "seed":           seed,
        "score":          None,
        "passed":         False,
        "elapsed_s":      elapsed,
        "gen_elapsed_s":  gen_elapsed,
        "judge_elapsed_s": None,
        "gen_usage":      gen_usage,
        "judge_usage":    None,
        "est_cost_usd":   None,
        "final_solution": gen_text,
        "verdict":        None,
        "error":          err,
    }


# ============================================================================
# Executor
# ============================================================================

def run_all(problems, prompts, mock):
    pids = sorted(problems.keys())
    trials = [(pid, m, s) for pid in pids for m, _ in ALL_MODELS for s in SEEDS]
    total = len(trials)
    print(f"Submitting {total} trials across {len(KEYS)} keys, max_workers={MAX_WORKERS}\n", flush=True)

    results, completed = [], 0
    def _run(pid, m, s):
        return run_trial(pid, problems[pid], m, s, prompts, mock)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, pid, m, s): (pid, m, s) for pid, m, s in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid, m, s = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = m.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{ms}|seed={s}]: {e}", flush=True)
                results.append(_err(pid, problems[pid], m, s, str(e), 0))
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)
    return results


# ============================================================================
# Reporting
# ============================================================================

def report(results, problems, mock):
    pids = sorted(problems.keys())
    print("\n" + "=" * 100)
    print("PASS@3 COMPARISON — same dev set, 3 seeds per (model, problem)")
    print("=" * 100)

    summary = {}
    for model, price in ALL_MODELS:
        ms = model.split("/")[-1]
        rs = [r for r in results if r["model"] == model]
        valid = [r for r in rs if r["score"] is not None]
        scores = [r["score"] for r in valid]
        gen_lat = [r["gen_elapsed_s"] for r in valid if r.get("gen_elapsed_s") is not None]
        out_tok = [r["gen_usage"]["completion_tokens"] for r in valid if r.get("gen_usage")]
        in_tok  = [r["gen_usage"]["prompt_tokens"]     for r in valid if r.get("gen_usage")]
        costs   = [r["est_cost_usd"] for r in valid if r.get("est_cost_usd") is not None]
        n_err   = sum(1 for r in rs if r.get("error"))

        # pass@3: per problem, did at least one seed pass?
        pass3 = []
        per_problem_means = []
        for pid in pids:
            pid_rs = [r for r in valid if r["problem_id"] == pid]
            if pid_rs:
                pass3.append(any(r["passed"] for r in pid_rs))
                per_problem_means.append(np.mean([r["score"] for r in pid_rs]))

        summary[model] = {
            "ms":           ms,
            "price_per_mtoken": price,
            "n_trials":     len(rs),
            "n_valid":      len(valid),
            "n_errors":     n_err,
            "n_seeds":      len(SEEDS),
            "mean_score":   round(float(np.mean(scores)), 3) if scores else 0.0,
            "std_score":    round(float(np.std(scores)),  3) if scores else 0.0,
            "pass3_rate":   round(float(np.mean(pass3)), 3) if pass3 else 0.0,
            "n_pass3":      sum(pass3),
            "n_problems":   len(pass3),
            "mean_per_problem_mean": round(float(np.mean(per_problem_means)), 3) if per_problem_means else 0.0,
            "mean_gen_lat": round(float(np.mean(gen_lat)), 1) if gen_lat else 0.0,
            "mean_in_tok":  int(np.mean(in_tok))  if in_tok  else 0,
            "mean_out_tok": int(np.mean(out_tok)) if out_tok else 0,
            "mean_cost":    round(float(np.mean(costs)), 4) if costs else None,
            "total_cost":   round(float(np.sum(costs)), 3) if costs else None,
        }

    print(f"\n{'Model':<32} {'$/Mt':>6} {'n':>4} {'err':>3}  {'mean':>5}  {'pass@3':>7}  {'lat(s)':>7}  {'out_tok':>7}  {'$/run':>8}  {'$ tot':>7}")
    print("-" * 110)
    for model, _ in sorted(ALL_MODELS, key=lambda x: -summary[x[0]]["mean_score"]):
        s = summary[model]
        price_s = f"${s['price_per_mtoken']:.2f}" if s['price_per_mtoken'] else "—"
        cost_s  = f"${s['mean_cost']:.4f}" if s['mean_cost'] is not None else "—"
        tcost_s = f"${s['total_cost']:.3f}" if s['total_cost'] is not None else "—"
        print(f"{s['ms']:<32} {price_s:>6} {s['n_valid']:>4} {s['n_errors']:>3}  "
              f"{s['mean_score']:>5.2f}  {s['n_pass3']}/{s['n_problems']}  "
              f"{s['mean_gen_lat']:>7.1f}  {s['mean_out_tok']:>7}  {cost_s:>8}  {tcost_s:>7}")

    # Per-problem table — show 3 scores per (model, problem) as [a/b/c]
    print(f"\n--- Per-problem scores [seed42 / seed0 / seed1] ---")
    col_w = 18
    hdr = f"  {'Problem':<14}{'Role':<22}"
    for m, _ in ALL_MODELS:
        hdr += f"{m.split('/')[-1][:col_w-2]:>{col_w}}"
    print(hdr)
    for pid in pids:
        role = problems[pid].get("role", "")[:20]
        row = f"  {pid:<14}{role:<22}"
        for model, _ in ALL_MODELS:
            rs = [r for r in results if r["model"] == model and r["problem_id"] == pid]
            rs.sort(key=lambda r: SEEDS.index(r["seed"]) if r.get("seed") in SEEDS else 99)
            cells = []
            for r in rs:
                if r.get("error"):
                    cells.append("E")
                elif r["score"] is None:
                    cells.append("—")
                else:
                    cells.append(str(r["score"]))
            cell = "/".join(cells)
            row += f"{cell:>{col_w}}"
        print(row)

    suffix = "_mock" if mock else ""
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment":     EXPERIMENT_NAME,
            "date":           datetime.now(timezone.utc).isoformat(),
            "mock":           mock,
            "seeds":          SEEDS,
            "pass_threshold": PASS_THRESHOLD,
            "n_keys":         len(KEYS),
            "max_workers":    MAX_WORKERS,
            "judge_model":    JUDGE_MODEL,
            "models":         [{"id": m, "price_per_mtoken": p} for m, p in ALL_MODELS],
            "dev_set":        {pid: DEV_SET[pid] for pid in sorted(problems)},
            "summary":        {summary[m]["ms"]: summary[m] for m, _ in ALL_MODELS},
            "all_results":    results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()
    prompts = {
        "generator": load_prompt("generator.md"),
        "judge_gt":  load_prompt("judge_gt.md"),
    }
    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Models:        {len(ALL_MODELS)}  Problems: {len(problems)}  Seeds: {SEEDS}")
    print(f"Total trials:  {len(ALL_MODELS) * len(problems) * len(SEEDS)}")
    print(f"Keys:          {len(KEYS)}  Workers: {MAX_WORKERS}")
    if args.mock:
        print("[MOCK MODE]")
    print()

    t0 = time.time()
    results = run_all(problems, prompts, args.mock)
    print(f"\nWall-clock: {round(time.time()-t0, 1)}s for {len(results)} trials")
    report(results, problems, args.mock)


if __name__ == "__main__":
    main()
