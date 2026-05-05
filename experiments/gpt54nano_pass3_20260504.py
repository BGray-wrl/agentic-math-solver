#!/usr/bin/env python3
"""
gpt-5.4-nano pass@3 with reasoning_effort='xhigh' on the 70-problem set.
Judge: deepseek-v4-flash.

Per-(problem, k) JSON saved on completion. Reports pass@1 and pass@3.

Usage:
    uv run experiments/gpt54nano_pass3_20260504.py [--mock] [--max-cost N]
"""

from __future__ import annotations

import argparse, concurrent.futures, itertools, json, os, re, sys, threading, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402
from problemset_70 import load_70_problems  # noqa: E402

# ----- Config -----
GEN_MODEL   = "openrouter/openai/gpt-5.4-nano"
JUDGE_MODEL = "openrouter/deepseek/deepseek-v4-flash"
GEN_PRICE   = 0.10   # rough estimate per $/M; actual may vary
JUDGE_PRICE = 0.28

REASONING_EFFORT = "xhigh"   # per user
N_PASS = 3

PROMPTS = ROOT / "prompts" / "pipeline"
RESULTS_DIR = ROOT / "experiments" / "results"

MAX_TOKENS_GEN = 65536
MAX_TOKENS_JUDGE = 65536
MAX_WORKERS = 30
LITELLM_TIMEOUT = 1800

# ----- Key rotation -----
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
_iter = itertools.cycle(KEYS)
_lock = threading.Lock()
def next_key():
    with _lock: return next(_iter)


def _ts():  return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


class CostTracker:
    def __init__(self, mc): self.max_cost=mc; self._c=0; self._l=threading.Lock(); self._a=False
    def add(self, c):
        with self._l:
            self._c += c
            if self.max_cost and self._c >= self.max_cost and not self._a:
                self._a = True; print(f"[{_ts()}] [KILLSWITCH] cum=${self._c:.2f}", flush=True)
    def aborted(self):
        with self._l: return self._a
    def snapshot(self):
        with self._l: return self._c


def call_model(model, system, user, max_tokens, reasoning_effort=None, retries=2, backoff=4.0):
    last = None
    for att in range(retries + 1):
        key = next_key()
        try:
            messages = []
            if system: messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": user})
            kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens,
                      "api_key": key, "timeout": LITELLM_TIMEOUT}
            if reasoning_effort:
                # litellm passes this through to OpenRouter / OpenAI as a top-level param
                kwargs["reasoning_effort"] = reasoning_effort
            resp = litellm.completion(**kwargs)
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
        if f"CLASSIFICATION: {label}" in (text or ""): return score
    return 0


GEN_PROMPT = (PROMPTS / "generator.md").read_text()
JUDGE_PROMPT = (PROMPTS / "judge_gt.md").read_text()


def trial_path(run_dir, pid, k): return run_dir / f"{pid}__k{k}.json"


def already_done(run_dir, pid, k):
    p = trial_path(run_dir, pid, k)
    if not p.exists(): return False
    try:
        with open(p) as f: t = json.load(f)
        return not t.get("error") and t.get("score") is not None
    except: return False


