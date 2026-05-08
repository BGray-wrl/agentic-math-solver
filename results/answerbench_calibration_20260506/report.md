# AnswerBench-50 Calibration — Report (last updated 2026-05-07)

This report compiles every AnswerBench-50 model evaluation we ran on May 4–7, 2026 into a single comparison. The dataset is in `trials.csv` (per-problem) and `summary.csv` (per model-config). The 50-problem stratified subset is the same across all runs (12 Algebra / 13 Combinatorics / 12 Geometry / 13 Number theory; seed=42; sourced from `benchmarks/IMO-bench/answerbench_v2.csv`). Judge: `google/gemini-3.1-flash-lite-preview`. Generate-only, pass@1.

## Headline table — 14 model/config combinations sorted by accuracy

| Model | Config | Acc | $/run | $ total | mean_lat | acc%/$ | Notes |
|---|---|---|---|---|---|---|---|
| **deepseek-v4-pro** | `default` | **47/50 (94%)** | $0.0185 | $0.93 | 723s | 5,080 |  |
| **gpt-5.4-nano** | `xhigh` | **45/49 (92%)** | $0.0560 | $2.75 | 1243s | 1,639 | 1 trial dropped (`geometry-021` hung >70 min) |
| **gemini-3-flash-preview** | `xhigh_effective_synthesized` | **45/50 (90%)** | $0.0337 | $1.69 | 51s | 2,671 | **SYNTHESIZED**: 37 default + 13 xhigh retests |
| **deepseek-v4-flash** | `default` | **44/50 (88%)** | $0.0055 | $0.28 | 357s | **15,901** |  |
| qwen3.6-35b-a3b | `default` | 40/50 (80%) | $0.0218 | $1.09 | 139s | 3,677 |  |
| qwen3.6-plus | `default` | 39/50 (78%) | $0.0739 | $3.70 | 739s | 1,056 |  |
| gemini-3.1-pro-preview | `default` | 39/50 (78%) | $0.2584 | $12.92 | 233s | 302 | NEW 2026-05-07: 12 PIDs from expensive-models 2026-05-04 + 38 PIDs from new run |
| gpt-oss-120b | `xhigh` | 37/50 (74%) | $0.0057 | $0.29 | 565s | 12,921 |  |
| gemini-3-flash-preview | `default` | 37/50 (74%) | $0.0100 | $0.50 | 18s | 7,389 |  |
| gemma-4-31b-it | `default` | 34/50 (68%) | $0.0015 | $0.08 | 235s | 45,585 | Default ≡ no reasoning emitted (per probe) |
| gemma-4-31b-it | `xhigh` | 27/43 (63%) | $0.0034 | $0.14 | 707s | 18,759 | 7 trials dropped (429 from upstream) |
| gemini-3-flash-preview | `xhigh` | 8/13 (62%) | $0.0976 | $1.27 | 138s | 631 | Tested only on 13 prior failures; rest = `not_tested_at_this_config` |
| gpt-oss-120b | `default` | 29/50 (58%) | $0.0011 | $0.06 | 191s | **51,687** | Default emits ~2K implicit reasoning tokens (per probe) |
| deepseek-v4-flash | `reasoning_off` | 25/50 (50%) | $0.0020 | $0.10 | 146s | 25,289 | `reasoning.enabled=false` explicitly |

Bold rows are the absolute-accuracy ≥85% tier (the "high accuracy" cluster).

## Per-category accuracy

| Model | Config | Algebra | Combinatorics | Geometry | Number theory |
|---|---|---|---|---|---|
| deepseek-v4-pro | `default` | 11/12 | 12/13 | **12/12** | 12/13 |
| gpt-5.4-nano | `xhigh` | 11/12 | 12/13 | 11/11 | 11/13 |
| gemini-3-flash-preview | `xhigh_effective` | 11/12 | 9/13 | **12/12** | **13/13** |
| deepseek-v4-flash | `default` | 10/12 | 10/13 | **12/12** | 12/13 |
| qwen3.6-35b-a3b | `default` | 10/12 | 11/13 | 10/12 | 9/13 |
| qwen3.6-plus | `default` | 10/12 | 8/13 | 11/12 | 10/13 |
| gemini-3.1-pro-preview | `default` | 11/12 | 8/13 | 11/12 | 9/13 |
| gpt-oss-120b | `xhigh` | 8/12 | 8/13 | 10/12 | 11/13 |
| gemini-3-flash-preview | `default` | 10/12 | 8/13 | 8/12 | 11/13 |
| gemma-4-31b-it | `default` | 6/12 | 7/13 | 10/12 | 11/13 |
| gemma-4-31b-it | `xhigh` | 5/12 | 5/9 | 6/11 | 11/11 |
| gemini-3-flash-preview | `xhigh` (13 only) | 1/2 | 1/5 | 4/4 | 2/2 |
| gpt-oss-120b | `default` | 7/12 | 5/13 | 9/12 | 8/13 |
| deepseek-v4-flash | `reasoning_off` | 4/12 | 5/13 | 8/12 | 8/13 |

Geometry is uniformly easy (most models hit 10-12/12). Combinatorics is the differentiator — both v4-pro and v4-flash @ default lead the field there, and gemma's collapse in combinatorics (5/9 valid at xhigh) is what drags its xhigh result below baseline.

## Default vs xhigh (where we have both)

