"""
Full arithmetic-kakeya forcing-pair verifier.

Implements the operations from the "Verifiable Set-up" of the prompt:
  Op 1: edges add matrix differences to R
  Op 2: if some f in R has f(e)=(a,-a), a≠0, and f(g)=(0,0) for g not in T∪{e},
        add e to T
  Op 3: any Z-linear combination of R is added to R

The forcing pair is valid if iterating these operations terminates with T = full vertex set.

We treat R as a vector subspace of Q^(2n) (each function is a 2-tuple at each vertex,
flattened). Op 3 gives a linear span. Op 1 lets us add fixed elements to the span
generators. Op 2 picks vertices to add to T.

Vertices are ordered tuples (e_1, ..., e_k) with 1 <= e_i <= d_i.
"""
from __future__ import annotations
import json, re
from itertools import product
from fractions import Fraction


def parse_solution(text: str):
    """Parse a kakeya answer into structured form. Returns dict or raises."""
    body = text
    m = re.search(r"##\s*Answer\s*\n", body, re.I)
    if m: body = body[m.end():]
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    if len(lines) < 6:
        raise ValueError(f"only {len(lines)} non-empty lines, need 6")
    # Line 1: score m |R| n |T|
    # Accept either "p/q m |R| n |T|" or "p/q, m, |R|, n, |T|" or even "<float> m |R| n |T|"
    line1 = lines[0].replace(",", " ")
    # Try "p/q m R n T"
    m1 = re.match(r"\s*(\d+)\s*/\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", line1)
    if m1:
        p_, q_, m_, R_, n_, T_ = (int(g) for g in m1.groups())
    else:
        # Try "<float> m R n T" (decimal score)
        m1 = re.match(r"\s*(\d+(?:\.\d+)?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", line1)
        if m1:
            score_str = m1.group(1)
            m_, R_, n_, T_ = (int(g) for g in m1.groups()[1:5])
            from fractions import Fraction
            f = Fraction(score_str).limit_denominator(10000)
            p_, q_ = f.numerator, f.denominator
        else:
            raise ValueError(f"bad line 1: {lines[0][:80]}")
    # Line 2: X
    X = eval(lines[1], {"__builtins__":{}}, {})
    if not isinstance(X, list): raise ValueError("line 2 not a list")
    X = [tuple(x) for x in X]
    # Line 3: dimensions
    line3 = lines[2].strip()
    if line3.startswith("["):
        ds = eval(line3, {"__builtins__":{}}, {})
    else:
        ds = [int(t) for t in re.split(r"[,\s]+", line3) if t]
    if not ds or any(d < 1 for d in ds):
        raise ValueError(f"bad dimensions: {ds}")
    # Line 4: f_i functions (a list of dicts)
    line4 = lines[3].strip()
    # Try to be permissive: it might be a Python list of dicts
    fs = eval(line4, {"__builtins__":{}}, {})
    if not isinstance(fs, list): raise ValueError("line 4 not a list")
    if len(fs) != len(ds): raise ValueError(f"line 4 has {len(fs)} functions, expected {len(ds)}")
    fs = [dict(f) if isinstance(f, dict) else dict() for f in fs]
    # Normalize keys: f_i: domain is d_1×...×d_{i-1}×(d_i-1).
    # Keys may be: a single int (for i=1, since 1-tuple), or a tuple
    def norm_key(k, i):
        if isinstance(k, int): return (k,)
        if isinstance(k, tuple): return tuple(int(x) for x in k)
        raise ValueError(f"bad key in f_{i}: {k}")
    fs = [
        {norm_key(k, i): tuple(int(x) for x in v)
         for k, v in fdict.items()}
        for i, fdict in enumerate(fs, 1)
    ]
    # Line 5: T
    T_list_raw = eval(lines[4], {"__builtins__":{}}, {})
    if not isinstance(T_list_raw, list): raise ValueError("line 5 not list")
    T_list = [tuple(int(x) for x in t) for t in T_list_raw] if T_list_raw else []
    # Line 6: R (list of dicts mapping vertex tuple → element of X)
    R_list_raw = eval(lines[5], {"__builtins__":{}}, {})
    if not isinstance(R_list_raw, list): raise ValueError("line 6 not list")
    R_list = []
    for rdict in R_list_raw:
        if not isinstance(rdict, dict): raise ValueError("R entry not dict")
        if len(rdict) != 1: raise ValueError(f"R entry should have exactly 1 nonzero entry, got {rdict}")
        ((v, x),) = rdict.items()
        v_t = tuple(int(c) for c in v) if isinstance(v, tuple) else (int(v),)
        x_t = tuple(int(c) for c in x)
        R_list.append({v_t: x_t})
    return {
        "p": p_, "q": q_, "m": m_, "R_size": R_, "n": n_, "T_size": T_,
        "X": X, "ds": ds, "fs": fs, "T": T_list, "R": R_list,
    }


