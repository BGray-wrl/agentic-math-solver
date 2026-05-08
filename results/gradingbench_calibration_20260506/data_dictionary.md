# GradingBench Judge-Calibration Dataset — Data Dictionary

This dataset compiles every GradingBench judge evaluation we ran on May 5, 2026 into a single normalized matrix: **10 judge configurations × the same 200-problem random sample** (seed=42) from `benchmarks/IMO-bench/gradingbench.csv`. It consolidates **7 separate source JSONs** with slightly different schemas into one canonical long-format dataset.

All judge calls used the same hardened prompt template `prompts/pipeline/judge_gt.md`, which restricts judge output to the IMO scoring rubric **{0, 1, 6, 7}**. Human scores in `gradingbench.csv` use the full 0–7 range; see "Granularity gap" below.

## Files

- **`trials.csv`** — Long format, **2000 rows** = 10 (judge × reasoning_config) × 200 PIDs. One row per (config, problem). Configs that lack a record for some grading_id (only nano-xhigh, missing 2/200) are filled with `judge_score=null`, `error="no_record_in_source_json"` so the matrix is complete-by-config.
- **`trials.jsonl`** — Same 2000 rows, one JSON object per line, **plus** `verdict` field (full judge response text, often 1–10K chars).
- **`summary.csv`** — Wide format, 10 rows = one per (judge_id, reasoning_config). Aggregate metrics, sorted descending by `pass_agree_at_6`.
- **`pricing_snapshot.json`** — Per-judge token-pricing rates used at run time to compute `cost_usd` in trials.csv. Best-effort; OpenRouter actual billing may differ.
- **`report.md`** — Findings narrative with headline tables.

## How `reasoning_config` is set

The label captures the *mode of operation*, not the literal API param. The exact param sent is preserved in `reasoning_param_json`.

| Value | Meaning | Used by |
|---|---|---|
| `default` | Model's natural out-of-the-box behavior. May or may not include any reasoning param — see `reasoning_param_json` for the literal call. (gemma emits 0 reasoning tokens at default; gpt-oss-120b accepts only effort=minimal as its lowest, ~equivalent to default.) | gemini-3-flash, deepseek-v4-pro, deepseek-v4-flash, gemma-4-31b-it, gpt-oss-120b, gemini-3.1-pro |
| `high` | `reasoning: {"effort": "high"}` was sent. | gemma-4-31b-it |
| `xhigh` | `reasoning: {"effort": "xhigh"}` was sent. | gpt-5.4-nano, gpt-oss-120b |
| `reasoning_off` | `reasoning: {"enabled": false}` was sent — explicit attempt to disable reasoning. Only deepseek-v4-flash supports this cleanly (rt drops to 0). | deepseek-v4-flash |

## How `human_score_bucketed` is set

Used **only** for `exact_match_bucketed`. The judge prompt only emits {0, 1, 6, 7}, so we map human Points to the nearest allowed bucket for a fair exact-match comparison:

| human_score | human_score_bucketed |
|---|---|
| 0 | 0 |
| 1, 2, 3 | 1 |
| 4, 5, 6 | 6 |
| 7 | 7 |

**Critically: `human_pass_at_6`, `human_signal_at_1`, and all confusion-derived metrics use the RAW `human_score`, NOT the bucketed value.** A human-4 with judge-6 is therefore a `False Positive` at the ≥6 threshold (judge says pass, raw human=4 says fail), even though both happen to land in the bucketed-{6} group.

## Granularity gap (the one critical caveat)

The judge prompt allows only {0, 1, 6, 7}. Human scores in this n=200 sample have:

| human_score | count |
|---|---|
| 0 | 73 |
| 1 | 31 |
| 2 | 5 |
| 3 | 4 |
| 4 | 13 |
| 5 | 14 |
| 6 | 8 |
| 7 | 52 |

