# Agentic Math Solver — Dataset 2026-05-05 — Findings Report

Companion to `dataset_20260505.jsonl` and `dataset_20260505_README.md`.

> Generated from the live JSONL by `experiments/build_report_20260505.py`.

## 0.  Coverage

|              | rows | with v4pro | with gemini | with v4flash | branch-rows | branch-v4pro | branch-gemini | branch-v4flash |
|---|---|---|---|---|---|---|---|---|
| phase1       | 1259 |       1256 |        1256 |         1234 |        2932 |         2932 |          2932 |           2889 |
| phase2       |  140 |        140 |         140 |          139 |         420 |           10 |           420 |            419 |
| phase3       |   69 |         68 |          69 |           68 |         207 |            0 |           207 |            205 |
| roleswap     |  560 |         18 |         560 |          559 |        1680 |           25 |          1668 |           1662 |
| scaling      |   60 |          0 |           0 |            0 |         420 |          420 |           420 |            420 |
| phase1_reasoning|  560 |          0 |           0 |          551 |        1377 |            0 |             0 |           1377 |
| scaling_reasoning|  140 |          0 |           0 |            0 |        1229 |            0 |             0 |           1229 |
| scaling_v4flash|   70 |          0 |           0 |            0 |         490 |            0 |             0 |            489 |
| gpt5_nano_pass3|   70 |          0 |           0 |            0 |         210 |            0 |             0 |            206 |
| **total**     | 2928 |       1482 |        2025 |         2551 |        8965 |         3387 |          5647 |           8896 |

## 1.  Triple-judge agreement

Cross-judge agreement statistics on cells where all three judges scored.

Triple-judge cells (all 3 scored): n=1458

|                          | v4pro vs gemini | v4pro vs v4flash | gemini vs v4flash |
|---|---|---|---|
| Exact-match rate         | 60% | 84% | 63% |
| Within-1 (\|Δ\|≤1) rate | 73% | 95% | 74% |
| Pass-flip (≥6 vs <6) rate| 27% | 5% | 26% |
| Mean Δ (col − row)       | +1.75 | +0.07 | -1.68 |

**Interpretation guide**: high pass-flip rate between two judges means they disagree on
who passes; mean Δ shows the systematic offset (e.g. v4pro − gemini < 0 means v4pro
scores lower).  Gradingbench correlations: v4pro r=0.79, v4flash r=0.76, gemini r=0.51.

## 2.  Phase 1 — 4-way mode comparison, three judges

| Model × Mode | n | v4pro | gemini | v4flash |
|---|---|---|---|---|
| deepseek-v4-flash      × full           |  70 | 3.09 | 4.63 | 3.38 |
| deepseek-v4-flash      × generate       |  70 | 3.39 | 4.81 | 3.22 |
| deepseek-v4-flash      × seed_generate  |  70 | 3.30 | 5.01 | 3.41 |
| deepseek-v4-pro        × full           |  68 | 3.66 | 5.35 | 3.85 |
| deepseek-v4-pro        × generate       |  68 | 3.38 | 5.56 | 3.53 |
| deepseek-v4-pro        × seed_generate  |  70 | 3.36 | 5.30 | 3.41 |
| gemini-3-flash-preview × full           |  70 | 1.29 | 3.76 | 1.59 |
| gemini-3-flash-preview × generate       |  70 | 1.83 | 2.93 | 1.83 |
| gemini-3-flash-preview × seed_generate  |  70 | 1.87 | 3.39 | 1.54 |
| gemma-4-31b-it         × full           |  70 | 1.17 | 3.51 | 1.39 |
| gemma-4-31b-it         × generate       |  70 | 1.83 | 3.21 | 1.49 |
| gemma-4-31b-it         × seed_generate  |  70 | 1.53 | 2.99 | 1.49 |
| gpt-oss-120b           × full           |  70 | 1.39 | 3.10 | 1.58 |
| gpt-oss-120b           × generate       |  70 | 1.33 | 2.59 | 1.34 |
| gpt-oss-120b           × seed_generate  |  70 | 1.27 | 2.40 | 1.09 |
| qwen3.6-35b-a3b        × full           |  70 | 1.44 | 3.74 | 1.62 |
| qwen3.6-35b-a3b        × generate       |  70 | 2.17 | 3.60 | 2.09 |
| qwen3.6-35b-a3b        × seed_generate  |  70 | 2.06 | 3.21 | 2.10 |

## 3.  Phase 2 / Phase 3 vs Phase 1-best

| Model | Phase1-best (v4pro) | Phase1-best (gemini) | Phase1-best (v4flash) | P2 seed_full (v4pro) | (gemini) | (v4flash) | P3 (v4pro) | (gemini) | (v4flash) |
|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4-flash      | 3.83 | 6.21 | 4.13 | — | — | — | 3.19 | 5.83 | 3.49 |
| deepseek-v4-pro        | 4.11 | 6.60 | 4.34 | — | — | — | — | — | — |
| gemini-3-flash-preview | 2.39 | 4.31 | 2.54 | — | — | — | — | — | — |
| gemma-4-31b-it         | 2.07 | 4.34 | 2.07 | 1.67 | 4.26 | 1.71 | — | — | — |
| gpt-oss-120b           | 1.86 | 3.60 | 1.76 | 1.37 | 3.99 | 1.41 | — | — | — |
| qwen3.6-35b-a3b        | 2.44 | 4.67 | 2.34 | — | — | — | — | — | — |

