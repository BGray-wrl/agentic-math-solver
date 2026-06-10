"""
M2-backed klt del Pezzo verifier for Method B (weighted hypersurface or CI).
Builds a per-candidate M2 script and runs it; parses results into a scored partial signal.

Score rubric (0-7):
  0: parse failure / not weight-homogeneous
  1: not tame OR not well-formed OR Fano index <= 0 OR codim wrong
  2: cone has positive-dim singular locus / X contains a singular stratum
  3: cone has isolated non-Du-Val singularities AND count < N_required
  4: cone has isolated singularities, count >= N_required (but not quasi-smooth)
  5: quasi-smooth + count OK + ρ(X) != 1 (verified non-1)
  6: quasi-smooth + count = N_required - 1 (ONE SHORT) OR quasi-smooth + count OK + ρ inconclusive (PICARD_UNKNOWN)
  7: quasi-smooth, count >= N_required, ρ(X) = 1 VERIFIED — PASS

Hardening 2026-05-11:
  - Linear-elimination detection: if F is linear in some variable with constant coefficient,
    X ≅ P(remaining weights). Short-circuits to lower-dim weighted projective space analysis.
  - Endpoint stabilizers: coordinate-point endpoints on singular lines have FULL stabilizer mu_{w_i},
    larger than the generic line stabilizer mu_gcd. Counted separately as coord-pts.
  - Picard escalation: if ρ check is inconclusive (e.g., CI case), refuse PASS — cap at score 6
    with verdict "PICARD_UNKNOWN" rather than auto-accept.

Usage:
    from klt_verifier import verify_method_b
    result = verify_method_b(weights=[2,2,5,5], eqns=["x0^5 + x1^5 + x2^2 + x3^2"], n_sing_required=7)
    print(result['score'], result['verdict'])
"""
from __future__ import annotations
import subprocess, tempfile, json, os, re
from pathlib import Path
from math import gcd
from functools import reduce

ITER_DIR = Path("/Users/benjamingrayzel/sandbox/agentic-math-solver/klt-del-pezzo-iteration")

