"""
Experiment 1: Pass@K with M2 verification across 3 models, with 1 revision on failure.

Goal: produce a verified klt del Pezzo solution (warmup or full) via straightforward pass@5
with the verifier as an iterative oracle.

Strategy:
- 3 models × 2 problem types (warmup N=7, full N=8) × 4 seeds = 24 trials.
- Each trial: 1 generation + (1 revision if first fails with score >= 2).
- Use high max_tokens to address truncation (60K for OpenRouter, 50K for Gemma).

Output: experiments/results/klt_iter_exp1_<TS>.json
"""
from __future__ import annotations
import os, sys, json, time, threading, argparse, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

ROOT = Path("/Users/benjamingrayzel/sandbox/agentic-math-solver")
ITER_DIR = ROOT / "klt-del-pezzo-iteration"
sys.path.insert(0, str(ITER_DIR))

from klt_pipeline import run_one_trial, log_jsonl, MODELS

EXP_NAME = "klt_iter_exp1_pass5_verified"

def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=4, help="Number of seeds per (model, prompt-type) cell")
    ap.add_argument("--models", default="all", help="Comma-separated model keys, or 'all'")
    ap.add_argument("--problems", default="warmup,full", help="Comma-separated: warmup, full")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--revisions", type=int, default=1)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    if args.mock:
        print("MOCK MODE: generating fake trial to test infra.")
        return

    models = list(MODELS.keys()) if args.models == "all" else args.models.split(",")
    problems = []
    if "warmup" in args.problems: problems.append(("warmup", 7))
    if "full" in args.problems:   problems.append(("full", 8))

    out_dir = ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    out_path  = out_dir / f"{EXP_NAME}_{ts}.json"
    log_path  = ROOT / "logs" / f"{EXP_NAME}_{ts}.jsonl"
    log_lock = threading.Lock()

    print(f"Models: {models}")
    print(f"Problems: {problems}")
    print(f"Seeds per cell: {args.seeds}")
    print(f"Output: {out_path}")
    print(f"Log:    {log_path}")
    print("")

    work = []
    for model_key in models:
        for ptype, N_sing in problems:
            for seed in range(42, 42 + args.seeds):
                work.append((model_key, ptype, N_sing, seed))

    print(f"Total trials: {len(work)}")
    results = []
    t_start = time.time()

    def go(model_key, ptype, N_sing, seed):
        tag = f"[{model_key}|{ptype}|seed={seed}]"
        print(f"{tag} START", flush=True)
        try:
            tr = run_one_trial(
                model_key=model_key,
                n_sing_required=N_sing,
                seed=seed,
                revisions=args.revisions,
            )
            tr["problem_type"] = ptype
            tr["seed"] = seed
            tr["model"] = model_key
            print(f"{tag} done status={tr['status']} best_score={tr['best_score']}", flush=True)
            with log_lock:
                log_jsonl(tr, log_path)
            return tr
        except Exception as e:
            print(f"{tag} ERROR: {e}\n{traceback.format_exc()[:600]}", flush=True)
            err = {"model": model_key, "problem_type": ptype, "seed": seed, "error": str(e), "status": "ERROR"}
            with log_lock:
                log_jsonl(err, log_path)
            return err

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(go, *w): w for w in work}
        for fu in as_completed(futs):
            results.append(fu.result())

    elapsed = round(time.time() - t_start, 1)

    summary = {
        "experiment": EXP_NAME,
        "timestamp": ts,
        "elapsed_s": elapsed,
        "models": models,
        "problems": problems,
        "n_seeds": args.seeds,
        "revisions": args.revisions,
        "n_trials": len(work),
        "n_pass": sum(1 for r in results if r.get("status") == "PASS"),
        "n_fail": sum(1 for r in results if r.get("status") == "FAIL"),
        "n_error": sum(1 for r in results if r.get("status") == "ERROR"),
        "results": results,
    }

    with open(out_path, "w") as f:
        json.dump(summary, f, indent=1, default=str)

    print("")
    print(f"Done. PASS: {summary['n_pass']} / {summary['n_trials']}")
    print(f"Best scores per cell:")
    for model_key in models:
        for ptype, _ in problems:
            cell = [r for r in results if r.get("model") == model_key and r.get("problem_type") == ptype]
            best = max((r.get("best_score", 0) for r in cell), default=0)
            print(f"  {model_key:18} {ptype:8}: best_score={best}, n_trials={len(cell)}")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
