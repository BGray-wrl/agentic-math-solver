# Sampling, Scaffolding, and Judging in Natural-Language Mathematical Proof Generation

## Abstract

We evaluate lightweight inference-time methods for natural-language mathematical proof generation. The study uses a 70-problem benchmark: 60 IMO-ProofBench problems plus 10 recent research-facing problems from Erdős problem resolutions, First Proof, and FrontierMath Open Problems. We compare pass@k generation, seeded ideation, generator-verifier-reviser loops, and seeded generator-verifier-reviser loops across several API models. Because long proof grading is itself a hard task, we first calibrate model judges on IMO-GradingBench and short-answer solvers on AnswerBench.

The main finding is that simple sampling is a harder baseline than the agentic scaffolding suggests. In the clean six-model Phase 1 sweep, pass@3 generation, seeded generation, and generator-verifier-reviser pipelines all score about 31-32% pass rate under the canonical calibrated judge. The richer pipelines do not reliably beat pass@3. The strongest effects are instead judge choice, reasoning effort, and pass@k scaling. DeepSeek V4 Flash gives 87.4% pass/fail agreement with human labels on a 200-item GradingBench sample at $0.0039 per call, making it our canonical judge. With that judge, DeepSeek V4 Flash generation on the full 70-problem set rises from 40% pass rate at n=1 to 64% at n=7. Reasoning effort is similarly large: GPT-OSS and Gemma improve by roughly 10-23 pass-rate points across comparable modes when max reasoning is enabled. Research-grade pass judgments occur, but they are concentrated in easier frontier items and require caution. The practical conclusion is that proof-generation architecture claims should be compared against equal-budget pass@k baselines, not pass@1.

## 1. Introduction

Mathematical reasoning benchmarks have become less informative at the low end. Modern models can solve many short-answer and contest-style problems that were difficult only a few years ago. The interesting question has shifted from "can a model solve math?" to "which inference-time procedures make proof attempts more reliable on problems near the edge of current capability?"

The answer matters for both evaluation and practice. A researcher using a language model for proof work has many options: ask once, sample many times, ask for ideas first, ask another model to criticize the proof, run a revise loop, or combine all of these. The richer procedures sound more like mathematical work. They also cost more. A three-branch pipeline that consumes several times the tokens of a direct sample should not be compared to a single direct sample. It should be compared to spending the same budget on repeated attempts.

This paper studies that comparison in a natural-language setting. We intentionally do not evaluate Lean proof search, theorem-prover agents, or code-evolution systems. Those approaches can be stronger when the problem has a formal verifier or a clear executable objective. Our setting is broader and messier: the model writes a proof in prose, and another model grades it.

We ask five questions:

1. Do seeded ideation and generator-verifier-reviser loops outperform pass@3 generation?
2. Does pass@k continue to improve proof quality on difficult problems?
3. How much does reasoning effort matter relative to architecture?
4. Can model-as-judge grading be trusted enough for directional claims?
5. Do cheap models ever produce judged-passing attempts on research-grade problems?

The short answers are: no clean architecture win; yes, scaling still helps; reasoning effort matters a lot; model judges are usable but fragile; and cheap models occasionally reach judged-passing frontier attempts, though not enough to claim independent mathematical discovery.

## 2. Background and Scope

Recent AI-math systems span several regimes. Formal systems such as AlphaProof and Aristotle use proof assistants or proof search to obtain stronger correctness guarantees. Natural-language frontier models such as Gemini Deep Think and OpenAI's reported IMO and First Proof systems operate closer to ordinary mathematical writing. Search systems such as AlphaEvolve work when a candidate solution can be scored by an automatic evaluator.

Our experiments sit in the middle. We use natural-language prompts and black-box API calls. We evaluate proof attempts with a calibrated model judge, not human mathematicians or formal verification. This makes the work less definitive than a formal proof benchmark, but it also tests the setting many researchers actually face: a hard problem, several model calls, and no cheap ground-truth verifier for arbitrary prose.

