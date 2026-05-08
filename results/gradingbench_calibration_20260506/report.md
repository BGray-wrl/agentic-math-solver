# GradingBench Judge-Calibration — Report (2026-05-06)

This report compiles every model-as-judge evaluation we ran on GradingBench during 2026-05-05 into a single comparison. The dataset is in `trials.csv` (per-call) and `summary.csv` (per config); see `data_dictionary.md` for schema details.

**Setup.** Same n=200 random sample (seed=42) from `benchmarks/IMO-bench/gradingbench.csv`, same hardened judge prompt `prompts/pipeline/judge_gt.md` (output restricted to {0, 1, 6, 7}), 10 (model × reasoning_config) configurations. Human scores are the gradingbench `Points` column (0–7).

The user's primary question: **how well do these judges replicate the human pass/fail verdict at IMO's ≥6/7 threshold?** Secondary: how well do they detect **any signal at all** (≥1) vs dead-zero, and how do they correlate continuously?

## Headline table — sorted by `pass_agree_at_6` (the priority metric)

| Judge | Reasoning | n | **pass≥6 agree** | recall | spec | prec | F1 | Pearson r | mean Δ | $ total | $/call | p50 lat |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **gpt-5.4-nano** | xhigh | 196 | **89.3%** | 70% | **98%** | **93%** | 0.800 | 0.711 | -0.95 | $7.26 | $0.0370 | 152s |
| **deepseek-v4-pro** | default | 198 | **88.9%** | 83% | 92% | 83% | **0.825** | 0.756 | -0.75 | $2.97 | $0.0150 | 299s |
| **deepseek-v4-flash** | default | 199 | 87.4% | 79% | 91% | 81% | 0.800 | 0.756 | -0.80 | **$0.77** | **$0.0039** | 81s |
| gemini-3.1-pro | default | 199 | 86.4% | **95%** | 82% | 71% | 0.816 | **0.872** | **+0.13** | $6.93 | $0.0348 | **22s** |
| gpt-oss-120b | xhigh | 178 | 84.3% | 90% | 82% | 70% | 0.788 | 0.770 | +0.21 | $0.39 | $0.0022 | 62s |
| deepseek-v4-flash | reasoning_off | 192 | 80.7% | 56% | 92% | 78% | 0.654 | 0.591 | -1.36 | $0.30 | $0.0015 | 13s |
| gemma-4-31b-it | high | 200 | 79.0% | 92% | 73% | 61% | 0.734 | 0.776 | +0.55 | $0.75 | $0.0038 | 126s |
| gpt-oss-120b | default | 199 | 71.9% | 74% | 71% | 53% | 0.622 | 0.513 | +0.11 | $0.17 | $0.0008 | 9s |
| gemma-4-31b-it | default | 200 | 65.5% | 98% | 50% | 48% | 0.642 | 0.629 | +1.53 | $0.42 | $0.0021 | 19s |
| gemini-3-flash | default | 200 | 64.0% | 98% | 48% | 47% | 0.633 | 0.606 | +1.65 | $3.24 | $0.0162 | 4s |

**Three top tiers emerge at the ≥6 threshold:**

1. **89%+ tier:** gpt-5.4-nano @ xhigh and deepseek-v4-pro. Both are slow (150–300s p50) and expensive ($3–7 / 200 decisions). nano leans toward high-precision conservatism (precision 93%, but recall only 70%); v4-pro is the most balanced single judge here (rec 83 / prec 83 / F1=0.825 — best F1 in the set).
2. **84–87% tier:** v4-flash, gemini-3.1-pro, gpt-oss-120b @ xhigh. All cheaper. v4-flash and gpt-oss-xhigh are the cost-effective sweet spot. gemini-3.1-pro is the best on signal/correlation but trails on the binary ≥6 metric due to lenient over-passing (recall 95% at the cost of precision 71%).
3. **Below 80%:** v4-flash with reasoning forcibly off, gemma-high, gpt-oss-default, gemma-default, gemini-3-flash. All have either non-reasoning architecture or have reasoning crippled. Gemma-default and gemini-3-flash are functionally identical lenient rubber-stamps (98% recall, ~48% precision).

## Same models — sorted by `signal_agree_at_1` (any-signal detection)

The ≥1 boundary asks "did the response detect any meaningful progress at all, vs dead-zero?" Useful when filtering out totally hopeless attempts.

