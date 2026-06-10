# Second-look audit of plausible candidates

Date: 2026-05-11

I rechecked the most plausible candidates against the Epoch prompt: characteristic 3,
klt del Pezzo, Picard number `rho(X)=1`, and at least 8 singular points.  I do
not see a rescued valid candidate.

## Hard rejections

### Retracted V2: `P(2,2,5,5,5,7)` CI

Still dead for a reason independent of the Picard-rank checker.  The equation
linear in `x5` eliminates `x5`, leaving the weight-5 locus as a full plane, not
three isolated pairwise lines.  The surface meets that plane in a conic, and the
local quotient is smoothed by a pseudoreflection.  The candidate has only the
five genuine `mu_2` points.

### `P(2,2,7,7)`, `x0^7+x1^7+x2^2+x3^2`

Still the cleanest near-miss: tame, well-formed, Fano, quasi-smooth, and it has
9 stratum singularities.  The failure is Picard rank.

The two points on `L23` are not `A6 = 1/7(1,6)`.  After eliminating one of
`x2,x3`, the tangent coordinates are `x0,x1`, both of weight `2 mod 7`, so the
local type is `1/7(1,1)`.  The corrected basket is

```text
7 * 1/2(1,1) + 2 * 1/7(1,1).
```

The exact cyclic-quotient calculation gives

```text
K_X^2 = 8/7
correction = 2 * 25/7
K_res^2 = -6
R = 9
rho(X) = 10 - K_res^2 - R = 7.
```

The original "rho=1 by Lefschetz" line is not reliable: Picard Lefschetz does
not give rank one for surface hypersurfaces the way it does in higher dimension.
Here the separated weighted form is birationally rational, so the rational
surface resolution formula is the right obstruction.

### `P(2,4,5,25)`, `x0^15+x0^13*x1+x0*x1^7+x2*x3`

Still a useful stress test, not a solution.  It is quasi-smooth and has 10
actual quotient-stratum points, but the basket is

```text
7 * 1/2(1,1) + 1/4(1,1) + 1/5(1,2) + 1/25(1,2),
```

with

```text
K_X^2 = 27/25
K_res^2 = -10
R = 12
rho(X) = 8.
```

### Wild `P(10,20,33,77)`, `x0^11+x0*x1^5+x2*x3`

Still not valid.  It violates the Method B tame-weight instruction because
`33` is divisible by 3, and after correcting the endpoint stabilizer on
`P(10,20)` from generic `10` to endpoint `20`, the basket gives `rho(X)=6`,
not `1`.

## Method C / incidence candidates

The Frobenius-tangent `P1 x P1` family remains numerically tight at 7
singularities.  For `n` chosen fibers it gives `2n+1` singularities and
rank one, but ampleness and `K_X^2 > 0` force `n <= 3`.  The finite-field
incidence variants checked in `P2(F3)` and `P1xP1(F3)` fail the necessary
positivity/compatibility tests before reaching 8 singularities.

## Pfaffian / Cox / GIT direction

No Pfaffian near-miss is rescued by the second look.  The important caveat is
that the Picard calculation is only a hard verifier once rationality or an
independent Picard computation is available.  For the bounded Pfaffian sieve I
would treat the basket/rho calculation as an escalation filter, not as final
proof.

Within that limitation, the corrected sieve still found no exact `rho=1`
format after:

- maximal-isotropy-stratum filtering, which removes pairwise-line overcounts;
- the Pfaffian perfect-matching support check on restricted skew matrices;
- tangent-type variant probing around the best near-misses.

The explicit random matrices checked near the cheaper corrected formats had
codimension 3 and nonzero target line restrictions, but failed quasi-smoothness.

## Checker caveat

The checker is not "too strict" in a way that rescues the main candidates.  The
real caveat is scope:

- For the explicit separated weighted hypersurfaces above, the surfaces are
  rational enough for the resolution formula to be decisive.
- For arbitrary codimension-3 Pfaffians, the same basket/rho arithmetic should
  be used as a rejection/escalation signal unless rationality or Picard rank is
  independently established.
- The older `rho=1 by Lefschetz` assertion is weaker than the basket obstruction
  in surface dimension and should not be used as verification.

Current bottom line: no candidate from this session satisfies all full-problem
requirements.
