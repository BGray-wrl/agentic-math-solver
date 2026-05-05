#!/usr/bin/env python3
"""
Judge ablation: re-judge 100 random trials from the seed_ideas Phase 1 run with
gemini-3-flash-preview, and compare scores to the deepseek-v4-pro judge already
on disk.

Sampling rules:
- 100 trials, random.seed(42), drawn from all (model, mode, problem) triples
- Stratified by problem-informativeness: only problems where 3-15 of the 18 trials
  scored ≥6/7 (i.e. roughly 17-83% pass rate). Drops problems where nearly all
  models passed or nearly all failed — those are uninformative for judge comparison.

Output: a side-by-side table of the two judges' scores, plus disagreement stats.

Usage:
    uv run experiments/judge_ablation_20260504.py
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

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

# Reuse the same judge prompt the original run used.
ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"

PHASE1_RUN_DIR = RESULTS_DIR / "seed_ideas_full_compare_20260504_20260504_101225"

GEMINI_JUDGE = "openrouter/google/gemini-3-flash-preview"
GEMINI_PRICE = 3.00  # $/M tokens
DEEPSEEK_JUDGE = "openrouter/deepseek/deepseek-v4-pro"
DEEPSEEK_PRICE = 0.87

N_TRIALS = 100
SEED = 42

PASS_RATE_LOW  = 3 / 18      # ≥ 3 of 18 passed (>16.7%)
PASS_RATE_HIGH = 15 / 18     # ≤ 15 of 18 passed (<83.3%)

MAX_TOKENS_JUDGE = 65536
MAX_WORKERS = 30
LITELLM_TIMEOUT = 600

# ----------------------------------------------------------------------------

load_dotenv()
_ALL_KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_X2"),
] if k]


def _filter_live_keys(keys):
    import requests
    live = []
    for i, k in enumerate(keys):
        try:
            r = requests.get("https://openrouter.ai/api/v1/key",
                             headers={"Authorization": f"Bearer {k}"}, timeout=8)
            if not r.ok:
                live.append(k); continue
            d = r.json().get("data", {}) or {}
            limit = d.get("limit"); usage = d.get("usage", 0) or 0
            if limit is not None and usage >= limit:
                print(f"[startup] key#{i}: EXHAUSTED ({usage:.2f}/{limit}) — dropped")
            else:
                rem = (limit - usage) if limit else "unlimited"
                print(f"[startup] key#{i}: live (usage={usage:.2f}/{limit}, remain={rem})")
                live.append(k)
        except Exception as e:
            print(f"[startup] key#{i}: probe failed ({e}), including anyway")
            live.append(k)
    return live


KEYS = _filter_live_keys(_ALL_KEYS)
if not KEYS:
    raise SystemExit("No live keys")

_key_iter = itertools.cycle(KEYS)
_key_lock = threading.Lock()
def next_key():
    with _key_lock: return next(_key_iter)


def _ts(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def call_judge(prompt: str, retries: int = 2, backoff: float = 4.0):
    last_err = None
    for attempt in range(retries + 1):
        key = next_key()
        try:
            resp = litellm.completion(
                model=GEMINI_JUDGE,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS_JUDGE,
                api_key=key,
                timeout=LITELLM_TIMEOUT,
            )
            content = resp.choices[0].message.content  # type: ignore
            if content is None:
                content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
            if content is None:
                raise ValueError(f"Gemini returned None content")
            usage = getattr(resp, "usage", None)
            return content, {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
            }
        except Exception as e:
            last_err = e
            msg = str(e)
            if "402" in msg or "Insufficient credits" in msg or "Key limit exceeded" in msg or '"code":403' in msg:
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] gemini attempt {attempt+1} failed: {e} — retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err


def parse_score(verdict_text: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict_text or "", re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict_text or "", re.I)
    if m: return int(m.group(1))
    classif = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif.items():
        if f"CLASSIFICATION: {label}" in (verdict_text or ""):
            return score
    return 0


# ----------------------------------------------------------------------------

def load_trials() -> list[dict]:
    """Load all per-trial JSONs from the Phase 1 run dir."""
    trials = []
    for p in PHASE1_RUN_DIR.rglob("*.json"):
        if p.parent == PHASE1_RUN_DIR:
            continue
        try:
            t = json.load(open(p))
            if t.get("error") or t.get("score") is None or not t.get("best_solution"):
                continue
            # Inject the source path for traceability
            t["__path"] = str(p)
            trials.append(t)
        except Exception:
            pass
    return trials


def filter_informative(trials: list[dict]) -> list[dict]:
    """Keep only trials whose problem has a mid-range pass rate."""
    from collections import defaultdict
    pass_rate = defaultdict(lambda: {"n": 0, "pass": 0})
    for t in trials:
        pr = pass_rate[t["problem_id"]]
        pr["n"] += 1
        pr["pass"] += int(t["score"] >= 6)
    eligible = {pid for pid, pr in pass_rate.items()
                if pr["n"] >= 12  # need decent coverage to assess pass rate
                and PASS_RATE_LOW <= (pr["pass"] / pr["n"]) <= PASS_RATE_HIGH}
    print(f"\nProblem-pass-rate filter:")
    for pid, pr in sorted(pass_rate.items()):
        rate = pr["pass"] / pr["n"] if pr["n"] else 0
        flag = "✓ keep" if pid in eligible else "✗ drop"
        print(f"  {pid:<32}  n={pr['n']:<3}  pass={pr['pass']:<3}  rate={rate:.2f}  {flag}")
    keep = [t for t in trials if t["problem_id"] in eligible]
    print(f"\n  Eligible problems: {len(eligible)}/{len(pass_rate)}")
    print(f"  Eligible trials:   {len(keep)}/{len(trials)}")
    return keep


def sample_trials(trials: list[dict], n: int) -> list[dict]:
    rng = random.Random(SEED)
    return rng.sample(trials, min(n, len(trials)))


# ----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=N_TRIALS)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    judge_prompt_template = (PROMPTS_DIR / "judge_gt.md").read_text()

    print(f"Loading trials from {PHASE1_RUN_DIR}…")
    all_trials = load_trials()
    print(f"  loaded {len(all_trials)} successful trials")

    eligible = filter_informative(all_trials)
    sample = sample_trials(eligible, args.n)
    print(f"\nSampled {len(sample)} trials (seed={SEED})\n")

    # Brief sample preview
    print(f"Sample preview (first 5):")
    for t in sample[:5]:
        print(f"  {t['problem_id']:<28}  {t['mode']:<14}  {t['model'].split('/')[-1]:<24}  "
              f"v4pro={t['score']}  cand_len={len(t.get('best_solution',''))}")
    print()

    # Re-judge each with gemini
    print(f"Re-judging with {GEMINI_JUDGE} ({MAX_WORKERS} workers)…\n")

    out_lock = threading.Lock()
    results = []

    def _judge(t):
        prompt = (judge_prompt_template
                  .replace("{problem}",      t.get("text") or "")
                  .replace("{ground_truth}", "")  # filled below
                  .replace("{candidate}",    t["best_solution"] or ""))
        # We don't have problem text or GT in the trial; rebuild from problemset_70
        # (each trial JSON only has problem_id and best_solution). Fix at top.
        return None

    # Need problem text and GT — load from problemset_70.
    from problemset_70 import load_70_problems
    problems = load_70_problems()

    def _judge_real(t):
        pid = t["problem_id"]
        prob = problems[pid]
        prompt = (judge_prompt_template
                  .replace("{problem}",      prob["text"])
                  .replace("{ground_truth}", prob["ground_truth"])
                  .replace("{candidate}",    t["best_solution"] or ""))
        if args.mock:
            return {
                "trial_path":  t["__path"],
                "problem_id":  pid,
                "mode":        t["mode"],
                "model":       t["model"],
                "v4pro_score": t["score"],
                "gemini_score": 7,
                "gemini_verdict": "<points>7 out of 7</points> mock",
                "gemini_usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
                "elapsed_s":   0.01,
                "cost_usd":    0.0,
            }
        t0 = time.time()
        try:
            verdict, usage = call_judge(prompt)
            score = parse_score(verdict)
            elapsed = round(time.time()-t0, 2)
            cost = round(GEMINI_PRICE * usage["total_tokens"] / 1_000_000, 6)
            tag = f"[{_ts()}] {pid:<28} {t['mode']:<14} {t['model'].split('/')[-1]:<24}"
            print(f"{tag}  v4pro={t['score']}  gemini={score}  Δ={score - t['score']:+}  ${cost:.4f}  {elapsed}s", flush=True)
            return {
                "trial_path":   t["__path"],
                "problem_id":   pid,
                "mode":         t["mode"],
                "model":        t["model"],
                "v4pro_score":  t["score"],
                "gemini_score": score,
                "gemini_verdict": verdict,
                "gemini_usage": usage,
                "elapsed_s":    elapsed,
                "cost_usd":     cost,
            }
        except Exception as e:
            elapsed = round(time.time()-t0, 2)
            print(f"[{_ts()}] FAILED {pid}|{t['mode']}: {e}", flush=True)
            return {
                "trial_path":   t["__path"],
                "problem_id":   pid,
                "mode":         t["mode"],
                "model":        t["model"],
                "v4pro_score":  t["score"],
                "gemini_score": None,
                "error":        str(e),
                "elapsed_s":    elapsed,
                "cost_usd":     0.0,
            }

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(_judge_real, t) for t in sample]
        for fut in concurrent.futures.as_completed(futs, timeout=LITELLM_TIMEOUT * len(sample)):
            try:
                results.append(fut.result(timeout=LITELLM_TIMEOUT))
            except Exception as e:
                print(f"[{_ts()}] outer FAILED: {e}", flush=True)

    elapsed_total = round(time.time()-t0, 1)
    total_cost = sum(r["cost_usd"] for r in results)
    valid = [r for r in results if r.get("gemini_score") is not None]
    n_err = sum(1 for r in results if r.get("error"))

    # ---- Stats ----
    print(f"\n{'='*100}")
    print(f"JUDGE ABLATION — gemini-3-flash vs deepseek-v4-pro (n={len(valid)} valid, {n_err} errors)")
    print(f"Wall-clock: {elapsed_total}s    Total cost: ${total_cost:.2f}")
    print(f"{'='*100}\n")

    # Score distribution shifts
    import statistics as st
    v4_scores = [r["v4pro_score"] for r in valid]
    gem_scores = [r["gemini_score"] for r in valid]
    deltas = [g - v for g, v in zip(gem_scores, v4_scores)]
    abs_dev = [abs(d) for d in deltas]
    print(f"v4pro mean:    {st.mean(v4_scores):.2f}")
    print(f"gemini mean:   {st.mean(gem_scores):.2f}")
    print(f"mean Δ:        {st.mean(deltas):+.2f}  (positive = gemini scored higher)")
    print(f"mean |Δ|:      {st.mean(abs_dev):.2f}")
    print(f"agreement (Δ=0): {sum(1 for d in deltas if d==0)}/{len(deltas)} = {100*sum(1 for d in deltas if d==0)/len(deltas):.1f}%")
    print(f"close   (|Δ|≤1): {sum(1 for d in abs_dev if d<=1)}/{len(abs_dev)} = {100*sum(1 for d in abs_dev if d<=1)/len(abs_dev):.1f}%")
    print(f"big     (|Δ|≥6): {sum(1 for d in abs_dev if d>=6)}")

    # Confusion-style cross-tab — pass/fail under each judge (≥6 = pass)
    v_pass = [s>=6 for s in v4_scores]
    g_pass = [s>=6 for s in gem_scores]
    tt = sum(1 for vv, gg in zip(v_pass, g_pass) if vv and gg)
    tf = sum(1 for vv, gg in zip(v_pass, g_pass) if vv and not gg)
    ft = sum(1 for vv, gg in zip(v_pass, g_pass) if not vv and gg)
    ff = sum(1 for vv, gg in zip(v_pass, g_pass) if not vv and not gg)
    print(f"\nPass/Fail confusion (rows=v4pro, cols=gemini):")
    print(f"           gemini-pass   gemini-fail")
    print(f"v4pro-pass    {tt:>6}        {tf:>6}")
    print(f"v4pro-fail    {ft:>6}        {ff:>6}")
    print(f"agreement-on-pass: {(tt+ff)/len(valid)*100:.1f}%  flips: {(tf+ft)} ({(tf+ft)/len(valid)*100:.1f}%)")

    # Top disagreements (largest |Δ|)
    print(f"\nTop 10 disagreements (sorted by |Δ|):")
    by_delta = sorted(valid, key=lambda r: -abs(r["gemini_score"] - r["v4pro_score"]))
    for r in by_delta[:10]:
        print(f"  {r['problem_id']:<28} {r['mode']:<14} {r['model'].split('/')[-1]:<24}  "
              f"v4pro={r['v4pro_score']}  gemini={r['gemini_score']}  Δ={r['gemini_score']-r['v4pro_score']:+}")

    # ---- Save ----
    out_path = RESULTS_DIR / f"judge_ablation_{_now()}{'_mock' if args.mock else ''}.json"
    with open(out_path, "w") as f:
        json.dump({
            "experiment":        "judge_ablation_20260504",
            "date":              datetime.now(timezone.utc).isoformat(),
            "phase1_run":        str(PHASE1_RUN_DIR),
            "v4pro_judge":       DEEPSEEK_JUDGE,
            "gemini_judge":      GEMINI_JUDGE,
            "n_sampled":         len(sample),
            "n_valid":           len(valid),
            "n_errors":          n_err,
            "total_cost_usd":    round(total_cost, 4),
            "wall_clock_s":      elapsed_total,
            "filter":            {"pass_rate_low": PASS_RATE_LOW, "pass_rate_high": PASS_RATE_HIGH},
            "results":           results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