M2_SCRIPT_TEMPLATE = r"""
p = {p};
weights = {{ {weights} }};
n = #weights;
varList = apply(n, i -> getSymbol("x" | toString i));
S = (ZZ/p)(monoid[varList, Degrees => weights]);
use S;

eqns = apply({eqns_list}, e -> value e);
print "EQNS_PARSED";
for f in eqns do print(toString f);

-- Check weight-homogeneity
homOK = all(eqns, f -> f != 0 and isHomogeneous f);
print("HOM_OK: " | toString homOK);
if homOK then (
    for f in eqns do print("DEG: " | toString (degree f)#0);
);

-- Tameness
print("TAME: " | toString all(weights, w -> w % p != 0));

-- Well-formedness
wf = true;
for i from 0 to n-1 do (
    wD = drop(weights, {{i,i}});
    if gcd wD > 1 then (wf = false);
);
print("WELL_FORMED: " | toString wf);

-- Fano index
sumW = sum weights;
sumD = if homOK then sum apply(eqns, f -> (degree f)#0) else 0;
fanoIdx = sumW - sumD;
print("FANO_INDEX: " | toString fanoIdx);

if not homOK or not wf then (exit 0;);

-- Linear-elimination detection (hypersurface only): is F = c * x_i + g(others) where c is a
-- nonzero constant? Then X ≅ P(remaining weights). Catches the linear-elim collapse class
-- of false positives (the round-3 deepseek seed=44 score-6 thread).
print "LINEAR_ELIM_CHECK:";
hasLinElim = false;
linElimVar = -1;
linElimCoef = "";
if #eqns == 1 then (
    fLE = eqns#0;
    for iLE from 0 to n-1 do (
        if not hasLinElim then (
            dfLE = diff(S_iLE, fLE);
            if dfLE != 0 and (degree dfLE)#0 == 0 then (
                hasLinElim = true;
                linElimVar = iLE;
                linElimCoef = toString dfLE;
            );
        );
    );
);
print("LINEAR_ELIM: " | toString hasLinElim);
if hasLinElim then (
    print("LINEAR_ELIM_VAR: " | toString linElimVar);
    print("LINEAR_ELIM_COEF: " | linElimCoef);
);

-- Cone singular locus
I = ideal eqns;
J = jacobian I;
M = minors(#eqns, J);
singCone = saturate(I + M, ideal vars S);
qs = (singCone == ideal 1_S);
print("QUASI_SMOOTH: " | toString qs);
if not qs then (
    print("SING_CONE_DIM: " | toString (dim singCone - 1));
    print("SING_CONE_GENS: " | toString flatten entries gens singCone);
);

-- Coordinate points: for each i with weights_i > 1, check if (0,...,1@i,...,0) on X
print "COORD_PTS:";
for i from 0 to n-1 do (
    if weights#i > 1 then (
        subList = apply(n, j -> if j == i then 1_S else 0_S);
        vals = apply(eqns, f -> sub(f, apply(n, j -> S_j => subList#j)));
        onX = all(vals, v -> v == 0);
        if onX then print("  P_" | toString i | " (wt " | toString weights#i | "): ON_X");
    );
);

-- Maximal-isotropy strata: for each PRIME p dividing some weight, find the maximal subset
-- of indices i with p | weights#i.  That subset defines the mu_p stratum.
-- If 3+ indices share a prime, the stratum has dim >= 2.
print "MAX_ISOTROPY_STRATA:";
allPrimes = unique flatten apply(weights, w -> apply(toList factor w, q -> q#0));
for q in allPrimes do (
    if q == p then continue;  -- characteristic; skip
    qSubset = positions(weights, w -> w % q == 0);
    if #qSubset < 2 then continue;  -- need at least 2 vars for a stratum >= 0-dim singular
    stratumDim = #qSubset - 1;  -- projective dim of stratum
    print("  Prime " | toString q | ": indices " | toString qSubset | " (stratum dim " | toString stratumDim | "):");
    -- Restrict X to this stratum: set x_k = 0 for k not in qSubset
    subList = apply(n, k -> if member(k, qSubset) then S_k else 0_S);
    eqnsLoc = apply(eqns, f -> sub(f, apply(n, k -> S_k => subList#k)));
    nzL = select(eqnsLoc, f -> f != 0);
    nNZ = length nzL;
    nEq = length eqns;
    print("    eqn_count_active: " | toString nNZ | " of " | toString nEq);
    if nNZ == 0 then (
        print("    CONTAINS_STRATUM: true");
    ) else (
        -- Build local ring of P(weights on stratum)
        kStrat = #qSubset;
        ynames = apply(kStrat, k -> getSymbol("y" | toString k));
        stratumWeights = apply(qSubset, k -> weights#k);
        Sloc = (ZZ/p)(monoid[ynames, Degrees => stratumWeights]);
        phi = map(Sloc, S, apply(n, k -> (
            posK = position(qSubset, x -> x == k);
            if posK === null then 0_Sloc else Sloc_(posK)
        )));
        eqnsLocLoc = apply(eqns, f -> phi f);
        eqnsLocNZ = select(eqnsLocLoc, f -> f != 0);
        Iloc = ideal eqnsLocNZ;
        satLoc = saturate(Iloc, ideal vars Sloc);
        if satLoc == ideal 1_Sloc then (
            print("    X_CAP_STRATUM_DIM: empty");
        ) else (
            xcapDim = dim satLoc - 1;  -- projective dim of X cap stratum
            print("    X_CAP_STRATUM_DIM: " | toString xcapDim);
            print("    DEGREE: " | toString degree satLoc);
            if xcapDim == 0 then (
                -- 0-dim: count using same formula as before
                print("    X_CAP_STRATUM_POINTS_COUNTED: 0d");
            ) else (
                print("    X_CAP_STRATUM_POINTS_COUNTED: positive_dim_SKIP");
            );
        );
    );
);

-- Singular lines: original pairwise enumeration kept for backward compatibility
print "SINGULAR_LINES:";
for i from 0 to n-2 do (
    for j from i+1 to n-1 do (
        isotropy = gcd(weights#i, weights#j);
        if isotropy > 1 then (
            -- Determine whether this pair lives in a LARGER stratum with same isotropy.
            -- Find any third index k with isotropy | weights#k.
            inLargerStratum = false;
            for k from 0 to n-1 do (
                if k != i and k != j and (weights#k % isotropy == 0) then (
                    inLargerStratum = true;
                    break;
                );
            );
            -- substitute zero for all but i, j
            subList = apply(n, k -> if k == i or k == j then S_k else 0_S);
            eqnsLoc = apply(eqns, f -> sub(f, apply(n, k -> S_k => subList#k)));
            nzList = select(eqnsLoc, f -> f != 0);
            nNZ = length nzList;
            nEq = length eqns;
            print("  Pair (" | toString i | "," | toString j | ") isotropy " | toString isotropy | " in_larger=" | toString inLargerStratum | ":");
            print("    eqn_count_active: " | toString nNZ | " of " | toString nEq);
            -- Endpoint detection: is the coord-point P_i (resp. P_j) on X? Endpoints have
            -- FULL stabilizer mu_(w_i) (resp. mu_(w_j)), which is generally larger than the
            -- generic line stabilizer mu_(gcd). They must be counted separately.
            endptIVals = apply(eqns, f -> sub(f, apply(n, k -> S_k => if k == i then 1_S else 0_S)));
            onEi = all(endptIVals, v -> v == 0);
            endptJVals = apply(eqns, f -> sub(f, apply(n, k -> S_k => if k == j then 1_S else 0_S)));
            onEj = all(endptJVals, v -> v == 0);
            print("    ENDPOINT_I_ON_X: " | toString onEi);
            print("    ENDPOINT_J_ON_X: " | toString onEj);
            if nNZ == 0 then (
                print("    CONTAINS_LINE: true");
            ) else (
                yname = apply(2, k -> getSymbol("y" | toString k));
                Sloc = (ZZ/p)(monoid[yname, Degrees => {{weights#i, weights#j}}]);
                phi = map(Sloc, S, apply(n, k -> (
                    if k == i then Sloc_0
                    else if k == j then Sloc_1
                    else 0_Sloc
                )));
                eqnsLocLoc = apply(eqns, f -> phi f);
                eqnsLocNZ = select(eqnsLocLoc, f -> f != 0);
                Iloc = ideal eqnsLocNZ;
                satLoc = saturate(Iloc, ideal vars Sloc);
                if satLoc == ideal 1_Sloc then (
                    print("    POINTS: 0 (empty common zero set)");
                ) else (
                    PD = primaryDecomposition satLoc;
                    nPD = length PD;
                    print("    POINTS: " | toString nPD);
                    print("    DEGREE: " | toString degree satLoc);
                    -- Generic-line points: exclude endpoint components (those containing y_0 or y_1)
                    -- by saturating against y_0 * y_1.
                    genIdeal = saturate(satLoc, ideal(Sloc_0 * Sloc_1));
                    if genIdeal == ideal 1_Sloc then (
                        print("    GENERIC_LINE_DEGREE: 0");
                    ) else (
                        print("    GENERIC_LINE_DEGREE: " | toString degree genIdeal);
                    );
                );
            );
        );
    );
);

print "DONE";
"""