| Model | default | xhigh | delta | Real story |
|---|---|---|---|---|
| **gpt-oss-120b** | 29/50 (58%) | 37/50 (74%) | **+16 pp** | Reasoning works as advertised. Out tokens 6.3K → 31.8K. Spend 5× ($0.06 → $0.29) for +16 pp. |
| **gemini-3-flash-preview** | 37/50 (74%) | 45/50 (90%, synth) | **+16 pp** | Big lift, also lowest latency in the high-accuracy tier (51s mean). Synth caveat applies. |
| **gemma-4-31b-it** | 34/50 (68%) | 27/43 (63%) | **−5 pp** | Reasoning-capable per the API but not reasoning-trained. Reasoning hurts here. |
| **deepseek-v4-flash** | 44/50 (88%) | 25/50 reasoning_off (50%) | -38 pp | Reasoning IS the value. Cutting it = cliff. |

## Findings

1. **Reasoning effort is the dominant variable, not the model identifier.** The same model can move 16-38 percentage points based on whether reasoning is on. The original 7-model writeup (lines 1005-1036 of `agent_log.md`) ranked models against each other at "default" effort, which is not a fair test for models that need to be told to think (gpt-5 family) and unfair-in-reverse for models that reason eagerly by default (v4-flash, deepseek-v4-pro).

2. **Three models tie/exceed 90% accuracy**: v4-pro (94%), nano-xhigh (92%), gemini-3-flash-xhigh-effective (90%). Two of these were "off the table" at default-effort.

3. **v4-flash @ default has the best `acc%/$` in the high-accuracy tier** at 15,901 (88% / $0.0055). The next-best high-tier model, v4-pro (94%) at 5,080, is 3× less efficient. Anything more accurate than v4-flash costs significantly more per problem.

4. **gpt-oss-120b @ xhigh is the new mid-tier value** at 12,921 acc%/$ (74%, $0.0057/run) — it dethrones gemma-4-default (45,585 at 68%) for any use case where 74% accuracy matters more than 68%.

5. **The cheapest models (gpt-oss @ default, gemma @ default) win pure $/accuracy at the bottom of the accuracy stack** but at 58-68% they're useful only as bulk ideators / coverage roles.

7. **gemini-3.1-pro-preview at default is strictly dominated** (added 2026-05-07). 39/50 (78%) at $0.2584/run = 302 acc%/$ — same accuracy as qwen3.6-plus but 3.5× the cost, and far behind v4-pro (94% at $0.019/run, 17× more efficient at higher accuracy). This is the **default-effort** number; the gpt-5 family showed default-effort can drastically understate a model's capability, so xhigh on gemini-3.1-pro is the obvious next probe before writing it off completely.

6. **Latency is decoupled from accuracy at this point**:
   - gemini-3-flash-preview is 7-25× faster than v4-pro/nano-xhigh at the same accuracy.
   - nano-xhigh has the highest mean latency (1243s) but a 456s median — heavy tail dominated by ~2 outlier problems.

## Caveats — what the dataset does NOT do

1. **Pass@1, single seed.** Differences within ~3 percentage points are inside noise.

2. **The synthesized `xhigh_effective_synthesized` row is NOT a real run.** It blends 37 default-correct PIDs (assumed unchanged at xhigh) with 13 actual xhigh retests. Real `gemini-3-flash @ xhigh` data is ONLY the 13-PID retest row (8/13).

3. **Judge errors are NOT corrected in this dataset.** For example, `combinatorics-026` has GT=`847288609444` and several models answered `3^25+1` (which equals GT). The judge marked some of those as incorrect. `score` reflects the raw judge output. See `verdict_raw` in `trials.csv` to inspect.

4. **`reasoning_off` only exists for v4-flash.** Other models' "default" is the closest analog but is not equivalent — see `notes` column for per-model default behavior caveats.

5. **`reasoning_tokens` is null for the 350 original-run rows** because the original generator script didn't capture the field.

6. **Costs are generator-only** (excluding judge), computed from the OpenRouter pricing snapshot in `pricing_snapshot.json` (fetched at build time on 2026-05-06).

## Methodology

- **Source files** — 6 result JSONs under `experiments/results/` (see `data_dictionary.md` for the full mapping).
- **Build script** — `experiments/build_answerbench_calibration_20260506.py`. No values are hand-entered; everything in `trials.csv` is sourced from those JSONs and missing/dropped trials are explicitly marked with an `error`.
- **Pricing** — fetched live from `https://openrouter.ai/api/v1/models` at build time. `est_cost_usd = prompt_tokens × p_in + completion_tokens × p_out` per row, where `p_in` and `p_out` are from the snapshot.
- **acc%/$ ratio** — `accuracy × 100 ÷ cost_per_run_usd`. Higher is better.

## Decision matrix

| Use case | Pick |
|---|---|
| **Bulk ideator / coverage** | gpt-oss-120b @ default (51,687 acc%/$, 58%) |
| **Cost-efficient workhorse at ≥85%** | **deepseek-v4-flash @ default** ($0.006/run, 88%) |
| **Lowest latency at ≥85%** | gemini-3-flash @ xhigh (51s mean, ~90%) — synth caveat |
| **Top accuracy** | deepseek-v4-pro @ default (94%) or gpt-5.4-nano @ xhigh (92%); pick by latency tolerance |
| **Avoid** | qwen3.6-plus (strictly dominated by qwen-35b); gemini-3.1-pro @ default (strictly dominated; 78% at $0.26/run); v4-flash @ reasoning_off (50%); gemma-4 @ xhigh (worse than gemma default) |

## Files in this directory

- `trials.csv` — long format, 650 rows
- `trials.jsonl` — same data + final_solution + reasoning_text
- `summary.csv` — 14 rows
- `data_dictionary.md` — column-by-column schema
- `pricing_snapshot.json` — OpenRouter pricing used to compute `est_cost_usd`
- `report.md` — this file
