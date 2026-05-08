# Comparing Inference-Time Methods for Natural-Language Mathematical Proofs

*Draft v4 — difficulty-stratified analysis, all-trial frontier solves, and statistical CIs.*

## Abstract

Recent work proposes increasingly elaborate inference-time architectures for mathematical proof generation — generator-verifier-revisor pipelines, seeded-ideator multi-trajectory sampling, and combinations — and reports gains over single-shot generation. We test what survives a fair, statistically-controlled comparison on a ~$1,000 budget that drove our model and architecture choices throughout. On 70 problems (60 IMO-ProofBench + 10 frontier-tier 2026 research problems), six cost-feasible base models, four architectures, and three judges: **(1) the generator-verifier-revisor pipeline does not beat pass@3 at any difficulty tier under either strict judge** (paired Δ = −0.08, 95% CI [−0.27, +0.13], n=533, p=0.45); on Gemma at reasoning=max it *hurts* (Δ = −0.57, p=0.023). **(2) Seeded-ideator-plus-pipeline beats pass@3 only on cheap models at reasoning=max** (Δ = +0.60 [+0.23, +0.99], p=0.003); at default reasoning the lift is null. At its proper pass@9 baseline the lift collapses. The pass@1 → pass@3 jump alone (+0.39 mean, +5pp pass rate) is itself larger than every architecture-vs-architecture delta — most of what looks like "architecture lift" against a pass@1 baseline is just sample-size doubling. **(3) Judge choice flips conclusions for cheap models**: P(Gemini pass | strict-judge fail) = 0.37 [0.34, 0.40] across 1,440 triple-judged trials; the two strict judges agree on 95.5% of pass/fail decisions. **(4) Pass-rate degrades sharply with difficulty**: 86% / 29% / 23% / 2% / 0% / 0% from pre-competition to research-frontier. **(5) Pooling all 3,178 trials yields 32 strict-judge R26 solves; DeepSeek-v4-flash at pass@7 produces the only strict solves of Erdős-1051 (research-medium) and FirstProof-6 (research-hard)**. Practical recommendations within the cost regime tested: draw more samples before adding pipeline depth, keep reasoning enabled where the model exposes it (a long-established effect we confirm rather than discover), and audit with at least two judges of different leniency. The same budget that constrained this paper makes the cheapest follow-ups — a v4-pro audit and multi-seed reruns on the four cells driving the +0.6 deltas — feasible at ~$20.

## 1. Introduction

Language models have moved from saturating school-math benchmarks to plausibly contributing to research mathematics within two years. The trajectory runs from GSM8K and MATH (Hendrycks et al., 2021), through AIME and IMO competitions — AlphaProof took silver in 2024 (Hubert et al., 2025), and gold-tier systems from DeepMind (DeepMind, 2025), OpenAI (Wei et al., 2025), and Harmonic (Achim et al., 2025) landed in 2025 — and on toward open problems. The Erdős repository now lists dozens of model-assisted contributions, and Tao describes recent solves as "major milestones" indicating models can attack genuinely novel problems (Tao, 2026).

Alongside the capability arc, the engineering question is which inference-time methods are worth their tokens. Two methodological gaps motivate this work. First, a common comparison in recent agentic-math reports — pipeline (generator–verifier–revisor) vs. single-shot generation — is unfair on its face. A three-step pipeline burns roughly three times the tokens of a single generation, so the proper baseline is pass@3 (or pass@n for an n-step pipeline), not pass@1. Second, evaluation of free-form proofs at scale relies on automated judges, and the gap between a "lenient" judge and our strict judges is large enough to flip qualitative conclusions about which architecture wins.

A third constraint shaped every choice we made: a ~$1,000 OpenRouter budget. That kept us off frontier-tier judges (Gemini-3.1-Pro at $0.035/call is ~9× our canonical), off frontier-tier generators in the main grid, and forced uneven coverage of the most expensive architecture (`seed_full`, ~9 calls/trial, ran on three of six base models). We flag this throughout, because the same constraints that bounded this study point toward the cheapest follow-ups that would tighten our headline numbers.

We do not propose a new method. We characterize a six-by-four-by-three space (model × architecture × judge) on a 70-problem benchmark and audit what holds up under paired bootstrap CIs and permutation tests. Contributions:

1. A token-cost-fair, statistically-tested comparison of pass@k against the generator-verifier-revisor pipeline, the seeded-ideator approach, and the combined ideator-plus-pipeline architecture, stratified by problem difficulty.
2. A direct quantification of judge-induced variance with cell-level numbers and CIs on the strict-vs-lenient one-sided false-positive rate.
3. A frontier-solves audit pooling all 3,178 trials across architecture and scaling experiments, with per-cell breakdowns and false-positive-rate context.
4. Reproducible per-experiment artifacts (`results/architecture_20260506/`, `results/scaling_20260506/`, plus three calibration buckets) totaling ~3,200 trial rows.

## 2. Background

**Capability arc.** AlphaProof (Hubert et al., 2025) achieved IMO silver in 2024 with a specialized formalizer trained via AlphaZero-style self-play. In 2025, three independent gold-tier systems landed within weeks of each other: DeepMind's Deep Think (DeepMind, 2025), OpenAI's IMO submission (Wei et al., 2025), and Harmonic's Aristotle (Achim et al., 2025), accompanied by an open-source agentic framework reaching gold-tier performance with frontier base models (Huang & Yang, 2025). Through early 2026, models began producing solutions to open problems on the Erdős repository (Tao, 2026; Erdős Problems, n.d.), and Epoch's FrontierMath open-problem set saw its first model-credited solution (Glazer et al., 2024). Knuth's "Claude's Cycles" essay (Knuth, 2026) and DeepMind's Aletheia case studies (Feng et al., 2026a,b) document the iterative human–AI workflows that have actually produced research-grade results.

**Benchmarks.** We use IMO-ProofBench (Luong et al., 2025), a 60-problem corpus of olympiad proofs split into 30 "Basic" and 30 "Advanced" tiers, paired with a hardened automated grader that correlates with human IMO judges at Pearson r=0.96. We augment this with ten 2026 research problems drawn from the Erdős repository (333, 397, 654, 659, 1051), the First Proof open challenge (problems 4, 5, 6, 10) (Abouzaid et al., 2026), and the Ramsey-hypergraph entry from Epoch's FrontierMath open-problem set. We do not claim these ten as a novel benchmark; we treat them as a small frontier-tier extension and refer to the union as PB+R26.

