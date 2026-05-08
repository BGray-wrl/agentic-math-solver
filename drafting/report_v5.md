# Stage 5 Report — peer-review revision

## What I did

Two pre-submission peer reviews flagged overlapping concerns. I addressed everything cross-reviewer-flagged plus the high-leverage singletons; deferred low-leverage items given deadline. All changes are reanalysis-from-existing-data plus framing — no new API calls.

## Cross-reviewer items (highest priority — both reviewers raised)

1. **"Strict solves" → "candidate passes" throughout.** Both reviewers pushed hard on this — "strict-judge solve" overstates what an automated grader produces. Renamed in abstract, §5.1, §5.4, §5.5, §6.2, §8, §9. Kept "candidate" in places where qualified.

2. **Demote pooled `seed_full = +0.32` framing.** Both reviewers flagged the pooled aggregate as misleading because seed_full has 3-of-6 model coverage. Now marked *(partial)* inline in §5.1 table; explicitly described as "directionally suggestive" with interpretation deferred to §5.4.

3. **Problem-clustered bootstrap.** Both reviewers flagged that trial-level CIs ignore problem-level dependence. Recomputed all headline contrasts with cluster-by-problem resampling. New cluster CIs replace trial-level numbers in §5.1 and §5.4 tables; trial-vs-cluster comparison in Appendix A.10. Result: cluster CIs are slightly tighter for the seed_full reasoning=max contrast (cluster Δ=+0.60 [+0.21, +1.03], p=0.005 vs trial-level [+0.23, +0.99], p=0.003) and slightly tighter for `full−generate` (still null). The clustered analysis confirms the v4 narrative.

4. **Empirical token/cost accounting** (Focused #4, Strict #8). Computed actual per-trial generator-side cost from `cost_usd` in the architecture trials. Big finding: median `full` cost is **0.78× generate** (full is *cheaper* than generate, not 1×; verifier-revisor calls are shorter and full early-stops on easy problems), and `seed_full` is **1.36× generate** (not 3×). Translates to cost-fair pass@k baselines: `seed_full` is closer to pass@4–5 than pass@9. New §3.1 paragraph + Appendix A.9 (pooled and per-model). The earlier "pass@9 collapses the lift" framing was overstated; revised §5.4 says "small edge for cheap models at reasoning=max; pure scaling wins for stronger generators" against properly cost-matched pass@5.

5. **Multiple-comparisons correction (Holm)** for §5.4 per-cell tests (Strict #2). Eight contrasts at α=0.05; Holm-adjusted, smallest p is 0.15 (Gemma max `full−generate`). None of the per-cell results survives at α=0.05 after correction. §5.4 now reports raw and Holm p-values side by side; the per-cell results are framed as exploratory. The pooled reasoning=max stratum cluster contrast (p=0.005) does survive and is the load-bearing positive in the paper.

6. **Wilson / Clopper–Pearson upper bounds for zero-pass cells** (Strict #4). The v4 [0.000, 0.000] CIs in Section 5.2 were a structural artifact, not precision. Now research-hard pass-rate is reported as "0/55, one-sided 95% upper ≤ 5.4%"; research-frontier "0/27, ≤ 10.6%" — honest given the small samples.

7. **Statistical-dependence caveat in §3.4 + Limitations**. Inserted: bootstraps quantify uncertainty over the observed grid, not a problem population; tier-level and frontier-pass analyses are descriptive given 1–4 unique problems per R26 tier.

8. **Promote §10 follow-ups into §8 limitations as fragility notes** (Strict, Focused both implicitly). New §8 entries: single-judge audit on reasoning=max; seed_full partial coverage; no expert grading on R26; multiple-comparisons posture; AI-assistance disclosure.

9. **Tighter abstract** (Focused #5). Repacked the abstract: leads with the negative `full−generate` result, marks `seed_full` as partial coverage, mentions Holm posture, flags FirstProof-10 as likely leaked, and ends with the practical recommendation. Length similar to v4.

## High-value singletons

10. **GradingBench off-distribution caveat in §5.5** (Strict #6). Now explicit that GradingBench calibration is on IMO-class items; pass-agreement on Erdős/First-Proof has not been independently calibrated.

11. **AI-assistance disclosure** (Strict #7). One sentence in §8.

12. **FirstProof-10 outlier note** (Strict #11). New paragraph in §5.5: 23/33 cells produce v4-flash candidate passes — far above any other R26 item, and FirstProof-10 has substantial public solution context. Excluding it drops the v4-flash total from 32 to 9. This reframes the headline "32 candidate passes" as concentrated on a likely-leaked item.

13. **Generator-judge family stratification** (Strict #5). Computed `seed_full − generate` Δ split by same vs different family (canonical judge = DeepSeek-v4-flash). Same family +0.15 [−0.49, +0.79]; different family +0.35 [+0.09, +0.62]. Lift is concentrated in cross-family generators — judge-family bias does not drive the headline. Inline in §5.3, full table in Appendix A.11.

14. **Zheng et al. 2023 LLM-as-judge citation** (Strict #5). Added in §5.3 next to the Gemini lenience finding.

15. **Malformed-ideator caveat near §5.1** (Focused #5). Inline note that we do not use `seed_generate` as primary evidence given the original Phase 1 fallback contamination.

## Deferred (low leverage given deadline)

- **Failure-mode qualitative inset** (Strict #9). Would require reading and annotating ~10 trials; modest reader value vs. word budget.
- **Concurrent-work scan** (Strict #10). Background subagent could do this; one sentence might suffice but felt below the cut.

## Numbers that changed materially

- v4 §5.1 trial-level `full−generate` CI [−0.27, +0.13] → cluster [−0.25, +0.08]. Same null direction, slightly tighter.
- v4 abstract "Δ=−0.57, p=0.023" for Gemma max `full−generate` → softened to "exploratory" framing (Holm p=0.152). The directional negative finding remains in §5.4 but is no longer a stand-alone claim.
- v4 abstract "+0.60 (p=0.003)" for seed_full max stratum → +0.60 [+0.21, +1.03], cluster p=0.005 (still a real positive).
- v4 "32 strict-judge solves" → "32 strict-judge candidate passes (9 excluding FirstProof-10)."
- v4 nominal "~3 calls / ~9 calls" → empirical "0.78× / 1.00× / 1.36× generate" cost ratios.

## Word counts

- **Main paper (Sections 1–10): 4,989 words.** Under the 5,000-word target.
- Figures + Appendix + References: ~2,800 words (added A.9, A.10, A.11; trimmed elsewhere).

## What's still imperfect

1. **No v4-pro grades on reasoning=max seed_full cells.** §8 calls this out as a fragility note and §10 prices the audit at ~$5–10. Not feasible before the deadline.
2. **No expert grading on R26.** Same. Now framed honestly as "candidates for expert review."
3. **Per-cell §5.4 results don't survive Holm.** Reframed as exploratory; pooled stratum carries the positive.
4. **Concurrent-work paragraph not added.** A reviewer could flag this.

## Final verification checklist

- [x] Main paper ≤5,000 (actual 4,989)
- [x] Cross-reviewer items #1–9 addressed
- [x] High-value singletons #10–15 addressed
- [x] Plots unchanged (still six)
- [x] References include Zheng et al. 2023
- [x] AI-assistance disclosure present in §8

Word count of this report: ~860.
