"""
Experiment: Cross-judged generate+verify comparison — Gemini 3 flash vs GPT-5.4 mini.
Date: 2026-03-26

Pipeline: generate → judge (with ground truth, Mode A 0-7 scoring)
Cross-judge: Gemini generates, GPT judges; GPT generates, Gemini judges
Problems: (PB-Advanced AND IMO-easy) OR (PB-Basic AND IMO-medium)
API: Direct (GEMINI_API_KEY, OPENAI_API_KEY) — no OpenRouter

Variables:
  Independent: generator model (Gemini 3 flash preview vs GPT-5.4 mini)
  Dependent: IMO 0-7 score; pass@2 rate (score >= 6/7 on at least 1 of 2 seeds)
  Controlled: problem set, ground-truth judging, cross-judge assignment,
              generator prompt, judge prompt, max_tokens
"""

import sys
import re
import csv
import json
import os
import time
import random
import argparse
import threading
import traceback
import concurrent.futures
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402
litellm.request_timeout = 540

# ---------------------------------------------------------------------------
# Load API keys from .env
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEEDS = [42, 123]  # pass@2

GEMINI_MODEL = "gemini/gemini-3-flash-preview"
OPENAI_MODEL = "openai/gpt-5.4-mini"

# (generator, judge) pairs — each model judged by the other
GENERATOR_JUDGE_PAIRS = [
    (GEMINI_MODEL, OPENAI_MODEL),   # Gemini generates, GPT judges
    (OPENAI_MODEL, GEMINI_MODEL),   # GPT generates, Gemini judges
]

# Filter: (PB-Advanced AND IMO-easy) OR (PB-Basic AND IMO-medium)
def include_problem(problem_id: str, level: str) -> bool:
    is_advanced = "Advanced" in problem_id
    is_basic    = "Basic" in problem_id
    return (is_advanced and level == "IMO-easy") or (is_basic and level == "IMO-medium")

PASS_THRESHOLD = 6  # out of 7

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BENCHMARKS_CSV  = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR     = Path(__file__).parent.parent / "prompts" / "pipeline"

GENERATOR_PROMPT_PATH = PROMPTS_DIR / "generator.md"
JUDGE_PROMPT_PATH     = PROMPTS_DIR / "judge.md"

MAX_TOKENS_GEN   = 32000
MAX_TOKENS_JUDGE = 16384
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


