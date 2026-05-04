"""
Experiment: Cross-judged pass@2 comparison — nemotron-120b vs deepseek-v3.2 on IMO-easy/medium.
Date: 2026-03-26
Hypothesis: With ground-truth judging and a stronger cross-judge, both models will score lower
  than in the self-judged run, with the gap between easy/medium widening.

Variables:
  Independent: generator model (nemotron vs deepseek)
  Dependent: IMO 0-7 score; pass@2 rate (≥6/7 on at least one of 2 attempts)
  Controlled: problem set (42 IMO-easy + IMO-medium), ground-truth judging,
              cross-judge (nemotron judges deepseek; deepseek judges nemotron),
              generator prompt, judge prompt, max_tokens
"""

import sys
import re
import csv
import json
import time
import random
import argparse
import threading
import traceback
import concurrent.futures
import numpy as np
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402
litellm.request_timeout = 540

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEEDS = [42, 123]  # pass@2

NEMOTRON = "openrouter/nvidia/nemotron-3-super-120b-a12b"
DEEPSEEK  = "openrouter/deepseek/deepseek-v3.2"

# (generator, judge) pairs — each model judged by the other
GENERATOR_JUDGE_PAIRS = [
    (NEMOTRON, DEEPSEEK),
    (DEEPSEEK,  NEMOTRON),
]

TARGET_LEVELS = {"IMO-easy"}

PASS_THRESHOLD = 6  # out of 7 — counts as "correct" for pass@2

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"

GENERATOR_PROMPT_PATH = PROMPTS_DIR / "generator.md"
JUDGE_PROMPT_PATH     = PROMPTS_DIR / "judge.md"

MAX_TOKENS_GEN   = 32000
MAX_TOKENS_JUDGE = 4096
MAX_WORKERS      = 12
TRIAL_TIMEOUT    = 600   # seconds per trial


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S")


def parse_points_score(verdict_text: str) -> int | None:
    """Extract N from '<points>N out of 7</points>'. Returns None if not found."""
    m = re.search(r"<points>\s*(\d)\s*out of 7\s*</points>", verdict_text, re.IGNORECASE)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Load resources
# ---------------------------------------------------------------------------

def load_problems() -> dict:
    """Return {problem_id: {text, solution, level}} filtered to TARGET_LEVELS."""
    problems = {}
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("Level") in TARGET_LEVELS:
                problems[row["Problem ID"]] = {
                    "text":     row["Problem"],
                    "solution": row["Solution"],
                    "level":    row["Level"],
                }
    return problems


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Single trial
# ---------------------------------------------------------------------------