**Architectures we compare.** *Pass@k*: sample k independent solutions and take the best (Brown et al., 2020); repeated sampling and self-consistency are long-established strong baselines (Chen et al., 2021; Wang et al., 2022). *Generator-verifier-revisor pipeline*: a generator emits a candidate, a verifier critiques it, and a revisor edits — looped a fixed number of times. This pattern appears in Aletheia (Feng et al., 2026b) and in the Huang–Yang IMO-gold framework (Huang & Yang, 2025), among others. *Seeded ideator*: an upstream ideation pass produces several candidate solution sketches (we use three), each of which feeds an independent generation. *Ideator + pipeline*: each ideated seed runs through the verifier-revisor loop, tripling token cost.

**Scope.** We restrict to natural-language proof generation. We do not study formal verification (Lean, AlphaProof, Aristotle), evolutionary search (AlphaEvolve; Novikov et al., 2025; Georgiev et al., 2025), or hybrid neuro-symbolic systems.

## 3. Methodology

### 3.1 Architectures

We implement all four architectures in a single pipeline (`src/pipeline.py`) with shared model-call infrastructure. Generation, verification, and revision use lightly hardened versions of the prompts published with DeepMind's Aletheia and Huang & Yang's IMO repository. Final grading uses DeepMind's IMO-ProofBench judge prompt, restricted to {0, 1, 6, 7} on a 0–7 scale.

- **Pass@k.** Run k independent generation calls; take max judge score. We sweep k ∈ {1, 3} as the headline comparison, k ∈ {1, 3, 5, 7, 9} in the dedicated scaling experiment. The `generate` mode in our architecture sweep produces 3 branches per trial and reports max-branch score, i.e. it is exactly pass@3.
- **Generator-verifier-revisor pipeline (`full`).** Up to three verifier-revisor iterations after the initial generation; early-stop when the verifier emits `VERDICT: correct`. ~3 calls per trial — token-equivalent to pass@3.
- **Seeded ideator (`seed_generate`).** A single ideation call produces three sketch directions; each direction is realized as one full solution; we take the best. ~3 calls — token-equivalent to pass@3.
- **Ideator + pipeline (`seed_full`).** Each of three ideated seeds runs through the verifier-revisor loop; we take the best final solution. ~9 calls — token-equivalent to pass@9.

The fair token-cost comparisons are pass@3 ↔ {generate, seed_generate, full} and pass@9 ↔ seed_full.

### 3.2 Models, reasoning, and dataset

We evaluate six cost-feasible base models: DeepSeek-v4-flash, DeepSeek-v4-pro, Gemini-3-flash-preview, Gemma-4-31B-IT, GPT-OSS-120B, and Qwen3.6-35B-A3B. Frontier-tier models (Claude Opus 4.7, GPT-5.4-Pro, Kimi-k2.6, Gemini-3.1-Pro) would have consumed our entire budget on a single phase; the expensive-models probe (Appendix A.5) is the small follow-up we could afford. For Gemma-4 and GPT-OSS we additionally run a "reasoning=max" condition. The 60-problem ProofBench split is taken unmodified from DeepMind. The R26 augmentation comprises ten 2026-disclosed research problems; we graded each on a six-level difficulty scale (Table 1).

| Tier | Source | Problems | n |
|---|---|---|---:|
| pre-competition (d=0) | PB-Basic | 30 problems | 30 |
| competition-hard (d=1) | PB-Advanced + Erdős 397 | 30 PB-Adv + 1 R26 | 31 |
| research-easy (d=2) | Erdős 333, 654, 659; FirstProof 10 | 4 R26 | 4 |
| research-medium (d=3) | Erdős 1051; FirstProof 5 | 2 R26 | 2 |
| research-hard (d=4) | FirstProof 4, 6 | 2 R26 | 2 |
| research-frontier (d=5) | Ramsey hypergraphs | 1 R26 | 1 |

### 3.3 Judges

Three judges score every architecture trial: DeepSeek-v4-flash (canonical), DeepSeek-v4-pro (audit, slow/strict), and Gemini-3-flash-preview (audit, cheap/lenient). Section 4 reports the GradingBench calibration we ran to choose v4-flash as default.

### 3.4 Statistical methodology

For paired comparisons, we use the within-(model, reasoning, problem) score difference. Confidence intervals are 95% percentile bootstrap (5,000 resamples; np.random seed = 20260507). Two-sided p-values are sign-flip permutation tests (10,000 permutations). For pass-rate deltas we paired the binary pass indicators directly. Reported "Δ" is the paired mean of `mode_a − mode_b` over the cells where both modes were observed.

## 4. Calibration

### 4.1 Judges on GradingBench

We tested ten judge configurations on a 200-problem random sample of DeepMind's GradingBench, holding the prompt fixed (output restricted to {0, 1, 6, 7}). Our priority metric is `pass_agree_at_6`: agreement with the human pass/fail verdict at the IMO threshold. The top-tier configurations are summarized in Table 2; the full table is in Appendix A.1.

| Judge | n | pass≥6 agree | F1 | Pearson r | $/call |
|---|---:|---:|---:|---:|---:|
| GPT-5.4-nano @ xhigh | 196 | 89.3% | 0.800 | 0.711 | $0.0370 |
| DeepSeek-v4-pro | 198 | 88.9% | 0.825 | 0.756 | $0.0150 |
| **DeepSeek-v4-flash** | 199 | **87.4%** | **0.800** | **0.756** | **$0.0039** |
| Gemini-3.1-pro | 199 | 86.4% | 0.816 | 0.872 | $0.0348 |
| Gemini-3-flash | 200 | 64.0% | 0.633 | 0.606 | $0.0162 |

DeepSeek-v4-flash is on the Pareto frontier: 87.4% pass-agreement at $0.004/call, r=0.756. The price gap to the next-best judges is large: v4-pro is **3.8× more expensive** ($0.0150), GPT-5.4-nano-xhigh **9.5×** ($0.0370) and ten times slower, and Gemini-3.1-Pro — the highest-correlation judge at r=0.872 — **8.9×** ($0.0348) and would have cost ~$250 to grade the architecture sweep alone. v4-flash is the only top-pass-agreement judge that lets us grade ~5,000 long proofs without dominating the budget. We use it as canonical, with v4-pro as the strict audit judge used selectively where the audit is load-bearing. Gemini-3-flash-preview (the cheap lenient judge — distinct from Gemini-3.1-pro, which we could not afford on architecture trials) drives the judge-disagreement results in Section 5.

