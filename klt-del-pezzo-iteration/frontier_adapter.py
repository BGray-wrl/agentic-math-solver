"""
Adapter: expose frontier_verifier with the (verify_method_b, feedback_for_revision)
interface that klt_pipeline.run_one_trial expects.

Differences from klt_verifier:
- Verification is delegated to frontier_verifier.verify_method_b_data, which uses
  exact char-p polynomial arithmetic + exact HJ-chain discrepancies + all-strata
  enumeration. See FRONTIER_VERIFIER_README.md for details.
- Verdicts are PASS / FAIL / ONE_SHORT / ESCALATE / UNSUPPORTED (frontier set).
  klt_pipeline only short-circuits on "PASS", so the others naturally flow into
  the revision loop.
"""
from __future__ import annotations
from pathlib import Path
import sys

ITER_DIR = Path("/Users/benjamingrayzel/sandbox/agentic-math-solver/klt-del-pezzo-iteration")
if str(ITER_DIR) not in sys.path:
    sys.path.insert(0, str(ITER_DIR))

from frontier_verifier import verify_method_b_data


def verify_method_b(weights, eqns, n_sing_required, char_p=3, timeout=180):
    """Returns a dict shaped like klt_verifier.verify_method_b's output."""
    res = verify_method_b_data(weights, eqns, n_sing_required, char_p)
    info = dict(res.details or {})
    return {
        "verdict": res.verdict,
        "score": res.score,
        "reason": res.reason,
        "trust": res.trust,
        "method": res.method,
        "info": info,
        "weights": weights,
        "eqns": eqns,
        "n_sing_required": n_sing_required,
        "sing_count": info.get("sing_count"),
        "rho_X": (info.get("picard_if_rational") or {}).get("rho"),
    }


def feedback_for_revision(result):
    """Construct revision feedback text from the frontier-style result dict."""
    info = result.get("info", {}) or {}
    target = result.get("n_sing_required")
    lines = [
        "## Frontier Verifier Output",
        "",
        f"Score: {result.get('score')}/7  ({result.get('verdict')})",
        f"Trust: {result.get('trust')}",
        f"Method: {result.get('method')}",
        f"Reason: {result.get('reason')}",
        "",
        "### Details:",
    ]
    if info.get("degrees"):
        lines.append(f"- equation degrees: {info['degrees']}")
    if info.get("fano_index") is not None:
        lines.append(f"- Fano index: {info['fano_index']}")
    m2 = info.get("m2") or {}
    if m2:
        if m2.get("codim_m2") is not None:
            lines.append(f"- M2 codim: {m2['codim_m2']}")
        if m2.get("quasi_smooth") is not None:
            lines.append(f"- quasi-smooth (M2): {m2['quasi_smooth']}")
        if m2.get("sing_cone_proj_dim") is not None:
            lines.append(f"- cone singular-locus projective dim: {m2['sing_cone_proj_dim']}")
    if info.get("linear_elimination"):
        le = info["linear_elimination"]
        lines.append(
            f"- LINEAR-ELIMINATION COLLAPSE: x_{le['variable']} eliminable; "
            f"X ≅ P{tuple(le['reduced_weights'])} with {le['sing_count']} sing pts, ρ=1."
        )
    strata = info.get("strata") or []
    if strata:
        lines.append(f"- strata analyzed: {len(strata)}")
        for s in strata[:8]:
            sup = s.get("support")
            stab = s.get("stabilizer")
            cnt = s.get("open_count")
            kind = s.get("kind") or s.get("status") or s.get("local_type") or "?"
            extra = f" count={cnt}" if cnt is not None else ""
            chain = s.get("hj_chain")
            chain_str = f" hj_chain={chain}" if chain else ""
            lines.append(f"    support={sup} stab={stab} kind={kind}{extra}{chain_str}")
        if len(strata) > 8:
            lines.append(f"    ...({len(strata) - 8} more)")
    if info.get("sing_count") is not None:
        lines.append(f"- TOTAL singular points found: {info['sing_count']} (need >= {target})")
    if info.get("basket_known"):
        lines.append("- known cyclic-quotient basket:")
        for b in info["basket_known"]:
            lines.append(f"    {b['count']} x {b['type']} (chain {b['chain']}, k2_corr={b['correction_each']})")
    pic = info.get("picard_if_rational")
    if pic:
        lines.append(
            f"- conditional Picard arithmetic (assumes rational resolution): "
            f"K_X^2={pic['KX2']}, corr={pic['correction']}, K_res^2={pic['Kres2']}, "
            f"R={pic['R']}, ρ_if_rational={pic['rho']}"
        )
    return "\n".join(lines)
