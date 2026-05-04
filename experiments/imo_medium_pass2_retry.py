"""
Retry script: re-run only trials that failed with 402 (insufficient credits)
from imo_medium_pass2. Merges results into a new combined JSON.
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

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402
litellm.request_timeout = 540

# ---------------------------------------------------------------------------
# Configuration — must match original experiment
# ---------------------------------------------------------------------------

PASS_THRESHOLD = 6
JUDGE_MODEL    = "openrouter/google/gemini-3-flash-preview"
RESULTS_DIR    = Path(__file__).parent / "results"
BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"

MAX_TOKENS_GEN   = 32000
MAX_TOKENS_JUDGE = 4096
MAX_WORKERS      = 16
TRIAL_TIMEOUT    = 600


# ---------------------------------------------------------------------------
# Helpers (copied from original)
# ---------------------------------------------------------------------------

def _ts():
    return datetime.utcnow().strftime("%H:%M:%S")


def parse_imo_score(verdict_text: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


def load_problems_from_csv(problem_ids: list) -> dict:
    problems = {}
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Problem ID"] in problem_ids:
                problems[row["Problem ID"]] = {
                    "text":     row["Problem"],
                    "solution": row.get("Solution", ""),
                    "level":    row.get("Level", "unknown"),
                }
    return problems


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def run_trial(problem_id, problem_text, problem_solution, problem_level,
              model, seed, generator_prompt, judge_prompt, log_path, log_lock,
              mock=False):
    from pipeline import generate, judge, make_logger

    np.random.seed(seed)
    random.seed(seed)

    model_short = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{model_short}|seed={seed}]"

    _base_logger = make_logger(str(log_path))
    def logger(call_type, iteration, mdl, system, prompt, response, elapsed):
        with log_lock:
            _base_logger(call_type, iteration, mdl, system, prompt, response, elapsed)

    ts_start = time.time()

    print(f"{tag} generate → {model_short}", flush=True)
    try:
        solution = generate(
            problem=problem_text, system=generator_prompt, model=model,
            max_tokens=MAX_TOKENS_GEN, logger=logger, iteration=0, mock=mock,
        )
    except Exception as e:
        print(f"{tag} ERROR generate: {e}\n{traceback.format_exc()}", flush=True)
        raise

    gen_elapsed = round(time.time() - ts_start, 2)
    print(f"{tag} generate done in {gen_elapsed}s ({len(solution)} chars)", flush=True)

    print(f"{tag} judge (with ground truth)", flush=True)
    try:
        verdict_text = judge(
            problem=problem_text, candidate=solution, ground_truth=problem_solution,
            system=judge_prompt, model=JUDGE_MODEL,
            max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
        )
    except Exception as e:
        print(f"{tag} ERROR judge: {e}\n{traceback.format_exc()}", flush=True)
        raise

    score = parse_imo_score(verdict_text)
    passed = score >= PASS_THRESHOLD
    total_elapsed = round(time.time() - ts_start, 2)

    print(f"{tag} → score={score}/7 pass={passed} total={total_elapsed}s", flush=True)
    return {
        "problem_id": problem_id, "level": problem_level, "model": model,
        "seed": seed, "score": score, "passed": passed,
        "elapsed_s": total_elapsed, "solution": solution, "verdict": verdict_text,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Path to original results JSON to retry from")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    source_path = Path(args.source)
    with open(source_path, encoding="utf-8") as f:
        original = json.load(f)

    # Find 402 credit failures
    retry_trials = []
    for r in original["all_results"]:
        err = r.get("error", "")
        if "402" in err or "Insufficient credits" in err or "requires more credits" in err:
            retry_trials.append((r["problem_id"], r["model"], r["seed"]))

    if not retry_trials:
        print("No 402 credit failures found in source file. Nothing to retry.")
        return

    print(f"Found {len(retry_trials)} trials to retry:")
    for pid, model, seed in retry_trials:
        print(f"  {pid}  {model.split('/')[-1]}  seed={seed}")
    print()

    # Load only the problems we need
    needed_pids = list({pid for pid, _, _ in retry_trials})
    problems = load_problems_from_csv(needed_pids)

    generator_prompt = load_prompt(PROMPTS_DIR / "generator.md")
    judge_prompt     = load_prompt(PROMPTS_DIR / "judge.md")

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{ts}.jsonl"
    log_lock = threading.Lock()

    print(f"Submitting {len(retry_trials)} trials (max_workers={MAX_WORKERS})\n", flush=True)

    retry_results = []
    completed = 0

    def _run(pid, model, seed):
        return run_trial(
            problem_id=pid, problem_text=problems[pid]["text"],
            problem_solution=problems[pid]["solution"],
            problem_level=problems[pid]["level"],
            model=model, seed=seed,
            generator_prompt=generator_prompt, judge_prompt=judge_prompt,
            log_path=log_path, log_lock=log_lock, mock=args.mock,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_trial = {
            executor.submit(_run, pid, model, seed): (pid, model, seed)
            for pid, model, seed in retry_trials
        }
        for future in concurrent.futures.as_completed(future_to_trial, timeout=TRIAL_TIMEOUT * len(retry_trials)):
            pid, model, seed = future_to_trial[future]
            completed += 1
            try:
                result = future.result(timeout=TRIAL_TIMEOUT)
                retry_results.append(result)
            except Exception as e:
                model_short = model.split("/")[-1]
                print(f"[{_ts()}] FAILED [{pid}|{model_short}|seed={seed}]: {e}", flush=True)
                retry_results.append({
                    "problem_id": pid, "level": problems[pid]["level"], "model": model,
                    "seed": seed, "score": None, "passed": False,
                    "elapsed_s": 0, "solution": None, "verdict": None, "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{len(retry_trials)}", flush=True)

    # Merge: replace failed entries with retry results
    retry_index = {(r["problem_id"], r["model"], r["seed"]): r for r in retry_results}
    merged = []
    replaced = 0
    for r in original["all_results"]:
        key = (r["problem_id"], r["model"], r["seed"])
        if key in retry_index:
            merged.append(retry_index[key])
            replaced += 1
        else:
            merged.append(r)

    print(f"\nReplaced {replaced} entries with retry results.")

    # Recompute model_stats
    all_models  = original["models"]
    all_pids    = original["problems"]
    score_map   = original.get("score_map", {})

    model_stats = {}
    for model in all_models:
        valid  = [r for r in merged if r["model"] == model and r.get("score") is not None]
        scores = [r["score"] for r in valid]
        pass2  = []
        for pid in all_pids:
            pid_r = [r for r in valid if r["problem_id"] == pid]
            if pid_r:
                pass2.append(any(r["passed"] for r in pid_r))
        pass2_rate = float(np.mean(pass2)) if pass2 else 0.0
        score_dist = {k: sum(1 for s in scores if s == k) for k in range(8)}
        model_stats[model] = {
            "mean_score":  round(float(np.mean(scores)), 3) if scores else 0.0,
            "std_score":   round(float(np.std(scores)), 3) if scores else 0.0,
            "pass2_rate":  round(pass2_rate, 3),
            "pass2_count": sum(pass2),
            "pass2_total": len(pass2),
            "n_valid":     len(valid),
            "n_errors":    sum(1 for r in merged if r["model"] == model and r.get("error")),
            "score_distribution": score_dist,
        }

    # Print summary
    print("\n" + "=" * 70)
    print("MERGED RESULTS SUMMARY")
    print("=" * 70)
    for model in all_models:
        s = model_stats[model]
        model_short = model.split("/")[-1]
        print(f"\n{model_short}")
        print(f"  Mean score:  {s['mean_score']:.3f} ± {s['std_score']:.3f}  (n={s['n_valid']})")
        print(f"  pass@2 rate: {s['pass2_rate']:.1%}  ({s['pass2_count']}/{s['pass2_total']} problems)")
        print(f"  Score dist:  " + "  ".join(f"{k}/7:{v}" for k, v in s['score_distribution'].items() if v > 0))
        if s["n_errors"]:
            print(f"  Errors:      {s['n_errors']}")

    # Per-problem table
    print(f"\n--- Per-problem scores (threshold >= {PASS_THRESHOLD}/7) ---")
    col_w = 24
    print(f"  {'Problem':<22}" + "".join(f"{m.split('/')[-1][:col_w]:<{col_w+2}}" for m in all_models))
    print("  " + "-" * (22 + (col_w + 2) * len(all_models)))
    for pid in all_pids:
        row = f"  {pid:<22}"
        for model in all_models:
            pid_r = [r for r in merged if r["model"] == model and r["problem_id"] == pid and r.get("score") is not None]
            if pid_r:
                scores_str = "/".join(str(r["score"]) for r in sorted(pid_r, key=lambda x: x["seed"]))
                flag = "✓" if any(r["passed"] for r in pid_r) else "✗"
                cell = f"{flag} [{scores_str}]"
            else:
                cell = "error"
            row += f"{cell:<{col_w+2}}"
        print(row)

    # Save merged output
    output = {**original, "model_stats": model_stats, "all_results": merged,
              "retry_source": str(source_path), "retry_date": datetime.utcnow().isoformat() + "Z"}
    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"imo_medium_pass2_merged_{run_ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nMerged results saved to: {out_path}")
    print(f"Pipeline log:            {log_path}")


if __name__ == "__main__":
    main()
