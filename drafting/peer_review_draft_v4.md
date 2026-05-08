# Peer Review: *Comparing Inference-Time Methods for Natural-Language Mathematical Proofs* (draft v4)

*Pre-submission review. Scoped for a near-deadline revision: no new experiments, only reanalysis from existing trial data and writing/framing fixes.*

---

## Recommendation

**Weak Accept** at an evaluation / Datasets-and-Benchmarks venue; **Borderline** at a methods-track main conference. **Confidence 4/5.** The paper makes a real, useful contribution — a token-cost-fair, statistically-controlled study showing that the verifier–revisor pipeline does not beat pass@3 (Δ=−0.08, p=0.45 over n=533, §5.1), plus a reusable quantification of judge leniency (§5.3, A.7). It deliberately proposes no new method; the contribution is measurement discipline and a negative result. The biggest risks to acceptance are (i) the only positive architecture finding rests on a single judge, (ii) some pooled aggregates are over non-representative subsets, and (iii) standard methodological hygiene (multiple-comparisons treatment, clustered bootstrap, generator–judge family bias) is missing.

## Strengths

- Headline negative result is well-supported and honestly framed (§5.1, §5.4, §9).
- §5.3 / A.7 conditional flip rate P(lenient pass | strict fail) = 0.37 over n=987 is a directly reusable artifact.
- §8 limitations are unusually candid (contamination, n=2 per-tier, single-judge audit).
- Budget transparency (§7) and concrete cost-sized follow-up plan (§10) are good practice.

## Required revisions (reanalysis + writing only — no new API calls)

1. **Reframe the pooled `seed_full − generate = +0.32` in §5.1 and the abstract.** This aggregate is over a non-representative subset (3 of 6 base models, weighted toward cheap + reasoning=max). §5.4 already does the right thing; just demote the pooled number to "directionally suggestive, see §5.4 for the trustworthy disaggregation" or move it to an appendix.

2. **Add multiple-comparisons treatment to the §5.4 per-cell tests.** With 8 contrasts at α=0.05, the marginally significant findings (p=0.023, 0.035, 0.048) do not survive Bonferroni at α=0.00625. Either Holm-corrected p-values or an explicit "exploratory, uncorrected" framing. The Gemma-max `full−generate = −0.57, p=0.023` claim in the abstract should be softened the same way.

3. **Problem-clustered bootstrap on headline contrasts.** §3.4 is ambiguous about resampling unit. Hard problems are correlated across architectures within a problem; trial-level bootstrap likely understates the CI. Recompute the headline `full − generate`, `seed_generate − generate`, and `seed_full − generate` CIs with cluster-by-problem resampling. This is a one-day reanalysis on existing data.

4. **Wilson / Clopper–Pearson CIs for the all-zero pass-rate cells in Table 4 (§5.2).** [0.00, 0.00] is a structural artifact, not a precision claim. Replace with proper one-sided upper bounds (n=55, x=0 → ≈ 6.5%).

5. **Generator–judge family overlap.** DeepSeek-flash is canonical judge AND a generator; v4-pro is audit judge AND a generator. Add a stratified sub-table from existing data: architecture deltas where judge family ≠ generator family vs. same-family. If the same-family deltas are systematically higher, flag it. Cite the LLM-as-judge calibration literature (Zheng et al. 2023 and follow-ups) — currently absent.

6. **Add the GradingBench off-distribution caveat to §5.5 explicitly.** GradingBench is IMO-class; the 87% pass-agreement does not transfer guaranteed to Erdős / FirstProof items where the "32 strict-judge solves" headline lives. One paragraph; no experiments needed.

7. **AI-assistance disclosure statement.** 2026 venue norms increasingly require it. One sentence.

## Recommended (still no API calls)

8. **Empirical token cost from existing logs.** Replace "~3×" and "~9×" in §3.1 with measured prompt+completion token ratios. Likely the verifier-revisor calls run longer than generations; if the true cost ratio is 3.5–4× rather than 3×, the fair baseline shifts and your null result becomes *stronger* (you're comparing `full` against an unfairly large pass@k).

9. **Failure-mode qualitative inset.** ~10 pre-existing trials where `generate` passes but `full` fails, plus the reverse, with one-line annotations. Turns a measurement paper into one that informs design and adds little length.

10. **Concurrent-work paragraph.** A short scan of late-2025 / early-2026 arXiv on judge calibration and inference-time scaling for math, even if just to acknowledge.

11. **One question on FirstProof-10.** Twenty-three of 33 cells solve it strictly — by far the largest contributor to the "32 solves" headline at a "research-easy" tier rating. Worth a sentence on whether it has public solution context that justifies the difficulty rating, since otherwise the strict-solve headline rests heavily on one possibly-misclassified item.

## Limitations to add (in lieu of experiments you can't run)

The four follow-ups in §10 (v4-pro audit, multi-seed reruns, Phase-1 seed_full extension, frontier-model sweep) are correctly identified as the right next steps. Since you can't run them before submission, **promote them from §10 into §8 limitations**, and add explicit fragility notes:

- The §5.4 cheap-model+max positive findings are unaudited under the second strict judge. Direction and magnitude are likely real but the precision is single-judge.
- The R26 strict-solve counts in §5.5 are not validated against expert grading; treat as candidates, not theorems. (You already say this — make it tier-1 prominent.)
- Three base models (DeepSeek-v4-pro, Gemini-3-flash-preview, Qwen3.6) lack `seed_full` coverage. The pooled seed_full statistic generalizes to cheap-model territory only.

A reviewer who sees these called out as known limitations is much friendlier than one who discovers them.

## For area chair

- **Reviewer disagreement likely on:** novelty (no new method); n=2 research-tier sample sizes; absence of frontier models. The first two are venue-fit issues; the third is a budget reality the paper handles honestly.
- **Recommendation stability:** Stable at Weak Accept assuming the seven required revisions land. Drops to Borderline if §5.1 framing of pooled `seed_full` and the multiple-comparisons treatment are not addressed.
- **Co-reviewer needed** with theorem-proving / olympiad-math expertise to validate the R26 difficulty calibration, especially the FirstProof-10 outlier.

---

*End of review.*
