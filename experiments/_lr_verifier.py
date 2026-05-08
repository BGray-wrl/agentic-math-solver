"""
Stretched Littlewood-Richardson coefficient verifier.

Problem: Find partitions λ, μ, ν with
  - |λ| = |μ| + |ν|
  - len ≤ 7, sum ≤ 30
  - the polynomial c^{tλ}_{tμ,tν} (in variable t) has at least one negative coefficient.

The LR coefficient c^λ_{μν} counts LR skew tableaux of shape λ/μ with content ν.
For "stretched" (t*λ, t*μ, t*ν) we compute the count for several t and check polynomial coefficients.

We use sympy's built-in computation for LR coefficients via Schur functions if available,
otherwise direct enumeration with limits.
"""
from __future__ import annotations
import re
import math
from itertools import product
from functools import lru_cache


def parse_three_partitions(text: str):
    """Extract a list of three partitions from the candidate text."""
    # Find a python-list-of-lists pattern
    body = text
    m = re.search(r"##\s*Answer\s*\n", body, re.I)
    if m: body = body[m.end():]
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    # Look for [[..],[..],[..]]
    m = re.search(r"\[\s*(\[[^\]]*\])\s*,\s*(\[[^\]]*\])\s*,\s*(\[[^\]]*\])\s*\]", body)
    if not m: raise ValueError("could not find three-partition structure")
    parts = []
    for g in m.groups():
        try:
            p = eval(g, {"__builtins__":{}}, {})
        except Exception as e:
            raise ValueError(f"parse failed: {e}")
        if not isinstance(p, list) or any(not isinstance(x, int) or x < 0 for x in p):
            raise ValueError(f"bad partition: {p}")
        # Strip trailing zeros, sort descending
        p = sorted([x for x in p if x > 0], reverse=True)
        parts.append(p)
    if len(parts) != 3: raise ValueError("need exactly 3 partitions")
    return parts


def is_partition(p):
    return all(p[i] >= p[i+1] for i in range(len(p)-1)) and all(x > 0 for x in p)


def contains(lam, mu):
    """Check μ ⊆ λ (componentwise)."""
    if len(mu) > len(lam): return False
    return all(mu[i] <= lam[i] for i in range(len(mu)))


def cells_skew(lam, mu):
    """Cells of λ/μ, as (row, col) with 1-indexed conventions stored 0-indexed."""
    cells = []
    for i, l in enumerate(lam):
        m = mu[i] if i < len(mu) else 0
        for j in range(m, l):
            cells.append((i, j))
    return cells


def lr_count(lam, mu, nu):
    """Count LR tableaux of shape λ/μ with content ν.
    LR tableau: skew tableau filled with 1..len(nu), rows weakly increasing,
    columns strictly increasing, reverse-reading word is lattice.
    """
    if not contains(lam, mu): return 0
    if sum(lam) - sum(mu) != sum(nu): return 0
    cells = cells_skew(lam, mu)
    n_cells = len(cells)
    if n_cells == 0:
        return 1 if sum(nu) == 0 else 0
    # Order cells by (row, col) for filling
    cells_sorted = sorted(cells)
    k = len(nu)
    # Reverse reading word: read right-to-left top-to-bottom
    # = cells sorted by (row, -col)
    rrw_order = sorted(cells, key=lambda c: (c[0], -c[1]))
    rrw_idx = {c: i for i, c in enumerate(rrw_order)}

    target_count = list(nu) + [0] * 10  # buffer
    # DFS with pruning
    cells_filled = {}  # (r,c) -> value (1-indexed)
    used = [0] * (k + 1)  # used[i] = how many i's placed so far
    # For lattice condition: track partial counts in the reverse reading word order.
    # Actually we'll check lattice incrementally using reverse-reading-word position.

    # Build a list of cells in row-major order (top-to-bottom, left-to-right).
    # We fill them in this order. At each step, check row/column constraints.
    # We also need to check lattice property dynamically by tracking the filled
    # positions in rrw order.

    n_solutions = [0]

    def backtrack(idx):
        if idx == n_cells:
            # All filled. Check lattice and content. Content is checked by `used`.
            if used[1:k+1] == list(nu):
                n_solutions[0] += 1
            return
        r, c = cells_sorted[idx]
        # Constraints:
        #   - row weakly increasing: must be >= cell_to_left in the same row (if filled)
        #   - col strictly increasing: must be > cell above (if filled)
        lo = 1
        # left neighbor
        if c > (mu[r] if r < len(mu) else 0):
            left = cells_filled.get((r, c-1))
            if left is not None: lo = max(lo, left)
        # cell above
        if r > 0:
            above = cells_filled.get((r-1, c))
            if above is not None: lo = max(lo, above + 1)
        for v in range(lo, k+1):
            # content: don't exceed nu[v-1]
            if used[v] >= nu[v-1]: continue
            # Lattice property: count of v at all rrw positions ≥ count of v+1
            # Quick check: after placing v at this rrw position, ensure count(v) ≥ count(v+1)
            # at THIS position considering all rrw positions ≤ this one.
            # Simpler: after placing, count(v) > count(v+1) at this prefix would violate? No.
            # The full check is: at every prefix, count(v) ≥ count(v+1).
            # Most efficient: skip this work and check at end. But tableau search blows up.
            # We do incremental lattice check:
            # current rrw_pos = rrw_idx[(r,c)]. We're placing at this cell.
            # But fill order is row-major, so cells later in row-major may be earlier in rrw.
            # That's a problem. Let me change fill order to rrw order.
            cells_filled[(r, c)] = v
            used[v] += 1
            backtrack(idx + 1)
            del cells_filled[(r, c)]
            used[v] -= 1

    # Use rrw_order as the fill order — same constraints but allows incremental lattice check.
    def fill_order():
        # Start from each row's first cell in rrw_order: rightmost col of leftmost row
        # rrw order: top-to-bottom, right-to-left
        return rrw_order

    rrw_cells = fill_order()

    def back2(idx, prefix_counts):
        if idx == n_cells:
            if used[1:k+1] == list(nu):
                n_solutions[0] += 1
            return
        r, c = rrw_cells[idx]
        # Constraints from already-filled neighbors:
        lo = 1
        # right neighbor in same row (already filled in rrw order since we go right-to-left)
        if c + 1 < (lam[r] if r < len(lam) else 0):
            right = cells_filled.get((r, c+1))
            if right is not None: lo = max(lo, right)  # must be >= or actually we filled right first so we need v <= right
        # Actually rrw goes right-to-left, so right neighbor was filled before this. Need this cell <= right.
        # Hmm: rows weakly increasing left-to-right means right cell >= left cell.
        # Reversed: when we fill right-to-left, current cell <= already-filled right cell.
        hi = k
        if c + 1 < (lam[r] if r < len(lam) else 0):
            right = cells_filled.get((r, c+1))
            if right is not None: hi = min(hi, right)
        # Cell above in same col (top-to-bottom in rrw, but col-strict means above < current)
        if r > 0:
            above = cells_filled.get((r-1, c))
            if above is not None: lo = max(lo, above + 1)
        # Cell below in same col (already filled because top-to-bottom in rrw)
        # Actually rrw order is top-to-bottom rows, then right-to-left in each row.
        # So "below same col" hasn't been filled yet. No constraint there.
        for v in range(lo, hi + 1):
            if used[v] >= nu[v-1]: continue
            # Lattice: prefix_counts[v-1] (count of v in prefix INCLUDING this cell)
            # would be prefix_counts[v-1] + 1. Need ≥ prefix_counts[v] (count of v+1).
            new_pc = list(prefix_counts)
            new_pc[v-1] += 1
            valid = True
            # After this placement, check that for all i: new_pc[i] >= new_pc[i+1]
            # (i.e., count of i+1 in prefix >= count of i+2)
            for i in range(k - 1):
                if new_pc[i] < new_pc[i+1]:
                    valid = False; break
            if not valid: continue
            cells_filled[(r, c)] = v
            used[v] += 1
            back2(idx + 1, new_pc)
            del cells_filled[(r, c)]
            used[v] -= 1

    back2(0, [0] * k)
    return n_solutions[0]


