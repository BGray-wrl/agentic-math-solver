#!/usr/bin/env python3
"""
Quick probe: can qwen3.6-plus:free make any progress on 3 hard research problems?
  1. erdos-659        (Negligible Novelty - distances in R^2)
  2. ramsey-hypergraphs (Moderately Interesting - partition hypergraphs)
  3. erdos-1051-aletheia (Minor Novelty - integer sequences, best shot at novelty)

Generate-only, no judge. Just read the output.

Usage:
    uv run experiments/qwen_hardproblems_20260405.py --mock
    uv run experiments/qwen_hardproblems_20260405.py
"""
from __future__ import annotations
import sys, csv, json, time, argparse, concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

MODEL      = "openrouter/qwen/qwen3.6-plus:free"
PROBLEM_IDS = ["erdos-659", "ramsey-hypergraphs", "erdos-1051-aletheia"]
MAX_TOKENS  = 16000
TIMEOUT     = 900   # these problems are hard; give it time

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR    = Path(__file__).parent.parent / "prompts" / "pipeline"
RESULTS_DIR    = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _now():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def load_problems() -> dict[str, dict]:
    rows = list(csv.DictReader(open(BENCHMARKS_CSV, encoding="utf-8")))
    return {
        r["Problem ID"]: {"text": r["Problem"], "level": r["Level"], "solution": r.get("Solution", "")}
        for r in rows if r["Problem ID"] in PROBLEM_IDS
    }


def run_one(pid: str, problem: dict, gen_prompt: str, mock: bool) -> dict:
    from pipeline import generate, make_logger
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    logger = make_logger(str(log_path))

    print(f"[{_ts()}] [{pid}] starting generate ...", flush=True)
    t0 = time.time()
    solution = generate(
        problem=problem["text"], system=gen_prompt, model=MODEL,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    elapsed = round(time.time() - t0, 1)
    print(f"[{_ts()}] [{pid}] done — {len(solution)} chars in {elapsed}s", flush=True)
    return {"problem_id": pid, "level": problem["level"], "solution": solution, "elapsed_s": elapsed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    import litellm
    litellm.request_timeout = TIMEOUT

    problems   = load_problems()
    gen_prompt = (PROMPTS_DIR / "generator.md").read_text(encoding="utf-8").strip()

    missing = [pid for pid in PROBLEM_IDS if pid not in problems]
    if missing:
        print(f"WARNING: not found in CSV: {missing}")

    print(f"Model:    {MODEL}")
    print(f"Problems: {list(problems.keys())}")
    print(f"Mock:     {args.mock}\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(run_one, pid, prob, gen_prompt, args.mock): pid
                for pid, prob in problems.items()}
        for fut in concurrent.futures.as_completed(futs, timeout=TIMEOUT * len(problems)):
            pid = futs[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"[{_ts()}] [{pid}] FAILED: {e}", flush=True)
                results.append({"problem_id": pid, "error": str(e)})

    # Print solutions
    print("\n" + "=" * 70)
    for r in sorted(results, key=lambda x: x["problem_id"]):
        pid = r["problem_id"]
        print(f"\n{'='*70}")
        print(f"PROBLEM: {pid}  ({problems.get(pid, {}).get('level', '?')})")
        print(f"{'='*70}")
        if r.get("error"):
            print(f"ERROR: {r['error']}")
        else:
            print(r["solution"])
        print()

    # Save
    out = {
        "model": MODEL, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "mock": args.mock, "results": results,
    }
    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"qwen_hardproblems_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Saved to: {out_path}")


if __name__ == "__main__":
    main()
