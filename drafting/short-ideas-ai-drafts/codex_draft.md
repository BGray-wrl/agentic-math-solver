# More Attempts or Better Critique?

## A short draft on test-time compute for math proof agents

## Abstract

This draft studies a simple question: when we give language models more test-time compute on hard math problems, what kind of extra compute actually helps? We compare several common approaches: single-shot generation, best-of-k sampling, a generate-then-verify/revise pipeline, and multi-branch seed-idea pipelines. We also compare several judges, because evaluation turns out to be a large part of the story.

The main result is that simple resampling is a very strong baseline. For stronger models, best-of-k sampling usually matches or beats iterative self-refinement. For weaker models, refinement can help, but mainly when the critic is stronger than the generator or when reasoning is explicitly enabled. A second result is that judge choice can reverse the conclusion: lenient judges reward polished-looking proofs, while stricter judges are closer to human grading and often remove apparent pipeline gains. The practical message is straightforward: always report a pass@k baseline, treat reasoning budget as part of the method, and calibrate judges before making strong claims about agentic math systems.

## 1. Introduction

Recent work on agentic reasoning often reports gains from multi-step pipelines. A typical system generates a solution, critiques it, revises it, and sometimes repeats this loop several times. Other systems branch into multiple ideas and choose the best result at the end. These designs are plausible, but they raise a basic question: are they helping because the structure is genuinely useful, or because they simply spend more test-time compute?

This question matters a lot for math proofs. A proof can look polished and still be wrong. A model can also fail on its first attempt but solve the same problem on a later sample. Because of this, any comparison between pipeline methods has to separate at least three things:

1. extra attempts
2. extra critique and revision
3. the choice of judge

Our main finding is that these factors are easy to confound. In particular, a full pipeline can look much better than a simple baseline if it is only compared against pass@1, and it can also look much better if it is graded by a lenient judge. Once we compare against a stronger baseline such as pass@k, and once we use stricter judges, the picture becomes more conservative.

The paper makes three claims. First, best-of-k sampling is the main baseline for math proof agents and is often hard to beat. Second, stronger critics can help weaker generators, but naive self-refinement and naive model mixing are much less reliable. Third, judge calibration is not a side issue. It is part of the main experimental design, because judge choice can change the ranking of methods.

## 2. Experimental setup

The main benchmark is a 70-problem proof set built from ProofBench-style IMO problems plus a small set of harder special problems. The problem set spans easier proof tasks, medium and advanced proof tasks, and a handful of harder frontier-style problems. We use this benchmark for the main architecture comparison because it measures what we care about most: not just whether the model finds the answer, but whether it can produce a proof that survives grading.

The main pipeline modes are:

- `pass@1`: one generated solution
- `pass@k`: k independent generated solutions, then pick the best judged result
- `full`: generate, then verify and revise for a few rounds
- `seed_full`: first generate several seed ideas, then run a full verify/revise pipeline on each branch

We also use two supporting evaluations. The first is an answer-only benchmark, which tests whether a model can reach the right final answer without having to produce a full proof. This is useful because it separates answer finding from proof writing. The second is a grading benchmark with human labels. This is used to compare judges against people rather than only against other judges.

The model set spans weaker and stronger models, including cheap open models, medium-cost reasoning models, and stronger DeepSeek-family models. We also test a few asymmetric setups where one model generates and another model critiques. Throughout the experiments, reasoning settings matter a great deal, so comparisons are only meaningful when reasoning effort is stated clearly.

## 3. Main results

### 3.1 Best-of-k is the strongest baseline

The clearest result is that simple resampling is very strong. When true best-of-k is measured carefully, it often matches or beats more elaborate self-refinement pipelines, especially for the stronger proof models. This means that many apparent gains from agentic structure are actually gains from having more attempts.

This point is easy to miss. If a full pipeline is compared only against pass@1, it can look clearly better. But this is not the right comparison when the pipeline uses much more compute. Once the pipeline is compared against a cost-matched best-of-k baseline, the gains often shrink or disappear. In the strongest versions of the main experiment, pass@3 was the best mode for the strongest models and remained the cleanest default baseline overall.

The practical lesson is simple: any math-agent paper that does not report pass@k is missing the main baseline.

### 3.2 Stronger critics help more than naive self-refinement

The result above does not mean critique is useless. It means critique has to be used carefully. In the main runs, weak models often over-approved their own solutions, and self-verification was noisy. In contrast, some asymmetric setups were more promising. When a stronger critic reviewed the output of a weaker generator, the pipeline sometimes recovered errors that self-critique missed.

