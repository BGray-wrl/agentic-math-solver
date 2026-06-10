-- Wild weighted candidate outside Epoch Method B's tame-weight restriction.
--
-- X = V(F) in P(10,20,33,77), char 3
-- F = x0^11 + x0*x1^5 + x2*x3
--
-- Degree = 110, Fano index = 30.
-- Singular-point near-miss:
--   L01=P(10,20): x0*(x0^10+x0^8*x1+x1^5)=0 gives 6 points.
--   P2 and P3 from x2*x3=0 on L23=P(33,77).
-- A naive generic-stabilizer basket gives rho=1, but this is WRONG:
-- the endpoint x0=0 has stabilizer 20, not 10.  Corrected rho is 6.

p = 3;
S = (ZZ/p)[x0,x1,x2,x3, Degrees=>{10,20,33,77}];
F = x0^11 + x0*x1^5 + x2*x3;

print "=== Wild candidate P(10,20,33,77), degree 110 ===";
print("F = " | toString F);
print("homogeneous: " | toString isHomogeneous F);
print("degree: " | toString (degree F)#0);
weights = {10,20,33,77};
for i from 0 to 3 do (
    print("gcd drop " | toString i | " = " | toString gcd drop(weights,{i,i}));
);
print("Fano index = " | toString (sum weights - (degree F)#0));
print("weights prime to char 3? " | toString all(weights, w -> w % 3 != 0));

print "";
print "Quasi-smooth cone check";
I = ideal F;
J = ideal flatten entries jacobian I;
SingCone = saturate(I + J, ideal vars S);
print("saturated cone singular ideal: " | toString SingCone);
print("cone smooth off origin: " | toString (SingCone == ideal 1_S));

print "";
print "L01 root count";
R = (ZZ/p)[t];
g = t^5 + 1; -- finite roots in chart x0=1, t=x1/x0^2
print("finite polynomial g(t) = " | toString g);
print("gcd(g,g') = " | toString gcd(g, diff(t,g)));
print("finite roots: 5 distinct; plus endpoint x0=0, total L01 points: 6");

print "";
print "L23 contribution";
print("F|L23 = x2*x3, so P2 and P3 contribute 2 coordinate quotient points");

print "";
print "Basket / rho arithmetic";
print("5 finite L01 points of type 1/10(3,7) = 1/10(1,9), chain [2,2,2,2,2,2,2,2,2]");
print("endpoint P1 on L01 has type 1/20(13,17) = 1/20(1,9), chain [3,2,2,2,3]");
print("P2: local quotient 1/33(10,20) = 1/33(1,2), chain [17,2]  (wild: 3 divides 33)");
print("P3: local quotient 1/77(10,20) = 1/77(1,2), chain [39,2]");
print("K_X^2 = 30^2*110/(10*20*33*77) = 15/77");
print("K_res^2 = -50, total exceptional curves R = 54, hence rho = 10 - (-50) - 54 = 6");

print "";
print "Verdict";
print("This does NOT satisfy Epoch Method B's tame-weight instruction, because 33 is divisible by 3.");
print("More importantly, after endpoint correction it is not rank one.  It is not a valid solution.");