| Judge | Reasoning | n | **signal≥1 agree** | recall | spec | prec | F1 | $ total |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **gemini-3.1-pro** | default | 199 | **83.4%** | 88% | 73% | 88% | **0.879** | $6.93 |
| **gemma-4-31b-it** | high | 200 | **81.0%** | 91% | 59% | 83% | 0.867 | $0.75 |
| gemma-4-31b-it | default | 200 | 77.0% | 84% | 62% | 83% | 0.832 | $0.42 |
| gpt-oss-120b | xhigh | 178 | 76.4% | 89% | 51% | 79% | 0.835 | $0.39 |
| gemini-3-flash | default | 200 | 75.5% | 85% | 56% | 80% | 0.824 | $3.24 |
| gpt-5.4-nano | xhigh | 196 | 73.0% | 84% | 50% | 78% | 0.807 | $7.26 |
| deepseek-v4-pro | default | 198 | 70.2% | 60% | 91% | 93% | 0.733 | $2.97 |
| gpt-oss-120b | default | 199 | 70.9% | 70% | 72% | 84% | 0.766 | $0.17 |
| deepseek-v4-flash | default | 199 | 66.3% | 54% | 92% | 94% | 0.685 | $0.77 |
| deepseek-v4-flash | reasoning_off | 192 | 59.4% | 46% | 88% | 90% | 0.610 | $0.30 |

**The ranking flips substantially.** The DeepSeek family — leaders on ≥6 — ranks *below* the Google family on ≥1. Why: DeepSeek judges deflate (mean Δ −0.75 to −1.36), so they often score 0 when the human gave partial credit (e.g. human=2, judge=0). Conversely, gemini-3.1-pro and the gemma family have positive bias and over-call signal, which happens to be aligned with "is there *anything* here?" Gemini-3.1-pro is the only judge above 80% on **both** metrics simultaneously.

## Calibration table — sorted by `pearson_r` (continuous correlation)

| Judge | Reasoning | n | **Pearson r** | Spearman | mean \|Δ\| | mean Δ | exact_raw | exact_bucketed |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **gemini-3.1-pro** | default | 199 | **0.872** | **0.843** | **0.81** | +0.13 | **60.8%** | **65.8%** |
| gemma-4-31b-it | high | 200 | 0.776 | 0.761 | 1.14 | +0.55 | 57.0% | 60.0% |
| gpt-oss-120b | xhigh | 178 | 0.770 | 0.733 | 1.11 | +0.21 | 55.6% | 57.9% |
| deepseek-v4-pro | default | 198 | 0.756 | 0.734 | 1.21 | -0.75 | 53.5% | 58.6% |
| deepseek-v4-flash | default | 199 | 0.756 | 0.710 | 1.23 | -0.80 | 55.3% | 57.8% |
| gpt-5.4-nano | xhigh | 196 | 0.711 | 0.660 | 1.41 | -0.95 | 40.3% | 45.4% |
| gemma-4-31b-it | default | 200 | 0.629 | 0.647 | 1.87 | +1.53 | 49.5% | 49.5% |
| gemini-3-flash | default | 200 | 0.606 | 0.629 | 1.98 | +1.65 | 48.0% | 48.0% |
| deepseek-v4-flash | reasoning_off | 192 | 0.591 | 0.538 | 1.76 | -1.36 | 43.8% | 48.4% |
| gpt-oss-120b | default | 199 | 0.513 | 0.531 | 1.89 | +1.89 | 46.7% | 49.7% |

