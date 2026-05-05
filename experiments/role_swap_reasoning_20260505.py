#!/usr/bin/env python3
"""
Seed-Ideas Phase 3 — role-swap matrix between gpt-oss-120b and gemma-4-31b-it.

Mode: seed_full only (ideate(3) -> 3 parallel branches of seeded_gen -> [V<->R]x2 -> judge).

8 conditions x 70 problems = 560 trials. Per-role model assignment lets us isolate which
sub-skill (ideation / generation / verification / revision) benefits from cross-model swap.

  | # | Name           | Ideator | Generator | Verifier | Reviser |
  |---|----------------|---------|-----------|----------|---------|
  | 1 | x_ideate_oss   | oss     | gemma     | gemma    | gemma   |
  | 2 | x_ideate_gemma | gemma   | oss       | oss      | oss     |
  | 3 | x_verify_oss   | gemma   | gemma     | oss      | gemma   |
  | 4 | x_verify_gemma | oss     | oss       | gemma    | oss     |
  | 5 | x_revise_oss   | gemma   | gemma     | gemma    | oss     |
  | 6 | x_revise_gemma | oss     | oss       | oss      | gemma   |
  | 7 | random_run1    | random per (trial, role), seed=1                  |
  | 8 | random_run2    | random per (trial, role), seed=2                  |

Judge
  Primary : gemini-3-flash-preview (every branch)
  Escalate: deepseek-v4-pro re-judges any branch where:
              - problem in SPECIAL_10 (frontier set), AND
              - gemini score >= 6
            v4-pro becomes the score-of-record for that branch when triggered;
            both judge texts + scores stored.

Hardening (matches Phase 2)
  - MAX_TOKENS = 65536 everywhere
  - Per-trial atomic save + per-branch incremental save
  - Branch-level frontier_branches.jsonl appended the moment a branch finishes >=6/7
  - Single key (OPENROUTER_API_KEY_seedgen). No rotation.
  - --max-cost killswitch.

Usage
  uv run experiments/seed_full_role_swap_20260505.py --mock
  uv run experiments/seed_full_role_swap_20260505.py --smoke
  uv run experiments/seed_full_role_swap_20260505.py --max-cost 60
  uv run experiments/seed_full_role_swap_20260505.py --max-cost 60 --from-run-id <id>
  uv run experiments/seed_full_role_swap_20260505.py --max-cost 60 --conditions x_ideate_oss random_run1
"""

from __future__ import annotations

import argparse
import concurrent.futures
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

EXPERIMENT_NAME = "role_swap_reasoning_20260505"

OSS   = "openrouter/openai/gpt-oss-120b"
GEMMA = "openrouter/google/gemma-4-31b-it"

PRICE_PER_MTOKEN = {
    OSS:   0.18,
    GEMMA: 0.38,
}

# Single judge per user instruction: deepseek-v4-flash. No escalation.
JUDGE_PRIMARY        = "openrouter/deepseek/deepseek-v4-flash"
JUDGE_PRIMARY_PRICE  = 0.28

# Escalation disabled (single-judge run). Kept fields for backwards-compat in code paths.
JUDGE_ESCALATE       = None
JUDGE_ESCALATE_PRICE = 0.0
ESCALATE_GEMINI_MIN  = 999  # never triggers

# Reasoning enabled for both models in their roles; not for judge.
REASONING_MODELS = {OSS, GEMMA}
REASONING_CONFIG = {"effort": "high"}

NUM_IDEAS  = 3
ITERATIONS = 2

MAX_TOKENS_GEN     = 65536
MAX_TOKENS_VERIFY  = 65536
MAX_TOKENS_REVISE  = 65536
MAX_TOKENS_IDEATE  = 16000
MAX_TOKENS_JUDGE   = 65536

MAX_WORKERS    = 40
INNER_WORKERS  = 3