def _format_weights(weights):
    return ", ".join(str(w) for w in weights)

def _format_eqns(eqns):
    # JSON-ize as a list of M2 strings
    parts = []
    for e in eqns:
        # Strip enclosing quotes if present; escape internal quotes
        s = e.replace('\\', '\\\\').replace('"', '\\"')
        parts.append(f'"{s}"')
    return "{" + ", ".join(parts) + "}"


def _run_m2(script_text, timeout=120):
    """Write script to tempfile, run M2, return (stdout, stderr, returncode).
    Uses Popen + explicit kill to dodge subprocess.run hanging on macOS."""
    import signal
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m2", delete=False, dir="/tmp") as tf:
        tf.write(script_text)
        tf.flush()
        path = tf.name
    out_path = path + ".out"
    err_path = path + ".err"
    try:
        with open(out_path, "w") as fout, open(err_path, "w") as ferr:
            proc = subprocess.Popen(
                ["M2", "--script", path],
                stdout=fout, stderr=ferr,
                start_new_session=True,
            )
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except Exception: pass
            try: proc.kill()
            except Exception: pass
            rc = -1
        out = ""
        err = ""
        if os.path.exists(out_path):
            with open(out_path, "r") as f: out = f.read()
        if os.path.exists(err_path):
            with open(err_path, "r") as f: err = f.read()
        if rc == -1:
            err = "TIMEOUT after " + str(timeout) + "s\n" + err
        return out, err, rc
    finally:
        for p in (path, out_path, err_path):
            try: os.unlink(p)
            except: pass


