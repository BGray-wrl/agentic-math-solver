# Agent Communication: Verifier Hardening

Date: 2026-05-11

The current verifier is useful as a partial-signal filter, but it still produces
false positives.  Before running another search round, harden these checks.

## Highest-priority fixes

1. Detect linear-elimination collapse.

If a defining equation is linear in a variable, especially with coefficient a
unit or a monomial that is nonzero on the counted stratum, eliminate that
variable and re-run dimension, stratum, singular-count, and Picard checks on
the lower weighted model.  Round 3 false positives such as

```text
P(16,2,1,1), F = x0 + x1^8 + x2^16 + x3^16
```

look like they have many roots on a weighted line, but geometrically collapse
to a weighted projective plane with only the usual few coordinate quotient
points.

2. Count points on weighted lines using the actual coarse geometry.

Do not infer point count from affine degree divided by a generic gcd when the
line is non-well-formed or an endpoint has larger stabilizer.  Endpoint
stabilizers killed the wild `P(10,20,33,77)` near-hit.  The line-count routine
should separately handle:

- finite chart roots;
- endpoint roots;
- generic stabilizer versus endpoint stabilizer;
- duplicate roots or non-reduced intersections.

3. Keep maximal-isotropy-stratum checks mandatory.

Pairwise line enumeration is unsafe when three or more weights share a prime.
The actual stratum is higher-dimensional.  This killed the original
`P(2,2,5,5,5,7)` candidate: the weight-5 plane met the surface in a conic, and
the quotient was smoothed by a pseudoreflection.

4. Compute local tangent quotient types, not just stabilizer orders.

For each counted quotient point, compute the actual `mu_r` action on `T_P X`.
This caught `P(2,2,7,7)`: the two `mu_7` points are `1/7(1,1)`, not
`A6 = 1/7(1,6)`, so the Picard rank is `7`, not `1`.

## Picard-rank hardening

The basket calculation

```text
rho(X) = 10 - K_res^2 - R
```

is decisive only when the resolution is known rational.  It is safe for the
explicit separated weighted hypersurface near-misses used in the notes, but for
general Pfaffian/Cox/GIT constructions it should be treated as an escalation
filter unless rationality or Picard rank is independently proved.

Needed improvements:

- exact cyclic quotient discrepancy corrections using HJ chains for every
  `1/r(1,q)`;
- CI Picard-rank support, not only 4-variable hypersurfaces;
- a fallback that records "Picard unknown" rather than accepting `rho=1` by
  Lefschetz in surface dimension;
- optional independent Picard computation for explicit candidates.

## Pfaffian-specific hardening

For codimension-3 Pfaffian searches, degree representability on a quotient line
is not enough.  The restricted `5x5` skew matrix must contain a perfect matching
in the relevant `4x4` Pfaffian minor.  Otherwise every Pfaffian vanishes on the
line and the surface contains the singular stratum.

Keep both filters:

- maximal-isotropy-stratum filtering;
- perfect-matching support filtering.

## Recommended next verifier order

1. Parse and normalize candidate dimension/codimension.
2. Detect linear eliminations and reduce the model if possible.
3. Enumerate maximal isotropy strata before pairwise lines.
4. Count coarse points with endpoint stabilizers separated.
5. Compute actual local tangent quotient types.
6. Apply exact HJ basket arithmetic.
7. Accept only if Picard rank is actually proved; otherwise mark as
   "needs escalation", not "verified".

Current status: no candidate from the session is a verified full solution.

---

## 2026-05-13: exp9 + exp9b results with the frontier verifier adopted

The hardening recommendations above were largely incorporated by switching from
`klt_verifier` to `frontier_verifier` (via `frontier_adapter`), which provides:

- exact char-p polynomial arithmetic + univariate GCD point counting (replaces
  the affdeg/gcd heuristic);
