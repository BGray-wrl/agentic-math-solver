#!/usr/bin/env python3
"""
Search a simple finite-grid Method C variant on P1xP1 over F3.

Blow up the 16 F3-grid points. Candidate contracted curves:
  - 4 vertical fibers, class (1,0), self 0-4 = -4;
  - 4 horizontal fibers, class (0,1), self 0-4 = -4;
  - graphs of PGL2(F3), class (1,1), self 2-4 = -2.

For rho(X)=1 from P1xP1 with b=16 blowups, need R=b+1=17
contracted curves. Since the 8 fibers are mutually compatible with all graphs,
we need a compatible clique of 9 graphs.
"""

from fractions import Fraction
from itertools import product

P1 = [0, 1, 2, "inf"]


def mobius(M, x):
    a, b, c, d = M
    if x == "inf":
        if c % 3 == 0:
            return "inf"
        return (a * pow(c, -1, 3)) % 3
    den = (c * x + d) % 3
    num = (a * x + b) % 3
    if den == 0:
        return "inf"
    return (num * pow(den, -1, 3)) % 3


def normM(M):
    M = tuple(x % 3 for x in M)
    for x in M:
        if x:
            inv = pow(x, -1, 3)
            return tuple((inv * y) % 3 for y in M)
    raise ValueError("zero")


PGL = sorted({
    normM((a, b, c, d))
    for a, b, c, d in product(range(3), repeat=4)
    if (a * d - b * c) % 3 != 0
})

GRAPHS = {M: frozenset((x, mobius(M, x)) for x in P1) for M in PGL}


def compatible(M, N):
    # Two (1,1) curves have intersection product 2.  For strict transforms to
    # be disjoint after blowing up grid points, both intersections must be grid
    # points, i.e. the maps agree at exactly two F3-points.
    return len(GRAPHS[M] & GRAPHS[N]) == 2


ADJ = {M: {N for N in PGL if N != M and compatible(M, N)} for M in PGL}


def find_clique(target=9):
    nodes = PGL[:]

    def expand(clique, candidates):
        if len(clique) == target:
            return clique
        if len(clique) + len(candidates) < target:
            return None
        while candidates:
            v = candidates[0]
            new_cands = [w for w in candidates[1:] if w in ADJ[v]]
            out = expand(clique + [v], new_cands)
            if out:
                return out
            candidates = candidates[1:]
        return None

    return expand([], nodes)


def main():
    print("#PGL2(F3) graphs:", len(PGL))
    clique = find_clique(9)
    if not clique:
        print("No compatible clique of 9 graphs; this 16-point grid variant cannot reach rho=1 with 17 curves.")
        return
    print("Found graph clique of size 9")

    # Pullback P = -K_Y + sum lambda_i C_i.
    # vertical/horizontal [-4] have lambda = -(4-2)/4 = -1/2.
    # (1,1) [-2] graphs have lambda = 0.
    # Therefore only the 8 fibers affect positivity.
    # For a generic (1,1) curve not in the selected clique:
    # -K_Y.D = 4 - 4 = 0, and it meets the 8 fibers in 8 points,
    # all at blown-up grid points, so intersections with strict transforms are 0.
    # This quick screen is inconclusive, but exceptional curves have:
    # P.E_p = 1 -1/2(vertical through p) -1/2(horizontal through p)=0.
    print("But P.E_p = 0 for every blown-up grid exceptional curve.")
    print("So even a clique would only give nef, not ample, before further modifications.")


if __name__ == "__main__":
    main()
