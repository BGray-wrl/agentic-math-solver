#!/usr/bin/env python3
"""Retry the failed gemma-4-31b-it@high calls from the validation run.
Loads the partial/final result JSON, finds rows with score=None, retries those
with low concurrency (10 workers) to avoid upstream Google rate limits.
Merges retried results back into a new final JSON.
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

JUDGE = "openrouter/google/gemma-4-31b-it"
EXTRA_BODY = {"reasoning": {"effort": "high"}}
PRICE_PER_M = 0.38
COST_CAP = 5.0
MAX_WORKERS = 10  # LOW concurrency to avoid upstream rate limits
MAX_TOKENS = 32768
TIMEOUT = 600

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

def call_judge(prompt, retries=4, backoff=8.0):
    last = None
    for attempt in range(retries + 1):
        try:
            resp = litellm.completion(
                model=JUDGE, messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS, api_key=next_key(), timeout=TIMEOUT,
                extra_body=EXTRA_BODY,
            )
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
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last

def parse_score(text):
    if not text: return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m:
        v = int(m.group(1)); return v if 0 <= v <= 7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    return int(m.group(1)) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to original gemma JSON (partial or final)")
    args = ap.parse_args()

    with open(args.input) as f:
        original = json.load(f)
    results = original.get("results", [])
    failed = [r for r in results if r.get("score") is None]
    valid = [r for r in results if r.get("score") is not None]
    print(f"Loaded {len(results)} results from {args.input}")
    print(f"  Valid: {len(valid)}, Failed: {len(failed)}")

    if not failed:
        print("No failures to retry. Done.")
        return

    # Look up the original sample records for the failed grading_ids
    rows = []
    with open(DATA_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"grading_id": r["Grading ID"], "problem_id": r["Problem ID"],
                         "problem": r["Problem"], "solution": r["Solution"],
                         "response": r["Response"], "human_points": int(r["Points"]),
                         "source": r["Problem Source"]})
    by_gid = {r["grading_id"]: r for r in rows}

    # Need the same sample set
    PRIOR_SEED = 42; VAL_SEED = 7
    old = random.Random(PRIOR_SEED).sample(rows, 200)
    old_ids = set(r["grading_id"] for r in old)
    remaining = [r for r in rows if r["grading_id"] not in old_ids]
    val_sample = random.Random(VAL_SEED).sample(remaining, 200)
    val_by_gid = {r["grading_id"]: r for r in val_sample}

    failed_records = [val_by_gid[r["grading_id"]] for r in failed if r["grading_id"] in val_by_gid]
    print(f"  Found {len(failed_records)} sample records to retry")

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()
    cost_state = {"spent": 0.0, "capped": False}
    cost_lock = threading.Lock()
    new_results = []

    def worker(rec):
        with cost_lock:
            if cost_state["spent"] >= COST_CAP:
                return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                        "score": None, "error": "cost cap", "cost": 0.0, "elapsed": 0.0}
        prompt = (judge_template
                  .replace("{problem}", rec["problem"])
                  .replace("{ground_truth}", rec["solution"])
                  .replace("{candidate}", rec["response"]))
        t0 = time.time()
        try:
            content, usage = call_judge(prompt)
            el = round(time.time() - t0, 2)
            score = parse_score(content)
            cost = round(PRICE_PER_M * usage["total_tokens"] / 1_000_000, 6)
            with cost_lock:
                cost_state["spent"] += cost
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

    print(f"\nRetrying {len(failed_records)} calls with {MAX_WORKERS} workers...")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(worker, r) for r in failed_records]
        for fut in concurrent.futures.as_completed(futs):
            try: new_results.append(fut.result())
            except Exception as e: print(f"outer fail: {e}", flush=True)

    el = round(time.time() - t0, 1)
    new_valid = [r for r in new_results if r.get("score") is not None]
    print(f"\nRetry complete: {len(new_valid)}/{len(failed_records)} now valid in {el}s, ${cost_state['spent']:.2f}")

    # Merge: replace the failed ones in original results
    new_by_gid = {r["grading_id"]: r for r in new_results}
    merged = []
    for r in results:
        if r.get("score") is None and r["grading_id"] in new_by_gid:
            replacement = new_by_gid[r["grading_id"]]
            if replacement.get("score") is not None:
                merged.append(replacement)
            else:
                merged.append(r)  # keep original failure
        else:
            merged.append(r)

    final_valid = sum(1 for r in merged if r.get("score") is not None)
    print(f"After merge: {final_valid}/{len(merged)} valid")

    # Save merged result
    out_path = RESULTS_DIR / f"judge_validation_gemma-4-31b-it_high_20260507_MERGED_{_now()}.json"
    final = dict(original)
    final["results"] = merged
    final["retry_applied"] = True
    final["retry_cost_usd"] = round(cost_state["spent"], 4)
    final["total_cost_usd"] = round(original.get("total_cost_usd", 0) + cost_state["spent"], 4)
    final["n_done"] = len(merged)
    # Recompute stats
    valid_merged = [r for r in merged if r.get("score") is not None]
    if valid_merged:
        h = [r["human_points"] for r in valid_merged]
        j = [r["score"] for r in valid_merged]
        final["stats"] = {
            "n": len(merged), "n_valid": len(valid_merged),
            "mean_J": round(st.mean(j), 3), "mean_H": round(st.mean(h), 3),
            "pass_agree_at_6": round(sum(1 for jj,hh in zip(j,h) if (jj>=6)==(hh>=6))/len(j), 4),
        }
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