### 4.2 Generator selection on AnswerBench

We tested 13 model–reasoning configurations on AnswerBench-50 (50 verifiable-answer problems judged by Gemini-3-flash-lite). Reasoning is the dominant variable: GPT-OSS-120B moves from 58% to 74% on the toggle alone, Gemini-3-flash from 74% to 90%, DeepSeek-v4-flash from 88% to 50% when reasoning is forced off. Six base models cleared 60% accuracy with sensible reasoning settings; we kept all six for the architecture sweep. Full table in Appendix A.2.

## 5. Main results

### 5.1 Architecture comparison at default reasoning

Pooled across the six base models on PB+R26, the four architectures are barely separated under v4-flash (Table 3, 95% bootstrap CIs). Pass@1 — the first branch of every `generate` trial, scored independently — is included as the unfair-but-common baseline against which agentic systems are usually pitched:

| Mode | tokens | n | mean (0–7) | pass rate (≥6) |
|---|---|---:|---:|---:|
| pass@1 (1st branch of generate) | ~1× | 613 | 1.97 [1.79, 2.15] | 0.28 [0.25, 0.32] |
| generate (pass@3) | ~3× | 543 | 2.31 [2.13, 2.49] | 0.33 [0.30, 0.37] |
| seed_generate | ~3× | 555 | 2.29 [2.11, 2.47] | 0.33 [0.30, 0.37] |
| full (pipeline) | ~3× | 550 | 2.24 [2.06, 2.42] | 0.32 [0.28, 0.35] |
| seed_full | ~9× | 344 | 2.58 [2.34, 2.81] | 0.37 [0.32, 0.42] |

The pass@1 → pass@3 step alone moves the mean +0.39 and the pass-rate +5pp at a 3× token cost — without any architectural change. That gap is *larger than every architecture-vs-architecture delta in this table.* So pass@1 → architecture is a real improvement (+0.27 to +0.61 mean), but most of it is the pass@1 → pass@3 sample-size effect. Holding the token budget fixed by comparing each scaffold to its like-cost pass@k baseline is the only honest read.

The right way to read the architecture differences is via paired contrasts. The pipeline-vs-pass@3 contrast, the cleanest available because both modes were collected on every (model, reasoning, problem) cell, is null:

| Contrast | n pairs | mean Δ | 95% CI | p |
|---|---:|---:|---:|---:|
| `full − generate` (pipeline vs pass@3) | 533 | −0.079 | [−0.272, +0.126] | 0.45 |
| `seed_generate − generate` | 539 | −0.028 | [−0.206, +0.160] | 0.78 |
| `seed_full − generate` (pooled all reasoning) | 337 | +0.315 | [+0.068, +0.570] | 0.013 |

The pooled `seed_full − generate` significance is real but mostly an artifact of which cells were populated, as Section 5.4 makes clear. The pipeline by itself does not beat pass@3.

### 5.2 Difficulty-stratified analysis

Pass-rate degrades sharply with difficulty (Figure 5; Table 4):

| Tier | n trials | mean | 95% CI | pass | 95% CI |
|---|---:|---:|---:|---:|---:|
| pre-competition (d=0, PB-Basic) | 231 | 6.02 | [5.71, 6.30] | 0.86 | [0.81, 0.90] |
| competition-hard (d=1, PB-Adv+E397) | 1,507 | 2.04 | [1.88, 2.20] | 0.29 | [0.27, 0.31] |
| research-easy (d=2) | 115 | 1.50 | [0.99, 2.05] | 0.23 | [0.16, 0.30] |
| research-medium (d=3) | 57 | 0.14 | [0.00, 0.40] | 0.02 | [0.00, 0.05] |
| research-hard (d=4) | 55 | 0.00 | [0.00, 0.00] | 0.00 | [0.00, 0.00] |
| research-frontier (d=5) | 27 | 0.00 | [0.00, 0.00] | 0.00 | [0.00, 0.00] |

Strict-judge pass rate falls from 86% at PB-Basic to ~0% beyond research-medium. Three observations follow.

First, **architecture lift is uniformly null on hard tiers** under strict judges. The `full − generate` contrast is null at every tier (overall +0.06 [−0.34, +0.49] on R26 only, p=1.0). The `seed_generate − generate` contrast is significantly *negative* on R26 (Δ=−0.24 [−0.54, −0.03], p=0.030). The `seed_full − generate` contrast on R26-only is +0.48 [−0.14, +1.17] (n=42, p=0.22) — directionally positive but not significant.

Second, **the only architecture lift that survives is on competition-hard problems** (`seed_full − generate` Δ=+0.33 [+0.04, +0.63] on d=1, n=255, p=0.032). And only when paired with reasoning=max (Section 5.4).

Third, **any aggregate "pipeline beats X" claim has to be read alongside this gradient**. Most of our 70-problem benchmark is pre-competition and competition-hard, and the architecture differences observable on those problems are mostly small enough that judge noise and inter-model variance dominate.

Figure 6 shows the lift-by-tier forest plot in full.

### 5.3 Judge choice flips the cheap-model comparison

The same raw outputs scored by Gemini-3-flash-preview tell a different story (Table 5; Figure 1):

| Model | v4-flash Δ | v4-pro Δ | Gemini Δ |
|---|---:|---:|---:|
| DeepSeek-v4-flash | +0.16 | −0.30 | −0.18 |
| DeepSeek-v4-pro | +0.32 | +0.28 | −0.21 |
| Gemini-3-flash-preview | −0.24 | −0.54 | **+0.83** |
| Gemma-4-31B-IT | −0.10 | −0.66 | **+0.30** |
| GPT-OSS-120B | +0.24 | +0.06 | **+0.51** |
| Qwen3.6-35B-A3B | −0.47 | −0.73 | **+0.14** |

Under Gemini, four of six models — all the cheap ones — show clean +0.14 to +0.83 lift from the pipeline. The strict judges show no such pattern. This is not noise. On the 1,440 cells where all three judges scored at the architecture experiment:

| Pair | pass-rate agreement | 95% CI |
|---|---:|---:|
| v4-flash vs v4-pro | 95.5% | [94.4%, 96.5%] |
| v4-flash vs Gemini | 73.7% | [71.5%, 76.0%] |
| v4-pro vs Gemini | 72.9% | [70.6%, 75.3%] |

