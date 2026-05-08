# FrontierMath Open-Problems Pass@5 — Findings (updated)

**Date**: 2026-05-07
**Models** (generators): `openai/gpt-oss-120b` (xhigh reasoning), `deepseek/deepseek-v4-flash`
**Initial judge**: `deepseek/deepseek-v4-flash`
**Consensus judges**: `openai/gpt-oss-120b` (xhigh), `google/gemini-3.1-pro-preview`, `deepseek/deepseek-v4-flash`
**Benchmark**: `benchmarks/frontiermath-open-problems/open_problems_prompts.csv` (excluding `ramsey-hypergraphs`; skipped broken `small-diophantine` full_problem with `___` placeholder)

## Headline result

**14 trials pass a local programmatic verifier** — split into two tiers:

### Fully verified (mathematics checked end-to-end)

| Problem | Prompt | Verified passes |
|---|---|---|
| `explicit-deformations` | warmup | **7 / 9** — gpt-oss-120b seeds 42, 44, 45, 46 + deepseek-v4-flash seeds 42, 43, 45. All produce valid curvilinear deformations from `k[t]/(t³)` to `k[x,y]/(x,y)²` (correct Hilbert function and embedding dimension dim(m/m²)=1) |
| `degree-sensitivity-boolean` | warmup | **1 / 10** — deepseek-v4-flash seed=44. Genuine construction: n=6 vars, deg=3 multilinear Boolean polynomial with sensitivity 6, exponent a = log 6 / log 3 ≈ 1.6309 > 1.63 threshold |

### Pass *necessary conditions only* (forcing-graph semantics NOT verified)

| Problem | Prompt | Candidates | Notes |
|---|---|---|---|
| `arithmetic-kakeya` | warmup | 2 / 10 — gpt-oss-120b seeds 43, 45 | Score 3/2 = 1.5 ≤ 1.75. Format consistent, but a real verifier needs to run the forcing-pair reduction algorithm |
| `arithmetic-kakeya` | full_problem | 4 / 7 — gpt-oss-120b seeds 42, 44, 45, 46 | Score 3/2 = 1.5 ≤ 1.675 (or 14/9 for seed=42). Same caveat |

For arithmetic-kakeya, we only check that (X format), (n product matches), (score formula matches), (|T|, |R| sizes match what the first line claims). The actual forcing-pair reduction (X-constructible-graph operations, Z-linear-combination closure, vertex-forcing rules) is NOT implemented — so these are best understood as "format-valid candidates" not confirmed solutions.

## Negative result: judge unreliability on inverse-galois

The LLM judges (single + 3-judge consensus) marked many `inverse-galois` polynomials as "correct". A 30-second sympy check shows **all 20 submitted polynomials FAIL the necessary conditions** for having Galois group M_22 / M_23:

- M_n is contained in A_n (Mathieu groups are simple non-abelian, so they sit inside A_n).
- ⇒ The discriminant must be a perfect square.
- 0 of 20 polynomials have a perfect-square discriminant.

So even though gpt-oss-120b xhigh + gemini-3.1-pro + deepseek-v4-flash all unanimously agreed that several seed=44, 45, 46 polynomials were "correct", **none of them can possibly have the claimed Galois group**. Each seed produced a different polynomial citing different "well-known" sources (LMFDB, Klüners-Malle, Ford-McKay, Malle-Matzat, Magma docs) — different fabrications each time, all defended by the judges.

This is a clean illustration that LLM-as-judge does not work for problems whose verification requires symbolic computation. Three-judge consensus does not save it.

## What we built

| File | Purpose |
|---|---|
| `experiments/openproblems_pass5_20260507.py` | Pass@5 driver (gpt-oss + deepseek, xhigh) |
| `experiments/openproblems_consensus_judge_20260507.py` | 3-judge consensus (gpt-oss xhigh + gemini-3.1-pro + deepseek) |
| `experiments/openproblems_local_verify_20260507.py` | Local verifiers: Hadamard, Steiner systems, Ramsey-book, small-diophantine, degree-sensitivity-boolean, explicit-deformations (warmup), inverse-galois necessary conditions |
| `experiments/check_galois_polys_20260507.py` | Standalone disc-square + irreducibility sanity check |
| `experiments/openproblems_seed_full_20260507.py` | Seed-full architecture (ideate→3 branches→V↔R→judge) — too slow on these problems with gemma 8-concurrency, killed |
| `experiments/openproblems_gemma_passN_20260507.py` | Focused gemma generate-only |
| `logs/openproblems_pass5_20260507_20260507_183859.jsonl` | Phase 1 raw (233/260 trials, ~21 MB with full reasoning text) |

