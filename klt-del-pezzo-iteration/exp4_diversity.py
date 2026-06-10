"""
Experiment 4: Forced diversity across weight sets.

Goal: explore weight-set space more broadly. The same-three-models keep landing on P(2,2,5,5)
or P(1,2,2,5,5). Try forcing each model to commit to a SPECIFIC weight set chosen for diversity.

Pre-selected weight families per seed (cycled across trials):
  seed=42: P(2,2,5,5,7)   (5-var; adds w=7 isolated coord with no quasi-smooth issue if d uses x_4)
  seed=43: P(2,2,5,5,11)  (5-var; w=11 isolated)
  seed=44: P(1,2,2,5,5,7) (6-var CI of 2 → 3-fold, NOT a surface! skip)  → use P(1,2,2,5,7) instead
  seed=45: P(2,5,5,7)     (4-var, 3-fold ambient; just hypersurface)
  seed=46: P(1,1,2,2,5,5) (6-var CI of 3 → surface)
  seed=47: P(2,2,2,5,5) — non-well-formed! Replace with P(2,2,5,5,4) which has 2-dim singular stratum, also no good. Use P(1,2,2,5,7).

Final list of 4 diverse weight sets to test (4-5 var, surface-yielding):
  W1: P(2,2,5,5,7)       (4-dim ambient, 2 eq CI → surface)
  W2: P(2,2,5,5,11)      (4-dim ambient, 2 eq CI)
  W3: P(1,2,2,5,7)       (3-dim ambient, hypersurface → surface)
  W4: P(2,5,5,7)         (3-dim ambient, hypersurface → surface; expect FEW sing pts)

Each cell: 3 models × 4 weight sets × 2 seeds = 24 trials. 2 revisions each.
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

EXP_NAME = "klt_iter_exp4_diversity"

WEIGHT_SETS = [
    {"name": "P(2,2,5,5,7) CI", "weights": [2,2,5,5,7], "kind": "CI", "n_eqns": 2,
     "advice": "P(2,2,5,5,7) is a 4-dim weighted PS; surface = CI of 2 hypersurfaces. Pick degrees (d1, d2) with d1+d2 < 21 = sum_w, each d_i compatible with L_{01} (gcd 2), L_{23} (gcd 5), and coord point P_4 (weight 7) quasi-smoothness."},
    {"name": "P(2,2,5,5,11) CI", "weights": [2,2,5,5,11], "kind": "CI", "n_eqns": 2,
     "advice": "P(2,2,5,5,11) is a 4-dim weighted PS; surface = CI of 2. Sum_w = 25. Pick d1, d2 each divisible by 2 and 5 (to engage L_{01} and L_{23}), and include monomial x_4 in some F_i to keep coord point P_4 off X."},
    {"name": "P(1,2,2,5,7) hyp", "weights": [1,2,2,5,7], "kind": "hyp", "n_eqns": 1,
     "advice": "P(1,2,2,5,7) is 3-dim ambient; surface = single hypersurface. Sum_w = 17. Pick degree d divisible by 2 (to engage L_{12}) and avoid putting coord points P_3 (weight 5) or P_4 (weight 7) on X without quasi-smoothness. NOTE: only one gcd-pair (1,2) — L_{12}. Hard to reach 8 singular points without extras."},
    {"name": "P(2,5,5,7) hyp", "weights": [2,5,5,7], "kind": "hyp", "n_eqns": 1,
     "advice": "P(2,5,5,7) is 3-dim ambient; surface = single hypersurface. Sum_w = 19. Pair (2,3) has gcd 5 (line L_{23}). No other gcd-pair > 1. Coord points P_0 (weight 2) and P_3 (weight 7) potentially on X."},
]


def make_user_prompt(weight_set, N_sing):
    return f"""You MUST use Method B with the following ambient (no exceptions):

**Required ambient**: P{tuple(weight_set['weights'])} over Z/3 (a {weight_set['kind']} construction).
**Number of equations**: {weight_set['n_eqns']}.

{weight_set['advice']}

Working in characteristic 3, produce a klt del Pezzo surface X in this ambient with Picard number rho(X)=1 and AT LEAST {N_sing} singular points.

Constraints:
- All weights are coprime to 3 (verify before committing).
- Equations weighted-homogeneous; Fano index > 0.
- Quasi-smooth (affine cone smooth outside origin).
- Singular point count over F_3-bar (algebraic closure) >= {N_sing}.

CRITICAL: bezout transversality must hold for your specific polynomial choices. Pure symmetric forms
like x^a + y^a paired with x^b + y^b often have EMPTY common zero locus over F_3-bar. Compute the
explicit roots on each singular stratum.

Show your work in detail (per-stratum point count over F_3-bar), then commit your answer in the required format.
"""


def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2)
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

    print(f"Models: {models}")
    print(f"Weight sets: {[w['name'] for w in WEIGHT_SETS]}")
    print(f"Seeds: {args.seeds}")
    work = [(m, ws, s) for m in models for ws in WEIGHT_SETS for s in range(42, 42 + args.seeds)]
    print(f"Total trials: {len(work)}")

    results = []
    t_start = time.time()

    def go(model_key, weight_set, seed):
        tag = f"[{model_key}|{weight_set['name']}|seed={seed}]"
        print(f"{tag} START", flush=True)
        try:
            tr = run_one_trial(
                model_key=model_key,
                n_sing_required=8,
                seed=seed,
                extra_user_prompt=make_user_prompt(weight_set, 8),
                revisions=args.revisions,
            )
            tr["seed"] = seed; tr["model"] = model_key; tr["weight_set"] = weight_set["name"]
            print(f"{tag} status={tr['status']} best_score={tr['best_score']}", flush=True)
            with log_lock: log_jsonl(tr, log_path)
            return tr
        except Exception as e:
            print(f"{tag} ERROR: {e}", flush=True)
            err = {"model": model_key, "weight_set": weight_set["name"], "seed": seed, "error": str(e), "status": "ERROR"}
            with log_lock: log_jsonl(err, log_path)
            return err

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(go, *w): w for w in work}
        for fu in as_completed(futs):
            results.append(fu.result())

    elapsed = round(time.time() - t_start, 1)
    summary = {
        "experiment": EXP_NAME, "timestamp": ts, "elapsed_s": elapsed,
        "models": models, "weight_sets": [w["name"] for w in WEIGHT_SETS],
        "n_seeds": args.seeds, "revisions": args.revisions,
        "n_pass": sum(1 for r in results if r.get("status") == "PASS"),
        "n_fail": sum(1 for r in results if r.get("status") == "FAIL"),
        "n_error": sum(1 for r in results if r.get("status") == "ERROR"),
        "results": results,
    }
    with open(out_path, "w") as f: json.dump(summary, f, indent=1, default=str)

    print("")
    print(f"PASS: {summary['n_pass']} / {len(work)}")
    for m in models:
        for ws in WEIGHT_SETS:
            cell = [r for r in results if r.get("model")==m and r.get("weight_set")==ws["name"]]
            best = max((r.get("best_score",0) for r in cell), default=0)
            print(f"  {m:18} {ws['name']:25}: best_score={best}")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
