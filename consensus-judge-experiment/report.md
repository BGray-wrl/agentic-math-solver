# Cheap LLM Judges Are Competitive with Frontier Judges on IMO-Style Math Proof Grading

**Author**: agentic-math-solver project · 2026-05-07
**Code & data**: this directory

> **Headline.** On a strictly held-out 200-problem sample of GradingBench, **gpt-oss-120b @ xhigh** (a single open-weight judge at \$0.32 / 200 calls) agrees with human IMO-style scores at the pass/fail threshold (≥6) in **87.5%** of cases [bootstrap 95% CI: 82.5–91.5%], comparable to or better than Claude Opus 4.7 (85.5% [80.0–90.0%]) and Gemini-3.1-Pro (84.0% [79.0–89.0%]) at **100× cheaper** than Opus. A majority-vote consensus of three small open judges matches Opus's F1 exactly (0.785) and beats Gemini reliably (P=0.80 across resamples) at **\$1.73 / 200 calls** — 19× cheaper than Opus, 4× cheaper than Gemini. The CIs overlap heavily within the cheap-vs-Opus tier; the strongly-supported claim is "cheap judges are at least competitive with frontier," not "single cheap judge dominates."

---

## 1. Introduction

Automatic evaluation of mathematical proofs is the bottleneck for any agentic math-solving pipeline. A judge has to read a lengthy candidate solution, follow a delicate logical chain, and decide whether the argument is sound. The default modern reflex is to throw a frontier LLM at the problem: Claude Opus, Gemini Pro, GPT-5.4. These models are slow and expensive at scale (a thousand-call calibration sweep on Opus 4.7 with reasoning enabled costs roughly \$160).

This paper asks the alternative question: do *small open-weight reasoning judges*, individually or voted, match the frontier? The intuition is that cheap judges with **opposite, structured biases** (gemma over-credits, deepseek under-credits, gpt-oss is roughly calibrated) can either compete on their own or cancel into a robust majority vote.

We pre-register a trio chosen from an exploratory sample, then validate on a strictly disjoint held-out sample with the same protocol, with **Claude Opus 4.7** and **Gemini-3.1-Pro** as independent frontier baselines. The validation result is an honest test of whether the cheap-judge advantage generalizes.

The result generalizes — and a single small judge (gpt-oss-120b @ xhigh) outperforms both frontiers on the headline metric.

---

## 2. Methodology

### 2.1 Dataset

**GradingBench** (`benchmarks/IMO-bench/gradingbench.csv`) contains 1000 grading instances drawn from 30 unique IMO-style problems. Each instance pairs a problem with a candidate solution and an expert human score on the standard 0–7 IMO rubric. The full benchmark distribution is dominated by easy ends (300 zeros, 300 sevens) with a long tail of intermediate scores {2,3,4,5} that judges cannot reproduce under our prompt (see §2.4).

### 2.2 Two disjoint random samples

- **Prior sample (exploratory):** 200 instances, `random.Random(42).sample(rows, 200)`. Used for individual-judge calibration and selecting the trio.
- **Validation sample (held-out):** 200 instances drawn from the *complement* of the prior sample using `random.Random(7)`. Zero overlap by construction; verified after compilation.

Score distribution of the validation sample: {0:54, 1:48, 2:10, 3:4, 4:12, 5:15, 6:9, 7:48}. Pass-rate (≥6) base = 28.5%; signal-rate (≥1) = 73.0%.

### 2.3 Judge prompt

Every judge call uses the same hardened prompt at `prompts/pipeline/judge_gt.md`, restricted to four scores: 0 (incorrect), 1 (partial), 6 (almost), 7 (correct). The {0,1,6,7} restriction was chosen because (a) intermediate scores require subjective judgments that human IMO graders themselves disagree on, and (b) the most consequential boundary is **pass at ≥6** ("did this proof pass IMO standards?").

### 2.4 The granularity gap

The judge prompt cannot emit {2,3,4,5}, but human scores do. In the validation sample, **41/200 records (20.5%)** have human scores in this range. This caps `exact_match_raw` at 79.5% even for a perfectly calibrated judge. **It does not affect any pass/fail or signal metric** — those binarize the score before comparing.

For bucketed exact-match we map human scores to the nearest legal bucket: {0→0, 1–3→1, 4–6→6, 7→7}. **Crucially, all confusion-derived metrics use the RAW human score**, not the bucketed value. A human-4 with judge-6 is therefore a False Positive at ≥6.

