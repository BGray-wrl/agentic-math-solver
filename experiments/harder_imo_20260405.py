#!/usr/bin/env python3
"""
Harder IMO experiment: test best config on IMO-hard problems.

Uses flash-lite ideator (best from Gemini experiments) with DS and OSS
generators on IMO-hard and IMO-medium problems from PB-Advanced.
Tests both full-pipeline and generate-only modes.

  Problems: 10 IMO-hard + 5 IMO-medium from PB-Advanced = 15 problems
  Ideator: gemini-3.1-flash-lite
  Generators: deepseek-v3.2, gpt-oss-120b
  Modes: full pipeline, generate-only
  N_IDEAS = 3

Total: 4 conditions × 15 problems × 1 seed = 60 trials

Usage:
    uv run experiments/harder_imo_20260405.py --mock
    uv run experiments/harder_imo_20260405.py
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

# ============================================================================
# CONFIGURATION
# ============================================================================

EXPERIMENT_NAME = "harder_imo"

DESCRIPTION = """
Hypothesis: The flash-lite ideator + seeded generation pipeline that worked
well on devset (IMO-medium) will show clear separation between full-pipeline
and generate-only on harder (IMO-hard) problems. Full pipeline should help
more on harder problems where initial solutions are more likely to have errors.

Variables:
  Independent: pipeline mode (full vs generate-only) × generator (ds vs oss)
  Dependent:   judge score (0-7)
  Controlled:  ideator model, N=3 ideas, judge model, seed
