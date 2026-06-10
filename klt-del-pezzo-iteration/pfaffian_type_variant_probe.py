#!/usr/bin/env python3
"""
For selected Pfaffian line-target formats, vary the possible tangent-weight
pairs at each quotient line and check whether any plausible basket gives
rho=1.

This is a numerical escalation after pfaffian_line_target_sieve.py reports
near misses.  It still does not prove a construction.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from itertools import combinations, product
from math import gcd

from pfaffian_format_sieve import H2_for_format
from search_binomial_hypersurface_family import correction, hj_chain, normalized_type


ROWS = [
    # Best near misses after the Pfaffian perfect-matching support correction.
    {
        "weights": (1, 1, 5, 5, 8, 8),
        "a": (1, 2, 7, 8, 8),
        "lines": [((2, 3), 25, 5), ((4, 5), 24, 3)],
    },
    {
        "weights": (2, 5, 5, 7, 8, 11),
        "a": (3, 5, 7, 9, 10),
        "lines": [((0, 4), 24, 3), ((1, 2), 25, 5)],
    },
    {
        "weights": (5, 5, 7, 7, 8, 11),
        "a": (2, 5, 6, 8, 10),
        "lines": [((0, 1), 25, 5), ((2, 3), 21, 3)],
    },
]


def possible_types(weights, pair):
    r = gcd(weights[pair[0]], weights[pair[1]])
    outside = [weights[k] for k in range(len(weights)) if k not in pair]
    out = sorted({
        normalized_type(r, u, v)
        for u, v in combinations(outside, 2)
        if normalized_type(r, u, v)
    })
    return out


def rho_for(weights, a, line_choices):
    s = sum(a)
    I = sum(weights) - s
    KX2 = I * I * H2_for_format(weights, a)
    basket = []
    for count, typ in line_choices:
        basket.extend([typ] * count)
    C = sum(correction(r, q) for r, q in basket)
    R = sum(len(hj_chain(r, q)) for r, q in basket)
    KY2 = KX2 - C
    rho = Fraction(10, 1) - KY2 - R
    return KX2, KY2, R, rho, Counter(basket)


def main():
    for row in ROWS:
        weights = row["weights"]
        a = row["a"]
        options = []
        print("FORMAT", weights, a)
        for pair, D, count in row["lines"]:
            ts = possible_types(weights, pair)
            print("  line", pair, "count", count, "possible types", ts)
            options.append([(count, t) for t in ts])
        hits = []
        near = []
        for choice in product(*options):
            KX2, KY2, R, rho, basket = rho_for(weights, a, choice)
            rec = (rho, KX2, KY2, R, basket, choice)
            if rho == 1:
                hits.append(rec)
            elif abs(rho - 1) <= 1:
                near.append(rec)
        print("  exact hits:", len(hits))
        for h in hits[:10]:
            print("   HIT", h)
        print("  closest:")
        for h in sorted(near, key=lambda x: abs(x[0] - 1))[:8]:
            print("   ", h)


if __name__ == "__main__":
    main()