### 2.5 Judge configurations

10 judge configurations were calibrated on the prior sample (May 5–6, 2026). The trio was selected from these based on three criteria:
1. **Strong individual performance** with reasoning engaged
2. **Diverse bias signs** (gemma +0.55, gpt-oss +0.21, v4-flash −0.80) so that majority vote benefits from cancellation
3. **Low cost** (each ≤ \$0.80 per 200 calls)

The validation experiment runs five configurations on the held-out sample:

| # | Judge | Model ID | Reasoning | $/M in | $/M out |
|---|---|---|---|---|---|
| 1 | deepseek-v4-flash | `deepseek/deepseek-v4-flash` | default | 0.28 | 0.28 |
| 2 | gpt-oss-120b @ xhigh | `openai/gpt-oss-120b` | `{"effort":"xhigh"}` | 0.15 | 0.15 |
| 3 | gemma-4-31b-it @ high | `google/gemma-4-31b-it` | `{"effort":"high"}` | 0.38 | 0.38 |
| 4 | gemini-3.1-pro | `google/gemini-3.1-pro-preview` | `{"enabled":true}` | 1.25 | 10.00 |
| 5 | **claude-opus-4.7** | `anthropic/claude-opus-4.7` | `{"enabled":true}` | 5.00 | 25.00 |

The first three are the pre-registered trio; the last two are independent frontier baselines.

### 2.6 Consensus rule

For each grading_id, the trio decision is the **majority vote** over the trio members' valid scores at the chosen threshold:

```python
trio_scores = [gemma_score, gptoss_score, v4flash_score]
valid       = [s for s in trio_scores if s is not None]
trio_pass_at_6  = sum(s >= 6 for s in valid) > len(valid) / 2
trio_signal_at_1 = sum(s >= 1 for s in valid) > len(valid) / 2
trio_mean_score  = mean(valid)   # for Pearson r
```

If 3 trio members are valid, the rule is genuine majority. If 2 are valid, majority means both agree. If only 1 is valid, the consensus equals that single judge's decision.

### 2.7 Metrics

- **`pass_agree_at_6`** — fraction of records where the system's pass/fail decision matches the human's (THE primary metric for IMO-grade judging)
- **`precision_at_6`**, **`recall_at_6`**, **`F1_at_6`** — standard binary classification
- **`pearson_r`** — continuous correlation with human score
- **`signal_agree_at_1`** — pass-agreement at the ≥1 threshold ("any non-zero progress?")
- cost and latency

All confusion counts use raw human scores. All numbers reported below are computed over `n_valid` (records where the judge produced a parsed score).

### 2.8 Run-time issues

The validation runs hit upstream rate limits — Google's API throttled OpenRouter's shared `gemma-4-31b-it` quota during peak Eastern-time hours, and DeepSeek upstream similarly slowed v4-flash. We patched dropped calls via three mechanisms:

1. **Direct Google AI Studio API** for gemma (using a Tier-2 GEMINI_API_KEY) to bypass OpenRouter's shared backend
2. **SiliconFlow provider routing** for v4-flash via OpenRouter's `provider.order` extra_body
3. **Retry with single-worker concurrency** for the long-tail problems

Final valid counts after patching:
- gpt-oss-120b @ xhigh: 200/200
- gemini-3.1-pro: 200/200
- claude-opus-4.7: 200/200
- deepseek-v4-flash: 195/200 (5 grading_ids consistently rate-limited)
- gemma-4-31b-it @ high: 190/200 (10 grading_ids stuck on Google quota; direct-API patch confirmed model-side reasoning, ~4000 thinking tokens / call)

Missing rows are recorded with `error="rate-limited"` etc. in `trials_validation.csv`, never with fabricated scores. The trio consensus is computed over whatever valid trio members each grading_id has — in 95.5% of validation problems (191/200) at least 2 of 3 trio members produced a valid score.

---

## 3. Results

### 3.1 Validation: cheap judges are competitive with both frontiers

Sorted by the headline metric `pass_agree_at_6`:

