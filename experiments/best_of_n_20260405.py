#!/usr/bin/env python3
"""
Best-of-N experiment: does generating more diverse ideas improve best-of-N score?

Vary N (number of ideas/branches) with generate-only + judge (no verify/revise).
For each N, ideate N ideas, generate N solutions, judge all, pick best.

  N = 1, 3, 5, 7
  Ideator: gemini-3.1-flash-lite (best from Gemini ideator experiments)
  Generators: deepseek-v3.2, gpt-oss-120b
  Problems: devset (6 problems)
  Mode: generate-only + judge

Total: 4 N-values × 2 generators × 6 problems × 1 seed = 48 trials
Each trial spawns N parallel branches, so total branches = (1+3+5+7) × 2 × 6 = 192

Usage:
    uv run experiments/best_of_n_20260405.py --mock
    uv run experiments/best_of_n_20260405.py
"""

from __future__ import annotations

import sys
import csv
import json
import re
import time
import random
import argparse
import threading
import concurrent.futures
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402
from devset import select_devset, DEV_SET

# ============================================================================
# CONFIGURATION
# ============================================================================

EXPERIMENT_NAME = "best_of_n"

DESCRIPTION = """
Hypothesis: Generating more diverse ideas (higher N) improves best-of-N score,
with diminishing returns. Tests whether diversity alone (without verify/revise)
can match or beat the full pipeline.

Variables:
  Independent: N (number of ideas/branches) = 1, 3, 5, 7
  Dependent:   best-of-N judge score (0-7), mean score, score distribution
  Controlled:  ideator model, generator model, judge model, prompts, seed
"""

# --- Models ---
IDEATOR = "openrouter/google/gemini-3.1-flash-lite-preview"
DS  = "openrouter/deepseek/deepseek-v3.2"
OSS = "openrouter/openai/gpt-oss-120b"
GENERATORS = [DS, OSS]

JUDGE_MODEL = "gemini/gemini-3-flash-preview"

# --- N values to test ---
N_VALUES = [1, 3, 5, 7]

SEEDS = [42]
PASS_THRESHOLD = 6
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 24  # aggressive parallelism
TRIAL_TIMEOUT = 1800
LITELLM_TIMEOUT = 540

# Build conditions: one per (N, generator) pair
CONDITIONS = {}
cond_idx = 1
for n_val in N_VALUES:
    for gen_model in GENERATORS:
        gen_short = "ds" if "deepseek" in gen_model else "oss"
        CONDITIONS[cond_idx] = {
            "name": f"n{n_val}-{gen_short}",
            "n_ideas": n_val,
            "ideator": IDEATOR,
            "generator": gen_model,
        }
        cond_idx += 1


