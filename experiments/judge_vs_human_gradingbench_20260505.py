#!/usr/bin/env python3
"""
Judge-vs-human comparison on IMO-bench/gradingbench.csv.

Compares four candidate judge models against human Points (0-7) on a random
sample (n=200, seed=42) of the 1000 gradingbench records:
  - openrouter/google/gemini-3-flash-preview        ($3.00/M)
  - openrouter/deepseek/deepseek-v4-pro             ($0.87/M)
  - openrouter/deepseek/deepseek-v4-flash           ($0.28/M)
  - openrouter/openai/gpt-5.4-nano  (xhigh effort)  ($1.25/M)

Methodology mirrors the Phase 1/2 judge runs (judge_ablation_20260504.py and
gpt5_xhigh_compare_20260504.py): same hardened `judge_gt.md` prompt with
{problem, ground_truth, candidate}, same litellm wrappers, multi-key rotation,
retries on transient failures. Reports cost + accuracy + time-to-completion in
both rolling intermediate snapshots and the final summary.

Usage:
    uv run experiments/judge_vs_human_gradingbench_20260505.py --mock --n 8
    uv run experiments/judge_vs_human_gradingbench_20260505.py --verify-reasoning
    uv run experiments/judge_vs_human_gradingbench_20260505.py --n 8
    uv run experiments/judge_vs_human_gradingbench_20260505.py
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

# ----- Judges -----------------------------------------------------------------
GEMINI = "openrouter/google/gemini-3-flash-preview"
V4PRO  = "openrouter/deepseek/deepseek-v4-pro"
V4FLA  = "openrouter/deepseek/deepseek-v4-flash"
NANO   = "openrouter/openai/gpt-5.4-nano"

# $/M total tokens (matches prior experiments' simplified accounting)
PRICE = {GEMINI: 3.00, V4PRO: 0.87, V4FLA: 0.28, NANO: 1.25}
SHORT = {GEMINI: "gemini-3F", V4PRO: "v4-pro", V4FLA: "v4-flash", NANO: "gpt-5.4-nano"}
JUDGES = [GEMINI, V4PRO, V4FLA, NANO]

REASONING_EFFORT = "xhigh"           # for nano only
TIMEOUT_DEFAULT  = 600
TIMEOUT_NANO     = 1800              # xhigh nano can be slow
MAX_TOKENS_JUDGE = 65536
MAX_WORKERS      = 80
N_DEFAULT        = 200
SEED             = 42
COST_CAP_USD     = 20.0

# How often to print rolling summary + write partial JSON
ROLL_EVERY_N     = 25
ROLL_EVERY_S     = 60.0

# ----- Boilerplate ------------------------------------------------------------
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
            if not r.ok:
                live.append(k); continue
            d = r.json().get("data", {}) or {}
            limit = d.get("limit"); usage = d.get("usage", 0) or 0
            if limit is not None and usage >= limit:
                print(f"[startup] key#{i}: EXHAUSTED ({usage:.2f}/{limit}) — dropped")
            else:
                rem = (limit - usage) if limit else "unlimited"
                print(f"[startup] key#{i}: live (usage={usage:.2f}/{limit}, remain={rem})")
                live.append(k)
        except Exception as e:
            print(f"[startup] key#{i}: probe failed ({e}), including anyway")
            live.append(k)
    return live


KEYS: list[str] = []
_key_iter = None
_key_lock = threading.Lock()
def next_key():
    with _key_lock: return next(_key_iter)


def _ts(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _fmt_mmss(s: float) -> str:
    s = max(0, int(s))
    return f"{s//60:02d}:{s%60:02d}"


# ----- LLM call ---------------------------------------------------------------

def call_judge(model: str, prompt: str, retries: int = 2, backoff: float = 4.0):
    """Returns (content, usage_dict, reasoning_text). reasoning_text is None for non-reasoning models."""
    timeout = TIMEOUT_NANO if model == NANO else TIMEOUT_DEFAULT
    extra_body = {"reasoning": {"effort": REASONING_EFFORT}} if model == NANO else None
    last_err = None
    for attempt in range(retries + 1):
        key = next_key()
        try:
            kwargs = dict(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS_JUDGE,
                api_key=key,
                timeout=timeout,
            )
            if extra_body is not None:
                kwargs["extra_body"] = extra_body
            resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message  # type: ignore
            content = getattr(msg, "content", None)
            reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
            if content is None:
                content = reasoning
            if content is None:
                raise ValueError(f"{model} returned None content & None reasoning")
            usage = getattr(resp, "usage", None)
            usage_dict = {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
            }
            cd = getattr(usage, "completion_tokens_details", None)
            if cd is not None:
                usage_dict["reasoning_tokens"] = int(getattr(cd, "reasoning_tokens", 0) or 0)
            return content, usage_dict, reasoning
        except Exception as e:
            last_err = e
            err = str(e)
            if "402" in err or "credit" in err.lower() or "insufficient" in err.lower():
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {SHORT.get(model, model)} attempt {attempt+1}: {e} — retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


def parse_score(verdict_text: str) -> int | None:
    """Returns int 0..7 or None if no score parseable."""
    if not verdict_text:
        return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict_text, re.I)
    if m:
        v = int(m.group(1))
        return v if 0 <= v <= 7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict_text, re.I)
    if m:
        return int(m.group(1))
    classif = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif.items():
        if f"CLASSIFICATION: {label}" in verdict_text:
            return score
    return None


# ----- Data loading & sampling ------------------------------------------------

def load_records() -> list[dict]:
    rows = []
    with open(DATA_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "grading_id":  r["Grading ID"],
                "problem_id":  r["Problem ID"],
                "problem":     r["Problem"],
                "solution":    r["Solution"],          # ground truth
                "response":    r["Response"],          # candidate
                "human_points": int(r["Points"]),
                "source":      r["Problem Source"],
            })
    return rows


def sample_records(records: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    return rng.sample(records, min(n, len(records)))


# ----- Metrics ----------------------------------------------------------------

def bucket_human(score: int) -> int:
    """Map human 0–7 to nearest of {0,1,6,7} since the judge prompt only emits those."""
    if score <= 0: return 0
    if score <= 3: return 1
    if score <= 6: return 6
    return 7


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2: return None
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx > 0 and dy > 0 else None


def percentile(values: list[float], p: float) -> float | None:
    if not values: return None
    sv = sorted(values)
    k = (len(sv) - 1) * (p / 100.0)
    f = math.floor(k); c = math.ceil(k)
    if f == c: return sv[int(k)]
    return sv[f] * (c - k) + sv[c] * (k - f)


def per_judge_stats(results: list[dict]) -> dict:
    """Group by judge, compute headline stats."""
    by = {}
    for r in results:
        by.setdefault(r["judge"], []).append(r)
    out = {}
    for judge, rows in by.items():
        valid = [r for r in rows if r.get("score") is not None]
        n = len(rows)
        nv = len(valid)
        n_err = sum(1 for r in rows if r.get("error"))
        if nv == 0:
            out[judge] = {"n": n, "n_valid": 0, "n_errors": n_err, "cost": sum(r["cost"] for r in rows),
                          "wall": max((r["elapsed"] for r in rows), default=0.0)}
            continue
        h_raw  = [r["human_points"] for r in valid]
        j_raw  = [r["score"]        for r in valid]
        h_buck = [bucket_human(h)   for h in h_raw]
        deltas = [j - h for j, h in zip(j_raw, h_raw)]
        abs_d  = [abs(d) for d in deltas]
        h_pass = [h >= 6 for h in h_raw]
        j_pass = [j >= 6 for j in j_raw]
        agree6 = sum(1 for hp, jp in zip(h_pass, j_pass) if hp == jp) / nv
        flips  = sum(1 for hp, jp in zip(h_pass, j_pass) if hp != jp) / nv
        exactb = sum(1 for hb, jr in zip(h_buck, j_raw) if hb == jr) / nv
        latencies = [r["elapsed"] for r in rows]
        rt = [r.get("reasoning_tokens") for r in rows if r.get("reasoning_tokens") is not None]
        d = {
            "n": n, "n_valid": nv, "n_errors": n_err,
            "mean_human_score": round(st.mean(h_raw), 3),
            "mean_judge_score": round(st.mean(j_raw), 3),
            "mean_abs_dev":     round(st.mean(abs_d), 3),
            "mean_delta":       round(st.mean(deltas), 3),
            "pearson_r":        round(pearson([float(x) for x in j_raw], [float(x) for x in h_raw]) or 0.0, 3),
            "pass_agreement_at_6": round(agree6, 4),
            "pass_flip_rate":      round(flips, 4),
            "exact_match_bucketed": round(exactb, 4),
            "cost":             round(sum(r["cost"] for r in rows), 4),
            "wall":             round(sum(r["elapsed"] for r in rows), 1),  # cumulative compute
            "latency_p50":      round(percentile(latencies, 50) or 0.0, 1),
            "latency_p95":      round(percentile(latencies, 95) or 0.0, 1),
        }
        if rt:
            d["mean_reasoning_tokens"] = int(st.mean(rt))
            d["p50_reasoning_tokens"]  = int(percentile(rt, 50) or 0)
        out[judge] = d
    return out


# ----- Reporting --------------------------------------------------------------

def print_rolling(results: list[dict], n_total: int, t_start: float):
    elapsed = time.time() - t_start
    n_done = len(results)
    eta = (elapsed / max(n_done, 1)) * (n_total - n_done) if n_done > 0 else 0.0
    stats = per_judge_stats(results)
    print(f"\n=== ROLLING [elapsed {_fmt_mmss(elapsed)}, {n_done}/{n_total} done, overall ETA ~{_fmt_mmss(eta)}] ===", flush=True)
    print(f"{'judge':<14} {'n':>4} {'mean_J':>7} {'mean_H':>7} {'|Δ|':>5} {'≥6-agree':>9} {'exact_b':>8} {'r':>6} {'$cost':>7} {'p50/p95':>14}", flush=True)
    for judge in JUDGES:
        s = stats.get(judge)
        if not s:
            print(f"{SHORT[judge]:<14} {'-':>4}", flush=True); continue
        if s.get("n_valid", 0) == 0:
            print(f"{SHORT[judge]:<14} {s['n']:>4} (no valid yet, errs={s['n_errors']})", flush=True); continue
        lat = f"{s['latency_p50']:>5.1f}s/{s['latency_p95']:>5.1f}s"
        rtxt = f"  rt~{s.get('mean_reasoning_tokens',0)}" if "mean_reasoning_tokens" in s else ""
        print(f"{SHORT[judge]:<14} {s['n_valid']:>4} {s['mean_judge_score']:>7.2f} "
              f"{s['mean_human_score']:>7.2f} {s['mean_abs_dev']:>5.2f} "
              f"{s['pass_agreement_at_6']*100:>7.1f}%  {s['exact_match_bucketed']*100:>6.1f}%  "
              f"{s['pearson_r']:>6.2f} ${s['cost']:>6.2f}  {lat}{rtxt}", flush=True)
    print("", flush=True)


def write_partial(results: list[dict], n_total: int, t_start: float, out_path_partial: Path,
                  sample_ids: list[str], args_dict: dict):
    payload = {
        "experiment":    "judge_vs_human_gradingbench_20260505",
        "is_partial":    True,
        "n_total":       n_total,
        "n_done":        len(results),
        "elapsed_s":     round(time.time() - t_start, 1),
        "date":          datetime.now(timezone.utc).isoformat(),
        "judges":        JUDGES,
        "prices_per_M":  PRICE,
        "sample_grading_ids": sample_ids,
        "args":          args_dict,
        "per_judge":     per_judge_stats(results),
        "results":       results,
    }
    tmp = out_path_partial.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, out_path_partial)


# ----- Verify-reasoning preflight --------------------------------------------

def verify_reasoning(records: list[dict], judge_template: str):
    """Single live call to gpt-5.4-nano @ xhigh. Asserts xhigh is engaging."""
    rec = records[0]
    prompt = (judge_template
              .replace("{problem}",      rec["problem"])
              .replace("{ground_truth}", rec["solution"])
              .replace("{candidate}",    rec["response"]))
    print(f"\n[verify-reasoning] sending one live request to {NANO} @ xhigh on {rec['grading_id']}…", flush=True)
    t0 = time.time()
    content, usage, reasoning = call_judge(NANO, prompt, retries=1)
    elapsed = time.time() - t0
    score = parse_score(content)
    rt = usage.get("reasoning_tokens", 0)
    cost = PRICE[NANO] * usage["total_tokens"] / 1_000_000
    print(f"[verify-reasoning] elapsed={elapsed:.1f}s  score={score}  "
          f"reasoning_tokens={rt}  total_tokens={usage['total_tokens']}  cost=${cost:.4f}", flush=True)
    print(f"[verify-reasoning] response head: {content[:300]!r}", flush=True)
    if reasoning:
        print(f"[verify-reasoning] reasoning head: {str(reasoning)[:200]!r}", flush=True)
    problems = []
    if score is None or score not in (0, 1, 6, 7):
        problems.append(f"score not parseable / not in {{0,1,6,7}}: {score!r}")
    if rt < 1000:
        problems.append(f"reasoning_tokens={rt} < 1000 — xhigh likely was NOT engaged")
    if problems:
        print("\n[verify-reasoning] FAILED:", flush=True)
        for p in problems:
            print(f"  - {p}", flush=True)
        raise SystemExit(2)
    print("[verify-reasoning] OK — xhigh is engaging, score parses cleanly\n", flush=True)


# ----- Main worker ------------------------------------------------------------

def make_worker(judge_template: str, mock: bool, cost_state: dict, cost_lock: threading.Lock):
    def worker(task: dict) -> dict:
        rec = task["rec"]
        judge = task["judge"]
        # Cost cap check
        with cost_lock:
            if cost_state["spent"] >= COST_CAP_USD:
                return {**_skel(rec, judge), "error": f"cost cap ${COST_CAP_USD} hit", "cost": 0.0, "elapsed": 0.0}
        prompt = (judge_template
                  .replace("{problem}",      rec["problem"])
                  .replace("{ground_truth}", rec["solution"])
                  .replace("{candidate}",    rec["response"]))
        if mock:
            time.sleep(0.01)
            score = 7 if rec["human_points"] >= 4 else 0
            return {**_skel(rec, judge),
                    "score": score, "verdict": f"<points>{score} out of 7</points> mock",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
                    "reasoning_tokens": 5000 if judge == NANO else None,
                    "cost": 0.0, "elapsed": 0.01}
        t0 = time.time()
        try:
            content, usage, _reasoning = call_judge(judge, prompt)
            elapsed = round(time.time() - t0, 2)
            score = parse_score(content)
            cost = round(PRICE[judge] * usage["total_tokens"] / 1_000_000, 6)
            with cost_lock:
                cost_state["spent"] += cost
            rt = usage.get("reasoning_tokens")
            tag = f"[{_ts()}] {rec['grading_id']:<8} pts={rec['human_points']} judge={SHORT[judge]:<13}"
            d = (score - rec["human_points"]) if score is not None else None
            d_str = f"Δ={d:+d}" if d is not None else "Δ=NA"
            extra = f"   rt={rt}" if rt is not None else ""
            print(f"{tag} score={score}  {d_str}  ${cost:.4f}  {elapsed}s{extra}", flush=True)
            return {**_skel(rec, judge),
                    "score": score, "verdict": content, "usage": usage,
                    "reasoning_tokens": rt, "cost": cost, "elapsed": elapsed}
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            print(f"[{_ts()}] FAILED {rec['grading_id']} {SHORT[judge]}: {e}", flush=True)
            return {**_skel(rec, judge), "error": str(e), "cost": 0.0, "elapsed": elapsed}
    return worker


def _skel(rec: dict, judge: str) -> dict:
    return {
        "grading_id":   rec["grading_id"],
        "problem_id":   rec["problem_id"],
        "human_points": rec["human_points"],
        "source":       rec["source"],
        "judge":        judge,
        "score":        None,
        "verdict":      None,
        "usage":        None,
        "reasoning_tokens": None,
    }


# ----- Main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_DEFAULT, help="sample size (default 200)")
    ap.add_argument("--mock", action="store_true", help="no API calls, fixed scores")
    ap.add_argument("--verify-reasoning", action="store_true", help="single live call to nano @ xhigh, then exit")
    args = ap.parse_args()

    global KEYS, _key_iter
    if not args.mock:
        KEYS = _filter_live_keys(_ALL_KEYS)
        if not KEYS:
            raise SystemExit("No live keys")
    else:
        KEYS = ["mock"]
    _key_iter = itertools.cycle(KEYS)

    litellm.request_timeout = TIMEOUT_NANO

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()

    print(f"Loading {DATA_CSV.relative_to(ROOT)}…", flush=True)
    records = load_records()
    print(f"  {len(records)} total records", flush=True)
    sample = sample_records(records, args.n, SEED)
    print(f"  sampled {len(sample)} (seed={SEED})", flush=True)

    if args.verify_reasoning:
        verify_reasoning(sample, judge_template)
        return

    # Build shuffled task list — every judge appears in every batch
    tasks = [{"rec": r, "judge": j} for r in sample for j in JUDGES]
    random.Random(SEED).shuffle(tasks)
    n_total = len(tasks)
    print(f"  total judge calls planned: {n_total}  ({len(sample)} × {len(JUDGES)} judges)", flush=True)
    print(f"  workers: {MAX_WORKERS}, cost cap: ${COST_CAP_USD}", flush=True)

    out_path = RESULTS_DIR / f"judge_vs_human_gradingbench_20260505_{_now()}{'_mock' if args.mock else ''}.json"
    out_path_partial = out_path.with_name(out_path.stem + "_partial.json")

    cost_state = {"spent": 0.0}
    cost_lock = threading.Lock()
    worker = make_worker(judge_template, args.mock, cost_state, cost_lock)

    args_dict = {"n": args.n, "mock": args.mock, "seed": SEED, "max_workers": MAX_WORKERS, "cost_cap": COST_CAP_USD}
    sample_ids = [r["grading_id"] for r in sample]

    results: list[dict] = []
    t_start = time.time()
    last_roll_t = t_start
    last_roll_n = 0

    print(f"\nStarting run at {_ts()} UTC …\n", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(worker, t) for t in tasks]
        for fut in concurrent.futures.as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"[{_ts()}] outer exception: {e}", flush=True)
            now = time.time()
            n_done = len(results)
            if (n_done - last_roll_n >= ROLL_EVERY_N) or (now - last_roll_t >= ROLL_EVERY_S):
                print_rolling(results, n_total, t_start)
                write_partial(results, n_total, t_start, out_path_partial, sample_ids, args_dict)
                last_roll_t, last_roll_n = now, n_done

    elapsed_total = round(time.time() - t_start, 1)
    print(f"\n{'='*100}", flush=True)
    print(f"FINAL  —  judge_vs_human_gradingbench  —  n={len(sample)} sampled, {n_total} planned, {len(results)} done", flush=True)
    print(f"Wall: {_fmt_mmss(elapsed_total)} ({elapsed_total}s)   Total cost: ${cost_state['spent']:.2f}", flush=True)
    print(f"{'='*100}\n", flush=True)
    print_rolling(results, n_total, t_start)

    final = {
        "experiment":    "judge_vs_human_gradingbench_20260505",
        "is_partial":    False,
        "date":          datetime.now(timezone.utc).isoformat(),
        "judges":        JUDGES,
        "prices_per_M":  PRICE,
        "judge_prompt":  "prompts/pipeline/judge_gt.md",
        "data_csv":      str(DATA_CSV.relative_to(ROOT)),
        "n_sampled":     len(sample),
        "n_planned":     n_total,
        "n_done":        len(results),
        "wall_clock_s":  elapsed_total,
        "total_cost_usd": round(cost_state["spent"], 4),
        "args":          args_dict,
        "sample_grading_ids": sample_ids,
        "per_judge":     per_judge_stats(results),
        "results":       results,
    }
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}", flush=True)
    if out_path_partial.exists():
        try:
            out_path_partial.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
