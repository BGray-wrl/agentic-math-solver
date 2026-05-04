"""
Experiment: Full pipeline (generate → verify ↔ revise → judge) on a mixed difficulty set.
Date: 2026-03-26
Hypothesis: The verifier/reviser loop will improve scores over bare generation,
  and the effect will be larger for DeepSeek (which showed stronger partial-credit
  patterns in prior experiments) than for Nemotron.

Models: nemotron-120b, deepseek-v3.2
Problems: (PB-Advanced AND IMO-easy) OR (PB-Basic AND IMO-medium)  — 18 problems
Judge: gemini-3-flash with ground-truth solution (0–7 IMO scoring)
Metric: pass@2 (>= 6/7 on at least 1 of 2 seeds)

Variables:
  Independent: generator/verifier/reviser model (2 conditions)
  Dependent: IMO score (0–7), pass@2 rate
  Controlled: judge model + ground truth, prompt set, iterations=3, 2 seeds
"""

import sys
import csv
import json
import re
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
ITERATIONS = 3     # max verify/revise rounds per trial

MODELS = [
    "openrouter/nvidia/nemotron-3-super-120b-a12b",
    "openrouter/deepseek/deepseek-v3.2",
]

JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"
PASS_THRESHOLD = 6  # out of 7

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"

MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 4096
MAX_WORKERS = 16
TRIAL_TIMEOUT = 900  # full pipeline per trial can be slow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S")


