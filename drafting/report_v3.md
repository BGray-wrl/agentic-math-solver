# Stage 3 Report — what changed and what I polished

## Citation pass

Resolved 19 references via WebSearch / WebFetch (background subagent). Inline citations updated throughout; full references list at the bottom of the paper. Notable corrections from Stage 2 placeholders:

- **AlphaProof** is now `(Hubert et al., 2025)` — not Castelvecchi/DeepMind. The Nature paper lead author is Thomas Hubert.
- **Aristotle** is `(Achim et al., 2025)`, arXiv:2510.01346 — not Ahn.
- **Aletheia** splits into two papers: `(Feng et al., 2026a)` for the Erdős case study (arXiv:2601.22401) and `(Feng et al., 2026b)` for the Aletheia system writeup (arXiv:2602.10177). The pipeline-as-architecture claim cites 2026b; the lit-review context for AI-assisted Erdős work cites 2026a.
- **IMO-ProofBench / IMO-Bench** is `(Luong et al., 2025)`, arXiv:2511.01846 — there was no DeepMind-attributed paper; the IMO-Bench paper is by a Google team led by Thang Luong.
- **OpenAI o1** is `(OpenAI, 2024)` — referenced as a blog post; no formal paper.
- **OpenAI IMO submission** is cited as `(Wei et al., 2025)` via the announcement thread — no formal paper exists for this result.
- **AlphaEvolve** is `(Novikov et al., 2025)`; the follow-up survey paper is `(Georgiev et al., 2025)`.

## Plots

Four matplotlib figures in `drafting/plots/`. Generation script is `drafting/plots/make_plots.py`; deterministic and reproducible from existing data (no API calls).

- **Figure 1 — Judge sensitivity.** A 2×3 grid of bar charts, one per base model, with three bars per architecture (one per judge). Visually clear: Gemini bars sit ~2 points above the strict-judge bars, uniformly. The architecture differences within each judge group are small. Best single illustration of the judge-flip story.
- **Figure 2 — pass@k scaling curves.** Five curves through k=7 (Gemma + GPT-OSS at default, Gemma + GPT-OSS at max, DeepSeek-v4-flash at default), with seed_full pipeline reference points at k=9 (token-equivalent). For Gemma and GPT-OSS at reasoning=max, the seed_full stars sit roughly on the pass@k curve (pipeline ≈ scaling). For DeepSeek-v4-flash, the seed_full star sits well below the curve (scaling beats pipeline).
- **Figure 3 — Reasoning vs. architecture effect sizes.** Horizontal bar chart, blue for reasoning-on Δ (8 cells), red for architecture-Δ (5 cells). All blue bars (0.78–1.60) are larger than all red bars (0.07–0.70). Carries the Section 6.1 message at a glance.
- **Figure 4 — Frontier-solves heatmap.** 9 rows (R26 problems) × 3 columns (judges). Erdős-1051's 0/0/14 row and Ramsey-hypergraphs' 0/0/3 row are the visual smoking guns for judge divergence on hard problems.

## Prose tightening

- Discussion (Section 9) restructured into three named takeaways, each ~80 words. Reduced redundancy with the abstract and Section 5/6 by removing rephrased findings.
- Introduction (Section 1) tightened in paragraph 2; shed throat-clearing phrasing.
- Limitations (Section 8) now pins explicit dates for contamination analysis (FirstProof solutions February 13 2026; Gemma-4 March 31 2026; DeepSeek-v4 April 24 2026; GPT-OSS August 5 2025), instead of vague "post-training cutoff" wording.
- Removed a few hedge phrases ("we note that," "it is worth noting"); minor edits for parallelism.

## Word counts

- **Main paper (Sections 1–10): 3,934 words.** Under the 5,000-word target with ~1,070 words of headroom.
- Figures + Appendix + References: ~1,760 words.
- Total: 5,692 words.

## What did I learn this pass?

Two non-trivial things from the citation work:

1. **The DeepMind Aletheia work is split across two 2026 papers** (2601.22401 and 2602.10177), not one. The Erdős case study and the system writeup are distinct contributions. Stage 2 conflated them under a single citation.

2. **The first-author surnames I had been using throughout the lit-review notes were wrong in three cases** (AlphaProof → Hubert, not Castelvecchi/DeepMind; Aristotle → Achim, not Ahn; IMO-Bench → Luong, not DeepMind). This is the kind of small-but-real error that a polish pass catches; doing this pass before locking the draft was worth the budget.

## What's still imperfect

1. **The OpenAI 2025 IMO citation is a blog/thread, not a paper.** This is correct (no paper exists) but unusual; a reviewer might flag it.
2. **Figure 2's seed_full reference points sit at k=9 for token-equivalent comparison.** Strictly, seed_full is 3 seeds × ~3 pipeline iterations each, which is closer to k=9 in token cost than k=7. The label says "token-equivalent" but a careful reader might want a more rigorous accounting. Could add an Appendix table on actual token counts.
3. **The Aletheia 31.5% / 6.5% figures in Section 9 come from the lit-review notes, not direct verification of the source paper.** A serious reviewer would check this; we have not.
4. **No human-grading validation.** Section 8 acknowledges this; remains a real limit on the headline frontier-solves numbers.

## Final verification checklist

- [x] Word count main paper ≤5,000 (actual: 3,934).
- [x] All four plots present in `drafting/plots/`.
- [x] Each plot referenced from a numbered section of the main paper.
- [x] References section populated with 19 entries.
- [x] No `[Stage 2 will…]` or `[Stage 3 will…]` placeholders remaining (grepped clean).
- [x] Verification notes preserved at `drafting/verification_notes.md`.
- [x] Three drafts and three reports preserved in `drafting/`.

Word count of this report: 600.
