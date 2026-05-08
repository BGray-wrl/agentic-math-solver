# Stage 1 Report — what changed and what I discovered

## Top-line discoveries from verification

Three findings shifted the paper's spine away from the rough outline.

1. **The judge-flip is real and one-sided, not symmetric.** The dataset cross-cut hinted that under Gemini, seed_full beats baselines while under DeepSeek-v4-pro it collapses. I verified this directly from `architecture_20260506/trials.jsonl` at the cell level. v4-flash and v4-pro agree on pass/fail on **95.5%** of the 1,440 triple-judge cells. Gemini calls "pass" on 25.2% of cases v4-flash calls "fail," and on 26.2% of cases v4-pro calls "fail" — but the reverse error is roughly 1%. Gemini systematically over-passes; v4-flash and v4-pro tell the same story. The hyped "judge sensitivity" is really one-sided Gemini lenience.

2. **The pipeline lift exists but only in a narrow regime.** Aggregate seed_full vs. generate is +0.27 (v4-flash), but that aggregate is dominated by a non-representative subset (seed_full was tested on only 3/6 base models). When I split by reasoning, the picture sharpens: at default reasoning, seed_full provides +0.07–0.27 v4-flash lift and zero v4-pro lift (+1.0 to +1.4 Gemini lift, suspect). At reasoning=max for Gemma + GPT-OSS, seed_full provides a real **+0.57 / +0.70** v4-flash lift over generate. Pipeline scaffolding helps cheap models with reasoning on; otherwise it is mostly a wash.

3. **Reasoning-on dwarfs every architecture effect.** On AnswerBench-50 the reasoning-toggle moves accuracy by 16–38 percentage points. On PB+R26 it moves the v4-flash mean by +0.78 to +1.60 across the modes I could compare. The largest architecture effect I saw was +0.70 (seed_full vs. generate, GPT-OSS reasoning=max). The reasoning-vs-architecture ratio is 3–5×.

## Structural changes from the rough outline

- **Headline reframed but spine preserved.** Architecture comparison stays as the spine of Section 5. Judge sensitivity gets its own subsection (5.2) with concrete numbers, but does not become the headline. This matches user guidance.
- **"Simple scaling is hard to beat" qualified, not deleted.** It is true under strict judges at default reasoning, broadly false under Gemini for cheap models, and falls down at reasoning=max where seed_full provides real lift on cheap models. The new framing: the architecture comparison is judge-, model-, and reasoning-conditioned.
- **Reasoning elevated.** Was tertiary in the outline; now Section 6.1 with explicit cross-comparison to architecture deltas.
- **Roleswap reported honestly null.** Outline hypothesis was "diversity helps at the frontier"; data shows seven of eight tested conditions are within ±0.4 of baseline, with one specific role assignment (GPT-OSS-as-verifier) showing modest lift. Reported as "null effect with one suggestive cell."
- **Frontier-solves panel is now in the main paper.** Outline had it scattered; consolidated into Section 5.4 with the v4-flash leaderboard. The Ramsey-hypergraphs zero-solve and the FirstProof-10 multi-solve are both flagged.
- **Coverage asymmetry callout (Section 6.4)** prevents over-reading aggregates: seed_full is missing from three of six base models, weighted toward cheap models.

## What I cut or moved

- The "consensus-vote of weak judges as a strong judge" thread is fully cut, per user guidance reserving deep-judge work for a separate paper.
- "Cross-model diversity helps at the frontier" is reframed from a finding to a null result.
- The 60+30+30 difficulty grading rubric was condensed into a single 10-row table (Section 3.3) instead of the three-paragraph treatment in the outline.
- The "Lessons Learned" / experiment-iteration anecdotes (broken ideator, missed logs) are condensed into one paragraph (Section 7).
- Lit review's long-tail — APOLLO, HorizonMath, Knuth's Cycles, OpenAI internal model v1/v2, the misc URL pile — is omitted from the main paper. We will pull what we need at Stage 3 citation pass.

## What still needs work going into Stage 2

1. **Abstract** is functional but generic. Stage 2 will rewrite once main results are locked.
2. **Conclusion** is a placeholder. Stage 2 will write the real one.
3. **Appendix** is empty. Stage 2 will populate full GradingBench table, AnswerBench by category, full architecture × judge × model × reasoning grid, expensive-models probe, roleswap detail, per-problem solve roster.
4. **Section 5.4 (frontier solves)** needs a per-problem roster table moved in from the verification (currently text-heavy).
5. **Effect-size phrasing** is inconsistent ("modest," "real," "small"). Stage 2 will normalize against the standard error from `summary.csv`.
6. **No plots yet** (per instruction). Stage 3 produces them.
7. **Limitations on contamination** is hand-wavy on dates. Stage 2 will pin model release vs. solution-disclosure dates from the lit-review notes.

Word count: 3,190 (well under 5,000). Headroom to expand findings in Stage 2.
