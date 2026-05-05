#!/usr/bin/env python3
"""
Quick reference comparison of 6 newly-released models vs. existing baselines.

Models under test (user-supplied prices in $/M tokens):
  qwen/qwen3.6-35b-a3b      $1.00
  qwen/qwen3.6-flash        $1.50
  qwen/qwen3.6-plus         $1.95   (subset of problems only — more expensive)
  google/gemma-4-31b-it     $0.38
  deepseek/deepseek-v4-pro  $0.87
  deepseek/deepseek-v4-flash $0.28

Baselines for direct comparison:
  google/gemini-3-flash-preview  (current top dev-set performer)
  deepseek/deepseek-v3.2         (direct upgrade comparison vs v4)

Mode: generate-only on the 6-problem dev set (qwen3.6-plus on 3-problem subset).
Judge: gemini-3-flash-preview (Mode A, ground truth, 0-7).
Single seed (42), pass@1.

Parallelization: 3 OpenRouter keys round-robin via litellm api_key=, 24 workers.

Reports per model: mean score, pass rate, mean latency, total tokens, est cost.

Usage:
    uv run experiments/new_models_compare_20260504.py --mock
    uv run experiments/new_models_compare_20260504.py
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

EXPERIMENT_NAME = "new_models_compare_20260504"

# Models to test, with user-supplied prices ($/M tokens, blended).
NEW_MODELS = [
    ("openrouter/qwen/qwen3.6-35b-a3b",       1.00),
    ("openrouter/qwen/qwen3.6-flash",         1.50),
    ("openrouter/qwen/qwen3.6-plus",          1.95),  # subset only
    ("openrouter/google/gemma-4-31b-it",      0.38),
    ("openrouter/deepseek/deepseek-v4-pro",   0.87),
    ("openrouter/deepseek/deepseek-v4-flash", 0.28),
]

# Strong reference baselines we already use.
BASELINE_MODELS = [
    ("openrouter/google/gemini-3-flash-preview", None),  # cost unknown — for accuracy comparison only
    ("openrouter/deepseek/deepseek-v3.2",        None),
]

ALL_MODELS = NEW_MODELS + BASELINE_MODELS
PRICE_PER_MTOKEN = {m: p for m, p in ALL_MODELS}

# Run qwen3.6-plus on a smaller subset to control cost (it's the priciest).
QWEN_PLUS_MODEL = "openrouter/qwen/qwen3.6-plus"
QWEN_PLUS_SUBSET = ["PB-Basic-024", "PB-Basic-012", "PB-Basic-007"]  # sanity, boundary, hard

JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"

SEED = 42
PASS_THRESHOLD = 6  # ≥6/7 counts as pass

MAX_TOKENS_GEN   = 16000
MAX_TOKENS_JUDGE = 16000

MAX_WORKERS     = 24
TRIAL_TIMEOUT   = 600  # seconds per trial
LITELLM_TIMEOUT = 540

# ============================================================================
# Paths and key rotation
# ============================================================================

ROOT = Path(__file__).parent.parent
PROMPTS_DIR    = ROOT / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
BENCHMARKS_CSV = ROOT / "benchmarks" / "combined-benchmarks.csv"
LOGS_DIR       = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)


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
# LLM call (with key rotation, retries, token capture)
# ============================================================================

def call_model(
    model: str,
    system: str | None,
    prompt: str,
    max_tokens: int,
    retries: int = 2,
    backoff: float = 5.0,
) -> tuple[str, dict]:
    """Call a model via litellm with rotating OpenRouter keys.

    Returns (text, usage_dict) where usage_dict has prompt_tokens,
    completion_tokens, total_tokens (zeros if not reported).
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_err: Exception | None = None
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
    assert last_err is not None
    raise last_err


# ============================================================================
# Score parsing (mirrors template)
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


def load_problems() -> dict[str, dict]:
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return select_devset(rows)


# ============================================================================
# Single trial (generate + judge)
# ============================================================================

