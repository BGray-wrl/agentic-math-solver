# Consensus-Judge-Experiment Dataset — Data Dictionary

This directory contains the full data and analysis for an experiment testing whether **cheap small-model judges (single or majority-vote consensus)** can match the agreement of frontier judges (gemini-3.1-pro, claude-opus-4.7) when grading IMO-style math proofs against human expert scores.

## v2 patches (2026-05-07)

Initial validation runs hit upstream rate limits. Three patch mechanisms were applied to recover dropped calls:
1. OpenRouter retry with non-default `provider.order` routing (e.g. SiliconFlow for v4-flash)
2. Direct Google AI Studio API for gemma (Tier-2 GEMINI_API_KEY, bypassing OpenRouter's shared backend)
3. Single-worker retry for long-tail problems

Final coverage:
- gpt-oss-120b @ xhigh: 200/200
- gemini-3.1-pro: 200/200
- claude-opus-4.7: 200/200
- deepseek-v4-flash: 195/200 (5 grading_ids consistently rate-limited)
- gemma-4-31b-it @ high: 190/200 (10 grading_ids consistently rate-limited)

Trio coverage: 95.5% of validation problems have ≥2 of 3 trio members valid (191/200), supporting robust majority vote.

## Experimental design

Two disjoint random samples of 200 grading instances each, drawn from `benchmarks/IMO-bench/gradingbench.csv` (1000 total grading instances over 30 unique problems):

- **Prior sample (seed=42)** — 200 instances, ran 10 judge configurations on May 5, 2026. Used for exploratory ranking and to discover the trio.
- **Validation sample (seed=7)** — 200 disjoint instances (drawn from the 800 not in the prior sample), ran 5 judge configurations on May 7, 2026. Used as a clean held-out test of the trio-consensus claim.

Sampling code (deterministic, reproducible):
```python
old = random.Random(42).sample(all_rows, 200)
remaining = [r for r in all_rows if r['Grading ID'] not in {r['Grading ID'] for r in old}]
new = random.Random(7).sample(remaining, 200)
```

All judges used the same hardened prompt template `prompts/pipeline/judge_gt.md`, which restricts judge output to the IMO scoring rubric **{0, 1, 6, 7}** via the format `<points>N out of 7</points>`.

## Files

- **`trials_prior.csv`** — 2000 rows (10 configs × 200 prior PIDs). One row per (config, problem). Identical schema to `results/gradingbench_calibration_20260506/trials.csv`.
- **`trials_validation.csv`** — 1000 rows (5 configs × 200 validation PIDs). Same schema as trials_prior.csv minus `verdict` (verdict is in the `.jsonl`).
- **`trials_validation.jsonl`** — Same 1000 rows in JSONL with full `verdict` text.
- **`consensus_analysis.csv`** — 400 rows (200 prior + 200 validation). One row per grading_id. Per-problem trio scores, consensus decisions, frontier judge decisions, and human ground truth.
- **`summary.csv`** — Per-(config, sample) aggregate metrics. Includes individual configs and consensus rows.
- **`pricing_snapshot.json`** — Per-model token-pricing rates used at run time.
- **`report.md`** — The paper.

## How `reasoning_config` is set

| Value | Meaning | Used by |
|---|---|---|
| `default` | Model's natural out-of-the-box behavior. | gemini-3-flash, deepseek-v4-pro, deepseek-v4-flash, gemma-4-31b-it, gpt-oss-120b (`{"effort":"minimal"}`), gemini-3.1-pro (`{"enabled":true}`), claude-opus-4.7 (`{"enabled":true}`) |
| `high` | `reasoning: {"effort": "high"}` was sent. | gemma-4-31b-it |
| `xhigh` | `reasoning: {"effort": "xhigh"}` was sent. | gpt-5.4-nano, gpt-oss-120b |
| `reasoning_off` | `reasoning: {"enabled": false}` was sent — explicit attempt to disable reasoning. | deepseek-v4-flash |

The exact API param sent is preserved verbatim in `reasoning_param_json` for each row.

## How `human_score_bucketed` is set

Used **only** for `exact_match_bucketed`. Maps human Points to the nearest of the four allowed judge buckets:

| human_score | human_score_bucketed |
|---|---|
| 0 | 0 |
| 1, 2, 3 | 1 |
| 4, 5, 6 | 6 |
| 7 | 7 |

**Critically: `human_pass_at_6`, `human_signal_at_1`, and all confusion-derived metrics use the RAW `human_score`, NOT the bucketed value.** A human-4 with judge-6 is a False Positive at the ≥6 threshold — bucketing the human into 6 would corrupt this count.

## Granularity gap (the key structural caveat)

The judge prompt only emits {0, 1, 6, 7}. Human scores in this benchmark use the full 0–7 range. In each 200-record sample, ~36–41 records (18–20%) have `human_score ∈ {2,3,4,5}` which no judge can match exactly. This caps `exact_match_raw` at ~80–82% even for a perfectly calibrated judge. Pass/fail and signal metrics are NOT affected — they binarize, so the granularity gap is irrelevant to those numbers.

| Sample | n with human ∈ {2,3,4,5} | % |
|---|---|---|
| Prior (seed=42) | 36 | 18.0% |
| Validation (seed=7) | 41 | 20.5% |

## Trio consensus rule

For each grading_id, the **trio** consists of:
- gemma-4-31b-it @ high
- gpt-oss-120b @ xhigh
- deepseek-v4-flash @ default

These three were selected from the prior calibration because their bias signs roughly cancel: gemma inflates (mean Δ +0.55), v4-flash deflates (mean Δ −0.80), gpt-oss is calibrated (mean Δ +0.21). Each emits a score in {0,1,6,7}; the consensus decision at threshold ≥6 is the majority vote among valid scores:

```python
trio_scores = [gemma_score, gptoss_score, v4flash_score]
valid = [s for s in trio_scores if s is not None]
trio_pass_at_6 = sum(1 for s in valid if s >= 6) > len(valid) / 2
```

Same rule for `signal_at_1` (threshold ≥1). For continuous metrics (Pearson r, mean delta) the trio score is the **mean** of the valid trio scores.

## `trials_prior.csv` and `trials_validation.csv` columns (26 each)

Identical schema (validation has one extra column `verdict` only in the `.jsonl` companion).

| Column | Type | Meaning |
|---|---|---|
| `judge_id` | str | Canonical short name |
| `model_id` | str | Provider model ID without `openrouter/` prefix |
| `reasoning_config` | str | `default`, `high`, `xhigh`, or `reasoning_off` |
| `reasoning_param_json` | str/null | Verbatim JSON of `reasoning` param sent (null = no param) |
| `grading_id` | str | e.g. `GB-0094` |
| `problem_id` | str | e.g. `PB-Advanced-004` |
| `problem_source` | str | e.g. `Novel Problem`, `USAMO 2025` |
| `human_score` | int | 0–7, ground-truth Points |
| `human_score_bucketed` | int | Mapped to nearest of {0,1,6,7} |
| `human_pass_at_6` | bool | `human_score >= 6` (RAW) |
| `human_signal_at_1` | bool | `human_score >= 1` (RAW) |
| `judge_score` | int/null | Parsed judge score |
| `score_in_allowed_set` | bool/null | `judge_score in {0,1,6,7}` |
| `judge_pass_at_6` | bool/null | `judge_score >= 6` |
| `judge_signal_at_1` | bool/null | `judge_score >= 1` |
| `pass_match_at_6` | bool/null | `judge_pass_at_6 == human_pass_at_6` |
| `signal_match_at_1` | bool/null | `judge_signal_at_1 == human_signal_at_1` |
| `delta` | int/null | `judge_score - human_score` (raw) |
| `abs_delta` | int/null | `abs(delta)` |
| `error` | str/null | Error message if call failed/score didn't parse |
| `prompt_tokens` | int/null | Input tokens |
| `completion_tokens` | int/null | Output tokens (excl. reasoning_tokens for some providers) |
| `reasoning_tokens` | int/null | Reasoning tokens (0 if model didn't reason; null if unreported) |
| `total_tokens` | int/null | Total tokens billed |
| `cost_usd` | float/null | Per-call estimated cost |
| `elapsed_s` | float/null | Per-call wall-clock seconds |

## `consensus_analysis.csv` columns

One row per `grading_id`. 400 rows total (200 prior + 200 validation).

| Column | Type | Meaning |
|---|---|---|
| `grading_id` | str | e.g. `GB-0094` |
| `sample` | str | `prior` or `validation` |
| `problem_id`, `problem_source`, `human_score` | — | From CSV |
| `human_pass_at_6`, `human_signal_at_1` | bool | From human_score |
| `gemma_4_31b_it_high_score` | int/null | Gemma's score |
| `gpt_oss_120b_xhigh_score` | int/null | GPT-OSS's score |
| `deepseek_v4_flash_default_score` | int/null | DeepSeek's score |
| `trio_n_valid` | int | How many of the 3 trio members had valid scores |
| `trio_majority_pass_at_6` | bool/null | Majority vote at ≥6 |
| `trio_majority_signal_at_1` | bool/null | Majority vote at ≥1 |
| `trio_mean_score` | float/null | Mean of valid trio scores |
| `trio_median_score` | int/null | Median of valid trio scores |
| `gemini_3_1_pro_score` | int/null | Gemini-3.1-Pro's score |
| `gemini_3_1_pro_pass_at_6` | bool/null | Gemini-3.1-Pro's pass decision |
| `claude_opus_4_7_score` | int/null | Claude-Opus-4.7's score (validation only) |
| `claude_opus_4_7_pass_at_6` | bool/null | Claude-Opus-4.7's pass decision (validation only) |
| `trio_pass_match_at_6` | bool/null | Trio pass decision matches human |
| `gemini_3_1_pro_pass_match_at_6` | bool/null | Gemini pass decision matches human |
| `claude_opus_4_7_pass_match_at_6` | bool/null | Opus pass decision matches human (validation only) |

## `summary.csv` columns (32 total)

Per-(config, sample) aggregates. Configs include both individual judges and consensus rows. Aggregates computed over `n_valid` (excluding null and missing-fill rows).

### Identity
- `config` (str), `sample` (str: `prior` or `validation`)

### Counts
- `n_attempted` (200), `n_valid`, `n_errors`

### Continuous score statistics
- `mean_judge_score`, `mean_human_score`, `mean_delta`, `mean_abs_dev`
- `pearson_r`, `spearman_r`
- `exact_match_raw`, `exact_match_bucketed` (blank for consensus rows since trio uses mean, not exact integers)

### Pass-at-≥6 (the headline binary boundary)
- **`pass_agree_at_6`** (HEADLINE METRIC)
- `recall_at_6`, `specificity_at_6`, `precision_at_6`, `f1_at_6`
- `tp_at_6`, `fp_at_6`, `tn_at_6`, `fn_at_6`

### Signal-at-≥1 (any-progress detection)
- `signal_agree_at_1`, `recall_at_1`, `specificity_at_1`, `precision_at_1`, `f1_at_1`

### Cost / latency / reasoning
- `mean_reasoning_tokens`, `total_cost_usd`, `mean_cost_per_call`
- `latency_p50_s`, `latency_p95_s`

## What is NOT included

- **Bootstrap CIs** — would balloon the schema; compute downstream from trial CSVs if needed.
- **Per-source breakdowns** — discussed in `report.md` prose only.
- **Confusion counts at ≥1** — derivable from `recall_at_1` + `specificity_at_1` + `n_valid` + the global signal rate.
- **Generator/reviser model identity** — every row in this dataset uses fixed-text human/AI responses already in `gradingbench.csv`.

## Source result files

### Prior sample (from `results/gradingbench_calibration_20260506/`)
See `results/gradingbench_calibration_20260506/data_dictionary.md` for the 7 source JSONs.

### Validation sample (from `experiments/results/`)
- `judge_validation_deepseek-v4-flash_default_20260507_*.json`
- `judge_validation_gpt-oss-120b_xhigh_20260507_*.json`
- `judge_validation_gemma-4-31b-it_high_20260507_*.json`
- `judge_validation_gemini-3.1-pro_default_20260507_*.json`
- `judge_validation_claude-opus-4.7_default_20260507_*.json`