The closest methodological inspirations are IMO-Bench, which provides AnswerBench, ProofBench, and GradingBench; Aletheia-style generator-verifier-reviser loops for Erdős problems; and First Proof, which emphasizes research-level proof attempts where correctness is hard to establish without expert review.

## 3. Benchmark

We evaluate on 70 problems. The base set is IMO-ProofBench: 30 basic and 30 advanced proof problems. We add 10 Research-2026 problems:

| Source | Problems |
|---|---|
| Erdős | 333, 397, 654, 659, 1051 |
| First Proof | 4, 5, 6, 10 |
| FrontierMath Open Problems | Ramsey hypergraphs |

The added problems are not presented as unsolved by us. They are used because accepted or public solution context exists and because they are near the current frontier of AI mathematical performance. This gives a harder tail than ProofBench alone.

For analysis we use two labels. `Research-2026` means membership in the 10 added problems. `difficulty` is a six-level scale: pre-competition, competition-hard, research-easy, research-medium, research-hard, and research-frontier. These are not identical: Erdős 397 is in Research-2026 but is tagged competition-hard because its solution path is closer to advanced competition mathematics.

The difficulty gradient is steep under the canonical judge:

| Difficulty | Valid rows | Mean score | Pass rate |
|---|---:|---:|---:|
| Pre-competition | 231 | 6.02 | 86.1% |
| Competition-hard | 1,507 | 2.04 | 28.9% |
| Research-easy | 115 | 1.50 | 22.6% |
| Research-medium | 57 | 0.14 | 1.8% |
| Research-hard | 55 | 0.00 | 0.0% |
| Research-frontier | 27 | 0.00 | 0.0% |

This matters for interpretation. A result can look decent on the full 70-problem set while still failing almost entirely on the harder research bins.

## 4. Methods

### 4.1 Architecture Modes

We test four inference-time modes.

`generate` is pass@3 direct generation in the architecture bucket. The trial score is the best judged branch.

`seed_generate` first asks for solution ideas, then generates proof attempts from those ideas.

`full` is a generator-verifier-reviser loop. The generator writes a proof, the verifier critiques it, and the reviser attempts to repair it.

`seed_full` combines seeded ideation with the full loop.

The cleanest comparison is Phase 1: six models, 70 problems, and the three modes `generate`, `seed_generate`, and `full`. `seed_full` was collected in later runs and has asymmetric coverage, so we treat it as suggestive rather than a clean fourth arm.

### 4.2 Metrics

All proof scores are on a 0-7 scale. A pass is score >= 6. The primary proof judge is DeepSeek V4 Flash with reasoning enabled, chosen after calibration. Means are computed over valid judged rows. For scaling experiments, pass@n is computed by exhaustive subset enumeration: for each problem, every size-n subset of available branches is scored by the maximum branch score in that subset, then averaged.

### 4.3 Buckets

The analysis uses five result buckets:

| Bucket | Role |
|---|---|
| AnswerBench calibration | Short-answer model capability and reasoning-effort checks |
| GradingBench calibration | Model-as-judge calibration against human labels |
| Architecture | Main mode comparison |
| Scaling | pass@n curves |
| Roleswap | Cross-model assignment of ideator/generator/verifier/reviser roles |

All headline aggregates in this draft were checked against the CSVs, not copied only from reports.

## 5. Judge Calibration

Automated proof grading is the largest risk in the study. A model judge can be systematically lenient, conservative, or sensitive to surface style. We therefore calibrate judges on a 200-item sample from IMO-GradingBench using the same pass threshold as the main experiments.

