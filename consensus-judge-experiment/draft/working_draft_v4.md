# Cost-Effective Automated Judging of Natural-Language Mathematical Proofs

**Working draft (v4) — 2026-05-26**

## Abstract

Grading natural-language mathematical proofs is a recurring cost in evaluating math-reasoning systems: formal verification covers only a narrow slice of mathematics, so most candidate proofs must be judged in natural language. We ask whether inexpensive open-weight models can serve as reliable judges when given a candidate proof, a ground-truth proof, and the protocol of an expert human grade to agree with. On a held-out 200-instance sample of IMO-GradingBench, we find that a tier of cheap judges (costing up to 100x less than frontier models) agrees with human pass/fail decisions at a rate statistically indistinguishable from Claude Opus 4.7 and Gemini 3.1 Pro. We initially expected a majority-vote consensus of three cheap models to be the best budget option; it performed well but did not exceed the strongest individual model within it. Our headline claim is therefore not that any one model is best, but that **cheap judges are competitive with the frontier at up to 100× lower cost** for this task. Two secondary studies support and qualify this: extending the cheap judges to the full 1000-instance benchmark confirms the pattern and shows the single-model leader is sample-dependent, and four repeated runs show that consensus rules, especially the unanimous all-three-pass rule, are both accurate and the most stable across runs, where single cheap judges drift a few points. We call for a larger-budget evaluation that also includes frontier reasoning models across the full benchmark.

---

## 1. Introduction

Benchmarks for AI mathematical reasoning increasingly include problems whose solutions are full natural-language proofs rather than short final answers, and scoring those proofs is a bottleneck. Formal verification with proof assistants such as Lean (Moura & Ullrich, 2021) gives trustworthy guarantees and has reached IMO-medal performance (AlphaProof, 2025), but it covers only a narrow slice of problems and typically requires manual formalization; the 2025 IMO gold-medal results from frontier models were produced and graded in natural language.

While the model under study can change between experiments, the judge must be reliable and held fixed across an entire study, so its cost is a tax on the whole research effort, and frontier judges are expensive. This motivates a concrete question: **is there a cheap judge a budget-constrained researcher can trust for proof grading?**

We study this judging task on **IMO-GradingBench** (Luong et al., 2025), the grading split of IMO-Bench: 1,000 instances, each pairing an Olympiad problem and a reference solution with a candidate proof and an expert human grade on the standard 0–7 IMO scale. The judge reads the problem, reference, and candidate, and predicts the grade.

Our prior expectation, following the Panel-of-LLM-evaluators result (Verga et al., 2024), was that a consensus of several cheap models would be the safest choice, as offsetting biases should cancel. We tested this: the consensus performed well, but it did **not** beat the strongest individual model within it. The more useful and general finding is that the cheap tier as a whole is competitive: cheap open-weight judges match frontier baselines (Claude Opus 4.7, Gemini 3.1 Pro) on pass/fail agreement with human graders at up to **100× lower cost** in our setup. We are deliberately narrow in scope; this is a study of *judging*, not *solving*, on problems that come with a reference proof and a human grade (not reference-free verification).

## 2. Related Work

LLM-as-a-judge (Zheng et al., 2023) is now the standard tool but is known to exhibit position, verbosity, and self-preference biases and to be sensitive to prompt design (Gu et al., 2024). For proofs specifically, frontier models often fail to produce valid arguments even when their final answers are correct (Petrov et al., 2025), motivating dedicated grading benchmarks such as the Open Proof Corpus (Dekoninck et al., 2025) and IMO-GradingBench (Luong et al., 2025). Cost has received less attention: Verga et al. (2024) show that small-model panels can outperform a single large judge at roughly 7× lower cost on QA and chatbot tasks. Two concurrent works frame our contribution. Ma et al. (2026) search the evaluator design space and reach expert-level agreement by combining a strong reasoning backbone with reference solutions, marking schemes, and ensembling; we ask whether the backbone itself must be strong and find that, for reference-based pass/fail grading, it need not be. Naik et al. (2026) study the closest reference-*free* version of our question and report cheap judges trailing the frontier by ~10% in accuracy (and ~25% in self-consistency), a gap that prompt ensembling narrows. In our reference-*based* setting (judging against ground-truth solutions), the accuracy gap closes entirely. This is consistent with the reference solution doing work the judge would otherwise have to do. We do not measure self-consistency, which remains open.

