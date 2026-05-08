# Focused Pre-Submission Peer Review

**Manuscript:** *Comparing Inference-Time Methods for Natural-Language Mathematical Proofs*  
**Draft:** v4  
**Review type:** Author-facing pre-submission review, optimized for limited revision time  
**Overall recommendation:** **Weak Reject / Borderline for main-conference submission as written; promising workshop submission or main-track resubmission after targeted cleanup**  
**Reviewer confidence:** **3/5**  

## Executive Summary

This is a timely and useful empirical paper. Its strongest contribution is methodological: it argues that generator-verifier-revisor and seeded-agentic proof pipelines should be compared against token- or call-matched pass@k baselines, not pass@1. The main negative result — that the verifier-revisor pipeline does not beat pass@3 under strict judging — is important and likely worth publishing. The judge-sensitivity result is also valuable: the paper shows that a lenient judge can reverse conclusions for cheap models, while the two strict judges mostly agree.

The paper is not currently held back by formatting or prose polish. It is held back by a few evidentiary risks: statistical dependence across repeated trials on the same small problem set, incomplete `seed_full` coverage, automated-judge-only “frontier solve” claims, and insufficiently explicit cost/token accounting. Because there is likely no time for serious new API work, the best path is not to add experiments. The best path is to tighten the claims, relabel risky claims, add caveats exactly where needed, and make the paper visibly honest about what is definitive versus suggestive.

## Recommendation

**Recommendation: Weak Reject for a top-tier main conference in current form; Borderline/Weak Accept for a focused workshop.**

The core idea is strong enough to be taken seriously, but the current draft sometimes presents narrow or judge-dependent findings too strongly. In particular, “strict solves” of frontier problems should be reframed as “strict-judge passes” or “candidate solves requiring expert review.” The paper should foreground the robust conclusion — pipeline depth does not beat matched sampling in this budget/model regime — and downweight the more fragile frontier-solve and `seed_full` positive claims.

## What the Paper Gets Right

1. **The central comparison is the right one.**  
   The pass@1 baseline is unfair for multi-call pipelines. Comparing `full` to pass@3 and `seed_full` to pass@9 is the paper’s core methodological contribution.

2. **The null result is useful.**  
   The finding that `full − generate` is effectively null is valuable because many agentic-math papers implicitly treat verifier-revisor scaffolding as an obvious improvement.

3. **The judge-sensitivity analysis is one of the strongest sections.**  
   The contrast between strict judges and Gemini-3-flash-preview is concrete, well motivated, and practically important.

4. **The limitations section is unusually candid.**  
   The draft discloses budget constraints, incomplete `seed_full` coverage, contamination risk, automated-judge limitations, and the malformed seeded-ideator issue. This candor should be preserved.

5. **The paper has a clear practical message.**  
   “Sample more before adding pipeline depth; keep reasoning enabled when available; audit with multiple judges” is a useful recommendation.

## Main Concerns

### 1. “Solves” language is too strong

The paper repeatedly refers to “strict solves” of research problems. Given that these are automated-judge passes, often single-cell passes, this wording is too strong. The draft itself correctly says that single strict-judge passes on research-medium-or-harder problems should be treated as candidates for expert review, not confirmed mathematics. The abstract and result headings should match that caution.

**Fast fix:** replace most instances of:

- “strict solves” → “strict-judge passes”
- “solves of Erdős-1051 / FirstProof-6” → “candidate passes on Erdős-1051 / FirstProof-6 under the v4-flash judge”
- “frontier solves audit” → “frontier candidate-pass audit”

Keep the word “solve” only when clearly qualified, e.g. “candidate solve requiring expert review.”

### 2. The statistical unit is unclear

The paper reports hundreds or thousands of trials, but many are repeated evaluations on the same 70 problems, and the R26 tiers contain very few unique problems. For example, some difficulty tiers have only 1–4 problems. Trial-level confidence intervals can therefore look much more precise than the actual problem-level evidence.

This does not necessarily invalidate the main result, but it changes the interpretation. The paper should avoid implying that trial-level CIs generalize cleanly to the whole class of research-hard or frontier problems.

**Fast fix, no new API calls:** add a paragraph in Section 3.4 or Limitations:

