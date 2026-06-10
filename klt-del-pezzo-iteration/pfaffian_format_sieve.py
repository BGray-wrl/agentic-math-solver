#!/usr/bin/env python3
"""
Numerical sieve for codimension-3 Gorenstein/Pfaffian surface formats.

Format model:
  X in weighted P^5 with 6 ambient variables of weights w.
  X is cut by the five 4x4 Pfaffians of a 5x5 skew matrix.
  Choose positive row degrees a_i.  Matrix entry (i,j) has degree a_i+a_j.
  Let s=sum(a_i).  The five Pfaffians have degrees s-a_i and the top
  self-dual resolution shift is s, so K_X = O(s-sum(w)).

This is only a numerical-format sieve.  It checks:
  - well-formed/tame ambient;
  - Fano index sum(w)-s > 0;
  - every matrix entry degree is representable by monomials in the ambient weights;
  - Hilbert leading coefficient H^2 and K_X^2;
  - possible ambient quotient singularity counts from maximal gcd strata;
  - approximate basket/rho target for isolated stratum points.

It does not prove quasi-smoothness or construct explicit equations.
"""

from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
from itertools import combinations, combinations_with_replacement
from math import gcd

from search_binomial_hypersurface_family import hj_chain, correction, normalized_type


def semigroup_representable(d: int, weights: tuple[int, ...]) -> bool:
    reachable = [False] * (d + 1)
    reachable[0] = True
    for n in range(d + 1):
        if not reachable[n]:
            continue
        for w in weights:
            if n + w <= d:
                reachable[n + w] = True
    return reachable[d]


def numerator_coeff_u3(pf_degs: list[int], s: int) -> int:
    # N(t)=1-sum t^D + sum t^{s-D} - t^s.
    # t^m=(1-u)^m has u^3 coefficient -C(m,3).
    def c3(m):
        return -m * (m - 1) * (m - 2) // 6

    return -sum(c3(d) for d in pf_degs) + sum(c3(s - d) for d in pf_degs) - c3(s)


def H2_for_format(weights: tuple[int, ...], a: tuple[int, ...]) -> Fraction:
    s = sum(a)
    pf = [s - x for x in a]
    coeff = numerator_coeff_u3(pf, s)
    prod = 1
    for w in weights:
        prod *= w
    return Fraction(coeff, prod)


def maximal_prime_strata(weights: tuple[int, ...]):
    primes = set()
    for w in weights:
        n = w
        p = 2
        while p * p <= n:
            if n % p == 0:
                primes.add(p)
                while n % p == 0:
                    n //= p
            p += 1
        if n > 1:
            primes.add(n)
    out = []
    for p in sorted(primes):
        idx = tuple(i for i, w in enumerate(weights) if w % p == 0)
        if idx:
            out.append((p, idx))
    return out


def stratum_expected_dim(weights, a, idx):
    """
    Crude expected projective dimension of X intersect maximal stratum idx.
    We count a Pfaffian as active if its degree is representable using only
    the stratum weights.  Expected codim is min(3, number active), since the
    five Pfaffians have codim at most 3.
    """
    s = sum(a)
    pf = [s - x for x in a]
    sw = tuple(weights[i] for i in idx)
    active = sum(1 for d in pf if semigroup_representable(d, sw))
    return len(idx) - 1 - min(3, active), active


def generic_type_for_stratum(weights, idx):
    g = 0
    for i in idx:
        g = weights[i] if g == 0 else gcd(g, weights[i])
    outside = [weights[i] % g for i in range(len(weights)) if i not in idx]
    # For a surface point, tangent is 2-dimensional; this is too crude, so use
    # the first two outside weights that are units mod g if possible.
    units = [u for u in outside if gcd(u, g) == 1]
    if len(units) >= 2:
        return normalized_type(g, units[0], units[1])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-w", type=int, default=14)
    ap.add_argument("--max-a", type=int, default=12)
    ap.add_argument("--max-hits", type=int, default=20)
    args = ap.parse_args()
    max_w = 18
    max_a = 18
    max_w = args.max_w
    max_a = args.max_a
    rows = []
    for weights in combinations_with_replacement(range(1, max_w + 1), 6):
        # Well-formed P^5: gcd of any 5 weights is 1.
        if any(gcd(*[weights[j] for j in range(6) if j != i]) != 1 for i in range(6)):
            continue
        if any(w % 3 == 0 for w in weights):
            continue
        sumw = sum(weights)
        for a in combinations_with_replacement(range(1, max_a + 1), 5):
            s = sum(a)
            I = sumw - s
            if I <= 0:
                continue
            entry_degs = [a[i] + a[j] for i in range(5) for j in range(i + 1, 5)]
            if not all(semigroup_representable(d, weights) for d in entry_degs):
                continue
            H2 = H2_for_format(weights, a)
            if H2 <= 0:
                continue
            KX2 = I * I * H2

            # Singularity count target: isolated maximal strata with expected
            # dim 0.  Degree count is not available here; use 1 point per such
            # stratum as a lower signal and active-degree product as an upper
            # signal would require real equations.
            strata = []
            basket = []
            bad_positive_dim = False
            for p, idx in maximal_prime_strata(weights):
                if len(idx) < 2:
                    continue
                edim, active = stratum_expected_dim(weights, a, idx)
                if edim > 0:
                    bad_positive_dim = True
                    break
                if edim == 0:
                    typ = generic_type_for_stratum(weights, idx)
                    strata.append((p, idx, active, typ))
                    if typ:
                        basket.append(typ)
            if bad_positive_dim or len(strata) < 8:
                continue
            R = 0
            C = Fraction(0)
            ok_basket = True
            for r, q in basket:
                try:
                    R += len(hj_chain(r, q))
                    C += correction(r, q)
                except Exception:
                    ok_basket = False
                    break
            if not ok_basket or len(basket) < 8:
                continue
            KY2 = KX2 - C
            rho = Fraction(10, 1) - KY2 - R
            if rho == 1:
                rows.append({
                    "weights": weights,
                    "a": a,
                    "s": s,
                    "index": I,
                    "pf_degs": tuple(s - x for x in a),
                    "H2": H2,
                    "KX2": KX2,
                    "strata": strata,
                    "basket": Counter(basket),
                    "R": R,
                    "rho": rho,
                })
                print("HIT", rows[-1])
                if len(rows) >= args.max_hits:
                    return
    print("hits:", len(rows))


if __name__ == "__main__":
    main()