def _parse_m2_output(out):
    """Parse the structured output of m2_verify_v2.m2."""
    info = {
        "raw": out,
        "homog": None, "tame": None, "well_formed": None, "fano_index": None,
        "quasi_smooth": None, "sing_cone_dim": None, "sing_cone_gens": None,
        "degrees": [],
        "coord_pts_on_X": [],
        "singular_lines": [],
        "contains_line": False,
        "max_isotropy_strata": [],
        "contains_stratum": False,
        "x_meets_stratum_pos_dim": False,
        "eqns_parsed": [],
        "linear_elim": False, "linear_elim_var": None, "linear_elim_coef": None,
    }
    lines = out.splitlines()
    i = 0
    cur_line_pair = None
    cur_stratum = None
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("HOM_OK:"): info["homog"] = (ln.split(":")[1].strip() == "true")
        elif ln.startswith("DEG:"): info["degrees"].append(int(ln.split(":")[1].strip()))
        elif ln.startswith("TAME:"): info["tame"] = (ln.split(":")[1].strip() == "true")
        elif ln.startswith("WELL_FORMED:"): info["well_formed"] = (ln.split(":")[1].strip() == "true")
        elif ln.startswith("FANO_INDEX:"): info["fano_index"] = int(ln.split(":")[1].strip())
        elif ln.startswith("LINEAR_ELIM:"): info["linear_elim"] = (ln.split(":")[1].strip() == "true")
        elif ln.startswith("LINEAR_ELIM_VAR:"):
            try: info["linear_elim_var"] = int(ln.split(":")[1].strip())
            except: pass
        elif ln.startswith("LINEAR_ELIM_COEF:"): info["linear_elim_coef"] = ln.split(":", 1)[1].strip()
        elif ln.startswith("QUASI_SMOOTH:"): info["quasi_smooth"] = (ln.split(":")[1].strip() == "true")
        elif ln.startswith("SING_CONE_DIM:"): info["sing_cone_dim"] = int(ln.split(":")[1].strip())
        elif ln.startswith("SING_CONE_GENS:"): info["sing_cone_gens"] = ln.split(":",1)[1].strip()
        elif "P_" in ln and "ON_X" in ln:
            m = re.search(r"P_(\d+)\s*\(wt\s*(\d+)\):", ln)
            if m:
                info["coord_pts_on_X"].append({"index": int(m.group(1)), "weight": int(m.group(2))})
        elif ln.startswith("Prime ") and "stratum dim" in ln:
            # e.g. "Prime 5: indices {2, 3, 4} (stratum dim 2):"
            m = re.search(r"Prime\s+(\d+):\s+indices\s+\{([\d,\s]+)\}\s+\(stratum dim\s+(\d+)\)", ln)
            if m:
                idxs = [int(x.strip()) for x in m.group(2).split(",") if x.strip()]
                cur_stratum = {
                    "prime": int(m.group(1)),
                    "indices": idxs,
                    "stratum_dim": int(m.group(3)),
                    "x_cap_dim": None,
                    "contains_stratum": False,
                }
                info["max_isotropy_strata"].append(cur_stratum)
                cur_line_pair = None
        elif "CONTAINS_STRATUM: true" in ln and cur_stratum:
            cur_stratum["contains_stratum"] = True
            info["contains_stratum"] = True
        elif "X_CAP_STRATUM_DIM:" in ln and cur_stratum:
            rhs = ln.split(":", 1)[1].strip()
            if rhs == "empty":
                cur_stratum["x_cap_dim"] = -1
            else:
                try: cur_stratum["x_cap_dim"] = int(rhs)
                except: cur_stratum["x_cap_dim"] = None
            if cur_stratum.get("x_cap_dim", -1) is not None and cur_stratum["x_cap_dim"] > 0:
                info["x_meets_stratum_pos_dim"] = True
        elif "Pair (" in ln:
            m = re.search(r"Pair\s*\((\d+),(\d+)\)\s*isotropy\s*(\d+)(?:\s*in_larger=(\w+))?", ln)
            if m:
                in_larger = (m.group(4) == "true") if m.group(4) else False
                cur_line_pair = {"i": int(m.group(1)), "j": int(m.group(2)),
                                 "isotropy": int(m.group(3)),
                                 "in_larger_stratum": in_larger,
                                 "points": None, "contains_line": False, "active_eqns": None,
                                 "endpoint_i_on_X": False, "endpoint_j_on_X": False,
                                 "generic_line_degree": None}
                info["singular_lines"].append(cur_line_pair)
                cur_stratum = None
        elif "eqn_count_active:" in ln and cur_line_pair:
            m = re.search(r"(\d+)\s+of\s+(\d+)", ln)
            if m: cur_line_pair["active_eqns"] = (int(m.group(1)), int(m.group(2)))
        elif "ENDPOINT_I_ON_X:" in ln and cur_line_pair:
            cur_line_pair["endpoint_i_on_X"] = (ln.split(":", 1)[1].strip() == "true")
        elif "ENDPOINT_J_ON_X:" in ln and cur_line_pair:
            cur_line_pair["endpoint_j_on_X"] = (ln.split(":", 1)[1].strip() == "true")
        elif "GENERIC_LINE_DEGREE:" in ln and cur_line_pair:
            m = re.search(r"GENERIC_LINE_DEGREE:\s*(\d+)", ln)
            if m: cur_line_pair["generic_line_degree"] = int(m.group(1))
        elif "CONTAINS_LINE: true" in ln and cur_line_pair:
            cur_line_pair["contains_line"] = True
            info["contains_line"] = True
        elif "POINTS:" in ln and cur_line_pair:
            m = re.search(r"POINTS:\s*(\d+)", ln)
            if m: cur_line_pair["pd_components"] = int(m.group(1))
            if "empty" in ln: cur_line_pair["points"] = 0
        elif "DEGREE:" in ln and cur_line_pair:
            m = re.search(r"DEGREE:\s*(\d+)", ln)
            if m:
                affdeg = int(m.group(1))
                g = cur_line_pair.get("isotropy", 1)
                n_active = cur_line_pair.get("active_eqns", (1, 1))[0]
                if n_active == 1:
                    cur_line_pair["points"] = affdeg // g if g else affdeg
                else:
                    cur_line_pair["points"] = affdeg
                cur_line_pair["affine_degree"] = affdeg
        i += 1
    return info


