#!/usr/bin/env python3
"""
"Strong critic" asymmetric pipeline — does using a strong model ONLY as
verifier+reviser (not generator) rescue cheap-model proofs?

Architecture (per (condition, problem)):
  generate(GEN)  ->  [verify(CRITIC) -> revise(CRITIC)] x ITER  ->  judge(JUDGE)

Conditions
  - flash_solo       : GEN=v4-flash,  CRITIC=v4-flash       (baseline: v4-flash full pipeline)
  - flash_with_vp    : GEN=v4-flash,  CRITIC=v4-pro         (test: strong critic on flash)
  - gemma_solo       : GEN=gemma-4-31b, CRITIC=gemma-4-31b  (baseline: cheap full pipeline)
  - gemma_with_vp    : GEN=gemma-4-31b, CRITIC=v4-pro       (test: strong critic on gemma)

Hypothesis: a strong verifier finds errors a weak self-verifier misses, and a
strong reviser fixes them properly — together they should rescue weak-generator
output even though the generator's capability ceiling is unchanged.

Judge: deepseek-v4-flash.
Problem set: 20 PB-Advanced (random seed=42).
Key: OPENROUTER_API_KEY_flex.
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

EXPERIMENT_NAME = "strong_critic_v4flash_20260505"

# Conditions: (generator, critic, gen_price, critic_price)
CONDITIONS = {
    "flash_solo":     ("openrouter/deepseek/deepseek-v4-flash",
                       "openrouter/deepseek/deepseek-v4-flash", 0.28, 0.28),
    "flash_with_vp":  ("openrouter/deepseek/deepseek-v4-flash",
                       "openrouter/deepseek/deepseek-v4-pro",   0.28, 0.87),
    "gemma_solo":     ("openrouter/google/gemma-4-31b-it",
                       "openrouter/google/gemma-4-31b-it",      0.38, 0.38),
    "gemma_with_vp":  ("openrouter/google/gemma-4-31b-it",
                       "openrouter/deepseek/deepseek-v4-pro",   0.38, 0.87),
}

JUDGE_MODEL = "openrouter/deepseek/deepseek-v4-flash"
JUDGE_PRICE = 0.28

ITERATIONS = 2
MAX_TOKENS_GEN     = 32768
MAX_TOKENS_VERIFY  = 32768
MAX_TOKENS_REVISE  = 32768
MAX_TOKENS_JUDGE   = 32768

MAX_WORKERS    = 10
TRIAL_TIMEOUT  = 3600
LITELLM_TIMEOUT = 1500

PASS_THRESHOLD = 6
N_PROBLEMS_DEFAULT = 20

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _now_id(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts():     return datetime.now(timezone.utc).strftime("%H:%M:%S")


load_dotenv()
FLEX_KEY = os.getenv("OPENROUTER_API_KEY_flex")
if not FLEX_KEY:
    raise SystemExit("OPENROUTER_API_KEY_flex not set in .env.")


def _probe_key(key: str) -> None:
    import requests
    try:
        r = requests.get("https://openrouter.ai/api/v1/key",
                          headers={"Authorization": f"Bearer {key}"}, timeout=8)
        if not r.ok:
            print(f"[startup] flex key probe HTTP {r.status_code}", flush=True); return
        d = r.json().get("data", {}) or {}
        usage = d.get("usage", 0) or 0; limit = d.get("limit")
        print(f"[startup] flex key usage=${usage:.4f} / limit=${limit}", flush=True)
    except Exception as e:
        print(f"[startup] probe failed: {e}", flush=True)


def call_model(model, system, user, max_tokens, retries=2, backoff=5.0):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = litellm.completion(
                model=model, messages=messages, max_tokens=max_tokens,
                api_key=FLEX_KEY, timeout=LITELLM_TIMEOUT,
            )
            content = resp.choices[0].message.content  # type: ignore
            if content is None:
                content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
            if content is None:
                raise ValueError(f"{model}: None content")
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
            if "402" in msg or "Insufficient credits" in msg or '"code":403' in msg:
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1}: {e} -> {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


class CostTracker:
    def __init__(self, max_cost):
        self.max_cost = max_cost
        self._cost = 0.0; self._tokens_in = 0; self._tokens_out = 0
        self._lock = threading.Lock(); self._aborted = False

    def add(self, cost, in_tok, out_tok):
        with self._lock:
            self._cost += cost; self._tokens_in += in_tok; self._tokens_out += out_tok
            if self.max_cost is not None and self._cost >= self.max_cost and not self._aborted:
                self._aborted = True
                print(f"[{_ts()}] [KILLSWITCH] cum=${self._cost:.2f} >= cap=${self.max_cost:.2f}", flush=True)

    def aborted(self):
        with self._lock: return self._aborted

    def snapshot(self):
        with self._lock: return self._cost, self._tokens_in, self._tokens_out


PRICE_BY_MODEL = {
    "openrouter/deepseek/deepseek-v4-flash": 0.28,
    "openrouter/deepseek/deepseek-v4-pro": 0.87,
    "openrouter/google/gemma-4-31b-it": 0.38,
}


def cost_for(model, total_tokens):
    p = PRICE_BY_MODEL.get(model, 0.5)
    return p * total_tokens / 1_000_000


def load_prompt(name): return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _record(calls, kind, model, usage, elapsed, tracker, response_text=None):
    cost = cost_for(model, usage["total_tokens"])
    calls.append({"kind": kind, "model": model, "elapsed": round(elapsed, 2),
                  "usage": usage, "cost_usd": round(cost, 6),
                  "response_text": response_text})
    tracker.add(cost, usage["prompt_tokens"], usage["completion_tokens"])


def parse_gt_score(verdict):
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m: return int(m.group(1))
    return 0


def do_generate(model, problem_text, calls, tracker, prompts):
    t0 = time.time()
    text, usage = call_model(model, prompts["generator"], problem_text, MAX_TOKENS_GEN)
    _record(calls, "generate", model, usage, time.time() - t0, tracker, response_text=text)
    return text


def do_verify(model, problem_text, solution, calls, tracker, prompts):
    t0 = time.time()
    sys_part, sep, content_part = prompts["verifier"].partition("\n**PROBLEM:**\n")
    if not sep: sys_part = ""; content_part = prompts["verifier"]
    else:       content_part = "**PROBLEM:**\n" + content_part
    user = content_part.replace("{problem}", problem_text).replace("{solution}", solution)
    text, usage = call_model(model, sys_part, user, MAX_TOKENS_VERIFY)
    _record(calls, "verify", model, usage, time.time() - t0, tracker, response_text=text)
    return text


def do_revise(model, problem_text, solution, critique, calls, tracker, prompts):
    t0 = time.time()
    sys_part, sep, content_part = prompts["reviser"].partition("\n**PROBLEM:**\n")
    if not sep: sys_part = ""; content_part = prompts["reviser"]
    else:       content_part = "**PROBLEM:**\n" + content_part
    user = (content_part.replace("{problem}", problem_text)
                         .replace("{solution}", solution)
                         .replace("{critique}", critique))
    text, usage = call_model(model, sys_part, user, MAX_TOKENS_REVISE)
    _record(calls, "revise", model, usage, time.time() - t0, tracker, response_text=text)
    return text


def do_judge(problem_text, candidate, ground_truth, calls, tracker, prompts):
    t0 = time.time()
    user = (prompts["judge_gt"]
            .replace("{problem}", problem_text)
            .replace("{ground_truth}", ground_truth)
            .replace("{candidate}", candidate))
    text, usage = call_model(JUDGE_MODEL, "", user, MAX_TOKENS_JUDGE)
    _record(calls, "judge", JUDGE_MODEL, usage, time.time() - t0, tracker, response_text=text)
    return text, parse_gt_score(text)


def run_condition(condition, gen_model, critic_model, problem, prompts, calls, tracker):
    solution = do_generate(gen_model, problem["text"], calls, tracker, prompts)
    loop_log = []; stopped_early = False
    for i in range(ITERATIONS):
        critique = do_verify(critic_model, problem["text"], solution, calls, tracker, prompts)
        if "VERDICT: correct" in critique:
            loop_log.append({"iteration": i+1, "verdict": "correct",
                             "critique": critique, "solution": solution})
            stopped_early = True
            break
        new_sol = do_revise(critic_model, problem["text"], solution, critique,
                             calls, tracker, prompts)
        loop_log.append({"iteration": i+1, "verdict": "issues_found",
                         "critique": critique, "solution_before": solution,
                         "solution_after": new_sol})
        solution = new_sol
    verdict, score = do_judge(problem["text"], solution, problem["ground_truth"],
                                calls, tracker, prompts)
    return solution, verdict, score, loop_log, stopped_early


def trial_path(run_dir, condition, pid):
    return run_dir / "trials" / condition / f"{pid}.json"


def save_trial(run_dir, manifest_lock, trial):
    p = trial_path(run_dir, trial["condition"], trial["problem_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trial, f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    summary = {"ts": trial["completed_at"], "condition": trial["condition"],
               "problem_id": trial["problem_id"], "score": trial.get("score"),
               "passed": trial.get("passed"), "elapsed_s": trial.get("elapsed_s"),
               "cost_usd": trial.get("cost_usd"), "n_calls": len(trial.get("calls", [])),
               "error": trial.get("error")}
    with manifest_lock:
        with open(run_dir / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")


def already_done(run_dir, condition, pid):
    p = trial_path(run_dir, condition, pid)
    if not p.exists(): return False
    try:
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        return not t.get("error") and t.get("score") is not None
    except Exception:
        return False


def run_trial(condition, spec, problem, pid, prompts, run_dir, manifest_lock, tracker):
    gen_model, critic_model, _, _ = spec
    tag = f"[{_ts()}] [{condition}|{pid}]"
    print(f"{tag} start", flush=True)
    t0 = time.time(); calls = []
    trial = {
        "experiment": EXPERIMENT_NAME, "condition": condition,
        "generator_model": gen_model, "critic_model": critic_model,
        "problem_id": pid, "category": problem.get("category", ""),
        "level": problem.get("level", ""), "source": problem.get("source", ""),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        sol, verdict, score, loop_log, stopped = run_condition(
            condition, gen_model, critic_model, problem, prompts, calls, tracker,
        )
        elapsed = round(time.time() - t0, 2)
        cost = round(sum(c["cost_usd"] for c in calls), 6)
        trial.update({
            "score": score, "passed": score >= PASS_THRESHOLD,
            "elapsed_s": elapsed, "cost_usd": cost,
            "final_solution": sol, "verdict": verdict,
            "loop_log": loop_log, "stopped_early": stopped,
            "calls": calls, "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"{tag} done score={score}/7 ${cost:.4f} {elapsed}s", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        cost = round(sum(c["cost_usd"] for c in calls), 6)
        traceback.print_exc()
        trial.update({"score": None, "passed": False, "elapsed_s": elapsed,
                      "cost_usd": cost, "final_solution": None, "verdict": None,
                      "loop_log": [], "stopped_early": False, "calls": calls,
                      "error": str(e), "completed_at": datetime.now(timezone.utc).isoformat()})
        print(f"{tag} ERROR {e}  ${cost:.4f}  {elapsed}s", flush=True)
    save_trial(run_dir, manifest_lock, trial)
    return trial


def execute(conditions, problems, prompts, run_dir, tracker):
    pids = sorted(problems.keys())
    trials = [(c, p) for c in conditions for p in pids]
    pending = [(c, p) for (c, p) in trials if not already_done(run_dir, c, p)]
    skipped = len(trials) - len(pending)

    print(f"\n=== Strong-critic | conditions={list(conditions.keys())} ===", flush=True)
    print(f"Trials: {len(trials)}  pending: {len(pending)}  skipped: {skipped}", flush=True)
    print(f"max_workers={MAX_WORKERS}, cap=${tracker.max_cost}\n", flush=True)

    manifest_lock = threading.Lock()
    results = []

    completed = 0; last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for cond, pid in pending:
            if tracker.aborted():
                print(f"[{_ts()}] [KILLSWITCH] aborting submission", flush=True)
                break
            futs[ex.submit(run_trial, cond, conditions[cond], problems[pid], pid,
                            prompts, run_dir, manifest_lock, tracker)] = (cond, pid)
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * max(len(pending), 1)):
            cond, pid = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                print(f"[{_ts()}] FAILED [{cond}|{pid}]: {e}", flush=True)
                results.append({"problem_id": pid, "condition": cond, "error": str(e)})
            now = time.time()
            if completed % 4 == 0 or now - last_print > 60:
                cum_cost, in_t, out_t = tracker.snapshot()
                print(f"[{_ts()}] Progress {completed}/{len(pending)} cum=${cum_cost:.2f} "
                       f"in={in_t:,} out={out_t:,}", flush=True)
                last_print = now
    return results


def print_summary(run_dir, conditions):
    by_cond = {c: [] for c in conditions}
    for c in conditions:
        d = run_dir / "trials" / c
        if not d.exists(): continue
        for p in sorted(d.glob("*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    by_cond[c].append(json.load(f))
            except Exception: pass

    print(f"\n{'='*100}\nSTRONG-CRITIC RESULTS — {run_dir.name}\n{'='*100}\n")
    cost_total = sum(t.get("cost_usd", 0) or 0 for c in by_cond.values() for t in c)
    print(f"Total cost: ${cost_total:.2f}\n")
    print(f"  {'Condition':<22}  {'n':>3}  {'mean':>5}  {'std':>5}  {'pass':>6}  {'$/run':>8}")
    for cond, ts in by_cond.items():
        valid = [t for t in ts if t.get("score") is not None and not t.get("error")]
        scores = [t["score"] for t in valid]
        passes = sum(1 for t in valid if t.get("passed"))
        costs = [t.get("cost_usd", 0) or 0 for t in ts]
        if scores:
            mean = float(np.mean(scores)); std = float(np.std(scores))
        else:
            mean = std = 0.0
        avg_cost = float(np.mean(costs)) if costs else 0
        print(f"  {cond:<22}  {len(valid):>3}  {mean:>5.2f}  {std:>5.2f}  "
              f"{passes}/{len(valid):<3}  ${avg_cost:.4f}")

    pids = sorted({t["problem_id"] for c in by_cond.values() for t in c})
    print(f"\n--- Per-problem ---")
    hdr = f"  {'Problem':<26}" + "".join(f"{c[:14]:<16}" for c in conditions)
    print(hdr)
    for pid in pids:
        row = f"  {pid:<26}"
        for cond in conditions:
            t = next((t for t in by_cond[cond] if t["problem_id"] == pid), None)
            cell = (str(t.get("score")) if t and t.get("score") is not None else "-")
            row += f"{cell:<16}"
        print(row)


def select_problems(n, seed=42):
    all_p = load_70_problems()
    pb = {pid: p for pid, p in all_p.items() if pid.startswith("PB-Advanced")}
    if n >= len(pb): return pb
    rng = random.Random(seed)
    keys = sorted(pb.keys())
    sampled = rng.sample(keys, n)
    return {k: pb[k] for k in sampled}


def load_prompts():
    return {
        "generator": load_prompt("generator.md"),
        "verifier":  load_prompt("verifier.md"),
        "reviser":   load_prompt("reviser.md"),
        "judge_gt":  load_prompt("judge_gt.md"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--n-problems", type=int, default=N_PROBLEMS_DEFAULT)
    p.add_argument("--from-run-id", default=None)
    p.add_argument("--max-cost", type=float, default=10.0)
    p.add_argument("--conditions", default="all")
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
    print(f"Problems:    {len(problems)}")
    print(f"Conditions:  {list(conditions.keys())}")
    print(f"Cost cap:    ${args.max_cost}")
    if args.mock: print("[MOCK]")
    if args.smoke: print("[SMOKE]")
    print()
    tracker = CostTracker(args.max_cost)
    t0 = time.time()
    execute(conditions, problems, prompts, run_dir, tracker)
    elapsed = round(time.time() - t0, 1)
    cum, in_t, out_t = tracker.snapshot()
    print(f"\nWall: {elapsed}s  Cumulative: ${cum:.2f}  in={in_t:,} out={out_t:,}")
    print_summary(run_dir, conditions)


if __name__ == "__main__":
    main()
