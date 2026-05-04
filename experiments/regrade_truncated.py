"""
Re-grade trials where the judge verdict was truncated (no <points> tag).
Loads an existing results JSON, re-calls only the affected judge entries,
and writes a corrected results file.

Usage:
    uv run experiments/regrade_truncated.py experiments/results/gemini_gpt_cross_20260327_021112.json
    uv run experiments/regrade_truncated.py experiments/results/gemini_gpt_cross_20260327_021112.json --mock
"""

import sys
import re
import os
import json
import time
import argparse
import threading
import traceback
import concurrent.futures
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm
litellm.request_timeout = 540

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")

MAX_TOKENS_JUDGE = 16384
MAX_WORKERS = 12
PASS_THRESHOLD = 6

PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "pipeline"
JUDGE_PROMPT_PATH = PROMPTS_DIR / "judge.md"


def _ts():
    return datetime.utcnow().strftime("%H:%M:%S")


def parse_points_score(verdict_text: str):
    m = re.search(r"<points>\s*(\d)\s*out of 7\s*</points>", verdict_text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def call_llm(prompt: str, model: str, system, max_tokens: int):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = litellm.completion(model=model, messages=messages, max_tokens=max_tokens)
    content = resp.choices[0].message.content  # type: ignore
    if content is None:
        content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
    if content is None:
        raise ValueError(f"Model {model} returned None content")
    try:
        cost = litellm.completion_cost(completion_response=resp)
    except Exception:
        cost = 0.0
    return content, cost


def regrade_trial(result: dict, judge_prompt: str, mock: bool = False) -> dict:
    """Re-call the judge for a single result. Returns updated result dict."""
    problem_text  = result["problem_text"]
    ground_truth  = result["ground_truth"]
    solution      = result["solution"]
    judge_model   = result["judge_model"]
    problem_id    = result["problem_id"]
    seed          = result["seed"]

    judge_short = judge_model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|judge={judge_short}|seed={seed}]"

    gt_section = f"**GROUND TRUTH SOLUTION:**\n{ground_truth}"
    sys_part, sep, content = judge_prompt.partition("\n**PROBLEM:**\n")
    if sep:
        judge_sys = sys_part.strip()
        judge_content = (
            "**PROBLEM:**\n" + content
            .replace("{problem}", problem_text)
            .replace("{ground_truth_section}", gt_section)
            .replace("{candidate}", solution)
        )
    else:
        judge_sys = None
        judge_content = (
            judge_prompt
            .replace("{problem}", problem_text)
            .replace("{ground_truth_section}", gt_section)
            .replace("{candidate}", solution)
        )

    print(f"{tag} re-judging → {judge_short} (max_tokens={MAX_TOKENS_JUDGE})", flush=True)
    ts_start = time.time()
    try:
        if mock:
            verdict_text, cost = "The solution is correct. <points>4 out of 7</points>", 0.0
        else:
            verdict_text, cost = call_llm(judge_content, judge_model, judge_sys, MAX_TOKENS_JUDGE)
    except Exception as e:
        print(f"{tag} ERROR: {e}\n{traceback.format_exc()}", flush=True)
        raise

    score = parse_points_score(verdict_text)
    elapsed = round(time.time() - ts_start, 2)

    if score is None:
        print(f"{tag} WARNING: still no <points> tag after re-grade. Defaulting to 0.", flush=True)
        score = 0

    print(f"{tag} → {score}/7  ({len(verdict_text)} chars)  {elapsed}s  ${cost:.4f}", flush=True)

    updated = dict(result)
    updated.pop("problem_text", None)
    updated.pop("ground_truth", None)
    updated["score"]    = score
    updated["pass"]     = score >= PASS_THRESHOLD
    updated["verdict"]  = verdict_text
    updated["cost_usd"] = result.get("cost_usd", 0.0) + cost
    updated["regraded"] = True
    return updated


