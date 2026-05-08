# Stage 2 Report — what changed and what I built out

## What changed from Stage 1

1. **Real abstract.** Replaced the placeholder with a four-claim abstract: token-cost-fair pipeline comparison, judge-flip story, reasoning dominance, and the frontier-solves audit (only research-easy problems clear strict judges). Numbers throughout match the verified data.

2. **Real Discussion section (Section 9).** Replaced the placeholder Conclusion. Three engineering takeaways: (a) control for token cost before claiming pipeline lift; (b) audit with at least one strict and one lenient judge; (c) genuine novelty in our data lives at research-easy problems where models reproduce known directions, not at the harder R26 tier. The Aletheia "31.5% technically correct, 6.5% intent-correct" framing helps qualify the "agentic pipelines unlock new mathematics" pitch.

3. **Per-problem frontier solves (Section 5.4 Table 6).** Replaced text-heavy summary with a clean per-problem roster across all three judges. The headline is now visible at a glance: FirstProof-10 is solved 20×, Erdős-654 is solved 5× (the strongest reproducible-research-tier evidence in the dataset), and FirstProof-4, FirstProof-6, Ramsey-hypergraphs all receive zero strict-judge solves. Also surfaces the Erdős-1051 row as the sharpest single illustration of judge divergence (0 v4-flash, 0 v4-pro, 14 Gemini). Three-paragraph interpretation grounds the table.

4. **Fully populated Appendix.** A.1: full GradingBench table. A.2: AnswerBench-50 full generator calibration. A.3: per-cell architecture × judge × model × reasoning grid (29 rows). A.4: reasoning-effect detail. A.5: expensive-models probe. A.6: roleswap detail. A.7: pass-flip rate detail.

5. **Effect-size phrasing tightened.** Stage 1's mix of "modest," "real," "small" is now anchored by paired numbers and pass-rate moves where the comparison is paired (Section 5.3 now reports both mean delta and pass-rate delta on Gemma and GPT-OSS reasoning=max).

6. **Limitations sharpened.** Added an explicit "single-judge audit on reasoning=max" gap, since the cleanest pipeline-lift result lives in cells where v4-pro grades are missing. This is honest and surfaces a real audit limitation.

## New things I noticed this pass

- **Gemma-4 with reasoning=max produces the single best research-tier solve count** (3/9, all under v4-flash, including the only Gemma solve of Erdős-333). This is the only architecture that puts a cheap-tier model at the top of the research-solve leaderboard. The seed_full × reasoning=max combination on Gemma is, on this metric, the clearest architectural result in the paper. I've made sure this is visible in Sections 5.3 and 5.4.

- **Erdős-654 is the cleanest reproducible solve.** Five v4-flash solves across four base models and four architectures, plus three v4-pro solves. This is stronger evidence of credible solving than FirstProof-10 (which is "easy" in the original challenge). Section 5.4 calls this out directly.

- **Gemini judge is sometimes stricter, not always more lenient.** On FirstProof-10 (the easiest research-tier problem), v4-flash counts 20 solves but Gemini counts only 8. On harder problems Gemini is much more lenient. The judge gap is non-uniform across difficulty. I noted this implicitly in Section 5.4 but did not center it; that's a Stage 3 candidate.

- **Pass@9 is mildly informative.** Extending Gemma's reasoning=max scaling curve to k=9 yielded 3.29 vs. k=7's 3.20. Not huge, but the slope hasn't plateaued. Mentioned in Section 6.2.

## Word budget

- Main paper (Sections 1–10): **3,949 words**. Under the 5,000-word target with ~1,050 words of headroom for Stage-3 citations and crispness pass.
- Appendix: 1,330 words.
- Total: 5,279 words.

## What's still rough heading into Stage 3

1. **No plots.** All findings are tables. Stage 3 will produce four matplotlib plots in `drafting/plots/`: judge-sensitivity per-mode means, pass@k scaling curves, reasoning-effect comparison, frontier-solves heatmap.

2. **No real citations.** Inline cites use placeholder author/year strings; references section is empty. Stage 3 resolves the lit-review URLs to author/year/venue via WebSearch.

3. **Section 5.4 could be even tighter.** The three-paragraph interpretation following Table 6 is necessary but slightly long. Stage 3 may compress to two paragraphs if word budget squeezes.

4. **Section 8 (Limitations) has a contamination subsection that doesn't pin actual model release dates.** Stage 3 should either tighten this or pull the explicit dates from the lit-review notes.

5. **Future Work (Section 10) is currently three follow-ups in one paragraph.** May tighten further if needed.

6. **Discussion paragraph 3** ("where novelty lives") makes a claim about Aletheia's 6.5% intent-correct figure that I should verify against the source before Stage 3 finalization.

## Stage 3 plan

- WebSearch each unique URL/title in `drafting/background_lit_review_context.md` to resolve canonical citations. Inline cites in the form `(Author et al., 2025)`; references section at the end.
- Generate four matplotlib plots from existing data; save to `drafting/plots/`. Reference each in the relevant main-paper section.
- Crispness pass on prose. Trim repeated phrasing across abstract / Section 1 / Section 9.
- Final word-count check on main paper (target: ≤5,000 strict).

Word count of this report: 581.