**36/200 records (18%) have `human_score ∈ {2,3,4,5}`**, which no judge can match exactly. This caps `exact_match_raw` at 82% even for a perfectly-calibrated judge. `pass_agree_at_6`, `signal_agree_at_1`, and all confusion metrics are NOT affected — they binarize, so the granularity is irrelevant.

## `trials.csv` columns (26 total)

| Column | Type | Meaning |
|---|---|---|
| `judge_id` | str | Canonical short name (e.g. `gemma-4-31b-it`) |
| `model_id` | str | Provider model ID without `openrouter/` prefix |
| `reasoning_config` | str | `default`, `high`, `xhigh`, or `reasoning_off` (see above) |
| `reasoning_param_json` | str/null | Verbatim JSON of the `reasoning` param sent. `null` = no param sent. |
| `grading_id` | str | e.g. `GB-0094` |
| `problem_id` | str | e.g. `PB-Advanced-004` |
| `problem_source` | str | e.g. `Novel Problem`, `USAMO 2025`, `(Modified) IMO 2024 P3` |
| `human_score` | int | 0–7, ground-truth Points from `gradingbench.csv` |
| `human_score_bucketed` | int | Human mapped to nearest of {0,1,6,7} per table above |
| `human_pass_at_6` | bool | `human_score >= 6` (RAW human, not bucketed) |
| `human_signal_at_1` | bool | `human_score >= 1` (any non-zero credit) |
| `judge_score` | int/null | 0–7 parsed from judge response. `null` if score didn't parse or call errored. |
| `score_in_allowed_set` | bool/null | `judge_score in {0,1,6,7}`. `null` if `judge_score` is null. |
| `judge_pass_at_6` | bool/null | `judge_score >= 6` |
| `judge_signal_at_1` | bool/null | `judge_score >= 1` |
| `pass_match_at_6` | bool/null | `judge_pass_at_6 == human_pass_at_6` |
| `signal_match_at_1` | bool/null | `judge_signal_at_1 == human_signal_at_1` |
| `delta` | int/null | `judge_score - human_score` (raw) |
| `abs_delta` | int/null | `abs(delta)` |
| `error` | str/null | Error message if call failed, score didn't parse, or row is missing-fill |
| `prompt_tokens` | int/null | Input tokens (from OpenRouter usage) |
| `completion_tokens` | int/null | Output tokens (excludes reasoning tokens for some providers) |
| `reasoning_tokens` | int/null | Reasoning tokens (0 for non-reasoning models, null if unreported) |
| `total_tokens` | int/null | Total tokens billed |
| `cost_usd` | float/null | Per-call estimated cost (computed from token counts × rate in `pricing_snapshot.json`) |
| `elapsed_s` | float/null | Per-call wall-clock seconds |

`trials.jsonl` adds one column: **`verdict`** (str/null) — full judge response text.

## `summary.csv` columns (34 total)

Per `(judge_id, reasoning_config)`. **All confusion-derived metrics use raw `human_score`.** Aggregates computed over `n_valid` rows (i.e., excluding score=null and missing-fill rows).

### Identity

| Column | Type | Meaning |
|---|---|---|
| `judge_id`, `model_id`, `reasoning_config`, `reasoning_param_json` | str | Same as trials.csv |

### Counts

| Column | Type | Meaning |
|---|---|---|
| `n_attempted` | int | Always 200 (full matrix per config) |
| `n_valid` | int | Trials with parseable `judge_score` |
| `n_errors` | int | Trials with non-null `error` (includes API failures, parse failures, and missing-fill rows) |

### Continuous-score statistics

