#!/usr/bin/env python3
"""
Search a finite-field incidence variant of Method C.

Start with P2 over char 3, blow up a subset B of the 13 F_3-points, and
contract selected F_3-lines.  A selected line through k blown-up points has
self-intersection 1-k, so k>=3 is contractible as a one-curve HJ chain [k-1].

For a rank-one target from P2, we need #selected_lines = #blown_up_points.
This script applies necessary tests:
  - selected lines are disjoint after blowup: every pairwise intersection is in B;
  - each selected line has k>=3;
  - pullback of -K_X is positive on exceptional curves and on unselected F_3-lines.

Passing this script would not prove ampleness against all curves, but failure is
a strong obstruction for this simple incidence-arrangement paradigm.
"""

from fractions import Fraction
from itertools import combinations


F = range(3)


def norm(pt):
    """Normalize a nonzero vector in F3^3 to a projective point."""
    pt = tuple(x % 3 for x in pt)
    for x in pt:
        if x % 3:
            inv = 1 if x == 1 else 2
            return tuple((inv * y) % 3 for y in pt)
    raise ValueError("zero vector")


POINTS = sorted({norm((a, b, c)) for a in F for b in F for c in F if (a, b, c) != (0, 0, 0)})
LINES = sorted({norm((a, b, c)) for a in F for b in F for c in F if (a, b, c) != (0, 0, 0)})


def dot(l, p):
    return sum(li * pi for li, pi in zip(l, p)) % 3


LINE_PTS = {l: frozenset(p for p in POINTS if dot(l, p) == 0) for l in LINES}
PT_LINES = {p: frozenset(l for l in LINES if dot(l, p) == 0) for p in POINTS}


def line_intersection(l1, l2):
    pts = LINE_PTS[l1] & LINE_PTS[l2]
    assert len(pts) == 1
    return next(iter(pts))


def coeff(k):
    # For a strict transform with self 1-k = -m, m=k-1.
    # Pullback coefficient in -K_X is -(m-2)/m = -(k-3)/(k-1).
    return -Fraction(k - 3, k - 1)


def p_intersections(B, selected):
    B = frozenset(B)
    selected = frozenset(selected)
    k = {l: len(LINE_PTS[l] & B) for l in selected}
    lam = {l: coeff(k[l]) for l in selected}

    # P.E_p = 1 + sum lambda_l over selected lines through p.
    min_E = min(Fraction(1, 1) + sum(lam[l] for l in PT_LINES[p] & selected) for p in B)

    # For an unselected F3-line M with kM blown-up points:
    # -K_Y.M = 3-kM.
    # L_l.M = 1 - #(B-points in l cap M), except if l=M.
    vals = []
    for M in LINES:
        if M in selected:
            continue
        kM = len(LINE_PTS[M] & B)
        val = Fraction(3 - kM, 1)
        for l in selected:
            val += lam[l] * (1 - len((LINE_PTS[l] & LINE_PTS[M]) & B))
        vals.append((val, M, kM))
    min_line = min(vals) if vals else (Fraction(999, 1), None, None)
    return min_E, min_line


def search():
    hits = []
    checked = 0
    for b in range(8, 14):
        for B_tuple in combinations(POINTS, b):
            B = frozenset(B_tuple)
            eligible = [l for l in LINES if len(LINE_PTS[l] & B) >= 3]
            if len(eligible) < b:
                continue
            for selected_tuple in combinations(eligible, b):
                selected = frozenset(selected_tuple)
                # Disjointness after blowup: every selected line-pair intersection is blown up.
                if any(line_intersection(l1, l2) not in B for l1, l2 in combinations(selected, 2)):
                    continue
                checked += 1
                min_E, min_line = p_intersections(B, selected)
                if min_E > 0 and min_line[0] > 0:
                    hits.append((B, selected, min_E, min_line))
                    print("HIT", "b=", b, "min_E=", min_E, "min_unselected_line=", min_line)
                    return hits
        print("finished b=", b, "checked configs so far", checked)
    return hits


def main():
    print(f"|P2(F3)|={len(POINTS)}, #F3-lines={len(LINES)}")
    hits = search()
    if not hits:
        print("No configuration passed the necessary positivity tests.")


if __name__ == "__main__":
    main()