## 3. Problem setting

We consider grading instances of the form *(problem, ground-truth solution, candidate solution, human score)*. A judge reads the first three and outputs a score; we compare its score to the human's. The decision that matters most for downstream use is the **pass/fail boundary**: did the candidate proof meet the bar (a score of ≥6 on the 0–7 IMO scale)? Our primary metric is **pass-agreement**: the fraction of instances where the judge's pass/fail decision matches the human's. We report precision, recall, and F1 at that boundary, and Spearman rank correlation with the human score as a secondary, ordinal measure (appropriate for the coarse {0, 1, 6, 7} output). We also report per-grading cost.

## 4. Methodology

**Data and sampling.** From IMO-GradingBench's 1,000 instances (spanning 30 IMO-style problems), we draw two disjoint random samples of 200 by uniform selection without replacement: a *prior* (exploratory) sample with seed 42, used for exploration and for selecting the consensus trio, and a *validation* sample with seed 7, drawn from the remaining 800 instances, used as a clean held-out test. Section 6.1 additionally reports results over the complete 1,000-instance benchmark. All headline results are on the validation sample unless noted otherwise.

**Judge prompt and scoring buckets.** Every judge uses the same prompt and emits a score in **{0, 1, 6, 7}** (incorrect / partial / almost / correct). This four-bucket scheme follows the public grading prompt released with IMO-GradingBench (Luong et al., 2025), which we lightly adapt so that our judges are scored under an established, externally defined rubric rather than one of our own design. Pass/fail and all confusion-matrix metrics use the raw human score, so a human-4 graded as 6 by a judge is correctly counted as a false positive. The benchmark also ships a per-problem marking scheme; we do not provide it to the judge.

**Judges and reasoning settings.** We evaluate three cheap open-weight models (**GPT-OSS-120B**, **DeepSeek-V4-Flash**, and **Gemma-4-31B**) and two frontier baselines, **Claude Opus 4.7** and **Gemini 3.1 Pro**. The three cheap models were chosen for their cost-accuracy tradeoff and offsetting calibration biases (Gemma over-credits, DeepSeek-V4-Flash under-credits, GPT-OSS is roughly calibrated), the intended ingredient for a majority vote. These bias signs hold across our replicate runs (§6.2), so the trio's diversity is a property of the models, not of any single run. *For each model we use the strongest reasoning configuration it exposes.* These settings are not normalized and are not directly comparable across providers: GPT-OSS-120B runs at effort `xhigh`, Gemma-4-31B and Gemini-3.1-Pro with reasoning activated (listed as effort `high`), while Claude Opus 4.7 (adaptive thinking) and DeepSeek-V4-Flash (default) self-regulate their reasoning, so we report them at their default. The "Reasoning" column in each table names the per-model setting.

**Consensus rule.** The cheap consensus is the majority pass/fail vote of the three cheap models. We also report a *continuous* consensus score (the mean of member scores) only for completeness: because averaging the bucketed {0, 1, 6, 7} outputs produces intermediate values that no single judge can emit, the consensus Spearman ρ is not comparable to single-judge correlations, and we therefore omit it (shown as "—") throughout.

**Providers, coverage, and re-runs.** The cheap open-weight judges are served through OpenRouter by a shifting pool of third-party providers at varying quantizations; we did not pin a provider, so a single judge's pass-agreement can move by a few points between runs (quantified in §6.2). For a reproducible number, pin a provider and log the served-provider field; the frontier baselines are first-party, single-provider, and stable. Under 2% of judge calls failed to return a parseable score on the first attempt (transient rate limits, or reasoning that exceeded the 32k-token output ceiling without concluding); we re-ran these (runaways usually converged on a retry) and never substituted fabricated scores. Final coverage is 1000/1000 for each cheap judge and 200/200 for each frontier baseline.

