# R26 Strict-Solve Cascade Validation

_Built 2026-05-07 10:55 UTC; mode=REAL_


## Headline ladder

- **Stage 0 (v4-flash strict)**: 44 R26 cells solved (v4-flash score ≥6)
- **Stage 1 (v4-pro validation)**: 31 cells survive (v4-pro score ≥6)
- **Stage 2 (GPT-5.4-nano-xhigh validation)**: 4 cells survive all three rungs

Existing v4-pro ≥6 grades present before re-grading: **16**.

Total candidate cells evaluated (v4-flash≥6 OR v4-pro≥6): **50**
Total judge-call cost: **$0.9081**

## Per-bucket counts

| Bucket        | Cells | v4flash≥6 | v4pro≥6 (orig) | v4pro validated | nano validated |
|---------------|-------|-----------|----------------|------------------|-----------------|
| architecture  |    34 |        28 |             16 |               21 |               4 |
| scaling       |    16   |        16 |              0 |               10 |               0 |

## Per-problem ladder (counts of cells)

| problem_id | v4flash≥6 | v4pro validated | nano validated |
|------------|-----------|------------------|-----------------|
| erdos-1051 | 1 | 0 | 0 |
| erdos-333 | 1 | 1 | 0 |
| erdos-397 | 1 | 0 | 0 |
| erdos-654 | 5 | 4 | 3 |
| erdos-659 | 1 | 2 | 0 |
| first-proof-10-official | 33 | 24 | 1 |
| first-proof-5-official | 1 | 0 | 0 |
| first-proof-6-official | 1 | 0 | 0 |

## Per-model ladder (counts of cells)

| model_short | v4flash≥6 | v4pro validated | nano validated |
|-------------|-----------|------------------|-----------------|
| deepseek-v4-flash | 11 | 10 | 2 |
| deepseek-v4-pro | 6 | 4 | 1 |
| gemini-3-flash-preview | 1 | 1 | 0 |
| gemma-4-31b-it | 13 | 8 | 1 |
| gpt-oss-120b | 10 | 6 | 0 |
| qwen3.6-35b-a3b | 3 | 2 | 0 |

## Cells surviving all three rungs (v4flash≥6 ∧ v4pro≥6 ∧ nano≥6): 4

| problem_id | model_short | mode_or_n | reasoning | source | v4flash | v4pro | nano |
|------------|-------------|-----------|-----------|--------|---------|-------|------|
| erdos-654 | deepseek-v4-flash | seed_full | default | phase3 | 7 | 6 | 7 |
| erdos-654 | deepseek-v4-pro | full | default | phase1 | 7 | 7 | 6 |
| erdos-654 | gemma-4-31b-it | seed_full | max | phase1_reasoning | 7 | 7 | 7 |
| first-proof-10-official | deepseek-v4-flash | full | default | phase1 | 7 | 6 | 6 |

## Disagreements

- v4flash passed but v4pro rejected: **19**
- v4pro validated but nano rejected: **27**

### v4flash≥6 but v4pro<6

| problem_id | model_short | mode_or_n | reasoning | source | v4flash | v4pro |
|------------|-------------|-----------|-----------|--------|---------|-------|
| erdos-1051 | deepseek-v4-flash | best_of_n_branch6 | default | scaling_v4flash | 6 | 0 |
| erdos-397 | deepseek-v4-flash | seed_generate | default | phase1 | 7 | 0 |
| erdos-654 | deepseek-v4-pro | generate | default | phase1 | 7 | 1 |
| erdos-654 | gpt-oss-120b | full | max | phase1_reasoning | 6 | 0 |
| first-proof-10-official | gemini-3-flash-preview | full | default | phase1 | 7 | 1 |
| first-proof-10-official | gemma-4-31b-it | full | default | phase1 | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | seed_full | default | phase2 | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | generate | max | phase1_reasoning | 7 | 0 |
| first-proof-10-official | gemma-4-31b-it | full | max | phase1_reasoning | 7 | 1 |
| first-proof-10-official | gemma-4-31b-it | seed_generate | max | phase1_reasoning | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | best_of_n_branch0 | max | scaling_reasoning | 7 | 1 |
| first-proof-10-official | gemma-4-31b-it | best_of_n_branch5 | max | scaling_reasoning | 7 | 1 |
| first-proof-10-official | gpt-oss-120b | generate | max | phase1_reasoning | 7 | 0 |
| first-proof-10-official | gpt-oss-120b | seed_full | max | phase1_reasoning | 6 | 0 |
| first-proof-10-official | gpt-oss-120b | best_of_n_branch1 | max | scaling_reasoning | 6 | 0 |
| first-proof-10-official | gpt-oss-120b | best_of_n_branch4 | max | scaling_reasoning | 7 | 0 |
| first-proof-10-official | qwen3.6-35b-a3b | full | default | phase1 | 6 | 0 |
| first-proof-5-official | deepseek-v4-pro | seed_generate | default | phase1 | 7 | 0 |
| first-proof-6-official | deepseek-v4-flash | best_of_n_branch2 | default | scaling_v4flash | 7 | 0 |

