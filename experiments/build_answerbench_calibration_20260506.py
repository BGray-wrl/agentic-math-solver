#!/usr/bin/env python3
"""
Build calibration datasets from existing AnswerBench result JSONs.

Two outputs (under repo-root /results/, NOT experiments/results):

  results/answerbench_calibration_20260506/
    trials.csv      — 1 row per (model_config, problem_id) attempt; missing/dropped trials present with score=null
    trials.jsonl    — same data with full records (verdict text, reasoning text)
    summary.csv     — 1 row per (model, model_config) with aggregates
    data_dictionary.md
    report.md

  results/expensive_models_calibration_20260506/  (12-problem subset, 4 frontier models)
    trials.csv, trials.jsonl, summary.csv, data_dictionary.md, report.md

No fabrication: trials that don't exist in source JSONs are emitted with score=null and
a clear `error` value so the matrix is complete-by-config but data is honest.
"""
from __future__ import annotations

import csv
import json
import os
import statistics
from collections import defaultdict, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv("/Users/benjamingrayzel/sandbox/agentic-math-solver/.env")

ROOT      = Path("/Users/benjamingrayzel/sandbox/agentic-math-solver")
EXP_RES   = ROOT / "experiments" / "results"
OUT_AB    = ROOT / "results" / "answerbench_calibration_20260506"
OUT_EXP   = ROOT / "results" / "expensive_models_calibration_20260506"
ANSW_CSV  = ROOT / "benchmarks" / "IMO-bench" / "answerbench_v2.csv"

OUT_AB.mkdir(parents=True, exist_ok=True)
OUT_EXP.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Authoritative pricing — fetched once at build time.
# ============================================================================

KEY = os.getenv("OPENROUTER_API_KEY_price_compare") or os.getenv("OPENROUTER_API_KEY")

NEEDED_MIDS = [
    # AnswerBench-50 dataset
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
    "qwen/qwen3.6-35b-a3b",
    "qwen/qwen3.6-plus",
    "google/gemini-3-flash-preview",
    "google/gemma-4-31b-it",
    "openai/gpt-oss-120b",
    "openai/gpt-5.4-nano",
    # Expensive 12-problem dataset
    "moonshotai/kimi-k2.6",
    "qwen/qwen3.6-max-preview",
    "google/gemini-3.1-pro-preview",
    "openai/gpt-5.4",
]

def fetch_pricing():
    r = requests.get("https://openrouter.ai/api/v1/models",
                     headers={"Authorization": f"Bearer {KEY}"} if KEY else {},
                     timeout=30)
    r.raise_for_status()
    out = {}
    for m in r.json()["data"]:
        if m["id"] in NEEDED_MIDS:
            p = m.get("pricing", {})
            out[m["id"]] = {
                "prompt":     float(p.get("prompt", 0) or 0),
                "completion": float(p.get("completion", 0) or 0),
                "request":    float(p.get("request", 0) or 0),
                "internal_reasoning": float(p.get("internal_reasoning", 0) or 0),
            }
    return out

PRICES = fetch_pricing()
PRICING_FETCH_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
print(f"Fetched authoritative pricing for {len(PRICES)} models on {PRICING_FETCH_DATE}")
for mid in NEEDED_MIDS:
    if mid not in PRICES:
        print(f"  WARN: {mid} not found in OpenRouter /models response")

# ============================================================================
# Canonical model name (short form) from full OpenRouter id.
# ============================================================================

def canon_name(model_id: str) -> str:
    """Return short-form name from openrouter ID like 'openrouter/openai/gpt-5.4-nano'
    or just 'openai/gpt-5.4-nano'."""
    s = model_id.replace("openrouter/", "")
    return s.split("/")[-1]

def strip_or(model_id: str) -> str:
    return model_id.replace("openrouter/", "")

# ============================================================================
# AnswerBench-50: stratified subset (seed=42), same logic as the original run
# ============================================================================

