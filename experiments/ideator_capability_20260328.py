#!/usr/bin/env python3
"""
Ideator capability scaling experiment: does a smarter ideator help?

Tests 3 Gemini-family ideators at different capability tiers paired with
deepseek-v3.2 and gpt-oss-120b as the pipeline model, in both full-pipeline
and generate-only modes.

  IDEATORS (3 tiers):
    lite  = gemini-3.1-flash-lite   (cheapest, weakest)
    flash = gemini-3.0-flash        (mid-tier)
    pro   = gemini-3.1-pro          (strongest)

  PIPELINE CONFIGS (4 per ideator):
    ds-pipe   = deepseek full pipeline (generate → verify ↔ revise → judge)
    oss-pipe  = gpt-oss full pipeline
    ds-gen    = deepseek generate-only (ideate → generate → judge)
    oss-gen   = gpt-oss generate-only

Total: 12 conditions × 6 dev-set problems × 1 seed = 72 trials.
Judge is always gemini/gemini-3-flash-preview.

Usage:
    uv run experiments/ideator_capability_20260328.py --mock
    uv run experiments/ideator_capability_20260328.py
    uv run experiments/ideator_capability_20260328.py --conditions 1,5,9
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

EXPERIMENT_NAME = "ideator_capability_oai"

DESCRIPTION = """
Hypothesis: A stronger ideator model produces higher-quality seed ideas that
lead to better solutions, especially on harder problems. The effect should be
larger in generate-only mode (where idea quality is all that differentiates
branches) than in full-pipeline mode (where verify/revise can compensate for
weaker ideas).

Variables:
  Independent: ideator capability tier (lite/flash/pro) × pipeline model (ds/oss) × mode (full/gen)
  Dependent:   judge score (0-7)
  Controlled:  judge model, dev set, seed, prompts
