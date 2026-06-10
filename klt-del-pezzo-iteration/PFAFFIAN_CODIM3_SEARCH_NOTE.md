# Codimension-3 Pfaffian search note

Date: 2026-05-11

I explored a bounded codimension-3 Gorenstein/Pfaffian direction with a hard Picard-rank filter.

## Format searched

Surface `X` in weighted `P^5` with 6 ambient variables, cut by the five `4x4` Pfaffians of a `5x5` skew matrix.

Numerical format:

```text
matrix entry degree M_ij = a_i + a_j
top resolution shift s = sum(a_i)
K_X = O(s - sum(weights))
Fano index = sum(weights) - s
```

The sieve computes the Hilbert-series leading coefficient, hence `K_X^2`, then estimates quotient-line singularities and applies the basket formula:

```text
rho(X) = 10 - K_res^2 - R
```

## Results After Completion Pass

No valid numerical or explicit Pfaffian candidate was found in the bounded tame search.

The first un-hardened hits were false positives such as:

```text
weights = (1,1,4,4,4,5)
a       = (1,3,3,5,6)
```

They looked like `rho=1` with 9 singularities, but only because the script counted the three pairwise lines among the three weight-4 variables separately. This is the same bug as the retracted `P(2,2,5,5,5,7)` candidate: the actual `mu_4` stratum is a weighted plane, and the pairwise-line count is not a valid isolated-singularity count.

After adding the maximal-stratum/pseudoreflection-risk filter, there were no exact `rho=1` hits for:

```text
line-stratum sieve: max weight 12, max row degree 10
coarser format sieve: max weight 12, max row degree 10
```

I then found a second, Pfaffian-specific bug in the line sieve: it is not enough that a Pfaffian degree is representable on a quotient line. The restricted `5x5` skew matrix must also have a perfect matching in the relevant `4x4` minor. Otherwise every Pfaffian vanishes on that line and the surface contains the singular line.

After adding this perfect-matching support check, the previous near misses changed. The corrected bounded run

```text
pfaffian_line_target_sieve.py --max-w 12 --max-a 10
```

again found no exact `rho=1` hits. The best corrected near misses were:

```text
weights = (1,1,5,5,8,8)
a       = (1,2,7,8,8)
estimated basket = 5*(1/5(1,1)) + 3*(1/8(1,1))
rho = 211/200
```

and

```text
weights = (2,5,5,7,8,11)
a       = (3,5,7,9,10)
estimated basket = 3*(1/2(1,1)) + 5*(1/5(1,1))
rho = 43/1925
```

and

```text
weights = (5,5,7,7,8,11)
a       = (2,5,6,8,10)
estimated basket = 5*(1/5(1,1)) + 3*(1/7(1,1))
rho = 5608/13475
```

I varied plausible tangent-weight choices for these corrected near misses; none became exact `rho=1`.

## Explicit Matrix Checks

I added `explicit_pfaffian_near_miss_search.py` and generated sparse random matrices biased toward the target quotient lines.

For the two cheaper corrected near formats:

```text
weights = (2,5,5,7,8,11), a = (3,5,7,9,10)
weights = (5,5,7,7,8,11), a = (2,5,6,8,10)
```

three random trials each had `codim = 3`, and the target quotient-line restrictions were nonzero, so the perfect-matching correction is behaving as intended. However, one quasi-smoothness check for each format failed:

```text
quasi_smooth false
sing_cone_dim 2
```

The heavier corrected near format

```text
weights = (1,1,5,5,8,8), a = (1,2,7,8,8)
```

timed out in the explicit M2 codimension/line pass. It is still not a rank-one numerical target: the tangent-type variant probe gives closest `rho = 211/200`, not `1`.

## Scripts

- `pfaffian_format_sieve.py`: coarse codimension-3 Pfaffian format sieve.
- `pfaffian_line_target_sieve.py`: quotient-line singularity target sieve with maximal-stratum hardening.
- `pfaffian_type_variant_probe.py`: checks whether alternative tangent-weight choices rescue near misses.
- `pfaffian_m2_harness.py`: starter harness for explicit Macaulay2 Pfaffian matrix checks.
- `explicit_pfaffian_near_miss_search.py`: random explicit matrix checks around corrected near-miss formats.

## Current assessment

This did not produce a positive candidate. The main useful outcomes are:

1. The same pairwise-line overcount appears immediately in Pfaffian formats unless maximal isotropy strata are handled first.
2. Pfaffian line restrictions also require a perfect-matching support test in the restricted skew matrix; degree representability alone gives false positives.
3. Corrected near misses are not rank-one under any plausible tangent quotient type, and explicit random representatives of the cheaper near formats fail quasi-smoothness.

The next plausible escalation would be a much more structured matrix search that imposes quasi-smoothness conditions directly while controlling line restrictions. Random sparse matrices around the near misses did not work.
