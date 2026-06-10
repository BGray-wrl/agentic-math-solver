#!/usr/bin/env python3
"""
Generate a Macaulay2 check script for a 5x5 skew Pfaffian format.

This is a harness, not an autonomous searcher.  Given weights and row degrees
a_i, it fills each matrix entry of degree a_i+a_j with a sparse deterministic
sum of available monomials, then checks codimension and cone smoothness.
"""

from __future__ import annotations

import itertools
import subprocess
import tempfile
from pathlib import Path


def monomials_of_degree(weights, degree, max_terms=4):
    out = []
    n = len(weights)

    def rec(i, rem, exps):
        if len(out) >= max_terms:
            return
        if i == n:
            if rem == 0:
                parts = []
                for j, e in enumerate(exps):
                    if e == 1:
                        parts.append(f"x{j}")
                    elif e > 1:
                        parts.append(f"x{j}^{e}")
                out.append("*".join(parts) or "1")
            return
        for e in range(rem // weights[i] + 1):
            rec(i + 1, rem - e * weights[i], exps + [e])

    rec(0, degree, [])
    return out


def make_script(weights, a):
    entries = {}
    for i in range(5):
        for j in range(i + 1, 5):
            d = a[i] + a[j]
            mons = monomials_of_degree(weights, d, max_terms=4)
            if not mons:
                raise ValueError(f"no monomials for entry {(i,j)} degree {d}")
            # deterministic small perturbation
            entries[(i, j)] = " + ".join(mons)

    rows = []
    for i in range(5):
        row = []
        for j in range(5):
            if i == j:
                row.append("0")
            elif i < j:
                row.append(entries[(i, j)])
            else:
                row.append(f"-({entries[(j, i)]})")
        rows.append("{" + ",".join(row) + "}")

    mat = "matrix{" + ",".join(rows) + "}"
    return f"""
p = 3;
S = (ZZ/p)[{','.join(f'x{i}' for i in range(len(weights)))}, Degrees=>{{{','.join(map(str, weights))}}}];
M = {mat};
I = pfaffians(4, M);
print "weights {weights}, row degrees {a}";
print("gens degrees: " | toString apply(flatten entries gens I, f -> (degree f)#0));
print("codim I: " | toString codim I);
J = jacobian I;
Sing = saturate(I + minors(3,J), ideal vars S);
print("sing cone ideal: " | toString Sing);
print("quasi-smooth: " | toString (Sing == ideal 1_S));
print("dim quotient ring: " | toString dim(S/I));
"""


def run(weights, a):
    script = make_script(weights, a)
    with tempfile.NamedTemporaryFile("w", suffix=".m2", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        return subprocess.check_output(["M2", "--script", path], text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    # Tiny smoke test format; not expected to solve anything.
    print(run((1, 1, 2, 2, 5, 5), (1, 1, 2, 2, 3)))
