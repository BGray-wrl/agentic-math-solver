#!/usr/bin/env python3
"""
Conservative verifier for the FrontierMath klt del Pezzo problem.

The problem accepts multiple presentations, so this verifier deliberately
separates proof-level verification from partial signal:

  PASS             proof-level success in a supported class
  FAIL             hard failure of a necessary condition
  ONE_SHORT        otherwise plausible but too few singular points
  PARTIAL          meaningful progress, not enough for verification
  ESCALATE         numerical/structural signal, human proof still needed
  UNSUPPORTED      presentation not handled by this verifier

Supported at proof/near-proof level:
  * Method B weighted hypersurfaces / CIs for basic algebraic checks via M2.
  * Exact point counts on one-dimensional weighted strata, including endpoints.
  * Exact HJ-chain discrepancy arithmetic.
  * Method C HJ basket arithmetic when blow-up count is supplied.

Intentionally not accepted as PASS:
  * Picard rank from Lefschetz for surfaces.
  * Method C basket-only claims without blow-up/incidence/ampleness data.
  * Method A quotient claims, unless converted to Method B data.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import re
import signal
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from fractions import Fraction
from functools import reduce
from typing import Any


CHAR_DEFAULT = 3


def gcd_list(xs: list[int]) -> int:
    return reduce(math.gcd, xs, 0)


def inv_mod(a: int, p: int) -> int:
    return pow(a % p, -1, p)


def hj_correction_from_chain(chain: list[int]) -> tuple[Fraction, list[Fraction], bool]:
    """
    For an HJ chain [b1,...,bn], solve discrepancies a_i from
        M a = (b_i - 2)
    where M has -b_i on diagonal and 1 on adjacent entries.
    Then K_X^2 - K_Y^2 = -a^T M a.
    Returns (correction, discrepancies, klt_ok).
    """
    n = len(chain)
    if n == 0 or any(b < 2 for b in chain):
        return Fraction(0), [], False
    M = [[Fraction(0) for _ in range(n)] for _ in range(n)]
    rhs = [Fraction(chain[i] - 2) for i in range(n)]
    for i, b in enumerate(chain):
        M[i][i] = Fraction(-b)
        if i:
            M[i][i - 1] = Fraction(1)
        if i + 1 < n:
            M[i][i + 1] = Fraction(1)
    A = [row[:] + [rhs[i]] for i, row in enumerate(M)]
    for col in range(n):
        piv = None
        for r in range(col, n):
            if A[r][col] != 0:
                piv = r
                break
        if piv is None:
            return Fraction(0), [], False
        A[col], A[piv] = A[piv], A[col]
        pv = A[col][col]
        A[col] = [x / pv for x in A[col]]
        for r in range(n):
            if r == col:
                continue
            fac = A[r][col]
            if fac:
                A[r] = [A[r][j] - fac * A[col][j] for j in range(n + 1)]
    a = [A[i][-1] for i in range(n)]
    val = Fraction(0)
    for i in range(n):
        for j in range(n):
            val += a[i] * M[i][j] * a[j]
    return -val, a, all(x > -1 for x in a)


def hj_chain(r: int, q: int) -> list[int]:
    q %= r
    if q == 0 or math.gcd(r, q) != 1:
        return []
    out: list[int] = []
    n, d = r, q
    while d != 1:
        b = (n + d - 1) // d
        out.append(b)
        n, d = d, b * d - n
        if len(out) > 100:
            return []
    out.append(n)
    return out


def normalized_type(r: int, u: int, v: int) -> tuple[int, int] | None:
    u %= r
    v %= r
    if u == 0 and v == 0:
        return None
    if u == 0 or v == 0:
        return None
    if math.gcd(u, r) == 1:
        q = (v * inv_mod(u, r)) % r
    elif math.gcd(v, r) == 1:
        q = (u * inv_mod(v, r)) % r
    else:
        return None
    if q == 0 or math.gcd(q, r) != 1:
        return None
    return (r, q)


def poly_add(a: dict[int, int], b: dict[int, int], p: int) -> dict[int, int]:
    out = dict(a)
    for k, v in b.items():
        out[k] = (out.get(k, 0) + v) % p
        if out[k] == 0:
            del out[k]
    return out


def poly_mul(a: dict[int, int], b: dict[int, int], p: int) -> dict[int, int]:
    out: dict[int, int] = {}
    for i, ai in a.items():
        for j, bj in b.items():
            out[i + j] = (out.get(i + j, 0) + ai * bj) % p
    return {k: v for k, v in out.items() if v % p}


def poly_divmod(a: dict[int, int], b: dict[int, int], p: int) -> tuple[dict[int, int], dict[int, int]]:
    if not b:
        raise ZeroDivisionError
    r = dict(a)
    q: dict[int, int] = {}
    db = max(b)
    lb = b[db] % p
    ilb = inv_mod(lb, p)
    while r and max(r) >= db:
        dr = max(r)
        coeff = r[dr] * ilb % p
        shift = dr - db
        q[shift] = (q.get(shift, 0) + coeff) % p
        for k, v in b.items():
            kk = k + shift
            r[kk] = (r.get(kk, 0) - coeff * v) % p
            if r[kk] == 0:
                del r[kk]
    return ({k: v for k, v in q.items() if v % p}, r)


def poly_gcd(a: dict[int, int], b: dict[int, int], p: int) -> dict[int, int]:
    a = dict(a)
    b = dict(b)
    while b:
        _, r = poly_divmod(a, b, p)
        a, b = b, r
    if not a:
        return {}
    d = max(a)
    inv = inv_mod(a[d], p)
    return {k: (v * inv) % p for k, v in a.items()}


def poly_deriv(a: dict[int, int], p: int) -> dict[int, int]:
    return {k - 1: (k * v) % p for k, v in a.items() if k > 0 and (k * v) % p}


def poly_pth_root(a: dict[int, int], p: int) -> dict[int, int] | None:
    out: dict[int, int] = {}
    for k, v in a.items():
        if k % p:
            return None
        out[k // p] = v % p
    return out


def squarefree_degree(a: dict[int, int], p: int) -> int:
    if not a:
        return 0
    if max(a) == 0:
        return 0
    der = poly_deriv(a, p)
    if not der:
        root = poly_pth_root(a, p)
        if root is None:
            return 0
        return squarefree_degree(root, p)
    g = poly_gcd(a, der, p)
    q, r = poly_divmod(a, g, p)
    if r:
        return max(a)
    return max(q) if q else 0


def distinct_nonzero_roots_degree(a: dict[int, int], p: int) -> int:
    if not a:
        return 0
    deg = squarefree_degree(a, p)
    if 0 in a:
        return deg
    return max(deg - 1, 0)


def common_nonzero_roots_degree(polys: list[dict[int, int]], p: int) -> int | None:
    active = [f for f in polys if f]
    if not active:
        return None
    g = active[0]
    for f in active[1:]:
        g = poly_gcd(g, f, p)
    return distinct_nonzero_roots_degree(g, p)


def parse_polynomial(expr: str, n_vars: int, p: int) -> dict[tuple[int, ...], int]:
    s = expr.strip()
    s = s.replace(" ", "").replace("\\cdot", "*").replace("·", "*")
    s = re.sub(r"x_\{?(\d+)\}?", r"x\1", s)
    if "=" in s:
        left, right = s.split("=", 1)
        s = left + "-(" + right + ")"
    s = s.replace("(", "").replace(")", "")
    s = s.replace("-", "+-")
    if s.startswith("+-"):
        s = "-" + s[2:]
    terms = [t for t in s.split("+") if t]
    out: dict[tuple[int, ...], int] = {}
    for term in terms:
        coeff = 1
        exps = [0] * n_vars
        factors = [f for f in term.split("*") if f]
        for fac in factors:
            if re.fullmatch(r"-?\d+", fac):
                coeff *= int(fac)
                continue
            m = re.fullmatch(r"(-?)x(\d+)(?:\^(\d+))?", fac)
            if not m:
                raise ValueError(f"unsupported polynomial factor: {fac!r}")
            if m.group(1) == "-":
                coeff *= -1
            idx = int(m.group(2))
            if idx >= n_vars:
                raise ValueError(f"variable x{idx} outside weights list")
            exps[idx] += int(m.group(3) or "1")
        key = tuple(exps)
        out[key] = (out.get(key, 0) + coeff) % p
        if out[key] == 0:
            del out[key]
    return out


def restrict_poly(poly: dict[tuple[int, ...], int], support: tuple[int, ...]) -> dict[tuple[int, ...], int]:
    support_set = set(support)
    out: dict[tuple[int, ...], int] = {}
    for exp, coeff in poly.items():
        if any(e and i not in support_set for i, e in enumerate(exp)):
            continue
        out[tuple(exp[i] for i in support)] = coeff
    return out


def weighted_binary_to_univar(
    poly: dict[tuple[int, int], int],
    weights_pair: tuple[int, int],
    p: int,
) -> dict[int, int]:
    """
    Convert a homogeneous binary weighted polynomial on the open torus of
    P(a,b) to a univariate Laurent polynomial, shifted to ordinary polynomial.
    The invariant is z = x0^(b/g) / x1^(a/g).
    """
    if not poly:
        return {}
    a, b = weights_pair
    g = math.gcd(a, b)
    ap, bp = a // g, b // g
    # Monomials of same weighted degree differ by multiples of (bp, -ap).
    keys = list(poly)
    u0, v0 = keys[0]
    exps: dict[int, int] = {}
    for u, v in keys:
        du, dv = u - u0, v - v0
        if du % bp or dv % ap or du // bp != -(dv // ap):
            raise ValueError("binary terms are not on one weighted degree lattice")
        k = du // bp
        exps[k] = (exps.get(k, 0) + poly[(u, v)]) % p
    if not exps:
        return {}
    mn = min(exps)
    return {k - mn: c % p for k, c in exps.items() if c % p}


def endpoint_on_x(polys: list[dict[tuple[int, ...], int]], idx: int, p: int) -> bool:
    for poly in polys:
        val = 0
        for exp, coeff in poly.items():
            if all((j == idx and e >= 0) or e == 0 for j, e in enumerate(exp)):
                if exp[idx] > 0 and sum(e for j, e in enumerate(exp) if j != idx) == 0:
                    val = (val + coeff) % p
        if val % p:
            return False
    return True


def run_m2_basic(weights: list[int], eqns: list[str], char_p: int, timeout: int = 60) -> dict[str, Any]:
    script = f"""
