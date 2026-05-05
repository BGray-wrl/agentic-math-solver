#!/usr/bin/env python3
"""
Best-of-N scaling curve for deepseek-v4-flash on PB-Advanced, v4-flash judge.

For each problem, sample N=8 independent generate-only completions (different
random seeds via temperature variability + different request order). Judge each
with deepseek-v4-flash. Compute pass@k for k = 1, 2, 3, 5, 7, 8.

The Phase 1 best-of-N study used gemini and v4-pro judges. This run is the
first under v4-flash judge (the user's chosen default) and extends N from 7 to 8
to check whether v4-flash plateaus or keeps scaling.

Cost target: ~$2 (20 problems × 8 samples × ~$0.012 per (gen+judge)).
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
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

from problemset_70 import load_70_problems  # noqa: E402

EXPERIMENT_NAME = "passN_v4flash_20260505"

GEN_MODEL    = "openrouter/deepseek/deepseek-v4-flash"
GEN_PRICE    = 0.28
JUDGE_MODEL  = "openrouter/deepseek/deepseek-v4-flash"
JUDGE_PRICE  = 0.28

N_SAMPLES = 8

MAX_TOKENS_GEN     = 32768
MAX_TOKENS_JUDGE   = 32768

MAX_WORKERS    = 12
TRIAL_TIMEOUT  = 1800
LITELLM_TIMEOUT = 1500

PASS_THRESHOLD = 6
N_PROBLEMS_DEFAULT = 20

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _now_id(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts():     return datetime.now(timezone.utc).strftime("%H:%M:%S")


load_dotenv()
FLEX_KEY = os.getenv("OPENROUTER_API_KEY_flex")
if not FLEX_KEY:
    raise SystemExit("OPENROUTER_API_KEY_flex not set in .env.")


def _probe_key(key):
    import requests
    try:
        r = requests.get("https://openrouter.ai/api/v1/key",
                          headers={"Authorization": f"Bearer {key}"}, timeout=8)
        if r.ok:
            d = r.json().get("data", {}) or {}
            usage = d.get("usage", 0) or 0; limit = d.get("limit")
            print(f"[startup] flex key usage=${usage:.4f} / limit=${limit}", flush=True)
    except Exception as e:
        print(f"[startup] probe failed: {e}", flush=True)


def call_model(model, system, user, max_tokens, retries=2, backoff=5.0, seed=None):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    last_err = None
    for attempt in range(retries + 1):
        try:
            kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                          api_key=FLEX_KEY, timeout=LITELLM_TIMEOUT)
            if seed is not None:
                kwargs["seed"] = seed
            resp = litellm.completion(**kwargs)
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
                print(f"[{_ts()}] [retry] {model.split('/')[-1]} {attempt+1}: {e} -> {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


class CostTracker:
    def __init__(self, max_cost):
        self.max_cost = max_cost
        self._cost = 0.0; self._tokens_in = 0; self._tokens_out = 0
        self._lock = threading.Lock(); self._aborted = False

    def add(self, cost, in_tok, out_tok):
        with self._lock:
            self._cost += cost; self._tokens_in += in_tok; self._tokens_out += out_tok
            if self.max_cost is not None and self._cost >= self.max_cost and not self._aborted:
                self._aborted = True
                print(f"[{_ts()}] [KILLSWITCH] cum=${self._cost:.2f} >= cap=${self.max_cost:.2f}", flush=True)

    def aborted(self):
        with self._lock: return self._aborted

    def snapshot(self):
        with self._lock: return self._cost, self._tokens_in, self._tokens_out


def cost_for(model, total_tokens):
    if model == GEN_MODEL or model == JUDGE_MODEL:
        return GEN_PRICE * total_tokens / 1_000_000
    return 0.5 * total_tokens / 1_000_000


def parse_gt_score(verdict):
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m: return int(m.group(1))
    return 0


def load_prompt(name): return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def sample_path(run_dir, pid, k):
    return run_dir / "samples" / pid / f"k{k:02d}.json"


def save_sample(run_dir, pid, k, sample):
    p = sample_path(run_dir, pid, k)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def already_done(run_dir, pid, k):
    p = sample_path(run_dir, pid, k)
    if not p.exists(): return False
    try:
        with open(p, encoding="utf-8") as f:
            s = json.load(f)
        return s.get("score") is not None and not s.get("error")
    except Exception:
        return False


def run_sample(pid, problem, k, run_dir, prompts, tracker, manifest_lock):
    tag = f"[{_ts()}] [{pid}|k={k}]"
    t0 = time.time()
    sample = {
        "problem_id": pid, "k": k, "level": problem.get("level", ""),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        # Generate
        gen_t0 = time.time()
        gen_text, gen_usage = call_model(
            GEN_MODEL, prompts["generator"], problem["text"], MAX_TOKENS_GEN, seed=k,
        )
        gen_cost = cost_for(GEN_MODEL, gen_usage["total_tokens"])
        tracker.add(gen_cost, gen_usage["prompt_tokens"], gen_usage["completion_tokens"])

        # Judge
        judge_t0 = time.time()
        judge_user = (prompts["judge_gt"]
                      .replace("{problem}", problem["text"])
                      .replace("{ground_truth}", problem["ground_truth"])
                      .replace("{candidate}", gen_text))
        verdict, j_usage = call_model(JUDGE_MODEL, "", judge_user, MAX_TOKENS_JUDGE)
        j_cost = cost_for(JUDGE_MODEL, j_usage["total_tokens"])
        tracker.add(j_cost, j_usage["prompt_tokens"], j_usage["completion_tokens"])
        score = parse_gt_score(verdict)

        elapsed = round(time.time() - t0, 2)
        sample.update({
            "score": score, "passed": score >= PASS_THRESHOLD,
            "elapsed_s": elapsed,
            "gen_elapsed": round(time.time() - gen_t0, 2),
            "judge_elapsed": round(time.time() - judge_t0, 2),
            "cost_usd": round(gen_cost + j_cost, 6),
            "solution": gen_text, "verdict": verdict,
            "gen_usage": gen_usage, "judge_usage": j_usage,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"{tag} score={score}  ${gen_cost+j_cost:.4f}  {elapsed}s", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        traceback.print_exc()
        sample.update({"score": None, "passed": False, "elapsed_s": elapsed,
                       "error": str(e),
                       "completed_at": datetime.now(timezone.utc).isoformat()})
        print(f"{tag} ERROR {e}  {elapsed}s", flush=True)

    save_sample(run_dir, pid, k, sample)
    summary = {"ts": sample["completed_at"], "problem_id": pid, "k": k,
                "score": sample.get("score"), "passed": sample.get("passed"),
                "cost_usd": sample.get("cost_usd"), "error": sample.get("error")}
    with manifest_lock:
        with open(run_dir / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")
    return sample


def execute(problems, prompts, run_dir, tracker):
    pids = sorted(problems.keys())
    units = [(pid, k) for pid in pids for k in range(N_SAMPLES)]
    pending = [(pid, k) for (pid, k) in units if not already_done(run_dir, pid, k)]
    print(f"\n=== passN | n_problems={len(pids)} N={N_SAMPLES} ===", flush=True)
    print(f"Units: {len(units)}  pending: {len(pending)}", flush=True)
    print(f"max_workers={MAX_WORKERS}  cap=${tracker.max_cost}\n", flush=True)

    manifest_lock = threading.Lock()
    completed = 0; last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for pid, k in pending:
            if tracker.aborted(): break
            futs[ex.submit(run_sample, pid, problems[pid], k, run_dir, prompts,
                            tracker, manifest_lock)] = (pid, k)

        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * max(len(pending), 1)):
            pid, k = futs[fut]
            completed += 1
            try:
                fut.result(timeout=TRIAL_TIMEOUT)
            except Exception as e:
                print(f"[{_ts()}] FAILED [{pid}|k={k}]: {e}", flush=True)
            now = time.time()
            if completed % 8 == 0 or now - last_print > 60:
                cum_cost, in_t, out_t = tracker.snapshot()
                print(f"[{_ts()}] Progress {completed}/{len(pending)} cum=${cum_cost:.2f} "
                       f"in={in_t:,} out={out_t:,}", flush=True)
                last_print = now


def compute_passN(run_dir, n_max=N_SAMPLES):
    """Per-problem stats and pass@k aggregate using the saved sample files."""
    problem_scores = {}
    for sd in sorted((run_dir / "samples").glob("*")):
        pid = sd.name
        scores = {}
        for f in sorted(sd.glob("k*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    s = json.load(fh)
                if s.get("score") is not None:
                    scores[s["k"]] = s["score"]
            except Exception:
                pass
        problem_scores[pid] = scores
    return problem_scores


def print_summary(run_dir):
    ps = compute_passN(run_dir)
    print(f"\n{'='*100}\nPASS@N RESULTS — {run_dir.name}\n{'='*100}\n")
    if not ps:
        print("No samples"); return
    n_pids = len(ps)
    print(f"Problems: {n_pids}\n")
    print(f"  {'k':>3}  {'mean_max':>9}  {'pass@k':>7}")
    for k in [1, 2, 3, 5, 7, 8]:
        if k > N_SAMPLES: continue
        means = []
        passes = 0
        for pid, scores in ps.items():
            available = [scores[i] for i in range(k) if i in scores]
            if available:
                m = max(available)
                means.append(m)
                if m >= PASS_THRESHOLD:
                    passes += 1
        if means:
            print(f"  {k:>3}  {float(np.mean(means)):>9.2f}  {passes}/{n_pids}")

    print(f"\n--- Per-problem (best score across k samples) ---")
    print(f"  {'Problem':<26}  {'best':>4}  {'samples (k=0..N-1)':<40}")
    for pid in sorted(ps.keys()):
        scores = ps[pid]
        s_str = ",".join(str(scores.get(k, "_")) for k in range(N_SAMPLES))
        best = max(scores.values()) if scores else None
        print(f"  {pid:<26}  {str(best):>4}  {s_str}")


def select_problems(n, seed=42):
    all_p = load_70_problems()
    pb = {pid: p for pid, p in all_p.items() if pid.startswith("PB-Advanced")}
    if n >= len(pb): return pb
    rng = random.Random(seed)
    keys = sorted(pb.keys())
    sampled = rng.sample(keys, n)
    return {k: pb[k] for k in sampled}


def load_prompts():
    return {"generator": load_prompt("generator.md"),
            "judge_gt":  load_prompt("judge_gt.md")}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--n-problems", type=int, default=N_PROBLEMS_DEFAULT)
    p.add_argument("--n-samples", type=int, default=N_SAMPLES)
    p.add_argument("--from-run-id", default=None)
    p.add_argument("--max-cost", type=float, default=3.0)
    args = p.parse_args()

    # n_samples controls how many samples per problem.
    if args.n_samples != N_SAMPLES:
        import passN_v4flash_20260505 as _self
        _self.N_SAMPLES = args.n_samples

    litellm.request_timeout = LITELLM_TIMEOUT
    _probe_key(FLEX_KEY)

    n = args.n_problems if not args.smoke else 2
    problems = select_problems(n, seed=42)

    run_id = args.from_run_id or _now_id()
    suffix = "_smoke" if args.smoke else ""
    run_dir = RESULTS_DIR / f"{EXPERIMENT_NAME}_{run_id}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts = load_prompts()
    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Run dir:    {run_dir}")
    print(f"Problems:   {len(problems)}")
    print(f"N_SAMPLES:  {N_SAMPLES}")
    print(f"Cost cap:   ${args.max_cost}")
    print()
    tracker = CostTracker(args.max_cost)
    t0 = time.time()
    execute(problems, prompts, run_dir, tracker)
    elapsed = round(time.time() - t0, 1)
    cum, in_t, out_t = tracker.snapshot()
    print(f"\nWall: {elapsed}s  Cumulative: ${cum:.2f}  in={in_t:,} out={out_t:,}")
    print_summary(run_dir)


if __name__ == "__main__":
    main()