The disagreement is one-sided. **P(Gemini calls pass | v4-flash calls fail) = 0.368 [0.338, 0.398]** over n=987 strict-fail cases. The reverse, P(Gemini calls fail | v4-flash pass), is 0.035 [0.020, 0.053] over n=453 strict-pass cases. The lenient judge over-passes on roughly a third of strict-fail cases, while the strict judges agree with each other on 95.5% of pass/fail decisions. Gemini's lenience is a systematic offset, not noise. We use v4-flash for headline numbers and report the Gemini view explicitly where it diverges.

### 5.4 Where seeded-ideator-plus-pipeline does help

The pooled `seed_full − generate` lift in Section 5.1 is +0.32 (p=0.013), but this aggregate is heavily confounded by reasoning. Stratifying:

| Stratum | n pairs | mean Δ | 95% CI | p |
|---|---:|---:|---:|---:|
| seed_full − generate, default reasoning | 203 | +0.128 | [−0.182, +0.453] | 0.46 |
| seed_full − generate, reasoning=max | 134 | **+0.597** | **[+0.231, +0.993]** | **0.003** |

The lift is *entirely* driven by the reasoning=max cells. Per-cell paired tests confirm:

| Cell | n | mean Δ | 95% CI | p | Δ pass-rate | 95% CI | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gemma-4 max, seed_full − generate | 70 | **+0.571** | [+0.071, +1.114] | 0.035 | +0.100 | [+0.029, +0.186] | 0.036 |
| GPT-OSS max, seed_full − generate | 64 | **+0.625** | [+0.094, +1.219] | 0.048 | +0.094 | [+0.016, +0.172] | 0.073 |
| Gemma-4 max, full − generate | 70 | **−0.571** | [−1.100, −0.100] | 0.023 | −0.071 | [−0.143, 0.000] | 0.122 |
| GPT-OSS max, full − generate | 65 | +0.169 | [−0.492, +0.892] | 0.71 | +0.031 | [−0.077, +0.138] | 0.77 |
| DeepSeek-v4-flash default, seed_full − generate | 66 | +0.152 | [−0.485, +0.773] | 0.71 | +0.030 | [−0.061, +0.121] | 0.76 |
| DeepSeek-v4-pro default, full − generate | 60 | +0.233 | [−0.467, +0.917] | 0.56 | +0.033 | [−0.067, +0.133] | 0.75 |
| Gemma-4 default, seed_full − generate | 69 | +0.145 | [−0.377, +0.667] | 0.57 | +0.014 | [−0.072, +0.101] | 1.0 |
| GPT-OSS default, seed_full − generate | 68 | +0.088 | [−0.441, +0.603] | 0.86 | +0.015 | [−0.059, +0.088] | 1.0 |

Two narrow positive results: Gemma-4 and GPT-OSS at reasoning=max gain ~+0.6 mean score and ~+10pp pass-rate from seed_full vs pass@3. **No other pipeline-vs-pass@3 comparison clears p<0.05.** Strikingly, *the pipeline alone (`full`) hurts Gemma-4 at reasoning=max by −0.57 (p=0.023)*: combining heavy reasoning with a verifier-revisor loop is worse than just sampling three times. This is a small-sample finding (n=70) and we do not over-interpret it, but it cuts directly against the case that "more pipeline = better."

We have no v4-pro grades on the reasoning=max seed_full cells, so the +0.57 / +0.625 lift cannot be cross-validated against the second strict judge. The v4-flash gain is large enough that we conclude it is most likely real, but a v4-pro audit on those cells remains a gap (Section 8).

The fairer baseline for seed_full is pass@9, not pass@3. Section 6.2 shows that at the same token budget, pass@7-extrapolated and pass@9 match (Gemma max) or exceed (DS-v4-flash, GPT-OSS max) seed_full.

### 5.5 Frontier solves — all trials pooled

We pool all 3,178 v4-flash-judged trials across the architecture (2,098 trials) and scaling (1,080 trials at n ∈ {1,3,5,7} per problem) experiments. A "cell" is a distinct (model × architecture-or-pass@n × reasoning × source-experiment) configuration. Each R26 problem has ~33 cells. A cell "solves" under judge J if any branch of that cell scores ≥6 under J. (For architecture trials, this is the trial-level judge score; for scaling trials, max over branch_scores.) Counts and pass rates per problem (Figure 4):

| Problem | Difficulty | cells | v4f solves | rate | v4p solves | rate | Gemini solves | rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| FirstProof 10 | research-easy | 33 | 23 | 70% | 12 | 36% | 8 | 24% |
| Erdős 654 | research-easy | 33 | 5 | 15% | 3 | 9% | 6 | 18% |
| Erdős 333 | research-easy | 33 | 1 | 3% | 0 | 0% | 2 | 6% |
| Erdős 659 | research-easy | 33 | 1 | 3% | 1 | 3% | 7 | 21% |
| Erdős 397 | competition-hard | 33 | 1 | 3% | 0 | 0% | 1 | 3% |
| FirstProof 5 | research-medium | 33 | 1 | 3% | 0 | 0% | 1 | 3% |
| **Erdős 1051** | research-medium | 33 | **1** | 3% | 0 | 0% | 14 | 42% |
| **FirstProof 6** | research-hard | 33 | **1** | 3% | 0 | 0% | 5 | 15% |
| FirstProof 4 | research-hard | 32 | 0 | 0% | 0 | 0% | 1 | 3% |
| Ramsey hypergraphs | research-frontier | 33 | 0 | 0% | 0 | 0% | 3 | 9% |

Across all 327 R26 cell-trials, v4-flash strict yields 32 solving cells; v4-pro strict yields 16; Gemini lenient yields 48. Pooling architecture and scaling adds five v4-flash solves over architecture alone, including the only strict solves of Erdős-1051 (research-medium) and FirstProof-6 (research-hard).

The 32 strict-judge solves concentrate: 23 on FirstProof-10 (the research-easy item with the most public solution context); 5 on Erdős-654 (multiple architectures × four base models — the cleanest reproducible research-tier solve); and 4 single-cell solves on Erdős-333, Erdős-1051, Erdős-659, and FirstProof-6 — the last two from DeepSeek-v4-flash at pass@7 in the scaling bucket. The single Erdős-397 and FirstProof-5 strict solves came from DeepSeek seed_generate cells.

**False-positive context.** A single strict-judge solve out of 33 trials (3%) on a research-medium-or-harder problem must be read alongside Section 5.3: the lenient judge over-passes on roughly a third of strict-fail cases. For Erdős-1051 the contrast is sharp — Gemini awards 14 passes against the strict judges' single (v4-flash) and zero (v4-pro). The defensible reading of any single strict-judge solve at this difficulty is "candidate for expert review," not "confirmed solve." On research-easy problems with multiple-architecture × multiple-model strict solves (FirstProof-10, Erdős-654), the case is much stronger. Research-medium-and-harder average 3% strict solve-rate; research-frontier (Ramsey) is 0%. The pipelines we tested do not extend the capability frontier on this dataset; they help on the existing one.

