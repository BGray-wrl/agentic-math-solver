#!/usr/bin/env python3
"""
Frontier attack v2 on ramsey-hypergraphs — one-shot design for novel finding.

Architecture:
  Phase 1: Dual ideation (flash-lite + Opus in parallel, deduplicate to 3 ideas)
  Phase 2: 3 branches in parallel, 6 iterations each:
           - Cross-model verification (generator != verifier)
           - Escalated revision (reviser != generator)
           - Programmatic checker after each revision
  Phase 3: Synthesis — feed top solutions to frontier model to combine insights
  Phase 4: Multi-judge consensus (3 frontier models, no ground truth)
           + programmatic verification as ground truth

Branch model assignments:
  b0: Opus generates,      Gemini Pro verifies,  Gemini Pro revises
  b1: Gemini Pro generates, Opus verifies,        Opus revises
  b2: Qwen3 Max generates, Gemini Pro verifies,  Opus revises

Cost estimate: ~$6-8 total

Usage:
    uv run experiments/frontier_ramsey_v2_20260405.py --mock
    uv run experiments/frontier_ramsey_v2_20260405.py
"""

from __future__ import annotations

import sys
import csv
import json
import re
import time
import argparse
import threading
import concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm  # noqa: E402

# ============================================================================
# CONFIGURATION
# ============================================================================

EXPERIMENT_NAME = "frontier_ramsey_v2"
PROBLEM_ID = "ramsey-hypergraphs"

# --- Branch configs: generator, cross-verifier, escalation reviser ---
BRANCHES = {
    0: {
        "name": "opus-branch",
        "generator":  "openrouter/anthropic/claude-opus-4.6",
        "verifier":   "openrouter/google/gemini-3.1-pro-preview",
        "reviser":    "openrouter/google/gemini-3.1-pro-preview",
    },
    1: {
        "name": "gemini-branch",
        "generator":  "openrouter/google/gemini-3.1-pro-preview",
        "verifier":   "openrouter/anthropic/claude-opus-4.6",
        "reviser":    "openrouter/anthropic/claude-opus-4.6",
    },
    2: {
        "name": "qwen-branch",
        "generator":  "openrouter/qwen/qwen3-max-thinking",
        "verifier":   "openrouter/google/gemini-3.1-pro-preview",
        "reviser":    "openrouter/anthropic/claude-opus-4.6",
    },
}

# --- Ideation ---
IDEATOR_CHEAP    = "openrouter/google/gemini-3.1-flash-lite-preview"
IDEATOR_FRONTIER = "openrouter/anthropic/claude-opus-4.6"
NUM_IDEAS_PER_IDEATOR = 5  # request 5 each, deduplicate to 3

# --- Judges (multi-judge consensus, no ground truth) ---
JUDGE_MODELS = [
    "openrouter/anthropic/claude-opus-4.6",
    "openrouter/google/gemini-3.1-pro-preview",
    "openrouter/qwen/qwen3-max-thinking",
]

# --- Synthesis ---
SYNTHESIZER_MODEL = "openrouter/anthropic/claude-opus-4.6"

# --- Pipeline params ---
ITERATIONS = 6
MAX_TOKENS = 32000
LITELLM_TIMEOUT = 900  # generous for frontier reasoning models


# ============================================================================
# Paths and helpers
# ============================================================================

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def _now():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def _short(model: str) -> str:
    return model.split("/")[-1][:25]


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


# ============================================================================
# Phase 1: Dual ideation
# ============================================================================