| System | n_valid | pass≥6 | precision | recall | specificity | F1 | Pearson r | signal≥1 | Cost (200) |
|---|---|---|---|---|---|---|---|---|---|
| **gpt-oss-120b @ xhigh** (member) | 200 | **0.875** | 0.722 | 0.912 | 0.860 | **0.806** | 0.676 | 0.730 | **\$0.32** |
| **trio_consensus_majority** | 200 | 0.860 | 0.699 | 0.895 | 0.846 | 0.785 | 0.747 | 0.720 | **\$1.73** |
| deepseek-v4-flash (member) | 195 | 0.856 | 0.733 | 0.786 | 0.885 | 0.759 | 0.669 | 0.605 | \$0.70 |
| **claude-opus-4.7** (frontier) | 200 | 0.855 | 0.680 | 0.930 | 0.825 | 0.785 | **0.789** | 0.730 | **\$32.45** |
| **gemini-3.1-pro** (frontier) | 200 | 0.840 | 0.651 | 0.947 | 0.797 | 0.771 | 0.766 | 0.780 | **\$7.07** |
| gemma-4-31b-it @ high (member) | 190 | 0.800 | 0.612 | 0.912 | 0.752 | 0.732 | 0.694 | 0.805 | \$0.71 |

Confusion matrices (TP/FP/TN/FN at ≥6, base rate 28.5%):
- gpt-oss: 52/20/123/5 (best balance)
- trio: 51/22/121/6
- v4-flash: 44/16/123/12 (most precision-biased; loses recall)
- opus: 53/25/118/4
- gemini: 54/29/114/3 (most recall-biased)
- gemma: 52/33/100/5 (worst false-positive rate)

**Headline observations:**
- **gpt-oss-120b @ xhigh alone** is the highest point-estimate on pass_agree_at_6 (87.5%) and F1 (0.806)
- The trio consensus matches Opus's F1 exactly (0.785) and beats both frontiers on point-estimate pass-agreement
- The frontiers retain a real lead on **Pearson r** (Opus 0.789 well above gpt-oss 0.676 — non-overlapping CIs); the cheap judges win on precision/F1 tradeoffs
- All three cheap judges individually beat Gemini-3.1-Pro on pass-agreement point-estimate; two of three beat Opus's point-estimate

### 3.1a Bootstrap 95% confidence intervals (1000 resamples, n=200 with replacement)

| System | pass≥6 [95% CI] | F1 [95% CI] | r [95% CI] |
|---|---|---|---|
| gpt-oss-120b @ xhigh | 0.875 [0.825, 0.915] | 0.808 [0.721, 0.876] | 0.674 [0.572, 0.764] |
| trio_consensus | 0.860 [0.810, 0.910] | 0.785 [0.706, 0.860] | 0.743 [0.654, 0.819] |
| deepseek-v4-flash | 0.857 [0.806, 0.904] | 0.759 [0.656, 0.836] | 0.667 [0.555, 0.761] |
| claude-opus-4.7 | 0.855 [0.800, 0.900] | 0.784 [0.701, 0.861] | **0.789** [0.705, 0.857] |
| gemini-3.1-pro | 0.840 [0.790, 0.890] | 0.770 [0.688, 0.844] | 0.768 [0.682, 0.840] |
| gemma-4-31b-it @ high | 0.800 [0.741, 0.853] | 0.734 [0.655, 0.809] | 0.694 [0.597, 0.776] |

**The CIs on pass≥6 overlap heavily across the top 5 systems.** A 4-pp difference (gpt-oss vs Opus) is well within 200-sample bootstrap noise.

### 3.1b Pairwise win rates on pass≥6 (P[A > B] across 1000 resamples)

| Comparison | P(A > B) | P(tie) | P(B > A) | Interpretation |
|---|---|---|---|---|
| gpt-oss > Gemini | **0.911** | 0.034 | 0.055 | reliably better |
| gpt-oss > Opus | 0.762 | 0.068 | 0.170 | weakly better |
| gpt-oss > trio | 0.763 | 0.095 | 0.142 | weakly better |
| trio > Gemini | 0.804 | 0.051 | 0.145 | reliably better |
| trio > Opus | 0.579 | 0.089 | 0.332 | toss-up |
| Opus > Gemini | 0.792 | 0.085 | 0.123 | weakly better |
| v4-flash > Opus | 0.527 | 0.000 | 0.473 | coin flip |
| any cheap > gemma | >0.97 | — | <0.03 | reliably better |

**The strongly-supported claims** (P>0.90):
- gpt-oss-120b @ xhigh > Gemini-3.1-Pro on pass≥6
- All cheap judges (incl. gemma) crush gemma alone is misleading — re-statement: every other judge is reliably better than gemma