p = {char_p};
weights = {{{', '.join(map(str, weights))}}};
n = #weights;
varsList = apply(n, i -> getSymbol("x" | toString i));
S = (ZZ/p)(monoid[varsList, Degrees => weights]);
use S;
eqns = apply({{{', '.join(json.dumps(e) for e in eqns)}}}, e -> value e);
print("HOMOG " | toString all(eqns, f -> f != 0 and isHomogeneous f));
if all(eqns, f -> f != 0 and isHomogeneous f) then (
  print("DEGREES " | toString apply(eqns, f -> (degree f)#0));
);
I = ideal eqns;
print("RING_DIM " | toString dim S);
print("IDEAL_DIM " | toString dim I);
print("CODIM " | toString (dim S - dim I));
J = jacobian I;
M = minors(#eqns, J);
singCone = saturate(I + M, ideal vars S);
print("QUASI_SMOOTH " | toString (singCone == ideal 1_S));
if singCone != ideal 1_S then (
  print("SING_CONE_PROJ_DIM " | toString (dim singCone - 1));
  print("SING_CONE_GENS " | toString flatten entries gens singCone);
);
print("DONE");
"""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".m2", delete=False, dir="/tmp") as f:
            f.write(script)
            path = f.name
        proc = subprocess.Popen(["M2", "--script", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
            out, err = proc.communicate()
            return {"available": True, "timeout": True, "stdout": out, "stderr": err}
    except FileNotFoundError:
        return {"available": False, "detail": "Macaulay2 not found"}
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass
    info: dict[str, Any] = {"available": True, "stdout": out, "stderr": err, "returncode": proc.returncode}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("HOMOG "):
            info["homogeneous_m2"] = line.split()[-1] == "true"
        elif line.startswith("DEGREES "):
            info["degrees_m2"] = [int(x) for x in re.findall(r"\d+", line)]
        elif line.startswith("CODIM "):
            info["codim_m2"] = int(line.split()[-1])
        elif line.startswith("QUASI_SMOOTH "):
            info["quasi_smooth"] = line.split()[-1] == "true"
        elif line.startswith("SING_CONE_PROJ_DIM "):
            info["sing_cone_proj_dim"] = int(line.split()[-1])
        elif line.startswith("SING_CONE_GENS "):
            info["sing_cone_gens"] = line.split(" ", 1)[1]
    return info


@dataclass
class VerificationResult:
    verdict: str
    score: int
    trust: str
    method: str
    reason: str
    details: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


def parse_method_b(text: str) -> tuple[list[int], list[str]] | None:
    body = text.replace("\\cdot", "*").replace("·", "*")
    body = re.sub(r"x_\{?(\d+)\}?", r"x\1", body)
    m = re.search(r"(?:Weights|weights)\s*[:=]?\s*\[\s*([0-9,\s]+)\]", body)
    if not m:
        m = re.search(r"P\((\s*\d+(?:\s*,\s*\d+)+\s*)\)", body)
    if not m:
        return None
    weights = [int(x.strip()) for x in m.group(1).split(",") if x.strip()]
    eqns: list[str] = []
    for line in body.splitlines():
        s = line.strip().strip("*")
        if not re.match(r"^(?:F\d*|Equation|Eqn)\s*[:=]", s, re.I):
            continue
        rhs = re.split(r"[:=]", s, maxsplit=1)[1].strip()
        if re.search(r"x\d", rhs):
            eqns.append(rhs)
    if not eqns:
        # Last resort: collect simple polynomial-looking lines after Answer.
        for line in body.splitlines():
            s = line.strip().strip("*")
            if re.search(r"x\d", s) and re.search(r"[+\-*^]", s) and not s.lower().startswith("weights"):
                s = re.sub(r"^[-*]\s*", "", s)
                s = re.sub(r"^F\d*\s*[:=]\s*", "", s)
                if re.match(r"^[0-9x+\-*\^()\s=]+$", s):
                    eqns.append(s)
    return (weights, eqns) if weights and eqns else None


def verify_method_b_text(text: str, target_sing: int, char_p: int = CHAR_DEFAULT) -> VerificationResult | None:
    parsed = parse_method_b(text)
    if not parsed:
        return None
    weights, eqns = parsed
    return verify_method_b_data(weights, eqns, target_sing, char_p)


def verify_method_b_data(weights: list[int], eqns: list[str], target_sing: int, char_p: int = CHAR_DEFAULT) -> VerificationResult:
    details: dict[str, Any] = {"weights": weights, "eqns": eqns, "checks": []}
    n = len(weights)
    c = len(eqns)
    if c != n - 3:
        return VerificationResult("FAIL", 1, "hard", "B", f"codimension mismatch: got {c} equations for {n} variables; surface needs {n-3}", details)
    if any(w % char_p == 0 for w in weights):
        return VerificationResult("FAIL", 1, "hard", "B", f"tameness fails: a weight is divisible by char {char_p}", details)
    for i in range(n):
        if gcd_list([weights[j] for j in range(n) if j != i]) != 1:
            return VerificationResult("FAIL", 1, "hard", "B", "weighted projective space is not well-formed", details)
    try:
        polys = [parse_polynomial(e, n, char_p) for e in eqns]
    except Exception as exc:
        return VerificationResult("FAIL", 0, "hard", "B", f"polynomial parse failed: {exc}", details)
    degrees: list[int] = []
    for poly in polys:
        ds = {sum(exp[i] * weights[i] for i in range(n)) for exp, coeff in poly.items() if coeff % char_p}
        if len(ds) != 1:
            return VerificationResult("FAIL", 0, "hard", "B", f"equation is not weight-homogeneous: degrees {sorted(ds)}", details)
        degrees.append(next(iter(ds)))
    details["degrees"] = degrees
    fano_index = sum(weights) - sum(degrees)
    details["fano_index"] = fano_index
    if fano_index <= 0:
        return VerificationResult("FAIL", 1, "hard", "B", f"Fano index {fano_index} <= 0", details)
    m2 = run_m2_basic(weights, eqns, char_p)
    details["m2"] = {k: v for k, v in m2.items() if k not in ("stdout", "stderr")}
    if m2.get("available") and not m2.get("timeout"):
        if m2.get("homogeneous_m2") is False:
            return VerificationResult("FAIL", 0, "hard", "B", "M2 says equation is not homogeneous", details)
        if m2.get("codim_m2") is not None and m2["codim_m2"] != c:
            return VerificationResult("FAIL", 2, "hard", "B", f"M2 codimension is {m2['codim_m2']}, expected {c}", details)
        if m2.get("quasi_smooth") is False:
            details["sing_cone_proj_dim"] = m2.get("sing_cone_proj_dim")
            return VerificationResult("FAIL", 3, "hard", "B", "affine cone is not quasi-smooth outside the origin", details)
    elif m2.get("timeout"):
        details["m2_warning"] = "M2 timed out; quasi-smoothness not proved"
    else:
        details["m2_warning"] = "M2 unavailable; quasi-smoothness not proved"

    # Linear elimination with unit coefficient: exact collapse to weighted projective plane.
    if c == 1:
        poly = polys[0]
        for i in range(n):
            exp = tuple(1 if j == i else 0 for j in range(n))
            if poly.get(exp, 0) % char_p:
                reduced = [w for j, w in enumerate(weights) if j != i]
                if len(reduced) == 3:
                    sing = sum(1 for w in reduced if w > 1)
                    details["linear_elimination"] = {"variable": i, "reduced_weights": reduced, "sing_count": sing, "rho": 1}
                    if sing >= target_sing:
                        return VerificationResult("PASS", 7, "hard", "B", f"linear elimination gives P{tuple(reduced)} with {sing} singular points and rho=1", details)
                    if sing == target_sing - 1:
                        return VerificationResult("ONE_SHORT", 6, "hard", "B", f"linear elimination gives only {sing} singular points", details)
                    return VerificationResult("FAIL", 5, "hard", "B", f"linear elimination gives only {sing} singular points", details)

    stratum_records: list[dict[str, Any]] = []
    total_sing = 0
    basket: list[tuple[int, int, int, list[int], Fraction]] = []
    unknown_strata: list[dict[str, Any]] = []
    positive_dim_risk = False
    for r in range(1, n + 1):
        for support in itertools.combinations(range(n), r):
            stab = gcd_list([weights[i] for i in support])
            if stab <= 1:
                continue
            rec: dict[str, Any] = {"support": support, "stabilizer": stab}
            if r == 1:
                idx = support[0]
                on = endpoint_on_x(polys, idx, char_p)
                rec["kind"] = "coordinate"
                rec["on_X"] = on
                if on and weights[idx] > 1:
                    total_sing += 1
                    rec["count"] = 1
                    if c == 1 and n == 4:
                        elim = None
                        for exp, coeff in polys[0].items():
                            if not coeff:
                                continue
                            non_idx = [j for j, e in enumerate(exp) if j != idx and e]
                            if len(non_idx) == 1 and exp[non_idx[0]] == 1:
                                elim = non_idx[0]
                                break
                        if elim is not None:
                            tang = [j for j in range(n) if j not in (idx, elim)]
                            typ = normalized_type(weights[idx], weights[tang[0]], weights[tang[1]])
                            if typ:
                                rr, q = typ
                                ch = hj_chain(rr, q)
                                corr, _, _ = hj_correction_from_chain(ch)
                                basket.append((1, rr, q, ch, corr))
                                rec["local_type"] = f"1/{rr}(1,{q})"
                                rec["hj_chain"] = ch
                                rec["eliminated_local_var"] = elim
                            else:
                                rec["local_type"] = "smooth_or_pseudoreflection_or_unknown"
                                unknown_strata.append(rec)
                        else:
                            rec["local_type"] = "coordinate_type_unknown"
                            unknown_strata.append(rec)
                    else:
                        rec["local_type"] = "coordinate_type_unknown"
                        unknown_strata.append(rec)
                stratum_records.append(rec)
                continue
            active_restrictions = []
            for poly in polys:
                rp = restrict_poly(poly, support)
                if rp:
                    active_restrictions.append(rp)
            rec["active_equations"] = len(active_restrictions)
            expected_dim = r - 1 - len(active_restrictions)
            rec["expected_open_dim"] = expected_dim
            if expected_dim > 0:
                rec["status"] = "positive_dim_or_contained"
                positive_dim_risk = True
                stratum_records.append(rec)
                continue
            if r == 2:
                unis = []
                for rp in active_restrictions:
                    bin_poly = {(exp[0], exp[1]): coeff for exp, coeff in rp.items()}
                    unis.append(weighted_binary_to_univar(bin_poly, (weights[support[0]], weights[support[1]]), char_p))
                cnt = common_nonzero_roots_degree(unis, char_p)
                if cnt is None:
                    rec["status"] = "contains_open_line"
                    positive_dim_risk = True
                else:
                    rec["open_count"] = cnt
                    if cnt:
                        total_sing += cnt
                        if c == 1 and n == 4:
                            others = [i for i in range(n) if i not in support]
                            typ = normalized_type(stab, weights[others[0]], weights[others[1]])
                            if typ:
                                rr, q = typ
                                ch = hj_chain(rr, q)
                                corr, _, _ = hj_correction_from_chain(ch)
                                basket.append((cnt, rr, q, ch, corr))
                                rec["local_type"] = f"1/{rr}(1,{q})"
                                rec["hj_chain"] = ch
                            else:
                                rec["local_type"] = "smooth_or_pseudoreflection_or_unknown"
                                unknown_strata.append(rec)
                        else:
                            rec["local_type"] = "unknown_outside_hypersurface_P3"
                            unknown_strata.append(rec)
                stratum_records.append(rec)
            else:
                rec["status"] = "zero_dim_high_dim_stratum_unimplemented"
                unknown_strata.append(rec)
                stratum_records.append(rec)
    details["strata"] = stratum_records
    details["sing_count"] = total_sing
    details["basket_known"] = [
        {"count": c0, "type": f"1/{r0}(1,{q0})", "chain": ch, "correction_each": str(corr)}
        for c0, r0, q0, ch, corr in basket
    ]
    if positive_dim_risk:
        return VerificationResult("ESCALATE", 4, "conservative", "B", "X meets a higher-dimensional isotropy stratum; local pseudoreflection/smoothness analysis needed", details)
    if total_sing < target_sing:
        if total_sing == target_sing - 1:
            return VerificationResult("ONE_SHORT", 6, "hard" if not unknown_strata else "partial", "B", f"only {total_sing} singular points found", details)
        return VerificationResult("FAIL", 4, "hard" if not unknown_strata else "partial", "B", f"only {total_sing} singular points found", details)

    if unknown_strata:
        return VerificationResult("ESCALATE", 6, "partial", "B", "count is high enough, but some local quotient/Picard data is unknown", details)

    if c == 1 and n == 4:
        prod_w = math.prod(weights)
        KX2 = Fraction(fano_index * fano_index * degrees[0], prod_w)
        C = sum(Fraction(cnt) * corr for cnt, _r, _q, _ch, corr in basket)
        R = sum(cnt * len(ch) for cnt, _r, _q, ch, _corr in basket)
        KY2 = KX2 - C
        rho_if_rational = Fraction(10) - KY2 - R
        details["picard_if_rational"] = {
            "KX2": str(KX2),
            "correction": str(C),
            "Kres2": str(KY2),
            "R": R,
            "rho": str(rho_if_rational),
        }
        if rho_if_rational != 1:
            return VerificationResult("ESCALATE", 5, "conditional", "B", f"count OK, but rho_if_rational={rho_if_rational}; independent Picard/rationality check needed", details)
        return VerificationResult("ESCALATE", 6, "conditional", "B", "count OK and rational-basket rho is 1, but Picard rank still needs proof", details)
    return VerificationResult("ESCALATE", 6, "partial", "B", "count OK, but Picard check is not implemented for this Method B format", details)


def parse_hj_basket(text: str) -> list[list[int]] | None:
    m = re.search(r"\{\s*\{[0-9,\s{}]+\}\s*\}", text)
    if not m:
        return None
    raw = m.group(0)
    chains = []
    for cm in re.finditer(r"\{([0-9,\s]+)\}", raw):
        nums = [int(x) for x in re.findall(r"\d+", cm.group(1))]
        if nums:
            chains.append(nums)
    return chains or None


def verify_method_c_text(text: str, target_sing: int) -> VerificationResult | None:
    chains = parse_hj_basket(text)
    if not chains:
        return None
    details: dict[str, Any] = {"chains": chains}
    sing = len(chains)
    R = sum(len(ch) for ch in chains)
    corrections = []
    klt = True
    for ch in chains:
        corr, disc, ok = hj_correction_from_chain(ch)
        corrections.append({"chain": ch, "correction": str(corr), "discrepancies": [str(x) for x in disc], "klt": ok})
        klt = klt and ok
    details["sing_count"] = sing
    details["R"] = R
    details["corrections"] = corrections
    details["klt_by_chains"] = klt
    b = None
    bm = re.search(r"(\d+)\s+blow[- ]?ups?", text, re.I)
    if bm:
        b = int(bm.group(1))
    else:
        bm = re.search(r"\bb\s*=\s*(\d+)", text)
        if bm:
            b = int(bm.group(1))
    base_rho = 2 if re.search(r"P\s*1\s*(?:x|×|\\times|\"|\\*)\s*P\s*1|P\^1\s*(?:x|×|\\times)\s*P\^1", text, re.I) else None
    if b is not None and base_rho is not None:
        rho = base_rho + b - R
        KY2 = Fraction(8 - b)
        KX2 = KY2 + sum(Fraction(x["correction"]) for x in corrections)
        details["base"] = "P1xP1"
        details["blowups"] = b
        details["rho"] = rho
        details["KX2"] = str(KX2)
        if not klt:
            return VerificationResult("FAIL", 3, "hard", "C", "some HJ chain is not klt", details)
        if KX2 <= 0:
            return VerificationResult("FAIL", 3, "hard", "C", f"K_X^2={KX2} is not positive", details)
        if rho != 1:
            return VerificationResult("FAIL", 4, "hard", "C", f"rho={rho}, not 1", details)
        if sing < target_sing:
            if sing == target_sing - 1:
                return VerificationResult("ONE_SHORT", 6, "numerical", "C", f"Method C basket has rho=1 but only {sing} singularities", details)
            return VerificationResult("FAIL", 4, "numerical", "C", f"Method C basket has only {sing} singularities", details)
        return VerificationResult("ESCALATE", 6, "numerical", "C", "basket numerics pass; need explicit disjoint curves and ampleness proof", details)
    if sing < target_sing:
        if sing == target_sing - 1:
            return VerificationResult("ONE_SHORT", 6, "hard_count", "C", f"HJ basket has only {sing} singularities; blow-up/rho data not supplied", details)
        return VerificationResult("FAIL", 4, "hard_count", "C", f"HJ basket has only {sing} singularities; blow-up/rho data not supplied", details)
    return VerificationResult("ESCALATE", 5, "partial", "C", "HJ basket count is high enough, but blow-up count/rho/ampleness data not supplied", details)


def verify_text(text: str, target_sing: int = 8, char_p: int = CHAR_DEFAULT) -> VerificationResult:
    # Prefer explicit Method C basket when present.
    c = verify_method_c_text(text, target_sing)
    if c:
        return c
    b = verify_method_b_text(text, target_sing, char_p)
    if b:
        return b
    if re.search(r"Method\s*A|quotient|involution|cyclic group", text, re.I):
        return VerificationResult("UNSUPPORTED", 2, "none", "A", "Method A quotient verification is not implemented; convert to fixed-point data or Method B", {})
    return VerificationResult("UNSUPPORTED", 0, "none", "unknown", "could not parse a supported Method B or Method C candidate", {})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="candidate text file; stdin if omitted")
    ap.add_argument("--target-sing", type=int, default=8)
    ap.add_argument("--char", type=int, default=3)
    args = ap.parse_args()
    if args.path:
        with open(args.path) as f:
            text = f.read()
    else:
        import sys
        text = sys.stdin.read()
    print(verify_text(text, args.target_sing, args.char).to_json())


if __name__ == "__main__":
    main()