## 6. Secondary results

### 6.1 Reasoning effects are larger than architecture effects (a confirmation)

Reasoning-on adds +0.78 to +1.60 to v4-flash mean score on PB+R26 (Gemma and GPT-OSS; per-cell deltas in Appendix A.4) and 16–38 percentage points on AnswerBench-50. Architecture deltas (Sections 5.1, 5.4) span −0.6 to +0.7 — so reasoning effects are roughly 3–5× larger (Figure 3). This is well-established by the chain-of-thought literature (Wei et al., 2022; OpenAI, 2024) and we present it as confirmation rather than discovery; we restate it because it sets the bar architecture has to clear. Reasoning also costs tokens (often substantially), so the comparison is itself token-asymmetric; comparing reasoning-on to extra pass@k samples at matched cost is the right next step.

### 6.2 Pass@k continues to scale through k=7, with significant deltas

A separate scaling experiment recomputed pass@n via exhaustive enumeration over all C(M, n) subsets of available branches — an unbiased estimator that avoids the correlated-trajectory artifact of the nested-prefix method. Curves under v4-flash (Figure 2; bootstrap CIs computed across problems):

| Model | Reasoning | n=1 mean | n=3 mean | n=7 mean | pass@7−pass@3 Δ | 95% CI | p |
|---|---|---:|---:|---:|---:|---:|---:|
| DS-v4-flash | default | 2.81 | 3.78 | 4.54 | +0.71 | [+0.43, +1.01] | <0.001 |
| Gemma-4 | max | 1.92 | 2.76 | 3.20 | +0.45 | [+0.26, +0.65] | <0.001 |
| GPT-OSS | max | 1.68 | 2.49 | 3.08 | +0.55 | [+0.35, +0.78] | <0.001 |
| Gemma-4 | default | 0.31 | 0.74 | 1.40 | +0.66 | [+0.22, +1.16] | 0.003 |
| GPT-OSS | default | 0.10 | 0.27 | 0.47 | +0.20 | [0.00, +0.48] | 0.25 |

Two observations. First, pass@k scaling is highly significant (p<0.005 in every cell except GPT-OSS-default which has 30 problems and very low base rates). At reasoning=max the pass@7 means (3.20, 3.08) match seed_full (3.31, 3.00) within their 95% CIs. Pure scaling matches the pipeline at the same token budget. For DeepSeek-v4-flash at default reasoning, scaled pass@7 reaches 4.54 [3.78, 5.25] — clearly above the phase-3 seed_full mean of 3.49 — and lands four R26 strict-judge solves (FirstProof-10, Erdős-1051, Erdős-659, FirstProof-6) versus two for seed_full. The strong-cheap model benefits more from breadth than from pipeline scaffolding.

Second, the slope does not flatten by k=7. For Gemma reasoning=max we extended to k=9 and saw 3.29 [2.55, 4.05] (vs. 3.20 at k=7). The marginal value of further branches is small but positive.

### 6.3 Cross-model role-swap is a null effect

A separate experiment tested cross-model diversity by varying which of GPT-OSS or Gemma fills the ideator/generator/verifier/revisor roles in the seed_full pipeline. At reasoning=max, the eight tested conditions span 2.96 to 3.63 in mean v4-flash score; the two random-baseline conditions are at 3.19 and 3.34. Only one swap — GPT-OSS as verifier (3.63) — clearly beats both baselines. The remaining seven conditions are within ±0.4 of baseline. The "diversity helps" hypothesis is not supported by these data; the suggestive cell may reflect the specific role-model fit rather than diversity per se.

### 6.4 Coverage asymmetry (a budget consequence)

Phase 1 (the canonical six-model × three-mode grid) does not include `seed_full`. At ~9 calls/trial × 70 problems × 6 models, clean Phase-1 seed_full would have consumed roughly a quarter of our budget; we ran it piecewise as confidence grew. The available seed_full data come from Phase 2 (Gemma + GPT-OSS, default reasoning), Phase 3 (DeepSeek-v4-flash, default), and phase1_reasoning (Gemma + GPT-OSS, max). Three base models (DeepSeek-v4-pro, Gemini-3-flash-preview, Qwen3.6-35B-A3B) remain untested on seed_full. Any pooled seed_full statement is over this non-representative subset, weighted toward cheap models. Closing this gap is the single largest follow-up the budget left on the table.

## 7. Resources, errors, and audit

Across the architecture sweep we ran 2,098 trial rows against six base models; 1,080 additional rows in the scaling bucket. Aggregate API spend across all experiments (architecture, scaling, roleswap, calibration) was approximately $800 against an internal $1,000 budget. A note on a known data quality issue: in the original Phase 1 seeded-ideator runs, roughly 10–28% of seeded ideation calls returned malformed outputs and the pipeline silently fell back to a pass@3 generation. This pushes seeded conditions toward the pass@3 baseline and would, if anything, *understate* the seeded-ideator effect relative to a clean implementation. We patched the bug for Phase 2 and downstream experiments, and the seed_full lift in Section 5.4 (which uses Phase 2 / phase1_reasoning data) is unaffected.

## 8. Limitations

**Benchmark contamination.** Most R26 solution-disclosure dates fall in 2026 (FirstProof: February 13, 2026; Erdős solves: spring 2026; FrontierMath open-problem solve: March 2026), as does the IMO-Bench release (November 3, 2025). Several of our generators have post-training cutoffs that overlap with these dates: Gemma-4 (March 31, 2026), DeepSeek-v4 (April 24, 2026). GPT-OSS-120B (released August 5, 2025) is provably contamination-free for every R26 solution and for IMO-Bench. Solve patterns for GPT-OSS and DeepSeek look broadly similar across the architectures — particularly on Erdős-654, which both solve cleanly — which we interpret as weak evidence that contamination is not the dominant signal. We cannot rule it out for the post-cutoff models on individual problems.

**Judging.** We rely on automated judges; calibrated to ~87% pass-agreement on GradingBench, this is more than enough for directional claims but not enough to certify any individual frontier solve. Section 5.5's per-problem strict-judge solve counts of 1/33 should be read as candidates for expert review, not confirmed mathematics. Manual grading at scale is impractical: 5,000+ proof outputs would require months of expert time we do not have.

