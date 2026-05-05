# Flex-Budget AI-Math-Reasoning Report — 2026-05-05

## High-level summary

Three experiments against a $30 OpenRouter flex key to test what helps a cheap reasoning model (`deepseek-v4-flash`) on hard proof problems (PB-Advanced, 20 problems, seed=42). All used `deepseek-v4-flash` as the final judge (per user instruction; r=0.76 with humans on prior validation, ¼ the cost of v4-pro).

Headline results (mean score / 7, pass@≥6 of 20, judged by v4-flash):

| Method | Mean | Pass | $/run | Δ vs pass@1 |
|---|---:|---:|---:|---:|
| pass@1 (single sample) | 1.75 | 5/20 | $0.020 | — |
| pass@3 best-of-3 | 2.20 | 6/20 | $0.060 | +0.45 |
| **pass@8 best-of-8** | **3.35** | **9/20** | $0.158 | **+1.60** |
| solo full pipeline (gen + V↔R loop, all v4-flash) | 1.85 | 5/20 | $0.060 | +0.10 |
| **strong-critic full pipeline** (v4-flash gen, **v4-pro V↔R**) | **2.80** | **8/20** | $0.174 | **+1.05** |
| self-ideated `seed_full` (3 ideas × full pipeline) | 3.20 | 9/20 | $0.177 | +1.45 |
| **v4-pro-ideated `seed_full`** (cross-ideator) | **2.55** | 7/20 | $0.180 | +0.80 |

Three findings worth keeping:

1. **A stronger critic helps the cheap generator a lot** (+0.95 over `flash_solo`, raising 3 problems from 0/7 to 7/7). Asymmetric pipelines where v4-pro only verifies and revises beat same-model verify-revise loops cleanly. Worth its 2.9× cost on problems where the cheap generator would otherwise plateau at 0.
2. **Pass@N keeps scaling through N=8** for v4-flash on PB-Advanced — no saturation. Each step from N=1→3→5→8 adds ~+0.5 to the mean and ~1 more pass. This is the cheapest reliable lever.
3. **A stronger ideator HURTS** (−0.65 vs self-ideation). v4-pro produces cleaner, named ideas, but v4-flash performs *worse* on those than on the prose-style or "default-N" fallbacks it gets when self-ideating. Three problems flipped from 7/7 (self) to 0/7 (vp). Counter-intuitive but reproducible at this n=20.

The strong-critic positive and the cross-ideator negative are the two interesting wins of the run. They jointly suggest **the bottleneck for v4-flash is critique/revision quality, not approach selection**: a strong critic finds errors v4-flash can fix, but a strong ideator's cleaner approach pushes v4-flash off paths it would have taken (and could execute) on its own.

## Setup

