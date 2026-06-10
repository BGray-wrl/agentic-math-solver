# Cost-Effective Automated Judging of Natural-Language Mathematical Proofs

**Working draft (v2) — 2026-05-25**

## Abstract

Grading natural-language mathematical proofs is a recurring cost in evaluating math-reasoning systems: formal verification covers only a narrow slice of mathematics, so most candidate proofs must be judged in natural language. We ask whether inexpensive open-weight models can serve as reliable judges when given a candidate proof, a ground-truth proof, and the protocol of an expert human grade to agree with. On a held-out 200-instance sample of IMO-GradingBench, we find that a tier of cheap judges (costing up to 100x less than frontier models) agrees with human pass/fail decisions at a rate statistically indistinguishable from Claude Opus 4.7 and Gemini 3.1 Pro. We initially expected a majority-vote consensus of three cheap models to be the best budget option; it performed well but did not exceed the strongest individual model within it. Our headline claim is therefore not that any one model is best, but that **cheap judges are competitive with the frontier at up to 100× lower cost** for this task. Extending the three cheap judges to the full 1000-instance benchmark confirms the pattern and shows the single-model leader is sample-dependent, while alternative consensus rules trade recall for precision. We call for a larger-budget evaluation that also includes frontier reasoning models across the full benchmark.

---

## 1. Introduction

Benchmarks for AI mathematical reasoning increasingly include problems whose solutions are full natural-language proofs rather than short final answers. Scoring these solutions is a bottleneck. Formal verification (e.g., Lean) is trustworthy but exists for only a subset of problems, so in practice an LLM judge must often read a candidate proof and decide whether the argument is sound. While the generator can vary on a per-experiment basis, the judge must be both reliable and held fixed across an entire study, which makes its cost a tax on the whole research effort.

This motivates a concrete question: **is there a cheap judge a budget-constrained researcher can trust?** Our prior expectation was that a majority-vote consensus of several cheap models would be the safest choice, as diverse models with offsetting biases should cancel each other's errors. We tested this. The consensus did perform well, but it did **not** outperform the best individual model inside it. The more useful and more general finding is that the cheap tier as a whole is competitive with the frontier, at a small fraction of the price.

We are deliberately narrow about scope. This is a study of *judging*, not *solving*: we measure how well a model grades proofs against ground truth and human scores, not whether it can produce proofs. And it concerns problems that have (1) a candidate natural-language proof, (2) a ground-truth natural-language proof, and (3) an expert human grade (i.e., a judging task, not open-ended verification where no reference exists).

## 2. Problem setting

We consider grading instances of the form *(problem, ground-truth solution, candidate solution, human score)*. A judge reads the first three and outputs a score; we compare its score to the human's. The decision that matters most for downstream use is the **pass/fail boundary**: did the candidate proof meet the bar (a score of ≥6 on the 0–7 IMO scale)? Our primary metric is **pass-agreement**: the fraction of instances where the judge's pass/fail decision matches the human's. We report precision, recall, and F1 at that boundary, and Pearson correlation with the raw human score as a secondary, continuous measure.

## 3. Methodology

**Data and sampling.** GradingBench comprises 1000 grading instances spanning 30 IMO-style problems, each with an expert human score on the standard 0–7 IMO rubric. We draw two disjoint random samples of 200 instances by uniform random selection without replacement: a *prior* (exploratory) sample with seed 42, used for exploration and for selecting the consensus trio; and a *validation* sample drawn with seed 7 from the remaining 800 instances, so the two are disjoint by construction. The validation sample is a clean held-out test. Section 6 additionally reports results over the complete 1000-instance benchmark. All results are on the validation sample unless noted.

**Judge prompt and scoring buckets.** Every judge uses the same prompt and emits a score in **{0, 1, 6, 7}** (incorrect / partial / almost / correct). This four-bucket scheme follows the public grading prompt released by Google DeepMind in *Towards Robust Mathematical Reasoning* [1], which we adopt so that our judges are scored under an established, externally defined rubric rather than one of our own design. Pass/fail and all confusion-matrix metrics use the raw human score, so a human-4 graded as 6 by a judge is correctly counted as a false positive.

