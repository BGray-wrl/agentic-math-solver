#!/usr/bin/env python3
"""
Pruning ideation experiment: can a cheap ranker predict the best idea?

Generate N=7 ideas, then compare:
  - all-7: run all 7 branches, pick best (oracle upper bound)
  - prune-to-3: use cheap ranker to pick top 3, run those, pick best
  - prune-to-1: use cheap ranker to pick top 1, run just that
  - no-rank-3: randomly pick 3 (no ranker), pick best (ablation)

Also: for the all-7 condition, record which idea won. Then separately
run the ranker on the same ideas and check if the ranker's top pick
matches the actual best-scoring branch (idea-prediction accuracy).

  Problems: devset (6 problems)
  Ideator: gemini-3.1-flash-lite
  Ranker: gemini-3.1-flash-lite (same-power test)
  Generator: deepseek-v3.2 (generate-only mode for speed)
  N_IDEAS = 7

Total: 4 conditions × 6 problems × 1 seed = 24 trials
  all-7:      7 branches each = 42 branches
  prune-to-3: 3 branches each = 18 branches
  prune-to-1: 1 branch each  = 6 branches
  no-rank-3:  3 branches each = 18 branches
  Total branches: 84

Usage:
    uv run experiments/pruning_ideation_20260405.py --mock
    uv run experiments/pruning_ideation_20260405.py
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

EXPERIMENT_NAME = "pruning_ideation"

DESCRIPTION = """
Hypothesis: A cheap ranker model can predict which ideas will produce the
best solutions, enabling early pruning that saves compute without sacrificing
quality. If ranker accuracy is high, we can get best-of-7 quality with
best-of-1 cost.

Variables:
  Independent: pruning strategy (all-7, prune-3, prune-1, random-3)
  Dependent:   best-of-K score, ranker prediction accuracy
  Controlled:  ideator, generator, judge, problem set, seed