def vertex_list(ds):
    """All vertices: tuples (e_1,...,e_k) with 1 <= e_i <= d_i."""
    return [tuple(e) for e in product(*[range(1, d+1) for d in ds])]


def edges_from_construction(ds, fs):
    """Yield (v1, v2, label) for each edge implied by the f_i functions.
    For f_i(a_1,...,a_i) = x ≠ (0,0), connect (a_1,...,a_i, e_{i+1}, ..., e_k)
    and (a_1,...,a_{i-1}, a_i+1, e_{i+1}, ..., e_k) for each (e_{i+1},...,e_k).
    """
    k = len(ds)
    for i in range(1, k+1):
        f_i = fs[i-1]
        d_after = ds[i:]   # d_{i+1}..d_k
        for prefix, x in f_i.items():
            # prefix is (a_1,...,a_i) but stored with a_i in [1, d_i-1]
            if x == (0, 0): continue
            assert len(prefix) == i, f"f_{i} key has wrong length: {prefix}"
            ai = prefix[-1]
            if not (1 <= ai <= ds[i-1] - 1):
                # invalid key; skip silently? For now raise.
                continue
            # Iterate over all suffixes (e_{i+1},...,e_k)
            for suffix in product(*[range(1, d+1) for d in d_after]):
                v1 = tuple(prefix) + suffix
                v2 = tuple(prefix[:-1]) + (ai+1,) + suffix
                yield v1, v2, x


def function_to_vec(f_dict, vertex_index):
    """Convert {vertex: (a,b)} to a 2n-dim vector indexed by (vertex_idx, 0/1)."""
    n = len(vertex_index)
    vec = [Fraction(0)] * (2 * n)
    for v, (a, b) in f_dict.items():
        i = vertex_index[v]
        vec[2*i] = Fraction(a)
        vec[2*i+1] = Fraction(b)
    return vec


def vec_to_function(vec, vertex_index, vertex_list):
    """Inverse: produce a {vertex: (a,b)} dict from the 2n-vector. Skip zero entries."""
    f = {}
    for v in vertex_list:
        i = vertex_index[v]
        a = vec[2*i]; b = vec[2*i+1]
        if a != 0 or b != 0:
            f[v] = (a, b)
    return f


def rref_with_pivots(matrix):
    """In-place rational row reduction. Returns (row_count_nonzero, pivot_cols)."""
    if not matrix: return 0, []
    M = [row[:] for row in matrix]
    rows = len(M); cols = len(M[0]) if M else 0
    r = 0
    pivots = []
    for c in range(cols):
        # Find pivot row
        piv_r = None
        for rr in range(r, rows):
            if M[rr][c] != 0:
                piv_r = rr; break
        if piv_r is None: continue
        M[r], M[piv_r] = M[piv_r], M[r]
        pv = M[r][c]
        M[r] = [v / pv for v in M[r]]
        for rr in range(rows):
            if rr != r and M[rr][c] != 0:
                factor = M[rr][c]
                M[rr] = [a - factor * b for a, b in zip(M[rr], M[r])]
        pivots.append(c)
        r += 1
        if r == rows: break
    # Replace M in-place
    for i in range(rows):
        matrix[i] = M[i]
    return r, pivots


