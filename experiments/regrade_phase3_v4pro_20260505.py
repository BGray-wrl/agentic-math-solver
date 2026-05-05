#!/usr/bin/env python3
"""
Regrade Phase 3 (v4-flash seed_full) trial best_solutions with deepseek-v4-pro.

For each completed trial in the Phase 3 run dir, we re-judge the trial's
best_solution (the gemini-picked best branch) with v4-pro for cross-judge
comparison — same pattern as Phase 1 item 11/12 regrade.

Runs in parallel with the Phase 3 main run: polls the run dir for newly
completed trials, regrades each one as it lands, and stops when the source
process exits AND every completed trial has been regraded.

Per-trial regrade JSONs are saved as the calls finish (crash-safe).
Final summary appended at the end.

Usage:
  uv run experiments/regrade_phase3_v4pro_20260505.py
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
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
MAX_TOKENS = 65536
TIMEOUT = 1800
MAX_WORKERS = 25     # parallel judge calls; v4-pro on one key handles this fine
POLL_INTERVAL = 30   # seconds between disk scans

PHASE3_RUN = (
    Path(__file__).parent / "results"
    / "seed_full_v4flash_phase3_20260505_20260505_021635"
)
TRIALS_DIR = PHASE3_RUN / "seed_full" / "deepseek-v4-flash"

OUT_DIR = (
    Path(__file__).parent / "results"
    / f"regrade_phase3_v4pro_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_score(text: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    if m: return int(m.group(1))
    return 0


def regrade_one(problems: dict, judge_prompt: str, trial_path: Path) -> dict:
    with open(trial_path, encoding="utf-8") as f:
        trial = json.load(f)
    pid = trial["problem_id"]
    out_path = OUT_DIR / f"{pid}.json"

    # Skip if errored or no candidate
    if trial.get("error") or not trial.get("best_solution"):
        rec = {
            "problem_id":   pid,
            "model":        trial.get("model"),
            "gemini_score": trial.get("score"),
            "v4pro_score":  None,
            "skipped":      True,
            "reason":       trial.get("error") or "no best_solution",
        }
        with open(out_path, "w") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
        return rec

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
        )
        # IMPORTANT: v4-pro often returns its output via `reasoning_content` rather than
        # `content` — same shape as Phase 1/2/3 main scripts. Without this fallback, every
        # such response silently parses to score=0.
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
        rec = {
            "problem_id":    pid,
            "model":         trial["model"],
            "is_special_10": trial.get("is_special", False),
            "gemini_score":  trial.get("score"),
            "v4pro_score":   score,
            "v4pro_verdict": text,
            "cost_usd":      round(cost, 6),
            "elapsed_s":     elapsed,
            "in_tokens":     in_tok,
            "out_tokens":    out_tok,
            "completed_at":  datetime.now(timezone.utc).isoformat(),
        }
        delta = score - (trial.get("score") or 0)
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] {pid:<28}  gem={trial.get('score')}/7 "
            f"v4pro={score}/7  Δ={delta:+d}  ${cost:.4f}  {elapsed}s",
            flush=True,
        )
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        rec = {
            "problem_id":   pid,
            "model":        trial.get("model"),
            "gemini_score": trial.get("score"),
            "v4pro_score":  None,
            "error":        str(e),
            "elapsed_s":    elapsed,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"[ERROR] {pid}: {e}", flush=True)

    tmp = out_path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    tmp.replace(out_path)
    return rec


def phase3_still_running() -> bool:
    """Check whether the Phase 3 generator process is still alive."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", "seed_full_v4flash_phase3_20260505.py"],
            capture_output=True, text=True, timeout=5,
        )
        return bool(out.stdout.strip())
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true",
                   help="Regrade trials available right now and exit (no polling).")
    args = p.parse_args()

    problems = load_70_problems()
    judge_prompt = (PROMPTS / "judge_gt.md").read_text(encoding="utf-8").strip()

    print(f"Source: {TRIALS_DIR}")
    print(f"Output: {OUT_DIR}")
    print(f"Judge:  {JUDGE}  (single key OPENROUTER_API_KEY_seedgen)")
    print(f"Workers: {MAX_WORKERS}  Poll: every {POLL_INTERVAL}s while Phase 3 is alive\n", flush=True)

    seen: set[str] = set()  # pids already regraded
    all_results: list[dict] = []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
    inflight: dict = {}

    def harvest(block: bool) -> None:
        nonlocal inflight
        if not inflight: return
        if block:
            done = list(inflight.keys())
        else:
            done = [f for f in inflight if f.done()]
        for f in done:
            try:
                rec = f.result()
                all_results.append(rec)
            except Exception as e:
                print(f"[ERROR harvesting] {e}", flush=True)
            del inflight[f]

    while True:
        # Find newly-completed trials on disk
        new_paths = []
        if TRIALS_DIR.exists():
            for p in sorted(TRIALS_DIR.glob("*.json")):
                pid = p.stem
                if pid in seen: continue
                # Validate it's complete (has score field)
                try:
                    with open(p, encoding="utf-8") as f:
                        t = json.load(f)
                    if t.get("score") is None and not t.get("error"):
                        continue
                except Exception:
                    continue
                seen.add(pid)
                new_paths.append(p)
        for p in new_paths:
            fut = pool.submit(regrade_one, problems, judge_prompt, p)
            inflight[fut] = p.stem

        # Drain whatever's done
        harvest(block=False)

        running = phase3_still_running()
        if args.once or not running:
            # Final drain — wait for everything in flight
            print(f"[poll] Phase 3 running={running}; "
                  f"regraded={len(all_results)} inflight={len(inflight)} seen={len(seen)} on_disk={len(list(TRIALS_DIR.glob('*.json'))) if TRIALS_DIR.exists() else 0}",
                  flush=True)
            # If Phase 3 has stopped, do one more sweep to pick up any final trials
            if not running and not args.once:
                # Scan one more time to catch the last completion
                for p in sorted(TRIALS_DIR.glob("*.json")):
                    pid = p.stem
                    if pid in seen: continue
                    try:
                        with open(p, encoding="utf-8") as f:
                            t = json.load(f)
                        if t.get("score") is None and not t.get("error"):
                            continue
                    except Exception:
                        continue
                    seen.add(pid)
                    fut = pool.submit(regrade_one, problems, judge_prompt, p)
                    inflight[fut] = p.stem
            harvest(block=True)
            break

        print(
            f"[poll {datetime.now().strftime('%H:%M:%S')}] regraded={len(all_results)}  "
            f"inflight={len(inflight)}  seen={len(seen)}  phase3_running={running}",
            flush=True,
        )
        time.sleep(POLL_INTERVAL)

    pool.shutdown(wait=True)

    # Final summary
    total_cost = sum(r.get("cost_usd", 0) or 0 for r in all_results)
    valid = [r for r in all_results if r.get("v4pro_score") is not None]
    if valid:
        delta_sum = sum(r["v4pro_score"] - (r["gemini_score"] or 0) for r in valid)
        mean_delta = delta_sum / len(valid)
        gem_mean   = sum(r["gemini_score"] or 0 for r in valid) / len(valid)
        v4p_mean   = sum(r["v4pro_score"] for r in valid) / len(valid)
        agree     = sum(1 for r in valid if r["v4pro_score"] == r["gemini_score"])
        gem_pass  = sum(1 for r in valid if (r["gemini_score"] or 0) >= 6)
        v4p_pass  = sum(1 for r in valid if r["v4pro_score"] >= 6)
    else:
        mean_delta = gem_mean = v4p_mean = agree = gem_pass = v4p_pass = 0

    summary = {
        "judge":            JUDGE,
        "phase3_run_dir":   str(PHASE3_RUN),
        "n_regraded":       len(all_results),
        "n_valid":          len(valid),
        "total_cost_usd":   round(total_cost, 4),
        "gemini_mean":      round(gem_mean, 3),
        "v4pro_mean":       round(v4p_mean, 3),
        "mean_delta":       round(mean_delta, 3),
        "exact_agreement":  agree,
        "gemini_passes":    gem_pass,
        "v4pro_passes":     v4p_pass,
        "results":          all_results,
    }
    with open(OUT_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n" + "="*80)
    print(f"PHASE 3 V4-PRO REGRADE SUMMARY")
    print("="*80)
    print(f"Trials regraded: {len(valid)}/{len(all_results)}")
    print(f"Total cost:      ${total_cost:.2f}")
    print(f"Gemini mean:     {gem_mean:.2f}/7  ({gem_pass}/{len(valid)} pass≥6)")
    print(f"V4-pro mean:     {v4p_mean:.2f}/7  ({v4p_pass}/{len(valid)} pass≥6)")
    print(f"Mean Δ (v4pro-gemini): {mean_delta:+.2f}")
    print(f"Exact agreement: {agree}/{len(valid)}")
    print(f"\nOutput: {OUT_DIR}")


if __name__ == "__main__":
    main()
