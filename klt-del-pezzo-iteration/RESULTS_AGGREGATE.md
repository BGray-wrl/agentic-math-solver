# klt del Pezzo iteration — final aggregate

**Date:** 2026-05-11
**Verifier:** Macaulay2 1.26.05, plus strengthened `klt_verifier.py` (stratum + pseudoreflection + Picard-rank checks).

## ⚠ Headline: Both warmup AND full problems remain UNSOLVED

After two rounds of adversarial review uncovered verifier bugs, **all previously-claimed "verified" solutions have been retracted**. The current set of strengthened checks (codim, char-3 tameness, well-formedness, Fano index, quasi-smoothness, max-isotropy-stratum + pseudoreflection-risk skip, and Picard rank ρ(X) = 1) rejects everything from this batch.

## Retracted candidates

| Candidate | Problem type | Reported score | Retracted by | True issue |
|---|---|---|---|---|
| `P(2,2,5,5), x_0^5+x_1^5+x_2^2+x_3^2` (gemma seed=46) | warmup (≥7) | 7 (sing=7) | Picard rank | ρ(X) = 5 ≠ 1 |
| `P(2,4,5,25), x_0^15 + ... + x_2 x_3` (gpt-oss seed=42, exp1) | warmup | 7 (sing=21) | Picard rank | ρ heuristic gives negative; case is genuinely not ρ=1 (multiplicity overcounting in my counter masks this) |
| `P(1,2,2,2,5), x_0^10+...+x_4^2` (gpt-oss seed=43, exp1) | warmup | 7 (sing=?) | Codim mismatch | X is a 3-fold, not a surface (5 vars, 1 eqn) |
| `P(2,4,5,5,5), x_0^10+...+x_4^4` (gpt-oss seed=44, exp2) | full | 7 | Codim mismatch | X is a 3-fold |
| `P(2,2,5,5,11) CI` (gpt-oss seed=42, exp4) | full | 7 (sing=10) | Coord-point double-count fix | After de-dup: 7 of 8; one short |
| `P(2,2,5,5,5,7) CI` "V2" (my candidate) | full | 7 (sing=11) | Max-stratum + pseudoreflection | 3 weight-5 vars → 2-dim mu_5 stratum; X meets it in conic; mu_5 acts via pseudoreflection on tangent → coarse smooth |
| `P(2,2,7,7), x_0^7+x_1^7+x_2^2+x_3^2` (gemma seed=43, exp2 re-launch) | full (≥8) | 7 (sing=9) | Picard rank | ρ(X) = 7 ≠ 1 (1/7(1,1) sings, not Du Val A_6) |

## Two waves of adversarial review

**Wave 1** (V2 retraction): caught the largest-stratum bug. When 3+ weights share a common prime factor, the singular stratum is ≥ 2-dim; pairwise gcd-2 "lines" inside it are sub-strata. X may meet the larger stratum in a curve; if the local mu_k action on the tangent is a pseudoreflection (codim-1 fixed locus), the coarse quotient is smooth (Chevalley–Shephard–Todd).

**Wave 2** (P(2,2,7,7) retraction): caught the Picard rank bug. I had assumed Lefschetz hyperplane theorem gives ρ(X) = 1 for any quasi-smooth weighted hypersurface. Wrong — Lefschetz only applies in dim ≥ 3; for surfaces, Pic(X) is generally larger. Concretely:
- At a generic conic point on L_{ij} of an `a+a+b+b`-Fermat-type F in P(c, c, w, w) (c | w·something), the tangent of X has 2 directions with the SAME mu_k weight → singularity type 1/k(1, 1), NOT A_{k-1}.
- 1/k(1,1) has HJ chain `[k]` (a single (-k)-curve), not the Du Val chain `[2,2,...,2]`.
- K^2 correction is (k-2)^2/k per point, not 0 (Du Val).
- The Picard rank formula ρ(X) = ρ(X_res) − R = (10 − K_res^2) − R gives ρ(X) > 1 for typical Fermat-style weighted hypersurfaces.

## Verifier (current state)

`klt_verifier.py` now performs the following partial-signal score:

| Score | Failure |
|---|---|
| 0 | Not weight-homogeneous / parse error |
| 1 | Not tame OR not well-formed OR Fano ≤ 0 OR codim wrong |
| 2 | X contains a singular stratum (positive-dim sing locus) |
| 3 | Cone non-quasi-smooth + count < N |
| 4 | Cone non-quasi-smooth + count ≥ N (klt status unverified) |
| 5 | Quasi-smooth + count OK + ρ(X) ≠ 1 |
| 6 | Quasi-smooth + count = N − 1 (one short) |
| 7 | Quasi-smooth + count ≥ N + ρ(X) = 1 — **PASS** |

