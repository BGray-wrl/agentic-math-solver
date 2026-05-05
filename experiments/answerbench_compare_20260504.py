#!/usr/bin/env python3
"""
Compare 7 models on a 50-problem stratified subset of AnswerBench v2.

- Mode: generate-only, pass@1, single seed (42).
- Judge: gemini-3.1-flash-lite-preview, doing answer-equivalence (binary).
- Stratified sample of 50 problems from benchmarks/IMO-bench/answerbench_v2.csv:
    12 Algebra + 13 Combinatorics + 12 Geometry + 13 Number theory.
  (Functional Equation row is dropped — only 1 of 400.)
- 3 OpenRouter keys round-robin via litellm api_key=, ~80–100 workers.

Reuses the call_model + retry + cost-tracking pattern from
experiments/new_models_compare_20260504.py and new_models_pass3_20260504.py.

Usage:
    uv run experiments/answerbench_compare_20260504.py --mock
    uv run experiments/answerbench_compare_20260504.py --smoke
    uv run experiments/answerbench_compare_20260504.py
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

# ============================================================================
# Configuration
# ============================================================================

EXPERIMENT_NAME = "answerbench_compare_20260504"

# Models under test, with user-supplied prices ($/M tokens, blended).
# gpt-oss-120b and gemini-3-flash-preview have no user-supplied price; cost = None.
MODELS = [
    ("openrouter/openai/gpt-oss-120b",            None),
    ("openrouter/deepseek/deepseek-v4-flash",     0.28),
    ("openrouter/deepseek/deepseek-v4-pro",       0.87),
    ("openrouter/google/gemma-4-31b-it",          0.38),
    ("openrouter/google/gemini-3-flash-preview",  None),
    ("openrouter/qwen/qwen3.6-35b-a3b",           1.00),
    ("openrouter/qwen/qwen3.6-plus",              1.95),
]
PRICE_PER_MTOKEN = {m: p for m, p in MODELS}

# Smoke-test model: cheapest of the lot.
SMOKE_MODEL = "openrouter/google/gemma-4-31b-it"

JUDGE_MODEL = "openrouter/google/gemini-3.1-flash-lite-preview"

SEED = 42

MAX_TOKENS_GEN   = 16000
MAX_TOKENS_JUDGE = 4000  # binary verdict + brief justification — 4K is plenty

# 350 trials, 3 keys; 90 workers ≈ 30 per key fans out a single wave.
MAX_WORKERS     = 90
TRIAL_TIMEOUT   = 600
LITELLM_TIMEOUT = 540

# Stratification target counts per category — sums to 50.
STRATA = {
    "Algebra":       12,
    "Combinatorics": 13,
    "Geometry":      12,
    "Number theory": 13,
}

# ============================================================================
# Paths and key rotation
# ============================================================================

ROOT = Path(__file__).parent.parent
PROMPTS_DIR    = ROOT / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
ANSWERBENCH_CSV = ROOT / "benchmarks" / "IMO-bench" / "answerbench_v2.csv"


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
# LLM call (key rotation, retries, token capture) — copied from sibling scripts
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
            msg = str(e)
            # Don't retry credit failures — they won't change.
            if "402" in msg or "credit" in msg.lower():
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1} failed: {e}, retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


# ============================================================================
# Verdict parsing
# ============================================================================

VERDICT_RE = re.compile(r"<verdict>\s*(correct|incorrect)\s*</verdict>", re.I)


def parse_verdict(text: str) -> int | None:
    """Return 1 for correct, 0 for incorrect, None if unparseable."""
    if text is None:
        return None
    m = VERDICT_RE.search(text)
    if m:
        return 1 if m.group(1).lower() == "correct" else 0
    # Fallbacks — be conservative.
    head = text[:200].lower()
    if "verdict>correct" in head or "answer is correct" in head:
        return 1
    if "verdict>incorrect" in head or "answer is incorrect" in head:
        return 0
    return None


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


# ============================================================================
# Stratified problem selection
# ============================================================================

def load_problems() -> dict:
    """Load AnswerBench v2 and return a stratified 50-problem subset.

    Sampling: random.seed(42), then for each category in STRATA take that many
    rows. Functional Equation is excluded.
    """
    with open(ANSWERBENCH_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        cat = r["Category"]
        if cat not in STRATA:
            continue
        by_cat.setdefault(cat, []).append(r)

    rng = random.Random(SEED)
    selected: dict[str, dict] = {}
    for cat, n in STRATA.items():
        pool = sorted(by_cat[cat], key=lambda r: r["Problem ID"])
        if len(pool) < n:
            raise SystemExit(f"Only {len(pool)} problems in {cat}, need {n}")
        chosen = rng.sample(pool, n)
        for row in chosen:
            pid = row["Problem ID"]
            selected[pid] = {
                "text":         row["Problem"].strip(),
                "short_answer": row["Short Answer"].strip(),
                "category":     row["Category"],
                "subcategory":  row.get("Subcategory", "").strip(),
                "source":       row.get("Source", "").strip(),
            }
    return selected


# ============================================================================
# Single trial (generate + judge)
# ============================================================================

def run_trial(problem_id, problem, model, prompts, mock):
    np.random.seed(SEED)
    random.seed(SEED)
    ms = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{ms}]"
    t0 = time.time()

    if mock:
        time.sleep(0.005)
        return _mk_result(
            problem_id, problem, model,
            score=1, gen_text="Mock solution.\n<answer>42</answer>",
            verdict="<verdict>correct</verdict> mock",
            gen_usage={"prompt_tokens":100,"completion_tokens":50,"total_tokens":150},
            judge_usage={"prompt_tokens":200,"completion_tokens":20,"total_tokens":220},
            gen_elapsed=0.005, judge_elapsed=0.005, elapsed_total=0.01,
        )

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
        print(f"{tag} gen {gen_elapsed}s in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']}", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} GEN FAILED: {e} ({elapsed}s)", flush=True)
        return _err(problem_id, problem, model, str(e), elapsed)

    judge_prompt = (prompts["judge"]
                    .replace("{problem}",      problem["text"])
                    .replace("{ground_truth}", problem["short_answer"])
                    .replace("{candidate}",    gen_text))
    judge_t0 = time.time()
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
        return _err(problem_id, problem, model, f"judge: {e}", elapsed,
                    gen_text=gen_text, gen_usage=gen_usage, gen_elapsed=gen_elapsed)

    score = parse_verdict(judge_text)
    elapsed_total = round(time.time() - t0, 2)
    s_str = "?" if score is None else str(score)
    print(f"{tag} -> verdict={s_str} total={elapsed_total}s", flush=True)
    return _mk_result(problem_id, problem, model, score, gen_text, judge_text,
                      gen_usage, judge_usage, gen_elapsed, judge_elapsed, elapsed_total)


def _mk_result(pid, problem, model, score, gen_text, verdict,
               gen_usage, judge_usage, gen_elapsed, judge_elapsed, elapsed_total):
    price = PRICE_PER_MTOKEN.get(model)
    est_cost = round(price * gen_usage["total_tokens"] / 1_000_000, 6) if (price and gen_usage) else None
    return {
        "problem_id":      pid,
        "category":        problem["category"],
        "subcategory":     problem["subcategory"],
        "short_answer":    problem["short_answer"],
        "model":           model,
        "seed":            SEED,
        "score":           score,           # 1 / 0 / None
        "passed":          bool(score) if score is not None else False,
        "elapsed_s":       elapsed_total,
        "gen_elapsed_s":   gen_elapsed,
        "judge_elapsed_s": judge_elapsed,
        "gen_usage":       gen_usage,
        "judge_usage":     judge_usage,
        "est_cost_usd":    est_cost,
        "final_solution":  gen_text,
        "verdict":         verdict,
    }


def _err(pid, problem, model, err, elapsed,
         gen_text=None, gen_usage=None, gen_elapsed=None):
    return {
        "problem_id":     pid,
        "category":       problem["category"],
        "subcategory":    problem["subcategory"],
        "short_answer":   problem["short_answer"],
        "model":          model,
        "seed":           SEED,
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

def run_all(problems, prompts, mock, models_to_run):
    pids = sorted(problems.keys())
    trials = [(pid, m) for pid in pids for m in models_to_run]
    total = len(trials)
    print(f"Submitting {total} trials across {len(KEYS)} keys, max_workers={MAX_WORKERS}\n", flush=True)

    results, completed = [], 0
    def _run(pid, m):
        return run_trial(pid, problems[pid], m, prompts, mock)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, pid, m): (pid, m) for pid, m in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid, m = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = m.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{ms}]: {e}", flush=True)
                traceback.print_exc()
                results.append(_err(pid, problems[pid], m, str(e), 0))
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)
    return results


# ============================================================================
# Reporting
# ============================================================================

def report(results, problems, mock, models_to_run, suffix=""):
    print("\n" + "=" * 100)
    print("ANSWERBENCH-50 COMPARISON (pass@1, gemini-3.1-flash-lite judge)")
    print("=" * 100)

    summary = {}
    for model in models_to_run:
        ms = model.split("/")[-1]
        rs = [r for r in results if r["model"] == model]
        valid = [r for r in rs if r["score"] is not None]
        scored = [r["score"] for r in valid]
        gen_lat = [r["gen_elapsed_s"] for r in valid if r.get("gen_elapsed_s") is not None]
        gen_in_tok  = [r["gen_usage"]["prompt_tokens"]     for r in valid if r.get("gen_usage")]
        gen_out_tok = [r["gen_usage"]["completion_tokens"] for r in valid if r.get("gen_usage")]
        costs   = [r["est_cost_usd"] for r in valid if r.get("est_cost_usd") is not None]
        n_err   = sum(1 for r in rs if r.get("error"))

        # Per-category accuracy.
        per_cat = {}
        for cat in STRATA:
            cat_rs = [r for r in valid if r["category"] == cat]
            if cat_rs:
                per_cat[cat] = {
                    "n":        len(cat_rs),
                    "n_correct": sum(r["score"] for r in cat_rs),
                    "accuracy": round(float(np.mean([r["score"] for r in cat_rs])), 3),
                }

        summary[model] = {
            "ms":          ms,
            "price_per_mtoken": PRICE_PER_MTOKEN.get(model),
            "n_trials":    len(rs),
            "n_valid":     len(valid),
            "n_errors":    n_err,
            "n_correct":   sum(scored),
            "accuracy":    round(float(np.mean(scored)), 3) if scored else 0.0,
            "mean_gen_lat":   round(float(np.mean(gen_lat)), 1) if gen_lat else 0.0,
            "median_gen_lat": round(float(np.median(gen_lat)), 1) if gen_lat else 0.0,
            "mean_in_tok":    int(np.mean(gen_in_tok))  if gen_in_tok  else 0,
            "mean_out_tok":   int(np.mean(gen_out_tok)) if gen_out_tok else 0,
            "mean_cost":      round(float(np.mean(costs)), 4) if costs else None,
            "total_cost":     round(float(np.sum(costs)), 3) if costs else None,
            "per_category":   per_cat,
        }

    print(f"\n{'Model':<32} {'$/Mt':>6} {'n':>4} {'err':>3}  {'acc':>6}  {'lat(s)':>7}  {'out_tok':>7}  {'$/run':>8}  {'$ tot':>7}")
    print("-" * 110)
    for model in sorted(models_to_run, key=lambda m: -summary[m]["accuracy"]):
        s = summary[model]
        price_s = f"${s['price_per_mtoken']:.2f}" if s['price_per_mtoken'] else "—"
        cost_s  = f"${s['mean_cost']:.4f}" if s['mean_cost'] is not None else "—"
        tcost_s = f"${s['total_cost']:.3f}" if s['total_cost'] is not None else "—"
        acc_s = f"{s['n_correct']}/{s['n_valid']}"
        print(f"{s['ms']:<32} {price_s:>6} {s['n_valid']:>4} {s['n_errors']:>3}  "
              f"{acc_s:>6}  {s['mean_gen_lat']:>7.1f}  {s['mean_out_tok']:>7}  {cost_s:>8}  {tcost_s:>7}")

    # Per-category table
    print(f"\n--- Accuracy by category ---")
    cat_order = list(STRATA.keys())
    hdr = f"  {'Model':<32}" + "".join(f"{c[:13]:>15}" for c in cat_order) + f"{'Total':>10}"
    print(hdr)
    for model in sorted(models_to_run, key=lambda m: -summary[m]["accuracy"]):
        s = summary[model]
        row = f"  {s['ms']:<32}"
        for cat in cat_order:
            pc = s["per_category"].get(cat)
            if pc:
                row += f"{pc['n_correct']}/{pc['n']:<2}".rjust(15)
            else:
                row += f"{'—':>15}"
        row += f"{s['n_correct']}/{s['n_valid']}".rjust(10)
        print(row)

    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment":     EXPERIMENT_NAME,
            "date":           datetime.now(timezone.utc).isoformat(),
            "mock":           mock,
            "smoke":          suffix == "_smoke",
            "seed":           SEED,
            "n_keys":         len(KEYS),
            "max_workers":    MAX_WORKERS,
            "max_tokens_gen": MAX_TOKENS_GEN,
            "max_tokens_judge": MAX_TOKENS_JUDGE,
            "judge_model":    JUDGE_MODEL,
            "models":         [{"id": m, "price_per_mtoken": PRICE_PER_MTOKEN.get(m)} for m in models_to_run],
            "strata":         STRATA,
            "problems":       {pid: {k: v for k, v in p.items() if k != "text"}
                               | {"text_chars": len(p["text"])} for pid, p in problems.items()},
            "summary":        {summary[m]["ms"]: summary[m] for m in models_to_run},
            "all_results":    results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    return out_path


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock",  action="store_true", help="No API calls, just exercise the pipeline.")
    parser.add_argument("--smoke", action="store_true", help="Real run with only the smoke model (gemma).")
    args = parser.parse_args()
    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()
    prompts = {
        "generator": load_prompt("generator.md"),
        "judge":     load_prompt("answerbench_judge.md"),
    }

    models_to_run = [SMOKE_MODEL] if args.smoke else [m for m, _ in MODELS]
    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")

    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Problems:      {len(problems)} (stratified, seed={SEED})")
    by_cat = {}
    for p in problems.values():
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    for cat, n in by_cat.items():
        print(f"  {cat:<20s} {n}")
    print(f"Models to run: {len(models_to_run)}")
    for m in models_to_run:
        price = PRICE_PER_MTOKEN.get(m)
        ps = f"${price:.2f}/Mtok" if price else "(no price)"
        print(f"  {m}  {ps}")
    print(f"Judge:         {JUDGE_MODEL}")
    print(f"Keys:          {len(KEYS)}  Workers: {MAX_WORKERS}")
    if args.mock:
        print("[MOCK MODE]")
    if args.smoke:
        print("[SMOKE MODE — gemma only]")
    print(f"Total trials:  {len(problems) * len(models_to_run)}\n", flush=True)

    t0 = time.time()
    results = run_all(problems, prompts, args.mock, models_to_run)
    print(f"\nWall-clock: {round(time.time()-t0, 1)}s for {len(results)} trials", flush=True)
    report(results, problems, args.mock, models_to_run, suffix=suffix)


if __name__ == "__main__":
    main()