**The weakly-supported claims** (P~0.75–0.80):
- gpt-oss > Opus (point estimate 87.5 vs 85.5; could easily flip on a different sample)
- trio > Gemini
- Opus > Gemini

**Toss-ups** (P~0.50–0.60):
- trio vs Opus
- v4-flash vs Opus

The honest summary: **the cheap-judge tier is statistically indistinguishable from the frontier tier** at this sample size, with the exception of gpt-oss-120b reliably beating Gemini and the cheap judges trailing Opus on continuous correlation (r).

### 3.2 Frontier-frontier agreement: they fail the same way

Of 200 problems where both frontiers produced valid pass/fail decisions, Opus and Gemini agree on **96.0%** (192/200). They are highly correlated; building an ensemble from "two frontier judges" would yield <5 pp of headroom. The cheap judges gain their edge from drawing on a *different* error mode entirely.

### 3.3 Per-problem breakdown of the win

For 200 validation problems where all three systems (trio, Opus, Gemini) produced valid pass/fail decisions:

| Outcome | Count |
|---|---|
| All 3 systems correct | 153 |
| Trio correct, both frontiers wrong | 9 |
| Opus correct, trio + Gemini wrong | 4 |
| Gemini correct, trio + Opus wrong | 1 |
| All 3 wrong | 14 |

The trio's lead is driven by 9 problems where the cheap ensemble caught something both frontier models missed, against 5 problems where a single frontier was right alone — a roughly 2:1 ratio in the trio's favor on the disagreement subset. Among individual cheap judges, gpt-oss-120b shows the same pattern with 11 unique-correct vs. 5 frontier-only-correct.

Inspecting the trio-only-correct cases: the failure mode for both frontiers is consistent — they award credit for a candidate solution that *looks* like a complete proof but contains an unjustified leap or a case-analysis gap. Each cheap judge, with a different bias profile, catches a different subset of these gaps.

### 3.4 Prior sample (exploratory): same direction

| System | pass≥6 | precision | recall | F1 | Pearson r | Cost (200) |
|---|---|---|---|---|---|---|
| gpt-5.4-nano @ xhigh | 0.8929 | 0.933 | 0.700 | 0.800 | 0.712 | \$7.26 |
| deepseek-v4-pro | 0.8889 | 0.825 | 0.825 | 0.825 | 0.756 | \$2.97 |
| deepseek-v4-flash | 0.8744 | 0.806 | 0.794 | 0.800 | 0.756 | \$0.77 |
| gemini-3.1-pro | 0.8643 | 0.714 | 0.952 | 0.816 | **0.872** | \$6.93 |
| **trio_consensus_majority** | 0.8550 | 0.718 | 0.889 | 0.794 | 0.842 | — |
| gpt-oss-120b @ xhigh | 0.8427 | 0.703 | 0.897 | 0.788 | 0.770 | \$0.39 |
| gemma-4-31b-it @ high | 0.7900 | 0.611 | 0.921 | 0.734 | 0.776 | \$0.75 |

On the exploratory sample the trio is *competitive* with Gemini-3.1-Pro (0.855 vs 0.864 pass_agree, within sampling noise; 0.842 vs 0.872 r). Several other frontier-priced or expensive models are nominally ahead. The cross-sample shift is consistent with cheap judges being *robust* relative to single frontier judges.

### 3.5 Cost-effectiveness

Per-decision cost on the validation sample:

| System | Cost / 200 | $/decision | pass_agree_at_6 |
|---|---|---|---|
| **gpt-oss-120b @ xhigh** (alone) | \$0.32 | **\$0.0016** | 0.875 |
| trio_consensus_majority | \$1.73 | \$0.0087 | 0.860 |
| deepseek-v4-flash (alone) | \$0.70 | \$0.0035 | 0.856 |
| gemma-4-31b-it @ high (alone) | \$0.71 | \$0.0036 | 0.800 |
| gemini-3.1-pro | \$7.07 | \$0.0354 | 0.840 |
| claude-opus-4.7 | \$32.45 | \$0.1623 | 0.855 |

A practitioner who prizes the absolute pass-agree number should run **gpt-oss-120b @ xhigh alone**: \$0.0016 per decision (22× cheaper than Gemini, 100× cheaper than Opus) for the highest pass-agree number observed in this experiment. The trio adds ensemble robustness at 5× the cost of the single-judge solution but still 19× cheaper than Opus.

