#!/usr/bin/env python3
"""
Frontier model probe on 3 hard research problems:
  1. erdos-659        (Negligible Novelty - distances in R^2)
  2. ramsey-hypergraphs (Moderately Interesting - partition hypergraphs)
  3. erdos-1051-aletheia (Minor Novelty - integer sequences)

Models: claude-opus-4.6, gemini-3.1-pro-preview
Generate + GT judge (0-7 score). Runs all 6 combos in parallel.

Usage:
    uv run experiments/frontier_hardproblems_20260405.py --mock
    uv run experiments/frontier_hardproblems_20260405.py
"""
from __future__ import annotations
import sys, csv, json, re, time, argparse, concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

MODELS = [
    "openrouter/anthropic/claude-opus-4.6",
    "openrouter/google/gemini-3.1-pro-preview",
]
JUDGE_MODEL = "openrouter/google/gemini-3-flash-preview"
PROBLEM_IDS = ["erdos-659", "ramsey-hypergraphs", "erdos-1051-aletheia"]
MAX_TOKENS       = 16000
MAX_TOKENS_JUDGE = 4096
TIMEOUT          = 600

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


def parse_gt_score(verdict: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m:
        return int(m.group(1))
    classif_map = {"correct": 7, "almost": 6, "partial": 1, "incorrect": 0}
    for label, score in classif_map.items():
        if f"CLASSIFICATION: {label}" in verdict:
            return score
    return 0


def run_one(pid: str, problem: dict, model: str, prompts: dict, mock: bool) -> dict:
    from pipeline import generate, judge, make_logger
    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{_now()}.jsonl"
    logger = make_logger(str(log_path))

    model_short = model.split("/")[-1]
    tag = f"[{pid}|{model_short}]"
    print(f"[{_ts()}] {tag} generate ...", flush=True)
    t0 = time.time()
    solution = generate(
        problem=problem["text"], system=prompts["generator"], model=model,
        max_tokens=MAX_TOKENS, logger=logger, iteration=0, mock=mock,
    )
    print(f"[{_ts()}] {tag} generate done ({len(solution)} chars), judging ...", flush=True)
    verdict_text = judge(
        problem=problem["text"], candidate=solution, ground_truth=problem["solution"],
        system=prompts["judge_gt"], model=JUDGE_MODEL,
        max_tokens=MAX_TOKENS_JUDGE, logger=logger, mock=mock,
        extract_prompt=prompts["extract_score"],
    )
    score = parse_gt_score(verdict_text)
    elapsed = round(time.time() - t0, 1)
    print(f"[{_ts()}] {tag} score={score}/7  {elapsed}s", flush=True)
    return {"problem_id": pid, "model": model, "level": problem["level"],
            "solution": solution, "verdict": verdict_text, "score": score, "elapsed_s": elapsed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    import litellm
    litellm.request_timeout = TIMEOUT

    problems = load_problems()
    prompts = {
        "generator":     (PROMPTS_DIR / "generator.md").read_text(encoding="utf-8").strip(),
        "judge_gt":      (PROMPTS_DIR / "judge_gt.md").read_text(encoding="utf-8").strip(),
        "extract_score": (PROMPTS_DIR / "extract_score.md").read_text(encoding="utf-8").strip(),
    }

    missing = [pid for pid in PROBLEM_IDS if pid not in problems]
    if missing:
        print(f"WARNING: not found in CSV: {missing}")

    trials = [(pid, prob, model) for pid, prob in problems.items() for model in MODELS]
    print(f"Models:   {[m.split('/')[-1] for m in MODELS]}")
    print(f"Judge:    {JUDGE_MODEL.split('/')[-1]}")
    print(f"Problems: {list(problems.keys())}")
    print(f"Trials:   {len(trials)}  (all parallel)")
    print(f"Mock:     {args.mock}\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(trials)) as ex:
        futs = {ex.submit(run_one, pid, prob, model, prompts, args.mock): (pid, model)
                for pid, prob, model in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TIMEOUT * 2):
            pid, model = futs[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                ms = model.split("/")[-1]
                print(f"[{_ts()}] [{pid}|{ms}] FAILED: {e}", flush=True)
                results.append({"problem_id": pid, "model": model,
                                 "level": problems[pid]["level"], "score": None, "error": str(e)})

    # Print scores
    print(f"\n{'='*70}")
    print(f"{'Problem':<28} {'claude-opus-4.6':>18} {'gemini-3.1-pro-preview':>24}")
    print("-" * 72)
    for pid in PROBLEM_IDS:
        row = f"{pid:<28}"
        for model in MODELS:
            r = next((x for x in results if x["problem_id"] == pid and x["model"] == model), None)
            cell = f"{r['score']}/7" if r and r.get("score") is not None else ("error" if r else "—")
            row += f"{cell:>18}" if model == MODELS[0] else f"{cell:>24}"
        print(row)

    # Save
    out = {
        "models": MODELS, "judge": JUDGE_MODEL,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "mock": args.mock, "results": results,
    }
    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"frontier_hardproblems_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
