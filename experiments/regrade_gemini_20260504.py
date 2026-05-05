#!/usr/bin/env python3
"""
Re-grade ALL trials in mid-difficulty problems (3-15 of 18 passes under v4-pro)
using gemini-3-flash-preview as judge. Same `judge_gt.md` prompt as Phase 1.

Crash-safe: per-trial regrade JSON written to disk on completion. Resume by
re-running — `already_done` skips trials with an existing non-error regrade.

Output:
- Per-trial regrade JSONs at: experiments/results/regrade_gemini_20260504_<run_id>/<mode>/<model>/<pid>.json
- Summary JSON at end + console table.

Usage:
    uv run experiments/regrade_gemini_20260504.py --mock
    uv run experiments/regrade_gemini_20260504.py [--max-cost 30]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import itertools
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
PHASE1_RUN_DIR = RESULTS_DIR / "seed_ideas_full_compare_20260504_20260504_101225"

GEMINI_JUDGE = "openrouter/google/gemini-3-flash-preview"
GEMINI_PRICE = 3.00
V4PRO_JUDGE  = "openrouter/deepseek/deepseek-v4-pro"

PASS_RATE_LOW  = 3 / 18
PASS_RATE_HIGH = 15 / 18
MAX_TOKENS_JUDGE = 65536
MAX_WORKERS    = 50
LITELLM_TIMEOUT = 600

MODELS_ORD = [
    "openrouter/openai/gpt-oss-120b",
    "openrouter/google/gemma-4-31b-it",
    "openrouter/google/gemini-3-flash-preview",
    "openrouter/deepseek/deepseek-v4-flash",
    "openrouter/deepseek/deepseek-v4-pro",
    "openrouter/qwen/qwen3.6-35b-a3b",
]


def _ts():  return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# --- Key rotation (same pattern as Phase 1 with live-key filter) ---
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
            if not r.ok: live.append(k); continue
            d = r.json().get("data", {}) or {}
            limit = d.get("limit"); usage = d.get("usage", 0) or 0
            if limit is not None and usage >= limit:
                print(f"[startup] key#{i}: EXHAUSTED ({usage:.2f}/{limit})")
            else:
                rem = (limit - usage) if limit else "unlimited"
                print(f"[startup] key#{i}: live (usage={usage:.2f}/{limit}, remain={rem})")
                live.append(k)
        except Exception as e:
            print(f"[startup] key#{i}: probe failed ({e}), including")
            live.append(k)
    return live


KEYS = _filter_live_keys(_ALL_KEYS)
if not KEYS: raise SystemExit("No live keys")

_key_iter = itertools.cycle(KEYS)
_key_lock = threading.Lock()
def next_key():
    with _key_lock: return next(_key_iter)


# --- Cost tracker w/ killswitch ---
class CostTracker:
    def __init__(self, max_cost):
        self.max_cost = max_cost
        self._cost = 0.0
        self._lock = threading.Lock()
        self._aborted = False

    def add(self, c):
        with self._lock:
            self._cost += c
            if self.max_cost and self._cost >= self.max_cost and not self._aborted:
                self._aborted = True
                print(f"[{_ts()}] [KILLSWITCH] cum=${self._cost:.2f} >= ${self.max_cost:.2f}", flush=True)

    def aborted(self):
        with self._lock: return self._aborted

    def snapshot(self):
        with self._lock: return self._cost


def call_judge(prompt, retries=2, backoff=4.0):
    last_err = None
    for attempt in range(retries + 1):
        key = next_key()
        try:
            resp = litellm.completion(
                model=GEMINI_JUDGE,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS_JUDGE,
                api_key=key, timeout=LITELLM_TIMEOUT,
            )
            content = resp.choices[0].message.content  # type: ignore
            if content is None:
                content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
            if content is None:
                raise ValueError("Gemini returned None content")
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
                print(f"[{_ts()}] [retry] gemini failed: {e} — retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err


def parse_score(text):
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text or "", re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text or "", re.I)
    if m: return int(m.group(1))
    classif = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif.items():
        if f"CLASSIFICATION: {label}" in (text or ""):
            return score
    return 0


# --- Eligibility filter ---
def find_eligible_problems(trials):
    pass_rate = defaultdict(lambda: {"n": 0, "pass": 0})
    for t in trials:
        if t.get("error") or t.get("score") is None: continue
        pr = pass_rate[t["problem_id"]]
        pr["n"] += 1
        pr["pass"] += int(t["score"] >= 6)
    eligible = {pid for pid, pr in pass_rate.items()
                if pr["n"] >= 12
                and PASS_RATE_LOW <= (pr["pass"] / pr["n"]) <= PASS_RATE_HIGH}
    return eligible, pass_rate


def load_phase1_trials():
    out = []
    for p in PHASE1_RUN_DIR.rglob("*.json"):
        if p.parent == PHASE1_RUN_DIR: continue
        try:
            t = json.load(open(p))
            if t.get("error") or t.get("score") is None or not t.get("best_solution"):
                continue
            t["__path"] = str(p)
            out.append(t)
        except Exception:
            pass
    return out


# --- Per-trial save ---
def regrade_path(run_dir, mode, model, pid):
    return run_dir / mode / model.split("/")[-1] / f"{pid}.json"


def already_done(run_dir, mode, model, pid):
    p = regrade_path(run_dir, mode, model, pid)
    if not p.exists(): return False
    try:
        with open(p) as f: t = json.load(f)
        return not t.get("error") and t.get("gemini_score") is not None
    except Exception:
        return False


def save_regrade(run_dir, lock, rec):
    p = regrade_path(run_dir, rec["mode"], rec["model"], rec["problem_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    summary = {k: rec[k] for k in ("mode","model","problem_id","v4pro_score","gemini_score","cost_usd","elapsed_s","error") if k in rec}
    with lock:
        with open(run_dir / "manifest.jsonl", "a") as f:
            f.write(json.dumps(summary) + "\n")


# --- Worker ---
def regrade_one(t, problems, judge_template, run_dir, lock, tracker, mock):
    pid = t["problem_id"]
    prob = problems[pid]
    rec = {
        "phase1_path":  t["__path"],
        "problem_id":   pid,
        "mode":         t["mode"],
        "model":        t["model"],
        "v4pro_score":  t["score"],
        "v4pro_judge":  V4PRO_JUDGE,
        "gemini_judge": GEMINI_JUDGE,
    }
    if mock:
        rec.update({"gemini_score": 7, "gemini_verdict": "<points>7 out of 7</points> mock",
                    "gemini_usage": {"prompt_tokens":100,"completion_tokens":30,"total_tokens":130},
                    "cost_usd": 0.0, "elapsed_s": 0.01})
        save_regrade(run_dir, lock, rec); return rec

    prompt = (judge_template
              .replace("{problem}",      prob["text"])
              .replace("{ground_truth}", prob["ground_truth"])
              .replace("{candidate}",    t["best_solution"]))
    t0 = time.time()
    try:
        verdict, usage = call_judge(prompt)
        score = parse_score(verdict)
        elapsed = round(time.time()-t0, 2)
        cost = round(GEMINI_PRICE * usage["total_tokens"] / 1_000_000, 6)
        tracker.add(cost)
        rec.update({"gemini_score": score, "gemini_verdict": verdict,
                    "gemini_usage": usage, "cost_usd": cost, "elapsed_s": elapsed})
        delta = score - t["score"]
        print(f"[{_ts()}] {pid:<28} {t['mode']:<14} {t['model'].split('/')[-1]:<24}  "
              f"v4pro={t['score']}  gemini={score}  Δ={delta:+}  ${cost:.4f}  {elapsed}s", flush=True)
    except Exception as e:
        elapsed = round(time.time()-t0, 2)
        rec.update({"gemini_score": None, "error": str(e), "cost_usd": 0.0, "elapsed_s": elapsed})
        print(f"[{_ts()}] FAILED {pid}|{t['mode']}|{t['model'].split('/')[-1]}: {e}", flush=True)
    save_regrade(run_dir, lock, rec)
    return rec


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--max-cost", type=float, default=None)
    p.add_argument("--all-trials", action="store_true",
                   help="Judge ALL Phase 1 trials, ignoring the mid-range filter.")
    p.add_argument("--from-run-id", default=None,
                   help="Reuse an existing regrade run dir (resume + skip already-done).")
    args = p.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()

    # Load Phase 1 trials and filter problems
    print(f"Loading Phase 1 trials from {PHASE1_RUN_DIR}…")
    trials = load_phase1_trials()
    print(f"  {len(trials)} successful trials loaded")

    eligible, pass_rate = find_eligible_problems(trials)
    if args.all_trials:
        print(f"\n[--all-trials] judging ALL {len(trials)} trials (ignoring mid-range filter).")
        trials_to_judge = trials
    else:
        print(f"\nEligible problems (3-15 of 18 passes): {len(eligible)}/{len(pass_rate)}")
        for pid in sorted(eligible):
            pr = pass_rate[pid]
            rate = pr["pass"]/pr["n"]
            print(f"  ✓ {pid:<32} n={pr['n']:<3} pass={pr['pass']:<3} rate={rate:.2f}")
        trials_to_judge = [t for t in trials if t["problem_id"] in eligible]
        print(f"\nTrials to re-judge: {len(trials_to_judge)}")

    # Load problems
    from problemset_70 import load_70_problems
    problems = load_70_problems()

    # Run dir — reuse if specified
    if args.from_run_id:
        run_id = args.from_run_id
        run_dir = RESULTS_DIR / f"regrade_gemini_20260504_{run_id}{'_mock' if args.mock else ''}"
        if not run_dir.exists():
            raise SystemExit(f"--from-run-id given but {run_dir} does not exist")
        print(f"Reusing run dir: {run_dir}")
    else:
        run_id = _now()
        run_dir = RESULTS_DIR / f"regrade_gemini_20260504_{run_id}{'_mock' if args.mock else ''}"
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"Run dir: {run_dir}\n")

    # Skip already-done
    pending = [t for t in trials_to_judge if not already_done(run_dir, t["mode"], t["model"], t["problem_id"])]
    print(f"Pending: {len(pending)} (skipping {len(trials_to_judge)-len(pending)} already done)")

    tracker = CostTracker(args.max_cost)
    lock = threading.Lock()

    t0 = time.time()
    results = []
    completed = 0
    last_print = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for t in pending:
            if tracker.aborted():
                print(f"[{_ts()}] killswitch — stop submitting"); break
            futs[ex.submit(regrade_one, t, problems, judge_template, run_dir, lock, tracker, args.mock)] = t
        for fut in concurrent.futures.as_completed(futs, timeout=LITELLM_TIMEOUT * len(pending)):
            completed += 1
            try:
                results.append(fut.result(timeout=LITELLM_TIMEOUT))
            except Exception as e:
                print(f"[{_ts()}] outer FAILED: {e}", flush=True)
            if time.time() - last_print > 30:
                print(f"[{_ts()}] Progress: {completed}/{len(pending)}  cum=${tracker.snapshot():.2f}", flush=True)
                last_print = time.time()
    elapsed = round(time.time()-t0, 1)

    # ---- Summary: per-mode × model under both judges ----
    # Re-load all per-trial regrade files (including resumed ones)
    all_records = []
    for q in run_dir.rglob("*.json"):
        if q.parent == run_dir: continue
        try: all_records.append(json.load(open(q)))
        except Exception: pass

    print(f"\n{'='*100}")
    print(f"GEMINI RE-GRADE — eligible mid-range problems only")
    print(f"  records: {len(all_records)}    cost: ${tracker.snapshot():.2f}    wall: {elapsed}s")
    print(f"{'='*100}\n")

    # Per-mode summary
    by_mm = defaultdict(lambda: {"v4": [], "gem": []})
    for r in all_records:
        if r.get("error") or r.get("gemini_score") is None: continue
        by_mm[(r["mode"], r["model"])]["v4"].append(r["v4pro_score"])
        by_mm[(r["mode"], r["model"])]["gem"].append(r["gemini_score"])

    for mode in ("generate","full","seed_generate"):
        print(f"\n--- {mode} ---")
        print(f"  {'Model':<28}  {'n':>3}  {'v4 mean':>8}  {'gem mean':>9}  {'Δ':>6}  {'v4 pass':>8}  {'gem pass':>9}")
        for m in MODELS_ORD:
            d = by_mm.get((mode, m))
            if not d or not d["v4"]: continue
            v4 = d["v4"]; gm = d["gem"]
            v4_mean = sum(v4)/len(v4)
            gm_mean = sum(gm)/len(gm)
            v4_pass = sum(1 for s in v4 if s>=6)
            gm_pass = sum(1 for s in gm if s>=6)
            print(f"  {m.split('/')[-1]:<28}  {len(v4):>3}  "
                  f"{v4_mean:>8.2f}  {gm_mean:>9.2f}  {gm_mean-v4_mean:>+6.2f}  "
                  f"{v4_pass}/{len(v4):<5}  {gm_pass}/{len(gm)}")

    # Mode-level aggregate (across all models)
    print(f"\n=== Mode-level aggregate ===")
    print(f"  {'Mode':<16}  {'n':>4}  {'v4 mean':>8}  {'gem mean':>9}  {'Δ':>6}")
    for mode in ("generate","full","seed_generate"):
        v4s, gms = [], []
        for m in MODELS_ORD:
            d = by_mm.get((mode, m))
            if d:
                v4s += d["v4"]; gms += d["gem"]
        if v4s:
            print(f"  {mode:<14}  {len(v4s):>4}  "
                  f"{sum(v4s)/len(v4s):>8.2f}  {sum(gms)/len(gms):>9.2f}  {sum(gms)/len(gms)-sum(v4s)/len(v4s):>+6.2f}")

    # Save final summary
    out = run_dir / "summary.json"
    with open(out, "w") as f:
        json.dump({
            "experiment": "regrade_gemini_20260504",
            "run_id": run_id,
            "v4pro_judge": V4PRO_JUDGE,
            "gemini_judge": GEMINI_JUDGE,
            "n_eligible_problems": len(eligible),
            "n_records": len(all_records),
            "total_cost_usd": round(tracker.snapshot(), 2),
            "wall_clock_s": elapsed,
            "by_mode_model": {
                f"{mode}|{m.split('/')[-1]}": {
                    "n":         len(by_mm[(mode,m)]["v4"]),
                    "v4_mean":   round(sum(by_mm[(mode,m)]["v4"])/len(by_mm[(mode,m)]["v4"]), 3) if by_mm.get((mode,m),{}).get("v4") else None,
                    "gem_mean":  round(sum(by_mm[(mode,m)]["gem"])/len(by_mm[(mode,m)]["gem"]), 3) if by_mm.get((mode,m),{}).get("gem") else None,
                }
                for mode in ("generate","full","seed_generate") for m in MODELS_ORD
                if by_mm.get((mode,m),{}).get("v4")
            },
        }, f, indent=2)
    print(f"\nSaved summary: {out}")


if __name__ == "__main__":
    main()
