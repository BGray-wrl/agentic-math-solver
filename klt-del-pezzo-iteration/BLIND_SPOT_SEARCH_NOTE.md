# Blind-spot candidate search note

Date: 2026-05-11

I searched several directions that `delpezzo.pdf` may not have fully exhausted. No valid positive candidate was found.

## 1. Wild weighted hypersurfaces of type `f(x0,x1)+x2*x3`

Family:

```text
X = V(f(x0,x1) + x2*x3) in P(a,b,c,d)
```

I allowed weights divisible by `3`, then filtered by:

- well-formedness;
- Fano index;
- at least `8` isolated stratum singularities;
- cyclic-quotient basket arithmetic with `rho = 10 - K_res^2 - R`;
- endpoint stabilizers counted separately from generic line stabilizers.

Search bound: weights up to `80`.

Result: no `rho=1` hits after endpoint correction.

A false hit appeared at:

```text
P(10,20,33,77), degree 110
F = x0^11 + x0*x1^5 + x2*x3
```

It is quasi-smooth and has 8 quotient-stratum points, but the endpoint on `P(10,20)` has stabilizer `20`, not generic stabilizer `10`; the corrected basket gives `rho=6`, not `1`.

See:

- `search_binomial_hypersurface_family.py`
- `check_wild_candidate_P10_20_33_77.m2`

## 2. Wild degree-1 del Pezzo hypersurfaces

Family:

```text
X = V(z^2 + G_6(u,v,w)) in P(1,1,2,3)
```

This was attractive because `K_X^2=1`; eight `A1` points would be an exact rank-one numerical target.

I tested:

- several reducible branch-style samples;
- 3,500 random degree-6 polynomials `G` over `F_3`;
- singular counts on the disjoint affine cover `v=1` plus `u=1, v/u=0`, using radicalized singular ideals.

Result: no 8-point candidate. The random search peaked at 6 distinct singular points.

See:

- `probe_degree1_wild_family.m2`
- `random_degree1_search.py`

## 3. Method C / incidence directions

Already tested in `METHOD_C_POSITIVE_SEARCH_NOTE.md`:

- Frobenius-tangent `P1xP1` generalization is numerically tight at 7 singularities.
- `P2(F3)` point-line arrangements fail positivity.
- `P1xP1(F3)` grid plus `(1,1)` graph arrangements cannot produce enough compatible contracted curves.

## Current assessment

The best blind-spot search produced plausible near-misses but no valid candidate. The most instructive failure was the wild `P(10,20,33,77)` row: it looked rank-one until endpoint stabilizers were handled correctly. This is exactly the kind of bug a coarse Hilbert-series or generic-stratum scan could miss.