def run_trial(
    problem_id: str,
    problem: dict,
    model: str,
    prompts: dict[str, str],
    mock: bool,
) -> dict:
    np.random.seed(SEED)
    random.seed(SEED)

    ms = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{ms}]"
    t0 = time.time()

    if mock:
        gen_text  = "Mock solution.\n\n<answer>42</answer>"
        gen_usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        gen_elapsed = 0.01
        judge_text = "Looks good.\n<points>7 out of 7</points>"
        judge_usage = {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230}
        judge_elapsed = 0.01
        score = 7
        time.sleep(0.01)
    else:
        # Generate
        print(f"{tag} generate", flush=True)
        gen_t0 = time.time()
        try:
            gen_text, gen_usage = call_model(
                model=model,
                system=prompts["generator"],
                prompt=problem["text"],
                max_tokens=MAX_TOKENS_GEN,
            )
            gen_elapsed = round(time.time() - gen_t0, 2)
            print(f"{tag} generated {len(gen_text)} chars in {gen_elapsed}s "
                  f"(in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']})", flush=True)
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            print(f"{tag} GEN FAILED: {e} ({elapsed}s)", flush=True)
            return _err_result(problem_id, problem, model, str(e), elapsed)

        # Judge
        print(f"{tag} judge", flush=True)
        judge_t0 = time.time()
        gt = problem["solution"]
        judge_prompt = (
            prompts["judge_gt"]
            .replace("{problem}", problem["text"])
            .replace("{ground_truth}", gt)
            .replace("{candidate}", gen_text)
        )
        try:
            judge_text, judge_usage = call_model(
                model=JUDGE_MODEL,
                system=None,
                prompt=judge_prompt,
                max_tokens=MAX_TOKENS_JUDGE,
            )
            judge_elapsed = round(time.time() - judge_t0, 2)
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            print(f"{tag} JUDGE FAILED: {e} ({elapsed}s)", flush=True)
            return _err_result(problem_id, problem, model, f"judge: {e}", elapsed,
                               gen_text=gen_text, gen_usage=gen_usage, gen_elapsed=gen_elapsed)

        score = parse_gt_score(judge_text)

    elapsed_total = round(time.time() - t0, 2)
    passed = score >= PASS_THRESHOLD

    # Cost (only for models with known prices)
    price = PRICE_PER_MTOKEN.get(model)
    est_cost = None
    if price is not None and not mock:
        est_cost = round(price * gen_usage["total_tokens"] / 1_000_000, 6)

    print(f"{tag} → score={score}/7 pass={passed} total={elapsed_total}s", flush=True)

    return {
        "problem_id":      problem_id,
        "level":           problem["level"],
        "category":        problem.get("category", ""),
        "role":            problem.get("role", ""),
        "model":           model,
        "seed":            SEED,
        "score":           score,
        "passed":          passed,
        "elapsed_s":       elapsed_total,
        "gen_elapsed_s":   gen_elapsed,
        "judge_elapsed_s": judge_elapsed,
        "gen_usage":       gen_usage,
        "judge_usage":     judge_usage,
        "est_cost_usd":    est_cost,
        "final_solution":  gen_text,
        "verdict":         judge_text,
    }


def _err_result(problem_id, problem, model, err, elapsed,
                gen_text=None, gen_usage=None, gen_elapsed=None):
    return {
        "problem_id": problem_id,
        "level":      problem["level"],
        "category":   problem.get("category", ""),
        "role":       problem.get("role", ""),
        "model":      model,
        "seed":       SEED,
        "score":      None,
        "passed":     False,
        "elapsed_s":  elapsed,
        "gen_elapsed_s":   gen_elapsed,
        "judge_elapsed_s": None,
        "gen_usage":       gen_usage,
        "judge_usage":     None,
        "est_cost_usd":    None,
        "final_solution":  gen_text,
        "verdict":         None,
        "error":           err,
    }


# ============================================================================
# Trial assembly + executor
# ============================================================================

