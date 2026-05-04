#!/usr/bin/env python3
"""
Ranker comparison experiment: which model best predicts idea quality?

For each problem:
  1. Ideate 7 ideas (flash-lite ideator, shared across conditions)
  2. Run all 7 branches (DS generate-only + judge) to get ground-truth scores
  3. Have each ranker model rank the ideas
  4. Compare ranker predictions to actual best-scoring branch

Ranker models:
  - gemini-3.1-flash-lite (cheap baseline)
  - gemini-3-flash (mid-tier)
  - gemma-4-31b-it (new, strong reasoning)
  - qwen3.6-plus:free (new, free tier)
  - deepseek-v3.2 (same as generator — can it predict its own success?)

Problems: devset (6) + 4 IMO-hard from PB-Advanced = 10 problems
This gives us 70 branches for ground truth + 50 ranker calls.

Usage:
    uv run experiments/ranker_comparison_20260405.py --mock
    uv run experiments/ranker_comparison_20260405.py
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

EXPERIMENT_NAME = "ranker_comparison"

DESCRIPTION = """
Hypothesis: Stronger or differently-capable ranker models can better predict
which seed idea will produce the best solution. Tests 5 ranker models including
new gemma-4 and qwen3.6-plus, plus deepseek (same as generator) to test
self-prediction.

Variables:
  Independent: ranker model
  Dependent:   top-1 accuracy, top-3 accuracy, score@pruned-1, Kendall tau
  Controlled:  ideator, generator, judge, ideas (shared), problem set
