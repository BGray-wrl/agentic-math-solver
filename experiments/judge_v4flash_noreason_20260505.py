#!/usr/bin/env python3
"""
Re-run the judge_vs_human comparison for ONLY deepseek-v4-flash with
`reasoning.enabled=False`, on the same n=200 sample. Direct counterfactual
for the main experiment's reasoning-on baseline so we can attribute deltas
to "thinking on/off" rather than dataset noise.

Usage:
    uv run experiments/judge_v4flash_noreason_20260505.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import itertools
import json
import math
import os
import random
import re
import statistics as st
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
DATA_CSV = ROOT / "benchmarks" / "IMO-bench" / "gradingbench.csv"

JUDGE = "openrouter/deepseek/deepseek-v4-flash"
PRICE_PER_M = 0.28
EXTRA_BODY = {"reasoning": {"enabled": False}}

N_DEFAULT  = 200
SEED       = 42
MAX_WORKERS = 80
MAX_TOKENS = 65536
TIMEOUT    = 300
ROLL_EVERY_N = 25
ROLL_EVERY_S = 30.0
COST_CAP   = 5.0

load_dotenv()
KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_X2"),
] if k]
_iter = itertools.cycle(KEYS)
_lock = threading.Lock()
def next_key():
    with _lock: return next(_iter)


def _ts(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _mmss(s): s = max(0, int(s)); return f"{s//60:02d}:{s%60:02d}"


def call_judge(prompt: str, retries: int = 2, backoff: float = 4.0):
    last = None
    for attempt in range(retries + 1):
        try:
            resp = litellm.completion(
                model=JUDGE,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                api_key=next_key(),
                timeout=TIMEOUT,
                extra_body=EXTRA_BODY,
            )
            msg = resp.choices[0].message
            content = msg.content or getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
            if content is None:
                raise ValueError("None content")
            usage = resp.usage
            cd = getattr(usage, "completion_tokens_details", None)
            return content, {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
                "reasoning_tokens":  int(getattr(cd, "reasoning_tokens", 0) or 0) if cd else 0,
            }
        except Exception as e:
            last = e
            err = str(e)
            if "402" in err or "credit" in err.lower() or "insufficient" in err.lower():
                raise
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last


def parse_score(text: str):
    if not text: return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m:
        v = int(m.group(1))
        return v if 0 <= v <= 7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    return int(m.group(1)) if m else None


def bucket(s): return 0 if s <= 0 else (1 if s <= 3 else (6 if s <= 6 else 7))


def pearson(xs, ys):
    if len(xs) < 2: return None
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x-mx)**2 for x in xs))
    dy = math.sqrt(sum((y-my)**2 for y in ys))
    return num/(dx*dy) if dx > 0 and dy > 0 else None


def pct(vals, p):
    if not vals: return 0.0
    sv = sorted(vals); k = (len(sv)-1)*(p/100); f, c = math.floor(k), math.ceil(k)
    return sv[int(k)] if f == c else sv[f]*(c-k) + sv[c]*(k-f)


def stats_block(results, t_start):
    valid = [r for r in results if r.get("score") is not None]
    n = len(results); nv = len(valid)
    if nv == 0:
        return {"n": n, "n_valid": 0}
    h = [r["human_points"] for r in valid]
    j = [r["score"] for r in valid]
    abs_d = [abs(a-b) for a, b in zip(j, h)]
    deltas = [a-b for a, b in zip(j, h)]
    h_pass = [x>=6 for x in h]; j_pass = [x>=6 for x in j]
    agr6 = sum(1 for a,b in zip(h_pass, j_pass) if a==b)/nv
    flip = 1 - agr6
    raw_ex = sum(1 for a,b in zip(h, j) if a==b)/nv
    bk_ex  = sum(1 for a,b in zip(h, j) if bucket(a)==b)/nv
    r = pearson([float(x) for x in j], [float(x) for x in h]) or 0
    lat = [rr["elapsed"] for rr in results]
    rts = [rr["usage"].get("reasoning_tokens", 0) for rr in valid if rr.get("usage")]
    cost = sum(rr["cost"] for rr in results)
    return {
        "n": n, "n_valid": nv,
        "mean_J": round(st.mean(j), 3), "mean_H": round(st.mean(h), 3),
        "mean_abs_dev": round(st.mean(abs_d), 3), "mean_delta": round(st.mean(deltas), 3),
        "pearson_r": round(r, 3),
        "pass_agree_at_6": round(agr6, 4), "pass_flip_rate": round(flip, 4),
        "exact_raw": round(raw_ex, 4), "exact_bucketed": round(bk_ex, 4),
        "cost_usd": round(cost, 4),
        "latency_p50": round(pct(lat, 50), 1), "latency_p95": round(pct(lat, 95), 1),
        "mean_reasoning_tokens": int(st.mean(rts)) if rts else 0,
        "p95_reasoning_tokens":  int(pct(rts, 95)) if rts else 0,
    }


def print_rolling(results, n_total, t_start):
    el = time.time() - t_start
    nd = len(results)
    eta = (el/max(nd,1))*(n_total-nd) if nd > 0 else 0.0
    s = stats_block(results, t_start)
    print(f"\n=== ROLLING [elapsed {_mmss(el)}, {nd}/{n_total} done, ETA ~{_mmss(eta)}] ===", flush=True)
    if s.get("n_valid", 0):
        print(f"  n_valid={s['n_valid']}  mean_J={s['mean_J']:.2f}  mean_H={s['mean_H']:.2f}  "
              f"|Δ|={s['mean_abs_dev']:.2f}  r={s['pearson_r']:.2f}  "
              f"≥6-agree={s['pass_agree_at_6']*100:.1f}%  "
              f"exact_raw={s['exact_raw']*100:.1f}%  exact_b={s['exact_bucketed']*100:.1f}%  "
              f"${s['cost_usd']:.2f}  p50={s['latency_p50']:.1f}s  p95={s['latency_p95']:.1f}s  "
              f"rt_mean={s['mean_reasoning_tokens']}  rt_p95={s['p95_reasoning_tokens']}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_DEFAULT)
    args = ap.parse_args()

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()
    print(f"Loading {DATA_CSV.relative_to(ROOT)}…", flush=True)
    rows = []
    with open(DATA_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "grading_id": r["Grading ID"], "problem_id": r["Problem ID"],
                "problem":    r["Problem"], "solution": r["Solution"],
                "response":   r["Response"], "human_points": int(r["Points"]),
                "source":     r["Problem Source"],
            })
    rng = random.Random(SEED)
    sample = rng.sample(rows, min(args.n, len(rows)))
    print(f"  {len(rows)} total → sampled {len(sample)} (seed={SEED})", flush=True)
    print(f"  judge: {JUDGE}  extra_body={EXTRA_BODY}", flush=True)
    print(f"  workers: {MAX_WORKERS}, cost cap: ${COST_CAP}\n", flush=True)

    out_path = RESULTS_DIR / f"judge_v4flash_noreason_20260505_{_now()}.json"
    out_partial = out_path.with_name(out_path.stem + "_partial.json")

    cost_state = {"spent": 0.0}; cost_lock = threading.Lock()

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
            el = round(time.time()-t0, 2)
            score = parse_score(content)
            cost = round(PRICE_PER_M * usage["total_tokens"] / 1_000_000, 6)
            with cost_lock: cost_state["spent"] += cost
            d = (score - rec["human_points"]) if score is not None else None
            d_str = f"Δ={d:+d}" if d is not None else "Δ=NA"
            print(f"[{_ts()}] {rec['grading_id']:<8} pts={rec['human_points']} score={score} "
                  f"{d_str}  ${cost:.4f}  {el}s  rt={usage.get('reasoning_tokens',0)}", flush=True)
            return {"grading_id": rec["grading_id"], "problem_id": rec["problem_id"],
                    "human_points": rec["human_points"], "source": rec["source"],
                    "score": score, "verdict": content, "usage": usage,
                    "cost": cost, "elapsed": el}
        except Exception as e:
            el = round(time.time()-t0, 2)
            print(f"[{_ts()}] FAIL {rec['grading_id']}: {e}", flush=True)
            return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                    "score": None, "error": str(e), "cost": 0.0, "elapsed": el}

    results = []
    t_start = time.time()
    last_n, last_t = 0, t_start
    print(f"Starting at {_ts()} UTC …\n", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(worker, r) for r in sample]
        for fut in concurrent.futures.as_completed(futs):
            try: results.append(fut.result())
            except Exception as e: print(f"outer fail: {e}", flush=True)
            now = time.time()
            if (len(results)-last_n) >= ROLL_EVERY_N or (now-last_t) >= ROLL_EVERY_S:
                print_rolling(results, len(sample), t_start)
                with open(out_partial.with_suffix(".tmp"), "w") as f:
                    json.dump({"is_partial": True, "n_done": len(results), "n_total": len(sample),
                               "elapsed_s": round(now-t_start,1), "stats": stats_block(results, t_start),
                               "results": results}, f, ensure_ascii=False)
                os.replace(out_partial.with_suffix(".tmp"), out_partial)
                last_n, last_t = len(results), now

    el = round(time.time()-t_start, 1)
    s = stats_block(results, t_start)
    print(f"\n{'='*100}", flush=True)
    print(f"FINAL  v4-flash (reasoning OFF)  n_sampled={len(sample)}  done={len(results)}  "
          f"valid={s.get('n_valid',0)}  wall={_mmss(el)} ({el}s)  cost=${cost_state['spent']:.2f}", flush=True)
    print(f"{'='*100}\n", flush=True)
    print_rolling(results, len(sample), t_start)
    final = {
        "experiment": "judge_v4flash_noreason_20260505",
        "is_partial": False,
        "date": datetime.now(timezone.utc).isoformat(),
        "judge": JUDGE,
        "extra_body": EXTRA_BODY,
        "price_per_M": PRICE_PER_M,
        "n_sampled": len(sample), "n_done": len(results),
        "wall_clock_s": el,
        "total_cost_usd": round(cost_state["spent"], 4),
        "stats": s,
        "results": results,
    }
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}", flush=True)
    if out_partial.exists():
        try: out_partial.unlink()
        except OSError: pass


if __name__ == "__main__":
    main()
