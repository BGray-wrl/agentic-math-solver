# Stage 1 Report

I turned the outline into a complete rushed draft with no placeholders. The biggest structural change was to move judge calibration before the main architecture results, because the architecture story depends heavily on which proof grader is trusted. I also separated the clean Phase 1 architecture comparison from the broader all-row summary, since the latter makes `seed_full` look better but is not like-for-like.

Main findings after checking the data:

- The clean architecture result is mostly negative. In Phase 1, pass@3 generation, seeded generation, and the generator-verifier-reviser loop all sit around 31-32% pass rate under the canonical DeepSeek V4 Flash judge.
- `seed_full` is promising but confounded. It has the best all-row mean and pass rate, but its coverage is asymmetric and bundled with later experiments and reasoning reruns.
- Reasoning effort is one of the strongest effects. GPT-OSS and Gemma improve substantially when reasoning is raised; DeepSeek V4 Flash collapses on AnswerBench when reasoning is disabled.
- Simple scaling is the strongest robust architecture-like result. DeepSeek V4 Flash rises from 40% pass rate at n=1 to 64% at n=7 on the full 70-problem scaling run.
- Research-grade pass judgments exist but are concentrated. First Proof 10 and Erdős 654 account for most of them. The hardest frontier problems remain mostly unsolved.

I added simple tables for dataset composition, judge calibration, architecture comparisons, scaling, and research results. I deliberately did not add plots in this stage. The main thing that fell out from shaking the draft is that the paper should not claim "agentic pipelines work"; it should claim that lightweight pipelines are hard to distinguish from pass@k unless compared against an equal-budget baseline.
