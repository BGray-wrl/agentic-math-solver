# Review of `ROUND3_NOTE.md`

Date: 2026-05-11

I do not agree that the stated top partial signal is geometrically close.  It
is the top verifier score, but the score is inflated by a linear-elimination
bug.

## Linear-elimination threads

Examples such as

```text
P(16,2,1,1),  F = x0 + x1^8 + x2^16 + x3^16
```

or

```text
P(1,2,14,13), F = x0^14 + x0*x3 + x1^7 + x2
```

are not near-solutions.  Since one variable appears linearly, the hypersurface
is isomorphic, as a graded Proj, to a lower weighted projective plane.  The
many apparent roots on a non-well-formed weighted line are artifacts of the
verifier's line count.  Geometrically the singularities collapse to the usual
few coordinate quotient points of the lower weighted projective plane, so this
cannot plausibly reach 8 singularities in the hypersurface case.

This is worth expanding only as a verifier hardening task: detect linearly
eliminable variables and normalize/count the resulting lower-dimensional
weighted model instead of counting roots on the original ambient stratum.

## Non-Fermat `P(2,2,7,7)` threads

These are real near-misses but not promising positive candidates.  Cross-terms
in the degree-14 equation can change the root polynomial on `L01`, but they do
not change the local tangent weights at the two `mu_7` points on `L23`.  At
those points the tangent directions are still the two normal coordinates
`x0,x1`, both of weight `2 mod 7`, so the type remains `1/7(1,1)`.  Thus the
Picard obstruction remains `rho(X)=7`.

This is worth expanding as a short no-go lemma for the whole `P(2,2,7,7)`
degree-14 hypersurface family, not as a candidate.

## Other Round 3 outputs

- The Method A attempts in the note do not look expandable for the full
  problem.  The generated candidates either left the requested framework or
  produced too few fixed/singular points.
- The `P(1,2,5,7)`-style outputs mostly became other linear-elimination
  weighted-plane examples; they are verifier artifacts, not new geometry.
- The `P(2,2,5,5,5)` crossbar idea is conceptually the most natural CI repair,
  but with a degree-5 equation on the weight-5 plane it tends to eliminate a
  weight-5 coordinate and collapse back toward the old `P(2,2,5,5)` ceiling.

## Verdict

Round 3 produced useful negative information and verifier-hardening targets,
but I would not expand any listed answer as a serious positive candidate.  The
best use of the batch is to add:

1. a linear-elimination collapse detector;
2. correct point counting on non-well-formed weighted lines;
3. a family-level no-go note for non-Fermat `P(2,2,7,7)` hypersurfaces.
