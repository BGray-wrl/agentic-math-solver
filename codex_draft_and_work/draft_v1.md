# Inference-Time Architecture for Natural-Language Mathematical Proofs

## Abstract

We study whether agentic proof-writing scaffolds improve over simple repeated sampling for natural-language mathematical reasoning. We evaluate 70 problems: 60 from IMO-ProofBench and 10 recent research-grade problems drawn from Erdős problem resolutions, First Proof, and FrontierMath Open Problems. We compare pass@k generation, seeded ideation, generator-verifier-reviser loops, and combined seeded pipelines across several inexpensive and mid-tier reasoning models. Because long-form proof grading is itself difficult, we first calibrate model judges on IMO-GradingBench and short-answer mathematical ability on AnswerBench.

The main result is negative but useful: in the clean architecture comparison, generator-verifier-reviser loops and seeded generation do not clearly beat pass@3. The strongest effects are instead (1) judge calibration, (2) reasoning effort, and (3) simple inference-time scaling. DeepSeek V4 Flash is a cost-effective proof judge, agreeing with human pass/fail labels on 87.4% of a 200-item GradingBench sample. In the main architecture bucket, Phase 1 pass@3, seeded generation, and full generator-verifier-reviser modes all land near 31-32% pass rate under this judge. Scaling to pass@7 gives clearer gains: DeepSeek V4 Flash rises from 40% to 64% pass rate across the full 70-problem set. Research-grade solves remain rare and highly concentrated, but not absent: several cheap or mid-tier configurations receive pass judgments on First Proof 10 and selected Erdős problems. We conclude that proof-generation papers should treat pass@k as the default baseline and compare architecture gains against equal token budgets.

## 1. Introduction

AI systems have moved quickly from solving school-level math benchmarks to writing plausible solutions for Olympiad and research-grade problems. Recent systems have reached medal-level performance on the International Mathematical Olympiad, and several AI-assisted projects now claim progress on previously open mathematical problems. This changes the evaluation question. It is no longer enough to ask whether a model can produce an answer on a benchmark with a short verifier. We need to know which inference-time methods reliably improve proof generation, how to judge long proof attempts, and whether agentic scaffolds add value beyond sampling more attempts.

This paper is a small empirical study of those questions. We focus on natural-language proof generation, not formal proof search. That choice matters. Formal systems such as Lean-based theorem provers can give strong correctness guarantees, but they apply only where the problem can be formalized and where the library supports the needed mathematics. Natural-language proof generation is weaker as evidence, but broader as a testbed: every problem in our set can be attempted in this form.

The central comparison is deliberately simple. We test four families of methods:

1. Pass@k generation: sample multiple complete proof attempts and take the best judged answer.
2. Seeded generation: first ask for ideas, then generate proofs from those ideas.
3. Full pipeline: generate, verify, and revise in a staged loop.
4. Seeded full pipeline: combine seeded ideation with generator-verifier-reviser refinement.

The initial hypothesis was that richer scaffolds would dominate. The data does not support that as a broad claim. On like-for-like Phase 1 comparisons, the richer modes are flat against pass@3. Some asymmetric seed-full runs look better, especially with max reasoning enabled, but they do not yet establish a clean architectural win. The more robust result is that sampling more, judging carefully, and enabling reasoning effort matter more than the nominal agent architecture.

## 2. Related Work and Scope

The background is a fast-moving literature. AlphaProof and AlphaGeometry showed that formal and geometry-specialized systems could reach silver-level IMO performance. Gemini Deep Think and other frontier systems later reported gold-level performance in natural language. Harmonic's Aristotle and other formal systems push in the opposite direction: use informal reasoning to guide formal proof search. AlphaEvolve demonstrates a different pattern again, using code-generating evolutionary search where an automatic evaluator is available.

Those systems are not directly comparable to the setting here. We study black-box API models producing natural-language proofs under fixed prompts and limited budgets. The most relevant prior work is IMO-Bench, which provides AnswerBench, ProofBench, and GradingBench; Aletheia-style generator-verifier-reviser loops for Erdős problems; and the First Proof challenge, which stress-tests research-level proof attempts where expert review is required.

We intentionally exclude tool-heavy theorem proving, Lean formalization, and search over executable constructions. These are important, but they answer a different question. Our question is: if a researcher can call current language models and can afford multiple attempts, which lightweight proof-generation scaffold should they use?

## 3. Dataset

We evaluate on a 70-problem set. The base is the 60-problem IMO-ProofBench. We add 10 recent research-facing problems, selected because public ground-truth or expert-accepted solutions exist and because they sit near the current frontier of AI mathematical capability.

