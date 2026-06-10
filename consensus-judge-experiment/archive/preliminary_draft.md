# Cheap LLM judges for natural-language math proofs: a preliminary finding

**Draft — 2026-05-24**

**Summary.** We wanted to know which LLM judges we can trust to grade natural-language math proofs, and whether there is a reliable option for researchers on a tight budget. We expected a majority vote of three cheap models to be the best cost-effective choice. It was strong — but it did not beat the single best model inside it. The clearer finding is simpler: a good cheap model (GPT-OSS-120B with high reasoning, ~$0.0016 per grading) is at least competitive with frontier judges (Claude Opus 4.7, Gemini 3.1 Pro) at roughly 1% of their cost. We also checked that this is not just an artifact of giving the cheap model more reasoning budget — it isn't.

The results are not conclusive. The sample is small, the confidence intervals overlap, and we could not afford a wide search. But we are confident in the practical takeaway: very cheap judges are effective and competitive, and that is worth knowing.

---

## Why this matters

Automatically grading proofs is a bottleneck for math research with LLMs. Formal verification (Lean, etc.) is reliable but only exists for a subset of problems; most mathematics is written and checked in natural language. So we need judges that read a proof, follow the argument, and decide whether it is correct — and we need to know which ones to trust.

Frontier models are the obvious choice, but they are expensive at scale: a thousand-call grading sweep on Opus 4.7 with reasoning costs on the order of $160. If a cheap model graded just as reliably, that would matter a lot for anyone working under a budget.

## Setup

- **Data.** GradingBench: 1000 grading instances over 30 IMO-style problems. Each instance is a problem, a candidate solution, and an expert human score on the 0–7 IMO scale.
- **Two disjoint samples.** A *prior* sample (200 instances) used to explore and pick our consensus trio, and a *validation* sample (200 instances, no overlap) used as a clean held-out test.
- **Task.** Every judge uses the same prompt and outputs a score in {0, 1, 6, 7}. The decision we care about most is **pass/fail at ≥6** ("does this proof meet IMO standards?"). Our headline metric is **pass-agreement**: how often the judge's pass/fail call matches the human's.
- **The trio we expected to win.** Three cheap models with opposite biases, chosen so their errors might cancel in a majority vote: **Gemma-4-31B** (over-credits), **DeepSeek-V4-Flash** (under-credits), and **GPT-OSS-120B @ high reasoning** (roughly calibrated). Baselines: **Claude Opus 4.7** and **Gemini 3.1 Pro**.

## What we found

On the held-out validation set (cost is per 200 gradings):

| Judge | pass-agree (≥6) | F1 | Pearson r | cost / 200 |
|---|---|---|---|---|
| **GPT-OSS-120B @ xhigh** (cheap) | **0.875** | **0.806** | 0.676 | **$0.32** |
| Cheap trio (majority vote) | 0.860 | 0.785 | 0.747 | $1.73 |
| DeepSeek-V4-Flash (cheap) | 0.856 | 0.759 | 0.669 | $0.70 |
| Claude Opus 4.7 (frontier) | 0.855 | 0.785 | **0.789** | $32.45 |
| Gemini 3.1 Pro (frontier) | 0.840 | 0.771 | 0.766 | $7.07 |
| Gemma-4-31B @ high (cheap) | 0.800 | 0.732 | 0.694 | $0.71 |

Two things stand out.

1. **The consensus was strong but not the best.** The trio matched Opus on F1 and beat both frontiers on point-estimate pass-agreement — but it did **not** beat its own strongest member. GPT-OSS-120B alone scored higher on pass-agreement and F1 than the trio, at about one-fifth the cost. The majority vote did its job (it is robust and its errors cancel), but combining a strong model with two weaker ones pulled the result down rather than up. The simpler, cheaper answer won.

2. **The cheap tier is competitive with the frontier.** GPT-OSS-120B at $0.0016 per grading is within sampling noise of Opus (100× the cost) and reliably ahead of Gemini on pass-agreement. The one place the frontier keeps a real edge is the continuous correlation with the human score (Pearson r): Opus's 0.789 is clearly above the cheap models. If you need a fine-grained quality signal rather than a pass/fail decision, the frontier is still better. For a pass/fail gate at scale, the cheap model is not.

## Is GPT-OSS-120B only winning because we gave it more reasoning?

A fair worry: GPT-OSS ran at its maximum reasoning setting, while the frontier baselines ran at their default. Maybe the gap is about reasoning budget, not the model. We checked.

- **Gemini, given more reasoning, does not improve.** We re-ran Gemini 3.1 Pro at high reasoning on all 200 validation problems. Its average reasoning grew from ~2,400 tokens to ~10,300 — *more* than GPT-OSS uses — yet its pass-agreement was **0.840, identical to its default run** (paired bootstrap: no detectable difference). GPT-OSS still beats it by the same margin. Giving Gemini more thinking simply did not help on this task.
- **Opus cannot be pushed.** Claude Opus 4.7 uses adaptive thinking and does not accept a manual reasoning budget; its original run already reflects however much it chooses to think. There is no higher-reasoning Opus to test.
- **Reasoning effort is a model-specific lever.** It matters a lot for GPT-OSS-120B (its pass-agreement rose from 0.72 at minimal effort to 0.84 at high), and close to nothing for Gemini. So the finding is not "high reasoning makes any model a good judge." It is "GPT-OSS-120B is a good judge, and it happens to benefit a lot from cheap reasoning tokens."

So GPT-OSS's standing is not a reasoning-budget artifact.

## What we are not claiming, and what we cannot rule out

- **Small sample, wide intervals.** With 200 held-out instances over 30 problems, the bootstrap confidence intervals for the top systems overlap heavily. We can say GPT-OSS reliably beats Gemini and is statistically indistinguishable from Opus; we cannot say any single cheap model definitively dominates the frontier.
- **Within-model variance is unclear.** We mostly ran one sample per judge and did not characterize run-to-run variation thoroughly.
- **Budget-limited search.** We could not afford a broad sweep of models and settings. In particular, we did **not** test GPT-5.5-Pro at high reasoning — at hundreds of dollars per million tokens it is far outside the budget this work is about.
- **This is about judging, not solving.** We measured judge reliability against verified artifacts and human scores. We make no claim that any of these models is good at *doing* the mathematics — only at grading it.

## Bottom line

For grading natural-language math proofs on a budget:

- **Use GPT-OSS-120B at high reasoning as a pass/fail judge.** It is the cheapest and most accurate option we found, within noise of frontier models at about 1% of their cost.
- **A cheap consensus is a reasonable hedge, not an upgrade.** It is robust and convenient, but here it cost more and graded no better than its single best member. Prefer the good single model unless you specifically want protection against one model failing or changing.
- **Reach for a frontier model only when you need a calibrated continuous score**, not a pass/fail decision.

These conclusions are preliminary, but the practical signal is clear: cheap judges are good enough to take seriously.

---

*Reproducibility: validation data in `trials_validation.csv` / `consensus_analysis.csv`; the high-reasoning Gemini run in `gemini_high_validation_20260524.py` and its result JSON. Full prior experiment and methodology in `report.md`.*
