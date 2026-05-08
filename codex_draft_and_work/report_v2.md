# Stage 2 Report

I rewrote the draft into a more complete paper rather than a cleaned outline. The main structural change was to make the thesis sharper: the paper is about baselines, not about proving that a specific agentic scaffold wins. I added explicit research questions, separated methods from results, and made the architecture asymmetry visible before discussing `seed_full`.

What changed from v1:

- The abstract and conclusion now state the actual result directly: lightweight scaffolds do not beat pass@3 in the clean comparison.
- I split "Research-2026" membership from the difficulty scale, because they are related but not identical. Erdős 397 is in the research extension but tagged competition-hard.
- I made the calibration section more central and explained why DeepSeek V4 Flash is the canonical judge despite Gemini 3.1 Pro having the best continuous correlation.
- I reframed `seed_full` as a promising but confounded result rather than a main win.
- I added a clearer scaling section using the exhaustive subset pass@n estimates.
- I moved future design advice into an appendix-style note so the main argument stays short.

The main thing discovered in this pass is that the paper should not bury judge calibration or reasoning effort. Both are bigger than the architecture deltas. The final draft should probably lean even harder into this claim: for proof generation, "agentic" is not a sufficient description of an intervention. The measurable variables are samples, reasoning effort, model strength, judge bias, and whether the scaffold actually beats the equal-budget sampling curve.