| Judge | n | Pass agreement | Recall | Precision | F1 | Pearson r | Mean delta | Cost / call |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.4-nano xhigh | 196 | 89.3% | 70.0% | 93.3% | 0.800 | 0.712 | -0.95 | $0.0370 |
| DeepSeek V4 Pro | 198 | 88.9% | 82.5% | 82.5% | 0.825 | 0.756 | -0.75 | $0.0150 |
| DeepSeek V4 Flash | 199 | 87.4% | 79.4% | 80.6% | 0.800 | 0.756 | -0.80 | $0.0039 |
| Gemini 3.1 Pro | 199 | 86.4% | 95.2% | 71.4% | 0.816 | 0.872 | +0.13 | $0.0348 |
| GPT-OSS 120B xhigh | 178 | 84.3% | 89.7% | 70.3% | 0.788 | 0.770 | +0.21 | $0.0022 |

Different judges are best for different purposes. GPT-5.4-nano has the highest pass agreement but is conservative, with many false negatives. DeepSeek V4 Pro has the best F1 at the pass threshold. Gemini 3.1 Pro is the best continuous calibrator, with Pearson r = 0.872 and small mean bias, but it is more lenient at the pass threshold. DeepSeek V4 Flash is close to the top pass/fail judges and much cheaper, so we use it as the canonical judge.

This choice is not cosmetic. In earlier analyses, lenient Gemini-family judges made some pipeline outputs look more improved than DeepSeek judges did. The paper's central claims should therefore be read as claims under a relatively conservative pass/fail grader.

## 6. Solver Calibration and Reasoning Effort

AnswerBench-50 gives a cheap short-answer capability check. It is not a proof benchmark, but it reveals which models are strong enough to be useful and how much reasoning settings matter.

| Model/config | Accuracy | Cost/run | Mean generation latency |
|---|---:|---:|---:|
| DeepSeek V4 Pro default | 47/50 | $0.0185 | 723s |
| GPT-5.4-nano xhigh | 45/49 | $0.0560 | 1,243s |
| Gemini 3 Flash xhigh effective | 45/50 | $0.0337 | 51s |
| DeepSeek V4 Flash default | 44/50 | $0.0055 | 357s |
| Qwen3.6 35B A3B default | 40/50 | $0.0218 | 139s |
| GPT-OSS 120B xhigh | 37/50 | $0.0057 | 565s |
| Gemma 4 31B default | 34/50 | $0.0015 | 235s |

Reasoning effort changes the story. GPT-OSS improves from 29/50 to 37/50 when moved from default to xhigh. DeepSeek V4 Flash drops from 44/50 to 25/50 when reasoning is explicitly disabled. In GradingBench, reasoning also improves judges: GPT-OSS pass agreement rises from 71.9% to 84.3%, and Gemma rises from 65.5% to 79.0%.

This motivates a later result: when architecture and reasoning are both changing, reasoning may explain more of the gain than the scaffold.

## 7. Main Architecture Results

The clean Phase 1 result is almost flat:

| Phase 1 mode | Valid n | Mean score | Pass rate |
|---|---:|---:|---:|
| pass@3 generate | 406 | 2.23 | 31.8% |
| seeded generate | 416 | 2.18 | 31.2% |
| generator-verifier-reviser | 412 | 2.22 | 31.6% |

This is the core result. On the same models and problems, neither seeded ideation nor the generator-verifier-reviser loop beats direct pass@3. The differences are small enough that the prudent interpretation is "no measurable architecture win" rather than "one mode is best."

Individual models vary:

| Model | Best Phase 1 mode | Best mean/pass | Note |
|---|---|---:|---|
| DeepSeek V4 Pro | full | 3.85 / 54.5% | Full loop helps slightly |
| DeepSeek V4 Flash | seed_generate | 3.41 / 49.3% | Seeded generation helps slightly |
| Qwen3.6 35B A3B | seed_generate | 2.10 / 30.0% | Tied with generate |
| Gemini 3 Flash | generate | 1.83 / 25.7% | Pipeline hurts |
| Gemma 4 31B | generate | 1.49 / 21.7% | Flat/negative |
| GPT-OSS 120B | full | 1.58 / 21.7% | Low baseline |

