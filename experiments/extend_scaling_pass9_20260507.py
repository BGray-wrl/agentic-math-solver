#!/usr/bin/env python3
"""
Extend the scaling bucket to M=9 branches per (cell, problem) on the canonical
70-problem PB+R26 set, for the 4 (model, reasoning) cells:

  1. gemma-4-31b-it  × default   (source: 'scaling',          + phase1 generate)
  2. gpt-oss-120b    × default   (source: 'scaling',          + phase1 generate)
  3. gemma-4-31b-it  × max       (source: 'scaling_reasoning' — already complete; skipped)
  4. gpt-oss-120b    × max       (source: 'scaling_reasoning' — top-up incomplete pids)

Plus deepseek-v4-flash × default (source: 'scaling_v4flash') extended from 7→9.

Reuse policy
------------
- Existing branches in `results/dataset_20260505.jsonl` are kept as-is.
- For ('scaling', gemma|gpt-oss, default) pids that have only 3 branches (the
  40 problems outside PB-Advanced 1..30), we reuse the phase1 'generate'
  k=0..2 branches (already v4flash-judged) — they were the seed Phase 1 for the
  canonical scaling experiment.
- For ('scaling_reasoning', gpt-oss-120b, max) we top-up the 4 partial pids.
- All NEW branches are generated here and judged with deepseek-v4-flash.

Output
------
- `experiments/results/extend_scaling_pass9_20260507_<runid>/branches/<source>/<model_short>/<pid>/k<NN>.json`
  Each JSON has {k, source, solution, judges:{v4flash:{score,verdict}}, ...}.
- `manifest.jsonl` for resume tracking.

This script does NOT rewrite the dataset or the scaling bucket. The companion
merger script (merge_scaling_pass9_20260507.py) reads the existing dataset +
these new branches and rebuilds `results/scaling_20260506/*` to include n=9.

Usage
-----
  uv run experiments/extend_scaling_pass9_20260507.py --mock
  uv run experiments/extend_scaling_pass9_20260507.py --max-cost 30
  uv run experiments/extend_scaling_pass9_20260507.py --from-run-id 20260507_120000
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

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

from problemset_70 import load_70_problems  # noqa: E402

# ============================================================================
# Configuration
# ============================================================================

EXPERIMENT_NAME = "extend_scaling_pass9_20260507"

GEMMA = "openrouter/google/gemma-4-31b-it"
OSS   = "openrouter/openai/gpt-oss-120b"
V4F   = "openrouter/deepseek/deepseek-v4-flash"

JUDGE_V4FLASH = "openrouter/deepseek/deepseek-v4-flash"
JUDGE_PRICE   = 0.28
PRICE_PER_MTOKEN = {GEMMA: 0.38, OSS: 0.18, V4F: 0.28}

TARGET_M = 9
MAX_TOKENS_GEN   = 65536
MAX_TOKENS_JUDGE = 32768
LITELLM_TIMEOUT  = 1800
MAX_WORKERS      = 50
PASS_THRESHOLD   = 6

# ============================================================================
# Paths
# ============================================================================

ROOT        = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
DATASET     = ROOT / "results" / "dataset_20260505.jsonl"
RESULTS_DIR.mkdir(exist_ok=True)


def _now_id() -> str: return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts() -> str:     return datetime.now(timezone.utc).strftime("%H:%M:%S")
def model_short(model: str) -> str: return model.split("/")[-1]


# ============================================================================
# Auth — multi-key rotation across available keys for throughput
# ============================================================================

load_dotenv()

CANDIDATE_KEYS = [
    os.getenv("OPENROUTER_API_KEY"),
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_price_compare"),
]
KEYS = [k for k in CANDIDATE_KEYS if k]
if not KEYS:
    raise SystemExit("No OPENROUTER_API_KEY* found in .env")

_key_idx = [0]
_key_lock = threading.Lock()
_dead_keys: set = set()

# Per-model concurrency caps. Provider upstreams (Novita/Chutes for gemma,
# Together/Fireworks for gpt-oss) rate-limit aggressively when a single user
# slams them with 50 simultaneous requests. Capping per-model concurrency
# drops 429 retry storms.
_model_sems: dict[str, threading.Semaphore] = {}
_model_sem_caps = {
    GEMMA: 30,    # push hard — accept more 429s, more retries with backoff
    OSS:   30,
    V4F:   40,    # deepseek's own provider handles much more
}

def _acquire_model_slot(model: str):
    sem = _model_sems.get(model)
    if sem is None:
        cap = _model_sem_caps.get(model, 30)
        sem = _model_sems.setdefault(model, threading.Semaphore(cap))
    return sem

def next_key(skip: set | None = None) -> str | None:
    """Round-robin among live keys; skip the given set as well as dead keys."""
    skip = skip or set()
    with _key_lock:
        for _ in range(len(KEYS)):
            k = KEYS[_key_idx[0] % len(KEYS)]
            _key_idx[0] += 1
            if k not in _dead_keys and k not in skip:
                return k
    return None


def mark_dead(key: str) -> None:
    with _key_lock:
        _dead_keys.add(key)
        idx = KEYS.index(key) if key in KEYS else -1
        print(f"[{_ts()}] [key] disabling key idx={idx} ({len(KEYS) - len(_dead_keys)} live remaining)", flush=True)


def _probe_keys() -> None:
    import requests
    for i, k in enumerate(KEYS):
        try:
            r = requests.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {k}"}, timeout=8,
            )
            d = r.json().get("data", {}) or {}
            usage = d.get("usage", 0) or 0
            limit = d.get("limit")
            rem = (limit - usage) if limit is not None else "unlim"
            print(f"[startup] KEY[{i}] usage={usage:.2f}/{limit}, remain={rem}", flush=True)
            if limit is not None and usage >= limit:
                mark_dead(k)
        except Exception as e:
            print(f"[startup] KEY[{i}] probe failed: {e}", flush=True)
    live = len(KEYS) - len(_dead_keys)
    print(f"[startup] {live}/{len(KEYS)} keys live", flush=True)
    if live == 0:
        raise SystemExit("No live keys available.")


# ============================================================================
# call_model
# ============================================================================

def call_model(
    model: str, system: str | None, user: str, max_tokens: int,
    extra_body: dict | None = None,
    seed: int | None = None,
    retries: int = 6, backoff: float = 5.0,
) -> tuple[str, dict]:
    messages = []
    if system: messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    last_err: Exception | None = None
    tried_dead: set = set()
    sem = _acquire_model_slot(model)
    with sem:
        for attempt in range(retries + 1):
            key = next_key(skip=tried_dead)
            if key is None:
                raise RuntimeError("All API keys exhausted")
            try:
                kwargs = dict(
                    model=model, messages=messages, max_tokens=max_tokens,
                    api_key=key, timeout=LITELLM_TIMEOUT,
                )
                if extra_body: kwargs["extra_body"] = extra_body
                if seed is not None: kwargs["seed"] = seed
                resp = litellm.completion(**kwargs)
                content = resp.choices[0].message.content  # type: ignore
                if not content:
                    content = getattr(resp.choices[0].message, "reasoning_content", None)  # type: ignore
                if not content:
                    raise ValueError(f"{model}: empty content + reasoning_content")
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
                # Per-key exhaustion or auth failure: mark dead and retry immediately on next key.
                if ("Key limit exceeded" in msg or '"code":403' in msg
                    or "User not found" in msg or '"code":401' in msg
                    or "AuthenticationError" in msg):
                    mark_dead(key)
                    tried_dead.add(key)
                    continue
                # Account-wide exhaustion: bail entirely.
                if "402" in msg or "Insufficient credits" in msg:
                    raise
                if attempt < retries:
                    # Cap backoff at ~3 minutes; jitter ±50% to avoid thundering herd.
                    wait = min(backoff * (2 ** attempt), 180.0)
                    wait *= (0.5 + random.random())
                    print(f"[{_ts()}] [retry] {model.split('/')[-1]} attempt {attempt+1}: {str(e)[:120]} — retry in {wait:.0f}s", flush=True)
                    time.sleep(wait)
        assert last_err is not None
        raise last_err


# ============================================================================
# Cost tracking
# ============================================================================

class CostTracker:
    def __init__(self, max_cost: float | None):
        self.max_cost = max_cost
        self._cost = 0.0; self._tokens_in = 0; self._tokens_out = 0
        self._lock = threading.Lock(); self._aborted = False

    def add(self, cost: float, in_tok: int, out_tok: int) -> None:
        with self._lock:
            self._cost += cost; self._tokens_in += in_tok; self._tokens_out += out_tok
            if self.max_cost is not None and self._cost >= self.max_cost and not self._aborted:
                self._aborted = True
                print(f"[{_ts()}] [KILLSWITCH] cum=${self._cost:.2f} >= cap=${self.max_cost:.2f}", flush=True)

    def aborted(self):
        with self._lock: return self._aborted

    def snapshot(self):
        with self._lock: return self._cost, self._tokens_in, self._tokens_out


def cost_for(model: str, total_tokens: int) -> float:
    p = PRICE_PER_MTOKEN.get(model, JUDGE_PRICE)
    return (p or 0.0) * total_tokens / 1_000_000


# ============================================================================
# Existing-branch reader
# ============================================================================

def load_existing_branch_counts() -> dict:
    """Return: {(source_experiment, model_id): {pid: branch_count}} from master jsonl.

    For ('scaling', gemma|gpt-oss) we fold in phase1 generate-condition branches
    on the 40 problems where the scaling source never ran — they're the same
    default-reasoning generations and were judged with v4flash, so they count.
    """
    counts: dict = {}
    phase1_generate_counts: dict = {}  # {model_id: {pid: count}}
    with open(DATASET, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            exp = r["experiment"]
            if exp in ("scaling", "scaling_reasoning", "scaling_v4flash"):
                key = (exp, r["model"])
                counts.setdefault(key, {})[r["problem_id"]] = len(r.get("branches") or [])
            elif exp == "phase1" and r.get("condition") == "generate":
                phase1_generate_counts.setdefault(r["model"], {})[r["problem_id"]] = len(r.get("branches") or [])

    # Fold phase1 generate into ('scaling', model) cells where scaling didn't run that pid.
    for model in (GEMMA, OSS):
        cell = counts.setdefault(("scaling", model), {})
        for pid, n in phase1_generate_counts.get(model, {}).items():
            if pid not in cell:
                cell[pid] = n  # reuse 3 phase1 branches
    return counts


# ============================================================================
# Cell plan
# ============================================================================

def parse_gt_score(v: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", v, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", v, re.I)
    if m: return int(m.group(1))
    return 0


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def build_workplan(problems: dict) -> list[dict]:
    """One row per (source, model, reasoning, pid, missing-branch-k)."""
    counts = load_existing_branch_counts()
    pids = sorted(problems.keys())

    cells = [
        # source_experiment, model, reasoning, extra_body
        ("scaling",           GEMMA, "default", None),
        ("scaling",           OSS,   "default", None),
        ("scaling_reasoning", OSS,   "max",     {"reasoning": {"effort": "high"}}),
        ("scaling_v4flash",   V4F,   "default", None),
    ]
    # gemma reasoning=max is already 70 × 9, skip.

    plan: list[dict] = []
    for src, model, rsn, extra in cells:
        cell_counts = counts.get((src, model), {})
        for pid in pids:
            existing = cell_counts.get(pid, 0)
            if existing >= TARGET_M:
                continue
            need = TARGET_M - existing
            for k in range(existing, TARGET_M):
                plan.append({
                    "source_experiment": src,
                    "model": model,
                    "reasoning": rsn,
                    "extra_body": extra,
                    "pid": pid,
                    "k": k,
                    "existing_in_dataset": existing,
                })
    return plan


# ============================================================================
# Generation worker
# ============================================================================

def branch_path(run_dir: Path, src: str, model: str, pid: str, k: int) -> Path:
    return run_dir / "branches" / src / model_short(model) / pid / f"k{k:02d}.json"


def already_done(run_dir: Path, src: str, model: str, pid: str, k: int) -> bool:
    p = branch_path(run_dir, src, model, pid, k)
    if not p.exists():
        return False
    try:
        with open(p, encoding="utf-8") as f:
            b = json.load(f)
        s = (b.get("judges") or {}).get("v4flash", {}).get("score")
        return isinstance(s, int) and not b.get("error")
    except Exception:
        return False


def run_unit(unit: dict, problems: dict, prompts: dict, run_dir: Path,
             tracker: CostTracker, manifest_lock: threading.Lock, mock: bool) -> dict:
    src   = unit["source_experiment"]
    model = unit["model"]
    pid   = unit["pid"]
    k     = unit["k"]
    extra = unit["extra_body"]
    ms    = model_short(model)
    tag   = f"[{_ts()}] [{src}|{ms}|{pid}|k={k}]"

    bp = branch_path(run_dir, src, model, pid, k)
    if bp.exists() and already_done(run_dir, src, model, pid, k):
        return {"unit": unit, "skipped": True}

    t0 = time.time()
    out: dict = {
        "k": k,
        "source_experiment": src,
        "model": model,
        "reasoning": unit["reasoning"],
        "problem_id": pid,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    cost = 0.0
    try:
        problem = problems[pid]
        # Generate
        if mock:
            sol = "## Summary\n**Verdict:** Solved\nMock proof.\n\\boxed{42}"
            gen_usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        else:
            sol, gen_usage = call_model(
                model, prompts["generator"], problem["text"],
                MAX_TOKENS_GEN, extra_body=extra, seed=k * 7 + hash(pid) % 9973,
            )
        gc = cost_for(model, gen_usage["total_tokens"])
        tracker.add(gc, gen_usage["prompt_tokens"], gen_usage["completion_tokens"])
        cost += gc

        # Judge
        if mock:
            verdict = "<points>7 out of 7</points>\nMock judge."
            j_usage = {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230}
        else:
            judge_user = (prompts["judge_gt"]
                          .replace("{problem}", problem["text"])
                          .replace("{ground_truth}", problem["ground_truth"])
                          .replace("{candidate}", sol))
            verdict, j_usage = call_model(JUDGE_V4FLASH, "", judge_user, MAX_TOKENS_JUDGE)
        jc = cost_for(JUDGE_V4FLASH, j_usage["total_tokens"])
        tracker.add(jc, j_usage["prompt_tokens"], j_usage["completion_tokens"])
        cost += jc

        score = parse_gt_score(verdict)
        elapsed = round(time.time() - t0, 2)

        out.update({
            "solution": sol,
            "judges": {
                "v4flash": {"score": score, "verdict": verdict, "source": EXPERIMENT_NAME},
            },
            "gen_usage": gen_usage,
            "judge_usage": j_usage,
            "cost_usd": round(cost, 6),
            "elapsed_s": elapsed,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"{tag} score={score}  ${cost:.4f}  {elapsed}s", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        traceback.print_exc()
        out.update({
            "error": str(e),
            "cost_usd": round(cost, 6),
            "elapsed_s": elapsed,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"{tag} ERROR {e}  ${cost:.4f}", flush=True)

    bp.parent.mkdir(parents=True, exist_ok=True)
    tmp = bp.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    tmp.replace(bp)

    summary = {
        "ts": out["completed_at"],
        "source": src, "model": ms, "pid": pid, "k": k,
        "score": (out.get("judges") or {}).get("v4flash", {}).get("score"),
        "cost_usd": out.get("cost_usd"), "error": out.get("error"),
    }
    with manifest_lock:
        with open(run_dir / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")
    return {"unit": unit, "result": out}


# ============================================================================
# Main
# ============================================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--from-run-id", default=None)
    p.add_argument("--max-cost", type=float, default=None)
    p.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    p.add_argument("--limit", type=int, default=None,
                   help="Limit number of units (for testing).")
    args = p.parse_args()

    litellm.request_timeout = LITELLM_TIMEOUT

    if not args.mock:
        _probe_keys()

    problems = load_70_problems()
    plan = build_workplan(problems)

    if args.smoke:
        plan = plan[:6]
    if args.limit:
        plan = plan[:args.limit]

    # Shuffle deterministically so workers see model variety from the start —
    # otherwise the first 300 gemma units saturate the semaphore and 38/50
    # workers block on it idle.
    random.Random(20260507).shuffle(plan)

    # Stats
    by_cell: dict = {}
    for u in plan:
        key = (u["source_experiment"], model_short(u["model"]), u["reasoning"])
        by_cell.setdefault(key, 0)
        by_cell[key] += 1
    print(f"\n=== Workplan: {len(plan)} (gen+judge) units ===")
    for k, v in sorted(by_cell.items()):
        print(f"  {k} -> {v} new branches")
    print()

    run_id = args.from_run_id or _now_id()
    suffix = "_mock" if args.mock else ("_smoke" if args.smoke else "")
    run_dir = RESULTS_DIR / f"{EXPERIMENT_NAME}_{run_id}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts = {
        "generator": load_prompt("generator.md"),
        "judge_gt":  load_prompt("judge_gt.md"),
    }

    print(f"Run dir:    {run_dir}")
    print(f"Workers:    {args.max_workers}")
    print(f"Cost cap:   ${args.max_cost}")
    print(f"Keys:       {len(KEYS)} rotated")
    print()

    tracker = CostTracker(args.max_cost)
    manifest_lock = threading.Lock()

    pending = [u for u in plan if not already_done(run_dir, u["source_experiment"], u["model"], u["pid"], u["k"])]
    skipped = len(plan) - len(pending)
    print(f"Pending: {len(pending)}   already-done (resume): {skipped}")
    if not pending:
        print("Nothing to do."); return

    t0 = time.time()
    completed = 0
    last_print = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = {}
        for u in pending:
            if tracker.aborted(): break
            futs[ex.submit(run_unit, u, problems, prompts, run_dir, tracker, manifest_lock, args.mock)] = u
        for fut in concurrent.futures.as_completed(futs):
            u = futs[fut]
            completed += 1
            try:
                fut.result()
            except Exception as e:
                print(f"[{_ts()}] FAILED [{u['source_experiment']}|{model_short(u['model'])}|{u['pid']}|k={u['k']}]: {e}", flush=True)
            now = time.time()
            if completed % 20 == 0 or now - last_print > 60:
                cum, in_t, out_t = tracker.snapshot()
                print(f"[{_ts()}] Progress {completed}/{len(pending)}  cum=${cum:.2f}  in={in_t:,} out={out_t:,}", flush=True)
                last_print = now

    elapsed = round(time.time() - t0, 1)
    cum, in_t, out_t = tracker.snapshot()
    print(f"\nWall: {elapsed}s   Cumulative: ${cum:.2f}   in={in_t:,}  out={out_t:,}")
    print(f"Run dir: {run_dir}")


if __name__ == "__main__":
    main()
