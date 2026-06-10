"""
Experiment 7: high-revision pass, 5 revisions per trial.

Goal: produce thread with substantive partial signal. Each model gets up to 6 generations
(initial + 5 revisions) on the FULL problem. The verifier feeds back ρ-rank info, and the model
is expected to iterate toward Du Val singularities (giving ρ = 1).
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

EXP_NAME = "klt_iter_exp7_high_revisions"

EXTRA_USER_PROMPT = """## Context: ρ(X) = 1 is the hard constraint

Earlier rounds found candidates that passed all checks EXCEPT Picard rank. The Fermat construction
F = x_0^7 + x_1^7 + x_2^2 + x_3^2 in P(2,2,7,7) gives 9 singular points and is quasi-smooth, but
ρ(X) = 7 because each L_{23} point is type 1/7(1,1) — NOT Du Val A_6.

You have **5 revision rounds** to find a candidate that achieves ρ(X) = 1. Use each revision to
respond to the verifier's specific feedback.

Some ideas to try:
- Non-Fermat F that breaks the symmetry at strata (e.g., add mixed terms x_i^a x_j^b with carefully
  chosen exponents so that the tangent at L_{ij} ∩ X has OPPOSITE mu_k weights, giving A_{k-1} type).
- Different weight families: e.g., (2, 2, w, w') with w ≠ w' — but coprime to each other in a way
  that gives Du Val sings.
- Use Method A (quotient of CI(2,2) in P^4 by an involution) — natural way to get A_n singularities.
- Carefully craft the polynomial so K_X^2 is an integer and corrections sum to give K_res^2 = 9 - R.

Aim for at least 8 singular points and ρ(X) = 1.
"""

def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--models", default="all")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--revisions", type=int, default=5)
    args = ap.parse_args()

    models = list(MODELS.keys()) if args.models == "all" else args.models.split(",")
    ts = _ts()
    out_dir = ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{EXP_NAME}_{ts}.json"
    log_path = ROOT / "logs" / f"{EXP_NAME}_{ts}.jsonl"
    log_lock = threading.Lock()

    work = [(m, s) for m in models for s in range(42, 42 + args.seeds)]
    print(f"Total trials: {len(work)} ({args.revisions} revisions each)")
    results = []
    t_start = time.time()

    def go(model_key, seed):
        tag = f"[{model_key}|seed={seed}]"
        print(f"{tag} START", flush=True)
        try:
            tr = run_one_trial(
                model_key=model_key, n_sing_required=8, seed=seed,
                extra_user_prompt=EXTRA_USER_PROMPT, revisions=args.revisions,
            )
            tr["seed"] = seed; tr["model"] = model_key
            print(f"{tag} status={tr['status']} best_score={tr['best_score']} rounds={len(tr.get('rounds',[]))}", flush=True)
            with log_lock: log_jsonl(tr, log_path)
            return tr
        except Exception as e:
            print(f"{tag} ERROR: {e}", flush=True)
            err = {"model": model_key, "seed": seed, "error": str(e), "status": "ERROR"}
            with log_lock: log_jsonl(err, log_path)
            return err

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(go, *w): w for w in work}
        for fu in as_completed(futs):
            results.append(fu.result())

    elapsed = round(time.time() - t_start, 1)
    summary = {
        "experiment": EXP_NAME, "timestamp": ts, "elapsed_s": elapsed,
        "models": models, "n_seeds": args.seeds, "revisions": args.revisions,
        "n_pass": sum(1 for r in results if r.get("status") == "PASS"),
        "n_fail": sum(1 for r in results if r.get("status") == "FAIL"),
        "n_error": sum(1 for r in results if r.get("status") == "ERROR"),
        "results": results,
    }
    with open(out_path, "w") as f: json.dump(summary, f, indent=1, default=str)
    print(f"\nPASS: {summary['n_pass']} / {len(work)}")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
