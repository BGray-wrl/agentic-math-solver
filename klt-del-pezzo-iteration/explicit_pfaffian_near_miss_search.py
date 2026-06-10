#!/usr/bin/env python3
"""
Explicit random-matrix search around the Pfaffian near-miss formats.

For each selected codim-3 Pfaffian format, generate sparse 5x5 skew matrices
with entry degrees a_i+a_j.  Entries are biased to include monomials supported
on the quotient lines predicted by the numerical sieve.  Macaulay2 then checks:

  - codim(pfaffian ideal) = 3;
  - affine cone quasi-smoothness;
  - actual restricted ideals on the target quotient lines.

This is meant to close the "try explicit matrices around near misses" loop.
"""

from __future__ import annotations

import argparse
import random
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Format:
    name: str
    weights: tuple[int, ...]
    a: tuple[int, ...]
    target_pairs: tuple[tuple[int, int], ...]


FORMATS = [
    Format(
        "A_rho_211_200",
        (1, 1, 5, 5, 8, 8),
        (1, 2, 7, 8, 8),
        ((2, 3), (4, 5)),
    ),
    Format(
        "B_rho_43_1925",
        (2, 5, 5, 7, 8, 11),
        (3, 5, 7, 9, 10),
        ((0, 4), (1, 2)),
    ),
    Format(
        "C_rho_5608_13475",
        (5, 5, 7, 7, 8, 11),
        (2, 5, 6, 8, 10),
        ((0, 1), (2, 3)),
    ),
]


def monomial_exps(weights, degree):
    out = []
    n = len(weights)

    def rec(i, rem, exps):
        if i == n:
            if rem == 0:
                out.append(tuple(exps))
            return
        for e in range(rem // weights[i] + 1):
            exps.append(e)
            rec(i + 1, rem - e * weights[i], exps)
            exps.pop()

    rec(0, degree, [])
    return out


def exp_to_str(exps):
    parts = []
    for i, e in enumerate(exps):
        if e == 1:
            parts.append(f"x{i}")
        elif e > 1:
            parts.append(f"x{i}^{e}")
    return "*".join(parts) or "1"


def supported_on_pair(exps, pair):
    return all(e == 0 for i, e in enumerate(exps) if i not in pair)


def random_form(weights, degree, target_pairs, rng, random_terms=7, line_terms=2):
    mons = monomial_exps(weights, degree)
    if not mons:
        raise ValueError(f"no monomials of degree {degree}")
    chosen = []
    for pair in target_pairs:
        line_mons = [m for m in mons if supported_on_pair(m, pair)]
        if line_mons:
            chosen.extend(rng.sample(line_mons, min(line_terms, len(line_mons))))
    chosen.extend(rng.sample(mons, min(random_terms, len(mons))))
    # Deduplicate while preserving order.
    seen = set()
    uniq = []
    for m in chosen:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    terms = []
    for m in uniq:
        coeff = rng.choice([1, 1, 2])
        s = exp_to_str(m)
        terms.append(s if coeff == 1 else f"-{s}")
    expr = "+".join(terms).replace("+-", "-")
    return expr or "0"


def matrix_script(fmt: Format, seed: int, check_qs: bool):
    rng = random.Random(seed)
    weights = fmt.weights
    a = fmt.a
    entries = {}
    for i in range(5):
        for j in range(i + 1, 5):
            entries[(i, j)] = random_form(weights, a[i] + a[j], fmt.target_pairs, rng)
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
    matrix = "matrix{" + ",".join(rows) + "}"
    pair_checks = []
    for idx, (i, j) in enumerate(fmt.target_pairs):
        pair_checks.append(f"""
T{idx} = (ZZ/p)[y0_{idx}, y1_{idx}, Degrees=>{{{weights[i]},{weights[j]}}}];
phi{idx} = map(T{idx}, S, apply(toList(0..numgens S-1), k -> if k == {i} then T{idx}_0 else if k == {j} then T{idx}_1 else 0_T{idx}));
loc{idx} = apply(flatten entries gens I, f -> phi{idx} f);
nz{idx} = select(loc{idx}, f -> f != 0_T{idx});
print("LINE {i},{j} nonzero_pfaffians " | toString (#nz{idx}));
if (#nz{idx}) == 0 then (
    print("LINE {i},{j} CONTAINS_LINE");
) else (
    Iloc{idx} = ideal(nz{idx});
    Rloc{idx} = saturate(radical Iloc{idx}, ideal vars T{idx});
    print("LINE {i},{j} ideal " | toString Rloc{idx});
    print("LINE {i},{j} dim " | toString dim Rloc{idx} | " degree " | toString degree Rloc{idx});
);
""")
    qs_block = ""
    if check_qs:
        qs_block = """
if codim I == 3 then (
    J = jacobian I;
    Sing = saturate(I + minors(3,J), ideal vars S);
    print("quasi_smooth " | toString (Sing == ideal 1_S));
    if Sing != ideal 1_S then print("sing_cone_dim " | toString dim Sing);
);
"""
    return f"""
p = 3;
S = (ZZ/p)[{",".join(f"x{i}" for i in range(len(weights)))}, Degrees=>{{{",".join(map(str, weights))}}}];
M = {matrix};
I = pfaffians(4, M);
print "FORMAT {fmt.name} seed {seed}";
print("weights {weights} row_degrees {a}");
print("pfaffian_degrees " | toString apply(flatten entries gens I, f -> (degree f)#0));
print("codim " | toString codim I);
print("dimSI " | toString dim(S/I));
{qs_block}
{''.join(pair_checks)}
"""


def run_trial(fmt: Format, seed: int, timeout: int, check_qs: bool):
    script = matrix_script(fmt, seed, check_qs)
    with tempfile.NamedTemporaryFile("w", suffix=".m2", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        proc = subprocess.run(
            ["M2", "--script", path],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"TIMEOUT after {timeout}s"
    finally:
        Path(path).unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--check-qs", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated format-name substrings to run")
    args = ap.parse_args()
    wanted = [x for x in args.only.split(",") if x]
    for fmt in FORMATS:
        if wanted and not any(w in fmt.name for w in wanted):
            continue
        print(f"=== {fmt.name} weights={fmt.weights} a={fmt.a} ===", flush=True)
        for t in range(args.trials):
            seed = 1000 + 97 * t + len(fmt.name)
            rc, out, err = run_trial(fmt, seed, args.timeout, args.check_qs)
            print(f"--- trial {t} seed={seed} rc={rc} ---")
            lines = []
            for ln in out.splitlines():
                if (
                    ln.startswith("FORMAT")
                    or ln.startswith("weights")
                    or ln.startswith("pfaffian_degrees")
                    or ln.startswith("codim")
                    or ln.startswith("dimSI")
                    or ln.startswith("quasi_smooth")
                    or ln.startswith("sing_cone_dim")
                    or ln.startswith("LINE")
                ):
                    lines.append(ln)
            print("\n".join(lines) if lines else out[:1200])
            if err.strip():
                print("stderr:", err.strip()[:1200])


if __name__ == "__main__":
    main()