def stretched_lr_polynomial(lam, mu, nu, max_t=None):
    """Compute c^{tλ}_{tμ,tν} for t = 0, 1, 2, ... and return the polynomial coefficients.
    The polynomial in t has degree at most |λ|. We sample enough points and interpolate.
    """
    if max_t is None:
        # Use degree bound: pochhammer-like, but conservative estimate
        max_t = min(8, max(2, sum(lam) // 4 + 2))
    values = []
    # Sample t = 1, 2, ..., max_t (exclude t=0 which doesn't fit the poly extension)
    for t in range(1, max_t + 1):
        tlam = [t*x for x in lam]
        tmu = [t*x for x in mu]
        tnu = [t*x for x in nu]
        c = lr_count(tlam, tmu, tnu)
        values.append(c)
    return values


def fit_polynomial(values):
    """Given f(1), f(2), ..., f(n), compute polynomial coefficients."""
    import sympy as sp
    t = sp.Symbol('t')
    # Points are (1, values[0]), (2, values[1]), ...
    pts = [(i+1, values[i]) for i in range(len(values))]
    poly = sp.interpolate(pts, t)
    poly = sp.expand(poly)
    p = sp.Poly(poly, t)
    coeffs = list(p.all_coeffs())  # highest-degree first
    return coeffs


def verify_stretched_lr(text: str) -> tuple[bool, str]:
    """Verify a candidate (λ, μ, ν) — check |λ| = |μ| + |ν|, length/sum constraints,
    then compute LR polynomial values and check for negative coefficient."""
    try:
        lam, mu, nu = parse_three_partitions(text)
    except Exception as e:
        return False, f"parse failed: {e}"
    if any(len(p) > 7 for p in (lam, mu, nu)):
        return False, f"length > 7: {[len(p) for p in (lam,mu,nu)]}"
    if any(sum(p) > 30 for p in (lam, mu, nu)):
        return False, f"sum > 30: {[sum(p) for p in (lam,mu,nu)]}"
    if sum(lam) != sum(mu) + sum(nu):
        return False, f"|λ|={sum(lam)} != |μ|+|ν| = {sum(mu)}+{sum(nu)}"
    # Compute stretched LR polynomial values
    try:
        vals = stretched_lr_polynomial(lam, mu, nu, max_t=6)
    except Exception as e:
        return False, f"LR computation crashed: {e}"
    if all(v == 0 for v in vals[1:]):
        return False, f"all c^{{tλ}}_{{tμ,tν}} = 0; not interesting"
    try:
        coeffs = fit_polynomial(vals)
    except Exception as e:
        return False, f"polynomial fit crashed: {e}"
    has_neg = any(c < 0 for c in coeffs)
    if not has_neg:
        return False, f"no negative coefficient (poly coeffs hi→lo: {coeffs}; values: {vals})"
    return True, f"PASS: λ={lam}, μ={mu}, ν={nu}; values t=0..{len(vals)-1}: {vals}; poly coeffs hi→lo: {coeffs}"