Across all architecture rows, `seed_full` is best:

| All architecture rows | Valid n | Mean score | Pass rate |
|---|---:|---:|---:|
| generate | 543 | 2.31 | 32.6% |
| seeded generate | 555 | 2.29 | 33.0% |
| full | 550 | 2.24 | 31.8% |
| seed_full | 344 | 2.58 | 36.9% |

But `seed_full` is not covered in the clean Phase 1 grid. Its rows come from Phase 2, Phase 3, and reasoning reruns. The best cell, Gemma 4 31B with max reasoning and seed_full, reaches mean 3.31 and 47.1% pass rate, but that combines a different mode with a major reasoning-effort change. This is a promising lead for future work, not a confirmed architecture result.

## 8. Scaling Results

Pass@k is the strongest baseline. In the generate rows, the first branch gives a correlated pass@1 proxy. Moving to pass@3 increases Phase 1 mean score by 0.40 and pass rate by 5.5 points. In the reasoning rerun, pass@3 increases mean score by 0.56 and pass rate by 6.5 points.

The dedicated scaling runs show continued gains through n=7:

| Model | Reasoning | Problems | n=1 mean/pass | n=3 mean/pass | n=7 mean/pass |
|---|---|---:|---:|---:|---:|
| Gemma 4 31B | default | 30 | 0.31 / 4.3% | 0.74 / 10.4% | 1.40 / 20.0% |
| GPT-OSS 120B | default | 30 | 0.10 / 1.4% | 0.27 / 3.8% | 0.47 / 6.7% |
| Gemma 4 31B | max | 70 | 1.92 / 27.0% | 2.76 / 38.8% | 3.20 / 44.8% |
| GPT-OSS 120B | max | 70 | 1.68 / 24.2% | 2.49 / 35.8% | 3.08 / 43.6% |
| DeepSeek V4 Flash | default | 70 | 2.81 / 40.0% | 3.78 / 53.3% | 4.54 / 63.8% |

The gains are large enough to dominate the clean architecture differences. For DeepSeek V4 Flash, n=1 to n=7 adds 1.72 mean score points and 23.8 pass-rate points. For max-reasoning GPT-OSS, it adds 1.40 points and 19.4 pass-rate points. For max-reasoning Gemma, it adds 1.28 points and 17.8 pass-rate points.

This does not mean pass@k is the final answer. It means every proposed scaffold must beat the pass@k curve at the same budget.

## 9. Role-Swap Results

The role-swap experiments ask whether mixing models across ideator, generator, verifier, and reviser roles improves performance. The main grid uses Gemma 4 31B and GPT-OSS 120B under default and max reasoning.

The random baselines average to 1.78 mean score and 25.7% pass rate at default reasoning, and 3.27 mean score and 46.7% pass rate at max reasoning. The best single-role condition is using GPT-OSS as verifier:

| Setting | Random baseline | Best role-swap condition | Lift |
|---|---:|---:|---:|
| Default reasoning | 1.78 / 25.7% | 2.07 / 29.0% | +0.29 / +3.3 pp |
| Max reasoning | 3.27 / 46.7% | 3.63 / 51.4% | +0.36 / +4.7 pp |

This is suggestive but small. It is also less stable than the reasoning and scaling effects. The safest conclusion is that naive model diversity may help in verifier-like roles, but it is not a substitute for more samples or more reasoning.

## 10. Research-Grade Results

The Research-2026 set is the most interesting and the easiest to overstate. We therefore separate judged pass events from mathematical claims.

Across architecture and roleswap rows, the canonical judge finds 46 passes among 439 valid Research-2026 attempts. The distribution is concentrated:

| Problem | Pass judgments |
|---|---:|
| First Proof 10 | 32 |
| Erdős 654 | 8 |
| Erdős 333 | 3 |
| Erdős 397 | 1 |
| Erdős 659 | 1 |
| First Proof 5 | 1 |