`agent_log.md` headlines:
- Under gemini: Phase 2 seed_full beats every Phase 1 mode for both cheap models (+0.6-0.9).
- Under v4-pro: Phase 2 seed_full collapses to the Phase 1 baseline (within ±0.1).

The v4flash column above is the third opinion.

## 4.  Roleswap — does cross-model diversity help?

| Condition | n | gemini | v4pro (special-10 only) | v4flash |
|---|---|---|---|---|
| random_run1            |  70 | 3.73 | 0.50 (n=2) | 1.49 |
| random_run2            |  70 | 4.14 | 1.50 (n=4) | 2.07 |
| x_ideate_gemma         |  70 | 3.97 | 1.50 (n=4) | 1.53 |
| x_ideate_oss           |  70 | 4.20 | 0.00 (n=2) | 1.66 |
| x_revise_gemma         |  70 | 4.04 | 0.00 (n=2) | 1.80 |
| x_revise_oss           |  70 | 4.24 | 3.00 (n=2) | 1.69 |
| x_verify_gemma         |  70 | 3.44 | 0.00 (n=2) | 1.60 |
| x_verify_oss           |  70 | 4.16 | — (n=0) | 2.07 |

## 4b.  Phase 1 RE-RUN with reasoning ON (gpt-oss + gemma, v4-flash judge)

| Model × Mode | n | v4flash mean | passes (≥6/7) |
|---|---|---|---|
| gemma-4-31b-it         × full           | 70 | 2.17 | 21/70 |
| gemma-4-31b-it         × generate       | 70 | 2.74 | 26/70 |
| gemma-4-31b-it         × seed_full      | 70 | 3.31 | 33/70 |
| gemma-4-31b-it         × seed_generate  | 70 | 2.74 | 27/70 |
| gpt-oss-120b           × full           | 68 | 2.43 | 24/68 |
| gpt-oss-120b           × generate       | 67 | 2.30 | 22/67 |
| gpt-oss-120b           × seed_full      | 67 | 3.00 | 29/67 |
| gpt-oss-120b           × seed_generate  | 69 | 2.54 | 26/69 |

## 4c.  GPT-5.4-nano pass@3 with reasoning xhigh (v4-flash judge)

| N | n | v4flash mean | passes |
|---|---|---|---|
| 1 | 70 | 2.69 | 27/70 |
| 3 | 70 | 3.01 | 30/70 |

`agent_log.md` line 2137 found role-swaps are within ±0.1 of the random_run baselines
under gemini.  v4flash provides an apples-to-apples strict-judge view across all 560
cells (not just special-10).

## 5.  Scaling — pass@k under each judge

| Model | k | gemini mean (best-of-k) | v4pro | v4flash |
|---|---|---|---|---|
| gemma-4-31b-it         | 1 | 1.67 | 0.43 | 0.27 |
| gemma-4-31b-it         | 3 | 2.50 | 0.57 | 0.47 |
| gemma-4-31b-it         | 5 | 3.20 | 0.63 | 0.67 |
| gemma-4-31b-it         | 7 | 3.63 | 0.93 | 1.40 |
| gpt-oss-120b           | 1 | 1.57 | 0.03 | 0.00 |
| gpt-oss-120b           | 3 | 1.63 | 0.10 | 0.20 |
| gpt-oss-120b           | 5 | 2.10 | 0.37 | 0.47 |
| gpt-oss-120b           | 7 | 2.10 | 0.40 | 0.47 |

## 5b.  Scaling RE-RUN with reasoning ON (v4-flash judge, k=0..8)

| Model | k | v4flash mean (best-of-k) | passes |
|---|---|---|---|
| gemma-4-31b-it         | 1 | 1.57 | 15/70 |
| gemma-4-31b-it         | 3 | 2.64 | 26/70 |
| gemma-4-31b-it         | 5 | 3.21 | 32/70 |
| gemma-4-31b-it         | 7 | 3.26 | 32/70 |
| gemma-4-31b-it         | 9 | 3.29 | 32/70 |
| gpt-oss-120b           | 1 | 1.52 | 15/67 |
| gpt-oss-120b           | 3 | 2.78 | 27/67 |
| gpt-oss-120b           | 5 | 2.87 | 28/67 |
| gpt-oss-120b           | 7 | 3.04 | 29/67 |
| gpt-oss-120b           | 9 | 3.18 | 30/67 |

## 5c.  Scaling on deepseek-v4-flash (70-problem, k=0..6, v4-flash judge)

| N | n | v4flash mean (best-of-N) | passes |
|---|---|---|---|
| 1 | 70 | 3.30 | 33/70 |
| 3 | 70 | 4.06 | 40/70 |
| 5 | 70 | 4.19 | 41/70 |
| 7 | 70 | 4.47 | 44/70 |