## 5. Results

Table 1 reports the validation results, sorted by pass-agreement, with 95% bootstrap confidence intervals (1000 resamples). This is our primary comparison: the only setting in which all five judges, frontier and cheap, are run head-to-head.

**Table 1. Validation results (n = 200; metrics over valid responses).** Reasoning names each model's maximum/natural setting (see §4); the consensus Spearman ρ is omitted ("—") as it is not comparable to single-judge correlations.

| Judge | Reasoning | Pass-agree [95% CI] | Prec. | Rec. | F1 | Spearman ρ | Cost / 200 |
|---|---|---|---|---|---|---|---|
| GPT-OSS-120B | xhigh | 0.875 [0.825, 0.915] | 0.722 | 0.912 | 0.806 | 0.623 | **$0.32** |
| DeepSeek-V4-Flash | default | 0.860 [0.805, 0.910] | 0.738 | 0.789 | 0.763 | 0.660 | $0.70 |
| Cheap consensus (trio) | — | 0.855 [0.805, 0.900] | 0.689 | 0.895 | 0.779 | — | $1.73 |
| Claude Opus 4.7 | adaptive | 0.855 [0.800, 0.900] | 0.680 | 0.930 | 0.785 | **0.715** | $32.45 |
| Gemini 3.1 Pro | high | 0.840 [0.790, 0.890] | 0.662 | 0.895 | 0.761 | 0.704 | $28.61 |
| Gemma-4-31B | high | 0.795 [0.740, 0.845] | 0.591 | 0.912 | 0.717 | 0.676 | $0.71 |

**The cheap tier is competitive with the frontier.** The confidence intervals for the top five systems overlap substantially. GPT-OSS-120B has the highest point estimate, but it is best read as the front-runner of a cluster, not a clear winner: pairwise, it is statistically indistinguishable from Claude Opus 4.7 (P ≈ 0.76 of being higher on a resample) and only weakly separated from Gemini. Our sample does not support a claim that any single model is best. It does support the claim that the cheap cluster sits inside the frontier's interval: three open-weight judges, each costing under $1 per 200 gradings, match two models costing $28–32 for the same work.

**The consensus did not beat its best member.** The majority vote was robust and matched Opus on pass-agreement, but its pass-agreement (0.855) and F1 (0.779) fell below those of its strongest single member, GPT-OSS-120B (0.875, 0.806), at roughly five times the cost ($1.73 vs $0.32). Combining a strong model with two weaker ones diluted rather than improved the result.

**Cost.** The practical headline is the price gap. GPT-OSS-120B grades at $0.0016 per instance, about **100× cheaper than Claude Opus 4.7** ($0.162) and ~90× cheaper than Gemini 3.1 Pro at high reasoning ($0.143). Every cheap judge in Table 1 is one to two orders of magnitude cheaper than either frontier baseline, with no consistent accuracy penalty on the pass/fail decision.

**Where the frontier still leads.** The frontier keeps an edge on rank correlation with the human score: Opus (0.715) and Gemini (0.704) sit above the cheap judges (0.62–0.68). The margin is modest (Gemma reaches 0.676), but for applications that need a graded quality signal rather than a pass/fail gate, a frontier judge is still the safer choice.

Reasoning effort turns out to be a model-specific lever: raising Gemini to high reasoning does not change its agreement, while it matters a great deal for GPT-OSS-120B; we report this comparison in Appendix A.

## 6. Additional results

The two studies below extend the primary comparison. Neither changes the headline, and both are run on the cheap tier only (the frontier baselines are validation-only, for budget); we present them as supporting evidence.

### 6.1 The full benchmark (n = 1000)

We graded all three cheap judges over the **complete 1000-instance benchmark** (prior + validation + the remaining 600) for a more stable estimate and to compare consensus configurations.

**Table 2. Full benchmark (n = 1000), 95% bootstrap CIs (2000 resamples).** Pairs and "all-three" use the unanimous-pass rule (a candidate passes only if all listed members pass); consensus Spearman ρ is omitted ("—"; see §4).

