#!/usr/bin/env python3
"""
Method B regrade: re-judge each Phase 2 trial's best_solution with v4-pro.

Why: gemini-3-flash and v4-pro disagree systematically on revised solutions
(Phase 2 frontier-only regrade showed mean Δ = -6.7).  This regrade lets us
report a true v4-pro mean for the seed_full mode on all 70 problems × 2 cheap
models, comparable to Phase 1's v4-pro means.

Costs: empirical projection $1.5-2.5.  Hard cost cap of $10 wired in.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import litellm
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from problemset_70 import load_70_problems

load_dotenv()
KEY = os.getenv("OPENROUTER_API_KEY_seedgen")
if not KEY:
    raise SystemExit("OPENROUTER_API_KEY_seedgen not set")

ROOT = Path(__file__).parent.parent
PROMPTS = ROOT / "prompts" / "pipeline"
JUDGE = "openrouter/deepseek/deepseek-v4-pro"
JUDGE_PRICE = 0.87
MAX_TOKENS = 32000      # half of the original 65K — caps long-tail without hurting normal calls
TIMEOUT = 1800

PHASE2_DIR = (
    Path(__file__).parent
    / "results"
    / "seed_full_phase2_20260504_20260505_002924"
    / "seed_full"
)
OUT_DIR = Path(__file__).parent / "results"


def parse_score(text: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    if m: return int(m.group(1))
    return 0


class CostCap:
    def __init__(self, cap: float):
        self.cap = cap
        self.cum = 0.0
        self.lock = threading.Lock()
        self.aborted = False
    def add(self, c: float) -> bool:
        with self.lock:
            self.cum += c
            if self.cum >= self.cap and not self.aborted:
                self.aborted = True
                print(f"[KILL] cum cost ${self.cum:.2f} >= cap ${self.cap} — no new submissions", flush=True)
            return not self.aborted


def regrade_one(problems, judge_prompt, trial: dict, cap: CostCap) -> dict:
    if cap.aborted:
        return {**_meta(trial), "skipped": "cost_cap"}
    pid = trial["problem_id"]
    prob = problems[pid]
    candidate = trial.get("best_solution") or ""
    if not candidate:
        return {**_meta(trial), "v4pro_score": None, "error": "no best_solution"}
    user = (judge_prompt
            .replace("{problem}", prob["text"])
            .replace("{ground_truth}", prob["ground_truth"])
            .replace("{candidate}", candidate))
    t0 = time.time()
    try:
        resp = litellm.completion(
            model=JUDGE,
            messages=[{"role": "user", "content": user}],
            max_tokens=MAX_TOKENS,
            api_key=KEY,
            timeout=TIMEOUT,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        in_tok  = int(getattr(usage, "prompt_tokens", 0) or 0)
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = JUDGE_PRICE * (in_tok + out_tok) / 1_000_000
        cap.add(cost)
        score = parse_score(text)
        elapsed = round(time.time() - t0, 1)
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] {trial['model'].split('/')[-1]:<15} "
            f"{pid:<25} gemini={trial.get('score'):>2}/7  v4pro={score}/7  "
            f"${cost:.4f}  cum=${cap.cum:.2f}  {elapsed}s",
            flush=True,
        )
        return {
            **_meta(trial),
            "gemini_score": trial.get("score"),
            "v4pro_score":  score,
            "v4pro_verdict": text,
            "cost_usd":    round(cost, 6),
            "elapsed_s":   elapsed,
            "in_tokens":   in_tok,
            "out_tokens":  out_tok,
        }
    except Exception as e:
        return {**_meta(trial), "v4pro_score": None, "error": str(e)}


def _meta(trial: dict) -> dict:
    return {
        "model":       trial["model"],
        "problem_id":  trial["problem_id"],
        "is_special":  trial.get("is_special", False),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max-cost", type=float, default=10.0)
    p.add_argument("--workers", type=int, default=20)
    args = p.parse_args()

    trials: list[dict] = []
    for f in sorted(PHASE2_DIR.rglob("*.json")):
        with open(f) as fh:
            trials.append(json.load(fh))
    valid = [t for t in trials if not t.get("error") and t.get("best_solution")]
    print(f"Phase 2 trials loaded: {len(trials)} (with best_solution: {len(valid)})", flush=True)
    print(f"Cost cap: ${args.max_cost}  workers={args.workers}  max_tokens={MAX_TOKENS}", flush=True)

    problems = load_70_problems()
    judge_prompt = (PROMPTS / "judge_gt.md").read_text(encoding="utf-8").strip()
    cap = CostCap(args.max_cost)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(lambda r: regrade_one(problems, judge_prompt, r, cap), valid))
    elapsed = round(time.time() - t0, 1)

    completed = [r for r in results if r.get("v4pro_score") is not None]
    skipped   = [r for r in results if r.get("skipped") == "cost_cap"]
    errors    = [r for r in results if r.get("error")]
    print(f"\nDone. Wall {elapsed}s. Cum cost ${cap.cum:.3f}.")
    print(f"  completed: {len(completed)}  skipped (cap): {len(skipped)}  errors: {len(errors)}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"regrade_phase2_full_v4pro_{ts}.json"
    with open(out, "w") as f:
        json.dump({
            "judge":      JUDGE,
            "n_target":   len(valid),
            "n_done":     len(completed),
            "wall_s":     elapsed,
            "total_cost_usd": round(cap.cum, 4),
            "max_cost":   args.max_cost,
            "results":    results,
        }, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out}")

    # Summary by model
    print("\n" + "="*80)
    print(f"{'Model':<18} {'n':>3} {'gemini':>7} {'v4pro':>6} {'Δ':>6}")
    print("="*80)
    for m in sorted(set(r["model"] for r in completed)):
        ms = m.split("/")[-1]
        rs = [r for r in completed if r["model"]==m]
        gm = sum(r["gemini_score"] for r in rs) / len(rs)
        vm = sum(r["v4pro_score"] for r in rs) / len(rs)
        print(f"  {ms:<16} {len(rs):>3} {gm:>7.2f} {vm:>6.2f} {vm-gm:>+6.2f}")


if __name__ == "__main__":
    main()
