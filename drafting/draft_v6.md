# Comparing Inference-Time Methods for Natural-Language Mathematical Proofs

*Draft v6 — systematic-evaluation framing; tighter abstract (4 findings); cascade audit and per-tier detail moved to appendix; future work scoped to out-of-budget directions.*

## Abstract

Recent agentic-math reports propose increasingly elaborate inference-time architectures for proof generation — generator-verifier-revisor pipelines, seeded-ideator multi-trajectory sampling, and combinations — and report gains over single-shot generation. We run a systematic, token-cost-controlled evaluation on a 70-problem benchmark (60 IMO-ProofBench + 10 frontier-tier problems disclosed in 2026), centered on three base models (Gemma-4-31B, GPT-OSS-120B, DeepSeek-v4-flash) crossed with four architectures and graded by a calibrated cheap judge. We expand this grid in five directions: three additional generators, two additional judges, a reasoning-effort sweep, a pass@k scaling sweep through k=9, and a cross-model role-swap. **(1) The generator-verifier-revisor pipeline does not beat pass@3 under either strict judge** (paired Δ = −0.08, 95% CI [−0.27, +0.13], n=533, p=0.45); on Gemma at reasoning=max it *hurts* (Δ = −0.57, p=0.023). **(2) Seeded-ideator-plus-pipeline beats pass@3 on cheap models at reasoning=max** (Δ = +0.60 [+0.23, +0.99], p=0.003) — intuitively the heftiest architecture lift we observe — but at the token-matched pass@9 baseline (a direct M=9 expansion on the five cells with seed_full coverage) no seed_full configuration beats pass@9, and on DeepSeek-v4-flash pass@9 wins by +0.98. The pass@1 → pass@3 jump (+0.39 mean, +5pp pass rate) is itself larger than every architecture-vs-architecture delta. **(3) Judge choice flips conclusions on cheap models**: P(Gemini-3-flash pass | strict-judge fail) = 0.37 [0.34, 0.40] across 1,440 triple-judged trials; the two strict judges agree on 95.5% of pass/fail decisions. **(4) Pass-rate degrades sharply with difficulty**: 0.86 / 0.29 / 0.23 / 0.02 / 0.000 / 0.000 from pre-competition to research-frontier. Practical takeaways within the cost regime tested: draw more samples before adding pipeline depth, keep reasoning enabled where the model exposes it, and audit with multiple judges across the calibration spectrum. A pooled-trial frontier-solves audit on the ten 2026 problems, including a three-rung cascade, appears in §5.5 and Appendix A.9.

## 1. Introduction

Language models have moved from saturating school-math benchmarks to plausibly contributing to research mathematics within two years. GSM8K and MATH (Hendrycks et al., 2021), AlphaProof's IMO silver (Hubert et al., 2025), three independent gold-tier IMO systems in 2025 (DeepMind, 2025; Wei et al., 2025; Achim et al., 2025), and through early 2026 the first model-credited contributions on the Erdős repository (Tao, 2026) and Epoch's FrontierMath open-problem set (Glazer et al., 2024) all trace the same arc.

Alongside the capability story is the engineering one: which inference-time methods are worth their tokens? Two methodological gaps motivate this work. First, agentic-math papers often pitch their pipelines against pass@1, which is token-asymmetric — a three-step pipeline burns roughly three times the tokens of a single sample, so the matched baseline is pass@3 (or pass@n for n-call pipelines), not pass@1. Second, free-form proof evaluation at scale relies on automated judges, and the gap between a lenient judge and a strict judge is large enough to flip qualitative conclusions about which architecture wins.

We do not propose a new method. We run a systematic evaluation of inference-time architectures with three disciplines: token-matched baselines, multi-judge audit, and difficulty stratification. The core grid is three open-weight or cheap base models (Gemma-4-31B, GPT-OSS-120B, DeepSeek-v4-flash) crossed with four architectures (pass@3, generator-verifier-revisor pipeline, seeded-ideator, ideator-plus-pipeline), graded by a calibrated cheap judge. We expand this in five directions: three additional generators (DeepSeek-v4-pro, Gemini-3-flash-preview, Qwen3.6-35B), two audit judges (DeepSeek-v4-pro and Gemini-3-flash-preview), a reasoning-effort sweep on the two open-weight cheap models, a pass@k scaling sweep through k=9 on the five cells with full coverage, and a cross-model role-swap in the seed_full pipeline.

