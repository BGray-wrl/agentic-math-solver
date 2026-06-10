"""
Experiment 2: Build on the verified warmup solution.

Goal: take the known passing warmup construction (P(2,2,5,5), F = x_0^5 + x_1^5 + x_2^2 + x_3^2,
giving 5+2=7 singular points) and ask each model to EXTEND it to 8 singular points for the
full problem.

Approaches the prompt suggests:
  (A) Add a 5th variable (CI in 5-var ambient) to introduce another singular line or coord point.
  (B) Use a less-symmetric polynomial in P(2,2,5,5) plus careful per-singularity klt argument.
  (C) Choose a different weight set with more singular strata.

The prompt explicitly highlights the failure mode in gpt-oss-seed42 (symmetric polynomials
have no F_3-bar zeros on L_12) so the model knows not to repeat it.

Each cell: 3 models × 5 trials × 1 revision = 30 candidates max.
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

EXP_NAME = "klt_iter_exp2_build_on_warmup"

EXTRA_USER_PROMPT = """## Verified WARMUP construction (use as starting point)

The construction below is *known to give exactly 7 singular points* on a klt del Pezzo with rho=1 in characteristic 3:

  Weights: [2, 2, 5, 5]
  Equation: F = x_0^5 + x_1^5 + x_2^2 + x_3^2  (weighted degree 10)

Verification (Macaulay2):
- Cone is smooth outside origin (quasi-smooth) ✓
- L_{01} = {x_2=x_3=0} contributes 5 mu_2 quotient singularities (zeros of x_0^5 + x_1^5 in F_9)
- L_{23} = {x_0=x_1=0} contributes 2 mu_5 quotient singularities (zeros of x_2^2 + x_3^2 in F_9)
- Coordinate points P_0..P_3 are all OFF X (each F(P_i) = 1)
- Total: 7 distinct klt singular points

## Your task

Extend this construction to yield AT LEAST 8 singular points (full problem). Some ideas:
  A) Add a 5th variable to make a CI of 2 in P(?,?,?,?,?), introducing another singular line.
     CAUTION: With degrees d1, d2, both must avoid identically vanishing on each singular line;
     symmetric polynomials like x_1^2 + x_2^2 paired with x_1^5 + x_2^5 give zero common zeros in F_3-bar.
  B) Choose different weights (e.g. P(2,2,5,5,11), P(2,2,5,5,7), P(1,2,2,5,5)) and find a CI where:
     - Each singular line gets transversely intersected (compute t^d = -1 conditions in F_3-bar).
     - Each coordinate point of weight >1 is either not on X (pure power present) or quasi-smooth.
  C) Use a slightly less-symmetric polynomial within P(2,2,5,5) that creates an isolated A_n singularity
     at a non-strata point. (HARD — requires careful klt verification.)

The key is to CHECK YOUR POLYNOMIAL CHOICE GIVES NON-EMPTY ZEROS over F_3-bar on each stratum.
Show your point count explicitly.
"""

def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--models", default="all")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--revisions", type=int, default=1)
    args = ap.parse_args()

    models = list(MODELS.keys()) if args.models == "all" else args.models.split(",")

    ts = _ts()
    out_dir = ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{EXP_NAME}_{ts}.json"
    log_path = ROOT / "logs" / f"{EXP_NAME}_{ts}.jsonl"
    log_lock = threading.Lock()

    print(f"Models: {models}")
    print(f"Seeds: {args.seeds}")
    print(f"Revisions: {args.revisions}")
    print(f"Output: {out_path}")

    work = [(m, s) for m in models for s in range(42, 42 + args.seeds)]
    print(f"Total trials: {len(work)}")

    results = []
    t_start = time.time()

    def go(model_key, seed):
        tag = f"[{model_key}|seed={seed}]"
        print(f"{tag} START", flush=True)
        try:
            tr = run_one_trial(
                model_key=model_key,
                n_sing_required=8,
                seed=seed,
                extra_user_prompt=EXTRA_USER_PROMPT,
                revisions=args.revisions,
            )
            tr["seed"] = seed
            tr["model"] = model_key
            print(f"{tag} done status={tr['status']} best_score={tr['best_score']}", flush=True)
            with log_lock:
                log_jsonl(tr, log_path)
            return tr
        except Exception as e:
            print(f"{tag} ERROR: {e}", flush=True)
            err = {"model": model_key, "seed": seed, "error": str(e), "status": "ERROR"}
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
        "n_seeds": args.seeds,
        "revisions": args.revisions,
        "n_pass": sum(1 for r in results if r.get("status") == "PASS"),
        "n_fail": sum(1 for r in results if r.get("status") == "FAIL"),
        "n_error": sum(1 for r in results if r.get("status") == "ERROR"),
        "results": results,
    }

    with open(out_path, "w") as f:
        json.dump(summary, f, indent=1, default=str)

    print("")
    print(f"PASS: {summary['n_pass']} / {len(work)}")
    print(f"Per-model best scores:")
    for m in models:
        cell = [r for r in results if r.get("model") == m]
        best = max((r.get("best_score", 0) for r in cell), default=0)
        print(f"  {m:18}: best_score={best}, n_trials={len(cell)}")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
