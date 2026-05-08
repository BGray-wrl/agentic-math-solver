# AnswerBench-50 Calibration Dataset — Data Dictionary

This dataset compiles every AnswerBench-50 evaluation we've run (May 4–7, 2026)
into a single normalized matrix: 13 model/reasoning-effort combinations × the same
50-problem stratified subset. It includes results from 6 separate runs which
were originally stored in 6 different JSON files with slightly different schemas.

## Files

- **`trials.csv`** — long format, **650 rows** = 13 model_configs × 50 PIDs. One row per (model, model_config, problem_id) attempt. Trials that were not run or were dropped are present with `score=null` and a non-null `error` so the matrix is complete-by-config.
- **`trials.jsonl`** — same data, one JSON object per line, plus `final_solution` and `reasoning_text` fields where available.
- **`summary.csv`** — wide format, 14 rows = 13 model_configs + 1 synthesized row for "gemini-3-flash @ xhigh effective on 50".
- **`pricing_snapshot.json`** — OpenRouter `/api/v1/models` pricing captured at build time. All `est_cost_usd` and summary `total_cost_usd` values are computed from this.

## How `model_config` is set

| Value | Meaning |
|---|---|
| `default` | No reasoning param sent. The model uses its built-in default behavior. (gemma emits 0 reasoning tokens; gpt-oss emits ~2K; v4-flash reasons fully.) |
| `xhigh`   | `reasoning: {"effort": "xhigh"}` was sent — max reasoning effort. |
| `reasoning_off` | `reasoning: {"enabled": false}` was sent — explicit OFF. Only deepseek-v4-flash has this row. |
| `xhigh_effective_synthesized` | Summary-only row. NOT a real run. Composite of: 37 PIDs default-correct (assumed unchanged at xhigh) + 13 PIDs from the gemini-3-flash xhigh retest. |

## `trials.csv` columns

| Column | Type | Meaning |
|---|---|---|
| `model` | str | Canonical short name, e.g. `gpt-5.4-nano` |
| `model_id` | str | Full provider ID without `openrouter/` prefix, e.g. `openai/gpt-5.4-nano` |
| `model_config` | str | `default`, `xhigh`, or `reasoning_off` (see above) |
| `reasoning_param_json` | str/null | Verbatim JSON of the `reasoning` param sent to OpenRouter. `null` for default. |
| `problem_id` | str | e.g. `imo-bench-algebra-032` |
| `category` | str | One of: Algebra, Combinatorics, Geometry, Number theory |
| `subcategory` | str | Sub-category from `answerbench_v2.csv` if present |
| `short_answer` | str | Ground-truth answer (used by the judge) |
| `score` | int/null | `1`=correct, `0`=incorrect, `null`=not graded or trial dropped |
| `verdict_raw` | str | Raw judge response (truncated to ≤1024 chars) |
| `gen_elapsed_s` | float | Generator wall-clock seconds |
| `judge_elapsed_s` | float | Judge wall-clock seconds |
| `total_elapsed_s` | float | Trial total wall-clock seconds |
| `prompt_tokens` | int | Input tokens reported by OpenRouter for the generator call |
| `completion_tokens` | int | Output tokens (includes reasoning tokens for OpenAI-style models) |
| `reasoning_tokens` | int/null | Internal reasoning tokens. `null` for runs that predated the field (the original 7-model run). |
| `total_tokens` | int | `prompt_tokens + completion_tokens` |
| `judge_prompt_tokens` | int | Judge call input tokens |
| `judge_completion_tokens` | int | Judge call output tokens |
| `est_cost_usd` | float/null | `prompt_tokens × p_in + completion_tokens × p_out` from authoritative OpenRouter pricing. Excludes the judge cost (judge call is run on a different key and tracked elsewhere). |
| `judge_model` | str | Always `google/gemini-3.1-flash-lite-preview` here |
| `run_date` | str | ISO date of the source experiment |
| `source_file` | str | Origin JSON filename for traceability |
| `error` | str/null | Non-null if the trial failed, was dropped, or was never attempted |

## `summary.csv` columns

| Column | Meaning |
|---|---|
| `model`, `model_config`, `model_id` | Identifying keys |
| `n_trials` | total rows in `trials.csv` for this group |
| `n_valid` | rows with `score is not null` |
| `n_correct` | sum of scores |
| `accuracy` | `n_correct / n_valid` |
| `acc_by_category` | JSON dict, e.g. `{"Algebra":"11/12","Combinatorics":"12/13",...}` |
| `mean_gen_lat_s`, `median_gen_lat_s` | from valid trials |
| `mean_prompt_tokens`, `mean_completion_tokens`, `mean_reasoning_tokens` | from valid trials |
| `total_cost_usd` | sum of `est_cost_usd` across valid trials |
| `cost_per_run_usd` | `total_cost_usd / n_valid` |
| `acc_pct_per_dollar` | `accuracy*100 / cost_per_run_usd` (efficiency metric) |
| `price_in_per_M`, `price_out_per_M` | OpenRouter pricing in USD/M tokens (snapshot date in `pricing_snapshot.json`) |
| `run_date`, `source_file` | provenance |
| `notes` | free text — error counts, default-behavior caveats, "SYNTHESIZED" flag |

