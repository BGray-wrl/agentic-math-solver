#!/usr/bin/env python3
"""
Audit closure: re-judge the 11 Phase 1 cheap-model trials whose v4-pro judge call
returned no parseable score (silently became 0).  Confirms whether those silent
zeros mask real >0 scores that would shift the Phase 1 v4-pro means I cited.
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
JUDGE = "openrouter/deepseek/deepseek-v4-pro"
MAX_TOKENS = 32000
TIMEOUT = 1800

ROOT = Path(__file__).parent.parent
PROMPTS = ROOT / "prompts" / "pipeline"
P1_DIR = ROOT / "experiments" / "results" / "seed_ideas_full_compare_20260504_20260504_101225"

CHEAP = {"openrouter/openai/gpt-oss-120b", "openrouter/google/gemma-4-31b-it"}

def has_points_tag(t): return bool(re.search(r"<points>\s*\d+\s*out of 7\s*</points>", t or "", re.I))
def has_alt_score(t): return bool(re.search(r"\b[0-7]\s*(?:/\s*7|out of 7)", t or "", re.I))
def parse_score(t):
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", t or "", re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", t or "", re.I)
    if m: return int(m.group(1))
    return None


def collect_targets():
    """Find every (model, problem, mode, branch_idx) where v4-pro silently scored 0."""
    targets = []
    for f in P1_DIR.rglob("*.json"):
        if f.parent == P1_DIR: continue
        try: t = json.load(open(f))
        except: continue
        if not isinstance(t, dict): continue
        if t.get("model") not in CHEAP: continue
        if t.get("error"): continue

        # Identify each judge call's status
        judge_calls = [c for c in t.get("calls", []) or []
                       if c.get("kind") == "judge" and c.get("model") == JUDGE]
        # In Phase 1 schema, judge calls are appended in branch order for generate/seed_generate
        # (one per branch), or just one for full.  We re-judge each problematic one against the
        # corresponding branch's solution.
        branches = t.get("branches", []) or []
        for idx, c in enumerate(judge_calls):
            txt = c.get("response_text") or ""
            if has_points_tag(txt) or has_alt_score(txt):
                continue
            if t["mode"] == "full":
                # Solution = best_solution
                cand = t.get("best_solution") or ""
                branch_label = "full"
            else:
                # Generate / seed_generate: judge call idx -> branch idx (assuming order preserved)
                if idx < len(branches):
                    cand = branches[idx].get("solution") or ""
                else:
                    cand = t.get("best_solution") or ""
                branch_label = f"branch{idx}"
            if not cand:
                continue
            targets.append({
                "model":      t["model"],
                "problem_id": t["problem_id"],
                "mode":       t["mode"],
                "branch":     branch_label,
                "branch_idx": idx,
                "candidate":  cand,
                "out_tok_orig": c["usage"]["completion_tokens"],
            })
    return targets


def regrade(prompt: str, problems: dict, tgt: dict) -> dict:
    prob = problems[tgt["problem_id"]]
    user = (prompt
            .replace("{problem}", prob["text"])
            .replace("{ground_truth}", prob["ground_truth"])
            .replace("{candidate}", tgt["candidate"]))
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
        usage = resp.usage
        score = parse_score(text)
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
        in_tok  = int(getattr(usage, "prompt_tokens",     0) or 0)
        cost = 0.87 * (in_tok + out_tok) / 1_000_000
        elapsed = round(time.time() - t0, 1)
        ms = tgt["model"].split("/")[-1]
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {ms:<15} {tgt['mode']:<14} "
              f"{tgt['problem_id']:<25} {tgt['branch']:<8}  v4pro_new={score}  out_tok={out_tok}  ${cost:.4f}  {elapsed}s",
              flush=True)
        return {
            **tgt,
            "v4pro_score_new": score,
            "verdict_new":     text,
            "in_tok":          in_tok,
            "out_tok":         out_tok,
            "cost_usd":        round(cost, 6),
            "elapsed_s":       elapsed,
        }
    except Exception as e:
        ms = tgt["model"].split("/")[-1]
        print(f"  ERROR {ms} {tgt['problem_id']} {tgt['branch']}: {e}", flush=True)
        return {**tgt, "v4pro_score_new": None, "error": str(e)}


def main():
    problems = load_70_problems()
    judge_prompt = (PROMPTS / "judge_gt.md").read_text(encoding="utf-8").strip()
    targets = collect_targets()
    print(f"Targets to re-judge: {len(targets)}")

    if not targets:
        print("(nothing to do)"); return

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as ex:
        results = list(ex.map(lambda tg: regrade(judge_prompt, problems, tg), targets))
    elapsed = round(time.time() - t0, 1)

    # Save & summarize
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "experiments" / "results" / f"regrade_p1_parse_fails_{ts}.json"
    with open(out_path, "w") as f:
        json.dump({"results": results, "wall_s": elapsed,
                   "total_cost": round(sum(r.get("cost_usd",0) for r in results), 4)},
                  f, indent=2, ensure_ascii=False)
    print(f"\nWall {elapsed}s.  Cost ${sum(r.get('cost_usd',0) for r in results):.3f}.")
    print(f"Saved: {out_path}\n")

    # Distribution of recovered scores
    from collections import Counter
    rec = Counter(r.get("v4pro_score_new") for r in results if r.get("v4pro_score_new") is not None)
    print(f"Recovered score distribution: {dict(sorted(rec.items()))}")

    # By mode + model
    print(f"\n{'Model':<18} {'Mode':<14} {'Problem':<25} {'Branch':<8} {'Recovered':>9}")
    for r in results:
        ms = r["model"].split("/")[-1]
        rec_s = r.get("v4pro_score_new")
        print(f"  {ms:<16} {r['mode']:<14} {r['problem_id']:<25} {r['branch']:<8} {rec_s!s:>9}")

    # Recompute Phase 1 cheap-model means with these substitutions
    # Walk Phase 1 trials, replace silent-0s with recovered scores, recompute.
    print("\n" + "="*80)
    print("UPDATED Phase 1 v4-pro means after substituting recovered scores")
    print("="*80)

    # Build a map (model, mode, problem, branch_idx) -> recovered score
    fix_map = {}
    for r in results:
        if r.get("v4pro_score_new") is None: continue
        fix_map[(r["model"], r["mode"], r["problem_id"], r["branch_idx"])] = r["v4pro_score_new"]

    import statistics
    by_cell = {}
    for f in P1_DIR.rglob("*.json"):
        if f.parent == P1_DIR: continue
        try: t = json.load(open(f))
        except: continue
        if not isinstance(t, dict): continue
        if t.get("model") not in CHEAP: continue
        if t.get("error"): continue

        judge_calls = [c for c in t.get("calls", []) or []
                       if c.get("kind") == "judge" and c.get("model") == JUDGE]
        # Per-branch parsed scores, with recovery substitution
        scores = []
        for idx, c in enumerate(judge_calls):
            txt = c.get("response_text") or ""
            sc = parse_score(txt)
            if sc is None:
                sc = fix_map.get((t["model"], t["mode"], t["problem_id"], idx))
            if sc is None:  # truly unrecoverable — keep as 0 (matches Phase 1 behavior)
                sc = 0
            scores.append(sc)
        new_trial_score = max(scores) if scores else t.get("score", 0)
        by_cell.setdefault((t["model"], t["mode"]), []).append({
            "orig": t.get("score"),
            "new":  new_trial_score,
        })

    print(f"\n{'Model':<18} {'Mode':<16} {'orig':>5} {'new':>5} {'Δ':>5}  changed_trials")
    for (m, mode), rows in sorted(by_cell.items()):
        orig_mean = statistics.mean(r["orig"] for r in rows)
        new_mean  = statistics.mean(r["new"] for r in rows)
        ch = sum(1 for r in rows if r["orig"] != r["new"])
        ms = m.split("/")[-1]
        print(f"  {ms:<16} {mode:<16} {orig_mean:>5.2f} {new_mean:>5.2f} {new_mean-orig_mean:>+5.2f}  {ch}")


if __name__ == "__main__":
    main()
