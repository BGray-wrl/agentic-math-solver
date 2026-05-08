# Expensive-Models 12-Problem Calibration — Data Dictionary

This is the smaller, secondary dataset capturing the May 4 frontier-model probe: 4 expensive models on a 12-problem stratified subset of the same AnswerBench-50 stratified set. Originally tested at default reasoning effort to answer "should we even consider these models for the pipeline?"

## Files

- **`trials.csv`** — long format, **48 rows** = 4 models × 12 PIDs. Trials that hung past the 49-min wall-clock cap are present with `score=null` and a non-null `error`.
- **`trials.jsonl`** — same data with `final_solution` + `reasoning_text` where present.
- **`summary.csv`** — 4 rows.
- **`pricing_snapshot.json`** — OpenRouter pricing snapshot at build time.

## Models

All four were run at **default reasoning effort** (no `reasoning` param sent):

| Model | OpenRouter ID | $/M (in) | $/M (out) |
|---|---|---|---|
| kimi-k2.6 | `moonshotai/kimi-k2.6` | from snapshot | from snapshot |
| qwen3.6-max-preview | `qwen/qwen3.6-max-preview` | | |
| gemini-3.1-pro-preview | `google/gemini-3.1-pro-preview` | | |
| gpt-5.4 | `openai/gpt-5.4` | | |

Pricing values are in `pricing_snapshot.json`.

## Problems

12 PIDs sub-sampled from the AnswerBench-50 stratified set (3 per category):

```
imo-bench-algebra-004, -012, -088
imo-bench-combinatorics-026, -028, -084
imo-bench-geometry-021, -029, -036
imo-bench-number_theory-045, -049, -078
```

## Columns

`trials.csv` and `summary.csv` share the same column schema as the AnswerBench-50 dataset — see `../answerbench_calibration_20260506/data_dictionary.md` for column-by-column definitions. The only differences:

- `model_config` is always `default` (only one config tested).
- 2 trials missing for kimi-k2.6 (`combinatorics-028`, `combinatorics-084` hung past the 49-min cap and were killed). They appear with `score=null`, `error="trial killed (hung in 49-min wall-clock cap)"`.

## Source file

- `experiments/results/expensive_models_compare_20260504_20260505_012855_partial.json` (46 trials) — see agent_log.md lines 1422-1476 for the original writeup.

## Caveats

1. **Default effort across all four models.** This was the configuration we initially tested. We later discovered (see the AnswerBench-50 calibration report) that gpt-5.4 at default effort emits ~3.6K out tokens with minimal reasoning and dramatically underperforms its xhigh-effort version (50% → 92% on the AnswerBench-50 subset). The 50% number for gpt-5.4 in this dataset is therefore NOT representative of what gpt-5.4 can do — see the AnswerBench-50 calibration for the corrected picture.
2. **Small sample (12).** Differences within ~10 percentage points are within noise.
3. **kimi-k2.6 is on n=10**, not 12. The 100% there is "10/10 with 2 dropped".