TRIAL_TIMEOUT    = 5400
LITELLM_TIMEOUT  = 1800

PASS_THRESHOLD = 6

MODE = "seed_full"

# Per-condition role assignments.
# A "static" condition has a fixed (ideator, generator, verifier, reviser) tuple.
# A "random" condition uses a seeded RNG: one random draw per (problem, role).
STATIC_CONDITIONS: list[tuple[str, dict]] = [
    ("x_ideate_oss",   {"ideator": OSS,   "generator": GEMMA, "verifier": GEMMA, "reviser": GEMMA}),
    ("x_ideate_gemma", {"ideator": GEMMA, "generator": OSS,   "verifier": OSS,   "reviser": OSS}),
    ("x_verify_oss",   {"ideator": GEMMA, "generator": GEMMA, "verifier": OSS,   "reviser": GEMMA}),
    ("x_verify_gemma", {"ideator": OSS,   "generator": OSS,   "verifier": GEMMA, "reviser": OSS}),
    ("x_revise_oss",   {"ideator": GEMMA, "generator": GEMMA, "verifier": GEMMA, "reviser": OSS}),
    ("x_revise_gemma", {"ideator": OSS,   "generator": OSS,   "verifier": OSS,   "reviser": GEMMA}),
]
RANDOM_CONDITIONS: list[tuple[str, int]] = [
    ("random_run1", 1),
    ("random_run2", 2),
]
ALL_CONDITION_NAMES = [c[0] for c in STATIC_CONDITIONS] + [c[0] for c in RANDOM_CONDITIONS]

ROLES = ("ideator", "generator", "verifier", "reviser")
RANDOM_POOL = (OSS, GEMMA)


def assign_roles(condition: str, problem_id: str) -> dict:
    """Return a {role: model} dict for the given condition + problem."""
    for name, roles in STATIC_CONDITIONS:
        if name == condition:
            return dict(roles)
    for name, seed in RANDOM_CONDITIONS:
        if name == condition:
            rng = random.Random(f"{name}|{seed}|{problem_id}")
            return {r: rng.choice(RANDOM_POOL) for r in ROLES}
    raise ValueError(f"unknown condition: {condition}")


# ============================================================================
# Paths
# ============================================================================

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ============================================================================
# Single-key auth
# ============================================================================

load_dotenv()
SINGLE_KEY_ENV = os.getenv("ROLE_SWAP_REASONING_KEY_ENV", "OPENROUTER_API_KEY_X2")
SEEDGEN_KEY = os.getenv(SINGLE_KEY_ENV)
if not SEEDGEN_KEY:
    raise SystemExit(f"{SINGLE_KEY_ENV} not set in .env")


def _probe_key(key: str) -> None:
    import requests
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=8,
        )
        if not r.ok:
            print(f"[startup] {SINGLE_KEY_ENV} probe: HTTP {r.status_code} (continuing anyway)", flush=True)
            return
        d = r.json().get("data", {}) or {}
        limit = d.get("limit")
        usage = d.get("usage", 0) or 0
        rem = (limit - usage) if limit is not None else "unlimited"
        print(f"[startup] {SINGLE_KEY_ENV}: usage={usage:.2f}/{limit}, remain={rem}", flush=True)
        if limit is not None and usage >= limit:
            raise SystemExit(f"{SINGLE_KEY_ENV} exhausted ({usage:.2f}/{limit}).")
    except SystemExit:
        raise
    except Exception as e:
        print(f"[startup] {SINGLE_KEY_ENV} probe failed ({e}); continuing anyway", flush=True)


# ============================================================================
# Mock responses
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
MOCK_VERIFY_FAIL = (
    "<ANALYSIS>Gap.</ANALYSIS>\n<CORRECT>false</CORRECT>\n"
    "<GAPS>- [Gap]: Step 2 unjustified.</GAPS>\nVERDICT: issues_found"
)
MOCK_REVISE = (
    "## Summary\n**Verdict:** Solved\n**Method sketch:** Revised mock.\n"
    "**Changes:** Fixed step 2.\n\n## Detailed Solution\nRevised mock proof.\n\\boxed{42}"
)
MOCK_JUDGE = "<points>7 out of 7</points>\nMock judge."


