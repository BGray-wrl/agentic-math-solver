# Architecture Bucket — Report

**2098 trial rows** combining 5 source experiments into a unified architecture
comparison. Canonical judge: deepseek-v4-flash (the recommended judge per the
gradingbench audit, r=0.76 with humans).

## Coverage

- **Source experiments:** gpt5_nano_pass3: 70, phase1: 1259, phase1_reasoning: 560, phase2: 140, phase3: 69
- **Difficulty distribution:** d=0: 240, d=1: 1589, d=2: 120, d=3: 60, d=4: 59, d=5: 30
- **Reasoning distribution:** default: 1468, max: 630

## Mode-level means under v4-flash

| Mode | n | mean score (0-7) | pass rate (≥6) |
|---|---:|---:|---:|
| generate | 543 | 2.31 | 0.33 |
| seed_generate | 555 | 2.29 | 0.33 |
| full | 550 | 2.24 | 0.32 |
| seed_full | 344 | 2.58 | 0.37 |

## Pass@1 → pass@3 lift (generate mode only)

`pass_at_1_v4flash` is the v4-flash score on `branches[0]` of pass@3. **It is
the first sample, NOT an independent draw**, so this is a within-trial delta
visualizing the architecture's incremental gain from emitting more samples,
not a clean independent-pass@1 comparison.

mean Δ = +0.44 (n=534)

## Research-tier (difficulty ≥ 2) solve leaders at v4flash ≥ 6

| Model | Mode | Reasoning | research solves / opportunities |
|---|---|---|---:|
| gemma-4-31b-it | seed_full | max | 3/9 |
| deepseek-v4-pro | generate | default | 2/9 |
| deepseek-v4-pro | full | default | 2/9 |
| deepseek-v4-pro | seed_generate | default | 2/9 |
| deepseek-v4-flash | seed_full | default | 2/8 |
| gpt-oss-120b | generate | default | 1/9 |
| qwen3.6-35b-a3b | generate | default | 1/9 |
| deepseek-v4-flash | full | default | 1/9 |
| gemini-3-flash-preview | full | default | 1/9 |
| gemma-4-31b-it | full | default | 1/9 |

## Asymmetry callouts

- **Phase 3** is 1 model × 1 mode (deepseek-v4-flash × seed_full only). Kept as
  a posterity check on a strong judge-tier model running its own pipeline; not
  a primary axis of comparison.
- **gpt5_nano_pass3** is 1 model × 1 mode (gpt-5.4-nano × pass@3 with
  `reasoning_effort='xhigh'`, normalized to `mode='generate'`). Different model
  family from the rest — extends the pass@3 axis but isn't a like-for-like
  comparison with Phase 1's 6 models.

## Coverage matrix (mode × model)

Phase 1 covers 6 models on `generate` / `seed_generate` / `full` only (NO
seed_full). `seed_full` data comes from Phase 2 (gpt-oss + gemma), Phase 3
(v4-flash), and `phase1_reasoning` (gpt-oss + gemma at reasoning=max).

| Mode | Default-reasoning models | Reasoning=max models | Asymmetric |
|---|---|---|---|
| generate | 6 (Phase 1) | gpt-oss + gemma | gpt-5.4-nano (1 cell) |
| seed_generate | 6 (Phase 1) | gpt-oss + gemma | — |
| full | 6 (Phase 1) | gpt-oss + gemma | — |
| seed_full | 3 (gpt-oss, gemma, v4-flash) | gpt-oss + gemma | — |