This leads to a more precise view of agentic pipelines. Self-refinement is weak when generator and critic share the same blind spots. Cross-model diversity by itself is also weak. Simply mixing models across ideation, verification, and revision is usually a wash and can even hurt. What seems to matter is not diversity in the abstract, but whether the critic is actually better at critique than the generator is at self-critique.

So the right question is not "does a pipeline help?" The right question is "where is the extra capability in the pipeline coming from?" In our experiments, a stronger critic was much more useful than a fancier but same-strength loop.

### 3.3 Reasoning is a major hidden variable

Another strong pattern is that many model comparisons changed once reasoning was turned on explicitly. Some models that looked weak under default settings became much more competitive at higher reasoning effort. The same was true for judging models.

This matters for both fairness and interpretation. If one model is evaluated at low reasoning effort and another at high reasoning effort, the comparison is not really model versus model. It is model plus configuration versus model plus configuration. A careful experimental paper should therefore treat reasoning budget as part of the method and report it clearly.

## 4. Judge calibration changes the headline

Judge choice turned out to be one of the most important findings in the project. Some judges were much more lenient than others. In practice, lenient judges tended to reward polished-looking proof attempts, especially after revision. Stricter judges looked deeper for actual gaps and therefore graded many of the same solutions much lower.

This was not a minor effect. In some cases, the ranking of methods changed under different judges. Under a lenient judge, a full verify/revise pipeline could look like the best method. Under a stricter judge, simple pass@k could become the winner. This is exactly the kind of experimental instability that can produce misleading paper claims.

To test this more directly, we compared judges against human-labeled grading data. The broad result was that stricter reasoning-based judges were much closer to humans than lenient non-reasoning judges. A cheap strict judge performed surprisingly well and tracked the more expensive strict judge closely. Small ensembles also worked well on practical pass/fail decisions.

The main lesson is that judge calibration belongs in the core methodology. A paper about math agents is partly a paper about how correctness is being measured. If the judge is systematically lenient, the paper can end up measuring polish instead of rigor.

## 5. Supporting results from answer-only math

The answer-only benchmark tells a simpler story. It mostly measures whether the model can get the right answer, not whether it can write a proof. Model rankings on this benchmark were related to the proof benchmark rankings, but they were not the same. Some models that looked strong on answer-only tasks were much less reliable on proof-writing tasks.

This difference is useful rather than inconvenient. It shows that answer finding and proof generation are not the same capability. As a result, answer-only benchmarks are helpful for model ranking and quick capability checks, but they should not replace proof benchmarks when the goal is to evaluate agentic proof systems.

## 6. Discussion

The main contribution of this work is not a single new pipeline. It is a cleaner way to evaluate pipelines.

First, pass@k should be treated as the default baseline. If a method cannot beat simple resampling at similar cost, then its structural complexity is not yet justified.

Second, stronger critics deserve more attention than naive self-refinement. A weak model critiquing itself is often not enough. A better critic can provide a real capability difference.

Third, reasoning budget should be reported as part of the method. Several conclusions changed once reasoning was enabled explicitly, and paper claims that ignore this will be unstable.

Fourth, judge calibration is necessary for credible results. In our experiments, lenient judges regularly inflated scores and frontier-style claims that looked exciting under one judge often disappeared under a stricter regrade. That does not mean the lenient judge is useless, but it does mean its role must be stated clearly.

Overall, the plain takeaway is that extra test-time compute does help. But the useful form of extra compute depends on model strength, critic strength, reasoning budget, and judge choice. For stronger models, more attempts often beat more reflection. For weaker models, reflection helps more when it comes from a stronger critic rather than from a model talking to itself.

## 7. Limitations

This study still relies heavily on automated judges, even though we calibrate them against humans. The human-labeled grading benchmark is smaller than the full proof benchmark, and full human grading at larger scale would be better. Provider instability and timeout behavior also affected some runs. Finally, some of the hardest special problems remain noisy and should be treated carefully in any final paper claim, especially when only one judge supports the result.

## 8. Conclusion

This draft argues for a simple experimental standard in math-agent work. Always report a pass@k baseline. Treat reasoning effort as part of the method. Use calibrated judges, and do not rely on a single lenient grader for headline claims. Under these standards, the main story becomes clearer: best-of-k sampling is a very strong baseline, stronger critics are more useful than naive self-refinement, and careful evaluation matters just as much as pipeline design.