def run_trial(
    problem_id: str,
    problem_text: str,
    ground_truth: str,
    problem_level: str,
    gen_model: str,
    judge_model: str,
    seed: int,
    generator_prompt: str,
    judge_prompt: str,
    log_path: Path,
    log_lock: threading.Lock,
    mock: bool = False,
) -> dict:
    """Generate with gen_model, judge with judge_model using ground truth. Returns result dict."""
    from pipeline import generate, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    gen_short   = gen_model.split("/")[-1]
    judge_short = judge_model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|gen={gen_short}|seed={seed}]"

    _base_logger = make_logger(str(log_path))
    def logger(call_type, iteration, mdl, system, prompt, response, elapsed):
        with log_lock:
            _base_logger(call_type, iteration, mdl, system, prompt, response, elapsed)

    ts_start = time.time()

    print(f"{tag} generate → {gen_short} (max_tokens={MAX_TOKENS_GEN})", flush=True)
    try:
        solution = generate(
            problem=problem_text,
            system=generator_prompt,
            model=gen_model,
            max_tokens=MAX_TOKENS_GEN,
            logger=logger,
            iteration=0,
            mock=mock,
        )
    except Exception as e:
        print(f"{tag} ERROR during generate: {e}\n{traceback.format_exc()}", flush=True)
        raise

    gen_elapsed = round(time.time() - ts_start, 2)
    print(f"{tag} generate done in {gen_elapsed}s ({len(solution)} chars) → judge={judge_short}", flush=True)

    try:
        verdict_text = judge(
            problem=problem_text,
            candidate=solution,
            ground_truth=ground_truth,
            system=judge_prompt,
            model=judge_model,
            max_tokens=MAX_TOKENS_JUDGE,
            logger=logger,
            mock=mock,
        )
    except Exception as e:
        print(f"{tag} ERROR during judge: {e}\n{traceback.format_exc()}", flush=True)
        raise

    score = parse_points_score(verdict_text)
    total_elapsed = round(time.time() - ts_start, 2)

    if score is None:
        print(f"{tag} WARNING: could not parse score from verdict. Defaulting to 0.", flush=True)
        score = 0

    print(f"{tag} → {score}/7  total={total_elapsed}s", flush=True)

    return {
        "problem_id":    problem_id,
        "level":         problem_level,
        "gen_model":     gen_model,
        "judge_model":   judge_model,
        "seed":          seed,
        "score":         score,
        "pass":          score >= PASS_THRESHOLD,
        "elapsed_s":     total_elapsed,
        "solution":      solution,       # full text
        "verdict":       verdict_text,   # full text
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cross-judged pass@2: nemotron vs deepseek on IMO-easy/medium")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    problems = load_problems()
    generator_prompt = load_prompt(GENERATOR_PROMPT_PATH)
    judge_prompt     = load_prompt(JUDGE_PROMPT_PATH)

    problem_ids = sorted(problems.keys())
    print(f"Problems: {len(problem_ids)}  ({', '.join(sorted(TARGET_LEVELS))})")
    print(f"Generator-judge pairs: {len(GENERATOR_JUDGE_PAIRS)}")
    print(f"Seeds (pass@{len(SEEDS)}): {SEEDS}")
    total_trials = len(problem_ids) * len(GENERATOR_JUDGE_PAIRS) * len(SEEDS)
    print(f"Total trials: {len(problem_ids)} × {len(GENERATOR_JUDGE_PAIRS)} pairs × {len(SEEDS)} seeds = {total_trials}")
    if args.mock:
        print("[MOCK MODE]")
    print()

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{ts}.jsonl"
    log_lock = threading.Lock()

    trials = [
        (pid, gen_model, judge_model, seed)
        for pid in problem_ids
        for (gen_model, judge_model) in GENERATOR_JUDGE_PAIRS
        for seed in SEEDS
    ]

    print(f"Submitting {len(trials)} trials to ThreadPoolExecutor(max_workers={MAX_WORKERS})\n", flush=True)

    all_results = []
    completed   = 0

    def _run(pid, gen_model, judge_model, seed):
        return run_trial(
            problem_id=pid,
            problem_text=problems[pid]["text"],
            ground_truth=problems[pid]["solution"],
            problem_level=problems[pid]["level"],
            gen_model=gen_model,
            judge_model=judge_model,
            seed=seed,
            generator_prompt=generator_prompt,
            judge_prompt=judge_prompt,
            log_path=log_path,
            log_lock=log_lock,
            mock=args.mock,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_trial = {
            executor.submit(_run, pid, gen, jdg, seed): (pid, gen, jdg, seed)
            for pid, gen, jdg, seed in trials
        }
        for future in concurrent.futures.as_completed(future_to_trial, timeout=TRIAL_TIMEOUT * len(trials)):
            pid, gen, jdg, seed = future_to_trial[future]
            completed += 1
            try:
                result = future.result(timeout=TRIAL_TIMEOUT)
                all_results.append(result)
            except Exception as e:
                gen_short = gen.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|gen={gen_short}|seed={seed}]: {e}", flush=True)
                all_results.append({
                    "problem_id":  pid,
                    "level":       problems[pid]["level"],
                    "gen_model":   gen,
                    "judge_model": jdg,
                    "seed":        seed,
                    "score":       None,
                    "pass":        False,
                    "elapsed_s":   0,
                    "error":       str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{len(trials)}", flush=True)

    # ---------------------------------------------------------------------------
    # Aggregate
    # ---------------------------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    for gen_model, judge_model in GENERATOR_JUDGE_PAIRS:
        gen_short   = gen_model.split("/")[-1]
        judge_short = judge_model.split("/")[-1]
        print(f"\n  Generator: {gen_short}  |  Judge: {judge_short}")

        valid = [r for r in all_results if r["gen_model"] == gen_model and r.get("score") is not None]

        # Overall
        scores   = [r["score"] for r in valid]
        pass_per_problem = {}
        for pid in problem_ids:
            pid_scores = [r["score"] for r in valid if r["problem_id"] == pid and r.get("score") is not None]
            if pid_scores:
                pass_per_problem[pid] = any(s >= PASS_THRESHOLD for s in pid_scores)

        pass2_rate = np.mean(list(pass_per_problem.values())) if pass_per_problem else 0.0
        print(f"  Overall   mean={np.mean(scores):.3f}±{np.std(scores):.3f}  pass@2={pass2_rate:.1%}  n={len(scores)}")

        # Per level
        for level in sorted(TARGET_LEVELS):
            lv = [r for r in valid if r["level"] == level]
            if not lv:
                continue
            lv_scores = [r["score"] for r in lv]
            lv_pass   = {}
            for pid in [p for p in problem_ids if problems[p]["level"] == level]:
                ps = [r["score"] for r in lv if r["problem_id"] == pid]
                if ps:
                    lv_pass[pid] = any(s >= PASS_THRESHOLD for s in ps)
            lv_pass2 = np.mean(list(lv_pass.values())) if lv_pass else 0.0
            print(f"  {level:<12} mean={np.mean(lv_scores):.3f}±{np.std(lv_scores):.3f}  pass@2={lv_pass2:.1%}  n={len(lv_scores)}")

    # Per-problem table
    print("\n--- Per-problem scores ---")
    header = f"{'Problem':<20} {'Level':<12}"
    for gen_model, judge_model in GENERATOR_JUDGE_PAIRS:
        g = gen_model.split("/")[-1][:16]
        header += f"  {g:>18}"
    print(header)
    print("-" * (20 + 12 + len(GENERATOR_JUDGE_PAIRS) * 20))

    for pid in problem_ids:
        row = f"{pid:<20} {problems[pid]['level']:<12}"
        for gen_model, judge_model in GENERATOR_JUDGE_PAIRS:
            r_list = [r for r in all_results if r["problem_id"] == pid and r["gen_model"] == gen_model and r.get("score") is not None]
            if r_list:
                s = [r["score"] for r in r_list]
                passed = "✓" if any(x >= PASS_THRESHOLD for x in s) else " "
                row += f"  {np.mean(s):4.1f}±{np.std(s):.1f} {passed} {'/'.join(str(x) for x in s):>6}"
            else:
                row += f"  {'—':>18}"
        print(row)

    # ---------------------------------------------------------------------------
    # Save
    # ---------------------------------------------------------------------------

    run_ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix   = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"cross_judge_imo_{run_ts}{suffix}.json"

    output = {
        "experiment":           "cross_judge_imo",
        "date":                 "2026-03-26",
        "mock":                 args.mock,
        "seeds":                SEEDS,
        "pass_threshold":       PASS_THRESHOLD,
        "target_levels":        sorted(TARGET_LEVELS),
        "generator_judge_pairs": GENERATOR_JUDGE_PAIRS,
        "problems":             problem_ids,
        "all_results":          all_results,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log: {log_path}")


if __name__ == "__main__":
    main()
