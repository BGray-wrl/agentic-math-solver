#!/usr/bin/env python3
"""Run gemini-3.1-pro-preview (default reasoning effort) on the 38 PIDs of the
AnswerBench-50 set NOT covered by the 2026-05-04 expensive-models run.

Same methodology as `expensive_models_compare_20260504.py`:
- Generate-only, pass@1, seed=42
- MAX_TOKENS_GEN=65536, no reasoning param sent
- Judge = google/gemini-3.1-flash-lite-preview
- Parallel: 38 workers (one wave)
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
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import litellm  # noqa: E402

EXPERIMENT_NAME = "gemini3pro_answerbench50_remaining_20260507"

MODEL = "openrouter/google/gemini-3.1-pro-preview"
PRICE_PER_MTOKEN = 12.00
JUDGE_MODEL = "openrouter/google/gemini-3.1-flash-lite-preview"

SEED = 42
MAX_TOKENS_GEN = 65536
MAX_TOKENS_JUDGE = 4000
MAX_WORKERS = 38
TRIAL_TIMEOUT = 1500
LITELLM_TIMEOUT = 1400

# 38 remaining PIDs of the AnswerBench-50 set.
REMAINING_PIDS = [
    "imo-bench-algebra-014","imo-bench-algebra-015","imo-bench-algebra-018",
    "imo-bench-algebra-029","imo-bench-algebra-032","imo-bench-algebra-037",
    "imo-bench-algebra-071","imo-bench-algebra-083","imo-bench-algebra-096",
    "imo-bench-combinatorics-004","imo-bench-combinatorics-005",
    "imo-bench-combinatorics-012","imo-bench-combinatorics-030",
    "imo-bench-combinatorics-055","imo-bench-combinatorics-065",
    "imo-bench-combinatorics-072","imo-bench-combinatorics-076",
    "imo-bench-combinatorics-078","imo-bench-combinatorics-092",
    "imo-bench-geometry-001","imo-bench-geometry-044","imo-bench-geometry-054",
    "imo-bench-geometry-055","imo-bench-geometry-058","imo-bench-geometry-070",
    "imo-bench-geometry-076","imo-bench-geometry-090","imo-bench-geometry-098",
    "imo-bench-number_theory-012","imo-bench-number_theory-013",
    "imo-bench-number_theory-014","imo-bench-number_theory-020",
    "imo-bench-number_theory-028","imo-bench-number_theory-034",
    "imo-bench-number_theory-036","imo-bench-number_theory-044",
    "imo-bench-number_theory-046","imo-bench-number_theory-098",
]

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
ANSWERBENCH_CSV = ROOT / "benchmarks" / "IMO-bench" / "answerbench_v2.csv"
PRIOR_RUN_JSON = RESULTS_DIR / "answerbench_compare_20260504_20260504_084012.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


load_dotenv()
GEN_KEY = os.getenv("OPENROUTER_API_KEY_2")
JUDGE_KEY = os.getenv("OPENROUTER_API_KEY_X") or os.getenv("OPENROUTER_API_KEY")
if not GEN_KEY:
    raise SystemExit("No gen key (need price_compare or _2)")


def call_model(model, system, prompt, max_tokens, key, retries=2, backoff=4.0):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = litellm.completion(
                model=model, messages=messages, max_tokens=max_tokens,
                api_key=key, timeout=LITELLM_TIMEOUT,
            )
            content = resp.choices[0].message.content
            if content is None:
                content = getattr(resp.choices[0].message, "reasoning_content", None)
            if content is None:
                raise ValueError(f"None content from {model}")
            usage = getattr(resp, "usage", None)
            return content, {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
            }
        except Exception as e:
            last_err = e
            msg = str(e)
            if "402" in msg or "credit" in msg.lower():
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] attempt {attempt+1}: {e}, retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err


VERDICT_RE = re.compile(r"<verdict>\s*(correct|incorrect)\s*</verdict>", re.I)
def parse_verdict(text):
    if text is None: return None
    m = VERDICT_RE.search(text)
    if m: return 1 if m.group(1).lower() == "correct" else 0
    head = text[:200].lower()
    if "verdict>correct" in head or "answer is correct" in head: return 1
    if "verdict>incorrect" in head or "answer is incorrect" in head: return 0
    return None


def load_prompt(name): return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def load_problems():
    import csv
    with open(ANSWERBENCH_CSV, encoding="utf-8") as f:
        rows = {r["Problem ID"]: r for r in csv.DictReader(f)}
    selected = {}
    for pid in REMAINING_PIDS:
        if pid not in rows:
            raise SystemExit(f"{pid} missing from CSV")
        r = rows[pid]
        selected[pid] = {
            "text": r["Problem"].strip(),
            "short_answer": r["Short Answer"].strip(),
            "category": r["Category"],
            "subcategory": r.get("Subcategory", "").strip(),
            "source": r.get("Source", "").strip(),
        }
    return selected


def run_trial(pid, problem, prompts, mock):
    np.random.seed(SEED); random.seed(SEED)
    tag = f"[{_ts()}] [{pid}]"
    t0 = time.time()
    if mock:
        time.sleep(0.005)
        return _mk(pid, problem, 1, "mock", "<verdict>correct</verdict>",
                   {"prompt_tokens":100,"completion_tokens":50,"total_tokens":150},
                   {"prompt_tokens":200,"completion_tokens":20,"total_tokens":220},
                   0.005, 0.005, 0.01)

    print(f"{tag} generate", flush=True)
    g0 = time.time()
    try:
        gen_text, gen_usage = call_model(MODEL, prompts["generator"], problem["text"],
                                          MAX_TOKENS_GEN, GEN_KEY)
        gen_elapsed = round(time.time() - g0, 2)
        print(f"{tag} gen {gen_elapsed}s in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']}", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} GEN FAILED: {e} ({elapsed}s)", flush=True)
        return _err(pid, problem, str(e), elapsed)

    judge_prompt = (prompts["judge"]
                    .replace("{problem}", problem["text"])
                    .replace("{ground_truth}", problem["short_answer"])
                    .replace("{candidate}", gen_text))
    j0 = time.time()
    try:
        judge_text, judge_usage = call_model(JUDGE_MODEL, None, judge_prompt,
                                              MAX_TOKENS_JUDGE, JUDGE_KEY)
        judge_elapsed = round(time.time() - j0, 2)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} JUDGE FAILED: {e} ({elapsed}s)", flush=True)
        return _err(pid, problem, f"judge: {e}", elapsed,
                    gen_text=gen_text, gen_usage=gen_usage, gen_elapsed=gen_elapsed)

    score = parse_verdict(judge_text)
    elapsed = round(time.time() - t0, 2)
    s = "?" if score is None else str(score)
    print(f"{tag} -> verdict={s} total={elapsed}s", flush=True)
    return _mk(pid, problem, score, gen_text, judge_text, gen_usage, judge_usage,
               gen_elapsed, judge_elapsed, elapsed)


def _mk(pid, problem, score, gen_text, verdict, gen_usage, judge_usage,
        gen_elapsed, judge_elapsed, elapsed):
    est = round(PRICE_PER_MTOKEN * gen_usage["total_tokens"] / 1_000_000, 6) if gen_usage else None
    return {
        "problem_id": pid, "category": problem["category"],
        "subcategory": problem["subcategory"], "short_answer": problem["short_answer"],
        "model": MODEL, "seed": SEED, "score": score,
        "passed": bool(score) if score is not None else False,
        "elapsed_s": elapsed, "gen_elapsed_s": gen_elapsed,
        "judge_elapsed_s": judge_elapsed, "gen_usage": gen_usage,
        "judge_usage": judge_usage, "est_cost_usd": est,
        "final_solution": gen_text, "verdict": verdict,
    }


def _err(pid, problem, err, elapsed, gen_text=None, gen_usage=None, gen_elapsed=None):
    return {
        "problem_id": pid, "category": problem["category"],
        "subcategory": problem["subcategory"], "short_answer": problem["short_answer"],
        "model": MODEL, "seed": SEED, "score": None, "passed": False,
        "elapsed_s": elapsed, "gen_elapsed_s": gen_elapsed,
        "judge_elapsed_s": None, "gen_usage": gen_usage,
        "judge_usage": None, "est_cost_usd": None,
        "final_solution": gen_text, "verdict": None, "error": err,
    }


def _save(results, path):
    try:
        with open(path, "w") as f:
            json.dump({"experiment": EXPERIMENT_NAME, "partial": True,
                       "n_results": len(results), "results": results},
                      f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[{_ts()}] save warn: {e}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()
    prompts = {"generator": load_prompt("generator.md"),
               "judge": load_prompt("answerbench_judge.md")}

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Model: {MODEL}  default reasoning")
    print(f"Judge: {JUDGE_MODEL}")
    print(f"PIDs: {len(problems)}  workers: {MAX_WORKERS}")
    by_cat = {}
    for p in problems.values():
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    for c, n in sorted(by_cat.items()): print(f"  {c}: {n}")

    suffix = "_mock" if args.mock else ""
    partial_path = RESULTS_DIR / f"{EXPERIMENT_NAME}{suffix}_partial.json"
    print(f"Partial: {partial_path}", flush=True)

    t0 = time.time()
    results = []
    pids = sorted(problems.keys())
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(run_trial, pid, problems[pid], prompts, args.mock): pid for pid in pids}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * len(pids)):
            pid = futs[fut]
            try:
                r = fut.result(timeout=TRIAL_TIMEOUT)
            except Exception as e:
                print(f"[{_ts()}] FAILED {pid}: {e}", flush=True)
                traceback.print_exc()
                r = _err(pid, problems[pid], str(e), 0)
            results.append(r)
            _save(results, partial_path)

    wall = round(time.time() - t0, 1)
    print(f"\nWall: {wall}s, {len(results)} trials", flush=True)

    valid = [r for r in results if r["score"] is not None]
    n_correct = sum(r["score"] for r in valid)
    print(f"Acc: {n_correct}/{len(valid)} ({n_correct/max(1,len(valid))*100:.1f}%)")
    costs = [r["est_cost_usd"] for r in valid if r.get("est_cost_usd")]
    if costs:
        print(f"Cost: ${sum(costs):.3f} total, ${sum(costs)/len(costs):.4f}/run")

    out = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out, "w") as f:
        json.dump({"experiment": EXPERIMENT_NAME,
                   "date": datetime.now(timezone.utc).isoformat(),
                   "mock": args.mock, "seed": SEED,
                   "model": MODEL, "judge_model": JUDGE_MODEL,
                   "max_workers": MAX_WORKERS, "max_tokens_gen": MAX_TOKENS_GEN,
                   "remaining_pids": REMAINING_PIDS,
                   "wall_s": wall, "n_results": len(results),
                   "n_valid": len(valid), "n_correct": n_correct,
                   "all_results": results}, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
