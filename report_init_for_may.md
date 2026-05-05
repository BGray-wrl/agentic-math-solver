# Agentic Math Solver — Project Report

*Reporting period: 2026-03-19 through 2026-04-06. Compiled 2026-05-04.*

This document summarizes the project structure, the experimental arc, and the
key findings to date. It is reconstructed from `CLAUDE.md`, the codebase, and
`agent_log.md` (which is roughly chronological but not strictly ordered — later
corrections supersede earlier preliminary entries).

---

## 1. Project Overview

The project is an agentic pipeline for solving olympiad- and research-level
math problems. The base architecture is:

```
generator → verifier ↔ reviser (loop, up to N iters) → final judge
```

Two judging modes:
- **Mode A** (with ground truth): 0–7 IMO-style score
- **Mode B** (no ground truth): `incorrect | partial | almost | correct`

Above this base, several higher-level architectures were layered in over the
course of the project:

- **Seed ideas / best-of-N** — an ideator model proposes K distinct attack
  strategies; K parallel branches each run the generate→verify↔revise loop;
  judge picks the best.
- **Cross-model pipelines** — generator and critic (verifier/reviser) are
  different models, in various combinations.
- **Agentic coding loops** — for constructive problems (Hadamard, Ramsey),
  multi-turn loops with sandboxed Python and programmatic verification.

### Repo layout

| Path | Purpose |
|---|---|
| `src/pipeline.py` | Core generate/verify/revise/judge pipeline + CLI |
| `src/utils.py` | LiteLLM (`llm()`) and direct OpenRouter (`openrouter()`) wrappers |
| `src/hadamard_checker.py`, `src/ramsey_checker.py` | Programmatic verifiers for constructive problems |
| `src/batch_eval.py` | Batch runner over selected proofbench problems |
| `prompts/pipeline/` | generator, generator_seeded, ideator, verifier, reviser, judge_gt/nogt, idea_ranker, extract_score |
| `experiments/` | One file per dated experiment; all share `experiment_template.py` |
| `experiments/devset.py` | Curated 6-problem dev set (~25 min/sweep) |
| `experiments/hadamard_agentic/` | Agentic coding loop infrastructure (sandbox, loop, prompts, e2e tests) |
| `benchmarks/` | IMO-bench, winning-gold, erdos sets, FrontierMath open problems |
| `logs/` | One JSONL per pipeline run (every model call) |
| `results/` | Selected candidate solutions and grading artifacts |

API access is via OpenRouter (`OPENROUTER_API_KEY` in `.env`).
`human_testing.py`, `human_log.md`, `docs/human_notes.md` are off-limits per
`CLAUDE.md`.

---

## 2. Experimental Arc

### Phase 1 — Build & first runs (Mar 19)

Pipeline implemented end-to-end with mock mode + JSONL logging. First real run
on IMO 2025 #1 ("sunny lines") with `gemini-3-flash-preview` failed (model
oscillated between two wrong answers) but the verifier correctly flagged real
errors at every step. A 20-problem proofbench sweep produced:

- Pre-IMO: 8/8 correct (mean 7.0/7)
- IMO-easy: 4/6 correct (mean 5.4/7)
- IMO-medium: 3/4 correct (mean 6.5/7)
- IMO-hard: 0/2 correct (mean 1.5/7)

Total cost ~$0.41. Key signal: **verifier over-approval is the dominant
failure mode** — the verifier passes incomplete proofs, killing the revise
loop.

### Phase 2 — Model & cross-judge sweeps (Mar 26–27)

- **6-model generator-only comparison** (60 problems, pass@3, Mode B):
  Qwen3.5-flash strongest (2.40/7), gemini-flash-lite worst (0.94/7).
- **IMO-medium pass@2** (Mode A, GT): nemotron-120b (44%) ≫ deepseek-v3.2 (17%).
- **Cross-judging** (nemotron ↔ deepseek; gemini ↔ gpt-5.4-mini): noisy due
  to API errors and judges failing to emit `<points>` tag.