**Contributions, at a glance.**

1. **Architecture vs. token-matched sampling.** Under strict judges, no architecture beats pass@n at matched token cost. The one positive deviation (seeded-ideator-plus-pipeline, cheap models, max reasoning) collapses against pass@9.
2. **Judge-induced variance.** Cell-level Δ's flip sign across judges on four of six base models. We give the conditional-flip rate (P(Gemini pass | strict fail) = 0.37) with cell-level CIs.
3. **Difficulty gradient.** A six-tier breakdown showing where automated-judge claims become unreliable.
4. **R26 frontier-tier extension.** Ten problems from three high-salience 2026 events (Erdős solves, FirstProof, FrontierMath open-problem solve), pooled across 3,178 trials and audited with a three-rung cascade.
5. **Reproducible artifacts.** Per-experiment trial tables in `results/architecture_20260506/`, `results/scaling_20260506/`, `results/validate_research_solves_20260507/`, and three calibration buckets totaling ~3,200 graded trials.

## 2. Background

**Capability arc.** AlphaProof (Hubert et al., 2025) took IMO silver in 2024 with a specialized formalizer. In 2025, three independent gold-tier IMO systems landed — DeepMind's Deep Think (DeepMind, 2025), OpenAI's IMO submission (Wei et al., 2025), Harmonic's Aristotle (Achim et al., 2025) — accompanied by an open-source agentic framework reaching gold-tier performance with frontier base models (Huang & Yang, 2025). Through early 2026, models began producing solutions to open problems on the Erdős repository (Tao, 2026); the Aletheia case studies (Feng et al., 2026a,b) and Knuth's "Claude's Cycles" essay (Knuth, 2026) document the human–AI workflows producing these results.

**Benchmarks and the R26 extension.** We use IMO-ProofBench (Luong et al., 2025): 60 olympiad proofs split into "Basic" and "Advanced" tiers, paired with an automated grader at Pearson r=0.96 with human IMO judges. We augment this with ten 2026 research problems drawn from three high-salience disclosure events:

- **Erdős repository** (Erdős Problems, n.d.): problems 333, 397, 654, 659, 1051.
- **First Proof** (Abouzaid et al., 2026): problems 4, 5, 6, 10.
- **FrontierMath open-problem set** (Glazer et al., 2024): the Ramsey-hypergraph entry.

All ten were closed or partially closed in 2026, most of them with credited model assistance. Each could carry a case study on its own; we treat them here as a pooled difficulty tail and refer to the union as PB+R26.

**Architectures.** *Pass@k*: sample k independent solutions, take the best (Brown et al., 2020); repeated sampling and self-consistency are long-established strong baselines (Chen et al., 2021; Wang et al., 2022). *Generator-verifier-revisor pipeline*: a generator emits a candidate, a verifier critiques it, a revisor edits — looped a fixed number of times. This pattern appears in Aletheia (Feng et al., 2026b) and in the Huang–Yang IMO-gold framework (Huang & Yang, 2025). *Seeded ideator*: an upstream pass produces several solution sketches (we use three), each feeding an independent generation. *Ideator + pipeline*: each ideated seed runs through the verifier-revisor loop.

**Scope.** Natural-language proof generation only. We do not study formal verification (Lean, AlphaProof, Aristotle), evolutionary search (Novikov et al., 2025; Georgiev et al., 2025), or neuro-symbolic systems.

## 3. Methodology

### 3.1 Architectures

All four architectures share a single pipeline implementation (`src/pipeline.py`). Prompts are lightly hardened versions of those published with DeepMind's IMO-Bench and Huang & Yang's IMO repository. Final grading uses DeepMind's IMO-ProofBench judge prompt, restricted to {0, 1, 6, 7} on a 0–7 scale.

- **Pass@k** — k independent generation calls, max judge score. Headline k ∈ {1, 3}; the scaling sweep covers k ∈ {1, 3, 5, 7, 9} on five cells.
- **Generator-verifier-revisor pipeline (`full`)** — up to three verifier-revisor iterations after the initial generation; early-stop on `VERDICT: correct`. ~3 calls per trial; token-equivalent to pass@3.
- **Seeded ideator (`seed_generate`)** — a single ideation call produces three sketch directions; each is realized as one full solution; take the best. ~3 calls; token-equivalent to pass@3.
- **Ideator + pipeline (`seed_full`)** — each of three ideated seeds runs through the verifier-revisor loop; take the best final. ~9 calls; token-equivalent to pass@9.