| System | Pass-agree [95% CI] | Prec. | Rec. | F1 | Spearman ρ |
|---|---|---|---|---|---|
| *Individual models* | | | | | |
| DeepSeek-V4-Flash | 0.873 [0.853, 0.893] | 0.815 | 0.812 | 0.814 | 0.732 |
| GPT-OSS-120B (xhigh) | 0.842 [0.818, 0.864] | 0.716 | 0.889 | 0.793 | 0.704 |
| Gemma-4-31B (high) | 0.801 [0.775, 0.825] | 0.640 | 0.953 | 0.766 | 0.741 |
| *Pairs (unanimous pass)* | | | | | |
| DeepSeek + GPT-OSS | 0.878 [0.858, 0.897] | 0.852 | 0.777 | 0.813 | — |
| DeepSeek + Gemma | 0.877 [0.857, 0.897] | 0.824 | 0.812 | 0.818 | — |
| GPT-OSS + Gemma | 0.866 [0.844, 0.887] | 0.765 | 0.877 | 0.817 | — |
| *Combined* | | | | | |
| Majority vote (trio) | 0.863 [0.841, 0.883] | 0.744 | 0.912 | 0.819 | — |
| All-three-pass | 0.879 [0.859, 0.898] | 0.855 | 0.777 | 0.814 | — |

Three observations. First, **the single-model leader changes with scale**: GPT-OSS-120B led on the 200-instance validation sample, but on the full benchmark DeepSeek-V4-Flash is the strongest single judge (0.873 vs 0.842), direct evidence that 200 instances cannot separate the leaders. Second, **requiring agreement raises precision at the cost of recall**: the unanimous all-three-pass rule reaches the highest pass-agreement (0.879) and precision (0.855), while majority vote is the most recall-heavy (0.912). Third, **every confidence interval still overlaps**, consistent with the validation finding that no single configuration is separable.

The choice of consensus rule is effectively a precision/recall dial. Unanimous rules, such as both-pass pairs (e.g., DeepSeek + GPT-OSS) or all-three-pass, suppress false positives by passing a candidate only when members agree, which is the right profile when wrongly passing a flawed proof is costly; majority vote instead maximizes recall. The strictness of a pair is driven by its most conservative member: any pairing that includes the under-crediting DeepSeek-V4-Flash inherits high precision, and adding the over-crediting Gemma to an already-strict pair changes little.

### 6.2 Run-to-run variance (validation, four runs)

How stable are these numbers across repeated runs? We re-ran the cheap tier on the same 200-instance validation sample three more times, with no fixed random seed, giving four independent runs per system (including the original). Table 3 reports pass-agreement for each run, with the mean and standard deviation.

**Table 3. Run-to-run pass-agreement on validation (n = 200).** *orig*–*rep3* are four independent runs; *mean* and *std* are over those four. *Self-maj.* and *self-all-3* apply the consensus rules to one model's own three replicates (rep1–3), over the problems where all three are valid (n = 191–199): self-maj. passes if ≥2 of 3 runs pass, self-all-3 if all 3 pass. Consensus-of-consensus cells are blank ("—").

| System | orig | rep1 | rep2 | rep3 | mean | std | Self-maj. | Self-all-3 |
|---|---|---|---|---|---|---|---|---|
| DeepSeek-V4-Flash | 0.860 | 0.861 | 0.898 | 0.905 | 0.881 | 0.024 | 0.901 | 0.895 |
| GPT-OSS-120B @ xhigh | 0.875 | 0.863 | 0.829 | 0.835 | 0.851 | 0.022 | 0.847 | 0.888 |
| Gemma-4-31B @ high | 0.795 | 0.820 | 0.810 | 0.814 | 0.810 | 0.011 | 0.824 | 0.849 |
| Majority vote (trio) | 0.855 | 0.875 | 0.890 | 0.875 | 0.874 | 0.014 | — | — |
| **All-three-pass** | 0.895 | 0.895 | 0.903 | 0.915 | **0.902** | **0.009** | — | — |

