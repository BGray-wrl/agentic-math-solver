#!/usr/bin/env python3
"""
Audit + re-judge truncated v4-pro escalations from the role-swap experiment.

Two known v4-pro silent-failure modes (per memory feedback_v4pro_judge_calls):
  1. Output goes to `message.reasoning_content` (not `message.content`) — already handled
     in the main script's call_model.
  2. Reasoning budget exhaustion: with max_tokens=65536 alone, v4-pro on long judge prompts
     (long ground truth + long candidate) burns reasoning tokens and never emits the final
     `<points>` tag. Verdict ends mid-sentence; parser silently scores 0.

This script:
  - Walks per-branch JSONs in role-swap run dir
  - Identifies branches where judge.escalated == True AND the escalate_verdict either
    (a) lacks `<points>...out of 7</points>` regex, or
    (b) is suspiciously long (>20K chars — typical of reasoning-overflow) AND lacks the tag,
        OR ends mid-sentence (no terminal punctuation in last 80 chars)
  - Re-judges those with hardened config: max_tokens=131072,
    extra_body={"reasoning": {"max_tokens": 100000}}
  - Atomically updates the branch JSON (and the parent trial JSON) with the new score/verdict

Usage:
  uv run experiments/regrade_role_swap_truncated_20260505.py --dry-run
  uv run experiments/regrade_role_swap_truncated_20260505.py --max-cost 5
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

sys.path.insert(0, str(Path(__file__).parent))

import litellm  # noqa: E402

# ============================================================================
# Configuration
# ============================================================================

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"

# Most recent role-swap run dir.
RUN_DIR = RESULTS_DIR / "seed_full_role_swap_20260505_20260505_032032"

JUDGE_MODEL  = "openrouter/deepseek/deepseek-v4-pro"
JUDGE_PRICE  = 0.87  # $/Mtok

MAX_TOKENS_TOTAL    = 131072
REASONING_BUDGET    = 100000
LITELLM_TIMEOUT     = 1800

# ============================================================================
# Auth
# ============================================================================

load_dotenv()
KEY = os.getenv("OPENROUTER_API_KEY_X")
if not KEY:
    raise SystemExit("OPENROUTER_API_KEY_X not set in .env")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ============================================================================
# Hardened v4-pro judge call
# ============================================================================

def parse_score(verdict: str) -> int | None:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m: return int(m.group(1))
    return None


def call_v4pro_hardened(judge_prompt: str, retries: int = 2):
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = litellm.completion(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": judge_prompt}],
                max_tokens=MAX_TOKENS_TOTAL,
                api_key=KEY,
                timeout=LITELLM_TIMEOUT,
                extra_body={"reasoning": {"max_tokens": REASONING_BUDGET}},
            )
            msg = resp.choices[0].message  # type: ignore
            text = msg.content
            if not text:
                text = getattr(msg, "reasoning_content", "") or ""
            if not text:
                raise ValueError("v4-pro returned empty content + empty reasoning_content")
            usage = getattr(resp, "usage", None)
            in_tok  = int(getattr(usage, "prompt_tokens", 0) or 0)
            out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
            cost = JUDGE_PRICE * (in_tok + out_tok) / 1_000_000
            return text, cost, {"in": in_tok, "out": out_tok}
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(5 * (2 ** attempt))
    raise last_err


# ============================================================================
# Audit
# ============================================================================

def looks_truncated(verdict: str) -> tuple[bool, str]:
    """Return (is_truncated, reason)."""
    if not verdict:
        return True, "empty verdict"
    has_tag = bool(re.search(r"<points>\s*\d+\s*out of 7\s*</points>", verdict, re.I))
    has_fallback = bool(re.search(r"\b[0-7]\s*(?:/\s*7|out of 7)", verdict, re.I))
    if has_tag:
        return False, "has <points> tag"
    if has_fallback:
        return False, "has fallback X/7 tag"
    # Neither — either short complete reject (rare) or truncated reasoning
    if len(verdict) > 5000:
        return True, f"long verdict ({len(verdict)} chars) without tag — reasoning overflow"
    if len(verdict) < 200:
        return True, f"very short verdict ({len(verdict)} chars) without tag"
    # Mid-length, no tag — treat as truncated (better safe than sorry)
    return True, f"verdict ({len(verdict)} chars) without any score tag"


def find_truncated() -> list[dict]:
    suspect = []
    for branch_path in sorted((RUN_DIR / "branches").rglob("branch_*.json")):
        try:
            with open(branch_path) as f:
                b = json.load(f)
        except Exception:
            continue
        j = b.get("judge", {})
        if not j.get("escalated"):
            continue
        verdict = j.get("escalate_verdict") or ""
        bad, reason = looks_truncated(verdict)
        if bad:
            suspect.append({
                "branch_path": str(branch_path),
                "condition":   branch_path.parent.parent.parent.name if "branches" in branch_path.parts else "?",
                "reason":      reason,
                "old_score":   j.get("escalate_score"),
                "primary_score": j.get("primary_score"),
                "verdict_len": len(verdict),
            })
    return suspect


# ============================================================================
# Re-judge + write
# ============================================================================

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def regrade_one(suspect: dict, judge_template: str, problems: dict, dry_run: bool) -> dict:
    bp = Path(suspect["branch_path"])
    with open(bp) as f:
        branch = json.load(f)
    pid = bp.parent.name
    prob = problems.get(pid)
    if not prob:
        return {**suspect, "error": f"unknown problem {pid}"}
    candidate = branch.get("final_solution") or branch.get("initial_solution") or ""
    if not candidate:
        return {**suspect, "error": "no candidate solution to judge"}
    user = (judge_template
            .replace("{problem}",      prob["text"])
            .replace("{ground_truth}", prob["ground_truth"])
            .replace("{candidate}",    candidate))

    if dry_run:
        return {**suspect, "would_regrade": True}

    text, cost, usage = call_v4pro_hardened(user)
    score = parse_score(text)
    branch["judge"]["escalate_verdict"] = text
    branch["judge"]["escalate_score"]   = score
    branch["judge"]["regraded_at"]      = datetime.now(timezone.utc).isoformat()
    branch["judge"]["regrade_usage"]    = usage
    if score is not None:
        branch["score"]   = score
        branch["verdict"] = text
    tmp = bp.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(branch, f, indent=2, ensure_ascii=False)
    tmp.replace(bp)
    return {**suspect, "new_score": score, "cost": cost, "verdict_len_new": len(text)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-cost", type=float, default=10.0)
    args = p.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from problemset_70 import load_70_problems
    problems = load_70_problems()

    print(f"[{_ts()}] scanning {RUN_DIR.name} for truncated v4-pro escalations...")
    suspects = find_truncated()
    print(f"[{_ts()}] found {len(suspects)} suspect branches")
    for s in suspects[:20]:
        print(f"  {s['branch_path'].split('branches/')[-1]:<60}  old={s['old_score']}  ({s['reason']})")

    if not suspects:
        print("nothing to do.")
        return

    if args.dry_run:
        print(f"[{_ts()}] dry-run: would regrade {len(suspects)} branches")
        return

    judge_template = load_prompt("judge_gt.md")
    cum = 0.0
    n_changed = 0
    for i, s in enumerate(suspects):
        if cum >= args.max_cost:
            print(f"[{_ts()}] killswitch at ${cum:.2f}, stopping")
            break
        try:
            r = regrade_one(s, judge_template, problems, dry_run=False)
            cum += r.get("cost", 0)
            old, new = r["old_score"], r.get("new_score")
            print(f"[{_ts()}] {i+1}/{len(suspects)}  {Path(r['branch_path']).parent.name}  "
                  f"old={old} -> new={new}  ${cum:.2f}")
            if old != new:
                n_changed += 1
        except Exception as e:
            print(f"[{_ts()}] ERROR on {s['branch_path']}: {e}")

    print(f"\n[{_ts()}] regrade done. {n_changed} of {len(suspects)} scores changed. cum cost ${cum:.2f}")


if __name__ == "__main__":
    main()
