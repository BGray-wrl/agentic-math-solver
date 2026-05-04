#!/usr/bin/env python3
"""
Seed-ideas pipeline variant on the dev set.

Architecture: ideate → for each idea: generate(conditioned on idea) → verify ↔ revise → judge → pick best

Compared to the baseline full pipeline which generates one solution and loops,
this fans out across multiple starting strategies and picks the best final score.

Usage:
    uv run experiments/seed_ideas_devset_20260327.py --mock
    uv run experiments/seed_ideas_devset_20260327.py
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

EXPERIMENT_NAME = "seed_ideas_devset"

DESCRIPTION = """
Hypothesis: Generating multiple seed ideas and solving conditioned on each
will outperform single-shot generation, especially on boundary/hard problems
where the model currently oscillates or picks the wrong approach.

Architecture: ideate(N ideas) → N parallel branches of (generate → verify ↔ revise) → judge all → pick best
"""

MODELS = [
    "openrouter/qwen/qwen3.5-flash-02-23",
    "openai/gpt-5.4-mini",
    "gemini/gemini-3-flash-preview",
    "openrouter/openai/gpt-oss-120b",
    "openrouter/google/gemini-3.1-flash-lite-preview",
    "openrouter/deepseek/deepseek-v3.2",
]

JUDGE_MODEL = "gemini/gemini-3-flash-preview"

# Seed-ideas specific
NUM_IDEAS = 3
"""Number of seed ideas to generate per problem."""

USE_GROUND_TRUTH = True
SEEDS = [42]
PASS_THRESHOLD = 6
ITERATIONS = 2  # fewer iters per branch since we have N branches
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 12
TRIAL_TIMEOUT = 3000  # >30 min — each trial fans out 3 branches
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
    # Fallback: map CLASSIFICATION to approximate score
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


def run_branch(
    problem_id, problem, model, seed, idea_idx, idea, prompts,
    log_path, log_lock, mock=False,
):
    """Run one branch: generate(conditioned on idea) → verify ↔ revise → judge."""
    from pipeline import generate, verify, revise, judge, make_logger

    ms = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{ms}|idea={idea_idx}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()
    loop_log = []

    # Build seeded generator prompt
    seeded_prompt = prompts["generator_seeded"].replace(
        "{idea}", f"**{idea['name']}**: {idea['description']}"
    )

    # Generate conditioned on idea
    print(f"{tag} generate ({idea['name']})", flush=True)
    solution = generate(
        problem=problem["text"], system=seeded_prompt, model=model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{tag} generated ({len(solution)} chars, {time.time()-t0:.1f}s)", flush=True)

    # Verify/Revise loop
    stopped_early = False
    for i in range(ITERATIONS):
        print(f"{tag} verify iter={i+1}", flush=True)
        critique = verify(
            problem=problem["text"], solution=solution, system=prompts["verifier"],
            model=model, max_tokens=MAX_TOKENS, logger=logger, iteration=i+1, mock=mock,
        )
        if "VERDICT: correct" in critique:
            print(f"{tag} verifier satisfied at iter={i+1}", flush=True)
            stopped_early = True
            loop_log.append({"iteration": i+1, "verdict": "correct",
                             "critique": critique, "solution": solution})
            break

        print(f"{tag} revise iter={i+1}", flush=True)
        new_solution = revise(
            problem=problem["text"], solution=solution, critique=critique,
            system=prompts["reviser"], model=model, max_tokens=MAX_TOKENS,
            logger=logger, iteration=i+1, mock=mock,
        )
        loop_log.append({"iteration": i+1, "verdict": "issues_found",
                         "critique": critique, "solution_before": solution,
                         "solution_after": new_solution})
        solution = new_solution

    # Judge
    gt = problem["solution"]
    judge_prompt = prompts["judge_gt"] if gt else prompts["judge_nogt"]
    print(f"{tag} judge", flush=True)
    verdict_text = judge(
        problem=problem["text"], candidate=solution, ground_truth=gt,
        system=judge_prompt, model=JUDGE_MODEL,
        max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
        extract_prompt=prompts["extract_score"],
    )
    score = parse_gt_score(verdict_text)

    elapsed = round(time.time() - t0, 2)
    print(f"{tag} → score={score}/7 ({elapsed}s)", flush=True)

    return {
        "idea_idx": idea_idx,
        "idea": idea,
        "score": score,
        "stopped_early": stopped_early,
        "iterations_run": len(loop_log),
        "elapsed_s": elapsed,
        "final_solution": solution,
        "verdict": verdict_text,
        "loop_log": loop_log,
    }


def run_trial(
    problem_id, problem, model, seed, prompts, log_path, log_lock, mock=False,
):
    """Run full seed-ideas trial: ideate → fan out → pick best."""
    from pipeline import ideate, make_logger

    np.random.seed(seed)
    random.seed(seed)

    ms = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{ms}|seed={seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # Step 1: Generate seed ideas
    print(f"{tag} ideating ({NUM_IDEAS} ideas)...", flush=True)
    ideas = ideate(
        problem=problem["text"], system=prompts["ideator"], model=model,
        max_tokens=4096, logger=logger, num_ideas=NUM_IDEAS, mock=mock,
    )
    print(f"{tag} got {len(ideas)} ideas: {[i['name'] for i in ideas]}", flush=True)

    # Step 2: Run branches in parallel (within this trial)
    branches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ideas)) as ex:
        futs = {
            ex.submit(run_branch, problem_id, problem, model, seed, idx, idea,
                      prompts, log_path, log_lock, mock): idx
            for idx, idea in enumerate(ideas)
        }
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT):
            try:
                branches.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                idx = futs[fut]
                print(f"{tag} branch {idx} FAILED: {e}", flush=True)
                branches.append({
                    "idea_idx": idx, "idea": ideas[idx] if idx < len(ideas) else {},
                    "score": 0, "error": str(e),
                })

    # Step 3: Pick best branch by score
    branches.sort(key=lambda b: b.get("score", 0), reverse=True)
    best = branches[0]

    elapsed = round(time.time() - t0, 2)
    all_scores = [b.get("score", 0) for b in branches]
    print(f"{tag} ✓ best={best.get('score',0)}/7 (all: {all_scores}) total={elapsed}s", flush=True)

    return {
        "problem_id": problem_id,
        "level": problem["level"],
        "category": problem.get("category", ""),
        "role": problem.get("role", ""),
        "model": model,
        "seed": seed,
        "pipeline_mode": "seed_ideas",
        "num_ideas": len(ideas),
        "ideas": ideas,
        "score": best.get("score", 0),
        "passed": best.get("score", 0) >= PASS_THRESHOLD,
        "best_idea_idx": best.get("idea_idx"),
        "best_idea_name": best.get("idea", {}).get("name", ""),
        "all_branch_scores": all_scores,
        "elapsed_s": elapsed,
        "final_solution": best.get("final_solution"),
        "verdict": best.get("verdict"),
        "branches": branches,
    }


def run_all(problems, prompts, mock):
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    trials = [(pid, m, s) for pid in sorted(problems) for m in MODELS for s in SEEDS]
    total = len(trials)
    print(f"\nSubmitting {total} trials ({NUM_IDEAS} ideas each → {total * NUM_IDEAS} branches)\n", flush=True)

    results = []
    # Run trials sequentially per model to avoid overwhelming API
    # (each trial already fans out NUM_IDEAS branches in parallel)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {
            ex.submit(run_trial, pid, problems[pid], model, seed, prompts,
                      log_path, log_lock, mock): (pid, model, seed)
            for pid, model, seed in trials
        }
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            pid, model, seed = futs[fut]
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = model.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{ms}]: {e}", flush=True)
                results.append({
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid].get("category", ""),
                    "role": problems[pid].get("role", ""),
                    "model": model, "seed": seed, "pipeline_mode": "seed_ideas",
                    "score": None, "passed": False, "error": str(e),
                })

    return results, log_path


def print_results(results, problems):
    pids = sorted(problems.keys())

    print(f"\n{'='*90}")
    print("SEED IDEAS — DEV SET RESULTS")
    print(f"{'='*90}\n")

    for model in MODELS:
        ms = model.split("/")[-1]
        valid = [r for r in results if r["model"] == model and r.get("score") is not None]
        if not valid:
            continue
        scores = [r["score"] for r in valid]
        n_pass = sum(1 for r in valid if r["passed"])
        print(f"{ms}:")
        print(f"  mean={np.mean(scores):.2f}/7  pass={n_pass}/{len(valid)}  scores={scores}")
        print()

    # Per-problem table
    print(f"{'Problem':<20} {'Role':<24}", end="")
    for model in MODELS:
        ms = model.split("/")[-1][:20]
        print(f"  {ms:>20s}", end="")
    print()
    print("-" * (44 + 22 * len(MODELS)))

    for pid in pids:
        role = problems[pid].get("role", "")
        row = f"{pid:<20} {role:<24}"
        for model in MODELS:
            r = [x for x in results if x["problem_id"] == pid and x["model"] == model]
            if r and r[0].get("score") is not None:
                s = r[0]["score"]
                all_s = r[0].get("all_branch_scores", [])
                best_idea = r[0].get("best_idea_name", "?")[:12]
                mark = "✓" if r[0]["passed"] else "✗"
                cell = f"{mark} {s}/7 {all_s}"
            else:
                cell = "error"
            row += f"  {cell:>20s}"
        print(row)

    print()


def main():
    parser = argparse.ArgumentParser(description="Seed ideas pipeline on dev set")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--generate-only", action="store_true",
                        help="Skip verify/revise loop — ideate → generate → judge only")
    args = parser.parse_args()

    global ITERATIONS
    if args.generate_only:
        ITERATIONS = 0

    litellm.request_timeout = LITELLM_TIMEOUT

    problems = load_problems()
    print(f"Seed-ideas pipeline: {NUM_IDEAS} ideas × {len(MODELS)} models × {len(problems)} problems")
    print(f"  Verify/revise iters per branch: {ITERATIONS}")
    for pid, p in sorted(problems.items()):
        print(f"  {pid:<20s}  {p['level']:<18s}  {p.get('role','')}")

    prompts = {
        "ideator":          load_prompt("ideator.md"),
        "generator_seeded": load_prompt("generator_seeded.md"),
        "verifier":         load_prompt("verifier.md"),
        "reviser":          load_prompt("reviser.md"),
        "judge_gt":         load_prompt("judge_gt.md"),
        "judge_nogt":       load_prompt("judge_nogt.md"),
        "extract_score":    load_prompt("extract_score.md"),
    }

    results, log_path = run_all(problems, prompts, args.mock)
    print_results(results, problems)

    # Save
    ts = _now()
    suffix = ("_genonly" if args.generate_only else "") + ("_mock" if args.mock else "")
    output = {
        "experiment": EXPERIMENT_NAME,
        "description": DESCRIPTION.strip(),
        "date": datetime.now(timezone.utc).isoformat(),
        "models": MODELS,
        "judge_model": JUDGE_MODEL,
        "num_ideas": NUM_IDEAS,
        "seeds": SEEDS,
        "iterations_per_branch": ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
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
