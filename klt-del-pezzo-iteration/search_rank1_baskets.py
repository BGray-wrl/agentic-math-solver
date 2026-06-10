#!/usr/bin/env python3
"""
Enumerate cyclic quotient baskets as numerical targets.

This is not a construction search.  It asks: are there even plausible
rank-one rational klt del Pezzo baskets with >=8 singularities and K_X^2>0?
Allow indices divisible by 3, flagged as wild targets.
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from itertools import combinations_with_replacement

from search_binomial_hypersurface_family import hj_chain, correction


def types(max_r=20):
    out = []
    for r in range(2, max_r + 1):
        for q in range(1, r):
            if __import__("math").gcd(r, q) != 1:
                continue
            ch = tuple(hj_chain(r, q))
            # identify q and inverse q as same unoriented singularity
            if q > pow(q, -1, r):
                continue
            out.append({
                "r": r,
                "q": q,
                "chain": ch,
                "len": len(ch),
                "corr": correction(r, q),
                "wild": r % 3 == 0,
            })
    return out


def main():
    ts = types(18)
    # Keep small-resolution targets first; otherwise the combinatorics explodes.
    ts = [t for t in ts if t["len"] <= 4]
    by_len = defaultdict(list)
    for t in ts:
        by_len[t["len"]].append(t)

    hits = []
    # For rho=1 on a rational surface: rho(X)=10-KY^2-R = 1.
    # So KY^2 = 9-R. Need KX^2 = KY^2 + sum(corr) > 0.
    # Also KY^2 is integer in [-?, 9].
    for n_sing in range(8, 13):
        # Restrict total exceptional length R to a sane range.
        for combo in combinations_with_replacement(range(len(ts)), n_sing):
            basket = [ts[i] for i in combo]
            R = sum(t["len"] for t in basket)
            if R > 24:
                continue
            KY2 = Fraction(9 - R, 1)
            KX2 = KY2 + sum(t["corr"] for t in basket)
            if KX2 <= 0:
                continue
            hits.append({
                "n": n_sing,
                "R": R,
                "KY2": KY2,
                "KX2": KX2,
                "wild": any(t["wild"] for t in basket),
                "basket": [(t["r"], t["q"], t["chain"]) for t in basket],
            })
            if len(hits) >= 50:
                break
        if len(hits) >= 50:
            break

    print("first numerical rank-one basket targets:", len(hits))
    for h in hits[:50]:
        print(h)


if __name__ == "__main__":
    main()