"""

# --- Models ---

DS  = "openrouter/deepseek/deepseek-v3.2"
OSS = "openrouter/openai/gpt-oss-120b"
LIT = "openai/gpt-5.4-nano"
FLASH = "openai/gpt-5.4-mini"
PRO = "openai/gpt-5.4"

JUDGE_MODEL = "gemini/gemini-3-flash-preview"

SEEDS = [42]
PASS_THRESHOLD = 6
ITERATIONS = 3
NUM_IDEAS = 3
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 12
TRIAL_TIMEOUT = 3000
LITELLM_TIMEOUT = 540

# ── Condition definitions ──────────────────────────────────────────────────

CONDITIONS = {
    # ── NANO ideator (gpt-5.4-nano) ──
    1:  {"name": "nano→ds-pipe",    "mode": "full",     "ideator": LIT, "generator": DS,  "verifier": DS,  "reviser": DS},
    2:  {"name": "nano→oss-pipe",   "mode": "full",     "ideator": LIT, "generator": OSS, "verifier": OSS, "reviser": OSS},
    3:  {"name": "nano→ds-gen",     "mode": "generate", "ideator": LIT, "generator": DS},
    4:  {"name": "nano→oss-gen",    "mode": "generate", "ideator": LIT, "generator": OSS},

    # ── MINI ideator (gpt-5.4-mini) ──
    5:  {"name": "mini→ds-pipe",    "mode": "full",     "ideator": FLASH, "generator": DS,  "verifier": DS,  "reviser": DS},
    6:  {"name": "mini→oss-pipe",   "mode": "full",     "ideator": FLASH, "generator": OSS, "verifier": OSS, "reviser": OSS},
    7:  {"name": "mini→ds-gen",     "mode": "generate", "ideator": FLASH, "generator": DS},
    8:  {"name": "mini→oss-gen",    "mode": "generate", "ideator": FLASH, "generator": OSS},

    # ── STANDARD ideator (gpt-5.4) ──
    9:  {"name": "std→ds-pipe",     "mode": "full",     "ideator": PRO, "generator": DS,  "verifier": DS,  "reviser": DS},
    10: {"name": "std→oss-pipe",    "mode": "full",     "ideator": PRO, "generator": OSS, "verifier": OSS, "reviser": OSS},
    11: {"name": "std→ds-gen",      "mode": "generate", "ideator": PRO, "generator": DS},
    12: {"name": "std→oss-gen",     "mode": "generate", "ideator": PRO, "generator": OSS},
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


def run_trial(
    problem_id, problem, cond_id, cond, seed, prompts, log_path, log_lock, mock=False,
):
    """Run one trial for a given condition."""
    from pipeline import generate, verify, revise, judge, ideate, make_logger

    np.random.seed(seed)
    random.seed(seed)

    cname = cond["name"]
    mode = cond["mode"]
    tag = f"[{_ts()}] [c{cond_id}:{cname}|{problem_id}|s{seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # ── Step 1: Ideate (if condition has ideator) ──
    has_ideator = "ideator" in cond
    if has_ideator:
        ideator_model = cond["ideator"]
        print(f"{tag} ideate ({_short(ideator_model)})", flush=True)
        ideas = ideate(
            problem=problem["text"], system=prompts["ideator"],
            model=ideator_model, max_tokens=4096, logger=logger,
            num_ideas=NUM_IDEAS, mock=mock,
        )
        print(f"{tag} got {len(ideas)} ideas: {[i['name'] for i in ideas]}", flush=True)
    else:
        ideas = [None]  # single branch, no seeded idea

    # ── Step 2: Run branches (in parallel if multiple) ──
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
        branch_result = run_branch(
            problem_id, problem, cond_id, cond, seed, 0, ideas[0],
            prompts, log_path, log_lock, tag, mock,
        )
        branches.append(branch_result)

    # ── Step 3: Pick best branch ──
    branches.sort(key=lambda b: b.get("score", 0), reverse=True)
    best = branches[0]

    elapsed = round(time.time() - t0, 2)
    all_scores = [b.get("score", 0) for b in branches]
    if has_ideator:
        print(f"{tag} best={best.get('score',0)}/7 (all: {all_scores}) {elapsed}s", flush=True)
    else:
        print(f"{tag} score={best.get('score',0)}/7 {elapsed}s", flush=True)

    return {
        "condition_id": cond_id,
        "condition_name": cname,
        "mode": mode,
        "problem_id": problem_id,
        "level": problem["level"],
        "role": problem.get("role", ""),
        "seed": seed,
        "score": best.get("score", 0),
        "passed": best.get("score", 0) >= PASS_THRESHOLD,
        "all_branch_scores": all_scores if has_ideator else None,
        "best_idea_idx": best.get("idea_idx") if has_ideator else None,
        "elapsed_s": elapsed,
        "final_solution": best.get("final_solution"),
        "verdict": best.get("verdict"),
        "branches": branches if has_ideator else None,
        "loop_log": best.get("loop_log", []),
        "stopped_early": best.get("stopped_early", False),
        "iterations_run": best.get("iterations_run", 0),
        "models": {
            "generator": _short(cond["generator"]),
            "verifier": _short(cond.get("verifier", cond["generator"])),
            "reviser": _short(cond.get("reviser", cond["generator"])),
            "ideator": _short(cond["ideator"]) if has_ideator else None,
        },
    }


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

    # ── Generate ──
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

    # ── Verify/Revise loop (full mode only) ──
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
                loop_log.append({"iteration": i+1, "verdict": "correct",
                                 "critique": critique, "solution": solution})
                break

            print(f"{btag} revise i={i+1} ({_short(rev_model)})", flush=True)
            new_solution = revise(
                problem=problem["text"], solution=solution, critique=critique,
                system=prompts["reviser"], model=rev_model, max_tokens=MAX_TOKENS,
                logger=logger, iteration=i+1, mock=mock,
            )
            loop_log.append({"iteration": i+1, "verdict": "issues_found",
                             "critique": critique, "solution_before": solution,
                             "solution_after": new_solution})
            solution = new_solution
            print(f"{btag} revised ({len(solution)} chars, {time.time()-t0:.1f}s)", flush=True)

    # ── Judge ──
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {
            ex.submit(run_trial, pid, problems[pid], cid, conditions[cid],
                      seed, prompts, log_path, log_lock, mock): (cid, pid, seed)
            for cid, pid, seed in trials
        }
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            cid, pid, seed = futs[fut]
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                cname = conditions[cid]["name"]
                print(f"[{_ts()}] FAILED [c{cid}:{cname}|{pid}|s{seed}]: {e}", flush=True)
                results.append({
                    "condition_id": cid, "condition_name": cname,
                    "mode": conditions[cid]["mode"],
                    "problem_id": pid, "level": problems[pid]["level"],
                    "role": problems[pid].get("role", ""), "seed": seed,
                    "score": None, "passed": False, "error": str(e),
                })

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
    print("IDEATOR CAPABILITY SCALING — RESULTS")
    print(f"{'='*110}\n")

    # ── Per-condition summary ──
    print(f"{'Cond':>4}  {'Name':<22} {'Mode':<9} {'Mean':>6} {'Pass':>6} {'Err':>4}  Ideator")
    print("-" * 90)
    for cid in cids:
        cond = conditions[cid]
        valid = [r for r in results if r["condition_id"] == cid and r.get("score") is not None]
        errs = sum(1 for r in results if r["condition_id"] == cid and r.get("error"))
        if valid:
            scores = [r["score"] for r in valid]
            n_pass = sum(1 for r in valid if r["passed"])
            mean = sum(scores) / len(scores)
            ide = _short(cond["ideator"]) if "ideator" in cond else "(none)"
            err_s = str(errs) if errs else ""
            print(f"  {cid:>2}   {cond['name']:<22} {cond['mode']:<9} {mean:5.2f}/7  "
                  f"{n_pass:>2}/{len(valid):<2} {err_s:>4}  {ide}")
        else:
            print(f"  {cid:>2}   {cond['name']:<22}  (all errors, n={errs})")

    # ── Ideator scaling comparison ──
    # Group by (pipeline_model, mode) and compare across ideator tiers
    print(f"\n{'─'*110}")
    print("\nIDEATOR SCALING (nano → mini → std):\n")

    comparisons = [
        ("DS full pipeline",  [1, 5, 9]),
        ("OSS full pipeline", [2, 6, 10]),
        ("DS generate-only",  [3, 7, 11]),
        ("OSS generate-only", [4, 8, 12]),
    ]

    for label, cid_list in comparisons:
        print(f"  {label}:")
        lite_mean, _ = _mean_score(results, cid_list[0])
        for cid in cid_list:
            mean, n = _mean_score(results, cid)
            if mean is not None:
                cond = conditions[cid]
                ide = _short(cond["ideator"])
                delta = ""
                if lite_mean is not None and cid != cid_list[0]:
                    d = mean - lite_mean
                    delta = f"  ({d:+.2f} vs lite)"
                print(f"    {ide:<24} {mean:.2f}/7{delta}")
        print()

    # ── Per-problem breakdown ──
    print(f"{'─'*110}")
    print("\nPer-problem scores:\n")

    # Header
    hdr = f"  {'Problem':<16}"
    for cid in cids:
        hdr += f" {cid:>3}"
    print(hdr)
    names = f"  {'':16}"
    for cid in cids:
        n = conditions[cid]["name"][:3]
        names += f" {n:>3}"
    print(names)
    print()

    for pid in pids:
        row = f"  {pid:<16}"
        for cid in cids:
            trial = [r for r in results if r["condition_id"] == cid
                     and r["problem_id"] == pid and r.get("score") is not None]
            if trial:
                s = trial[0]["score"]
                row += f" {s:>3}"
            else:
                row += f" {'—':>3}"
        print(row)

    # ── Full vs generate-only comparison for each ideator tier ──
    print(f"\n{'─'*110}")
    print("\nFULL PIPELINE UPLIFT (full − generate-only) by ideator tier:\n")

    uplift_groups = [
        ("Lite",       [(1, 3), (2, 4)]),
        ("Flash",      [(5, 7), (6, 8)]),
        ("Pro",        [(9, 11), (10, 12)]),
    ]

    for tier_label, pairs in uplift_groups:
        print(f"  {tier_label}:")
        for full_cid, gen_cid in pairs:
            full_mean, _ = _mean_score(results, full_cid)
            gen_mean, _ = _mean_score(results, gen_cid)
            if full_mean is not None and gen_mean is not None:
                delta = full_mean - gen_mean
                pipe_model = "DS" if "ds" in conditions[full_cid]["name"] else "OSS"
                print(f"    {pipe_model}: gen={gen_mean:.2f} → full={full_mean:.2f}  ({delta:+.2f})")
        print()

    print()


def main():
    parser = argparse.ArgumentParser(description="Ideator capability scaling experiment")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--conditions", type=str, default=None,
                        help="Comma-separated condition IDs to run (default: all)")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    # Select conditions
    if args.conditions:
        cond_ids = [int(x.strip()) for x in args.conditions.split(",")]
        conditions = {k: v for k, v in CONDITIONS.items() if k in cond_ids}
    else:
        conditions = CONDITIONS

    problems = load_problems()

    n_trials = len(conditions) * len(problems) * len(SEEDS)
    print(f"Ideator Capability Scaling Experiment")
    print(f"  {len(conditions)} conditions × {len(problems)} problems × {len(SEEDS)} seeds = {n_trials} trials")
    print(f"  Ideators: lite={_short(LIT)}, flash={_short(FLASH)}, pro={_short(PRO)}")
    print(f"  Pipeline: ds={_short(DS)}, oss={_short(OSS)}")
    print(f"  Judge: {_short(JUDGE_MODEL)}")
    print(f"  Workers: {MAX_WORKERS}  Timeout: {TRIAL_TIMEOUT}s")
    print()

    for cid, cond in sorted(conditions.items()):
        gen = _short(cond["generator"])
        ide = f"ide={_short(cond['ideator'])} " if "ideator" in cond else ""
        mode = cond["mode"]
        if mode == "full":
            ver = _short(cond.get("verifier", cond["generator"]))
            rev = _short(cond.get("reviser", cond["generator"]))
            print(f"  c{cid:>2}: {cond['name']:<22}  {ide}gen={gen} ver={ver} rev={rev}")
        else:
            print(f"  c{cid:>2}: {cond['name']:<22}  {ide}gen={gen}  (generate-only)")
    print()

    for pid, p in sorted(problems.items()):
        print(f"  {pid:<20s}  {p.get('role','')}")

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
        "seeds": SEEDS,
        "iterations": ITERATIONS,
        "num_ideas": NUM_IDEAS,
        "pass_threshold": PASS_THRESHOLD,
        "judge_model": JUDGE_MODEL,
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