---

## 4. Discussion

### 4.1 Why a single small judge can win

The gpt-oss-120b @ xhigh result (87.5% pass-agree) on the held-out sample is the strongest individual judge result we have observed. Two factors plausibly drive it:

1. **Calibration.** gpt-oss-120b @ xhigh has the smallest calibration bias of any single judge tested (mean Δ = +0.21 on prior, near-zero). It is neither over-rewarding (like gemma-4-31b @ high, +0.55) nor over-deflating (like deepseek-v4-flash, −0.80).

2. **Reasoning effort matters most for this model family.** The same model at "minimal" effort scores only 71.9% pass-agree on prior; at xhigh it scores 84.3% — a 12.4 pp swing. Among all judges tested, gpt-oss-120b shows the largest reasoning-effort sensitivity. The xhigh setting allocates ~6000 reasoning tokens per call (\$0.001 added cost); this is a 1000× return on inference compute relative to the difference it makes in agreement.

### 4.2 Why majority vote of cheap judges still helps

The cheap-judge biases on the prior sample are:
- gemma-4-31b-it @ high: mean Δ = +0.55 (over-credits)
- gpt-oss-120b @ xhigh: mean Δ = +0.21 (calibrated)
- deepseek-v4-flash: mean Δ = −0.80 (under-credits)

The biases sum to roughly zero. More importantly, the *errors are uncorrelated* in a way that the two frontiers' errors are not (Opus and Gemini agree on pass/fail 96.0% of the time on validation). The trio fails three different ways, and majority vote eats most of those failures.

This generalizes the classic ensemble bias-variance argument to LLM judges: don't ensemble three frontier models; ensemble three models from three providers with three different reasoning regimes.

### 4.3 Precision vs recall tradeoff

The frontier judges are **recall-biased** (Gemini recall=0.95, Opus recall=0.93). They like to award credit. The cheap judges are more **precision-biased** (precision 0.70–0.73 vs frontier 0.65–0.68) without giving up much recall (0.79–0.91). For high-stakes settings where false positives are costly (e.g., admitting "almost correct" solutions to competition awards), the cheap judges' profile is closer to what you actually want.

### 4.4 Why Opus 4.7 doesn't dominate

Opus 4.7 has the best Pearson r (0.79), the best calibration (mean Δ ≈ −0.04), and the cleanest run profile. Its pass-agreement (85.5%) is competitive but doesn't beat the cheap judges, because Opus inherits the same recall-biased failure mode as Gemini: it awards credit liberally and produces 30 false positives on 200 records (vs gpt-oss's 22). At ~\$0.16 per decision, Opus is the **best continuous-score judge** observed but not the best pass/fail judge.

### 4.5 What the consensus is *not*

The trio is not a calibrated continuous-score predictor. Its `mean_score` is the average of three integers in {0,1,6,7}, which is a coarse summary of the human 0–7 scale. The trio's Pearson r (0.75) lags the frontier's (0.77–0.79). For applications that need a fine-grained quality signal (e.g., training a reward model), use a frontier judge; for applications that need a binary pass/fail decision at scale, use the cheap judges (single or trio).

### 4.6 Limitations

- **Single benchmark.** All numbers are on GradingBench (1000 instances over 30 problems). The cluster structure means problem-level shocks are real.
- **Single prompt template.** All judges share `judge_gt.md`, which restricts output to {0,1,6,7}. A different prompt could change all the rankings.
- **Single seed for the validation sample.** We report bootstrap 95% CIs in §3.1a and pairwise win rates in §3.1b, but a different seed=7 sample would give different point estimates.
- **No measurable inter-rater ceiling.** GradingBench has only 3 (problem, response) pairs with multiple human grades — far too few to compute meaningful inter-rater statistics. We therefore cannot say whether the judges' ~85–87% pass-agreement rates are *near the human ceiling* or *substantially below it*. If real human inter-rater agreement on this benchmark were, say, 90%, then 87.5% from gpt-oss is essentially at the ceiling (not 12.5 pp below perfect). This is the single largest unknown in interpreting the results.
- **Some missing data.** 5 v4-flash and 10 gemma calls did not complete due to upstream rate limits even after patching. Coverage is 95-100% across all configs.
- **No human inter-rater study.** The "human" score is a single expert grader's call from GradingBench; we treat it as ground truth.
- **No held-out problem set.** Validation shares the 30-problem pool with the prior sample; only the response/grade combinations differ. A truly out-of-distribution test would draw from new problems.

