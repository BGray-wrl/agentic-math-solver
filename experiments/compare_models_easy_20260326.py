"""
Experiment: Compare six models as generator-only on PB-Basic and PB-Advanced benchmark problems.
Date: 2026-03-26
Hypothesis: Models will differ meaningfully in solution quality; larger/stronger models
  should score higher on both tiers, with flash-tier models showing a larger drop on
  PB-Advanced vs PB-Basic.

Variables:
  Independent: generator model (6 conditions)
  Dependent: judge classification (incorrect=0, partial=1, almost=2, correct=3)
             and mean numeric score per model
  Controlled: problem set (30 PB-Basic + 5 PB-Advanced), generator prompt, judge model,
              judge prompt, max_tokens, no verifier/reviser loop, seeds applied
              to numpy/random for reproducibility
"""

import sys
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

# Set litellm request timeout before any model calls
import litellm  # noqa: E402
litellm.request_timeout = 540  # matches API_CALL_TIMEOUT below

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEEDS = [42, 123, 456]

MODELS = [
    "openrouter/nvidia/nemotron-3-super-120b-a12b",
    "openrouter/stepfun/step-3.5-flash",
    "openrouter/deepseek/deepseek-v3.2",
    "openrouter/qwen/qwen3.5-flash-02-23",
    "openrouter/deepseek/deepseek-v3.2-speciale",
    "openrouter/google/gemini-3.1-flash-lite-preview",
]

# All 30 PB-Basic + first 5 PB-Advanced problems
PROBLEM_IDS = (
    [f"PB-Basic-{i:03d}" for i in range(1, 31)]
    + [f"PB-Advanced-{i:03d}" for i in range(1, 31)]
)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "pipeline"

GENERATOR_PROMPT_PATH = PROMPTS_DIR / "generator.md"
JUDGE_PROMPT_PATH = PROMPTS_DIR / "judge.md"

# Judge model — use gemini-3-flash
JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"

MAX_TOKENS_GEN = 32000
MAX_TOKENS_JUDGE = 4096
MAX_WORKERS = 24        # parallel trials (630 total — 6 models × 35 problems × 3 seeds)
TRIAL_TIMEOUT = 600     # seconds before abandoning a stalled trial
API_CALL_TIMEOUT = 540  # litellm request timeout (slightly shorter than trial ceiling)

# ---------------------------------------------------------------------------
# Score mapping
# ---------------------------------------------------------------------------

SCORE_MAP = {
    "correct": 3,
    "almost": 2,
    "partial": 1,
    "incorrect": 0,
}


def parse_judge_classification(verdict_text: str) -> str:
    """Extract classification label from judge response."""
    for label in ("correct", "almost", "partial", "incorrect"):
        if f"CLASSIFICATION: {label}" in verdict_text:
            return label
    # Fallback: scan for the label anywhere
    lower = verdict_text.lower()
    for label in ("correct", "almost", "partial", "incorrect"):
        if label in lower:
            return label
    return "incorrect"


# ---------------------------------------------------------------------------
# Load resources
# ---------------------------------------------------------------------------

def load_problems() -> dict:
    """Return {problem_id: {"text": ..., "level": ...}} for selected problem IDs."""
    problems = {}
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Problem ID"] in PROBLEM_IDS:
                problems[row["Problem ID"]] = {
                    "text": row["Problem"],
                    "level": row.get("Level", "unknown"),
                }
    return problems


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Single trial
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S")