**Judges and reasoning settings.** We evaluate three cheap open-weight models — **GPT-OSS-120B**, **DeepSeek-V4-Flash**, and **Gemma-4-31B** — and two frontier baselines, **Claude Opus 4.7** and **Gemini 3.1 Pro**. The three cheap models were chosen for their cost-accuracy tradeoff and offsetting calibration biases (Gemma over-credits, DeepSeek-V4-Flash under-credits, GPT-OSS is roughly calibrated), the intended ingredient for a majority vote. *For each model we use the strongest reasoning configuration it exposes.* These settings are not normalized and are not directly comparable across providers: GPT-OSS-120B runs at effort `xhigh`, Gemma-4-31B and Gemini-3.1-Pro at effort `high`, while Claude Opus 4.7 (adaptive thinking) and DeepSeek-V4-Flash (default) self-regulate their reasoning, so we report them at their default. The "Reasoning" column in each table names the per-model setting.

**Consensus rule.** The cheap consensus is the majority pass/fail vote of the three cheap models. We also report a *continuous* consensus score (the mean of member scores) only for completeness: because averaging the bucketed {0, 1, 6, 7} outputs produces intermediate values that no single judge can emit, the consensus Pearson r is not comparable to single-judge correlations, and we therefore omit it (shown as "—") throughout.

**Coverage and re-runs.** Under 2% of judge calls failed to return a parseable score on the first attempt, chiefly transient rate limits or reasoning that exceeded the 32k-token output ceiling without concluding. We re-ran these calls (runaway reasoning usually converged on a retry) and never substituted fabricated scores. Final coverage is 1000/1000 for each cheap judge and 200/200 for each frontier baseline on the validation sample.

## 4. Results

Table 1 reports the validation results, sorted by pass-agreement, with 95% bootstrap confidence intervals (1000 resamples).

**Table 1. Validation results (n = 200; metrics over valid responses).** Reasoning names each model's maximum/natural setting (see §3); the consensus Pearson r is omitted ("—") as it is not comparable to single-judge correlations.

| Judge | Reasoning | Pass-agree [95% CI] | Prec. | Rec. | F1 | Pearson r | Cost / 200 |
|---|---|---|---|---|---|---|---|
| GPT-OSS-120B | xhigh | 0.875 [0.825, 0.915] | 0.722 | 0.912 | 0.806 | 0.676 | **$0.32** |
| DeepSeek-V4-Flash | default | 0.856 [0.806, 0.904] | 0.733 | 0.786 | 0.759 | 0.669 | $0.70 |
| Cheap consensus (trio) | — | 0.855 [0.805, 0.900] | 0.689 | 0.895 | 0.779 | — | $1.73 |
| Claude Opus 4.7 | adaptive | 0.855 [0.800, 0.900] | 0.680 | 0.930 | 0.785 | **0.789** | $32.45 |
| Gemini 3.1 Pro | high | 0.840 [0.790, 0.890] | 0.662 | 0.895 | 0.761 | 0.762 | $28.61 |
| Gemma-4-31B | high | 0.800 [0.741, 0.853] | 0.612 | 0.912 | 0.732 | 0.694 | $0.71 |

**The cheap tier is competitive with the frontier.** The confidence intervals for the top five systems overlap substantially. GPT-OSS-120B has the highest point estimate, but it is best read as the front-runner of a cluster, not a clear winner: pairwise, it is statistically indistinguishable from Claude Opus 4.7 (P ≈ 0.76 of being higher on a resample) and only weakly separated from Gemini. Our sample does not support a claim that any single model is best. It does support the claim that the cheap cluster sits inside the frontier's interval — three open-weight judges, each costing under $1 per 200 gradings, match two models costing $28–32 for the same work.

