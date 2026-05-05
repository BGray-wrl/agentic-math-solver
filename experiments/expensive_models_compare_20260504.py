#!/usr/bin/env python3
"""
Compare 4 expensive frontier models on a 12-problem stratified subset of the
same AnswerBench-50 set used in `answerbench_compare_20260504_20260504_084012`.

Goal: figure out whether any of the more expensive models we've been avoiding
is actually cost-effective vs. the previous 7-model run.

- 12 problems = 3 per category, sub-sampled (seed=42) from the prior 50.
- Mode: generate-only, pass@1, single seed.
- Judge: gemini-3.1-flash-lite-preview (matches prior run exactly).
- MAX_TOKENS_GEN = 65536 (don't suppress reasoning).

BUDGET CONTROL:
- Single dedicated key (OPENROUTER_API_KEY_price_compare, $12 cap).
- Hard killswitch at $9.50 spent (poll OpenRouter /auth/key every 3 completions).
- Per-model early abort if first 3 trials avg > $0.55/run (would project >$6.6 for 12).
- Models run SEQUENTIALLY in cost order (cheapest first); a blow-up on cheap
  end stops execution before expensive models are touched.

Usage:
    uv run experiments/expensive_models_compare_20260504.py --mock
    uv run experiments/expensive_models_compare_20260504.py --smoke   # kimi-only
    uv run experiments/expensive_models_compare_20260504.py
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

EXPERIMENT_NAME = "expensive_models_compare_20260504"

# Models under test, with user-supplied prices ($/M tokens, blended).
# Run sequentially in this order — cheapest first so a blow-up trips the
# killswitch before the most expensive model is touched.
MODELS = [
    ("openrouter/moonshotai/kimi-k2.6",              3.49),
    ("openrouter/qwen/qwen3.6-max-preview",          6.24),
    ("openrouter/google/gemini-3.1-pro-preview",    12.00),
    ("openrouter/openai/gpt-5.4",                   15.00),
]
PRICE_PER_MTOKEN = {m: p for m, p in MODELS}

SMOKE_MODEL = "openrouter/moonshotai/kimi-k2.6"

JUDGE_MODEL = "openrouter/google/gemini-3.1-flash-lite-preview"
# Judge runs on a separate (existing) key so it doesn't eat the price_compare budget.

SEED = 42

MAX_TOKENS_GEN   = 65536
MAX_TOKENS_JUDGE = 4000

# Single dedicated test key — OpenRouter rate-limits by account credits, not
# concurrency, so fan out aggressively (48 = 4 models × 12 problems all at once).
MAX_WORKERS     = 48
TRIAL_TIMEOUT   = 1200
LITELLM_TIMEOUT = 1100

# Budget killswitch (USD, against price_compare key only).
HARD_BUDGET_USD          = 9.50
EARLY_ABORT_AVG_PER_RUN  = 0.55   # after first 3 trials of a model

# 12 stratified problems (3 per category, seed=42 sub-sample of prior 50).
SUBSET_PIDS = [
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

# Path to prior run's JSON — we pull problems from there for guaranteed
# like-to-like matching.
PRIOR_RUN_JSON = (
    Path(__file__).parent / "results"
    / "answerbench_compare_20260504_20260504_084012.json"
)

# ============================================================================
# Paths
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


# ============================================================================
# Keys: gen models use price_compare ONLY, judge uses an existing key
# ============================================================================

load_dotenv()

PRICE_COMPARE_KEY = os.getenv("OPENROUTER_API_KEY_price_compare")
if not PRICE_COMPARE_KEY:
    raise SystemExit(
        "OPENROUTER_API_KEY_price_compare not in .env — required for budget isolation."
    )

# Judge key: prefer the explicit "X" pool so we don't consume from the
# price_compare key. Fall back to default if needed.
JUDGE_KEY = (
    os.getenv("OPENROUTER_API_KEY_X")
    or os.getenv("OPENROUTER_API_KEY")
)
if not JUDGE_KEY:
    raise SystemExit("No judge key (need OPENROUTER_API_KEY_X or OPENROUTER_API_KEY).")


# ============================================================================
# OpenRouter usage poller (ground-truth budget for the price_compare key)
# ============================================================================

_usage_lock = threading.Lock()
_usage_state = {
    "usage_usd":    None,   # float, latest known cumulative usage (USD)
    "limit_usd":    None,   # float, key's hard cap
    "last_polled":  0.0,
    "abort":        False,
    "abort_reason": None,
}


def poll_key_usage(force=False) -> dict:
    """Query OpenRouter for cumulative spend on the price_compare key.

    Returns the full state dict. Throttled to one call per ~10s unless force=True.
    """
    now = time.time()
    with _usage_lock:
        if not force and (now - _usage_state["last_polled"]) < 10:
            return dict(_usage_state)
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {PRICE_COMPARE_KEY}"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        with _usage_lock:
            _usage_state["usage_usd"]   = float(data.get("usage", 0.0))
            _usage_state["limit_usd"]   = (
                float(data["limit"]) if data.get("limit") is not None else None
            )
            _usage_state["last_polled"] = now
            if (
                _usage_state["usage_usd"] is not None
                and _usage_state["usage_usd"] >= HARD_BUDGET_USD
                and not _usage_state["abort"]
            ):
                _usage_state["abort"] = True
                _usage_state["abort_reason"] = (
                    f"OpenRouter usage ${_usage_state['usage_usd']:.2f} "
                    f">= hard budget ${HARD_BUDGET_USD:.2f}"
                )
    except Exception as e:
        print(f"[{_ts()}] [poll] WARN: failed to query /auth/key: {e}", flush=True)
    return dict(_usage_state)


def trip_abort(reason: str):
    with _usage_lock:
        if not _usage_state["abort"]:
            _usage_state["abort"] = True
            _usage_state["abort_reason"] = reason


def is_aborted() -> bool:
    with _usage_lock:
        return bool(_usage_state["abort"])


# ============================================================================
# LLM call (single key for gen models, separate key for judge)
# ============================================================================

def call_model(model, system, prompt, max_tokens, key, retries=2, backoff=4.0):
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
            if "402" in msg or "credit" in msg.lower() or "insufficient" in msg.lower():
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1}: {e}, retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


# ============================================================================
# Verdict parsing
# ============================================================================

VERDICT_RE = re.compile(r"<verdict>\s*(correct|incorrect)\s*</verdict>", re.I)


def parse_verdict(text: str):
    if text is None:
        return None
    m = VERDICT_RE.search(text)
    if m:
        return 1 if m.group(1).lower() == "correct" else 0
    head = text[:200].lower()
    if "verdict>correct" in head or "answer is correct" in head:
        return 1
    if "verdict>incorrect" in head or "answer is incorrect" in head:
        return 0
    return None


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


# ============================================================================
# Problem loading: pull from prior run's JSON for exact like-to-like
# ============================================================================

def load_problems() -> dict:
    """Pull the 12 chosen problems from the prior answerbench_compare result.

    The prior JSON only stores text_chars (length), not the full text — so we
    still read the CSV for the actual problem statement. We use the prior
    JSON's pid → category/short_answer mapping to verify the subset matches.
    """
    import csv
    with open(ANSWERBENCH_CSV, encoding="utf-8") as f:
        rows = {r["Problem ID"]: r for r in csv.DictReader(f)}

    with open(PRIOR_RUN_JSON, encoding="utf-8") as f:
        prior = json.load(f)
    prior_problems = prior["problems"]

    selected: dict[str, dict] = {}
    for pid in SUBSET_PIDS:
        if pid not in prior_problems:
            raise SystemExit(f"{pid} not in prior run — subset mismatch")
        if pid not in rows:
            raise SystemExit(f"{pid} not in AnswerBench CSV")
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
# Single trial
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
            key=PRICE_COMPARE_KEY,
        )
        gen_elapsed = round(time.time() - gen_t0, 2)
        print(f"{tag} gen {gen_elapsed}s in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']}", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        msg = str(e)
        print(f"{tag} GEN FAILED: {e} ({elapsed}s)", flush=True)
        if "402" in msg or "credit" in msg.lower() or "insufficient" in msg.lower():
            trip_abort(f"key out of credits during {ms}: {msg[:120]}")
        return _err(problem_id, problem, model, msg, elapsed)

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
            key=JUDGE_KEY,
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
        "score":           score,
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
# Per-model executor with budget gates
# ============================================================================

def run_model(model, problems, prompts, mock, all_results, out_path_partial):
    pids = sorted(problems.keys())
    ms = model.split("/")[-1]
    print(f"\n{'='*100}\n[{_ts()}] === MODEL: {ms} (price ${PRICE_PER_MTOKEN[model]:.2f}/Mtok) ===\n{'='*100}", flush=True)

    # Pre-flight budget poll.
    if not mock:
        st = poll_key_usage(force=True)
        if st["usage_usd"] is not None:
            remaining = HARD_BUDGET_USD - st["usage_usd"]
            print(f"[{_ts()}] [budget] before {ms}: usage=${st['usage_usd']:.4f}, remaining vs hard cap=${remaining:.2f}", flush=True)
            if st["abort"]:
                print(f"[{_ts()}] [ABORT] {st['abort_reason']}", flush=True)
                return []

    model_results = []
    completed = 0
    submitted_pids = set()

    def _run(pid):
        return run_trial(pid, problems[pid], model, prompts, mock)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for pid in pids:
            if is_aborted():
                break
            futs[ex.submit(_run, pid)] = pid
            submitted_pids.add(pid)

        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * len(pids)):
            pid = futs[fut]
            completed += 1
            try:
                r = fut.result(timeout=TRIAL_TIMEOUT)
            except Exception as e:
                print(f"[{_ts()}] FAILED [{pid}|{ms}]: {e}", flush=True)
                traceback.print_exc()
                r = _err(pid, problems[pid], model, str(e), 0)
            model_results.append(r)
            all_results.append(r)

            # Persist on every completion (crash-safe).
            _save_partial(all_results, out_path_partial)

            # Poll usage periodically and after early trials.
            if not mock and (completed <= 3 or completed % 3 == 0):
                st = poll_key_usage(force=(completed <= 3))
                if st["usage_usd"] is not None:
                    print(f"[{_ts()}] [budget] {ms} {completed}/{len(pids)}: usage=${st['usage_usd']:.4f}", flush=True)
                if st["abort"]:
                    print(f"[{_ts()}] [ABORT] {st['abort_reason']}", flush=True)

            # Per-model early abort: after first 3 valid trials, project total cost.
            if not mock and completed == 3:
                early = [x for x in model_results if x.get("est_cost_usd") is not None]
                if early:
                    avg = sum(x["est_cost_usd"] for x in early) / len(early)
                    print(f"[{_ts()}] [early-check] {ms} avg cost over {len(early)} trials: ${avg:.4f}", flush=True)
                    if avg > EARLY_ABORT_AVG_PER_RUN:
                        trip_abort(
                            f"{ms} early avg ${avg:.4f} > ${EARLY_ABORT_AVG_PER_RUN} — would project ${avg*len(pids):.2f}"
                        )

    if is_aborted():
        st = _usage_state
        print(f"\n[{_ts()}] [{ms}] ABORTED: {st.get('abort_reason')}", flush=True)
    return model_results


def run_all_parallel(models_to_run, problems, prompts, mock, all_results, out_path_partial):
    """Submit all (model, problem) pairs at once across MAX_WORKERS threads.

    OpenRouter rate-limits by credits, not concurrency, so a single wave of
    M*P concurrent requests is fine on one key.
    """
    pids = sorted(problems.keys())
    trials = [(m, pid) for m in models_to_run for pid in pids]
    total = len(trials)
    print(f"\n{'='*100}\n[{_ts()}] Submitting {total} trials in one wave (workers={MAX_WORKERS})\n{'='*100}", flush=True)

    if not mock:
        st = poll_key_usage(force=True)
        if st["usage_usd"] is not None:
            print(f"[{_ts()}] [budget] start: usage=${st['usage_usd']:.4f}, hard cap=${HARD_BUDGET_USD:.2f}", flush=True)

    completed_by_model: dict[str, list] = {}
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
            completed_by_model.setdefault(m, []).append(r)
            _save_partial(all_results, out_path_partial)

            # Periodic budget poll.
            if not mock and completed % 5 == 0:
                st = poll_key_usage(force=False)
                if st["usage_usd"] is not None:
                    print(f"[{_ts()}] [budget] {completed}/{total}: usage=${st['usage_usd']:.4f}", flush=True)
                if st["abort"]:
                    print(f"[{_ts()}] [ABORT] {st['abort_reason']}", flush=True)

    # Final usage poll.
    if not mock:
        poll_key_usage(force=True)


def _save_partial(all_results, out_path):
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "experiment":  EXPERIMENT_NAME,
                "partial":     True,
                "n_results":   len(all_results),
                "results":     all_results,
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[{_ts()}] [WARN] failed partial save: {e}", flush=True)


# ============================================================================
# Reporting
# ============================================================================

def report(results, problems, mock, suffix=""):
    print("\n" + "=" * 110)
    print("EXPENSIVE-MODELS COMPARISON (12 problems, pass@1, gemini-3.1-flash-lite judge)")
    print("=" * 110)

    # Recover models actually run from results.
    models_seen = []
    for m, _ in MODELS:
        if any(r["model"] == m for r in results):
            models_seen.append(m)

    summary = {}
    for model in models_seen:
        ms = model.split("/")[-1]
        rs = [r for r in results if r["model"] == model]
        valid = [r for r in rs if r["score"] is not None]
        scored = [r["score"] for r in valid]
        gen_lat = [r["gen_elapsed_s"] for r in valid if r.get("gen_elapsed_s") is not None]
        gen_in_tok  = [r["gen_usage"]["prompt_tokens"]     for r in valid if r.get("gen_usage")]
        gen_out_tok = [r["gen_usage"]["completion_tokens"] for r in valid if r.get("gen_usage")]
        costs   = [r["est_cost_usd"] for r in valid if r.get("est_cost_usd") is not None]
        n_err   = sum(1 for r in rs if r.get("error"))

        per_cat = {}
        for cat in ["Algebra", "Combinatorics", "Geometry", "Number theory"]:
            cat_rs = [r for r in valid if r["category"] == cat]
            if cat_rs:
                per_cat[cat] = {
                    "n":         len(cat_rs),
                    "n_correct": sum(r["score"] for r in cat_rs),
                    "accuracy":  round(float(np.mean([r["score"] for r in cat_rs])), 3),
                }

        summary[model] = {
            "ms":               ms,
            "price_per_mtoken": PRICE_PER_MTOKEN.get(model),
            "n_trials":         len(rs),
            "n_valid":          len(valid),
            "n_errors":         n_err,
            "n_correct":        sum(scored),
            "accuracy":         round(float(np.mean(scored)), 3) if scored else 0.0,
            "mean_gen_lat":     round(float(np.mean(gen_lat)), 1) if gen_lat else 0.0,
            "median_gen_lat":   round(float(np.median(gen_lat)), 1) if gen_lat else 0.0,
            "mean_in_tok":      int(np.mean(gen_in_tok))  if gen_in_tok  else 0,
            "mean_out_tok":     int(np.mean(gen_out_tok)) if gen_out_tok else 0,
            "mean_cost":        round(float(np.mean(costs)), 4) if costs else None,
            "total_cost":       round(float(np.sum(costs)), 3) if costs else None,
            "per_category":     per_cat,
        }

    print(f"\n{'Model':<36} {'$/Mt':>6} {'n':>4} {'err':>3}  {'acc':>6}  {'lat(s)':>7}  {'out_tok':>8}  {'$/run':>8}  {'$ tot':>7}")
    print("-" * 110)
    for model in sorted(models_seen, key=lambda m: -summary[m]["accuracy"]):
        s = summary[model]
        price_s = f"${s['price_per_mtoken']:.2f}"
        cost_s  = f"${s['mean_cost']:.4f}" if s['mean_cost'] is not None else "—"
        tcost_s = f"${s['total_cost']:.3f}" if s['total_cost'] is not None else "—"
        acc_s = f"{s['n_correct']}/{s['n_valid']}"
        print(f"{s['ms']:<36} {price_s:>6} {s['n_valid']:>4} {s['n_errors']:>3}  "
              f"{acc_s:>6}  {s['mean_gen_lat']:>7.1f}  {s['mean_out_tok']:>8}  {cost_s:>8}  {tcost_s:>7}")

    # Final OpenRouter-reported usage on the price_compare key.
    if not mock:
        st = poll_key_usage(force=True)
        if st["usage_usd"] is not None:
            print(f"\n[OpenRouter ground truth]  price_compare key usage: ${st['usage_usd']:.4f}", flush=True)

    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment":      EXPERIMENT_NAME,
            "date":            datetime.now(timezone.utc).isoformat(),
            "mock":            mock,
            "smoke":           suffix == "_smoke",
            "seed":            SEED,
            "judge_model":     JUDGE_MODEL,
            "max_workers":     MAX_WORKERS,
            "max_tokens_gen":  MAX_TOKENS_GEN,
            "max_tokens_judge": MAX_TOKENS_JUDGE,
            "hard_budget_usd": HARD_BUDGET_USD,
            "early_abort_avg_per_run": EARLY_ABORT_AVG_PER_RUN,
            "subset_pids":     SUBSET_PIDS,
            "models":          [{"id": m, "price_per_mtoken": p} for m, p in MODELS],
            "abort":           _usage_state["abort"],
            "abort_reason":    _usage_state["abort_reason"],
            "openrouter_usage_end": _usage_state["usage_usd"],
            "problems":        {pid: {k: v for k, v in p.items() if k != "text"}
                                | {"text_chars": len(p["text"])} for pid, p in problems.items()},
            "summary":         {summary[m]["ms"]: summary[m] for m in models_seen},
            "all_results":     results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    return out_path


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock",  action="store_true", help="No API calls.")
    parser.add_argument("--smoke", action="store_true", help="Real run, kimi only, 2 problems.")
    args = parser.parse_args()
    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()
    if args.smoke:
        # Limit to 2 problems for smoke (one Algebra, one Combinatorics).
        problems = {pid: problems[pid] for pid in list(problems.keys())[:2]}
    prompts = {
        "generator": load_prompt("generator.md"),
        "judge":     load_prompt("answerbench_judge.md"),
    }
    models_to_run = [SMOKE_MODEL] if args.smoke else [m for m, _ in MODELS]
    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")

    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Problems:      {len(problems)} (subset of prior 50)")
    by_cat = {}
    for p in problems.values():
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat:<20s} {n}")
    print(f"Models:        {len(models_to_run)}")
    for m in models_to_run:
        print(f"  {m}  ${PRICE_PER_MTOKEN[m]:.2f}/Mtok")
    print(f"Judge:         {JUDGE_MODEL}  (separate key)")
    print(f"Hard budget:   ${HARD_BUDGET_USD:.2f} on price_compare key")
    print(f"Workers:       {MAX_WORKERS}  (single key)")
    if args.mock:
        print("[MOCK MODE]")
    if args.smoke:
        print("[SMOKE MODE — kimi only, 2 problems]")
    print(f"Total trials:  {len(problems) * len(models_to_run)}\n", flush=True)

    # Pre-flight: query starting balance.
    if not args.mock:
        st = poll_key_usage(force=True)
        if st["usage_usd"] is not None:
            print(f"[startup] price_compare key usage: ${st['usage_usd']:.4f} of limit ${st['limit_usd']}", flush=True)
            if st["usage_usd"] >= HARD_BUDGET_USD:
                raise SystemExit(f"Already over budget: ${st['usage_usd']:.4f} >= ${HARD_BUDGET_USD:.2f}")

    out_path_partial = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}_partial.json"
    print(f"Partial saves: {out_path_partial}", flush=True)

    t0 = time.time()
    all_results = []
    if args.smoke:
        # Smoke path keeps the per-model loop (only 1 model anyway).
        for model in models_to_run:
            if is_aborted():
                print(f"\n[{_ts()}] [skip] {model.split('/')[-1]} — abort tripped", flush=True)
                continue
            run_model(model, problems, prompts, args.mock, all_results, out_path_partial)
    else:
        run_all_parallel(models_to_run, problems, prompts, args.mock, all_results, out_path_partial)
    print(f"\nWall-clock: {round(time.time()-t0, 1)}s for {len(all_results)} trials", flush=True)
    report(all_results, problems, args.mock, suffix=suffix)


if __name__ == "__main__":
    main()
