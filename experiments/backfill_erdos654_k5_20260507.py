#!/usr/bin/env python3
"""
Backfill the single missing scaling_v4flash branch: erdos-654 / k=5 / deepseek-v4-flash.
The original scaling_v4flash run had a failed generation here; the extension run
counted the slot as filled (length-7 list with None) and skipped it.

Generates one candidate solution + v4flash judge score and writes it as a new
branch in the extend-scaling run dir so the merger picks it up next rebuild.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

import litellm  # noqa: E402

from problemset_70 import load_70_problems  # noqa: E402

PID = "erdos-654"
K = 5
GEN = "openrouter/deepseek/deepseek-v4-flash"
JUDGE = "openrouter/deepseek/deepseek-v4-flash"
RUN_DIR = ROOT / "experiments" / "results" / "extend_scaling_pass9_20260507_20260507_090106"
PROMPTS_DIR = ROOT / "prompts" / "pipeline"

load_dotenv()
KEYS = [v for k, v in os.environ.items() if k.startswith("OPENROUTER_API_KEY") and v]


def parse_score(v):
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", v, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", v, re.I)
    if m: return int(m.group(1))
    return 0


def call(model, system, user, max_tokens):
    last = None
    for k in KEYS:
        try:
            kw = dict(model=model, messages=[], max_tokens=max_tokens, api_key=k, timeout=1800)
            if system: kw["messages"].append({"role": "system", "content": system})
            kw["messages"].append({"role": "user", "content": user})
            resp = litellm.completion(**kw)
            content = resp.choices[0].message.content
            if not content:
                content = getattr(resp.choices[0].message, "reasoning_content", None)
            if not content:
                raise ValueError("empty content")
            return content
        except Exception as e:
            last = e
            if "402" in str(e): raise
    raise last


def main():
    p = load_70_problems()[PID]
    gen_prompt = (PROMPTS_DIR / "generator.md").read_text(encoding="utf-8").strip()
    judge_prompt = (PROMPTS_DIR / "judge_gt.md").read_text(encoding="utf-8").strip()

    print(f"Generating {PID} k={K} with {GEN}...", flush=True)
    t0 = time.time()
    sol = call(GEN, gen_prompt, p["text"], 65536)
    print(f"  gen done ({time.time()-t0:.1f}s, {len(sol)} chars)", flush=True)

    print(f"Judging with {JUDGE}...", flush=True)
    t0 = time.time()
    judge_user = (judge_prompt
                  .replace("{problem}", p["text"])
                  .replace("{ground_truth}", p["ground_truth"])
                  .replace("{candidate}", sol))
    verdict = call(JUDGE, "", judge_user, 32768)
    score = parse_score(verdict)
    print(f"  judge done ({time.time()-t0:.1f}s, score={score})", flush=True)

    # Save in the extend_scaling branch tree under "scaling_v4flash" source so merger picks it up.
    out = {
        "k": K,
        "source_experiment": "scaling_v4flash",
        "model": GEN,
        "reasoning": "default",
        "problem_id": PID,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "solution": sol,
        "judges": {"v4flash": {"score": score, "verdict": verdict, "source": "backfill_erdos654_k5_20260507"}},
    }
    target = RUN_DIR / "branches" / "scaling_v4flash" / "deepseek-v4-flash" / PID / f"k{K:02d}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