def main():
    parser = argparse.ArgumentParser(description="Re-grade truncated verdicts in a results JSON")
    parser.add_argument("results_file", help="Path to the results JSON to fix")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    results_path = Path(args.results_file)
    with open(results_path, encoding="utf-8") as f:
        data = json.load(f)

    judge_prompt = JUDGE_PROMPT_PATH.read_text(encoding="utf-8").strip()

    # Build a lookup of problem_text and ground_truth from the BENCHMARKS CSV
    import csv
    benchmarks_csv = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
    problem_lookup = {}
    with open(benchmarks_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            problem_lookup[row["Problem ID"]] = {
                "text":     row["Problem"],
                "solution": row["Solution"],
            }

    all_results = data["all_results"]

    # Identify trials to re-grade: verdict missing <points> tag
    to_regrade = []
    to_keep    = []
    for r in all_results:
        verdict = r.get("verdict", "")
        if verdict and "<points>" not in verdict:
            pid = r["problem_id"]
            enriched = dict(r)
            enriched["problem_text"]  = problem_lookup[pid]["text"]
            enriched["ground_truth"]  = problem_lookup[pid]["solution"]
            to_regrade.append(enriched)
        else:
            to_keep.append(r)

    print(f"Loaded {len(all_results)} results from {results_path.name}")
    print(f"Need to re-grade: {len(to_regrade)}  |  Already valid: {len(len(to_keep) and to_keep or to_keep)}")
    print(f"Judge max_tokens: {MAX_TOKENS_JUDGE}")
    if args.mock:
        print("[MOCK MODE]")
    print()

    regraded = []
    completed = 0
    total_regrade_cost = 0.0
    cost_lock = threading.Lock()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_r = {
            executor.submit(regrade_trial, r, judge_prompt, args.mock): r
            for r in to_regrade
        }
        for future in concurrent.futures.as_completed(future_to_r):
            orig = future_to_r[future]
            completed += 1
            try:
                updated = future.result(timeout=300)
                regraded.append(updated)
                with cost_lock:
                    total_regrade_cost += updated.get("cost_usd", 0.0) - orig.get("cost_usd", 0.0)
            except Exception as e:
                print(f"[{_ts()}] FAILED {orig['problem_id']} seed={orig['seed']}: {e}", flush=True)
                regraded.append(orig)  # keep original on failure
            if completed % 10 == 0 or completed == len(to_regrade):
                with cost_lock:
                    cur = total_regrade_cost
                print(f"[{_ts()}] Progress: {completed}/{len(to_regrade)}  regrade cost=${cur:.4f}", flush=True)
            else:
                print(f"[{_ts()}] Progress: {completed}/{len(to_regrade)}", flush=True)

    # Merge and re-aggregate
    all_updated = to_keep + regraded

    parse_fails_after = sum(
        1 for r in all_updated
        if r.get("verdict") and "<points>" not in r.get("verdict", "") and not r.get("error")
    )
    total_cost = sum(r.get("cost_usd", 0.0) for r in all_updated)

    print(f"\nParse fails after re-grade: {parse_fails_after}/{len(all_updated)}")
    print(f"Re-grade cost: ${total_regrade_cost:.4f}  |  Total cumulative cost: ${total_cost:.4f}")

    # Summary table
    gen_judge_pairs = data.get("generator_judge_pairs", [])
    problem_ids = data.get("problems", sorted({r["problem_id"] for r in all_updated}))

    print("\n" + "=" * 70)
    print("UPDATED RESULTS SUMMARY")
    print("=" * 70)

    for gen_model, judge_model in gen_judge_pairs:
        gen_short   = gen_model.split("/")[-1]
        judge_short = judge_model.split("/")[-1]
        print(f"\n  Generator: {gen_short}  |  Judge: {judge_short}")

        valid = [r for r in all_updated if r["gen_model"] == gen_model and r.get("score") is not None]
        scores = [r["score"] for r in valid]

        pass_per_problem = {}
        for pid in problem_ids:
            pid_scores = [r["score"] for r in valid if r["problem_id"] == pid]
            if pid_scores:
                pass_per_problem[pid] = any(s >= PASS_THRESHOLD for s in pid_scores)

        pass2_rate = np.mean(list(pass_per_problem.values())) if pass_per_problem else 0.0

        if scores:
            print(f"  Overall   mean={np.mean(scores):.3f}±{np.std(scores):.3f}  pass@2={pass2_rate:.1%}  n={len(scores)}")

        levels = sorted({r["level"] for r in valid if r.get("level")})
        for level in levels:
            lv = [r for r in valid if r["level"] == level]
            lv_scores = [r["score"] for r in lv]
            lv_pass = {}
            for pid in [p for p in problem_ids if any(r["problem_id"] == p and r["level"] == level for r in valid)]:
                ps = [r["score"] for r in lv if r["problem_id"] == pid]
                if ps:
                    lv_pass[pid] = any(s >= PASS_THRESHOLD for s in ps)
            lv_pass2 = np.mean(list(lv_pass.values())) if lv_pass else 0.0
            print(f"  {level:<12} mean={np.mean(lv_scores):.3f}±{np.std(lv_scores):.3f}  pass@2={lv_pass2:.1%}  n={len(lv_scores)}")

    # Per-problem table
    print("\n--- Per-problem scores ---")
    for pid in problem_ids:
        level = next((r["level"] for r in all_updated if r["problem_id"] == pid), "?")
        row = f"{pid:<22} {level:<12}"
        for gen_model, judge_model in gen_judge_pairs:
            r_list = [r for r in all_updated if r["problem_id"] == pid and r["gen_model"] == gen_model and r.get("score") is not None]
            if r_list:
                s = [r["score"] for r in r_list]
                passed = "✓" if any(x >= PASS_THRESHOLD for x in s) else " "
                row += f"  {np.mean(s):4.1f}±{np.std(s):.1f}{passed}  [{'/'.join(str(x) for x in s)}]"
            else:
                row += f"  {'—':>15}"
        print(row)

    # Save corrected results
    suffix = "_mock" if args.mock else ""
    out_path = results_path.parent / (results_path.stem + f"_regraded{suffix}.json")
    data_out = dict(data)
    data_out["all_results"]    = all_updated
    data_out["total_cost_usd"] = round(total_cost, 6)
    data_out["regraded"]       = True

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data_out, f, indent=2, ensure_ascii=False)
    print(f"\nSaved corrected results to: {out_path}")


if __name__ == "__main__":
    main()
