#!/usr/bin/env python3
"""
Per-branch gemini regrade for generate and seed_generate modes.

Phase 1 stored 3 branches per (model, problem) in those modes. The earlier
`regrade_gemini` only judged the v4-pro-best pick (best_solution). To compute
TRUE gemini pass@1 (k=0) and pass@3 (best of 3 under gemini), we need each
branch judged.

This script judges every branch in `generate` and `seed_generate`, saving
per-(mode, model, pid, k) JSONs. Reuses `judge_gt.md` and the same key-rotation
infra. Crash-safe and resumable via already_done.

Usage:
    uv run experiments/regrade_branches_gemini_20260504.py --mock
    uv run experiments/regrade_branches_gemini_20260504.py [--max-cost 80] [--from-run-id <id>]
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
MAX_TOKENS_JUDGE = 65536
MAX_WORKERS = 50
LITELLM_TIMEOUT = 600

MODES = ("generate", "seed_generate")  # full mode has only 1 branch — covered by regrade_gemini
NUM_BRANCHES = 3
PASS1_ONLY = False  # if True, judge only k=0 in generate mode (for pass@1 column)

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


load_dotenv()
_ALL_KEYS = [k for k in [os.getenv("OPENROUTER_API_KEY"),
                          os.getenv("OPENROUTER_API_KEY_X"),
                          os.getenv("OPENROUTER_API_KEY_X2")] if k]


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
            print(f"[startup] key#{i}: probe failed ({e})"); live.append(k)
    return live


KEYS = _filter_live_keys(_ALL_KEYS)
if not KEYS: raise SystemExit("No live keys")

_key_iter = itertools.cycle(KEYS)
_key_lock = threading.Lock()
def next_key():
    with _key_lock: return next(_key_iter)


class CostTracker:
    def __init__(self, mc): self.max_cost=mc; self._c=0; self._l=threading.Lock(); self._a=False
    def add(self, c):
        with self._l:
            self._c += c
            if self.max_cost and self._c >= self.max_cost and not self._a:
                self._a = True
                print(f"[{_ts()}] [KILLSWITCH] cum=${self._c:.2f}", flush=True)
    def aborted(self):
        with self._l: return self._a
    def snapshot(self):
        with self._l: return self._c


def call_judge(prompt, retries=2, backoff=4.0):
    last = None
    for att in range(retries + 1):
        key = next_key()
        try:
            resp = litellm.completion(
                model=GEMINI_JUDGE,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS_JUDGE, api_key=key, timeout=LITELLM_TIMEOUT,
            )
            content = resp.choices[0].message.content  # type: ignore
            if content is None:
                content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
            if content is None: raise ValueError("None content")
            usage = getattr(resp, "usage", None)
            return content, {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
            }
        except Exception as e:
            last = e; msg = str(e)
            if "402" in msg or "Insufficient credits" in msg or "Key limit exceeded" in msg or '"code":403' in msg:
                raise
            if att < retries:
                time.sleep(backoff * (2 ** att))
    raise last


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


def load_phase1_branches():
    """Yield (mode, model, pid, k, solution_text, v4_score) for every branch in
    generate / seed_generate modes. If PASS1_ONLY, restrict to generate k=0."""
    out = []
    for mode in MODES:
        if PASS1_ONLY and mode != "generate":
            continue
        for p in (PHASE1_RUN_DIR / mode).rglob("*.json"):
            try: t = json.load(open(p))
            except: continue
            if t.get("error") or not t.get("branches"): continue
            for b in t["branches"]:
                k = b.get("k") if "k" in b else b.get("idea_idx")
                if k is None: continue
                if PASS1_ONLY and int(k) != 0:
                    continue
                sol = b.get("solution")
                if not sol: continue
                v4 = b.get("score")
                if v4 is None: continue
                out.append({
                    "mode":     mode,
                    "model":    t["model"],
                    "pid":      t["problem_id"],
                    "k":        int(k),
                    "solution": sol,
                    "v4_score": v4,
                })
    return out


def regrade_path(run_dir, mode, model, pid, k):
    return run_dir / mode / model.split("/")[-1] / f"{pid}__k{k}.json"


def already_done(run_dir, mode, model, pid, k):
    p = regrade_path(run_dir, mode, model, pid, k)
    if not p.exists(): return False
    try:
        with open(p) as f: t = json.load(f)
        return not t.get("error") and t.get("gemini_score") is not None
    except Exception: return False


def regrade_one(rec, problems, judge_template, run_dir, lock, tracker, mock):
    pid = rec["pid"]; mode = rec["mode"]; model = rec["model"]; k = rec["k"]
    prob = problems[pid]
    out = {
        "mode":         mode,
        "model":        model,
        "problem_id":   pid,
        "k":            k,
        "v4_score":     rec["v4_score"],
        "gemini_judge": GEMINI_JUDGE,
    }
    if mock:
        out.update({"gemini_score": 7, "gemini_verdict": "<points>7 out of 7</points>",
                    "cost_usd": 0.0, "elapsed_s": 0.01})
        save(run_dir, lock, out); return out

    prompt = (judge_template
              .replace("{problem}",      prob["text"])
              .replace("{ground_truth}", prob["ground_truth"])
              .replace("{candidate}",    rec["solution"]))
    t0 = time.time()
    try:
        verdict, usage = call_judge(prompt)
        score = parse_score(verdict)
        elapsed = round(time.time()-t0, 2)
        cost = round(GEMINI_PRICE * usage["total_tokens"] / 1_000_000, 6)
        tracker.add(cost)
        out.update({"gemini_score": score, "gemini_verdict": verdict,
                    "gemini_usage": usage, "cost_usd": cost, "elapsed_s": elapsed})
        delta = score - rec["v4_score"]
        print(f"[{_ts()}] {pid:<28} {mode:<14} {model.split('/')[-1]:<24} k={k}  "
              f"v4={rec['v4_score']}  gem={score}  Δ={delta:+}  ${cost:.4f}", flush=True)
    except Exception as e:
        elapsed = round(time.time()-t0, 2)
        out.update({"gemini_score": None, "error": str(e), "cost_usd": 0.0, "elapsed_s": elapsed})
        print(f"[{_ts()}] FAILED {pid}|{mode}|{model.split('/')[-1]} k={k}: {e}", flush=True)
    save(run_dir, lock, out)
    return out


def save(run_dir, lock, rec):
    p = regrade_path(run_dir, rec["mode"], rec["model"], rec["problem_id"], rec["k"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    summary = {k: rec[k] for k in ("mode","model","problem_id","k","v4_score","gemini_score","cost_usd","error") if k in rec}
    with lock:
        with open(run_dir / "manifest.jsonl", "a") as f:
            f.write(json.dumps(summary) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--max-cost", type=float, default=None)
    p.add_argument("--from-run-id", default=None)
    args = p.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()
    branches = load_phase1_branches()
    print(f"\n{len(branches)} branches to potentially regrade")

    if args.from_run_id:
        run_id = args.from_run_id
        run_dir = RESULTS_DIR / f"regrade_branches_gemini_20260504_{run_id}{'_mock' if args.mock else ''}"
        if not run_dir.exists():
            raise SystemExit(f"--from-run-id given but {run_dir} does not exist")
    else:
        run_id = _now()
        run_dir = RESULTS_DIR / f"regrade_branches_gemini_20260504_{run_id}{'_mock' if args.mock else ''}"
        run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run dir: {run_dir}")

    pending = [b for b in branches if not already_done(run_dir, b["mode"], b["model"], b["pid"], b["k"])]
    print(f"Pending: {len(pending)} (skipping {len(branches)-len(pending)} already done)\n")

    from problemset_70 import load_70_problems
    problems = load_70_problems()

    tracker = CostTracker(args.max_cost)
    lock = threading.Lock()

    t0 = time.time()
    completed = 0
    last_print = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for b in pending:
            if tracker.aborted(): break
            futs[ex.submit(regrade_one, b, problems, judge_template, run_dir, lock, tracker, args.mock)] = b
        for fut in concurrent.futures.as_completed(futs, timeout=LITELLM_TIMEOUT * len(pending)):
            completed += 1
            try: fut.result(timeout=LITELLM_TIMEOUT)
            except Exception as e:
                print(f"[{_ts()}] outer FAILED: {e}", flush=True)
            if time.time() - last_print > 30:
                print(f"[{_ts()}] Progress: {completed}/{len(pending)}  cum=${tracker.snapshot():.2f}", flush=True)
                last_print = time.time()
    elapsed = round(time.time()-t0, 1)

    print(f"\nWall: {elapsed}s    Cost: ${tracker.snapshot():.2f}")
    print(f"Branch-regrade dir: {run_dir}")


if __name__ == "__main__":
    main()
