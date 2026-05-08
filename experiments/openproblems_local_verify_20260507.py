#!/usr/bin/env python3
"""
Local verifiers for FrontierMath open-problem solutions where we can actually
check correctness without Magma/Sage. Run on Phase-1 results to filter the
real positives from LLM-judge hallucinations.

Verifiable here:
  - hadamard           : H @ H.T == n*I, entries ±1
  - large-steiner-systems : every r-subset covered exactly once
  - ramsey-book-graphs : no B_{n-1} in G, no B_n in complement
  - small-diophantine  : plug into z^2 + y^2 z + x^3 + 2 = 0
  - degree-sensitivity-boolean : multilinear poly, Boolean on cube, sensitivity formula
  - explicit-deformations : check ideal generators specialize to A at eps=0,
                            and to k[t]/(t^N) at eps=1 (best-effort sympy check)

Not verified locally (needs Magma/Sage):
  - inverse-galois (Galois group computation)
  - klt-del-pezzo-surface (Macaulay2 / scheme theory)
  - q2-absolute-galois (profinite group presentation)
  - arithmetic-kakeya (custom forcing-graph verifier)
  - prime-factorization (algorithm, not a single answer)
  - symplectic-ball-packing (Hamiltonian flow check)
  - unknotting-number (custom knot algorithm)
  - stretched-lr-coefficients (LR symmetric function check)

Usage:
  uv run experiments/openproblems_local_verify_20260507.py <log.jsonl>
  uv run experiments/openproblems_local_verify_20260507.py <log.jsonl> --pid hadamard
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import _kakeya_verifier as _kv
import _lr_verifier as _lr

# ---------- Helpers ----------
def extract_after_answer(text: str) -> str:
    """Pull out the '## Answer' section, fallback to whole text."""
    m = re.search(r"##\s*Answer\s*\n", text, re.I)
    if m:
        return text[m.end():].strip()
    return text.strip()


# ---------- Hadamard ----------
def verify_hadamard(text: str, expected_n: int) -> tuple[bool, str]:
    body = extract_after_answer(text)
    # Strip code fences
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    # Parse CSV
    rows = []
    for line in body.splitlines():
        line = line.strip().strip(",")
        if not line: continue
        # Tokens are ±1, possibly comma- or space-separated
        toks = re.split(r"[,\s]+", line)
        try:
            row = [int(t) for t in toks if t]
        except ValueError:
            return False, f"non-integer token in row: {line[:80]}"
        if not row: continue
        rows.append(row)
    n = len(rows)
    if n != expected_n:
        return False, f"got {n} rows, expected {expected_n}"
    if any(len(r) != n for r in rows):
        return False, "non-square"
    if any(abs(v) != 1 for r in rows for v in r):
        return False, "entries not all ±1"
    # Check H H^T = n I
    import numpy as np
    H = np.array(rows, dtype=int)
    P = H @ H.T
    expected = expected_n * np.eye(expected_n, dtype=int)
    if not np.array_equal(P, expected):
        return False, f"H H^T != {expected_n}*I"
    return True, "PASS"


# ---------- Steiner systems ----------
def verify_steiner(text: str, r_constraint: str = "warmup") -> tuple[bool, str]:
    body = extract_after_answer(text)
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    if not lines:
        return False, "empty"
    header = lines[0]
    m = re.match(r"#?\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)", header)
    if not m: return False, f"bad header: {header[:80]}"
    n, q, r = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (n > q > r):
        return False, f"need n>q>r, got {n},{q},{r}"
    if n >= 200:
        return False, f"n>={n} >= 200"
    if r_constraint == "warmup" and r != 5:
        return False, f"warmup requires r=5, got r={r}"
    if r_constraint == "full" and not (5 < r < 10):
        return False, f"full requires r in (6,7,8,9), got r={r}"
    blocks = []
    for line in lines[1:]:
        # Stop at first non-numeric line (defends against trailing prose)
        try:
            block = tuple(sorted(int(x) for x in line.split()))
        except ValueError:
            break
        if len(block) != q:
            return False, f"block size {len(block)} != q={q}"
        if len(set(block)) != q:
            return False, f"duplicate in block: {block}"
        blocks.append(block)
    # Detect 0-indexed vs 1-indexed
    all_vals = {v for b in blocks for v in b}
    if not all_vals:
        return False, "no blocks"
    if min(all_vals) == 0 and max(all_vals) == n - 1:
        # 0-indexed; shift to 1-indexed
        blocks = [tuple(sorted(v + 1 for v in b)) for b in blocks]
    elif min(all_vals) == 1 and max(all_vals) == n:
        pass  # 1-indexed, OK
    else:
        return False, f"index range {min(all_vals)}..{max(all_vals)} doesn't fit n={n}"
    # Check every r-subset of [n] covered exactly once
    from itertools import combinations
    cov = {}
    for B in blocks:
        for sub in combinations(B, r):
            cov[sub] = cov.get(sub, 0) + 1
    n_choose_r = 1
    for i in range(r):
        n_choose_r = n_choose_r * (n - i) // (i + 1)
    if len(cov) != n_choose_r:
        return False, f"covered {len(cov)} of {n_choose_r} r-subsets"
    if any(v != 1 for v in cov.values()):
        bad = [k for k,v in cov.items() if v != 1][:3]
        return False, f"r-subsets not covered exactly once (e.g. {bad})"
    return True, f"PASS (n={n}, q={q}, r={r}, {len(blocks)} blocks)"


# ---------- Ramsey book graphs ----------
def adjstr_to_matrix(s: str, expected_n: int) -> "np.ndarray | None":
    import numpy as np
    s = re.sub(r"\s", "", s)
    s = re.sub(r"[^01]", "", s)
    expected = expected_n * (expected_n - 1) // 2
    if len(s) != expected:
        return None
    A = np.zeros((expected_n, expected_n), dtype=int)
    idx = 0
    for j in range(1, expected_n):
        for i in range(j):
            A[i,j] = int(s[idx]); A[j,i] = A[i,j]; idx += 1
    return A


def has_book(A, n_pages):
    """Returns True iff the graph A contains B_{n_pages} (an edge with n common neighbors)."""
    import numpy as np
    N = A.shape[0]
    if n_pages == 0: return False
    for i in range(N):
        for j in range(i+1, N):
            if A[i,j] == 0: continue
            common = (A[i] & A[j]).sum()
            if common >= n_pages:
                return True
    return False


def verify_ramsey_book_warmup(text: str) -> tuple[bool, str]:
    """Warmup: 98-vertex graph, no B_{24} in G, no B_{25} in complement."""
    import numpy as np
    body = extract_after_answer(text)
    body = re.sub(r"\s+", "", body)
    A = adjstr_to_matrix(body, 98)
    if A is None: return False, f"adj string length wrong (got {len(body)} of needed 4753)"
    np.fill_diagonal(A, 0)
    if has_book(A, 24): return False, "G contains B_{24}"
    Ac = 1 - A; np.fill_diagonal(Ac, 0)
    if has_book(Ac, 25): return False, "complement contains B_{25}"
    return True, "PASS"


# ---------- Small diophantine ----------
def verify_small_diophantine(text: str) -> tuple[bool, str]:
    """Find 3 distinct (x,y,z) with z^2+y^2 z+x^3+2=0 and |x|>10^50."""
    body = extract_after_answer(text)
    # Parse triples (x,y,z) — a tuple regex
    triples = re.findall(r"\(\s*([\-\d]+)\s*,\s*([\-\d]+)\s*,\s*([\-\d]+)\s*\)", body)
    if len(triples) < 3:
        return False, f"found {len(triples)} triples, need 3"
    xs = set()
    for sx, sy, sz in triples[:3]:
        try:
            x, y, z = int(sx), int(sy), int(sz)
        except ValueError:
            return False, f"non-int triple: {sx},{sy},{sz}"
        if abs(x) <= 10**50:
            return False, f"|x| too small: {x}"
        if z*z + y*y*z + x**3 + 2 != 0:
            return False, f"({x},{y},{z}) not a solution"
        xs.add(x)
    if len(xs) < 3:
        return False, f"only {len(xs)} distinct x values"
    return True, f"PASS (3 distinct solutions, |x| up to {max(abs(int(t[0])) for t in triples[:3])})"


# ---------- Degree-sensitivity-boolean ----------
def verify_degree_sensitivity(text: str, threshold_a: float = 1.63) -> tuple[bool, str]:
    """Multilinear poly P over {0,1}^n that is Boolean on cube, with sensitivity_at_0 = deg(P)^a, a > threshold."""
    import sympy as sp
    body = extract_after_answer(text)
    # Strip code fences
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    # Try to find a clean polynomial expression: longest line composed only of x_i, ints, +, -, *, parens, spaces
    candidates = []
    # Whole body if clean
    if re.fullmatch(r"[\sx0-9+\-*()\.]+", body.replace("**","")):
        candidates.append(body)
    for ln in body.split("\n"):
        ln = ln.strip()
        if "x" in ln and re.fullmatch(r"[\sx0-9+\-*()\.]+", ln.replace("**","")):
            candidates.append(ln)
    if candidates:
        body = max(candidates, key=len)
    # Find variables x1, x2, ...
    vars_used = sorted(set(int(v) for v in re.findall(r"\bx(\d+)\b", body)))
    if not vars_used:
        return False, "no x_i variables"
    n = max(vars_used)
    if n > 100 or n < 2:
        return False, f"n={n} out of range"
    syms = {i: sp.Symbol(f"x{i}") for i in vars_used}
    # Replace variable names with sympy symbols
    expr_str = body
    # Parse safely: only allow x_i, integers, +, -, *, parens
    if not re.fullmatch(r"[\sx0-9+\-*()\.]+", expr_str.replace("\n","").replace("**","")):
        # Try anyway but with replace
        pass
    try:
        P = sp.sympify(expr_str, locals={f"x{i}": s for i,s in syms.items()})
    except Exception as e:
        return False, f"sympy parse failed: {e}"
    # Check multilinear: expand and ensure each variable has degree ≤ 1 in every monomial
    P = sp.expand(P)
    from sympy import Poly
    try:
        all_syms = [sp.Symbol(f"x{i}") for i in range(1, n+1)]
        poly = Poly(P, *all_syms)
        for monom, _ in poly.terms():
            if any(d > 1 for d in monom):
                return False, "not multilinear"
    except Exception as e:
        return False, f"poly form error: {e}"

    # Boolean on cube — check all 2^n if n <= 20
    if n > 20:
        return False, f"n={n} too large for full cube check (cap=20)"
    bool_check = True
    P0 = P.subs({sp.Symbol(f"x{i}"):0 for i in range(1,n+1)})
    deg = max(sum(m) for m in poly.monoms()) if poly.monoms() else 0
    if deg <= 1:
        return False, f"deg(P)={deg}, need >1"
    sens = 0
    P_int = sp.Integer(P0)
    if P_int not in (0, 1):
        return False, f"P(0)={P0} not in {{0,1}}"
    for i in range(1, n+1):
        sub = {sp.Symbol(f"x{j}"): (1 if j == i else 0) for j in range(1, n+1)}
        Pi = P.subs(sub)
        if Pi not in (0, 1):
            return False, f"P(e_{i})={Pi} not in {{0,1}}"
        sens += abs(int(P0) - int(Pi))
    # Check Boolean on entire cube
    from itertools import product
    for assign in product([0,1], repeat=n):
        sub = {sp.Symbol(f"x{i+1}"): a for i,a in enumerate(assign)}
        v = P.subs(sub)
        if v not in (0, 1):
            return False, f"P({assign})={v} not in {{0,1}}"
    # sensitivity = deg^a
    if sens <= 0 or deg <= 1:
        return False, f"sens={sens}, deg={deg}"
    import math
    a = math.log(sens) / math.log(deg)
    if a <= threshold_a:
        return False, f"a={a:.4f} not > {threshold_a}"
    return True, f"PASS (n={n}, deg={deg}, sens={sens}, a={a:.4f})"


# ---------- Dispatch ----------
def expected_hadamard_n(prompt_type: str) -> int:
    return 428 if prompt_type == "warmup" else 668

# ---------- Explicit deformations (warmup: k[t]/(t^3) ↔ k[x,y]/(x,y)^2) ----------
def verify_explicit_deformations_warmup(text: str) -> tuple[bool, str]:
    """
    For the warmup, A = k[x,y]/(x,y)^2 has Hilbert function (1,2,0,...) and dim_k = 3.
    The generic fiber must be k[t]/(t^3) which has Hilbert function (1,1,1,0,...) and dim_k = 3.
    We check, by computing Groebner bases at eps=0 and eps=1, that:
      - dim_k of quotient at eps=0 is 3
      - dim_k of quotient at eps=1 is 3
      - the special fiber I|_{eps=0} ⊆ (x_1,...,x_s)^2 (so it kills all degree-1 monomials in m^2)
      - the generic fiber is curvilinear (dim of m/m^2 is 1)
    """
    import sympy as sp
    body = extract_after_answer(text)
    # Try to extract I_gens
    m = re.search(r"I_gens\s*=\s*\[(.*?)\]", body, re.DOTALL)
    if not m: return False, "no I_gens list found"
    gens_text = m.group(1)
    # Parse Python list of sympy exprs naively
    items = re.split(r",\s*\n", gens_text)
    items = [it.strip().rstrip(",").strip() for it in items if it.strip()]
    items = [it for it in items if it and not it.startswith("#")]
    if len(items) < 1: return False, "no generators"
    # Find x variables and eps
    var_names = sorted(set(re.findall(r"\bx(\d+)\b", gens_text)), key=int)
    if not var_names: return False, "no x_i variables"
    syms = {f"x{n}": sp.Symbol(f"x{n}") for n in var_names}
    syms["eps"] = sp.Symbol("eps")
    s = len(var_names)
    try:
        gens = [sp.sympify(it.replace("**", "**"), locals=syms) for it in items]
    except Exception as e:
        return False, f"parse failed: {e}"
    x_syms = [syms[f"x{n}"] for n in var_names]
    eps = syms["eps"]
    # Special fiber I|_eps=0
    gens_0 = [g.subs(eps, 0) for g in gens]
    # Generic fiber I|_eps=1
    gens_1 = [g.subs(eps, 1) for g in gens]
    try:
        gb0 = sp.groebner(gens_0, *x_syms, order="grevlex")
        gb1 = sp.groebner(gens_1, *x_syms, order="grevlex")
    except Exception as e:
        return False, f"groebner failed: {e}"
    # Compute monomial basis (by degree) modulo each ideal up to total degree 5
    def basis_of_quotient(gb, deg_cap=5):
        """Return basis of k[x_syms]/gb as monomials of total deg <= deg_cap that are not in lt(gb)."""
        from itertools import product
        lts = [sp.LM(p, *x_syms) for p in gb]
        bas = []
        for d in range(deg_cap+1):
            for exps in product(range(d+1), repeat=s):
                if sum(exps) != d: continue
                mono = sp.prod([x_syms[i]**exps[i] for i in range(s)])
                # Check if any lt divides mono
                divisible = False
                for lt in lts:
                    if lt == 0: continue
                    lt_exps = [int(lt.as_poly(*x_syms).monoms()[0][i]) if lt.has(x_syms[i]) else 0 for i in range(s)] if hasattr(lt,'as_poly') else None
                    if lt_exps is None: continue
                    if all(exps[i] >= lt_exps[i] for i in range(s)):
                        divisible = True; break
                if not divisible: bas.append(mono)
        return bas
    # Use sympy's PolyRing quotient instead — simpler approach via reductions
    def dim_quotient(gb_basis, x_syms, deg_cap=8):
        """Brute force monomial counting up to deg_cap, modulo gb."""
        from itertools import product
        s = len(x_syms)
        # Get leading monomials' exponent tuples
        lt_exps_list = []
        for p in gb_basis:
            poly = sp.Poly(p, *x_syms)
            if poly.is_zero: continue
            mono = poly.monoms()[0]  # leading monomial in grlex order
            lt_exps_list.append(mono)
        bas = 0
        nonzero_bas = set()
        for d in range(deg_cap+1):
            for exps in product(range(d+1), repeat=s):
                if sum(exps) != d: continue
                # Check divisibility
                if any(all(exps[i] >= le[i] for i in range(s)) for le in lt_exps_list):
                    continue
                bas += 1
                nonzero_bas.add(exps)
        return bas, nonzero_bas
    try:
        d0, basis0 = dim_quotient(list(gb0), x_syms, deg_cap=8)
        d1, basis1 = dim_quotient(list(gb1), x_syms, deg_cap=8)
    except Exception as e:
        return False, f"dim calc failed: {e}"
    if d0 != 3:
        return False, f"dim k[x]/I|eps=0 = {d0}, expected 3"
    if d1 != 3:
        return False, f"dim k[x]/I|eps=1 = {d1}, expected 3"
    # Special fiber should look like A = k[x,y]/(x,y)^2: basis 1, x_i (s vars worth), then nothing
    # The basis monomials have total degrees = (1, s, 0, ...). For dim=3 with s>=2 we want degrees (1, 2, 0, ...)
    deg_count_0 = {}
    for e in basis0:
        d = sum(e); deg_count_0[d] = deg_count_0.get(d,0) + 1
    if deg_count_0.get(0,0) != 1 or deg_count_0.get(1,0) != 2 or sum(deg_count_0.values()) != 3:
        # Allow extra dimensions if some xi are killed in the ideal at eps=0
        return False, f"special fiber Hilbert function {deg_count_0}, expected (1,2,0,...)"
    # Generic fiber should be k[t]/(t^3): Hilbert (1,1,1,0,...)
    deg_count_1 = {}
    for e in basis1:
        d = sum(e); deg_count_1[d] = deg_count_1.get(d,0) + 1
    if deg_count_1.get(0,0) != 1 or sum(deg_count_1.get(d,0) for d in (1,2,3)) != 2:
        return False, f"generic fiber Hilbert function {deg_count_1} doesn't fit k[t]/(t^3)"
    # Curvilinearity check: in the generic fiber (eps=1), is dim_k(m/m^2) = 1?
    # m^2 is the ideal generated by all x_i * x_j. Compute reduced normal forms and count linearly indep ones.
    try:
        m_squared_gens = [x_syms[i]*x_syms[j] for i in range(s) for j in range(i, s)]
        # Reduce each x_i x_j mod the generic-fiber GB and find their linear span
        gb1_polys = list(gb1)
        reduced = [sp.reduced(g, gb1_polys, *x_syms)[1] for g in m_squared_gens]
        # m as a vector space: standard monomials of degree >= 1
        # (we already have basis1 from dim_quotient; we know |basis1| = 3, so m has dim 2)
        # Count linearly indep reductions in m^2:
        # Build matrix of (basis-coordinates of each reduction) and rank it
        from sympy import Matrix
        # The standard monomial basis from dim_quotient
        all_basis_monos = []
        from itertools import product
        lt1 = []
        for p in gb1_polys:
            poly = sp.Poly(p, *x_syms)
            if not poly.is_zero: lt1.append(poly.monoms()[0])
        for d in range(8+1):
            for exps in product(range(d+1), repeat=s):
                if sum(exps) != d: continue
                if any(all(exps[i] >= le[i] for i in range(s)) for le in lt1):
                    continue
                all_basis_monos.append(exps)
        # Express each reduction in this basis
        rows = []
        for red in reduced:
            poly = sp.Poly(red, *x_syms)
            row = [0]*len(all_basis_monos)
            for mono, coef in zip(poly.monoms(), poly.coeffs()):
                if mono in all_basis_monos:
                    row[all_basis_monos.index(mono)] = int(coef) if coef.is_Integer else float(coef)
            rows.append(row)
        if rows:
            M = Matrix(rows)
            m_sq_dim = M.rank()
        else:
            m_sq_dim = 0
        m_dim = d1 - 1  # m = quotient \ {1}
        m_mod_m_sq = m_dim - m_sq_dim
        if m_mod_m_sq != 1:
            return False, f"generic fiber dim(m/m^2) = {m_mod_m_sq} (m={m_dim}, m^2={m_sq_dim}), expected 1"
    except Exception as e:
        return False, f"m/m^2 calc failed: {e}"
    return True, f"PASS (special fiber Hilb {deg_count_0}, generic fiber Hilb {deg_count_1}, curvilinear)"


# ---------- Inverse Galois (necessary conditions: irreducible + perfect-square discriminant) ----------
def verify_inverse_galois_necessary(text: str, expected_deg: int) -> tuple[bool, str]:
    """Necessary conditions for poly to have Galois group M_n (n=22 or 23):
       - degree exactly n
       - irreducible over Q
       - discriminant a perfect square (since M_n ⊂ A_n)
       This does NOT prove the Galois group is M_n, only that it's *consistent*.
       A FAIL here means the poly cannot have G = M_n.
    """
    import sympy as sp
    body = extract_after_answer(text)
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    x = sp.Symbol("x")
    poly = None
    for ln in body.split("\n"):
        ln = ln.strip()
        if "x" in ln and re.match(r"^[\sx0-9+\-*^()\.]+$", ln.replace("**","").replace("\\^","^")):
            try:
                poly = sp.sympify(ln.replace("^","**"), locals={"x": x})
                break
            except: continue
    if poly is None:
        return False, "no polynomial found in answer"
    deg = int(sp.Poly(poly, x).total_degree())
    if deg != expected_deg:
        return False, f"deg={deg}, expected {expected_deg}"
    factored = sp.factor(poly)
    if factored != sp.expand(poly):
        return False, f"reducible: {str(factored)[:120]}"
    try:
        disc = int(sp.discriminant(poly, x))
    except Exception as e:
        return False, f"disc compute failed: {e}"
    if disc == 0: return False, "disc=0 (not separable)"
    if not sp.sqrt(abs(disc)).is_integer:
        return False, f"disc not a perfect square (Galois ⊄ A_{expected_deg})"
    return True, f"PASS necessary conditions (irreducible, disc perfect square; sufficiency requires Magma/Sage)"


# ---------- Arithmetic-Kakeya (necessary conditions only) ----------
def verify_arithmetic_kakeya_necessary(text: str, threshold: float) -> tuple[bool, str]:
    """Check NECESSARY conditions on a candidate solution:
       - Line 1: 'fraction num m R n T' with score <= threshold and (m+|R|)/(n-|T|) matching
       - Line 2: list of pairs with (0,0) and a+b!=0 for non-(0,0)
       - Line 3: dimensions whose product equals n
       - Line 4: list of partial dictionaries (presence is required, content not validated)
       - Line 5: T list (size matches |T|)
       - Line 6: R list (size matches |R|)
       Does NOT validate the forcing-pair semantics — that requires implementing
       the X-constructible graph + matrix-row-reduction logic.
    """
    body = extract_after_answer(text).strip()
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    if len(lines) < 6:
        return False, f"only {len(lines)} non-empty lines, need 6"
    # Line 1: fraction + parameters
    line1 = lines[0]
    m_score = re.match(r"\s*(\d+)\s*/\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", line1)
    if not m_score:
        return False, f"line 1 doesn't match 'p/q m |R| n |T|': {line1[:80]}"
    p, q, m_param, R_param, n_param, T_param = (int(g) for g in m_score.groups())
    if q == 0: return False, "denominator 0"
    if p / q > threshold + 1e-9:
        return False, f"score {p}/{q}={p/q:.4f} > threshold {threshold}"
    # check (m+|R|)/(n-|T|) matches p/q
    if (n_param - T_param) <= 0:
        return False, f"n-|T| = {n_param-T_param} <= 0"
    expected_num = m_param + R_param
    expected_den = n_param - T_param
    # cross-multiply
    if p * expected_den != q * expected_num:
        return False, f"(m+|R|)/(n-|T|) = {expected_num}/{expected_den} != {p}/{q}"
    # Line 2: list of pairs
    try:
        X = eval(lines[1], {"__builtins__":{}}, {})
    except Exception as e:
        return False, f"line 2 X parse failed: {e}"
    if not isinstance(X, list) or any(not (isinstance(t, tuple) and len(t)==2 and isinstance(t[0],int) and isinstance(t[1],int)) for t in X):
        return False, "line 2 not list of (int,int) tuples"
    if (0,0) not in X:
        return False, "X must contain (0,0)"
    for (a,b) in X:
        if (a,b) != (0,0) and a + b == 0:
            return False, f"X contains ({a},{b}) with a+b=0"
    # Line 3: dimensions (could be Python list or space-separated ints)
    line3 = lines[2].strip()
    if line3.startswith("["):
        try:
            ds = eval(line3, {"__builtins__":{}}, {})
        except Exception as e:
            return False, f"line 3 ds parse failed: {e}"
    else:
        # space-separated
        try:
            ds = [int(t) for t in re.split(r"[,\s]+", line3) if t]
        except ValueError:
            return False, f"line 3 ds: can't parse: {line3[:80]}"
    if not isinstance(ds, list) or any(not isinstance(d, int) or d < 1 for d in ds):
        return False, "line 3 not list of positive ints"
    n_calc = 1
    for d in ds: n_calc *= d
    if n_calc != n_param:
        return False, f"product of d_i = {n_calc} != n={n_param}"
    # Line 5: T
    try:
        T_list = eval(lines[4], {"__builtins__":{}}, {})
    except Exception as e:
        return False, f"line 5 T parse failed: {e}"
    if not isinstance(T_list, list):
        return False, "line 5 not a list"
    if len(T_list) != T_param:
        return False, f"|T|={len(T_list)} != T_param={T_param}"
    # Line 6: R
    try:
        R_list = eval(lines[5], {"__builtins__":{}}, {})
    except Exception as e:
        return False, f"line 6 R parse failed: {e}"
    if not isinstance(R_list, list):
        return False, "line 6 not a list"
    if len(R_list) != R_param:
        return False, f"|R|={len(R_list)} != R_param={R_param}"
    return True, f"PASS necessary conditions: score={p}/{q}, {n_param} verts, {m_param} edges, |T|={T_param}, |R|={R_param} (forcing semantics NOT verified)"


VERIFIERS = {
    ("hadamard", "warmup"):       lambda t: verify_hadamard(t, 428),
    ("hadamard", "full_problem"): lambda t: verify_hadamard(t, 668),
    ("inverse-galois", "warmup"):       lambda t: verify_inverse_galois_necessary(t, 22),
    ("inverse-galois", "full_problem"): lambda t: verify_inverse_galois_necessary(t, 23),
    # Use the FULL forcing-semantics verifier instead of necessary-conditions
    ("arithmetic-kakeya", "warmup"):       lambda t: _kv.verify_kakeya(t, 1.75),
    ("arithmetic-kakeya", "full_problem"): lambda t: _kv.verify_kakeya(t, 1.675),
    ("large-steiner-systems", "warmup"):       lambda t: verify_steiner(t, "warmup"),
    ("large-steiner-systems", "full_problem"): lambda t: verify_steiner(t, "full"),
    ("ramsey-book-graphs", "warmup"):          verify_ramsey_book_warmup,
    ("small-diophantine", "warmup"):           verify_small_diophantine,
    ("degree-sensitivity-boolean", "warmup"):       lambda t: verify_degree_sensitivity(t, 1.63),
    ("degree-sensitivity-boolean", "full_problem"): lambda t: verify_degree_sensitivity(t, 1.6309),
    ("explicit-deformations", "warmup"):            verify_explicit_deformations_warmup,
    ("stretched-lr-coefficients", "full_problem"):  _lr.verify_stretched_lr,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log_or_json")
    ap.add_argument("--pid", help="Filter by problem_id")
    ap.add_argument("--label-min", default="partial",
                    choices=["correct","almost","partial","incorrect"])
    args = ap.parse_args()

    # Load Phase 1 log/json
    p = Path(args.log_or_json)
    items = []
    if p.suffix == ".jsonl":
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                # Accept any record with problem_id and a candidate text field
                if r.get("problem_id") and (r.get("gen_text") or r.get("best_candidate") or r.get("final_solution")):
                    items.append(r)
    else:
        with open(p) as f:
            d = json.load(f)
        items = d.get("results", d.get("all_results", []))

    rank = {"incorrect":0, "partial":1, "almost":2, "correct":3}
    # Use 'label' or 'best_label' (seed_full uses best_label)
    def trial_label(r): return r.get("label") or r.get("best_label")
    items = [r for r in items if trial_label(r) and rank.get(trial_label(r), -1) >= rank[args.label_min]]
    if args.pid: items = [r for r in items if r["problem_id"] == args.pid]
    print(f"Items to verify: {len(items)}")

    results = []
    for r in items:
        key = (r["problem_id"], r["prompt_type"])
        verifier = VERIFIERS.get(key)
        if not verifier:
            continue  # no checker available for this problem/type
        text = r.get("gen_text") or r.get("best_candidate") or r.get("final_solution") or ""
        try:
            ok, msg = verifier(text)
        except Exception as e:
            ok, msg = False, f"verifier crash: {type(e).__name__}: {e}"
        lab = trial_label(r)
        model = (r.get("model") or r.get("condition") or "?").split("/")[-1]
        results.append({"problem_id": r["problem_id"], "prompt_type": r["prompt_type"],
                        "model": model, "seed": r["seed"], "label": lab,
                        "verified": ok, "msg": msg})
        flag = "✓ VERIFIED" if ok else "✗"
        print(f"  {flag}  {r['problem_id']:<26} {r['prompt_type']:<14} {model:<22} seed={r['seed']}  judge={lab}  | {msg}")

    print(f"\nTotal verified: {sum(1 for r in results if r.get('verified'))} / {len(results)} eligible (others have no local verifier)")


if __name__ == "__main__":
    main()