# ============================================================================
# call_model
# ============================================================================

def call_model(
    model: str, system: str | None, user: str, max_tokens: int,
    retries: int = 2, backoff: float = 5.0,
) -> tuple[str, dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            kwargs = dict(
                model=model, messages=messages, max_tokens=max_tokens,
                api_key=SEEDGEN_KEY, timeout=LITELLM_TIMEOUT,
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
            if (
                "402" in msg or "Insufficient credits" in msg
                or "Key limit exceeded" in msg or '"code":403' in msg
            ):
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(
                    f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1} failed: {e} "
                    f"— retry in {wait:.0f}s", flush=True,
                )
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
        self._tokens_in = 0
        self._tokens_out = 0
        self._lock = threading.Lock()
        self._aborted = False

    def add(self, cost: float, in_tok: int, out_tok: int) -> None:
        with self._lock:
            self._cost += cost
            self._tokens_in += in_tok
            self._tokens_out += out_tok
            if self.max_cost is not None and self._cost >= self.max_cost and not self._aborted:
                self._aborted = True
                print(
                    f"[{_ts()}] [KILLSWITCH] cum cost ${self._cost:.2f} >= cap ${self.max_cost:.2f}.",
                    flush=True,
                )

    def aborted(self) -> bool:
        with self._lock:
            return self._aborted

    def snapshot(self) -> tuple[float, int, int]:
        with self._lock:
            return self._cost, self._tokens_in, self._tokens_out


def cost_for(model: str, total_tokens: int) -> float:
    if model == JUDGE_PRIMARY:
        p = JUDGE_PRIMARY_PRICE
    elif model == JUDGE_ESCALATE:
        p = JUDGE_ESCALATE_PRICE
    else:
        p = PRICE_PER_MTOKEN.get(model, 0.0)
    return (p or 0.0) * total_tokens / 1_000_000


# ============================================================================
# Pipeline atomic calls
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
        "response_text": response_text,
    })
    tracker.add(cost, usage["prompt_tokens"], usage["completion_tokens"])


