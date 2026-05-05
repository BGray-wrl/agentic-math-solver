#!/usr/bin/env python3
"""
Seed-Ideas 4-Way Comparison v2 — 70-problem cross-model benchmark.

Architecture (per (model, problem, mode)):
  Roles
    Ideator/Generator/Verifier/Reviser  : <model under test> (self-ideation/critique/revision)
    Final Judge                         : openrouter/deepseek/deepseek-v4-pro + judge_gt.md

  Modes
    1. generate       : 3 × (generate → judge), pick best (pass@3)
    2. full           : 1 × (generate → [verify → revise] × 2 → judge)
    3. seed_generate  : ideate(3) → 3 parallel (seeded generate → judge), pick best
    4. seed_full      : ideate(3) → 3 parallel (seeded generate → [V↔R]×2 → judge), pick best

Hardening
  - MAX_TOKENS = 65536 everywhere (let reasoning models breathe; user requirement)
  - Per-trial incremental save to disk so a crash can't lose a frontier solve
  - 3-key OpenRouter rotation, 80 outer workers + 3 inner workers per seed-mode trial
  - --max-cost killswitch aborts cleanly when cumulative spend hits the cap

Usage
  uv run experiments/seed_ideas_full_compare_20260504.py --mock
  uv run experiments/seed_ideas_full_compare_20260504.py --smoke
  uv run experiments/seed_ideas_full_compare_20260504.py --phase initial --max-cost 80
  uv run experiments/seed_ideas_full_compare_20260504.py --phase seed-full \
      --models gpt-oss-120b gemma-4-31b-it deepseek-v4-flash \
      --problems-subset 30 \
      --from-run-id <phase1_run_id>
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import itertools
import json
import os
import random
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

from problemset_70 import load_70_problems, SPECIAL_10  # noqa: E402

# ============================================================================
# Configuration
# ============================================================================

EXPERIMENT_NAME = "phase1_reasoning_20260505"

# Re-run with reasoning ON for both cheap models. Judge: v4-flash.
MODELS = [
    ("openrouter/openai/gpt-oss-120b",   0.18),
    ("openrouter/google/gemma-4-31b-it", 0.38),
]
PRICE_PER_MTOKEN = {m: p for m, p in MODELS}

JUDGE_MODEL  = "openrouter/deepseek/deepseek-v4-flash"
JUDGE_PRICE  = 0.28

# Reasoning: enable extra_body reasoning for both models (effort=high).
# Judge model gets no reasoning (v4-flash is non-reasoning).
REASONING_MODELS = {m for m, _ in MODELS}
REASONING_CONFIG = {"effort": "high"}

NUM_IDEAS         = 3
ITERATIONS        = 2          # 1 generate + 2 revisions
PASS_K_GENERATE   = 3          # pass@3 for generate-only mode

# Token budgets — generously sized so reasoning models can output their full trace.
MAX_TOKENS_GEN     = 65536
MAX_TOKENS_VERIFY  = 65536
MAX_TOKENS_REVISE  = 65536
MAX_TOKENS_IDEATE  = 16000     # ideas are short; 16K is enough
MAX_TOKENS_JUDGE   = 65536

MAX_WORKERS        = 80        # outer pool across (model, problem, mode) trials
INNER_WORKERS      = 3         # parallel branches per seed-mode trial

TRIAL_TIMEOUT      = 5400      # 90 min per trial
LITELLM_TIMEOUT    = 1800      # 30 min per single API call

PASS_THRESHOLD     = 6         # ≥6/7 = passed (used for special-10 frontier-pass logging)

ALL_MODES = ("generate", "full", "seed_generate", "seed_full")
INITIAL_MODES = ("generate", "full", "seed_generate")
SEED_FULL_MODES = ("seed_full",)

# ============================================================================
# Paths
# ============================================================================

ROOT = Path(__file__).parent.parent
PROMPTS_DIR  = ROOT / "prompts" / "pipeline"
RESULTS_DIR  = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ============================================================================
# Key rotation
# ============================================================================

load_dotenv()
# Single key dedicated to this run — keeps experiments isolated.
SINGLE_KEY_ENV = os.getenv("PHASE1_REASONING_KEY_ENV", "OPENROUTER_API_KEY_X")
SINGLE_KEY = os.getenv(SINGLE_KEY_ENV)
if not SINGLE_KEY:
    raise SystemExit(f"{SINGLE_KEY_ENV} not set in .env")


def _probe_key(key: str) -> None:
    import requests
    try:
        r = requests.get("https://openrouter.ai/api/v1/key",
                         headers={"Authorization": f"Bearer {key}"}, timeout=8)
        d = r.json().get("data", {}) or {}
        usage = d.get("usage", 0) or 0
        limit = d.get("limit")
        rem = (limit - usage) if limit is not None else "unlim"
        print(f"[startup] {SINGLE_KEY_ENV}: usage={usage:.2f}/{limit}, remain={rem}", flush=True)
        if limit is not None and usage >= limit:
            raise SystemExit(f"{SINGLE_KEY_ENV} exhausted")
    except SystemExit:
        raise
    except Exception as e:
        print(f"[startup] {SINGLE_KEY_ENV}: probe failed ({e})", flush=True)


KEYS = [SINGLE_KEY]
_key_iter = itertools.cycle(KEYS)
_key_lock = threading.Lock()
def next_key() -> str:
    with _key_lock:
        return next(_key_iter)


# ============================================================================
# Mock responses (for --mock)
# ============================================================================

MOCK_IDEAS = [
    {"name": "Direct construction", "description": "Build an explicit example."},
    {"name": "Contradiction",       "description": "Assume the negation, derive contradiction."},
    {"name": "Induction on n",      "description": "Strong induction on the parameter."},
]

MOCK_GEN = (
    "## Summary\n**Verdict:** Solved\n**Method sketch:** Mock solution.\n\n"
    "## Detailed Solution\nMock detailed proof.\n\n\\boxed{42}"
)
MOCK_VERIFY_PASS = "<ANALYSIS>OK</ANALYSIS>\n<CORRECT>true</CORRECT>\n<GAPS>None</GAPS>\nVERDICT: correct"
MOCK_VERIFY_FAIL = "<ANALYSIS>Gap.</ANALYSIS>\n<CORRECT>false</CORRECT>\n<GAPS>- [Gap]: Step 2 unjustified.</GAPS>\nVERDICT: issues_found"
MOCK_REVISE = (
    "## Summary\n**Verdict:** Solved\n**Method sketch:** Revised mock.\n"
    "**Changes:** Fixed step 2.\n\n## Detailed Solution\nRevised mock proof.\n\\boxed{42}"
)
MOCK_JUDGE = "<points>7 out of 7</points>\nMock judge."


# ============================================================================
# call_model — single LLM call with key rotation, retry, token capture
# ============================================================================

def call_model(
    model: str,
    system: str | None,
    user: str,
    max_tokens: int,
    retries: int = 2,
    backoff: float = 5.0,
) -> tuple[str, dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        key = next_key()
        try:
            kwargs = dict(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                api_key=key,
                timeout=LITELLM_TIMEOUT,
            )
            if model in REASONING_MODELS:
                kwargs["extra_body"] = {"reasoning": REASONING_CONFIG}
            resp = litellm.completion(**kwargs)
            content = resp.choices[0].message.content  # type: ignore
            if not content:
                content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
            if not content:
                raise ValueError(f"Model {model} returned empty content + reasoning_content")
            usage = getattr(resp, "usage", None)
            usage_dict = {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
            }
            return content, usage_dict
        except Exception as e:
            last_err = e
            msg = str(e)
            if "402" in msg or "Insufficient credits" in msg or "Key limit exceeded" in msg or '"code":403' in msg:
                raise   # don't retry credit/key-limit failures
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1} failed: {e} — retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    assert last_err is not None
    raise last_err


# ============================================================================
# Cost tracking + killswitch
# ============================================================================

class CostTracker:
    def __init__(self, max_cost: float | None):
        self.max_cost = max_cost
        self._cost = 0.0
        self._tokens_in  = 0
        self._tokens_out = 0
        self._lock = threading.Lock()
        self._aborted = False

    def add(self, cost: float, in_tok: int, out_tok: int) -> None:
        with self._lock:
            self._cost += cost
            self._tokens_in  += in_tok
            self._tokens_out += out_tok
            if self.max_cost is not None and self._cost >= self.max_cost and not self._aborted:
                self._aborted = True
                print(f"[{_ts()}] [KILLSWITCH] Cumulative cost ${self._cost:.2f} >= cap ${self.max_cost:.2f}. "
                      f"No new trials will start; in-flight trials will finish.", flush=True)

    def aborted(self) -> bool:
        with self._lock:
            return self._aborted

    def snapshot(self) -> tuple[float, int, int]:
        with self._lock:
            return self._cost, self._tokens_in, self._tokens_out


def cost_for(model: str, total_tokens: int) -> float:
    p = PRICE_PER_MTOKEN.get(model) if model != JUDGE_MODEL else JUDGE_PRICE
    return (p or 0.0) * total_tokens / 1_000_000


# ============================================================================
# Atomic pipeline calls (each tracks its own cost)
# ============================================================================

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _record_call(
    calls: list, kind: str, model: str, usage: dict, elapsed: float, tracker: CostTracker,
    response_text: str | None = None,
) -> None:
    cost = cost_for(model, usage["total_tokens"])
    calls.append({
        "kind":          kind,
        "model":         model,
        "elapsed":       round(elapsed, 2),
        "usage":         usage,
        "cost_usd":      round(cost, 6),
        "response_text": response_text,   # full raw response for audit / debugging
    })
    tracker.add(cost, usage["prompt_tokens"], usage["completion_tokens"])


def do_generate(model, problem_text, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    if mock:
        return MOCK_GEN, {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    text, usage = call_model(model, prompts["generator"], problem_text, MAX_TOKENS_GEN)
    _record_call(calls, "generate", model, usage, time.time()-t0, tracker, response_text=text)
    return text, usage


def do_ideate(model, problem_text, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    prompt_filled = prompts["ideator"].replace("{problem}", problem_text).replace("{num_ideas}", str(NUM_IDEAS))
    if mock:
        ideas = MOCK_IDEAS[:NUM_IDEAS]
        return ideas, "MOCK_IDEATE", {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}
    text, usage = call_model(model, "", prompt_filled, MAX_TOKENS_IDEATE)
    _record_call(calls, "ideate", model, usage, time.time()-t0, tracker, response_text=text)
    # Parse JSON ideas (mirroring src/pipeline.py:ideate logic)
    ideas = None
    def _fix(t): return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', t)
    for pattern in (r"```json\s*(\[.*?\])\s*```", r"(\[.*\])"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            for attempt in (m.group(1), _fix(m.group(1))):
                try:
                    ideas = json.loads(attempt); break
                except json.JSONDecodeError:
                    continue
            if ideas: break
    if not ideas:
        ideas = [{"name": f"default-{i}", "description": "Solve naturally."} for i in range(NUM_IDEAS)]
    return ideas[:NUM_IDEAS], text, usage


def do_seeded_generate(model, problem_text, idea, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    idea_str = f"**{idea.get('name','')}**: {idea.get('description','')}"
    sys_filled = prompts["generator_seeded"].replace("{idea}", idea_str)
    if mock:
        return MOCK_GEN, {"prompt_tokens": 120, "completion_tokens": 50, "total_tokens": 170}
    text, usage = call_model(model, sys_filled, problem_text, MAX_TOKENS_GEN)
    _record_call(calls, "seeded_generate", model, usage, time.time()-t0, tracker, response_text=text)
    return text, usage


def do_verify(model, problem_text, solution, calls, tracker, mock=False, mock_pass=False, prompts=None):
    t0 = time.time()
    sys_part, _, content_part = prompts["verifier"].partition("\n**PROBLEM:**\n")
    if not _:
        # Whole template is content; no system part.
        sys_part = ""
        content_part = prompts["verifier"]
    else:
        content_part = "**PROBLEM:**\n" + content_part
    user = content_part.replace("{problem}", problem_text).replace("{solution}", solution)
    if mock:
        return (MOCK_VERIFY_PASS if mock_pass else MOCK_VERIFY_FAIL), {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230}
    text, usage = call_model(model, sys_part, user, MAX_TOKENS_VERIFY)
    _record_call(calls, "verify", model, usage, time.time()-t0, tracker, response_text=text)
    return text, usage


def do_revise(model, problem_text, solution, critique, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    sys_part, _, content_part = prompts["reviser"].partition("\n**PROBLEM:**\n")
    if not _:
        sys_part = ""
        content_part = prompts["reviser"]
    else:
        content_part = "**PROBLEM:**\n" + content_part
    user = (content_part
            .replace("{problem}", problem_text)
            .replace("{solution}", solution)
            .replace("{critique}", critique))
    if mock:
        return MOCK_REVISE, {"prompt_tokens": 300, "completion_tokens": 60, "total_tokens": 360}
    text, usage = call_model(model, sys_part, user, MAX_TOKENS_REVISE)
    _record_call(calls, "revise", model, usage, time.time()-t0, tracker, response_text=text)
    return text, usage


def do_judge(problem_text, candidate, ground_truth, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    if mock:
        return MOCK_JUDGE, 7, {"prompt_tokens": 400, "completion_tokens": 30, "total_tokens": 430}
    user = (prompts["judge_gt"]
            .replace("{problem}", problem_text)
            .replace("{ground_truth}", ground_truth)
            .replace("{candidate}", candidate))
    text, usage = call_model(JUDGE_MODEL, "", user, MAX_TOKENS_JUDGE)
    _record_call(calls, "judge", JUDGE_MODEL, usage, time.time()-t0, tracker, response_text=text)
    score = parse_gt_score(text)
    return text, score, usage


def parse_gt_score(verdict: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m: return int(m.group(1))
    return 0


# ============================================================================
# Mode runners — each returns a trial-result dict
# ============================================================================

def run_full_branch(model, problem_text, ground_truth, initial_solution, calls, tracker, mock, prompts):
    """generate (already done) → [verify → revise]*ITERATIONS → judge."""
    solution = initial_solution
    loop_log = []
    stopped_early = False
    for i in range(ITERATIONS):
        critique, _u = do_verify(model, problem_text, solution, calls, tracker,
                                 mock=mock, mock_pass=(i==1 and mock), prompts=prompts)
        if "VERDICT: correct" in critique:
            stopped_early = True
            loop_log.append({"iteration": i+1, "verdict": "correct", "critique": critique, "solution": solution})
            break
        new_solution, _u = do_revise(model, problem_text, solution, critique, calls, tracker,
                                     mock=mock, prompts=prompts)
        loop_log.append({"iteration": i+1, "verdict": "issues_found",
                         "critique": critique, "solution_before": solution,
                         "solution_after": new_solution})
        solution = new_solution
    verdict, score, _u = do_judge(problem_text, solution, ground_truth, calls, tracker,
                                  mock=mock, prompts=prompts)
    return solution, verdict, score, loop_log, stopped_early


def run_mode_generate(model, problem, calls, tracker, mock, prompts):
    """3 independent generates, judge each, pick best."""
    branches = []
    for k in range(PASS_K_GENERATE):
        sol, _u = do_generate(model, problem["text"], calls, tracker, mock=mock, prompts=prompts)
        verdict, score, _ju = do_judge(problem["text"], sol, problem["ground_truth"], calls, tracker,
                                        mock=mock, prompts=prompts)
        branches.append({"k": k, "solution": sol, "verdict": verdict, "score": score})
    best = max(branches, key=lambda b: b["score"])
    return {
        "best_score":      best["score"],
        "best_solution":   best["solution"],
        "best_verdict":    best["verdict"],
        "branches":        branches,
        "mode_extras":     {"pass_k": PASS_K_GENERATE},
    }


def run_mode_full(model, problem, calls, tracker, mock, prompts):
    """1 generate → verify ↔ revise × 2 → judge."""
    sol, _u = do_generate(model, problem["text"], calls, tracker, mock=mock, prompts=prompts)
    final_sol, verdict, score, loop_log, stopped_early = run_full_branch(
        model, problem["text"], problem["ground_truth"], sol, calls, tracker, mock, prompts)
    return {
        "best_score":     score,
        "best_solution":  final_sol,
        "best_verdict":   verdict,
        "branches":       [{
            "k": 0, "initial_solution": sol, "final_solution": final_sol,
            "verdict": verdict, "score": score, "loop_log": loop_log,
            "stopped_early": stopped_early,
        }],
        "mode_extras":    {"iterations": ITERATIONS, "stopped_early": stopped_early},
    }


def run_mode_seed_generate(model, problem, calls, tracker, mock, prompts):
    """ideate(3) → 3 parallel (seeded gen → judge), pick best."""
    ideas, ideate_text, _u = do_ideate(model, problem["text"], calls, tracker, mock=mock, prompts=prompts)

    def _branch(idx_idea):
        idx, idea = idx_idea
        b_calls = []
        sol, _ = do_seeded_generate(model, problem["text"], idea, b_calls, tracker, mock=mock, prompts=prompts)
        verdict, score, _ = do_judge(problem["text"], sol, problem["ground_truth"], b_calls, tracker,
                                     mock=mock, prompts=prompts)
        return {"idea_idx": idx, "idea": idea, "solution": sol, "verdict": verdict, "score": score, "calls": b_calls}

    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        branches = list(ex.map(_branch, list(enumerate(ideas))))
    # Append branch calls to outer call log (for cost accounting fidelity)
    for b in branches:
        calls.extend(b.pop("calls"))
    best = max(branches, key=lambda b: b["score"])
    return {
        "best_score":     best["score"],
        "best_solution":  best["solution"],
        "best_verdict":   best["verdict"],
        "branches":       branches,
        "mode_extras":    {"num_ideas": NUM_IDEAS, "ideas": ideas, "ideate_response": ideate_text},
    }


def run_mode_seed_full(model, problem, calls, tracker, mock, prompts):
    """ideate(3) → 3 parallel (seeded gen → V↔R×2 → judge), pick best."""
    ideas, ideate_text, _u = do_ideate(model, problem["text"], calls, tracker, mock=mock, prompts=prompts)

    def _branch(idx_idea):
        idx, idea = idx_idea
        b_calls = []
        sol, _ = do_seeded_generate(model, problem["text"], idea, b_calls, tracker, mock=mock, prompts=prompts)
        final_sol, verdict, score, loop_log, stopped_early = run_full_branch(
            model, problem["text"], problem["ground_truth"], sol, b_calls, tracker, mock, prompts)
        return {
            "idea_idx": idx, "idea": idea,
            "initial_solution": sol, "final_solution": final_sol,
            "verdict": verdict, "score": score,
            "loop_log": loop_log, "stopped_early": stopped_early,
            "calls": b_calls,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        branches = list(ex.map(_branch, list(enumerate(ideas))))
    for b in branches:
        calls.extend(b.pop("calls"))
    best = max(branches, key=lambda b: b["score"])
    return {
        "best_score":     best["score"],
        "best_solution":  best["final_solution"],
        "best_verdict":   best["verdict"],
        "branches":       branches,
        "mode_extras":    {"num_ideas": NUM_IDEAS, "iterations": ITERATIONS, "ideas": ideas,
                           "ideate_response": ideate_text},
    }


MODE_RUNNERS = {
    "generate":      run_mode_generate,
    "full":          run_mode_full,
    "seed_generate": run_mode_seed_generate,
    "seed_full":     run_mode_seed_full,
}


# ============================================================================
# Trial wrapper + per-trial save
# ============================================================================

def model_short(model: str) -> str:
    return model.split("/")[-1]


def trial_path(run_dir: Path, mode: str, model: str, pid: str) -> Path:
    return run_dir / mode / model_short(model) / f"{pid}.json"


def save_trial(run_dir: Path, manifest_lock: threading.Lock, frontier_lock: threading.Lock,
               trial: dict) -> None:
    p = trial_path(run_dir, trial["mode"], trial["model"], trial["problem_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(trial, f, indent=2, ensure_ascii=False)
    summary = {
        "ts":           trial["completed_at"],
        "mode":         trial["mode"],
        "model":        trial["model"],
        "problem_id":   trial["problem_id"],
        "score":        trial.get("score"),
        "passed":       trial.get("passed"),
        "elapsed_s":    trial.get("elapsed_s"),
        "cost_usd":     trial.get("cost_usd"),
        "n_calls":      len(trial.get("calls", [])),
        "error":        trial.get("error"),
    }
    with manifest_lock:
        with open(run_dir / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")
    # Frontier solve logging for the special 10
    if (trial["problem_id"] in SPECIAL_10
            and trial.get("score") is not None
            and trial["score"] >= PASS_THRESHOLD
            and not trial.get("error")):
        with frontier_lock:
            with open(run_dir / "frontier_passes.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts":         trial["completed_at"],
                    "mode":       trial["mode"],
                    "model":      trial["model"],
                    "problem_id": trial["problem_id"],
                    "score":      trial["score"],
                    "solution":   trial["best_solution"],
                    "verdict":    trial["best_verdict"],
                }) + "\n")


def run_trial(model: str, problem: dict, problem_id: str, mode: str,
              prompts: dict, run_dir: Path, manifest_lock: threading.Lock,
              frontier_lock: threading.Lock, tracker: CostTracker, mock: bool) -> dict:
    pid = problem_id
    ms = model_short(model)
    tag = f"[{_ts()}] [{mode}|{ms}|{pid}]"
    print(f"{tag} start", flush=True)
    t0 = time.time()
    calls: list = []

    trial: dict = {
        "experiment":   EXPERIMENT_NAME,
        "mode":         mode,
        "model":        model,
        "problem_id":   pid,
        "category":     problem.get("category", ""),
        "level":        problem.get("level", ""),
        "source":       problem.get("source", ""),
        "is_special":   pid in SPECIAL_10,
        "started_at":   datetime.now(timezone.utc).isoformat(),
    }

    try:
        runner = MODE_RUNNERS[mode]
        out = runner(model, problem, calls, tracker, mock, prompts)
        elapsed = round(time.time() - t0, 2)
        score = out["best_score"]
        cost = round(sum(c["cost_usd"] for c in calls), 6)
        trial.update({
            "score":         score,
            "passed":        score is not None and score >= PASS_THRESHOLD,
            "elapsed_s":     elapsed,
            "cost_usd":      cost,
            "best_solution": out["best_solution"],
            "best_verdict":  out["best_verdict"],
            "branches":      out["branches"],
            "mode_extras":   out.get("mode_extras", {}),
            "calls":         calls,
            "completed_at":  datetime.now(timezone.utc).isoformat(),
        })
        print(f"{tag} done  score={score}/7  ${cost:.4f}  {elapsed}s", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        cost = round(sum(c["cost_usd"] for c in calls), 6)
        traceback.print_exc()
        trial.update({
            "score":         None,
            "passed":        False,
            "elapsed_s":     elapsed,
            "cost_usd":      cost,
            "best_solution": None,
            "best_verdict":  None,
            "branches":      [],
            "calls":         calls,
            "error":         str(e),
            "completed_at":  datetime.now(timezone.utc).isoformat(),
        })
        print(f"{tag} ERROR {e}  ${cost:.4f}  {elapsed}s", flush=True)

    save_trial(run_dir, manifest_lock, frontier_lock, trial)
    return trial


# ============================================================================
# Phase executor
# ============================================================================

def _short_to_full(short: str) -> str:
    for m, _ in MODELS:
        if model_short(m) == short:
            return m
    raise SystemExit(f"Unknown model short name: {short}")


def already_done(run_dir: Path, mode: str, model: str, pid: str) -> bool:
    """Skip a trial if its per-trial file already exists with a non-error result.

    Lets us resume a partially-completed phase without redoing work.
    """
    p = trial_path(run_dir, mode, model, pid)
    if not p.exists():
        return False
    try:
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        return not t.get("error") and t.get("score") is not None
    except Exception:
        return False


def execute_phase(modes: tuple[str, ...], models: list[str], problems: dict, prompts: dict,
                  run_dir: Path, tracker: CostTracker, mock: bool) -> list[dict]:
    pids = sorted(problems.keys())
    trials = [(pid, m, mo) for pid in pids for m in models for mo in modes]
    # Skip already-done
    pending = [(pid, m, mo) for (pid, m, mo) in trials
               if not already_done(run_dir, mo, m, pid)]
    skipped = len(trials) - len(pending)

    print(f"\n=== Phase: modes={list(modes)}  models={[model_short(m) for m in models]} ===", flush=True)
    print(f"Total trials: {len(trials)}  pending: {len(pending)}  skipped (already done): {skipped}", flush=True)
    print(f"max_workers={MAX_WORKERS}, keys={len(KEYS)}, max_cost=${tracker.max_cost}\n", flush=True)

    manifest_lock = threading.Lock()
    frontier_lock = threading.Lock()

    results = []

    def _submit(pid, m, mo):
        return run_trial(m, problems[pid], pid, mo, prompts, run_dir, manifest_lock, frontier_lock, tracker, mock)

    completed = 0
    last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        # Submit initially. If killswitch fires, we stop submitting more.
        futs = {}
        for pid, m, mo in pending:
            if tracker.aborted():
                print(f"[{_ts()}] [KILLSWITCH] not submitting remaining {len(pending)-completed-len(futs)} trials.", flush=True)
                break
            futs[ex.submit(_submit, pid, m, mo)] = (pid, m, mo)

        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * max(len(pending), 1)):
            pid, m, mo = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = model_short(m)
                print(f"[{_ts()}] FAILED [{mo}|{ms}|{pid}]: {e}", flush=True)
                results.append({"problem_id": pid, "model": m, "mode": mo, "error": str(e)})
            now = time.time()
            if completed % 5 == 0 or now - last_print > 60:
                cum_cost, in_t, out_t = tracker.snapshot()
                print(f"[{_ts()}] Progress: {completed}/{len(pending)}  cum=${cum_cost:.2f}  "
                      f"in={in_t:,} out={out_t:,}", flush=True)
                last_print = now
    return results


# ============================================================================
# Reporting
# ============================================================================

def aggregate(run_dir: Path) -> dict:
    """Walk per-trial files and build a summary."""
    trials = []
    for p in sorted(run_dir.rglob("*.json")):
        if p.parent == run_dir:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                trials.append(json.load(f))
        except Exception:
            pass
    return {"n_trials": len(trials), "trials": trials}


def print_summary(run_dir: Path) -> None:
    agg = aggregate(run_dir)
    trials = agg["trials"]
    if not trials:
        print(f"No trials in {run_dir}")
        return
    print(f"\n{'='*100}")
    print(f"SEED-IDEAS 4-WAY COMPARISON v2 — run_dir = {run_dir.name}")
    print(f"{'='*100}\n")

    by_mode: dict[str, dict[str, list[dict]]] = {}
    for t in trials:
        by_mode.setdefault(t["mode"], {}).setdefault(t["model"], []).append(t)

    cost_total = sum(t.get("cost_usd", 0) or 0 for t in trials)
    print(f"Total trials: {len(trials)}    Total cost: ${cost_total:.2f}\n")

    for mode in ALL_MODES:
        if mode not in by_mode: continue
        print(f"-- {mode} --")
        print(f"  {'Model':<30}  {'n':>3}  {'mean':>5}  {'pass':>6}  {'$/run':>8}  {'$ tot':>7}")
        for model in [m for m, _ in MODELS]:
            rs = by_mode[mode].get(model, [])
            if not rs: continue
            valid = [r for r in rs if r.get("score") is not None and not r.get("error")]
            scores = [r["score"] for r in valid]
            passes = sum(1 for r in valid if r.get("passed"))
            costs  = [r.get("cost_usd", 0) or 0 for r in rs]
            ms = model_short(model)
            mean_s = float(np.mean(scores)) if scores else 0.0
            print(f"  {ms:<30}  {len(valid):>3}  {mean_s:>5.2f}  {passes}/{len(valid):<3}  "
                  f"${np.mean(costs):.4f}  ${sum(costs):.3f}")
        print()


# ============================================================================
# Main / CLI
# ============================================================================

def load_prompts() -> dict:
    return {
        "generator":         load_prompt("generator.md"),
        "generator_seeded":  load_prompt("generator_seeded.md"),
        "ideator":           load_prompt("ideator.md"),
        "verifier":          load_prompt("verifier.md"),
        "reviser":           load_prompt("reviser.md"),
        "judge_gt":          load_prompt("judge_gt.md"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock",  action="store_true", help="Mock mode — no API calls.")
    p.add_argument("--smoke", action="store_true", help="Real run, gpt-oss only, 5 problems, all 4 modes.")
    p.add_argument("--phase", choices=["initial", "seed-full", "all"], default="all",
                   help="Default 'all' = run all 4 modes. 'initial' = modes 1+2+3. 'seed-full' = mode 4 only.")
    p.add_argument("--models", nargs="+", default=None,
                   help="Restrict to a subset of model short names (gpt-oss-120b, gemma-4-31b-it, ...).")
    p.add_argument("--problems-subset", type=int, default=None,
                   help="Random subsample of problems (kept stable by seed=42).")
    p.add_argument("--from-run-id", default=None,
                   help="Reuse an existing run dir (resume / continue).")
    p.add_argument("--max-cost", type=float, default=None,
                   help="Hard kill switch: abort cleanly when cumulative spend exceeds N dollars.")
    args = p.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    if not args.mock:
        _probe_key(SINGLE_KEY)

    # --- Load problems ---
    problems = load_70_problems()
    if args.problems_subset and args.problems_subset < len(problems):
        rng = random.Random(42)
        keys = sorted(problems.keys())
        sampled = set(rng.sample(keys, args.problems_subset))
        problems = {k: v for k, v in problems.items() if k in sampled}
        print(f"Subsampled to {len(problems)} problems (seed=42)")

    # --- Pick models ---
    models_full = [m for m, _ in MODELS]
    if args.smoke:
        models = ["openrouter/openai/gpt-oss-120b"]
    elif args.models:
        models = [_short_to_full(s) for s in args.models]
    else:
        models = models_full

    # --- Pick modes / problem subset for smoke ---
    if args.smoke:
        modes = ALL_MODES
        # 5 problems: 3 random proofbench + 2 special-10 (pick erdos-659 and ramsey)
        rng = random.Random(0)
        proofbench_pool = [pid for pid in problems if pid.startswith(("PB-Basic", "PB-Advanced"))]
        sample = set(rng.sample(proofbench_pool, 3))
        sample.update({"erdos-659", "ramsey-hypergraphs"})
        problems = {k: v for k, v in problems.items() if k in sample}
    elif args.phase == "initial":
        modes = INITIAL_MODES
    elif args.phase == "seed-full":
        modes = SEED_FULL_MODES
    else:
        modes = ALL_MODES

    # --- Run dir ---
    run_id = args.from_run_id or _now_id()
    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")
    run_dir = RESULTS_DIR / f"{EXPERIMENT_NAME}_{run_id}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts = load_prompts()

    # --- Header ---
    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Run dir:       {run_dir}")
    print(f"Problems:      {len(problems)}")
    print(f"Models:        {[model_short(m) for m in models]}")
    print(f"Modes:         {list(modes)}")
    print(f"Judge:         {JUDGE_MODEL}")
    print(f"max_tokens:    gen={MAX_TOKENS_GEN}  judge={MAX_TOKENS_JUDGE}  ideate={MAX_TOKENS_IDEATE}")
    print(f"Workers:       outer={MAX_WORKERS}  inner(branches)={INNER_WORKERS}  keys={len(KEYS)}")
    print(f"Trial timeout: {TRIAL_TIMEOUT}s  litellm timeout: {LITELLM_TIMEOUT}s")
    if args.max_cost:
        print(f"Cost cap:      ${args.max_cost} (killswitch)")
    if args.mock:
        print("[MOCK MODE]")
    if args.smoke:
        print(f"[SMOKE MODE — {len(models)} model on {len(problems)} problems × {len(modes)} modes]")
    print()

    tracker = CostTracker(args.max_cost)

    # Validate problem set integrity for non-mock runs
    if not args.mock:
        for pid, prob in problems.items():
            if not prob["text"] or not prob["ground_truth"]:
                raise SystemExit(f"{pid}: missing text or ground_truth")

    t0 = time.time()
    execute_phase(modes, models, problems, prompts, run_dir, tracker, args.mock)
    elapsed = round(time.time() - t0, 1)
    cum_cost, in_t, out_t = tracker.snapshot()
    print(f"\nWall-clock: {elapsed}s    Cumulative: ${cum_cost:.2f}  in={in_t:,}  out={out_t:,}")
    print_summary(run_dir)


if __name__ == "__main__":
    main()
