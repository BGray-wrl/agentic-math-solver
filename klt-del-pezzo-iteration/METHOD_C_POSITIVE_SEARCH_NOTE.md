# Method C positive-search note

Date: 2026-05-11

I tried the two most natural Method C / incidence directions for producing more than seven singular points.

## 1. Frobenius-tangent `P1xP1` construction

The known characteristic-3 construction uses the curve

```text
C: x2*y1^3 - x1*y2^3 = 0 in P1_x x P1_y
```

Every vertical fiber is triple tangent to `C`. Choosing `n` fibers and blowing up three times over each tangency gives:

- `n` isolated `[-3]` curves `F_i`,
- `n` canonical `[2,2]` chains,
- one final curve `C` with self-intersection `-m`.

Contracting these curves gives

```text
b = 3n blowups
R = 3n + 1 contracted curves
rho(X) = 2 + b - R = 1
#Sing(X) = 2n + 1
```

For `n=3`, this is the known 7-singularity example.

The tempting extension is `n >= 4`, but it fails. If `P = f^*(-K_X)`, then on each uncontracted connector curve `E_i`,

```text
P.E_i = 1 - 1/3 - (m-2)/m = (6-m)/(3m).
```

So ampleness requires `m < 6`. But with `m = 2,3,4,5`, the condition `K_X^2 > 0` forces `n <= 3`. Thus this one-central-Frobenius-curve family cannot exceed `2*3+1 = 7` singularities.

See `method_c_frobenius_probe.py`.

## 2. Finite-field incidence arrangements

I also tested the natural incidence-geometry variant: blow up finite-field rational points and contract finite-field curves.

### `P2(F3)` line arrangement

Blowing up all 13 `F_3`-points and contracting all 13 `F_3`-lines gives the right rank count, but the pullback of `-K_X` is negative on ordinary lines. A brute-force search over selected `F_3` points/lines found no rank-one configuration passing even the necessary positivity tests.

See `p2_f3_line_arrangement_search.py`.

### `P1xP1(F3)` grid

Blowing up the 16 grid points and using vertical/horizontal fibers plus `(1,1)` graphs also fails. For `rho=1`, one needs 17 contracted curves, which would require a compatible clique of 9 `(1,1)` graphs after taking the 8 fibers. No such clique exists.

See `p1xp1_f3_graph_search.py`.

## Current conclusion

I did not identify a positive Method C solution. The standard Frobenius construction is numerically tight at 7 singularities, and the simplest finite-incidence alternatives fail before reaching a plausible ample rank-one model.