- endpoint-stabilizer separation in line counts;
- all-strata enumeration (not just pairwise);
- exact HJ-chain discrepancy arithmetic;
- conditional Picard via the basket formula returning `ESCALATE` rather than
  accepting `ρ = 1 by Lefschetz` in surface dimension;
- explicit `PASS / FAIL / ONE_SHORT / ESCALATE / UNSUPPORTED` verdict taxonomy.

Two experiments were run with the new verifier as the iteration signal:
**exp9** (initial 36-trial diverse-framework run, 17 trials completed before
OpenRouter slow-stream hangs stalled the pool) and **exp9b** (resume of the
remaining 19 trials with a wall-clock-bounded `model_chat`, incremental JSON
writes, and a stagnation watchdog). All 36 ran to completion across the two.

### Headline counts

- **0 PASS** across 36 trials.
- **1 × score 6** (ONE_SHORT) — gemma fell back to the warmup Fermat
  `P(2,2,5,5), x_0^5 + x_1^5 + x_2^2 + x_3^2` with 7 sing points.
- **15 × score 5** (ESCALATE) spanning 3 candidate families.
- 4 × score 3 (cone non-quasi-smooth) + 5 × score 1 + 11 × score 0 (parse fail).

### Candidate families at score 5

1. **P(2,2,7,7) Fermat-class — 8 trials, all `sing = 9`, all `ρ_if_rat = 7`.**
   Pure Fermat plus various binary cross-terms (`x_0^6 x_1`, `x_0^4 x_1^3`,
   `x_0^3 x_1^4`). The exact-arithmetic verifier confirmed across 8 attempts
   that **binary cross-terms in the degree-14 part do NOT change the local
   mu_7 representation at the L_{23} conic points** — the type stays
   1/7(1,1), so ρ stays 7. This rules out a whole class of "obvious" repairs.

2. **P(2,2,11,13) — 6 trials, all `sing = 14`, all `ρ_if_rat = 12`.**
   A novel ambient that emerged this round: three models independently
   converged on `x_0^{11} x_1 + x_0 x_1^{11} + x_2 x_3` and variants. Lots
   of singular points but mu_11 and mu_13 inflate ρ. Worth investigating
   whether a re-weighting (e.g., changing the role of x_3) breaks the
   inflation.

3. **P(2,2,5,7) deepseek hybrid (seed=43) — `sing = 8`, `ρ_if_rat = 6`.**
   The single closest result. Drifted from a prompted P(2,5,5,7) framework
   to a P(2,2,5,7) construction:
   `F = x_0^5 x_1 + x_0 x_1^5 + x_0 x_2^2 + x_1 x_2^2 + x_2 x_3`.
   Only candidate with `ρ_if_rat ≤ 6`. Worth a manual tangent-type check
   to confirm the verifier's basket; if any of the counted strata is
   actually pseudoreflection-smooth or has different local type, the true
   ρ could be lower.

### Pending verifier work (from this note's roadmap)

Still not addressed:
- **CI Picard support** (frontier_verifier currently only computes
  `ρ_if_rational` for 4-variable hypersurfaces; CI cases fall back to
  generic `ESCALATE`).
- **Pfaffian / Cox / GIT presentations** — none have appeared in candidates yet.
- **Independent Picard computation** for the score-5 candidates (the
  basket-based ρ is conditional on rationality of the resolution).

### Infrastructure lessons (for any next agent picking this up)

- `requests.timeout` is per-read-byte. With OpenRouter, slow-streaming
  responses can hang workers indefinitely. **Use a wall-clock guard via
  `concurrent.futures.Future.result(timeout=...)`** at the `model_chat`
  layer (see `exp9b_resume.py`).
- Write the results JSON **incrementally** (atomic temp + rename) after
  each trial, not just at the end. The exp9 hang lost no data because the
  jsonl log was per-trial; but the summary JSON was never written.
- A **stagnation watchdog** (kill self if the result JSON has not been
  updated in N minutes) is cheap insurance against silent thread-pool
  hangs.

---

## 2026-05-13: review of exp9/exp9b answers and reasoning logs

