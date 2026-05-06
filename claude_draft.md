# The Judge Is the Experiment: Calibrated Multi-Judge Evaluation for Agentic Math Solvers

*Draft, 2026-05-05*

## Abstract

Agentic math solvers — generator, verifier, reviser, idea proposer — are typically
evaluated with a single LLM judge. We collect three independent LLM judges' scores
on 2,848 trials drawn from a 70-problem benchmark (60 IMO ProofBench + 10 frontier
"special" problems), spanning six generator models, four pipeline modes, role-swap
ablations, and best-of-N curves. We find that the *judge*, not the *pipeline*, drives
most of the headline variance: a strict judge and a lenient judge disagree on
pass/fail 27% of the time, and the choice of judge flips the qualitative ranking of
pipeline modes for four of six generator models. Reasoning effort, both in the
generator and in the judge, dominates pipeline architecture as a lever. Finally, a
three-judge ensemble of cheap, oppositely-biased models matches a frontier judge on
human-calibrated accuracy at roughly a quarter of the cost. We release the dataset,
the human-calibration set, and the ensemble recipe.

## 1. Why this paper

LLM-as-a-judge is the default evaluator for agentic math systems. Most published
results report a single judge and a single score. Our central empirical claim is that
this practice is unreliable enough to flip the qualitative direction of pipeline
comparisons. We argue the field should treat single-judge evaluations the way it
treats single-seed benchmarks: reportable, but not load-bearing.

## 2. What we did

**Benchmark.** 70 problems: 60 from IMO ProofBench (basic, advanced, and
beyond-IMO difficulty) and 10 "special" problems drawn from open Erdős conjectures
and `first-proof` competition material. Each solution is graded on the standard
0–7 IMO rubric.

**Generators.** Six models: deepseek-v4-pro, deepseek-v4-flash, qwen3.6-35b-a3b,
gemini-3-flash-preview, gemma-4-31b-it, gpt-oss-120b. Reasoning configurations were
ablated separately for the two cheap models (gpt-oss, gemma).

**Pipeline modes.** Four modes:
1. *generate* (single-shot, with pass@N best-of-N where applicable).
2. *full* (verify ↔ revise loop, up to 2 iterations).
3. *seed_generate* (model proposes 3 ideas, generates one solution per idea).
4. *seed_full* (3 ideas × full verify/revise loop per branch).

**Role swap.** A separate 8-condition matrix (gpt-oss × gemma) where each role
(ideator, generator, verifier, reviser) is independently swapped between the two
models, plus two random-mix baselines.

**Judges.** Every trial was scored by up to three judges:
- **deepseek-v4-pro** (strict, expensive).
- **deepseek-v4-flash** (cheaper, also strict — was added later as a third opinion).
- **gemini-3-flash-preview** (fast, lenient).

We additionally ran 200 problems through seven judge configurations (varying model
and reasoning effort) and compared each to **human-graded "Points"** in
`gradingbench`, giving a per-judge correlation with human ground truth.

**Dataset.** 2,848 trials, 8,276 branches, ~567 MB of long-format JSONL. Released
alongside the paper.

## 3. Result 1: The judge flips the headline

**Triple-judge agreement.** On 1,458 trials all three judges scored:

|                          | v4-pro vs gemini | v4-pro vs v4-flash | gemini vs v4-flash |
|---|---|---|---|
| Exact match              | 60% | **84%** | 63% |
| Pass-flip (≥6 vs <6)     | 27% | **5%**  | 26% |
| Mean Δ (col − row)       | +1.75 | **+0.07** | -1.68 |

Two of the three judges agree closely; the third (gemini-3-flash) is systematically
~1.75 points more lenient on a 7-point scale. Importantly, on the 402 cells where
v4-pro and gemini disagree about pass/fail, **v4-flash sides with v4-pro 90% of the
time** — gemini is the outlier, not the consensus.

**Against humans.** On 200 human-graded solutions (`gradingbench`), Pearson
correlations with human Points are: gemini-3-flash r=0.51, v4-flash r=0.76,
v4-pro r=0.79. Gemini's mean offset against human ground truth is +1.65, with 47%
precision at the ≥6 threshold.

**Headline-flipping examples.**
- For gemma-4-31b-it, v4-pro picks `generate` as the best mode; gemini picks `full`.
- For gpt-oss-120b, all three judges pick `full`, but gemini scores it 3.10 and
  v4-pro scores it 1.39.
