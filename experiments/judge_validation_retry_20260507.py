#!/usr/bin/env python3
"""Retry missing/failed grading_ids for any validation judge config.
Uses LOW concurrency (12 workers) and longer backoff to recover from upstream rate limits.
Merges retried results back into a NEW final JSON.
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
TIMEOUT = 300  # shorter — fail fast on hangs
MAX_WORKERS = 12

load_dotenv()

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
            if limit is not None and usage >= limit: continue
            live.append(k)
        except: live.append(k)
    return live

KEYS = _filter_live_keys([k for k in [
    os.getenv("OPENROUTER_API_KEY"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_X2"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k])
if not KEYS: raise SystemExit("No live keys")
_iter = itertools.cycle(KEYS); _lock = threading.Lock()
def next_key():
    with _lock: return next(_iter)

def _ts(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def call_judge(prompt, model, extra_body, retries=3, backoff=10.0):
    last = None
    for attempt in range(retries + 1):
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
            if attempt < retries: time.sleep(backoff * (2 ** attempt))
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
    ap.add_argument("--cost-cap", type=float, default=10.0)
    args = ap.parse_args()

    with open(args.input) as f:
        original = json.load(f)
    judge_id = original["judge_id"]
    rc = original["reasoning_config"]
    model = original["judge"]
    extra_body = original.get("extra_body")
    price_in = original.get("price_input_per_M", 0)
    price_out = original.get("price_output_per_M", 0)
    price_mode = original.get("price_mode", "flat")

    results = original.get("results", [])
    by_gid = {r["grading_id"]: r for r in results}
    valid = [r for r in results if r.get("score") is not None]
    print(f"Loaded {judge_id}@{rc} from {os.path.basename(args.input)}")
    print(f"  Existing: {len(results)} results, {len(valid)} valid, {len(results)-len(valid)} failed")

    # Build the canonical seed=7 sample
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

    # Determine which gids need retry: missing OR score=None
    to_retry = []
    for rec in val_sample:
        gid = rec["grading_id"]
        if gid not in by_gid:
            to_retry.append(rec)  # never attempted
        elif by_gid[gid].get("score") is None:
            to_retry.append(rec)  # attempted but failed
    print(f"  To retry: {len(to_retry)} (missing + failed)")

    if not to_retry:
        print("Nothing to retry. Exiting.")
        return

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()
    cost_state = {"spent": 0.0}
    cost_lock = threading.Lock()

    def compute_cost(usage):
        if price_mode == "flat":
            return round(price_in * usage["total_tokens"] / 1_000_000, 6)
        else:
            return round((price_in * usage["prompt_tokens"] +
                         price_out * usage["completion_tokens"]) / 1_000_000, 6)

    def worker(rec):
        with cost_lock:
            if cost_state["spent"] >= args.cost_cap:
                return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                        "score": None, "error": "cost cap", "cost": 0.0, "elapsed": 0.0}
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
            print(f"[{_ts()}] {rec['grading_id']:<8} pts={rec['human_points']} score={score} {ds}  "
                  f"${cost:.4f}  {el}s  cum=${cost_state['spent']:.2f}", flush=True)
            return {"grading_id": rec["grading_id"], "problem_id": rec["problem_id"],
                    "human_points": rec["human_points"], "source": rec["source"],
                    "score": score, "verdict": content, "usage": usage,
                    "cost": cost, "elapsed": el}
        except Exception as e:
            el = round(time.time() - t0, 2)
            print(f"[{_ts()}] FAIL {rec['grading_id']}: {str(e)[:120]}", flush=True)
            return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                    "score": None, "error": str(e), "cost": 0.0, "elapsed": el}

    print(f"\nStarting retry: {len(to_retry)} calls × {args.workers} workers (cost_cap=${args.cost_cap})")
    new_results = []
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, r) for r in to_retry]
        for fut in concurrent.futures.as_completed(futs):
            try: new_results.append(fut.result())
            except Exception as e: print(f"outer fail: {e}", flush=True)

    el = round(time.time() - t0, 1)
    new_valid = [r for r in new_results if r.get("score") is not None]
    print(f"\nRetry done: {len(new_valid)}/{len(to_retry)} valid in {el}s, ${cost_state['spent']:.2f}")

    # Merge: replace existing failures, add missing ones
    new_by_gid = {r["grading_id"]: r for r in new_results}
    merged = list(results)  # start with existing
    merged_gids = set(r["grading_id"] for r in merged)
    for gid, new_r in new_by_gid.items():
        if gid in merged_gids:
            # Replace if new has a score and old doesn't
            for i, r in enumerate(merged):
                if r["grading_id"] == gid:
                    if r.get("score") is None and new_r.get("score") is not None:
                        merged[i] = new_r
                    break
        else:
            merged.append(new_r)

    final_valid = sum(1 for r in merged if r.get("score") is not None)
    print(f"After merge: {len(merged)} total, {final_valid} valid")

    # Recompute stats
    valid_merged = [r for r in merged if r.get("score") is not None]
    h = [r["human_points"] for r in valid_merged]
    j = [r["score"] for r in valid_merged]
    pass_agree = sum(1 for jj,hh in zip(j,h) if (jj>=6)==(hh>=6))/len(j) if j else 0

    final = dict(original)
    final["results"] = merged
    final["retry_applied"] = True
    final["retry_cost_usd"] = round(cost_state["spent"], 4)
    final["total_cost_usd"] = round(original.get("total_cost_usd", 0) + cost_state["spent"], 4)
    final["n_done"] = len(merged)
    final["stats"] = {
        "n": len(merged), "n_valid": len(valid_merged),
        "mean_J": round(st.mean(j), 3) if j else 0,
        "mean_H": round(st.mean(h), 3) if h else 0,
        "pass_agree_at_6": round(pass_agree, 4),
    }
    out_path = RESULTS_DIR / f"judge_validation_{judge_id}_{rc}_20260507_MERGED_{_now()}.json"
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