import random
STRATA = OrderedDict([
    ("Algebra", 12), ("Combinatorics", 13), ("Geometry", 12), ("Number theory", 13),
])

def load_50_problems():
    """Recompute the same stratified 50-problem set from answerbench_v2.csv (seed=42)."""
    with open(ANSW_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_cat = defaultdict(list)
    for r in rows:
        cat = r["Category"]
        if cat in STRATA:
            by_cat[cat].append(r)
    rng = random.Random(42)
    out = OrderedDict()
    for cat, n in STRATA.items():
        pool = sorted(by_cat[cat], key=lambda r: r["Problem ID"])
        chosen = rng.sample(pool, n)
        for row in chosen:
            out[row["Problem ID"]] = {
                "category": row["Category"],
                "subcategory": row.get("Subcategory", "").strip(),
                "short_answer": row["Short Answer"].strip(),
            }
    return out

PROBLEMS_50 = load_50_problems()
PIDS_50 = list(PROBLEMS_50.keys())
print(f"Loaded {len(PIDS_50)} stratified problems")

# ============================================================================
# Source JSONs and their model_config tagging
# ============================================================================

SOURCES_AB = [
    # (label, filename, model_config, run_date, expected_models, optional all-50 expectation)
    {
        "label": "original_7model_default",
        "file":  "answerbench_compare_20260504_20260504_084012.json",
        "model_config": "default",
        "reasoning_param": None,
        "run_date": "2026-05-04",
        "expects_50_per_model": True,
    },
    {
        "label": "nano_xhigh",
        "file":  "nano_xhigh_answerbench50_20260505_partial.json",
        "model_config": "xhigh",
        "reasoning_param": {"effort": "xhigh"},
        "run_date": "2026-05-05",
        "expects_50_per_model": True,
    },
    {
        "label": "gemini3flash_xhigh_retest",
        "file":  "gemini3flash_xhigh_retest_20260505_20260505_064305.json",
        "model_config": "xhigh",
        "reasoning_param": {"effort": "xhigh"},
        "run_date": "2026-05-05",
        "expects_50_per_model": False,  # only 13 PIDs
    },
    {
        "label": "v4flash_reasoning_off",
        "file":  "v4flash_noreasoning_answerbench50_20260505_partial.json",
        "model_config": "reasoning_off",
        "reasoning_param": {"enabled": False},
        "run_date": "2026-05-05",
        "expects_50_per_model": True,
    },
    {
        "label": "cheap_xhigh",
        "file":  "cheap_xhigh_answerbench50_20260505_20260505_081826.json",
        "model_config": "xhigh",
        "reasoning_param": {"effort": "xhigh"},
        "run_date": "2026-05-05",
        "expects_50_per_model": True,
    },
    {
        "label": "gemini3pro_default_remaining",
        "file":  "gemini3pro_answerbench50_remaining_20260507_20260507_075148.json",
        "model_config": "default",
        "reasoning_param": None,
        "run_date": "2026-05-07",
        "expects_50_per_model": False,  # 38 PIDs (the remainder of the 50)
    },
    {
        # 12 of the 50 PIDs were already covered by gemini-3.1-pro at default in
        # the expensive_models probe on 2026-05-04. Pull just those rows in here
        # so the gemini-3.1-pro/default row of the AB-50 dataset has all 50.
        "label": "gemini3pro_default_from_expensive12",
        "file":  "expensive_models_compare_20260504_20260505_012855_partial.json",
        "model_config": "default",
        "reasoning_param": None,
        "run_date": "2026-05-04",
        "expects_50_per_model": False,
        "model_filter": ["openrouter/google/gemini-3.1-pro-preview"],
    },
]

JUDGE_MODEL = "google/gemini-3.1-flash-lite-preview"

# ============================================================================
# Trial extraction
# ============================================================================

def trial_array(d):
    """Source files use either 'all_results' or 'results' for the trial array."""
    if "all_results" in d: return d["all_results"]
    if "results" in d:     return d["results"]
    raise SystemExit("no all_results / results array")

def est_cost_per_trial(model_id_short: str, gen_usage: dict | None) -> float | None:
    if not gen_usage: return None
    p = PRICES.get(model_id_short)
    if not p: return None
    return (gen_usage.get("prompt_tokens", 0) * p["prompt"]
            + gen_usage.get("completion_tokens", 0) * p["completion"])

def trial_to_row(trial: dict, source: dict) -> dict:
    model_id_full = trial["model"]                # e.g. "openrouter/openai/gpt-5.4-nano"
    model_id      = strip_or(model_id_full)        # "openai/gpt-5.4-nano"
    gen_u   = trial.get("gen_usage")  or {}
    judge_u = trial.get("judge_usage") or {}
    verdict_raw = trial.get("verdict")
    if verdict_raw and len(verdict_raw) > 1024:
        verdict_raw = verdict_raw[:1024] + "...[truncated]"
    return {
        "model":              canon_name(model_id_full),
        "model_id":           model_id,
        "model_config":       source["model_config"],
        "reasoning_param_json": json.dumps(source["reasoning_param"], separators=(",", ":")) if source["reasoning_param"] is not None else None,
        "problem_id":         trial.get("problem_id"),
        "category":           trial.get("category"),
        "subcategory":        trial.get("subcategory"),
        "short_answer":       trial.get("short_answer"),
        "score":              trial.get("score"),
        "verdict_raw":        verdict_raw,
        "gen_elapsed_s":      trial.get("gen_elapsed_s"),
        "judge_elapsed_s":    trial.get("judge_elapsed_s"),
        "total_elapsed_s":    trial.get("elapsed_s"),
        "prompt_tokens":      gen_u.get("prompt_tokens"),
        "completion_tokens":  gen_u.get("completion_tokens"),
        "reasoning_tokens":   gen_u.get("reasoning_tokens"),
        "total_tokens":       gen_u.get("total_tokens"),
        "judge_prompt_tokens":     judge_u.get("prompt_tokens"),
        "judge_completion_tokens": judge_u.get("completion_tokens"),
        "est_cost_usd":       est_cost_per_trial(model_id, gen_u),
        "judge_model":        JUDGE_MODEL,
        "run_date":           source["run_date"],
        "source_file":        source["file"],
        "error":              trial.get("error"),
    }

# Placeholder rows for "we know this (model_config, pid) was not tested"
def missing_row(model_short: str, model_id: str, model_config: str,
                reasoning_param, pid: str, source_file: str, run_date: str) -> dict:
    pinfo = PROBLEMS_50.get(pid, {})
    return {
        "model":              model_short,
        "model_id":           model_id,
        "model_config":       model_config,
        "reasoning_param_json": json.dumps(reasoning_param, separators=(",", ":")) if reasoning_param is not None else None,
        "problem_id":         pid,
        "category":           pinfo.get("category"),
        "subcategory":        pinfo.get("subcategory"),
        "short_answer":       pinfo.get("short_answer"),
        "score":              None,
        "verdict_raw":        None,
        "gen_elapsed_s":      None,
        "judge_elapsed_s":    None,
        "total_elapsed_s":    None,
        "prompt_tokens":      None,
        "completion_tokens":  None,
        "reasoning_tokens":   None,
        "total_tokens":       None,
        "judge_prompt_tokens":     None,
        "judge_completion_tokens": None,
        "est_cost_usd":       None,
        "judge_model":        JUDGE_MODEL,
        "run_date":           run_date,
        "source_file":        source_file,
        "error":              "not_tested_at_this_config",
    }

# ============================================================================
# Build AnswerBench-50 dataset
# ============================================================================

def build_answerbench_50():
    rows: list[dict] = []
    full_records: list[dict] = []   # for jsonl with full text fields

    # First pass: ingest every actual trial.
    for src in SOURCES_AB:
        path = EXP_RES / src["file"]
        d = json.load(open(path))
        mfilter = set(src.get("model_filter") or [])
        for t in trial_array(d):
            if mfilter and t.get("model") not in mfilter:
                continue
            row = trial_to_row(t, src)
            rows.append(row)
            full = dict(row)
            full["final_solution"] = t.get("final_solution")
            full["reasoning_text"] = t.get("reasoning_text")
            full_records.append(full)

    # Second pass: pad with missing-trial placeholders for partially-tested configs.
    # (model_short, model_config) -> {pid -> row} actually present
    seen = defaultdict(set)
    for r in rows:
        seen[(r["model"], r["model_config"])].add(r["problem_id"])

    # Pad gemini-3-flash-preview xhigh (only 13 PIDs tested).
    gem_xhigh_present = seen[("gemini-3-flash-preview", "xhigh")]
    for pid in PIDS_50:
        if pid not in gem_xhigh_present:
            rows.append(missing_row(
                "gemini-3-flash-preview", "google/gemini-3-flash-preview",
                "xhigh", {"effort": "xhigh"}, pid,
                "gemini3flash_xhigh_retest_20260505_20260505_064305.json", "2026-05-05",
            ))

    # Pad nano-xhigh's 1 missing PID (geometry-021 hung).
    nano_present = seen[("gpt-5.4-nano", "xhigh")]
    for pid in PIDS_50:
        if pid not in nano_present:
            rows.append({
                **missing_row("gpt-5.4-nano", "openai/gpt-5.4-nano", "xhigh",
                              {"effort": "xhigh"}, pid,
                              "nano_xhigh_answerbench50_20260505_partial.json", "2026-05-05"),
                "error": "trial killed (hung >70 min, HTTP timeout did not fire)",
            })

    # Sort canonically: model, model_config, pid for stable diffs.
    config_order = {"default": 0, "xhigh": 1, "reasoning_off": 2}
    pid_order    = {pid: i for i, pid in enumerate(PIDS_50)}
    rows.sort(key=lambda r: (r["model"], config_order.get(r["model_config"], 99),
                             pid_order.get(r["problem_id"], 99)))
    full_records.sort(key=lambda r: (r["model"], config_order.get(r["model_config"], 99),
                                     pid_order.get(r["problem_id"], 99)))

    # Write trials.csv and trials.jsonl
    cols = list(rows[0].keys())
    with open(OUT_AB / "trials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows: w.writerow(r)

    with open(OUT_AB / "trials.jsonl", "w", encoding="utf-8") as f:
        for r in full_records: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # Append the synthetic placeholders to jsonl (without final_solution/reasoning_text)
    placeholder_rows = [r for r in rows if r["error"] in (
        "not_tested_at_this_config", "trial killed (hung >70 min, HTTP timeout did not fire)")]
    if placeholder_rows:
        with open(OUT_AB / "trials.jsonl", "a", encoding="utf-8") as f:
            for r in placeholder_rows:
                f.write(json.dumps({**r, "final_solution": None, "reasoning_text": None},
                                   ensure_ascii=False) + "\n")

    print(f"  Wrote {len(rows)} rows to {OUT_AB}/trials.csv")
    return rows

# ============================================================================
# Build summary for AnswerBench-50
# ============================================================================

def safe_mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None
def safe_median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None

def summarize_trials(rows):
    """Group rows by (model, model_config) and compute per-group aggregates."""
    by_grp = defaultdict(list)
    for r in rows:
        by_grp[(r["model"], r["model_config"])].append(r)

    out = []
    for (model, cfg), trials in by_grp.items():
        valid = [t for t in trials if t["score"] is not None]
        n_correct = sum(t["score"] for t in valid)
        n_valid   = len(valid)
        n_total   = len(trials)
        # Per-category accuracy
        by_cat = defaultdict(list)
        for t in valid:
            by_cat[t["category"]].append(t["score"])
        per_cat = {c: f"{sum(s)}/{len(s)}" for c, s in sorted(by_cat.items())}

        gen_lat = [t["gen_elapsed_s"] for t in valid]
        in_t    = [t["prompt_tokens"]     for t in valid]
        out_t   = [t["completion_tokens"] for t in valid]
        rea_t   = [t["reasoning_tokens"]  for t in valid]
        costs   = [t["est_cost_usd"]      for t in valid]
        total_cost = sum(c for c in costs if c is not None)
        cost_per_run = total_cost / n_valid if n_valid else None
        accuracy = n_correct / n_valid if n_valid else None
        acc_pd   = (accuracy * 100) / cost_per_run if (accuracy is not None and cost_per_run) else None

        # Pricing for this model
        model_id = trials[0]["model_id"]
        p = PRICES.get(model_id, {})

        # Notes
        notes_bits = []
        n_err = sum(1 for t in trials if t.get("error"))
        if n_err:
            err_kinds = defaultdict(int)
            for t in trials:
                if t.get("error"):
                    err_kinds[t["error"]] += 1
            for k, c in err_kinds.items():
                notes_bits.append(f"{c} trials with error '{k}'")
        if model == "gpt-oss-120b" and cfg == "default":
            notes_bits.append("default behavior emits ~2K reasoning tokens (per probe) — not a true reasoning-off")
        if model == "gemma-4-31b-it" and cfg == "default":
            notes_bits.append("default behavior emits 0 reasoning tokens (per probe) — effectively reasoning-off")

        out.append({
            "model": model,
            "model_config": cfg,
            "model_id": model_id,
            "n_trials": n_total,
            "n_valid": n_valid,
            "n_correct": n_correct,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            "acc_by_category": json.dumps(per_cat),
            "mean_gen_lat_s":   round(safe_mean(gen_lat), 1)   if gen_lat else None,
            "median_gen_lat_s": round(safe_median(gen_lat), 1) if gen_lat else None,
            "mean_prompt_tokens":     int(safe_mean(in_t))   if [x for x in in_t  if x is not None] else None,
            "mean_completion_tokens": int(safe_mean(out_t))  if [x for x in out_t if x is not None] else None,
            "mean_reasoning_tokens":  int(safe_mean(rea_t))  if [x for x in rea_t if x is not None] else None,
            "total_cost_usd":   round(total_cost, 4),
            "cost_per_run_usd": round(cost_per_run, 5) if cost_per_run is not None else None,
            "acc_pct_per_dollar": round(acc_pd, 1) if acc_pd is not None else None,
            "price_in_per_M":    round(p.get("prompt", 0)*1e6, 4)     if p else None,
            "price_out_per_M":   round(p.get("completion", 0)*1e6, 4) if p else None,
            "run_date":   trials[0]["run_date"],
            "source_file": trials[0]["source_file"],
            "notes": "; ".join(notes_bits),
        })

    # Synthesized "gemini-3-flash-preview xhigh-effective" row.
    # Composite of: 37 prior-default-correct + 13 xhigh retests.
    # Real default-effort numbers for the 37 default-correct PIDs +
    # xhigh retest numbers for the 13 retested PIDs.
    gem_default = [r for r in rows if r["model"] == "gemini-3-flash-preview" and r["model_config"] == "default"]
    gem_xhigh   = [r for r in rows if r["model"] == "gemini-3-flash-preview" and r["model_config"] == "xhigh" and r["error"] != "not_tested_at_this_config"]
    if gem_default and gem_xhigh:
        # PIDs tested at xhigh
        retested_pids = {r["problem_id"] for r in gem_xhigh}
        # For non-retested PIDs, use the original default record
        kept_default = [r for r in gem_default if r["problem_id"] not in retested_pids]
        synth_trials = kept_default + gem_xhigh
        # Compute a synthetic summary row (cost mixes actual default + xhigh costs)
        n_correct = sum(r["score"] for r in synth_trials if r["score"] is not None)
        n_valid   = sum(1 for r in synth_trials if r["score"] is not None)
        in_t  = [r["prompt_tokens"]     for r in synth_trials if r["prompt_tokens"]     is not None]
        out_t = [r["completion_tokens"] for r in synth_trials if r["completion_tokens"] is not None]
        rea_t = [r["reasoning_tokens"]  for r in synth_trials if r["reasoning_tokens"]  is not None]
        gen_lat = [r["gen_elapsed_s"]   for r in synth_trials if r["gen_elapsed_s"]     is not None]
        total_cost = sum(r["est_cost_usd"] for r in synth_trials if r["est_cost_usd"] is not None)
        cost_per_run = total_cost / n_valid if n_valid else None
        accuracy = n_correct / n_valid if n_valid else None
        acc_pd = (accuracy*100)/cost_per_run if cost_per_run else None

        per_cat = defaultdict(list)
        for t in synth_trials:
            if t["score"] is not None:
                per_cat[t["category"]].append(t["score"])
        per_cat_s = {c: f"{sum(v)}/{len(v)}" for c, v in sorted(per_cat.items())}

        out.append({
            "model": "gemini-3-flash-preview",
            "model_config": "xhigh_effective_synthesized",
            "model_id": "google/gemini-3-flash-preview",
            "n_trials": len(synth_trials),
            "n_valid": n_valid,
            "n_correct": n_correct,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            "acc_by_category": json.dumps(per_cat_s),
            "mean_gen_lat_s":   round(safe_mean(gen_lat),1)   if gen_lat else None,
            "median_gen_lat_s": round(safe_median(gen_lat),1) if gen_lat else None,
            "mean_prompt_tokens":     int(safe_mean(in_t))  if in_t  else None,
            "mean_completion_tokens": int(safe_mean(out_t)) if out_t else None,
            "mean_reasoning_tokens":  int(safe_mean(rea_t)) if rea_t else None,
            "total_cost_usd":   round(total_cost, 4),
            "cost_per_run_usd": round(cost_per_run, 5) if cost_per_run is not None else None,
            "acc_pct_per_dollar": round(acc_pd, 1) if acc_pd is not None else None,
            "price_in_per_M":  round(PRICES["google/gemini-3-flash-preview"]["prompt"]*1e6, 4),
            "price_out_per_M": round(PRICES["google/gemini-3-flash-preview"]["completion"]*1e6, 4),
            "run_date":    "2026-05-04 + 2026-05-05",
            "source_file": "synthesized: 37 prior-default + 13 xhigh retests",
            "notes":       "SYNTHESIZED. 37 PIDs use default-effort result (assumed unchanged at xhigh). 13 PIDs use real xhigh retest. NOT a real 50-trial xhigh run.",
        })

    # Sort: by accuracy desc (synthesized rows last in their accuracy group).
    out.sort(key=lambda r: (-(r["accuracy"] or 0), r["cost_per_run_usd"] or 0))
    return out

# ============================================================================
# Build AnswerBench-50 outputs
# ============================================================================

print("\n=== AnswerBench-50 dataset ===")
ab_rows    = build_answerbench_50()
ab_summary = summarize_trials(ab_rows)

with open(OUT_AB / "summary.csv", "w", newline="", encoding="utf-8") as f:
    cols = list(ab_summary[0].keys())
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in ab_summary: w.writerow(r)
print(f"  Wrote {len(ab_summary)} summary rows to {OUT_AB}/summary.csv")

# ============================================================================
# 12-problem expensive dataset
# ============================================================================

EXPENSIVE_PIDS = sorted([
    "imo-bench-algebra-004", "imo-bench-algebra-012", "imo-bench-algebra-088",
    "imo-bench-combinatorics-026", "imo-bench-combinatorics-028", "imo-bench-combinatorics-084",
    "imo-bench-geometry-021", "imo-bench-geometry-029", "imo-bench-geometry-036",
    "imo-bench-number_theory-045", "imo-bench-number_theory-049", "imo-bench-number_theory-078",
])
EXPENSIVE_PROBLEMS = {pid: PROBLEMS_50.get(pid, {}) for pid in EXPENSIVE_PIDS}

EXP_SOURCE = {
    "label": "expensive_4model_default",
    "file":  "expensive_models_compare_20260504_20260505_012855_partial.json",
    "model_config": "default",
    "reasoning_param": None,
    "run_date": "2026-05-04",
    "expects_50_per_model": False,
}

def build_expensive_12():
    rows = []
    full_records = []
    d = json.load(open(EXP_RES / EXP_SOURCE["file"]))
    for t in trial_array(d):
        row = trial_to_row(t, EXP_SOURCE)
        rows.append(row)
        full = dict(row)
        full["final_solution"] = t.get("final_solution")
        full["reasoning_text"] = t.get("reasoning_text")
        full_records.append(full)

    # Pad missing trials per-model so the matrix is complete (kimi has 10 vs 12).
    seen = defaultdict(set)
    for r in rows:
        seen[(r["model"], r["model_id"])].add(r["problem_id"])
    expected_models = sorted({(r["model"], r["model_id"]) for r in rows})
    for (model, mid) in expected_models:
        for pid in EXPENSIVE_PIDS:
            if pid not in seen[(model, mid)]:
                pinfo = EXPENSIVE_PROBLEMS.get(pid, {})
                rows.append({
                    "model": model, "model_id": mid,
                    "model_config": EXP_SOURCE["model_config"],
                    "reasoning_param_json": None,
                    "problem_id": pid,
                    "category": pinfo.get("category"),
                    "subcategory": pinfo.get("subcategory"),
                    "short_answer": pinfo.get("short_answer"),
                    "score": None, "verdict_raw": None,
                    "gen_elapsed_s": None, "judge_elapsed_s": None, "total_elapsed_s": None,
                    "prompt_tokens": None, "completion_tokens": None,
                    "reasoning_tokens": None, "total_tokens": None,
                    "judge_prompt_tokens": None, "judge_completion_tokens": None,
                    "est_cost_usd": None,
                    "judge_model": JUDGE_MODEL,
                    "run_date": EXP_SOURCE["run_date"],
                    "source_file": EXP_SOURCE["file"],
                    "error": "trial killed (hung in 49-min wall-clock cap)",
                })

    pid_order = {pid: i for i, pid in enumerate(EXPENSIVE_PIDS)}
    rows.sort(key=lambda r: (r["model"], pid_order.get(r["problem_id"], 99)))
    full_records.sort(key=lambda r: (r["model"], pid_order.get(r["problem_id"], 99)))

    cols = list(rows[0].keys())
    with open(OUT_EXP / "trials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows: w.writerow(r)
    with open(OUT_EXP / "trials.jsonl", "w", encoding="utf-8") as f:
        for r in full_records: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        for r in rows:
            if r["error"] and not any(fr["model"]==r["model"] and fr["problem_id"]==r["problem_id"] for fr in full_records):
                f.write(json.dumps({**r, "final_solution": None, "reasoning_text": None}, ensure_ascii=False) + "\n")

    print(f"  Wrote {len(rows)} rows to {OUT_EXP}/trials.csv")
    return rows

print("\n=== Expensive-models 12-problem dataset ===")
exp_rows    = build_expensive_12()
exp_summary = summarize_trials(exp_rows)
with open(OUT_EXP / "summary.csv", "w", newline="", encoding="utf-8") as f:
    cols = list(exp_summary[0].keys())
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in exp_summary: w.writerow(r)
print(f"  Wrote {len(exp_summary)} summary rows to {OUT_EXP}/summary.csv")

# ============================================================================
# Stash pricing snapshot for traceability
# ============================================================================

with open(OUT_AB / "pricing_snapshot.json", "w") as f:
    json.dump({"fetch_date_utc": PRICING_FETCH_DATE, "prices": PRICES}, f, indent=2)
with open(OUT_EXP / "pricing_snapshot.json", "w") as f:
    json.dump({"fetch_date_utc": PRICING_FETCH_DATE, "prices": PRICES}, f, indent=2)

print("\n=== Done. Run dictionary/report writer next. ===")
