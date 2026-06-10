# Cost-Effective Automated Judging of AI-Generated Natural-Language Proofs

**Working draft — 2026-05-24**

## Abstract

Grading natural-language mathematical proofs is a recurring cost in evaluating math-reasoning systems: formal verification covers only a narrow slice of mathematics, so most candidate proofs must be judged in natural language. We ask whether inexpensive open-weight models can serve as reliable judges when given a candidate proof, a ground-truth proof, and the protocol of an expert human grade to agree with. On a held-out 200-instance sample of IMO-GradingBench, we find that a tier of cheap judges (costing roughly 1% of frontier models) agrees with human pass/fail decisions at a rate statistically indistinguishable from Claude Opus 4.7 and Gemini 3.1 Pro. We initially expected a majority-vote consensus of three cheap models to be the best budget option; it performed well but did not exceed the strongest individual model within it. Our headline claim is therefore not that any one model is best, but that **cheap judges are highly competitive with the frontier at up to 100× lower cost** for this task. We further show that giving the frontier judge (Gemini 3.1 Pro) high reasoning does not meaningfully change its agreement, ruling out reasoning budget as the explanation. We call for a larger-budget evaluation across the full benchmark.

---

## 1. Introduction

Benchmarks for AI mathematical reasoning increasingly include problems whose solutions are full natural-language proofs rather than short final answers. Scoring these solutions is a bottleneck. Formal verification (e.g., Lean) is trustworthy but exists for only a subset of problems, so in practice an LLM judge must often read a candidate proof and decide whether the argument is sound. While the generator can vary on a per-experiment basis, the judge must be both reliable and held fixed across an entire study, which makes its cost a tax on the whole research effort.

This motivates a concrete question: **is there a cheap judge a budget-constrained researcher can trust?** Our prior expectation was that a majority-vote consensus of several cheap models would be the safest choice, as diverse models with offsetting biases should cancel each other's errors. We tested this. The consensus did perform well, but it did **not** outperform the best individual model inside it. The more useful and more general finding is that the cheap tier as a whole is competitive with the frontier, at a small fraction of the price.

We are deliberately narrow about scope. This is a study of *judging*, not *solving*: we measure how well a model grades proofs against ground truth and human scores, not whether it can produce proofs. And it concerns problems that have (1) a candidate natural-language proof, (2) a ground-truth natural-language proof, and (3) an expert human grade (i.e., a judging task, not open-ended verification where no reference exists).

## 2. Problem setting

We consider grading instances of the form *(problem, ground-truth solution, candidate solution, human score)*. A judge reads the first three and outputs a score; we compare its score to the human's. The decision that matters most for downstream use is the **pass/fail boundary**: did the candidate proof meet the bar (a score of ≥6 on the 0–7 IMO scale)? Our primary metric is **pass-agreement**: the fraction of instances where the judge's pass/fail decision matches the human's. We report precision, recall, and F1 at that boundary, and Pearson correlation with the raw human score as a secondary, continuous measure.

## 3. Methodology

**Data.** GradingBench comprises 1000 grading instances spanning 30 IMO-style problems, each with an expert human score on the standard 0–7 IMO rubric. We draw two disjoint random samples of 200 instances: a *prior* sample used for exploration and for selecting the consensus trio, and a *validation* sample (no overlap) used as a clean held-out test. All results below are on the validation sample unless noted.

**Judge prompt and scoring buckets.** Every judge uses the same prompt and emits a score in **{0, 1, 6, 7}** (incorrect / partial / almost / correct). This four-bucket scheme follows the public grading prompt released by Google DeepMind in *Towards Robust Mathematical Reasoning* [1], which we adopt so that our judges are scored under an established, externally defined rubric rather than one of our own design. Pass/fail and all confusion-matrix metrics use the raw human score, so a human-4 graded as 6 by a judge is correctly counted as a false positive.

**Judges.** We evaluate three cheap open-weight models: **GPT-OSS-120B** (xhigh), **DeepSeek-V4-Flash**, and **Gemma-4-31B** (reasoning); and two frontier baselines: **Claude Opus 4.7** and **Gemini 3.1 Pro**. The three cheap models were chosen from the exploratory sample for their demonstrated cost-accuracy tradeoff and to have offsetting calibration biases (Gemma over-credits, DeepSeek-V4-Flash under-credits, GPT-OSS is roughly calibrated), the intended ingredient for a majority vote.

**Consensus rule.** The cheap consensus is the majority pass/fail vote of the three cheap models; its continuous score is their mean. Note that the continuous score should not be compared against correlation metrics from single judges, as the average can reach a wider output range (2-5).

## 4. Results

Table 1 reports the validation results, sorted by pass-agreement, with 95% bootstrap confidence intervals (1000 resamples).

**Table 1. Validation results (n = 200; metrics over valid responses).**

| Judge | Reasoning | Pass-agree [95% CI] | Prec. | Rec. | F1 | Pearson r | Cost / 200 |
|---|---|---|---|---|---|---|---|
| GPT-OSS-120B | xhigh | 0.875 [0.825, 0.915] | 0.722 | 0.912 | 0.806 | 0.676 | **$0.32** |
| Cheap consensus (trio) | — | 0.855 [0.805, 0.900] | 0.689 | 0.895 | 0.779 | 0.754 | $1.73 |
| DeepSeek-V4-Flash | adaptive | 0.856 [0.806, 0.904] | 0.733 | 0.786 | 0.759 | 0.669 | $0.70 |
| Claude Opus 4.7 | adaptive | 0.855 [0.800, 0.900] | 0.680 | 0.930 | 0.785 | **0.789** | $32.45 |
| Gemini 3.1 Pro | active/high | 0.840 [0.790, 0.890] | 0.662 | 0.895 | 0.761 | 0.762 | $28.61 |
| Gemma-4-31B | active/high | 0.800 [0.741, 0.853] | 0.612 | 0.912 | 0.732 | 0.694 | $0.71 |

