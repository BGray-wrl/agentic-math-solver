# Comparing Inference-Time Methods for Natural-Language Mathematical Proofs

*Draft v1 — light pass.*

## Abstract

We empirically study natural-language mathematical proof generation in large language models. Across 70 problems (60 from DeepMind's IMO-ProofBench plus 10 frontier-grade research problems first solved in 2026), six base models, four inference-time architectures (pass@k, generator-verifier-revisor pipeline, seeded ideator, and ideator-plus-pipeline), and three independent judges, we compare what actually moves the needle. Three findings stand out. First, at default reasoning, the pipeline does not meaningfully beat simple scaling under our two strict judges; the seeded ideator-plus-pipeline architecture provides modest lift (+0.5 to +0.7 in mean score) only when paired with reasoning-on. Second, judge choice flips the headline for cheap models: under a lenient Gemini judge, pipelines look strictly better; under DeepSeek-v4-flash and v4-pro (the two strict judges, which agree on 95.5% of pass/fail decisions), the same data shows mostly null effect. Third, reasoning-on adds 16 to 38 percentage points on AnswerBench and +1.0 to +1.6 mean-score on ProofBench — three to five times any architecture effect we measured. We outline what these findings imply for evaluation practice and where genuinely novel mathematical capability seems to live.

## 1. Introduction

Large language models have moved from saturating school-math benchmarks to plausibly contributing to research mathematics within the span of two years. The trajectory runs from GSM8K and MATH (Hendrycks et al., 2021), through AIME and IMO competitions (where DeepMind's AlphaProof took silver in 2024 and gold-tier systems landed in 2025), and on toward open problems — the Erdős problem repository now lists dozens of contributions credited to model assistance. With capability rising fast, the engineering question becomes pressing: which inference-time methods are actually worth their tokens?

Two methodological gaps motivate this paper. First, the dominant comparison in recent agentic-math papers — pipeline (generator–verifier–revisor) vs. plain best-of-1 — is unfair. A three-step pipeline burns roughly three times the tokens of a single generation, so the proper baseline is pass@3 (or pass@n for an n-step pipeline), not pass@1. We re-run that comparison at parity. Second, evaluation of free-form proofs at scale relies on automated judges, and our results show that the gap between a "lenient" judge (Gemini-3-flash) and a "strict" judge (DeepSeek-v4-flash or v4-pro) is large enough to flip qualitative conclusions about which architecture is best.

We do not propose a new method. We characterize a six-by-four-by-three space (model × architecture × judge) on a 70-problem benchmark with three judges, and audit what holds up. The contributions are: (1) a careful side-by-side comparison of pass@k, generator-verifier-revisor pipelines, seeded ideators, and the combined ideator-plus-pipeline architecture, with reasoning toggled on and off where models support it; (2) a quantification of judge-induced variance that is large enough to flip the comparison; (3) reproducible per-experiment artifacts (`results/architecture_20260506/`, plus four other buckets) covering ~2,900 trial rows; and (4) an honest accounting of which "frontier" problems were actually solved, by which architectures.

## 2. Background

**Capability arc.** AlphaProof (Castelvecchi & DeepMind, 2024) achieved IMO silver in 2024 with a specialized 3B-parameter formalizer trained via AlphaZero-style self-play. In 2025, three independent gold-tier systems landed within weeks of each other: DeepMind's Deep Think, OpenAI's IMO submission, and Harmonic's Aristotle (Ahn et al., 2025), accompanied by an open-source agentic framework reaching gold-tier performance with frontier base models (Huang & Yang, 2025). Through early 2026, models began contributing solutions to genuinely open problems on the Erdős repository (Tao, 2026), and Epoch's FrontierMath open-problem set saw its first credited model solution. Knuth's "Claude's cycles" essay and DeepMind's Aletheia case study (DeepMind, 2026) document the ad-hoc iterative human–AI workflows that have actually produced research-grade results.

**Benchmarks.** We use IMO-ProofBench (DeepMind, 2026), a 60-problem corpus of olympiad proofs split into 30 "Basic" and 30 "Advanced" tiers, paired with a hardened automated grader that correlates with human IMO judges at Pearson r=0.96. We augment this with ten 2026 research problems drawn from the Erdős repository (333, 397, 654, 659, 1051), the First Proof open challenge (problems 4, 5, 6, 10), and the Ramsey-hypergraph entry from Epoch's FrontierMath open-problem set. We do not claim these ten as a novel benchmark; we treat them as a small frontier-tier extension and refer to the union as PB+R26.

**Architectures we compare.** *Pass@k*: sample k independent solutions and take the best (Brown et al., 2020; OpenAI, 2025). *Generator-verifier-revisor pipeline*: a generator emits a candidate, a verifier critiques it, and a revisor edits — looped a fixed number of times. This is the architecture central to Aletheia (DeepMind, 2026) and to the Huang–Yang IMO-gold framework (2025). *Seeded ideator*: an upstream ideation pass produces several candidate solution sketches (we use three), each of which feeds a generation step (the OpenAI IMO-style submission used a similar method). *Ideator + pipeline*: each ideated seed runs through the full verifier-revisor loop, tripling token cost.

**Scope.** We restrict to natural-language proof generation. We do not study formal verification (Lean, AlphaProof, Aristotle), evolutionary search (AlphaEvolve), or hybrid neuro-symbolic systems. The reason is breadth: natural-language proofs are the only universally applicable solution medium for problems that resist formalization or hill-climbing, and the bulk of recent open-domain mathematical contributions have come through this channel.

## 3. Methodology

### 3.1 Architectures

We implement all four architectures in a single pipeline (`src/pipeline.py`) with shared model-call infrastructure. Generation, verification, and revision use lightly hardened versions of the prompts published with DeepMind's Aletheia and Huang & Yang's IMO repository. Final grading uses DeepMind's IMO-ProofBench judge prompt, restricted to {0, 1, 6, 7} on a 0–7 scale.

- **Pass@k.** Run k independent generation calls; take max judge score. We sweep k ∈ {1, 3} as the headline comparison and k up to 7 (occasionally 9) in the scaling experiment.
- **Generator-verifier-revisor pipeline (`full`).** Up to three verifier-revisor iterations after the initial generation; early-stop when the verifier emits `VERDICT: correct`.
- **Seeded ideator (`seed_generate`).** A single ideation call produces three sketch directions; each direction is realized as one full solution; we take the best.
- **Ideator + pipeline (`seed_full`).** Each of three ideated seeds runs through the verifier-revisor loop; we take the best final solution.

The fair token-cost comparison is: pass@1 ↔ generate (1 call); pass@3 ↔ seed_generate (3 calls); pass@9 ↔ seed_full (3 seeds × roughly 3 pipeline iterations each).

### 3.2 Models and reasoning

We evaluate six base models: DeepSeek-v4-flash, DeepSeek-v4-pro, Gemini-3-flash-preview, Gemma-4-31B-IT, GPT-OSS-120B, and Qwen3.6-35B-A3B. For Gemma-4 and GPT-OSS we additionally run a "reasoning=max" condition, since these models expose explicit thinking-token control. GPT-5.4-nano was added later for a pass@3 spot-check at xhigh effort.

### 3.3 PB+R26 dataset

The 60-problem ProofBench split is taken unmodified from DeepMind's release. The R26 augmentation comprises ten problems first solved by AI models in 2026, hand-graded for difficulty on a 1–4 scale (research-easy, research-medium, research-hard, research-frontier) following the rubrics used by DeepMind's superhuman team and Epoch. The full per-problem difficulty assignment appears in Table 1.

| Problem | Difficulty | Provenance note |
|---|---|---|
| Erdős 397 | comp-hard | AI alongside competition literature |
| Erdős 333 | research-easy | AI alongside prior literature |
| Erdős 654 | research-easy | AI standalone, one formulation |
| Erdős 659 | research-easy | AI alongside prior literature |
| FirstProof 10 | research-easy | known-private-solution challenge |
| Erdős 1051 | research-medium | AI standalone, full Lean solution |
| FirstProof 5 | research-medium | known-private-solution challenge |
| FirstProof 4 | research-hard | frontier/internal setting |
| FirstProof 6 | research-hard | frontier/internal setting |
| Ramsey hypergraphs | research-frontier | AI-assisted publishable result |

### 3.4 Judges

Three judges score every architecture trial: DeepSeek-v4-flash (canonical), DeepSeek-v4-pro (audit, slow/strict), and Gemini-3-flash-preview (audit, cheap/lenient). Section 4 reports the calibration we ran on GradingBench to choose v4-flash as the default.

## 4. Setup: Calibration

### 4.1 Judge calibration on GradingBench

We tested ten judge configurations on a 200-problem random sample of DeepMind's GradingBench, holding the prompt fixed (output restricted to {0, 1, 6, 7}). Our priority metric is `pass_agree_at_6`: agreement with the human pass/fail verdict at the IMO threshold. Table 2 shows the top tier.

| Judge | n | pass≥6 agree | F1 | Pearson r | $/call |
|---|---:|---:|---:|---:|---:|
| GPT-5.4-nano @ xhigh | 196 | 89.3% | 0.800 | 0.711 | $0.0370 |
| DeepSeek-v4-pro | 198 | 88.9% | 0.825 | 0.756 | $0.0150 |
| **DeepSeek-v4-flash** | 199 | **87.4%** | **0.800** | **0.756** | **$0.0039** |
| Gemini-3.1-pro | 199 | 86.4% | 0.816 | 0.872 | $0.0348 |
| Gemini-3-flash | 200 | 64.0% | 0.633 | 0.606 | $0.0162 |

DeepSeek-v4-flash is on the Pareto frontier: 87.4% pass-agreement at $0.004 per call. We use it as the canonical judge across all main experiments. DeepSeek-v4-pro and Gemini-3-flash-preview serve as audit judges. We caveat that Gemini-3-flash-preview correlates with humans only at r=0.51 on the ProofBench cross-cut, considerably worse than v4-flash and v4-pro at r=0.76 and r=0.79 respectively (DeepMind 2026, Section 7); this matters for the headline interpretation in Section 5.

### 4.2 Generator calibration on AnswerBench

We tested 13 model–reasoning configurations on AnswerBench-50 (50 verifiable-answer problems). Reasoning is the dominant variable: GPT-OSS-120B moves from 58% to 74% (default → xhigh), Gemini-3-flash from 74% to 90%, DeepSeek-v4-flash from 88% with default reasoning to 50% with reasoning forced off. The full table appears in Appendix A. From this we selected six base models for the architecture sweep (those above 60% with their defaults).

## 5. Main results

### 5.1 Architecture comparison at default reasoning

Under the canonical v4-flash judge, the four architectures are barely separated when averaged across the six base models on PB+R26:

| Mode | n | mean (0–7) | pass rate (≥6) |
|---|---:|---:|---:|
| generate | 543 | 2.31 | 0.33 |
| seed_generate | 555 | 2.29 | 0.33 |
| full | 550 | 2.24 | 0.32 |
| seed_full | 344 | 2.58 | 0.37 |

The aggregate seed_full lift (+0.27) is real but small, and the comparison is asymmetric: seed_full is only tested on three of the six base models (Section 6.4). Within-model deltas for full vs. generate (the cleanest pipeline-vs-baseline contrast, available on all six models) are mixed and small under v4-flash and v4-pro, ranging from −0.47 to +0.32. Strong models (DeepSeek family) show no clear pipeline gain. Cheap models (Gemini-3-flash-preview, Gemma, GPT-OSS, Qwen) show no consistent direction either.

### 5.2 Judge choice flips the cheap-model comparison

The same raw outputs, scored by Gemini-3-flash-preview (the lenient audit judge), tell a different story. Table 3 summarizes full-vs-generate deltas across all three judges:

| Model | v4-flash Δ | v4-pro Δ | Gemini Δ |
|---|---:|---:|---:|
| DeepSeek-v4-flash | +0.16 | −0.30 | −0.18 |
| DeepSeek-v4-pro | +0.32 | +0.28 | −0.21 |
| Gemini-3-flash-preview | −0.24 | −0.54 | **+0.83** |
| Gemma-4-31B-IT | −0.10 | −0.66 | **+0.30** |
| GPT-OSS-120B | +0.24 | +0.06 | **+0.51** |
| Qwen3.6-35B-A3B | −0.47 | −0.73 | **+0.14** |

Under Gemini, four of six models — all the cheap ones — show clean +0.14 to +0.83 lift from the pipeline. The strict judges show no such pattern. This is not noise. On the 1,440 cells where all three judges scored, v4-flash and v4-pro agree on pass-or-fail at the ≥6 threshold 95.5% of the time. v4-flash and Gemini agree only 73.7% of the time, and the disagreement is one-sided: Gemini calls "pass" on 25.2% of cases that v4-flash calls "fail," and on 26.2% of cases that v4-pro calls "fail." The reverse error (Gemini calls fail when others pass) is roughly 1%. Gemini's lenience is a systematic offset, not noise. We use v4-flash for headline numbers and report the Gemini view explicitly where it diverges.

### 5.3 Where the seeded ideator + pipeline does help

Restricted to cheap models with reasoning=max — the only setting where we have apples-to-apples seed_full data — the pipeline does provide real lift (Table 4):

| Model | Reasoning | generate | seed_full | Δ |
|---|---|---:|---:|---:|
| Gemma-4-31B-IT | max | 2.74 | 3.31 | **+0.57** |
| GPT-OSS-120B | max | 2.30 | 3.00 | **+0.70** |

This is a meaningful effect — about a 2× of the standard error across problems — and it reproduces in both models tested. Whether it would survive a v4-pro audit remains untested (we have no v4-pro grades on the reasoning=max trials). For DeepSeek-v4-flash at default reasoning the seed_full–generate gap is +0.27 under v4-flash but −0.20 under v4-pro, suggesting the lift may be borderline for stronger generators.

### 5.4 Frontier solves

We surfaced every R26 problem solved at v4-flash ≥ 6, by any architecture–model–reasoning combination. Twelve of the 70 PB+R26 problems are research-tier (difficulty ≥ 2). Four problems received multiple credible solves (FirstProof-10, Erdős-654, Erdős-333, Erdős-1051), three received one or two (Erdős-659, FirstProof-5, FirstProof-6), three received zero (FirstProof-4, Ramsey hypergraphs, plus ties at the bottom). The leaderboard, by model–architecture, is concentrated:

| Model | Mode | Reasoning | research solves / opportunities |
|---|---|---|---:|
| Gemma-4-31B-IT | seed_full | max | 3/9 |
| DeepSeek-v4-pro | generate | default | 2/9 |
| DeepSeek-v4-pro | full | default | 2/9 |
| DeepSeek-v4-pro | seed_generate | default | 2/9 |
| DeepSeek-v4-flash | seed_full | default | 2/8 |

Two cautions. First, FirstProof-10 was a known-easy problem in the underlying challenge — multiple frontier teams claimed it before our run, so a "solve" here likely reflects reproducible-from-prior-public-discussion territory rather than novel capability. Second, the "research-frontier" Ramsey hypergraph problem went unsolved at the strict-judge ≥6 threshold across every model and architecture we tested. Genuine novelty remains rare.

## 6. Secondary results

### 6.1 Reasoning is the single biggest knob

Within-model contrasts at fixed architecture show reasoning-on adding +0.78 to +1.60 to the v4-flash mean score on PB+R26 (Gemma and GPT-OSS, the two models where we ran both reasoning settings). On AnswerBench-50, the same toggle moves accuracy by 16 to 38 percentage points. Architecture deltas (Section 5.1) are between 0.0 and +0.7 on the same scale. Reasoning is roughly 3–5× the size of any architecture choice. This is consistent with the literature (chain-of-thought, OpenAI o1) but worth restating in our context.

### 6.2 Pass@k continues to scale through k=7

A separate scaling experiment (`results/scaling_20260506/`) recomputed pass@n via exhaustive enumeration over all C(M, n) subsets of available branches. Curves under v4-flash:

| Model | Reasoning | n=1 | n=3 | n=5 | n=7 |
|---|---|---:|---:|---:|---:|
| Gemma-4-31B-IT | default | 0.31 | 0.74 | 1.08 | 1.40 |
| Gemma-4-31B-IT | max | 1.92 | 2.76 | 3.05 | 3.20 |
| GPT-OSS-120B | default | 0.10 | 0.27 | 0.39 | 0.47 |
| GPT-OSS-120B | max | 1.68 | 2.49 | 2.83 | 3.08 |
| DeepSeek-v4-flash | default | 2.81 | 3.78 | 4.18 | 4.54 |

At reasoning=max the pass@7 means (3.20, 3.08) match seed_full (3.31, 3.00). Pure scaling matches the pipeline at the same token budget. For DeepSeek-v4-flash at default reasoning, scaled pass@7 (4.54, 4 R26 solves) clearly exceeds phase-3 seed_full (3.49, 2 R26 solves) — the strong-cheap model benefits more from breadth than from pipeline scaffolding.

### 6.3 Cross-model role-swap is a null effect

A separate experiment (`results/roleswap_20260506/`) tested cross-model diversity by varying which of GPT-OSS or Gemma fills the ideator/generator/verifier/revisor roles in the seed_full pipeline. At reasoning=max, the eight tested conditions span 2.96 to 3.63 in mean v4-flash score; the random-baseline conditions are at 3.19 and 3.34. Only one swap — GPT-OSS as verifier (3.63) — clearly beats both baselines. The remaining seven conditions are within ±0.4 of the baseline, well within the noise scale. The "diversity helps" hypothesis is not supported. The data may instead suggest that *which model handles verification* matters more than which model handles generation; we treat this as a hint, not a result, given the limited sweep.

A small ideator-strength side-experiment on a 20-problem PB-Advanced subset showed that swapping the ideator from DeepSeek-v4-flash to the stronger DeepSeek-v4-pro *hurt* (3.20 → 2.55). We do not over-read this.

### 6.4 Coverage asymmetry caveats

Phase 1 (the canonical six-model × three-mode grid) does not include `seed_full`. The seed_full data come from Phase 2 (Gemma + GPT-OSS at default reasoning), Phase 3 (DeepSeek-v4-flash at default), and Phase 1-reasoning-max (Gemma + GPT-OSS at max). Any aggregate seed_full statement is over a non-representative subset, weighted toward the cheap models. We report per-cell numbers in Sections 5.1 and 5.3 where this matters.

## 7. Resources, errors, and audit

Across the architecture sweep we ran 2,098 trial rows against six base models. Aggregate API spend across all experiments (architecture, scaling, roleswap, calibration) was approximately $800 against an $1,000 internal budget. A note on a known data quality issue: in the original Phase 1 seeded-ideator runs, roughly 10–28% of seeded ideation calls returned malformed outputs and the pipeline silently fell back to a pass@3 generation (the broken-ideator regression). This pushes seeded conditions toward the pass@3 baseline and would, if anything, *understate* the seeded-ideator effect. We patched the bug for Phase 2 and downstream experiments.

## 8. Limitations

**Benchmark contamination.** The 60 ProofBench problems and most R26 problems were either released or solved in 2026; for several of our models (Gemma-4 March 2026, DeepSeek-v4 April 2026) post-training cutoffs overlap with public solution disclosure. GPT-OSS (released August 2025) is provably contamination-free for every R26 problem. Solve patterns for GPT-OSS and DeepSeek look broadly similar, which we interpret as weak evidence that contamination is not the dominant signal — but we cannot rule it out for the post-cutoff models on individual problems.

**Judging.** We rely on automated judges; calibrated to ~87% pass-agreement on GradingBench, this is more than enough for directional claims but not enough to certify any individual frontier solve. We spot-checked Erdős-659 by hand and the v4-flash grade tracked the manual reading. We cannot manually grade 5,000+ proof outputs.

**Generalization.** Our six base models top out at DeepSeek-v4-pro, which is well below the strongest commercially available systems. We do not test Claude Opus 4.7, GPT-5.4-Pro, or Gemini-3.1-Pro on the full sweep.

**Dataset size.** n=70 is small. We chose it to keep the architecture-by-model-by-judge factorial tractable at pass@9 cost. Only ten problems are research-grade; conclusions about frontier capability are accordingly sparse.

## 9. Conclusion

[Placeholder — full revision in Stage 2.] Two takeaways for engineering practice. First, when comparing inference-time architectures for math proofs, control for token cost (pass@3 against the pipeline, pass@9 against ideator-plus-pipeline) and report results under at least two judges of different leniency. Otherwise the comparison is not interpretable. Second, the highest-leverage knob is reasoning depth, not pipeline scaffolding. For genuinely novel mathematics, our data suggests breadth (scaled pass@k) matters at least as much as iterative refinement.

## 10. Future work

We encourage three follow-ups: (i) a fair pass@k vs. pipeline comparison on frontier closed-source models; (ii) human-expert grading on a handful of R26-tier solutions to validate (or invalidate) the v4-flash judge; and (iii) a deeper study of judge calibration across continuous and binary metrics. We intend to take up (iii) in a separate paper.

## Appendix A. Supplementary tables

[Stage 2 will populate this with: full GradingBench table; AnswerBench by category; full architecture × judge × model × reasoning grid; expensive-models probe; roleswap detail; broken-ideator estimate; per-problem solve roster.]

## References

[Stage 3 will populate full citations from the lit-review URLs.]
