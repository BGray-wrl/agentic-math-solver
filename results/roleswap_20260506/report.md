# Roleswap Bucket — Report

**1160 trial rows** combining roleswap + roleswap_reasoning + flex_cross_ideator
into a single cross-model role-assignment comparison.

## Coverage

- **Source experiments:** flex_cross_ideator: 40, roleswap: 560, roleswap_reasoning: 560
- **Reasoning distribution:** default: 600, max: 560
- **Subclass distribution:** {'oss_gemma_8cell': 1120, 'ideator_strength': 40}

## Subclass: oss_gemma_8cell

8 conditions × 2 reasoning settings (default / max). Random-baseline
(`random_run1`, `random_run2`) plus 6 single-role-swap conditions.

| condition | reasoning | n | mean | pass rate |
|---|---|---:|---:|---:|
| random_run1 | default | 70 | 1.49 | 0.21 |
| random_run1 | max | 69 | 3.19 | 0.45 |
| random_run2 | default | 70 | 2.07 | 0.30 |
| random_run2 | max | 70 | 3.34 | 0.49 |
| x_ideate_gemma | default | 70 | 1.53 | 0.21 |
| x_ideate_gemma | max | 68 | 3.09 | 0.44 |
| x_ideate_oss | default | 70 | 1.66 | 0.23 |
| x_ideate_oss | max | 70 | 2.96 | 0.41 |
| x_revise_gemma | default | 70 | 1.80 | 0.26 |
| x_revise_gemma | max | 69 | 3.48 | 0.49 |
| x_revise_oss | default | 70 | 1.69 | 0.24 |
| x_revise_oss | max | 70 | 3.41 | 0.49 |
| x_verify_gemma | default | 70 | 1.60 | 0.24 |
| x_verify_gemma | max | 69 | 3 | 0.43 |
| x_verify_oss | default | 69 | 2.07 | 0.29 |
| x_verify_oss | max | 70 | 3.63 | 0.51 |


## Subclass: ideator_strength

3 conditions, all on a 20-problem PB-Advanced subset (NOT the full 70).
v4-flash held fixed in generator + verifier + reviser; only the ideator varies.

| condition | ideator_model | n | mean | pass rate |
|---|---|---:|---:|---:|
| self_v4flash | openrouter/deepseek/deepseek-v4-flash | 20 | 3.20 | 0.45 |
| vp_v4flash | openrouter/deepseek/deepseek-v4-pro | 20 | 2.55 | 0.35 |


**Caveat:** `ideator_strength` runs on a different problem set than the
`oss_gemma_8cell` subclass. To compare across subclasses you must filter to
overlapping `problem_id`s.

## Reading the role columns

For each trial row, `ideator_model` / `generator_model` / `verifier_model` /
`reviser_model` give the model assigned to that pipeline role. In
`oss_gemma_8cell`, the `condition` label tells you which single role was
swapped: e.g. `x_ideate_oss` means the ideator is `gpt-oss-120b` and all other
roles are `gemma-4-31b-it`. `random_run1` / `random_run2` are seeded
random-assignment baselines.
