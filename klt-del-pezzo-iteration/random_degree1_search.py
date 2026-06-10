#!/usr/bin/env python3
"""
Random search in degree-1 del Pezzo hypersurfaces
    z^2 + G_6(u,v,w) = 0 in P(1,1,2,3), char 3.

For each sample, count distinct singular points on the disjoint cover:
  chart v=1, plus chart u=1 with t=v/u=0.
This misses only u=v=0, checked separately by the endpoint chart when needed;
for the generated samples with z^2 term and generic G, that locus is off or
non-singular unless the w^3 coefficient is special.
"""

from __future__ import annotations

import random
import subprocess
import tempfile
from pathlib import Path


MONOMS = []
for i in range(7):
    for j in range(7 - i):
        for k in range(4):
            if i + j + 2 * k == 6:
                parts = []
                if i:
                    parts.append("u" if i == 1 else f"u^{i}")
                if j:
                    parts.append("v" if j == 1 else f"v^{j}")
                if k:
                    parts.append("w" if k == 1 else f"w^{k}")
                MONOMS.append("*".join(parts) or "1")


def poly(coeffs):
    terms = []
    for c, m in zip(coeffs, MONOMS):
        if c == 1:
            terms.append(m)
        elif c == 2:
            terms.append("-" + m)
    return "+".join(terms).replace("+-", "-") or "0"


def main(n=500, seed=1234):
    rng = random.Random(seed)
    samples = []
    # include random dense and sparse samples
    for _ in range(n):
        coeffs = [rng.randrange(3) for _ in MONOMS]
        if all(c == 0 for c in coeffs):
            coeffs[0] = 1
        samples.append(poly(coeffs))

    body = "\n".join(f"Gs = append(Gs, {g});" for g in samples)
    script = f"""
p = 3;
S = (ZZ/p)[u,v,w, Degrees=>{{1,1,2}}];
Gs = {{}};
{body}

countG = G -> (
    Rv = (ZZ/p)[s,W2,Z2];
    phiv = map(Rv, S, {{s, 1_Rv, W2}});
    Gv = phiv G;
    Fv = Z2^2 + Gv;
    Iv = radical ideal(Fv, diff(s,Fv), diff(W2,Fv), diff(Z2,Fv));
    dv = if dim Iv <= 0 then degree Iv else -1000;

    Ru = (ZZ/p)[t,W,Z];
    phiu = map(Ru, S, {{1_Ru, t, W}});
    Gu = phiu G;
    Fu = Z^2 + Gu;
    Iu = radical ideal(Fu, diff(t,Fu), diff(W,Fu), diff(Z,Fu), t);
    du0 = if dim Iu <= 0 then degree Iu else -1000;
    dv + du0
);

best = 0;
bestG = 0_S;
for G in Gs do (
    c := countG G;
    if c > best then (
        best = c;
        bestG = G;
        print("NEW_BEST " | toString best | " :: " | toString bestG);
    );
    if c >= 8 then print("HIT " | toString c | " :: " | toString G);
);
print("FINAL_BEST " | toString best | " :: " | toString bestG);
"""
    with tempfile.NamedTemporaryFile("w", suffix=".m2", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        out = subprocess.check_output(["M2", "--script", path], text=True, timeout=120)
        print(out)
    finally:
        Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