| Column | Type | Meaning |
|---|---|---|
| `mean_judge_score` | float | Mean of `judge_score` over `n_valid` |
| `mean_human_score` | float | Mean of `human_score` over the same `n_valid` rows |
| `mean_delta` | float | Mean of `delta` (calibration bias; positive = judge inflates) |
| `mean_abs_dev` | float | Mean of `abs_delta` (raw, on 0–7 scale) |
| `pearson_r` | float | Pearson correlation of judge vs human |
| `spearman_r` | float | Spearman rank correlation (more robust to coarse 4-level judge scale) |
| `exact_match_raw` | float | Fraction where `judge_score == human_score` exactly |
| `exact_match_bucketed` | float | Fraction where `judge_score == human_score_bucketed` |

### Pass at ≥6 threshold (the headline binary boundary — "did the proof pass IMO standards?")

| Column | Type | Meaning |
|---|---|---|
| **`pass_agree_at_6`** | float | **HEADLINE.** Fraction where `judge_pass_at_6 == human_pass_at_6` |
| `recall_at_6` | float | TP / (TP+FN) at ≥6 |
| `specificity_at_6` | float | TN / (TN+FP) at ≥6 |
| `precision_at_6` | float | TP / (TP+FP) at ≥6 |
| `f1_at_6` | float | Harmonic mean of recall and precision at ≥6 |
| `tp_at_6`, `fp_at_6`, `tn_at_6`, `fn_at_6` | int | Confusion counts at ≥6 |

### Signal at ≥1 threshold (the secondary binary boundary — "did the response detect any meaningful progress vs dead-zero?")

| Column | Type | Meaning |
|---|---|---|
| **`signal_agree_at_1`** | float | Fraction where `judge_signal_at_1 == human_signal_at_1` |
| `recall_at_1` | float | TP / (TP+FN) at ≥1 |
| `specificity_at_1` | float | TN / (TN+FP) at ≥1 |
| `precision_at_1` | float | TP / (TP+FP) at ≥1 |
| `f1_at_1` | float | Harmonic mean of recall and precision at ≥1 |

### Cost / latency / reasoning

| Column | Type | Meaning |
|---|---|---|
| `mean_reasoning_tokens` | float/null | Mean of `reasoning_tokens` over `n_valid` (null if all rows reported null reasoning) |
| `total_cost_usd` | float | Sum of all non-null `cost_usd` for this config (across all 200 attempted rows, not just `n_valid`) |
| `mean_cost_per_call` | float | `total_cost_usd / n_valid` |
| `latency_p50_s` | float | Median per-call wall-clock seconds |
| `latency_p95_s` | float | 95th-percentile per-call wall-clock seconds |

## What is NOT included (deliberately)

- **Bootstrap CIs** — would balloon to 50+ cols; user asked to avoid bloat. Compute downstream from `trials.csv` if needed.
- **Per-bucket / per-source breakdowns** — discussed in `report.md` prose only, not in the CSV.
- **Confusion counts at ≥1** — derivable from `recall_at_1` + `specificity_at_1` + `n_valid` and the global human signal-rate.
- **Both Pearson and Kendall** — Spearman covers the rank-robustness use case adequately.

## Source JSONs (read-only inputs)

| Source file | Configs extracted from it |
|---|---|
| `experiments/results/judge_vs_human_gradingbench_20260505_20260505_050213.json` | gemini-3-flash/default, deepseek-v4-pro/default, deepseek-v4-flash/default, gpt-5.4-nano/xhigh |
| `experiments/results/judge_v4flash_noreason_20260505_20260505_063740.json` | deepseek-v4-flash/reasoning_off |
| `experiments/results/judge_gemma4_31b_20260505_20260505_064650.json` | gemma-4-31b-it/default |
| `experiments/results/judge_gemma4_31b_high_20260505_20260505_070206.json` | gemma-4-31b-it/high |
| `experiments/results/judge_gptoss_120b_minimal_20260505_20260505_080159.json` | gpt-oss-120b/default |
| `experiments/results/judge_gptoss_120b_xhigh_20260505_20260505_080159.json` | gpt-oss-120b/xhigh |
| `experiments/results/judge_gemini3_pro_20260505_20260505_121952.json` | gemini-3.1-pro/default |