def do_ideate(model, problem_text, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    prompt_filled = (
        prompts["ideator"]
        .replace("{problem}", problem_text)
        .replace("{num_ideas}", str(NUM_IDEAS))
    )
    if mock:
        ideas = MOCK_IDEAS[:NUM_IDEAS]
        return ideas, "MOCK_IDEATE", {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}
    text, usage = call_model(model, "", prompt_filled, MAX_TOKENS_IDEATE)
    _record_call(calls, "ideate", model, usage, time.time() - t0, tracker, response_text=text)
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
    _record_call(calls, "seeded_generate", model, usage, time.time() - t0, tracker, response_text=text)
    return text, usage


def do_verify(model, problem_text, solution, calls, tracker, mock=False, mock_pass=False, prompts=None):
    t0 = time.time()
    sys_part, _, content_part = prompts["verifier"].partition("\n**PROBLEM:**\n")
    if not _:
        sys_part = ""
        content_part = prompts["verifier"]
    else:
        content_part = "**PROBLEM:**\n" + content_part
    user = content_part.replace("{problem}", problem_text).replace("{solution}", solution)
    if mock:
        return (
            (MOCK_VERIFY_PASS if mock_pass else MOCK_VERIFY_FAIL),
            {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230},
        )
    text, usage = call_model(model, sys_part, user, MAX_TOKENS_VERIFY)
    _record_call(calls, "verify", model, usage, time.time() - t0, tracker, response_text=text)
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
    _record_call(calls, "revise", model, usage, time.time() - t0, tracker, response_text=text)
    return text, usage


def do_judge(judge_model, problem_text, candidate, ground_truth, calls, tracker, mock=False, prompts=None,
             kind="judge"):
    t0 = time.time()
    if mock:
        return MOCK_JUDGE, 7, {"prompt_tokens": 400, "completion_tokens": 30, "total_tokens": 430}
    user = (prompts["judge_gt"]
            .replace("{problem}", problem_text)
            .replace("{ground_truth}", ground_truth)
            .replace("{candidate}", candidate))
    text, usage = call_model(judge_model, "", user, MAX_TOKENS_JUDGE)
    _record_call(calls, kind, judge_model, usage, time.time() - t0, tracker, response_text=text)
    score = parse_gt_score(text)
    return text, score, usage


def parse_gt_score(verdict: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m: return int(m.group(1))
    return 0


# ============================================================================
# seed_full runner with per-role models + judge escalation
# ============================================================================

def run_full_branch_per_role(
    roles, problem_text, ground_truth, initial_solution, calls, tracker, mock, prompts,
):
    """generate (already done) -> [verify(verifier-model) -> revise(reviser-model)] x ITERATIONS -> judge(s)."""
    solution = initial_solution
    loop_log = []
    stopped_early = False
    for i in range(ITERATIONS):
        critique, _u = do_verify(
            roles["verifier"], problem_text, solution, calls, tracker,
            mock=mock, mock_pass=(i == 1 and mock), prompts=prompts,
        )
        if "VERDICT: correct" in critique:
            stopped_early = True
            loop_log.append({
                "iteration": i + 1, "verdict": "correct",
                "verifier_model": roles["verifier"],
                "critique": critique, "solution": solution,
            })
            break
        new_solution, _u = do_revise(
            roles["reviser"], problem_text, solution, critique, calls, tracker,
            mock=mock, prompts=prompts,
        )
        loop_log.append({
            "iteration": i + 1, "verdict": "issues_found",
            "verifier_model": roles["verifier"],
            "reviser_model":  roles["reviser"],
            "critique": critique,
            "solution_before": solution,
            "solution_after": new_solution,
        })
        solution = new_solution

    # Primary judge.
    g_text, g_score, _u = do_judge(
        JUDGE_PRIMARY, problem_text, solution, ground_truth, calls, tracker,
        mock=mock, prompts=prompts, kind="judge_primary",
    )
    judge_record = {
        "primary_judge":    JUDGE_PRIMARY,
        "primary_score":    g_score,
        "primary_verdict":  g_text,
        "escalated":        False,
        "escalate_judge":   None,
        "escalate_score":   None,
        "escalate_verdict": None,
    }
    return solution, g_text, g_score, loop_log, stopped_early, judge_record


def run_seed_full_with_roles(
    roles, problem, calls, tracker, mock, prompts,
    branch_save, frontier_save,
):
    """ideate(ideator-model) -> 3 parallel branches -> per-branch judge (+ escalation if special)."""
    ideas, ideate_text, _u = do_ideate(
        roles["ideator"], problem["text"], calls, tracker, mock=mock, prompts=prompts,
    )

    is_special = problem["id"] in SPECIAL_10
    branches: list[dict] = [None] * len(ideas)  # type: ignore
    branches_lock = threading.Lock()

    def _branch(idx_idea):
        idx, idea = idx_idea
        b_calls: list = []
        try:
            sol, _ = do_seeded_generate(
                roles["generator"], problem["text"], idea, b_calls, tracker,
                mock=mock, prompts=prompts,
            )
            final_sol, primary_verdict, primary_score, loop_log, stopped_early, jr = (
                run_full_branch_per_role(
                    roles, problem["text"], problem["ground_truth"], sol,
                    b_calls, tracker, mock, prompts,
                )
            )

            # Judge escalation: if SPECIAL_10 and gemini score >= ESCALATE_GEMINI_MIN,
            # additionally judge with v4-pro and use that as score-of-record.
            score_of_record = primary_score
            verdict_of_record = primary_verdict
            if (
                not mock
                and is_special
                and primary_score is not None
                and primary_score >= ESCALATE_GEMINI_MIN
            ):
                e_text, e_score, _u = do_judge(
                    JUDGE_ESCALATE, problem["text"], final_sol, problem["ground_truth"],
                    b_calls, tracker, mock=mock, prompts=prompts, kind="judge_escalate",
                )
                jr.update({
                    "escalated":        True,
                    "escalate_judge":   JUDGE_ESCALATE,
                    "escalate_score":   e_score,
                    "escalate_verdict": e_text,
                })
                score_of_record = e_score
                verdict_of_record = e_text

            branch = {
                "idea_idx":         idx,
                "idea":             idea,
                "initial_solution": sol,
                "final_solution":   final_sol,
                "verdict":          verdict_of_record,
                "score":            score_of_record,
                "loop_log":         loop_log,
                "stopped_early":    stopped_early,
                "judge":            jr,
                "calls":            b_calls,
                "completed_at":     datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            branch = {
                "idea_idx":     idx,
                "idea":         idea,
                "error":        str(e),
                "calls":        b_calls,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        try:
            branch_save(idx, branch)
        except Exception as save_err:
            print(f"[{_ts()}] WARN branch_save failed (idx={idx}): {save_err}", flush=True)
        if (
            is_special
            and branch.get("score") is not None
            and branch["score"] >= PASS_THRESHOLD
        ):
            try:
                frontier_save(branch)
            except Exception as fr_err:
                print(f"[{_ts()}] WARN frontier_save failed: {fr_err}", flush=True)
        with branches_lock:
            branches[idx] = branch
        return branch

    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        list(ex.map(_branch, list(enumerate(ideas))))

    valid = [b for b in branches if b is not None]
    for b in valid:
        calls.extend(b.get("calls", []))

    scored = [b for b in valid if b.get("score") is not None]
    if scored:
        best = max(scored, key=lambda b: b["score"])
        return {
            "best_score":    best["score"],
            "best_solution": best["final_solution"],
            "best_verdict":  best["verdict"],
            "branches":      valid,
            "mode_extras":   {
                "num_ideas": NUM_IDEAS, "iterations": ITERATIONS,
                "ideas": ideas, "ideate_response": ideate_text,
                "roles": roles,
            },
        }
    return {
        "best_score":    None,
        "best_solution": None,
        "best_verdict":  None,
        "branches":      valid,
        "mode_extras":   {
            "num_ideas": NUM_IDEAS, "iterations": ITERATIONS,
            "ideas": ideas, "ideate_response": ideate_text,
            "roles": roles,
        },
    }


# ============================================================================
# Trial wrapper + per-trial save
# ============================================================================

def model_short(model: str) -> str:
    return model.split("/")[-1]


def trial_path(run_dir: Path, condition: str, pid: str) -> Path:
    return run_dir / "trials" / condition / f"{pid}.json"


def branch_dir(run_dir: Path, condition: str, pid: str) -> Path:
    return run_dir / "branches" / condition / pid


def save_branch_inflight(run_dir: Path, condition: str, pid: str, idx: int, branch: dict) -> None:
    d = branch_dir(run_dir, condition, pid)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"branch_{idx}.json"
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(branch, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def save_trial(
    run_dir: Path, manifest_lock: threading.Lock, frontier_lock: threading.Lock, trial: dict,
) -> None:
    p = trial_path(run_dir, trial["condition"], trial["problem_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trial, f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    summary = {
        "ts":          trial["completed_at"],
        "mode":        trial["mode"],
        "condition":   trial["condition"],
        "problem_id":  trial["problem_id"],
        "score":       trial.get("score"),
        "passed":      trial.get("passed"),
        "elapsed_s":   trial.get("elapsed_s"),
        "cost_usd":    trial.get("cost_usd"),
        "n_calls":     len(trial.get("calls", [])),
        "error":       trial.get("error"),
        "roles":       trial.get("mode_extras", {}).get("roles"),
        "n_escalated": sum(1 for b in trial.get("branches", []) if b.get("judge", {}).get("escalated")),
    }
    with manifest_lock:
        with open(run_dir / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")
    if (trial["problem_id"] in SPECIAL_10
            and trial.get("score") is not None
            and trial["score"] >= PASS_THRESHOLD
            and not trial.get("error")):
        with frontier_lock:
            with open(run_dir / "frontier_passes.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts":         trial["completed_at"],
                    "mode":       trial["mode"],
                    "condition":  trial["condition"],
                    "problem_id": trial["problem_id"],
                    "score":      trial["score"],
                    "solution":   trial["best_solution"],
                    "verdict":    trial["best_verdict"],
                }) + "\n")


def append_frontier_branch(
    run_dir: Path, frontier_lock: threading.Lock, condition: str, pid: str, branch: dict,
) -> None:
    with frontier_lock:
        with open(run_dir / "frontier_branches.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts":               branch["completed_at"],
                "mode":             MODE,
                "condition":        condition,
                "problem_id":       pid,
                "idea_idx":         branch.get("idea_idx"),
                "idea":             branch.get("idea"),
                "score":            branch["score"],
                "primary_score":    branch.get("judge", {}).get("primary_score"),
                "escalated":        branch.get("judge", {}).get("escalated"),
                "escalate_score":   branch.get("judge", {}).get("escalate_score"),
                "solution":         branch.get("final_solution"),
                "verdict":          branch.get("verdict"),
            }) + "\n")


def run_trial(
    condition: str, problem: dict, problem_id: str,
    prompts: dict, run_dir: Path, manifest_lock: threading.Lock,
    frontier_lock: threading.Lock, tracker: CostTracker, mock: bool,
) -> dict:
    pid = problem_id
    roles = assign_roles(condition, pid)
    tag = f"[{_ts()}] [{condition}|{pid}]"
    print(f"{tag} start  roles={ {k: model_short(v) for k, v in roles.items()} }", flush=True)
    t0 = time.time()
    calls: list = []

    def _branch_save(idx: int, branch: dict) -> None:
        save_branch_inflight(run_dir, condition, pid, idx, branch)

    def _frontier_save(branch: dict) -> None:
        append_frontier_branch(run_dir, frontier_lock, condition, pid, branch)

    trial: dict = {
        "experiment":  EXPERIMENT_NAME,
        "mode":        MODE,
        "condition":   condition,
        "roles":       roles,
        "problem_id":  pid,
        "category":    problem.get("category", ""),
        "level":       problem.get("level", ""),
        "source":      problem.get("source", ""),
        "is_special":  pid in SPECIAL_10,
        "started_at":  datetime.now(timezone.utc).isoformat(),
    }

    try:
        prob_for_runner = dict(problem)
        prob_for_runner["id"] = pid
        out = run_seed_full_with_roles(
            roles, prob_for_runner, calls, tracker, mock, prompts,
            branch_save=_branch_save, frontier_save=_frontier_save,
        )
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
        n_esc = sum(1 for b in out["branches"] if b.get("judge", {}).get("escalated"))
        print(f"{tag} done  score={score}/7  ${cost:.4f}  {elapsed}s  esc={n_esc}", flush=True)
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

def already_done(run_dir: Path, condition: str, pid: str) -> bool:
    p = trial_path(run_dir, condition, pid)
    if not p.exists():
        return False
    try:
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        return not t.get("error") and t.get("score") is not None
    except Exception:
        return False


def execute(
    conditions: list[str], problems: dict, prompts: dict,
    run_dir: Path, tracker: CostTracker, mock: bool,
) -> list[dict]:
    pids = sorted(problems.keys())
    trials = [(pid, c) for pid in pids for c in conditions]
    pending = [(pid, c) for (pid, c) in trials if not already_done(run_dir, c, pid)]
    skipped = len(trials) - len(pending)

    print(f"\n=== Role-swap | conditions={conditions} ===", flush=True)
    print(
        f"Total trials: {len(trials)}  pending: {len(pending)}  "
        f"skipped (already done): {skipped}",
        flush=True,
    )
    print(f"max_workers={MAX_WORKERS}, inner={INNER_WORKERS}, max_cost=${tracker.max_cost}\n", flush=True)

    manifest_lock = threading.Lock()
    frontier_lock = threading.Lock()
    results = []

    def _submit(pid, c):
        return run_trial(
            c, problems[pid], pid, prompts, run_dir, manifest_lock, frontier_lock, tracker, mock,
        )

    completed = 0
    last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for pid, c in pending:
            if tracker.aborted():
                print(
                    f"[{_ts()}] [KILLSWITCH] not submitting remaining "
                    f"{len(pending)-completed-len(futs)} trials.",
                    flush=True,
                )
                break
            futs[ex.submit(_submit, pid, c)] = (pid, c)

        for fut in concurrent.futures.as_completed(
            futs, timeout=TRIAL_TIMEOUT * max(len(pending), 1),
        ):
            pid, c = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                print(f"[{_ts()}] FAILED [{c}|{pid}]: {e}", flush=True)
                results.append({"problem_id": pid, "condition": c, "error": str(e)})
            now = time.time()
            if completed % 5 == 0 or now - last_print > 60:
                cum_cost, in_t, out_t = tracker.snapshot()
                print(
                    f"[{_ts()}] Progress: {completed}/{len(pending)}  cum=${cum_cost:.2f}  "
                    f"in={in_t:,} out={out_t:,}",
                    flush=True,
                )
                last_print = now
    return results


# ============================================================================
# Reporting
# ============================================================================

def aggregate(run_dir: Path) -> list[dict]:
    trials = []
    trials_dir = run_dir / "trials"
    for p in sorted(trials_dir.rglob("*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                trials.append(json.load(f))
        except Exception:
            pass
    return trials


def print_summary(run_dir: Path) -> None:
    trials = aggregate(run_dir)
    if not trials:
        print(f"No trials in {run_dir}")
        return
    print(f"\n{'='*100}")
    print(f"ROLE-SWAP — run_dir = {run_dir.name}")
    print(f"{'='*100}\n")
    cost_total = sum(t.get("cost_usd", 0) or 0 for t in trials)
    n_esc = sum(
        1 for t in trials for b in t.get("branches", [])
        if b.get("judge", {}).get("escalated")
    )
    print(f"Total trials: {len(trials)}    Total cost: ${cost_total:.2f}    Escalated branches: {n_esc}\n")

    by_cond: dict[str, list[dict]] = {}
    for t in trials:
        by_cond.setdefault(t["condition"], []).append(t)

    print(f"  {'Condition':<20}  {'n':>3}  {'mean':>5}  {'std':>4}  {'pass':>6}  {'$/run':>8}  {'$ tot':>7}")
    for c in ALL_CONDITION_NAMES:
        rs = by_cond.get(c, [])
        if not rs: continue
        valid = [r for r in rs if r.get("score") is not None and not r.get("error")]
        scores = [r["score"] for r in valid]
        passes = sum(1 for r in valid if r.get("passed"))
        costs = [r.get("cost_usd", 0) or 0 for r in rs]
        mean_s = float(np.mean(scores)) if scores else 0.0
        std_s = float(np.std(scores)) if len(scores) > 1 else 0.0
        print(
            f"  {c:<20}  {len(valid):>3}  {mean_s:>5.2f}  {std_s:>4.2f}  {passes}/{len(valid):<3}  "
            f"${np.mean(costs):.4f}  ${sum(costs):.3f}",
        )
    print()


# ============================================================================
# Main / CLI
# ============================================================================

def load_prompts() -> dict:
    return {
        "generator_seeded": load_prompt("generator_seeded.md"),
        "ideator":          load_prompt("ideator.md"),
        "verifier":         load_prompt("verifier.md"),
        "reviser":          load_prompt("reviser.md"),
        "judge_gt":         load_prompt("judge_gt.md"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock",  action="store_true")
    p.add_argument("--smoke", action="store_true",
                   help="Real API: 3 problems (incl. erdos-654 to exercise escalation), 1 condition.")
    p.add_argument("--conditions", nargs="+", default=None,
                   help=f"Subset of conditions: {ALL_CONDITION_NAMES}")
    p.add_argument("--problems-subset", type=int, default=None)
    p.add_argument("--from-run-id", default=None)
    p.add_argument("--max-cost", type=float, default=None)
    args = p.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    if not args.mock:
        _probe_key(SEEDGEN_KEY)

    problems = load_70_problems()
    if args.problems_subset and args.problems_subset < len(problems):
        rng = random.Random(42)
        keys = sorted(problems.keys())
        sampled = set(rng.sample(keys, args.problems_subset))
        problems = {k: v for k, v in problems.items() if k in sampled}
        print(f"Subsampled to {len(problems)} problems (seed=42)")

    if args.conditions:
        unknown = [c for c in args.conditions if c not in ALL_CONDITION_NAMES]
        if unknown:
            raise SystemExit(f"unknown conditions: {unknown}. Valid: {ALL_CONDITION_NAMES}")
        conditions = args.conditions
    else:
        conditions = list(ALL_CONDITION_NAMES)

    if args.smoke:
        conditions = ["x_ideate_oss"]
        sample = {"PB-Basic-002", "erdos-654", "first-proof-10-official"}
        problems = {k: v for k, v in problems.items() if k in sample}

    run_id = args.from_run_id or _now_id()
    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")
    run_dir = RESULTS_DIR / f"{EXPERIMENT_NAME}_{run_id}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts = load_prompts()

    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Run dir:       {run_dir}")
    print(f"Problems:      {len(problems)}")
    print(f"Conditions:    {conditions}")
    print(f"Mode:          {MODE}")
    print(f"Primary judge: {JUDGE_PRIMARY}")
    print(f"Escalate:      DISABLED (single judge: v4-flash)")
    print(f"max_tokens:    gen={MAX_TOKENS_GEN}  judge={MAX_TOKENS_JUDGE}  ideate={MAX_TOKENS_IDEATE}")
    print(f"Workers:       outer={MAX_WORKERS}  inner(branches)={INNER_WORKERS}")
    print(f"Trial timeout: {TRIAL_TIMEOUT}s  litellm timeout: {LITELLM_TIMEOUT}s")
    print(f"Key:           {SINGLE_KEY_ENV} (single, no rotation)")
    if args.max_cost:
        print(f"Cost cap:      ${args.max_cost} (killswitch)")
    if args.mock:  print("[MOCK MODE]")
    if args.smoke: print(f"[SMOKE MODE]")
    print()

    tracker = CostTracker(args.max_cost)

    if not args.mock:
        for pid, prob in problems.items():
            if not prob["text"] or not prob["ground_truth"]:
                raise SystemExit(f"{pid}: missing text or ground_truth")

    t0 = time.time()
    execute(conditions, problems, prompts, run_dir, tracker, args.mock)
    elapsed = round(time.time() - t0, 1)
    cum_cost, in_t, out_t = tracker.snapshot()
    print(f"\nWall-clock: {elapsed}s    Cumulative: ${cum_cost:.2f}  in={in_t:,}  out={out_t:,}")
    print_summary(run_dir)


if __name__ == "__main__":
    main()
