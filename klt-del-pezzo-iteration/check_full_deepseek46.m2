-- deepseek seed=46 candidate (full re-check)
-- weights [1,2,2,14], hypersurface degree 16
-- F = x1^8 - x2^8 + x3*x2 + x3*x0^2 + x0^16 + x0^14*x1
-- Required: klt del Pezzo with rho(X)=1 and >=8 singular points.

print "============================================";
print "deepseek seed=46: P(1,2,2,14), deg 16, char 3";
print "============================================";

p = 3;
weights = {1,2,2,14};
S = (ZZ/p)[x0,x1,x2,x3, Degrees=>weights];
F = x1^8 - x2^8 + x3*x2 + x3*x0^2 + x0^16 + x0^14*x1;
print ("F = " | toString F);
print ("isHomogeneous F = " | toString isHomogeneous F | " degree " | toString degree F);

-- Tameness: gcd(14, 3) = 1, so weights coprime to 3 ✓ (well, 14 = 2·7, not div by 3)
print ("char-3 tameness: " | toString all(weights, w -> w%3 != 0));

-- Well-formedness: ambient dim 3, need gcd of any 3 weights = 1
print "well-formedness:";
for i from 0 to 3 do (
    wD = drop(weights, {i,i});
    print ("  drop x" | toString i | ": gcd = " | toString (gcd wD));
);

-- Fano index = sum_weights - degree
print ("Fano index = " | toString (sum weights - 16) | " (need > 0 for Fano)");

-- Quasi-smoothness check
print "";
print "Quasi-smoothness of hypersurface:";
I = ideal F;
J = jacobian I;
print ("Jacobian: " | toString flatten entries J);
SingCone = saturate(I + ideal mingens(ideal flatten entries J), ideal vars S);
print ("Singular locus ideal: " | toString SingCone);
if SingCone == ideal(1_S) then (
    print "  ✓ quasi-smooth";
) else (
    d = dim SingCone;
    print ("  ✗ NOT quasi-smooth; Krull dim of singular locus = " | toString d);
    print "  Primary decomposition:";
    apply(decompose SingCone, P -> print ("    " | toString P));
);

-- Singular strata of P(1,2,2,14)
-- gcd(2,2)=2: line L12 = {x0=x3=0}
-- gcd(14,2)=2: but we already counted; the singular strata are subsets with gcd>1.
-- {x1}: weight 2, isolated point (1/2 sing)
-- {x2}: weight 2, isolated point
-- {x3}: weight 14, isolated point (1/14 sing)
-- {x1,x2}: weight (2,2), gcd 2, line L12
-- {x1,x3}: weight (2,14), gcd 2, line L13
-- {x2,x3}: weight (2,14), gcd 2, line L23

print "";
print "Strata count for X = V(F):";

-- L12: x0=x3=0
print "";
print "L12 = {x0=x3=0}, weights (2,2), isotropy gcd(2,2)=2:";
FL12 = sub(F, {x0=>0_S, x3=>0_S});
print ("  F|L12 = " | toString FL12);
-- weighted degree 16 on P(2,2) = 16/2 = 8 distinct points if separable
print ("  on P(2,2) the equation has effective degree 16/2 = 8");

-- L13: x0=x2=0
print "";
print "L13 = {x0=x2=0}, weights (2,14), isotropy gcd(2,14)=2:";
FL13 = sub(F, {x0=>0_S, x2=>0_S});
print ("  F|L13 = " | toString FL13);
-- weights (2,14): monomial x1^a x3^b with 2a + 14b = 16: (a,b) = (8,0), (1,1). So x1^8 and x3*x1.
-- But our F: at x0=x2=0, only terms with no x0, x2: x1^8 (yes), -x2^8 (no, x2=0), x3*x2 (no), x3*x0^2 (no), x0^16 (no), x0^14*x1 (no). So F|L13 = x1^8.
print ("  Solve x1^8 = 0 on P(2,14): only x1=0, giving the point (0:0:0:1).");

-- L23: x0=x1=0
print "";
print "L23 = {x0=x1=0}, weights (2,14), isotropy gcd(2,14)=2:";
FL23 = sub(F, {x0=>0_S, x1=>0_S});
print ("  F|L23 = " | toString FL23);

-- Coord points
print "";
print "Coord point lookup:";
print ("  P0 (x0 only, weight 1, smooth): F(1,0,0,0) = " | toString sub(F, {x0=>1_S, x1=>0_S, x2=>0_S, x3=>0_S}));
print ("  P1 (x1 only, weight 2): F(0,1,0,0) = " | toString sub(F, {x0=>0_S, x1=>1_S, x2=>0_S, x3=>0_S}));
print ("  P2 (x2 only, weight 2): F(0,0,1,0) = " | toString sub(F, {x0=>0_S, x1=>0_S, x2=>1_S, x3=>0_S}));
print ("  P3 (x3 only, weight 14): F(0,0,0,1) = " | toString sub(F, {x0=>0_S, x1=>0_S, x2=>0_S, x3=>1_S}));
