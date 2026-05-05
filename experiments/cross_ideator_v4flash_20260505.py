#!/usr/bin/env python3
"""
Cross-model ideator experiment — does a STRONGER ideator help a CHEAP generator?

Mode (per (condition, problem)):
  ideate(NUM_IDEAS)  ->  NUM_IDEAS parallel branches of:
      seeded_generate(v4-flash) -> [verify(v4-flash) -> revise(v4-flash)] x ITERATIONS
      -> judge(v4-flash) -> pick best

Conditions
  - self_v4flash    : v4-flash IDEATES (and does everything else) — baseline
  - vp_v4flash      : v4-PRO IDEATES, v4-flash everything else — test condition
  - mini_v4flash    : gpt-5.4-mini @ xhigh IDEATES, v4-flash everything else — test condition

Final judge: deepseek-v4-flash (strict, but cheap; r=0.76 with humans per agent_log).

Hypothesis (the "lit-ideas" March 5.28/7 result, never re-tested with the v4 family):
  ideas from a stronger model translate to better solutions from a weaker model
  even when generation/verification/revision are all done by the weaker model.

Problem set:
  20 random PB-Advanced problems (seed=42). Stays under flex-key budget.

Key: OPENROUTER_API_KEY_flex (single, no rotation).
Cost cap: $5 hard kill.
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

from problemset_70 import load_70_problems  # noqa: E402

# ============================================================================
# Configuration
# ============================================================================

EXPERIMENT_NAME = "cross_ideator_v4flash_20260505"

# Generator/verifier/reviser model — held fixed across conditions
GENERATOR_MODEL = "openrouter/deepseek/deepseek-v4-flash"
GENERATOR_PRICE = 0.28  # $/Mtok blended

# Conditions: name -> (ideator_model, ideator_extra_body, ideator_price_per_Mtok)
CONDITIONS = {
    "self_v4flash":  ("openrouter/deepseek/deepseek-v4-flash", None, 0.28),
    "vp_v4flash":    ("openrouter/deepseek/deepseek-v4-pro",   None, 0.87),
    "mini_v4flash":  ("openrouter/openai/gpt-5.4-mini",
                      {"reasoning": {"effort": "xhigh"}}, 5.00),  # ~ blended estimate
}

# Final judge — per user instruction: deepseek-v4-flash
JUDGE_MODEL = "openrouter/deepseek/deepseek-v4-flash"
JUDGE_PRICE = 0.28

NUM_IDEAS = 3
ITERATIONS = 2

# Token budgets — let reasoning models breathe.
MAX_TOKENS_GEN     = 32768
MAX_TOKENS_VERIFY  = 32768
MAX_TOKENS_REVISE  = 32768
MAX_TOKENS_IDEATE  = 16000
MAX_TOKENS_JUDGE   = 32768

MAX_WORKERS    = 24
INNER_WORKERS  = 3

TRIAL_TIMEOUT    = 3600
LITELLM_TIMEOUT  = 1500

PASS_THRESHOLD = 6
N_PROBLEMS_DEFAULT = 20

# ============================================================================
# Paths / utility
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
# API key — flex
# ============================================================================

load_dotenv()
FLEX_KEY = os.getenv("OPENROUTER_API_KEY_flex")
if not FLEX_KEY:
    raise SystemExit("OPENROUTER_API_KEY_flex not set in .env.")


def _probe_key(key: str) -> None:
    import requests
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=8,
        )
        if not r.ok:
            print(f"[startup] flex key probe: HTTP {r.status_code} (continuing)", flush=True)
            return
        d = r.json().get("data", {}) or {}
        usage = d.get("usage", 0) or 0
        limit = d.get("limit")
        print(f"[startup] flex key: usage=${usage:.4f} / limit=${limit}", flush=True)
    except Exception as e:
        print(f"[startup] flex key probe failed: {e}", flush=True)


# ============================================================================
# Mock responses
# ============================================================================

MOCK_IDEAS = [
    {"name": "Direct construction", "description": "Build an explicit example."},
    {"name": "Contradiction",       "description": "Assume the negation, derive contradiction."},
    {"name": "Induction on n",      "description": "Strong induction on the parameter."},
]
MOCK_GEN = ("## Summary\n**Verdict:** Solved\n**Method sketch:** Mock.\n\n"
            "## Detailed Solution\nMock proof.\n\\boxed{42}")
MOCK_VERIFY_PASS = "<CORRECT>true</CORRECT>\nVERDICT: correct"
MOCK_VERIFY_FAIL = "<CORRECT>false</CORRECT>\nVERDICT: issues_found"
MOCK_REVISE = ("## Summary\n**Verdict:** Solved\n## Detailed Solution\nRevised.\n\\boxed{42}")
MOCK_JUDGE = "<points>7 out of 7</points>\nMock judge."


# ============================================================================
# call_model
# ============================================================================

def call_model(
    model: str,
    system: str | None,
    user: str,
    max_tokens: int,
    extra_body: dict | None = None,
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
            kwargs = dict(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                api_key=FLEX_KEY,
                timeout=LITELLM_TIMEOUT,
            )
            if extra_body:
                kwargs["extra_body"] = extra_body
            resp = litellm.completion(**kwargs)
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
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(
                    f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1}: {e} -> {wait:.0f}s",
                    flush=True,
                )
                time.sleep(wait)
    assert last_err is not None
    raise last_err


# ============================================================================
# Cost tracker
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
                    f"[{_ts()}] [KILLSWITCH] cum=${self._cost:.2f} >= cap=${self.max_cost:.2f}",
                    flush=True,
                )

    def aborted(self) -> bool:
        with self._lock:
            return self._aborted

    def snapshot(self) -> tuple[float, int, int]:
        with self._lock:
            return self._cost, self._tokens_in, self._tokens_out


def cost_for(model: str, total_tokens: int, ideator_price: float | None = None) -> float:
    if model == JUDGE_MODEL:
        p = JUDGE_PRICE
    elif model == GENERATOR_MODEL:
        p = GENERATOR_PRICE
    elif ideator_price is not None:
        p = ideator_price
    else:
        p = 0.5  # fallback
    return p * total_tokens / 1_000_000


# ============================================================================
# Atomic pipeline calls
# ============================================================================

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _record_call(
    calls: list, kind: str, model: str, usage: dict, elapsed: float, tracker: CostTracker,
    response_text: str | None = None, ideator_price: float | None = None,
) -> None:
    cost = cost_for(model, usage["total_tokens"], ideator_price=ideator_price)
    calls.append({
        "kind":     kind,
        "model":    model,
        "elapsed":  round(elapsed, 2),
        "usage":    usage,
        "cost_usd": round(cost, 6),
        "response_text": response_text,
    })
    tracker.add(cost, usage["prompt_tokens"], usage["completion_tokens"])


def do_ideate(ideator_model, ideator_extra, ideator_price, problem_text,
              calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    prompt_filled = (
        prompts["ideator"]
        .replace("{problem}", problem_text)
        .replace("{num_ideas}", str(NUM_IDEAS))
    )
    if mock:
        return MOCK_IDEAS[:NUM_IDEAS], "MOCK_IDEATE", {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}
    text, usage = call_model(ideator_model, "", prompt_filled, MAX_TOKENS_IDEATE,
                              extra_body=ideator_extra)
    _record_call(calls, "ideate", ideator_model, usage, time.time() - t0, tracker,
                 response_text=text, ideator_price=ideator_price)

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
    sys_part, sep, content_part = prompts["verifier"].partition("\n**PROBLEM:**\n")
    if not sep:
        sys_part = ""
        content_part = prompts["verifier"]
    else:
        content_part = "**PROBLEM:**\n" + content_part
    user = content_part.replace("{problem}", problem_text).replace("{solution}", solution)
    if mock:
        return ((MOCK_VERIFY_PASS if mock_pass else MOCK_VERIFY_FAIL),
                {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230})
    text, usage = call_model(model, sys_part, user, MAX_TOKENS_VERIFY)
    _record_call(calls, "verify", model, usage, time.time() - t0, tracker, response_text=text)
    return text, usage


def do_revise(model, problem_text, solution, critique, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    sys_part, sep, content_part = prompts["reviser"].partition("\n**PROBLEM:**\n")
    if not sep:
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
# Branch / trial runners
# ============================================================================

def run_full_branch(model, problem_text, ground_truth, initial_solution, calls, tracker, mock, prompts):
    solution = initial_solution
    loop_log = []
    stopped_early = False
    for i in range(ITERATIONS):
        critique, _ = do_verify(model, problem_text, solution, calls, tracker,
                                 mock=mock, mock_pass=(i == 1 and mock), prompts=prompts)
        if "VERDICT: correct" in critique:
            stopped_early = True
            loop_log.append({"iteration": i+1, "verdict": "correct",
                              "critique": critique, "solution": solution})
            break
        new_solution, _ = do_revise(model, problem_text, solution, critique, calls, tracker,
                                     mock=mock, prompts=prompts)
        loop_log.append({"iteration": i+1, "verdict": "issues_found",
                          "critique": critique, "solution_before": solution,
                          "solution_after": new_solution})
        solution = new_solution
    verdict, score, _ = do_judge(problem_text, solution, ground_truth, calls, tracker,
                                  mock=mock, prompts=prompts)
    return solution, verdict, score, loop_log, stopped_early


def run_condition(condition_name, ideator_spec, problem, problem_id, prompts,
                  calls, tracker, mock, branch_save):
    ideator_model, ideator_extra, ideator_price = ideator_spec
    ideas, ideate_text, _ = do_ideate(ideator_model, ideator_extra, ideator_price,
                                        problem["text"], calls, tracker,
                                        mock=mock, prompts=prompts)

    branches = [None] * len(ideas)
    branches_lock = threading.Lock()

    def _branch(idx_idea):
        idx, idea = idx_idea
        b_calls = []
        try:
            sol, _ = do_seeded_generate(GENERATOR_MODEL, problem["text"], idea,
                                          b_calls, tracker, mock=mock, prompts=prompts)
            final_sol, verdict, score, loop_log, stopped_early = run_full_branch(
                GENERATOR_MODEL, problem["text"], problem["ground_truth"], sol,
                b_calls, tracker, mock, prompts,
            )
            branch = {
                "idea_idx": idx, "idea": idea, "initial_solution": sol,
                "final_solution": final_sol, "verdict": verdict, "score": score,
                "loop_log": loop_log, "stopped_early": stopped_early,
                "calls": b_calls, "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            branch = {"idea_idx": idx, "idea": idea, "error": str(e),
                       "calls": b_calls,
                       "completed_at": datetime.now(timezone.utc).isoformat()}
        try:
            branch_save(idx, branch)
        except Exception as save_err:
            print(f"[{_ts()}] WARN branch_save: {save_err}", flush=True)
        with branches_lock:
            branches[idx] = branch
        return branch

    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        list(ex.map(_branch, list(enumerate(ideas))))

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
                "ideator_model": ideator_model, "ideator_extra": ideator_extra,
                "ideas": ideas, "ideate_response": ideate_text,
            },
        }
    return {
        "best_score":    None,
        "best_solution": None,
        "best_verdict":  None,
        "branches":      valid_branches,
        "mode_extras":   {
            "num_ideas": NUM_IDEAS, "iterations": ITERATIONS,
            "ideator_model": ideator_model, "ideator_extra": ideator_extra,
            "ideas": ideas, "ideate_response": ideate_text,
        },
    }


# ============================================================================
# Per-trial save
# ============================================================================

def trial_path(run_dir: Path, condition: str, pid: str) -> Path:
    return run_dir / "trials" / condition / f"{pid}.json"


def branch_dir(run_dir: Path, condition: str, pid: str) -> Path:
    return run_dir / "branches" / condition / pid


def save_branch_inflight(run_dir, condition, pid, idx, branch):
    d = branch_dir(run_dir, condition, pid)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"branch_{idx}.json"
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(branch, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def save_trial(run_dir, manifest_lock, trial):
    p = trial_path(run_dir, trial["condition"], trial["problem_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trial, f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    summary = {
        "ts":         trial["completed_at"],
        "condition":  trial["condition"],
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


def already_done(run_dir, condition, pid):
    p = trial_path(run_dir, condition, pid)
    if not p.exists():
        return False
    try:
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        return not t.get("error") and t.get("score") is not None
    except Exception:
        return False


def run_trial(condition, ideator_spec, problem, pid, prompts, run_dir,
              manifest_lock, tracker, mock):
    tag = f"[{_ts()}] [{condition}|{pid}]"
    print(f"{tag} start", flush=True)
    t0 = time.time()
    calls = []

    def _branch_save(idx, branch):
        save_branch_inflight(run_dir, condition, pid, idx, branch)

    trial = {
        "experiment":  EXPERIMENT_NAME,
        "condition":   condition,
        "problem_id":  pid,
        "category":    problem.get("category", ""),
        "level":       problem.get("level", ""),
        "source":      problem.get("source", ""),
        "started_at":  datetime.now(timezone.utc).isoformat(),
    }

    try:
        out = run_condition(condition, ideator_spec, problem, pid, prompts,
                             calls, tracker, mock, _branch_save)
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
        print(f"{tag} done score={score}/7  ${cost:.4f}  {elapsed}s", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        cost = round(sum(c["cost_usd"] for c in calls), 6)
        traceback.print_exc()
        trial.update({
            "score": None, "passed": False, "elapsed_s": elapsed, "cost_usd": cost,
            "best_solution": None, "best_verdict": None, "branches": [],
            "calls": calls, "error": str(e),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"{tag} ERROR {e}  ${cost:.4f}  {elapsed}s", flush=True)

    save_trial(run_dir, manifest_lock, trial)
    return trial


# ============================================================================
# Executor
# ============================================================================

def execute(conditions, problems, prompts, run_dir, tracker, mock):
    pids = sorted(problems.keys())
    trials = [(cond, pid) for cond in conditions for pid in pids]
    pending = [(c, p) for (c, p) in trials if not already_done(run_dir, c, p)]
    skipped = len(trials) - len(pending)

    print(f"\n=== Cross-ideator | conditions={list(conditions.keys())} ===", flush=True)
    print(f"Trials: {len(trials)}  pending: {len(pending)}  skipped: {skipped}", flush=True)
    print(f"max_workers={MAX_WORKERS}, inner={INNER_WORKERS}, cap=${tracker.max_cost}\n", flush=True)

    manifest_lock = threading.Lock()
    results = []

    def _submit(cond, pid):
        return run_trial(cond, conditions[cond], problems[pid], pid, prompts,
                          run_dir, manifest_lock, tracker, mock)

    completed = 0
    last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for cond, pid in pending:
            if tracker.aborted():
                print(f"[{_ts()}] [KILLSWITCH] not submitting "
                      f"{len(pending)-completed-len(futs)} more trials.", flush=True)
                break
            futs[ex.submit(_submit, cond, pid)] = (cond, pid)

        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * max(len(pending), 1)):
            cond, pid = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                print(f"[{_ts()}] FAILED [{cond}|{pid}]: {e}", flush=True)
                results.append({"problem_id": pid, "condition": cond, "error": str(e)})
            now = time.time()
            if completed % 3 == 0 or now - last_print > 60:
                cum_cost, in_t, out_t = tracker.snapshot()
                print(f"[{_ts()}] Progress: {completed}/{len(pending)}  cum=${cum_cost:.2f}  "
                       f"in={in_t:,} out={out_t:,}", flush=True)
                last_print = now
    return results


# ============================================================================
# Reporting
# ============================================================================

def print_summary(run_dir, conditions):
    trials_by_cond = {c: [] for c in conditions}
    for c in conditions:
        d = run_dir / "trials" / c
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    trials_by_cond[c].append(json.load(f))
            except Exception:
                pass

    print(f"\n{'='*100}\nCROSS-IDEATOR RESULTS — run_dir = {run_dir.name}\n{'='*100}\n")
    cost_total = sum(t.get("cost_usd", 0) or 0 for c in trials_by_cond.values() for t in c)
    print(f"Total cost: ${cost_total:.2f}\n")
    print(f"  {'Condition':<25}  {'n':>3}  {'mean':>5}  {'std':>5}  {'pass':>6}  {'$/run':>8}")
    for cond, ts in trials_by_cond.items():
        valid = [t for t in ts if t.get("score") is not None and not t.get("error")]
        scores = [t["score"] for t in valid]
        passes = sum(1 for t in valid if t.get("passed"))
        costs = [t.get("cost_usd", 0) or 0 for t in ts]
        if scores:
            mean = float(np.mean(scores)); std = float(np.std(scores))
        else:
            mean = std = 0.0
        avg_cost = float(np.mean(costs)) if costs else 0
        print(f"  {cond:<25}  {len(valid):>3}  {mean:>5.2f}  {std:>5.2f}  "
              f"{passes}/{len(valid):<3}  ${avg_cost:.4f}")

    # Head-to-head
    pids = sorted({t["problem_id"] for c in trials_by_cond.values() for t in c})
    print(f"\n--- Per-problem scores ---")
    hdr = f"  {'Problem':<26}" + "".join(f"{c[:14]:<16}" for c in conditions)
    print(hdr)
    for pid in pids:
        row = f"  {pid:<26}"
        for cond in conditions:
            t = next((t for t in trials_by_cond[cond] if t["problem_id"] == pid), None)
            cell = (str(t.get("score")) if t and t.get("score") is not None else "-")
            row += f"{cell:<16}"
        print(row)


# ============================================================================
# Main
# ============================================================================

def select_problems(n: int, seed: int = 42) -> dict[str, dict]:
    all_problems = load_70_problems()
    pb_advanced = {pid: p for pid, p in all_problems.items() if pid.startswith("PB-Advanced")}
    if n >= len(pb_advanced):
        return pb_advanced
    rng = random.Random(seed)
    keys = sorted(pb_advanced.keys())
    sampled = rng.sample(keys, n)
    return {k: pb_advanced[k] for k in sampled}


def load_prompts():
    return {
        "ideator":          load_prompt("ideator.md"),
        "generator_seeded": load_prompt("generator_seeded.md"),
        "verifier":         load_prompt("verifier.md"),
        "reviser":          load_prompt("reviser.md"),
        "judge_gt":         load_prompt("judge_gt.md"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--smoke", action="store_true",
                   help="2 problems, all conditions")
    p.add_argument("--n-problems", type=int, default=N_PROBLEMS_DEFAULT)
    p.add_argument("--from-run-id", default=None)
    p.add_argument("--max-cost", type=float, default=8.0)
    p.add_argument("--conditions", default="all",
                   help="comma-sep; subset of: " + ",".join(CONDITIONS))
    args = p.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    if not args.mock:
        _probe_key(FLEX_KEY)

    n = args.n_problems if not args.smoke else 2
    problems = select_problems(n, seed=42)

    if args.conditions == "all":
        cond_keys = list(CONDITIONS.keys())
    else:
        cond_keys = [c.strip() for c in args.conditions.split(",")]
    conditions = {c: CONDITIONS[c] for c in cond_keys}

    run_id = args.from_run_id or _now_id()
    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")
    run_dir = RESULTS_DIR / f"{EXPERIMENT_NAME}_{run_id}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts = load_prompts()

    print(f"Experiment:  {EXPERIMENT_NAME}")
    print(f"Run dir:     {run_dir}")
    print(f"Problems:    {len(problems)} (seed=42 random PB-Advanced subset)")
    print(f"Conditions:  {list(conditions.keys())}")
    print(f"Generator:   {GENERATOR_MODEL}")
    print(f"Judge:       {JUDGE_MODEL}")
    print(f"NUM_IDEAS={NUM_IDEAS}  ITER={ITERATIONS}")
    print(f"Cost cap:    ${args.max_cost}")
    if args.mock:
        print("[MOCK MODE]")
    if args.smoke:
        print("[SMOKE MODE]")
    print()

    tracker = CostTracker(args.max_cost)

    t0 = time.time()
    execute(conditions, problems, prompts, run_dir, tracker, args.mock)
    elapsed = round(time.time() - t0, 1)
    cum_cost, in_t, out_t = tracker.snapshot()
    print(f"\nWall-clock: {elapsed}s  Cumulative: ${cum_cost:.2f}  in={in_t:,} out={out_t:,}")
    print_summary(run_dir, conditions)


if __name__ == "__main__":
    main()
