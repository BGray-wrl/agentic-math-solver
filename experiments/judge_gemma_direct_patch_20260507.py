#!/usr/bin/env python3
"""Patch gemma dropped calls via DIRECT Google AI Studio API.
Bypasses OpenRouter's shared upstream quota.
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, glob, json, math, os, random, re
import statistics as st, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import requests

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
DATA_CSV = ROOT / "benchmarks" / "IMO-bench" / "gradingbench.csv"

PRIOR_SEED = 42; VAL_SEED = 7
TIMEOUT = 180
PRICE_PER_M = 0.38  # tracking only

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY: raise SystemExit("GEMINI_API_KEY not set")

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent"

def _ts(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def call_gemma(prompt, retries=5):
    last = None
    for attempt, backoff in enumerate([0, 30, 60, 120, 180, 240]):
        if backoff > 0: time.sleep(backoff)
        try:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 16384},
            }
            r = requests.post(f"{URL}?key={GEMINI_API_KEY}", json=payload, timeout=TIMEOUT)
            if r.status_code == 429:
                last = Exception(f"429 rate limit: {r.text[:120]}")
                continue
            r.raise_for_status()
            d = r.json()
            cand = d.get("candidates", [{}])[0]
            parts = cand.get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)
            usage = d.get("usageMetadata", {})
            return content, {
                "prompt_tokens": int(usage.get("promptTokenCount", 0) or 0),
                "completion_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
                "reasoning_tokens": int(usage.get("thoughtsTokenCount", 0) or 0),
                "total_tokens": int(usage.get("totalTokenCount", 0) or 0),
            }
        except Exception as e:
            last = e
            if attempt < retries: continue
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
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    with open(args.input) as f:
        original = json.load(f)
    judge_id = original["judge_id"]
    rc = original["reasoning_config"]

    results = list(original.get("results", []))
    by_gid = {r["grading_id"]: r for r in results}
    print(f"Loaded {judge_id}@{rc}: {len(results)} results, {sum(1 for r in results if r.get('score') is not None)} valid")

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
        if gid not in by_gid or by_gid[gid].get("score") is None:
            to_retry.append(rec)
    print(f"  To retry via DIRECT Google API: {len(to_retry)}")

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()
    cost_state = {"spent": 0.0}
    cost_lock = threading.Lock()
    save_lock = threading.Lock()
    out_path = RESULTS_DIR / f"judge_validation_{judge_id}_{rc}_20260507_PATCHED_DIRECT_{_now()}.json"

    def save_progress():
        merged = list(results)
        valid = [r for r in merged if r.get("score") is not None]
        h = [r["human_points"] for r in valid]
        j = [r["score"] for r in valid]
        pa = sum(1 for jj,hh in zip(j,h) if (jj>=6)==(hh>=6))/len(j) if j else 0
        out = dict(original)
        out["results"] = merged
        out["retry_applied"] = True
        out["retry_via"] = "direct_google_api"
        out["retry_cost_usd"] = round(cost_state["spent"], 4)
        out["total_cost_usd"] = round(original.get("total_cost_usd", 0) + cost_state["spent"], 4)
        out["n_done"] = len(merged)
        out["stats"] = {"n": len(merged), "n_valid": len(valid),
                        "mean_J": round(st.mean(j), 3) if j else 0,
                        "mean_H": round(st.mean(h), 3) if h else 0,
                        "pass_agree_at_6": round(pa, 4)}
        tmp = out_path.with_suffix(".tmp")
        with open(tmp, "w") as f: json.dump(out, f, indent=2, ensure_ascii=False)
        os.replace(tmp, out_path)

    def merge_in(new_r):
        gid = new_r["grading_id"]
        for i, r in enumerate(results):
            if r["grading_id"] == gid:
                results[i] = new_r; return
        results.append(new_r)

    def worker(rec):
        prompt = (judge_template
                  .replace("{problem}", rec["problem"])
                  .replace("{ground_truth}", rec["solution"])
                  .replace("{candidate}", rec["response"]))
        t0 = time.time()
        try:
            content, usage = call_gemma(prompt)
            el = round(time.time() - t0, 2)
            score = parse_score(content)
            cost = round(PRICE_PER_M * usage["total_tokens"] / 1_000_000, 6)
            with cost_lock: cost_state["spent"] += cost
            d = (score - rec["human_points"]) if score is not None else None
            ds = f"D={d:+d}" if d is not None else "D=NA"
            print(f"[{_ts()}] {rec['grading_id']:<8} pts={rec['human_points']} score={score} {ds}  ${cost:.4f}  {el}s  thoughts={usage.get('reasoning_tokens',0)}  cum=${cost_state['spent']:.2f}", flush=True)
            new_r = {"grading_id": rec["grading_id"], "problem_id": rec["problem_id"],
                     "human_points": rec["human_points"], "source": rec["source"],
                     "score": score, "verdict": content, "usage": usage,
                     "cost": cost, "elapsed": el, "via": "direct_google"}
            with save_lock: merge_in(new_r); save_progress()
            return new_r
        except Exception as e:
            el = round(time.time() - t0, 2)
            print(f"[{_ts()}] FAIL {rec['grading_id']}: {str(e)[:100]}", flush=True)
            new_r = {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                     "score": None, "error": str(e), "cost": 0.0, "elapsed": el, "via": "direct_google"}
            with save_lock: merge_in(new_r); save_progress()
            return new_r

    if not to_retry:
        print("Nothing to retry."); return
    print(f"Starting {len(to_retry)} retries × {args.workers} workers via DIRECT Google API")
    save_progress()
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, r) for r in to_retry]
        for fut in concurrent.futures.as_completed(futs):
            try: fut.result()
            except Exception as e: print(f"outer fail: {e}", flush=True)

    el = round(time.time() - t0, 1)
    final_valid = sum(1 for r in results if r.get("score") is not None)
    print(f"\nDONE: {final_valid}/{len(results)} valid in {el}s, ${cost_state['spent']:.2f} spent")
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