> Our bootstrap and permutation tests treat observed paired cells as the empirical population. Because many cells reuse the same problems, these intervals should be read as uncertainty over the observed benchmark grid rather than as problem-population confidence intervals. This matters most for R26 tiers, where the number of unique problems per tier is small. We therefore treat difficulty-tier and frontier-pass analyses as descriptive rather than definitive.

If there is time for a code-only reanalysis from existing results, add problem-clustered bootstrap CIs for the two or three headline contrasts. If not, disclose the limitation clearly.

### 3. `seed_full` coverage is incomplete and non-representative

The positive `seed_full − generate` result is interesting but fragile. The paper says `seed_full` was not run across the full six-model grid and remains untested on several base models. This makes pooled `seed_full` statements vulnerable to selection/coverage bias.

**Fast fix:** in the abstract and main results, qualify the result:

> In the partially covered `seed_full` grid, the apparent lift is concentrated in the reasoning=max cheap-model cells; at the proper pass@9 baseline, the lift largely collapses.

Also add a visual marker or footnote to every table containing `seed_full` that says coverage is partial and non-representative.

### 4. Cost fairness is argued with call counts, not actual token/cost accounting

The paper’s central claim is budget fairness, but most architecture comparisons are described as “~3 calls” or “~9 calls.” This is probably directionally right, but call count is not the same as token count, dollar cost, or latency. Verifier and revisor calls may be shorter or longer than generation calls.

**Fast fix, no new API calls:** if token/cost logs already exist, add a small table with mean/median cost per architecture. If not, soften “token-equivalent” to “call-equivalent” in the places where actual token accounting is absent.

Recommended language:

> We use call count as a practical proxy for inference budget. Because generation, verification, revision, and ideation calls can differ in token length, these comparisons are best read as call-matched rather than perfectly token-matched unless otherwise stated.

### 5. The malformed seeded-ideator fallback issue needs clearer handling

Section 7 discloses that 10–28% of original Phase 1 seeded ideation calls returned malformed outputs and silently fell back to pass@3. This is a serious data-quality issue. The draft argues this likely understates seeded effects, which may be true, but readers will want to know exactly which results are affected.

**Fast fix:** add a small note near the first seeded-result table:

> Seeded-generation results from original Phase 1 include fallback contamination from malformed ideator outputs; patched downstream `seed_full` results are unaffected. We therefore interpret `seed_generate` estimates conservatively and do not use them as the primary evidence for or against seeded ideation.

If possible from existing logs, include fallback rates by model/mode in the appendix.

## No-Time Revision Plan

If submission is imminent, prioritize these edits in order.

### Must do before submission

1. **Rename “strict solves” to “strict-judge passes” throughout.**  
   This is the highest-value, lowest-effort credibility fix.

2. **Add one explicit statistical-dependence caveat.**  
   Make clear that the CIs are over the observed grid, not over an independent population of math problems.

3. **Qualify `seed_full` as partial coverage.**  
   Put the caveat in the abstract, Section 5.1, Section 5.4, and table captions.

4. **Change “token-equivalent” to “call-equivalent” unless actual token accounting is shown.**  
   If actual token/cost logs exist, add a compact table. Otherwise, avoid overclaiming.

5. **Tighten the abstract.**  
   The abstract currently tries to report too many numbers. Emphasize the robust claims and move fragile details to the body.

### Should do if it only requires existing data/scripts

6. Add problem-clustered bootstrap CIs for the headline `full − generate` result.  
7. Add a cost-per-architecture table from existing logs.  
8. Add fallback rates for seeded ideation.  
9. Add a small “primary vs exploratory contrasts” note.  
10. Add a table footnote distinguishing full-grid results from partial-grid results.

### Defer; likely not possible before submission

These would strengthen the paper but should not be attempted if time is short or API calls are constrained:

- v4-pro audit of reasoning=max `seed_full` cells.
- Multi-seed reruns of the positive `seed_full` cells.
- Full Phase-1 `seed_full` extension to missing base models.
- Frontier-model comparison sweep.
- Large manual expert grading study.

Instead of doing these now, list them honestly as future work.

## Suggested Abstract Rewrite

