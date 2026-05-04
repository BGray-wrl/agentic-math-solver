#!/usr/bin/env python3
"""Quick generate-only + judge on PB-Basic-007 and PB-Basic-028 to sanity-check difficulty."""

from __future__ import annotations
import sys, csv, json, re, time, threading, concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import litellm

MODELS = [
    "openai/gpt-5.4-mini",
    "gemini/gemini-3-flash-preview",
    "openrouter/openai/gpt-oss-120b",
    "openrouter/google/gemini-3.1-flash-lite-preview",
    "openrouter/deepseek/deepseek-v3.2",
]

JUDGE_MODEL = "gemini/gemini-3-flash-preview"
PROBLEM_IDS = ["PB-Basic-012", "PB-Basic-023", "PB-Basic-017", "PB-Basic-020"]
MAX_TOKENS = 32000
MAX_TOKENS_JUDGE = 32000
MAX_WORKERS = 10
LITELLM_TIMEOUT = 540

BENCHMARKS_CSV = Path(__file__).parent.parent / "benchmarks" / "combined-benchmarks.csv"
PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "pipeline"

def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def parse_gt_score(verdict: str) -> int:
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", verdict, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", verdict, re.I)
    if m: return int(m.group(1))
    return 0

def load_problems():
    with open(BENCHMARKS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        pid = r.get("Problem ID", "")
        if pid in PROBLEM_IDS:
            out[pid] = {"text": r["Problem"], "solution": r.get("Solution", ""), "level": r.get("Level", "")}
    return out

def load_prompt(name):
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()

def run_trial(pid, problem, model, prompts, log_path, log_lock):
    from pipeline import generate, judge, make_logger
    ms = model.split("/")[-1]
    tag = f"[{_ts()}] [{pid}|{ms}]"
    _base = make_logger(str(log_path))
    def logger(*a):
        with log_lock:
            _base(*a)
    t0 = time.time()
    print(f"{tag} generate", flush=True)
    solution = generate(problem=problem["text"], system=prompts["generator"], model=model,
                        max_tokens=MAX_TOKENS, logger=logger, iteration=0)
    print(f"{tag} generated ({len(solution)} chars, {time.time()-t0:.1f}s)", flush=True)
    gt = problem["solution"]
    judge_prompt = prompts["judge_gt"] if gt else prompts["judge_nogt"]
    print(f"{tag} judge", flush=True)
    verdict_text = judge(problem=problem["text"], candidate=solution, ground_truth=gt,
                         system=judge_prompt, model=JUDGE_MODEL, max_tokens=MAX_TOKENS_JUDGE,
                         logger=logger, extract_prompt=prompts["extract_score"])
    score = parse_gt_score(verdict_text)
    elapsed = round(time.time() - t0, 2)
    print(f"{tag} → score={score}/7 {elapsed}s", flush=True)
    return {"problem_id": pid, "model": model, "score": score, "elapsed_s": elapsed, "level": problem["level"]}

def main():
    litellm.request_timeout = LITELLM_TIMEOUT
    problems = load_problems()
    print(f"Sanity-checking {len(problems)} problems × {len(MODELS)} models")
    for pid, p in sorted(problems.items()):
        print(f"  {pid}  {p['level']}")

    prompts = {
        "generator": load_prompt("generator.md"),
        "judge_gt": load_prompt("judge_gt.md"),
        "judge_nogt": load_prompt("judge_nogt.md"),
        "extract_score": load_prompt("extract_score.md"),
    }

    log_path = Path(__file__).parent.parent / "logs" / f"pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl"
    log_lock = threading.Lock()

    trials = [(pid, m) for pid in sorted(problems) for m in MODELS]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(run_trial, pid, problems[pid], m, prompts, log_path, log_lock): (pid, m) for pid, m in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=900 * len(trials)):
            pid, m = futs[fut]
            try:
                results.append(fut.result(timeout=900))
            except Exception as e:
                print(f"[{_ts()}] FAILED [{pid}|{m.split('/')[-1]}]: {e}", flush=True)
                results.append({"problem_id": pid, "model": m, "score": None, "error": str(e)})

    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}\n")
    for pid in PROBLEM_IDS:
        pr = [r for r in results if r["problem_id"] == pid]
        scores = [r["score"] for r in pr if r.get("score") is not None]
        mean = sum(scores)/len(scores) if scores else 0
        n_pass = sum(1 for s in scores if s >= 6)
        times = [r["elapsed_s"] for r in pr if r.get("elapsed_s")]
        mean_t = sum(times)/len(times) if times else 0
        print(f"{pid}:  mean={mean:.2f}/7  pass={n_pass}/{len(scores)}  mean_time={mean_t:.0f}s")
        for r in pr:
            ms = r["model"].split("/")[-1]
            s = r.get("score", "ERR")
            t = r.get("elapsed_s", 0)
            print(f"  {ms:<30} {s}/7  {t:.0f}s")
        print()

if __name__ == "__main__":
    main()