`agent_log.md` line 1649 (under gemini): N=1→7 yielded +2.0 / +1.5 (oss / gemma).
Under v4-pro: +0.5 / +0.5 — almost flat.

## 6.  Frontier solves — special-10 results

≥6/7 hits per judge.  "(trial)" = ≥6 on the trial's best_solution; "(branch)" = ≥6 on
any individual branch.

| Problem | v4pro ≥6 | gemini ≥6 | v4flash ≥6 |
|---|---|---|---|
| erdos-1051                   | — | phase1/gemma-4-31b-it(branch)×6, phase1/deepseek-v4-flash(branch)×5, phase1/deepseek-v4-pro(branch)×5, phase1/gemini-3-flash-preview(branch)×4 | phase3/deepseek-v4-flash(branch), scaling_v4flash/deepseek-v4-flash(branch) |
| erdos-333                    | — | phase1/deepseek-v4-flash(branch)×3, phase1/deepseek-v4-pro(branch)×2, phase1/deepseek-v4-pro(trial), phase3/deepseek-v4-flash(trial) | roleswap_reasoning/gemma-4-31b-it(trial)×2, roleswap_reasoning/gemma-4-31b-it(branch)×2, phase3/deepseek-v4-flash(branch), phase1_reasoning/gemma-4-31b-it(trial) |
| erdos-397                    | — | phase1/deepseek-v4-pro(branch)×3, phase1/deepseek-v4-pro(trial) | phase1/deepseek-v4-flash(trial), phase1/deepseek-v4-flash(branch) |
| erdos-654                    | phase1/deepseek-v4-pro(trial), phase1/deepseek-v4-pro(branch), phase1/gpt-oss-120b(trial), phase1/gpt-oss-120b(branch) | phase1/deepseek-v4-pro(branch)×3, phase2/gpt-oss-120b(branch)×3, phase1/deepseek-v4-flash(branch)×2, phase1/deepseek-v4-pro(trial)×2 | phase1/deepseek-v4-pro(trial)×2, roleswap/gpt-oss-120b(trial)×2, phase1/deepseek-v4-pro(branch), phase3/deepseek-v4-flash(trial) |
| erdos-659                    | phase1/deepseek-v4-flash(trial), phase1/deepseek-v4-flash(branch) | phase1/deepseek-v4-pro(branch)×4, phase1/deepseek-v4-pro(trial)×3, phase1/deepseek-v4-flash(branch)×2, phase1/qwen3.6-35b-a3b(branch)×2 | scaling_v4flash/deepseek-v4-flash(branch), roleswap_reasoning/gemma-4-31b-it(trial), roleswap_reasoning/gemma-4-31b-it(branch) |
| first-proof-10-official      | phase1/deepseek-v4-pro(branch)×5, phase1/deepseek-v4-flash(branch)×4, phase1/deepseek-v4-flash(trial)×3, phase1/deepseek-v4-pro(trial)×3 | phase1/deepseek-v4-flash(branch)×5, phase1/qwen3.6-35b-a3b(branch)×3, phase1/deepseek-v4-pro(branch)×2, phase1/gpt-oss-120b(branch)×2 | roleswap/gemma-4-31b-it(branch)×9, roleswap_reasoning/gemma-4-31b-it(branch)×7, phase1_reasoning/gemma-4-31b-it(branch)×6, roleswap_reasoning/gpt-oss-120b(branch)×6 |
| first-proof-4-official       | — | phase1/deepseek-v4-flash(branch)×4, phase1/deepseek-v4-pro(branch)×4, phase1/deepseek-v4-pro(trial) | — |
| first-proof-5-official       | — | phase1/deepseek-v4-pro(branch)×2, phase1/deepseek-v4-pro(trial) | phase1/deepseek-v4-pro(trial) |
| first-proof-6-official       | — | phase1/deepseek-v4-pro(branch)×4, phase1/deepseek-v4-pro(trial)×3, phase1/deepseek-v4-flash(trial), phase1/deepseek-v4-flash(branch) | scaling_v4flash/deepseek-v4-flash(branch) |
| ramsey-hypergraphs           | — | phase1/deepseek-v4-flash(branch)×2, phase1/gpt-oss-120b(branch)×2, phase1/qwen3.6-35b-a3b(branch)×2, phase1/deepseek-v4-pro(branch) | — |

## 7.  Open questions

- Where v4-pro and gemini disagree on pass/no-pass, how does v4-flash break the tie?
- Does v4-flash agree with the v4-pro headline that Phase 2 seed_full was a gemini-only
  mirage?
- For frontier solves where only gemini calls ≥6, does v4-flash also call ≥6, or does
  it side with v4-pro?

## Regenerate

```bash
uv run experiments/regrade_all_v4flash_20260505.py --max-cost 100   # regrade
uv run experiments/export_dataset_20260505.py                       # export
uv run experiments/build_report_20260505.py                         # this script
```