### v4pro validated but nano<6

| problem_id | model_short | mode_or_n | reasoning | source | v4pro | nano |
|------------|-------------|-----------|-----------|--------|-------|------|
| erdos-333 | gemma-4-31b-it | seed_full | max | phase1_reasoning | 6 | 1 |
| erdos-654 | gpt-oss-120b | seed_generate | default | phase1 | 7 | 0 |
| erdos-659 | deepseek-v4-flash | generate | default | phase1 | 6 | 1 |
| erdos-659 | deepseek-v4-flash | best_of_n_branch2 | default | scaling_v4flash | 6 | 1 |
| first-proof-10-official | deepseek-v4-flash | generate | default | phase1 | 6 | 1 |
| first-proof-10-official | deepseek-v4-flash | seed_generate | default | phase1 | 6 | 1 |
| first-proof-10-official | deepseek-v4-flash | seed_full | default | phase3 | 6 | 2 |
| first-proof-10-official | deepseek-v4-flash | best_of_n_branch1 | default | scaling_v4flash | 6 | 1 |
| first-proof-10-official | deepseek-v4-flash | best_of_n_branch2 | default | scaling_v4flash | 6 | 1 |
| first-proof-10-official | deepseek-v4-flash | best_of_n_branch4 | default | scaling_v4flash | 6 | 1 |
| first-proof-10-official | deepseek-v4-pro | generate | default | phase1 | 6 | 1 |
| first-proof-10-official | deepseek-v4-pro | full | default | phase1 | 6 | 1 |
| first-proof-10-official | deepseek-v4-pro | seed_generate | default | phase1 | 6 | 1 |
| first-proof-10-official | gemini-3-flash-preview | generate | default | phase1 | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | generate | default | phase1 | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | seed_generate | default | phase1 | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | seed_full | max | phase1_reasoning | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | best_of_n_branch2 | max | scaling_reasoning | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | best_of_n_branch4 | max | scaling_reasoning | 6 | 1 |
| first-proof-10-official | gemma-4-31b-it | best_of_n_branch8 | max | scaling_reasoning | 6 | 1 |
| first-proof-10-official | gpt-oss-120b | generate | default | phase1 | 6 | 1 |
| first-proof-10-official | gpt-oss-120b | seed_generate | max | phase1_reasoning | 6 | 1 |
| first-proof-10-official | gpt-oss-120b | best_of_n_branch5 | max | scaling_reasoning | 6 | 1 |
| first-proof-10-official | gpt-oss-120b | best_of_n_branch6 | max | scaling_reasoning | 6 | 1 |
| first-proof-10-official | gpt-oss-120b | best_of_n_branch8 | max | scaling_reasoning | 6 | 1 |
| first-proof-10-official | qwen3.6-35b-a3b | generate | default | phase1 | 6 | 1 |
| first-proof-10-official | qwen3.6-35b-a3b | seed_generate | default | phase1 | 6 | 1 |

## Methodology notes

- Stage 1 judge: `openrouter/deepseek/deepseek-v4-pro` (extra reasoning_max_tokens=32768; reasoning_content fallback).
- Stage 2 judge: `openrouter/openai/gpt-5.4-nano` with `reasoning_effort='high'` (xhigh in repo nomenclature).
- Judge prompt: `prompts/pipeline/judge_gt.md` (output restricted to {0,1,6,7}).
- Pass threshold: score ≥ 6 (counts both 'almost' (6) and 'correct' (7)).
- For architecture cells already showing v4-pro ≥6 in the bucket data, the existing grade is reused; only cells without a passing v4-pro grade were re-graded (35 re-grade calls).
- Stage 2 is run for every v4pro-validated cell (including those whose v4-pro grade was pre-existing).
- Scaling cells: validated at the per-branch level (each branch with v4flash ≥6 = one cell).

Source data:
- `results/architecture_20260506/trials.jsonl`
- `results/scaling_20260506/trials.jsonl`
- `results/dataset_20260505.jsonl` (used to look up scaling branch text)