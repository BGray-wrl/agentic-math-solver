-- klt del Pezzo verifier (Method B: weighted hypersurface or CI).
-- Reads JSON-like input from environment variables and writes a result JSON to stdout.
-- Required env vars: KLT_WEIGHTS (e.g. "2,2,5,5"), KLT_EQNS (multiple lines, blank-line separated),
-- KLT_NSING (target number of singular points), KLT_CHAR (default 3).

needsPackage "JSON";

p = value (if getenv "KLT_CHAR" != "" then getenv "KLT_CHAR" else "3");
weightsStr = getenv "KLT_WEIGHTS";
eqnsStr    = getenv "KLT_EQNS";   -- multiple eqns separated by ";;"
NsingReq   = value (if getenv "KLT_NSING" != "" then getenv "KLT_NSING" else "8");

weights = value("{" | weightsStr | "}");
nVars = #weights;

-- Build varNames x0..x_{n-1}
varNames = apply(nVars, i -> getSymbol ("x" | toString i));
S = (ZZ/p)(monoid[varNames, Degrees => weights]);

-- Substitute the variables into a parsing environment so `value` works on eqn strings.
use S;

-- Parse equations
eqnList = separate(";;", eqnsStr);
eqnList = select(eqnList, e -> length e > 0);
eqns = apply(eqnList, e -> value e);

result = new MutableHashTable;
result#"weights" = weights;
result#"degrees" = apply(eqns, f -> if f == 0 then null else (degree f)#0);
result#"char" = p;
result#"n_sing_required" = NsingReq;
result#"n_eqns" = #eqns;
result#"trace" = {};
push = m -> result#"trace" = append(result#"trace", m);

-- Score: 0=parse fail, 7=full pass.
score := 0;
verdict := "FAIL";
failReason := "";

-- Check 1: weight-homogeneity
homOK := true;
for f in eqns do (
    if f == 0 then (homOK = false; failReason = "An equation is zero or unparseable.")
    else if not isHomogeneous f then (homOK = false; failReason = "Equation not weight-homogeneous: " | toString f)
);
push("hom_ok: " | toString homOK);
result#"weight_homogeneous" = homOK;

if not homOK then (
    result#"score" = 0;
    result#"verdict" = "FAIL";
    result#"reason" = failReason;
    print toJSON new HashTable from result;
    exit 0;
);
score = 1;

-- Check 2: tameness (all weights coprime to char p)
tame := all(weights, w -> w % p != 0);
result#"tame" = tame;
push("tame: " | toString tame);
if not tame then (
    result#"score" = 1;
    result#"verdict" = "FAIL";
    result#"reason" = "Some weight divisible by char " | toString p;
    print toJSON new HashTable from result;
    exit 0;
);

-- Check 3: well-formedness (gcd of any (n-1) weights = 1)
wf := true;
for i from 0 to nVars-1 do (
    wD := drop(weights, {i, i});
    if gcd wD > 1 then (wf = false; failReason = "Not well-formed: gcd after dropping index " | toString i | " = " | toString (gcd wD); break);
);
result#"well_formed" = wf;
push("well_formed: " | toString wf);
if not wf then (
    result#"score" = 1;
    result#"verdict" = "FAIL";
    result#"reason" = failReason;
    print toJSON new HashTable from result;
    exit 0;
);