| Subset | Count | Description |
|---|---:|---|
| ProofBench Basic | 30 | Easier IMO-style proof problems |
| ProofBench Advanced | 30 | Harder IMO-style proof problems |
| Research-2026 | 10 | Erdős, First Proof, and FrontierMath-derived problems |

The Research-2026 set contains Erdős 333, 397, 654, 659, 1051; First Proof 4, 5, 6, 10; and the Ramsey hypergraphs FrontierMath Open Problem. We do not claim these are newly solved here. They are used as hard evaluation items with known solution context.

For analysis we also use a unified difficulty scale. The scale is imperfect but useful: pre-competition, competition-hard, research-easy, research-medium, research-hard, and research-frontier. Performance collapses sharply as difficulty rises. In the architecture bucket, the canonical judge gives an 86.1% pass rate on pre-competition items, 28.9% on competition-hard items, 22.6% on research-easy items, 1.8% on research-medium items, and 0% on research-hard/frontier items.

## 4. Judging and Calibration

Long proof grading is the main methodological risk. We cannot manually grade thousands of proof attempts. Instead, we use a model judge and calibrate it against IMO-GradingBench. The judge prompt restricts outputs to 0, 1, 6, or 7, which makes the main target pass/fail at 6/7 rather than fine-grained mathematical partial credit.

On a 200-item GradingBench sample, the strongest judges are clustered closely at the pass/fail threshold:

| Judge | Pass agreement | Recall | Precision | F1 | Pearson r | Cost / call |
|---|---:|---:|---:|---:|---:|---:|
| GPT-5.4-nano xhigh | 89.3% | 70.0% | 93.3% | 0.800 | 0.712 | $0.0370 |
| DeepSeek V4 Pro | 88.9% | 82.5% | 82.5% | 0.825 | 0.756 | $0.0150 |
| DeepSeek V4 Flash | 87.4% | 79.4% | 80.6% | 0.800 | 0.756 | $0.0039 |
| Gemini 3.1 Pro | 86.4% | 95.2% | 71.4% | 0.816 | 0.872 | $0.0348 |

We use DeepSeek V4 Flash as the canonical judge because it is close to the best pass/fail judges but much cheaper. Gemini 3.1 Pro is the best continuous calibrator, but it is more lenient at the pass threshold. This choice affects headline results: weaker or more lenient judges tend to like pipeline outputs more.

We also calibrated model math ability on a 50-problem AnswerBench subset. DeepSeek V4 Pro scored 47/50, GPT-5.4-nano xhigh scored 45/49, a synthesized Gemini 3 Flash xhigh row scored 45/50, and DeepSeek V4 Flash scored 44/50 at low cost. Reasoning effort is a major confound: GPT-OSS improves from 29/50 to 37/50 when moved to xhigh, while DeepSeek V4 Flash drops from 44/50 to 25/50 when reasoning is disabled.

## 5. Architecture Experiments

The architecture bucket contains 2,098 trial rows, with 1,992 valid canonical judge scores. Phase 1 is the cleanest comparison: six models, three architecture modes, and the same 70 problems. In that like-for-like slice, the modes are essentially tied.

| Mode, Phase 1 only | Valid n | Mean score | Pass rate |
|---|---:|---:|---:|
| pass@3 generate | 406 | 2.23 | 31.8% |
| seeded generate | 416 | 2.18 | 31.2% |
| full generator-verifier-reviser | 412 | 2.22 | 31.6% |

This is the first major finding. The extra scaffolding does not clearly improve the result. In some individual model cells it helps, and in others it hurts. DeepSeek V4 Pro does best in the full loop; DeepSeek V4 Flash does slightly best in seeded generation; Qwen is roughly tied between generate and seeded generate; several weaker models regress under the richer prompts.

Across all architecture rows, seed_full has the highest mean score and pass rate:

| Mode, all architecture rows | Valid n | Mean score | Pass rate |
|---|---:|---:|---:|
| generate | 543 | 2.31 | 32.6% |
| seeded generate | 555 | 2.29 | 33.0% |
| full | 550 | 2.24 | 31.8% |
| seed_full | 344 | 2.58 | 36.9% |

But this table is not a clean architecture result. Seed_full coverage is asymmetric: it comes from Phase 2, Phase 3, and the reasoning rerun, not from the same six-model Phase 1 sweep. The best small-model cell is Gemma 4 31B with max reasoning and seed_full: mean 3.31, pass rate 47.1%, and three Research-2026 pass judgments. This is promising, but it bundles architecture with reasoning effort and a different coverage pattern.

## 6. Scaling and Reasoning