I rechecked the raw logs, not just this summary.  The primary completed set is
`klt_iter_exp9_frontier_diverse_deep_20260512_164929.jsonl` plus
`klt_iter_exp9b_resume_20260513_051246.jsonl`: 36 rows, 101 model rounds, no
PASS.  I also scanned the older partial files `...160131.jsonl` and
`...044632.jsonl` because they contain two extra near-miss/hardening signals.

### Conclusion

No new answer should be treated as a valid solution.  The best candidates still
fail the Picard-rank requirement under the rational basket computation, and the
surfaces are rational/separated enough that this is not just a cosmetic
verifier concern.

### Most useful partial signals

1. **P(2,2,5,7), degree 12: two variants with exactly 8 singular points.**

   Examples:

   ```text
   x0^6 + x0^5*x1 + x0^4*x1^2 + x1^6 + x0*x2^2 + x2*x3
   x0^5*x1 + x0*x1^5 + x0*x2^2 + x1*x2^2 + x2*x3
   ```

   Both are quasi-smooth hypersurfaces with basket
   `6 A1 + 1/5(1,1) + 1/7(1,1)` up to endpoint/open-line redistribution,
   hence `sing_count = 8`, `K_X^2 = 48/35`, `K_res^2 = -4`, `R = 8`, and
   `rho_if_rational = 6`.  These are the closest numerical near-misses, but
   they are not plausible fixes as-is.  The `x2*x3` term gives an obvious
   rational projection/birational parameterization, so the conditional Picard
   obstruction should probably be promoted to a hard rejection for this family.

2. **P(2,2,7,7), degree 14: useful structural no-go.**

   The logs repeatedly rediscovered that degree-14 monomials do not create
   mixed terms between the weight-2 and weight-7 blocks.  At the `mu_7` line
   the tangent representation is therefore always generated by the two
   weight-2 directions, giving `1/7(1,1)`, not Du Val `A6 = 1/7(1,6)`.
   Cross-terms in the binary weight-2 block cannot change this.  The verifier
   consistently reports `sing_count = 9`, `rho_if_rational = 7`.

3. **P(2,2,11,13): useful no-go arithmetic, not a candidate.**

   Several models converged on degree-24 equations like
   `x0^11*x1 + x0*x1^11 + x2*x3`, giving many points but
   `rho_if_rational = 12`.  One reasoning trace did something useful: it
   enumerated possible degrees and balanced
   `sum(R_i - correction_i) = 9 - K_X^2`.  In this ambient, the only sources
   are the `mu_2` line plus the `P2/P3` heavy coordinate points; avoiding one
   heavy point and keeping enough line points never hits the required equality.
   This is worth reusing as a negative lemma/prompt constraint for hypersurface
   searches in this ambient.

4. **Older WCI partials are verifier-hardening cases, not leads.**

   The older partial `P(2,2,2,5,7)` WCI claims 15 points from three pairwise
   `mu_2` lines, but the maximal `mu_2` stratum is the whole `P(2,2,2)` plane
   and the surface meets it in a curve.  Pairwise counts overcount isolated
   singularities.  This should be scored lower or hard-rejected after a
   maximal-stratum/pseudoreflection check.

### Recommended verifier hardening from this review

- Promote rational separated hypersurface cases with `rho_if_rational != 1`
  to hard FAIL when a simple rational projection is detected, e.g. equations
  linear in one heavy variable with nonzero coefficient on a dense open.
- Lower the partial score for WCI candidates meeting a positive-dimensional
  maximal isotropy stratum.  Pairwise line counts should not produce a high
  score until the maximal stratum is cleared.
- Keep extracting and summarizing reasoning from parse-failed rounds: the best
  new signal here was a no-go argument embedded in a parse-failed/failed
  P(2,2,11,13) run.
- Treat the older partial log files as superseded for headline counts, but do
  not ignore them when mining near-misses; the first P(2,2,5,7) degree-12
  near-miss appeared only there.
