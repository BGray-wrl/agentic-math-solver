-- Probe wild degree-1 del Pezzo hypersurfaces in P(1,1,2,3), char 3.
-- Equation form: z^2 + G_6(u,v,w) = 0.
-- Since d=6 and sum weights=7, K_X^2=1.  Eight A1 points would be a
-- rank-one numerical target.

p = 3;

checkG = G -> (
    R = (ZZ/p)[t, W, Z];
    phiu = map(R, ring G, {1_R, t, W, 0_R});
    Gu = phiu G;
    Fu = Z^2 + Gu;
    Iu = ideal(Fu, diff(t, Fu), diff(W, Fu), diff(Z, Fu));
    IuRad = radical Iu;
    du = if dim IuRad <= 0 then degree IuRad else -1;
    IuEndpoint = IuRad + ideal t;
    duEndpoint = if dim IuEndpoint <= 0 then degree IuEndpoint else -1;

    R2 = (ZZ/p)[s, W2, Z2];
    phiv = map(R2, ring G, {s, 1_R2, W2, 0_R2});
    Gv = phiv G;
    Fv = Z2^2 + Gv;
    Iv = ideal(Fv, diff(s, Fv), diff(W2, Fv), diff(Z2, Fv));
    IvRad = radical Iv;
    dv = if dim IvRad <= 0 then degree IvRad else -1;

    -- overlap u!=0,v!=0 is double-counted; chart u=1 with t!=0
    -- is hard to subtract generically here, so report both chart ideals.
    print("G = " | toString G);
    print("  u=1 radical singular ideal: " | toString IuRad | " dim " | toString dim IuRad | " degree " | toString du);
    print("  u=1 endpoint t=0 degree: " | toString duEndpoint);
    print("  v=1 radical singular ideal: " | toString IvRad | " dim " | toString dim IvRad | " degree " | toString dv);
    print("  disjoint chart count estimate: v=1 all + u=1,t=0 = " | toString (dv + duEndpoint));
);

S = (ZZ/p)[u, v, w, z, Degrees=>{1,1,2,3}];

print "=== Degree-1 wild family probes in P(1,1,2,3) ===";
print "All examples are F=z^2+G.";

-- Three smooth degree-2 components w+quadratic.  Pairwise intersections
-- of three conics suggest at most six nodes in the branch curve.
G1 = (w + u^2) * (w + v^2) * (w + u*v + u^2 + v^2);
checkG(G1);

-- Two degree-2 components plus two lines, the classical way to try to get
-- more branch intersections in total degree 6.
G2 = (w + u^2 + v^2) * (w + u*v + v^2) * u * v;
checkG(G2);

-- A deliberately nonreduced/wild-ish perturbation with cubic-in-w behavior.
G3 = w^3 + u*v*(u^4 + u^3*v + u^2*v^2 + u*v^3 + v^4);
checkG(G3);

-- A mixed term sample using all weight-6 shapes.
G4 = w^3 + w^2*(u^2 + u*v + v^2) + w*(u^4 + u^3*v + v^4) + u*v*(u-v)*(u+v)*(u^2+v^2);
checkG(G4);