-- Check 4: Fano index = sum(weights) - sum(degrees) > 0
sumW = sum weights;
sumD = sum apply(eqns, f -> (degree f)#0);
fanoIdx = sumW - sumD;
result#"fano_index" = fanoIdx;
push("fano_index: " | toString fanoIdx);
if fanoIdx <= 0 then (
    result#"score" = 1;
    result#"verdict" = "FAIL";
    result#"reason" = "Fano index = " | toString fanoIdx | ", need > 0 for Fano/del Pezzo";
    print toJSON new HashTable from result;
    exit 0;
);
score = 2;

-- Check 5: dimension of V(I) — for surface in dim-(n-1) ambient, codim = nEqns, so V(I) should be dim 2.
-- Ambient projective dim = n - 1. Surface dim = 2 means codim = (n-1) - 2 = n - 3.
-- So #eqns should equal n - 3 for a clean surface.
expectedCodim = nVars - 1 - 2;
if #eqns != expectedCodim then (
    push("WARNING: #eqns = " | toString #eqns | " but expected " | toString expectedCodim | " for surface in P^" | toString (nVars-1));
);

-- Check 6: cone singular locus
I = ideal eqns;
J = jacobian I;
codimEqns := #eqns;
Jminors = minors(codimEqns, J);
singCone = saturate(I + Jminors, ideal vars S);
isQuasiSmooth = (singCone == ideal(1_S));
result#"quasi_smooth" = isQuasiSmooth;
push("quasi_smooth: " | toString isQuasiSmooth);

singCount = -1;  -- will fill in below
singConeDim = -1;
if not isQuasiSmooth then (
    singConeDim = dim singCone - 1;  -- projective dim
    result#"sing_cone_proj_dim" = singConeDim;
    if singConeDim > 0 then (
        result#"score" = 2;
        result#"verdict" = "FAIL";
        result#"reason" = "Cone has positive-dim singular locus (proj dim " | toString singConeDim | "). Not klt.";
        print toJSON new HashTable from result;
        exit 0;
    );
    score = 3;  -- isolated cone singularity, may or may not be klt
);

-- Count singular points of X via strata intersection (only for Method B hypersurface/CI).
-- For each subset of indices I_sub with |I_sub| in [1, nVars-1] and gcd(weights_{I_sub}) > 1:
-- compute V(I) restricted to the stratum.
totalSing := 0;
strataDetails := {};

subsetIxs = subsets(toList(0..nVars-1));
for Isub in subsetIxs do (
    if #Isub == 0 or #Isub == nVars then continue;
    sw = weights_Isub;
    isotropy = gcd sw;
    if isotropy <= 1 then continue;
    if #Isub > 2 then (
        -- 2-dim+ singular stratum: any surface meeting it transversely is bad.
        -- We need to check whether the surface contains this stratum or just meets it.
        substList = apply(toList(0..nVars-1), j -> if member(j, Isub) then S_j => S_j else S_j => 0_S);
        eqns_loc = apply(eqns, f -> sub(f, substList));
        nonzero_eqns = select(eqns_loc, f -> f != 0);
        if #nonzero_eqns == 0 then (
            push("Stratum " | toString Isub | " (isotropy mu_" | toString isotropy | "): X contains entire stratum — BAD");
            result#"score" = 2;
            result#"verdict" = "FAIL";
            result#"reason" = "X contains a 2-dim singular stratum (X is non-isolated singular).";
            print toJSON new HashTable from result;
            exit 0;
        );
        continue;  -- 2-dim stratum touched transversely is fine (gives curve or finite set)
    );
    -- |Isub| == 1 (isolated coord point) or |Isub| == 2 (singular line)
    substList = apply(toList(0..nVars-1), j -> if member(j, Isub) then S_j => S_j else S_j => 0_S);
    eqns_loc = apply(eqns, f -> sub(f, substList));
    if #Isub == 1 then (
        -- single coord point: is it on X?
        Pcoord = apply(toList(0..nVars-1), j -> if j == Isub#0 then 1_S else 0_S);
        vals = apply(eqns, f -> sub(f, apply(toList(0..nVars-1), j -> S_j => Pcoord#j)));
        onX = all(vals, v -> v == 0);
        if onX then (
            push("Coord point at index " | toString Isub#0 | " (isotropy mu_" | toString isotropy | "): ON X");
            totalSing = totalSing + 1;
            strataDetails = append(strataDetails, ("coord_pt_" | toString Isub#0, 1));
        );
    );
    if #Isub == 2 then (
        -- Singular line P(w_i, w_j) ≅ P^1. Compute V(I|stratum).
        Slocal_vars = apply(Isub, k -> getSymbol("y" | toString k));
        Slocal = (ZZ/p)(monoid[Slocal_vars, Degrees => sw]);
        substLocal = apply(toList(0..nVars-1), j -> (
            pos = position(Isub, x -> x == j);
            if pos === null then S_j => 0_S else S_j => sub(Slocal_(pos), S)
        ));
        -- Build the local equations more carefully via direct ring map
        phi = map(Slocal, S, apply(toList(0..nVars-1), j -> (
            pos = position(Isub, x -> x == j);
            if pos === null then 0_Slocal else Slocal_pos
        )));
        local_eqns = apply(eqns, f -> phi f);
        -- Number of points on the singular line:
        -- Each equation of degree d (on P^1 with both weights = isotropy in the relevant case)
        -- has d / gcd(stratum_weights) effective degree.
        -- For gcd-equal strata (both weights = w), the "effective degree" of an eqn of weight d is d/w.
        if sw#0 == sw#1 then (
            -- P(w,w) ≅ P^1 after identifying coords. Count common zeros.
            -- Method: select non-zero local eqns and compute their common zero count on P^1.
            non_zero = select(local_eqns, f -> f != 0_Slocal);
            n_vanish = #local_eqns - #non_zero;
            if n_vanish > 0 then (
                push("Stratum " | toString Isub | ": " | toString n_vanish | " of " | toString #local_eqns | " equation(s) vanish identically — non-CI here");
                -- still try to count points using non-zero subset
                if #non_zero == 0 then (
                    push("All eqns vanish on stratum " | toString Isub | " — X contains the line. BAD.");
                    result#"score" = 2;
                    result#"verdict" = "FAIL";
                    result#"reason" = "X contains 1-dim singular line " | toString Isub | " — non-isolated.";
                    print toJSON new HashTable from result;
                    exit 0;
                );
            );
            -- For points, count distinct zeros over algebraic closure
            -- Use the dim 0 ideal saturation trick
            Iloc = ideal non_zero;
            satIloc = saturate(Iloc, ideal vars Slocal);
            if satIloc == ideal(1_Slocal) then (
                push("Stratum " | toString Isub | " (isotropy mu_" | toString isotropy | "): EMPTY common zero set over F_p-bar (likely!)");
                strataDetails = append(strataDetails, ("line_" | toString Isub, 0));
            ) else (
                -- Degree of saturated ideal as 0-dim scheme.
                d0 = if dim satIloc <= 1 then degree satIloc else -1;
                -- That's the AFFINE degree. To get PROJECTIVE point count on P^1 ≅ P(w,w),
                -- divide by the stratum weight (since each projective point has w affine cone preimages).
                if d0 >= 0 then (
                    nPts = d0 // (isotropy^(#local_eqns - n_vanish)); -- heuristic
                    -- Better: try to count primary decomposition components
                    PD = primaryDecomposition satIloc;
                    nPts_via_PD = #PD;
                    push("Stratum " | toString Isub | " (isotropy mu_" | toString isotropy | "): " | toString nPts_via_PD | " distinct singular points (PD components)");
                    totalSing = totalSing + nPts_via_PD;
                    strataDetails = append(strataDetails, ("line_" | toString Isub, nPts_via_PD));
                );
            );
        );
    );
);

result#"sing_count" = totalSing;
result#"strata_details" = strataDetails;
push("Total singular points: " | toString totalSing);

-- Final scoring
if isQuasiSmooth then (
    if totalSing >= NsingReq then (
        score = 7;
        verdict = "PASS";
        result#"reason" = "Cone quasi-smooth, " | toString totalSing | " singular points >= " | toString NsingReq | " required.";
    ) else if totalSing == NsingReq - 1 then (
        score = 6;
        verdict = "FAIL";
        result#"reason" = "Quasi-smooth but ONE singular point short: " | toString totalSing | " of " | toString NsingReq;
    ) else (
        score = 5;
        verdict = "FAIL";
        result#"reason" = "Quasi-smooth but " | toString (NsingReq - totalSing) | " singular points short of requirement.";
    );
) else (
    -- isolated cone singularities; check if all are Du Val by examining their local structure
    -- For now use simpler heuristic: count >= req with isolated cone sings means score 4.
    if totalSing >= NsingReq then (
        score = 4;
        verdict = "FAIL";
        result#"reason" = "Has sufficient singular points but cone is not quasi-smooth (additional non-quotient singularities possible).";
    ) else (
        score = 3;
        verdict = "FAIL";
        result#"reason" = "Cone has isolated singularities AND point count " | toString totalSing | " < " | toString NsingReq;
    );
);

result#"score" = score;
result#"verdict" = verdict;
print toJSON new HashTable from result;
exit 0;
