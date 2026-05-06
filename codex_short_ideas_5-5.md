# Short ideas from May 2026

## Main takeaways

1. The most stable result is not "the pipeline helps" or "the pipeline hurts." The stable result is that **extra test-time compute helps, but the best form depends on model strength**.
   - For stronger proof models, simple resampling (`pass@k`) is very hard to beat.
   - For weaker models, verify/revise can help, but mainly when the critic is stronger or when reasoning is enabled.

2. The second stable result is that **judge choice can reverse the paper headline**.
   - `gemini-3-flash` is much more lenient.
   - `deepseek-v4-flash` is much closer to `deepseek-v4-pro` and closer to human grading.
   - Any paper claim about pipeline gains has to be paired with a calibrated judge story.

3. The third stable result is that **reasoning settings matter a lot**.
   - Several model rankings changed once reasoning was turned on.
   - Several judge rankings also changed once reasoning was turned on.
   - A paper should treat reasoning budget as a first-class variable, not a hidden default.

4. The fourth stable result is that **cross-model diversity is not automatically useful**.
   - Cheap-model role swaps were mostly a wash.
   - Some verifier swaps clearly hurt.
   - A stronger critic can help a weaker generator, but naive mixing does not.

## Best paper direction

### Option A: main paper on pipeline design

Working claim:

`pass@k` is the main baseline for math-proof agents. Self-refinement often helps less than extra samples, especially for strong models. But stronger critics can still rescue weaker generators.

Why this works:

- It matches the biggest experiment in the log.
- It keeps the focus on architecture, which seems to be the main story.
- It leaves room for a useful negative result: many fancy pipeline moves do less than plain resampling.

What to show:

- A 4-way comparison: pass@1, pass@k, full pipeline, seed+full.
- Break results out by model strength.
- Show one asymmetric result where a strong critic helps a weaker generator.
- Put judge calibration in the main paper, not just the appendix, because it changes the result.

Simple thesis:

More attempts often beat more reflection. Reflection helps most when the critic is better than the generator.

## Strong secondary paper angle

### Option B: judge calibration paper

Working claim:

Math-agent conclusions are very sensitive to the grader. A cheap, calibrated judge or small judge ensemble can match much more expensive judging setups on practical pass/fail decisions.

Why this works:

- The May log has a real judge story, not just a side note.
- There is comparison against humans, not only judge-vs-judge.
- There is a practical systems result: `v4-flash` is a strong default judge, and cheap ensembles can be competitive.

What to show:

- Human grading benchmark.
- Cross-judge agreement table.
- Examples where the same solution flips the pipeline conclusion under different judges.

## Good combined paper framing

### Option C: one paper with two linked claims

Claim 1:

The best architecture result depends on whether the evaluation is measuring polished proof attempts or rigorous proofs.

Claim 2:

Once the judge is calibrated, the cleanest pattern is:

- strong models benefit most from sampling
- weak models benefit more from stronger critics and reasoning
- naive role diversity adds little

This is probably the most complete NeurIPS-style framing.

## Concrete points worth keeping

- The Phase 1 audit matters. It corrected both the baseline mismatch and the judge mismatch.
- True best-of-3 is important. It stopped a misleading "full pipeline wins" story.
- AnswerBench is useful as a side benchmark because it separates "get the answer" from "write the proof." The ranking there is related to, but not the same as, the proof benchmark ranking.
- The human-grading comparison matters. It makes the judge section publishable.
- Frontier claims need dual-judge confirmation. Many gemini-only "solves" did not survive stricter regrading.
- The unified dataset is a real asset. It supports a paper, a release, or both.

## A plain possible title list

- `Sampling, Self-Refinement, and Judge Calibration in Math Proof Agents`
- `When Does Self-Refinement Help Math Reasoning?`
- `More Attempts or Better Critique? Test-Time Compute for Math Proof Agents`
- `Judge Choice Can Reverse Conclusions in Math Agent Benchmarks`

## What I would not oversell

- I would not claim that seed ideas are broadly better than pass@k.
- I would not claim broad frontier breakthroughs from the special-10 set.
- I would not claim that cross-model diversity helps in general.
- I would not use gemini-only frontier passes as headline results.

## Minimal paper message

The clean message is:

`pass@k` is the right baseline, calibrated judging is mandatory, and stronger critics matter more than naive self-refinement or naive model mixing.


---

## Even shorter version

- The main result is simple: extra test-time compute helps, but for strong models `pass@k` is usually better than a full self-refinement pipeline.
- For weaker models, refinement can help, but mainly when the critic is stronger or reasoning is turned on.
- Judge choice changes the story a lot. `gemini-3-flash` is lenient. `deepseek-v4-flash` is much closer to `deepseek-v4-pro` and to human grading.
- Because of that, judge calibration should be part of the main paper, not a side note.
- Cross-model mixing is not a general win. Most role swaps were small or negative.
- AnswerBench is useful, but it is a side benchmark. It measures getting the answer, not writing a rigorous proof.
- Frontier claims should be treated carefully. Many gemini-only "solves" did not survive stricter regrading.

Best paper direction:

- Main paper: compare `pass@1`, `pass@k`, full pipeline, and seed+full, with judge calibration in the main results.
- Core claim: simple sampling is the main baseline, stronger critics matter more than naive self-refinement, and judge choice can reverse the headline.

What not to oversell:

- Do not claim that seed ideas are broadly better than `pass@k`.
- Do not claim that cross-model diversity helps in general.
- Do not use lenient-judge frontier passes as headline results.

Plain one-line message:

`pass@k` is the baseline to beat, calibrated judging is necessary, and stronger critics help more than fancy pipeline structure.