The clearest improvement comes from inference-time scaling. In the generate rows, the first branch is a correlated pass@1 proxy rather than an independent draw, but the direction is still useful. In Phase 1, pass@3 improves over the first branch by 0.40 mean score points and raises pass rate from 25.7% to 31.2%. In the reasoning rerun, the gain is 0.56 points and pass rate rises from 28.5% to 35.0%.

The dedicated scaling bucket gives a cleaner view by exhaustively averaging over subsets of branches.

| Model | Reasoning | Problems | n=1 mean/pass | n=7 mean/pass |
|---|---|---:|---:|---:|
| Gemma 4 31B | default | 30 | 0.31 / 4% | 1.40 / 20% |
| GPT-OSS 120B | default | 30 | 0.10 / 1% | 0.47 / 7% |
| Gemma 4 31B | max | 70 | 1.92 / 27% | 3.20 / 45% |
| GPT-OSS 120B | max | 70 | 1.68 / 24% | 3.08 / 44% |
| DeepSeek V4 Flash | default | 70 | 2.81 / 40% | 4.54 / 64% |

The second major finding is therefore straightforward: pass@k continues to buy performance, at least through n=7, and the gain is larger than the clean architecture deltas.

Reasoning effort is similarly large. For Gemma and GPT-OSS, max reasoning improves every comparable mode. GPT-OSS seeded generation rises from 1.09 mean score and 15.9% pass rate to 2.54 and 37.7%. Gemma generation rises from 1.49 and 21.7% to 2.74 and 37.1%. These are not subtle effects.

## 7. Role Swaps and Model Diversity

We also tested whether assigning different models to ideator, generator, verifier, and reviser roles helps. The role-swap bucket combines Gemma 4 31B and GPT-OSS 120B, with default and max reasoning settings.

The result is weakly positive at best. Averaging the two random baselines gives 1.78 mean score and 25.7% pass rate at default reasoning, and 3.27 mean score and 46.7% pass rate at max reasoning. The best single-role condition, using GPT-OSS as verifier, reaches 2.07/29.0% at default and 3.63/51.4% at max. That is an uplift, but only about 3-5 pass-rate points over random assignment. It is much smaller than the reasoning-effort effect.

This does not rule out model diversity. It suggests that naive role assignment is not a reliable substitute for stronger reasoning, more samples, or better judging.

## 8. Research-Grade Problems

Research-2026 results should be read cautiously. The canonical judge can identify signal, but it cannot certify new mathematics. Still, the distribution is informative.

Across architecture and roleswap valid Research-2026 rows, we see 46 pass judgments out of 439 judged attempts. They are highly concentrated: First Proof 10 accounts for 32, Erdős 654 for 8, Erdős 333 for 3, and Erdős 397, Erdős 659, and First Proof 5 for one each. The harder First Proof problems and Ramsey hypergraphs are mostly unsolved in these runs.

In the scaling bucket, DeepSeek V4 Flash at n=7 receives pass judgments on four Research-2026 problems: Erdős 1051, Erdős 659, First Proof 10, and First Proof 6. Gemma and GPT-OSS at max reasoning each reach one research solve at n=7. These are not claims of mathematical resolution. They are evidence that inexpensive models can occasionally land near known frontier solutions when sampled enough and judged by a calibrated proof grader.

## 9. Limitations

The largest limitation is automated judging. We calibrate against GradingBench, but a pass judgment on a research problem is not the same as expert verification. This is especially important for frontier items, where plausible but wrong proofs are common.

The second limitation is asymmetry. The cleanest architecture comparison lacks seed_full. The seed_full results are suggestive but confounded by reasoning effort and source experiment. A future run should evaluate all four modes across the same model/problem grid and equalize token budgets.

The third limitation is dataset size. Seventy problems is enough to see broad effects, but the research subset has only ten problems and the hardest bins have very few successes. This makes frontier conclusions fragile.

Finally, the cost accounting is incomplete. We record many per-trial costs, but total project cost includes failed calls, judge calls, reruns, and human iteration.

## 10. Discussion

The paper's practical recommendation is simple: start with pass@k, use a calibrated judge, turn reasoning on when the model needs it, and be skeptical of architectural improvements unless they beat equal-budget sampling. The generator-verifier-reviser loop is intuitively appealing, and in high-end systems it may be essential. In this dataset, however, the lightweight version does not consistently outperform simple repeated generation.

This is not a failure of agentic proof search as a field. It is a warning about baselines. A pipeline that triples token use should not be compared to pass@1. It should be compared to pass@3 or pass@9. Once we make that comparison, most of the apparent architecture gain disappears.

The more encouraging result is that inference-time scaling still works on hard proof problems, and that cheap models are not useless at the frontier. They are unreliable, but occasionally capable. The right next experiment is a clean, equal-budget four-mode sweep with stronger models and human expert review on every claimed research-grade pass.

