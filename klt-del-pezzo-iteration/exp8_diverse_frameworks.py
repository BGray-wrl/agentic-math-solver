"""
Experiment 8: forced framework diversity.

For each (model, seed), assign a specific framework family to explore. This forces models
to attempt structures they wouldn't naturally try, increasing the chance of finding a real
solution AND producing diverse partial-signal threads.

Frameworks attempted:
- F1: Method A quotient (CI(2,2)/involution in P^4)
- F2: Hypersurface with intentionally non-Fermat F (mixed monomials)
- F3: P(1,2,5,7) hypersurface (no singular lines, max 3 sing pts from coord pts)
- F4: P(2,2,5,5) with cross-term F (e.g., F = x_0^2 x_2 + x_1^2 x_3 + x_0 x_2 x_3 + ...)
- F5: Non-Fermat in P(2,2,7,7)
- F6: P(1,1,2,2,5,5) CI of 3
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

EXP_NAME = "klt_iter_exp8_diverse_frameworks"

FRAMEWORKS = [
    {
        "name": "Method A: quotient of CI(2,2) in P^4",
        "prompt": """Use **Method A**: start with smooth CI(2,2) ⊂ P^4 over Z/3, find a diagonal involution g (each entry ±1) that is free in codimension 1 (no fixed curve), and quotient. The fixed points of g on Y = CI(2,2) become the singular points of X = Y/<g>. Diagonal involutions can give up to 4 fixed points on Y. Aim for as many as possible.

Output format (Method A):
- g as a list of 5 integers, each +1 or -1.
- Y as two quadrics in x0..x4, each g-invariant (i.e., each monomial has even number of g=-1 variables)."""
    },
    {
        "name": "Non-Fermat in P(2,2,7,7)",
        "prompt": """Use **Method B with a NON-Fermat polynomial in P(2,2,7,7)** over Z/3 (degree 14).

Recall: F = x_0^7 + x_1^7 + x_2^2 + x_3^2 gives 9 singular points but ρ(X) = 7 (FAILS). The issue is that the singularities at L_{23} have type 1/7(1, 1).

To get Du Val A_6 singularities (which would have ρ = 1 contribution) at L_{23}, the mu_7 action on the local tangent must have OPPOSITE weights (one of weight 1, other of weight 6 ≡ -1 mod 7). This means the polynomial must NOT be purely Fermat — try mixed monomials like x_0^a x_1^b x_2^c x_3^d with carefully tuned exponents.

For example: try F = x_0^7 + x_1^7 + x_2^2 + x_3^2 + x_0^3 x_1^3 x_2 + ... (the cross terms break the symmetry).

Show your analysis: at each conic point on L_{23}, what are the local mu_7 weights on T_P X?"""
    },
    {
        "name": "P(1,2,5,7) hypersurface (few sing pts; partial signal)",
        "prompt": """Use **P(1, 2, 5, 7)** weighted projective space over Z/3 (a 3-dim ambient with no singular lines — only isolated coord-point singularities of types 1/2, 1/5, 1/7). This gives at most 3 singular points (one per coord pt with weight > 1), which is too few for ≥7/8 singular points. **However**, working in this ambient can produce useful partial signal about how ρ(X) interacts with isolated sings.

Pick a degree d with sum_w - d > 0 (e.g., d = 8 or 10), arrange F so that all three coord points P_1, P_2, P_3 lie on X with quasi-smoothness preserved. Report the type of each singularity and ρ(X)."""
    },
    {
        "name": "P(2,2,5,5,5) CI of 2 with engineered crossbar",
        "prompt": """Use **P(2, 2, 5, 5, 5) CI of 2** (5-var, ambient dim 4, surface = codim 2). Note: 3 weight-5 vars share gcd 5, giving a 2-dim mu_5 singular plane. Earlier work showed this leads to pseudoreflection-risk along a curve. **BUT** if X meets the plane in 0-dim isolated points (not a curve), the points contribute genuinely.

Design F1, F2 such that:
- F1 of degree 10 (divisible by both 2 and 5).
- F2 of degree d (sum_w - 10 - d > 0).
- Both F1, F2 RESTRICTED to the mu_5 plane should give a 0-dim subscheme (transverse intersection in the plane).

Try various polynomial choices that achieve this."""
    },
    {
        "name": "P(1, 1, 2, 2, 5, 5) CI of 3",
        "prompt": """Use **P(1, 1, 2, 2, 5, 5) CI of 3 equations** (6-var, ambient dim 5, surface = codim 3). Sum_w = 16. Pick (d1, d2, d3) with sum < 16. The mu_2 line is L_{23} (weights 2, 2); mu_5 line is L_{45} (weights 5, 5). Both 1-dim, no 2-dim singular strata."""
    },
]


def make_user_prompt(framework, N_sing):
    return f"""You MUST use the following framework. No deviation.

**Framework: {framework['name']}**

{framework['prompt']}

Find a klt del Pezzo surface X in this framework with rho(X) = 1 and >= {N_sing} singular points (char 3, klt singularities).

CRITICAL: ρ(X) = 1 requires very careful work — use the verifier feedback to iterate.
"""


def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--models", default="all")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--revisions", type=int, default=4)
    args = ap.parse_args()

    models = list(MODELS.keys()) if args.models == "all" else args.models.split(",")
    ts = _ts()
    out_dir = ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{EXP_NAME}_{ts}.json"
    log_path = ROOT / "logs" / f"{EXP_NAME}_{ts}.jsonl"
    log_lock = threading.Lock()

    work = [(m, fw, s) for m in models for fw in FRAMEWORKS for s in range(42, 42 + args.seeds)]
    print(f"Total trials: {len(work)} ({args.revisions} revisions each)")
    results = []
    t_start = time.time()

    def go(model_key, framework, seed):
        tag = f"[{model_key}|{framework['name'][:30]}|seed={seed}]"
        print(f"{tag} START", flush=True)
        try:
            tr = run_one_trial(
                model_key=model_key, n_sing_required=8, seed=seed,
                extra_user_prompt=make_user_prompt(framework, 8),
                revisions=args.revisions,
            )
            tr["seed"] = seed; tr["model"] = model_key; tr["framework"] = framework["name"]
            print(f"{tag} status={tr['status']} best_score={tr['best_score']}", flush=True)
            with log_lock: log_jsonl(tr, log_path)
            return tr
        except Exception as e:
            print(f"{tag} ERROR: {e}", flush=True)
            err = {"model": model_key, "framework": framework["name"], "seed": seed, "error": str(e), "status": "ERROR"}
            with log_lock: log_jsonl(err, log_path)
            return err

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(go, *w): w for w in work}
        for fu in as_completed(futs):
            results.append(fu.result())

    elapsed = round(time.time() - t_start, 1)
    summary = {
        "experiment": EXP_NAME, "timestamp": ts, "elapsed_s": elapsed,
        "models": models, "frameworks": [f["name"] for f in FRAMEWORKS],
        "n_seeds": args.seeds, "revisions": args.revisions,
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