def call_llm(prompt: str, model: str, system: str | None, max_tokens: int) -> tuple[str, float]:
    """Call LiteLLM directly. Returns (response_text, cost_usd)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = litellm.completion(model=model, messages=messages, max_tokens=max_tokens)
    content = resp.choices[0].message.content  # type: ignore
    if content is None:
        content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
    if content is None:
        raise ValueError(f"Model {model} returned None content. Full response: {resp}")
    try:
        cost = litellm.completion_cost(completion_response=resp)
    except Exception:
        cost = 0.0
    return content, cost


# ---------------------------------------------------------------------------
# Load resources
# ---------------------------------------------------------------------------

def load_problems() -> dict:
    """Return {problem_id: {text, solution, level}} filtered to target problem set."""
    problems = {}
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid   = row["Problem ID"]
            level = row.get("Level", "")
            if include_problem(pid, level):
                problems[pid] = {
                    "text":     row["Problem"],
                    "solution": row["Solution"],
                    "level":    level,
                }
    return problems


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Single trial: generate + judge
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
    """Generate with gen_model, judge with judge_model using ground truth."""
    from pipeline import make_logger

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

    trial_cost = 0.0

    # ---- Generate ----
    print(f"{tag} generate → {gen_short}", flush=True)
    try:
        if mock:
            solution, gen_cost = "MOCK SOLUTION: This is a placeholder for testing.", 0.0
        else:
            solution, gen_cost = call_llm(
                prompt=problem_text,
                model=gen_model,
                system=generator_prompt,
                max_tokens=MAX_TOKENS_GEN,
            )
        trial_cost += gen_cost
        gen_elapsed = round(time.time() - ts_start, 2)
        logger("generate", 0, gen_model, generator_prompt, problem_text, solution, gen_elapsed)
        print(f"{tag} generate done in {gen_elapsed}s ({len(solution)} chars, ${gen_cost:.4f})", flush=True)
    except Exception as e:
        print(f"{tag} ERROR during generate: {e}\n{traceback.format_exc()}", flush=True)
        raise

    # ---- Build judge prompt (Mode A: with ground truth) ----
    gt_section = f"**GROUND TRUTH SOLUTION:**\n{ground_truth}"
    sys_part, sep, content = judge_prompt.partition("\n**PROBLEM:**\n")
    if sep:
        judge_sys = sys_part.strip()
        judge_content = (
            "**PROBLEM:**\n" + content
            .replace("{problem}", problem_text)
            .replace("{ground_truth_section}", gt_section)
            .replace("{candidate}", solution)
        )
    else:
        judge_sys = None
        judge_content = (
            judge_prompt
            .replace("{problem}", problem_text)
            .replace("{ground_truth_section}", gt_section)
            .replace("{candidate}", solution)
        )

    # ---- Judge ----
    print(f"{tag} judge → {judge_short}", flush=True)
    try:
        if mock:
            verdict_text, judge_cost = "The solution is correct. <points>6 out of 7</points>", 0.0
        else:
            verdict_text, judge_cost = call_llm(
                prompt=judge_content,
                model=judge_model,
                system=judge_sys,
                max_tokens=MAX_TOKENS_JUDGE,
            )
        trial_cost += judge_cost
        judge_elapsed = round(time.time() - ts_start, 2)
        logger("judge", 0, judge_model, judge_sys or "", judge_content, verdict_text, judge_elapsed)
    except Exception as e:
        print(f"{tag} ERROR during judge: {e}\n{traceback.format_exc()}", flush=True)
        raise

    score = parse_points_score(verdict_text)
    total_elapsed = round(time.time() - ts_start, 2)

    if score is None:
        print(f"{tag} WARNING: could not parse score. Defaulting to 0.", flush=True)
        score = 0

    print(f"{tag} → {score}/7  total={total_elapsed}s  cost=${trial_cost:.4f}", flush=True)

    return {
        "problem_id":    problem_id,
        "level":         problem_level,
        "gen_model":     gen_model,
        "judge_model":   judge_model,
        "seed":          seed,
        "score":         score,
        "pass":          score >= PASS_THRESHOLD,
        "elapsed_s":     total_elapsed,
        "cost_usd":      trial_cost,
        "solution":      solution,
        "verdict":       verdict_text,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cross-judged generate+verify: Gemini 3.0 flash vs GPT-5.4 nano"
    )
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    problems = load_problems()
    generator_prompt = load_prompt(GENERATOR_PROMPT_PATH)
    judge_prompt     = load_prompt(JUDGE_PROMPT_PATH)

    problem_ids = sorted(problems.keys())

    print(f"Problems: {len(problem_ids)}")
    for pid in problem_ids:
        print(f"  {pid}  [{problems[pid]['level']}]")
    print(f"\nGenerator-judge pairs: {len(GENERATOR_JUDGE_PAIRS)}")
    for gen, jdg in GENERATOR_JUDGE_PAIRS:
        print(f"  gen={gen.split('/')[-1]}  judge={jdg.split('/')[-1]}")
    print(f"\nSeeds (pass@{len(SEEDS)}): {SEEDS}")
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
    total_cost  = 0.0
    cost_lock   = threading.Lock()

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
                with cost_lock:
                    total_cost += result.get("cost_usd", 0.0)
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
                    "cost_usd":    0.0,
                    "error":       str(e),
                })
            # Progress update every 10 trials or at end
            if completed % 10 == 0 or completed == len(trials):
                with cost_lock:
                    cur_cost = total_cost
                print(f"[{_ts()}] Progress: {completed}/{len(trials)}  cumulative cost=${cur_cost:.4f}", flush=True)
            else:
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
        scores = [r["score"] for r in valid]

        pass_per_problem = {}
        for pid in problem_ids:
            pid_scores = [r["score"] for r in valid if r["problem_id"] == pid and r.get("score") is not None]
            if pid_scores:
                pass_per_problem[pid] = any(s >= PASS_THRESHOLD for s in pid_scores)

        pass2_rate = np.mean(list(pass_per_problem.values())) if pass_per_problem else 0.0

        if scores:
            print(f"  Overall   mean={np.mean(scores):.3f}±{np.std(scores):.3f}  pass@2={pass2_rate:.1%}  n={len(scores)}")
        else:
            print(f"  No valid results.")

        # Per level
        for level in sorted({problems[p]["level"] for p in problem_ids}):
            lv = [r for r in valid if r["level"] == level]
            if not lv:
                continue
            lv_scores = [r["score"] for r in lv]
            lv_pass = {}
            for pid in [p for p in problem_ids if problems[p]["level"] == level]:
                ps = [r["score"] for r in lv if r["problem_id"] == pid and r.get("score") is not None]
                if ps:
                    lv_pass[pid] = any(s >= PASS_THRESHOLD for s in ps)
            lv_pass2 = np.mean(list(lv_pass.values())) if lv_pass else 0.0
            print(f"  {level:<12} mean={np.mean(lv_scores):.3f}±{np.std(lv_scores):.3f}  pass@2={lv_pass2:.1%}  n={len(lv_scores)}")

    # Per-problem table
    print("\n--- Per-problem scores ---")
    header = f"{'Problem':<22} {'Level':<12}"
    for gen_model, judge_model in GENERATOR_JUDGE_PAIRS:
        g = gen_model.split("/")[-1][:18]
        j = judge_model.split("/")[-1][:10]
        header += f"  {g}(judged by {j})"
    print(header)
    print("-" * 100)

    for pid in problem_ids:
        row = f"{pid:<22} {problems[pid]['level']:<12}"
        for gen_model, judge_model in GENERATOR_JUDGE_PAIRS:
            r_list = [r for r in all_results if r["problem_id"] == pid and r["gen_model"] == gen_model and r.get("score") is not None]
            if r_list:
                s = [r["score"] for r in r_list]
                passed = "✓" if any(x >= PASS_THRESHOLD for x in s) else " "
                row += f"  {np.mean(s):4.1f}±{np.std(s):.1f}{passed}  [{'/'.join(str(x) for x in s)}]"
            else:
                row += f"  {'—':>20}"
        print(row)

    # Error and cost summary
    errors = [r for r in all_results if r.get("error")]
    parse_fails = [r for r in all_results if r.get("score") == 0 and not r.get("error") and r.get("verdict") and "<points>" not in r.get("verdict", "")]
    print(f"\nErrors: {len(errors)}/{len(trials)}  |  Score parse fails (defaulted 0): {len(parse_fails)}/{len(trials)}")
    print(f"Total cost: ${total_cost:.4f}")

    # ---------------------------------------------------------------------------
    # Save
    # ---------------------------------------------------------------------------

    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"gemini_gpt_cross_{run_ts}{suffix}.json"

    output = {
        "experiment":            "gemini_gpt_cross_judge",
        "date":                  "2026-03-26",
        "mock":                  args.mock,
        "seeds":                 SEEDS,
        "pass_threshold":        PASS_THRESHOLD,
        "problem_filter":        "(PB-Advanced AND IMO-easy) OR (PB-Basic AND IMO-medium)",
        "generator_judge_pairs": GENERATOR_JUDGE_PAIRS,
        "problems":              problem_ids,
        "total_cost_usd":        round(total_cost, 6),
        "all_results":           all_results,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