- **Hard/open problems** (erdos-659, ramsey-hypergraphs): mostly 0/7.
  gpt-5.4-mini got 3/7 on erdos-659 (one partial result).

### Phase 3 — Judge truncation bug + retry logic (Mar 27)

Discovered that Gemini judges were truncating before reaching `<points>`,
defaulting most scores to 0. Fixes:
1. Restructured `judge_gt.md` to require `<points>N out of 7</points>` *at the
   start*, before analysis.
2. `extract_score.md` now infers from truncated text.
3. `MAX_TOKENS_JUDGE` bumped 4096 → 32000.
4. `_call_llm` got 2-retry exponential backoff (5s, 10s).

Result: error rate 15/72 → 0/72; `<points>` parse rate 14/72 → 60/60. This
**invalidated earlier "pipeline hurts" findings** — those were artifacts of
connection drops, not real regressions.

### Phase 4 — Dev set + seed ideas (Mar 27–28)

Built a curated 6-problem dev set covering sanity / boundary / hard / frontier
(`experiments/devset.py`), tuned to ~25 min single-model sweeps:

| ID | Role |
|---|---|
| PB-Basic-024 | sanity / regression canary |
| PB-Basic-028 | boundary — pipeline should help |
| PB-Basic-012 | boundary — exposes verifier over-approval |
| PB-Basic-017 | boundary — pipeline should not degrade an easy correct solution |
| PB-Basic-007 | hard stretch case |
| erdos-659 | frontier north star |

Introduced the **seed-ideas architecture**: ideator generates K distinct
strategies → K parallel branches run full pipeline → judge picks best.
Results were dramatic — see findings table in §3.

### Phase 5 — Architecture sweeps (Mar 28 – Apr 5)

A series of experiments probed *which parts* of the pipeline contribute:

- **Model diversity** (216 trials, 12 conditions): cross-verification between
  similarly-capable models helps; weak verifiers hurt; cheap ideator + strong
  pipeline is the single best condition.
- **Ideator capability scaling** — Gemini family shows *inverse* scaling (lite
  > flash > pro as ideator); OAI family shows *positive* scaling (std > mini >
  nano). Effect is family-specific, not universal.
- **Best-of-N** (N ∈ {1,3,5,7}): OSS peaks at N=3 (4.83/7); diversity uplift
  grows with N as expected; per-branch mean is low — value is in the tail.
- **Pruning ideation / ranker comparison**: 5 ranker models tested across 7
  ideas/problem. **All rank at or below random for top-1.** Idea-to-solution
  mapping is too noisy for description-only ranking.
- **Idea-prediction signal analysis** (132 trials): score distribution is
  bimodal (52.5% score 0–1, 47.5% score 6–7); ideas matter on 43% of trials;
  position bias — idea #0 wins 61% of the time vs 33% random.

### Phase 6 — Hard problems & frontier models (Apr 5)

- **Harder IMO** (10 IMO-hard + 5 IMO-medium PB-Advanced): full pipeline
  *helps more* on hard problems (+1.2 to +1.4 on IMO-hard), but only 2–3 of
  10 hard problems are crackable at all by DS/OSS. Geometry: 0/7 across every
  condition; number theory strongest.
- **Frontier probes** (`claude-opus-4.6`, `gemini-3.1-pro-preview`): Opus
  solved ramsey-hypergraphs cleanly with a sunflower construction (7/7
  confirmed by GT judge); Opus failed erdos-659 (self-corrected mid-solution
  into a hand-wave); Opus and Qwen3.6-plus *disagreed on direction* for
  erdos-1051 (Qwen: irrational; Opus: counterexample exists).
- **Qwen3.6-plus:free** got erdos-659 right on its own (Z + i√2·Z lattice +
  Landau-Ramanujan bound) but free-tier rate limits make it impractical.

### Phase 7 — Frontier Ramsey + the constructive-problem realization (Apr 5)

