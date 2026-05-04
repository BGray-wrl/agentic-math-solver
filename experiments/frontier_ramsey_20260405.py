#!/usr/bin/env python3
"""
Frontier attack on ramsey-hypergraphs.

Single focused trial with 4 frontier models. Each model gets one seeded idea
and runs full pipeline (generate → verify ↔ revise → judge). A 5th branch
uses DeepSeek R1 (reasoning model) unseeded as a wild card.

COST-SAVING MEASURES:
  - Early stopping: judge-gated (≥6/7) — signals all branches to stop
    when any branch gets a high judge score
  - Flash-lite ideator (cheapest, proven effective)
  - Only judge branches that complete (skip stopped ones)
  - Max 3 verify/revise iterations
  - Stop verifying once correct

MODELS (NO gpt-pro — too expensive):
  Branch 0: Claude Opus 4.6       ($5/$25/Mtok — strongest frontier)
  Branch 1: Gemini 3.1 Pro Preview ($2/$12/Mtok — Google frontier)
  Branch 2: Qwen3 Max Thinking    ($0.78/$3.90/Mtok — reasoning specialist, cheap)
  Branch 3: GPT-OSS 120B          ($0.04/$0.19/Mtok — frontier tier, very cheap)
  Branch 4: Qwen3 Max Thinking    (unseeded wild card — may find novel approach)

Usage:
    uv run experiments/frontier_ramsey_20260405.py --mock
    uv run experiments/frontier_ramsey_20260405.py
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

EXPERIMENT_NAME = "frontier_ramsey"

# --- Models ---
MODELS = {
    0: {"name": "claude-opus-4.6",      "model": "openrouter/anthropic/claude-opus-4.6",          "seeded": True},
    1: {"name": "gemini-3.1-pro",       "model": "openrouter/google/gemini-3.1-pro-preview",      "seeded": True},
    2: {"name": "qwen3-max-thinking",   "model": "openrouter/qwen/qwen3-max-thinking",            "seeded": True},
    3: {"name": "gpt-oss-120b",         "model": "openrouter/openai/gpt-oss-120b",                "seeded": True},
    4: {"name": "qwen3-max-wild",       "model": "openrouter/qwen/qwen3-max-thinking",            "seeded": False},
}

IDEATOR   = "openrouter/google/gemini-3.1-flash-lite-preview"
JUDGE_MODEL = "gemini/gemini-3-flash-preview"

NUM_IDEAS = 4  # one per seeded branch
ITERATIONS = 3
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
LITELLM_TIMEOUT = 600  # generous for frontier models

PROBLEM_ID = "ramsey-hypergraphs"


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


def load_problem():
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["Problem ID"] == PROBLEM_ID:
            return {
                "text":     row["Problem"],
                "solution": row.get("Solution", ""),
                "level":    row.get("Level", ""),
                "category": row.get("Category", ""),
            }
    raise ValueError(f"Problem {PROBLEM_ID} not found")


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _short(model: str) -> str:
    return model.split("/")[-1][:20]


# ---------------------------------------------------------------------------
# Branch execution with early stopping
# ---------------------------------------------------------------------------

def run_branch(
    branch_id: int,
    branch_cfg: dict,
    problem: dict,
    idea: dict | None,
    prompts: dict,
    log_path: Path,
    log_lock: threading.Lock,
    stop_event: threading.Event,
    winner_lock: threading.Lock,
    winner_info: dict,
    mock: bool = False,
):
    """Run one branch with early-stopping support."""
    from pipeline import generate, verify, revise, judge, make_logger

    model = branch_cfg["model"]
    bname = branch_cfg["name"]
    tag = f"[{_ts()}] [b{branch_id}:{bname}]"

    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)

    t0 = time.time()

    # --- Check if another branch already won ---
    if stop_event.is_set():
        print(f"{tag} SKIPPED (another branch already won)", flush=True)
        return {"branch_id": branch_id, "name": bname, "status": "skipped"}

    # --- Generate ---
    if idea is not None:
        gen_prompt = prompts["generator_seeded"].replace(
            "{idea}", f"**{idea['name']}**: {idea['description']}"
        )
        print(f"{tag} GENERATE (idea: {idea['name'][:40]})", flush=True)
    else:
        gen_prompt = prompts["generator"]
        print(f"{tag} GENERATE (unseeded wild card)", flush=True)

    solution = generate(
        problem=problem["text"], system=gen_prompt, model=model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    elapsed_gen = time.time() - t0
    print(f"{tag} generated ({len(solution)} chars, {elapsed_gen:.0f}s)", flush=True)

    # --- Verify/Revise loop ---
    loop_log = []
    stopped_early = False

    for i in range(ITERATIONS):
        # Check early stopping before each iteration
        if stop_event.is_set():
            print(f"{tag} STOPPING (another branch won during verify/revise)", flush=True)
            break

        print(f"{tag} VERIFY iter={i+1}", flush=True)
        critique = verify(
            problem=problem["text"], solution=solution, system=prompts["verifier"],
            model=model, max_tokens=MAX_TOKENS, logger=logger,
            iteration=i+1, mock=mock,
        )

        if "VERDICT: correct" in critique:
            print(f"{tag} verifier says correct at iter={i+1} (will confirm with judge)", flush=True)
            stopped_early = True
            loop_log.append({"iteration": i+1, "verdict": "correct"})
            break

        # Check if another branch already confirmed by judge
        if stop_event.is_set():
            print(f"{tag} STOPPING (another branch confirmed by judge)", flush=True)
            loop_log.append({"iteration": i+1, "verdict": "issues_found", "stopped": True})
            break

        print(f"{tag} REVISE iter={i+1}", flush=True)
        new_solution = revise(
            problem=problem["text"], solution=solution, critique=critique,
            system=prompts["reviser"], model=model, max_tokens=MAX_TOKENS,
            logger=logger, iteration=i+1, mock=mock,
        )
        loop_log.append({
            "iteration": i+1,
            "verdict": "issues_found",
            "solution_len_before": len(solution),
            "solution_len_after": len(new_solution),
        })
        solution = new_solution
        print(f"{tag} revised ({len(solution)} chars, {time.time()-t0:.0f}s)", flush=True)

    # --- Judge (always judge — early stop is gated on judge, not verifier) ---
    score = None
    verdict_text = None

    if stop_event.is_set() and not stopped_early:
        # Another branch already confirmed by judge, and we didn't even get verifier correct
        print(f"{tag} skipping judge (another branch already confirmed)", flush=True)
    else:
        gt = problem["solution"]
        judge_prompt = prompts["judge_gt"] if gt else prompts["judge_nogt"]
        print(f"{tag} JUDGE", flush=True)
        verdict_text = judge(
            problem=problem["text"], candidate=solution, ground_truth=gt,
            system=judge_prompt, model=JUDGE_MODEL,
            max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
            extract_prompt=prompts["extract_score"],
        )
        score = parse_gt_score(verdict_text)
        print(f"{tag} → SCORE: {score}/7 (total {time.time()-t0:.0f}s)", flush=True)

        # Early stopping: only trigger on HIGH judge score (≥6/7)
        if score is not None and score >= 6:
            print(f"\n{'='*60}", flush=True)
            print(f"{tag} *** JUDGE CONFIRMED {score}/7 — SIGNALING EARLY STOP ***", flush=True)
            print(f"{'='*60}\n", flush=True)
            with winner_lock:
                if not stop_event.is_set():
                    stop_event.set()
                    winner_info["branch_id"] = branch_id
                    winner_info["name"] = bname
                    winner_info["score"] = score

    elapsed = round(time.time() - t0, 2)

    return {
        "branch_id": branch_id,
        "name": bname,
        "model": model,
        "idea": idea,
        "seeded": branch_cfg["seeded"],
        "score": score,
        "stopped_early": stopped_early,
        "iterations_run": len(loop_log),
        "elapsed_s": elapsed,
        "final_solution": solution,
        "verdict": verdict_text,
        "loop_log": loop_log,
        "status": "completed",
    }


def main():
    parser = argparse.ArgumentParser(description="Frontier attack on ramsey-hypergraphs")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problem = load_problem()

    print(f"{'='*70}")
    print(f"FRONTIER ATTACK: {PROBLEM_ID}")
    print(f"{'='*70}")
    print(f"Level: {problem['level']}")
    print(f"Problem: {problem['text'][:200]}...")
    print(f"Solution length: {len(problem['solution'])} chars")
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

    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()

    # --- Step 1: Ideate ---
    from pipeline import ideate, make_logger
    _base = make_logger(str(log_path))
    def _logger(*a):
        with log_lock:
            _base(*a)

    print(f"[{_ts()}] Ideating {NUM_IDEAS} approaches ({_short(IDEATOR)})...", flush=True)
    if args.mock:
        ideas = [
            {"name": "Direct construction", "description": "Build an explicit example satisfying the conditions."},
            {"name": "Greedy algorithm", "description": "Iteratively add edges while checking partition constraint."},
            {"name": "Probabilistic method", "description": "Use random construction and verify properties."},
            {"name": "Algebraic design", "description": "Use finite field or group structure to design edges."},
        ]
    else:
        ideas = ideate(
            problem=problem["text"], system=prompts["ideator"],
            model=IDEATOR, max_tokens=4096, logger=_logger,
            num_ideas=NUM_IDEAS, mock=False,
        )
        ideas = ideas[:NUM_IDEAS]

    print(f"[{_ts()}] Got {len(ideas)} ideas:", flush=True)
    for i, idea in enumerate(ideas):
        print(f"  {i}: {idea['name']} — {idea['description'][:80]}", flush=True)
    print()

    # --- Step 2: Assign ideas to branches ---
    # Branches 0-3 get seeded ideas, branch 4 is unseeded wild card
    branch_ideas = {}
    for bid, cfg in MODELS.items():
        if cfg["seeded"] and bid < len(ideas):
            branch_ideas[bid] = ideas[bid]
        else:
            branch_ideas[bid] = None

    print("Branch assignments:", flush=True)
    for bid, cfg in MODELS.items():
        idea = branch_ideas[bid]
        idea_str = f"idea: {idea['name'][:40]}" if idea else "unseeded (wild card)"
        print(f"  b{bid}: {cfg['name']:<20} {idea_str}", flush=True)
    print()

    # --- Step 3: Run all branches in parallel with early stopping ---
    stop_event = threading.Event()
    winner_lock = threading.Lock()
    winner_info = {}

    print(f"[{_ts()}] Launching {len(MODELS)} branches in parallel...\n", flush=True)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(MODELS)) as ex:
        futs = {
            ex.submit(
                run_branch, bid, cfg, problem, branch_ideas[bid],
                prompts, log_path, log_lock, stop_event,
                winner_lock, winner_info, args.mock,
            ): bid
            for bid, cfg in MODELS.items()
        }
        for fut in concurrent.futures.as_completed(futs, timeout=3600):
            bid = futs[fut]
            try:
                result = fut.result(timeout=3600)
                results.append(result)
                if result.get("score") is not None:
                    print(f"\n[{_ts()}] Branch {bid} ({MODELS[bid]['name']}) finished: {result['score']}/7\n", flush=True)
            except Exception as e:
                print(f"\n[{_ts()}] Branch {bid} ({MODELS[bid]['name']}) FAILED: {e}\n", flush=True)
                results.append({
                    "branch_id": bid,
                    "name": MODELS[bid]["name"],
                    "model": MODELS[bid]["model"],
                    "status": "error",
                    "error": str(e),
                    "score": None,
                })

    # --- Step 4: Report ---
    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}\n")

    results.sort(key=lambda r: (r.get("score") or -1), reverse=True)

    for r in results:
        status = r.get("status", "unknown")
        if status == "skipped":
            print(f"  b{r['branch_id']}: {r['name']:<20} SKIPPED (early stopping)")
        elif status == "error":
            print(f"  b{r['branch_id']}: {r['name']:<20} ERROR: {r.get('error', '')[:60]}")
        else:
            score = r.get("score")
            iters = r.get("iterations_run", 0)
            early = r.get("stopped_early", False)
            elapsed = r.get("elapsed_s", 0)
            idea = r.get("idea")
            idea_str = idea["name"][:30] if idea else "(unseeded)"
            flag = " *** WINNER ***" if early else ""
            score_str = f"{score}/7" if score is not None else "n/a"
            print(f"  b{r['branch_id']}: {r['name']:<20} score={score_str}  iters={iters}  "
                  f"early={early}  {elapsed:.0f}s  idea={idea_str}{flag}")

    if winner_info:
        print(f"\n  EARLY STOPPING triggered by branch {winner_info['branch_id']} "
              f"({winner_info['name']}) with judge score {winner_info.get('score', '?')}/7")

    best = max(results, key=lambda r: r.get("score") or -1)
    print(f"\n  BEST: {best['name']} with {best.get('score', 'n/a')}/7")

    # Show solution preview for best
    if best.get("final_solution"):
        sol = best["final_solution"]
        print(f"\n  Solution preview ({len(sol)} chars):")
        # Look for the actual hypergraph output
        for line in sol.split("\n"):
            if "{" in line and "}" in line and "," in line:
                print(f"    {line[:200]}")
                break

    total_elapsed = sum(r.get("elapsed_s", 0) for r in results)
    print(f"\n  Total compute time: {total_elapsed:.0f}s across {len(results)} branches")

    # --- Save ---
    ts = _now()
    suffix = "_mock" if args.mock else ""
    output = {
        "experiment": EXPERIMENT_NAME,
        "problem_id": PROBLEM_ID,
        "date": datetime.now(timezone.utc).isoformat(),
        "models": {str(k): v for k, v in MODELS.items()},
        "ideator": IDEATOR,
        "judge_model": JUDGE_MODEL,
        "ideas": ideas,
        "early_stopping": bool(winner_info),
        "winner": winner_info if winner_info else None,
        "mock": args.mock,
        "all_results": results,
    }
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
