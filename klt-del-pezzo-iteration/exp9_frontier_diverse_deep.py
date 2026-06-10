"""
Experiment 9: high-revision (8 per trial) × diverse frameworks, using frontier_verifier.

The new verifier gives the model exact K_X^2, exact HJ basket, exact ρ_if_rational,
and per-stratum point counts on each revision. This is much richer signal than the
heuristic affdeg//gcd that earlier rounds had to work with.

Setup: 4 frameworks × 3 seeds × 3 models = 36 trials × 8 revisions each.

Frameworks (designed to span the missing solution space):
  F1 — Refined non-Fermat in P(2,2,7,7) targeting Du Val A_6 (opposite mu_7 weights).
  F2 — Mixed coprime weights P(2,5,5,7) — only one mu_5 line, partial signal genuinely cheap.
  F3 — Larger coprime-pair hypersurface P(2,2,11,13) — non-trivial mu_2 + mu_11 + mu_13 isolated pts.
  F4 — Hypersurface in P(2,5,7,11) with d divisible by carefully chosen subset of weights.
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

EXP_NAME = "klt_iter_exp9_frontier_diverse_deep"

FRAMEWORKS = [
    {
        "name": "Refined P(2,2,7,7) → Du Val A_6",
        "prompt": """Use **P(2,2,7,7)** weighted projective space over Z/3 (degree d = 14).

The Fermat F = x_0^7 + x_1^7 + x_2^2 + x_3^2 gives 9 sing pts but ρ(X) = 7 (FAIL) because
at each conic point on L_{23} the local mu_7 representation on T_P X has weights (1, 1)
(NOT opposite), giving type 1/7(1,1) which is NOT Du Val A_6.

To get Du Val A_6 = 1/7(1,6) at L_{23}: the mu_7 action on the tangent must have
OPPOSITE weights. The 2 tangent directions at the conic point are (dx_0, dx_1) with
local weights (w_0 mod 7, w_1 mod 7) = (2, 2). For Du Val, need (a, -a mod 7), e.g., (2, 5) — NOT (2, 2).

This requires a non-Fermat F that produces a different tangent direction.  Try
**polynomials where ∂F/∂x_0|_P and ∂F/∂x_1|_P are NOT both zero** at the L_{23}
conic point — e.g., F = x_0^7 + x_1^7 + x_2^2 + x_3^2 + x_0^a x_1^b x_2^c x_3^d with
exponents such that the cross term is nonzero on L_{23} after differentiation.

Concrete suggestion: try F with a term like x_0^? x_3^? that survives ∂/∂x_0 at x_2 = 0
but vanishes at x_3 = 0. Aim for ρ_if_rational = 1.

Verifier feedback will show the EXACT 1/r(1,q) type, the EXACT K_X^2 and ρ_if_rational
arithmetic, and a per-stratum basket. Use it.""",
    },
    {
        "name": "P(2,5,5,7) — single mu_5 line",
        "prompt": """Use **P(2,5,5,7)** over Z/3 (deg d divisible by w_i so all coord pts are on X).

sum_w = 19. Try d = 14 (so a = Fano index = 5).  Or d = 10 (a = 9).

Pairwise singular lines: only L_{12} (gcd(5,5)=5), since gcd(2,5)=gcd(2,7)=gcd(5,7)=1.
Coordinate points P_0 (wt 2), P_3 (wt 7) are isolated cyclic-quotient candidates if F
vanishes on them.

This is a CLEAN ambient with rich isolated singularity structure. Aim for ≥ 8 sing pts:
- L_{12} contributes (degree of F restricted to L_{12} as poly in (5,5)) / 5 points.
- For d = 14: F|_L_{12} = x_1^a x_2^b with 5a + 5b = 14 has no solution; either F restricts
  to zero or we need d divisible by 5.
- For d = 10: F|_L_{12} = a x_1^2 + b x_1 x_2 + c x_2^2 — 2 points generically (after gcd
  with isotropy).
- For d = 35: F|_L_{12} has 7 points generically.

Pick d carefully so the count is high AND coord pts P_0, P_3 are on X.

Verifier feedback will give EXACT point counts (not affdeg/gcd heuristics). Iterate.""",
    },
    {
        "name": "P(2,2,11,13) — mu_2 + isolated mu_11 + mu_13",
        "prompt": """Use **P(2,2,11,13)** over Z/3.

sum_w = 28. Try d = 22 (Fano index = 6) so F vanishes at P_0, P_1, P_2 (since 22 = 11·2).
Or d = 26 (Fano index = 2).

