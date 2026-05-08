#!/usr/bin/env python3
"""Patch dropped calls — robust serial-with-low-concurrency retry.
Saves progress after EVERY call (not just at end) so partial progress survives kills.
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, glob, itertools, json, math, os, random, re
import statistics as st, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import litellm  # noqa: E402

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
DATA_CSV = ROOT / "benchmarks" / "IMO-bench" / "gradingbench.csv"

PRIOR_SEED = 42; VAL_SEED = 7
MAX_TOKENS = 32768
TIMEOUT = 180  # short — fail fast
MAX_WORKERS = 4
RETRY_BACKOFF_S = [15, 30, 60, 120]  # progressive

load_dotenv()

_keys_env = os.getenv("PATCH_KEYS", "OPENROUTER_API_KEY_3")
KEYS = [v for v in (os.getenv(name.strip()) for name in _keys_env.split(",")) if v]
if not KEYS: raise SystemExit("No keys")
_iter = itertools.cycle(KEYS); _lock = threading.Lock()
def next_key():
    with _lock: return next(_iter)

def _ts(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def call_judge(prompt, model, extra_body):
    last = None
    for attempt, backoff in enumerate([0] + RETRY_BACKOFF_S):
        if backoff > 0:
            time.sleep(backoff)
        try:
            kw = dict(model=model, messages=[{"role": "user", "content": prompt}],
                      max_tokens=MAX_TOKENS, api_key=next_key(), timeout=TIMEOUT)
            if extra_body: kw["extra_body"] = extra_body
            resp = litellm.completion(**kw)
            msg = resp.choices[0].message
            content = msg.content or getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
            if content is None: raise ValueError("None content")
            usage = resp.usage
            cd = getattr(usage, "completion_tokens_details", None)
            return content, {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
                "reasoning_tokens": int(getattr(cd, "reasoning_tokens", 0) or 0) if cd else 0,
            }
        except Exception as e:
            last = e
            err = str(e)
            if "402" in err or "Key limit" in err: raise
    raise last

def parse_score(text):
    if not text: return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m: v = int(m.group(1)); return v if 0<=v<=7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    return int(m.group(1)) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--cost-cap", type=float, default=15.0)
    ap.add_argument("--provider", type=str, default=None,
                    help="Force OpenRouter provider (e.g. DeepInfra)")
    args = ap.parse_args()

    with open(args.input) as f:
        original = json.load(f)
    judge_id = original["judge_id"]
    rc = original["reasoning_config"]
    model = original["judge"]
    extra_body = dict(original.get("extra_body") or {})
    if args.provider:
        extra_body["provider"] = {"order": [args.provider], "allow_fallbacks": False}
        print(f"  Forcing provider: {args.provider}")
    price_in = original.get("price_input_per_M", 0)
    price_out = original.get("price_output_per_M", 0)
    price_mode = original.get("price_mode", "flat")

    results = list(original.get("results", []))
    by_gid = {r["grading_id"]: r for r in results}
    valid_orig = sum(1 for r in results if r.get("score") is not None)
    print(f"Loaded {judge_id}@{rc}: {len(results)} results, {valid_orig} valid")

    # Build canonical seed=7 sample
    rows = []
    with open(DATA_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"grading_id": r["Grading ID"], "problem_id": r["Problem ID"],
                         "problem": r["Problem"], "solution": r["Solution"],
                         "response": r["Response"], "human_points": int(r["Points"]),
                         "source": r["Problem Source"]})
    old = random.Random(PRIOR_SEED).sample(rows, 200)
    old_ids = set(r["grading_id"] for r in old)
    remaining = [r for r in rows if r["grading_id"] not in old_ids]
    val_sample = random.Random(VAL_SEED).sample(remaining, 200)

    to_retry = []
    for rec in val_sample:
        gid = rec["grading_id"]
        if gid not in by_gid:
            to_retry.append(rec)
        elif by_gid[gid].get("score") is None:
            to_retry.append(rec)
    print(f"  To retry: {len(to_retry)}")
    if not to_retry:
        print("Nothing to retry."); return

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()
    cost_state = {"spent": 0.0}
    cost_lock = threading.Lock()

    # Output path: incremental save after every call
    out_path = RESULTS_DIR / f"judge_validation_{judge_id}_{rc}_20260507_PATCHED_{_now()}.json"
    save_lock = threading.Lock()

    def compute_cost(usage):
        if price_mode == "flat":
            return round(price_in * usage["total_tokens"] / 1_000_000, 6)
        return round((price_in * usage["prompt_tokens"] +
                     price_out * usage["completion_tokens"]) / 1_000_000, 6)

    def save_progress():
        merged = list(results)
        merged_by_gid = {r["grading_id"]: r for r in merged}
        valid = sum(1 for r in merged if r.get("score") is not None)
        h = [r["human_points"] for r in merged if r.get("score") is not None]
        j = [r["score"] for r in merged if r.get("score") is not None]
        pa = sum(1 for jj,hh in zip(j,h) if (jj>=6)==(hh>=6))/len(j) if j else 0
        out = dict(original)
        out["results"] = merged
        out["retry_applied"] = True
        out["retry_cost_usd"] = round(cost_state["spent"], 4)
        out["total_cost_usd"] = round(original.get("total_cost_usd", 0) + cost_state["spent"], 4)
        out["n_done"] = len(merged)
        out["stats"] = {"n": len(merged), "n_valid": valid,
                        "mean_J": round(st.mean(j), 3) if j else 0,
                        "mean_H": round(st.mean(h), 3) if h else 0,
                        "pass_agree_at_6": round(pa, 4)}
        tmp = out_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        os.replace(tmp, out_path)

    def merge_in(new_r):
        gid = new_r["grading_id"]
        for i, r in enumerate(results):
            if r["grading_id"] == gid:
                results[i] = new_r
                return
        results.append(new_r)

    def worker(rec):
        with cost_lock:
            if cost_state["spent"] >= args.cost_cap: return None
        prompt = (judge_template
                  .replace("{problem}", rec["problem"])
                  .replace("{ground_truth}", rec["solution"])
                  .replace("{candidate}", rec["response"]))
        t0 = time.time()
        try:
            content, usage = call_judge(prompt, model, extra_body)
            el = round(time.time() - t0, 2)
            score = parse_score(content)
            cost = compute_cost(usage)
            with cost_lock: cost_state["spent"] += cost
            d = (score - rec["human_points"]) if score is not None else None
            ds = f"D={d:+d}" if d is not None else "D=NA"
            print(f"[{_ts()}] {judge_id[:10]} {rec['grading_id']:<8} pts={rec['human_points']} score={score} {ds}  ${cost:.4f}  {el}s  cum=${cost_state['spent']:.2f}", flush=True)
            new_r = {"grading_id": rec["grading_id"], "problem_id": rec["problem_id"],
                     "human_points": rec["human_points"], "source": rec["source"],
                     "score": score, "verdict": content, "usage": usage,
                     "cost": cost, "elapsed": el}
            with save_lock:
                merge_in(new_r)
                save_progress()
            return new_r
        except Exception as e:
            el = round(time.time() - t0, 2)
            print(f"[{_ts()}] {judge_id[:10]} FAIL {rec['grading_id']}: {str(e)[:100]}", flush=True)
            new_r = {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                     "score": None, "error": str(e), "cost": 0.0, "elapsed": el}
            with save_lock:
                merge_in(new_r)
                save_progress()
            return new_r

    print(f"Starting {len(to_retry)} retries × {args.workers} workers (timeout={TIMEOUT}s, cost_cap=${args.cost_cap})")
    save_progress()  # initial save
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, r) for r in to_retry]
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            done += 1
            if done % 5 == 0:
                el = time.time() - t0
                print(f"  --- progress: {done}/{len(to_retry)} processed in {el:.0f}s ---", flush=True)

    el = round(time.time() - t0, 1)
    final_valid = sum(1 for r in results if r.get("score") is not None)
    print(f"\nDONE: {final_valid}/{len(results)} valid in {el}s, ${cost_state['spent']:.2f} spent")
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