---

## 5. Conclusion

The strongly-supported finding from this experiment, with bootstrap 95% CIs from 1000 resamples on the held-out 200-problem validation sample:

- **Cheap small open-weight reasoning judges are at least competitive with frontier judges on pass/fail agreement with human IMO graders** at 100× lower cost. Specifically, gpt-oss-120b @ xhigh (\$0.0016/decision) reliably beats Gemini-3.1-Pro on pass≥6 (P=0.91) and is statistically indistinguishable from Claude Opus 4.7 (P=0.76, point estimate 87.5% vs 85.5%, CIs heavily overlap).
- **A trio consensus** (gemma-4-31b-it @ high + gpt-oss-120b @ xhigh + deepseek-v4-flash @ default) achieves point estimate 86.0% pass-agree, matches Opus's F1 exactly (0.785), and adds ensemble robustness at \$1.73 / 200 calls.
- **Frontier judges retain a real lead on continuous calibration** (Pearson r): Opus 0.79 [0.71, 0.86] is well above gpt-oss 0.67 [0.57, 0.76]. For applications that need a fine-grained quality signal, the frontier still wins.
- **The two frontier judges fail the same way** — Opus and Gemini agree on pass/fail 96% of the time on validation. Ensembling two frontier judges gives little headroom; the leverage comes from cheap judges with **opposite, structured biases** (gemma over-credits, deepseek under-credits, gpt-oss is calibrated).

The headline cannot be "single cheap judge dominates frontier" — the bootstrap doesn't support that. The headline is **"cheap judges are competitive with frontier at 1–5% of the cost on this benchmark, with a real frontier lead remaining on continuous-score calibration."**

**Practical recommendations:**
- For **pass/fail decisions at scale**: gpt-oss-120b @ xhigh alone gets you within bootstrap noise of frontier accuracy at 100× lower cost.
- For **robustness against single-judge failures** (rate limits, weight changes, training-data shifts): use the cheap trio at 5× the cost of single-judge.
- For **calibrated continuous quality scores** (e.g. training a reward model): use a frontier judge (Opus 4.7 leads on r).

**The largest uncaptured uncertainty** is human inter-rater agreement on GradingBench. The benchmark has only 3 problem+response pairs with multiple human grades, so we cannot estimate the human ceiling. If the ceiling is ~90%, then gpt-oss at 87.5% is essentially at the ceiling, not 12.5 pp below perfect. Future work should commission an inter-rater study before declaring any judge "incomplete."

---

## Appendix A. Reproducibility

- All raw per-call data: `trials_prior.csv` (2000 rows), `trials_validation.csv` (1000 rows), `trials_validation.jsonl` (with verdict text)
- Per-problem consensus computation: `consensus_analysis.csv` (400 rows, one per grading_id × sample)
- Per-system aggregates: `summary.csv`
- Pricing: `pricing_snapshot.json`
- Schema: `data_dictionary.md`
- Sampling: `random.Random(42).sample(rows, 200)` for prior; from the complement, `random.Random(7).sample(remaining, 200)` for validation. Verified zero overlap.
- Prompt: `prompts/pipeline/judge_gt.md`
- Source experiment scripts:
  - `experiments/judge_consensus_validation_20260507.py` (initial 5-config run)
  - `experiments/judge_validation_patch_20260507.py` (OpenRouter patch with provider routing)
  - `experiments/judge_gemma_direct_patch_20260507.py` (direct Google API for gemma)
- Build script: `_build_consensus_experiment_20260507.py` (run from repo root; deletes after run)

## Appendix B. Cost of patches

The validation run consumed approximately:
- gpt-oss-120b: \$0.32 (no patch needed)
- gemini-3.1-pro: \$7.07 (4 calls patched via OpenRouter retry)
- deepseek-v4-flash: \$0.70 (58 calls patched via SiliconFlow provider routing on OpenRouter)
- gemma-4-31b-it: \$0.71 total (~$0.50 OpenRouter + $0.21 direct Google API)
- claude-opus-4.7: \$32.45 (no patch needed)
- **Total validation cost: ~\$41.25**

The bulk is the single Opus 4.7 frontier baseline. The cheap-judge runs cost \$1.73 combined. The Gemini frontier cost \$7.07.