## Experiments run

**Round 1** (with old verifier — many false PASSes that I retracted after wave 1):
- exp1 (pass@K verified): 18 trials, ~13 completed, several "PASSes" all retracted.
- exp2 (build on warmup): 9 trials, completed, 1 retracted "PASS".
- exp3 (fix gpt-oss-seed=42): 9 trials, ~8 completed, 1 retracted "PASS".
- exp4 (diversity over weight sets): 24 trials, ~6 completed, 1 retracted "PASS".
- exp6 (refine V2 framework): 6 trials, completed, retracted "PASSes" all V2-pattern.

**Round 2** (with strengthened verifier including ρ check, currently running):
- Same 5 experiments relaunched at 2026-05-11 ~04:33. PIDs 57395-57399.
- 10/66 trials completed at last check, **0 PASSes**.

## Per-model breakdown (Round 1, including retractions)

| Model | Trials completed (across rounds 1+2) | Raw PASSes | Verified PASSes (final) |
|---|---|---|---|
| gpt-oss-120b @ xhigh | ~25 | 6 | **0** (all retracted) |
| deepseek-v4-flash | ~10 | 0 | 0 |
| gemma-4-31b-it @ max | ~10 | 2 | **0** (both retracted) |

gemma found one elegant near-miss (`P(2,2,7,7)`) that would have been a real solution if not for the Picard rank constraint. The model genuinely engaged with the problem structure and produced a clean construction; it just happens to have the wrong Picard rank.

## What changed in this batch from the prior FrontierMath open-problems work

- Added M2-backed partial-signal verifier (`klt_verifier.py` + `m2_verify.m2`) with the score rubric above.
- Added generate-verify-revise pipeline with key rotation across 3 OpenRouter keys, judge-fallback extraction, high `max_tokens`.
- 5 experiments (exp1-4 + exp6) launched across 3 models with verifier feedback in the revision loop.
- 2 rounds of adversarial review found two deep verifier bugs (stratum + Picard rank), retracting all claimed solutions.

The headline lesson: **a multi-step partial-signal verifier can give the appearance of progress while missing global invariants like Picard rank.** A truly verified solution would require either:
1. A working Picard-rank check that handles general cyclic-quotient types (not just 1/k(1,1) and A_n).
2. A different problem framing where ρ is computed externally (e.g., by the problem's intended Macaulay2 verifier).

## Files

| File | Purpose |
|---|---|
| `VERIFIED_SOLUTION.md` | RETRACTED — see for retraction details. |
| `VERIFIED_SOLUTION_ADVERSARIAL_NOTE.md` | Wave 1 adversarial note (V2 retraction). |
| `FINAL_SOLUTION_ADVERSARIAL_NOTE.md` | Wave 2 adversarial note (P(2,2,7,7) retraction). |
| `RESULTS.md` | Earlier batch's M2 follow-up (Phase 1) |
| `RESULTS_AGGREGATE.md` | This file |
| `VERIFIER_HARDENING.md` | Round 1 hardening (stratum + pseudoreflection) |
| `klt_verifier.py` | Strengthened verifier with Picard rank check |
| `klt_pipeline.py` | Generate → verify → revise pipeline |
| `check_V2_PASS.m2`, `check_FINAL_SOLUTION.m2` | Earlier verification scripts (now misleading; left for historical record) |
| `probe_verified_solution.m2` | Adversary's probe of V2 (correct) |
| `exp1_*.py` ... `exp6_*.py` | Experiment scripts |
| `aggregate.py` | Collates results |

## Conclusion

**The klt del Pezzo full problem (≥ 8 singular points, ρ(X) = 1, klt, char 3) remains unsolved in this batch. The warmup also remains unsolved.** The adversarial-review process revealed that the verifier I built had multiple latent bugs that allowed false-positive PASSes through three rounds before catching the genuine issue (Picard rank).

The most-engaged near-miss is gemma-max's `P(2,2,7,7), F = x_0^7+x_1^7+x_2^2+x_3^2` — a beautiful and natural construction, just unfortunately ρ = 7 not 1. Models can plausibly find the right framework but lack a feedback mechanism for the Picard-rank constraint until the verifier itself enforces it. The round-2 experiments (currently running) are the first to receive ρ-rank feedback in the revision loop; results pending.
