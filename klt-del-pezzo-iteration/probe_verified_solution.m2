-- Adversarial probes for VERIFIED_SOLUTION.md.
-- Focus: the advertised singular count, especially the missed weight-5 plane.

p = 3;
S = (ZZ/p)[x0, x1, x2, x3, x4, x5, Degrees=>{2,2,5,5,5,7}];
F1 = x0^5 + x1^5 + x2^2 + x3^2 + x2*x4;
F2 = x5 + x0*x2 + x1*x3;
F3 = x1*x2 + x0*x3 + x0*x4;

print "=== Probe 1: x5 is eliminable ===";
print "S/(F2) is the weighted polynomial ring in x0..x4; the candidate is equivalent to";
print "  V(F1, F3) in P(2,2,5,5,5).";

print "";
print "=== Probe 2: full mu_5 stratum, not just pairwise lines ===";
T = (ZZ/p)[a,b,c]; -- a=x2, b=x3, c=x4 on the weight-5 plane
C = a^2 + b^2 + a*c;
IC = ideal C;
print("mu_5 stratum intersection cone ideal: " | toString IC);
print("affine cone dimension = " | toString dim IC | " (so projective dimension = 1)");
print("degree of the projective conic = " | toString degree IC);
gradC = ideal flatten entries jacobian IC;
singC = saturate(IC + gradC, ideal(a,b,c));
print("singular locus of that conic = " | toString singC);

print "";
print "=== Probe 3: where could the mu_5 quotient be genuinely singular? ===";
print "On the mu_5 plane, F3 is the linear form x1*x2 + x0*(x3+x4)";
print "in the nontrivial variables x0,x1.  If both coefficients vanished,";
print "the local tangent quotient would not be a pseudoreflection quotient.";
bad = saturate(ideal(C, a, b+c), ideal(a,b,c));
print("ideal(C, x2, x3+x4) saturated = " | toString bad);
print "ideal 1 means there is no such bad point on the conic.";

print "";
print "=== Probe 4: mu_2 stratum count ===";
U = (ZZ/p)[u,v]; -- u=x0, v=x1 on the weight-2 line
D = u^5 + v^5;
ID = ideal D;
print("mu_2 stratum equation: " | toString D);
print("degree = " | toString degree ID | " (five geometric points over kbar)");
print("separability check: gcd(D, dD/du) in chart u=1 is done conceptually since d(1+t^5)/dt = 5*t^4 = 2*t^4, nonzero at roots.");

print "";
print "Conclusion from probes:";
print "  The advertised line count splits a single mu_5 conic into coordinate lines.";
print "  Along that conic the local quotient is smooth, not an isolated cyclic quotient singularity.";
print "  The only actual coarse singularities are the five mu_2 points.";
