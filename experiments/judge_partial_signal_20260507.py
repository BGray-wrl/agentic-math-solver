#!/usr/bin/env python3
"""
For each problem, compute structural-quality metrics on candidates and see if
they correlate with judge label (even when no candidate fully verifies).

Hypothesis: judge=correct → more "progress toward the answer" than judge=incorrect.
"""
from __future__ import annotations
import json, sys, re
from pathlib import Path
from collections import defaultdict
import sympy as sp

ROOT = Path(__file__).parent.parent

def extract_after_answer(text):
    m = re.search(r"##\s*Answer\s*\n", text, re.I)
    if m: text = text[m.end():]
    return text.strip()


# ---------- Inverse-Galois quality metrics ----------
def metrics_inverse_galois(text, expected_deg):
    body = extract_after_answer(text)
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    out = {"poly_extracted": False, "deg_match": False, "irreducible": False,
           "disc_nonzero": False, "disc_perfect_sq": False, "coeff_max": 0}
    x = sp.Symbol("x")
    poly = None
    for ln in body.split("\n"):
        ln = ln.strip()
        if "x" in ln and re.match(r"^[\sx0-9+\-*^()\.]+$", ln.replace("**","").replace("\\^","^")):
            try:
                poly = sp.sympify(ln.replace("^","**"), locals={"x":x})
                break
            except: continue
    if poly is None: return out
    out["poly_extracted"] = True
    try:
        deg = int(sp.Poly(poly, x).total_degree())
        out["deg"] = deg
        out["deg_match"] = (deg == expected_deg)
        if not out["deg_match"]: return out
        out["irreducible"] = (sp.factor(poly) == sp.expand(poly))
        try:
            disc = int(sp.discriminant(poly, x))
            out["disc_nonzero"] = (disc != 0)
            out["disc"] = disc
            out["disc_perfect_sq"] = sp.sqrt(abs(disc)).is_integer if disc != 0 else False
            # log10 of |disc| as a rough size measure
            if abs(disc) > 0:
                out["disc_log10"] = float(sp.log(abs(disc), 10))
        except: pass
        coeffs = [int(c) for c in sp.Poly(poly, x).all_coeffs()]
        out["coeff_max"] = max(abs(c) for c in coeffs) if coeffs else 0
    except: pass
    return out


# ---------- arithmetic-kakeya quality metrics ----------
def metrics_arithmetic_kakeya(text, threshold):
    body = extract_after_answer(text).strip()
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    out = {"line1_format": False, "score_le_threshold": False,
           "x_format": False, "x_has_origin": False, "x_no_antidiag": False,
           "n_product_matches": False, "T_size_matches": False, "R_size_matches": False,
           "n_vertices": 0, "score_value": None}
    if len(lines) < 6: out["n_lines"] = len(lines); return out
    out["n_lines"] = len(lines)
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", lines[0])
    if not m: return out
    p,q,m_,R_,n_,T_ = (int(g) for g in m.groups())
    out["line1_format"] = True
    out["n_vertices"] = n_
    if q != 0:
        out["score_value"] = p/q
        out["score_le_threshold"] = p/q <= threshold + 1e-9
    # Try parse X
    try:
        X = eval(lines[1], {"__builtins__":{}}, {})
        if isinstance(X, list) and all(isinstance(t, tuple) and len(t)==2 for t in X):
            out["x_format"] = True
            out["x_has_origin"] = (0,0) in X
            out["x_no_antidiag"] = all(a+b!=0 for (a,b) in X if (a,b)!=(0,0))
    except: pass
    # Try parse d
    try:
        line3 = lines[2].strip()
        if line3.startswith("["):
            ds = eval(line3, {"__builtins__":{}}, {})
        else:
            ds = [int(t) for t in re.split(r"[,\s]+", line3) if t]
        n_calc = 1
        for d in ds: n_calc *= d
        out["n_product_matches"] = (n_calc == n_)
    except: pass
    # T size
    try:
        T_list = eval(lines[4], {"__builtins__":{}}, {})
        out["T_size_matches"] = len(T_list) == T_
    except: pass
    # R size
    try:
        R_list = eval(lines[5], {"__builtins__":{}}, {})
        out["R_size_matches"] = len(R_list) == R_
    except: pass
    return out