def parse_imo_score(verdict_text: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


# ---------------------------------------------------------------------------
# Load resources
# ---------------------------------------------------------------------------

def load_problems() -> dict:
    """Return problems matching (PB-Advanced AND IMO-easy) OR (PB-Basic AND IMO-medium)."""
    problems = {}
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid   = row["Problem ID"]
            level = row.get("Level", "")
            is_advanced_easy = pid.startswith("PB-Advanced") and level == "IMO-easy"
            is_basic_medium  = pid.startswith("PB-Basic")    and level == "IMO-medium"
            if is_advanced_easy or is_basic_medium:
                problems[pid] = {
                    "text":     row["Problem"],
                    "solution": row.get("Solution", ""),
                    "level":    level,
                    "category": "PB-Advanced" if pid.startswith("PB-Advanced") else "PB-Basic",
                }
    return problems


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Single trial — full pipeline
# ---------------------------------------------------------------------------

def run_trial(
    problem_id: str,
    problem_text: str,
    problem_solution: str,
    problem_level: str,
    problem_category: str,
    model: str,
    seed: int,
    generator_prompt: str,
    verifier_prompt: str,
    reviser_prompt: str,
    judge_prompt: str,
    log_path: Path,
    log_lock: threading.Lock,
    mock: bool = False,
) -> dict:
    from pipeline import generate, verify, revise, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    model_short = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{model_short}|seed={seed}]"

    # Thread-safe logger
    _base_logger = make_logger(str(log_path))
    def logger(call_type, iteration, mdl, system, prompt, response, elapsed):
        with log_lock:
            _base_logger(call_type, iteration, mdl, system, prompt, response, elapsed)

    ts_start = time.time()
    loop_log = []

    # --- Generate ---
    print(f"{tag} generate", flush=True)
    try:
        solution = generate(
            problem=problem_text,
            system=generator_prompt,
            model=model,
            max_tokens=MAX_TOKENS,
            logger=logger,
            iteration=0,
            mock=mock,
        )
    except Exception as e:
        print(f"{tag} ERROR generate: {e}\n{traceback.format_exc()}", flush=True)
        raise
    print(f"{tag} generate done ({len(solution)} chars, {round(time.time()-ts_start,1)}s)", flush=True)

    # --- Verify / Revise loop ---
    stopped_early = False
    for i in range(ITERATIONS):
        print(f"{tag} verify iter={i+1}", flush=True)
        try:
            critique = verify(
                problem=problem_text,
                solution=solution,
                system=verifier_prompt,
                model=model,
                max_tokens=MAX_TOKENS,
                logger=logger,
                iteration=i + 1,
                mock=mock,
            )
        except Exception as e:
            print(f"{tag} ERROR verify iter={i+1}: {e}\n{traceback.format_exc()}", flush=True)
            raise

        if "VERDICT: correct" in critique:
            print(f"{tag} verifier satisfied at iter={i+1}, stopping early", flush=True)
            stopped_early = True
            loop_log.append({"iteration": i + 1, "verdict": "correct", "stopped_early": True,
                              "critique": critique, "solution": solution})
            break

        print(f"{tag} revise iter={i+1}", flush=True)
        try:
            new_solution = revise(
                problem=problem_text,
                solution=solution,
                critique=critique,
                system=reviser_prompt,
                model=model,
                max_tokens=MAX_TOKENS,
                logger=logger,
                iteration=i + 1,
                mock=mock,
            )
        except Exception as e:
            print(f"{tag} ERROR revise iter={i+1}: {e}\n{traceback.format_exc()}", flush=True)
            raise

        loop_log.append({"iteration": i + 1, "verdict": "issues_found", "stopped_early": False,
                          "critique": critique, "solution_before": solution, "solution_after": new_solution})
        solution = new_solution
        print(f"{tag} revised ({len(solution)} chars, {round(time.time()-ts_start,1)}s elapsed)", flush=True)

    # --- Judge with ground truth ---
    print(f"{tag} judge (with ground truth)", flush=True)
    try:
        verdict_text = judge(
            problem=problem_text,
            candidate=solution,
            ground_truth=problem_solution,
            system=judge_prompt,
            model=JUDGE_MODEL,
            max_tokens=MAX_TOKENS_JUDGE,
            logger=logger,
            mock=mock,
        )
    except Exception as e:
        print(f"{tag} ERROR judge: {e}\n{traceback.format_exc()}", flush=True)
        raise

    score = parse_imo_score(verdict_text)
    passed = score >= PASS_THRESHOLD
    total_elapsed = round(time.time() - ts_start, 2)

    print(f"{tag} → score={score}/7 pass={passed} iters={len(loop_log)} stopped_early={stopped_early} total={total_elapsed}s", flush=True)

    return {
        "problem_id":       problem_id,
        "level":            problem_level,
        "category":         problem_category,
        "model":            model,
        "seed":             seed,
        "score":            score,
        "passed":           passed,
        "iterations_run":   len(loop_log),
        "stopped_early":    stopped_early,
        "elapsed_s":        total_elapsed,
        "final_solution":   solution,
        "verdict":          verdict_text,
        "loop_log":         loop_log,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Full pipeline on mixed IMO-easy/medium problems")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    problems = load_problems()
    problem_ids = sorted(problems.keys())

    generator_prompt = load_prompt(PROMPTS_DIR / "generator.md")
    verifier_prompt  = load_prompt(PROMPTS_DIR / "verifier.md")
    reviser_prompt   = load_prompt(PROMPTS_DIR / "reviser.md")
    judge_prompt     = load_prompt(PROMPTS_DIR / "judge.md")

    print(f"Problems ({len(problem_ids)}):")
    for pid in problem_ids:
        print(f"  {pid}  [{problems[pid]['level']}]  ({problems[pid]['category']})")
    print(f"Models:     {[m.split('/')[-1] for m in MODELS]}")
    print(f"Seeds:      {SEEDS}  (pass@{len(SEEDS)}, threshold >= {PASS_THRESHOLD}/7)")
    print(f"Iterations: {ITERATIONS} max verify/revise rounds")
    total_trials = len(problem_ids) * len(MODELS) * len(SEEDS)
    print(f"Total trials: {len(problem_ids)} x {len(MODELS)} x {len(SEEDS)} = {total_trials}")
    if args.mock:
        print("[MOCK MODE]")
    print()

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{ts}.jsonl"
    log_lock = threading.Lock()

    trials = [
        (pid, model, seed)
        for pid in problem_ids
        for model in MODELS
        for seed in SEEDS
    ]
    print(f"Submitting {len(trials)} trials (max_workers={MAX_WORKERS})\n", flush=True)

    all_results = []
    completed = 0

    def _run(pid, model, seed):
        return run_trial(
            problem_id=pid,
            problem_text=problems[pid]["text"],
            problem_solution=problems[pid]["solution"],
            problem_level=problems[pid]["level"],
            problem_category=problems[pid]["category"],
            model=model,
            seed=seed,
            generator_prompt=generator_prompt,
            verifier_prompt=verifier_prompt,
            reviser_prompt=reviser_prompt,
            judge_prompt=judge_prompt,
            log_path=log_path,
            log_lock=log_lock,
            mock=args.mock,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_trial = {
            executor.submit(_run, pid, model, seed): (pid, model, seed)
            for pid, model, seed in trials
        }
        for future in concurrent.futures.as_completed(future_to_trial, timeout=TRIAL_TIMEOUT * total_trials):
            pid, model, seed = future_to_trial[future]
            completed += 1
            try:
                result = future.result(timeout=TRIAL_TIMEOUT)
                all_results.append(result)
            except Exception as e:
                model_short = model.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{model_short}|seed={seed}]: {e}", flush=True)
                all_results.append({
                    "problem_id": pid, "level": problems[pid]["level"],
                    "category": problems[pid]["category"], "model": model,
                    "seed": seed, "score": None, "passed": False,
                    "iterations_run": None, "stopped_early": None,
                    "elapsed_s": 0, "final_solution": None, "verdict": None,
                    "loop_log": [], "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total_trials}", flush=True)

    # ---------------------------------------------------------------------------
    # Aggregate
    # ---------------------------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    model_stats = {}
    for model in MODELS:
        model_short = model.split("/")[-1]
        valid = [r for r in all_results if r["model"] == model and r["score"] is not None]
        scores = [r["score"] for r in valid]

        # pass@2
        pass2 = []
        for pid in problem_ids:
            pid_r = [r for r in valid if r["problem_id"] == pid]
            if pid_r:
                pass2.append(any(r["passed"] for r in pid_r))
        pass2_rate = float(np.mean(pass2)) if pass2 else 0.0

        # iterations stats
        iters = [r["iterations_run"] for r in valid if r["iterations_run"] is not None]
        stopped = sum(1 for r in valid if r.get("stopped_early"))

        score_dist = {k: sum(1 for s in scores if s == k) for k in range(8)}

        model_stats[model] = {
            "mean_score":      round(float(np.mean(scores)), 3) if scores else 0.0,
            "std_score":       round(float(np.std(scores)), 3) if scores else 0.0,
            "pass2_rate":      round(pass2_rate, 3),
            "pass2_count":     sum(pass2),
            "pass2_total":     len(pass2),
            "n_valid":         len(valid),
            "n_errors":        sum(1 for r in all_results if r["model"] == model and r.get("error")),
            "mean_iters":      round(float(np.mean(iters)), 2) if iters else 0.0,
            "stopped_early_n": stopped,
            "score_distribution": score_dist,
        }

        print(f"\n{model_short}")
        print(f"  Mean score:    {model_stats[model]['mean_score']:.3f} ± {model_stats[model]['std_score']:.3f}  (n={len(valid)})")
        print(f"  pass@2 rate:   {pass2_rate:.1%}  ({sum(pass2)}/{len(pass2)} problems)")
        print(f"  Avg iters:     {model_stats[model]['mean_iters']:.2f}  (stopped early: {stopped}/{len(valid)})")
        print(f"  Score dist:    " + "  ".join(f"{k}/7:{v}" for k, v in score_dist.items() if v > 0))
        if model_stats[model]["n_errors"]:
            print(f"  Errors:        {model_stats[model]['n_errors']}")

    # Per-category breakdown
    for category in ("PB-Basic", "PB-Advanced"):
        cat_pids = [pid for pid in problem_ids if problems[pid]["category"] == category]
        level = problems[cat_pids[0]]["level"] if cat_pids else "?"
        print(f"\n--- {category} [{level}]  ({len(cat_pids)} problems) ---")
        for model in MODELS:
            model_short = model.split("/")[-1]
            cat_valid = [r for r in all_results if r["model"] == model and r["category"] == category and r["score"] is not None]
            if not cat_valid:
                continue
            cat_scores = [r["score"] for r in cat_valid]
            cat_pass2 = []
            for pid in cat_pids:
                pid_r = [r for r in cat_valid if r["problem_id"] == pid]
                if pid_r:
                    cat_pass2.append(any(r["passed"] for r in pid_r))
            print(f"  {model_short:<45}  mean={np.mean(cat_scores):.2f}±{np.std(cat_scores):.2f}  pass@2={np.mean(cat_pass2):.1%}  ({sum(cat_pass2)}/{len(cat_pass2)})")

    # Per-problem table
    print(f"\n--- Per-problem scores (✓ = at least one seed >= {PASS_THRESHOLD}/7) ---")
    col_w = 22
    print(f"  {'Problem':<26}{'Level':<14}" + "".join(f"{m.split('/')[-1][:col_w]:<{col_w+2}}" for m in MODELS))
    print("  " + "-" * (26 + 14 + (col_w + 2) * len(MODELS)))
    for pid in problem_ids:
        level_str = problems[pid]["level"]
        row = f"  {pid:<26}{level_str:<14}"
        for model in MODELS:
            pid_results = [r for r in all_results if r["model"] == model and r["problem_id"] == pid and r["score"] is not None]
            if pid_results:
                scores_str = "/".join(str(r["score"]) for r in sorted(pid_results, key=lambda x: x["seed"]))
                flag = "✓" if any(r["passed"] for r in pid_results) else "✗"
                cell = f"{flag} [{scores_str}]"
            else:
                cell = "error"
            row += f"{cell:<{col_w+2}}"
        print(row)

    # ---------------------------------------------------------------------------
    # Save
    # ---------------------------------------------------------------------------

    output = {
        "experiment":    "full_pipeline_imo_20260326",
        "date":          "2026-03-26",
        "mock":          args.mock,
        "seeds":         SEEDS,
        "iterations":    ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
        "problems":      problem_ids,
        "models":        MODELS,
        "judge_model":   JUDGE_MODEL,
        "model_stats":   model_stats,
        "all_results":   all_results,
    }

    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"full_pipeline_imo_{run_ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