Two attempts at ramsey-hypergraphs with the orchestrated pipeline:

- **v1** (5 branches × 3 iters, self-verification): all 0/7. Opus produced
  71K-char solutions still scoring 0.
- **v2** (dual ideation, cross-verify, programmatic checker, synthesis,
  multi-judge consensus): best result |V|=61 (need ≥64). Synthesis genuinely
  helped (59 → 61). But **Opus regressed from a promising exploration to
  arguing impossibility** by iteration 6 — the cross-verify/revise loop
  destroyed real progress.

Comparison with Epoch AI (who solved this with Opus + 38 agentic turns +
Python REPL): **constructive problems need code execution, not LLM
proof-checking.** LLM verifiers cannot exhaustively check 2^20 subsets;
revisers will simplify away a buried-but-correct construction.

### Phase 8 — Hadamard agentic loop (Apr 5–6)

Built a multi-turn agentic loop with sandboxed Python and a programmatic
checker for the order-668 Hadamard problem. Three iterations:

- **v1**: Gemini produced math prose with no code blocks on 19/20 turns.
  Opus stuck verifying ≤4×4 cases; never scaled to 668. Burned ~$10.
- **v2**: Opus↔Gemini alternation fixed Gemini's no-code problem (34/35
  turns). `reasoning_effort=high` *broke* Opus (40% no-code turns). Hit
  monthly OpenRouter cap mid-run.
- **v2 resume**: Both branches completed 50 turns. Best PAF defect ~2688
  (need 0). **Critical bug discovered**: sandbox stdout was capped at 8KB; a
  668×668 CSV is ~900KB, so the checker had been parsing truncated fragments
  as 4×668 matrices. The "best_order=4" across the entire v2 run was a
  measurement artifact, not the model's real output.
- **v3 fix + e2e**: `sandbox_exec.py` writes via `HADAMARD_OUTPUT_DIR` shared
  dir; checker reads `candidate.csv` from file. New rich feedback:
  orthogonality %, perfect rows, max off-diagonal, quality 0–100. Stale-file
  cleanup between turns. **58/58 e2e tests pass**, including the exact
  668×668 failure scenario from v2. Pipeline ready for a real run; no
  successful real-run logged yet.

---

## 3. Headline Findings

### What works

| Technique | Effect |
|---|---|
| **Seed ideas (ideator + K branches + judge best)** | Largest single uplift. Qwen3.5-flash 0.50 → 5.67/7 dev set; deepseek-v3.2 1.50 → 5.83 on new dev set. Often 1/3 branches hits 7/7 while the others miss. |
| **Verify ↔ revise loop (with retries)** | Helps strong generators meaningfully. Gemini-3-flash 5.83 → 6.83/7 (+1.0); gpt-oss-120b +2.0. Helps *more* on harder problems. |
| **Cheap ideator + strong pipeline** | Best single condition in diversity sweep (5.28/7, +2.0 vs ds baseline). Lite generates simpler, more actionable ideas. |
| **Cross-verification between similar-capability models** | DS↔OSS mutual benefit confirmed (+1.11 for ds, +0.78 for oss). |
| **Programmatic verification for constructive problems** | The Hadamard / Ramsey checkers make construction debugging tractable in a way LLM verification cannot. |
| **File-based I/O in agentic sandbox** | Bypasses the 8KB stdout cap that silently broke 100+ Hadamard turns. |
| **Retry with exponential backoff on `_call_llm`** | Eliminated the spurious "pipeline hurts" finding from Phase 1. |

### What doesn't work