# ---------- Hadamard quality metrics ----------
def metrics_hadamard(text, expected_n):
    body = extract_after_answer(text)
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    rows = []
    for line in body.splitlines():
        line = line.strip().strip(",")
        if not line: continue
        toks = re.split(r"[,\s]+", line)
        try:
            row = [int(t) for t in toks if t]
            if row: rows.append(row)
        except: pass
    out = {"any_rows": False, "n_rows": 0, "max_row_len": 0,
           "all_pm1": False, "n_rows_match": False, "square": False,
           "row_orthogonal_pairs": 0}
    if not rows: return out
    out["any_rows"] = True
    out["n_rows"] = len(rows)
    out["max_row_len"] = max(len(r) for r in rows)
    out["all_pm1"] = all(abs(v) == 1 for r in rows for v in r) if rows else False
    out["n_rows_match"] = len(rows) == expected_n
    if all(len(r) == len(rows[0]) for r in rows):
        out["square"] = (len(rows) == len(rows[0]))
        if out["square"] and out["all_pm1"]:
            import numpy as np
            H = np.array(rows, dtype=int)
            P = H @ H.T
            n = len(rows)
            # how many off-diagonal entries are 0 (orthogonal)?
            mask = 1 - np.eye(n, dtype=int)
            out["row_orthogonal_pairs"] = int(np.sum((P == 0) & (mask == 1)) // 2)
            out["row_orthogonal_pct"] = out["row_orthogonal_pairs"] / (n*(n-1)/2) if n >= 2 else 0
    return out


# ---------- Steiner quality metrics ----------
def metrics_steiner(text, r_constraint):
    body = extract_after_answer(text)
    body = re.sub(r"^```\w*\n?|```$", "", body.strip(), flags=re.M).strip()
    lines = [l for l in body.split("\n") if l.strip()]
    out = {"header_format": False, "blocks_parsed": 0, "uniform_block_size": False,
           "values_in_range": False, "no_dup_in_block": False,
           "all_r_subsets_covered_at_least_once": False, "all_r_subsets_at_most_once": False,
           "n": 0, "q": 0, "r": 0}
    if not lines: return out
    m = re.match(r"#?\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)", lines[0])
    if not m: return out
    n,q,r = int(m.group(1)), int(m.group(2)), int(m.group(3))
    out["n"] = n; out["q"] = q; out["r"] = r
    out["header_format"] = True
    out["r_in_range"] = (r == 5) if r_constraint == "warmup" else (5 < r < 10)
    out["n_lt_200"] = n < 200
    out["n_gt_q_gt_r"] = n > q > r
    blocks = []
    for line in lines[1:]:
        try:
            block = tuple(sorted(int(x) for x in line.split()))
            blocks.append(block)
        except: pass
    out["blocks_parsed"] = len(blocks)
    if not blocks: return out
    out["uniform_block_size"] = all(len(b) == q for b in blocks)
    out["values_in_range"] = all(all(1 <= v <= n for v in b) for b in blocks)
    out["no_dup_in_block"] = all(len(set(b)) == len(b) for b in blocks)
    if out["uniform_block_size"] and out["values_in_range"] and out["no_dup_in_block"]:
        from itertools import combinations
        n_choose_r = 1
        for i in range(r): n_choose_r = n_choose_r * (n-i) // (i+1)
        cov = {}
        for B in blocks:
            for sub in combinations(B, r):
                cov[sub] = cov.get(sub, 0) + 1
        out["coverage"] = len(cov) / n_choose_r if n_choose_r else 0
        out["all_r_subsets_covered_at_least_once"] = (len(cov) == n_choose_r)
        out["all_r_subsets_at_most_once"] = all(v == 1 for v in cov.values())
    return out


# ---------- Ramsey-book quality metrics ----------
def metrics_ramsey_book_warmup(text):
    body = extract_after_answer(text)
    body = re.sub(r"\s+", "", body)
    body = re.sub(r"[^01]", "", body)
    out = {"any_bits": False, "len": len(body), "expected_len": 4753,
           "len_match": False}
    if not body: return out
    out["any_bits"] = True
    out["len_match"] = (len(body) == 4753)
    if out["len_match"]:
        import numpy as np
        N = 98
        A = np.zeros((N,N), dtype=int)
        idx = 0
        for j in range(1, N):
            for i in range(j):
                A[i,j] = int(body[idx]); A[j,i] = A[i,j]; idx += 1
        # # of B_24 in G, # of B_25 in complement
        def count_books(M, n_pages):
            count = 0
            for i in range(N):
                for j in range(i+1, N):
                    if M[i,j] == 0: continue
                    common = (M[i] & M[j]).sum()
                    if common >= n_pages: count += 1
            return count
        out["density"] = float(np.sum(A)) / (N*(N-1))
        out["b24_in_G"] = count_books(A, 24)
        out["b25_in_complement"] = count_books(1 - A - np.eye(N,dtype=int), 25)
    return out


# ---------- Small-diophantine quality metrics ----------
def metrics_small_diophantine(text):
    body = extract_after_answer(text)
    triples = re.findall(r"\(\s*([\-\d]+)\s*,\s*([\-\d]+)\s*,\s*([\-\d]+)\s*\)", body)
    out = {"n_triples": len(triples), "n_int_triples": 0, "n_x_big": 0,
           "n_satisfy_eq": 0, "n_distinct_x_big": 0, "max_log_x": 0}
    big_xs = set()
    int_triples = []
    for t in triples[:10]:
        try:
            x,y,z = int(t[0]), int(t[1]), int(t[2])
            int_triples.append((x,y,z))
        except: continue
    out["n_int_triples"] = len(int_triples)
    for x,y,z in int_triples:
        if abs(x) > 10**50:
            out["n_x_big"] += 1
            big_xs.add(x)
            try:
                lg = sp.log(abs(x), 10)
                out["max_log_x"] = max(out["max_log_x"], float(lg))
            except: pass
        if z*z + y*y*z + x**3 + 2 == 0:
            out["n_satisfy_eq"] += 1
    out["n_distinct_x_big"] = len(big_xs)
    return out


METRICS = {
    ("inverse-galois", "warmup"):       lambda t: metrics_inverse_galois(t, 22),
    ("inverse-galois", "full_problem"): lambda t: metrics_inverse_galois(t, 23),
    ("arithmetic-kakeya", "warmup"):       lambda t: metrics_arithmetic_kakeya(t, 1.75),
    ("arithmetic-kakeya", "full_problem"): lambda t: metrics_arithmetic_kakeya(t, 1.675),
    ("hadamard", "warmup"):       lambda t: metrics_hadamard(t, 428),
    ("hadamard", "full_problem"): lambda t: metrics_hadamard(t, 668),
    ("large-steiner-systems", "warmup"):       lambda t: metrics_steiner(t, "warmup"),
    ("large-steiner-systems", "full_problem"): lambda t: metrics_steiner(t, "full"),
    ("ramsey-book-graphs", "warmup"):          metrics_ramsey_book_warmup,
    ("small-diophantine", "warmup"):           metrics_small_diophantine,
}


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "logs" / "openproblems_pass5_20260507_20260507_183859.jsonl")
    rows = []
    with open(log) as f:
        for ln in f:
            r = json.loads(ln)
            if r.get("kind") == "trial" or (r.get("gen_text") and r.get("problem_id")):
                rows.append(r)

    by_pid = defaultdict(list)
    for r in rows:
        key = (r["problem_id"], r["prompt_type"])
        if key not in METRICS: continue
        try:
            m = METRICS[key](r.get("gen_text") or "")
        except Exception as e:
            m = {"crash": str(e)}
        by_pid[key].append((r["label"], m, r["seed"], r["model"].split("/")[-1]))

    rank = {"correct":3, "almost":2, "partial":1, "incorrect":0}

    for k in sorted(by_pid):
        print(f"\n{'='*78}")
        print(f"{k[0]}  ({k[1]})")
        print('='*78)
        items = by_pid[k]
        # Group by judge label, average each metric
        groups = defaultdict(list)
        for lab, m, seed, model in items:
            groups[lab].append(m)
        # Find all keys
        all_keys = set()
        for ms in groups.values():
            for m in ms: all_keys.update(m.keys())
        all_keys = [k for k in sorted(all_keys) if not k.startswith("crash")]
        # Print per-label averages
        labels_order = [l for l in ("correct","almost","partial","incorrect") if l in groups]
        if not labels_order: continue
        print(f"  {'Metric':<30}", "  ".join(f"{l:<14}" for l in labels_order))
        for mk in all_keys:
            vals_per_label = []
            for lab in labels_order:
                ms = groups[lab]
                vs = [m.get(mk) for m in ms if m.get(mk) is not None]
                if not vs: vals_per_label.append("-"); continue
                if isinstance(vs[0], bool):
                    pct = sum(1 for v in vs if v) / len(vs)
                    vals_per_label.append(f"{pct:.0%} ({sum(1 for v in vs if v)}/{len(vs)})")
                elif isinstance(vs[0], (int,float)):
                    avg = sum(vs)/len(vs)
                    vals_per_label.append(f"{avg:.2f}")
                else:
                    vals_per_label.append(str(vs[0])[:14])
            print(f"  {mk:<30}", "  ".join(f"{v:<14}" for v in vals_per_label))


if __name__ == "__main__":
    main()