def build_trials(problems: dict) -> list[tuple[str, str]]:
    """Return list of (problem_id, model) trials.

    Skips qwen3.6-plus on problems outside its subset.
    """
    pids = sorted(problems.keys())
    trials: list[tuple[str, str]] = []
    for model, _ in ALL_MODELS:
        for pid in pids:
            if model == QWEN_PLUS_MODEL and pid not in QWEN_PLUS_SUBSET:
                continue
            trials.append((pid, model))
    return trials


def run_all(problems: dict, prompts: dict, mock: bool) -> list[dict]:
    trials = build_trials(problems)
    total = len(trials)
    print(f"Submitting {total} trials across {len(KEYS)} keys with max_workers={MAX_WORKERS}\n", flush=True)

    results: list[dict] = []
    completed = 0

    def _run(pid, model):
        return run_trial(pid, problems[pid], model, prompts, mock)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, pid, m): (pid, m) for pid, m in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid, model = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = model.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{ms}]: {e}", flush=True)
                traceback.print_exc()
                results.append(_err_result(pid, problems[pid], model, str(e), 0))
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)
    return results


# ============================================================================
# Reporting
# ============================================================================

def report(results: list[dict], problems: dict, mock: bool) -> Path:
    pids = sorted(problems.keys())
    print("\n" + "=" * 90)
    print("NEW MODELS COMPARISON — accuracy / cost / latency")
    print("=" * 90)

    summary = {}
    for model, price in ALL_MODELS:
        ms = model.split("/")[-1]
        rs = [r for r in results if r["model"] == model]
        valid = [r for r in rs if r["score"] is not None]
        scores = [r["score"] for r in valid]
        passed = [r["passed"] for r in valid]
        gen_lat = [r["gen_elapsed_s"] for r in valid if r.get("gen_elapsed_s") is not None]
        gen_in_tok  = [r["gen_usage"]["prompt_tokens"]     for r in valid if r.get("gen_usage")]
        gen_out_tok = [r["gen_usage"]["completion_tokens"] for r in valid if r.get("gen_usage")]
        gen_tot_tok = [r["gen_usage"]["total_tokens"]      for r in valid if r.get("gen_usage")]
        costs = [r["est_cost_usd"] for r in valid if r.get("est_cost_usd") is not None]
        n_err = sum(1 for r in rs if r.get("error"))

        n = len(valid)
        mean_score   = float(np.mean(scores)) if scores else 0.0
        std_score    = float(np.std(scores))  if scores else 0.0
        pass_rate    = float(np.mean(passed)) if passed else 0.0
        mean_lat     = float(np.mean(gen_lat)) if gen_lat else 0.0
        median_lat   = float(np.median(gen_lat)) if gen_lat else 0.0
        mean_in_tok  = float(np.mean(gen_in_tok))  if gen_in_tok  else 0.0
        mean_out_tok = float(np.mean(gen_out_tok)) if gen_out_tok else 0.0
        mean_cost    = float(np.mean(costs)) if costs else None
        total_cost   = float(np.sum(costs))  if costs else None

        summary[model] = {
            "ms":          ms,
            "price_per_mtoken": price,
            "n_trials":    len(rs),
            "n_valid":     n,
            "n_errors":    n_err,
            "mean_score":  round(mean_score, 3),
            "std_score":   round(std_score, 3),
            "pass_rate":   round(pass_rate, 3),
            "n_passed":    sum(passed),
            "mean_gen_latency_s":   round(mean_lat, 2),
            "median_gen_latency_s": round(median_lat, 2),
            "mean_in_tokens":       round(mean_in_tok),
            "mean_out_tokens":      round(mean_out_tok),
            "mean_cost_usd":        round(mean_cost, 4) if mean_cost is not None else None,
            "total_cost_usd":       round(total_cost, 4) if total_cost is not None else None,
        }

    # Pretty print
    print(f"\n{'Model':<40} {'$/Mt':>6} {'n':>3} {'err':>3}  {'mean':>5}  {'pass':>6}  {'lat(s)':>7}  {'in_tok':>7}  {'out_tok':>7}  {'$/run':>7}  {'$ tot':>7}")
    print("-" * 130)
    # Sort: new models first (with prices), then baselines
    def _sort_key(item):
        m, p = item
        return (0 if p is not None else 1, m)
    for model, price in sorted(ALL_MODELS, key=_sort_key):
        s = summary[model]
        price_s = f"${price:.2f}" if price is not None else "—"
        cost_s  = f"${s['mean_cost_usd']:.4f}" if s['mean_cost_usd'] is not None else "—"
        tcost_s = f"${s['total_cost_usd']:.3f}" if s['total_cost_usd'] is not None else "—"
        print(f"{s['ms']:<40} {price_s:>6} {s['n_valid']:>3} {s['n_errors']:>3}  "
              f"{s['mean_score']:>5.2f}  {s['n_passed']}/{s['n_valid']:<3}  "
              f"{s['mean_gen_latency_s']:>7.1f}  {s['mean_in_tokens']:>7}  {s['mean_out_tokens']:>7}  "
              f"{cost_s:>7}  {tcost_s:>7}")

    # Per-problem table
    print(f"\n--- Per-problem scores ---")
    col_w = 14
    hdr = f"  {'Problem':<16}{'Role':<22}"
    for model, _ in ALL_MODELS:
        ms = model.split("/")[-1][:col_w]
        hdr += f"{ms:>{col_w+2}}"
    print(hdr)
    for pid in pids:
        role = problems[pid].get("role", "")[:20]
        row = f"  {pid:<16}{role:<22}"
        for model, _ in ALL_MODELS:
            r = next((x for x in results if x["model"] == model and x["problem_id"] == pid), None)
            if r is None:
                cell = "—"
            elif r.get("error"):
                cell = "ERR"
            elif r["score"] is None:
                cell = "—"
            else:
                mark = "✓" if r["passed"] else "✗"
                cell = f"{mark}{r['score']}/7"
            row += f"{cell:>{col_w+2}}"
        print(row)

    # Save
    suffix = "_mock" if mock else ""
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    output = {
        "experiment":      EXPERIMENT_NAME,
        "date":            datetime.now(timezone.utc).isoformat(),
        "mock":            mock,
        "seed":            SEED,
        "pass_threshold":  PASS_THRESHOLD,
        "max_tokens_gen":  MAX_TOKENS_GEN,
        "max_tokens_judge": MAX_TOKENS_JUDGE,
        "n_keys":          len(KEYS),
        "max_workers":     MAX_WORKERS,
        "judge_model":     JUDGE_MODEL,
        "models":          [{"id": m, "price_per_mtoken": p} for m, p in ALL_MODELS],
        "qwen_plus_subset": QWEN_PLUS_SUBSET,
        "dev_set":         {pid: DEV_SET[pid] for pid in sorted(problems)},
        "summary":         {summary[m]["ms"]: summary[m] for m in [x[0] for x in ALL_MODELS]},
        "all_results":     results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    return out_path


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Compare new models against baselines")
    parser.add_argument("--mock", action="store_true", help="Smoke test, no API calls")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()
    prompts = {
        "generator": load_prompt("generator.md"),
        "judge_gt":  load_prompt("judge_gt.md"),
    }

    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Dev set:       {len(problems)} problems")
    for pid, p in sorted(problems.items()):
        print(f"  {pid:<18s} {p['level']:<14s} {p.get('role','')}")
    print(f"Models:        {len(ALL_MODELS)}")
    print(f"Keys:          {len(KEYS)} OpenRouter keys")
    print(f"Workers:       {MAX_WORKERS}")
    print(f"Mode:          generate-only, GT judge ({JUDGE_MODEL.split('/')[-1]})")
    print(f"qwen3.6-plus restricted to: {QWEN_PLUS_SUBSET}")
    if args.mock:
        print("[MOCK MODE]")
    print()

    t0 = time.time()
    results = run_all(problems, prompts, args.mock)
    print(f"\nWall-clock: {round(time.time()-t0, 1)}s for {len(results)} trials")
    report(results, problems, args.mock)


if __name__ == "__main__":
    main()
