#!/usr/bin/env python3
"""
Re-judge Phase 3 trials whose v4-pro regrade was truncated mid-reasoning.

Background: regrade_phase3_v4pro_20260505 used max_tokens=65536 but observed
truncation at ~22-25K out_tokens. v4-pro's reasoning budget is service-capped
below what we requested, so reasoning consumed the budget before final-content
emission of the `<points>` tag.

Fix: use OpenRouter's `reasoning` config to explicitly request a larger
reasoning budget (`max_tokens: 100000`) on top of `max_tokens=131072` total.

Source list: /tmp/truncated_trials.json (auto-generated from prior regrade)
Output:      replaces files in
             experiments/results/regrade_phase3_v4pro_20260505_043627/<pid>.json
             (atomically, only after the new judge succeeds and parses cleanly)
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
MAX_TOKENS = 131072
REASONING_BUDGET = 100000   # explicit reasoning_max via OpenRouter
TIMEOUT = 3600              # 60 min — these calls are heavy
MAX_WORKERS = 12

PHASE3_TRIALS = (
    Path(__file__).parent / "results"
    / "seed_full_v4flash_phase3_20260505_20260505_021635"
    / "seed_full" / "deepseek-v4-flash"
)
REGRADE_DIR = (
    Path(__file__).parent / "results"
    / "regrade_phase3_v4pro_20260505_043627"
)
TRUNC_LIST = Path("/tmp/truncated_trials.json")


def parse_score(text: str) -> int | None:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    if m: return int(m.group(1))
    return None


def regrade_one(judge_prompt: str, problems: dict, pid: str) -> dict:
    trial_path = PHASE3_TRIALS / f"{pid}.json"
    with open(trial_path, encoding="utf-8") as f:
        trial = json.load(f)
    prob = problems[pid]
    user = (judge_prompt
            .replace("{problem}",      prob["text"])
            .replace("{ground_truth}", prob["ground_truth"])
            .replace("{candidate}",    trial["best_solution"]))

    t0 = time.time()
    try:
        resp = litellm.completion(
            model=JUDGE,
            messages=[{"role": "user", "content": user}],
            max_tokens=MAX_TOKENS,
            api_key=KEY,
            timeout=TIMEOUT,
            extra_body={"reasoning": {"max_tokens": REASONING_BUDGET}},
        )
        msg = resp.choices[0].message
        text = msg.content
        if not text:
            text = getattr(msg, "reasoning_content", "") or ""
        usage = getattr(resp, "usage", None)
        in_tok  = int(getattr(usage, "prompt_tokens", 0) or 0)
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
        score = parse_score(text)
        cost = JUDGE_PRICE * (in_tok + out_tok) / 1_000_000
        elapsed = round(time.time() - t0, 1)

        has_tag = bool(re.search(r"<points>\s*\d+\s*out of 7\s*</points>", text, re.I))
        status = "OK" if has_tag else "STILL_TRUNCATED"
        gem = trial.get("score")
        delta = (score - (gem or 0)) if score is not None else None
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] {pid:<28} "
            f"out_tok={out_tok:>5}  len(v)={len(text):>6}  "
            f"gem={gem}/7 v4pro={score}/7  Δ={delta:+d}  ${cost:.4f}  "
            f"{elapsed}s  [{status}]",
            flush=True,
        )

        rec = {
            "problem_id":    pid,
            "model":         trial["model"],
            "is_special_10": trial.get("is_special", False),
            "gemini_score":  trial.get("score"),
            "v4pro_score":   score if has_tag else None,
            "v4pro_verdict": text,
            "cost_usd":      round(cost, 6),
            "elapsed_s":     elapsed,
            "in_tokens":     in_tok,
            "out_tokens":    out_tok,
            "rejudge":       True,
            "rejudge_reason": "truncated_in_first_pass",
            "still_truncated": not has_tag,
            "completed_at":  datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        print(f"[ERROR] {pid}: {e}", flush=True)
        rec = {
            "problem_id":   pid,
            "model":        trial.get("model"),
            "gemini_score": trial.get("score"),
            "v4pro_score":  None,
            "error":        str(e),
            "elapsed_s":    elapsed,
            "rejudge":      True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    out_path = REGRADE_DIR / f"{pid}.json"
    tmp = out_path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    tmp.replace(out_path)
    return rec


def main():
    pids = json.loads(TRUNC_LIST.read_text())["pids"]
    problems = load_70_problems()
    judge_prompt = (PROMPTS / "judge_gt.md").read_text(encoding="utf-8").strip()

    print(f"Re-judging {len(pids)} truncated trials with reasoning_budget={REASONING_BUDGET}, "
          f"max_tokens={MAX_TOKENS}", flush=True)
    print(f"Output dir: {REGRADE_DIR}\n", flush=True)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(lambda p: regrade_one(judge_prompt, problems, p), pids))
    wall = round(time.time() - t0, 1)
    cost = sum(r.get("cost_usd", 0) or 0 for r in results)
    fixed = sum(1 for r in results if r.get("v4pro_score") is not None)
    still_trunc = sum(1 for r in results if r.get("still_truncated"))
    print(f"\nDone. Wall {wall}s. Cost ${cost:.3f}.")
    print(f"Fixed: {fixed}/{len(results)}  Still truncated: {still_trunc}")


if __name__ == "__main__":
    main()