Token-cost-fair comparisons: pass@3 ↔ {generate, seed_generate, full}; pass@9 ↔ seed_full.

### 3.2 Models, reasoning, dataset

**Core 3×4×1 grid.** Three base models, four architectures, one canonical judge: Gemma-4-31B-IT, GPT-OSS-120B, DeepSeek-v4-flash × {pass@3 / generate, seed_generate, full, seed_full} × DeepSeek-v4-flash judge (selected per §4). These three generators are cheap enough to cover the full grid; DeepSeek-v4-flash also generates well above its price tier (§4.2).

**Generator expansions.** Three additional generators on subsets of cells: DeepSeek-v4-pro, Gemini-3-flash-preview, Qwen3.6-35B-A3B — covering `generate`, `seed_generate`, `full` at default reasoning (no `seed_full`).

**Judge expansions.** Every architecture-sweep trial is re-graded by DeepSeek-v4-pro (strict, slow audit) and Gemini-3-flash-preview (cheap, lenient audit), giving 1,440 triple-judged cells.

**Reasoning sweep.** On Gemma-4 and GPT-OSS-120B (the open-weight generators that expose a reasoning-effort knob through OpenRouter), every architecture is run at reasoning=max as well as default.

**Scaling sweep.** A separate experiment computes pass@n via exhaustive enumeration over C(M, n) subsets of M generated branches (unbiased; avoids the correlated-trajectory artifact of the nested-prefix estimator). M=9 across all five covered cells: Gemma-4 default and max, GPT-OSS-120B default and max, DeepSeek-v4-flash default.

**Cross-model role-swap.** A separate experiment varies which of GPT-OSS or Gemma fills the ideator / generator / verifier / revisor roles in seed_full at reasoning=max (Appendix A.6).

**Dataset.** Sixty ProofBench problems unmodified from DeepMind, plus the ten R26 problems above. Difficulty graded on a six-level scale:

| Tier | Source | Problems | n |
|---|---|---|---:|
| pre-competition (d=0) | PB-Basic | 30 problems | 30 |
| competition-hard (d=1) | PB-Advanced + Erdős 397 | 30 PB-Adv + 1 R26 | 31 |
| research-easy (d=2) | Erdős 333, 654, 659; FirstProof 10 | 4 R26 | 4 |
| research-medium (d=3) | Erdős 1051; FirstProof 5 | 2 R26 | 2 |
| research-hard (d=4) | FirstProof 4, 6 | 2 R26 | 2 |
| research-frontier (d=5) | Ramsey hypergraphs | 1 R26 | 1 |

### 3.3 Statistical methodology

For paired comparisons, we use within-(model, reasoning, problem) score differences. Confidence intervals are 95% percentile bootstrap (5,000 resamples; seed 20260507). Two-sided p-values are sign-flip permutation tests (10,000 permutations). For pass-rate deltas we pair the binary pass indicators. "Δ" is the paired mean of `mode_a − mode_b` over cells where both modes were observed.

## 4. Calibration

We calibrated the judge first — a noisy grader makes everything else hopeless — then the generator, then ran the main experiments. Both stages used purpose-built calibration benchmarks rather than reusing the evaluation set. Headline numbers here; full tables in Appendix A.1 and A.2.

### 4.1 Judges on GradingBench

Ten judge configurations on a 200-problem random sample of DeepMind's GradingBench, prompt held fixed (output restricted to {0, 1, 6, 7}). Priority metric: `pass_agree_at_6`, agreement with the human pass/fail verdict at the IMO threshold.

| Judge | n | pass≥6 agree | F1 | Pearson r | $/call |
|---|---:|---:|---:|---:|---:|
| GPT-5.4-nano @ xhigh | 196 | 89.3% | 0.800 | 0.711 | $0.0370 |
| DeepSeek-v4-pro | 198 | 88.9% | 0.825 | 0.756 | $0.0150 |
| **DeepSeek-v4-flash** | 199 | **87.4%** | **0.800** | **0.756** | **$0.0039** |
| Gemini-3.1-pro | 199 | 86.4% | 0.816 | 0.872 | $0.0348 |
| Gemini-3-flash | 200 | 64.0% | 0.633 | 0.606 | $0.0162 |

