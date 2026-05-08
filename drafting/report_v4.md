# Stage 4 Report — what changed and why

## What you asked for

Four substantive critiques on v3:

1. **Difficulty-controlled lift**: does pipeline lift survive on hard problems? Plot tier vs successes; add a difficulty-gradient table.
2. **All-trial frontier solves**: collapse architecture + scaling buckets into one frontier-solves table; note DeepSeek pass@7 hits Erdős-1051 and FirstProof-6; comment on failures-alongside-successes (false-positive concern).
3. **Review codex's draft**: pull anything I missed.
4. **Confidence intervals and p-values throughout**: how does the reader know what's significant?

I did all four.

## What changed in the prose (Sections 1–10)

**Headline reversal.** v3 framed pipelines as having genuine narrow lift on cheap models at reasoning=max. Direct verification against `architecture_20260506/trials.csv` with paired bootstrap CIs shows the actual story is more conservative and matches codex's reading more closely:

- `full − generate` (the cleanest pipeline-vs-pass@3 contrast, n=533 paired cells): **Δ = −0.08, 95% CI [−0.27, +0.13], p=0.45**. The pipeline does not beat token-matched pass@3.
- At Gemma reasoning=max specifically: **`full − generate` Δ = −0.57, p=0.023** — the pipeline *hurts* on cheap-model max-reasoning cells.
- The pooled `seed_full − generate` lift (+0.32, p=0.013) survives but stratifies entirely into the reasoning=max cells: at default reasoning Δ=+0.13 (p=0.46, null); at reasoning=max Δ=+0.60 (p=0.003). The "lift" is a reasoning effect riding on architecture coverage.

The abstract, Section 5.1, Section 5.4, and Discussion are rewritten to reflect this. The headline now reads: "pipeline does not beat token-matched sampling; reasoning and scaling dominate."

**New Section 5.2 — Difficulty stratification.** Pass-rate falls cleanly with difficulty: 86% at PB-Basic, 29% at competition-hard, 23% at research-easy, 2% at research-medium, 0% at research-hard or research-frontier — all under the canonical strict judge. The paired-diff lift table by tier is in Section 5.2 and the full version in Appendix A.8. Key per-tier finding: `seed_generate − generate` is *significantly negative* on R26-only (Δ=−0.24 [−0.54, −0.03], p=0.030) — seeded ideation hurts on hard problems. The new Figure 5 renders this gradient with bootstrap CIs.

**Section 5.5 — Frontier solves rewritten with all 3,178 trials**. Pooling architecture (2,098 trials) and scaling (1,080 trials) lifts the strict-judge solve count from v3's 27 to **32**. Critically, DeepSeek-v4-flash at pass@7 default reasoning produces the *only* strict-judge solves of Erdős-1051 (research-medium) and FirstProof-6 (research-hard). New per-cell counts and false-positive context: 33 cells per problem, with strict-judge pass-rates of 70% on FirstProof-10 down to 3% on the harder research-medium-or-research-hard items. The 14/33 Gemini "passes" on Erdős-1051 against 1/33 v4-flash and 0/33 v4-pro is the sharpest single illustration of judge-induced false positives.

**False-positive analysis.** P(Gemini pass | v4-flash fail) = **0.368 [0.338, 0.398]** over n=987 strict-fail cases. The reverse, P(Gemini fail | v4-flash pass), is 0.035 [0.020, 0.053]. The lenient judge over-passes on a third of strict-fail cases — meaningful when interpreting any single-cell solve on a hard problem.

**CIs and p-values throughout.** Every load-bearing claim now carries a 95% percentile-bootstrap CI (5,000 resamples) and a sign-flip permutation p-value (10,000 permutations). Methodology is in Section 3.4. Tables in 5.1, 5.2, 5.3, 5.4, 5.5, 6.2, A.4, A.7, A.8 all carry CIs.

## What I pulled from codex's draft

Codex's v3 frames the result more conservatively ("simple sampling is a strong baseline; pipelines do not reliably beat pass@3"). Direct verification against the CSV confirms codex was closer to right than my v3, so the headline reframing in v4 broadly matches their reading. I borrowed three specific things:

