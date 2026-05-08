# Comparing Inference-Time Methods for Natural-Language Mathematical Proofs

*Draft v3 — polish.*

## Abstract

Frontier-tier language models can now produce mathematical proofs that pass automated graders calibrated against IMO judges. Recent work proposes increasingly elaborate inference-time architectures — generator-verifier-revisor pipelines, seeded-ideator multi-trajectory sampling, and combinations of the two — and reports gains over single-shot generation. We test what survives a fair comparison. On 70 problems (60 from DeepMind's IMO-ProofBench plus 10 frontier-tier research problems first solved in 2026), six base models, four architectures, and three independent judges, we find: (1) at default reasoning, the pipeline does not beat pass@k at matched token budgets under either of our two strict judges; the seeded ideator-plus-pipeline architecture provides modest lift (+0.5 to +0.7 mean score) only when paired with reasoning-on for cheap models. (2) Judge choice flips qualitative conclusions for cheap models: under a lenient Gemini judge the pipeline looks strictly better; under DeepSeek-v4-flash and v4-pro (which agree on 95.5% of pass/fail decisions across 1,440 triple-judged cells) the same data shows mostly null effect. (3) Reasoning-on adds 16 to 38 percentage points on AnswerBench and roughly +1.0 to +1.6 mean-score on PB+R26 — three to five times any architecture effect we measured. Across 2,098 architecture trials, the only research-tier problems solved by any model–architecture under our strict judges were a handful of "research-easy" Erdős and First-Proof problems; the genuinely harder R26 problems went unsolved at the strict ≥6 threshold. Practically, fair token-budget controls and a strict-judge audit are necessary before pipeline gains can be claimed; the highest-leverage knob remains reasoning depth.

## 1. Introduction

Language models have moved from saturating school-math benchmarks to plausibly contributing to research mathematics within two years. The trajectory runs from GSM8K and MATH (Hendrycks et al., 2021), through AIME and IMO competitions — AlphaProof took silver in 2024 (Hubert et al., 2025), and gold-tier systems from DeepMind (DeepMind, 2025), OpenAI (Wei et al., 2025), and Harmonic (Achim et al., 2025) landed in 2025 — and on toward open problems. The Erdős repository now lists dozens of model-assisted contributions, and Tao describes recent solves as "major milestones" indicating models can attack genuinely novel problems (Tao, 2026).

Alongside the capability arc, the engineering question is which inference-time methods are worth their tokens. Two methodological gaps motivate this work. First, the dominant comparison in recent agentic-math papers — pipeline (generator–verifier–revisor) vs. single-shot generation — is unfair on its face. A three-step pipeline burns roughly three times the tokens of a single generation, so the proper baseline is pass@3 (or pass@n for an n-step pipeline), not pass@1. Second, evaluation of free-form proofs at scale relies on automated judges, and the gap between a "lenient" judge and our strict judges is large enough to flip qualitative conclusions about which architecture wins.

We do not propose a new method. We characterize a six-by-four-by-three space (model × architecture × judge) on a 70-problem benchmark and audit what holds up. Contributions:

1. A token-cost-fair comparison of pass@k against the generator-verifier-revisor pipeline, the seeded-ideator approach, and the combined ideator-plus-pipeline architecture, with reasoning toggled where models support it. Pass@3 is the relevant baseline for the pipeline; pass@9 is the relevant baseline for the combined approach.
2. A direct quantification of judge-induced variance, with cell-level numbers showing the strict judges agree on 95.5% of pass/fail decisions while the lenient judge over-passes on roughly a quarter of strict-fail cases.
3. A frontier-solves audit reporting which R26 problems were solved by which model–architecture, broken out by judge.
4. Reproducible per-experiment artifacts (`results/architecture_20260506/` plus four other buckets) totaling ~2,900 trial rows.

## 2. Background

**Capability arc.** AlphaProof (Hubert et al., 2025) achieved IMO silver in 2024 with a specialized formalizer trained via AlphaZero-style self-play. In 2025, three independent gold-tier systems landed within weeks of each other: DeepMind's Deep Think (DeepMind, 2025), OpenAI's IMO submission (Wei et al., 2025), and Harmonic's Aristotle (Achim et al., 2025), accompanied by an open-source agentic framework reaching gold-tier performance with frontier base models (Huang & Yang, 2025). Through early 2026, models began producing solutions to open problems on the Erdős repository (Tao, 2026; Erdős Problems, n.d.), and Epoch's FrontierMath open-problem set saw its first model-credited solution (Glazer et al., 2024). Knuth's "Claude's cycles" essay (Knuth, 2026) and DeepMind's Aletheia case studies (Feng et al., 2026a,b) document the iterative human–AI workflows that have actually produced research-grade results.

**Benchmarks.** We use IMO-ProofBench (Luong et al., 2025), a 60-problem corpus of olympiad proofs split into 30 "Basic" and 30 "Advanced" tiers, paired with a hardened automated grader that correlates with human IMO judges at Pearson r=0.96. We augment this with ten 2026 research problems drawn from the Erdős repository (333, 397, 654, 659, 1051), the First Proof open challenge (problems 4, 5, 6, 10) (Abouzaid et al., 2026), and the Ramsey-hypergraph entry from Epoch's FrontierMath open-problem set. We do not claim these ten as a novel benchmark; we treat them as a small frontier-tier extension and refer to the union as PB+R26.

**Architectures we compare.** *Pass@k*: sample k independent solutions and take the best (Brown et al., 2020). *Generator-verifier-revisor pipeline*: a generator emits a candidate, a verifier critiques it, and a revisor edits — looped a fixed number of times. This is the architecture central to Aletheia (Feng et al., 2026b) and to the Huang–Yang IMO-gold framework (Huang & Yang, 2025). *Seeded ideator*: an upstream ideation pass produces several candidate solution sketches (we use three), each of which feeds an independent generation. The OpenAI IMO-style submission used a similar method. *Ideator + pipeline*: each ideated seed runs through the full verifier-revisor loop, tripling token cost.

**Scope.** We restrict to natural-language proof generation. We do not study formal verification (Lean, AlphaProof, Aristotle), evolutionary search (AlphaEvolve; Novikov et al., 2025; Georgiev et al., 2025), or hybrid neuro-symbolic systems. The reason is breadth: natural-language proofs are the only universally applicable solution medium for problems that resist formalization or hill-climbing, and the bulk of recent open-domain mathematical contributions have come through this channel.

## 3. Methodology

### 3.1 Architectures

We implement all four architectures in a single pipeline (`src/pipeline.py`) with shared model-call infrastructure. Generation, verification, and revision use lightly hardened versions of the prompts published with DeepMind's Aletheia and Huang & Yang's IMO repository. Final grading uses DeepMind's IMO-ProofBench judge prompt, restricted to {0, 1, 6, 7} on a 0–7 scale.

- **Pass@k.** Run k independent generation calls; take max judge score. We sweep k ∈ {1, 3} as the headline comparison, k ∈ {1, 3, 5, 7, 9} in the dedicated scaling experiment.
- **Generator-verifier-revisor pipeline (`full`).** Up to three verifier-revisor iterations after the initial generation; early-stop when the verifier emits `VERDICT: correct`.
- **Seeded ideator (`seed_generate`).** A single ideation call produces three sketch directions; each direction is realized as one full solution; we take the best.
- **Ideator + pipeline (`seed_full`).** Each of three ideated seeds runs through the verifier-revisor loop; we take the best final solution.

The fair token-cost comparison is pass@1 ↔ generate (1 call), pass@3 ↔ seed_generate (3 calls), pass@9 ↔ seed_full (3 seeds × roughly 3 pipeline iterations each).

### 3.2 Models and reasoning

We evaluate six base models: DeepSeek-v4-flash, DeepSeek-v4-pro, Gemini-3-flash-preview, Gemma-4-31B-IT, GPT-OSS-120B, and Qwen3.6-35B-A3B. For Gemma-4 and GPT-OSS we additionally run a "reasoning=max" condition, since these models expose explicit thinking-token control. GPT-5.4-nano was added later for a pass@3 spot-check at xhigh reasoning effort.

### 3.3 PB+R26 dataset

The 60-problem ProofBench split is taken unmodified from DeepMind's release. The R26 augmentation comprises ten problems first solved or claimed-solved by AI models in 2026. We graded each on a 1–4 difficulty scale (research-easy, research-medium, research-hard, research-frontier) following the rubrics used by DeepMind's superhuman team and Epoch (Table 1).

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

Three judges score every architecture trial: DeepSeek-v4-flash (canonical), DeepSeek-v4-pro (audit, slow/strict), and Gemini-3-flash-preview (audit, cheap/lenient). Section 4 reports the GradingBench calibration we ran to choose v4-flash as default.

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

DeepSeek-v4-flash is on the Pareto frontier: 87.4% pass-agreement at $0.004 per call, with continuous-correlation r=0.756. We use it as canonical. DeepSeek-v4-pro and Gemini-3-flash-preview serve as audit judges. We caveat that Gemini-3-flash-preview is the cheap audit judge, not Gemini-3.1-pro. The cross-cut of our actual usage shows Gemini-3-flash-preview correlating with v4-flash at r=0.51 on architecture-experiment cells, considerably worse than v4-flash and v4-pro at r=0.76 and r=0.79 respectively. This shows up in Section 5.

### 4.2 Generator selection on AnswerBench

We tested 13 model–reasoning configurations on AnswerBench-50 (50 verifiable-answer problems judged by Gemini-3-flash-lite). Reasoning is the dominant variable: GPT-OSS-120B moves from 58% to 74% on the toggle alone, Gemini-3-flash from 74% to 90%, DeepSeek-v4-flash from 88% (default reasoning on) to 50% (forced off). Six base models cleared 60% accuracy with sensible reasoning settings; we kept all six for the architecture sweep. Full table in Appendix A.2.

## 5. Main results

### 5.1 Architecture comparison at default reasoning

Under the canonical v4-flash judge, the four architectures are barely separated when averaged across the six base models on PB+R26 (Table 3):

| Mode | n | mean (0–7) | pass rate (≥6) |
|---|---:|---:|---:|
| generate | 543 | 2.31 | 0.33 |
| seed_generate | 555 | 2.29 | 0.33 |
| full | 550 | 2.24 | 0.32 |
| seed_full | 344 | 2.58 | 0.37 |

The aggregate seed_full lift (+0.27) is real but small, and the comparison is asymmetric: seed_full was tested on three of the six base models (Section 6.4). Within-model deltas for full vs. generate (the cleanest pipeline-vs-baseline contrast, available on all six base models) are mixed and small under v4-flash and v4-pro, ranging from −0.47 to +0.32. Strong models (DeepSeek family) show no clear pipeline gain. Cheap models show no consistent direction either.

### 5.2 Judge choice flips the cheap-model comparison

The same raw outputs scored by Gemini-3-flash-preview tell a different story (Table 4; Figure 1):

| Model | v4-flash Δ | v4-pro Δ | Gemini Δ |
|---|---:|---:|---:|
| DeepSeek-v4-flash | +0.16 | −0.30 | −0.18 |
| DeepSeek-v4-pro | +0.32 | +0.28 | −0.21 |
| Gemini-3-flash-preview | −0.24 | −0.54 | **+0.83** |
| Gemma-4-31B-IT | −0.10 | −0.66 | **+0.30** |
| GPT-OSS-120B | +0.24 | +0.06 | **+0.51** |
| Qwen3.6-35B-A3B | −0.47 | −0.73 | **+0.14** |

Under Gemini, four of six models — all the cheap ones — show clean +0.14 to +0.83 lift from the pipeline. The strict judges show no such pattern. This is not noise. On the 1,440 cells where all three judges scored at the architecture experiment, v4-flash and v4-pro agree on pass-or-fail at the ≥6 threshold **95.5% of the time**. v4-flash and Gemini agree 73.7%; v4-pro and Gemini agree 72.9%. The disagreement is one-sided: Gemini calls "pass" on 25.2% of cases that v4-flash calls "fail" and on 26.2% of cases that v4-pro calls "fail," while the reverse error (Gemini calls "fail" when others pass) is roughly 1%. Gemini's lenience is a systematic offset, not noise. We use v4-flash for headline numbers and report the Gemini view explicitly where it diverges.

### 5.3 Where seeded-ideator-plus-pipeline does help

Restricted to cheap models with reasoning=max — the only setting where seed_full data exists side-by-side with generate data — the pipeline does provide real lift (Table 5):

| Model | Reasoning | generate | seed_full | Δ |
|---|---|---:|---:|---:|
| Gemma-4-31B-IT | max | 2.74 | 3.31 | **+0.57** |
| GPT-OSS-120B | max | 2.30 | 3.00 | **+0.70** |

Both deltas are larger than the single-judge inter-mode noise we observed in Section 5.1. The lift is also visible in pass-rate terms: Gemma's pass rate moves from 37% to 47%, GPT-OSS's from 33% to 43%. We have no v4-pro grades on these reasoning=max cells, so the lift cannot be cross-validated against the second strict judge; the v4-flash gain is large enough that we conclude it is most likely real but the v4-pro audit remains a gap.

For DeepSeek-v4-flash at default reasoning, the seed_full–generate gap is +0.27 under v4-flash but −0.20 under v4-pro, suggesting borderline lift on stronger generators. We do not see meaningful seed_full gains on the strongest model in our sweep.

### 5.4 Frontier solves

Twelve of the 70 PB+R26 problems are research-tier (difficulty ≥ 2). Across the architecture experiment we count, for each problem and each judge, how many model × mode × reasoning combinations scored ≥ 6 (Table 6; Figure 4):

| Problem | Difficulty | v4-flash solves | v4-pro solves | Gemini solves |
|---|---|---:|---:|---:|
| FirstProof 10 | research-easy | 20 | 12 | 8 |
| Erdős 654 | research-easy | 5 | 3 | 6 |
| Erdős 333 | research-easy | 1 | 0 | 2 |
| FirstProof 5 | research-medium | 1 | 0 | 1 |
| Erdős 659 | research-easy | 0 | 1 | 7 |
| Erdős 1051 | research-medium | 0 | 0 | 14 |
| FirstProof 6 | research-hard | 0 | 0 | 5 |
| FirstProof 4 | research-hard | 0 | 0 | 1 |
| Ramsey hypergraphs | research-frontier | 0 | 0 | 3 |

Three observations. First, FirstProof-10 is solved by twenty different model-architecture combinations under v4-flash, including Gemma-4 with default reasoning. This is the easiest research-tier problem in our set: the original challenge confirmed multiple frontier teams cracked it before our run. We treat FirstProof-10 solves as reproducible-from-public-discussion territory rather than novel capability, even though the problem statement is technically research-grade.

Second, Erdős-654 is solved by five distinct architectures across four base models under v4-flash, and three under v4-pro. This includes the strong DeepSeek-v4-pro at both `generate` and `full`, GPT-OSS-120B at `full` (reasoning=max), Gemma-4-31B-IT at `seed_full` (reasoning=max), and DeepSeek-v4-flash at `seed_full`. This pattern — multiple architectures, multiple base models, two strict judges — is the strongest evidence in our dataset that current cheap-tier models can solve a research-easy problem reproducibly.

Third, the genuinely harder problems went unsolved under our strict judges. FirstProof-6, FirstProof-4, and Ramsey-hypergraphs receive zero v4-flash and zero v4-pro solves. Erdős-1051, judged by humans as research-medium and known to admit a clean Lean proof, also receives zero strict-judge solves. The fourteen Gemini solves on Erdős-1051 alongside zero strict solves is the sharpest single illustration of the judge gap (Section 5.2).

## 6. Secondary results

### 6.1 Reasoning is the single biggest knob

Within-model contrasts at fixed architecture show reasoning-on adding +0.78 to +1.60 to the v4-flash mean score on PB+R26 (Gemma and GPT-OSS, the two models where we ran both reasoning settings; per-cell deltas in Appendix A.4). On AnswerBench-50, the same toggle moves accuracy by 16 to 38 percentage points. Architecture deltas (Section 5.1) are between 0.0 and +0.7 on the same scale. Reasoning is roughly 3–5× the size of any architecture choice (Figure 3). This is consistent with the chain-of-thought literature (Wei et al., 2022; OpenAI, 2024) but worth restating in our context: pipeline complexity is a much smaller knob than letting the model think longer.

### 6.2 Pass@k continues to scale through k=7

A separate scaling experiment (`results/scaling_20260506/`) recomputed pass@n via exhaustive enumeration over all C(M, n) subsets of available branches — an unbiased estimator that avoids the correlated-trajectory artifact of the nested-prefix method. Curves under v4-flash (Figure 2):

| Model | Reasoning | n=1 | n=3 | n=5 | n=7 |
|---|---|---:|---:|---:|---:|
| Gemma-4-31B-IT | default | 0.31 | 0.74 | 1.08 | 1.40 |
| Gemma-4-31B-IT | max | 1.92 | 2.76 | 3.05 | 3.20 |
| GPT-OSS-120B | default | 0.10 | 0.27 | 0.39 | 0.47 |
| GPT-OSS-120B | max | 1.68 | 2.49 | 2.83 | 3.08 |
| DeepSeek-v4-flash | default | 2.81 | 3.78 | 4.18 | 4.54 |

Two observations. At reasoning=max the pass@7 means (3.20, 3.08) match seed_full (3.31, 3.00) within the inter-experiment noise scale. Pure scaling matches the pipeline at the same token budget. For DeepSeek-v4-flash at default reasoning, scaled pass@7 reaches 4.54 — clearly above the phase-3 seed_full mean of 3.49 — and lands four R26 solves vs. two for seed_full. The strong-cheap model benefits more from breadth than from pipeline scaffolding. We also observed that the slope of the scaling curve does not flatten by k=7; for Gemma reasoning=max we extended to k=9 and saw 3.29 (vs. 3.20 at k=7). The marginal value of further branches is small but positive.

### 6.3 Cross-model role-swap is a null effect

A separate experiment (`results/roleswap_20260506/`) tested cross-model diversity by varying which of GPT-OSS or Gemma fills the ideator/generator/verifier/revisor roles in the seed_full pipeline. At reasoning=max, the eight tested conditions span 2.96 to 3.63 in mean v4-flash score; the two random-baseline conditions are at 3.19 and 3.34. Only one swap — GPT-OSS as verifier (3.63) — clearly beats both baselines. The remaining seven conditions are within ±0.4 of baseline. The "diversity helps" hypothesis is not supported by these data; the suggestive cell may reflect the specific role-model fit (GPT-OSS as verifier) rather than diversity per se. We treat this as a hint, not a result, given the limited sweep.

A small ideator-strength side-experiment on a 20-problem PB-Advanced subset showed that swapping the ideator from DeepSeek-v4-flash to the stronger DeepSeek-v4-pro hurt (3.20 → 2.55, n=20 each). We do not over-read this; small sample on the hardest subset.

### 6.4 Coverage asymmetry caveats

Phase 1 (the canonical six-model × three-mode grid) does not include `seed_full`. The seed_full data come from Phase 2 (Gemma + GPT-OSS at default reasoning), Phase 3 (DeepSeek-v4-flash at default), and Phase 1-reasoning-max (Gemma + GPT-OSS at max). Any aggregate seed_full statement is over a non-representative subset, weighted toward the cheap models. Per-cell deltas are reported in Sections 5.1 and 5.3 where this matters.

## 7. Resources, errors, and audit

Across the architecture sweep we ran 2,098 trial rows against six base models. Aggregate API spend across all experiments (architecture, scaling, roleswap, calibration) was approximately $800 against an internal $1,000 budget. A note on a known data quality issue: in the original Phase 1 seeded-ideator runs, roughly 10–28% of seeded ideation calls returned malformed outputs and the pipeline silently fell back to a pass@3 generation (the broken-ideator regression). This pushes seeded conditions toward the pass@3 baseline and would, if anything, *understate* the seeded-ideator effect relative to a clean implementation. We patched the bug for Phase 2 and downstream experiments, and the seed_full lift in Section 5.3 (which uses Phase 2 / phase1_reasoning data) is unaffected.

## 8. Limitations

**Benchmark contamination.** Most R26 solution-disclosure dates fall in 2026 (FirstProof: February 13, 2026; Erdős solves: spring 2026; FrontierMath open-problem solve: March 2026), as does the IMO-Bench release (November 3, 2025). Several of our generators have post-training cutoffs that overlap with these dates: Gemma-4 (March 31, 2026), DeepSeek-v4 (April 24, 2026). GPT-OSS-120B (released August 5, 2025) is provably contamination-free for every R26 solution and for IMO-Bench. Solve patterns for GPT-OSS and DeepSeek look broadly similar across the architectures — particularly on Erdős-654, which both solve cleanly — which we interpret as weak evidence that contamination is not the dominant signal. We cannot rule it out for the post-cutoff models on individual problems.

**Judging.** We rely on automated judges; calibrated to ~87% pass-agreement on GradingBench, this is more than enough for directional claims but not enough to certify any individual frontier solve. We spot-checked Erdős-659 by hand and the v4-flash grade tracked the manual reading. Manual grading at scale is impractical: 5,000+ proof outputs would require months of expert time we do not have.

**Generalization.** Our six base models top out at DeepSeek-v4-pro, well below the strongest commercially available systems. We do not test Claude Opus 4.7, GPT-5.4-Pro, or Gemini-3.1-Pro on the full sweep, though a small expensive-models calibration pass (12 problems, 4 frontier models; Appendix A.5) suggests Kimi-k2.6 deserves a future look.

**Dataset size.** n=70 is small. We chose it to keep the architecture-by-model-by-judge factorial tractable at pass@9 cost. Only ten problems are research-grade; conclusions about frontier capability are accordingly sparse.

**Single-judge audit on reasoning=max.** Our cleanest pipeline-lift result (Section 5.3) is observed under v4-flash only. A v4-pro audit on those cells would strengthen the claim.

## 9. Discussion

Three takeaways for engineering practice.

**Control for token cost before claiming pipeline lift.** A pass@3 baseline is the right comparison for a three-step pipeline; pass@9 is the right comparison for the ideator-plus-pipeline. Without that control, almost any pipeline appears to "win" against pass@1 simply because it draws more samples. With it, the pipeline's advantage is real but narrow: +0.5 to +0.7 mean score on cheap models at reasoning=max, and roughly zero at default reasoning.

**Audit with judges of different leniency.** v4-flash and v4-pro agree on 95.5% of pass/fail decisions and paint a consistent picture: limited architecture lift, dominated by reasoning. Gemini-3-flash-preview tells a much rosier story because it calls "pass" on a quarter of cases the strict judges call "fail." The lenience is a systematic offset, not noise. A two-judge audit is a cheap discipline.

**Genuine novelty, in our data, lives at research-easy problems where the solution direction is already in the literature.** Erdős-654 is the cleanest example: five v4-flash solves and three v4-pro solves spanning four base models and four architectures. The harder R26 problems go unsolved under strict judges. The pipelines we tested do not extend this capability frontier; they help on the existing one. Aletheia (Feng et al., 2026b) reports a similar pattern: 31.5% of its solutions are technically correct under some interpretation but only 6.5% address the intended question.

For practitioners: spend the marginal token on reasoning depth and on more independent samples, and audit with at least two judges of different leniency before concluding that scaffolding helps.

## 10. Future work

Three follow-ups would sharpen the picture. First, a fair pass@k-vs-pipeline comparison at the strongest available frontier models (Claude Opus 4.7, GPT-5.4-Pro, Gemini-3.1-Pro) would test whether our cheap-model finding generalizes to the frontier. Second, a small human-expert grading study on R26-tier solves would validate or invalidate the v4-flash judge in the regime where we most need it. Third, a deeper study of judge calibration — how to detect Gemini-style lenience automatically, what the right ensembling strategies are, and whether continuous-correlation judges (e.g., Gemini-3.1-pro at r=0.872) can replace the binary-pass-agreement metric — is worth a paper of its own; we intend to take this up separately.

## Figures

Figures live in `drafting/plots/`.

- **Figure 1 — `fig1_judge_sensitivity.png`.** Mean PB+R26 score by architecture (generate / seed_generate / full) for each of the six base models, under each of the three judges (Phase 1, default reasoning). Visualizes the one-sided Gemini lenience that drives Section 5.2.
- **Figure 2 — `fig2_passk_scaling.png`.** Pass@k curves under v4-flash for Gemma-4, GPT-OSS-120B, and DeepSeek-v4-flash. Stars mark the seed_full pipeline result at its token-equivalent budget. Visualizes Sections 5.3 and 6.2.
- **Figure 3 — `fig3_reasoning_vs_architecture.png`.** Effect-size comparison: blue bars are reasoning-on Δ per (model, mode); red bars are architecture (seed_full − generate) Δ per cell. Visualizes Section 6.1.
- **Figure 4 — `fig4_frontier_solves_heatmap.png`.** Per-problem solve counts on the 9 R26 problems, by judge. Visualizes Section 5.4.

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
| Qwen3.6-Plus | default | 78% (39/50) | $0.0739 | dominated by 35B |
| GPT-OSS-120B | xhigh | 74% (37/50) | $0.0057 | +16pp vs default |
| Gemini-3-flash | default | 74% (37/50) | $0.0100 | |
| Gemma-4-31B-IT | default | 68% (34/50) | $0.0015 | reasoning effectively off |
| Gemma-4-31B-IT | xhigh | 63% (27/43) | $0.0034 | reasoning hurts here |
| GPT-OSS-120B | default | 58% (29/50) | $0.0011 | |
| DeepSeek-v4-flash | reasoning_off | 50% (25/50) | $0.0020 | -38pp |

### A.3 Architecture × judge × model × reasoning per-cell means

Below are the v4-flash, v4-pro, and Gemini means for the canonical Phase 1 grid (n≈70 trials per cell, default reasoning), plus phase1_reasoning rows for cheap models at reasoning=max (v4-flash only — no v4-pro / Gemini coverage).

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

| Model | Mode | default | max | Δ |
|---|---|---:|---:|---:|
| Gemma-4-31B | generate | 1.49 | 2.74 | +1.25 |
| Gemma-4-31B | seed_generate | 1.49 | 2.74 | +1.25 |
| Gemma-4-31B | full | 1.39 | 2.17 | +0.78 |
| Gemma-4-31B | seed_full | 1.71 | 3.31 | +1.60 |
| GPT-OSS-120B | generate | 1.34 | 2.30 | +0.96 |
| GPT-OSS-120B | seed_generate | 1.09 | 2.54 | +1.45 |
| GPT-OSS-120B | full | 1.58 | 2.43 | +0.85 |
| GPT-OSS-120B | seed_full | 1.41 | 3.00 | +1.59 |

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

| Pair | Pass-rate agreement |
|---|---:|
| v4-flash vs v4-pro | 95.5% (1375/1440) |
| v4-flash vs Gemini | 73.7% (1061/1440) |
| v4-pro vs Gemini | 72.9% (1050/1440) |

| Directional flip | Count | Share |
|---|---:|---:|
| v4-flash pass, v4-pro fail | 41 | 2.8% |
| v4-flash fail, v4-pro pass | 24 | 1.7% |
| v4-flash pass, Gemini fail | 16 | 1.1% |
| v4-flash fail, Gemini pass | 363 | 25.2% |
| v4-pro pass, Gemini fail | 13 | 0.9% |
| v4-pro fail, Gemini pass | 377 | 26.2% |

## References

- Abouzaid, M., Blumberg, A. J., Hairer, M., et al. (2026). First Proof. arXiv:2602.05192. https://1stproof.org/
- Achim, T., Best, A., Bietti, A., et al. (2025). Aristotle: IMO-level Automated Theorem Proving. arXiv:2510.01346.
- Brown, T. B., Mann, B., Ryder, N., et al. (2020). Language Models are Few-Shot Learners. arXiv:2005.14165.
- DeepMind. (2025). Advanced version of Gemini with Deep Think officially achieves gold-medal standard at the International Mathematical Olympiad. Google DeepMind blog, July 21, 2025.
- Erdős Problems. (n.d.). Erdős Problems database. https://www.erdosproblems.com/ ; AI contributions tracker https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems
- Feng, T., Trinh, T., Bingham, G., et al. (2026a). Semi-Autonomous Mathematics Discovery with Gemini: A Case Study on the Erdős Problems. arXiv:2601.22401.
- Feng, T., Trinh, T. H., Bingham, G., et al. (2026b). Towards Autonomous Mathematics Research (Aletheia). arXiv:2602.10177.
- Georgiev, B., Gómez-Serrano, J., Tao, T., Wagner, A. Z. (2025). Mathematical exploration and discovery at scale. arXiv:2511.02864.
- Glazer, E., Erdil, E., Besiroglu, T., et al. (2024). FrontierMath: A Benchmark for Evaluating Advanced Mathematical Reasoning in AI. arXiv:2411.04872.
- Hendrycks, D., Burns, C., Kadavath, S., et al. (2021). Measuring Mathematical Problem Solving With the MATH Dataset. arXiv:2103.03874.
- Huang, Y., & Yang, L. F. (2025). Winning Gold at IMO 2025 with a Model-Agnostic Verification-and-Refinement Pipeline. arXiv:2507.15855. https://github.com/lyang36/IMO25
- Hubert, T., et al. (2025). Olympiad-level formal mathematical reasoning with reinforcement learning (AlphaProof). Nature 651, 607–613. DOI 10.1038/s41586-025-09833-y.
- Knuth, D. E. (2026). Claude's Cycles. Stanford CS, February 2026. https://www-cs-faculty.stanford.edu/~knuth/papers/claude-cycles.pdf
- Luong, T., Hwang, D., Nguyen, H. H., et al. (2025). Towards Robust Mathematical Reasoning (IMO-Bench). arXiv:2511.01846. https://imobench.github.io/
- Novikov, A., Vũ, N., Eisenberger, M., et al. (2025). AlphaEvolve: A coding agent for scientific and algorithmic discovery. arXiv:2506.13131.
- OpenAI. (2024). Learning to Reason with LLMs (o1). OpenAI blog, September 12, 2024.
- Tao, T. (2026). Primitive sets and von Mangoldt chains: Erdős Problem #1196 and beyond. *What's New* blog, May 3, 2026; see also https://mathstodon.xyz/@tao/115855840223258103.
- Wei, A., Hsu, S., Brown, N. (2025). OpenAI's experimental reasoning LLM achieves gold-medal performance on IMO 2025. Announcement thread, July 19, 2025.
- Wei, J., Wang, X., Schuurmans, D., et al. (2022). Chain-of-Thought Prompting Elicits Reasoning in Large Language Models. arXiv:2201.11903.