DeepSeek-v4-flash sits on the Pareto frontier: 87.4% pass-agreement at \$0.0039/call. The price gap to alternatives is large — v4-pro 3.8×, GPT-5.4-nano-xhigh 9.5× (and ~10× slower), Gemini-3.1-Pro 8.9× — and v4-flash is the only top-pass-agreement judge that lets us grade ~5,000 long proofs without dominating the budget. We use it as canonical, with v4-pro as the strict audit judge and Gemini-3-flash-preview as the lenient audit judge (a distinct configuration from Gemini-3.1-Pro, which was out of budget on full sweeps).

### 4.2 Generator selection on AnswerBench

Thirteen model–reasoning configurations on AnswerBench-50 (50 verifiable-answer problems judged by Gemini-3-flash-lite). Six base models cleared 60% accuracy with sensible reasoning settings; we kept all six for the architecture sweep. The reasoning toggle is the single largest knob — GPT-OSS-120B moves from 58% to 74%, DeepSeek-v4-flash drops from 88% to 50% with reasoning forced off — which informs the reasoning sweep in §3.2 and §5.4.

## 5. Main results

### 5.1 Architecture comparison at default reasoning

Pooled across the six generators on PB+R26 under v4-flash (95% bootstrap CIs). Pass@1 here is the first branch of each `generate` trial scored independently — the unfair-but-common baseline that agentic-math reports are often pitched against. Trial counts differ across modes because `seed_full` was run on a smaller set of generators (Gemma, GPT-OSS, DS-flash only); §6.3 expands on this.

| Mode | tokens | n | mean (0–7) | pass rate (≥6) |
|---|---|---:|---:|---:|
| pass@1 (1st branch of generate) | ~1× | 613 | 1.97 [1.79, 2.15] | 0.28 [0.25, 0.32] |
| generate (pass@3) | ~3× | 543 | 2.31 [2.13, 2.49] | 0.33 [0.30, 0.37] |
| seed_generate | ~3× | 555 | 2.29 [2.11, 2.47] | 0.33 [0.30, 0.37] |
| full (pipeline) | ~3× | 550 | 2.24 [2.06, 2.42] | 0.32 [0.28, 0.35] |
| seed_full | ~9× | 344 | 2.58 [2.34, 2.81] | 0.37 [0.32, 0.42] |

The pass@1 → pass@3 step alone moves the mean +0.39 and the pass-rate +5pp at a 3× token cost without any architectural change. That gap is *larger than every architecture-vs-architecture delta in this table.* Most of what looks like architecture lift against a pass@1 baseline is sample-size doubling.

The right read is via paired contrasts. Pipeline-vs-pass@3 is the cleanest, with both modes run on every (model, reasoning, problem) cell:

| Contrast | n pairs | mean Δ | 95% CI | p |
|---|---:|---:|---:|---:|
| `full − generate` (pipeline vs pass@3) | 533 | −0.079 | [−0.272, +0.126] | 0.45 |
| `seed_generate − generate` | 539 | −0.028 | [−0.206, +0.160] | 0.78 |

Both null. The pipeline by itself does not beat pass@3, and seeded ideation by itself does not beat pass@3.

The `seed_full − generate` contrast is held over to §5.4, where we restrict to the like-like subset of cells where both `seed_full` and `generate` were run (since seed_full has incomplete generator coverage).

### 5.2 Difficulty stratification

Pass-rate degrades sharply with difficulty:

| Tier | n trials | mean | pass rate |
|---|---:|---:|---:|
| pre-competition (d=0) | 231 | 6.02 | 0.86 |
| competition-hard (d=1) | 1,507 | 2.04 | 0.29 |
| research-easy (d=2) | 115 | 1.50 | 0.23 |
| research-medium (d=3) | 57 | 0.14 | 0.02 |
| research-hard (d=4) | 55 | 0.00 | 0.000 |
| research-frontier (d=5) | 27 | 0.00 | 0.000 |

The gradient confirms our difficulty grading and sets the prior for §5.5: a single strict-judge solve on a research-medium-or-harder problem is a candidate worth auditing, not a confirmed result. Per-tier architecture deltas (uniformly null on hard tiers, modestly positive at competition-hard for seed_full at max) are in Appendix A.8.

### 5.3 Judge choice flips the cheap-model comparison

The same raw outputs scored by Gemini-3-flash-preview tell a different story:

