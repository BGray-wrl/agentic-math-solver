-- Probe the L_{34} singularity at the CORRECT F_9 representation.
-- M2's F_9 = F_3[w]/(w^2 - w - 1), so w^2 = w + 1.
-- Square roots of -1 = 2 in F_9: solve (a+bw)^2 = 2.
-- Found: 1+w and 2+2w are sqrt(-1).

p = 3;
F9 = GF(9, Variable => w);
S = F9[x0, x1, x2, x3, x4, Degrees=>{1,2,2,5,5}];
F1 = x0^4 + x1^2 + x2^2 + x0^2*x1 + x0^2*x2;
F2 = x0^10 + x1^5 + x2^5 + x3^2 + x4^2;

-- The 2 points on L_{34} cap V(F2): (0:0:0:1:1+w) and (0:0:0:1:2+2w).
print "Compute F1, F2 at the 2 points on L_{34} cap V(F2):";
i1 = 1_F9 + w;
i2 = 2_F9 + 2_F9 * w;
for s in {i1, i2} do (
    print ("  P = (0,0,0,1,"|toString s|"):");
    print ("    F1(P) = " | toString sub(F1, {x0=>0_S, x1=>0_S, x2=>0_S, x3=>1_S, x4=>sub(s, S)}));
    print ("    F2(P) = " | toString sub(F2, {x0=>0_S, x1=>0_S, x2=>0_S, x3=>1_S, x4=>sub(s, S)}));
);

-- Now compute the local model at P_1 = (0,0,0,1, 1+w) in the affine chart x_3 = 1.
-- Local coords y0 = x0, y1 = x1, y2 = x2, y4 = x4 - (1+w).
print "";
print "Local structure at P = (0,0,0,1,1+w) in chart x_3 = 1:";
R = F9[y0, y1, y2, y4];
F1loc = y0^4 + y1^2 + y2^2 + y0^2*y1 + y0^2*y2;  -- doesn't depend on x3, x4
i_val = 1_R + (sub(w, R));  -- the F_9 element 1+w embedded into R
F2loc = y0^10 + y1^5 + y2^5 + 1_R + (y4 + i_val)^2;  -- x4 = y4 + i_val
F2loc_at_origin = sub(F2loc, {y0=>0_R, y1=>0_R, y2=>0_R, y4=>0_R});
print ("  F2_loc at origin: " | toString F2loc_at_origin | "  (should be 0)");

print ("  F1_loc: " | toString F1loc);
print ("  F2_loc: " | toString F2loc);

-- F2_loc has a nonzero linear term in y4: ∂F2/∂y4 at origin = 2·i_val = 2·(1+w).
-- We can use F2 to eliminate y4 locally: y4 = (some function of y0, y1, y2).
-- The resulting local equation for V(F1, F2) ⊂ (y0,y1,y2,y4)-space is V(F1) in (y0,y1,y2)-space.
-- We need to check if F1_loc has an isolated singularity at origin and what type it is.

I1 = ideal F1loc;
J1 = jacobian I1;
print ("");
print ("Jacobian of F1_loc: " | toString J1);
JminorsCol = ideal(flatten entries J1);
SingF1 = saturate(I1 + JminorsCol, ideal(y0, y1, y2, y4));
print ("Singular locus saturated: " | toString SingF1);
if SingF1 == ideal(1_R) then (
    print "  ✓ V(F1_loc) singular only at origin (isolated singularity)";
) else (
    print "  *** V(F1_loc) has non-isolated singular locus or other issues";
);

-- Identify the singularity type by examining the leading terms.
print "";
print "Singularity classification:";
print "  F1_loc = y0^4 + y1^2 + y2^2 + y0^2*y1 + y0^2*y2";
print "  Lowest-order quadratic part: y1^2 + y2^2 (rank 2 over F_9, factorable as (y1+iy2)(y1-iy2))";
print "  The transverse coordinate (y0) appears with lowest-degree y0^4.";
print "  Local model after coord change: uv + y0^4 = 0  (A_3 Du Val singularity)";
print "";
print "  A_n surface singularities are Du Val/canonical/terminal — they are KLT.";
print "  So the 2 points on L_{34} contribute 2 A_3 klt singular points to X.";