Singular structure:
- L_{01}: gcd(2,2) = 2 (singular line with mu_2 action).
- L_{23}: gcd(11,13) = 1 — NOT singular (no isotropy).
- Coord pts P_2 (wt 11) and P_3 (wt 13) are isolated 1/11 and 1/13 sings IF on X.
- Coord pts P_0, P_1 are part of L_{01} endpoint structure.

For d = 22 (degree-11 in x_0, x_1; degree-2 in x_2; degree must be 22), monomials include
x_0^11, x_1^11, x_2^2 (these give P_3 on X), x_3 * something of weight 9 (no clean monomial).

Try: F = x_0^11 + x_1^11 + x_2^2 + x_2 · g_11(x_0, x_1) + x_3 · h_9(...). Hmm, 9 not weight-attainable.

Better: d = 26. Then monomials x_0^13, x_1^13, x_2 · x_3 (wt 11+13=24, nope), x_3^2 (26).
F = x_0^13 + x_1^13 + x_2^2 · x_0 ... hmm, weight 22 + 2 = 24. Try x_2^? x_3^? such that
11a + 13b = 26: a=0, b=2 → x_3^2; a=... 11a = 26 - 13b. For b=0: a doesn't exist. For b=1: a = 13/11.

OK pick d = 22: F = x_0^11 + x_1^11 + x_2^2 · (low deg in x_0, x_1) + ... Try F where:
- F has degree 22.
- P_2 = [0:0:1:0]: F(P_2) = (coef of x_2^2) — yes, must vanish at P_2, so no pure x_2^2 term.
- P_3: F(P_3) = (coef of x_3^?). 13 doesn't divide 22, so no pure x_3^k. P_3 on X automatically.

Aim: produce many sing pts on L_{01} ∩ X (≥ 6) PLUS isolated coord pts at P_2, P_3.""",
    },
    {
        "name": "P(2,5,7,11) — all-coprime hypersurface",
        "prompt": """Use **P(2,5,7,11)** over Z/3. All pairwise gcds = 1, so NO singular lines.
Only isolated 1/w_k sings at coord points P_k (k = 0, 1, 2, 3) if P_k on X.

sum_w = 25. d divisibility matters: we want F vanishing at P_0, P_1, P_2, P_3.
- F(P_k) = (coef of x_k^{d/w_k} if w_k | d, else 0). To force F(P_k) ≠ 0 we need w_k | d
  AND a nonzero coefficient on x_k^{d/w_k}.

With only 4 coord-pt sings, this CANNOT reach 8. **But** this framework is useful for:
1. Producing partial signal at score 4–6 with EXACT ρ_if_rational arithmetic.
2. Testing if cleaner-ambient candidates approach ρ = 1.
3. Models can use a slightly different ambient — e.g., a CI extension P(2,5,7,11, w_5)
   with 2 equations to get more isolated sing pts.

Suggestion: instead of pure hypersurface, try **P(2,5,7,11, w_5) CI of 2** with carefully
chosen w_5 (e.g., 13 or 17) and degrees (d_1, d_2) chosen so that:
- CI has dim 2 (codim 2 in 4-dim ambient — surface).
- Multiple coord pts P_k are on X.
- Pairwise gcd matters: gcd(w_5, w_k) > 1 for some k to introduce a singular line.

E.g., P(2,2,5,7,11) with d_1 = 10, d_2 = 14. mu_2 line L_{01}.

Iterate using the verifier feedback (it gives EXACT point counts).""",
    },
]


def make_user_prompt(framework, N_sing):
    return f"""You MUST use the following framework. No deviation from the ambient or equation shape.

**Framework: {framework['name']}**

{framework['prompt']}

Find a klt del Pezzo surface X in this framework with rho(X) = 1 and >= {N_sing} singular points
(char 3, klt singularities).

CRITICAL: The verifier now uses EXACT arithmetic (not heuristics). It will give you:
- exact ρ_if_rational from the cyclic-quotient basket + K_X^2 formula;
- exact point counts on each stratum (no affdeg/gcd approximation);
- LINEAR-ELIMINATION COLLAPSE detection — if F is linear in any variable with constant
  coefficient, X collapses to a lower-dim weighted projective space. DO NOT submit such F.
Iterate against this exact feedback. Aim for ρ = 1.
"""


def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--models", default="all")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--revisions", type=int, default=8)
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
    print(f"Output JSON:  {out_path}")
    print(f"Logs:         {log_path}")
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
            print(f"{tag} status={tr['status']} best_score={tr['best_score']} rounds={len(tr.get('rounds',[]))}", flush=True)
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
    print(f"elapsed: {elapsed}s")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