## Per-problem judge labels (Phase 1, 233 trials × deepseek-v4-flash judge)

| Problem | Type | Trials | Best judge | Pos seeds | 3/3 consensus | Locally verified |
|---|---|---|---|---|---|---|
| arithmetic-kakeya | full_problem | 7 | correct | 1 | 0 | (no checker) |
| arithmetic-kakeya | warmup | 10 | incorrect | 0 | 0 | (no checker) |
| degree-sensitivity-boolean | full_problem | 7 | incorrect | 0 | 0 | 0 |
| **degree-sensitivity-boolean** | **warmup** | 10 | correct | 3 | 0 | **1** |
| explicit-deformations | full_problem | 7 | incorrect | 0 | 0 | 0 |
| **explicit-deformations** | **warmup** | 9 | correct | 9 | (5 of 5 sampled) | **7** |
| hadamard | full_problem | 10 | almost | 1 | 0 | 0 |
| hadamard | warmup | 10 | partial | 1 | 0 | 0 |
| inverse-galois | full_problem | 10 | correct | 5 | 1 (FALSE) | 0 |
| inverse-galois | warmup | 10 | correct | 6 | 2 (FALSE) | 0 |
| klt-del-pezzo-surface | full_problem | 10 | correct | 7 | 0 | (no checker) |
| klt-del-pezzo-surface | warmup | 9 | correct | 4 | 0 | (no checker) |
| large-steiner-systems | full_problem | 9 | partial | 1 | 0 | 0 |
| large-steiner-systems | warmup | 8 | partial | 2 | 0 | 0 |
| prime-factorization | full_problem | 8 | incorrect | 0 | 0 | (no checker) |
| prime-factorization | warmup | 10 | partial | 6 | 0 | (no checker) |
| q2-absolute-galois | full_problem | 9 | incorrect | 0 | 0 | (no checker) |
| q2-absolute-galois | warmup | 8 | correct | 2 | 0 | (no checker) |
| ramsey-book-graphs | full_problem | 9 | correct | 2 | 0 | 0 |
| ramsey-book-graphs | warmup | 10 | correct | 4 | 0 | 0 |
| small-diophantine | warmup | 8 | partial | 3 | 0 | 0 |
| stretched-lr-coefficients | full_problem | 7 | correct | 4 | 0 | (no checker) |
| symplectic-ball-packing | full_problem | 10 | correct | 3 | 0 | (no checker) |
| symplectic-ball-packing | warmup | 10 | correct | 4 | 0 | (no checker) |
| unknotting-number | full_problem | 8 | partial | 2 | 0 | (no checker) |
| unknotting-number | warmup | 10 | partial | 3 | 0 | (no checker) |

## What would close the verification gap

For the problems where the judge agreed but we have no local verifier:
- **arithmetic-kakeya** — implement the forcing-graph semantics in Python (the prompt fully specifies the algorithm)
- **klt-del-pezzo-surface** — needs Macaulay2; could be installed
- **inverse-galois** — needs Magma or Sage's `K.<a> = NumberField(f); K.galois_group()`
- **q2-absolute-galois** — needs a profinite-group prover; very hard
- **stretched-lr-coefficients** — implementable in pure Python via Littlewood-Richardson rule
- **symplectic-ball-packing**, **unknotting-number**, **prime-factorization** — algorithms; need to actually run them

Without these, the "consensus-correct" labels above the locally-verified ones are unreliable.

## Budget

Approximate spend on the $40 budget:
- Phase 1 pass@5: ~$6
- 3-judge consensus (55/70 done before kill): ~$3
- Gemma seed_full + roleswap (killed early): negligible
- Local verifiers + sanity checks: $0 (run locally)

~$10 of $40 used. Plenty of room for follow-on experiments.