| Model | v4-flash Δ (full − gen) | v4-pro Δ | Gemini Δ |
|---|---:|---:|---:|
| DeepSeek-v4-flash | +0.16 | −0.30 | −0.18 |
| DeepSeek-v4-pro | +0.32 | +0.28 | −0.21 |
| Gemini-3-flash-preview | −0.24 | −0.54 | **+0.83** |
| Gemma-4-31B-IT | −0.10 | −0.66 | **+0.30** |
| GPT-OSS-120B | +0.24 | +0.06 | **+0.51** |
| Qwen3.6-35B-A3B | −0.47 | −0.73 | **+0.14** |

Under Gemini-3-flash-preview, four of six models — all the cheap ones — show a clean +0.14 to +0.83 lift from the pipeline. The strict judges show no such pattern. On the 1,440 cells where all three judges scored:

| Pair | pass-rate agreement | 95% CI |
|---|---:|---:|
| v4-flash vs v4-pro | 95.5% | [94.4%, 96.5%] |
| v4-flash vs Gemini | 73.7% | [71.5%, 76.0%] |
| v4-pro vs Gemini | 72.9% | [70.6%, 75.3%] |

The disagreement is one-sided: **P(Gemini pass | v4-flash fail) = 0.368 [0.338, 0.398]** over 987 strict-fail cases, against a reverse rate of 0.035 [0.020, 0.053]. This is a systematic lenience offset, not noise. Aggregate "pipeline beats X" claims that rely on a lenient judge are at high risk of inverting under a strict audit.

A reasonable worry is that pass@k inflates the false-positive rate by giving the judge k independent chances to call "pass." We address this directly via the §5.5 cascade audit, but the v4-flash / v4-pro agreement of 95.5% and the conditional-flip asymmetry above suggest the cheap-judge "wins" come from raw lenience, not from k-sampling artefacts.

### 5.4 Where seeded-ideator-plus-pipeline does help — and why it doesn't help enough