**Generalization.** Our six base models top out at DeepSeek-v4-pro, well below the strongest commercially available systems. We do not test Claude Opus 4.7, GPT-5.4-Pro, or Gemini-3.1-Pro on the full sweep, though a small expensive-models calibration pass (12 problems, 4 frontier models; Appendix A.5) suggests Kimi-k2.6 deserves a future look.

**Dataset size.** n=70 is small. Only ten problems are research-grade; the n=2 to n=4 per-tier sample at research-medium and harder difficulty makes per-problem confidence intervals on the 0% pass-rate wide enough that we cannot rule out small-but-non-zero capability. The CI on research-hard pass-rate (n=55 trials across 2 problems) is [0.00, 0.00] only because every trial scored zero — a noisier estimator would not have this property.

**Single-judge audit on reasoning=max.** Our cleanest pipeline-lift result (Section 5.4) is observed under v4-flash only. A v4-pro audit on those cells would strengthen the claim. Multi-seed reruns on the four cells driving the +0.57/+0.625 deltas would put proper paired-difference error bars on the magnitude.

## 9. Discussion

Three takeaways for engineering practice.

**The verifier-revisor pipeline does not beat token-matched sampling in our data.** Across 533 paired cells, `full − generate` is null (Δ=−0.08, p=0.45); on Gemma at reasoning=max it hurts (Δ=−0.57, p=0.023). Seeded-ideator-plus-pipeline beats pass@3 by ~+0.6 on cheap models *only* at reasoning=max, and at its proper pass@9 baseline the lift collapses. Within the cost regime tested, the architecture default for natural-language proof generation is "draw more samples before adding pipeline depth, keep reasoning on, use a calibrated judge." Reasoning effects are larger than architecture effects in our deltas, but this is well-documented; we are not relitigating it.

**Audit with judges of different leniency.** Strict judges (v4-flash, v4-pro) agree on 95.5% of pass/fail decisions and paint a consistent picture: limited architecture lift, dominated by reasoning. Gemini-3-flash-preview tells a much rosier story because it calls "pass" on 37% of cases the strict judges call "fail." That lenience is a systematic offset, not noise. A two-judge audit is a cheap discipline.

**Frontier solves exist but are concentrated and judge-fragile.** Pooling all 3,178 trials yields 32 strict-judge R26 solves: 23 on FirstProof-10, 5 on Erdős-654, and 4 single-cell solves on harder problems including DeepSeek-v4-flash pass@7's solves of Erdős-1051 and FirstProof-6. Aletheia (Feng et al., 2026b) reports a similar pattern: 31.5% of its solutions are technically correct under some interpretation but only 6.5% address the intended question. A judged pass from a cheap model on a research-medium-or-harder problem is a candidate, not a theorem.

For practitioners: prefer extra samples to extra pipeline depth, keep reasoning on where the model exposes it, audit with at least two judges of different leniency before concluding that scaffolding helps, and route any frontier-tier strict-judge solve to expert review.

**On budget.** These results came from ~$800 of inference. The same budget kept us off frontier-tier judges and generators and forced uneven seed_full coverage — each a cheap, well-targeted follow-up. ~$20 of v4-pro grades on the four reasoning=max seed_full cells would either harden Section 5.4's p=0.035 result or expose it as a v4-flash artifact. A Phase-1 seed_full extension on the three missing base models closes the largest coverage gap. None of these are expensive on the scale of recent agentic-math papers.

## 10. Future work

Four follow-ups, ordered by cost-per-information. First (~$5–10), a v4-pro audit on the four reasoning=max seed_full cells would harden Section 5.4's marginal p-values. Second (~$15–25), multi-seed reruns on those cells would deliver paired-difference error bars. Third (~$200–400), a Phase-1 seed_full extension on the three uncovered base models closes the largest coverage gap. Fourth, a fair pass@k-vs-pipeline comparison at frontier models (Claude Opus 4.7, GPT-5.4-Pro, Gemini-3.1-Pro, Kimi-k2.6) would test whether the cheap-model finding generalizes. A deeper judge-calibration study is worth a separate paper.

## Figures

Figures live in `drafting/plots/`.

- **Figure 1 — `fig1_judge_sensitivity.png`.** Mean PB+R26 score by architecture (generate / seed_generate / full) for each of the six base models, under each of the three judges (Phase 1, default reasoning).
- **Figure 2 — `fig2_passk_scaling.png`.** Pass@k curves under v4-flash for Gemma-4, GPT-OSS-120B, and DeepSeek-v4-flash with 95% bootstrap CI ribbons. Stars mark the seed_full pipeline result at its token-equivalent k=9 budget.
- **Figure 3 — `fig3_effect_sizes_forest.png`.** Forest plot of paired effect sizes with 95% CIs: reasoning toggle (blue) vs architecture deltas (red = significant positive, orange = significant negative, grey = null).
- **Figure 4 — `fig4_frontier_solves_heatmap.png`.** Per-problem strict-vs-lenient solve counts on the 10 R26 problems, pooling architecture and scaling experiments (counts shown as `solves/cells`).
- **Figure 5 — `fig5_difficulty_gradient.png`.** Pass-rate and mean-score by difficulty tier with 95% bootstrap CIs.
- **Figure 6 — `fig6_lift_by_tier.png`.** Forest plot of architecture lift (paired Δ in v4-flash mean score) stratified by tier and reasoning.

## Appendix

### A.1 GradingBench full table

10 judge configurations on n=200 from GradingBench, hardened prompt restricted to {0, 1, 6, 7}. Sorted by `pass_agree_at_6`.

| Judge | Reasoning | n | pass≥6 | recall | spec | prec | F1 | Pearson r | $/call | p50 lat |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.4-nano | xhigh | 196 | 89.3% | 70% | 98% | 93% | 0.800 | 0.711 | $0.0370 | 152s |
| DeepSeek-v4-pro | default | 198 | 88.9% | 83% | 92% | 83% | 0.825 | 0.756 | $0.0150 | 299s |
| DeepSeek-v4-flash | default | 199 | 87.4% | 79% | 91% | 81% | 0.800 | 0.756 | $0.0039 | 81s |
| Gemini-3.1-pro | default | 199 | 86.4% | 95% | 82% | 71% | 0.816 | 0.872 | $0.0348 | 22s |
| GPT-OSS-120B | xhigh | 178 | 84.3% | 90% | 82% | 70% | 0.788 | 0.770 | $0.0022 | 62s |
| DeepSeek-v4-flash | reasoning_off | 192 | 80.7% | 56% | 92% | 78% | 0.654 | 0.591 | $0.0015 | 13s |
| Gemma-4-31B-IT | high | 200 | 79.0% | 92% | 73% | 61% | 0.734 | 0.776 | $0.0038 | 126s |
| GPT-OSS-120B | default | 199 | 71.9% | 74% | 71% | 53% | 0.622 | 0.513 | $0.0008 | 9s |
| Gemma-4-31B-IT | default | 200 | 65.5% | 98% | 50% | 48% | 0.642 | 0.629 | $0.0021 | 19s |
| Gemini-3-flash | default | 200 | 64.0% | 98% | 48% | 47% | 0.633 | 0.606 | $0.0162 | 4s |

