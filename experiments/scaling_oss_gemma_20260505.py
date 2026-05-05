#!/usr/bin/env python3
"""
Best-of-N scaling experiment — gpt-oss-120b + gemma-4-31b-it, generate-only.

Tests N in {1, 3, 5, 7} on a 30-problem subset (PB-Advanced-001..030 — the harder
canonical IMO-style proofbench set, where scaling matters most).

Per user instruction: re-uses Phase 1 generate-mode branches as k=0..2 (so we only
need to run k=3..6 fresh). For comparability we judge each NEW branch with BOTH
gemini-3-flash-preview and deepseek-v4-pro.

Phase 1 data sources (already on disk, no re-judging needed):
  k=0..2 solutions  -> seed_ideas_full_compare_20260504_20260504_101225/generate/<model>/<pid>.json
  k=0..2 v4-pro     -> same file (b['score'])
  k=0..2 gemini     -> regrade_branches_gemini_20260504_20260504_222334/generate/<model>/<pid>__k{0,1,2}.json

New work (this script):
  k=3..6 generate, judge with BOTH judges, save per-branch.

Aggregation:
  best_of_N[judge] = max(scores[0..N-1]) for N in {1, 3, 5, 7}
  Reported per (model, judge) over the 30-problem subset.

Key
  Uses OPENROUTER_API_KEY_X (no rotation, separate from seedgen) so this can run
  concurrently with the role-swap experiment without rate-limit contention.

Usage
  uv run experiments/scaling_oss_gemma_20260505.py --mock
  uv run experiments/scaling_oss_gemma_20260505.py --smoke
  uv run experiments/scaling_oss_gemma_20260505.py --max-cost 25
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

EXPERIMENT_NAME = "scaling_oss_gemma_20260505"

OSS   = "openrouter/openai/gpt-oss-120b"
GEMMA = "openrouter/google/gemma-4-31b-it"

PRICE_PER_MTOKEN = {OSS: 0.18, GEMMA: 0.38}

JUDGE_GEMINI       = "openrouter/google/gemini-3-flash-preview"
JUDGE_GEMINI_PRICE = 3.00
JUDGE_V4PRO        = "openrouter/deepseek/deepseek-v4-pro"
JUDGE_V4PRO_PRICE  = 0.87

JUDGES = [
    ("gemini", JUDGE_GEMINI, JUDGE_GEMINI_PRICE),
    ("v4pro",  JUDGE_V4PRO,  JUDGE_V4PRO_PRICE),
]

N_VALUES         = (1, 3, 5, 7)
EXISTING_K       = 3                    # Phase 1 has k=0,1,2
NEW_K_RANGE      = range(EXISTING_K, max(N_VALUES))   # k=3,4,5,6 -> 4 new gens

MAX_TOKENS_GEN   = 65536
MAX_TOKENS_JUDGE = 65536

MAX_WORKERS      = 30
LITELLM_TIMEOUT  = 1800

PASS_THRESHOLD   = 6

# 30 PB-Advanced problems — the canonical "scaling-meaningful" cut.
SCALING_SUBSET = [f"PB-Advanced-{i:03d}" for i in range(1, 31)]

MODELS = [OSS, GEMMA]

# ============================================================================
# Paths
# ============================================================================

ROOT = Path(__file__).parent.parent
PROMPTS_DIR  = ROOT / "prompts" / "pipeline"
RESULTS_DIR  = Path(__file__).parent / "results"
PHASE1_DIR   = RESULTS_DIR / "seed_ideas_full_compare_20260504_20260504_101225"
REGRADE_DIR  = RESULTS_DIR / "regrade_branches_gemini_20260504_20260504_222334"
RESULTS_DIR.mkdir(exist_ok=True)


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def model_short(model: str) -> str:
    return model.split("/")[-1]


# ============================================================================
# Auth — uses OPENROUTER_API_KEY_X (separate from seedgen)
# ============================================================================

load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY_X")
if not API_KEY:
    raise SystemExit("OPENROUTER_API_KEY_X not set in .env")


def _probe_key(key: str) -> None:
    import requests
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}"}, timeout=8,
        )
        d = r.json().get("data", {}) or {}
        usage = d.get("usage", 0) or 0
        limit = d.get("limit")
        rem = (limit - usage) if limit is not None else "unlim"
        print(f"[startup] OPENROUTER_API_KEY_X usage={usage:.2f}/{limit}, remain={rem}", flush=True)
        if limit is not None and usage >= limit:
            raise SystemExit(f"key exhausted ({usage:.2f}/{limit}).")
    except SystemExit:
        raise
    except Exception as e:
        print(f"[startup] key probe failed ({e}); continuing", flush=True)


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
            resp = litellm.completion(
                model=model, messages=messages, max_tokens=max_tokens,
                api_key=API_KEY, timeout=LITELLM_TIMEOUT,
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
                "402" in msg or "Insufficient credits" in msg
                or "Key limit exceeded" in msg or '"code":403' in msg
            ):
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(
                    f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1}: {e} — retry in {wait:.0f}s",
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
                    f"[{_ts()}] [KILLSWITCH] cum cost ${self._cost:.2f} >= cap ${self.max_cost:.2f}",
                    flush=True,
                )

    def aborted(self) -> bool:
        with self._lock:
            return self._aborted

    def snapshot(self) -> tuple[float, int, int]:
        with self._lock:
            return self._cost, self._tokens_in, self._tokens_out


def cost_for(model: str, total_tokens: int) -> float:
    if model == JUDGE_GEMINI:
        p = JUDGE_GEMINI_PRICE
    elif model == JUDGE_V4PRO:
        p = JUDGE_V4PRO_PRICE
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


MOCK_GEN = "## Summary\n**Verdict:** Solved\n## Detailed Solution\nMock proof.\n\\boxed{42}"
MOCK_JUDGE = "<points>7 out of 7</points>\nMock judge."


def do_generate(model, problem_text, calls, tracker, mock=False, prompts=None):
    t0 = time.time()
    if mock:
        return MOCK_GEN, {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    text, usage = call_model(model, prompts["generator"], problem_text, MAX_TOKENS_GEN)
    _record_call(calls, "generate", model, usage, time.time() - t0, tracker, response_text=text)
    return text, usage


def do_judge(judge_model, kind, problem_text, candidate, ground_truth, calls, tracker,
             mock=False, prompts=None):
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
# Existing Phase 1 + regrade reader
# ============================================================================

def read_existing_branches(model: str, pid: str) -> list[dict]:
    """Return list of 3 branch dicts {k, solution, gemini_score, v4pro_score} from Phase 1."""
    ms = model_short(model)
    p1 = PHASE1_DIR / "generate" / ms / f"{pid}.json"
    rg_dir = REGRADE_DIR / "generate" / ms
    if not p1.exists():
        raise SystemExit(f"Phase 1 missing: {p1}")
    with open(p1, encoding="utf-8") as f:
        trial = json.load(f)
    branches_p1 = trial.get("branches", [])
    by_k = {b["k"]: b for b in branches_p1}
    out = []
    for k in range(EXISTING_K):
        b = by_k.get(k)
        if not b:
            raise SystemExit(f"Phase 1 branch missing: {ms} {pid} k={k}")
        # v4-pro score is the original branch score
        v4pro_score = b.get("score")
        # gemini regrade score
        rg_path = rg_dir / f"{pid}__k{k}.json"
        gemini_score = None
        if rg_path.exists():
            with open(rg_path, encoding="utf-8") as f:
                rg = json.load(f)
            gemini_score = rg.get("gemini_score")
        out.append({
            "k": k,
            "source": "phase1",
            "solution": b.get("solution"),
            "gemini_score": gemini_score,
            "v4pro_score":  v4pro_score,
        })
    return out


# ============================================================================
# Per-trial runner — generates 4 new samples, judges each with both judges
# ============================================================================

def trial_path(run_dir: Path, model: str, pid: str) -> Path:
    return run_dir / "trials" / model_short(model) / f"{pid}.json"


def branch_path(run_dir: Path, model: str, pid: str, k: int) -> Path:
    return run_dir / "branches" / model_short(model) / pid / f"k{k}.json"


def save_branch(run_dir: Path, model: str, pid: str, branch: dict) -> None:
    p = branch_path(run_dir, model, pid, branch["k"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(branch, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def save_trial(run_dir: Path, manifest_lock: threading.Lock, trial: dict) -> None:
    p = trial_path(run_dir, trial["model"], trial["problem_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trial, f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    summary = {
        "ts":          trial["completed_at"],
        "model":       trial["model"],
        "problem_id":  trial["problem_id"],
        "n_new":       trial.get("n_new"),
        "n_existing":  trial.get("n_existing"),
        "cost_usd":    trial.get("cost_usd"),
        "elapsed_s":   trial.get("elapsed_s"),
        "error":       trial.get("error"),
    }
    with manifest_lock:
        with open(run_dir / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")


def run_trial(model: str, problem: dict, problem_id: str, prompts: dict,
              run_dir: Path, manifest_lock: threading.Lock, tracker: CostTracker,
              mock: bool) -> dict:
    pid = problem_id
    ms = model_short(model)
    tag = f"[{_ts()}] [scaling|{ms}|{pid}]"
    print(f"{tag} start", flush=True)
    t0 = time.time()
    calls: list = []
    new_branches: list[dict] = []

    trial: dict = {
        "experiment":  EXPERIMENT_NAME,
        "model":       model,
        "problem_id":  pid,
        "started_at":  datetime.now(timezone.utc).isoformat(),
    }

    try:
        existing = read_existing_branches(model, pid) if not mock else []
        for k in NEW_K_RANGE:
            # Skip if already done (resume support).
            bp = branch_path(run_dir, model, pid, k)
            if bp.exists():
                try:
                    with open(bp, encoding="utf-8") as f:
                        new_branches.append(json.load(f))
                    continue
                except Exception:
                    pass
            sol, _u = do_generate(model, problem["text"], calls, tracker, mock=mock, prompts=prompts)
            scores = {}
            verdicts = {}
            for label, jm, _ in JUDGES:
                vt, sc, _ = do_judge(jm, f"judge_{label}", problem["text"], sol,
                                     problem["ground_truth"], calls, tracker,
                                     mock=mock, prompts=prompts)
                scores[label] = sc
                verdicts[label] = vt
            branch = {
                "k":             k,
                "source":        "scaling_new",
                "solution":      sol,
                "gemini_score":  scores.get("gemini"),
                "gemini_verdict": verdicts.get("gemini"),
                "v4pro_score":   scores.get("v4pro"),
                "v4pro_verdict": verdicts.get("v4pro"),
                "completed_at":  datetime.now(timezone.utc).isoformat(),
            }
            save_branch(run_dir, model, pid, branch)
            new_branches.append(branch)

        # Combine existing + new for the trial-level summary.
        all_branches = existing + new_branches
        elapsed = round(time.time() - t0, 2)
        cost = round(sum(c["cost_usd"] for c in calls), 6)
        trial.update({
            "branches":     all_branches,
            "n_existing":   len(existing),
            "n_new":        len(new_branches),
            "elapsed_s":    elapsed,
            "cost_usd":     cost,
            "calls":        calls,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        gem_scores = [b.get("gemini_score") for b in all_branches]
        v4_scores  = [b.get("v4pro_score")  for b in all_branches]
        print(f"{tag} done  ${cost:.4f}  {elapsed}s  gem={gem_scores}  v4={v4_scores}", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        cost = round(sum(c["cost_usd"] for c in calls), 6)
        traceback.print_exc()
        trial.update({
            "branches":     new_branches,
            "n_existing":   None,
            "n_new":        len(new_branches),
            "elapsed_s":    elapsed,
            "cost_usd":     cost,
            "calls":        calls,
            "error":        str(e),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"{tag} ERROR {e}  ${cost:.4f}", flush=True)

    save_trial(run_dir, manifest_lock, trial)
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
        if t.get("error"):
            return False
        # all 4 new branches present?
        new = [b for b in t.get("branches", []) if b.get("source") == "scaling_new"]
        return len(new) >= len(NEW_K_RANGE)
    except Exception:
        return False


def execute(problems: dict, prompts: dict, run_dir: Path, tracker: CostTracker,
            mock: bool) -> list[dict]:
    pids = sorted([pid for pid in problems if pid in problems])
    work = [(pid, m) for pid in pids for m in MODELS]
    pending = [(pid, m) for (pid, m) in work if not already_done(run_dir, m, pid)]
    skipped = len(work) - len(pending)
    print(f"\n=== Scaling | models={[model_short(m) for m in MODELS]}  N_VALUES={N_VALUES} ===", flush=True)
    print(f"Total: {len(work)}  pending: {len(pending)}  skipped: {skipped}", flush=True)
    print(f"max_workers={MAX_WORKERS}, max_cost=${tracker.max_cost}\n", flush=True)

    manifest_lock = threading.Lock()
    results = []

    def _submit(pid, m):
        return run_trial(m, problems[pid], pid, prompts, run_dir, manifest_lock, tracker, mock)

    completed = 0
    last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {}
        for pid, m in pending:
            if tracker.aborted():
                break
            futs[ex.submit(_submit, pid, m)] = (pid, m)
        for fut in concurrent.futures.as_completed(futs):
            pid, m = futs[fut]
            completed += 1
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"[{_ts()}] FAILED [{model_short(m)}|{pid}]: {e}", flush=True)
            now = time.time()
            if completed % 5 == 0 or now - last_print > 60:
                cum, in_t, out_t = tracker.snapshot()
                print(
                    f"[{_ts()}] Progress: {completed}/{len(pending)}  cum=${cum:.2f}  "
                    f"in={in_t:,} out={out_t:,}",
                    flush=True,
                )
                last_print = now
    return results


# ============================================================================
# Reporting — best-of-N table
# ============================================================================

def best_of_n(scores: list[int | None], n: int) -> int | None:
    """Best score in scores[:n]. None if any of those is None."""
    sub = scores[:n]
    if any(s is None for s in sub):
        return None
    return max(sub)


def print_summary(run_dir: Path) -> None:
    trials_dir = run_dir / "trials"
    if not trials_dir.exists():
        print(f"(no trials dir)")
        return
    by_model: dict[str, list[dict]] = {}
    for p in sorted(trials_dir.rglob("*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                t = json.load(f)
            by_model.setdefault(t["model"], []).append(t)
        except Exception:
            pass
    if not any(by_model.values()):
        print("No trials.")
        return
    cost_total = sum(t.get("cost_usd", 0) or 0 for ts in by_model.values() for t in ts)
    print(f"\n{'='*100}")
    print(f"SCALING — run_dir = {run_dir.name}")
    print(f"{'='*100}")
    n_trials = sum(len(v) for v in by_model.values())
    print(f"Total trials: {n_trials}    Total cost: ${cost_total:.2f}\n")

    for model in MODELS:
        ts = by_model.get(model, [])
        if not ts: continue
        ms = model_short(model)
        print(f"-- {ms} ({len(ts)} problems) --")
        for label, _, _ in JUDGES:
            print(f"  judge={label}")
            row = {n: [] for n in N_VALUES}
            for t in ts:
                branches = sorted(t.get("branches", []), key=lambda b: b["k"])
                scores = [b.get(f"{label}_score") for b in branches]
                for n in N_VALUES:
                    s = best_of_n(scores, n)
                    if s is not None:
                        row[n].append(s)
            for n in N_VALUES:
                vals = row[n]
                if not vals: continue
                mean = float(np.mean(vals))
                passes = sum(1 for v in vals if v >= PASS_THRESHOLD)
                print(f"    N={n}  n_problems={len(vals):>3}  mean={mean:.2f}  pass≥6={passes}/{len(vals)}")
        print()


# ============================================================================
# Main / CLI
# ============================================================================

def load_prompts() -> dict:
    return {
        "generator": load_prompt("generator.md"),
        "judge_gt":  load_prompt("judge_gt.md"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock",  action="store_true")
    p.add_argument("--smoke", action="store_true",
                   help="3 problems × 1 model with real APIs")
    p.add_argument("--from-run-id", default=None)
    p.add_argument("--max-cost", type=float, default=None)
    args = p.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    if not args.mock:
        _probe_key(API_KEY)

    all_problems = load_70_problems()
    problems = {pid: p for pid, p in all_problems.items() if pid in SCALING_SUBSET}
    if len(problems) != len(SCALING_SUBSET):
        missing = set(SCALING_SUBSET) - set(problems)
        raise SystemExit(f"Missing problems: {missing}")

    if args.smoke:
        keep = SCALING_SUBSET[:3]
        problems = {k: v for k, v in problems.items() if k in keep}
        global MODELS
        MODELS = [OSS]

    run_id = args.from_run_id or _now_id()
    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")
    run_dir = RESULTS_DIR / f"{EXPERIMENT_NAME}_{run_id}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts = load_prompts()

    print(f"Experiment:    {EXPERIMENT_NAME}")
    print(f"Run dir:       {run_dir}")
    print(f"Subset:        {len(problems)} problems (PB-Advanced-001..030)")
    print(f"Models:        {[model_short(m) for m in MODELS]}")
    print(f"N values:      {N_VALUES} (k=0..2 reused from Phase 1, k=3..6 new)")
    print(f"Judges:        {[j[0] for j in JUDGES]}")
    print(f"Workers:       {MAX_WORKERS}")
    print(f"Key:           OPENROUTER_API_KEY_X")
    if args.max_cost:
        print(f"Cost cap:      ${args.max_cost}")
    print()

    tracker = CostTracker(args.max_cost)

    t0 = time.time()
    execute(problems, prompts, run_dir, tracker, args.mock)
    elapsed = round(time.time() - t0, 1)
    cum, in_t, out_t = tracker.snapshot()
    print(f"\nWall: {elapsed}s    Cumulative: ${cum:.2f}  in={in_t:,}  out={out_t:,}")
    print_summary(run_dir)


if __name__ == "__main__":
    main()