def _hj_chain(k, q):
    """Hirzebruch-Jung continued fraction of k/q (k > q >= 1, gcd(k,q)=1).
    Returns list of integers >= 2.
    For 1/k(1, q): k/q = b_1 - 1/(b_2 - 1/(... - 1/b_r))."""
    if q == 0: return []
    chain = []
    while True:
        a = -(-k // q)  # ceil(k/q)
        chain.append(a)
        new_k, new_q = q, a*q - k
        if new_q == 0: break
        k, q = new_k, new_q
        if len(chain) > 50: break  # safety
    return chain


def _k2_correction(k, q):
    """K^2 correction for cyclic quotient singularity 1/k(1, q).
    For Du Val A_n = 1/(n+1)(1, n): correction = 0 (crepant).
    For 1/k(1, 1): correction = (k-2)^2 / k.
    For general 1/k(1, q): use HJ chain formula (rough approximation for non-Du-Val)."""
    if q == k - 1:
        return 0  # A_{k-1}, Du Val, crepant
    if q == 1:
        return (k - 2) ** 2 / k
    # General — for our common cases this is sufficient.
    # The exact formula involves discrepancies; for unknown q we approximate.
    chain = _hj_chain(k, q)
    if not chain: return 0
    return sum((b - 2) for b in chain)  # rough; for Du Val (all b=2) this gives 0; for [k] gives k-2


def _singularity_type_at_line(weights, i, j):
    """For singular line L_{ij} (gcd k = gcd(w_i, w_j)) in a 4-var weighted hypersurface,
    determine the cyclic quotient type 1/k(a, b) at a generic point on L_{ij} ∩ X.

    Heuristic: tangent of X at the conic point is spanned by the OTHER two coords
    (indices not in {i, j}), with mu_k weights (w_a mod k, w_b mod k) where {a,b} = others.
    """
    n = len(weights)
    if n != 4:
        return {"unknown": True, "reason": f"only hypersurface case (n=4) supported; got n={n}"}
    k = gcd(weights[i], weights[j])
    if k <= 1: return {"type": "smooth", "k": k}
    others = [l for l in range(n) if l != i and l != j]
    if len(others) != 2:
        return {"unknown": True}
    w_a, w_b = weights[others[0]], weights[others[1]]
    a, b = w_a % k, w_b % k
    if a == 0 and b == 0:
        return {"type": "trivial", "k": k}
    if a == 0 or b == 0:
        return {"type": "pseudoreflection", "k": k, "weights": (a, b)}
    # Standardize: 1/k(a, b) = 1/k(1, c) where c = b * a^{-1} mod k.
    try:
        a_inv = pow(a, -1, k)
    except Exception:
        return {"unknown": True, "reason": f"no modular inverse for {a} mod {k}"}
    c = (b * a_inv) % k
    chain = _hj_chain(k, c)
    correction = _k2_correction(k, c)
    return {
        "type": f"1/{k}(1,{c})",
        "k": k, "c": c,
        "hj_chain": chain,
        "chain_length": len(chain),
        "k2_correction": correction,
        "is_du_val_An": (c == k - 1),
    }


def _picard_rank_check(weights, eqns, info, has_pseudoreflection_risk):
    """Compute ρ(X) for a weighted hypersurface (or CI) and return result.
    Currently best for hypersurface case (n=4)."""
    n = len(weights)
    n_eqns = len(eqns)
    sum_w = sum(weights)
    sum_d = sum(info.get("degrees") or [])
    prod_w = reduce(lambda x, y: x*y, weights, 1)

    out = {"ok": False, "rho_X": None, "detail": ""}

    if has_pseudoreflection_risk:
        out["detail"] = "Pseudoreflection risk -- skip ρ check (would need adversary-style local analysis)."
        return out

    if n_eqns == 1 and n == 4:
        # Hypersurface in 4-var ambient.
        a = sum_w - sum_d
        d = info["degrees"][0]
        if a <= 0:
            out["detail"] = "Not Fano."
            return out
        K_X_sq = (a ** 2) * d / prod_w  # for surface in P^3-like, K_X^2 = a^{n-2} d / prod_w; here n=4 so a^2 d / prod
        out["K_X_sq"] = K_X_sq

        # Iterate over singular lines in info to get singularity types.
        total_R = 0
        total_correction = 0.0
        types_list = []
        for L in info.get("singular_lines", []):
            i, j = L["i"], L["j"]
            n_geom = L.get("points") or 0
            if n_geom == 0: continue
            sigType = _singularity_type_at_line(weights, i, j)
            types_list.append({"line": (i, j), "n_points": n_geom, **sigType})
            if sigType.get("type") in ("smooth", "trivial", "pseudoreflection"):
                continue  # not contributing to R or correction
            cl = sigType.get("chain_length", 1)
            cor = sigType.get("k2_correction", 0)
            total_R += n_geom * cl
            total_correction += n_geom * cor

        # Coordinate points isolated (mu_k singletons not on any line)
        # For now, assume each isolated coord point has chain length 1 and correction (k-2)^2/k
        for cp in info.get("coord_pts_on_X", []):
            k0 = cp["index"]
            wk = weights[k0]
            in_line = any(j != k0 and gcd(weights[j], wk) > 1 for j in range(n))
            if in_line: continue
            # Isolated; assume type 1/wk(1, 1) heuristically.
            types_list.append({"coord_pt": k0, "type": f"1/{wk}(1,1)_assumed", "chain_length": 1,
                               "k2_correction": (wk-2)**2 / wk if wk > 1 else 0})
            total_R += 1
            total_correction += (wk-2)**2 / wk if wk > 1 else 0

        K_res_sq = K_X_sq - total_correction
        rho_res = 10 - K_res_sq  # assuming smooth rational surface
        rho_X = rho_res - total_R

        out["ok"] = True
        out["sing_types"] = types_list
        out["K_X_sq"] = K_X_sq
        out["total_correction"] = total_correction
        out["K_res_sq"] = K_res_sq
        out["rho_X_res"] = rho_res
        out["R_total"] = total_R
        out["rho_X"] = rho_X
        out["detail"] = (f"K_X^2={K_X_sq:.4f}, corr={total_correction:.4f}, K_res^2={K_res_sq:.4f}, "
                        f"ρ(X_res)={rho_res:.2f}, R={total_R}, ρ(X) = ρ(X_res) - R = {rho_X:.2f}")
        return out

    if n_eqns == 2 and n == 5:
        # CI of 2 in 5-var; K_X^2 formula: K_X^2 = a^{n-2-1}? not exactly.
        # Skip ρ computation for CI case (complex); return ok=False.
        out["detail"] = "CI case (n_eqns=2, n=5) — ρ check not implemented."
        return out

    out["detail"] = f"Unsupported case (n={n}, n_eqns={n_eqns}) for ρ check."
    return out


def _all_subsets_with_isotropy(weights):
    """All subsets of indices with gcd of weights > 1, by length."""
    from itertools import combinations
    n = len(weights)
    out = []
    for k in range(1, n):
        for combo in combinations(range(n), k):
            sub = [weights[i] for i in combo]
            g = reduce(gcd, sub)
            if g > 1:
                out.append((combo, g))
    return out


def verify_method_b(weights, eqns, n_sing_required, char_p=3, timeout=180):
    """Verify a Method B candidate. Returns dict with score, verdict, details."""
    # Quick syntactic sanity
    if not isinstance(weights, list) or not weights or not isinstance(eqns, list) or not eqns:
        return {"score": 0, "verdict": "FAIL", "reason": "Missing weights or equations", "info": {}}

    script = M2_SCRIPT_TEMPLATE.format(
        p=char_p,
        weights=_format_weights(weights),
        eqns_list=_format_eqns(eqns)
    )
    stdout, stderr, rc = _run_m2(script, timeout=timeout)

    info = _parse_m2_output(stdout)

    # Compute score from parsed info
    out = {
        "weights": weights,
        "eqns": eqns,
        "n_sing_required": n_sing_required,
        "info": info,
        "m2_stderr": stderr[:2000] if stderr else "",
    }

    # If M2 errored out, mark as parse failure
    if "error" in (stderr or "").lower() and not info.get("homog"):
        out["score"] = 0
        out["verdict"] = "FAIL"
        out["reason"] = "M2 parse error: " + (stderr[:300] if stderr else "unknown")
        return out

    # Step through scoring criteria
    if info["homog"] is False:
        out["score"] = 0; out["verdict"] = "FAIL"; out["reason"] = "Not weight-homogeneous"
        return out
    if info["homog"] is None:
        out["score"] = 0; out["verdict"] = "FAIL"; out["reason"] = "Parse failure or empty equations"
        return out

    if info["tame"] is False:
        out["score"] = 1; out["verdict"] = "FAIL"; out["reason"] = f"Tameness fail: weight divisible by {char_p}"
        return out

    if info["well_formed"] is False:
        out["score"] = 1; out["verdict"] = "FAIL"; out["reason"] = "Not well-formed (gcd of some n-1 weights > 1)"
        return out

    if info["fano_index"] is not None and info["fano_index"] <= 0:
        out["score"] = 1; out["verdict"] = "FAIL"; out["reason"] = f"Fano index = {info['fano_index']}, need > 0"
        return out

    # Dimension check: X must be a SURFACE.
    # Ambient P(w) has dim = n - 1; surface = codim 2, so #eqns must equal n - 1 - 2 = n - 3.
    n_vars = len(weights)
    expected_codim = n_vars - 1 - 2
    n_eqns = len(eqns)
    if n_eqns != expected_codim:
        out["score"] = 1; out["verdict"] = "FAIL"
        out["reason"] = (f"Codim mismatch: ambient P(w) has dim {n_vars - 1}, "
                         f"need {expected_codim} equation(s) for a surface; got {n_eqns}. "
                         f"X is dim {n_vars - 1 - n_eqns}, not a surface.")
        return out

    # Linear-elimination collapse (hypersurface case).
    # If F = c * x_i + g(others) with c a nonzero constant, then X ≅ P(weights \ {w_i})
    # as a weighted projective plane. Singular points of X are the coord pts of
    # the reduced ambient with weight > 1, and ρ(X) = 1 always for P(w).
    # This catches the round-3 deepseek seed=44 false positive (P(2,1,1,14), F = x_3 + g).
    if info.get("linear_elim") and n_eqns == 1 and info.get("linear_elim_var") is not None:
        elim_var = info["linear_elim_var"]
        reduced_weights = [weights[k] for k in range(n_vars) if k != elim_var]
        # Reduced ambient must still be a surface (i.e., 3 remaining weights for a 2-dim P).
        if len(reduced_weights) - 1 != 2:
            out["score"] = 1; out["verdict"] = "FAIL"
            out["reason"] = (f"Linear-elim collapse: x_{elim_var} eliminable, but reduced ambient "
                             f"P{tuple(reduced_weights)} has dim {len(reduced_weights) - 1} != 2.")
            return out
        # Reduced ambient must be well-formed (gcd of any (k-1) of k weights = 1).
        n_red = len(reduced_weights)
        wf_red = True
        for ir in range(n_red):
            sub_w = [reduced_weights[k] for k in range(n_red) if k != ir]
            if reduce(gcd, sub_w) > 1:
                wf_red = False; break
        if not wf_red:
            out["score"] = 1; out["verdict"] = "FAIL"
            out["reason"] = (f"Linear-elim collapse: X ≅ P{tuple(reduced_weights)} is not well-formed.")
            return out
        # Coord-point singularities of P(reduced_weights): one per weight > 1.
        sing_after = sum(1 for w in reduced_weights if w > 1)
        out["linear_elim_applied"] = True
        out["sing_count"] = sing_after
        out["rho_X"] = 1
        out["linear_elim_detail"] = (
            f"F is linear in x_{elim_var} with constant coefficient ({info.get('linear_elim_coef')}). "
            f"After eliminating x_{elim_var}: X ≅ P({','.join(str(w) for w in reduced_weights)}), "
            f"a weighted projective plane. Singularities are at coord points with weight > 1 "
            f"(count = {sing_after}). ρ(X) = 1 automatically. The naive line-count in the "
            f"original P(w) ambient over-counts these points by a factor of (deg F / gcd)."
        )
        if sing_after >= n_sing_required:
            out["score"] = 7; out["verdict"] = "PASS"
            out["reason"] = (f"Linear-elim case: X ≅ P({reduced_weights}) has {sing_after} "
                             f">= {n_sing_required} klt sings, ρ=1 verified.")
        elif sing_after == n_sing_required - 1:
            out["score"] = 6; out["verdict"] = "FAIL"
            out["reason"] = (f"Linear-elim case: X ≅ P({reduced_weights}) has {sing_after} "
                             f"sings — ONE SHORT of {n_sing_required}.")
        else:
            out["score"] = 5 if sing_after >= 1 else 3
            out["verdict"] = "FAIL"
            out["reason"] = (f"Linear-elim case: X ≅ P({reduced_weights}) has only {sing_after} "
                             f"sings, < {n_sing_required}.")
        return out

    # Now check for X containing a singular line (worst case)
    if info["contains_line"] or info.get("contains_stratum"):
        out["score"] = 2; out["verdict"] = "FAIL"; out["reason"] = "X contains a singular stratum (non-isolated singularities)"
        return out

    # NEW: detect cases where X meets a higher-dim isotropy stratum in a positive-dim subscheme.
    # Such curves/surfaces of stratum-points are typically smoothed by pseudoreflection in the
    # coarse projective surface. We CONSERVATIVELY refuse to credit any singular-point count
    # from sub-strata in this case, since the adversary showed (V2 retraction) that pairwise
    # lines counted under a larger 2-dim mu_p stratum may all live on a curve where the local
    # cyclic action acts as a pseudoreflection — hence smooth.
    pseudoreflection_risk_primes = set()
    for strat in info.get("max_isotropy_strata", []):
        xcd = strat.get("x_cap_dim")
        sd = strat.get("stratum_dim", 0)
        if xcd is not None and xcd >= 1 and sd >= 2:
            pseudoreflection_risk_primes.add(strat["prime"])

    if pseudoreflection_risk_primes:
        # FLAG: pairwise lines under these primes are likely smooth in coarse X. Skip their counts.
        out["pseudoreflection_risk_primes"] = sorted(pseudoreflection_risk_primes)

    # Count singular points: sum over singular lines (GENERIC-LINE points only, excluding
    # endpoints) + COORD pts on X (endpoints get full mu_{w_k} stabilizer counted here).
    # The endpoint-stabilizer fix: when a coord point P_k is also on a singular line, it has
    # FULL stabilizer mu_{w_k}, not the smaller line-stratum mu_{gcd}. Count it once as a
    # coord-pt with full type, and exclude its endpoint component from the line count.
    line_pts = 0
    line_pts_excluded = 0
    n = len(weights)
    for L in info["singular_lines"]:
        iso = L.get("isotropy", 1)
        # Prefer generic_line_degree (endpoints excluded) when available; fall back to old count.
        gen_deg = L.get("generic_line_degree")
        if gen_deg is not None:
            n_active = (L.get("active_eqns") or (1, 1))[0]
            if n_active == 1:
                pts = gen_deg // iso if iso else gen_deg
            else:
                pts = gen_deg
            L["generic_line_pts"] = pts
        else:
            pts = L.get("points", 0) or 0
        skip = False
        for q in pseudoreflection_risk_primes:
            if iso % q == 0:
                skip = True
                break
        if skip:
            line_pts_excluded += pts
        else:
            line_pts += pts

    # Coord points on X: count all with weight > 1 (including endpoints of singular lines,
    # since those now carry full mu_{w_k} stabilizer rather than mu_{gcd}). Skip ones whose
    # weight is divisible by a pseudoreflection-risk prime.
    isolated_coord_pts = 0
    for cp in info.get("coord_pts_on_X", []):
        k = cp["index"]
        wk = weights[k]
        if wk <= 1: continue
        skip_cp = any(wk % q == 0 for q in pseudoreflection_risk_primes)
        if not skip_cp:
            isolated_coord_pts += 1

    coord_pts = isolated_coord_pts
    total_sing = line_pts + coord_pts
    out["sing_count"] = total_sing
    out["sing_breakdown"] = {
        "line_pts": line_pts, "coord_pts": coord_pts,
        "line_pts_excluded_pseudoreflection_risk": line_pts_excluded,
    }

    # ------------------------------------------------------------------
    # Picard-rank check.  For each singular point P on X (from line strata),
    # compute the local cyclic quotient type 1/k(a, b) and the HJ chain.
    # Aggregate: ρ(X) = ρ(X_res) - R where R = sum of HJ chain lengths.
    # For X_res a smooth rational surface, ρ(X_res) = 10 - K_res^2.
    # K_res^2 = K_X^2 - sum_of_corrections.  K_X^2 = a^(n-2) * d / prod(w) for hypersurface
    # in n-var ambient with degree d, a = sum_w - d.  (For CI, more complex; we approximate.)
    # ------------------------------------------------------------------
    rho_check = _picard_rank_check(weights, eqns, info, line_pts_excluded > 0)
    out["picard_check"] = rho_check
    out["rho_X"] = rho_check.get("rho_X")

    rho_verified_eq_1 = (
        rho_check.get("ok")
        and rho_check.get("rho_X") is not None
        and rho_check["rho_X"] == 1
    )
    rho_verified_ne_1 = (
        rho_check.get("ok")
        and rho_check.get("rho_X") is not None
        and rho_check["rho_X"] != 1
    )

    if rho_verified_ne_1 and total_sing >= n_sing_required and info["quasi_smooth"]:
        out["score"] = 5; out["verdict"] = "FAIL"
        out["reason"] = (f"Quasi-smooth, count OK ({total_sing}>={n_sing_required}), "
                         f"BUT ρ(X) = {rho_check['rho_X']} != 1. {rho_check.get('detail','')}")
        return out

    if info["quasi_smooth"]:
        if total_sing >= n_sing_required:
            if rho_verified_eq_1:
                out["score"] = 7; out["verdict"] = "PASS"
                out["reason"] = (f"PASS — quasi-smooth with {total_sing} singular points "
                                 f">= {n_sing_required}, ρ(X) = 1 verified.")
            else:
                # Would-be PASS, but ρ check inconclusive. Don't auto-accept; flag for escalation.
                out["score"] = 6; out["verdict"] = "PICARD_UNKNOWN"
                out["reason"] = (f"Quasi-smooth, count OK ({total_sing}>={n_sing_required}), "
                                 f"but ρ check inconclusive: {rho_check.get('detail','no detail')}. "
                                 f"NEEDS ESCALATION — independent ρ(X) = 1 proof required.")
        elif total_sing == n_sing_required - 1:
            out["score"] = 6; out["verdict"] = "FAIL"
            out["reason"] = f"Quasi-smooth but ONE SHORT ({total_sing} of {n_sing_required})"
        else:
            out["score"] = 5; out["verdict"] = "FAIL"
            out["reason"] = (f"Quasi-smooth but {n_sing_required - total_sing} singular points "
                             f"short ({total_sing} of {n_sing_required})")
    else:
        # cone has isolated singularities
        if total_sing >= n_sing_required:
            out["score"] = 4; out["verdict"] = "FAIL"
            out["reason"] = (f"Count OK ({total_sing}) but cone NOT quasi-smooth "
                             f"(additional singularities — klt status uncertain)")
        else:
            out["score"] = 3; out["verdict"] = "FAIL"
            out["reason"] = (f"Cone has isolated singularities AND count {total_sing} "
                             f"< {n_sing_required}")

    return out


def feedback_for_revision(result):
    """Generate human-readable feedback text for the model to use in revision."""
    info = result.get("info", {})
    lines = [
        f"## Macaulay2 Verifier Output",
        f"",
        f"Score: {result['score']}/7  ({result['verdict']})",
        f"Reason: {result['reason']}",
        f"",
        f"### Detailed checks:",
        f"- weight-homogeneous: {info.get('homog')}",
        f"- char-{result.get('weights') and 3 or '?'}-tame: {info.get('tame')}",
        f"- well-formed: {info.get('well_formed')}",
        f"- Fano index: {info.get('fano_index')}",
        f"- quasi-smooth (cone smooth off origin): {info.get('quasi_smooth')}",
    ]
    if info.get("sing_cone_dim") is not None:
        lines.append(f"- singular locus of cone: projective dim {info['sing_cone_dim']}")
        if info.get("sing_cone_gens"):
            lines.append(f"  generators of singular locus: {info['sing_cone_gens'][:300]}")
    if info.get("coord_pts_on_X"):
        lines.append(f"- coordinate points on X: {info['coord_pts_on_X']}")
    if info.get("singular_lines"):
        lines.append(f"- singular lines:")
        for L in info["singular_lines"]:
            note = f"contains_line={L['contains_line']}" if L["contains_line"] else f"points={L['points']}"
            lines.append(f"  pair ({L['i']},{L['j']}) isotropy {L['isotropy']}: {note}, active eqns {L.get('active_eqns')}")
    if result.get("sing_count") is not None:
        lines.append(f"- TOTAL singular points found: {result['sing_count']} (need >= {result['n_sing_required']})")
    return "\n".join(lines)


if __name__ == "__main__":
    # Self-test
    print("Test 1: warmup gemma seed=46 (should PASS with 7 points)")
    r = verify_method_b(weights=[2,2,5,5], eqns=["x0^5 + x1^5 + x2^2 + x3^2"], n_sing_required=7)
    print(f"  score={r['score']} verdict={r['verdict']} reason={r['reason']}")
    print(f"  sing_count={r.get('sing_count')} breakdown={r.get('sing_breakdown')}")
    print()
    print("Test 2: gpt-oss seed=42 (should FAIL — L_12 empty)")
    r = verify_method_b(weights=[1,2,2,5,5], eqns=[
        "x0^4 + x1^2 + x2^2 + x0^2*x1 + x0^2*x2",
        "x0^10 + x1^5 + x2^5 + x3^2 + x4^2"
    ], n_sing_required=8)
    print(f"  score={r['score']} verdict={r['verdict']} reason={r['reason']}")
    print(f"  sing_count={r.get('sing_count')}")
    print()
    print("Test 3: warmup looking for 8 (should be score 6 — quasi-smooth but ONE SHORT)")
    r = verify_method_b(weights=[2,2,5,5], eqns=["x0^5 + x1^5 + x2^2 + x3^2"], n_sing_required=8)
    print(f"  score={r['score']} verdict={r['verdict']} reason={r['reason']}")
    print()
    print("Test 4: deepseek seed=44 linear-elim false positive (should be score 5, NOT 6)")
    r = verify_method_b(weights=[2,1,1,14], eqns=["x3 + x0^7 + x1^14 + x2^14"], n_sing_required=8)
    print(f"  score={r['score']} verdict={r['verdict']} reason={r['reason']}")
    print(f"  sing_count={r.get('sing_count')} linear_elim_applied={r.get('linear_elim_applied')}")