- An earlier result of ours, judged only by gemini, claimed cheap models had
  produced "first-ever" 7/7 solutions on three open Erdős problems. Under v4-pro
  re-grade, all of those collapsed to 0/7. The "frontier breakthrough" was
  judge leniency.

**Implication.** Single-judge agentic-pipeline papers are likely to be reporting
judge-specific artifacts rather than pipeline behavior.

## 4. Result 2: Reasoning is the dominant axis

We re-ran Phase 1 for the two cheap models (gpt-oss, gemma) with reasoning ON,
keeping the v4-flash judge fixed for apples-to-apples comparison.

| Mode | gpt-oss (no-R → R) | Δ | gemma (no-R → R) | Δ |
|---|---|---|---|---|
| generate      | 1.34 → 2.30 | +0.96 | 1.49 → 2.74 | +1.25 |
| full          | 1.58 → 2.43 | +0.85 | 1.39 → 2.17 | +0.79 |
| seed_generate | 1.09 → 2.54 | +1.45 | 1.49 → 2.74 | +1.26 |
| seed_full     | 1.41 → 3.00 | +1.59 | 1.71 → 3.31 | +1.60 |

Reasoning roughly **doubles** strict-judge scores in every mode. By contrast, moving
between pipeline modes within a fixed reasoning state moves scores by ≤±0.4.

**Reasoning helps judges too.** On gradingbench, gemma-4-31b-it default → reasoning=high
shifts r from 0.63 to 0.78 (the highest correlation any single judge achieves).
gpt-oss-120b minimal → xhigh: r 0.51 → 0.77. v4-flash with reasoning forcibly off
falls from r=0.76 to 0.59 with recall collapsing 79% → 57%.

The data show two clean clusters: reasoning-on judges (r ≈ 0.71–0.78), and
non-reasoning judges (r ≈ 0.51–0.63). Lineage modulates the bias direction
(deflation for DS family, inflation for gemini/gemma) but the reasoning state
determines whether you are in the "useful" cluster at all.

**Methodological consequence.** Comparing pipeline modes without first locking
reasoning effort gives mostly noise. Reports of "+0.5 from architecture X" can be
matched or exceeded by a reasoning-effort flip on the same model.

## 5. Result 3: Best-of-N beats verify/revise

Best-of-N sampling (run N times, judge each, take the best) is the strongest cheap
baseline in our data. Under strict judging, pass@3 wins for 5 of 6 generators.
Verify/revise (`full`) wins only for deepseek-v4-pro, the single strongest base
model. Average uplifts vs single-shot pass@1 (gemini-judged, with strict-judge
ranking qualitatively the same): pass@3 +1.04, seed_generate +0.71, full +0.37.

**Why verify/revise underperforms for cheap models.** The verifier is the weakest
link: weak-model verifiers early-stop "VERDICT: correct" on broken proofs 60–68% of
the time (verifier false-positive rate, conditional on early-stop). The reviser then
can't fix what the verifier didn't flag.

**One asymmetric architecture works.** Pairing a cheap generator (v4-flash) with a
strong critic (v4-pro running verify/revise) gives **+1.05 over flash-solo** on a
20-problem PB-Advanced subset, and rescues 3 problems from 0/7 to 7/7. Symmetric
weak-model pipelines do not.

**Saturation.** Best-of-N saturates by N=5–7 for both cheap models with reasoning
ON: gpt-oss 1.40 → 1.40 → 1.73 at N=3,5,7; gemma 0.87 → 1.93 → 1.97. v4-flash hits
64% pass rate on 70 problems at N=7.

## 6. Result 4: Role swap is mostly noise; the verifier is the fragile slot

Cross-model role swap is appealing in theory but does not deliver at the cheap tier.
Of 8 swap conditions × 70 problems, **5 land within ±0.1** of the same-model
baseline. The worst swap is replacing gpt-oss's verifier with gemma's, which costs
−0.55 points; the reverse direction is fine. Best swap (+0.05) is below noise: two
random-mix runs differ by 0.41 points, putting the noise floor at ≈ ±0.4 at n=70.

**Implication.** Authors proposing role-swap pipelines should ablate the verifier
specifically — the rest of the architecture is largely interchangeable.

## 7. Result 5: A cheap diverse-bias judge ensemble matches a frontier judge

