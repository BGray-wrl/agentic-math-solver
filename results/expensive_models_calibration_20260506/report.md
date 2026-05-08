# Expensive-Models 12-Problem Calibration — Report (2026-05-06)

This is the smaller, secondary dataset: a probe of 4 frontier models at default reasoning effort on 12 problems from the AnswerBench stratified subset. Originally collected on 2026-05-04 to answer "is any of these expensive models worth using?" — the short version is "not at default effort." See the larger AnswerBench-50 calibration for the corrected picture once xhigh effort is enabled.

## Headline table

| Model | Acc | $/run | $ total | mean_lat | acc%/$ | Notes |
|---|---|---|---|---|---|---|
| **kimi-k2.6** | **10/10 (100%)** | $0.0971 | $0.97 | 641s | 1,032 | 2 trials dropped (hung past 49-min cap) — 10/10 only on completed |
| qwen3.6-max-preview | 11/12 (92%) | $0.1722 | $2.07 | 656s | 532 |  |
| gemini-3.1-pro-preview | 10/12 (83%) | $0.2503 | $3.00 | 174s | 333 |  |
| **gpt-5.4** | **6/12 (50%)** | $0.0539 | $0.65 | 51s | 927 | At default effort — see caveats |

## Findings

1. **kimi-k2.6 perfect score on the 10 it completed.** No reasoning param required — it reasons by default and produced 27.7K mean output tokens. The two dropped trials (combinatorics-028 and combinatorics-084) both hung past the 49-min wall-clock cap; the model was apparently still reasoning. Whether it would have eventually solved them or hung indefinitely is unknown.

2. **qwen3.6-max-preview matches accuracy (92%) of v4-flash at 30× the cost.** Strictly dominated for the same accuracy bucket.

3. **gemini-3.1-pro-preview disappointing at default** (83%, $0.25/run). Even on this small sample, dominated by deepseek-v4-pro at $0.019/run (the AnswerBench-50 dataset shows v4-pro at 94%). At default effort, gemini-3.1-pro doesn't pay back its 12× input pricing.

4. **gpt-5.4 6/12 = the surprise** — but a known artifact at default effort. The follow-up xhigh test showed gpt-5.4 jumps from 6/12 to 11/12 effective with `reasoning.effort=xhigh`. **The 50% number here is NOT representative of gpt-5.4's capability**, only of its default-effort behavior. See `results/answerbench_calibration_20260506/` for xhigh data on the gpt-5.4 family (nano/mini/full).

## Decision

After this 12-problem probe, the practical takeaways are:

- Don't blind-test at default effort for OpenAI's gpt-5 series — it underperforms.
- kimi-k2.6 is the only one of these four worth a second look on a harder benchmark; promising for combinatorics specifically.
- gemini-3.1-pro and qwen3.6-max are dominated by cheaper alternatives even at this small sample.

## Caveats

1. **Default effort only.** All four models were run with NO `reasoning` parameter. For the gpt-5 family this is a major handicap — see the AnswerBench-50 calibration for what gpt-5.4 does at xhigh.
2. **Small sample (n=12).** Order-of-magnitude conclusions only.
3. **kimi at n=10 not 12** — 2 trials hung and were killed.

## Files

- `trials.csv` — 48 rows (4 models × 12 PIDs)
- `trials.jsonl` — full records
- `summary.csv` — 4 rows
- `data_dictionary.md`
- `pricing_snapshot.json`

Source: `experiments/results/expensive_models_compare_20260504_20260505_012855_partial.json`. Original writeup: `agent_log.md` lines 1422-1476.
