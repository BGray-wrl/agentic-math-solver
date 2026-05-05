#!/usr/bin/env python3
"""
Composed pipeline: pass@N best-of-N → strong-critic V↔R loop.

Stage 1 (REUSES existing passN_v4flash_20260505 samples):
  For each problem, pick the BEST-scoring v4-flash sample under v4-flash judge.

Stage 2 (NEW):
  Apply v4-pro V↔R loop (ITER=2) to that best solution.
  Re-judge with v4-flash.

Hypothesis:
  Strong-critic (Exp 2, +0.95) and pass@N (Exp 3, +1.6 to pass@8) are complementary.
  Their composition should beat both individually. Predicted mean ~3.7-4.0.

Stages run as a single pipeline per problem (not parallelized over problems
because the v4-pro critique is the bottleneck and we want clean, sequential
spend tracking against the remaining flex budget).

Critically, Stage 2 v4-pro can ONLY HELP or HURT — it cannot exceed 7/7. So
this is a test of *does composition increase mean* with no asymmetric risk.

Usage:
  uv run experiments/composed_critic_passN_20260505.py --max-cost 5
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
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
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

EXPERIMENT_NAME = "composed_critic_passN_20260505"

PASSN_RUN_DIR = Path(__file__).parent / "results" / "passN_v4flash_20260505_20260505_120944"

CRITIC_MODEL = "openrouter/deepseek/deepseek-v4-pro"
JUDGE_MODEL  = "openrouter/deepseek/deepseek-v4-flash"

ITERATIONS   = 2
MAX_TOKENS_VERIFY  = 32768
MAX_TOKENS_REVISE  = 32768
MAX_TOKENS_JUDGE   = 32768

MAX_WORKERS  = 8
TRIAL_TIMEOUT = 3600
LITELLM_TIMEOUT = 1500

PASS_THRESHOLD = 6

PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"

PRICE = {
    "openrouter/deepseek/deepseek-v4-flash": 0.28,
    "openrouter/deepseek/deepseek-v4-pro":   0.87,
}


def _ts():    return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now_id(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


load_dotenv()
FLEX_KEY = os.getenv("OPENROUTER_API_KEY_flex")
if not FLEX_KEY:
    raise SystemExit("OPENROUTER_API_KEY_flex not set in .env")


def call_model(model, system, user, max_tokens, retries=2, backoff=5.0):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = litellm.completion(
                model=model, messages=messages, max_tokens=max_tokens,
                api_key=FLEX_KEY, timeout=LITELLM_TIMEOUT,
            )
            content = resp.choices[0].message.content  # type: ignore
            if content is None:
                content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
            if content is None:
                raise ValueError(f"{model}: None content")
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
            if "402" in msg or "Insufficient credits" in msg or '"code":403' in msg:
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model.split('/')[-1]} {attempt+1}: {e} -> {wait:.0f}s",
                      flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


class CostTracker:
    def __init__(self, cap):
        self.cap = cap
        self._cost = 0.0
        self._lock = threading.Lock()
        self._aborted = False

    def add(self, cost):
        with self._lock:
            self._cost += cost
            if self.cap and self._cost >= self.cap and not self._aborted:
                self._aborted = True
                print(f"[{_ts()}] [KILLSWITCH] ${self._cost:.2f} >= ${self.cap:.2f}", flush=True)

    def aborted(self):
        with self._lock:
            return self._aborted

    def snapshot(self):
        with self._lock:
            return self._cost


def cost_for(model, total_tokens):
    return PRICE.get(model, 0.5) * total_tokens / 1_000_000


def load_prompt(name): return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def parse_gt_score(verdict):
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m: return int(m.group(1))
    return 0


def load_passN_best(samples_dir):
    """Return {pid: {k, score, solution, problem_text, ground_truth}} of the best-judged sample."""
    out = {}
    # Need problem text & ground_truth — load fresh
    sys.path.insert(0, str(Path(__file__).parent))
    from problemset_70 import load_70_problems
    all_p = load_70_problems()

    for pdir in sorted(samples_dir.glob("*")):
        if not pdir.is_dir(): continue
        pid = pdir.name
        if pid not in all_p:
            print(f"[{_ts()}] WARN: pid {pid} not in problem set"); continue
        best = None
        for f in sorted(pdir.glob("k*.json")):
            with open(f) as fh:
                s = json.load(fh)
            if s.get("score") is None: continue
            if best is None or s["score"] > best["score"]:
                best = {
                    "pid": pid,
                    "k": s["k"],
                    "score": s["score"],
                    "solution": s["solution"],
                    "problem_text": all_p[pid]["text"],
                    "ground_truth": all_p[pid]["ground_truth"],
                }
        if best is not None:
            out[pid] = best
    return out


def do_verify(prompts, problem, solution):
    sys_part, sep, content_part = prompts["verifier"].partition("\n**PROBLEM:**\n")
    if not sep: sys_part = ""; content_part = prompts["verifier"]
    else:       content_part = "**PROBLEM:**\n" + content_part
    user = content_part.replace("{problem}", problem).replace("{solution}", solution)
    text, usage = call_model(CRITIC_MODEL, sys_part, user, MAX_TOKENS_VERIFY)
    return text, usage


def do_revise(prompts, problem, solution, critique):
    sys_part, sep, content_part = prompts["reviser"].partition("\n**PROBLEM:**\n")
    if not sep: sys_part = ""; content_part = prompts["reviser"]
    else:       content_part = "**PROBLEM:**\n" + content_part
    user = (content_part.replace("{problem}", problem)
                          .replace("{solution}", solution)
                          .replace("{critique}", critique))
    text, usage = call_model(CRITIC_MODEL, sys_part, user, MAX_TOKENS_REVISE)
    return text, usage


def do_judge(prompts, problem, candidate, ground_truth):
    user = (prompts["judge_gt"]
            .replace("{problem}", problem)
            .replace("{ground_truth}", ground_truth)
            .replace("{candidate}", candidate))
    text, usage = call_model(JUDGE_MODEL, "", user, MAX_TOKENS_JUDGE)
    return text, parse_gt_score(text), usage


def run_trial(starter, prompts, run_dir, manifest_lock, tracker):
    pid = starter["pid"]
    tag = f"[{_ts()}] [{pid}|k0={starter['k']}|s0={starter['score']}]"
    print(f"{tag} start", flush=True)
    t0 = time.time()
    calls = []
    try:
        solution = starter["solution"]
        loop_log = []
        stopped_early = False
        cost_cum = 0.0

        for i in range(ITERATIONS):
            critique, vu = do_verify(prompts, starter["problem_text"], solution)
            c1 = cost_for(CRITIC_MODEL, vu["total_tokens"])
            tracker.add(c1); cost_cum += c1
            calls.append({"kind": "verify", "model": CRITIC_MODEL, "usage": vu, "cost_usd": c1})
            if "VERDICT: correct" in critique:
                stopped_early = True
                loop_log.append({"iteration": i+1, "verdict": "correct",
                                 "critique": critique, "solution": solution})
                break
            new_sol, ru = do_revise(prompts, starter["problem_text"], solution, critique)
            c2 = cost_for(CRITIC_MODEL, ru["total_tokens"])
            tracker.add(c2); cost_cum += c2
            calls.append({"kind": "revise", "model": CRITIC_MODEL, "usage": ru, "cost_usd": c2})
            loop_log.append({"iteration": i+1, "verdict": "issues_found",
                             "critique": critique,
                             "solution_before": solution, "solution_after": new_sol})
            solution = new_sol

        verdict, score, ju = do_judge(prompts, starter["problem_text"], solution,
                                       starter["ground_truth"])
        c3 = cost_for(JUDGE_MODEL, ju["total_tokens"])
        tracker.add(c3); cost_cum += c3
        calls.append({"kind": "judge", "model": JUDGE_MODEL, "usage": ju, "cost_usd": c3})

        elapsed = round(time.time() - t0, 2)
        trial = {
            "experiment": EXPERIMENT_NAME,
            "problem_id": pid,
            "starter_k": starter["k"],
            "starter_score": starter["score"],
            "post_critic_score": score,
            "delta": score - starter["score"],
            "passed_before": starter["score"] >= PASS_THRESHOLD,
            "passed_after": score >= PASS_THRESHOLD,
            "elapsed_s": elapsed,
            "cost_usd": round(cost_cum, 6),
            "starter_solution": starter["solution"],
            "final_solution": solution,
            "verdict": verdict,
            "loop_log": loop_log,
            "stopped_early": stopped_early,
            "calls": calls,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"{tag} done s0={starter['score']}→s_after={score}  ${cost_cum:.4f}  {elapsed}s",
               flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        traceback.print_exc()
        trial = {
            "experiment": EXPERIMENT_NAME, "problem_id": pid,
            "starter_k": starter["k"], "starter_score": starter["score"],
            "post_critic_score": None, "elapsed_s": elapsed,
            "cost_usd": round(sum(c.get("cost_usd",0) for c in calls), 6),
            "calls": calls, "error": str(e),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"{tag} ERROR {e}  {elapsed}s", flush=True)

    p = run_dir / "trials" / f"{pid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trial, f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    summary = {
        "ts": trial["completed_at"], "problem_id": pid,
        "starter_score": trial.get("starter_score"),
        "post_critic_score": trial.get("post_critic_score"),
        "elapsed_s": trial.get("elapsed_s"), "cost_usd": trial.get("cost_usd"),
        "error": trial.get("error"),
    }
    with manifest_lock:
        with open(run_dir / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")
    return trial


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max-cost", type=float, default=5.0)
    args = p.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    samples_dir = PASSN_RUN_DIR / "samples"
    if not samples_dir.exists():
        raise SystemExit(f"passN samples not found at {samples_dir}")

    starters = load_passN_best(samples_dir)
    if not starters:
        raise SystemExit("No passN best samples found")

    print(f"Loaded {len(starters)} starter samples (best of N=8 v4-flash per problem)")
    print(f"Starter score distribution:")
    score_dist = {}
    for s in starters.values():
        score_dist[s["score"]] = score_dist.get(s["score"], 0) + 1
    for sc in sorted(score_dist):
        print(f"  score={sc}  n={score_dist[sc]}")

    run_id = _now_id()
    run_dir = RESULTS_DIR / f"{EXPERIMENT_NAME}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts = {
        "verifier": load_prompt("verifier.md"),
        "reviser":  load_prompt("reviser.md"),
        "judge_gt": load_prompt("judge_gt.md"),
    }

    print(f"\nExperiment: {EXPERIMENT_NAME}")
    print(f"Run dir:   {run_dir}")
    print(f"Critic:    {CRITIC_MODEL}")
    print(f"Judge:     {JUDGE_MODEL}")
    print(f"Cost cap:  ${args.max_cost}")
    print(f"Workers:   {MAX_WORKERS}")
    print()

    tracker = CostTracker(args.max_cost)
    manifest_lock = threading.Lock()
    results = []

    pending = sorted(starters.values(), key=lambda x: -x["score"])  # passes first
    completed = 0
    last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for st in pending:
            if tracker.aborted(): break
            futs[ex.submit(run_trial, st, prompts, run_dir, manifest_lock, tracker)] = st["pid"]
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * len(pending)):
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                print(f"[{_ts()}] FAILED: {e}", flush=True)
            now = time.time()
            if completed % 3 == 0 or now - last_print > 60:
                cum = tracker.snapshot()
                print(f"[{_ts()}] Progress {completed}/{len(pending)} cum=${cum:.2f}", flush=True)
                last_print = now

    # Summary
    print(f"\n{'='*80}\nCOMPOSED CRITIC + PASS@N RESULTS\n{'='*80}\n")
    valid = [r for r in results if r.get("post_critic_score") is not None]
    starter_scores = [r["starter_score"] for r in valid]
    post_scores    = [r["post_critic_score"] for r in valid]

    print(f"n_valid: {len(valid)}")
    print(f"  starter (best-of-8 v4-flash):  mean={np.mean(starter_scores):.2f}  pass={sum(1 for s in starter_scores if s>=6)}/{len(valid)}")
    print(f"  after v4-pro V↔R critique:     mean={np.mean(post_scores):.2f}  pass={sum(1 for s in post_scores if s>=6)}/{len(valid)}")
    print(f"  Δ mean: {np.mean(post_scores) - np.mean(starter_scores):+.2f}")
    deltas = [r["delta"] for r in valid]
    pos = sum(1 for d in deltas if d > 0)
    neg = sum(1 for d in deltas if d < 0)
    z   = sum(1 for d in deltas if d == 0)
    print(f"  Per-problem: improved {pos}, unchanged {z}, regressed {neg}")
    print()
    print(f"  {'Problem':<22}  {'starter':>7}  {'post':>5}  {'Δ':>3}")
    for r in sorted(valid, key=lambda x: x["problem_id"]):
        print(f"  {r['problem_id']:<22}  {r['starter_score']:>7}  {r['post_critic_score']:>5}  {r['delta']:>+3}")

    cum = tracker.snapshot()
    print(f"\nCumulative cost: ${cum:.3f}")


if __name__ == "__main__":
    main()