Combining cheap, oppositely-biased judges cancels their systematic offsets and
matches the accuracy of a single expensive frontier judge.

| System | r | F1 | ≥6-agree | $/decision |
|---|---|---|---|---|
| gemini-3.1-pro (frontier) | 0.881 | 84 | 88.4% | $0.033 |
| 4-judge ensemble (v4-pro + oss-xhigh + nano-xhigh + gemma-high), majority | 0.863 | 84 | **91.3%** | $0.057 |
| Cheap trio (gemma-high + oss-xhigh + v4-flash), mean | 0.862 | 84 | 90.1% | **$0.009** |
| Tiered: trio auto-decides; v4-pro audits 21% disagreements | — | — | 89.8% | **$0.013** |

The active ingredient is bias diversity: gemma-high inflates (+0.55), gpt-oss-xhigh
mildly inflates (+0.21), v4-flash deflates (−0.80). Their sum is near zero. With a
shared bias direction the ensemble wouldn't help.

The tiered system — let the cheap trio decide alone when its members agree, escalate
to v4-pro on the 21% of cases where they disagree — reaches 89.8% agreement with
human pass/fail decisions at $0.013 per decision, **3.7× cheaper** than running
gemini-3.1-pro and **4.4× cheaper** than the four-judge gold standard.

## 8. Discussion

**The methodological recommendation.** Any paper claiming "agentic pipeline X
improves math solving by Y" should report results from at least two judges of
different bias directions, calibrated against humans. We treat this as analogous to
reporting mean ± std over multiple seeds: a baseline of basic statistical hygiene,
not a research contribution.

**Why this matters beyond math.** The same effect plausibly governs LLM-as-judge
evaluations in code, agent benchmarks, RAG quality grading, and reasoning chains —
anywhere a single LLM call ends up encoding the binary pass/fail decision for
downstream comparison. Our specific judge-ensemble recipe is math-specific, but the
methodological frame transfers.

**Why agentic pipelines disappoint relative to the lit.** Many published gains for
verify/revise loops, idea-conditioned generation, and role-swap pipelines were
reported under judges (often gemini family, often without reasoning) that
systematically reward "polished prose that pattern-matches a proof." Once the judge
demands actual rigor, most of the gain disappears. The exceptions are (a)
strong-base-model verify/revise (only v4-pro in our set), and (b) asymmetric
pipelines with a strong critic. Best-of-N sampling is competitive almost
everywhere else.

## 9. What we ship

1. **`dataset_20260505.jsonl`** — 2,848 trials, 8,276 branches, three independent
   judges per cell where available, full problem text, ground truth, solution text,
   and verdict text. Schema and loading recipes are documented.
2. **gradingbench-200** — 200 human-graded solutions with seven judge configurations
   (varying model and reasoning state) for direct comparison against human Points.
3. **The cheap-ensemble recipe** — three judges (gemma-4-31b-it @ reasoning=high,
   gpt-oss-120b @ effort=xhigh, deepseek-v4-flash with reasoning ON) plus the
   tiered escalation rule.
4. **Per-experiment scripts** — Phase 1 / Phase 2 / Phase 3 generators, role swap,
   best-of-N scaling, judge-vs-human calibration. All deterministic given seeds.

## 10. Limits

- 70-problem benchmark detects ±0.4-point effects but not 0.1.
- Cheap-ensemble result rests on the n=200 human-calibration set. A larger human
  sample would tighten the recipe.
- The reasoning-doubles-score result was measured under v4-flash judge (a strict
  judge) on both arms. A v4-pro re-grade would harden the comparison; the effect is
  too large to be entirely judge bias.
- Asymmetric "strong critic on cheap generator" was n=20; needs replication.
- We do not test whether judges with different *prompts* (rather than different
  *models*) cluster the same way — the prompt was held fixed at our hardened
  `judge_gt.md`.

## 11. Conclusion

The cheapest, most general improvement to agentic math evaluation is to replace the
single LLM judge with a small calibrated ensemble. Beyond that, two simple priors
beat most architecture work in our data: **set reasoning to high before changing
anything else, and prefer best-of-N sampling unless your generator is strong enough
to critique itself.** We release the dataset, the calibration set, and the ensemble
recipe so that future agentic-pipeline papers can be evaluated on whether they
improve solver behavior, not on whether they pick a friendlier judge.