Three points. First, **the unanimous all-three-pass rule is the best configuration on this sample on both counts**: the highest mean (0.902) and the smallest spread (std 0.009). Second, **the majority vote is steadier than its individual members** (std 0.014, versus 0.022–0.024 for GPT-OSS and DeepSeek). Third, the single-judge numbers move enough to matter: **GPT-OSS's headline 0.875 is the top of its 0.83–0.88 range, not a fixed value**, while DeepSeek is the most reliable single judge (mean 0.881), matching the full-benchmark result in §6.1. We do not claim consensus always reduces variance: Gemma alone is the steadiest single judge (std 0.011), edging out even the majority vote.

This variance comes from how the models are served, not from the models changing. Each call to GPT-OSS-120B or DeepSeek-V4-Flash is routed to one of several third-party providers, and different providers run the model at different numerical precisions (quantization), so identical requests can return slightly different scores. Gemma is served almost entirely (~93%) by a single provider, which is why its spread is small. The frontier baselines run on their own providers and are stable (a 20-problem re-run of Opus produced no pass/fail changes), so the run-to-run movement is specific to the cheaply-hosted open judges and does not affect the head-to-head comparison in §5. It does mean that any single cheap-judge number should be read as one draw from a few-point band, which is a further reason to prefer the steadier consensus rules.

The two rightmost columns of Table 3 turn that variance to advantage by applying the consensus rules to a single model's own three runs. For the recall-biased judges this helps: requiring all three GPT-OSS runs to pass lifts agreement from a single-run mean of 0.851 to 0.888, and Gemma from 0.810 to 0.849, because the run-to-run noise produces occasional spurious passes that a unanimity rule filters out. DeepSeek, already balanced, gains nothing beyond its best single run (self-majority 0.901). This is the same precision-for-recall trade as the cross-model rules in §6.1, amplified because successive runs are often served by different providers; in effect, running one cheap model three times and requiring unanimity recovers much of the multi-model consensus benefit (GPT-OSS self-all-3 reaches 0.888, approaching the cross-model all-three-pass at 0.902).

## 7. Limitations

- **Sample size and intervals.** Even on the full benchmark, the leading systems' confidence intervals overlap and we cannot resolve a single best judge. The 30-problem pool means problem-level effects are real.
- **Run-to-run variance (cheap tier).** Single cheap judges vary by ~2 points (std) across runs due to OpenRouter provider routing (§6.2); we did not pin providers for the headline runs. We did not replicate the frontier baselines beyond a 20-problem Opus drift screen (0/20 flips), which suggests they are stable.
- **Budget-constrained search.** We could not afford a broad sweep, and frontier baselines were not run on the full benchmark. Most notably, we did **not** evaluate GPT-5.5 Pro at high reasoning: at roughly $180 per million output tokens (more than 7× the price of Claude Opus 4.7) a single full run was out of budget.
- **Contamination.** Training-data leakage is unlikely to explain the result, at least for our strongest cheap judge: GPT-OSS-120B was released on 2025-08-05, three months *before* IMO-GradingBench (2025-11-03), so it cannot have trained on the benchmark's graded instances. Models released afterward (including Gemma-4 and DeepSeek-V4) could in principle have seen it, but grading a candidate against a provided reference solution is a distinct task from having encountered the problem, and the benchmark includes problems written specifically for it.
- **Judging, not solving.** These results speak to judge reliability against ground-truth proofs and human scores. They say nothing about a model's ability to *produce* proofs.
- **Scope.** Findings are specific to IMO-style competition mathematics with a ground-truth reference and a human grade. We do not claim they transfer to reference-free verification or to other domains.

## 8. Conclusion

For grading AI-generated natural-language proofs on a budget, cheap open-weight judges are a credible choice: they match frontier judges on pass/fail agreement with human graders at about 1% of the cost. The intuition that a consensus of cheap models would be the best option was not borne out (the vote did not beat its strongest member), but the broader result is more valuable and more robust: the cheap tier as a whole competes at the frontier, and the consensus rule offers a precision/recall dial and the most stable behavior across runs. We deliberately stop short of crowning a single model; our intervals do not support it, and the leader shifts between the validation sample and the full benchmark.