"""

# --- Models ---
IDEATOR   = "openrouter/google/gemini-3.1-flash-lite-preview"
GENERATOR = "openrouter/deepseek/deepseek-v3.2"
JUDGE_MODEL = "gemini/gemini-3-flash-preview"

RANKERS = {
    "flash-lite":  "openrouter/google/gemini-3.1-flash-lite-preview",
    "gemini-flash": "openrouter/google/gemini-3-flash-preview",
    "gemma-4":     "openrouter/google/gemma-4-31b-it",
    "qwen3.6":     "openrouter/qwen/qwen3.6-plus:free",
    "deepseek":    "openrouter/deepseek/deepseek-v3.2",
}

# --- Problem set ---
# Devset (6) + 4 hard PB-Advanced problems for more signal
EXTRA_HARD = {"PB-Advanced-006", "PB-Advanced-012", "PB-Advanced-021", "PB-Advanced-027"}

N_IDEAS = 7
SEEDS = [42]
PASS_THRESHOLD = 6
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 20
TRIAL_TIMEOUT = 1800
LITELLM_TIMEOUT = 540


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
    # Devset + extra hard
    problems = select_devset(rows)
    for row in rows:
        pid = row["Problem ID"]
        if pid in EXTRA_HARD:
            problems[pid] = {
                "text":     row["Problem"],
                "solution": row.get("Solution", ""),
                "level":    row.get("Level", ""),
                "category": row.get("Category", ""),
                "role":     "hard-extra",
            }
    return problems


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _short(model: str) -> str:
    return model.split("/")[-1][:20]


# ---------------------------------------------------------------------------
# Branch execution (generate → judge)
# ---------------------------------------------------------------------------

def run_branch(problem_id, problem, seed, idea_idx, idea,
               prompts, log_path, log_lock, tag, mock=False):
    from pipeline import generate, judge, make_logger

    btag = f"{tag}[b{idea_idx}]"
    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    gen_prompt = prompts["generator_seeded"].replace(
        "{idea}", f"**{idea['name']}**: {idea['description']}"
    )
    print(f"{btag} generate ({_short(GENERATOR)}, idea={idea['name'][:30]})", flush=True)

    solution = generate(
        problem=problem["text"], system=gen_prompt, model=GENERATOR,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{btag} generated ({len(solution)} chars, {time.time()-t0:.1f}s)", flush=True)

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


# ---------------------------------------------------------------------------
# Ranker call
# ---------------------------------------------------------------------------

def call_ranker(ranker_name, ranker_model, problem_text, ideas,
                ranker_prompt, log_path, log_lock, mock=False):
    """Call one ranker model. Returns (ranking, raw_response)."""
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

    tag = f"[{_ts()}] [ranker:{ranker_name}]"
    print(f"{tag} ranking {len(ideas)} ideas", flush=True)

    t0 = time.time()
    if mock:
        response = f"```json\n{json.dumps(list(range(len(ideas))))}\n```\nIdea 0 is best because it's the most direct approach."
    else:
        # qwen free tier needs retry patience
        retries = 3 if "free" in ranker_model else 2
        backoff = 8.0 if "free" in ranker_model else 5.0
        for attempt in range(retries + 1):
            try:
                response = _call_llm("", prompt, ranker_model, 1024)
                break
            except Exception as e:
                if attempt < retries:
                    wait = backoff * (2 ** attempt)
                    print(f"{tag} attempt {attempt+1} failed: {e}, retrying in {wait:.0f}s", flush=True)
                    time.sleep(wait)
                else:
                    print(f"{tag} all attempts failed: {e}", flush=True)
                    response = "[]"

    logger("rank_ideas", 0, ranker_model, "", prompt, response, time.time() - t0)
    elapsed = round(time.time() - t0, 2)

    # Parse ranking
    ranking = None
    for pattern in [r"```json\s*(\[.*?\])\s*```", r"(\[[\d,\s]+\])"]:
        m = re.search(pattern, response, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(1))
                if all(isinstance(x, int) for x in parsed):
                    ranking = parsed
                    break
            except json.JSONDecodeError:
                continue

    if not ranking:
        ranking = list(range(len(ideas)))  # fallback

    print(f"{tag} ranking: {ranking} ({elapsed}s)", flush=True)
    return ranking, response


# ---------------------------------------------------------------------------
# Per-problem execution
# ---------------------------------------------------------------------------

def run_problem(problem_id, problem, seed, prompts, log_path, log_lock, mock=False):
    """For one problem: ideate, run all branches, call all rankers."""
    from pipeline import ideate, make_logger

    np.random.seed(seed)
    random.seed(seed)

    tag = f"[{_ts()}] [{problem_id}|s{seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # Step 1: Ideate
    print(f"{tag} ideate (n={N_IDEAS})", flush=True)
    ideas = ideate(
        problem=problem["text"], system=prompts["ideator"],
        model=IDEATOR, max_tokens=4096, logger=logger,
        num_ideas=N_IDEAS, mock=mock,
    )
    ideas = ideas[:N_IDEAS]
    print(f"{tag} got {len(ideas)} ideas: {[i['name'] for i in ideas]}", flush=True)

    # Step 2: Run ALL branches in parallel (ground truth)
    branches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ideas)) as ex:
        futs = {
            ex.submit(run_branch, problem_id, problem, seed, idx, idea,
                      prompts, log_path, log_lock, tag, mock): idx
            for idx, idea in enumerate(ideas)
        }
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT):
            try:
                branches.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                idx = futs[fut]
                print(f"{tag} branch {idx} FAILED: {e}", flush=True)
                branches.append({"idea_idx": idx, "idea": ideas[idx], "score": 0, "error": str(e)})

    branch_scores = {b["idea_idx"]: b.get("score", 0) for b in branches}
    best_idx = max(branch_scores, key=branch_scores.get)
    best_score = branch_scores[best_idx]
    print(f"{tag} ground truth: best=idea_{best_idx}({best_score}/7) all={dict(sorted(branch_scores.items()))}", flush=True)

    # Step 3: Call all rankers in parallel
    ranker_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(RANKERS)) as ex:
        futs = {
            ex.submit(call_ranker, rname, rmodel, problem["text"], ideas,
                      prompts["idea_ranker"], log_path, log_lock, mock): rname
            for rname, rmodel in RANKERS.items()
        }
        for fut in concurrent.futures.as_completed(futs, timeout=300):
            rname = futs[fut]
            try:
                ranking, raw = fut.result(timeout=300)
                ranker_results[rname] = {
                    "ranking": ranking,
                    "raw_response": raw,
                }
            except Exception as e:
                print(f"{tag} ranker {rname} FAILED: {e}", flush=True)
                ranker_results[rname] = {
                    "ranking": list(range(len(ideas))),
                    "error": str(e),
                }

    elapsed = round(time.time() - t0, 2)
    print(f"{tag} done ({elapsed}s)", flush=True)

    return {
        "problem_id": problem_id,
        "level": problem["level"],
        "role": problem.get("role", ""),
        "seed": seed,
        "ideas": ideas,
        "branch_scores": branch_scores,
        "best_idx": best_idx,
        "best_score": best_score,
        "branches": branches,
        "ranker_results": ranker_results,
        "elapsed_s": elapsed,
    }


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

def run_all(problems, prompts, mock):
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    pids = sorted(problems.keys())
    total = len(pids)
    print(f"\nRunning {total} problems × {N_IDEAS} branches + {len(RANKERS)} rankers\n", flush=True)

    results = []
    completed = 0

    # Run problems with moderate parallelism (each problem spawns 7 branches)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, total)) as ex:
        futs = {
            ex.submit(run_problem, pid, problems[pid], SEEDS[0],
                      prompts, log_path, log_lock, mock): pid
            for pid in pids
        }
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                print(f"[{_ts()}] PROBLEM FAILED [{pid}]: {e}", flush=True)
                results.append({
                    "problem_id": pid,
                    "level": problems[pid]["level"],
                    "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total} problems", flush=True)

    return results, log_path


# ---------------------------------------------------------------------------
# Analysis and reporting
# ---------------------------------------------------------------------------

def kendall_tau(ranking, scores):
    """Compute Kendall tau between ranker's ranking and actual scores (higher=better)."""
    n = len(ranking)
    if n < 2:
        return 0.0
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            ri, rj = ranking.index(i) if i in ranking else n, ranking.index(j) if j in ranking else n
            si, sj = scores.get(i, 0), scores.get(j, 0)
            # Lower rank position = better; higher score = better
            rank_order = (ri < rj)  # ranker thinks i is better
            score_order = (si > sj)  # i actually is better
            if si == sj:
                continue  # tied scores, skip
            if rank_order == score_order:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return 0.0
    return (concordant - discordant) / total


