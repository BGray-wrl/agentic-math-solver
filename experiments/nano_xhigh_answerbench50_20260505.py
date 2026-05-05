#!/usr/bin/env python3
"""
gpt-5.4-nano @ reasoning.effort=xhigh on the full 50-problem AnswerBench
stratified subset (seed=42) — the SAME problems as
`answerbench_compare_20260504_20260504_084012`.

Direct OpenRouter API (requests.post) — bypasses the litellm timeout-not-firing
bug we hit on the prior nano-xhigh run. Per-trial hard timeout enforced.

pass@1, generate-only, judge = gemini-3.1-flash-lite-preview (matches prior).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
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
import requests
from dotenv import load_dotenv

load_dotenv("/Users/benjamingrayzel/sandbox/agentic-math-solver/.env")

# ============================================================================
# Configuration
# ============================================================================

EXPERIMENT_NAME = "nano_xhigh_answerbench50_20260505"
SEED = 42
REASONING_EFFORT = "xhigh"

MODEL = "openai/gpt-5.4-nano"
MODEL_FULL_LABEL = "gpt-5.4-nano (xhigh)"
JUDGE_MODEL = "google/gemini-3.1-flash-lite-preview"

MAX_TOKENS_GEN   = 65536
MAX_TOKENS_JUDGE = 4000

MAX_WORKERS         = 50
GEN_HTTP_TIMEOUT    = 1500   # seconds; OpenRouter will return or err within this
JUDGE_HTTP_TIMEOUT  = 120
TRIAL_TIMEOUT       = 1700   # outer cap when collecting futures
HARD_BUDGET_USD     = 18.50  # generous; expected actual ~$1.50

STRATA = {
    "Algebra":       12,
    "Combinatorics": 13,
    "Geometry":      12,
    "Number theory": 13,
}

ROOT = Path(__file__).parent.parent
PROMPTS_DIR    = ROOT / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
ANSWERBENCH_CSV = ROOT / "benchmarks" / "IMO-bench" / "answerbench_v2.csv"

PRICE_COMPARE_KEY = os.getenv("OPENROUTER_API_KEY_price_compare")
JUDGE_KEY = os.getenv("OPENROUTER_API_KEY_X") or os.getenv("OPENROUTER_API_KEY")
if not PRICE_COMPARE_KEY: raise SystemExit("price_compare key missing")
if not JUDGE_KEY:         raise SystemExit("judge key missing")


def _now() -> str: return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts()  -> str: return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ============================================================================
# Direct OpenRouter call (no litellm) — gets us reliable timeouts.
# ============================================================================

def or_chat(model, messages, max_tokens, key, http_timeout, reasoning=None,
            retries=2, backoff=4.0):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning is not None:
        body["reasoning"] = reasoning
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"},
                json=body,
                timeout=http_timeout,
            )
            if r.status_code == 402 or "credit" in r.text.lower()[:200]:
                raise RuntimeError(f"402/credit: {r.text[:200]}")
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content")
            reasoning_text = choice.get("reasoning") or choice.get("reasoning_content")
            if content is None:
                content = reasoning_text
            if content is None:
                raise ValueError("no content and no reasoning")
            usage = j.get("usage", {})
            cd = usage.get("completion_tokens_details") or {}
            usage_out = {
                "prompt_tokens":     int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens":      int(usage.get("total_tokens", 0) or 0),
                "reasoning_tokens":  int(cd.get("reasoning_tokens", 0) or 0),
            }
            return content, usage_out, reasoning_text
        except Exception as e:
            last_err = e
            msg = str(e)
            if "402" in msg or "insufficient" in msg.lower():
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model} attempt {attempt+1}: {e}, retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


# ============================================================================
# Budget polling (soft killswitch)
# ============================================================================

_lock = threading.Lock()
_state = {"usage": None, "limit": None, "abort": False, "abort_reason": None, "last": 0.0}

def poll_usage(force=False):
    now = time.time()
    with _lock:
        if not force and (now - _state["last"]) < 10:
            return dict(_state)
    try:
        r = requests.get("https://openrouter.ai/api/v1/auth/key",
                         headers={"Authorization": f"Bearer {PRICE_COMPARE_KEY}"}, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        with _lock:
            _state["usage"] = float(data.get("usage", 0.0))
            _state["limit"] = float(data["limit"]) if data.get("limit") is not None else None
            _state["last"] = now
            if _state["usage"] >= HARD_BUDGET_USD and not _state["abort"]:
                _state["abort"] = True
                _state["abort_reason"] = f"usage ${_state['usage']:.2f} >= cap ${HARD_BUDGET_USD}"
    except Exception as e:
        print(f"[{_ts()}] [poll] WARN: {e}", flush=True)
    return dict(_state)


# ============================================================================
# Verdict parsing + problem loading
# ============================================================================

VERDICT_RE = re.compile(r"<verdict>\s*(correct|incorrect)\s*</verdict>", re.I)
def parse_verdict(text):
    if text is None: return None
    m = VERDICT_RE.search(text)
    if m: return 1 if m.group(1).lower() == "correct" else 0
    head = (text or "")[:200].lower()
    if "verdict>correct" in head or "answer is correct" in head: return 1
    if "verdict>incorrect" in head or "answer is incorrect" in head: return 0
    return None

def load_prompt(name): return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()

def load_problems():
    """Stratified 50 from answerbench_v2.csv with seed=42 — matches the original
    answerbench_compare_20260504 run exactly (same code path)."""
    with open(ANSWERBENCH_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_cat = {}
    for r in rows:
        cat = r["Category"]
        if cat not in STRATA:
            continue
        by_cat.setdefault(cat, []).append(r)
    rng = random.Random(SEED)
    selected = {}
    for cat, n in STRATA.items():
        pool = sorted(by_cat[cat], key=lambda r: r["Problem ID"])
        chosen = rng.sample(pool, n)
        for row in chosen:
            pid = row["Problem ID"]
            selected[pid] = {
                "text": row["Problem"].strip(),
                "short_answer": row["Short Answer"].strip(),
                "category": row["Category"],
                "subcategory": row.get("Subcategory", "").strip(),
                "source": row.get("Source", "").strip(),
            }
    return selected


# ============================================================================
# Trial
# ============================================================================

def run_trial(pid, problem, prompts, mock):
    np.random.seed(SEED); random.seed(SEED)
    tag = f"[{_ts()}] [{pid}|nano-xhigh]"
    t0 = time.time()
    if mock:
        return _mk(pid, problem, 1, "Mock.\n<answer>42</answer>",
                   "<verdict>correct</verdict> mock",
                   {"prompt_tokens":100,"completion_tokens":50,"total_tokens":150,"reasoning_tokens":40},
                   {"prompt_tokens":200,"completion_tokens":20,"total_tokens":220},
                   0.005, 0.005, 0.01, None)
    print(f"{tag} generate", flush=True)
    gen_t0 = time.time()
    try:
        gen_text, gen_usage, reasoning_text = or_chat(
            model=MODEL,
            messages=[
                {"role":"system","content":prompts["generator"]},
                {"role":"user","content":problem["text"]},
            ],
            max_tokens=MAX_TOKENS_GEN,
            key=PRICE_COMPARE_KEY,
            http_timeout=GEN_HTTP_TIMEOUT,
            reasoning={"effort": REASONING_EFFORT},
        )
        gen_elapsed = round(time.time() - gen_t0, 2)
        print(f"{tag} gen {gen_elapsed}s in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']} reason={gen_usage['reasoning_tokens']}", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} GEN FAILED: {e} ({elapsed}s)", flush=True)
        return _err(pid, problem, str(e), elapsed)

    judge_prompt = (prompts["judge"]
                    .replace("{problem}", problem["text"])
                    .replace("{ground_truth}", problem["short_answer"])
                    .replace("{candidate}", gen_text))
    judge_t0 = time.time()
    try:
        judge_text, judge_usage, _ = or_chat(
            model=JUDGE_MODEL,
            messages=[{"role":"user","content":judge_prompt}],
            max_tokens=MAX_TOKENS_JUDGE,
            key=JUDGE_KEY,
            http_timeout=JUDGE_HTTP_TIMEOUT,
        )
        judge_elapsed = round(time.time() - judge_t0, 2)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} JUDGE FAILED: {e} ({elapsed}s)", flush=True)
        return _err(pid, problem, f"judge: {e}", elapsed,
                    gen_text=gen_text, gen_usage=gen_usage, gen_elapsed=gen_elapsed)

    score = parse_verdict(judge_text)
    elapsed_total = round(time.time() - t0, 2)
    s_str = "?" if score is None else str(score)
    print(f"{tag} -> verdict={s_str} total={elapsed_total}s", flush=True)
    return _mk(pid, problem, score, gen_text, judge_text, gen_usage, judge_usage,
               gen_elapsed, judge_elapsed, elapsed_total, reasoning_text)


def _mk(pid, problem, score, gen_text, verdict, gen_usage, judge_usage,
        gen_elapsed, judge_elapsed, elapsed_total, reasoning_text):
    return {
        "problem_id": pid, "category": problem["category"], "subcategory": problem["subcategory"],
        "short_answer": problem["short_answer"], "model": f"openrouter/{MODEL}",
        "reasoning_effort": REASONING_EFFORT, "seed": SEED,
        "score": score, "passed": bool(score) if score is not None else False,
        "elapsed_s": elapsed_total, "gen_elapsed_s": gen_elapsed, "judge_elapsed_s": judge_elapsed,
        "gen_usage": gen_usage, "judge_usage": judge_usage,
        "final_solution": gen_text, "reasoning_text": reasoning_text,
        "verdict": verdict,
    }

def _err(pid, problem, err, elapsed, gen_text=None, gen_usage=None, gen_elapsed=None):
    return {
        "problem_id": pid, "category": problem["category"], "subcategory": problem["subcategory"],
        "short_answer": problem["short_answer"], "model": f"openrouter/{MODEL}",
        "reasoning_effort": REASONING_EFFORT, "seed": SEED,
        "score": None, "passed": False, "elapsed_s": elapsed,
        "gen_elapsed_s": gen_elapsed, "judge_elapsed_s": None,
        "gen_usage": gen_usage, "judge_usage": None,
        "final_solution": gen_text, "reasoning_text": None,
        "verdict": None, "error": err,
    }


# ============================================================================
# Executor + reporting
# ============================================================================

def run_all(problems, prompts, mock):
    pids = sorted(problems.keys())
    total = len(pids)
    print(f"\n[{_ts()}] Submitting {total} trials, workers={MAX_WORKERS}", flush=True)
    if not mock:
        st = poll_usage(force=True)
        if st["usage"] is not None:
            print(f"[{_ts()}] [budget] start: usage=${st['usage']:.4f} cap=${HARD_BUDGET_USD}", flush=True)

    out_partial = RESULTS_DIR / f"{EXPERIMENT_NAME}_partial.json"
    print(f"Partial saves: {out_partial}\n", flush=True)

    results = []
    completed = 0
    def _run(pid):
        return run_trial(pid, problems[pid], prompts, mock)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, pid): pid for pid in pids}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid = futs[fut]
            completed += 1
            try:
                r = fut.result(timeout=TRIAL_TIMEOUT)
            except Exception as e:
                print(f"[{_ts()}] FAILED [{pid}]: {e}", flush=True)
                traceback.print_exc()
                r = _err(pid, problems[pid], str(e), 0)
            results.append(r)
            try:
                with open(out_partial, "w", encoding="utf-8") as f:
                    json.dump({"experiment": EXPERIMENT_NAME, "partial": True,
                               "n_results": len(results), "results": results},
                              f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[{_ts()}] [WARN] partial save: {e}", flush=True)
            if not mock and completed % 5 == 0:
                st = poll_usage()
                if st["usage"] is not None:
                    print(f"[{_ts()}] [budget] {completed}/{total}: usage=${st['usage']:.4f}", flush=True)
    return results


def report(results, problems, mock, suffix=""):
    print("\n" + "=" * 110)
    print(f"AnswerBench-50 — {MODEL_FULL_LABEL}, pass@1, gemini-3.1-flash-lite judge")
    print("=" * 110)

    valid = [r for r in results if r["score"] is not None]
    scored = [r["score"] for r in valid]
    gen_lat = [r["gen_elapsed_s"] for r in valid if r.get("gen_elapsed_s") is not None]
    in_t  = [r["gen_usage"]["prompt_tokens"]     for r in valid if r.get("gen_usage")]
    out_t = [r["gen_usage"]["completion_tokens"] for r in valid if r.get("gen_usage")]
    rea_t = [r["gen_usage"].get("reasoning_tokens", 0) for r in valid if r.get("gen_usage")]
    n_err = sum(1 for r in results if r.get("error"))

    n = len(valid)
    n_correct = sum(scored)
    acc = n_correct / n if n else 0
    mean_lat = float(np.mean(gen_lat)) if gen_lat else 0.0
    median_lat = float(np.median(gen_lat)) if gen_lat else 0.0
    mean_in   = int(np.mean(in_t))  if in_t  else 0
    mean_out  = int(np.mean(out_t)) if out_t else 0
    mean_rea  = int(np.mean(rea_t)) if rea_t else 0

    # Authoritative cost from per-trial token counts.
    pin, pout = 0.20e-6, 1.25e-6  # nano pricing (USD per token)
    total_cost = sum(i*pin + o*pout for i,o in zip(in_t, out_t))
    cost_per_run = total_cost / n if n else 0

    # Per-category accuracy
    per_cat = {}
    for cat in STRATA:
        cat_rs = [r for r in valid if r["category"] == cat]
        if cat_rs:
            per_cat[cat] = {
                "n": len(cat_rs),
                "n_correct": sum(r["score"] for r in cat_rs),
                "accuracy": round(float(np.mean([r["score"] for r in cat_rs])), 3),
            }

    print(f"\nTrials: {n}/{len(results)} valid  Errors: {n_err}")
    print(f"Accuracy: {n_correct}/{n} = {acc*100:.0f}%")
    print(f"Mean gen lat: {mean_lat:.1f}s  (median {median_lat:.1f}s)")
    print(f"Mean in_tok:  {mean_in}   out_tok: {mean_out}   reasoning: {mean_rea}")
    print(f"Cost (auth pricing): ${cost_per_run:.4f}/run  total ${total_cost:.3f}")

    print(f"\nBy category:")
    for cat in STRATA:
        pc = per_cat.get(cat)
        if pc:
            print(f"  {cat:<16} {pc['n_correct']}/{pc['n']} = {pc['accuracy']*100:.0f}%")

    if not mock:
        st = poll_usage(force=True)
        if st["usage"] is not None:
            print(f"\n[OpenRouter] price_compare key usage end: ${st['usage']:.4f}")

    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment": EXPERIMENT_NAME, "date": datetime.now(timezone.utc).isoformat(),
            "mock": mock, "seed": SEED,
            "model": MODEL, "reasoning_effort": REASONING_EFFORT,
            "judge_model": JUDGE_MODEL,
            "max_tokens_gen": MAX_TOKENS_GEN, "max_workers": MAX_WORKERS,
            "gen_http_timeout": GEN_HTTP_TIMEOUT,
            "openrouter_usage_end": _state.get("usage"),
            "summary": {
                "n_trials": len(results), "n_valid": n, "n_errors": n_err,
                "n_correct": n_correct, "accuracy": round(acc, 3),
                "mean_gen_lat": round(mean_lat, 1),
                "mean_in_tok": mean_in, "mean_out_tok": mean_out, "mean_reasoning_tok": mean_rea,
                "cost_per_run": round(cost_per_run, 5),
                "total_cost": round(total_cost, 4),
                "per_category": per_cat,
            },
            "problems": {pid: {k: v for k, v in p.items() if k != "text"}
                         | {"text_chars": len(p["text"])} for pid, p in problems.items()},
            "all_results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    problems = load_problems()
    prompts = {
        "generator": load_prompt("generator.md"),
        "judge":     load_prompt("answerbench_judge.md"),
    }
    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Model: {MODEL}  effort={REASONING_EFFORT}")
    print(f"Problems: {len(problems)}")
    by_cat = {}
    for p in problems.values():
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    for cat, n in by_cat.items():
        print(f"  {cat:<20s} {n}")
    print(f"Hard budget: ${HARD_BUDGET_USD}")
    if args.mock: print("[MOCK]")

    t0 = time.time()
    results = run_all(problems, prompts, args.mock)
    print(f"\nWall-clock: {round(time.time()-t0,1)}s")
    report(results, problems, args.mock)


if __name__ == "__main__":
    main()