# ============================================================================
# Machinery
# ============================================================================

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def _now():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def parse_gt_score(verdict: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m:
        return int(m.group(1))
    classif_map = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif_map.items():
        if f"CLASSIFICATION: {label}" in verdict:
            return score
    return 0


def load_problems():
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return select_devset(rows)


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _short(model: str) -> str:
    return model.split("/")[-1][:16]


def run_branch(
    problem_id, problem, cond_id, cond, seed, idea_idx, idea,
    prompts, log_path, log_lock, tag, mock=False,
):
    """Run one branch: generate → judge (no verify/revise)."""
    from pipeline import generate, judge, make_logger

    gen_model = cond["generator"]
    btag = f"{tag}[b{idea_idx}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # Generate with seeded idea
    if idea is not None:
        gen_prompt = prompts["generator_seeded"].replace(
            "{idea}", f"**{idea['name']}**: {idea['description']}"
        )
        print(f"{btag} generate ({_short(gen_model)}, idea={idea['name'][:30]})", flush=True)
    else:
        gen_prompt = prompts["generator"]
        print(f"{btag} generate ({_short(gen_model)})", flush=True)

    solution = generate(
        problem=problem["text"], system=gen_prompt, model=gen_model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{btag} generated ({len(solution)} chars, {time.time()-t0:.1f}s)", flush=True)

    # Judge
    gt = problem["solution"]
    judge_prompt = prompts["judge_gt"] if gt else prompts["judge_nogt"]
    print(f"{btag} judge", flush=True)
    verdict_text = judge(
        problem=problem["text"], candidate=solution, ground_truth=gt,
        system=judge_prompt, model=JUDGE_MODEL,
        max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
        extract_prompt=prompts["extract_score"],
    )
    score = parse_gt_score(verdict_text)
    elapsed = round(time.time() - t0, 2)
    print(f"{btag} → {score}/7 ({elapsed}s)", flush=True)

    return {
        "idea_idx": idea_idx,
        "idea": idea,
        "score": score,
        "elapsed_s": elapsed,
        "final_solution": solution,
        "verdict": verdict_text,
    }


def run_trial(
    problem_id, problem, cond_id, cond, seed, prompts, log_path, log_lock, mock=False,
):
    """Run one trial: ideate N ideas → N parallel branches → pick best."""
    from pipeline import ideate, make_logger

    np.random.seed(seed)
    random.seed(seed)

    cname = cond["name"]
    n_ideas = cond["n_ideas"]
    tag = f"[{_ts()}] [c{cond_id}:{cname}|{problem_id}|s{seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # Ideate
    if n_ideas > 0:
        print(f"{tag} ideate (n={n_ideas}, {_short(cond['ideator'])})", flush=True)
        ideas = ideate(
            problem=problem["text"], system=prompts["ideator"],
            model=cond["ideator"], max_tokens=4096, logger=logger,
            num_ideas=n_ideas, mock=mock,
        )
        # Trim to requested N (model may return more or fewer)
        ideas = ideas[:n_ideas]
        print(f"{tag} got {len(ideas)} ideas: {[i['name'] for i in ideas]}", flush=True)
    else:
        ideas = [None]

    # Run branches in parallel
    branches = []
    if len(ideas) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(ideas)) as ex:
            futs = {
                ex.submit(run_branch, problem_id, problem, cond_id, cond, seed,
                          idx, idea, prompts, log_path, log_lock, tag, mock): idx
                for idx, idea in enumerate(ideas)
            }
            for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT):
                try:
                    branches.append(fut.result(timeout=TRIAL_TIMEOUT))
                except Exception as e:
                    idx = futs[fut]
                    print(f"{tag} branch {idx} FAILED: {e}", flush=True)
                    branches.append({"idea_idx": idx, "idea": ideas[idx], "score": 0, "error": str(e)})
    else:
        idea = ideas[0] if ideas else None
        branch = run_branch(
            problem_id, problem, cond_id, cond, seed, 0, idea,
            prompts, log_path, log_lock, tag, mock,
        )
        branches.append(branch)

    # Pick best
    branches.sort(key=lambda b: b.get("score", 0), reverse=True)
    best = branches[0]
    all_scores = [b.get("score", 0) for b in branches]

    elapsed = round(time.time() - t0, 2)
    print(f"{tag} best={best.get('score',0)}/7 (all: {all_scores}) {elapsed}s", flush=True)

    return {
        "condition_id": cond_id,
        "condition_name": cname,
        "n_ideas": n_ideas,
        "problem_id": problem_id,
        "level": problem["level"],
        "role": problem.get("role", ""),
        "seed": seed,
        "score": best.get("score", 0),
        "passed": best.get("score", 0) >= PASS_THRESHOLD,
        "all_branch_scores": all_scores,
        "best_idea_idx": best.get("idea_idx"),
        "elapsed_s": elapsed,
        "final_solution": best.get("final_solution"),
        "verdict": best.get("verdict"),
        "branches": branches,
        "models": {
            "generator": _short(cond["generator"]),
            "ideator": _short(cond["ideator"]),
        },
    }