No broad method reliably solves the research set. Most Research-2026 pass judgments come from easier or already more accessible frontier items. The harder First Proof problems and the Ramsey hypergraphs problem are mostly missed in our runs.

Still, the results are not empty. In the scaling bucket, DeepSeek V4 Flash at n=7 receives pass judgments on four Research-2026 problems: Erdős 1051, Erdős 659, First Proof 10, and First Proof 6. Gemma and GPT-OSS at max reasoning each reach one research solve at n=7. This supports a modest claim: cheap and mid-tier models can sometimes produce proof attempts that a calibrated judge rates as passing on known frontier-adjacent problems. It does not support a claim of autonomous mathematical discovery.

## 11. Discussion

The main lesson is about baselines. The field has many plausible scaffolds: ideators, verifiers, revisers, model swaps, debate, consensus, and search. These may work. But if they use multiple samples or multiple long calls, they must be compared to spending the same budget on direct sampling. In our clean comparison, the lightweight scaffolds do not beat pass@3. In the broader data, the apparent gains are confounded by reasoning effort and coverage.

This also changes how we should read model-as-judge results. Judge calibration is not an appendix detail; it is part of the main experiment. A lenient judge can convert style improvements into apparent proof improvements. A conservative judge can miss partial progress. We choose a relatively conservative and cost-effective judge because the primary target is pass/fail correctness, but we should not pretend the choice is neutral.

The positive result is that inference-time compute still buys capability on hard proof problems. This is practically useful. If a user has a fixed budget, the first dollar should likely go to enabling the model's reasoning mode and sampling more attempts. More complex scaffolding should be added only when it has been shown to beat that baseline.

The research-grade results are also useful, but mainly as a warning about evaluation. A few judged passes can be real signal while still being far from proof of correctness. They are candidates for expert review, not end results.

## 12. Limitations

Automated judging is the central limitation. GradingBench calibration gives confidence for directional comparisons, but it cannot certify research mathematics. This is especially important for First Proof and Erdős items, where plausible wrong proofs are common.

The architecture design is incomplete. `seed_full` was not run in the clean Phase 1 grid, so the strongest-looking mode remains confounded. A decisive follow-up should run all four modes on the same models and problems with matched token budgets.

The research subset is small. Ten problems are enough to expose failure modes, not enough to estimate frontier capability precisely. The hardest bins have almost no successes, so any per-problem claim is fragile.

Contamination protection is partial. The Research-2026 items were recent, and some were not publicly solved until 2026, but model training and post-training dates are often opaque. We therefore treat the research set as hard and recent, not as a clean no-contamination benchmark.

Finally, cost accounting is approximate. Per-call costs are available for many rows, but total project cost includes judge calls, failures, retries, and human iteration.

## 13. Conclusion

For natural-language proof generation, the current default should be pass@k plus calibrated judging. In this dataset, lightweight seeded ideation and generator-verifier-reviser scaffolds do not clearly beat pass@3 in the clean comparison. Reasoning effort and repeated sampling are larger and more reliable effects. Model diversity may help in verifier roles, and seed_full pipelines may be promising, but neither result is yet clean enough to displace the simple baseline.

The next experiment is clear: run all four architecture modes across the same model/problem grid, match token budgets to pass@k, and send every research-grade judged pass to expert review. Until then, the strongest claim is not that agentic proof pipelines fail. It is that they have to beat sampling, and sampling is strong.

## Appendix A. Notes for a Cleaner Follow-up

A decisive follow-up should include `generate`, `seed_generate`, `full`, and `seed_full` for every model. It should report pass@1, pass@3, pass@7, and equal-cost pass@k. It should use at least two calibrated judges with known bias profiles: one conservative pass/fail judge and one continuous calibrator. Finally, it should pre-register a human-review protocol for all Research-2026 candidates that receive score >= 6 from either judge.

