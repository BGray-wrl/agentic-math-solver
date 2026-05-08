#!/usr/bin/env python3
"""
Backfill missing v4flash judge scores on the 5 phase1 generate-condition
branches that were never v4flash-graded. Without these, the pass@9
enumeration drops those 5 pids (any subset including a None score is skipped).

Outputs a JSON sidecar at:
  experiments/results/extend_scaling_pass9_20260507_<runid>/phase1_v4flash_backfill.json
The merger reads this sidecar (after we wire it in) to fill the missing scores.

Usage:
  uv run experiments/backfill_phase1_v4flash_20260507.py --run-dir <run-dir>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

ROOT = Path(__file__).parent.parent
DATASET = ROOT / "results" / "dataset_20260505.jsonl"
PROMPTS_DIR = ROOT / "prompts" / "pipeline"

JUDGE = "openrouter/deepseek/deepseek-v4-flash"
MAX_TOKENS = 32768
TIMEOUT = 1800

load_dotenv()
KEYS = [v for k, v in os.environ.items() if k.startswith("OPENROUTER_API_KEY") and v]


def parse_score(v: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", v, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", v, re.I)
    if m: return int(m.group(1))
    return 0


def judge(problem_text: str, ground_truth: str, candidate: str, judge_prompt: str) -> tuple[int, str]:
    user = (judge_prompt
            .replace("{problem}", problem_text)
            .replace("{ground_truth}", ground_truth)
            .replace("{candidate}", candidate))
    last_err = None
    for k in KEYS:
        try:
            resp = litellm.completion(
                model=JUDGE, messages=[{"role": "user", "content": user}],
                max_tokens=MAX_TOKENS, api_key=k, timeout=TIMEOUT,
            )
            text = resp.choices[0].message.content  # type: ignore
            if not text:
                text = getattr(resp.choices[0].message, "reasoning_content", "")  # type: ignore
            return parse_score(text or ""), text or ""
        except Exception as e:
            last_err = e
            if "402" in str(e) or "Insufficient credits" in str(e):
                raise
    raise last_err  # type: ignore


def find_missing() -> list[tuple]:
    """Returns list of (model_id, pid, k, problem_text, ground_truth, candidate_solution)."""
    out: list[tuple] = []
    with open(DATASET, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["experiment"] != "phase1" or r.get("condition") != "generate":
                continue
            ms = r["model"].split("/")[-1]
            if ms not in ("gemma-4-31b-it", "gpt-oss-120b"):
                continue
            for b in r.get("branches") or []:
                v4f = (b.get("judges") or {}).get("v4flash", {}).get("score")
                if v4f is None:
                    sol = b.get("final_solution") or b.get("solution") or b.get("initial_solution")
                    out.append((r["model"], r["problem_id"], b["k"],
                                r["problem_text"], r["ground_truth"], sol))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    args = p.parse_args()
    run_dir = Path(args.run_dir)

    judge_prompt = (PROMPTS_DIR / "judge_gt.md").read_text(encoding="utf-8").strip()

    todo = find_missing()
    print(f"Missing v4flash scores: {len(todo)}")
    out_path = run_dir / "phase1_v4flash_backfill.json"
    backfill: dict = {}
    for i, (model, pid, k, ptext, gt, sol) in enumerate(todo):
        ms = model.split("/")[-1]
        key = f"{model}|{pid}|{k}"
        print(f"[{i+1}/{len(todo)}] {key}", flush=True)
        if not sol:
            print("  no solution text — skipping")
            continue
        t0 = time.time()
        score, verdict = judge(ptext, gt, sol, judge_prompt)
        backfill[key] = {
            "score": score, "verdict": verdict, "source": "backfill_phase1_v4flash_20260507",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"  score={score}  ({time.time()-t0:.1f}s)")
        # Save incrementally
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(backfill, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