### A.2 AnswerBench-50 generator calibration

| Model | Config | Accuracy | $/run | Notes |
|---|---|---:|---:|---|
| DeepSeek-v4-pro | default | 94% (47/50) | $0.0185 | top accuracy |
| GPT-5.4-nano | xhigh | 92% (45/49) | $0.0560 | 1 trial hung |
| Gemini-3-flash | xhigh (synth) | 90% (45/50) | $0.0337 | 37 default + 13 xhigh |
| DeepSeek-v4-flash | default | 88% (44/50) | $0.0055 | best value tier |
| Qwen3.6-35B-A3B | default | 80% (40/50) | $0.0218 | |
| GPT-OSS-120B | xhigh | 74% (37/50) | $0.0057 | +16pp vs default |
| Gemini-3-flash | default | 74% (37/50) | $0.0100 | |
| Gemma-4-31B-IT | default | 68% (34/50) | $0.0015 | reasoning effectively off |
| GPT-OSS-120B | default | 58% (29/50) | $0.0011 | |
| DeepSeek-v4-flash | reasoning_off | 50% (25/50) | $0.0020 | -38pp |

### A.3 Architecture × judge × model × reasoning per-cell means

v4-flash, v4-pro, and Gemini means for the canonical Phase 1 grid (n≈70 trials per cell, default reasoning), plus phase1_reasoning rows for cheap models at reasoning=max (v4-flash only).

| Model × Mode | Reasoning | v4-flash | v4-pro | Gemini |
|---|---|---:|---:|---:|
| DeepSeek-v4-flash × generate | default | 3.22 | 3.39 | 4.81 |
| DeepSeek-v4-flash × seed_generate | default | 3.41 | 3.30 | 5.01 |
| DeepSeek-v4-flash × full | default | 3.38 | 3.09 | 4.63 |
| DeepSeek-v4-flash × seed_full | default | 3.49 | 3.19 | 5.83 |
| DeepSeek-v4-pro × generate | default | 3.53 | 3.38 | 5.56 |
| DeepSeek-v4-pro × seed_generate | default | 3.41 | 3.36 | 5.30 |
| DeepSeek-v4-pro × full | default | 3.85 | 3.66 | 5.35 |
| Gemini-3-flash × generate | default | 1.83 | 1.83 | 2.93 |
| Gemini-3-flash × seed_generate | default | 1.54 | 1.87 | 3.39 |
| Gemini-3-flash × full | default | 1.59 | 1.29 | 3.76 |
| Gemma-4-31B × generate | default | 1.49 | 1.83 | 3.21 |
| Gemma-4-31B × seed_generate | default | 1.49 | 1.53 | 2.99 |
| Gemma-4-31B × full | default | 1.39 | 1.17 | 3.51 |
| Gemma-4-31B × seed_full | default | 1.71 | 1.67 | 4.26 |
| Gemma-4-31B × generate | max | 2.74 | – | – |
| Gemma-4-31B × seed_generate | max | 2.74 | – | – |
| Gemma-4-31B × full | max | 2.17 | – | – |
| Gemma-4-31B × seed_full | max | 3.31 | – | – |
| GPT-OSS-120B × generate | default | 1.34 | 1.33 | 2.59 |
| GPT-OSS-120B × seed_generate | default | 1.09 | 1.27 | 2.40 |
| GPT-OSS-120B × full | default | 1.58 | 1.39 | 3.10 |
| GPT-OSS-120B × seed_full | default | 1.41 | 1.37 | 3.99 |
| GPT-OSS-120B × generate | max | 2.30 | – | – |
| GPT-OSS-120B × seed_generate | max | 2.54 | – | – |
| GPT-OSS-120B × full | max | 2.43 | – | – |
| GPT-OSS-120B × seed_full | max | 3.00 | – | – |
| Qwen3.6-35B × generate | default | 2.09 | 2.17 | 3.60 |
| Qwen3.6-35B × seed_generate | default | 2.10 | 2.06 | 3.21 |
| Qwen3.6-35B × full | default | 1.62 | 1.44 | 3.74 |

### A.4 Reasoning effect on PB+R26 (cheap models, v4-flash judge)

| Model | Mode | default | max | Δ (paired) | 95% CI |
|---|---|---:|---:|---:|---:|
| Gemma-4-31B | generate | 1.49 | 2.74 | +1.25 | [+0.74, +1.77] |
| Gemma-4-31B | seed_generate | 1.49 | 2.74 | +1.25 | [+0.74, +1.77] |
| Gemma-4-31B | full | 1.39 | 2.17 | +0.78 | [+0.27, +1.29] |
| Gemma-4-31B | seed_full | 1.71 | 3.31 | +1.60 | [+1.07, +2.14] |
| GPT-OSS-120B | generate | 1.34 | 2.30 | +0.96 | [+0.46, +1.46] |
| GPT-OSS-120B | seed_generate | 1.09 | 2.54 | +1.45 | [+0.93, +1.97] |
| GPT-OSS-120B | full | 1.58 | 2.43 | +0.85 | [+0.34, +1.36] |
| GPT-OSS-120B | seed_full | 1.41 | 3.00 | +1.59 | [+1.05, +2.13] |

### A.5 Expensive-models probe (n=12 problems, default reasoning)

| Model | Accuracy | $/run | Notes |
|---|---:|---:|---|
| Kimi-k2.6 | 100% (10/10) | $0.0971 | 2/12 hung past timeout |
| Qwen3.6-Max-Preview | 92% (11/12) | $0.1722 | strictly dominated by v4-flash at 30× cost |
| Gemini-3.1-Pro-Preview | 83% (10/12) | $0.2503 | dominated by v4-pro |
| GPT-5.4 | 50% (6/12) | $0.0539 | known artifact at default effort; jumps to ~92% at xhigh |

