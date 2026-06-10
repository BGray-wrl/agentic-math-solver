-- Candidate / near-miss:
--   X = V(F) in P(2,4,5,25), char 3
--   F = x0^15 + x0^13*x1 + x0*x1^7 + x2*x3
--
-- This script checks the algebraic conditions and the actual distinct
-- singular point count, avoiding the weighted-degree overcount used by the
-- earlier heuristic verifier.  It also records the Picard-number obstruction.

p = 3;
S = (ZZ/p)[x0, x1, x2, x3, Degrees=>{2,4,5,25}];
F = x0^15 + x0^13*x1 + x0*x1^7 + x2*x3;

print "=== Candidate X in P(2,4,5,25), char 3 ===";
print("F = " | toString F);

print "";
print "1. Basic weighted checks";
print("homogeneous: " | toString isHomogeneous F);
print("degree: " | toString (degree F)#0);
weights = {2,4,5,25};
print("tame in char 3: " | toString all(weights, w -> w % p != 0));
for i from 0 to 3 do (
    wD = drop(weights, {i,i});
    print("gcd after dropping index " | toString i | ": " | toString gcd wD);
);
print("Fano index sum(w)-deg(F): " | toString (sum weights - (degree F)#0));

print "";
print "2. Quasi-smoothness: affine cone smooth outside the origin";
I = ideal F;
J = ideal flatten entries jacobian I;
SingCone = saturate(I + J, ideal vars S);
print("saturated cone singular ideal: " | toString SingCone);
print("quasi-smooth: " | toString (SingCone == ideal 1_S));

print "";
print "3. Actual singular-point count";
print "The ambient singular strata meeting X are:";

-- L01 = P(2,4).  In the chart x0 != 0, set t=x1/x0^2.
-- F|L01 = x0^15 * (1 + t + t^7), plus the point x0=0.
R = (ZZ/p)[t];
g = t^7 + t + 1;
gp = diff(t, g);
print("L01, finite chart polynomial g(t) = " | toString g);
print("g'(t) = " | toString gp);
print("gcd(g,g') = " | toString gcd(g,gp));
print("finite roots on L01: 7 distinct; plus x0=0 gives P1");
print("L01 contributes 8 distinct points");

-- L23 = P(5,25). F restricts to x2*x3, so only the two coordinate points.
print("L23 restriction: x2*x3 = 0");
print("L23 contributes 2 distinct points: P2 and P3");
print("Total distinct ambient-quotient singular points on X: 8 + 2 = 10");

print "";
print "4. Local quotient types";
print "At the 7 finite L01 points, X is locally A^2/mu_2 since the roots are simple.";
print "At the endpoint P1 on L01, X is locally A^2/mu_4 with weights (1,1).";
print "At P2, local type is A^2/mu_5 with weights (2,4).";
print "At P3, local type is A^2/mu_25 with weights (2,4).";
print "All stabilizer orders are prime to char 3, so these are tame cyclic quotient singularities.";

print "";
print "5. Picard-number obstruction";
print "K_X^2 = (sum(w)-d)^2 * d/(product w) = 6^2 * 30/(2*4*5*25) = 27/25.";
print "Basket: 7*A1, [4], [3,2], [13,2].";
print "Discrepancy corrections C = 0, 1, 2/5, 242/25 respectively.";
print "Thus K_res^2 = 27/25 - 1 - 2/5 - 242/25 = -10.";
print "Total exceptional curves R = 7 + 1 + 2 + 2 = 12.";
print "For a rational tame quotient log del Pezzo surface, rho(X)=10-K_res^2-R = 8.";

print "";
print "VERDICT: quasi-smooth tame weighted del Pezzo with 10 singular points, but rho=8.";
print "It is not a full solution to the Picard-rank-one problem.";
