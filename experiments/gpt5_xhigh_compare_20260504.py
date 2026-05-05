#!/usr/bin/env python3
"""
Re-test the GPT-5.4 family at maximum reasoning effort.

Motivated by the prior `expensive_models_compare_20260504` run where gpt-5.4
ran at default reasoning (3.6K mean output tokens, 6/12 acc). User suspects
that with `reasoning.effort=xhigh`, gpt-5.4 will behave like a real reasoning
model. We're also adding the smaller siblings (mini, nano) for a tier sweep.

Plan:
  - nano on ALL 12 PIDs from the original AnswerBench-50 subset
  - mini on ALL 12 PIDs
  - gpt-5.4 only on the 6 PIDs it got WRONG at default effort (skip the 6 it
    got right — those are evidence it can handle them already)
  - All at reasoning.effort=xhigh, MAX_TOKENS=65536
  - Wave 1 (nano + mini, 24 trials) → wave 2 (gpt-5.4, 6 trials)
  - Single key (price_compare, $20 cap), $19 hard killswitch

Usage:
  uv run experiments/gpt5_xhigh_compare_20260504.py --mock
  uv run experiments/gpt5_xhigh_compare_20260504.py --smoke   # 1 nano trial
  uv run experiments/gpt5_xhigh_compare_20260504.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
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

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import litellm  # noqa: E402

# ============================================================================
# Configuration
# ============================================================================

EXPERIMENT_NAME = "gpt5_xhigh_compare_20260504"
SEED = 42
REASONING_EFFORT = "xhigh"

ALL_12_PIDS = [
    "imo-bench-algebra-004",
    "imo-bench-algebra-012",
    "imo-bench-algebra-088",
    "imo-bench-combinatorics-026",
    "imo-bench-combinatorics-028",
    "imo-bench-combinatorics-084",
    "imo-bench-geometry-021",
    "imo-bench-geometry-029",
    "imo-bench-geometry-036",
    "imo-bench-number_theory-045",
    "imo-bench-number_theory-049",
    "imo-bench-number_theory-078",
]
# PIDs where gpt-5.4 was WRONG at default effort (from prior run).
GPT54_FAILED_PIDS = [
    "imo-bench-algebra-004",
    "imo-bench-combinatorics-026",
    "imo-bench-combinatorics-028",
    "imo-bench-combinatorics-084",
    "imo-bench-geometry-021",
    "imo-bench-geometry-029",
]

# Model id → list of PIDs to run.
MODEL_PLAN = [
    ("openrouter/openai/gpt-5.4-nano", ALL_12_PIDS),
    ("openrouter/openai/gpt-5.4-mini", ALL_12_PIDS),
    ("openrouter/openai/gpt-5.4",      GPT54_FAILED_PIDS),  # runs last (wave 2)
]
SMOKE_MODEL = "openrouter/openai/gpt-5.4-nano"

JUDGE_MODEL = "openrouter/google/gemini-3.1-flash-lite-preview"

MAX_TOKENS_GEN   = 65536
MAX_TOKENS_JUDGE = 4000

MAX_WORKERS     = 30
TRIAL_TIMEOUT   = 1800   # xhigh can be slow
LITELLM_TIMEOUT = 1700

HARD_BUDGET_USD = 19.00  # cap is $20 on the key

ROOT = Path(__file__).parent.parent
PROMPTS_DIR    = ROOT / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
ANSWERBENCH_CSV = ROOT / "benchmarks" / "IMO-bench" / "answerbench_v2.csv"
PRIOR_RUN_JSON = (
    Path(__file__).parent / "results"
    / "answerbench_compare_20260504_20260504_084012.json"
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ============================================================================
# Keys
# ============================================================================

load_dotenv()
PRICE_COMPARE_KEY = os.getenv("OPENROUTER_API_KEY_price_compare")
if not PRICE_COMPARE_KEY:
    raise SystemExit("OPENROUTER_API_KEY_price_compare not in .env")
JUDGE_KEY = os.getenv("OPENROUTER_API_KEY_X") or os.getenv("OPENROUTER_API_KEY")
if not JUDGE_KEY:
    raise SystemExit("Need OPENROUTER_API_KEY_X or OPENROUTER_API_KEY for judge")


# ============================================================================
# Budget poller (OpenRouter ground truth)
# ============================================================================

_usage_lock = threading.Lock()
_usage_state = {"usage_usd": None, "limit_usd": None, "last_polled": 0.0,
                "abort": False, "abort_reason": None}

def poll_key_usage(force=False):
    now = time.time()
    with _usage_lock:
        if not force and (now - _usage_state["last_polled"]) < 10:
            return dict(_usage_state)
    try:
        r = requests.get("https://openrouter.ai/api/v1/auth/key",
                         headers={"Authorization": f"Bearer {PRICE_COMPARE_KEY}"},
                         timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        with _usage_lock:
            _usage_state["usage_usd"] = float(data.get("usage", 0.0))
            _usage_state["limit_usd"] = float(data["limit"]) if data.get("limit") else None
            _usage_state["last_polled"] = now
            if _usage_state["usage_usd"] >= HARD_BUDGET_USD and not _usage_state["abort"]:
                _usage_state["abort"] = True
                _usage_state["abort_reason"] = (
                    f"usage ${_usage_state['usage_usd']:.2f} >= hard cap ${HARD_BUDGET_USD:.2f}"
                )
    except Exception as e:
        print(f"[{_ts()}] [poll] WARN: {e}", flush=True)
    return dict(_usage_state)

def trip_abort(reason):
    with _usage_lock:
        if not _usage_state["abort"]:
            _usage_state["abort"] = True
            _usage_state["abort_reason"] = reason

def is_aborted():
    with _usage_lock:
        return bool(_usage_state["abort"])


# ============================================================================
# LLM call (with reasoning param)
# ============================================================================

def call_model_with_reasoning(model, system, prompt, max_tokens, key, retries=2, backoff=4.0):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                api_key=key,
                timeout=LITELLM_TIMEOUT,
                # OpenRouter reasoning param — pass via extra_body for safety.
                extra_body={"reasoning": {"effort": REASONING_EFFORT}},
            )
            content = resp.choices[0].message.content  # type: ignore
            reasoning = getattr(resp.choices[0].message, "reasoning", None) or getattr(  # type: ignore
                resp.choices[0].message, "reasoning_content", None
            )
            if content is None:
                content = reasoning
            if content is None:
                raise ValueError(f"Model {model} returned None content & None reasoning")
            usage = getattr(resp, "usage", None)
            usage_dict = {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
            }
            cd = getattr(usage, "completion_tokens_details", None)
            if cd is not None:
                usage_dict["reasoning_tokens"] = int(getattr(cd, "reasoning_tokens", 0) or 0)
            return content, usage_dict, reasoning
        except Exception as e:
            last_err = e
            msg = str(e)
            if "402" in msg or "credit" in msg.lower() or "insufficient" in msg.lower():
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1}: {e}, retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


def call_judge(model, prompt, max_tokens, key):
    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        api_key=key,
        timeout=LITELLM_TIMEOUT,
    )
    content = resp.choices[0].message.content  # type: ignore
    usage = getattr(resp, "usage", None)
    return content, {
        "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
    }


# ============================================================================
# Verdict + prompts + problems
# ============================================================================

VERDICT_RE = re.compile(r"<verdict>\s*(correct|incorrect)\s*</verdict>", re.I)

def parse_verdict(text):
    if text is None: return None
    m = VERDICT_RE.search(text)
    if m: return 1 if m.group(1).lower() == "correct" else 0
    head = text[:200].lower()
    if "verdict>correct" in head or "answer is correct" in head: return 1
    if "verdict>incorrect" in head or "answer is incorrect" in head: return 0
    return None

def load_prompt(name):
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()

def load_problems():
    import csv
    with open(ANSWERBENCH_CSV, encoding="utf-8") as f:
        rows = {r["Problem ID"]: r for r in csv.DictReader(f)}
    selected = {}
    for pid in ALL_12_PIDS:
        row = rows[pid]
        selected[pid] = {
            "text":         row["Problem"].strip(),
            "short_answer": row["Short Answer"].strip(),
            "category":     row["Category"],
            "subcategory":  row.get("Subcategory", "").strip(),
            "source":       row.get("Source", "").strip(),
        }
    return selected


# ============================================================================
# Trial
# ============================================================================

def run_trial(problem_id, problem, model, prompts, mock):
    np.random.seed(SEED); random.seed(SEED)
    ms = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{ms}]"
    t0 = time.time()

    if mock:
        return _mk_result(
            problem_id, problem, model, score=1,
            gen_text="Mock.\n<answer>42</answer>",
            verdict="<verdict>correct</verdict> mock",
            gen_usage={"prompt_tokens":100,"completion_tokens":50,"total_tokens":150,"reasoning_tokens":40},
            judge_usage={"prompt_tokens":200,"completion_tokens":20,"total_tokens":220},
            gen_elapsed=0.005, judge_elapsed=0.005, elapsed_total=0.01,
            reasoning_text=None,
        )

    print(f"{tag} generate (effort={REASONING_EFFORT})", flush=True)
    gen_t0 = time.time()
    try:
        gen_text, gen_usage, reasoning_text = call_model_with_reasoning(
            model=model,
            system=prompts["generator"],
            prompt=problem["text"],
            max_tokens=MAX_TOKENS_GEN,
            key=PRICE_COMPARE_KEY,
        )
        gen_elapsed = round(time.time() - gen_t0, 2)
        rt = gen_usage.get("reasoning_tokens", 0)
        print(f"{tag} gen {gen_elapsed}s in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']} reason={rt}", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        msg = str(e)
        print(f"{tag} GEN FAILED: {e} ({elapsed}s)", flush=True)
        if "402" in msg or "credit" in msg.lower():
            trip_abort(f"key out of credits during {ms}: {msg[:120]}")
        return _err(problem_id, problem, model, msg, elapsed)

    judge_prompt = (prompts["judge"]
                    .replace("{problem}", problem["text"])
                    .replace("{ground_truth}", problem["short_answer"])
                    .replace("{candidate}", gen_text))
    judge_t0 = time.time()
    try:
        judge_text, judge_usage = call_judge(JUDGE_MODEL, judge_prompt, MAX_TOKENS_JUDGE, JUDGE_KEY)
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
                      gen_usage, judge_usage, gen_elapsed, judge_elapsed, elapsed_total,
                      reasoning_text=reasoning_text)


def _mk_result(pid, problem, model, score, gen_text, verdict,
               gen_usage, judge_usage, gen_elapsed, judge_elapsed, elapsed_total,
               reasoning_text=None):
    return {
        "problem_id":       pid,
        "category":         problem["category"],
        "subcategory":      problem["subcategory"],
        "short_answer":     problem["short_answer"],
        "model":            model,
        "reasoning_effort": REASONING_EFFORT,
        "seed":             SEED,
        "score":            score,
        "passed":           bool(score) if score is not None else False,
        "elapsed_s":        elapsed_total,
        "gen_elapsed_s":    gen_elapsed,
        "judge_elapsed_s":  judge_elapsed,
        "gen_usage":        gen_usage,
        "judge_usage":      judge_usage,
        "final_solution":   gen_text,
        "reasoning_text":   reasoning_text,
        "verdict":          verdict,
    }

def _err(pid, problem, model, err, elapsed, gen_text=None, gen_usage=None, gen_elapsed=None):
    return {
        "problem_id": pid, "category": problem["category"], "subcategory": problem["subcategory"],
        "short_answer": problem["short_answer"], "model": model,
        "reasoning_effort": REASONING_EFFORT, "seed": SEED,
        "score": None, "passed": False, "elapsed_s": elapsed,
        "gen_elapsed_s": gen_elapsed, "judge_elapsed_s": None,
        "gen_usage": gen_usage, "judge_usage": None,
        "final_solution": gen_text, "reasoning_text": None,
        "verdict": None, "error": err,
    }


# ============================================================================
# Wave executor (run a list of (model, pid) pairs in one parallel wave)
# ============================================================================

def run_wave(label, trials, problems, prompts, mock, all_results, out_path_partial):
    if is_aborted():
        print(f"\n[{_ts()}] [skip wave {label}] abort tripped", flush=True)
        return
    total = len(trials)
    print(f"\n{'='*100}\n[{_ts()}] WAVE {label}: {total} trials, workers={MAX_WORKERS}\n{'='*100}", flush=True)

    if not mock:
        st = poll_key_usage(force=True)
        if st["usage_usd"] is not None:
            print(f"[{_ts()}] [budget] before wave {label}: usage=${st['usage_usd']:.4f}", flush=True)
        if st["abort"]:
            print(f"[{_ts()}] [ABORT] {st['abort_reason']}", flush=True)
            return

    completed = 0
    def _run(model, pid):
        return run_trial(pid, problems[pid], model, prompts, mock)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, m, pid): (m, pid) for m, pid in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            m, pid = futs[fut]
            ms = m.split("/")[-1]
            completed += 1
            try:
                r = fut.result(timeout=TRIAL_TIMEOUT)
            except Exception as e:
                print(f"[{_ts()}] FAILED [{pid}|{ms}]: {e}", flush=True)
                traceback.print_exc()
                r = _err(pid, problems[pid], m, str(e), 0)
            all_results.append(r)
            _save_partial(all_results, out_path_partial)

            if not mock and completed % 5 == 0:
                st = poll_key_usage(force=False)
                if st["usage_usd"] is not None:
                    print(f"[{_ts()}] [budget] wave {label} {completed}/{total}: usage=${st['usage_usd']:.4f}", flush=True)
                if st["abort"]:
                    print(f"[{_ts()}] [ABORT] {st['abort_reason']}", flush=True)


def _save_partial(all_results, out_path):
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": EXPERIMENT_NAME,
                "partial":    True,
                "n_results":  len(all_results),
                "results":    all_results,
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[{_ts()}] [WARN] partial save: {e}", flush=True)


# ============================================================================
# Reporting
# ============================================================================

def report(results, problems, mock, suffix=""):
    print("\n" + "=" * 110)
    print("GPT-5.4 FAMILY @ xhigh REASONING (12 PIDs base, gpt-5.4 only on prior failures)")
    print("=" * 110)

    by_m = {}
    for r in results:
        by_m.setdefault(r["model"], []).append(r)

    summary = {}
    for model, rs in by_m.items():
        ms = model.split("/")[-1]
        valid  = [r for r in rs if r["score"] is not None]
        scored = [r["score"] for r in valid]
        gen_lat = [r["gen_elapsed_s"] for r in valid if r.get("gen_elapsed_s") is not None]
        in_t  = [r["gen_usage"]["prompt_tokens"]     for r in valid if r.get("gen_usage")]
        out_t = [r["gen_usage"]["completion_tokens"] for r in valid if r.get("gen_usage")]
        rea_t = [r["gen_usage"].get("reasoning_tokens", 0) for r in valid if r.get("gen_usage")]
        n_err = sum(1 for r in rs if r.get("error"))
        summary[model] = {
            "ms": ms,
            "n_trials": len(rs), "n_valid": len(valid), "n_errors": n_err,
            "n_correct": sum(scored), "accuracy": round(np.mean(scored), 3) if scored else 0.0,
            "mean_gen_lat":   round(np.mean(gen_lat), 1) if gen_lat else 0.0,
            "mean_in_tok":    int(np.mean(in_t)) if in_t else 0,
            "mean_out_tok":   int(np.mean(out_t)) if out_t else 0,
            "mean_reason_tok": int(np.mean(rea_t)) if rea_t else 0,
        }

    print(f"\n{'Model':<30} {'n':>4} {'err':>3} {'acc':>10} {'lat(s)':>7} {'in':>5} {'out':>7} {'reason':>7}")
    print("-" * 100)
    for model in sorted(by_m, key=lambda m: -summary[m]["accuracy"]):
        s = summary[model]
        acc = f"{s['n_correct']}/{s['n_valid']}={s['accuracy']*100:.0f}%"
        print(f"{s['ms']:<30} {s['n_valid']:>4} {s['n_errors']:>3} {acc:>10} {s['mean_gen_lat']:>7.1f} {s['mean_in_tok']:>5} {s['mean_out_tok']:>7} {s['mean_reason_tok']:>7}")

    if not mock:
        st = poll_key_usage(force=True)
        if st["usage_usd"] is not None:
            print(f"\n[OpenRouter] price_compare key usage: ${st['usage_usd']:.4f}")

    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment": EXPERIMENT_NAME, "date": datetime.now(timezone.utc).isoformat(),
            "mock": mock, "smoke": suffix == "_smoke",
            "reasoning_effort": REASONING_EFFORT,
            "max_tokens_gen": MAX_TOKENS_GEN, "max_workers": MAX_WORKERS,
            "judge_model": JUDGE_MODEL, "hard_budget_usd": HARD_BUDGET_USD,
            "model_plan": [{"model": m, "pids": pids} for m, pids in MODEL_PLAN],
            "abort": _usage_state["abort"], "abort_reason": _usage_state["abort_reason"],
            "openrouter_usage_end": _usage_state["usage_usd"],
            "problems": {pid: {k: v for k, v in p.items() if k != "text"}
                         | {"text_chars": len(p["text"])} for pid, p in problems.items()},
            "summary": {summary[m]["ms"]: summary[m] for m in by_m},
            "all_results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    return out_path


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="1 nano trial, real API")
    args = parser.parse_args()
    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()
    prompts = {
        "generator": load_prompt("generator.md"),
        "judge":     load_prompt("answerbench_judge.md"),
    }

    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")
    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Reasoning:     effort={REASONING_EFFORT}")
    for m, pids in MODEL_PLAN:
        print(f"  {m}  →  {len(pids)} PIDs")
    print(f"Hard budget:   ${HARD_BUDGET_USD:.2f}")
    if args.mock: print("[MOCK MODE]")
    if args.smoke: print("[SMOKE MODE]")
    print()

    if not args.mock:
        st = poll_key_usage(force=True)
        if st["usage_usd"] is not None:
            print(f"[startup] key usage: ${st['usage_usd']:.4f} of limit ${st['limit_usd']}")

    out_path_partial = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}_partial.json"
    print(f"Partial saves: {out_path_partial}\n", flush=True)

    t0 = time.time()
    all_results = []

    if args.smoke:
        # Single nano trial on first PID only.
        smoke_trials = [(SMOKE_MODEL, ALL_12_PIDS[0])]
        run_wave("smoke", smoke_trials, problems, prompts, args.mock, all_results, out_path_partial)
    else:
        # Wave 1: nano + mini, all 12 PIDs each (24 trials)
        wave1 = []
        for m, pids in MODEL_PLAN:
            if "gpt-5.4-nano" in m or "gpt-5.4-mini" in m:
                wave1 += [(m, pid) for pid in pids]
        run_wave("1 (nano+mini, 12 PIDs each)", wave1, problems, prompts, args.mock, all_results, out_path_partial)

        # Wave 2: gpt-5.4 on its 6 failed PIDs
        wave2 = []
        for m, pids in MODEL_PLAN:
            if m.endswith("/openai/gpt-5.4"):
                wave2 += [(m, pid) for pid in pids]
        run_wave("2 (gpt-5.4 on 6 failed PIDs)", wave2, problems, prompts, args.mock, all_results, out_path_partial)

    print(f"\nWall-clock: {round(time.time()-t0, 1)}s for {len(all_results)} trials", flush=True)
    report(all_results, problems, args.mock, suffix=suffix)


if __name__ == "__main__":
    main()