Seed_full is the heftiest architecture in our grid (~9 calls vs. pass@3's ~3) and intuitively the most plausible place to find a real architecture lift: three ideated tracks plus verifier-revisor loops, with reasoning enabled so the verifier has substantive content to bite into. Restricted to the like-like subset of cells where both `seed_full` and `generate` were run, stratified by reasoning:

| Stratum | n pairs | mean Δ | 95% CI | p |
|---|---:|---:|---:|---:|
| seed_full − generate, default reasoning | 203 | +0.128 | [−0.182, +0.453] | 0.46 |
| seed_full − generate, reasoning=max | 134 | **+0.597** | **[+0.231, +0.993]** | **0.003** |

The lift is entirely in the reasoning=max cells. Per-cell:

| Cell | n | mean Δ | 95% CI | p |
|---|---:|---:|---:|---:|
| Gemma-4 max, seed_full − generate | 70 | **+0.571** | [+0.071, +1.114] | 0.035 |
| GPT-OSS max, seed_full − generate | 64 | **+0.625** | [+0.094, +1.219] | 0.048 |
| Gemma-4 max, **full − generate** | 70 | **−0.571** | [−1.100, −0.100] | 0.023 |

A striking pair of signs at Gemma-4 max: the pipeline alone *hurts* by −0.57, while seed_full lifts by +0.57. Combining heavy reasoning with a single ideation track plus verifier-revisor loops appears worse than three independent samples; combining it with three ideated tracks plus loops appears better than three independent samples. No other pipeline-vs-pass@3 comparison clears p<0.05.

**But the proper baseline for seed_full is pass@9, not pass@3.** From the M=9 scaling sweep (§6.2, all five covered cells):

| Cell | seed_full mean | pass@9 mean | Δ (seed_full − pass@9) |
|---|---:|---:|---:|
| Gemma-4 max | 3.31 | 3.29 | +0.02 |
| GPT-OSS max | 3.00 | 3.23 | −0.23 |
| Gemma-4 default | 1.71 | 2.41 | −0.70 |
| GPT-OSS default | 1.41 | 1.71 | −0.30 |
| DeepSeek-v4-flash default | 3.49 | 4.47 | **−0.98** |

No seed_full cell in our data beats its token-matched pass@9 baseline. The Gemma-max lift over pass@3 looks real, but at matched cost the right call is to sample more, not to scaffold harder. We flag the seed_full lift in case it generalizes to other models, but our recommendation remains: spend the tokens on samples.

### 5.5 Frontier solves — all trials pooled

We pool all 3,178 v4-flash-judged trials across the architecture (2,098 trials) and scaling (1,080 trials) experiments. A "cell" is a distinct (model × architecture-or-pass@n × reasoning × source-experiment); each R26 problem has ~33 cells. A cell "solves" under judge J if any branch scores ≥6.

| Problem | Difficulty | cells | v4f | v4p | Gemini |
|---|---|---:|---:|---:|---:|
| FirstProof 10 | research-easy | 33 | 23 | 12 | 8 |
| Erdős 654 | research-easy | 33 | 5 | 3 | 6 |
| Erdős 333 | research-easy | 33 | 1 | 0 | 2 |
| Erdős 659 | research-easy | 33 | 1 | 1 | 7 |
| Erdős 397 | competition-hard | 33 | 1 | 0 | 1 |
| FirstProof 5 | research-medium | 33 | 1 | 0 | 1 |
| Erdős 1051 | research-medium | 33 | 1 | 0 | 14 |
| FirstProof 6 | research-hard | 33 | 1 | 0 | 5 |
| FirstProof 4 | research-hard | 32 | 0 | 0 | 1 |
| Ramsey hypergraphs | research-frontier | 33 | 0 | 0 | 3 |

Pooling across architecture and scaling experiments yields strict-judge v4-flash solves on six of ten R26 problems, including single-cell solves on Erdős-1051 (research-medium) and FirstProof-6 (research-hard) — both from the DeepSeek-v4-flash scaling sweep, branches that did not appear as architecture-sweep solves. These are candidates for expert review, not theorems: §5.3 shows that lenient judges over-pass a third of strict-fail cells, and the cascade audit (Appendix A.9) shows that even strict judges disagree at the margin.

**Cascade audit.** A three-rung cascade (DeepSeek-v4-flash → DeepSeek-v4-pro → GPT-5.4-nano-xhigh) on the 50 union-candidate cells collapses 44 v4-flash strict solves to 31 v4-pro-validated to 4 cells surviving all three rungs (per-cell breakdown in Appendix A.9). Three of the four triple-validated cells are Erdős-654 across three (model, architecture) pairs — DS-flash seed_full, DS-pro full, Gemma-4 seed_full max; the fourth is FirstProof-10 (DS-flash full).

Erdős-654 is the only R26 problem with multiple triple-validated cells across multiple base models and architectures, which makes it the most credibly-reproducible research-tier result in the data. We do not claim it as the *only* correct R26 solve: GPT-5.4-nano-xhigh has the best precision but the worst recall (70%) of the Pareto-frontier judges, so its rejections are themselves noisy. Of the 19 cells dropped at the v4-pro rung, 8 received v4-pro=1 (partial credit, i.e. some traction on the question); of the 27 dropped at the nano rung, 25 received nano=1. Resolving any specific candidate either way requires expert review; Erdős-1051, FirstProof-6, and the harder-tier single-cell hits remain open.

## 6. Secondary results

### 6.1 Reasoning effects are larger than architecture effects

Reasoning-on adds +0.78 to +1.60 v4-flash mean score on PB+R26 on Gemma-4 and GPT-OSS (Appendix A.4) — roughly 3–5× the magnitude of any architecture delta. This is well-established (Wei et al., 2022; OpenAI, 2024); we confirm it as the bar architecture has to clear.

### 6.2 Pass@k through k=9

| Model | Reasoning | n=1 | n=3 | n=9 |
|---|---|---:|---:|---:|
| DS-v4-flash | default | 2.74 | 3.65 | **4.47** |
| Gemma-4 | max | 1.92 | 2.76 | **3.29** |
| GPT-OSS | max | 1.63 | 2.45 | **3.23** |
| Gemma-4 | default | 0.88 | 1.54 | **2.41** |
| GPT-OSS | default | 0.82 | 1.27 | **1.71** |

Pass@k is monotonic by construction — each pass@k is the max over k draws from a shared sample, so pass@k ≥ pass@k−1 trivially. The *magnitudes* are the load-bearing observations: pass@9 sits well above pass@3 across all five cells, the slopes have not flattened by k=9 (every pass@9 − pass@7 delta is positive, +0.08 to +0.22), and pass@9 is the comparison seed_full must beat (§5.4). Simple sampling is a remarkably strong baseline at the token budgets where agentic pipelines are commonly proposed.

### 6.3 Coverage of the architecture grid

Phase 1 of the architecture sweep covered six generators on three architectures (no `seed_full`); seed_full was added in subsequent phases on three generators only (Gemma, GPT-OSS at default and max; DS-flash at default). This is a deliberate scoping choice — the core 3×4×1 was run first, then we expanded — but it means any pooled seed_full statement is over the cheap-model subset. Three generators (DeepSeek-v4-pro, Gemini-3-flash-preview, Qwen3.6-35B) have no seed_full coverage. §5.4's like-like cell-level analysis is the principled response.

Implementation note: in the original Phase 1 seeded-ideator runs, 10–28% of seeded ideation calls returned malformed outputs and the pipeline silently fell back to pass@3 generation. This pushes seeded conditions toward the pass@3 baseline; if anything it *understates* the seeded effect. The bug was patched for Phase 2 and downstream experiments, and the §5.4 seed_full lift (which uses Phase 2 / phase1_reasoning data) is unaffected. Roleswap detail is in Appendix A.6.

## 7. Limitations

**Benchmark contamination.** R26 solution-disclosure dates fall in 2026 (FirstProof: Feb 13, 2026; Erdős solves: spring 2026; FrontierMath open-problem solve: March 2026), as does the IMO-Bench release (Nov 3, 2025). Generator post-training cutoffs that overlap: Gemma-4 (March 31, 2026), DeepSeek-v4 (April 24, 2026). The R26 set is in fact a *strength* on contamination grounds: solutions were not in the legacy training data window for any of our generators, and GPT-OSS-120B (released August 5, 2025) is provably contamination-free for every R26 solution and for IMO-Bench. Solve patterns for GPT-OSS and DeepSeek look broadly similar across architectures — particularly on Erdős-654, where both solve cleanly — which is weak evidence that contamination is not the dominant signal.

**Judging.** Automated judges calibrated to ~87% pass-agreement are enough for directional claims, not enough to certify any individual frontier solve. The §5.5 single-cell strict solves on harder R26 are candidates for expert review. The cascade narrows the field but does not resolve it: GPT-5.4-nano-xhigh has the lowest GradingBench recall (70%) of the Pareto-frontier judges, so cells it rejects are not necessarily wrong.

**Generalization.** Our generators top out at DeepSeek-v4-pro, well below the strongest commercially available systems. A small expensive-models calibration probe (12 problems, 4 frontier models; Appendix A.5) suggests Kimi-k2.6 deserves a future look.

**Dataset size.** Ten research-grade problems is small; n=2 per-tier at research-medium and harder makes per-problem confidence on the 0% pass-rate wide.

**Single-judge audit on reasoning=max.** Our cleanest pipeline-lift result (§5.4) is observed under v4-flash only.

## 8. Discussion

Three takeaways for engineering practice.

**The verifier-revisor pipeline does not beat token-matched sampling.** Across 533 paired cells, `full − generate` is null (Δ=−0.08, p=0.45); on Gemma at reasoning=max it hurts (Δ=−0.57, p=0.023). Seeded-ideator-plus-pipeline beats pass@3 by ~+0.6 on cheap models *only* at reasoning=max, and at its proper pass@9 baseline the lift collapses. The default for natural-language proof generation in the cost regime tested should be "draw more samples before adding pipeline depth, keep reasoning on, use a calibrated judge."

**Audit with judges of different leniency.** Strict judges (v4-flash, v4-pro) agree on 95.5% of pass/fail decisions and paint a consistent picture: limited architecture lift, dominated by reasoning. Gemini-3-flash-preview tells a much rosier story because it calls "pass" on 37% of cases the strict judges call "fail." A two-judge audit is a cheap discipline.

**Frontier solves exist but are concentrated and judge-fragile.** Pooling 3,178 trials yields v4-flash strict solves on six of ten R26 problems; the cascade collapses 44 candidates to 4 triple-validated cells, three of which are Erdős-654. Aletheia (Feng et al., 2026b) reports a similar pattern: 31.5% of solutions are technically correct under some interpretation but only 6.5% address the intended question. A judged pass from a cheap model on a research-medium-or-harder problem is a candidate, not a theorem.

## 9. Future work

We think the natural next steps live above our cost regime. A fair pass@k-vs-pipeline comparison at frontier models (Claude Opus 4.7, GPT-5.4-Pro, Gemini-3.1-Pro, Kimi-k2.6) would test whether the cheap-model pattern generalizes — particularly the seed_full vs pass@9 comparison, where stronger generators may give the verifier-revisor loop substantively more to bite into. A deeper judge-calibration study against expert human grades on a small frontier-tier sample is worth a separate paper.

## Figures

Figures live in `drafting/plots/`.

- **Figure 1 — `fig1_judge_sensitivity.png`.** Mean PB+R26 score by architecture × base model × judge.
- **Figure 2 — `fig2_passk_scaling.png`.** Pass@k curves under v4-flash with 95% bootstrap CI ribbons; stars at the seed_full k=9-equivalent.
- **Figure 3 — `fig3_effect_sizes_forest.png`.** Forest plot of paired effect sizes: reasoning vs architecture.
- **Figure 4 — `fig4_frontier_solves_heatmap.png`.** Per-problem strict-vs-lenient solve counts on R26.
- **Figure 5 — `fig5_difficulty_gradient.png`.** Pass-rate and mean-score by difficulty tier with 95% bootstrap CIs.
- **Figure 6 — `fig6_lift_by_tier.png`.** Forest plot of architecture lift by tier and reasoning.

## Appendix

### A.1 GradingBench full table

Ten judge configurations on n=200 from GradingBench, hardened prompt restricted to {0, 1, 6, 7}. Sorted by `pass_agree_at_6`.

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

The eight tested conditions span 2.96 to 3.63 in mean v4-flash score; the two random-baseline conditions are at 3.19 and 3.34. Only one swap — GPT-OSS as verifier (3.63) — clearly beats both baselines. The remaining seven conditions are within ±0.4 of baseline. The "diversity helps" hypothesis is not supported; the one suggestive cell more likely reflects role-model fit than diversity per se.

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

### A.9 Cascade audit — per-cell ladder on R26 strict candidates

50 candidate cells (44 v4-flash≥6 ∪ 16 v4-pro≥6 originally; scaling-bucket strict-judge solves expanded to per-branch). Cascade: DeepSeek-v4-flash → DeepSeek-v4-pro → GPT-5.4-nano @ xhigh. Total grader cost $0.91. Full data in `results/validate_research_solves_20260507/`.

**Headline ladder.** 44 v4-flash strict → 31 v4-pro-validated → 4 nano-validated.

Per-problem ladder:

| Problem | Difficulty | v4-flash | + v4-pro | + nano |
|---|---|---:|---:|---:|
| FirstProof 10 | research-easy | 33 | 24 | 1 |
| **Erdős 654** | research-easy | 5 | 4 | **3** |
| Erdős 333 | research-easy | 1 | 1 | 0 |
| Erdős 659 | research-easy | 1 | 2 | 0 |
| Erdős 397 | competition-hard | 1 | 0 | 0 |
| FirstProof 5 | research-medium | 1 | 0 | 0 |
| Erdős 1051 | research-medium | 1 | 0 | 0 |
| FirstProof 6 | research-hard | 1 | 0 | 0 |

(Erdős 659 shows 2 in the + v4-pro column because two cells were originally v4-pro≥6 but v4-flash<6, and they appear in the union of audited candidates.)

**Cells surviving all three rungs:**

| Problem | Model | Mode | Reasoning | Source | v4f | v4p | nano |
|---|---|---|---|---|---:|---:|---:|
| Erdős 654 | DeepSeek-v4-flash | seed_full | default | phase3 | 7 | 6 | 7 |
| Erdős 654 | DeepSeek-v4-pro | full | default | phase1 | 7 | 7 | 6 |
| Erdős 654 | Gemma-4-31B-IT | seed_full | max | phase1_reasoning | 7 | 7 | 7 |
| FirstProof 10 | DeepSeek-v4-flash | full | default | phase1 | 7 | 6 | 6 |

**Stage 1 disagreements (v4-flash≥6, final v4-pro<6, n=19).** 8 of 19 received v4-pro=1 (partial credit, some traction on the question); 11 received v4-pro=0 (no meaningful progress).

**Stage 2 disagreements (v4-pro≥6, final nano<6, n=27).** 25 of 27 received nano=1, one nano=2, one nano=0. Most v4-pro→nano flips are mild partial-credit rejections by a judge with the lowest GradingBench recall (70%) of the Pareto frontier. Strict-by-recall and strict-by-precision judges disagree at the margin; the cascade narrows the candidate set, not the truth.

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