def print_results(results):
    valid = [r for r in results if "error" not in r]

    print(f"\n{'='*110}")
    print("RANKER COMPARISON EXPERIMENT — RESULTS")
    print(f"{'='*110}\n")

    # --- Per-ranker aggregate metrics ---
    print(f"{'Ranker':<16} {'Top-1':>6} {'Top-3':>6} {'Score@1':>8} {'Kendall τ':>10} {'Avg Rank of Best':>18}")
    print("-" * 75)

    ranker_metrics = {}
    for rname in RANKERS:
        top1_correct = 0
        top3_correct = 0
        score_at_1 = []
        taus = []
        rank_of_best = []
        n_problems = 0

        for r in valid:
            rr = r["ranker_results"].get(rname, {})
            ranking = rr.get("ranking", [])
            if not ranking:
                continue

            n_problems += 1
            best_idx = r["best_idx"]
            branch_scores = r["branch_scores"]

            # Top-1 accuracy
            if ranking[0] == best_idx:
                top1_correct += 1

            # Top-3 accuracy
            if best_idx in ranking[:3]:
                top3_correct += 1

            # Score at pruned-to-1
            score_at_1.append(branch_scores.get(ranking[0], 0))

            # Kendall tau
            tau = kendall_tau(ranking, branch_scores)
            taus.append(tau)

            # Where did the ranker place the actual best?
            if best_idx in ranking:
                rank_of_best.append(ranking.index(best_idx))
            else:
                rank_of_best.append(len(ranking))

        if n_problems > 0:
            top1_rate = top1_correct / n_problems
            top3_rate = top3_correct / n_problems
            mean_s1 = sum(score_at_1) / len(score_at_1) if score_at_1 else 0
            mean_tau = sum(taus) / len(taus) if taus else 0
            mean_rob = sum(rank_of_best) / len(rank_of_best) if rank_of_best else 0

            ranker_metrics[rname] = {
                "top1": top1_rate, "top3": top3_rate,
                "score_at_1": mean_s1, "tau": mean_tau,
                "rank_of_best": mean_rob, "n": n_problems,
            }

            print(f"  {rname:<14} {top1_rate:5.0%}  {top3_rate:5.0%}  {mean_s1:7.2f}/7  {mean_tau:9.3f}  {mean_rob:17.2f}")

    # Random baseline
    print(f"\n  {'(random)':<14} {1/7:5.0%}  {3/7:5.0%}  {'—':>8}  {'0.000':>10}  {'3.00':>18}")

    # --- Per-problem breakdown ---
    print(f"\n{'─'*110}")
    print("\nPER-PROBLEM RANKER ACCURACY (✓=top-1 correct, ○=top-3 correct, ✗=miss):\n")

    hdr = f"  {'Problem':<20} {'Best':>4} {'Scores':<30}"
    for rname in RANKERS:
        hdr += f" {rname:>12}"
    print(hdr)
    print()

    for r in sorted(valid, key=lambda x: x["problem_id"]):
        pid = r["problem_id"]
        best_idx = r["best_idx"]
        bs = r["branch_scores"]
        scores_str = ",".join(f"{bs.get(i,0)}" for i in range(len(bs)))

        row = f"  {pid:<20} {best_idx:>4} [{scores_str[:28]:<28}]"
        for rname in RANKERS:
            rr = r["ranker_results"].get(rname, {})
            ranking = rr.get("ranking", [])
            if not ranking:
                row += f" {'err':>12}"
                continue

            top1 = ranking[0]
            top1_score = bs.get(top1, 0)
            if top1 == best_idx:
                mark = "✓"
            elif best_idx in ranking[:3]:
                mark = "○"
            else:
                mark = "✗"
            row += f" {mark}#{top1}({top1_score}):>12"
        print(row)

    # --- Detailed ranking comparison for each problem ---
    print(f"\n{'─'*110}")
    print("\nFULL RANKINGS vs GROUND TRUTH:\n")

    for r in sorted(valid, key=lambda x: x["problem_id"]):
        pid = r["problem_id"]
        bs = r["branch_scores"]
        # Sort by score descending for ground truth ordering
        gt_order = sorted(bs.keys(), key=lambda i: bs[i], reverse=True)
        gt_str = " > ".join(f"#{i}({bs[i]})" for i in gt_order)
        print(f"  {pid}:")
        print(f"    Ground truth: {gt_str}")
        for rname in RANKERS:
            rr = r["ranker_results"].get(rname, {})
            ranking = rr.get("ranking", [])
            if ranking:
                rank_str = " > ".join(f"#{i}({bs.get(i,0)})" for i in ranking)
                tau = kendall_tau(ranking, bs)
                print(f"    {rname:<14}: {rank_str}  (τ={tau:+.3f})")
        print()

    # --- Which ranker would be best for each strategy? ---
    print(f"\n{'─'*110}")
    print("\nBEST RANKER BY STRATEGY:\n")

    if ranker_metrics:
        best_top1 = max(ranker_metrics, key=lambda r: ranker_metrics[r]["top1"])
        best_top3 = max(ranker_metrics, key=lambda r: ranker_metrics[r]["top3"])
        best_score = max(ranker_metrics, key=lambda r: ranker_metrics[r]["score_at_1"])
        best_tau = max(ranker_metrics, key=lambda r: ranker_metrics[r]["tau"])

        print(f"  Prune-to-1 (top-1 accuracy): {best_top1} ({ranker_metrics[best_top1]['top1']:.0%})")
        print(f"  Prune-to-3 (top-3 accuracy): {best_top3} ({ranker_metrics[best_top3]['top3']:.0%})")
        print(f"  Score@pruned-1:              {best_score} ({ranker_metrics[best_score]['score_at_1']:.2f}/7)")
        print(f"  Overall ranking (Kendall τ): {best_tau} ({ranker_metrics[best_tau]['tau']:.3f})")

    print()