"""

# --- Models ---
IDEATOR = "openrouter/google/gemini-3.1-flash-lite-preview"
RANKER  = "openrouter/google/gemini-3.1-flash-lite-preview"  # same-power test
GENERATOR = "openrouter/deepseek/deepseek-v3.2"

JUDGE_MODEL = "gemini/gemini-3-flash-preview"

N_IDEAS = 7
SEEDS = [42]
PASS_THRESHOLD = 6
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 24
TRIAL_TIMEOUT = 1800
LITELLM_TIMEOUT = 540

# Conditions:
# All share the same ideation step (cached), differ in which branches run
CONDITIONS = {
    1: {"name": "all-7",      "k_branches": 7, "use_ranker": False, "description": "Oracle: run all 7, pick best"},
    2: {"name": "prune-to-3", "k_branches": 3, "use_ranker": True,  "description": "Ranker picks top 3, run those"},
    3: {"name": "prune-to-1", "k_branches": 1, "use_ranker": True,  "description": "Ranker picks top 1, run just that"},
    4: {"name": "random-3",   "k_branches": 3, "use_ranker": False, "description": "Random 3 (no ranker), ablation"},
}


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


def rank_ideas(problem_text: str, ideas: list[dict], ranker_prompt: str,
               log_path, log_lock, mock=False) -> list[int]:
    """Use ranker model to rank ideas. Returns ordered indices (best first)."""
    from pipeline import _call_llm, make_logger

    ideas_text = "\n".join(
        f"{i}. **{idea['name']}**: {idea['description']}"
        for i, idea in enumerate(ideas)
    )
    prompt = ranker_prompt.replace("{problem}", problem_text).replace("{ideas}", ideas_text)

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()
    if mock:
        # Mock: return original order
        response = f"```json\n{json.dumps(list(range(len(ideas))))}\n```"
    else:
        response = _call_llm("", prompt, RANKER, 1024)

    logger("rank_ideas", 0, RANKER, "", prompt, response, time.time() - t0)

    # Parse ranking
    ranking = None
    for pattern in [r"```json\s*(\[.*?\])\s*```", r"(\[[\d,\s]+\])"]:
        m = re.search(pattern, response, re.DOTALL)
        if m:
            try:
                ranking = json.loads(m.group(1))
                break
            except json.JSONDecodeError:
                continue

    if not ranking or not all(isinstance(x, int) for x in ranking):
        # Fallback: original order
        ranking = list(range(len(ideas)))

    return ranking


def run_branch(
    problem_id, problem, seed, idea_idx, idea,
    prompts, log_path, log_lock, tag, mock=False,
):
    """Run one branch: generate → judge (generate-only)."""
    from pipeline import generate, judge, make_logger

    btag = f"{tag}[b{idea_idx}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # Generate with seeded idea
    gen_prompt = prompts["generator_seeded"].replace(
        "{idea}", f"**{idea['name']}**: {idea['description']}"
    )
    print(f"{btag} generate ({_short(GENERATOR)}, idea={idea['name'][:30]})", flush=True)

    solution = generate(
        problem=problem["text"], system=gen_prompt, model=GENERATOR,
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


# We share ideation across conditions to keep ideas identical.
# Cache: (problem_id, seed) → (ideas, ranking)
_idea_cache = {}
_idea_cache_lock = threading.Lock()


def get_or_create_ideas(problem_id, problem, seed, prompts, log_path, log_lock, mock):
    """Get cached ideas and ranking, or create them."""
    key = (problem_id, seed)
    with _idea_cache_lock:
        if key in _idea_cache:
            return _idea_cache[key]

    from pipeline import ideate, make_logger

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    tag = f"[{_ts()}] [shared|{problem_id}|s{seed}]"

    # Ideate
    print(f"{tag} ideate (n={N_IDEAS}, {_short(IDEATOR)})", flush=True)
    ideas = ideate(
        problem=problem["text"], system=prompts["ideator"],
        model=IDEATOR, max_tokens=4096, logger=logger,
        num_ideas=N_IDEAS, mock=mock,
    )
    ideas = ideas[:N_IDEAS]
    print(f"{tag} got {len(ideas)} ideas: {[i['name'] for i in ideas]}", flush=True)

    # Rank
    print(f"{tag} ranking ideas ({_short(RANKER)})", flush=True)
    ranking = rank_ideas(problem["text"], ideas, prompts["idea_ranker"],
                        log_path, log_lock, mock)
    print(f"{tag} ranking: {ranking}", flush=True)

    result = (ideas, ranking)
    with _idea_cache_lock:
        _idea_cache[key] = result

    return result


def run_trial(
    problem_id, problem, cond_id, cond, seed, prompts, log_path, log_lock, mock=False,
):
    np.random.seed(seed + cond_id)  # offset so random-3 differs from all-7
    random.seed(seed + cond_id)

    cname = cond["name"]
    k = cond["k_branches"]
    use_ranker = cond["use_ranker"]
    tag = f"[{_ts()}] [c{cond_id}:{cname}|{problem_id}|s{seed}]"

    t0 = time.time()

    # Get shared ideas and ranking
    ideas, ranking = get_or_create_ideas(
        problem_id, problem, seed, prompts, log_path, log_lock, mock,
    )

    # Select which ideas to run
    if use_ranker:
        # Use ranker's top-K picks
        selected_indices = ranking[:k]
    elif k < len(ideas):
        # Random selection (for ablation)
        selected_indices = random.sample(range(len(ideas)), k)
    else:
        # All ideas
        selected_indices = list(range(len(ideas)))

    selected_ideas = [(idx, ideas[idx]) for idx in selected_indices]
    print(f"{tag} running {len(selected_ideas)} branches: indices={selected_indices}", flush=True)

    # Run branches in parallel
    branches = []
    if len(selected_ideas) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected_ideas)) as ex:
            futs = {
                ex.submit(run_branch, problem_id, problem, seed, idx, idea,
                          prompts, log_path, log_lock, tag, mock): idx
                for idx, idea in selected_ideas
            }
            for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT):
                try:
                    branches.append(fut.result(timeout=TRIAL_TIMEOUT))
                except Exception as e:
                    idx = futs[fut]
                    print(f"{tag} branch {idx} FAILED: {e}", flush=True)
                    branches.append({"idea_idx": idx, "idea": ideas[idx], "score": 0, "error": str(e)})
    else:
        idx, idea = selected_ideas[0]
        branch = run_branch(
            problem_id, problem, seed, idx, idea,
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
        "k_branches": k,
        "use_ranker": use_ranker,
        "problem_id": problem_id,
        "level": problem["level"],
        "role": problem.get("role", ""),
        "seed": seed,
        "score": best.get("score", 0),
        "passed": best.get("score", 0) >= PASS_THRESHOLD,
        "all_branch_scores": all_scores,
        "selected_indices": selected_indices,
        "ranking": ranking,
        "best_idea_idx": best.get("idea_idx"),
        "elapsed_s": elapsed,
        "final_solution": best.get("final_solution"),
        "verdict": best.get("verdict"),
        "branches": branches,
    }


def run_all(conditions, problems, prompts, mock):
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    # Run all-7 first (populates cache), then others can reuse
    # Actually, since we cache ideas, we can run all in parallel —
    # the cache lock will serialize ideation per problem.
    trials = [
        (cid, pid, seed)
        for cid in sorted(conditions)
        for pid in sorted(problems)
        for seed in SEEDS
    ]
    total = len(trials)
    print(f"\nSubmitting {total} trials\n", flush=True)

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
                    "k_branches": conditions[cid]["k_branches"],
                    "use_ranker": conditions[cid]["use_ranker"],
                    "problem_id": pid, "level": problems[pid]["level"],
                    "role": problems[pid].get("role", ""),
                    "seed": seed,
                    "score": None, "passed": False, "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    return results, log_path


def print_results(results, conditions, problems):
    pids = sorted(problems.keys())
    cids = sorted(conditions.keys())

    print(f"\n{'='*100}")
    print("PRUNING IDEATION EXPERIMENT — RESULTS")
    print(f"{'='*100}\n")

    # Per-condition summary
    print(f"{'Cond':>4}  {'Name':<14} {'K':>2} {'Ranker':>6} {'Mean':>6} {'Pass':>6} {'Err':>4}")
    print("-" * 65)
    for cid in cids:
        cond = conditions[cid]
        valid = [r for r in results if r["condition_id"] == cid and r.get("score") is not None]
        errs = sum(1 for r in results if r["condition_id"] == cid and r.get("error"))
        if valid:
            scores = [r["score"] for r in valid]
            n_pass = sum(1 for r in valid if r["passed"])
            mean = sum(scores) / len(scores)
            ranker = "yes" if cond["use_ranker"] else "no"
            err_s = str(errs) if errs else ""
            print(f"  {cid:>2}   {cond['name']:<14} {cond['k_branches']:>2} {ranker:>6}  {mean:5.2f}/7  "
                  f"{n_pass:>2}/{len(valid):<2} {err_s:>4}")
        else:
            print(f"  {cid:>2}   {cond['name']:<14}  (all errors)")

    # Ranker prediction accuracy
    print(f"\n{'─'*100}")
    print("\nRANKER PREDICTION ACCURACY:\n")
    print("For each problem, does the ranker's #1 pick match the actual best-scoring idea?")
    print()

    # Compare: for each problem, get all-7 results (cond 1) and check if ranker's #1
    # (from ranking) matches the best-scoring branch
    correct_top1 = 0
    correct_top3 = 0
    total_problems = 0

    for pid in pids:
        all7 = [r for r in results if r["condition_id"] == 1
                and r["problem_id"] == pid and r.get("score") is not None]
        if not all7:
            continue
        r = all7[0]
        ranking = r.get("ranking", [])
        branches = r.get("branches", [])
        if not ranking or not branches:
            continue

        total_problems += 1

        # Find actual best branch
        best_branch = max(branches, key=lambda b: b.get("score", 0))
        best_idx = best_branch.get("idea_idx")
        best_score = best_branch.get("score", 0)

        # Ranker's predictions
        ranker_top1 = ranking[0] if ranking else None
        ranker_top3 = ranking[:3] if len(ranking) >= 3 else ranking

        # Check if ranker's #1 matches actual best
        top1_match = ranker_top1 == best_idx
        top3_match = best_idx in ranker_top3

        if top1_match:
            correct_top1 += 1
        if top3_match:
            correct_top3 += 1

        # Also show all branch scores
        branch_scores = {b.get("idea_idx"): b.get("score", 0) for b in branches}
        ranker_top1_score = branch_scores.get(ranker_top1, "?")

        match_str = "✓" if top1_match else "✗"
        print(f"  {pid:<16} ranker_top1={ranker_top1}(score={ranker_top1_score})"
              f"  actual_best={best_idx}(score={best_score})"
              f"  {match_str}"
              f"  all_scores={dict(sorted(branch_scores.items()))}")

    if total_problems > 0:
        print(f"\n  Top-1 accuracy: {correct_top1}/{total_problems} ({100*correct_top1/total_problems:.0f}%)")
        print(f"  Top-3 accuracy: {correct_top3}/{total_problems} ({100*correct_top3/total_problems:.0f}%)")

    # Cost comparison
    print(f"\n{'─'*100}")
    print("\nCOST COMPARISON (mean elapsed time per trial):\n")
    for cid in cids:
        cond = conditions[cid]
        valid = [r for r in results if r["condition_id"] == cid and r.get("score") is not None]
        if valid:
            mean_time = sum(r["elapsed_s"] for r in valid) / len(valid)
            mean_score, _ = sum(r["score"] for r in valid) / len(valid), len(valid)
            print(f"  {cond['name']:<14} K={cond['k_branches']}  mean_time={mean_time:.0f}s  mean_score={mean_score:.2f}/7")

    # Per-problem table
    print(f"\n{'─'*100}")
    print("\nPer-problem scores:\n")
    hdr = f"  {'Problem':<16}"
    for cid in cids:
        hdr += f" {conditions[cid]['name']:>12}"
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
                row += f" {s:>12}"
            else:
                row += f" {'—':>12}"
        print(row)

    print()


def main():
    parser = argparse.ArgumentParser(description="Pruning ideation experiment")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--conditions", type=str, default=None)
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    if args.conditions:
        cond_ids = [int(x.strip()) for x in args.conditions.split(",")]
        conditions = {k: v for k, v in CONDITIONS.items() if k in cond_ids}
    else:
        conditions = CONDITIONS

    problems = load_problems()

    n_trials = len(conditions) * len(problems) * len(SEEDS)
    total_branches = sum(conditions[c]["k_branches"] for c in conditions) * len(problems) * len(SEEDS)
    print(f"Pruning Ideation Experiment")
    print(f"  {len(conditions)} conditions × {len(problems)} problems × {len(SEEDS)} seeds = {n_trials} trials")
    print(f"  Total branches: {total_branches}")
    print(f"  Ideator: {_short(IDEATOR)}, N_IDEAS={N_IDEAS}")
    print(f"  Ranker: {_short(RANKER)}")
    print(f"  Generator: {_short(GENERATOR)}")
    print(f"  Judge: {_short(JUDGE_MODEL)}")
    print(f"  Workers: {MAX_WORKERS}  Timeout: {TRIAL_TIMEOUT}s")
    print()

    for cid, cond in sorted(conditions.items()):
        print(f"  c{cid}: {cond['name']:<14} K={cond['k_branches']} ranker={'yes' if cond['use_ranker'] else 'no':>3}  {cond['description']}")
    print()

    prompts = {
        "generator":        load_prompt("generator.md"),
        "generator_seeded": load_prompt("generator_seeded.md"),
        "ideator":          load_prompt("ideator.md"),
        "idea_ranker":      load_prompt("idea_ranker.md"),
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
        "n_ideas": N_IDEAS,
        "seeds": SEEDS,
        "pass_threshold": PASS_THRESHOLD,
        "judge_model": JUDGE_MODEL,
        "ideator_model": IDEATOR,
        "ranker_model": RANKER,
        "generator_model": GENERATOR,
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