"""

# --- Models ---
IDEATOR = "openrouter/google/gemini-3.1-flash-lite-preview"
DS  = "openrouter/deepseek/deepseek-v3.2"
OSS = "openrouter/openai/gpt-oss-120b"

JUDGE_MODEL = "gemini/gemini-3-flash-preview"

NUM_IDEAS = 3
SEEDS = [42]
PASS_THRESHOLD = 6
ITERATIONS = 3
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 20  # aggressive parallelism
TRIAL_TIMEOUT = 2400  # longer for hard problems + full pipeline
LITELLM_TIMEOUT = 540

# --- Problem selection ---
# All IMO-hard from PB-Advanced (10) + select IMO-medium from PB-Advanced (5)
HARD_PROBLEMS = {
    "PB-Advanced-003", "PB-Advanced-006", "PB-Advanced-009", "PB-Advanced-012",
    "PB-Advanced-015", "PB-Advanced-018", "PB-Advanced-021", "PB-Advanced-024",
    "PB-Advanced-027", "PB-Advanced-030",
    # Plus 5 IMO-medium for comparison
    "PB-Advanced-002", "PB-Advanced-005", "PB-Advanced-008",
    "PB-Advanced-010", "PB-Advanced-014",
}

CONDITIONS = {
    1: {"name": "ds-pipe",  "mode": "full",     "ideator": IDEATOR, "generator": DS,  "verifier": DS,  "reviser": DS},
    2: {"name": "oss-pipe", "mode": "full",     "ideator": IDEATOR, "generator": OSS, "verifier": OSS, "reviser": OSS},
    3: {"name": "ds-gen",   "mode": "generate", "ideator": IDEATOR, "generator": DS},
    4: {"name": "oss-gen",  "mode": "generate", "ideator": IDEATOR, "generator": OSS},
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
    problems = {}
    for row in rows:
        pid = row["Problem ID"]
        if pid in HARD_PROBLEMS:
            problems[pid] = {
                "text":     row["Problem"],
                "solution": row.get("Solution", ""),
                "level":    row.get("Level", ""),
                "category": row.get("Category", ""),
            }
    return problems


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _short(model: str) -> str:
    return model.split("/")[-1][:16]


def run_branch(
    problem_id, problem, cond_id, cond, seed, idea_idx, idea,
    prompts, log_path, log_lock, tag, mock=False,
):
    """Run one branch: generate [→ verify ↔ revise] → judge."""
    from pipeline import generate, verify, revise, judge, make_logger

    gen_model = cond["generator"]
    mode = cond["mode"]
    btag = f"{tag}[b{idea_idx}]" if idea is not None else tag

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()
    loop_log = []

    # Generate
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

    # Verify/Revise loop (full mode only)
    stopped_early = False
    if mode == "full":
        for i in range(ITERATIONS):
            ver_model = cond.get("verifier", gen_model)
            rev_model = cond.get("reviser", gen_model)

            print(f"{btag} verify i={i+1} ({_short(ver_model)})", flush=True)
            critique = verify(
                problem=problem["text"], solution=solution, system=prompts["verifier"],
                model=ver_model, max_tokens=MAX_TOKENS, logger=logger,
                iteration=i+1, mock=mock,
            )
            if "VERDICT: correct" in critique:
                print(f"{btag} verified correct at i={i+1}", flush=True)
                stopped_early = True
                loop_log.append({"iteration": i+1, "verdict": "correct"})
                break

            print(f"{btag} revise i={i+1} ({_short(rev_model)})", flush=True)
            new_solution = revise(
                problem=problem["text"], solution=solution, critique=critique,
                system=prompts["reviser"], model=rev_model, max_tokens=MAX_TOKENS,
                logger=logger, iteration=i+1, mock=mock,
            )
            loop_log.append({"iteration": i+1, "verdict": "issues_found"})
            solution = new_solution
            print(f"{btag} revised ({len(solution)} chars, {time.time()-t0:.1f}s)", flush=True)

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
        "stopped_early": stopped_early,
        "iterations_run": len(loop_log),
        "elapsed_s": elapsed,
        "final_solution": solution,
        "verdict": verdict_text,
        "loop_log": loop_log,
    }


def run_trial(
    problem_id, problem, cond_id, cond, seed, prompts, log_path, log_lock, mock=False,
):
    from pipeline import ideate, make_logger

    np.random.seed(seed)
    random.seed(seed)

    cname = cond["name"]
    tag = f"[{_ts()}] [c{cond_id}:{cname}|{problem_id}|s{seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # Ideate
    print(f"{tag} ideate (n={NUM_IDEAS}, {_short(cond['ideator'])})", flush=True)
    ideas = ideate(
        problem=problem["text"], system=prompts["ideator"],
        model=cond["ideator"], max_tokens=4096, logger=logger,
        num_ideas=NUM_IDEAS, mock=mock,
    )
    ideas = ideas[:NUM_IDEAS]
    print(f"{tag} got {len(ideas)} ideas: {[i['name'] for i in ideas]}", flush=True)

    # Run branches in parallel
    branches = []
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

    # Pick best
    branches.sort(key=lambda b: b.get("score", 0), reverse=True)
    best = branches[0]
    all_scores = [b.get("score", 0) for b in branches]

    elapsed = round(time.time() - t0, 2)
    print(f"{tag} best={best.get('score',0)}/7 (all: {all_scores}) {elapsed}s", flush=True)

    return {
        "condition_id": cond_id,
        "condition_name": cname,
        "mode": cond["mode"],
        "problem_id": problem_id,
        "level": problem["level"],
        "category": problem.get("category", ""),
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
                    "mode": conditions[cid]["mode"],
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid].get("category", ""),
                    "seed": seed,
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

    print(f"\n{'='*110}")
    print("HARDER IMO EXPERIMENT — RESULTS")
    print(f"{'='*110}\n")

    # Per-condition summary
    print(f"{'Cond':>4}  {'Name':<16} {'Mode':<9} {'Mean':>6} {'Pass':>6} {'Err':>4}")
    print("-" * 70)
    for cid in cids:
        cond = conditions[cid]
        valid = [r for r in results if r["condition_id"] == cid and r.get("score") is not None]
        errs = sum(1 for r in results if r["condition_id"] == cid and r.get("error"))
        if valid:
            scores = [r["score"] for r in valid]
            n_pass = sum(1 for r in valid if r["passed"])
            mean = sum(scores) / len(scores)
            err_s = str(errs) if errs else ""
            print(f"  {cid:>2}   {cond['name']:<16} {cond['mode']:<9} {mean:5.2f}/7  "
                  f"{n_pass:>2}/{len(valid):<2} {err_s:>4}")
        else:
            print(f"  {cid:>2}   {cond['name']:<16}  (all errors, n={errs})")

    # By difficulty level
    print(f"\n{'─'*110}")
    print("\nBY DIFFICULTY LEVEL:\n")

    levels = sorted({r["level"] for r in results if r.get("level")})
    for level in levels:
        print(f"  {level}:")
        for cid in cids:
            cond = conditions[cid]
            valid = [r for r in results if r["condition_id"] == cid
                     and r["level"] == level and r.get("score") is not None]
            if valid:
                scores = [r["score"] for r in valid]
                mean = sum(scores) / len(scores)
                n_pass = sum(1 for r in valid if r["passed"])
                print(f"    {cond['name']:<16} {mean:.2f}/7  pass={n_pass}/{len(valid)}")
        print()

    # By category
    print(f"{'─'*110}")
    print("\nBY CATEGORY:\n")
    cats = sorted({r.get("category","") for r in results if r.get("category")})
    for cat in cats:
        print(f"  {cat}:")
        for cid in cids:
            cond = conditions[cid]
            valid = [r for r in results if r["condition_id"] == cid
                     and r.get("category") == cat and r.get("score") is not None]
            if valid:
                scores = [r["score"] for r in valid]
                mean = sum(scores) / len(scores)
                print(f"    {cond['name']:<16} {mean:.2f}/7  (n={len(valid)})")
        print()

    # Full pipeline uplift
    print(f"{'─'*110}")
    print("\nFULL PIPELINE UPLIFT (full − generate-only):\n")
    for gen_label, pipe_cid, gen_cid in [("DS", 1, 3), ("OSS", 2, 4)]:
        pipe_mean, _ = _mean_score(results, pipe_cid)
        gen_mean, _ = _mean_score(results, gen_cid)
        if pipe_mean is not None and gen_mean is not None:
            delta = pipe_mean - gen_mean
            print(f"  {gen_label}: gen={gen_mean:.2f} → full={pipe_mean:.2f}  ({delta:+.2f})")

        # By level
        for level in levels:
            pipe_valid = [r for r in results if r["condition_id"] == pipe_cid
                         and r["level"] == level and r.get("score") is not None]
            gen_valid = [r for r in results if r["condition_id"] == gen_cid
                        and r["level"] == level and r.get("score") is not None]
            if pipe_valid and gen_valid:
                pm = sum(r["score"] for r in pipe_valid) / len(pipe_valid)
                gm = sum(r["score"] for r in gen_valid) / len(gen_valid)
                d = pm - gm
                print(f"    {level:<16} gen={gm:.2f} → full={pm:.2f}  ({d:+.2f})")
    print()

    # Per-problem table
    print(f"{'─'*110}")
    print("\nPer-problem scores:\n")
    hdr = f"  {'Problem':<20} {'Level':<12}"
    for cid in cids:
        hdr += f" {conditions[cid]['name']:>10}"
    print(hdr)
    print()

    for pid in pids:
        level = problems[pid]["level"]
        row = f"  {pid:<20} {level:<12}"
        for cid in cids:
            trial = [r for r in results if r["condition_id"] == cid
                     and r["problem_id"] == pid and r.get("score") is not None]
            if trial:
                r = trial[0]
                s = r["score"]
                all_s = r.get("all_branch_scores", [s])
                cell = f"{s}({','.join(str(x) for x in all_s)})"
                row += f" {cell:>10}"
            else:
                row += f" {'—':>10}"
        print(row)

    print()


def main():
    parser = argparse.ArgumentParser(description="Harder IMO experiment")
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
    total_branches = NUM_IDEAS * n_trials
    print(f"Harder IMO Experiment")
    print(f"  {len(conditions)} conditions × {len(problems)} problems × {len(SEEDS)} seeds = {n_trials} trials")
    print(f"  Total branches: {total_branches}")
    print(f"  Ideator: {_short(IDEATOR)}, N_IDEAS={NUM_IDEAS}")
    print(f"  Judge: {_short(JUDGE_MODEL)}")
    print(f"  Workers: {MAX_WORKERS}  Timeout: {TRIAL_TIMEOUT}s")
    print()

    for cid, cond in sorted(conditions.items()):
        gen = _short(cond["generator"])
        mode = cond["mode"]
        if mode == "full":
            print(f"  c{cid}: {cond['name']:<16} gen={gen} ver+rev={gen} (full pipeline)")
        else:
            print(f"  c{cid}: {cond['name']:<16} gen={gen} (generate-only)")
    print()

    # Show problems by level
    for level in sorted({p["level"] for p in problems.values()}):
        pids = [pid for pid, p in sorted(problems.items()) if p["level"] == level]
        print(f"  {level}: {', '.join(pids)}")
    print()

    prompts = {
        "generator":        load_prompt("generator.md"),
        "generator_seeded": load_prompt("generator_seeded.md"),
        "ideator":          load_prompt("ideator.md"),
        "verifier":         load_prompt("verifier.md"),
        "reviser":          load_prompt("reviser.md"),
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
        "num_ideas": NUM_IDEAS,
        "seeds": SEEDS,
        "iterations": ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
        "judge_model": JUDGE_MODEL,
        "ideator_model": IDEATOR,
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