1. The pass-rate-by-tier breakdown (their Section 2 quotes "86.1%, 28.9%, 22.6%, 1.8%, 0%, 0%" — I recomputed and matched these exactly).
2. The framing that the appropriate baseline for the seed_full pipeline is pass@9, not pass@3 — and the explicit observation that at pass@7-extrapolated, scaling matches or beats every pipeline configuration.
3. The "every proposed scaffold should beat the pass@k curve at the same cost" framing in Section 6.2 / Discussion.

I did not adopt codex's overall paper structure (their Section 4 puts judge calibration upfront as a main result; mine keeps the architecture comparison as the spine, per the user's earlier instruction). I also kept the explicit reasoning section as a major secondary finding rather than merging it into a generic "knobs that matter."

## What I dropped or de-emphasized from v3

- Section 5.3's framing of seed_full as having "real lift" on cheap models is now qualified throughout: lift exists vs pass@3 only at reasoning=max, and at the proper pass@9 baseline the lift collapses.
- The v3 "bottom line" claim that "the highest-leverage knob remains reasoning depth" is preserved but no longer paired with claims of pipeline lift.
- v3's frontier-solves count of "Erdős-1051: 0 strict solves" is updated to 1 (DeepSeek pass@7) because the scaling bucket now contributes.

## New plots

- **Figure 2** updated with 95% bootstrap-CI ribbons on pass@k curves (not just point estimates).
- **Figure 3** rebuilt as a forest plot: paired effect sizes with CIs, color-coded by significance (green = sig pos, orange = sig neg, grey = null). Replaces the deprecated `fig3_reasoning_vs_architecture.png`.
- **Figure 4** updated to reflect ALL-trial frontier solves; cells now annotated as `solves/cells` rather than just count.
- **Figure 5 (new)** difficulty gradient with CIs.
- **Figure 6 (new)** lift-by-tier forest plot.

The plot script is `drafting/plots/make_plots.py`. All plots regenerate deterministically from the cached numbers (no API calls).

## Word count

- **Main paper (Sections 1–10): 4,648 words.** Under the 5,000-word target with ~350-word margin.
- Figures + Appendix + References: ~2,030 words.
- Total: ~6,980 words.

## Statistical methodology, briefly

`drafting/analysis_v4.py` produces every CI and p-value reported. Bootstrap is 5,000 resamples (np.random seed 20260507), CIs are percentile method. p-values are sign-flip permutation tests with 10,000 permutations on paired diffs. For pass-rate deltas the binary indicator is paired directly, then bootstrapped on the paired-diff series. All numbers in the v4 prose tie to entries in `drafting/analysis_v4_output.txt`.

## What's still imperfect

1. **No v4-pro grades on reasoning=max cells.** The two clean significant cells (Gemma max seed_full−generate p=0.035; GPT-OSS max seed_full−generate p=0.048) are v4-flash-only. Section 8 surfaces this as a real audit gap. The +0.035 p-value is also borderline — a v4-pro audit (~$5–10) is the cheapest way to harden this.
2. **Single-trial point estimates per cell.** Each (model, reasoning, problem) was run once. The CIs in this paper are over the *problem dimension* — variance across the 70 problems, treated as a fixed sample. Multi-seed reruns (e.g., 3× on the four cells driving Section 5.4) would give true paired-difference SEs and let us put a tighter bound on the +0.6 deltas.
3. **The Aletheia 31.5%/6.5% citation in Section 9** is from lit-review notes, not direct verification of arXiv:2602.10177 (Section 9 uses it as a qualitative anchor; carrying it forward from v3).
4. **The R26 difficulty rubric** is our judgment call. Re-rating with a hidden second grader would test the difficulty gradient's robustness.

## What I'd recommend for "milder edits" next

- A v4-pro pass on the four reasoning=max seed_full cells would close the audit gap and likely tighten the headline number from "p=0.035" to something cleaner.
- Decide whether to demote Section 5.3 (judge sensitivity) to a Methods-adjacent subsection, since the judge-flip story is now mostly handled by the abstract's claim 3 plus Section 5.5's false-positive context.
- A pass on the abstract's first claim — the pipeline-vs-sampling negative result — to make sure the wording is the strongest version of the claim that the data actually supports.

Word count of this report: ~840.