**The consensus did not beat its best member.** The majority vote was robust and matched Opus on pass-agreement, but its pass-agreement (0.855) and F1 (0.779) fell below those of its strongest single member, GPT-OSS-120B (0.875, 0.806), at roughly five times the cost ($1.73 vs $0.32). Combining a strong model with two weaker ones diluted rather than improved the result.

**Cost.** The practical headline is the price gap. GPT-OSS-120B grades at $0.0016 per instance, about **100× cheaper than Claude Opus 4.7** ($0.162) and ~90× cheaper than Gemini 3.1 Pro at high reasoning ($0.143). Every cheap judge in Table 1 is one to two orders of magnitude cheaper than either frontier baseline, with no consistent accuracy penalty on the pass/fail decision.

**Where the frontier still leads.** The one metric on which the frontier retains a clear edge is the continuous Pearson correlation with the human score: Opus's 0.789 is well above the cheap models' 0.67–0.69. For applications that need a fine-grained quality signal rather than a pass/fail gate, a frontier judge is still preferable.

## 5. Reasoning effort is a model-specific lever

Because Table 1 already reports Gemini 3.1 Pro at high reasoning, we can read the effect of reasoning effort directly. We were interested in whether reasoning *budget*, rather than model identity, drives judge quality, so we additionally ran Gemini 3.1 Pro at its default setting for a within-model comparison (Table 2).

**Table 2. Gemini 3.1 Pro: default vs. high reasoning (n = 200).**

| Setting | Mean reasoning tokens | Pass-agree | F1 | Pearson r | Cost / 200 |
|---|---|---|---|---|---|
| Default | ~2,400 | 0.840 | 0.771 | 0.766 | $7.07 |
| High | ~10,400 | 0.840 | 0.761 | 0.762 | $28.61 |

Raising Gemini's reasoning roughly fourfold left its pass-agreement **unchanged** (0.840 in both cases; a paired bootstrap finds no detectable difference, and ten individual decisions flipped but canceled out), while quadrupling its cost. By contrast, reasoning effort matters a great deal for GPT-OSS-120B: its pass-agreement rises from 0.72 at minimal effort to 0.84 at its `xhigh` setting. Claude Opus 4.7 uses adaptive thinking and does not accept a manual reasoning budget, so its reported result already reflects whatever thinking it elects to do.

The conclusion is that reasoning effort is a **model-specific lever**, not a universal one: large for GPT-OSS-120B, negligible for Gemini. For the cheap tier this is good news: GPT-OSS-120B's strong showing comes from a setting that costs fractions of a cent per call, not from model scale.

## 6. The cheap judges across the full benchmark

Having established the cheap tier's competitiveness on the held-out sample, we graded all three cheap judges over the **complete 1000-instance benchmark** (prior + validation + the remaining 600) for a more stable estimate and to compare consensus configurations. Frontier baselines remain validation-only; extending them to the full benchmark was out of budget.

**Table 3. Full benchmark (n = 1000), 95% bootstrap CIs (2000 resamples).** Pairs and "all-three" use the unanimous-pass rule (a candidate passes only if all listed members pass); consensus Pearson r is omitted ("—"; see §3).

| System | Pass-agree [95% CI] | Prec. | Rec. | F1 | Pearson r |
|---|---|---|---|---|---|
| *Individual models* | | | | | |
| DeepSeek-V4-Flash | 0.873 [0.853, 0.893] | 0.815 | 0.812 | 0.814 | 0.751 |
| GPT-OSS-120B (xhigh) | 0.842 [0.818, 0.864] | 0.716 | 0.889 | 0.793 | 0.725 |
| Gemma-4-31B (high) | 0.801 [0.775, 0.825] | 0.640 | 0.953 | 0.766 | 0.760 |
| *Pairs (unanimous pass)* | | | | | |
| DeepSeek + GPT-OSS | 0.878 [0.858, 0.897] | 0.852 | 0.777 | 0.813 | — |
| DeepSeek + Gemma | 0.877 [0.857, 0.897] | 0.824 | 0.812 | 0.818 | — |
| GPT-OSS + Gemma | 0.866 [0.844, 0.887] | 0.765 | 0.877 | 0.817 | — |
| *Combined* | | | | | |
| Majority vote (trio) | 0.863 [0.841, 0.883] | 0.744 | 0.912 | 0.819 | — |
| All-three-pass | 0.879 [0.859, 0.898] | 0.855 | 0.777 | 0.814 | — |

