# Plain paper sketch

## Working title

`More Attempts or Better Critique? Test-Time Compute for Math Proof Agents`

## Short summary

This paper studies a simple question: when we give language models extra test-time compute on hard math problems, what kind of extra compute actually helps?

We compare a few common choices:

- one-shot generation
- best-of-k sampling
- a generate then verify/revise pipeline
- a seed-ideas pipeline with multiple branches
- a few cross-model variants where a different model acts as critic

The main result is simple. For stronger models, plain resampling is usually the hardest baseline to beat. For weaker models, iterative critique can help, but mostly when the critic is stronger than the generator or when reasoning is explicitly enabled. Naive model mixing usually does not help.

There is a second result that is just as important. The answer changes a lot depending on the judge. A lenient judge rewards polished-looking proofs and can make a pipeline look much better than it really is. A stricter judge is closer to human grading and often removes many of the apparent gains. Because of this, judge calibration is part of the main experimental design, not a side issue.

## Motivation

Recent work on agentic reasoning often reports gains from multi-step pipelines such as critique, revision, branching, or tool use. But these claims are hard to compare because three things are often mixed together:

1. extra attempts
2. extra critique
3. different evaluation judges

In math proof generation, this matters a lot. A model may produce something that looks organized and plausible but still miss a key gap. A lenient judge may score that highly, while a stricter judge may not.

So the paper asks three questions:

1. Is iterative self-refinement better than simple best-of-k sampling?
2. When does a stronger critic help?
3. How much do the conclusions depend on the judge?

## Setup

The main benchmark is a 70-problem proof set built from ProofBench-style IMO problems plus a small set of harder "special" problems. The main models span a cheap-to-strong range. The main pipeline modes are:

- `pass@1`: one sample
- `pass@k`: k independent samples, pick the best judged solution
- `full`: generate, then verify and revise for a few rounds
- `seed_full`: generate multiple idea-conditioned branches, each with its own verify/revise loop

The paper also includes two supporting evaluations:

- an answer-only math benchmark, which measures whether the model can get the final answer without requiring a proof
- a grading benchmark with human labels, used to calibrate judges

The answer-only benchmark is useful because it separates answer finding from proof writing. The grading benchmark is useful because it tells us which judges are closest to humans.

## Main findings

### 1. Best-of-k is the main baseline

The biggest lesson from the main pipeline experiment is that simple sampling is very strong. Once true best-of-k is measured correctly, it often matches or beats more elaborate self-refinement pipelines, especially for stronger models.

This does not mean critique is useless. It means that many apparent pipeline gains are really sampling gains. If a pipeline is compared only to pass@1, it may look impressive. If it is compared to a cost-matched pass@k baseline, the result is often much less dramatic.

This is the cleanest headline in the paper: more attempts often beat more reflection.

### 2. Strong critics help more than naive self-critique

The negative result above is not the whole story. Some asymmetric setups do help. In particular, a stronger critic can improve a weaker generator more than the generator can improve itself.

This suggests a more precise view of agentic math pipelines:

- self-refinement is weak when generator and critic have similar blind spots
- cross-model diversity is not enough on its own
- a real capability gap in the critic can matter

So the useful comparison is not "pipeline or no pipeline." It is "what kind of extra compute is being added, and where?"

### 3. Judge choice can reverse the conclusion

One of the strongest empirical patterns in the May runs is that some judges are much more lenient than others. A lenient judge tends to reward polished proof attempts, especially after revision. A stricter judge tends to focus on whether the proof is actually complete.

This can change the ranking of methods. Under one judge, a full pipeline can look like the best method. Under another, plain pass@k can clearly win. This is not just noise. It is a real measurement issue.

The paper should therefore treat judge calibration as part of the core contribution.

### 4. Reasoning is a hidden variable in many model comparisons

A separate but related result is that many models change a lot when reasoning is explicitly enabled. Some models that looked weak at default settings became competitive once reasoning effort was raised. The same was true for judges.

This means that "model A vs model B" is often partly "configuration A vs configuration B." A careful paper should set reasoning budgets explicitly and report them clearly.

## Judge section

The judge section can stand on its own. On a human-graded benchmark, stricter reasoning-based judges line up much better with people than lenient non-reasoning judges. A cheap strict judge also gets close to a more expensive one, and a small ensemble can be even better on pass/fail decisions.

This matters for the main paper because it changes what counts as a success. Some frontier-style solves disappear under stricter regrading. So the paper should avoid overselling single-judge results, especially on special hard problems.

## Practical message

The paper should end with a practical message for people building math agents:

- always report a pass@k baseline
- do not trust a single lenient judge
- use stronger critics when you can, not just different critics
- treat reasoning budget as part of the method

That is a useful contribution even if the strongest result is partly negative. It gives a cleaner recipe for future work.

## What the paper should not claim

The paper should not claim that branching or seed ideas are always better than sampling. It should not claim that cross-model diversity helps in general. It should not headline frontier solves that survive only under lenient judging.

The strongest version of the paper is careful and narrow: extra test-time compute helps, but the useful form of compute depends on model strength, critic strength, reasoning setting, and judge calibration.

## Simple paper outline

1. Introduction
   Ask whether agentic refinement really beats simple resampling on hard math proofs.

2. Experimental setup
   Describe the 70-problem proof benchmark, the answer-only benchmark, the human-grading benchmark, the four main pipeline modes, and the judge set.

3. Main architecture results
   Show pass@1, pass@k, full, and seed_full by model family and cost.

4. Judge calibration
   Show judge-vs-human results and explain how judge choice changes the architecture ranking.

5. Cross-model and reasoning ablations
   Show that naive role swaps mostly do not help, while stronger critics and explicit reasoning do.

6. Discussion
   Explain what future math-agent papers should use as default baselines and judges.

7. Limitations
   Note remaining reliance on automated judges, provider instability, and the small frontier subset.

## Figures and tables to include

- A figure showing the four pipeline modes.
- A table comparing pass@1, pass@k, full, and seed_full.
- A table showing judge-vs-human calibration.
- A judge agreement matrix.
- A small case-study table where one solution flips from "pass" to "fail" across judges.

## Bottom line

The paper can make one plain claim:

In math proof agents, simple resampling is a very strong baseline, stronger critics matter more than naive self-refinement, and calibrated judging is necessary to know which conclusion is real.
