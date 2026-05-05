#!/usr/bin/env python3
"""
Seed-Ideas Phase 3 — seed_full only, deepseek-v4-flash, gemini-3-flash judge.

Same mode + hardening as Phase 2; only the model under test changes.

Problem ordering is priority-loaded from
`experiments/results/v4flash_priority_20260505.json` so that under killswitch,
the most informative trials run first:
  Tier 1 — special-10 ever-solved (4 problems)
  Tier 2 — problems where v4-flash struggled but other models solved (5 problems)
  Tier 3 — rest (61 problems)

Usage
  uv run experiments/seed_full_v4flash_phase3_20260505.py --mock
  uv run experiments/seed_full_v4flash_phase3_20260505.py --smoke
  uv run experiments/seed_full_v4flash_phase3_20260505.py --max-cost 40
  uv run experiments/seed_full_v4flash_phase3_20260505.py --max-cost 40 --from-run-id <id>
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

EXPERIMENT_NAME = "seed_full_v4flash_phase3_20260505"

# (model_id, $/M tokens) — Phase 3 is single-model: deepseek-v4-flash.
MODELS = [
    ("openrouter/deepseek/deepseek-v4-flash", 0.28),
]

PRIORITY_FILE = Path(__file__).parent / "results" / "v4flash_priority_20260505.json"
PRICE_PER_MTOKEN = {m: p for m, p in MODELS}

# Judge: gemini-3-flash-preview (matches Phase 1 regrade judge for cross-comparability).
JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"
JUDGE_PRICE = 3.00   # $/M tokens

NUM_IDEAS       = 3
ITERATIONS      = 2          # 1 generate + 2 revisions per branch (inside the V<->R loop)

# Token budgets — generously sized so reasoning models can output their full trace.
MAX_TOKENS_GEN     = 65536
MAX_TOKENS_VERIFY  = 65536
MAX_TOKENS_REVISE  = 65536
MAX_TOKENS_IDEATE  = 16000
MAX_TOKENS_JUDGE   = 65536

# Concurrency. Single API key + cheap models -> we can push outer pool fairly hard.
# Outer = trials in flight. Inner = 3 branches per trial run truly in parallel.
MAX_WORKERS    = 40
INNER_WORKERS  = 3

TRIAL_TIMEOUT    = 5400      # 90 min per trial
LITELLM_TIMEOUT  = 1800      # 30 min per single API call

PASS_THRESHOLD = 6           # >=6/7 = passed (used for special-10 frontier-pass logging)

MODE = "seed_full"

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
# Single-key auth (per user requirement: ONLY OPENROUTER_API_KEY_seedgen)
# ============================================================================

load_dotenv()
SEEDGEN_KEY = os.getenv("OPENROUTER_API_KEY_seedgen")
if not SEEDGEN_KEY:
    raise SystemExit(
        "OPENROUTER_API_KEY_seedgen not set in .env. "
        "Add a line like 'OPENROUTER_API_KEY_seedgen=sk-or-v1-...' before running."
    )


def _probe_key(key: str) -> None:
    """Sanity check: hit /key endpoint to make sure the key is live before we burn time."""
    import requests
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=8,
        )
        if not r.ok:
            print(f"[startup] seedgen key probe: HTTP {r.status_code} (continuing anyway)", flush=True)
            return
        d = r.json().get("data", {}) or {}
        limit = d.get("limit")
        usage = d.get("usage", 0) or 0
        rem = (limit - usage) if limit is not None else "unlimited"
        print(f"[startup] seedgen key: usage={usage:.2f}/{limit}, remain={rem}", flush=True)
        if limit is not None and usage >= limit:
            raise SystemExit(
                f"seedgen key already exhausted ({usage:.2f}/{limit}). Top up before running."
            )
    except SystemExit:
        raise
    except Exception as e:
        print(f"[startup] seedgen key probe failed ({e}); continuing anyway", flush=True)


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
# call_model — single LLM call using the seedgen key only
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
        try:
            resp = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                api_key=SEEDGEN_KEY,
                timeout=LITELLM_TIMEOUT,
            )
            content = resp.choices[0].message.content  # type: ignore
            if content is None:
                content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
            if content is None:
                raise ValueError(f"Model {model} returned None content")
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
                "402" in msg
                or "Insufficient credits" in msg
                or "Key limit exceeded" in msg
                or '"code":403' in msg
            ):
                raise   # don't retry credit/key-limit failures
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(
                    f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1} failed: {e} "
                    f"— retry in {wait:.0f}s",
                    flush=True,
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
                    f"[{_ts()}] [KILLSWITCH] cum cost ${self._cost:.2f} >= cap ${self.max_cost:.2f}. "
                    f"No new trials will start; in-flight trials will finish.",
                    flush=True,
                )

    def aborted(self) -> bool:
        with self._lock:
            return self._aborted

    def snapshot(self) -> tuple[float, int, int]:
        with self._lock:
            return self._cost, self._tokens_in, self._tokens_out


def cost_for(model: str, total_tokens: int) -> float:
    if model == JUDGE_MODEL:
        p = JUDGE_PRICE
    else:
        p = PRICE_PER_MTOKEN.get(model, 0.0)
    return (p or 0.0) * total_tokens / 1_000_000


# ============================================================================
# Atomic pipeline calls (each tracks its own cost + appends to a calls list)
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
        "response_text": response_text,   # ALWAYS save full text — never truncate
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


def do_judge(problem_text, candidate, ground_truth, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    if mock:
        return MOCK_JUDGE, 7, {"prompt_tokens": 400, "completion_tokens": 30, "total_tokens": 430}
    user = (prompts["judge_gt"]
            .replace("{problem}", problem_text)
            .replace("{ground_truth}", ground_truth)
            .replace("{candidate}", candidate))
    text, usage = call_model(JUDGE_MODEL, "", user, MAX_TOKENS_JUDGE)
    _record_call(calls, "judge", JUDGE_MODEL, usage, time.time() - t0, tracker, response_text=text)
    score = parse_gt_score(text)
    return text, score, usage


def parse_gt_score(verdict: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m: return int(m.group(1))
    return 0


# ============================================================================
# Mode runner — seed_full
# ============================================================================

def run_full_branch(model, problem_text, ground_truth, initial_solution, calls, tracker, mock, prompts):
    """generate (already done) -> [verify -> revise]*ITERATIONS -> judge."""
    solution = initial_solution
    loop_log = []
    stopped_early = False
    for i in range(ITERATIONS):
        critique, _u = do_verify(
            model, problem_text, solution, calls, tracker,
            mock=mock, mock_pass=(i == 1 and mock), prompts=prompts,
        )
        if "VERDICT: correct" in critique:
            stopped_early = True
            loop_log.append({
                "iteration": i + 1, "verdict": "correct",
                "critique": critique, "solution": solution,
            })
            break
        new_solution, _u = do_revise(model, problem_text, solution, critique, calls, tracker,
                                     mock=mock, prompts=prompts)
        loop_log.append({
            "iteration": i + 1, "verdict": "issues_found",
            "critique": critique, "solution_before": solution,
            "solution_after": new_solution,
        })
        solution = new_solution
    verdict, score, _u = do_judge(problem_text, solution, ground_truth, calls, tracker,
                                  mock=mock, prompts=prompts)
    return solution, verdict, score, loop_log, stopped_early


def run_mode_seed_full(
    model, problem, calls, tracker, mock, prompts,
    branch_save: callable,            # takes (idx, branch_dict) -> None; called immediately each branch finishes
    frontier_save: callable,          # takes branch_dict -> None when score >= PASS_THRESHOLD on a special-10
):
    """ideate(3) -> 3 parallel branches: seeded_gen -> V<->R x 2 -> judge -> save."""
    ideas, ideate_text, _u = do_ideate(model, problem["text"], calls, tracker,
                                       mock=mock, prompts=prompts)

    branches: list[dict] = [None] * len(ideas)  # type: ignore
    branches_lock = threading.Lock()

    def _branch(idx_idea):
        idx, idea = idx_idea
        b_calls: list = []
        try:
            sol, _ = do_seeded_generate(
                model, problem["text"], idea, b_calls, tracker, mock=mock, prompts=prompts,
            )
            final_sol, verdict, score, loop_log, stopped_early = run_full_branch(
                model, problem["text"], problem["ground_truth"], sol,
                b_calls, tracker, mock, prompts,
            )
            branch = {
                "idea_idx":         idx,
                "idea":             idea,
                "initial_solution": sol,
                "final_solution":   final_sol,
                "verdict":          verdict,
                "score":            score,
                "loop_log":         loop_log,
                "stopped_early":    stopped_early,
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
        # Per-branch save: keeps work safe even if the trial dies later.
        try:
            branch_save(idx, branch)
        except Exception as save_err:
            print(f"[{_ts()}] WARN branch_save failed (idx={idx}): {save_err}", flush=True)
        # Frontier-pass save: highest priority; never lose a special-10 solve.
        if (problem["id"] in SPECIAL_10
                and branch.get("score") is not None
                and branch["score"] >= PASS_THRESHOLD):
            try:
                frontier_save(branch)
            except Exception as fr_err:
                print(f"[{_ts()}] WARN frontier_save failed: {fr_err}", flush=True)
        with branches_lock:
            branches[idx] = branch
        return branch

    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        list(ex.map(_branch, list(enumerate(ideas))))

    # Pull branch calls into the outer call log for trial-level cost accounting.
    valid_branches = [b for b in branches if b is not None]
    for b in valid_branches:
        calls.extend(b.get("calls", []))

    scored = [b for b in valid_branches if b.get("score") is not None]
    if scored:
        best = max(scored, key=lambda b: b["score"])
        return {
            "best_score":    best["score"],
            "best_solution": best["final_solution"],
            "best_verdict":  best["verdict"],
            "branches":      valid_branches,
            "mode_extras":   {
                "num_ideas": NUM_IDEAS, "iterations": ITERATIONS,
                "ideas": ideas, "ideate_response": ideate_text,
            },
        }
    # All branches errored.
    return {
        "best_score":    None,
        "best_solution": None,
        "best_verdict":  None,
        "branches":      valid_branches,
        "mode_extras":   {
            "num_ideas": NUM_IDEAS, "iterations": ITERATIONS,
            "ideas": ideas, "ideate_response": ideate_text,
        },
    }


# ============================================================================
# Trial wrapper + per-trial save
# ============================================================================

def model_short(model: str) -> str:
    return model.split("/")[-1]


def trial_path(run_dir: Path, model: str, pid: str) -> Path:
    return run_dir / MODE / model_short(model) / f"{pid}.json"


def branch_dir(run_dir: Path, model: str, pid: str) -> Path:
    return run_dir / "branches" / model_short(model) / pid


def save_branch_inflight(run_dir: Path, model: str, pid: str, idx: int, branch: dict) -> None:
    d = branch_dir(run_dir, model, pid)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"branch_{idx}.json"
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(branch, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def save_trial(
    run_dir: Path, manifest_lock: threading.Lock, frontier_lock: threading.Lock, trial: dict,
) -> None:
    p = trial_path(run_dir, trial["model"], trial["problem_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trial, f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    summary = {
        "ts":         trial["completed_at"],
        "mode":       trial["mode"],
        "model":      trial["model"],
        "problem_id": trial["problem_id"],
        "score":      trial.get("score"),
        "passed":     trial.get("passed"),
        "elapsed_s":  trial.get("elapsed_s"),
        "cost_usd":   trial.get("cost_usd"),
        "n_calls":    len(trial.get("calls", [])),
        "error":      trial.get("error"),
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
                    "model":      trial["model"],
                    "problem_id": trial["problem_id"],
                    "score":      trial["score"],
                    "solution":   trial["best_solution"],
                    "verdict":    trial["best_verdict"],
                }) + "\n")


def append_frontier_branch(
    run_dir: Path, frontier_lock: threading.Lock, model: str, pid: str, branch: dict,
) -> None:
    """Appends a per-branch frontier hit immediately, before the trial finishes."""
    with frontier_lock:
        with open(run_dir / "frontier_branches.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts":         branch["completed_at"],
                "mode":       MODE,
                "model":      model,
                "problem_id": pid,
                "idea_idx":   branch.get("idea_idx"),
                "idea":       branch.get("idea"),
                "score":      branch["score"],
                "solution":   branch.get("final_solution"),
                "verdict":    branch.get("verdict"),
            }) + "\n")


def run_trial(
    model: str, problem: dict, problem_id: str,
    prompts: dict, run_dir: Path, manifest_lock: threading.Lock,
    frontier_lock: threading.Lock, tracker: CostTracker, mock: bool,
) -> dict:
    pid = problem_id
    ms = model_short(model)
    tag = f"[{_ts()}] [{MODE}|{ms}|{pid}]"
    print(f"{tag} start", flush=True)
    t0 = time.time()
    calls: list = []

    # Bind model+pid into save closures for the branch hooks.
    def _branch_save(idx: int, branch: dict) -> None:
        save_branch_inflight(run_dir, model, pid, idx, branch)

    def _frontier_save(branch: dict) -> None:
        append_frontier_branch(run_dir, frontier_lock, model, pid, branch)

    trial: dict = {
        "experiment":  EXPERIMENT_NAME,
        "mode":        MODE,
        "model":       model,
        "problem_id":  pid,
        "category":    problem.get("category", ""),
        "level":       problem.get("level", ""),
        "source":      problem.get("source", ""),
        "is_special":  pid in SPECIAL_10,
        "started_at":  datetime.now(timezone.utc).isoformat(),
    }

    try:
        # Inject pid into problem dict for SPECIAL_10 check inside the runner.
        prob_for_runner = dict(problem)
        prob_for_runner["id"] = pid
        out = run_mode_seed_full(
            model, prob_for_runner, calls, tracker, mock, prompts,
            branch_save=_branch_save,
            frontier_save=_frontier_save,
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

def already_done(run_dir: Path, model: str, pid: str) -> bool:
    p = trial_path(run_dir, model, pid)
    if not p.exists():
        return False
    try:
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        return not t.get("error") and t.get("score") is not None
    except Exception:
        return False


def execute_phase(
    models: list[str], problems: dict, prompts: dict,
    run_dir: Path, tracker: CostTracker, mock: bool,
    pid_order: list[str] | None = None,
) -> list[dict]:
    # Honor caller-provided priority ordering when present, otherwise sort.
    if pid_order:
        seen = set()
        pids = [p for p in pid_order if p in problems and not (p in seen or seen.add(p))]
        # Append any problems missing from the order (defensive).
        for p in sorted(problems):
            if p not in seen:
                pids.append(p)
    else:
        pids = sorted(problems.keys())
    trials = [(pid, m) for pid in pids for m in models]
    pending = [(pid, m) for (pid, m) in trials if not already_done(run_dir, m, pid)]
    skipped = len(trials) - len(pending)

    print(f"\n=== Phase 3 seed_full | models={[model_short(m) for m in models]} ===", flush=True)
    print(
        f"Total trials: {len(trials)}  pending: {len(pending)}  "
        f"skipped (already done): {skipped}",
        flush=True,
    )
    print(f"max_workers={MAX_WORKERS}, inner={INNER_WORKERS}, max_cost=${tracker.max_cost}\n", flush=True)

    manifest_lock = threading.Lock()
    frontier_lock = threading.Lock()

    results = []

    def _submit(pid, m):
        return run_trial(
            m, problems[pid], pid, prompts, run_dir, manifest_lock, frontier_lock, tracker, mock,
        )

    completed = 0
    last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for pid, m in pending:
            if tracker.aborted():
                print(
                    f"[{_ts()}] [KILLSWITCH] not submitting remaining "
                    f"{len(pending)-completed-len(futs)} trials.",
                    flush=True,
                )
                break
            futs[ex.submit(_submit, pid, m)] = (pid, m)

        for fut in concurrent.futures.as_completed(
            futs, timeout=TRIAL_TIMEOUT * max(len(pending), 1),
        ):
            pid, m = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                ms = model_short(m)
                print(f"[{_ts()}] FAILED [{MODE}|{ms}|{pid}]: {e}", flush=True)
                results.append({"problem_id": pid, "model": m, "mode": MODE, "error": str(e)})
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

def aggregate(run_dir: Path) -> dict:
    trials = []
    for p in sorted(run_dir.rglob("*.json")):
        if p.parent == run_dir or "branches" in p.parts:
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
    print(f"SEED-IDEAS PHASE 2 (seed_full) — run_dir = {run_dir.name}")
    print(f"{'='*100}\n")

    by_model: dict[str, list[dict]] = {}
    for t in trials:
        by_model.setdefault(t["model"], []).append(t)

    cost_total = sum(t.get("cost_usd", 0) or 0 for t in trials)
    print(f"Total trials: {len(trials)}    Total cost: ${cost_total:.2f}\n")
    print(f"-- {MODE} --")
    print(f"  {'Model':<30}  {'n':>3}  {'mean':>5}  {'pass':>6}  {'$/run':>8}  {'$ tot':>7}")
    for model in [m for m, _ in MODELS]:
        rs = by_model.get(model, [])
        if not rs: continue
        valid = [r for r in rs if r.get("score") is not None and not r.get("error")]
        scores = [r["score"] for r in valid]
        passes = sum(1 for r in valid if r.get("passed"))
        costs = [r.get("cost_usd", 0) or 0 for r in rs]
        ms = model_short(model)
        mean_s = float(np.mean(scores)) if scores else 0.0
        print(
            f"  {ms:<30}  {len(valid):>3}  {mean_s:>5.2f}  {passes}/{len(valid):<3}  "
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
    p.add_argument("--mock", action="store_true", help="Mock mode — no API calls.")
    p.add_argument("--smoke", action="store_true",
                   help="Real API: v4-flash on 2 problems incl. erdos-659.")
    p.add_argument("--problems-subset", type=int, default=None,
                   help="Random subsample of problems (kept stable by seed=42).")
    p.add_argument("--from-run-id", default=None, help="Reuse an existing run dir (resume).")
    p.add_argument("--max-cost", type=float, default=None,
                   help="Hard kill switch: abort cleanly when cumulative spend exceeds N dollars.")
    p.add_argument("--priority-file", type=str, default=str(PRIORITY_FILE),
                   help="JSON file with an 'ordered' list of pids (priority for killswitch).")
    p.add_argument("--no-priority", action="store_true",
                   help="Ignore priority file; sort problems alphabetically.")
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

    models_full = [m for m, _ in MODELS]
    models = models_full
    if args.smoke:
        rng = random.Random(0)
        proofbench_pool = [pid for pid in problems if pid.startswith(("PB-Basic", "PB-Advanced"))]
        sample = set(rng.sample(proofbench_pool, 1))
        sample.update({"erdos-659"})
        problems = {k: v for k, v in problems.items() if k in sample}

    pid_order = None
    if not args.no_priority:
        try:
            with open(args.priority_file) as f:
                pid_order = json.load(f).get("ordered")
            print(f"Loaded priority order from {args.priority_file} ({len(pid_order)} pids)")
        except Exception as e:
            print(f"[priority] could not load {args.priority_file}: {e} — falling back to sorted order")

    run_id = args.from_run_id or _now_id()
    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")
    run_dir = RESULTS_DIR / f"{EXPERIMENT_NAME}_{run_id}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts = load_prompts()

    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Run dir:       {run_dir}")
    print(f"Problems:      {len(problems)}")
    print(f"Models:        {[model_short(m) for m in models]}")
    print(f"Mode:          {MODE}")
    print(f"Judge:         {JUDGE_MODEL}")
    print(f"max_tokens:    gen={MAX_TOKENS_GEN}  judge={MAX_TOKENS_JUDGE}  ideate={MAX_TOKENS_IDEATE}")
    print(f"Workers:       outer={MAX_WORKERS}  inner(branches)={INNER_WORKERS}")
    print(f"Trial timeout: {TRIAL_TIMEOUT}s  litellm timeout: {LITELLM_TIMEOUT}s")
    print(f"Key:           OPENROUTER_API_KEY_seedgen (single, no rotation)")
    if args.max_cost:
        print(f"Cost cap:      ${args.max_cost} (killswitch)")
    if args.mock:
        print("[MOCK MODE]")
    if args.smoke:
        print(f"[SMOKE MODE — {len(models)} model on {len(problems)} problems]")
    print()

    tracker = CostTracker(args.max_cost)

    if not args.mock:
        for pid, prob in problems.items():
            if not prob["text"] or not prob["ground_truth"]:
                raise SystemExit(f"{pid}: missing text or ground_truth")

    t0 = time.time()
    execute_phase(models, problems, prompts, run_dir, tracker, args.mock, pid_order=pid_order)
    elapsed = round(time.time() - t0, 1)
    cum_cost, in_t, out_t = tracker.snapshot()
    print(f"\nWall-clock: {elapsed}s    Cumulative: ${cum_cost:.2f}  in={in_t:,}  out={out_t:,}")
    print_summary(run_dir)


if __name__ == "__main__":
    main()
