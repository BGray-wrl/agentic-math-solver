#!/usr/bin/env python3
"""
Sanity-check the inverse-galois polynomial submissions.
Without Magma, I can at least check:
  - is the polynomial irreducible over Q?
  - is the discriminant a perfect square (required for Galois group ⊆ A_n)?
  - the actual coefficients
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
import sympy as sp
from sympy import Poly, symbols, factor, discriminant

x = symbols("x")

def parse_poly(text):
    # Find ## Answer
    m = re.search(r"##\s*Answer\s*\n", text, re.I)
    if m: text = text[m.end():]
    text = re.sub(r"^```\w*\n?|```$", "", text.strip(), flags=re.M).strip()
    # Pick the first line that looks like a polynomial
    for ln in text.split("\n"):
        ln = ln.strip()
        if "x" in ln and re.match(r"^[\sx0-9+\-*^()\.]+$", ln.replace("**","").replace("\\^","^")):
            try:
                expr = ln.replace("^","**")
                p = sp.sympify(expr, locals={"x": x})
                return p, ln
            except: continue
    return None, None


def check_poly(p, expected_deg):
    info = {"deg": int(sp.Poly(p, x).total_degree()), "expected_deg": expected_deg}
    info["matches_deg"] = info["deg"] == expected_deg
    if not info["matches_deg"]: return info
    # irreducibility over Q
    factored = sp.factor(p)
    if factored != sp.expand(p):  # factored is different
        info["reducible"] = True
        info["factored"] = str(factored)[:200]
    else:
        info["reducible"] = False
    # discriminant
    try:
        disc = int(sp.discriminant(p, x))
        info["disc_abs"] = abs(disc)
        # Check if perfect square
        sqrt_disc = sp.sqrt(abs(disc))
        info["disc_sqrt_int"] = sqrt_disc.is_integer
        info["disc_sign"] = "+" if disc > 0 else ("-" if disc < 0 else "0")
    except Exception as e:
        info["disc_error"] = str(e)
    return info


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "logs" / "openproblems_pass5_20260507_20260507_183859.jsonl")
    rows = []
    with open(log) as f:
        for ln in f:
            r = json.loads(ln)
            if r.get("kind") == "trial" and r.get("problem_id") == "inverse-galois":
                rows.append(r)
    print(f"inverse-galois trials: {len(rows)}\n")
    for r in rows:
        p, raw = parse_poly(r.get("gen_text") or "")
        if p is None:
            print(f"  {r['prompt_type']:<14} {r['model'].split('/')[-1]:<22} seed={r['seed']}  {r['label']:<10}  → no poly extracted")
            continue
        expected_deg = 22 if r["prompt_type"] == "warmup" else 23
        info = check_poly(p, expected_deg)
        irr = "IRRED" if not info.get("reducible", True) else "REDUCIBLE"
        sq = "sq" if info.get("disc_sqrt_int") else "non-sq"
        sgn = info.get("disc_sign", "?")
        deg_ok = "✓" if info.get("matches_deg") else "✗"
        # Galois group ⊆ A_n iff disc is perfect square in Q.
        # M_22 ⊆ A_22 yes (M_22 has odd permutations? Actually M_22 ⊆ A_22 since M_22 is simple non-abelian, it's in the unique simple subgroup of S_22)
        # Actually M_22 is contained in A_22 (since [S_22:A_22]=2 and M_22 simple non-abelian → M_22 ⊆ A_22).
        # So disc must be a perfect square.
        # M_23 ⊆ A_23 similarly.
        consistent = "OK" if (info.get("matches_deg") and not info.get("reducible") and info.get("disc_sqrt_int")) else "FAIL"
        print(f"  {r['prompt_type']:<14} {r['model'].split('/')[-1]:<22} seed={r['seed']}  judge={r['label']:<10}  deg={deg_ok}{info['deg']}  {irr}  disc={sgn}{sq}  → {consistent}")


if __name__ == "__main__":
    main()
