"""
Experiment: Model comparison on hard/open problems (generate → judge, no verify/revise).
Date: 2026-03-26
Problems: erdos-659, ramsey-hypergraphs (from combined-benchmarks.csv)
Models: nemotron-3-super-120b, deepseek-v3.2, deepseek-v3.2-speciale,
        qwen3.5-flash-02-23, gemini-3-flash-preview, gpt-5.4-mini
Judge: gemini-3-flash-preview with ground-truth (0–7 IMO scoring)
Pipeline: simple two-step generate → judge
Timeout: 10 minutes per trial
Max tokens: 32k generation, 4k judge
"""

import sys
import csv
import json
import re
import time
import threading
import traceback
import concurrent.futures
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402
litellm.request_timeout = 600  # 10 min

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROBLEM_IDS = ["erdos-659", "ramsey-hypergraphs"]

MODELS = [
    "openrouter/nvidia/nemotron-3-super-120b-a12b",
    "openrouter/deepseek/deepseek-v3.2",
    "openrouter/deepseek/deepseek-v3.2-speciale",
    "openrouter/qwen/qwen3.5-flash-02-23",
    "gemini/gemini-3-flash-preview",
    "openai/gpt-5.4-mini",
]

JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"

MAX_TOKENS_GEN = 32000
MAX_TOKENS_JUDGE = 4096
TRIAL_TIMEOUT = 600  # 10 minutes
MAX_WORKERS = 12

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

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


def load_problems() -> dict:
    """Load only the target problems from the benchmark CSV."""
    problems = {}
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["Problem ID"]
            if pid in PROBLEM_IDS:
                problems[pid] = {
                    "text": row["Problem"],
                    "solution": row.get("Solution", ""),
                    "level": row.get("Level", ""),
                    "category": row.get("Category", ""),
                    "source": row.get("Source", ""),
                }
    return problems


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def make_logger(log_path: Path, lock: threading.Lock):
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(call_type: str, model: str, problem_id: str,
            prompt_preview: str, response_preview: str, elapsed_s: float):
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "call_type": call_type,
            "model": model,
            "problem_id": problem_id,
            "prompt_len": len(prompt_preview),
            "response_len": len(response_preview),
            "elapsed_s": round(elapsed_s, 3),
        }
        with lock:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
    return log


# ---------------------------------------------------------------------------
# Single trial: generate → judge
# ---------------------------------------------------------------------------