def run_all(conditions, problems, prompts, mock):
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    trials = [
        (cid, pid, seed)
        for cid in sorted(conditions)
        for pid in sorted(problems)
        for seed in SEEDS
    ]
    total = len(trials)
    print(f"\nSubmitting {total} trials "
          f"({len(conditions)} conditions × {len(problems)} problems × {len(SEEDS)} seeds)\n",
          flush=True)

    results = []
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {
            ex.submit(run_trial, pid, problems[pid], cid, conditions[cid],
                      seed, prompts, log_path, log_lock, mock): (cid, pid, seed)
            for cid, pid, seed in trials
        }
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            cid, pid, seed = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                cname = conditions[cid]["name"]
                print(f"[{_ts()}] FAILED [c{cid}:{cname}|{pid}|s{seed}]: {e}", flush=True)
                results.append({
                    "condition_id": cid, "condition_name": cname,
                    "n_ideas": conditions[cid]["n_ideas"],
                    "problem_id": pid, "level": problems[pid]["level"],
                    "role": problems[pid].get("role", ""), "seed": seed,
                    "score": None, "passed": False, "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    return results, log_path


def _mean_score(results, cond_id):
    valid = [r for r in results if r["condition_id"] == cond_id and r.get("score") is not None]
    if not valid:
        return None, 0
    return sum(r["score"] for r in valid) / len(valid), len(valid)


def print_results(results, conditions, problems):
    pids = sorted(problems.keys())
    cids = sorted(conditions.keys())

    print(f"\n{'='*100}")
    print("BEST-OF-N EXPERIMENT — RESULTS")
    print(f"{'='*100}\n")

    # Per-condition summary
    print(f"{'Cond':>4}  {'Name':<16} {'N':>2} {'Mean':>6} {'Pass':>6} {'Err':>4}  {'Mean All Scores'}")
    print("-" * 80)
    for cid in cids:
        cond = conditions[cid]
        valid = [r for r in results if r["condition_id"] == cid and r.get("score") is not None]
        errs = sum(1 for r in results if r["condition_id"] == cid and r.get("error"))
        if valid:
            scores = [r["score"] for r in valid]
            n_pass = sum(1 for r in valid if r["passed"])
            mean = sum(scores) / len(scores)
            # Mean of all branch scores (not just best)
            all_branch_means = []
            for r in valid:
                if r.get("all_branch_scores"):
                    all_branch_means.extend(r["all_branch_scores"])
            mean_all = sum(all_branch_means) / len(all_branch_means) if all_branch_means else 0
            err_s = str(errs) if errs else ""
            print(f"  {cid:>2}   {cond['name']:<16} {cond['n_ideas']:>2}  {mean:5.2f}/7  "
                  f"{n_pass:>2}/{len(valid):<2} {err_s:>4}  mean_all={mean_all:.2f}/7")
        else:
            print(f"  {cid:>2}   {cond['name']:<16}  (all errors, n={errs})")

    # N scaling comparison
    print(f"\n{'─'*100}")
    print("\nBEST-OF-N SCALING:\n")

    for gen_label, gen_model in [("DeepSeek", DS), ("GPT-OSS", OSS)]:
        print(f"  {gen_label}:")
        gen_short = "ds" if "deepseek" in gen_model else "oss"
        for n_val in N_VALUES:
            cid = [c for c, v in conditions.items() if v["n_ideas"] == n_val and gen_short in v["name"]]
            if cid:
                mean, n = _mean_score(results, cid[0])
                if mean is not None:
                    # Also compute mean of ALL branch scores to see raw generation quality
                    valid = [r for r in results if r["condition_id"] == cid[0] and r.get("score") is not None]
                    all_scores = []
                    for r in valid:
                        if r.get("all_branch_scores"):
                            all_scores.extend(r["all_branch_scores"])
                    mean_all = sum(all_scores)/len(all_scores) if all_scores else 0
                    print(f"    N={n_val:>2}:  best={mean:.2f}/7  mean_all={mean_all:.2f}/7  (n={n})")
        print()

    # Per-problem breakdown
    print(f"{'─'*100}")
    print("\nPer-problem best scores:\n")

    hdr = f"  {'Problem':<16}"
    for cid in cids:
        hdr += f" {conditions[cid]['name']:>8}"
    print(hdr)
    print()

    for pid in pids:
        row = f"  {pid:<16}"
        for cid in cids:
            trial = [r for r in results if r["condition_id"] == cid
                     and r["problem_id"] == pid and r.get("score") is not None]
            if trial:
                r = trial[0]
                s = r["score"]
                all_s = r.get("all_branch_scores", [s])
                row += f" {s:>3}({','.join(str(x) for x in all_s)})"
            else:
                row += f" {'—':>8}"
        print(row)

    # Diversity analysis: how often does best-of-N beat mean?
    print(f"\n{'─'*100}")
    print("\nDIVERSITY UPLIFT (best - mean_branch):\n")
    for cid in cids:
        cond = conditions[cid]
        valid = [r for r in results if r["condition_id"] == cid and r.get("score") is not None]
        uplifts = []
        for r in valid:
            if r.get("all_branch_scores") and len(r["all_branch_scores"]) > 1:
                best = max(r["all_branch_scores"])
                mean_b = sum(r["all_branch_scores"]) / len(r["all_branch_scores"])
                uplifts.append(best - mean_b)
        if uplifts:
            avg_uplift = sum(uplifts) / len(uplifts)
            print(f"  {cond['name']:<16} N={cond['n_ideas']:>2}  avg_uplift={avg_uplift:+.2f}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Best-of-N experiment")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--conditions", type=str, default=None,
                        help="Comma-separated condition IDs to run (default: all)")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    if args.conditions:
        cond_ids = [int(x.strip()) for x in args.conditions.split(",")]
        conditions = {k: v for k, v in CONDITIONS.items() if k in cond_ids}
    else:
        conditions = CONDITIONS

    problems = load_problems()

    n_trials = len(conditions) * len(problems) * len(SEEDS)
    total_branches = sum(conditions[c]["n_ideas"] for c in conditions) * len(problems) * len(SEEDS)
    print(f"Best-of-N Experiment")
    print(f"  {len(conditions)} conditions × {len(problems)} problems × {len(SEEDS)} seeds = {n_trials} trials")
    print(f"  Total branches (generate+judge calls): {total_branches}")
    print(f"  Ideator: {_short(IDEATOR)}")
    print(f"  Judge: {_short(JUDGE_MODEL)}")
    print(f"  Workers: {MAX_WORKERS}  Timeout: {TRIAL_TIMEOUT}s")
    print()

    for cid, cond in sorted(conditions.items()):
        print(f"  c{cid:>2}: {cond['name']:<16} N={cond['n_ideas']}  gen={_short(cond['generator'])}")
    print()

    prompts = {
        "generator":        load_prompt("generator.md"),
        "generator_seeded": load_prompt("generator_seeded.md"),
        "ideator":          load_prompt("ideator.md"),
        "judge_gt":         load_prompt("judge_gt.md"),
        "judge_nogt":       load_prompt("judge_nogt.md"),
        "extract_score":    load_prompt("extract_score.md"),
    }

    results, log_path = run_all(conditions, problems, prompts, args.mock)
    print_results(results, conditions, problems)

    # Save
    ts = _now()
    suffix = "_mock" if args.mock else ""
    output = {
        "experiment": EXPERIMENT_NAME,
        "description": DESCRIPTION.strip(),
        "date": datetime.now(timezone.utc).isoformat(),
        "conditions": {str(k): v for k, v in conditions.items()},
        "n_values": N_VALUES,
        "seeds": SEEDS,
        "pass_threshold": PASS_THRESHOLD,
        "judge_model": JUDGE_MODEL,
        "ideator_model": IDEATOR,
        "mock": args.mock,
        "dev_set": {pid: DEV_SET[pid] for pid in sorted(problems)},
        "all_results": results,
    }
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