def run_trial(
    problem_id: str,
    problem_text: str,
    problem_level: str,
    model: str,
    seed: int,
    generator_prompt: str,
    judge_prompt: str,
    log_path: Path,
    log_lock: threading.Lock,
    mock: bool = False,
) -> dict:
    """Run one generate + judge call. Returns a result dict."""
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

    print(f"{tag} generate → calling {model_short} (max_tokens={MAX_TOKENS_GEN})", flush=True)
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
    print(f"{tag} generate done in {gen_elapsed}s, solution len={len(solution)} chars", flush=True)

    print(f"{tag} judge → calling {JUDGE_MODEL.split('/')[-1]}", flush=True)
    try:
        verdict_text = judge(
            problem=problem_text,
            candidate=solution,
            ground_truth=None,
            system=judge_prompt,
            model=JUDGE_MODEL,
            max_tokens=MAX_TOKENS_JUDGE,
            logger=logger,
            mock=mock,
        )
    except Exception as e:
        print(f"{tag} ERROR during judge: {e}\n{traceback.format_exc()}", flush=True)
        raise

    classification = parse_judge_classification(verdict_text)
    score = SCORE_MAP[classification]
    total_elapsed = round(time.time() - ts_start, 2)

    print(f"{tag} → {classification} (score={score}) total={total_elapsed}s", flush=True)
    return {
        "problem_id": problem_id,
        "level": problem_level,
        "model": model,
        "seed": seed,
        "classification": classification,
        "score": score,
        "elapsed_s": total_elapsed,
        "solution_snippet": solution[:300],
        "judge_snippet": verdict_text[:300],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compare 4 models on easy benchmark problems")
    parser.add_argument("--mock", action="store_true", help="Use canned responses (no API calls)")
    args = parser.parse_args()

    problems = load_problems()
    generator_prompt = load_prompt(GENERATOR_PROMPT_PATH)
    judge_prompt = load_prompt(JUDGE_PROMPT_PATH)

    # Verify all requested problem IDs were found
    missing = set(PROBLEM_IDS) - set(problems.keys())
    if missing:
        print(f"WARNING: Could not find problems: {missing}", file=sys.stderr)

    found_ids = [pid for pid in PROBLEM_IDS if pid in problems]
    print(f"Loaded {len(found_ids)} problems: {found_ids}")
    print(f"Models: {len(MODELS)}")
    print(f"Seeds: {SEEDS}")
    print(f"Total trials: {len(found_ids)} x {len(MODELS)} x {len(SEEDS)} = "
          f"{len(found_ids) * len(MODELS) * len(SEEDS)}")
    if args.mock:
        print("[MOCK MODE — no API calls]")
    print()

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{ts}.jsonl"
    log_lock = threading.Lock()

    # Build all (pid, model, seed) combos
    trials = [
        (pid, model, seed)
        for pid in found_ids
        for model in MODELS
        for seed in SEEDS
    ]
    total_trials = len(trials)
    print(f"Submitting {total_trials} trials to ThreadPoolExecutor(max_workers={MAX_WORKERS})\n", flush=True)

    all_results = []
    completed = 0

    def _run(pid, model, seed):
        return run_trial(
            problem_id=pid,
            problem_text=problems[pid]["text"],
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
                    "level": problems[pid]["level"],
                    "model": model,
                    "seed": seed,
                    "classification": "error",
                    "score": 0,
                    "elapsed_s": 0,
                    "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total_trials} trials done", flush=True)

    # ---------------------------------------------------------------------------
    # Aggregate results
    # ---------------------------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    # Per-model stats across all problems and seeds
    model_stats = {}
    for model in MODELS:
        model_results = [r for r in all_results if r["model"] == model and r.get("classification") != "error"]
        scores = [r["score"] for r in model_results]
        if scores:
            mean_score = np.mean(scores)
            std_score = np.std(scores)
            # Classification breakdown
            breakdown = {k: 0 for k in SCORE_MAP}
            for r in model_results:
                if r["classification"] in breakdown:
                    breakdown[r["classification"]] += 1
            model_stats[model] = {
                "mean": round(float(mean_score), 3),
                "std": round(float(std_score), 3),
                "n": len(scores),
                "breakdown": breakdown,
            }
        else:
            model_stats[model] = {"mean": 0.0, "std": 0.0, "n": 0, "breakdown": {}}

    # Overall table
    print(f"\n{'Model':<50} {'Mean±Std':>12} {'N':>4}  correct/almost/partial/incorrect")
    print("-" * 90)
    for model in MODELS:
        s = model_stats[model]
        model_short = model.split("/", 1)[-1]  # strip openrouter/
        bd = s["breakdown"]
        bd_str = f"{bd.get('correct',0)}/{bd.get('almost',0)}/{bd.get('partial',0)}/{bd.get('incorrect',0)}"
        print(f"{model_short:<50} {s['mean']:>6.3f}±{s['std']:<5.3f} {s['n']:>4}  {bd_str}")

    # Per-level breakdown
    all_levels = sorted({r["level"] for r in all_results if r.get("level")})
    print(f"\n--- Per-level breakdown ---")
    for level in all_levels:
        level_results = [r for r in all_results if r.get("level") == level and r.get("classification") != "error"]
        print(f"\n  Level: {level}  (n={len(level_results)} scored trials)")
        print(f"  {'Model':<48} {'Mean±Std':>12}  correct/almost/partial/incorrect")
        print(f"  {'-'*85}")
        for model in MODELS:
            model_short = model.split("/", 1)[-1]
            r_list = [r for r in level_results if r["model"] == model]
            if r_list:
                scores = [r["score"] for r in r_list]
                bd = {k: sum(1 for r in r_list if r["classification"] == k) for k in SCORE_MAP}
                bd_str = f"{bd['correct']}/{bd['almost']}/{bd['partial']}/{bd['incorrect']}"
                print(f"  {model_short:<48} {np.mean(scores):>6.3f}±{np.std(scores):<5.3f}  {bd_str}")

    # Per-problem breakdown
    print("\n--- Per-problem mean scores ---")
    for pid in found_ids:
        level = problems[pid]["level"] if pid in problems else "?"
        print(f"\n  Problem: {pid}  [{level}]")
        for model in MODELS:
            model_short = model.split("/")[-1]
            r_list = [r for r in all_results if r["model"] == model and r["problem_id"] == pid and r.get("classification") != "error"]
            if r_list:
                scores = [r["score"] for r in r_list]
                labels = [r["classification"] for r in r_list]
                print(f"    {model_short:<45} {np.mean(scores):.2f}±{np.std(scores):.2f}  [{', '.join(labels)}]")

    # ---------------------------------------------------------------------------
    # Save results
    # ---------------------------------------------------------------------------

    # Build per-level stats for JSON output
    level_model_stats = {}
    for level in all_levels:
        level_model_stats[level] = {}
        for model in MODELS:
            r_list = [r for r in all_results if r.get("level") == level and r["model"] == model and r.get("classification") != "error"]
            scores = [r["score"] for r in r_list]
            if scores:
                bd = {k: sum(1 for r in r_list if r["classification"] == k) for k in SCORE_MAP}
                level_model_stats[level][model] = {"mean": round(float(np.mean(scores)), 3), "std": round(float(np.std(scores)), 3), "n": len(scores), "breakdown": bd}
            else:
                level_model_stats[level][model] = {"mean": 0.0, "std": 0.0, "n": 0, "breakdown": {}}

    output = {
        "experiment": "compare_models_easy_20260326",
        "date": "2026-03-26",
        "mock": args.mock,
        "seeds": SEEDS,
        "problems": found_ids,
        "models": MODELS,
        "judge_model": JUDGE_MODEL,
        "score_map": SCORE_MAP,
        "model_stats": model_stats,
        "level_model_stats": level_model_stats,
        "all_results": all_results,
    }

    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"compare_models_easy_{run_ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log: {log_path}")


if __name__ == "__main__":
    main()