def main():
    parser = argparse.ArgumentParser(description="Ranker comparison experiment")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()

    n_branches = len(problems) * N_IDEAS
    n_ranker_calls = len(problems) * len(RANKERS)
    print(f"Ranker Comparison Experiment")
    print(f"  {len(problems)} problems × {N_IDEAS} branches = {n_branches} ground-truth trials")
    print(f"  {len(problems)} problems × {len(RANKERS)} rankers = {n_ranker_calls} ranking calls")
    print(f"  Ideator: {_short(IDEATOR)}")
    print(f"  Generator: {_short(GENERATOR)}")
    print(f"  Judge: {_short(JUDGE_MODEL)}")
    print(f"  Workers: {MAX_WORKERS}  Timeout: {TRIAL_TIMEOUT}s")
    print()

    print("  Rankers:")
    for rname, rmodel in RANKERS.items():
        print(f"    {rname:<14} {_short(rmodel)}")
    print()

    for pid, p in sorted(problems.items()):
        print(f"  {pid:<24} {p.get('level',''):<16} {p.get('role','')}")
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

    results, log_path = run_all(problems, prompts, args.mock)
    print_results(results)

    # Save
    ts = _now()
    suffix = "_mock" if args.mock else ""
    output = {
        "experiment": EXPERIMENT_NAME,
        "description": DESCRIPTION.strip(),
        "date": datetime.now(timezone.utc).isoformat(),
        "rankers": RANKERS,
        "n_ideas": N_IDEAS,
        "seeds": SEEDS,
        "ideator_model": IDEATOR,
        "generator_model": GENERATOR,
        "judge_model": JUDGE_MODEL,
        "mock": args.mock,
        "all_results": results,
    }
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
