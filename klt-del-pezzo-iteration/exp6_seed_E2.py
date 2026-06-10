"""
Experiment 6: Seed models with my E2 candidate and ask them to (a) verify it themselves,
(b) clean it up to be strictly quasi-smooth (if possible), or (c) propose adjacent constructions
that are strictly quasi-smooth with 8+ singular points.

E2 candidate: P(2,2,5,5,5,7) CI of:
  F1 = x_0^5 + x_1^5 + x_2^2 + x_3^2 (deg 10)
  F2 = x_5 + x_0*x_2 + x_1*x_3 (deg 7)
  F3 = x_1*x_2 + x_0*x_3 + x_0*x_4 (deg 7)

Analysis: 5 (L_{01}) + 2 (L_{23}) + 1 (P_4 as A_4 Du Val) = 8 distinct singular points.
The cone is non-quasi-smooth at the lift of P_4 (singular locus = x_4-axis).
Locally at P_4: y_2^2 + y_3^2 + y_1^5 = A_4 (klt) ✓.

Goal: find strict quasi-smooth variant OR confirm/improve.
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

EXP_NAME = "klt_iter_exp6_seed_E2"

EXTRA_USER_PROMPT = """## A near-passing candidate to refine

Consider this Method B candidate in P(2,2,5,5,5,7) over Z/3:

  F1 = x_0^5 + x_1^5 + x_2^2 + x_3^2        (weighted degree 10)
  F2 = x_5 + x_0*x_2 + x_1*x_3              (weighted degree 7)
  F3 = x_1*x_2 + x_0*x_3 + x_0*x_4          (weighted degree 7)

Properties confirmed in Macaulay2:
- Weights all coprime to 3 (tame): 2, 5, 7 ✓
- Well-formed (gcd of any 5 weights = 1) ✓
- Fano index 26 - 24 = 2 > 0 ✓
- Singular strata intersections give 5 (L_{01}) + 2 (L_{23}) + 1 (P_4) = 8 distinct singular points.
- BUT: the affine cone is NOT quasi-smooth — singular along the x_4-axis. Projectively this is the single point P_4 = (0:0:0:0:1:0).
- LOCAL ANALYSIS at P_4: after eliminating x_5 via F2 and x_0 via F3 (~ -y_1 y_2 near origin), F1 becomes locally y_2^2 + y_3^2 + y_1^5 + (higher) in (y_1, y_2, y_3). This is the standard Brieskorn-Pham A_4 surface singularity (Milnor number 4), which is a Du Val rational double point — KLT.

So the candidate IS plausibly a klt del Pezzo with rho=1 and 8 singular points, but it's NOT strictly quasi-smooth.

## Your task

(a) Find a STRICTLY QUASI-SMOOTH variant (cone smooth outside origin) that still has >= 8 singular points,
in P(2,2,5,5,5,7) OR a related ambient. If you can't, explain WHY (i.e., is the A_4 unavoidable here?).

(b) Alternatively, propose a different ambient with a different construction that achieves both
quasi-smoothness AND 8+ singular points.

In particular, check whether including SLIGHTLY MODIFIED F's can avoid the cone singularity at P_4
while preserving the singular-line contributions:
- Adding a monomial that gives ∂F_i/∂x_? non-zero at P_4 lift would help.
- The "missing piece" is a monomial x_4 * (lower-weight) that's compatible with one of the degrees.
  In P(2,2,5,5,5,7) at deg 7 or 10: x_4 has weight 5, so x_4 * x_j has weight 5 + w_j. For degree 7: w_j = 2, so x_0*x_4 or x_1*x_4 (deg 2+5=7 ✓). For degree 10: w_j = 5, so x_4*x_2, x_4*x_3, x_4^2 (deg 10 ✓).

Try including x_4^2 or x_2*x_4 in F1 (deg 10) to see if it eliminates the P_4 cone singularity while keeping the 8 singular points.
"""

def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--models", default="all")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--revisions", type=int, default=2)
    args = ap.parse_args()

    models = list(MODELS.keys()) if args.models == "all" else args.models.split(",")
    ts = _ts()
    out_dir = ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{EXP_NAME}_{ts}.json"
    log_path = ROOT / "logs" / f"{EXP_NAME}_{ts}.jsonl"
    log_lock = threading.Lock()

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
            tr["seed"] = seed; tr["model"] = model_key
            print(f"{tag} status={tr['status']} best_score={tr['best_score']}", flush=True)
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
    print(f"PASS: {summary['n_pass']} / {len(work)}")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