def run_trial(
    problem_id: str,
    problem_text: str,
    problem_solution: str,
    model: str,
    generator_system: str,
    judge_prompt_template: str,
    logger,
) -> dict:
    from utils import llm

    model_short = model.split("/")[-1]
    tag = f"[{_ts()}] [{problem_id}|{model_short}]"

    # --- Generate ---
    print(f"{tag} generating...", flush=True)
    t0 = time.time()
    try:
        solution = llm(problem_text, model=model, system=generator_system, max_tokens=MAX_TOKENS_GEN)
    except Exception as e:
        print(f"{tag} ERROR generate: {e}", flush=True)
        raise
    gen_elapsed = time.time() - t0
    logger("generate", model, problem_id, problem_text[:200], solution[:200], gen_elapsed)
    print(f"{tag} generated ({len(solution)} chars, {gen_elapsed:.1f}s)", flush=True)

    # --- Judge with ground truth ---
    gt_section = f"**GROUND TRUTH SOLUTION:**\n{problem_solution}"

    # Parse the judge template to get system vs content parts
    sys_part, sep, content_part = judge_prompt_template.partition("\n**PROBLEM:**\n")
    if not sep:
        sys_part = ""
        content_part = judge_prompt_template

    judge_user_prompt = ("**PROBLEM:**\n" + content_part).replace(
        "{problem}", problem_text
    ).replace(
        "{ground_truth_section}", gt_section
    ).replace(
        "{candidate}", solution
    )

    print(f"{tag} judging...", flush=True)
    t1 = time.time()
    try:
        verdict_text = llm(
            judge_user_prompt,
            model=JUDGE_MODEL,
            system=sys_part.strip() if sys_part.strip() else None,
            max_tokens=MAX_TOKENS_JUDGE,
        )
    except Exception as e:
        print(f"{tag} ERROR judge: {e}", flush=True)
        raise
    judge_elapsed = time.time() - t1
    logger("judge", JUDGE_MODEL, problem_id, judge_user_prompt[:200], verdict_text[:200], judge_elapsed)

    score = parse_imo_score(verdict_text)
    total_elapsed = round(time.time() - t0, 2)

    print(f"{tag} → score={score}/7  total={total_elapsed}s", flush=True)

    return {
        "problem_id": problem_id,
        "model": model,
        "score": score,
        "gen_elapsed_s": round(gen_elapsed, 2),
        "judge_elapsed_s": round(judge_elapsed, 2),
        "total_elapsed_s": total_elapsed,
        "solution": solution,
        "verdict": verdict_text,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    problems = load_problems()

    missing = [pid for pid in PROBLEM_IDS if pid not in problems]
    if missing:
        print(f"ERROR: problems not found in CSV: {missing}")
        sys.exit(1)

    generator_system = load_prompt(PROMPTS_DIR / "generator.md")
    judge_prompt_template = load_prompt(PROMPTS_DIR / "judge.md")

    print("=" * 70)
    print("MODEL COMPARISON — HARD/OPEN PROBLEMS")
    print("=" * 70)
    print(f"Problems:  {PROBLEM_IDS}")
    for pid in PROBLEM_IDS:
        p = problems[pid]
        print(f"  {pid}: level={p['level']}, category={p['category']}")
    print(f"Models:    {[m.split('/')[-1] for m in MODELS]}")
    print(f"Judge:     {JUDGE_MODEL}")
    print(f"Pipeline:  generate → judge (no verify/revise)")
    print(f"Timeout:   {TRIAL_TIMEOUT}s per trial")
    print(f"Max tokens: gen={MAX_TOKENS_GEN}, judge={MAX_TOKENS_JUDGE}")
    total_trials = len(PROBLEM_IDS) * len(MODELS)
    print(f"Total trials: {len(PROBLEM_IDS)} x {len(MODELS)} = {total_trials}")
    print()

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent.parent / "logs" / f"model_comparison_hard_{ts}.jsonl"
    log_lock = threading.Lock()
    logger = make_logger(log_path, log_lock)

    trials = [
        (pid, model)
        for pid in PROBLEM_IDS
        for model in MODELS
    ]

    all_results = []
    completed = 0

    def _run(pid, model):
        return run_trial(
            problem_id=pid,
            problem_text=problems[pid]["text"],
            problem_solution=problems[pid]["solution"],
            model=model,
            generator_system=generator_system,
            judge_prompt_template=judge_prompt_template,
            logger=logger,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_trial = {
            executor.submit(_run, pid, model): (pid, model)
            for pid, model in trials
        }
        for future in concurrent.futures.as_completed(future_to_trial, timeout=TRIAL_TIMEOUT * total_trials):
            pid, model = future_to_trial[future]
            completed += 1
            model_short = model.split("/")[-1]
            try:
                result = future.result(timeout=TRIAL_TIMEOUT)
                all_results.append(result)
            except Exception as e:
                print(f"[{_ts()}] FAILED [{pid}|{model_short}]: {e}", flush=True)
                all_results.append({
                    "problem_id": pid,
                    "model": model,
                    "score": None,
                    "gen_elapsed_s": 0,
                    "judge_elapsed_s": 0,
                    "total_elapsed_s": 0,
                    "solution": None,
                    "verdict": None,
                    "error": str(e),
                })
            print(f"[{_ts()}] Progress: {completed}/{total_trials}", flush=True)

    # ---------------------------------------------------------------------------
    # Results summary
    # ---------------------------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    # Per-model summary
    print(f"\n{'Model':<35} {'erdos-659':>12} {'ramsey-hyp':>12} {'Mean':>8}")
    print("-" * 70)
    for model in MODELS:
        model_short = model.split("/")[-1]
        scores = {}
        for pid in PROBLEM_IDS:
            r = [x for x in all_results if x["model"] == model and x["problem_id"] == pid]
            if r and r[0]["score"] is not None:
                scores[pid] = r[0]["score"]
            else:
                scores[pid] = None

        erdos_str = f"{scores.get('erdos-659', 'err')}/7" if scores.get("erdos-659") is not None else "error"
        ramsey_str = f"{scores.get('ramsey-hypergraphs', 'err')}/7" if scores.get("ramsey-hypergraphs") is not None else "error"
        valid_scores = [v for v in scores.values() if v is not None]
        mean_str = f"{sum(valid_scores)/len(valid_scores):.1f}/7" if valid_scores else "n/a"

        print(f"  {model_short:<33} {erdos_str:>12} {ramsey_str:>12} {mean_str:>8}")

    # Per-problem summary
    for pid in PROBLEM_IDS:
        print(f"\n--- {pid} ---")
        pid_results = sorted(
            [r for r in all_results if r["problem_id"] == pid],
            key=lambda r: r.get("score") or -1,
            reverse=True,
        )
        for r in pid_results:
            model_short = r["model"].split("/")[-1]
            if r["score"] is not None:
                print(f"  {model_short:<33}  score={r['score']}/7  gen={r['gen_elapsed_s']:.1f}s  judge={r['judge_elapsed_s']:.1f}s")
            else:
                print(f"  {model_short:<33}  ERROR: {r.get('error', 'unknown')}")

    # Timing
    print(f"\n--- Timing ---")
    for r in sorted(all_results, key=lambda x: x.get("total_elapsed_s", 0), reverse=True):
        if r["score"] is not None:
            model_short = r["model"].split("/")[-1]
            print(f"  {r['problem_id']:<25} {model_short:<33} {r['total_elapsed_s']:.1f}s")

    # ---------------------------------------------------------------------------
    # Save
    # ---------------------------------------------------------------------------

    output = {
        "experiment": "model_comparison_hard_20260326",
        "date": "2026-03-26",
        "problems": PROBLEM_IDS,
        "models": MODELS,
        "judge_model": JUDGE_MODEL,
        "pipeline": "generate → judge (no verify/revise)",
        "max_tokens_gen": MAX_TOKENS_GEN,
        "max_tokens_judge": MAX_TOKENS_JUDGE,
        "trial_timeout_s": TRIAL_TIMEOUT,
        "all_results": all_results,
    }

    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"model_comparison_hard_{run_ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