Three observations. First, **the single-model leader changes with scale**: GPT-OSS-120B led on the 200-instance validation sample, but on the full benchmark DeepSeek-V4-Flash is the strongest single judge (0.873 vs 0.842). This is direct evidence that 200 instances cannot separate the leaders. Second, **requiring agreement raises precision at the cost of recall**: the unanimous all-three-pass rule reaches the highest pass-agreement (0.879) and precision (0.855), while majority vote is the most recall-heavy (0.912). Third, **every confidence interval still overlaps**, consistent with the validation finding that no single configuration is separable.

### 6.1 Alternative consensus configurations

The choice of consensus rule is effectively a precision/recall dial. Unanimous rules — both-pass pairs (e.g., DeepSeek + GPT-OSS) or all-three-pass — suppress false positives by passing a candidate only when members agree, which is the right profile when wrongly passing a flawed proof is costly. Majority vote instead maximizes recall. Notably, the strictness of a pair is driven by its most conservative member: any pairing that includes the under-crediting DeepSeek-V4-Flash inherits high precision, and adding the over-crediting Gemma to an already-strict pair changes little.

> *[Placeholder — to expand.] A fuller treatment of consensus configurations is left to future work: per-bias pairings, weighted and tie-broken votes, threshold tuning on the continuous mean, and the precision/recall operating points each implies for high-precision (e.g., award-gating) versus high-recall (e.g., triage) use cases.*

## 7. Limitations

- **Sample size and intervals.** Even on the full benchmark, the leading systems' confidence intervals overlap and we cannot resolve a single best judge. The 30-problem pool means problem-level effects are real.
- **Within-model variance.** We largely ran one sample per judge and did not thoroughly characterize run-to-run variability.
- **Budget-constrained search.** We could not afford a broad sweep, and frontier baselines were not run on the full benchmark. Most notably, we did **not** evaluate GPT-5.5 Pro at high reasoning: at roughly $180 per million output tokens (more than 7× the price of Claude Opus 4.7) a single full run was out of budget.
- **Judging, not solving.** These results speak to judge reliability against ground-truth proofs and human scores. They say nothing about a model's ability to *produce* proofs.
- **Scope.** Findings are specific to IMO-style competition mathematics with a ground-truth reference and a human grade. We do not claim they transfer to reference-free verification or to other domains.

## 8. Conclusion

For grading AI-generated natural-language proofs on a budget, cheap open-weight judges are a credible choice: they match frontier judges on pass/fail agreement with human graders at about 1% of the cost. The intuition that a consensus of cheap models would be the best option was not borne out — the vote did not beat its strongest member — but the broader result is more valuable and more robust: the cheap tier as a whole competes at the frontier, and the consensus rule offers a precision/recall dial when one is needed. We deliberately stop short of crowning a single model; our intervals do not support it, and the leader shifts between the validation sample and the full benchmark.

These conclusions are preliminary. The clear next step is a more comprehensive evaluation, with multiple seeds per judge to pin down within-model variance and a wider set of models run across the entire benchmark by researchers with a larger budget. We expect the central finding (that very cheap judges are competitive) to hold, though we would not be surprised to learn that they underperform GPT-5.5 Pro (xhigh) or Gemini 3.1 DeepThink.

## References

[1] Google DeepMind. *Towards Robust Mathematical Reasoning.* The {0, 1, 6, 7} grading buckets and judge prompt used here follow the public grading prompt released with this work.