**On continuous calibration, gemini-3.1-pro is in a class of its own** — r=0.872 is +0.10 ahead of the next-best (gemma-high at 0.776), with the smallest mean \|Δ\| (0.81 vs everyone else >1.1) and the most-calibrated bias (+0.13, vs others' ±0.5–1.7). It's also the only judge whose `exact_match_raw` exceeds 60% — but see the granularity caveat below for context.

## The granularity gap

The hardened `judge_gt.md` prompt restricts judges to **{0, 1, 6, 7}**. Human scores in our n=200 sample are distributed:

| human_score | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| count | 73 | 31 | 5 | 4 | 13 | 14 | 8 | 52 |

**36 of 200 records (18%) have `human_score ∈ {2, 3, 4, 5}` — a value the judges literally cannot emit.** This caps `exact_match_raw` at 82% even for an oracle judge. So `exact_match_raw` numbers should be read with that ceiling in mind. **`pass_agree_at_6`, `signal_agree_at_1`, and all confusion metrics use raw `human_score` and binarize, so they're unaffected.** The `exact_match_bucketed` metric (which maps human → nearest of {0,1,6,7}) sidesteps the ceiling.

## Reasoning on/off contrast

Three pairs let us isolate the effect of the reasoning param holding model constant:

| Model pair | metric | OFF/default | ON | Δ |
|---|---|---:|---:|---:|
| **gemma-4-31b-it** (default→high) | pass≥6 | 65.5% | 79.0% | **+13.5 pp** |
| | signal≥1 | 77.0% | 81.0% | +4.0 pp |
| | pearson r | 0.629 | 0.776 | **+0.147** |
| | mean Δ | +1.53 | +0.55 | -0.98 (less inflation) |
| | $ cost | $0.42 | $0.75 | +79% |
| **gpt-oss-120b** (default→xhigh) | pass≥6 | 71.9% | 84.3% | **+12.4 pp** |
| | signal≥1 | 70.9% | 76.4% | +5.5 pp |
| | pearson r | 0.513 | 0.770 | **+0.257** |
| | mean Δ | +0.11 | +0.21 | almost no change |
| | $ cost | $0.17 | $0.39 | +129% |
| **deepseek-v4-flash** (default→reasoning_off, *reverse direction*) | pass≥6 | 87.4% | 80.7% | **−6.7 pp** |
| | signal≥1 | 66.3% | 59.4% | −6.9 pp |
| | pearson r | 0.756 | 0.591 | **−0.165** |
| | mean Δ | -0.80 | -1.36 | -0.56 (more deflation) |
| | $ cost | $0.77 | $0.30 | -61% |

**Reasoning is consistently worth +7 to +13 percentage points of `pass_agree_at_6`** and +0.15 to +0.26 of Pearson r, at a cost of roughly 1.5–3× the dollars. The direction is symmetric: turning it on improves accuracy on lenient-default models (gemma, gpt-oss); turning it off degrades accuracy on strict-default models (v4-flash). For judging math proofs, **reasoning on is essentially free in terms of decision quality** — the cost increase is small in absolute terms.

## Cost / accuracy frontier

Per-call dollars vs `pass_agree_at_6`:

| Tier | Configurations |
|---|---|
| **Best $/`pass_agree_at_6`** (under $0.005/call, ≥84%) | gpt-oss-120b @ xhigh ($0.0022, 84.3%); deepseek-v4-flash @ default ($0.0039, 87.4%); gemma-4-31b-it @ high ($0.0038, 79.0%) |
| **Premium reasoning judges** ($0.015–0.037/call, 86–89%) | deepseek-v4-pro ($0.015, 88.9%); gemini-3.1-pro ($0.035, 86.4%); gpt-5.4-nano @ xhigh ($0.037, 89.3%) |
| **Avoid** (no reasoning, 64–73%) | gemini-3-flash ($0.016, 64.0% — the worst $/quality); gemma @ default ($0.002, 65.5%); gpt-oss @ default ($0.001, 71.9%); v4-flash reasoning_off ($0.0015, 80.7%) |

**Best on signal_agree_at_1 per dollar:** gemma-4-31b-it @ high ($0.0038, 81.0%) — gemini-3.1-pro is the absolute leader (83.4%) but at 9× the cost.

**Best Pearson r per dollar:** gemma-4-31b-it @ high (r=0.776, $0.75 total). For the absolute best correlation, gemini-3.1-pro at r=0.872 / $6.93 is the only choice.

## Limitations

- **Single random seed (=42)** — no per-config variance estimate. To bootstrap confidence intervals downstream, resample over the 200 grading_ids in `trials.csv`.
- **Single judge prompt** — `judge_gt.md` is fixed across all configs; results may shift with a different rubric or scoring scale.
- **30 unique problems** in the source benchmark, with multiple grading instances each — there's clustering at the problem level that this analysis doesn't account for.
- **No held-out split** — any ensemble or threshold selection done downstream should split out a test fraction.
- **Pricing is approximate** — per-call `cost_usd` was computed at run time using rough per-judge `$/M` rates (see `pricing_snapshot.json`); OpenRouter actual billing may differ at the percent level.
- **gpt-5.4-nano @ xhigh dropped 4/200 calls** to litellm timeouts (n_valid=196). gpt-oss-120b @ xhigh dropped 22/200 (n_valid=178) for the same reason. Per-config metrics use `n_valid`, so these don't bias the ratios — but the cost figures sum across all attempted (including failed) calls.
- **No frontier closed-source baselines** beyond gemini-3.1-pro — Claude Opus 4.7, GPT-5.4-full @ xhigh, and others are still unmeasured here.