### A.6 Roleswap detail (oss_gemma_8cell, reasoning=max, v4-flash)

| Condition | n | mean | pass rate |
|---|---:|---:|---:|
| random_run1 | 69 | 3.19 | 0.45 |
| random_run2 | 70 | 3.34 | 0.49 |
| x_ideate_gemma | 68 | 3.09 | 0.44 |
| x_ideate_oss | 70 | 2.96 | 0.41 |
| x_revise_gemma | 69 | 3.48 | 0.49 |
| x_revise_oss | 70 | 3.41 | 0.49 |
| x_verify_gemma | 69 | 3.00 | 0.43 |
| **x_verify_oss** | 70 | **3.63** | **0.51** |

### A.7 Pass-flip rates on 1,440 triple-judge cells

| Pair | Pass-rate agreement | 95% CI |
|---|---:|---:|
| v4-flash vs v4-pro | 95.5% | [94.4%, 96.5%] |
| v4-flash vs Gemini | 73.7% | [71.5%, 76.0%] |
| v4-pro vs Gemini | 72.9% | [70.6%, 75.3%] |

| Conditional flip | Estimate | 95% CI | n |
|---|---:|---:|---:|
| P(Gemini pass \| v4-flash fail) | 0.368 | [0.338, 0.398] | 987 |
| P(Gemini fail \| v4-flash pass) | 0.035 | [0.020, 0.053] | 453 |

### A.8 Architecture lift by difficulty tier — full table (paired diffs, v4-flash)

| Contrast | Tier | n pairs | mean Δ | 95% CI | p |
|---|---|---:|---:|---:|---:|
| `full − generate` | all | 533 | −0.079 | [−0.272, +0.126] | 0.454 |
| | comp-hard (d=1) | 402 | −0.065 | [−0.301, +0.182] | 0.618 |
| | research-easy | 31 | +0.129 | [−0.742, +0.968] | 1.0 |
| | research-med+ (d≥3) | 36 | 0.000 | [0, 0] | 1.0 |
| | R26 only | 67 | +0.060 | [−0.343, +0.493] | 1.0 |
| `seed_generate − generate` | all | 539 | −0.028 | [−0.206, +0.160] | 0.78 |
| | research-easy | 31 | −0.548 | [−1.194, −0.097] | 0.030 |
| | R26 only | 70 | −0.243 | [−0.543, −0.029] | 0.030 |
| `seed_full − generate` | all | 337 | +0.315 | [+0.068, +0.570] | 0.013 |
| | comp-hard | 255 | +0.325 | [+0.039, +0.627] | 0.032 |
| | research-easy | 19 | +1.000 | [−0.368, +2.421] | 0.32 |
| | R26 only | 42 | +0.476 | [−0.143, +1.167] | 0.22 |
| | default reasoning, all | 203 | +0.128 | [−0.182, +0.453] | 0.46 |
| | reasoning=max, all | 134 | +0.597 | [+0.231, +0.993] | 0.003 |

## References

- Abouzaid, M., Blumberg, A. J., Hairer, M., et al. (2026). First Proof. arXiv:2602.05192. https://1stproof.org/
- Achim, T., Best, A., Bietti, A., et al. (2025). Aristotle: IMO-level Automated Theorem Proving. arXiv:2510.01346.
- Brown, T. B., Mann, B., Ryder, N., et al. (2020). Language Models are Few-Shot Learners. arXiv:2005.14165.
- Chen, M., Tworek, J., Jun, H., et al. (2021). Evaluating Large Language Models Trained on Code. arXiv:2107.03374.
- DeepMind. (2025). Advanced version of Gemini with Deep Think officially achieves gold-medal standard at the International Mathematical Olympiad. Google DeepMind blog, July 21, 2025.
- Erdős Problems. (n.d.). Erdős Problems database. https://www.erdosproblems.com/ ; AI contributions tracker https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems
- Feng, T., Trinh, T., Bingham, G., et al. (2026a). Semi-Autonomous Mathematics Discovery with Gemini: A Case Study on the Erdős Problems. arXiv:2601.22401.
- Feng, T., Trinh, T. H., Bingham, G., et al. (2026b). Towards Autonomous Mathematics Research (Aletheia). arXiv:2602.10177.
- Georgiev, B., Gómez-Serrano, J., Tao, T., Wagner, A. Z. (2025). Mathematical exploration and discovery at scale. arXiv:2511.02864.
- Glazer, E., Erdil, E., Besiroglu, T., et al. (2024). FrontierMath: A Benchmark for Evaluating Advanced Mathematical Reasoning in AI. arXiv:2411.04872.
- Hendrycks, D., Burns, C., Kadavath, S., et al. (2021). Measuring Mathematical Problem Solving With the MATH Dataset. arXiv:2103.03874.
- Huang, Y., & Yang, L. F. (2025). Winning Gold at IMO 2025 with a Model-Agnostic Verification-and-Refinement Pipeline. arXiv:2507.15855.
- Hubert, T., et al. (2025). Olympiad-level formal mathematical reasoning with reinforcement learning (AlphaProof). Nature 651, 607–613. DOI 10.1038/s41586-025-09833-y.
- Knuth, D. E. (2026). Claude's Cycles. Stanford CS, February 2026.
- Luong, T., Hwang, D., Nguyen, H. H., et al. (2025). Towards Robust Mathematical Reasoning (IMO-Bench). arXiv:2511.01846. https://imobench.github.io/
- Novikov, A., Vũ, N., Eisenberger, M., et al. (2025). AlphaEvolve: A coding agent for scientific and algorithmic discovery. arXiv:2506.13131.
- OpenAI. (2024). Learning to Reason with LLMs (o1). OpenAI blog, September 12, 2024.
- Tao, T. (2026). Primitive sets and von Mangoldt chains: Erdős Problem #1196 and beyond. *What's New* blog, May 3, 2026.
- Wang, X., Wei, J., Schuurmans, D., et al. (2022). Self-Consistency Improves Chain of Thought Reasoning in Language Models. arXiv:2203.11171.
- Wei, A., Hsu, S., Brown, N. (2025). OpenAI's experimental reasoning LLM achieves gold-medal performance on IMO 2025. Announcement thread, July 19, 2025.
- Wei, J., Wang, X., Schuurmans, D., et al. (2022). Chain-of-Thought Prompting Elicits Reasoning in Large Language Models. arXiv:2201.11903.
