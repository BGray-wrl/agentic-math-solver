"""
Experiment: Nemotron-120b vs DeepSeek-v3.2 on IMO-medium problems, judged with ground truth.
Date: 2026-03-26
Hypothesis: DeepSeek-v3.2 will match or exceed Nemotron on IMO-medium given its stronger
  overall performance, but both models will show relatively low pass@2 at this difficulty tier.

Variables:
  Independent: generator model (2 conditions: nemotron-120b, deepseek-v3.2)
  Dependent: IMO score (0–7), pass@2 rate (>= 6/7 on at least 1 of 2 attempts)
  Controlled: problem set (18 IMO-medium), judge model (gemini-3-flash) + ground truth,
              generator prompt, 2 seeds, no verifier/reviser loop
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

# Set litellm request timeout before any model calls
import litellm  # noqa: E402
litellm.request_timeout = 540

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEEDS = [42, 123]  # pass@2

MODELS = [
    "openrouter/nvidia/nemotron-3-super-120b-a12b",
    "openrouter/deepseek/deepseek-v3.2",
]

TARGET_LEVEL = "IMO-medium"
PASS_THRESHOLD = 6  # out of 7 — "almost correct" or better counts as a pass

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "pipeline"

GENERATOR_PROMPT_PATH = PROMPTS_DIR / "generator.md"
JUDGE_PROMPT_PATH = PROMPTS_DIR / "judge.md"

JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"

MAX_TOKENS_GEN = 32000
MAX_TOKENS_JUDGE = 4096
MAX_WORKERS = 16
TRIAL_TIMEOUT = 600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S")


def parse_imo_score(verdict_text: str) -> int:
    """Extract integer score from '<points>N out of 7</points>'."""
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Fallback: scan for any digit followed by /7 or "out of 7"
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


# ---------------------------------------------------------------------------
# Load resources
# ---------------------------------------------------------------------------

def load_problems() -> dict:
    """Return {problem_id: {"text": ..., "solution": ..., "level": ...}} for IMO-medium."""
    problems = {}
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Level") == TARGET_LEVEL:
                problems[row["Problem ID"]] = {
                    "text": row["Problem"],
                    "solution": row.get("Solution", ""),
                    "level": row["Level"],
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
    problem_solution: str,
    problem_level: str,
    model: str,
    seed: int,
    generator_prompt: str,
    judge_prompt: str,
    log_path: Path,
    log_lock: threading.Lock,
    mock: bool = False,
) -> dict:
    """Run one generate + ground-truth judge call. Returns a result dict."""
    from pipeline import generate, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    model_short = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{model_short}|seed={seed}]"

    # Thread-safe logger wrapper
    _base_logger = make_logger(str(log_path))
    def logger(call_type, iteration, mdl, system, prompt, response, elapsed):
        with log_lock:
            _base_logger(call_type, iteration, mdl, system, prompt, response, elapsed)

    ts_start = time.time()

    print(f"{tag} generate → {model_short} (max_tokens={MAX_TOKENS_GEN})", flush=True)
    try:
        solution = generate(
            problem=problem_text,
            system=generator_prompt,
            model=model,
            max_tokens=MAX_TOKENS_GEN,
            logger=logger,
            iteration=0,
            mock=mock,
        )
    except Exception as e:
        print(f"{tag} ERROR during generate: {e}\n{traceback.format_exc()}", flush=True)
        raise

    gen_elapsed = round(time.time() - ts_start, 2)
    print(f"{tag} generate done in {gen_elapsed}s ({len(solution)} chars)", flush=True)

    print(f"{tag} judge → {JUDGE_MODEL.split('/')[-1]} (with ground truth)", flush=True)
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
        print(f"{tag} ERROR during judge: {e}\n{traceback.format_exc()}", flush=True)
        raise

    score = parse_imo_score(verdict_text)
    passed = score >= PASS_THRESHOLD
    total_elapsed = round(time.time() - ts_start, 2)

    print(f"{tag} → score={score}/7 pass={passed} total={total_elapsed}s", flush=True)
    return {
        "problem_id": problem_id,
        "level": problem_level,
        "model": model,
        "seed": seed,
        "score": score,
        "passed": passed,
        "elapsed_s": total_elapsed,
        "solution": solution,        # full text — no truncation
        "verdict": verdict_text,     # full text — no truncation
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nemotron vs DeepSeek on IMO-medium with GT judge")
    parser.add_argument("--mock", action="store_true", help="Use canned responses (no API calls)")
    args = parser.parse_args()

    problems = load_problems()
    generator_prompt = load_prompt(GENERATOR_PROMPT_PATH)
    judge_prompt = load_prompt(JUDGE_PROMPT_PATH)

    problem_ids = sorted(problems.keys())
    print(f"Loaded {len(problem_ids)} {TARGET_LEVEL} problems: {problem_ids}")
    print(f"Models: {MODELS}")
    print(f"Seeds: {SEEDS}  (pass@{len(SEEDS)}, threshold >= {PASS_THRESHOLD}/7)")
    total_trials = len(problem_ids) * len(MODELS) * len(SEEDS)
    print(f"Total trials: {len(problem_ids)} x {len(MODELS)} x {len(SEEDS)} = {total_trials}")
    if args.mock:
        print("[MOCK MODE — no API calls]")
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
    print(f"Submitting {len(trials)} trials to ThreadPoolExecutor(max_workers={MAX_WORKERS})\n", flush=True)

    all_results = []
    completed = 0

    def _run(pid, model, seed):
        return run_trial(
            problem_id=pid,
            problem_text=problems[pid]["text"],
            problem_solution=problems[pid]["solution"],
            problem_level=problems[pid]["level"],
            model=model,
            seed=seed,
            generator_prompt=generator_prompt,
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
                    "problem_id": pid,
                    "level": TARGET_LEVEL,
                    "model": model,
                    "seed": seed,
                    "score": None,
                    "passed": False,
                    "elapsed_s": 0,
                    "solution": None,
                    "verdict": None,
                    "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total_trials} trials done", flush=True)

    # ---------------------------------------------------------------------------
    # Aggregate results
    # ---------------------------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    model_stats = {}
    for model in MODELS:
        model_short = model.split("/")[-1]
        valid = [r for r in all_results if r["model"] == model and r["score"] is not None]
        scores = [r["score"] for r in valid]

        # pass@2: per problem, did at least one seed pass?
        pass2_results = []
        for pid in problem_ids:
            pid_results = [r for r in valid if r["problem_id"] == pid]
            if pid_results:
                pass2_results.append(any(r["passed"] for r in pid_results))

        pass2_rate = np.mean(pass2_results) if pass2_results else 0.0
        score_dist = {k: sum(1 for s in scores if s == k) for k in range(8)}

        model_stats[model] = {
            "mean_score": round(float(np.mean(scores)), 3) if scores else 0.0,
            "std_score": round(float(np.std(scores)), 3) if scores else 0.0,
            "pass2_rate": round(float(pass2_rate), 3),
            "pass2_count": sum(pass2_results),
            "pass2_total": len(pass2_results),
            "n_valid": len(valid),
            "n_errors": len([r for r in all_results if r["model"] == model and r.get("error")]),
            "score_distribution": score_dist,
        }

        print(f"\n{model_short}")
        print(f"  Mean score:  {model_stats[model]['mean_score']:.3f} ± {model_stats[model]['std_score']:.3f}  (n={len(valid)})")
        print(f"  pass@2 rate: {pass2_rate:.1%}  ({sum(pass2_results)}/{len(pass2_results)} problems)")
        print(f"  Score dist:  " + "  ".join(f"{k}/7:{v}" for k, v in score_dist.items() if v > 0))
        if model_stats[model]["n_errors"]:
            print(f"  Errors:      {model_stats[model]['n_errors']}")

    # Per-problem breakdown
    print(f"\n--- Per-problem scores (threshold >= {PASS_THRESHOLD}/7) ---")
    col_w = 20
    header = f"  {'Problem':<22}" + "".join(f"{m.split('/')[-1][:col_w]:<{col_w+4}}" for m in MODELS)
    print(header)
    print("  " + "-" * (22 + (col_w + 4) * len(MODELS)))
    for pid in problem_ids:
        row = f"  {pid:<22}"
        for model in MODELS:
            pid_results = [r for r in all_results if r["model"] == model and r["problem_id"] == pid and r["score"] is not None]
            if pid_results:
                scores_str = "/".join(str(r["score"]) for r in sorted(pid_results, key=lambda x: x["seed"]))
                passed = any(r["passed"] for r in pid_results)
                flag = "✓" if passed else "✗"
                cell = f"{flag} [{scores_str}]"
            else:
                cell = "error"
            row += f"{cell:<{col_w+4}}"
        print(row)

    # ---------------------------------------------------------------------------
    # Save results
    # ---------------------------------------------------------------------------

    output = {
        "experiment": "imo_medium_pass2_20260326",
        "date": "2026-03-26",
        "mock": args.mock,
        "seeds": SEEDS,
        "target_level": TARGET_LEVEL,
        "pass_threshold": PASS_THRESHOLD,
        "problems": problem_ids,
        "models": MODELS,
        "judge_model": JUDGE_MODEL,
        "model_stats": model_stats,
        "all_results": all_results,
    }

    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"imo_medium_pass2_{run_ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