> Recent work on mathematical proof generation often reports gains from inference-time scaffolding such as generator-verifier-revisor loops and seeded multi-trajectory pipelines. We ask how much of this gain survives comparison to simple sampling at matched inference budget. On a 70-problem benchmark combining IMO-ProofBench with ten 2026 research-tier problems, we evaluate six cost-feasible base models, several inference architectures, and three automated judges under an approximately $1,000 budget. The main result is negative: the generator-verifier-revisor pipeline does not outperform pass@3 under either strict judge, and in one reasoning=max Gemma setting it hurts performance. Seeded ideator-plus-pipeline runs show a positive effect only in partially covered reasoning=max cheap-model cells, and the effect largely disappears when compared to the appropriate pass@9 baseline. Judge choice is a major source of apparent architecture lift: the two strict judges agree on 95.5% of pass/fail decisions, while the lenient Gemini judge calls pass on roughly 37% of strict-judge failures. Difficulty-stratified results show sharp degradation from ProofBench Basic to research-tier problems, and research-medium-or-harder candidate passes remain rare and require expert verification. Within the budget and model regime tested, the practical recommendation is simple: sample more before adding pipeline depth, enable reasoning when available, and audit conclusions with more than one judge.

## Suggested Framing Changes

### Current framing to avoid

- “DeepSeek-v4-flash at pass@7 produces the only strict solves...”
- “Pooling all trials yields 32 strict-judge R26 solves...”
- “token-equivalent to pass@3” without token/cost table
- “architecture lift is uniformly null on hard tiers” without noting tiny number of unique problems

### Safer framing

- “DeepSeek-v4-flash at pass@7 produces the only strict-judge candidate passes...”
- “Pooling all trials yields 32 strict-judge R26 candidate passes...”
- “approximately call-matched to pass@3”
- “within the observed hard-tier cells, we find no evidence of architecture lift; because the number of unique R26 problems is small, this should be read descriptively.”

## Section-by-Section Notes

### Abstract

Strong but too packed. It should stop trying to carry every quantitative result. The main message should be: matched sampling beats or matches pipelines; judge choice matters; frontier candidate passes are rare and fragile; budget constraints shape the result.

### Introduction

The motivation is strong. The paper should emphasize that it is an evaluation/methodology paper, not a new method paper. The “capability arc” is useful context, but do not let it imply that this experiment evaluates systems comparable to AlphaProof, Aletheia, Aristotle, or frontier proprietary math agents.

### Methodology

The architecture descriptions are clear. The main change is terminology: use “call-equivalent” unless actual tokens are reported. Also explain the unit of statistical inference more carefully.

### Calibration

This is one of the better sections. The judge-cost tradeoff is convincing. Add one sentence reminding readers that 87.4% pass-agreement is enough for aggregate evaluation but not enough to certify individual research-level proofs.

### Main Results

The `full − generate` result is the centerpiece. Put it first and keep it clean. Treat `seed_full` as secondary and partially covered. Avoid presenting the frontier-pass table as a solve table.

### Secondary Results

The reasoning-effect section is useful but should remain framed as confirmation. The pass@k scaling result is important and supports the main thesis. The role-swap result is likely secondary and can be shortened if space is tight.

### Limitations

This section is strong. Add the statistical-dependence caveat and make the “no expert verification” point even clearer. The limitations should not sound apologetic; they should make the paper more trustworthy.

### Discussion

The practical recommendations are good. Keep them concrete and avoid overstating generality beyond the tested models, judges, and budget regime.

## Final Verdict

This paper has a publishable core. The central null result is useful, the judge-sensitivity analysis is important, and the budget-aware framing is refreshing. The fastest route to a stronger submission is not more API calls. It is claim discipline.

The authors should make the paper narrower, more careful, and more obviously robust:

- call the main contribution a cost-matched evaluation;
- call frontier results candidate passes, not solves;
- disclose that trial-level uncertainty is not problem-population uncertainty;
- mark `seed_full` as partially covered;
- avoid saying token-matched when only call-matched evidence is shown.

With those changes, the paper becomes much easier to defend. Without them, reviewers are likely to focus on overclaiming and statistical fragility rather than the genuinely valuable methodological message.