def dual_ideate(problem_text, prompts, logger, log_lock, mock=False):
    """Run flash-lite and Opus ideation in parallel, merge to 3 distinct ideas."""
    from pipeline import ideate

    def _logged_ideate(model, num):
        def _log(*a):
            with log_lock:
                logger(*a)
        return ideate(
            problem=problem_text, system=prompts["ideator"],
            model=model, max_tokens=4096, logger=_log,
            num_ideas=num, mock=mock,
        )

    print(f"[{_ts()}] Phase 1: Dual ideation", flush=True)
    print(f"  Cheap:    {_short(IDEATOR_CHEAP)} ({NUM_IDEAS_PER_IDEATOR} ideas)", flush=True)
    print(f"  Frontier: {_short(IDEATOR_FRONTIER)} ({NUM_IDEAS_PER_IDEATOR} ideas)", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fut_cheap = ex.submit(_logged_ideate, IDEATOR_CHEAP, NUM_IDEAS_PER_IDEATOR)
        fut_front = ex.submit(_logged_ideate, IDEATOR_FRONTIER, NUM_IDEAS_PER_IDEATOR)
        ideas_cheap = fut_cheap.result(timeout=120)
        ideas_frontier = fut_front.result(timeout=120)

    print(f"  Cheap ideas ({len(ideas_cheap)}):", flush=True)
    for i, idea in enumerate(ideas_cheap):
        print(f"    {i}: {idea['name']}", flush=True)
    print(f"  Frontier ideas ({len(ideas_frontier)}):", flush=True)
    for i, idea in enumerate(ideas_frontier):
        print(f"    {i}: {idea['name']}", flush=True)

    merged = deduplicate_ideas(ideas_cheap, ideas_frontier)
    print(f"  Merged to {len(merged)} ideas:", flush=True)
    for i, idea in enumerate(merged):
        src = idea.get("_source", "?")
        print(f"    {i}: [{src}] {idea['name']} — {idea['description'][:80]}", flush=True)

    return merged


def deduplicate_ideas(ideas_cheap, ideas_frontier):
    """Merge two idea lists, remove near-duplicates. Prefer frontier version.

    Uses word-level Jaccard similarity on name+description.
    Returns exactly 3 ideas.
    """
    def _words(idea):
        text = (idea["name"] + " " + idea["description"]).lower()
        return set(re.findall(r'\w+', text))

    # Start with frontier ideas (preferred), add cheap ones that are novel
    frontier_word_sets = [_words(idea) for idea in ideas_frontier]
    selected = []

    # Add all frontier ideas first
    for idea in ideas_frontier:
        idea_copy = dict(idea)
        idea_copy["_source"] = "frontier"
        selected.append(idea_copy)

    # Add cheap ideas that are sufficiently different from all selected
    for idea in ideas_cheap:
        idea_words = _words(idea)
        is_dup = False
        for fw in frontier_word_sets:
            if not idea_words or not fw:
                continue
            jaccard = len(idea_words & fw) / len(idea_words | fw)
            if jaccard > 0.4:  # >40% word overlap = duplicate
                is_dup = True
                break
        if not is_dup:
            idea_copy = dict(idea)
            idea_copy["_source"] = "cheap"
            selected.append(idea_copy)
            frontier_word_sets.append(idea_words)

    # Take top 3 (frontier ideas first, then cheap novelties)
    return selected[:3]


# ============================================================================
# Phase 2: Branch execution with cross-verification + programmatic checking
# ============================================================================

def run_branch(
    branch_id, branch_cfg, problem, idea, prompts,
    log_path, log_lock, stop_event, winner_lock, winner_info, mock=False,
):
    """Run one branch: generate → [cross-verify → escalated-revise + prog check] × ITERATIONS."""
    from pipeline import generate, verify, revise, make_logger
    from ramsey_checker import verify_solution_text

    gen_model = branch_cfg["generator"]
    ver_model = branch_cfg["verifier"]
    rev_model = branch_cfg["reviser"]
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
    gen_prompt = prompts["generator_seeded"].replace(
        "{idea}", f"**{idea['name']}**: {idea['description']}"
    )
    print(f"{tag} GENERATE ({_short(gen_model)}, idea: {idea['name'][:40]})", flush=True)

    solution = generate(
        problem=problem["text"], system=gen_prompt, model=gen_model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"{tag} generated ({len(solution)} chars, {time.time()-t0:.0f}s)", flush=True)

    # --- Programmatic check after generation ---
    prog_result = verify_solution_text(solution) if not mock else {"valid": False, "violations": ["mock"]}
    if prog_result["valid"]:
        print(f"{tag} *** PROGRAMMATIC CHECK PASSED after generation! ***", flush=True)

    # --- Verify/Revise loop with cross-model verification + escalated revision ---
    loop_log = []
    verifier_correct = False
    prog_valid_ever = prog_result["valid"]

    for i in range(ITERATIONS):
        if stop_event.is_set():
            print(f"{tag} STOPPING iter={i+1} (another branch won)", flush=True)
            break

        # Cross-model verify (different model than generator)
        print(f"{tag} VERIFY iter={i+1} ({_short(ver_model)})", flush=True)
        critique = verify(
            problem=problem["text"], solution=solution, system=prompts["verifier"],
            model=ver_model, max_tokens=MAX_TOKENS, logger=logger,
            iteration=i+1, mock=mock,
        )

        if "VERDICT: correct" in critique:
            print(f"{tag} cross-verifier says CORRECT at iter={i+1}", flush=True)
            verifier_correct = True
            loop_log.append({"iteration": i+1, "verdict": "correct", "verifier": _short(ver_model)})
            break

        if stop_event.is_set():
            loop_log.append({"iteration": i+1, "verdict": "issues_found", "stopped": True})
            break

        # Escalated revision (different model than generator)
        print(f"{tag} REVISE iter={i+1} ({_short(rev_model)}, escalated)", flush=True)
        new_solution = revise(
            problem=problem["text"], solution=solution, critique=critique,
            system=prompts["reviser"], model=rev_model, max_tokens=MAX_TOKENS,
            logger=logger, iteration=i+1, mock=mock,
        )

        # Programmatic check after revision
        prog_result = verify_solution_text(new_solution) if not mock else {"valid": False, "violations": ["mock"]}
        if prog_result["valid"] and not prog_valid_ever:
            print(f"\n{'='*60}", flush=True)
            print(f"{tag} *** PROGRAMMATIC CHECK PASSED at iter={i+1}! ***", flush=True)
            print(f"  V={prog_result.get('V_size')}, H={prog_result.get('H_size')}", flush=True)
            print(f"  max_partition={prog_result.get('checks',{}).get('max_partition_found')}", flush=True)
            print(f"{'='*60}\n", flush=True)
            prog_valid_ever = True

        loop_log.append({
            "iteration": i+1,
            "verdict": "issues_found",
            "verifier": _short(ver_model),
            "reviser": _short(rev_model),
            "solution_len": len(new_solution),
            "prog_valid": prog_result["valid"],
        })
        solution = new_solution
        elapsed = time.time() - t0
        print(f"{tag} revised ({len(solution)} chars, {elapsed:.0f}s, prog_valid={prog_result['valid']})", flush=True)

    elapsed = round(time.time() - t0, 2)

    return {
        "branch_id": branch_id,
        "name": bname,
        "generator": gen_model,
        "verifier": ver_model,
        "reviser": rev_model,
        "idea": {k: v for k, v in idea.items() if not k.startswith("_")},
        "iterations_run": len(loop_log),
        "verifier_correct": verifier_correct,
        "prog_valid": prog_valid_ever,
        "elapsed_s": elapsed,
        "final_solution": solution,
        "loop_log": loop_log,
        "status": "completed",
    }


# ============================================================================
# Phase 3: Synthesis
# ============================================================================

SYNTHESIS_PROMPT = """You are an expert mathematician working on a challenging combinatorics/hypergraph problem. You have been given {n} candidate solutions from different approaches. Your task:

1. Carefully read each solution and identify the key ideas, constructions, and techniques used.
2. Identify which solutions (if any) produce valid constructions, and what makes them work.
3. Combine the best insights from all solutions into a single, improved solution.
4. If one solution has a valid construction, try to improve upon it (e.g., find a larger vertex set).
5. If no solution has a valid construction, synthesize the partial progress into a new attempt.

Output a complete solution in the same format, including the explicit hypergraph in {{a,b,...}} notation.

---

**PROBLEM:**
{problem}

**CANDIDATE SOLUTIONS:**

{solutions}

---

Produce your synthesized solution below. Include the explicit hypergraph construction."""


def synthesize(problem, top_results, log_path, log_lock, logger, mock=False):
    """Feed top solutions to Opus for synthesis."""
    from pipeline import _call_llm, make_logger

    print(f"\n[{_ts()}] Phase 3: Synthesis ({_short(SYNTHESIZER_MODEL)})", flush=True)
    print(f"  Combining {len(top_results)} solutions", flush=True)

    solutions_text = ""
    for i, r in enumerate(top_results):
        sol = r.get("final_solution", "")
        name = r.get("name", f"branch-{i}")
        prog = "PROG_VALID" if r.get("prog_valid") else "prog_invalid"
        ver = "VER_CORRECT" if r.get("verifier_correct") else "ver_issues"
        solutions_text += f"\n### Solution {i+1} ({name}, {prog}, {ver})\n\n{sol}\n\n---\n"

    prompt = SYNTHESIS_PROMPT.format(
        n=len(top_results),
        problem=problem["text"],
        solutions=solutions_text,
    )

    t0 = time.time()
    if mock:
        response = "## Synthesized Solution\n\nMock synthesis.\n\n{1,2,3},{4,5,6}"
    else:
        response = _call_llm("", prompt, SYNTHESIZER_MODEL, MAX_TOKENS)

    def _log(*a):
        with log_lock:
            logger(*a)
    _log("synthesize", 0, SYNTHESIZER_MODEL, "", prompt[:500] + "...", response, time.time() - t0)

    print(f"[{_ts()}] Synthesis complete ({len(response)} chars, {time.time()-t0:.0f}s)", flush=True)

    # Programmatic check on synthesis
    from ramsey_checker import verify_solution_text
    prog = verify_solution_text(response) if not mock else {"valid": False, "violations": ["mock"]}
    if prog["valid"]:
        print(f"  *** SYNTHESIS PROGRAMMATIC CHECK PASSED! V={prog.get('V_size')}, H={prog.get('H_size')} ***", flush=True)
    else:
        print(f"  Synthesis prog check: {prog.get('violations', [])}", flush=True)

    return {
        "solution": response,
        "prog_valid": prog["valid"],
        "prog_result": prog,
        "elapsed_s": round(time.time() - t0, 2),
    }


# ============================================================================
# Phase 4: Multi-judge consensus
# ============================================================================

def multi_judge(problem, solution, prompts, log_path, log_lock, logger, label="", mock=False):
    """Run 3 frontier judges in parallel. Return consensus result.

    Uses judge_nogt (no ground truth) for open-problem evaluation.
    Also runs programmatic verification as the real ground truth.
    """
    from pipeline import _call_llm

    print(f"[{_ts()}] Judging: {label}", flush=True)

    def run_one_judge(judge_model):
        prompt = (
            prompts["judge_nogt"]
            .replace("{problem}", problem["text"])
            .replace("{candidate}", solution)
        )
        t0 = time.time()
        if mock:
            response = "The solution is complete and rigorous.\n\nCLASSIFICATION: correct"
        else:
            response = _call_llm("", prompt, judge_model, MAX_TOKENS)

        def _log(*a):
            with log_lock:
                logger(*a)
        _log("judge", 0, judge_model, "", prompt[:300] + "...", response, time.time() - t0)

        # Parse classification
        classif = "incorrect"
        for label_str in ["correct", "almost", "partial", "incorrect"]:
            if f"CLASSIFICATION: {label_str}" in response:
                classif = label_str
                break

        return {
            "model": judge_model,
            "classification": classif,
            "response": response,
            "elapsed_s": round(time.time() - t0, 2),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(JUDGE_MODELS)) as ex:
        futs = {ex.submit(run_one_judge, m): m for m in JUDGE_MODELS}
        judge_results = []
        for fut in concurrent.futures.as_completed(futs, timeout=600):
            result = fut.result(timeout=600)
            judge_results.append(result)
            print(f"  {_short(result['model'])}: {result['classification']} ({result['elapsed_s']:.0f}s)", flush=True)

    # Programmatic verification (the real test)
    from ramsey_checker import verify_solution_text
    prog = verify_solution_text(solution) if not mock else {"valid": False, "violations": ["mock"]}

    classifications = [r["classification"] for r in judge_results]
    consensus = all(c in ("correct", "almost") for c in classifications)

    return {
        "label": label,
        "judge_results": judge_results,
        "classifications": classifications,
        "consensus_positive": consensus,
        "programmatic": prog,
    }


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Frontier attack v2 on ramsey-hypergraphs")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    problem = load_problem()

    print(f"\n{'='*70}")
    print(f"FRONTIER ATTACK v2: {PROBLEM_ID}")
    print(f"{'='*70}")
    print(f"Level: {problem['level']}")
    print(f"Problem: {problem['text'][:200]}...")
    print(f"Ground-truth solution: {len(problem['solution'])} chars")
    print()
    print("Architecture:")
    print("  Phase 1: Dual ideation (flash-lite + Opus)")
    print("  Phase 2: 3 branches × 6 iterations (cross-verify, escalated-revise, prog check)")
    print("  Phase 3: Synthesis (Opus combines top solutions)")
    print("  Phase 4: Multi-judge consensus (3 frontier models) + programmatic verification")
    print()
    print("Branch assignments:")
    for bid, cfg in BRANCHES.items():
        print(f"  b{bid}: {cfg['name']}")
        print(f"      gen={_short(cfg['generator'])}, ver={_short(cfg['verifier'])}, rev={_short(cfg['reviser'])}")
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

    from pipeline import make_logger
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    log_lock = threading.Lock()
    logger = make_logger(str(log_path))

    t_start = time.time()

    # -----------------------------------------------------------------------
    # Phase 1: Dual ideation
    # -----------------------------------------------------------------------
    ideas = dual_ideate(problem["text"], prompts, logger, log_lock, mock=args.mock)
    print(f"\n[{_ts()}] Ideation complete: {len(ideas)} ideas in {time.time()-t_start:.0f}s\n", flush=True)

    # Assign ideas to branches
    branch_ideas = {}
    for bid in BRANCHES:
        if bid < len(ideas):
            branch_ideas[bid] = ideas[bid]
        else:
            # Fallback: reuse first idea
            branch_ideas[bid] = ideas[0]

    # -----------------------------------------------------------------------
    # Phase 2: Branch execution
    # -----------------------------------------------------------------------
    print(f"[{_ts()}] Phase 2: Launching {len(BRANCHES)} branches in parallel", flush=True)
    print(f"  {ITERATIONS} verify/revise iterations each, cross-model verification\n", flush=True)

    stop_event = threading.Event()
    winner_lock = threading.Lock()
    winner_info = {}

    branch_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(BRANCHES)) as ex:
        futs = {
            ex.submit(
                run_branch, bid, cfg, problem, branch_ideas[bid],
                prompts, log_path, log_lock, stop_event,
                winner_lock, winner_info, args.mock,
            ): bid
            for bid, cfg in BRANCHES.items()
        }
        for fut in concurrent.futures.as_completed(futs, timeout=7200):
            bid = futs[fut]
            try:
                result = fut.result(timeout=7200)
                branch_results.append(result)
                status = result.get("status", "?")
                prog = result.get("prog_valid", False)
                ver = result.get("verifier_correct", False)
                elapsed = result.get("elapsed_s", 0)
                print(f"\n[{_ts()}] Branch {bid} ({BRANCHES[bid]['name']}) finished: "
                      f"prog_valid={prog}, verifier_correct={ver}, {elapsed:.0f}s\n", flush=True)
            except Exception as e:
                print(f"\n[{_ts()}] Branch {bid} ({BRANCHES[bid]['name']}) FAILED: {e}\n", flush=True)
                branch_results.append({
                    "branch_id": bid,
                    "name": BRANCHES[bid]["name"],
                    "status": "error",
                    "error": str(e),
                })

    print(f"\n[{_ts()}] All branches complete ({time.time()-t_start:.0f}s total)\n", flush=True)

    # -----------------------------------------------------------------------
    # Phase 3: Synthesis
    # -----------------------------------------------------------------------
    # Select top solutions for synthesis (all completed branches)
    completed = [r for r in branch_results if r.get("status") == "completed"]
    # Sort: programmatically valid first, then by iterations run
    completed.sort(key=lambda r: (r.get("prog_valid", False), r.get("verifier_correct", False)), reverse=True)
    top_for_synthesis = completed[:3]

    synthesis_result = None
    if top_for_synthesis:
        synthesis_result = synthesize(
            problem, top_for_synthesis, log_path, log_lock, logger, mock=args.mock,
        )

    # -----------------------------------------------------------------------
    # Phase 4: Multi-judge consensus
    # -----------------------------------------------------------------------
    print(f"\n[{_ts()}] Phase 4: Multi-judge consensus\n", flush=True)

    # Judge each completed branch + synthesis
    candidates = []
    for r in completed:
        if r.get("final_solution"):
            candidates.append({
                "label": r["name"],
                "solution": r["final_solution"],
                "prog_valid": r.get("prog_valid", False),
                "source": "branch",
                "branch_result": r,
            })

    if synthesis_result and synthesis_result.get("solution"):
        candidates.append({
            "label": "synthesis",
            "solution": synthesis_result["solution"],
            "prog_valid": synthesis_result.get("prog_valid", False),
            "source": "synthesis",
        })

    # Judge programmatically valid candidates first, then others
    candidates.sort(key=lambda c: c["prog_valid"], reverse=True)

    judge_results = []
    for cand in candidates:
        jresult = multi_judge(
            problem, cand["solution"], prompts,
            log_path, log_lock, logger,
            label=cand["label"], mock=args.mock,
        )
        jresult["prog_valid"] = cand["prog_valid"]
        judge_results.append(jresult)

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    total_elapsed = round(time.time() - t_start, 2)

    print(f"\n{'='*70}")
    print(f"RESULTS — FRONTIER ATTACK v2")
    print(f"{'='*70}\n")

    print("Branch results:")
    for r in branch_results:
        status = r.get("status", "?")
        if status == "skipped":
            print(f"  {r['name']:<20} SKIPPED")
        elif status == "error":
            print(f"  {r['name']:<20} ERROR: {r.get('error', '')[:60]}")
        else:
            prog = "PROG_VALID" if r.get("prog_valid") else "prog_invalid"
            ver = "VER_OK" if r.get("verifier_correct") else "ver_issues"
            iters = r.get("iterations_run", 0)
            elapsed = r.get("elapsed_s", 0)
            idea = r.get("idea", {})
            print(f"  {r['name']:<20} {prog:<15} {ver:<12} iters={iters}  {elapsed:.0f}s  idea={idea.get('name','?')[:30]}")

    if synthesis_result:
        prog = "PROG_VALID" if synthesis_result.get("prog_valid") else "prog_invalid"
        print(f"\n  Synthesis:          {prog:<15} {synthesis_result.get('elapsed_s', 0):.0f}s")

    print("\nJudge consensus:")
    for jr in judge_results:
        label = jr.get("label", "?")
        classifs = jr.get("classifications", [])
        prog = jr.get("programmatic", {})
        prog_str = "PROG_VALID" if prog.get("valid") else f"prog_invalid({prog.get('violations', ['?'])[0][:40]})"
        consensus = "CONSENSUS" if jr.get("consensus_positive") else "no_consensus"
        print(f"  {label:<20} judges={classifs}  {consensus}  {prog_str}")

    # Determine best candidate
    best = None
    # Priority 1: programmatically valid
    for jr in judge_results:
        if jr.get("programmatic", {}).get("valid"):
            best = jr
            break
    # Priority 2: judge consensus positive
    if not best:
        for jr in judge_results:
            if jr.get("consensus_positive"):
                best = jr
                break
    # Priority 3: any "correct" classification
    if not best:
        for jr in judge_results:
            if "correct" in jr.get("classifications", []):
                best = jr
                break

    if best:
        prog = best.get("programmatic", {})
        print(f"\n  BEST: {best['label']}")
        print(f"    Judge consensus: {best.get('classifications')}")
        print(f"    Programmatic: valid={prog.get('valid')}, V={prog.get('V_size')}, H={prog.get('H_size')}")
        if prog.get("checks", {}).get("max_partition_found") is not None:
            print(f"    Max partition found: {prog['checks']['max_partition_found']}")
    else:
        print("\n  No valid solution found.")

    print(f"\n  Total elapsed: {total_elapsed:.0f}s")

    # --- Save ---
    ts = _now()
    suffix = "_mock" if args.mock else ""
    output = {
        "experiment": EXPERIMENT_NAME,
        "problem_id": PROBLEM_ID,
        "date": datetime.now(timezone.utc).isoformat(),
        "architecture": {
            "branches": {str(k): v for k, v in BRANCHES.items()},
            "ideators": [IDEATOR_CHEAP, IDEATOR_FRONTIER],
            "judges": JUDGE_MODELS,
            "synthesizer": SYNTHESIZER_MODEL,
            "iterations": ITERATIONS,
        },
        "ideas": [{k: v for k, v in idea.items() if not k.startswith("_")} for idea in ideas],
        "branch_results": branch_results,
        "synthesis_result": synthesis_result,
        "judge_results": [
            {k: v for k, v in jr.items() if k != "judge_results" or True}
            for jr in judge_results
        ],
        "best_label": best["label"] if best else None,
        "total_elapsed_s": total_elapsed,
        "mock": args.mock,
    }
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to: {out_path}")
    print(f"Pipeline log:     {log_path}")


if __name__ == "__main__":
    main()
