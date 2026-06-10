-- Probe the L_{34} singularity of gpt-oss seed=42's CI to see if it's klt (Du Val) or worse.
-- Local model near a point P = (0,0,0,1,i) where i^2 = -1 = 2 (i in F_9).

print "============================================";
print "Probe: local structure of CI at L_{34} point";
print "============================================";

-- Work in char 3 and use F_9 = F_3[w]/(w^2 - 2) to have a square root of -1.
p = 3;
F9 = GF(9, Variable => w);  -- w^2 = -1 = 2 in F_3.
S = F9[x0, x1, x2, x3, x4, Degrees=>{1,2,2,5,5}];

F1 = x0^4 + x1^2 + x2^2 + x0^2*x1 + x0^2*x2;
F2 = x0^10 + x1^5 + x2^5 + x3^2 + x4^2;
print ("F1 = " | toString F1);
print ("F2 = " | toString F2);

-- The 2 points on L_{34} cap V(F2): (0:0:0:1:w) and (0:0:0:1:-w) since w^2 = 2 = -1.
-- Check that these are on V(F1) and V(F2):
print "";
print "Check the 2 points (0,0,0,1,±w) lie on V(F1, F2):";
for s in {1, -1} do (
    P = {0_F9, 0_F9, 0_F9, 1_F9, s*w};
    F1P = sub(F1, {x0=>0_S, x1=>0_S, x2=>0_S, x3=>1_S, x4=>(s*w)*x4_S});  -- hack: keep symbolic
    print ("  P = (0,0,0,1," | toString (s*w) | "):");
    print ("    F1(P) = " | toString sub(F1, {x0=>0_F9, x1=>0_F9, x2=>0_F9, x3=>1_F9, x4=>s*w}));
    print ("    F2(P) = " | toString sub(F2, {x0=>0_F9, x1=>0_F9, x2=>0_F9, x3=>1_F9, x4=>s*w}));
);

-- Now examine the local structure at P = (0,0,0,1,w) in the affine chart x3 = 1.
-- Local coords: y0 = x0, y1 = x1, y2 = x2, y4 = x4 - w. Set x3 = 1.
print "";
print "Local structure in affine chart x3 = 1 near P = (0,0,0,1,w):";
R = F9[y0, y1, y2, y4];
F1loc = y0^4 + y1^2 + y2^2 + y0^2*y1 + y0^2*y2;
F2loc = y0^10 + y1^5 + y2^5 + 1 + (y4 + w)^2;  -- x4 = y4 + w, so x4^2 = (y4+w)^2
F2loc = F2loc - 0;  -- already 0 at origin since (0+w)^2 + 1 = w^2 + 1 = -1 + 1 = 0
print ("  F1_loc (around y=0): " | toString F1loc);
print ("  F2_loc (around y=0, shifted by P's image): " | toString F2loc);

-- F2's linear term in y4: (y4 + w)^2 = y4^2 + 2*w*y4 + w^2. So derivative ∂F2/∂y4 at origin = 2*w.
-- We can use F2 to solve for y4 in terms of higher-order y0, y1, y2.
-- The lowest-order term of F2 (after evaluating at origin) is the linear y4 part: 2*w*y4.
-- So locally V(F2) is a smooth divisor: y4 = (- 1/(2w)) * (y0^10 + y1^5 + y2^5 + y4^2).
-- Substituting back into F1 (which doesn't depend on y4) — same F1.

-- So the local structure of V(F1, F2) near P is the same as the local structure of V(F1) in the (y0, y1, y2) 3-space.
-- F1_loc = y0^4 + y1^2 + y2^2 + y0^2*y1 + y0^2*y2.
-- Lowest-order terms at origin: y1^2 + y2^2 (degree 2). y0^4 is degree 4. Mixed y0^2*y1, y0^2*y2 are degree 3.
-- Standard form: F1_loc = y1^2 + y2^2 + (terms in y0 of degree >= 3).
-- After a coord change diagonalizing y1^2 + y2^2: this is uv (where u = y1+iy2, v = y1-iy2) in some sense over F_9.
-- The singularity is locally a hypersurface uv + y0^4 = 0 in 3-space (after eliminating y4 via F2).
-- That's a hypersurface in 3-vars: f(u, v, y0) = uv + y0^4. This is the standard A_3 surface singularity!
-- (A_n surface singularity: uv + y^{n+1} = 0; A_3 corresponds to n+1 = 4.)

-- Verify by computing the singular locus of F1_loc:
print "";
print "Singular locus of F1_loc (as hypersurface in 3-space (y0, y1, y2)):";
I1 = ideal F1loc;
J1 = jacobian I1;
print ("Jacobian: " | toString J1);
SingF1 = I1 + ideal(J1);
sat = saturate(SingF1, ideal(y0, y1, y2));
print ("Singular locus saturated by ideal of vars: " | toString sat);
if sat == ideal 1_R then print "  ✓ origin only — isolated singularity at P"
else print "  ✗ non-isolated";

-- The singularity at origin is isolated (origin only). Now: what type?
-- We've argued it's A_3 by inspection of the local form.

print "";
print "============================================";
print "Probe of singularity type via lowest-order quadratic form:";
print "============================================";
-- Take the quadratic part:
quadF1 = y1^2 + y2^2;
print ("  Lowest-order quadratic part of F1_loc: " | toString quadF1);
print ("  This has rank 2 (over F_9, factors as (y1+w·y2)(y1-w·y2) where w^2 = -1).");
print ("  The remaining (transverse) coordinate is y0, and the lowest y0-only term is y0^4 (degree 4).";
print "  Standard local form: uv + y0^4 = 0 (A_3 Du Val singularity).";
print "";
print "VERDICT: the 2 points on L_{34} are A_3 SURFACE SINGULARITIES (rational double points = klt).";
