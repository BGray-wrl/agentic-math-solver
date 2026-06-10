"""
Experiment 3: Surgical fix of gpt-oss-seed42's L_12 bug.

Goal: take gpt-oss-seed42's framework (P(1,2,2,5,5) CI with degrees (4,10)) and ask the model
to FIX the specific polynomial-symmetry problem that made L_12 ∩ X empty.

Background: the candidate's F1|L_12 = x_1^2 + x_2^2 and F2|L_12 = x_1^5 + x_2^5 have no common
zeros over F_3-bar because t^2 = -1 forces order(t) = 4, while t^5 = -1 forces order(t) | 10,
gcd = 2 → contradiction.

Fix needed: choose F1, F2 with non-symmetric (x_1, x_2) parts such that their joint zero locus
on the L_12 line is non-empty over F_3-bar.

Each cell: 3 models × 6 trials × 2 revisions.
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

EXP_NAME = "klt_iter_exp3_fix_gptoss42"

EXTRA_USER_PROMPT = """## Context: a near-miss to repair

A previous attempt (gpt-oss-120b) proposed a Method-B complete-intersection construction:

  Weights: [1, 2, 2, 5, 5]
  F1 = x_0^4 + x_1^2 + x_2^2 + x_0^2 * x_1 + x_0^2 * x_2     (weighted degree 4)
  F2 = x_0^10 + x_1^5 + x_2^5 + x_3^2 + x_4^2                 (weighted degree 10)

The framework is correct (P(1,2,2,5,5) is well-formed, char-3 tame, Fano index 1), BUT the
specific polynomials FAIL:

(a) F1 contains no x_3 or x_4 terms (degree 4 < 5 = weights of x_3, x_4), so F1 ≡ 0 on the
    singular line L_{34} = {x_0=x_1=x_2=0}. At each point of L_{34} ∩ V(F2), the Jacobian of
    (F1, F2) has rank only 1 (F1's row vanishes). The CI is non-quasi-smooth at these 2 points.
    However, the local model uv + y_0^4 at these points is an A_3 Du Val (klt) singularity —
    so klt-ness *might* survive if the verifier is generous about quasi-smoothness.

(b) MORE CRITICAL: F1 | L_{12} = x_1^2 + x_2^2 and F2 | L_{12} = x_1^5 + x_2^5 have NO common
    zeros over F_3-bar. Reason: for t = x_1/x_2, t^2 = -1 forces order(t) = 4. t^5 = -1 forces
    order(t) | 10. gcd(4, 10) = 2 contradicts order(t) = 4. So L_{12} ∩ X = ∅, not 10 points
    as claimed by naive Bezout. The candidate thus has 0 + 2 = 2 singular points, far short of 8.

## Your task

Fix the L_{12} polynomial-transversality bug. Choose F1, F2 such that on the singular line L_{12}
the restricted polynomials have a non-empty common zero locus over F_3-bar.

Possible fixes:
  - Use less-symmetric polynomials, e.g. F1|L_12 = x_1^2 + x_1 x_2  or  a x_1^2 + b x_1 x_2 + c x_2^2
    with discriminant b^2 - 4ac yielding actual zeros.
  - Make sure F1|L_12 (a degree-2 polynomial in u=x_1/x_2) and F2|L_12 (degree-5) have a non-empty
    common zero set in F_3-bar. Concretely: if F1|L_12 has roots α_1, α_2 ∈ F_3-bar, then F2|L_12
    must be divisible by (u - α_1)(u - α_2) OR share at least one root with F1|L_12.

Stay within Method B in characteristic 3 (no weight divisible by 3). You may use the same
ambient P(1,2,2,5,5) or modify it.

Show:
  - F1 | L_{12} and F2 | L_{12} explicitly.
  - The common roots in F_3 or F_9.
  - F1 | L_{34} and F2 | L_{34} explicitly.
  - Total singular point count over F_3-bar.

Aim for >= 8 distinct singular points total.
"""

def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--models", default="all")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--revisions", type=int, default=2)
    args = ap.parse_args()

    models = list(MODELS.keys()) if args.models == "all" else args.models.split(",")

    ts = _ts()
    out_dir = ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{EXP_NAME}_{ts}.json"
    log_path = ROOT / "logs" / f"{EXP_NAME}_{ts}.jsonl"
    log_lock = threading.Lock()

    print(f"Models: {models}")
    print(f"Seeds: {args.seeds}, Revisions: {args.revisions}")
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
    with open(out_path, "w") as f: json.dump(summary, f, indent=1, default=str)

    print("")
    print(f"PASS: {summary['n_pass']} / {len(work)}")
    for m in models:
        cell = [r for r in results if r.get("model") == m]
        best = max((r.get("best_score", 0) for r in cell), default=0)
        print(f"  {m:18}: best_score={best}, n_trials={len(cell)}")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