| Technique | Effect |
|---|---|
| **Idea ranking from descriptions** | All 5 rankers (cheap and expensive, same and cross family) at or below random for top-1. The "always pick idea #0" baseline is 61% — hard to beat. |
| **Pruning N=7 → N=3 with a ranker** | 2.67/7 vs 3.67/7 random vs 3.83/7 all-7. Active negative value. |
| **Cross-model pipeline with mismatched capability** | Flash-lite as verifier hurts (~−0.8 vs baseline). Cross-model on IMO-medium underperformed both same-model baselines. |
| **More iterations on construction problems** | Cross-verify/revise destroyed Opus's promising Ramsey exploration over 6 iterations, ending in a confidently-wrong impossibility claim. |
| **`reasoning_effort=high` on Opus in code-writing context** | Made Opus produce thinking prose without code on 40% of turns. |
| **Stronger ideator on the Gemini family** | Inverse: lite (5.83) > flash (4.67) > pro (3.83) in full pipeline. |

### Recurring failure modes

1. **Verifier over-approval** — passes incomplete/wrong solutions on iter 1,
   killing the revise loop. Worst with weaker verifiers.
2. **Judge truncation** — long ground-truth prompts overflow output, score
   defaults to 0. Mitigated but not fully solved.
3. **Construction problems treated as proof problems** — LLM verifiers cannot
   validate 2^20 subset claims; revisers simplify away buried correct ideas.
4. **OpenRouter reliability** — connection drops, malformed JSON, monthly
   credit caps. The retry layer made the difference between unusable and
   usable for batch runs.
5. **Bimodal scoring** — solutions are mostly 0/7 or 7/7; "almost correct" is
   rare. Pass-rate matters as much as means.

---

## 4. Cost & Operational Notes

- Phase 1 runs: ~$0.40 for 20 problems × 2 iters.
- Cross-judge runs hit ~$4 with re-grading.
- Frontier Ramsey v2: ~$15–20 for one trial.
- Hadamard v1+v2+resume+v3: ~$15–20 across runs (much wasted on the stdout bug).
- **Always smoke-test with `--mock` first.**
- **Lessons captured in CLAUDE.md**: store full solution text (no
  truncation); timestamp output filenames; use pass@1 for exploration; lock
  `make_logger` when parallelizing; parallelize branches *within* trials.

---

## 5. Current State (2026-04-06 last entry)

- **Pipeline**: stable, with retries, hardened judge, file-based logging.
- **Dev set**: 6 problems, 25 min/sweep, role-tagged for diagnostics.
- **Best architecture**: seed ideas (cheap ideator) + full pipeline + GT
  judge. ~7.00/7 on dev set with qwen3.5-flash or gemini-3-flash.
- **Frontier targets**:
  - `erdos-659`: solved by qwen3.6-plus:free; one full-pipeline 7/7 from
    qwen3.5-flash with judge confirmation but external review found
    inaccuracies — judge may be too lenient on long GTs.
  - `ramsey-hypergraphs`: solved by Opus alone in a probe (7/7 GT-confirmed);
    orchestrated pipeline regressed it. Best orchestrated attempt: |V|=61.
  - `erdos-1051-aletheia`: model disagreement on direction; expert review
    needed.
- **Hadamard**: v3 pipeline ready for real run after the stdout-truncation
  fix; e2e tests green; no successful real run logged yet.

### Known issues

- `agent_log.md` contains superseded conclusions and isn't strictly ordered.
- Multiple dated experiment scripts may carry stale constants from prior runs.
- Single LLM judges are too lenient for frontier problems with long GTs.
- The iteration-depth experiment hung at 0% CPU for 6+ hours and was killed.
- Top-level `README.md` is essentially empty.

### Suggested next steps

1. Real run of Hadamard v3 with the file-based feedback loop.
2. Replace verify↔revise with **generate code → execute → check → feed errors
   back** for constructive problems generally.
3. Investigate the "cheap ideator wins" effect — Gemini-specific or general?
4. Re-run IMO-medium baselines with the hardened judge + retries to produce a
   clean reference number for the current best architecture.
5. Harden frontier judging with programmatic checks, multi-judge consensus,
   or manual review before claiming solves.
6. Write a real top-level `README.md`; index the experiment scripts as
   current / superseded / mock-only / exploratory.
