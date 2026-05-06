# Paper sketch — "The Judge Is the Experiment"

A 2-page, accessible sketch. Not a draft; just the outline of what the paper *could*
look like. Plain language, no jargon-heavy framing.

## Title

**The Judge Is the Experiment: Why Agentic Math Pipelines Need Calibrated Multi-Judge
Evaluation**

(Working title. The point: in 2026, evaluating agentic math solvers without a
calibrated judge isn't measuring the pipeline — it's measuring the judge.)

## One-sentence summary

When you grade the same 2,848 LLM math solutions with three different LLM judges,
the headline finding ("does the pipeline help?") flips for almost every architecture
choice — and we show how to fix this with a cheap, diverse-bias judge ensemble that
matches a frontier judge at a fraction of the cost.

## Why now

LLM-as-a-judge is the default evaluation tool for agentic math systems, but virtually
all current papers report a single judge. We collected three judges' scores on the
same 2,848 problem×model×pipeline trials — and the answers diverge enough to flip
qualitative conclusions about which pipeline architectures are worth using.

## What we did

1. **Built a unified benchmark.** 70 problems (60 IMO ProofBench + 10 frontier
   "special" problems), 6 generator models, 4 pipeline modes (single-shot,
   verify/revise loop, idea-conditioned generation, idea-conditioned verify/revise),
   and several role-swap and best-of-N variants. Total: ~2,800 trials, ~8,200 branches.
2. **Judged every trial with three different LLMs.**
   - deepseek-v4-pro (strict, high-reasoning)
   - deepseek-v4-flash (cheaper, also-strict)
   - gemini-3-flash (lenient, fast)
   And calibrated all three against 200 human-scored solutions ("gradingbench").
3. **Looked for cases where the judges disagree about whether the pipeline helps.**

## What we found (in plain words)

**Finding 1. The judges disagree, a lot, in ways that flip headline claims.**
On the 1,458 trials where all three judges scored, deepseek-v4-pro and gemini-3-flash
disagree about pass/fail 27% of the time, with gemini systematically scoring 1.75
points higher on a 7-point scale. Deepseek-v4-flash, by contrast, agrees with v4-pro
84% exactly and disagrees on pass/fail just 5% of the time. Against human scores,
gemini's correlation is only 0.51; v4-pro is 0.79 and v4-flash is 0.76.

The size of this disagreement is enough to swing what conclusion you'd draw from any
given experiment. In our data, the "best mode" per generator model picks a different
mode under v4-pro vs gemini for 4 of 6 models. A whole earlier round of "first-ever
frontier solves" by cheap models on Erdős problems collapsed to zero under v4-pro
re-grade.

**Finding 2. Reasoning matters more than the pipeline.** Turning reasoning ON for
gpt-oss-120b and gemma-4-31b-it raises strict-judge scores by +0.8 to +1.6 points
across every pipeline mode. By contrast, switching among pipeline modes — single-shot,
verify/revise, idea-conditioned, etc. — moves scores by no more than ±0.4 within the
same reasoning state. **Reasoning effort, not pipeline architecture, is doing most of
the work.**

This applies to judges too. A non-reasoning judge (gemma at default) correlates at
r=0.63 with humans. The same model with reasoning ON jumps to r=0.78. Reasoning state
explains more judge-quality variance than model family.

**Finding 3. Pipelines rarely beat best-of-N sampling.** Across all 6 generator models,
simple pass@3 best-of-3 sampling outperforms verify/revise pipelines for 5 of 6 models
under strict judging. The verify/revise loop only earns its keep when the base
generator is strong enough to critique itself — in our set, only deepseek-v4-pro.
For weaker models, the verifier wrongly approves broken solutions 60–70% of the time,
so iteration adds noise.

But there is a clean pattern: **mixing a cheap generator with a strong critic** (e.g.
v4-flash producing solutions, v4-pro running verify/revise) gives clear gains —
+1.05 points and rescues 3/20 hard problems from 0/7 to 7/7. Symmetric pipelines
within a single weak model don't help; asymmetric ones do.

**Finding 4. A cheap multi-judge ensemble matches a frontier judge.** We assembled
three cheap judges with biases that cancel each other (one scores high, one scores
low, one is neutral). Their averaged score correlates with humans at r=0.86 — within
2 points of gemini-3.1-pro's r=0.88, at 27% of the cost. A tiered system (cheap-trio
auto-decides; v4-pro audits the 21% of cases where they disagree) reaches 89.8%
agreement with humans at $0.013 per decision, four times cheaper than the four-judge
"gold standard" alternative.

**Finding 5. The verifier role is the only fragile slot.** When we swapped models
across roles in the pipeline (ideator, generator, verifier, reviser), 7 of 8
combinations were within ±0.1 of the same-model baseline. The exception:
**replacing gpt-oss's verifier with gemma's verifier costs 0.55 points.** The
verifier is where role-swap experiments should focus; everything else is noise at
this benchmark scale.

## The core methodological claim

Any paper claiming "agentic pipeline X improves math solving by Y" without showing
results from at least two judges of differing biases — calibrated against humans —
should be assumed to be measuring the judge, not the pipeline. The artifact is
strong enough that we recommend the field treat single-judge agentic benchmarks the
way the ML community treats single-seed numbers: reportable but not load-bearing.

## What we ship

1. **A 2,848-trial three-judge dataset** (`dataset_20260505.jsonl`, 567 MB), with
   per-judge scores, per-judge verdict text, per-branch breakdowns, and full
   problem/ground-truth/solution text for downstream use.
2. **A 200-record human-vs-judge calibration set** (`gradingbench`), with seven
   different judge configurations evaluated against human scores.
3. **The cheap-ensemble recipe**: which three judges to use and how to combine them
   to substitute for a frontier judge at ~3.7× lower cost.
4. **Ablation results** for reasoning effort, pipeline mode, role swap, and best-of-N
   scaling — all under multi-judge evaluation.

## What we are *not* claiming

- We are not claiming any single pipeline is "the right" architecture. The reverse:
  pipeline differences are smaller than judge differences.
- We are not claiming our three judges are unbiased. They are differently biased,
  which is exactly what makes the ensemble work.
- We are not claiming the cheap ensemble beats frontier judges; it matches them on
  pass/fail decisions and slightly trails on continuous correlation. The win is
  cost.

## Limits & honest caveats

- **70-problem benchmark.** Strong enough to detect ±0.4 point effects but not 0.1.
  Several "is it really zero?" claims rest on small samples (n=20 in the
  flex-budget sweep, etc.).
- **Cheap-ensemble result depends on the n=200 human calibration set.** A larger
  human-scored set would tighten the recipe.
- **Reasoning ablation was within v4-flash judge.** Re-judging with v4-pro would
  cost ~$10 and improve strictness; the qualitative result is robust to that.
- **No direct mechanistic claim** about why gemini is lenient on revised solutions
  ("polish vs rigor"). It's a plausible explanation, not a tested one.

## Why this is a NeurIPS-shaped paper

- The dataset is a substantial, releasable artifact with a clear schema.
- The core finding (judge-flip rates of 27% in agentic eval) is surprising enough to
  matter to a wide audience — anyone using LLM-as-a-judge.
- The fix (cheap diverse-bias ensemble) is practical and reproducible.
- The methodology generalizes outside math: the same three-judge calibration recipe
  applies to any task where evaluation is itself an LLM call.