**The cheap tier is competitive with the frontier.** The confidence intervals for the top five systems overlap substantially. GPT-OSS-120B has the highest point estimate, but it is best read as the front-runner of a cluster, not a clear winner: pairwise, it is statistically indistinguishable from Claude Opus 4.7 (P ≈ 0.76 of being higher on a resample) and only weakly separated from Gemini. Our sample does not support a claim that any single model is best. It does support the claim that the cheap cluster sits inside the frontier's interval — three open-weight judges, each costing under $1.75 per 200 gradings, match two models costing $28–32 for the same work.

**The consensus did not beat its best member.** The majority vote was robust and matched Opus on F1, but its pass-agreement (0.855) and F1 (0.779) fell below those of its strongest single member, GPT-OSS-120B (0.875, 0.806), at roughly five times the cost ($1.73 vs $0.32). Combining a strong model with two weaker ones diluted rather than improved the result.

**Cost.** The practical headline is the price gap. GPT-OSS-120B grades at $0.0016 per instance, about **100× cheaper than Claude Opus 4.7** ($0.162) and ~90× cheaper than Gemini 3.1 Pro at high reasoning ($0.143). Every cheap judge in Table 1 is one to two orders of magnitude cheaper than either frontier baseline, with no consistent accuracy penalty on the pass/fail decision.

**Where the frontier still leads.** The one metric on which the frontier retains a clear edge is the continuous Pearson correlation with the human score: Opus's 0.789 is well above the cheap models' 0.67–0.69. For applications that need a fine-grained quality signal rather than a pass/fail gate, a frontier judge is still preferable.

## 5. Secondary finding: reasoning effort is a model-specific lever

A natural concern is that GPT-OSS 120B's standing reflects its high reasoning setting while the frontier baselines ran at default effort. We tested this directly by re-running Gemini 3.1 Pro at high reasoning over the full validation set.

**Table 2. Gemini 3.1 Pro: default vs. high reasoning (n = 200).**

| Setting | Mean reasoning tokens | Pass-agree | F1 | Pearson r | Cost / 200 |
|---|---|---|---|---|---|
| Default | ~2,400 | 0.840 | 0.771 | 0.766 | $7.07 |
| High | ~10,400 | 0.840 | 0.761 | 0.762 | $28.61 |

Raising Gemini's reasoning roughly fourfold left its pass-agreement **unchanged** (0.840 in both cases; a paired bootstrap finds no detectable difference, and ten individual decisions flipped but canceled out), while quadrupling its cost. By contrast, reasoning effort matters a great deal for GPT-OSS 120B: its pass-agreement rises from 0.72 at minimal effort to 0.84 at high effort. Claude Opus 4.7 uses adaptive thinking and does not accept a manual reasoning budget, so its reported result already reflects whatever thinking it elects to do; there is no higher-reasoning configuration to test.

The conclusion is that reasoning effort is a **model-specific lever**, not a universal one: large for GPT-OSS 120B, negligible for Gemini. GPT-OSS 120B's competitiveness is therefore not an artifact of extra reasoning budget. When the frontier model is given the same advantage, it does not move.

## 6. Limitations

- **Sample size and intervals.** With 200 held-out instances over 30 problems, the confidence intervals for the leading systems overlap, and we cannot resolve a single best judge. Problem-level effects are real given only 30 problems.
- **Within-model variance.** We largely ran one sample per judge and did not thoroughly characterize run-to-run variability.
- **Budget-constrained search.** We could not afford a broad sweep of models and settings. Most notably, we did **not** evaluate GPT-5.5 Pro at high reasoning: at roughly $180 per million output tokens (more than 7× the price of Claude Opus 4.7) a single full run was out of budget.
- **Judging, not solving.** These results speak to judge reliability against ground-truth proofs and human scores. They say nothing about a model's ability to *produce* proofs.
- **Scope.** Findings are specific to IMO-style competition mathematics with a ground-truth reference and a human grade. We do not claim they transfer to reference-free verification or to other domains.

## 7. Conclusion

For grading AI-generated natural-language proofs on a budget, cheap open-weight judges are a credible choice: on held-out IMO-style data they match frontier judges on pass/fail agreement with human graders at about 1% of the cost. The intuition that a consensus of cheap models would be the best option was not borne out — the vote did not beat its strongest member — but the broader result is more valuable and more robust: the cheap tier as a whole competes at the frontier. We deliberately stop short of crowning a single model; our intervals do not support it.

These conclusions are preliminary. The clear next step is a more comprehensive evaluation across the **entire** GradingBench benchmark, with multiple seeds per judge to pin down within-model variance and a wider set of models (including the frontier reasoning systems we could not afford), run by researchers with a larger budget. We expect the central finding (that very cheap judges are competitive) to hold, though we would not be surprised to learn that they underperform GPT 5.5 Pro (xhigh) or Gemini 3.1 DeepThink.

## References

[1] Google DeepMind. *Towards Robust Mathematical Reasoning.* The {0, 1, 6, 7} grading buckets and judge prompt used here follow the public grading prompt released with this work.