def save_trial(run_dir, lock, rec):
    p = trial_path(run_dir, rec["problem_id"], rec["k"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f: json.dump(rec, f, indent=2, ensure_ascii=False)
    with lock:
        with open(run_dir / "manifest.jsonl", "a") as f:
            f.write(json.dumps({k: rec[k] for k in ("problem_id","k","score","cost_usd","error") if k in rec}) + "\n")


def run_one(problem, pid, k, run_dir, lock, tracker, mock):
    rec = {"problem_id": pid, "k": k, "model": GEN_MODEL, "judge_model": JUDGE_MODEL,
           "reasoning_effort": REASONING_EFFORT}
    t0 = time.time()
    if mock:
        rec.update({"solution": "mock", "score": 7, "verdict": "<points>7 out of 7</points>",
                    "cost_usd": 0.0, "elapsed_s": 0.01})
        save_trial(run_dir, lock, rec); return rec

    try:
        sol, gen_usage = call_model(GEN_MODEL, GEN_PROMPT, problem["text"],
                                    MAX_TOKENS_GEN, reasoning_effort=REASONING_EFFORT)
        gen_cost = round(GEN_PRICE * gen_usage["total_tokens"] / 1_000_000, 6)
        tracker.add(gen_cost)
    except Exception as e:
        elapsed = round(time.time()-t0, 2)
        rec.update({"solution": None, "score": None, "error": str(e),
                    "cost_usd": 0.0, "elapsed_s": elapsed})
        print(f"[{_ts()}] GEN-FAIL {pid} k={k}: {e}", flush=True)
        save_trial(run_dir, lock, rec); return rec

    judge_prompt = (JUDGE_PROMPT
                    .replace("{problem}",      problem["text"])
                    .replace("{ground_truth}", problem["ground_truth"])
                    .replace("{candidate}",    sol))
    try:
        verdict, judge_usage = call_model(JUDGE_MODEL, "", judge_prompt, MAX_TOKENS_JUDGE)
        score = parse_score(verdict)
        judge_cost = round(JUDGE_PRICE * judge_usage["total_tokens"] / 1_000_000, 6)
        tracker.add(judge_cost)
        elapsed = round(time.time()-t0, 2)
        rec.update({"solution": sol, "verdict": verdict, "score": score,
                    "gen_usage": gen_usage, "judge_usage": judge_usage,
                    "cost_usd": round(gen_cost + judge_cost, 6), "elapsed_s": elapsed})
        print(f"[{_ts()}] {pid:<28} k={k}  score={score}  ${rec['cost_usd']:.4f}  {elapsed}s", flush=True)
    except Exception as e:
        elapsed = round(time.time()-t0, 2)
        rec.update({"solution": sol, "verdict": None, "score": None, "error": f"judge: {e}",
                    "gen_usage": gen_usage, "judge_usage": None, "cost_usd": gen_cost, "elapsed_s": elapsed})
        print(f"[{_ts()}] JUDGE-FAIL {pid} k={k}: {e}", flush=True)
    save_trial(run_dir, lock, rec); return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--max-cost", type=float, default=None)
    args = ap.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT
    problems = load_70_problems()

    run_id = _now()
    run_dir = RESULTS_DIR / f"gpt54nano_pass3_20260504_{run_id}{'_mock' if args.mock else ''}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run dir: {run_dir}")
    print(f"Generator: {GEN_MODEL}  reasoning_effort={REASONING_EFFORT}")
    print(f"Judge:     {JUDGE_MODEL}")

    pending = []
    for pid in sorted(problems):
        for k in range(N_PASS):
            if already_done(run_dir, pid, k): continue
            pending.append((pid, k))
    print(f"Pending: {len(pending)} of {len(problems)*N_PASS}\n")

    tracker = CostTracker(args.max_cost)
    lock = threading.Lock()

    t0 = time.time()
    completed = 0
    last_print = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for pid, k in pending:
            if tracker.aborted(): break
            futs[ex.submit(run_one, problems[pid], pid, k, run_dir, lock, tracker, args.mock)] = (pid, k)
        for fut in concurrent.futures.as_completed(futs, timeout=LITELLM_TIMEOUT * len(pending)):
            completed += 1
            try: fut.result(timeout=LITELLM_TIMEOUT)
            except Exception as e: print(f"[{_ts()}] outer fail: {e}", flush=True)
            if time.time() - last_print > 30:
                print(f"[{_ts()}] Progress: {completed}/{len(pending)}  cum=${tracker.snapshot():.2f}", flush=True)
                last_print = time.time()
    elapsed = round(time.time()-t0, 1)
    print(f"\nWall: {elapsed}s    Cost: ${tracker.snapshot():.2f}")

    # Aggregate
    all_scores = defaultdict(dict)
    for p in run_dir.glob("*.json"):
        try: r = json.load(open(p))
        except: continue
        if r.get("error") or r.get("score") is None: continue
        all_scores[r["problem_id"]][r["k"]] = r["score"]

    print(f"\n=== gpt-5.4-nano (xhigh) pass@N (judge=v4-flash) ===")
    for n in (1, 3):
        scores = []
        for pid in sorted(problems):
            ks = all_scores.get(pid, {})
            if all(k in ks for k in range(n)):
                scores.append(max(ks[k] for k in range(n)))
        if scores:
            mean = sum(scores)/len(scores)
            passes = sum(1 for s in scores if s >= 6)
            print(f"  pass@{n}: n={len(scores)}  mean={mean:.3f}  pass={passes}/{len(scores)}")

    summary_path = run_dir / "summary.json"
    summary = {
        "experiment": "gpt54nano_pass3",
        "model": GEN_MODEL, "judge": JUDGE_MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "n_problems": len(problems),
        "wall_clock_s": elapsed, "total_cost_usd": round(tracker.snapshot(), 2),
        "per_problem_scores": {pid: dict(scores) for pid, scores in all_scores.items()},
    }
    for n in (1, 3):
        scores = []
        for pid in sorted(problems):
            ks = all_scores.get(pid, {})
            if all(k in ks for k in range(n)):
                scores.append(max(ks[k] for k in range(n)))
        summary[f"pass@{n}"] = {
            "n": len(scores),
            "mean": round(sum(scores)/len(scores), 3) if scores else None,
            "passes": sum(1 for s in scores if s >= 6),
        }
    with open(summary_path, "w") as f: json.dump(summary, f, indent=2)
    print(f"\nSaved: {summary_path}")


if __name__ == "__main__":
    main()
