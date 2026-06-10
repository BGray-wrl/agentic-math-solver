# klt-del-pezzo round 3 — results note

**Date:** 2026-05-11
**Setup:** Two experiments with the strengthened verifier (codim + max-stratum + pseudoreflection + Picard rank).
- `exp7`: 9 trials (3 models × 3 seeds), **5 revisions** each.
- `exp8`: 30 trials (3 models × 5 frameworks × 2 seeds), **4 revisions** each.

**Outcome:** 39 trials, **0 PASSes**, ~22 min wall time, < $5 spend.

## Top partial-signal threads

| Trial | Score | What the model did | Why it fails |
|---|---|---|---|
| **deepseek seed=44 exp7** | **6** (closest) | Over 5 revisions, evolved from Fermat in P(2,2,7,7) → mixed-monomial cross-terms → finally `F = x_3 + g(x_0,x_1,x_2)` (linear in x_3) in P(2,1,1,14). Found that X ≅ P(2,1,1) with Du Val singularities. | Linear elimination collapses the "7 sing pts on L_{03}" to a single coord-point. True sing_count = 1, not 7. My verifier overcounts and reports score 6 (one-short). |
| gemma seed=43 exp7 | 6 | Reverted to baseline warmup `P(2,2,5,5), F = Fermat`. | Same as previous warmup: ρ(X) = 5 from 1/5(1,1) sings. |
| gemma seed=42 P(2,2,7,7) Non-Fermat exp8 | 5 | Added `x_0^2 x_1^5 + x_0^5 x_1^2 + x_0^3 x_1^4` cross-terms to Fermat. | Cross-terms don't change the tangent mu_7 weights at L_{23} ∩ X — still 1/7(1,1) — so ρ stays 7. |
| deepseek seed=43 P(1,2,5,7) exp8 | 5 | Used linear-elim trick again with weights `[1,2,14,13]`. | Verifier returns fractional ρ = 1.46 (heuristic breaks); actual ρ likely 1 but sing-count too low. |
| deepseek seed=43 Method A exp8 | 5 | Attempted Method A with weights `[2,2,2,5,7]` CI. | Produced 0 singular points (model couldn't engineer enough fixed points of the involution). |

## What was learned

1. **deepseek genuinely iterates on verifier feedback.** Its 5-round trajectory in exp7 (Fermat → cross-terms → linear-elim) is real learning from the partial-signal output. The other models tended to flip-flop or stay in the Fermat well.

2. **Cross-terms in Fermat hypersurfaces don't change ρ.** Models reach for them repeatedly because they superficially look like "non-symmetric" polynomials, but they don't affect the local mu_k action at strata. ρ(X) = 7 in P(2,2,7,7) regardless of which deg-14 cross-terms you add.

3. **Method A is too restrictive.** Diagonal involutions on CI(2,2) ⊂ P^4 max at 4 fixed points. No model in this batch reached even 4 — most produced 0 or 1. Probably wrong approach for ≥ 8 singular points.

4. **Linear-elimination is a "fake" solution generator.** When F = x_l + g(others), V(F) ≅ ambient \ {x_l = 1}, and the singular structure collapses. Models can find these (deepseek did, twice) and the verifier scores them well (score 6) but they're false positives — the actual X has few singularities.

## Verifier bugs round 3 exposed (still unfixed)

1. **Linear-elimination collapse:** sing-line points on a coord shared with a linearly-eliminable variable collapse to a single point in the abstract quotient X. My verifier doesn't detect this.

2. **ρ heuristic breaks for non-generic surfaces.** The formula `ρ(X_res) = 10 - K_res^2` only works for smooth rational generic surfaces. For toric / linear-elim / special cases it gives negative or fractional ρ. False rejections likely.

3. **CI ρ computation not implemented.** Only hypersurfaces (4 vars + 1 eqn) get a ρ check; CI cases (5 vars + 2 eqns) skip ρ entirely and so still rely on the older incomplete checks.

## Status

Both warmup and full klt del Pezzo problems **remain unsolved by this batch.** All previously-claimed "PASS" candidates have been retracted by either codim, coord-double-count, stratum/pseudoreflection, or Picard-rank checks. Round 3 made the verifier stricter and produced meaningful partial-signal threads, but no genuine solution emerged.

The current best-known direction is the **linear-elimination idea** deepseek discovered: F linear in one variable gives a clean X ≅ P(w) of lower dim with ρ=1 via Lefschetz, AND can produce A_1 singularities. The problem: it collapses too many of them. A construction that uses this trick on TWO coords simultaneously, or one that has linear-elimination + a richer singular stratum on the remaining factor, might break through. None of the models in this batch produced such a construction.

## Recommendation for future work

1. **Fix verifier bugs** before another round: linear-elim detection + CI ρ computation + a non-generic-surface fallback for ρ.
2. **Try Method C (HJ basket on P^1×P^1)** — the only major method untouched. Models can't do this without specialized tutoring.
3. **Increase budget** for revision-deep gemma trials. gemma at high reasoning + 10+ revisions might break through, but needs the rate-limit headroom we don't currently have.
4. **Manual mathematician intervention** may be needed at this point — the problem may genuinely be at the edge of what LLM-driven search can do without deep specialized algebraic-geometry priors.

Total spend across all rounds: **~$5–10 OpenRouter** + Gemma direct API tier-2 ≈ **under $15**.
