#!/usr/bin/env python3
"""
Search hypersurfaces

    X = { f(x0,x1) + x2*x3 = 0 } in P(a,b,c,d)

over characteristic 3, allowing weights divisible by 3.

This is a deliberately narrow but useful blind-spot family:
  - it includes the P(2,4,5,25) near-miss;
  - it can have many ambient-stratum singular points;
  - basket/rho arithmetic is explicit enough to filter candidates.

The script reports rows with >=8 singular points, K_X^2>0, and rho=1 under
the standard rational-resolution cyclic-quotient basket calculation.
Rows involving indices divisible by 3 are flagged as WILD: the basket formula
is only a target signal there, not a proof of klt.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import gcd


def inv_mod(a: int, r: int) -> int:
    a %= r
    for x in range(1, r):
        if (a * x) % r == 1:
            return x
    raise ValueError((a, r))


def hj_chain(r: int, q: int) -> list[int]:
    """HJ chain for 1/r(1,q), using r/q = [b1,...,bk], b_i>=2."""
    q %= r
    if q == 0:
        raise ValueError("q=0")
    out = []
    n, d = r, q
    while d != 1:
        b = (n + d - 1) // d
        out.append(b)
        n, d = d, b * d - n
    out.append(n)
    return out


def correction(r: int, q: int) -> Fraction:
    """
    K^2 correction K_X^2 - K_Y^2 for the cyclic quotient 1/r(1,q).
    Solves the discrepancy linear system on the HJ chain.
    """
    bs = hj_chain(r, q)
    n = len(bs)
    # M a = rhs, where M has -b_i on diagonal and 1 adjacent.
    M = [[Fraction(0) for _ in range(n)] for _ in range(n)]
    rhs = [Fraction(bs[i] - 2, 1) for i in range(n)]
    for i, b in enumerate(bs):
        M[i][i] = Fraction(-b, 1)
        if i:
            M[i][i - 1] = Fraction(1, 1)
        if i + 1 < n:
            M[i][i + 1] = Fraction(1, 1)
    # Gaussian elimination
    A = [row[:] + [rhs[i]] for i, row in enumerate(M)]
    for col in range(n):
        piv = next(i for i in range(col, n) if A[i][col] != 0)
        A[col], A[piv] = A[piv], A[col]
        pv = A[col][col]
        A[col] = [x / pv for x in A[col]]
        for i in range(n):
            if i == col:
                continue
            fac = A[i][col]
            if fac:
                A[i] = [A[i][j] - fac * A[col][j] for j in range(n + 1)]
    a = [A[i][-1] for i in range(n)]
    # Correction is - a^T M a, because K_Y = pi^*K_X + sum a_i E_i
    val = Fraction(0)
    for i in range(n):
        for j in range(n):
            val += a[i] * M[i][j] * a[j]
    return -val


def normalized_type(r: int, u: int, v: int) -> tuple[int, int] | None:
    """Return 1/r(1,q) for weights (u,v), or None if smooth/pseudoreflection."""
    u %= r
    v %= r
    if u == 0 and v == 0:
        return None
    if gcd(u, r) == 1:
        q = (v * inv_mod(u, r)) % r
        return None if q == 0 or gcd(q, r) != 1 else (r, q)
    if gcd(v, r) == 1:
        q = (u * inv_mod(v, r)) % r
        return None if q == 0 or gcd(q, r) != 1 else (r, q)
    # Non-isolated or non-cyclic in this naive model; skip.
    return None


@dataclass(frozen=True)
class Sing:
    r: int
    q: int
    label: str

    @property
    def wild(self) -> bool:
        return self.r % 3 == 0

    @property
    def chain(self) -> tuple[int, ...]:
        return tuple(hj_chain(self.r, self.q))

    @property
    def corr(self) -> Fraction:
        return correction(self.r, self.q)

    @property
    def length(self) -> int:
        return len(self.chain)


def binary_root_details(a: int, b: int, D: int):
    """
    Max number of distinct coarse roots for a squarefree weighted binary
    polynomial of degree D.  Computed from the exponent lattice interval.
    """
    sols = [(i, (D - a * i) // b) for i in range(D // a + 1) if (D - a * i) >= 0 and (D - a * i) % b == 0]
    if not sols:
        return None
    min_i = min(i for i, j in sols)
    min_j = min(j for i, j in sols)
    # Endpoint roots of multiplicity >1 make the simple quasi-smooth model fail.
    if min_i > 1 or min_j > 1:
        return None
    return {
        "finite": len(sols) - 1,
        "P1": min_i == 1,  # x0=0 endpoint, stabilizer b
        "P0": min_j == 1,  # x1=0 endpoint, stabilizer a
    }


def candidate(a: int, b: int, c: int, d: int):
    D = c + d
    if D >= a + b + c + d:
        return None
    rootinfo = binary_root_details(a, b, D)
    if not rootinfo:
        return None
    sings: list[Sing] = []
    g01 = gcd(a, b)
    if g01 > 1 and rootinfo["finite"]:
        typ = normalized_type(g01, c, d)
        if typ:
            r, q = typ
            for _ in range(rootinfo["finite"]):
                sings.append(Sing(r, q, "L01-finite-root"))
    if rootinfo["P0"]:
        typ = normalized_type(a, c, d)
        if typ:
            sings.append(Sing(*typ, label="P0-endpoint"))
    if rootinfo["P1"]:
        typ = normalized_type(b, c, d)
        if typ:
            sings.append(Sing(*typ, label="P1-endpoint"))
    # x2*x3=0 on L23 gives P2 and P3 if gcd(c,d)>1; endpoints may have larger
    # stabilizers c,d.
    if gcd(c, d) > 1:
        typ2 = normalized_type(c, a, b)
        typ3 = normalized_type(d, a, b)
        if typ2:
            sings.append(Sing(*typ2, label="P2"))
        if typ3:
            sings.append(Sing(*typ3, label="P3"))
    if len(sings) < 8:
        return None
    KX2 = Fraction((a + b + c + d - D) ** 2 * D, a * b * c * d)
    if KX2 <= 0:
        return None
    KY2 = KX2 - sum(s.corr for s in sings)
    R = sum(s.length for s in sings)
    rho = Fraction(10, 1) - KY2 - R
    return {
        "weights": (a, b, c, d),
        "degree": D,
        "rootinfo": rootinfo,
        "sing_count": len(sings),
        "wild": any(s.wild for s in sings) or any(w % 3 == 0 for w in (a, b, c, d)),
        "KX2": KX2,
        "KY2": KY2,
        "R": R,
        "rho": rho,
        "basket": [s.chain for s in sings],
        "types": [(s.r, s.q, s.label) for s in sings],
    }


def main():
    hits = []
    near = []
    maxw = 80
    for a in range(1, maxw + 1):
        for b in range(a, maxw + 1):
            for c in range(1, maxw + 1):
                for d in range(c, maxw + 1):
                    # Well-formed weighted P3: gcd of any 3 weights is 1.
                    ws = (a, b, c, d)
                    if any(gcd(gcd(ws[i], ws[j]), ws[k]) != 1 for i in range(4) for j in range(i + 1, 4) for k in range(j + 1, 4)):
                        continue
                    row = candidate(a, b, c, d)
                    if not row:
                        continue
                    if row["rho"] == 1:
                        hits.append(row)
                    elif abs(row["rho"] - 1) <= 2:
                        near.append(row)
    print("rho=1 hits:", len(hits))
    for row in hits[:50]:
        print(row)
    print()
    print("near rho rows:", len(near))
    for row in sorted(near, key=lambda r: (abs(r["rho"] - 1), r["sing_count"]))[:20]:
        print(row)


if __name__ == "__main__":
    main()
