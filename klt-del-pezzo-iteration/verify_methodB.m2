-- Macaulay2 verification of Method B candidates (weighted hypersurface or CI)
-- Usage: M2 --script verify_methodB.m2  CANDIDATE_TAG  WEIGHTS  EQUATIONS  N_SING

-- Inputs are read from arguments below; this script is invoked once per candidate via the python driver.

needsPackage "WeightedProjectiveSpace" -- may or may not exist; use base ring otherwise

-- Helper: given char p, weight list w, and ring of weight d equations, check:
--   1. each equation is weight-homogeneous of declared degree
--   2. P(w) is well-formed (gcd of any n weights = 1 for ambient dim n)
--   3. weights coprime to p (tame)
--   4. the affine cone is smooth outside origin (quasi-smoothness)
--   5. count isolated singularities of X
checkCandidate = (p, weights, eqnsStr, declaredDegrees, NsingRequired) -> (
    print "=== Candidate ===";
    print ("char p = " | toString p);
    print ("weights = " | toString weights);
    print ("declaredDegrees = " | toString declaredDegrees);
    n := #weights;

    -- Build polynomial ring with weighted grading
    varNames := apply(n, i -> "x"|toString i);
    S := (ZZ/p)[varNames, Degrees=>weights];
    setupVars := apply(n, i -> (varNames#i) => S_(i));

    -- Parse equations from strings (use S's variables)
    eqns := apply(eqnsStr, e -> value e);
    print "Parsed equations:";
    apply(eqns, e -> print ("  " | toString e));

    -- Check (1): weight-homogeneity
    print "";
    print "Check 1: weight-homogeneity";
    homOK := true;
    for i from 0 to #eqns-1 do (
        f := eqns#i;
        d := declaredDegrees#i;
        if f == 0 then (print ("  eqn "|i|": ZERO — invalid"); homOK = false; continue);
        if isHomogeneous f then (
            -- get the degree from the polynomial
            deg := (degree f)#0;
            if deg == d then print ("  eqn "|i|": homogeneous of weighted degree "|toString deg|" ✓")
            else (print ("  eqn "|i|": homogeneous of degree "|toString deg|" but declared "|toString d|" ✗"); homOK = false)
        ) else (
            print ("  eqn "|i|": NOT weight-homogeneous ✗");
            homOK = false;
        )
    );
    if not homOK then (print "FAIL: not weight-homogeneous"; return false);

    -- Check (2): well-formedness — gcd of any (n-1) weights = 1 (since ambient dim = n-1 for P^{n-1})
    print "";
    print "Check 2: well-formed weighted projective space";
    wf := true;
    -- for each i, gcd of weights with index i dropped
    for i from 0 to n-1 do (
        wDropped := drop(weights, {i,i});
        g := gcd wDropped;
        if g > 1 then (print ("  drop x"|i|": gcd = "|toString g|" ✗"); wf = false)
    );
    if not wf then print "FAIL: not well-formed";

    -- Check (3): tameness (no weight divisible by char p)
    print "";
    print "Check 3: tameness (no weight divisible by char)";
    tame := all(weights, w -> w % p != 0);
    if tame then print "  ✓ all weights coprime to char"
    else (print ("  ✗ some weight divisible by "|toString p); print "FAIL: not tame"; return false);

    -- Check (4): quasi-smoothness via Jacobian
    -- Singular locus of the affine cone V(eqns) is V(eqns) ∩ V(Jacobian minors)
    -- For a CI of codim r, we want the Jacobian to have rank r everywhere on V(eqns) \ {0}
    print "";
    print "Check 4: quasi-smoothness (singular locus of affine cone)";
    I := ideal eqns;
    codim_expected := #eqns;
    J := jacobian I;
    -- Minors of size codim_expected
    Jminors := minors(codim_expected, J);
    sing := saturate(I + Jminors, ideal vars S);
    if sing == ideal(1_S) then (
        print "  ✓ affine cone smooth outside origin (quasi-smooth)";
    ) else (
        print "  ✗ singular locus of cone contains more than the origin";
        print ("  singular locus ideal: " | toString sing);
        -- show generators
        gens_sing := flatten entries gens sing;
        if #gens_sing < 20 then print ("  gens: " | toString gens_sing);
        -- check if singular locus is positive-dim
        if dim sing > 0 then print ("  WARNING: singular locus has dimension " | toString (dim sing));
        return false;
    );

    -- Check (5): count singular points of X (the quotient X = Proj(R/I) by mu_? actions)
    -- Singular points of X come from intersections with ambient singular strata
    print "";
    print "Check 5: counting singular points of X";
    -- For each subset of indices I_sub with |I_sub| >= 1, the stratum is
    -- the locus where x_i ≠ 0 iff i in I_sub. Isotropy = gcd of weights in I_sub.
    -- If isotropy > 1, the stratum is in ambient singular locus.
    -- We count the points of X on each such stratum.

    total := 0;
    subsetIxs := subsets(toList(0..n-1));
    for I_sub in subsetIxs do (
        if #I_sub == 0 then continue;
        if #I_sub == n then continue; -- full ambient is not a stratum
        sub_weights := weights_I_sub;
        isotropy := gcd sub_weights;
        if isotropy <= 1 then continue;
        -- Localize: set x_j = 0 for j not in I_sub
        substList := apply(toList(0..n-1), j -> if member(j, I_sub) then S_j => S_j else S_j => 0);
        eqns_loc := apply(eqns, f -> sub(f, substList));
        I_loc := ideal eqns_loc;
        -- Now look at V(I_loc) in the sub-projective space P(weights_{I_sub})
        -- Its dimension should be |I_sub| - 1 - #eqns (codim # eqns inside P(sub_weights))
        -- We count points: it's 0-dim iff |I_sub| - 1 - #eqns == 0, i.e., #I_sub == #eqns + 1
        -- Otherwise compute dim and (if 0) degree.
        Slocal_vars := apply(I_sub, i -> varNames#i);
        Slocal := (ZZ/p)[Slocal_vars, Degrees => sub_weights];
        Slocal_substList := apply(toList(0..n-1), j ->
            if member(j, I_sub) then S_j => Slocal_((position(I_sub, x -> x == j))) else S_j => 0
        );
        eqns_in_local := apply(eqns, f -> sub(f, Slocal_substList));
        I_local := ideal eqns_in_local;
        -- Check if any equation is identically zero
        nonzero_eqns := select(eqns_in_local, f -> f != 0);
        if #nonzero_eqns == 0 then (
            print ("  stratum " | toString I_sub | " (isotropy "|toString isotropy|"): X CONTAINS this whole stratum — BAD");
            return false;
        );
        if #nonzero_eqns < #eqns then (
            print ("  stratum " | toString I_sub | " (isotropy "|toString isotropy|"): "|toString(#eqns-#nonzero_eqns)|" eqn(s) vanish identically here — non-CI");
        );
        -- Form projective scheme
        try (
            J_local := ideal nonzero_eqns;
            dim_local := dim J_local - 1; -- Proj dimension
            if dim_local <= 0 then (
                deg_local := degree(J_local);
                print ("  stratum " | toString I_sub | " (isotropy "|toString isotropy|"): dim="|toString dim_local|", degree="|toString deg_local);
                total = total + deg_local;
            ) else (
                print ("  stratum " | toString I_sub | " (isotropy "|toString isotropy|"): dim "|toString dim_local|" (positive-dim singular locus) — BAD");
                return false;
            )
        ) else (print ("  stratum " | toString I_sub | ": error computing"));
    );
    print "";
    print ("Total singular points (counted with multiplicity from ambient strata): " | toString total);
    if total >= NsingRequired then (
        print ("VERDICT: PASSES count requirement >= " | toString NsingRequired);
        true
    ) else (
        print ("VERDICT: FAILS count requirement (got "|toString total|", need >="|toString NsingRequired|")");
        false
    )
);
