-- deepseek seed=46 candidate: weights [1,2,2,14], non-homogeneous equation
p = 3;
S = (ZZ/p)[x0,x1,x2,x3, Degrees=>{1,2,2,14}];
F = x1^8 - x2^8 + x3*x2 + x3*x0^2 + x0^16 + x0^14*x1;
print ("F = " | toString F);
print ("isHomogeneous F = " | toString isHomogeneous F);
-- Check each monomial's weighted degree
T = terms F;
print ("Terms and their weighted degrees:");
for t in T do print ("  " | toString t | " : " | toString degree t);
