"""
Batch evaluator: runs the pipeline on selected proofbench problems
and collects judge scores.

Usage:
    uv run src/batch_eval.py
    uv run src/batch_eval.py --max-workers 5 --iterations 2 --model openrouter/...
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


# ── Problem selection ────────────────────────────────────────────────────────

SELECTED_IDS = [
    # pre-IMO (all 8)
    "PB-Basic-002", "PB-Basic-008", "PB-Basic-013", "PB-Basic-014",
    "PB-Basic-015", "PB-Basic-016", "PB-Basic-017", "PB-Basic-018",
    # IMO-easy (6 sampled)
    "PB-Basic-001", "PB-Basic-004", "PB-Basic-010", "PB-Basic-021",
    "PB-Advanced-001", "PB-Advanced-016",
    # IMO-medium (4 sampled)
    "PB-Basic-006", "PB-Basic-012", "PB-Advanced-002", "PB-Advanced-020",
    # IMO-hard (2 sampled)
    "PB-Advanced-006", "PB-Advanced-018",
]


def load_problems(csv_path: str) -> dict[str, dict]:
    with open(csv_path, encoding="utf-8") as f:
        return {r["Problem ID"]: r for r in csv.DictReader(f)}


# ── Per-problem runner ───────────────────────────────────────────────────────

def run_one(pid: str, row: dict, args, tmpdir: str) -> dict:
    t0 = time.time()

    # Write problem file
    prob_file = os.path.join(tmpdir, f"{pid}_problem.txt")
    with open(prob_file, "w") as f:
        f.write(row["Problem"])

    # Write ground-truth file (solution + grading guidelines)
    gt_parts = []
    if row.get("Solution", "").strip():
        gt_parts.append("## Reference Solution\n" + row["Solution"].strip())
    if row.get("Grading guidelines", "").strip():
        gt_parts.append("## Grading Guidelines\n" + row["Grading guidelines"].strip())
    gt_text = "\n\n".join(gt_parts)
    gt_file = None
    if gt_text.strip():
        gt_file = os.path.join(tmpdir, f"{pid}_gt.txt")
        with open(gt_file, "w") as f:
            f.write(gt_text)

    # Build command
    script_dir = Path(__file__).parent.parent
    cmd = [
        "uv", "run", "src/pipeline.py", prob_file,
        "--model", args.model,
        "--iterations", str(args.iterations),
        "--max-tokens", str(args.max_tokens),
        "--log-dir", args.log_dir,
    ]
    if gt_file:
        cmd += ["--ground-truth", gt_file]

    result_file = os.path.join(tmpdir, f"{pid}_result.json")
    cmd += ["-o", result_file]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=300, cwd=str(script_dir)
        )
        if proc.returncode != 0:
            return {
                "pid": pid, "level": row["Level"], "category": row["Category"],
                "error": proc.stderr[-500:], "elapsed": time.time() - t0,
            }

        with open(result_file) as f:
            data = json.load(f)

        verdict = data.get("judge_verdict", "")
        score = parse_score(verdict)
        classification = parse_classification(verdict)

        return {
            "pid": pid,
            "level": row["Level"],
            "category": row["Category"],
            "source": row.get("Source", ""),
            "iterations_run": data["iterations_run"],
            "stopped_early": data["stopped_early"],
            "score": score,
            "classification": classification,
            "judge_verdict": verdict,
            "final_solution_snippet": data.get("final_solution", "")[:300],
            "elapsed": time.time() - t0,
        }

    except subprocess.TimeoutExpired:
        return {
            "pid": pid, "level": row["Level"], "category": row["Category"],
            "error": "timeout", "elapsed": time.time() - t0,
        }
    except Exception as e:
        return {
            "pid": pid, "level": row["Level"], "category": row["Category"],
            "error": str(e), "elapsed": time.time() - t0,
        }


def parse_score(verdict: str) -> str | None:
    m = re.search(r"<points>\s*(\d+)\s*out of\s*7\s*</points>", verdict, re.IGNORECASE)
    if m:
        return f"{m.group(1)}/7"
    return None


def parse_classification(verdict: str) -> str | None:
    m = re.search(r"CLASSIFICATION:\s*(correct|almost|partial|incorrect)", verdict, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


# ── Summary ──────────────────────────────────────────────────────────────────

def summarise(results: list[dict]):
    print("\n" + "=" * 80)
    print("BATCH EVALUATION RESULTS")
    print("=" * 80)

    header = f"{'ID':<20} {'Level':<12} {'Cat':<14} {'Iters':<6} {'Early':<6} {'Score':<8} {'Class':<12} {'t(s)':<6}"
    print(header)
    print("-" * 80)

    by_level: dict[str, list] = {}
    for r in results:
        level = r.get("level", "?")
        by_level.setdefault(level, []).append(r)

    level_order = ["pre-IMO", "IMO-easy", "IMO-medium", "IMO-hard"]
    for level in level_order:
        if level not in by_level:
            continue
        for r in by_level[level]:
            err = r.get("error")
            if err:
                row = f"{'  ' + r['pid']:<20} {r['level']:<12} {r.get('category','?'):<14} {'--':<6} {'--':<6} {'ERROR':<8} {str(err)[:12]:<12} {r['elapsed']:.1f}"
            else:
                score = r.get("score") or "-"
                cls = r.get("classification") or "-"
                row = (
                    f"{'  ' + r['pid']:<20} {r['level']:<12} {r['category']:<14} "
                    f"{r['iterations_run']:<6} {'Y' if r['stopped_early'] else 'N':<6} "
                    f"{score:<8} {cls:<12} {r['elapsed']:.1f}"
                )
            print(row)
        print()

    # Aggregate stats
    print("=" * 80)
    print("AGGREGATE")
    for level in level_order:
        rows = by_level.get(level, [])
        if not rows:
            continue
        valid = [r for r in rows if "error" not in r]
        correct = sum(1 for r in valid if r.get("classification") in ("correct",) or r.get("score") in ("7/7",))
        almost = sum(1 for r in valid if r.get("classification") == "almost" or r.get("score") == "6/7")
        partial = sum(1 for r in valid if r.get("classification") == "partial" or r.get("score") in ("1/7",))
        incorrect = sum(1 for r in valid if r.get("classification") == "incorrect" or r.get("score") == "0/7")
        scores_7 = [int(r["score"].split("/")[0]) for r in valid if r.get("score")]
        avg = sum(scores_7) / len(scores_7) if scores_7 else None
        avg_str = f"avg={avg:.1f}/7" if avg is not None else ""
        early = sum(1 for r in valid if r.get("stopped_early"))
        print(f"  {level:<12}: {len(valid)}/{len(rows)} ran | correct={correct} almost={almost} partial={partial} incorrect={incorrect} | early_stop={early} | {avg_str}")

    # Grand totals
    all_valid = [r for r in results if "error" not in r]
    all_scores = [int(r["score"].split("/")[0]) for r in all_valid if r.get("score")]
    all_cls = [r.get("classification") for r in all_valid if r.get("classification")]
    print(f"\n  TOTAL: {len(all_valid)}/{len(results)} ran")
    if all_scores:
        print(f"  Scored (0-7): {all_scores}  mean={sum(all_scores)/len(all_scores):.2f}")
    if all_cls:
        from collections import Counter
        print(f"  Classifications: {dict(Counter(all_cls))}")
    print("=" * 80)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="benchmarks/IMO-bench/proofbench.csv")
    parser.add_argument("--model", default=os.environ.get(
        "PIPELINE_MODEL", "openrouter/google/gemini-3-flash-preview"))
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--log-dir", default="logs/")
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--ids", nargs="*", help="Override problem IDs to run")
    parser.add_argument("-o", "--output", help="Write full results JSON here")
    args = parser.parse_args()

    problems = load_problems(args.csv)
    ids = args.ids or SELECTED_IDS
    ids = [i for i in ids if i in problems]

    print(f"Running {len(ids)} problems | model={args.model} | iters={args.iterations} | workers={args.max_workers}")
    print(f"IDs: {ids}\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        futures = {}
        results = []
        with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
            for pid in ids:
                f = pool.submit(run_one, pid, problems[pid], args, tmpdir)
                futures[f] = pid

            done = 0
            for fut in as_completed(futures):
                done += 1
                pid = futures[fut]
                r = fut.result()
                results.append(r)
                score = r.get("score") or r.get("classification") or r.get("error", "?")
                early = "✓ early" if r.get("stopped_early") else ""
                print(f"[{done}/{len(ids)}] {pid} ({r.get('level','?')}) → {score} {early}")

    # Sort by level then ID
    level_order = {"pre-IMO": 0, "IMO-easy": 1, "IMO-medium": 2, "IMO-hard": 3}
    results.sort(key=lambda r: (level_order.get(r.get("level", ""), 9), r.get("pid", "")))

    summarise(results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nFull results → {args.output}")


if __name__ == "__main__":
    main()