## Source files (origin → group)

| Source JSON (under `experiments/results/`) | Models / configs it contributes |
|---|---|
| `answerbench_compare_20260504_20260504_084012.json` | All 7 models @ `default` (deepseek-v4-pro, deepseek-v4-flash, qwen3.6-35b-a3b, qwen3.6-plus, gemini-3-flash-preview, gemma-4-31b-it, gpt-oss-120b) |
| `nano_xhigh_answerbench50_20260505_partial.json` | gpt-5.4-nano @ `xhigh` (49 valid + 1 placeholder for `geometry-021` which hung) |
| `gemini3flash_xhigh_retest_20260505_20260505_064305.json` | gemini-3-flash-preview @ `xhigh` on the 13 PIDs it failed at default. Other 37 PIDs are `not_tested_at_this_config` placeholders. |
| `v4flash_noreasoning_answerbench50_20260505_partial.json` | deepseek-v4-flash @ `reasoning_off` (50 valid) |
| `cheap_xhigh_answerbench50_20260505_20260505_081826.json` | gpt-oss-120b @ `xhigh` (50 valid) and gemma-4-31b-it @ `xhigh` (43 valid + 7 trials with `429 rate-limit` error captured in source) |
| `gemini3pro_answerbench50_remaining_20260507_20260507_075148.json` | gemini-3.1-pro-preview @ `default` on the 38 PIDs of the 50 not covered by the expensive-models probe (38 valid). |
| `expensive_models_compare_20260504_20260505_012855_partial.json` (filtered to gemini-3.1-pro-preview) | The 12 PIDs of the 50 that gemini-3.1-pro-preview was tested on during the 2026-05-04 expensive-models probe. Combined with the 38 above to give a full 50-PID gemini-3.1-pro/default row. |

## Counts

- 13 real (model, model_config) groups → 13 × 50 = 650 trial rows
- Of those, **valid (scored) trials**: 608. Breakdown of the 42 non-valid:
  - 1 nano-xhigh trial: `geometry-021` killed (hung >70 min)
  - 7 gemma-4 xhigh trials: 429 rate-limits from upstream provider
  - 37 gemini-3-flash xhigh trials: not tested at this config (only 13 retests done)
  - 0 missing for gemini-3.1-pro-preview default (12 from expensive-models source + 38 from the 2026-05-07 remainder run = 50/50 valid)

## Pricing methodology

All costs are computed at build time as `prompt_tokens × p_in + completion_tokens × p_out` where `p_in`/`p_out` come from a live snapshot of OpenRouter's `/api/v1/models` endpoint (date in `pricing_snapshot.json`). This means:

- **Cost includes reasoning tokens** — for OpenAI-style models (gpt-5, gpt-oss), `completion_tokens` already includes reasoning, and OpenRouter's `completion` price applies to the whole bucket.
- **Cost ignores judge spend** — judge calls run on a different key. We track judge token counts in the trials but don't roll them into the per-trial cost. The original answerbench writeup at line 1009 listed $6.69 total which DID include judge; this dataset's per-model costs are *generator-only*. To compare to that $6.69, sum all `est_cost_usd` for `default` rows here ($6.62 — close enough, small differences from pricing-snapshot drift).

## Caveats / what the dataset DOES NOT do

1. **Pass@1, single seed.** No re-runs for variance. Differences within a few percentage points are noise.
2. **The synthesized "xhigh_effective" row is not a real 50-trial run** — see `notes`. Use `gemini-3-flash-preview` `default` (37/50) and `xhigh` (8/13) rows for real data.
3. **Default ≠ reasoning_off** for all models. We have a true reasoning-off only for v4-flash. For other models, `default` is "whatever the model does without a reasoning param" — gemma=0 reasoning, gpt-oss=~2K, v4-flash=full.
4. **Judge model unchanged across all runs**: `google/gemini-3.1-flash-lite-preview`. Judge errors (e.g. on `combinatorics-026` where gemini-3-flash answered `3^25+1 = 847288609444 = GT` but was marked incorrect) are NOT corrected in this dataset — `score` reflects the original judge verdict. See `verdict_raw` for the raw text.
5. **`reasoning_tokens` is null for the 350 original-run rows** because the original generator didn't capture the field. It's present for all newer rows.