These conclusions are preliminary. The clear next step is a more comprehensive evaluation, with more replicates per judge (and pinned providers) and a wider set of models run across the entire benchmark by researchers with a larger budget. We expect the central finding (that very cheap judges are competitive) to hold, though we would not be surprised to learn that they underperform GPT-5.5 Pro (xhigh) or Gemini 3.1 DeepThink.

## Appendix A. Reasoning effort is a model-specific lever

Because Table 1 reports Gemini 3.1 Pro at high reasoning, we can read the effect of reasoning effort directly. To check whether reasoning *budget*, rather than model identity, drives judge quality, we additionally ran Gemini 3.1 Pro at its default setting for a within-model comparison (Table A1).

**Table A1. Gemini 3.1 Pro: default vs. high reasoning (n = 200).**

| Setting | Mean reasoning tokens | Pass-agree | F1 | Spearman ρ | Cost / 200 |
|---|---|---|---|---|---|
| Default | ~2,400 | 0.840 | 0.771 | 0.714 | $7.07 |
| High | ~10,400 | 0.840 | 0.761 | 0.704 | $28.61 |

Raising Gemini's reasoning roughly fourfold left its pass-agreement **unchanged** (0.840 in both cases; a paired bootstrap finds no detectable difference, and ten individual decisions flipped but canceled out), while quadrupling its cost. By contrast, reasoning effort matters a great deal for GPT-OSS-120B: its pass-agreement rises from 0.72 at minimal effort to 0.84 at its `xhigh` setting. Claude Opus 4.7 uses adaptive thinking and does not accept a manual reasoning budget, so its reported result already reflects whatever thinking it elects to do. The conclusion is that reasoning effort is a model-specific lever, not a universal one: large for GPT-OSS-120B, negligible for Gemini. For the cheap tier this is good news: GPT-OSS-120B's strong showing comes from a setting that costs fractions of a cent per call, not from model scale.

## References

- AlphaProof and AlphaGeometry teams, Google DeepMind (2025). *AI achieves silver-medal standard solving International Mathematical Olympiad problems.* [verify exact title/venue]
- Dekoninck, J., et al. (2025). *The Open Proof Corpus.* [verify]
- Gu, J., et al. (2024). *A Survey on LLM-as-a-Judge.* [verify]
- Luong, T., et al. (2025). *Towards Robust Mathematical Reasoning.* arXiv:2511.01846; EMNLP 2025. Introduces IMO-Bench (incl. IMO-GradingBench) and the {0, 1, 6, 7} grading prompt used here.
- Ma, et al. (2026). *[Evaluator design-space search for proof grading — verify title/authors.]*
- Moura, L. de, & Ullrich, S. (2021). *The Lean 4 Theorem Prover and Programming Language.* CADE 28.
- Naik, et al. (2026). *[Reference-free proof grading with small models — verify title/authors.]*
- Petrov, et al. (2025). *[Frontier models fail to produce valid proofs — verify title/authors.]*
- Verga, P., et al. (2024). *Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models (PoLL).*
- Zheng, L., et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS.

<!-- Author notes (not for camera-ready):
- VERIFY 2026 concurrent works (Ma et al., Naik et al.) and their figures (~10% acc, ~25% self-consistency, ~7× cost); fill exact titles/authors/venues for all bracketed references.
- GPT-OSS-120B release date (2025-08-05) is from internal notes; confirm for camera-ready.
- §6.2 variance is run-to-run replicate variance (orig + 3 no-seed reps), NOT pass@k. Source: multi-seed-cheap/. Seeded replicates were confounded by provider routing and are excluded.
- Table 1 cheap-judge rows now reflect full 200/200 coverage (DeepSeek 0.860, Gemma 0.795), matching the §6.2 "orig" column.
- Reasoning effort moved to Appendix A per review (was a main section); restore as §6 if a reviewer wants it in-body.
-->
