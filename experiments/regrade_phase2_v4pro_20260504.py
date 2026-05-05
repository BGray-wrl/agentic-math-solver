#!/usr/bin/env python3
"""
Regrade Phase 2 frontier breakthrough branches with deepseek-v4-pro
to sanity-check whether gemini-3-flash judge was lenient.

Source: experiments/results/seed_full_phase2_20260504_20260505_002924/frontier_branches.jsonl
Output: experiments/results/regrade_phase2_v4pro_<TS>.json
Key:    OPENROUTER_API_KEY_seedgen (single, no rotation)
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import sys
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
MAX_TOKENS = 65536
TIMEOUT = 1800

FRONTIER = (
    Path(__file__).parent
    / "results"
    / "seed_full_phase2_20260504_20260505_002924"
    / "frontier_branches.jsonl"
)

OUT_DIR = Path(__file__).parent / "results"
OUT_DIR.mkdir(exist_ok=True)


def parse_score(text: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    if m: return int(m.group(1))
    return 0


def regrade(problems: dict, judge_prompt: str, row: dict) -> dict:
    pid = row["problem_id"]
    prob = problems[pid]
    user = (judge_prompt
            .replace("{problem}", prob["text"])
            .replace("{ground_truth}", prob["ground_truth"])
            .replace("{candidate}", row["solution"]))
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
        score = parse_score(text)
        cost = JUDGE_PRICE * (in_tok + out_tok) / 1_000_000
        elapsed = round(time.time() - t0, 1)
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] {row['model'].split('/')[-1]:<15} "
            f"{pid:<25} idx={row['idea_idx']}  gemini={row['score']}/7  v4pro={score}/7  "
            f"${cost:.4f}  {elapsed}s",
            flush=True,
        )
        return {
            "model":       row["model"],
            "problem_id":  pid,
            "idea_idx":    row["idea_idx"],
            "idea":        row.get("idea"),
            "gemini_score": row["score"],
            "v4pro_score":  score,
            "v4pro_verdict": text,
            "cost_usd":    round(cost, 6),
            "elapsed_s":   elapsed,
            "in_tokens":   in_tok,
            "out_tokens":  out_tok,
        }
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        print(f"[ERROR] {pid} idx={row['idea_idx']}: {e}", flush=True)
        return {
            "model":      row["model"],
            "problem_id": pid,
            "idea_idx":   row["idea_idx"],
            "gemini_score": row["score"],
            "v4pro_score": None,
            "error":      str(e),
            "elapsed_s":  elapsed,
        }


def main():
    rows = [json.loads(l) for l in open(FRONTIER)]
    print(f"Regrading {len(rows)} frontier branches with {JUDGE}", flush=True)
    problems = load_70_problems()
    judge_prompt = (PROMPTS / "judge_gt.md").read_text(encoding="utf-8").strip()

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(rows)) as ex:
        results = list(ex.map(lambda r: regrade(problems, judge_prompt, r), rows))
    elapsed = round(time.time() - t0, 1)
    total_cost = sum(r.get("cost_usd", 0) or 0 for r in results)
    print(f"\nDone. Wall {elapsed}s. Cost ${total_cost:.3f}.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"regrade_phase2_v4pro_{ts}.json"
    with open(out, "w") as f:
        json.dump({
            "judge":     JUDGE,
            "wall_s":    elapsed,
            "total_cost_usd": round(total_cost, 4),
            "n":         len(results),
            "results":   results,
        }, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out}")

    # Quick agreement table
    print("\n" + "="*80)
    print(f"{'Model':<15} {'Problem':<25} idx  gemini  v4pro  Δ")
    print("="*80)
    for r in results:
        if r.get("v4pro_score") is None: continue
        ms = r["model"].split("/")[-1]
        d = r["v4pro_score"] - r["gemini_score"]
        print(f"  {ms:<13} {r['problem_id']:<25} {r['idea_idx']:>3}  {r['gemini_score']:>6}  {r['v4pro_score']:>5}  {d:+d}")


if __name__ == "__main__":
    main()
