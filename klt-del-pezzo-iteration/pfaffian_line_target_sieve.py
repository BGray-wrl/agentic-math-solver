#!/usr/bin/env python3
"""
Targeted codim-3 Pfaffian line-stratum sieve.

This is a numerical search for Pfaffian formats where quotient singularities
come from isolated points on ambient singular lines.  For each pair of ambient
weights with gcd>1, restrict the five Pfaffian degrees to that weighted line.
If exactly one Pfaffian degree can appear on the line, estimate the number of
distinct roots by the binary weighted-polynomial lattice count, then compute
the cyclic basket contribution and rho.

This is a target generator, not a proof: explicit matrices still need M2.
"""

from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
from itertools import combinations, combinations_with_replacement
from math import gcd

from search_binomial_hypersurface_family import binary_root_details, correction, hj_chain, normalized_type
from pfaffian_format_sieve import H2_for_format, maximal_prime_strata, semigroup_representable, stratum_expected_dim


def wf(weights):
    return all(gcd(*[weights[j] for j in range(len(weights)) if j != i]) == 1 for i in range(len(weights)))


def point_types_on_line(weights, pair, D):
    i, j = pair
    info = binary_root_details(weights[i], weights[j], D)
    if not info:
        return []
    g = gcd(weights[i], weights[j])
    outside = [weights[k] for k in range(len(weights)) if k not in pair]
    # Crude tangent model for a quasi-smooth codim-3 format along an isolated
    # line point: two surviving outside tangent directions.
    typ_gen = None
    for u, v in combinations(outside, 2):
        typ_gen = normalized_type(g, u, v)
        if typ_gen:
            break
    out = []
    if typ_gen:
        out += [typ_gen] * info["finite"]
    if info["P0"]:
        for u, v in combinations(outside, 2):
            typ = normalized_type(weights[i], u, v)
            if typ:
                out.append(typ)
                break
    if info["P1"]:
        for u, v in combinations(outside, 2):
            typ = normalized_type(weights[j], u, v)
            if typ:
                out.append(typ)
                break
    return out


def has_perfect_matching(vertices, edges):
    verts = list(vertices)
    if not verts:
        return True
    v = verts[0]
    for w in verts[1:]:
        e = tuple(sorted((v, w)))
        if e in edges:
            rest = [x for x in verts if x not in (v, w)]
            if has_perfect_matching(rest, edges):
                return True
    return False


def active_pfaffian_degrees_on_line(line_weights, a):
    """Pfaffian degrees whose restricted 4x4 Pfaffian can be nonzero."""
    s = sum(a)
    edges = set()
    for i, j in combinations(range(5), 2):
        if semigroup_representable(a[i] + a[j], line_weights):
            edges.add((i, j))
    active = []
    for k in range(5):
        verts = [i for i in range(5) if i != k]
        if has_perfect_matching(verts, edges):
            active.append(s - a[k])
    return active


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-w", type=int, default=16)
    ap.add_argument("--max-a", type=int, default=14)
    ap.add_argument("--max-hits", type=int, default=10)
    args = ap.parse_args()
    hits = []
    near = []
    max_w = args.max_w
    max_a = args.max_a
    for weights in combinations_with_replacement(range(1, max_w + 1), 6):
        if not wf(weights):
            continue
        if any(w % 3 == 0 for w in weights):
            continue
        sumw = sum(weights)
        pairs = [(i, j) for i, j in combinations(range(6), 2) if gcd(weights[i], weights[j]) > 1]
        if not pairs:
            continue
        for a in combinations_with_replacement(range(1, max_a + 1), 5):
            s = sum(a)
            index = sumw - s
            if index <= 0:
                continue
            entry_degs = [a[i] + a[j] for i in range(5) for j in range(i + 1, 5)]
            if not all(semigroup_representable(d, weights) for d in entry_degs):
                continue
            pf_degs = [s - x for x in a]
            H2 = H2_for_format(weights, a)
            if H2 <= 0:
                continue
            KX2 = index * index * H2

            risk_primes = set()
            bad_positive_dim = False
            for p, idx in maximal_prime_strata(weights):
                if len(idx) >= 3:
                    edim, active = stratum_expected_dim(weights, a, idx)
                    if edim > 0:
                        bad_positive_dim = True
                        break
                    # Conservative: if a higher-dimensional isotropy stratum
                    # exists and is touched, do not count pairwise lines inside
                    # it until a local tangent quotient is explicitly checked.
                    if edim >= 0:
                        risk_primes.add(p)
            if bad_positive_dim:
                continue

            basket = []
            line_data = []
            bad = False
            for pair in pairs:
                gpair = gcd(weights[pair[0]], weights[pair[1]])
                if any(gpair % p == 0 for p in risk_primes):
                    continue
                active = active_pfaffian_degrees_on_line((weights[pair[0]], weights[pair[1]]), a)
                if len(active) == 0:
                    # Whole ambient singular line would lie on X.
                    bad = True
                    break
                if len(active) == 1:
                    types = point_types_on_line(weights, pair, active[0])
                    if types:
                        basket.extend(types)
                        line_data.append((pair, active[0], len(types), Counter(types)))
            if bad or len(basket) < 8:
                continue
            try:
                R = sum(len(hj_chain(r, q)) for r, q in basket)
                C = sum(correction(r, q) for r, q in basket)
            except Exception:
                continue
            KY2 = KX2 - C
            rho = Fraction(10, 1) - KY2 - R
            row = {
                "weights": weights,
                "a": a,
                "s": s,
                "index": index,
                "pf_degs": tuple(pf_degs),
                "KX2": KX2,
                "sing_count_est": len(basket),
                "basket": Counter(basket),
                "line_data": line_data,
                "R": R,
                "KY2": KY2,
                "rho": rho,
            }
            if rho == 1:
                hits.append(row)
                print("HIT", row)
                if len(hits) >= args.max_hits:
                    print("stopping after", args.max_hits, "hits")
                    return
            elif abs(rho - 1) <= 1:
                near.append(row)
    print("hits:", len(hits))
    print("near:", len(near))
    for row in sorted(near, key=lambda r: (abs(r["rho"] - 1), r["sing_count_est"]))[:20]:
        print("NEAR", row)


if __name__ == "__main__":
    main()
