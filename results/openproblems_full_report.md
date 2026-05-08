# FrontierMath open-problems — full report

Generated: 2026-05-07T23:43:41.752508+00:00

## Datasets

| Source | Trials |
|---|---|
| Phase 1 (gpt-oss-120b xhigh + deepseek-v4-flash via OpenRouter) | 234 |
| Phase 1 gemma (gemma-4-31b-it via Gemini API) | 122 |
| seed_full homogeneous gemma | 12 |
| seed_full roleswap (gemma + oss verifier) | 12 |
| 3-judge consensus entries | 111 |

## Locally verified passes (8)

| Problem | Type | Source | Seed | Verifier message |
|---|---|---|---|---|
| degree-sensitivity-boolean | warmup | deepseek-v4-flash | 44 | PASS (n=6, deg=3, sens=6, a=1.6309) |
| explicit-deformations | warmup | deepseek-v4-flash | 42 | PASS (special fiber Hilb {1: 2, 0: 1}, generic fiber Hilb {1: 2, 0: 1}, curvilin |
| explicit-deformations | warmup | deepseek-v4-flash | 43 | PASS (special fiber Hilb {1: 2, 0: 1}, generic fiber Hilb {1: 2, 0: 1}, curvilin |
| explicit-deformations | warmup | deepseek-v4-flash | 45 | PASS (special fiber Hilb {1: 2, 0: 1}, generic fiber Hilb {1: 2, 0: 1}, curvilin |
| explicit-deformations | warmup | gpt-oss-120b | 42 | PASS (special fiber Hilb {1: 2, 0: 1}, generic fiber Hilb {1: 2, 0: 1}, curvilin |
| explicit-deformations | warmup | gpt-oss-120b | 44 | PASS (special fiber Hilb {1: 2, 0: 1}, generic fiber Hilb {1: 2, 0: 1}, curvilin |
| explicit-deformations | warmup | gpt-oss-120b | 45 | PASS (special fiber Hilb {1: 2, 0: 1}, generic fiber Hilb {1: 2, 0: 1}, curvilin |
| explicit-deformations | warmup | gpt-oss-120b | 46 | PASS (special fiber Hilb {1: 2, 0: 1}, generic fiber Hilb {1: 2, 0: 1}, curvilin |

## Consensus unanimous correct (30)

| Problem | Type | Source | Seed | Consensus version | Judges |
|---|---|---|---|---|---|
| arithmetic-kakeya | warmup | ? | 42 | v2_2judge | oss-xhigh=correct deepseek=correct |
| degree-sensitivity-boolean | warmup | deepseek-v4-flash | 44 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| explicit-deformations | warmup | deepseek-v4-flash | 42 | v2_2judge | deepseek=correct oss-xhigh=correct |
| explicit-deformations | warmup | deepseek-v4-flash | 45 | v2_2judge | oss-xhigh=correct deepseek=correct |
| explicit-deformations | warmup | deepseek-v4-flash | 46 | v2_2judge | oss-xhigh=correct deepseek=correct |
| explicit-deformations | warmup | gpt-oss-120b | 42 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| explicit-deformations | warmup | gpt-oss-120b | 43 | v2_2judge | oss-xhigh=correct deepseek=correct |
| explicit-deformations | warmup | gpt-oss-120b | 44 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| explicit-deformations | warmup | gpt-oss-120b | 45 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| explicit-deformations | warmup | gpt-oss-120b | 46 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| inverse-galois | full_problem | deepseek-v4-flash | 45 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| inverse-galois | full_problem | deepseek-v4-flash | 46 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| inverse-galois | full_problem | gemma-4-31b-it | 45 | v2_2judge | oss-xhigh=correct deepseek=correct |
| inverse-galois | warmup | deepseek-v4-flash | 44 | v2_2judge | deepseek=correct oss-xhigh=correct |
| inverse-galois | warmup | deepseek-v4-flash | 46 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| inverse-galois | warmup | gemma-4-31b-it | 42 | v2_2judge | deepseek=correct oss-xhigh=correct |
| inverse-galois | warmup | gpt-oss-120b | 46 | v1_3judge | gpt-oss-120b=correct gemini-3.1-pro-preview=correct deepseek-v4-flash=correct |
| klt-del-pezzo-surface | full_problem | gpt-oss-120b | 42 | v2_2judge | oss-xhigh=correct deepseek=correct |
| klt-del-pezzo-surface | warmup | ? | 42 | v2_2judge | oss-xhigh=correct deepseek=correct |
| klt-del-pezzo-surface | warmup | gemma-4-31b-it | 46 | v2_2judge | oss-xhigh=correct deepseek=correct |
| large-steiner-systems | warmup | ? | 42 | v2_2judge | oss-xhigh=correct deepseek=correct |
| prime-factorization | warmup | deepseek-v4-flash | 43 | v2_2judge | deepseek=correct oss-xhigh=correct |
| q2-absolute-galois | warmup | ? | 42 | v2_2judge | oss-xhigh=correct deepseek=correct |
| q2-absolute-galois | warmup | deepseek-v4-flash | 44 | v2_2judge | oss-xhigh=correct deepseek=correct |
| ramsey-book-graphs | full_problem | deepseek-v4-flash | 43 | v2_2judge | deepseek=correct oss-xhigh=correct |
| ramsey-book-graphs | warmup | gemma-4-31b-it | 42 | v2_2judge | oss-xhigh=correct deepseek=correct |
| stretched-lr-coefficients | full_problem | deepseek-v4-flash | 43 | v2_2judge | deepseek=correct oss-xhigh=correct |
| stretched-lr-coefficients | full_problem | deepseek-v4-flash | 44 | v2_2judge | oss-xhigh=correct deepseek=correct |
| stretched-lr-coefficients | full_problem | gemma-4-31b-it | 43 | v2_2judge | oss-xhigh=correct deepseek=correct |
| stretched-lr-coefficients | full_problem | gemma-4-31b-it | 46 | v2_2judge | oss-xhigh=correct deepseek=correct |

## Per-problem signal

| Problem | Type | OG pos | Gemma pos | seed_full homo | roleswap | Cons-correct | Verified |
|---|---|---|---|---|---|---|---|
| arithmetic-kakeya | full_problem | 1 | 1 | 0 | 0 | 0 | 0 |
| arithmetic-kakeya | warmup | 1 | 0 | 0 | 1 | 1 | 0 |
| degree-sensitivity-boolean | warmup | 1 | 0 | 0 | 0 | 1 | 1 |
| explicit-deformations | warmup | 9 | 0 | 0 | 0 | 8 | 7 |
| hadamard | full_problem | 1 | 1 | 0 | 0 | 0 | 0 |
| inverse-galois | full_problem | 4 | 4 | 0 | 0 | 3 | 0 |
| inverse-galois | warmup | 6 | 3 | 1 | 1 | 4 | 0 |
| klt-del-pezzo-surface | full_problem | 3 | 0 | 0 | 0 | 1 | 0 |
| klt-del-pezzo-surface | warmup | 2 | 0 | 1 | 1 | 2 | 0 |
| large-steiner-systems | warmup | 0 | 2 | 0 | 1 | 1 | 0 |
| prime-factorization | warmup | 0 | 0 | 0 | 0 | 1 | 0 |
| q2-absolute-galois | full_problem | 0 | 2 | 0 | 0 | 0 | 0 |
| q2-absolute-galois | warmup | 2 | 0 | 1 | 0 | 2 | 0 |
| ramsey-book-graphs | full_problem | 1 | 0 | 0 | 0 | 1 | 0 |
| ramsey-book-graphs | warmup | 1 | 1 | 0 | 1 | 1 | 0 |
| stretched-lr-coefficients | full_problem | 2 | 0 | 0 | 0 | 4 | 0 |
| symplectic-ball-packing | full_problem | 1 | 1 | 0 | 0 | 0 | 0 |
| symplectic-ball-packing | warmup | 2 | 0 | 0 | 0 | 0 | 0 |
| unknotting-number | warmup | 0 | 0 | 1 | 1 | 0 | 0 |