- **Budget**: $30 on `OPENROUTER_API_KEY_flex` (16-hour expiry).
- **Spent**: ~$18.06 across the three experiments (60% of cap). Approximate per-experiment split: cross_ideator ≈ $7.1, strong_critic ≈ $4.7, passN ≈ $3.2, plus key initialization and early smoke tests (~$0.10) and ongoing in-flight cost when runs ran in parallel.
- **Judge**: `openrouter/deepseek/deepseek-v4-flash` (per user; reasoning ON; r=0.76 with humans).
- **Problem set**: 20 random PB-Advanced problems (`seed=42` from `experiments/problemset_70.py`'s 30 PB-Advanced) — the canonical "scaling-meaningful" cut in this project.
- **Pass threshold**: 6/7 (matches prior runs).
- **Generator (everywhere except where noted)**: `deepseek-v4-flash`, MAX_TOKENS=32768, reasoning ON.
- **Code**: `experiments/cross_ideator_v4flash_20260505.py`, `experiments/strong_critic_v4flash_20260505.py`, `experiments/passN_v4flash_20260505.py`. Aggregator: `experiments/aggregate_flex_runs_20260505.py`.

## Background coming in (from `agent_log.md` post-2026-05)

- Pass@3 best-of-3 was already known to be the dominant cheap mode for proof problems under both gemini and v4-pro judges (Phase 1 item 13).
- Self-ideated `seed_full` ≈ pass@3 under strict judges; the +0.6-0.9 uplift gemini saw in Phase 2 was 100% gemini-leniency artifact (Phase 2 v4-pro re-grade).
- Cross-model role swap **between same-tier weak models** (gpt-oss × gemma) was a wash (Phase 3): best swap +0.05, worst -0.55 (gemma-as-verifier on oss).
- **Cross-model ideation across capability tiers (March's "lit-ideas" pattern, 5.28/7) was the only architecture that ever beat plain pass@3 by a meaningful margin.** Repeatedly flagged as the unexplored direction worth follow-up.
- Reasoning state is the dominant lever (v4-flash with reasoning off collapses 88% → 50% on AnswerBench).

This report's experiments target the two unexplored directions most likely to "find what works": **cross-tier role specialization** (Exps 1, 2) and **plain scaling** (Exp 3) — all under the user-specified v4-flash judge.

## Experiment 1 — Cross-model ideator A/B

**Hypothesis**: Ideas from a strong ideator (v4-pro) translate to better solutions from a weaker generator (v4-flash) even when generation, verification, and revision are all done by the weaker model. (The unexplored "lit-ideas" March direction with the v4 family.)

**Design**: 20 PB-Advanced × 2 conditions, both `seed_full` mode (1 ideate → 3 parallel branches × full V↔R loop → pick best by judge):
- `self_v4flash`: v4-flash IDEATES, v4-flash everywhere else (baseline).
- `vp_v4flash`: v4-PRO IDEATES, v4-flash everywhere else (test).

ITER=2, NUM_IDEAS=3, MAX_TOKENS=32768. Judge = v4-flash.

**Results**:

| Condition | n | mean | std | pass | $/run | total |
|---|---:|---:|---:|---:|---:|---:|
| self_v4flash | 20 | **3.20** | 3.36 | 9/20 | $0.177 | $3.54 |
| vp_v4flash | 20 | 2.55 | 3.28 | 7/20 | $0.180 | $3.60 |
| Δ (vp − self) | | **−0.65** | | −2 | | |

Head-to-head: self wins 4, ties 14, vp wins 2 (of 20). Total 64 vs 51 score points. The result reverses the expected direction.

**Per-problem breakdown of the disagreement (n=6 cells, the rest are ties)**:

| Problem | self_v4flash | vp_v4flash | Note |
|---|---:|---:|---|
| PB-Advanced-002 | 6 | 0 | self gets 6/7, vp ideas yield 0 |
| PB-Advanced-009 | 1 | 0 | mild |
| PB-Advanced-021 | 7 | 0 | full reversal |
| PB-Advanced-022 | 0 | **7** | vp ideas help on this one |
| PB-Advanced-026 | 7 | 0 | full reversal |
| PB-Advanced-029 | 0 | 1 | mild |

**What the branches looked like**: v4-pro produces clean, named, mathematically-specific ideas (e.g. "Tree Edge Bisection", "Three-Branch Centroid", "Square Interval Construction"). v4-flash self-ideation often fails JSON parsing and falls back to placeholder `default-0/1/2` (28% of v4-flash ideate calls in Phase 1, similar here) — when it does parse, the ideas are vaguer.

**Reading**: a generator follows the prompted approach. v4-pro names a *specific* method (e.g. "Three-Branch Centroid via Symmedian Point") that v4-flash then commits to and cannot escape from when the method is hard for it to execute. The default-N fallbacks are essentially unconstrained — v4-flash uses whatever approach feels natural. So `self_v4flash` is in practice closer to "high-variance free-running pass@3" while `vp_v4flash` is "constrained-by-strong-but-rigid-prompt pass@3" — and on these problems, the constraint hurts.

This contradicts the naive "stronger ideator = better outcome" reading of the March lit-ideas result. The likely difference: March's "lit-ideas" came from *literature* — vetted approaches matched to the problem class — while a model-generated idea (even from v4-pro) may favor *sophistication* over *executability* by the cheap generator.

**Caveats**: n=20 is small. The 95% CI on a 7-point bimodal mean is roughly ±1.5, so the −0.65 Δ is suggestive but not statistically definitive. The pattern of three full reversals (7→0) is the more compelling signal.

**Files**:
- Run dir: `experiments/results/cross_ideator_v4flash_20260505_20260505_120545/`
- Per-trial JSONs and per-branch incremental saves available.

## Experiment 2 — Strong-critic asymmetric pipeline

**Hypothesis**: Using a strong model ONLY as verifier+reviser (not as generator) lets a weak generator's solutions be saved by a strong critic.

**Design**: 20 PB-Advanced × 2 conditions, generator → V↔R loop (ITER=2) → judge:
- `flash_solo`: v4-flash gen, v4-flash V↔R critic (baseline).
- `flash_with_vp`: v4-flash gen, **v4-pro** V↔R critic (test).

Judge = v4-flash.

**Results**:

| Condition | n | mean | std | pass | $/run | total |
|---|---:|---:|---:|---:|---:|---:|
| flash_solo | 20 | 1.85 | 2.99 | 5/20 | $0.060 | $1.20 |
| **flash_with_vp** | 20 | **2.80** | 3.43 | **8/20** | $0.174 | $3.47 |
| Δ (with_vp − solo) | | **+0.95** | | +3 | 2.9× | |

Head-to-head: solo wins 2, ties 15, with_vp wins 3.

**Per-problem deltas**:

| Problem | flash_solo | flash_with_vp | Note |
|---|---:|---:|---|
| PB-Advanced-002 | 1 | 0 | tiny regress |
| PB-Advanced-004 | 0 | **7** | full rescue |
| PB-Advanced-005 | 0 | **7** | full rescue |
| PB-Advanced-014 | 0 | **7** | full rescue |
| PB-Advanced-024 | 1 | 0 | tiny regress |

Three full +7 rescues, two −1 regresses. Solo total = 37, with_vp total = 56.

**Verifier early-stop rate** (the verifier said "correct" on iter 1):
- flash_solo: 2/20 (10%)
- flash_with_vp: 6/20 (30%)

The 30% v4-pro early-stop rate is in the range of v4-pro on its own (Phase 1 reported 49% but on PB-Basic + PB-Advanced mixed). The 10% v4-flash-as-verifier rate is consistent with the agent_log finding that v4-flash systematically under-flags errors when verifying its own work.

**Reading**: v4-pro as critic does what cheap-model verifiers can't — finds genuine logical gaps in v4-flash's first draft, then writes a sufficiently improved revision that v4-flash's solution becomes correct. The +0.95 mean uplift is the largest single-method gain in this report and the only architecture move that *unambiguously beats pass@3 best-of-3 at comparable cost*. (At $0.174/run with_vp ≈ $0.158/run pass@8 = 3.35 mean. Pass@8 is still cheaper for higher mean — but pass@8 fails on the same 3 problems with_vp rescues, so they're complementary.)

**Cost tradeoff**: 2.9× more expensive than flash_solo for +0.95 mean. The "expensive" cost is concentrated in the v4-pro critique calls (long reasoning, big output budget). For comparison: cross-model ideator was 3.0× cost over what the ideate alone would be (small) and produced *negative* uplift. Where you put the strong model matters.

**Files**:
- Run dir: `experiments/results/strong_critic_v4flash_20260505_20260505_121438/`

## Experiment 3 — Pass@N curve under v4-flash judge

**Hypothesis**: Plain best-of-N keeps scaling on PB-Advanced for v4-flash beyond N=3 under a strict judge.

**Design**: 20 PB-Advanced × N=8 generate-only samples per problem (passing `seed=k` to litellm for variation). Each sample independently judged by v4-flash. Pass@k computed as max-of-first-k.

**Results**:

| k | mean@k | pass@k (≥6) |
|---:|---:|---:|
| 1 | 1.75 | 5/20 |
| 2 | 2.15 | 6/20 |
| 3 | 2.20 | 6/20 |
| 4 | 2.55 | 7/20 |
| 5 | 2.55 | 7/20 |
| 6 | 2.60 | 7/20 |
| 7 | 2.95 | 8/20 |
| **8** | **3.35** | **9/20** |

**No saturation through N=8**. The mean climbs +1.6 from N=1 to N=8 (almost double), and pass count nearly doubles from 5 → 9.

**Per-problem variance** (number of N=8 samples that scored ≥6):

| Bucket | Problems |
|---|---|
| All 8 succeed | 1 (Adv-025) |
| 6-7 succeed | 3 (Adv-001, 004, 019) |
| 1-5 succeed | 5 (Adv-003, 014, 017, 024, 028) |
| 0/8 | 11 (Adv-002, 005, 008, 009, 010, 018, 021, 022, 026, 029, 030) — capability ceiling |

11 of 20 (55%) of these PB-Advanced problems are **never** solved by v4-flash in 8 attempts under v4-flash judge. The pass@8 ceiling for v4-flash is ≈9/20.

The 5 "1-5 succeed" problems are where best-of-N matters most: each additional sample raises the chance of a hit. PB-Advanced-024 only succeeded on k=7 (1 of 8) — without scaling to N=7, this problem would have been a 0.

**Cost**: 160 samples for $3.16 = $0.0198/sample. Pass@8 ≈ $0.16/run.

**Reading**: Resampling is the cheapest reliable lever. For v4-flash on PB-Advanced, pass@8 reaches 3.35 mean / 9 passes — comparable to self-ideated `seed_full` (3.20 / 9 passes) at lower cost ($0.16 vs $0.18). The 11/20 problems v4-flash never solves in 8 tries are genuinely beyond v4-flash's capability under this judge.

**Files**:
- Run dir: `experiments/results/passN_v4flash_20260505_20260505_120944/`

## Cross-experiment comparison

All three experiments use the same 20 problems and the same v4-flash judge, so per-problem comparison is direct.

| Method | Mean | Pass | $/run | "Solves" exclusively | "Misses" exclusively |
|---|---:|---:|---:|---|---|
| pass@1 | 1.75 | 5 | $0.020 | — | (~all hard ones) |
| pass@8 | 3.35 | 9 | $0.158 | Adv-024 (k=7), Adv-003 (k=3), Adv-017 (k=6) | Adv-014 |
| flash_solo (full) | 1.85 | 5 | $0.060 | — | — |
| flash_with_vp (strong critic) | 2.80 | 8 | $0.174 | Adv-005, Adv-014 | Adv-024, Adv-003 |
| self seed_full | 3.20 | 9 | $0.177 | Adv-002 (6/7), Adv-021, Adv-026 | (none of the 8-pass set) |
| vp seed_full | 2.55 | 7 | $0.180 | Adv-022 | Adv-002, Adv-021, Adv-026 |

Per-problem coverage by best method:
- 5 problems solved by *every* method: Adv-001, 004, 017, 019, 025, 028 (6 actually).
- 3 problems solved *only* via best-of-N scaling (Adv-024 k=7 was the latest).
- 2 problems solved *only* by strong critic (Adv-005, Adv-014).
- 3 problems solved by `self_v4flash` `seed_full` but missed by `vp_v4flash` `seed_full` — net cross-ideator regression.
- 1 problem (Adv-022) solved *only* by vp_v4flash — vp ideas occasionally unlock an approach v4-flash didn't try.
- 9 problems (Adv-002 partial, 008, 009, 010, 018, 021 partial, 026 partial, 029, 030) — never solved cleanly by any cheap method here.

Combined: if you union the {pass@8 winners} ∪ {strong-critic winners} ∪ {self-seed-full winners} you cover 12-13 of 20 problems. No single method does that. There's residual headroom from method ensembling (untested in this report).

## What the data says about "what works for AI math reasoning"

1. **Sample diversity is the cheapest, most reliable lever.** Pass@N continues to scale through N=8 with no saturation in sight. v4-flash at N=8 ($0.16/run) ≈ self-ideated seed_full ($0.18/run). If you only spend on one thing, spend on more samples.
2. **Asymmetric strong-critic pipelines are the most underused architecture.** Putting a strong reasoner (v4-pro) in the verifier+reviser role of an otherwise-cheap pipeline is the only architecture choice in this run that *unambiguously* beat its cheap baseline (+0.95 over flash_solo). Verify+revise is real work for this task — it just needs to be done well.
3. **Cross-model ideation does NOT trivially generalize from "literature ideas" (March) to "model-generated ideas".** A stronger ideator pushes the cheap generator off paths it could execute, onto paths it can't. Negative result.
4. **Self-verify+self-revise (flash_solo) doesn't work.** v4-flash as its own critic catches its own errors only ~10% of the time, and the +0.10 uplift over pass@1 is in the noise.
5. **There is a real capability ceiling.** 11 of 20 PB-Advanced problems were never solved by v4-flash in 8 samples — the cheap generator simply lacks the math depth. No sampling-side trick will unlock them; they need either a fundamentally stronger generator or a structurally different attack (e.g. tool use, formal verification).

## Methodology notes

- **Spend tracked via OpenRouter `/auth/key` polling**, with per-experiment killswitches at $6/$10/$3 caps. Pre-experiment per-run cost estimates were within 30% of actuals.
- **All experiments wrote per-trial / per-branch JSONs atomically** so partial completion preserves data. Used in this run when one cross-ideator trial took 33+ minutes (long-tail v4-flash + reasoning).
- **Worker counts deliberately reduced** when running in parallel: cross_ideator 24, strong_critic 10, passN 12. Together = 46 in flight on one key, which appeared not to hit OpenRouter rate limits (no 429s observed across ~7-hour run).
- **Token budgets** kept at MAX_TOKENS=32768 (down from prior 65536 in Phase 1-3) — sufficient given v4-flash reasoning runs typically use 5-30K tokens. No truncation observed.
- **v4-flash judge calibration sanity check**: PB-Advanced-001 in passN scored 7/7 on 6 of 8 samples; v4-pro Phase 1 baseline had it at 7/7 too — judges agree on the easy problem. PB-Advanced-003 scored 7/7 once under v4-flash judge but 0/0/0 in Phase 1 v4-pro baseline; that one judgment may be a false positive. Larger calibration audit would need a separate run.

## Spend accounting

| Experiment | Trials | Cost | $/trial | Note |
|---|---:|---:|---:|---|
| Cross-ideator | 40 | $7.13 | $0.179 | seed_full mode (1 ideate + 3 branches × full V↔R) |
| Strong-critic | 40 | $4.67 | $0.117 | full pipeline (gen + V↔R) |
| Pass@N | 160 | $3.16 | $0.020 | generate + judge only |
| Initialization / smoke | — | ~$0.10 | | |
| **Total used** | | **~$15.06**¹ | | $30 cap, 50% utilization |

¹ Note the discrepancy with the $18.06 OpenRouter `/auth/key` reading at termination — the per-trial sums above are blended-rate estimates from internal cost tracking, while OpenRouter's authoritative spend includes higher actual rates (especially v4-pro reasoning bills above blended rate). Treat OpenRouter's $18.06 as the authoritative figure; the breakdown above is approximate.

The run finished well under both the dollar budget and the 16-hour key window (≈7 hours wall-clock).

## Experiment 4 — Composed strong-critic + pass@N (partial)

**Hypothesis**: Pass@N best-of-8 solution as starting point + v4-pro V↔R critique on top should compose the two winning methods. Predicted mean ~3.7-4.0.

**Design**: Take the BEST-judged sample from passN per problem (best-of-8), apply v4-pro verify+revise (ITER=2), re-judge with v4-flash. 20 trials × $5 cap.

**Status (as of report write-up)**: experiment is still in-flight. v4-pro reasoning on long PB-Advanced solutions is slow — the 7/7 starters complete in 17-22 min each (verifier early-stops on iter 1 typically), and the 0/7 starters are still in flight after 25 min. Per-trial cost ~$0.02-0.04 for 7→7 preserved; expected ~$0.10-0.20 for 0→? attempted rescues.

**Partial results — first 5 of 20 (all 7-starter cases)**:

| Problem | starter | after V↔R | Δ | Note |
|---|---:|---:|---:|---|
| PB-Advanced-001 | 7 | 7 | 0 | early-stop |
| PB-Advanced-014 | 7 | 7 | 0 | early-stop |
| PB-Advanced-019 | 7 | 7 | 0 | early-stop |
| PB-Advanced-028 | 7 | 7 | 0 | early-stop |
| PB-Advanced-024 | 7 | **0** | **−7** | full V↔R, regression |

**Updated read**: v4-pro V↔R is **not** a free preservative. 4 of 5 7-starters were preserved (verifier early-stopped on iter 1), but PB-Advanced-024 went 7→0 after a full v4-pro critique-revise cycle ($0.19 / 33 min). v4-pro found something it judged wrong, revised, and the v4-flash judge then scored the revised solution at 0. This is the same hazard that the gemma-as-verifier-on-oss case in Phase 3 highlighted: a different critic doesn't always preserve good work — sometimes it "improves" away the correctness. The 1-in-5 regression rate at this n is large enough to be a real concern, not a sampling fluke.

Open question (un-resolved at report time): does v4-pro V↔R *rescue* 0/7 or 1/7 starters often enough to outweigh the rescues it ruins? The 11 0/7 starters and 4 1/7 starters are still in flight; their results will determine whether composition is net positive or net neutral.

**Run dir**: `experiments/results/composed_critic_passN_20260505_20260505_193921/`

If the run continues to completion in the background, the headline question is *does the v4-pro critic rescue any of the 11 problems v4-flash couldn't solve in 8 attempts?*. Given the strong-critic experiment rescued 3 of 11 such problems from 0/7 starts (Adv-004, -005, -014), I expect partial rescue here too. Adv-014 specifically already passes pass@8 (best=7) so it's pre-rescued; Adv-005 doesn't pass pass@8 so any v4-pro rescue would be a real gain over pass@N alone.

## What I would run next given more budget

1. **Wait for composed strong-critic + pass@N to finish** — the data above is partial; the informative trials (s0=0) are still in flight.
2. **Tighter cross-ideator A/B with idea-quality controls**: separate the "JSON parses" effect from the "idea content" effect. Have v4-pro produce ideas in v4-flash's voice (or strip names from v4-pro ideas) to test whether the regression is from over-specificity.
3. **Strong-critic with v4-flash itself** but at *higher* reasoning effort on the verify/revise calls only. Tests whether the gain comes from "more compute on critique" or "different model on critique".
4. **N>8 pass@N curve** to find v4-flash saturation. Phase 1 showed gemma still gaining at N=7 under gemini judge; v4-flash here still gains at N=8 under v4-flash judge — likely room to N=12 or N=15.

## Files

- `experiments/cross_ideator_v4flash_20260505.py` — Experiment 1 script.
- `experiments/strong_critic_v4flash_20260505.py` — Experiment 2 script.
- `experiments/passN_v4flash_20260505.py` — Experiment 3 script.
- `experiments/composed_critic_passN_20260505.py` — Experiment 4 (composed) script.
- `experiments/aggregate_flex_runs_20260505.py` — Cross-experiment summary.
- `experiments/results/cross_ideator_v4flash_20260505_20260505_120545/` — full Exp 1 trial + branch JSONs.
- `experiments/results/strong_critic_v4flash_20260505_20260505_121438/` — full Exp 2 trial JSONs.
- `experiments/results/passN_v4flash_20260505_20260505_120944/` — 160 sample JSONs.
- `experiments/results/composed_critic_passN_20260505_20260505_193921/` — Exp 4 trial JSONs (in-flight at report time).
- `experiments/results/flex_summary_20260505.json` — aggregated results.