def verify_kakeya_full(parsed, threshold=1.75):
    """Verify the full kakeya semantics. Returns (ok: bool, msg: str)."""
    p, q = parsed["p"], parsed["q"]
    m = parsed["m"]; Rsz = parsed["R_size"]; n = parsed["n"]; Tsz = parsed["T_size"]
    X = parsed["X"]; ds = parsed["ds"]; fs = parsed["fs"]; T_init = parsed["T"]; R_init = parsed["R"]
    # 1. score check
    if q == 0: return False, "denominator 0"
    if p / q > threshold + 1e-9:
        return False, f"score {p}/{q}={p/q:.4f} > threshold {threshold}"
    if (n - Tsz) <= 0: return False, "n - |T| <= 0"
    if p * (n - Tsz) != q * (m + Rsz):
        return False, f"(m+|R|)/(n-|T|) = {m+Rsz}/{n-Tsz} != {p}/{q}"
    # 2. X format
    if (0, 0) not in X: return False, "X must contain (0,0)"
    for (a, b) in X:
        if (a, b) != (0, 0) and (a + b) == 0:
            return False, f"X has ({a},{b}) with a+b=0"
    # 3. n product
    n_calc = 1
    for d in ds: n_calc *= d
    if n_calc != n: return False, f"prod(d_i)={n_calc} != n={n}"
    # 4. m count
    edge_list = list(edges_from_construction(ds, fs))
    if len(edge_list) != m:
        return False, f"|edges| = {len(edge_list)} != m = {m}"
    # 5. T size + |T| match
    if len(T_init) != Tsz: return False, f"|T|={len(T_init)} != T_size={Tsz}"
    # 6. R size match
    if len(R_init) != Rsz: return False, f"|R|={len(R_init)} != R_size={Rsz}"
    # 7. R format: each entry assigns x∈X at exactly one vertex
    X_set = set(X)
    for ridx, rdict in enumerate(R_init):
        if len(rdict) != 1: return False, f"R[{ridx}] not single-entry"
        ((v, x),) = rdict.items()
        if x not in X_set: return False, f"R[{ridx}]: label {x} not in X"
    # 8. simulate forcing
    vertices = vertex_list(ds)
    vidx = {v: i for i, v in enumerate(vertices)}
    # Initial R: list of vectors
    R_vectors = []
    # 8a: R_init contributions
    for rdict in R_init:
        R_vectors.append(function_to_vec(rdict, vidx))
    # 8b: edge ops (op 1 — adds fixed elements to R)
    # f_i((a_1,...,a_i))=x, edge between e_1=(a_1,...,a_i, e_{i+1},...) and e_2=(a_1,...,a_{i-1}, a_i+1, e_{i+1},...)
    # adds {e_1: x, e_2: -x} to R.
    for v1, v2, x in edge_list:
        f = {v1: x, v2: tuple(-c for c in x)}
        R_vectors.append(function_to_vec(f, vidx))
    # T = T_init copy
    T = set(T_init)
    # Iterate op 2 until no progress
    progress = True
    forced_in = []
    iterations = 0
    max_iterations = 4 * len(vertices) + 10
    while progress and iterations < max_iterations:
        progress = False
        iterations += 1
        # Reduce R_vectors to RREF
        if R_vectors:
            mat = [v[:] for v in R_vectors]
            rref_with_pivots(mat)
            # Keep only nonzero rows
            R_vectors = [r for r in mat if any(c != 0 for c in r)]
        # Check op 2: for each vertex e not in T, is there f in span(R_vectors) with
        # f(e) = (a, -a) for some a≠0 and f(g) = (0,0) for g not in T∪{e}?
        # Equivalently: does the linear system have a solution?
        # Variables: coefficients alpha_j for each row of R_vectors basis.
        # Constraints:
        #   For each g not in T∪{e}: f(g) = sum_j alpha_j * R_vectors[j][2g], 2g+1] = 0  (2 equations)
        #   For e: f(e) = (a, -a), i.e., f(e)[0] + f(e)[1] = 0  (1 equation)
        #   And f(e)[0] != 0 (or some nonzero to ensure a != 0)
        # Just: solve the linear constraints, then check if the solution space has
        #       a vector with f(e)[0] != 0 (then a≠0 and -a is the second comp).
        if not R_vectors: break
        # Build basis as rows. Variable count = num basis vectors.
        for e in vertices:
            if e in T: continue
            # Constraints matrix A * alpha = 0 except f(e)[0]+f(e)[1] = 0.
            # Equivalently, all-zero except for the single constraint at e.
            constraints = []
            for g in vertices:
                if g in T or g == e: continue
                gi = vidx[g]
                # f(g)[0] = 0
                constraints.append([R[2*gi] for R in R_vectors])
                # f(g)[1] = 0
                constraints.append([R[2*gi + 1] for R in R_vectors])
            ei = vidx[e]
            # f(e)[0] + f(e)[1] = 0
            constraints.append([R[2*ei] + R[2*ei + 1] for R in R_vectors])
            # Solve: nullspace of constraints. Check if any vector in nullspace
            # has nonzero f(e)[0].
            # Compute RREF of constraints^T... actually let's compute nullspace.
            # constraints is (num_constraints, num_vars). We want alpha s.t. C @ alpha = 0
            # AND f(e)[0] = sum_j alpha_j * R_vectors[j][2*ei] != 0.
            # Equivalent: f(e)[0] is NOT in the row span of C (treated as a linear function).
            # Add f(e)[0] expression as an additional row and compute rank.
            row_fe0 = [R[2*ei] for R in R_vectors]
            # If row_fe0 is in row-span of constraints, then any alpha satisfying
            # constraints also has f(e)[0]=0 → can't force.
            # Test: rank(C ∪ {row_fe0}) > rank(C) ⟹ row_fe0 NOT in row-span ⟹ can force.
            # (Because row_fe0 must be linearly INDEPENDENT of constraints to allow nonzero f(e)[0])
            # Wait, this is backwards. Let me re-think.
            # We want: exists alpha with C @ alpha = 0 and row_fe0 . alpha != 0.
            # ⟺ row_fe0 is NOT in the row-span of C.
            # rank-nullity: rank(C) + dim(nullspace(C)) = num_vars.
            # row_fe0 . nullspace(C) is nonzero iff row_fe0 ∉ rowspan(C).
            # So check rank(C) vs rank(C ∪ {row_fe0}).
            rk_C = _rank(constraints)
            rk_C_plus = _rank(constraints + [row_fe0])
            if rk_C_plus > rk_C:
                # Can force e
                T.add(e)
                forced_in.append(e)
                progress = True
                # Don't break — keep adding all forceable in this round
    # 9. Check T == all vertices
    if set(vertices) != T:
        missing = sorted(set(vertices) - T)
        return False, f"forcing pair fails: {len(missing)}/{len(vertices)} vertices not forced (e.g., {missing[:5]})"
    return True, f"PASS forcing semantics: {len(vertices)} verts, {len(edge_list)} edges, {len(R_init)} initial R, score={p}/{q}, forced T_init={len(T_init)} → all"


def _rank(matrix):
    if not matrix: return 0
    M = [row[:] for row in matrix]
    rows = len(M); cols = len(M[0]) if M else 0
    r = 0
    for c in range(cols):
        piv = None
        for rr in range(r, rows):
            if M[rr][c] != 0: piv = rr; break
        if piv is None: continue
        M[r], M[piv] = M[piv], M[r]
        pv = M[r][c]
        M[r] = [v / pv for v in M[r]]
        for rr in range(rows):
            if rr != r and M[rr][c] != 0:
                factor = M[rr][c]
                M[rr] = [a - factor * b for a, b in zip(M[rr], M[r])]
        r += 1
        if r == rows: break
    return r


def verify_kakeya(text: str, threshold: float = 1.75):
    try:
        parsed = parse_solution(text)
    except Exception as e:
        return False, f"parse failed: {type(e).__name__}: {e}"
    try:
        return verify_kakeya_full(parsed, threshold)
    except Exception as e:
        return False, f"semantic check crashed: {type(e).__name__}: {e}"
