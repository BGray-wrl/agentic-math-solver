-- Candidate: gpt-oss-120b seed=42 full
-- P(1,2,2,5,5), CI of F1 (deg 4) and F2 (deg 10), char 3
--   F1 = x0^4 + x1^2 + x2^2 + x0^2*x1 + x0^2*x2
--   F2 = x0^10 + x1^5 + x2^5 + x3^2 + x4^2
-- Required: klt del Pezzo with rho(X)=1 and >=8 singular points.

print "============================================";
print "Candidate: P(1,2,2,5,5), CI of degrees (4,10), char 3";
print "============================================";

p = 3;
weights = {1,2,2,5,5};
S = (ZZ/p)[x0,x1,x2,x3,x4, Degrees=>weights];
F1 = x0^4 + x1^2 + x2^2 + x0^2*x1 + x0^2*x2;
F2 = x0^10 + x1^5 + x2^5 + x3^2 + x4^2;
print ("F1 = " | toString F1);
print ("F2 = " | toString F2);

-- Check 1: weight-homogeneity
print "";
print "Check 1: weight-homogeneity";
print ("F1 homogeneous: " | toString isHomogeneous F1 | ", degree: " | toString degree F1);
print ("F2 homogeneous: " | toString isHomogeneous F2 | ", degree: " | toString degree F2);

-- Check 2: char-3 tame
print "";
print "Check 2: char-3 tameness";
print ("all weights coprime to 3: " | toString all(weights, w -> w%3 != 0));

-- Check 3: well-formed P(1,2,2,5,5) — ambient dim 4, need gcd of any 4 weights = 1
print "";
print "Check 3: well-formedness (drop one, gcd of remaining 4 = 1)";
for i from 0 to 4 do (
    wD = drop(weights, {i,i});
    print ("  drop index " | toString i | ": gcd of " | toString wD | " = " | toString (gcd wD));
);

-- Check 4: quasi-smoothness of the CI's affine cone
-- For a CI of codim 2, the cone is smooth at a point iff Jacobian has rank 2 there.
print "";
print "Check 4: quasi-smoothness of CI (Jacobian rank 2 outside origin)";
I = ideal(F1, F2);
J = jacobian I;
print ("Jacobian matrix:");
print J;
-- Singular locus of cone = V(I) ∩ V(rank-2 minors)
M2x2minors = minors(2, J);
SingCone = saturate(I + M2x2minors, ideal vars S);
print ("Singular locus ideal (saturated): " | toString SingCone);
if SingCone == ideal(1_S) then (
    print "  ✓ affine cone smooth outside origin: CI is quasi-smooth";
) else (
    print "  ✗ CONE HAS SINGULARITIES OUTSIDE ORIGIN — not quasi-smooth as CI";
    print "  Dimension of singular locus: " | toString (dim SingCone - 1);
    -- Saturate by each variable to see the locus more clearly
    SingPrim = decompose SingCone;
    print "  Primary decomposition:";
    apply(SingPrim, P -> print ("    " | toString P));
);

-- Check 5: localize to each stratum and check intersection with X
print "";
print "Check 5: stratum intersections";

-- L12 stratum: x0=x3=x4=0, isotropy gcd(2,2)=2
print "";
print "Stratum L12 = {x0=x3=x4=0}, weights (2,2), isotropy mu_2:";
F1L12 = sub(F1, {x0=>0_S, x3=>0_S, x4=>0_S});
F2L12 = sub(F2, {x0=>0_S, x3=>0_S, x4=>0_S});
print ("  F1|L12 = " | toString F1L12);
print ("  F2|L12 = " | toString F2L12);
-- On L12, the ring is P(2,2), so weighted degree d means polynomial of "actual degree" d/2 on the underlying P^1.
S12 = (ZZ/p)[y1,y2, Degrees=>{2,2}];
F1L12loc = sub(F1L12, {x0=>0_S, x1=>S12_0, x2=>S12_1, x3=>0_S, x4=>0_S});
F2L12loc = sub(F2L12, {x0=>0_S, x1=>S12_0, x2=>S12_1, x3=>0_S, x4=>0_S});
print ("  F1|L12 on S12: " | toString F1L12loc);
print ("  F2|L12 on S12: " | toString F2L12loc);
print ("  weighted degree F1|L12: " | toString degree F1L12loc);
print ("  weighted degree F2|L12: " | toString degree F2L12loc);
-- Expect (d1/2) * (d2/2) = 2 * 5 = 10 points on L12, by Bezout in P(2,2) ≅ P^1.
-- Actual intersection:
IL12 = ideal(F1L12loc, F2L12loc);
print ("  Krull dim V(I_L12): " | toString dim IL12);

-- L34 stratum: x0=x1=x2=0, isotropy gcd(5,5)=5
print "";
print "Stratum L34 = {x0=x1=x2=0}, weights (5,5), isotropy mu_5:";
F1L34 = sub(F1, {x0=>0_S, x1=>0_S, x2=>0_S});
F2L34 = sub(F2, {x0=>0_S, x1=>0_S, x2=>0_S});
print ("  F1|L34 = " | toString F1L34 | "   (expected: 0 since deg 4 < weight 5)");
print ("  F2|L34 = " | toString F2L34);
if F1L34 == 0 then (
    print "  *** F1 vanishes identically on L34. This means the SCHEME-THEORETIC INTERSECTION X cap L34";
    print "      drops codim: cone of F1 contains lift(L34). At points of L34 cap V(F2),";
    print "      Jacobian of (F1, F2) has rank 1, not 2, so X is NOT a quasi-smooth CI there.";
);

-- Quasi-smoothness check at L34 ∩ X points specifically
print "";
print "  Computing Jacobian at a point of L34 ∩ X explicitly:";
-- Pick (0,0,0,1,t) with t^2 = -1 = 2 in F_3-bar (or just work in F_9)
-- We can check this symbolically: at any point with x0=x1=x2=0 and x3^2+x4^2=0,
-- evaluate gradient.
-- ∂F1/∂xi at (0,0,0,a,b): all zero (no x_3,x_4 in F1, and other vars vanish).
gradF1 = transpose jacobian matrix{{F1}};
gradF2 = transpose jacobian matrix{{F2}};
print ("    grad F1 = " | toString flatten entries gradF1);
print ("    grad F2 = " | toString flatten entries gradF2);
gradF1_at_L34 = sub(gradF1, {x0=>0_S, x1=>0_S, x2=>0_S});
gradF2_at_L34 = sub(gradF2, {x0=>0_S, x1=>0_S, x2=>0_S});
print ("    grad F1 |_{x0=x1=x2=0} = " | toString flatten entries gradF1_at_L34);
print ("    grad F2 |_{x0=x1=x2=0} = " | toString flatten entries gradF2_at_L34);

print "";
print "==================== Verdict ====================";
print "If SingCone above is NOT trivial, this is the proof: X is not a quasi-smooth CI";
print "  along L34. The 2 points on L34 are NOT clean isolated klt singularities of X.";
print "  Locally near each, X = V(F1, F2) has codim drop (F1 vanishes on a 1-dim subscheme of L34),";
print "  giving X a reducible / non-normal local structure, which is NOT klt del Pezzo.";
