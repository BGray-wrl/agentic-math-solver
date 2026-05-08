# Scaling Bucket — Report

**1750 trial rows** = (model, problem, n) cells across 3 source experiments,
with bootstrap-resampled pass@n for n ∈ {1, 3, 5, 7, 9}.

## Coverage

- **Source experiments:** scaling: 700, scaling_reasoning: 700, scaling_v4flash: 350
- **Reasoning distribution:** default: 1050, max: 700

### n_problems per cell (at n=1)
- `scaling | gemma-4-31b-it | default`: n_problems = 70
- `scaling | gpt-oss-120b | default`: n_problems = 70
- `scaling_reasoning | gemma-4-31b-it | max`: n_problems = 70
- `scaling_reasoning | gpt-oss-120b | max`: n_problems = 70
- `scaling_v4flash | deepseek-v4-flash | default`: n_problems = 70

## Headline scaling curves (v4-flash judge)

Mean across-problems of `pass_at_n_mean_v4flash`. Each cell is exhaustively
enumerated over C(M, n) subsets of the available branches.

| source | model | reasoning | n=1 | n=3 | n=5 | n=7 | n=9 |
|---|---|---|---:|---:|---:|---:|---:|
| scaling | gemma-4-31b-it | default | 0.88 | 1.54 | 1.93 | 2.20 | 2.41 |
| scaling | gpt-oss-120b | default | 0.82 | 1.27 | 1.47 | 1.61 | 1.71 |
| scaling_reasoning | gemma-4-31b-it | max | 1.92 | 2.76 | 3.05 | 3.20 | 3.29 |
| scaling_reasoning | gpt-oss-120b | max | 1.63 | 2.45 | 2.81 | 3.05 | 3.23 |
| scaling_v4flash | deepseek-v4-flash | default | 2.74 | 3.65 | 4.01 | 4.25 | 4.47 |


## Methodology note

The original scaling experiments stored branches sorted by k=0..M-1 and
computed pass@n as `max(scores[:n])` — a deterministic prefix. We replace this
with **exhaustive enumeration of all C(M, n) size-n subsets** per (model,
problem):

| M (branches) | n=1 | n=3 | n=5 | n=7 | n=9 |
|---:|---:|---:|---:|---:|---:|
| 7  | 7   | 35  | 21  | 1   | —   |
| 9  | 9   | 84  | 126 | 36  | 1   |

Per-problem pass@n is the mean over all subsets of `max(score over subset)`;
the population std is the right error bar. This is unbiased and avoids the
correlated-trajectory artifact of the nested estimator.

The `pass_at_n_pass_rate_v4flash` column reports the fraction of subsets
whose max-score ≥ 6, i.e. how often the trial would "pass" at this n.

## Why pass@9?

The `full` (generator → verifier ↔ reviser) pipeline runs roughly N=9
generation calls per problem before early-stopping (1 initial generate + up
to N-1 verify/revise rounds). pass@9 is therefore the right token-matched
generate-only baseline against `full`-mode evaluation on PB+R26.

## Why pass@2?

To unblock pass@9 without re-running the original 7-branch scaling experiments,
`extend_scaling_pass9_20260507` only generates the missing branches per cell:
+2 per problem for cells already at M=7, plus reuse of phase1 generate
branches where applicable.

## How to read the std columns

`std_pass_at_n_v4flash` in `summary.csv` is the std **across problems** of
each problem's subset-mean. It tells you between-problem variability of the
scaling estimate at this n. The within-problem subset std is in
`pass_at_n_std_v4flash` per row of `trials.csv`.
