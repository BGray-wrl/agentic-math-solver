# Scaling Bucket — Data Dictionary

Best-of-N scaling curves with **bootstrap-resampled pass@n** instead of nested
prefix pass@n. Sources: scaling, scaling_reasoning, scaling_v4flash from
`results/dataset_20260505.jsonl`, augmented by `extend_scaling_pass9_20260507`
to bring all 5 cells to **M=9 branches × 70 problems** (canonical PB+R26 set).

## Why bootstrap?

The master scaling experiments computed pass@n as `max(scores[:n])` — a
deterministic prefix of branches sorted by k. This makes pass@1 ⊂ pass@3 ⊂
pass@5 ⊂ pass@7 ⊂ pass@9, so per-problem trajectories are monotonic by
construction and understate the variance of the estimator. We replace this with
**exhaustive enumeration** of all C(M, n) size-n subsets per (model, problem)
and report the mean and standard deviation of `max(score over subset)`.

For M=9 (all 5 cells after the 2026-05-07 extension):
n=1/3/5/7/9 enumerates 9/84/126/36/1 subsets. (Cells where M<9 only on stragglers.)

## Coverage extension (2026-05-07)

The original 2026-05-06 bucket had:
- `scaling` × {gemma, gpt-oss} × default: 30 problems × 7 branches.
- `scaling_reasoning` × {gemma, gpt-oss} × max: 70 × 9 (gpt-oss had 4 incomplete pids).
- `scaling_v4flash` × deepseek-v4-flash × default: 70 × 7.

Extended via `extend_scaling_pass9_20260507`:
- For ('scaling', gemma|gpt-oss, default), the 40 missing problems reuse
  phase1 generate-condition branches (already v4flash-judged, default
  reasoning) as k=0..2 and add k=3..8 fresh.
- For ('scaling', gemma|gpt-oss, default), the 30 already-covered problems get
  k=7, k=8 added on top of existing k=0..6.
- For ('scaling_reasoning', gpt-oss, max), 4 incomplete pids topped up to 9.
- For ('scaling_v4flash', deepseek-v4-flash, default), all 70 pids get k=7, k=8.
All new branches generated with the same generator prompt and judged with
deepseek-v4-flash (canonical).

## Files

- **`trials.jsonl`** — one row per (source_experiment, model, problem, n).
  Carries `branch_scores_v4flash` etc. so any bespoke n-enumeration is
  reproducible. `branch_origins` labels each branch's provenance
  (`scaling`, `scaling.new`, `phase1.generate`, etc.).
- **`trials.csv`** — flat tabular view.
- **`summary.csv`** — one row per (source_experiment, model_short, reasoning, n)
  aggregating across problems.

## `trials.csv` columns

| Column | Type | Meaning |
|---|---|---|
| `experiment` | str | Always `scaling`. |
| `source_experiment` | str | `scaling` / `scaling_reasoning` / `scaling_v4flash`. |
| `model_short`, `model_id` | str | Model. |
| `reasoning` | str | `default` for `scaling` and `scaling_v4flash`; `max` for `scaling_reasoning`. |
| `problem_id`, `level`, `difficulty`, `difficulty_label`, `is_26_research` | — | See architecture data dictionary. |
| `n` | int | Subset size for pass@n: one of 1, 3, 5, 7, 9. |
| `branches_available` | int | Total branches for this (cell, problem). Should be 9 post-extension. |
| `subsets_used` | int | C(branches_available, n) (after dropping subsets with any None score). |
| `pass_at_n_mean_v4flash` | float or null | Mean of `max(branch v4flash score over subset)`. **Canonical metric.** |
| `pass_at_n_std_v4flash` | float or null | Population std of the same. |
| `pass_at_n_pass_rate_v4flash` | float or null | Fraction of subsets whose max-score ≥ 6. |
| `pass_at_n_mean_v4pro`, `pass_at_n_std_v4pro` | float | Same for v4pro judge (only `scaling` source has v4pro inline; null elsewhere). |
| `pass_at_n_mean_gemini`, `pass_at_n_std_gemini` | float | Same for gemini judge (only `scaling` source has gemini inline; null elsewhere). |

## `summary.csv` columns

| Column | Meaning |
|---|---|
| `source_experiment`, `model_short`, `reasoning`, `n` | Group key. |
| `n_problems` | Number of problems in this group at this n. |
| `mean_pass_at_n_v4flash` | Mean across problems of `pass_at_n_mean_v4flash`. |
| `std_pass_at_n_v4flash` | Population std across problems (between-problem variability). |
| `pass_rate_v4flash` | Mean across problems of `pass_at_n_pass_rate_v4flash`. |
| `mean_score_imo` | Restricted to difficulty=1 problems. |
| `mean_score_research` | Restricted to difficulty ≥ 2 problems. |
| `research_solves` | Count of difficulty ≥ 2 problems with mean score ≥ 6 at this n. |

## Loading recipes

```python
import pandas as pd
df = pd.read_csv("results/scaling_20260506/trials.csv")
import seaborn as sns
sns.lineplot(data=df, x="n", y="pass_at_n_mean_v4flash",
             hue="model_short", style="reasoning")
```
