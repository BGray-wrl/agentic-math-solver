#!/usr/bin/env python3
"""
Model diversity experiment: does mixing deepseek-v3.2, gpt-oss-120b, and
gemini-3.1-flash-lite across pipeline stages help or hurt?

Tests 12 conditions on the 6-problem dev set with pass@3 (seeds 42,123,7):

  BASELINES (3 conditions — same model at all stages):
    1. deepseek-self:     gen=ds  ver=ds  rev=ds
    2. oss-self:          gen=oss ver=oss rev=oss
    3. lite-self:         gen=lit ver=lit rev=lit

  CROSS-VERIFY (4 conditions — different verifier/reviser, same generator):
    4. ds-gen+oss-vr:     gen=ds  ver=oss rev=oss
    5. oss-gen+ds-vr:     gen=oss ver=ds  rev=ds
    6. ds-gen+lit-vr:     gen=ds  ver=lit rev=lit
    7. oss-gen+lit-vr:    gen=oss ver=lit rev=lit

  CROSS-IDEATE (2 conditions — different ideator, same pipeline model):
    8. lit-ideas+ds-pipe: ideate=lit  gen/ver/rev=ds
    9. lit-ideas+oss-pipe: ideate=lit gen/ver/rev=oss

  MIXED-STAGE (3 conditions — different model at every stage):
   10. ds-gen+oss-ver+ds-rev:  gen=ds  ver=oss rev=ds   (oss catches ds mistakes, ds fixes)
   11. oss-gen+ds-ver+oss-rev: gen=oss ver=ds  rev=oss  (ds catches oss mistakes, oss fixes)
   12. round-robin:            stage model cycles ds→oss→lit→ds...

All conditions run full pipeline (3 verify/revise iterations).
Judge is always gemini/gemini-3-flash-preview.

Usage:
    uv run experiments/model_diversity_20260328.py --mock
    uv run experiments/model_diversity_20260328.py
    uv run experiments/model_diversity_20260328.py --conditions 1,4,5   # subset
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

EXPERIMENT_NAME = "model_diversity"

DS  = "openrouter/deepseek/deepseek-v3.2"
OSS = "openrouter/openai/gpt-oss-120b"
LIT = "openrouter/google/gemini-3.1-flash-lite-preview"

JUDGE_MODEL = "gemini/gemini-3-flash-preview"

SEEDS = [42, 123, 7]
PASS_THRESHOLD = 6
ITERATIONS = 3
NUM_IDEAS = 3
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 8
TRIAL_TIMEOUT = 3000
LITELLM_TIMEOUT = 540

# ── Condition definitions ──────────────────────────────────────────────────
# Each condition specifies which model handles each stage.
# "ideator" is optional — if absent, no seed-ideas step.
# "verifier_pattern" / "reviser_pattern" can be a list for per-iteration cycling.

CONDITIONS = {
    # ── BASELINES ──
    1:  {"name": "deepseek-self",
         "generator": DS, "verifier": DS, "reviser": DS},
    2:  {"name": "oss-self",
         "generator": OSS, "verifier": OSS, "reviser": OSS},
    3:  {"name": "lite-self",
         "generator": LIT, "verifier": LIT, "reviser": LIT},

    # ── CROSS-VERIFY (different verifier/reviser) ──
    4:  {"name": "ds-gen+oss-vr",
         "generator": DS, "verifier": OSS, "reviser": OSS},
    5:  {"name": "oss-gen+ds-vr",
         "generator": OSS, "verifier": DS, "reviser": DS},
    6:  {"name": "ds-gen+lit-vr",
         "generator": DS, "verifier": LIT, "reviser": LIT},
    7:  {"name": "oss-gen+lit-vr",
         "generator": OSS, "verifier": LIT, "reviser": LIT},

    # ── CROSS-IDEATE (different ideator, pipeline model does the rest) ──
    8:  {"name": "lit-ideas+ds-pipe",
         "ideator": LIT, "generator": DS, "verifier": DS, "reviser": DS},
    9:  {"name": "lit-ideas+oss-pipe",
         "ideator": LIT, "generator": OSS, "verifier": OSS, "reviser": OSS},

    # ── MIXED-STAGE (different model at each step) ──
    10: {"name": "ds-gen+oss-ver+ds-rev",
         "generator": DS, "verifier": OSS, "reviser": DS},
    11: {"name": "oss-gen+ds-ver+oss-rev",
         "generator": OSS, "verifier": DS, "reviser": OSS},
    12: {"name": "round-robin",
         "generator": DS,
         "verifier_pattern": [OSS, LIT, DS],
         "reviser_pattern":  [LIT, DS, OSS]},
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


def get_model_for_iteration(cond: dict, stage: str, iteration: int) -> str:
    """Resolve which model to use for a given stage and iteration.

    Supports both fixed models and per-iteration patterns.
    """
    pattern_key = f"{stage}_pattern"
    if pattern_key in cond:
        pattern = cond[pattern_key]
        return pattern[iteration % len(pattern)]
    return cond[stage]


def _short(model: str) -> str:
    """Short display name for a model."""
    return model.split("/")[-1][:12]


def run_trial(
    problem_id, problem, cond_id, cond, seed, prompts, log_path, log_lock, mock=False,
):
    """Run one trial for a given condition."""
    from pipeline import generate, verify, revise, judge, ideate, make_logger

    np.random.seed(seed)
    random.seed(seed)

    cname = cond["name"]
    tag = f"[{_ts()}] [c{cond_id}:{cname}|{problem_id}|s{seed}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # ── Step 1: Ideate (if cross-ideate condition) ──
    has_ideator = "ideator" in cond
    if has_ideator:
        ideator_model = cond["ideator"]
        print(f"{tag} ideate ({_short(ideator_model)})", flush=True)
        ideas = ideate(
            problem=problem["text"], system=prompts["ideator"],
            model=ideator_model, max_tokens=4096, logger=logger,
            num_ideas=NUM_IDEAS, mock=mock,
        )
        print(f"{tag} got {len(ideas)} ideas", flush=True)
    else:
        ideas = [None]  # single branch, no seeded idea

    # ── Step 2: Run branches ──
    branches = []
    for idea_idx, idea in enumerate(ideas):
        branch_result = run_branch(
            problem_id, problem, cond_id, cond, seed, idea_idx, idea,
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
        # Model assignment for analysis
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
    """Run one branch: generate → verify ↔ revise → judge."""
    from pipeline import generate, verify, revise, judge, make_logger

    gen_model = cond["generator"]

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

    # ── Verify/Revise loop ──
    stopped_early = False
    for i in range(ITERATIONS):
        ver_model = get_model_for_iteration(cond, "verifier", i)
        rev_model = get_model_for_iteration(cond, "reviser", i)

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
                             "verifier": _short(ver_model),
                             "critique": critique, "solution": solution})
            break

        print(f"{btag} revise i={i+1} ({_short(rev_model)})", flush=True)
        new_solution = revise(
            problem=problem["text"], solution=solution, critique=critique,
            system=prompts["reviser"], model=rev_model, max_tokens=MAX_TOKENS,
            logger=logger, iteration=i+1, mock=mock,
        )
        loop_log.append({"iteration": i+1, "verdict": "issues_found",
                         "verifier": _short(ver_model), "reviser": _short(rev_model),
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

    # Build trial list: (cond_id, problem_id, seed)
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
                    "problem_id": pid, "level": problems[pid]["level"],
                    "role": problems[pid].get("role", ""), "seed": seed,
                    "score": None, "passed": False, "error": str(e),
                })

    return results, log_path


def print_results(results, conditions, problems):
    pids = sorted(problems.keys())
    cids = sorted(conditions.keys())

    print(f"\n{'='*100}")
    print("MODEL DIVERSITY — RESULTS")
    print(f"{'='*100}\n")

    # ── Per-condition summary ──
    print(f"{'Cond':<4} {'Name':<28} {'Mean':>6} {'Pass':>8} {'Err':>5}  Config")
    print("-" * 95)
    for cid in cids:
        cond = conditions[cid]
        valid = [r for r in results if r["condition_id"] == cid and r.get("score") is not None]
        errs = sum(1 for r in results if r["condition_id"] == cid and r.get("error"))
        if valid:
            scores = [r["score"] for r in valid]
            n_pass = sum(1 for r in valid if r["passed"])
            mean = sum(scores) / len(scores)
            # Config summary
            gen = _short(cond["generator"])
            ver = _short(cond.get("verifier", cond["generator"]))
            rev = _short(cond.get("reviser", cond["generator"]))
            ide = _short(cond["ideator"]) + "→" if "ideator" in cond else ""
            if "verifier_pattern" in cond:
                ver = "cycle"
                rev = "cycle"
            config = f"{ide}G:{gen} V:{ver} R:{rev}"
            err_s = str(errs) if errs else ""
            print(f"  {cid:<2}  {cond['name']:<28} {mean:5.2f}/7  "
                  f"{n_pass:>2}/{len(valid):<3} {err_s:>5}  {config}")
        else:
            print(f"  {cid:<2}  {cond['name']:<28}  (all errors, n={errs})")

    # ── Group comparisons ──
    print(f"\n{'─'*100}")
    print("\nBASELINE vs CROSS-VERIFY (does a different verifier/reviser help?):")
    for base_cid, cross_cids in [(1, [4, 6, 10]), (2, [5, 7, 11])]:
        base_valid = [r for r in results if r["condition_id"] == base_cid and r.get("score") is not None]
        if not base_valid:
            continue
        base_mean = sum(r["score"] for r in base_valid) / len(base_valid)
        base_name = conditions[base_cid]["name"]
        print(f"\n  {base_name}: {base_mean:.2f}/7")
        for ccid in cross_cids:
            cross_valid = [r for r in results if r["condition_id"] == ccid and r.get("score") is not None]
            if cross_valid:
                cross_mean = sum(r["score"] for r in cross_valid) / len(cross_valid)
                delta = cross_mean - base_mean
                d = f"{delta:+.2f}" if delta != 0 else "  0.00"
                print(f"    → {conditions[ccid]['name']:<28} {cross_mean:.2f}/7  ({d})")

    # ── Cross-ideate comparison ──
    print(f"\n{'─'*100}")
    print("\nCROSS-IDEATE (does using flash-lite for ideas help?):")
    for base_cid, cross_cid in [(1, 8), (2, 9)]:
        base_valid = [r for r in results if r["condition_id"] == base_cid and r.get("score") is not None]
        cross_valid = [r for r in results if r["condition_id"] == cross_cid and r.get("score") is not None]
        if base_valid and cross_valid:
            base_mean = sum(r["score"] for r in base_valid) / len(base_valid)
            cross_mean = sum(r["score"] for r in cross_valid) / len(cross_valid)
            delta = cross_mean - base_mean
            d = f"{delta:+.2f}" if delta != 0 else "  0.00"
            print(f"  {conditions[base_cid]['name']:<28} {base_mean:.2f}/7")
            print(f"    → {conditions[cross_cid]['name']:<28} {cross_mean:.2f}/7  ({d})")

    # ── Per-problem breakdown for key conditions ──
    print(f"\n{'─'*100}")
    print("\nPer-problem scores (mean over seeds):")
    hdr = f"  {'Problem':<16}"
    for cid in cids:
        hdr += f"  {cid:>4}"
    print(hdr)
    print(f"  {'':16}" + "".join(f"  {conditions[c]['name'][:4]:>4}" for c in cids))
    print()
    for pid in pids:
        row = f"  {pid:<16}"
        for cid in cids:
            trials = [r for r in results if r["condition_id"] == cid
                      and r["problem_id"] == pid and r.get("score") is not None]
            if trials:
                mean = sum(r["score"] for r in trials) / len(trials)
                row += f"  {mean:4.1f}"
            else:
                row += f"  {'—':>4}"
        print(row)

    # ── ds↔oss mutual benefit check ──
    print(f"\n{'─'*100}")
    print("\nDEEPSEEK ↔ OSS MUTUAL BENEFIT:")
    for label, base, cross in [
        ("ds improved by oss?", 1, [4, 10]),
        ("oss improved by ds?", 2, [5, 11]),
    ]:
        base_valid = [r for r in results if r["condition_id"] == base and r.get("score") is not None]
        if not base_valid:
            continue
        base_mean = sum(r["score"] for r in base_valid) / len(base_valid)
        print(f"\n  {label}")
        print(f"    baseline ({conditions[base]['name']}): {base_mean:.2f}/7")
        for ccid in cross:
            cross_valid = [r for r in results if r["condition_id"] == ccid and r.get("score") is not None]
            if cross_valid:
                cross_mean = sum(r["score"] for r in cross_valid) / len(cross_valid)
                delta = cross_mean - base_mean
                d = f"{delta:+.2f}" if delta != 0 else "  0.00"
                verdict = "HELPS" if delta > 0.5 else "HURTS" if delta < -0.5 else "NEUTRAL"
                print(f"    {conditions[ccid]['name']:<28} {cross_mean:.2f}/7  ({d}) → {verdict}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Model diversity experiment")
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
    print(f"Model Diversity Experiment")
    print(f"  {len(conditions)} conditions × {len(problems)} problems × {len(SEEDS)} seeds = {n_trials} trials")
    print(f"  Models: ds={_short(DS)}, oss={_short(OSS)}, lit={_short(LIT)}")
    print(f"  Judge: {_short(JUDGE_MODEL)}")
    print(f"  Workers: {MAX_WORKERS}  Timeout: {TRIAL_TIMEOUT}s")
    print()

    for cid, cond in sorted(conditions.items()):
        gen = _short(cond["generator"])
        ver = _short(cond.get("verifier", "?"))
        rev = _short(cond.get("reviser", "?"))
        ide = f"ide={_short(cond['ideator'])} " if "ideator" in cond else ""
        pat = " (cycling)" if "verifier_pattern" in cond else ""
        print(f"  c{cid:>2}: {cond['name']:<28}  {ide}gen={gen} ver={ver} rev={rev}{pat}")
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
