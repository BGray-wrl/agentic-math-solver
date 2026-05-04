## Pipeline Implementation - 2026-03-19T17:02:51

Implemented the full generator → verifier ↔ reviser → judge pipeline.

Files created/modified:
- `CLAUDE.md`: updated project description, assignment structure, setup deps (added `litellm`), run commands
- `src/utils.py`: added `llm()` LiteLLM wrapper for OpenRouter
- `prompts/pipeline/generator.md`: system prompt for solution generation
- `prompts/pipeline/verifier.md`: step-by-step verifier prompt with `VERDICT: correct|issues_found` machine tag
- `prompts/pipeline/reviser.md`: reviser prompt with `{problem}`, `{solution}`, `{critique}` placeholders
- `prompts/pipeline/judge.md`: dual-mode judge (Mode A: 0–7 score with GT; Mode B: 4-label without GT)
- `src/pipeline.py`: full pipeline with `generate/verify/revise/judge` functions, `run_pipeline()`, JSONL logging, mock mode, and CLI

Smoke test (`--mock`) passed: 2 loop iterations (1 issues_found → revise, 1 correct → early stop), judge ran, 5 JSONL records written to `logs/pipeline_20260319_170251.jsonl`.

## Pipeline Real Run - IMO Problem 1 - 2026-03-19T17:30:00

Model: `openrouter/google/gemini-3-flash-preview`, 2 iterations, max_tokens=2048, no ground truth (Mode B judge)
Problem: `benchmarks/winning-gold/imo01.txt` (IMO 2025 #1 — "sunny lines" combinatorics)
Log: `logs/pipeline_20260319_172742.jsonl`

Correct answer: k ∈ {0, 1, 2, 3} for all n ≥ 3

**Iteration trace:**
1. **Generate**: Model claimed k=0 only. Incorrect — missed constructions with sunny lines.
2. **Verify 1**: Correctly caught the error (k>0 is possible; gave k=1 counterexample for n=3). VERDICT: issues_found ✓
3. **Revise 1**: Overcorrected — claimed k can be any value in {0,...,n}. Wrong direction.
4. **Verify 2**: Correctly flagged the incomplete/wrong construction. Unfortunately added a misleading note suggesting k=0 is the known result. VERDICT: issues_found ✓
5. **Revise 2**: Reverted to k=0. Wrong again.
6. **Judge (Mode B)**: Correctly classified final solution as `incorrect`. Identified k=1 counterexample. ✓

**Outcome:** Pipeline did not reach the correct answer (k ∈ {0,1,2,3}).
- Verifier was useful: both iterations correctly flagged real errors.
- The model oscillated between two wrong answers without converging.
- Problem likely requires stronger model or more iterations with explicit guidance.

Estimated cost: ~$0.03 (well under budget).

## Pipeline Batch Run - IMO-bench proofbench (3 problems) - 2026-03-19T17:40:00

Model: `openrouter/google/gemini-3-flash-preview`, 2 iterations max, max_tokens=2048, Mode B judge
Problems: 2× pre-IMO, 1× IMO-easy from benchmarks/IMO-bench/proofbench.csv

| Problem | Level | Category | iters | stopped_early | judge |
|---------|-------|----------|-------|--------------|-------|
| PB-Basic-002 | pre-IMO | Algebra | 1 | ✓ | correct |
| PB-Basic-018 | pre-IMO | Number Theory | 2 | ✓ | correct |
| PB-Basic-001 | IMO-easy | Algebra | 1 | ✓ | correct |

All three: judge classified as `correct`. All stopped early (verifier satisfied on first or second pass).
- PB-Basic-002: early stop at iter 1 (single clean proof via AM-GM + Cauchy-Schwarz)
- PB-Basic-018: 1 revision needed (verifier caught errors in Pell equation indexing), iter 2 passed
- PB-Basic-001: early stop at iter 1 (linearity argument + case analysis clean)

Estimated total cost: ~$0.06 for all three runs.

## Batch Evaluation Run - 20 proofbench problems - 2026-03-19T18:00:00

Model: gemini-3-flash-preview, 2 iterations, 20 problems (8 pre-IMO + 6 IMO-easy + 4 IMO-medium + 2 IMO-hard)
Ground truth passed to judge (Mode A, 0-7 scoring).

### Results by level:
| Level      | n  | correct/7/7 | avg score | notes |
|------------|----|---------|-----------|----|
| pre-IMO    | 8  | 8/8     | 7.0/7     | all early stopped |
| IMO-easy   | 6  | 4/6     | 5.4/7     | geometry (2/7) and NT (4/7) failures |
| IMO-medium | 4  | 3/4     | 6.5/7     | one 6/7 (minor gap) |
| IMO-hard   | 2  | 0/2     | 1.5/7     | 3/7 (missed solution branch), 0/7 (wrong constant) |

### Phase 2: PB-Advanced-018 (0/7 IMO-hard combinatorics snake problem)
- gemini-3.1-pro, 2 iters: still 0/7. Pro model gave up mid-response (empty solution after realizing approach was wrong).
- gemini-3-flash, 5 iters: still 0/7. Claimed a(n)=n+1 (off by O(n) — correct is O(n²/3)) across all 5 iterations with no meaningful progress.
- Conclusion: this problem is beyond current pipeline capability regardless of model/iteration scaling.

Total estimated cost for all runs: ~$0.41 (well under $0.50 budget).

## PB-Advanced-006 Ablation - 2026-03-19T18:35:00

Problem: f:Z→Z with f(x−f(xy))=f(x)f(1−y) (IMO-hard, Algebra, 5 solutions total)
Previous batch score: 3/7

| Variant | Model | Iters | Stopped early | Score | Notes |
|---------|-------|-------|--------------|-------|-------|
| Baseline | gemini-3-flash-preview | 3 | N | partial | Found f=0,1,x; missed mod-2 and mod-3 solutions |
| Pro 3 iters | gemini-3.1-pro-preview | 3 | N | 0/7 | Collapsed — scattered notes, no real progress |
| Flash 8 iters | gemini-3-flash-preview | 8 | Y (iter 1) | 1/7 | Verifier passed too early; judge caught 2 missing periodic solutions |

Correct solutions: f=0, f=1, f=x, f=parity(mod-2), f=mod-3 periodic.
Best variant was baseline (flash, 3 iters) with "partial". Neither more iters nor stronger model helped.

## PB-Advanced-006 — gemini-3-pro-preview (3 iters, 4096 tokens) - 2026-03-19T19:08:00

Score: 0/7. Model produced truncated, fragmented scratch work across all iterations — never reached a coherent proof structure. The judge noted "unintelligible as a complete proof." Worse than both 3.1-pro (also 0/7) and flash (partial). The 3.x Pro models appear to struggle with this specific hard functional equation more than flash.

## PB-Basic IMO-easy batch (5 problems, flash-preview, 2 iters, 4096 tokens) - 2026-03-19T19:30:00

Problems: PB-Basic-003, 005, 009, 019, 020 — all IMO-easy, non-geometry, PB-Basic only.

| ID | Category | Score | Notes |
|----|----------|-------|-------|
| PB-Basic-003 | Algebra | 1/7 | Verifier passed too early (iter 1 ✓); judge caught missing solution family |
| PB-Basic-005 | Algebra | 2/7 | Verifier passed too early; judge caught wrong degree bound conclusion |
| PB-Basic-009 | Combinatorics | 7/7 | 2 iters, never converged (issues_found both) but final solution correct |
| PB-Basic-019 | Number theory | 7/7 | Clean 1-iter early stop |
| PB-Basic-020 | Number theory | 7/7 | Clean 1-iter early stop |

Mean: 4.80/7. Both failures (003, 005) caused by verifier over-approving on iteration 1 — key issue is verifier leniency on completeness (missing solution families, wrong degree bound).

## 6-Model Comparison — 60 problems, generator-only, Mode B judge - 2026-03-26T22:09:43

Script: `experiments/compare_models_easy_20260326.py`
Problems: 30 PB-Basic + 30 PB-Advanced (all levels), generator-only (no verifier/reviser loop)
Seeds: 3 | Judge: gemini-3-flash-preview (Mode B, no ground truth)
Results: `experiments/results/compare_models_easy_20260326_220943.json`

| Model | Mean±Std | pass rate (correct) | n |
|---|---|---|---|
| qwen3.5-flash-02-23 | 2.395±1.026 | 128/177 | 177 |
| deepseek-v3.2-speciale | 2.331±1.196 | 93/124 | 124 ⚠️ |
| deepseek-v3.2 | 2.136±1.171 | 109/177 | 177 |
| nemotron-3-super-120b | 1.914±1.381 | 105/174 | 174 |
| step-3.5-flash | 1.438±1.476 | 83/178 | 178 |
| gemini-3.1-flash-lite | 0.944±1.109 | 34/180 | 180 |

Key findings:
- Qwen3.5-flash is strongest overall and most consistent (lowest std)
- deepseek-v3.2-speciale had 56/180 API errors (very slow ~18min/trial avg); score unreliable
- gemini-flash-lite scores 0/7 correct at IMO-hard; not viable above pre-IMO difficulty
- step-3.5-flash is bimodal: correct or wrong, almost no partial credit
- nemotron underperforms for its size; scores higher at IMO-hard than IMO-medium (anomalous)

## IMO-medium pass@2 — nemotron vs deepseek, generate-only, GT judge (Final) - 2026-03-27T01:52:32

Script: `experiments/imo_medium_pass2_20260326.py` + retry via `experiments/imo_medium_pass2_retry.py`
Problems: 18 IMO-medium (10 PB-Advanced + 8 PB-Basic) | Seeds: 2 (pass@2) | Judge: gemini-3-flash-preview (Mode A, GT)
Pass threshold: ≥6/7 | Results: `experiments/results/imo_medium_pass2_merged_20260327_015232.json`

| Model | Mean±Std | pass@2 | n | Errors |
|---|---|---|---|---|
| nemotron-3-super-120b | 2.50±3.21 | 44.4% (8/18) | 36 | 0 |
| deepseek-v3.2 | 0.89±1.97 | 16.7% (3/18) | 35 | 1 |

Original run had 10 API 402 credit failures (9 DeepSeek, 1 Nemotron); retry filled these in.
Remaining 1 error: PB-Advanced-011/deepseek/seed=42 — malformed API response (not credits).
Score distribution is highly bimodal (mostly 0s and 7s) — consistent with IMO 0/1/6/7 rubric.
Nemotron substantially outperforms DeepSeek on IMO-medium in generate-only mode.
Several problems show seed variance (e.g. `[0/7]`) suggesting they sit at the model capability boundary.

## Cross-Judged pass@2 — nemotron vs deepseek, IMO-easy, ground-truth judging - 2026-03-27T01:22:51

Script: `experiments/cross_judge_imo_20260326.py`
Problems: 24 IMO-easy only | Seeds: 2 (pass@2) | Judge: cross (nemotron judges deepseek; deepseek judges nemotron)
Ground truth from combined-benchmarks.csv (Mode A, 0–7 scale) | pass threshold: ≥6/7
Results: `experiments/results/cross_judge_imo_20260327_012251.json`

| Generator | Judge | Mean/7 | pass@2 | n |
|---|---|---|---|---|
| nemotron-120b | deepseek-v3.2 | 2.256 | 45.5% | 43/48 |
| deepseek-v3.2 | nemotron-120b | 0.744 | 18.2% | 39/48 |

Data quality issues: 14 API errors (nemotron OpenRouter malformed JSON); 35 score parse failures
(judges not outputting `<points>N out of 7</points>` format, defaulted to 0 — understates DeepSeek score).
Run ended early on last 2 trials due to insufficient OpenRouter credits (402 error).
Results directionally valid but noisy — recommend re-run with stable judge model and topped-up credits.

## Gemini 3 flash vs GPT-5.4 mini Cross-Judge — 2026-03-27T02:34:27

Script: `experiments/gemini_gpt_cross_judge_20260326.py`
Problems: 10 PB-Advanced/IMO-easy + 8 PB-Basic/IMO-medium = 18 problems
API: Direct (GEMINI_API_KEY → `gemini/gemini-3-flash-preview`, OPENAI_API_KEY → `openai/gpt-5.4-mini`)
Seeds: 2 (pass@2) | Ground truth judging (Mode A, 0–7) | Parallelized (12 workers)

### Results (after re-grading truncated verdicts):
| Generator | Judge | Mean/7 | pass@2 | n | Parse fails |
|---|---|---|---|---|---|
| gemini-3-flash-preview | gpt-5.4-mini | 1.194±2.481 | 22.2% | 36 | 0/36 |
| gpt-5.4-mini | gemini-3-flash-preview | 0.500±1.518 | 11.1% | 36 | 8/36 (still 0) |

**Gemini → GPT judge (fully reliable):**
- IMO-easy: mean=0.45/7, pass@2=10%
- IMO-medium: mean=2.125/7, pass@2=37.5%
- Best: PB-Basic-029 (7/7 both seeds), PB-Basic-012 (7+6), PB-Basic-024 (7+0)

**GPT → Gemini judge (partial data — 8/36 still defaulted 0):**
- IMO-easy: mean=0.70/7, pass@2=20%
- IMO-medium: mean=0.25/7, pass@2=0%
- Best: PB-Advanced-019 (7+0), PB-Advanced-028 (6+0)

### Data quality issues:
- Initial run: 31/36 Gemini verdicts truncated (Gemini capping output at ~150 tokens with large input)
- Re-graded with `max_tokens=16384`: reduced to 8/36 failures — very long PB-Advanced ground truth LaTeX docs still overflowing
- Root cause: PB-Advanced ground truths avg 2,965 chars (max 6,819); combined with problem + solution, Gemini output gets capped before `<points>` tag

### Key observations:
- Both models struggle significantly on this harder problem set (IMO-easy PB-Advanced and IMO-medium)
- GPT-5.4-mini appears weaker than Gemini on these problems (lower pass@2), though the 8 remaining parse failures understate its score
- Gemini performs better on IMO-medium (2.125/7) than IMO-easy (0.45/7) — likely because PB-Advanced/IMO-easy problems are research-frontier style
- High score variance ([0/6], [7/0]) suggests problems sit at model capability boundary

### Costs:
- Original run: $3.02 (72 trials)
- Re-grade run: $1.09 (31 trials, max_tokens=16384)
- Total: $4.11

## Model Comparison — Hard/Open Problems - 2026-03-27T02:51:11

Ran 6 models on 2 hard problems (erdos-659, ramsey-hypergraphs) with simple generate→judge pipeline. Judge: gemini-3-flash-preview with ground-truth, 0–7 IMO scoring.

**Results:**
| Model | erdos-659 | ramsey-hypergraphs | Mean |
|---|---|---|---|
| nemotron-3-super-120b-a12b | 0/7 | 0/7 | 0.0 |
| deepseek-v3.2 | 0/7 | 0/7 | 0.0 |
| deepseek-v3.2-speciale | 0/7 | 0/7 | 0.0 |
| qwen3.5-flash-02-23 | error (judge returned None) | 0/7 | 0.0 |
| gemini-3-flash-preview | 0/7 | 0/7 | 0.0 |
| gpt-5.4-mini | 3/7 | 0/7 | 1.5 |

**Key observations:**
- Only gpt-5.4-mini scored above 0, getting 3/7 on erdos-659 (partial progress)
- All models scored 0/7 on ramsey-hypergraphs — no model made meaningful progress
- deepseek-v3.2-speciale generated massive outputs (120k chars) but scored 0 — verbose ≠ correct
- gpt-5.4-mini was fastest (7-8s generation) while deepseek models took 20+ minutes
- One qwen/erdos-659 trial failed: judge model returned None content (Gemini reasoning-only response)

Script: `experiments/model_comparison_hard_20260326.py`
Results: `experiments/results/model_comparison_hard_20260327_025111.json`

## Full Pipeline IMO-medium pass@1 — nemotron vs deepseek - 2026-03-27T03:11:30

Full pipeline (generate → verify ↔ revise → judge) on 18 IMO-medium problems, pass@1 (seed=42), 3 verify/revise iterations max. Judge: gemini-3-flash-preview with ground truth (Mode A, 0–7).

| Model | Mean±Std | pass@1 | Avg iters | Stopped early | Errors |
|---|---|---|---|---|---|
| nemotron-120b | 1.93±3.07 | 26.7% (4/15) | 2.53 | 6/15 | 3 |
| deepseek-v3.2 | 2.60±3.16 | 33.3% (5/15) | 2.87 | 2/15 | 3 |

Scores highly bimodal (0s and 7s). Compared to generate-only pass@2 baseline:
- DeepSeek: 16.7% → 33.3% — reviser loop doubles pass rate
- Nemotron: 44.4% → 26.7% — drops, but confounded by pass@2→pass@1 and errors
- Nemotron verifier over-approves (stopped early 6/15, many scoring 0/7 after)
- DeepSeek runs full iterations and benefits from revision

Script: `experiments/full_pipeline_imo_medium_pass1_20260327.py`
Results: `experiments/results/full_pipeline_imo_medium_pass1_20260327_031130.json`

## Full Pipeline — Hard/Open Problems (6 models) - 2026-03-27T04:25:12

Full pipeline (generate → verify ↔ revise → judge, 3 iters) on erdos-659 and ramsey-hypergraphs, pass@1 (seed=42). Judge: gemini-3-flash-preview with ground truth (0–7).

| Model | erdos-659 | ramsey-hyp | Iters (erdos/ramsey) | Notes |
|---|---|---|---|---|
| nemotron-120b | 0/7 | 0/7 | 1/1 | Verifier over-approves both |
| qwen3.5-flash | **7/7** | 0/7 | 1/3 | Judge gave 7/7 on erdos-659 |
| gemini-3-flash | 0/7 | 0/7 | 1/3 | Verifier over-approves erdos |
| gpt-5.4-mini | 0/7 | 0/7 | 3/3 | Dropped from 3/7 baseline |
| deepseek-v3.2 | 0/7 | 0/7 | 3/1 | Early stop on ramsey |
| deepseek-v3.2-speciale | error | error | — | 429 rate-limited both trials |

**Key findings:**
- qwen3.5-flash got 7/7 from the judge on erdos-659, but external verification found inaccuracies in the writeup — the general structure/approach was correct but details had errors. This suggests the judge (gemini-3-flash) may be too lenient on problems with long ground-truth solutions.
- gpt-5.4-mini regressed from 3/7 → 0/7 on erdos-659 — verify/revise loop hurt
- Nemotron/Gemini verifiers over-approve (stop at iter 1 with 0/7 solutions)
- deepseek-v3.2-speciale hit upstream rate limits on both problems (429 errors)
- ramsey-hypergraphs remains unsolved by all 6 models

Scripts: `experiments/full_pipeline_hard_fast_20260327.py`, `experiments/full_pipeline_hard_deepseek_20260327.py`
Results: `experiments/results/full_pipeline_hard_fast_20260327_040931.json`, `experiments/results/full_pipeline_hard_deepseek_20260327_042512.json`

## Cross-Model Pipeline — Diversity Hypothesis - 2026-03-27T04:43:44

Full pipeline with cross-model verify/revise on 18 IMO-medium problems, pass@1 (seed=42), 3 iters. Generator and critic (verifier/reviser) use different models. Judge: gemini-3-flash with GT.

| Condition | Generator | Critic | pass@1 | Mean/7 | Stopped early | Errors |
|---|---|---|---|---|---|---|
| nemotron-self (baseline) | nemotron | nemotron | **26.7%** | **1.93** | 6/15 | 3 |
| deepseek-self (baseline) | deepseek | deepseek | **33.3%** | **2.60** | 2/15 | 3 |
| deepseek→nemotron (cross) | deepseek | nemotron | 17.6% | 1.53 | 9/17 | 1 |
| nemotron→deepseek (cross) | nemotron | deepseek | 6.2% | 0.69 | 1/16 | 2 |

**Conclusion: Model diversity hurts.** Both cross-model conditions underperform both same-model baselines.
- Nemotron as cross-critic over-approves (stopped early 9/17, most scoring 0/7)
- DeepSeek as cross-critic is too harsh/slow, revisions degrade rather than improve
- Self-critique outperforms cross-critique — models understand their own reasoning style better

Script: `experiments/cross_model_pipeline_20260327.py`
Results: `experiments/results/cross_model_pipeline_20260327_20260327_044344.json`

## Judge Truncation Bug Fix - 2026-03-27T06:30:00

Discovered that the Gemini judge was truncating responses before reaching the `<points>` tag at the end, causing most scores to parse as 0/7. The first fast baseline run had only 14/72 verdicts with `<points>`.

**Fixes applied:**
1. `prompts/pipeline/judge_gt.md`: Restructured to require `<points>N out of 7</points>` at the **beginning** of the response, before analysis
2. `prompts/pipeline/extract_score.md`: Now infers scores from truncated analysis text instead of returning "not_found"; defaults to "0"
3. `MAX_TOKENS_JUDGE` bumped from 4096 → 32000 across all experiment scripts
4. `src/pipeline.py` `ideate()`: Fixed JSON parsing for LaTeX backslashes (`Invalid \escape` errors)

After fix: 57/72 verdicts with `<points>` in fast baseline (up from 14/72).

## Fast Baseline v2 (Hardened Judge) - 2026-03-27T06:50:00

6 fast models × 6 dev-set problems × 2 modes (generate-only + full pipeline). Seed=42.

| Model | Generate mean | Generate pass | Full mean | Full pass | Notes |
|---|---|---|---|---|---|
| qwen3.5-flash-02-23 | 0.50/7 | 0/6 | — | — | All 6 full trials errored (OpenRouter drops) |
| gpt-5.4-mini | 0.00/7 | 0/6 | 0.17/7 | 0/6 | |
| gemini-3-flash-preview | 1.67/7 | 1/6 | 0.25/7 | 0/4 | 2 errors |
| gpt-oss-120b | **2.50/7** | **2/6** | 0.00/7 | 0/3 | 3 errors |
| nemotron-3-super-120b-a12b | 1.40/7 | 1/5 | 0.00/7 | 0/4 | 1 gen error, 2 full errors |
| gemini-3.1-flash-lite-preview | 0.00/7 | 0/6 | 0.40/7 | 0/5 | 1 error |

**Key finding:** Full pipeline still hurts. 15/72 trials errored (OpenRouter connection drops). gpt-oss-120b best generator.

Script: `experiments/devset_baseline_fast_20260327.py`
Results: `experiments/results/devset_baseline_fast_20260327_065052.json`

## DeepSeek Baseline v2 (Hardened Judge) - 2026-03-27T07:45:00

2 DeepSeek models × 6 dev-set problems × 2 modes. Seed=42.

| Model | Generate mean | Generate pass | Full mean | Full pass | Notes |
|---|---|---|---|---|---|
| deepseek-v3.2 | 1.60/7 | 1/5 | 0.50/7 | 0/2 | 1 gen error, 4 full errors |
| deepseek-v3.2-speciale | 0.25/7 | 0/4 | — | — | 2 gen errors, all 6 full errored |

High error rate due to DeepSeek's long generation times + OpenRouter timeouts. speciale nearly unusable via OpenRouter for full pipeline.

Script: `experiments/devset_baseline_deepseek_20260327.py`
Results: `experiments/results/devset_baseline_deepseek_20260327_*.json`

## Seed Ideas Pipeline - 2026-03-27T07:30:00

Architecture: ideate(3 ideas) → 3 parallel branches of (generate conditioned on idea → verify ↔ revise × 2 iters) → judge all → pick best.
7 models × 6 dev-set problems. Seed=42.

| Model | Mean | Pass | Notes |
|---|---|---|---|
| **qwen3.5-flash-02-23** | **5.67/7** | **5/6** | Best overall — up from 0.50/7 baseline |
| **gemini-3-flash-preview** | **4.67/7** | **4/6** | Up from 1.67/7 baseline |
| deepseek-v3.2 | 1.83/7 | 1/6 | |
| gpt-oss-120b | 1.33/7 | 1/6 | |
| gemini-3.1-flash-lite-preview | 1.33/7 | 1/6 | |
| gpt-5.4-mini | 1.17/7 | 1/6 | |
| nemotron-3-super-120b-a12b | 0.00/7 | 0/6 | Broken — likely bare \boxed outputs |

**0 errors** across all 42 trials (vs 15/72 and 13/24 in baselines).

Branch diversity clearly works: winning scores typically come from 1/3 branches (e.g., `[7, 1, 1]`). PB-Advanced-023 is 0/7 across all models/approaches — genuinely hard.

**Conclusion:** Best-of-N via seed ideas massively outperforms both generate-only and verify/revise loop. The pipeline's value is in idea diversity, not self-correction. qwen3.5-flash is cheapest model but best performer with seed ideas.

Script: `experiments/seed_ideas_devset_20260327.py`
Results: `experiments/results/seed_ideas_devset_20260327_*.json`

## Retry Logic + Fast Baseline v3 - 2026-03-27T19:04:00

Added 2-retry with exponential backoff (5s, 10s) to `_call_llm` in `src/pipeline.py`. Dropped nemotron (broken bare \boxed outputs). Re-ran fast baseline.

**Result: 0 errors (down from 15/72), 100% judge parsing (60/60 with `<points>`).**

14 retries fired and all recovered. This completely changes the pipeline narrative — full pipeline now **helps** for stronger models:

| Model | Generate | Full | Delta |
|---|---|---|---|
| gemini-3-flash-preview | 2.50/7 | **5.00/7** | **+2.50** |
| qwen3.5-flash-02-23 | 2.50/7 | 3.83/7 | +1.33 |
| gpt-oss-120b | 1.00/7 | 1.33/7 | +0.33 |
| gpt-5.4-mini | 0.00/7 | 0.17/7 | +0.17 |
| gemini-flash-lite | 0.17/7 | 0.17/7 | 0 |

Prior "pipeline hurts" finding was mostly an artifact of connection drops killing full-pipeline trials (more API calls = more failure chances). With reliable calls, verify/revise genuinely improves scores for gemini-3-flash and qwen.

Script: `experiments/devset_baseline_fast_20260327.py`
Results: `experiments/results/devset_baseline_fast_20260327_190414.json`

## Dev Set Optimization — PB-Advanced → PB-Basic Swaps - 2026-03-27T22:00:00

Swapped all 4 slow PB-Advanced problems for faster PB-Basic alternatives in `experiments/devset.py`:

| Old | New | Role | Speed improvement |
|---|---|---|---|
| PB-Advanced-014 (1124s) | PB-Basic-028 (~120s) | boundary-pipeline-helps | ~9× |
| PB-Advanced-023 (616s) | PB-Basic-012 (~149s) | boundary-verifier-bug | ~4× |
| PB-Advanced-026 (327s) | PB-Basic-017 (~79s) | boundary-pipeline-hurts | ~4× |
| PB-Advanced-006 (1150s) | PB-Basic-007 (~120s) | hard | ~10× |

Candidates validated via `experiments/sanity_check_candidates.py`. Estimated iteration time: ~3-4 min single model (down from ~19 min).

## New Dev Set Baseline - 2026-03-27T23:51:00

6 models × 6 new problems × 2 modes (generate + full). Seed=42. Retries enabled. **25 min wall time, 0 errors, 72/72 `<points>` parsed.**

| Model | Generate | Full | Delta |
|---|---|---|---|
| **gemini-3-flash-preview** | 5.83/7 (5/6) | **6.83/7 (6/6)** | **+1.00** |
| qwen3.5-flash-02-23 | 3.83/7 (3/6) | 4.83/7 (4/6) | +1.00 |
| gpt-oss-120b | 2.67/7 (2/6) | 4.67/7 (4/6) | **+2.00** |
| deepseek-v3.2 | 1.50/7 (1/6) | 2.33/7 (2/6) | +0.83 |
| gemini-flash-lite | 1.17/7 (1/6) | 1.33/7 (1/6) | +0.16 |
| gpt-5.4-mini | 0.33/7 (0/6) | 0.00/7 (0/6) | -0.33 |

Per-problem (generate/full):
```
                    gpt-5.4-mini  gemini-3-flash  qwen3.5-flash  gpt-oss-120b  deepseek-v3.2  gemini-lite
PB-Basic-007 hard         0/0          6/6            1/1           1/7           1/0          0/1
PB-Basic-012 verifier     0/0          7/7            7/7           7/7           0/0          0/0
PB-Basic-017 hurts        1/0          7/7            7/7           7/7           7/7          7/6
PB-Basic-024 sanity       1/0          1/7            7/7           1/7           1/7          0/1
PB-Basic-028 helps        0/0          7/7            1/0           0/0           0/0          0/0
erdos-659    frontier     0/0          7/7            0/7           0/0           0/0          0/0
```

**Findings:** Full pipeline helps across the board (except gpt-5.4-mini). gemini-3-flash dominates at 6/6 full pipeline. gpt-oss-120b biggest beneficiary (+2.00). erdos-659 only solved by gemini-3-flash.

Script: `experiments/devset_baseline_fast_20260327.py`
Results: `experiments/results/devset_baseline_fast_20260327_235126.json`

## Seed Ideas on New Dev Set - 2026-03-28T01:51:00

6 models × 6 new problems × 3 ideas per trial. Seed=42, 2 verify/revise iters per branch. Retries enabled. **76 min wall time, 1 error (gpt-oss timeout on erdos-659).**

| Model | Mean | Pass | vs Baseline Generate | vs Baseline Full |
|---|---|---|---|---|
| **qwen3.5-flash-02-23** | **7.00/7** | **6/6** | +3.17 | +2.17 |
| **gemini-3-flash-preview** | **7.00/7** | **6/6** | +1.17 | +0.17 |
| deepseek-v3.2 | 5.83/7 | 5/6 | +4.33 | +3.50 |
| gpt-oss-120b | 5.40/7 | 4/5 | +2.73 | +0.73 |
| gemini-flash-lite | 2.50/7 | 2/6 | +1.33 | +1.17 |
| gpt-5.4-mini | 1.17/7 | 1/6 | +0.84 | +1.17 |

**qwen3.5-flash and gemini-3-flash both achieve perfect 7.00/7** on seed ideas — qwen jumps from 3.83/7 generate-only.

Branch diversity patterns: winning scores typically come from 1/3 branches (e.g., `[7, 7, 1]`, `[7, 6, 0]`). PB-Basic-028 and erdos-659 remain hard for weaker models even with 3 attempts. deepseek-v3.2 massive beneficiary (+4.33 vs generate).

**Seed ideas + full pipeline > full pipeline > generate-only** confirmed on new dev set.

Script: `experiments/seed_ideas_devset_20260327.py`
Results: `experiments/results/seed_ideas_devset_20260328_015120.json`

## Seed Ideas Generate-Only + Full 4-Way Comparison - 2026-03-28T02:37:00

Added `--generate-only` flag to seed ideas script (sets ITERATIONS=0, skips verify/revise). Ran on new dev set. **34 min wall time, 0 errors.**

Full comparison across all 4 modes (6 models × 6 problems, seed=42):

| Model | Generate | Full Pipeline | Seed+Generate | Seed+Full |
|---|---|---|---|---|
| **qwen3.5-flash** | 3.83 (3/6) | 4.83 (4/6) | 4.83 (4/6) | **7.00 (6/6)** |
| gpt-5.4-mini | 0.33 (0/6) | 0.00 (0/6) | 2.33 (2/6) | 1.17 (1/6) |
| **gemini-3-flash** | 5.83 (5/6) | 6.83 (6/6) | 5.67 (5/6) | **7.00 (6/6)** |
| gpt-oss-120b | 2.67 (2/6) | 4.67 (4/6) | 4.50 (4/6) | 5.40 (4/5) |
| gemini-flash-lite | 1.17 (1/6) | 1.33 (1/6) | 1.33 (1/6) | 2.50 (2/6) |
| deepseek-v3.2 | 1.50 (1/6) | 2.33 (2/6) | 1.83 (1/6) | **5.83 (5/6)** |

Wall times: baseline ~25min, seed+gen ~34min, seed+full ~76min.

**Key findings:**
- Seed+generate ≈ full pipeline for most models (idea diversity alone matches iterative refinement)
- Seed+full is best overall but slower than seed+generate
- deepseek-v3.2 biggest beneficiary of seed+full (1.50 → 5.83), needs both diversity AND refinement
- gemini-3-flash barely needs the pipeline (5.83 generate-only) but seed+full pushes to perfect
- erdos-659 remains 0/7 for all models in seed+generate mode — only solved with full pipeline attached

Script: `experiments/seed_ideas_devset_20260327.py --generate-only`
Results: `experiments/results/seed_ideas_devset_20260328_023722_genonly.json`

## Model Diversity Experiment - 2026-03-28T11:28:00

12 conditions × 6 problems × 3 seeds (pass@3) = 216 trials. 0 errors.
Models: deepseek-v3.2 (ds), gpt-oss-120b (oss), gemini-3.1-flash-lite (lit). Judge: gemini-3-flash.

| # | Condition | Mean | Pass | Key Finding |
|---|---|---|---|---|
| 1 | ds-self (baseline) | 3.28/7 | 8/18 | |
| 2 | oss-self (baseline) | 3.56/7 | 9/18 | |
| 3 | lit-self (baseline) | 2.11/7 | 5/18 | Weakest as expected |
| **4** | **ds-gen + oss-vr** | **4.39/7** | **11/18** | **+1.11 vs ds. OSS verifying DS helps!** |
| **5** | **oss-gen + ds-vr** | **4.33/7** | **11/18** | **+0.78 vs oss. DS verifying OSS helps!** |
| 6 | ds-gen + lit-vr | 2.44/7 | 6/18 | -0.83 vs ds. Lit verifier hurts. |
| 7 | oss-gen + lit-vr | 2.78/7 | 7/18 | -0.78 vs oss. Lit verifier hurts. |
| **8** | **lit-ideas + ds-pipe** | **5.28/7** | **13/18** | **+2.00 vs ds. Best condition!** |
| **9** | **lit-ideas + oss-pipe** | **4.67/7** | **12/18** | **+1.11 vs oss. Ideas help.** |
| 10 | ds-gen + oss-ver + ds-rev | 3.06/7 | 7/18 | -0.22 vs ds. Split verify/revise doesn't help. |
| **11** | **oss-gen + ds-ver + oss-rev** | **4.56/7** | **12/18** | **+1.00 vs oss. DS verifies, OSS revises = good combo** |
| 12 | round-robin | 4.17/7 | 11/18 | +0.89 vs ds, +0.61 vs oss |

**Key findings:**

1. **DS ↔ OSS mutual benefit confirmed.** Cross-verification helps both directions (+1.11 for ds, +0.78 for oss). Your hypothesis was correct.

2. **Flash-lite as verifier hurts** — exactly as predicted. Conditions 6,7 both drop ~0.8 vs baselines.

3. **Flash-lite as ideator helps massively** — c8 (lit-ideas+ds-pipe) is the best condition at 5.28/7, +2.00 vs ds baseline. The cheap model generates useful diverse starting ideas even though it can't solve problems itself.

4. **Asymmetric cross-verification:** oss-gen+ds-ver+oss-rev (c11, 4.56/7) works much better than ds-gen+oss-ver+ds-rev (c10, 3.06/7). DS is a better verifier than reviser; OSS is better at self-repair.

5. **PB-Basic-028 and erdos-659 remain hard** — 0/7 across nearly all conditions. Only c4 (ds+oss-vr) and c8 (lit-ideas+ds) crack erdos-659 partially (2.7/7 and 3.0/7).

**Per-seed stability (3 pass@1 runs, not pass@3):**
Robust: c8 lit-ideas+ds always helps (+2.33/+1.33/+2.33, std=0.52), c11 oss+ds-ver very stable (std=0.16), c6 lit-vr always hurts (0/-1.17/-1.33). Noisier: c4 ds+oss-vr swings (+0.17 to +2.17), oss-self baseline most volatile (std=0.83). Effect directions hold across all seeds; magnitudes would tighten with more.

Wall-clock runtime: **8h 33m** (216 trials, 8 workers, 02:55–11:28 UTC).

**IMPORTANT — branches run sequentially in this script.** Seed-ideas conditions (c8, c9) average 70m and 34m per trial because 3 branches run in series. The `seed_ideas_devset` script parallelizes branches (ThreadPoolExecutor inside `run_trial`), but this script and `ideator_capability` do not. **Always parallelize branches within trials for future runs** — would cut ideator-condition wall-clock by ~3x.

Script: `experiments/model_diversity_20260328.py`
Results: `experiments/results/model_diversity_20260328_112821.json`

## Ideator Capability Scaling - 2026-03-29T10:03:00

Does a stronger ideator model produce better seed ideas? Tested 3 Gemini tiers (flash-lite, flash, pro) as ideators for DS and OSS pipelines, full + generate-only modes. 12 conditions × 6 dev-set problems, pass@1, seed=42.

**Key finding: stronger ideator ≠ better results. Lite wins in full pipeline.**

| Ideator | DS full | OSS full | DS gen | OSS gen |
|---------|---------|----------|--------|---------|
| Lite    | **5.83** | **5.83** | 2.50  | 2.33   |
| Flash   | 4.67    | 4.67    | 2.50   | 2.50   |
| Pro     | 3.83    | 4.83    | 3.50   | 2.50   |

- Lite ideator beats flash and pro by 1-2 pts in full pipeline (both DS and OSS)
- Full pipeline uplift is massive with lite (+3.50 for OSS, +3.33 for DS)
- Pro slightly helps in DS generate-only (3.50 vs 2.50) but not in full pipeline
- PB-Basic-028 only cracked by lite ideator + full pipeline
- erdos-659 unsolved across all tiers
- Interpretation: lite generates simpler, more actionable ideas that pipeline models can execute on; stronger ideators may over-specify

First run hit DNS failures during hotspot transition (42/72 errors); retried failed conditions cleanly (0 errors).

Script: `experiments/ideator_capability_20260328.py`
Results: `experiments/results/ideator_capability_20260329_100311.json` (retry), `experiments/results/ideator_capability_20260328_203500.json` (c3 only)

## Ideator Capability Scaling (OAI family) - 2026-03-30T18:43:00

Same experiment as above but with gpt-5.4-nano, gpt-5.4-mini, gpt-5.4 as ideators. 12 conditions × 6 dev-set problems, pass@1, seed=42. Parallelized branches (3x speedup vs sequential).

**Key finding: opposite pattern to Gemini — stronger OAI ideator = better results.**

| Ideator | DS full | OSS full | DS gen | OSS gen |
|---------|---------|----------|--------|---------|
| Nano    | 4.20    | 4.50     | 3.50   | 3.67    |
| Mini    | 4.67    | 4.67     | 4.67   | 4.67    |
| **Std** | **5.00** | **5.67** | 3.50  | **5.83** |

- Std ideator + OSS pipeline is the best OAI combo (5.67 full, 5.83 gen-only)
- Scaling helps most with OSS as pipeline model; DS benefits less
- Mini is flat 4.67 across all configs
- PB-Basic-028 only cracked by std→oss (6/7 full, 7/7 gen)
- erdos-659 still essentially unsolved (std→ds-pipe got 1/7)

**Cross-family comparison:** Gemini flash-lite (5.83/7) ≈ OAI gpt-5.4 std (5.67/7) as ideator for full pipeline, but with opposite scaling directions. Suggests the "weaker ideator wins" effect is Gemini-specific, not a universal property of ideation.

First run hit OpenRouter key limit (42/54 trials empty); re-ran with fresh key, 1 error (c1 PB-Basic-007).

Script: `experiments/ideator_capability_20260328.py` (modified for OAI models)
Results: `experiments/results/ideator_capability_oai_20260330_184302.json`

## Idea-Prediction Signal Analysis - 2026-04-05T11:48:00

Analyzed 132 trials with branched results across ideator_capability (Gemini + OAI) and seed_ideas experiments. Key findings:

**Score distribution is bimodal**: 52.5% of branches score 0-1, 47.5% score 6-7, virtually nothing in between. Ideas either lead to a correct solution or completely fail.

**Ideas matter 43% of the time**: 57 of 132 trials have score variance across branches. The remaining 57% tie at 0 (too hard) or 7 (too easy). When ideas matter, the gap is large (mean 5.12, median 6.0 — the difference between total failure and success).

**Position bias**: Idea #0 (first generated) is best 61% of the time, vs 33% random. Mean score: pos0=4.48, pos1=3.45, pos2=2.27. Ideators front-load their best idea.

**Problem sensitivity**: PB-Basic-007 shows variance 89% of the time (most idea-sensitive). PB-Basic-017 only 14%. Harder problems are more idea-sensitive.

**Category-based prediction**: A global category predictor reaches 65% accuracy (2x random), but winning categories are problem-specific, not universal.

**Best-of-3 uplift**: Single branch mean=3.40, best-of-3 mean=4.48 (+1.08). Pass rate: 47.5% → 63.6% (+16.1pp). Diversity is already very effective without a predictor.

**Pipeline does NOT affect variance**: Full pipeline (43.1% variance) ≈ generate-only (45.2% variance). Verify/revise rescues all branches similarly, not selectively.

**Implication for pruning experiment**: A ranker needs to beat the "always pick idea #0" baseline (61% accuracy). Category-based signal exists but is moderate. The practical question: can pruning to K=1 with a ranker match K=3 random?

## Best-of-N Experiment - 2026-04-05T12:06:00

Tested N={1,3,5,7} ideas with generate-only + judge on devset. Ideator: gemini-3.1-flash-lite. Generators: DS and OSS. 48 trials, pass@1.

**Results (best-of-N score / mean all branches):**

| Config | N=1 | N=3 | N=5 | N=7 |
|--------|-----|-----|-----|-----|
| DS best | 3.33 | 1.67 | 3.67 | 3.67 |
| OSS best | 1.50 | 4.83 | 4.67 | 4.50 |
| DS mean_all | 3.33 | 1.39 | 2.03 | 1.76 |
| OSS mean_all | 1.50 | 3.56 | 3.47 | 2.14 |

**Diversity uplift (best - mean_branch):** Grows with N as expected. N=7 OSS: +2.36, N=7 DS: +1.90.

**Key findings:**
- OSS benefits much more from diversity than DS (4.83 at N=3 vs DS 1.67)
- DS is highly inconsistent across N — N=1 outperforms N=3 (3.33 vs 1.67), suggesting seed randomness at pass@1
- OSS peaks at N=3 (4.83), slight decline at N=5/7 — more ideas may dilute quality
- PB-Basic-028 still unsolved across all N and both models (0/7 everywhere)
- erdos-659: DS got 6/7 at N=7 (1 of 7 branches hit) — first DS success on erdos
- PB-Basic-017 trivially solved by both models at all N
- Per-branch mean score is LOW (1.39-3.56), confirming most branches fail — diversity's value is in the tail

**Architecture insight for frontier deployment:** Best-of-N is effective but noisy at pass@1. The optimal N appears to be 3-5 for OSS, with diminishing returns beyond. For frontier models where per-call cost is high, N=3 appears to be the sweet spot.

Script: `experiments/best_of_n_20260405.py`
Results: `experiments/results/best_of_n_20260405_120602.json`

## Pruning Ideation Experiment - 2026-04-05T12:04:00

Tested whether a cheap ranker can predict the best idea. N=7 ideas, generator: DS (generate-only). Conditions: all-7, prune-to-3 (ranker), prune-to-1 (ranker), random-3 (no ranker). 24 trials.

**Results:**

| Condition | Mean | Pass | Time |
|-----------|------|------|------|
| all-7 | 3.83/7 | 3/6 | 364s |
| prune-to-3 (ranker) | 2.67/7 | 2/6 | 400s |
| prune-to-1 (ranker) | 3.67/7 | 3/6 | 187s |
| random-3 | 3.67/7 | 3/6 | 321s |

**Ranker prediction accuracy (flash-lite ranking flash-lite ideas):**
- Top-1 accuracy: 1/6 (17%) — worse than random (14% = 1/7)!
- Top-3 accuracy: 4/6 (67%)
- The ranker's top-1 pick was frequently the worst choice (PB-Basic-012: ranked idea 0 at top, scored 0/7; actual best was idea 5, scored 7/7)

**Key findings:**
- **Ranker pruning HURTS**: prune-to-3 (2.67) is worse than random-3 (3.67) and worse than all-7 (3.83)
- **prune-to-1 surprisingly matches random-3**: both 3.67/7, but prune-to-1 is 2x faster (187s vs 321s)
- **All-7 is the best strategy** but only marginally (3.83 vs 3.67)
- **The ranker has negative value for top-3**: it actively selects worse ideas than random
- **Cost: prune-to-1 is the best cost/quality tradeoff** (half the time of all-7, only 0.16/7 worse)
- **PB-Basic-012 shows ranker's failure**: ranker picked idea 0 (score 0) over ideas 4,5 (scores 7,7)

**Architecture insight:** Same-power rankers cannot reliably predict solution quality from idea descriptions alone. The mapping from "idea sounds good" to "idea produces correct solution" is too noisy. Better alternatives: (1) run all branches cheaply, then invest in verify/revise for only the promising ones, or (2) use a stronger model as ranker (but this defeats the cost purpose).

Script: `experiments/pruning_ideation_20260405.py`
Results: `experiments/results/pruning_ideation_20260405_120445.json`

## Harder IMO Experiment - 2026-04-05T12:34:00

Tested flash-lite ideator + DS/OSS on 10 IMO-hard + 5 IMO-medium PB-Advanced problems. N=3 ideas, full pipeline + generate-only. 60 trials, 1 error (ds-pipe PB-Advanced-015 timeout).

**Results:**

| Condition | Mean | Pass | IMO-hard | IMO-medium |
|-----------|------|------|----------|------------|
| ds-pipe (full) | 1.21/7 | 2/14 | 1.67/7 | 0.40/7 |
| oss-pipe (full) | 0.93/7 | 2/15 | 1.40/7 | 0.00/7 |
| ds-gen | 0.27/7 | 0/15 | 0.30/7 | 0.20/7 |
| oss-gen | 0.13/7 | 0/15 | 0.20/7 | 0.00/7 |

**Pipeline uplift on hard problems:** DS: +1.37 on IMO-hard, OSS: +1.20. Full pipeline helps MORE on harder problems (as hypothesized).

**By category:** Geometry is completely unsolved (0/7 across all conditions). Number theory best (3.50/7 ds-pipe). Combinatorics middling (1.33/7 ds-pipe).

**Per-problem highlights:**
- PB-Advanced-012 (IMO-hard, Number theory): 6/7 for both ds-pipe and oss-pipe — best result
- PB-Advanced-021 (IMO-hard, Combinatorics): 7/7 for ds-pipe only (1 of 3 branches hit)
- PB-Advanced-030 (IMO-hard, Combinatorics): 7/7 for oss-pipe only (1 of 3 branches hit)
- 9 of 15 problems scored 0/7 across ALL conditions — genuinely beyond these models
- Branch diversity still matters: winning scores come from 1/3 branches (7,0,0 pattern)

**Key insight for frontier deployment:** These models hit a hard capability wall on IMO-hard. The pipeline helps (+1.2-1.4 on hard), but only 2-3 of 10 hard problems are crackable at all. Frontier models should dramatically expand the "crackable" set, and the pipeline uplift should compound with higher base capability.

Script: `experiments/harder_imo_20260405.py`
Results: `experiments/results/harder_imo_20260405_123452.json`

## Ranker Comparison Experiment - 2026-04-05T12:49:00

Tested 5 ranker models on idea-prediction accuracy. 10 problems (6 devset + 4 IMO-hard), 7 ideas each, DS generator (generate-only). 70 branches for ground truth + 50 ranker calls.

**Results:**

| Ranker | Top-1 | Top-3 | Score@1 | Kendall τ |
|--------|-------|-------|---------|-----------|
| flash-lite | 22% | 44% | 2.11/7 | -0.066 |
| gemini-flash | 22% | 33% | 2.00/7 | -0.026 |
| gemma-4 | 22% | 33% | 1.89/7 | +0.042 |
| qwen3.6 | 11% | 33% | 2.00/7 | +0.085 |
| deepseek | 11% | 33% | 2.00/7 | +0.082 |
| **(random)** | **14%** | **43%** | — | 0.000 |

**All rankers perform at or below random baseline for top-1 and top-3 accuracy.** Flash-lite is marginally best (44% top-3 vs 43% random) but this is within noise.

**Per-problem findings:**
- PB-Basic-012 is the only problem where rankers show positive signal (all achieve τ=+0.714 except qwen3.6 at +0.429)
- erdos-659: gemini-flash, gemma-4, and qwen3.6 all achieve perfect τ=+1.0 (but scores are only 0-1, so signal is weak)
- PB-Basic-024: all rankers fail badly — they rank idea #6 (the only 7/7 scorer) at position 5-6
- Self-prediction (deepseek ranking for deepseek generation): no better than others

**Conclusion: Idea ranking from descriptions alone does not work.** No model — cheap or expensive, same-family or cross-family — can reliably predict which idea will produce a correct solution. The mapping from "sounds promising" to "generates correct proof" is fundamentally noisy. This confirms that best-of-N (run all, pick best) is the right strategy, and pruning should be done via cheaper mechanisms if at all (e.g., run cheap generation first, then invest in verification only for promising branches).

Script: `experiments/ranker_comparison_20260405.py`
Results: `experiments/results/ranker_comparison_20260405_124928.json`

## New Model Exploration: qwen3.6-plus:free + gemma-4-31b-it - 2026-04-05T13:40:00

### Experiment 1: Easy benchmark (generate-only, no GT judge)
- **Models**: `qwen/qwen3.6-plus:free`, `google/gemma-4-31b-it`
- **Problems**: 5 × IMO-easy (PB-Basic-001/003/004/005/009), seed=42, no ground truth
- **Results**: Both models scored 5/5 correct — but IMO-easy is too easy to discriminate
- **Key finding**: Severe rate-limit slowdown on free tier. ~850s/trial for Qwen, ~900s/trial for Gemma. 10 trials took ~30 min total. Neither model is usable for batch evaluation runs at free tier.

Script: `experiments/new_models_explore_20260405.py`
Results: `experiments/results/new_models_explore_20260405_20260405_130350.json`

### Experiment 2: Hard research problems (qwen3.6-plus:free only, generate-only)
- **Model**: `qwen/qwen3.6-plus:free`
- **Problems**: erdos-659 (Negligible Novelty), erdos-1051-aletheia (Minor Novelty), ramsey-hypergraphs (Moderately Interesting)

**erdos-659** (~793s): ✓ Correct construction. Qwen independently found Z+i√2·Z lattice, correctly verified no squares/equilateral triangles/pentagon trapezoids exist via quadratic form arguments, and cited Landau-Ramanujan for the O(n/√log n) distinct-distance bound. Matches known solution.

**erdos-1051-aletheia** (~646s): Plausible irrationality proof. Used rationality lower bound (|S - S_N| ≥ 1/(q·Q_N)) combined with super-exponential tail decay to derive contradiction. Argument structure looks sound but has a gap in the denominator bound (LCM vs product). Worth expert review.

**ramsey-hypergraphs**: API ERROR — response was ~41K chars before OpenRouter returned malformed JSON. Likely hit a context/response-size limit on the free tier. Content was cut off mid-response.

**Overall takeaway**: Qwen3.6-plus:free is surprisingly capable on research-level math (got erdos-659 right), but the free tier is unreliable for long outputs (ramsey failure) and too slow (~10-20 min/call) for systematic use.

## Frontier Model Hard Problems Probe - 2026-04-05T14:10:00

- **Models**: `anthropic/claude-opus-4.6`, `google/gemini-3.1-pro-preview`
- **Problems**: erdos-659, ramsey-hypergraphs, erdos-1051-aletheia
- **Mode**: generate-only, all 6 combos in parallel

**erdos-659**:
- Opus 4.6 (30s): Attempted Z² integer lattice but self-corrected mid-solution — noticed it contains squares (which violate the 4-point condition), then hand-waved a "generic subset / remove forbidden quadruples" argument. Verdict: incomplete/flawed but shows awareness of the problem.
- Gemini 3.1 Pro (130s): Got lost exploring whether 4 collinear points can determine ≤2 distances. Never completed a valid construction. Response appeared truncated.

**ramsey-hypergraphs**:
- Opus 4.6 (27s): Produced a clean, explicit sunflower construction — 20 edges each of size 5 sharing one core vertex. Correctly argued any two edges intersect → max partition = 1 edge → |D| ≤ 5 ≤ 20, union = 81 ≥ 64. Looks correct.
- Gemini 3.1 Pro (196s): Attempted incidence matrix formulation with modular arithmetic, but construction was truncated mid-listing.

**erdos-1051-aletheia**:
- Opus 4.6 (197s): Concluded the answer is **no** (sum can be rational — counterexample exists), and spent most of the response searching for an explicit construction via Sylvester sequence, Fermat-type sequences, and product telescoping. Found partial directions but no clean closed-form counterexample. Shows deep engagement but no decisive result.
- Gemini 3.1 Pro (122s): Appears to have been working through a formal proof by contradiction (partial fractions on I_k/P_k), but output was cut mid-derivation. Can't evaluate.

**Key takeaways**: Opus 4.6 is dramatically faster (26-197s vs 122-196s) and produces more coherent long-form reasoning. Gemini 3.1 Pro tends to get truncated or lost. Ramsey was the clearest success for Opus. erdos-1051 disagreed with Qwen (Qwen said "yes, provably irrational"; Opus said "no, counterexample exists") — expert review needed.

Script: `experiments/frontier_hardproblems_20260405.py`
Results: `experiments/results/frontier_hardproblems_20260405_140538.json`

## Frontier Ramsey v1 (wrong models) - 2026-04-05T13:39:00

First frontier attack on ramsey-hypergraphs using wrong models (claude-sonnet-4, gpt-5.4, gemini-2.5-pro, deepseek-r1, qwen3-max-thinking). 5 branches × 3 iterations, self-verification. Judge: gemini-3-flash with GT.

**All 5 branches scored 0/7.** Opus produced 71K char solution still scoring 0. DeepSeek R1 verifier false-positive triggered early stop before fix. After fix (judge-gated early stop ≥6/7), no branch triggered stop.

Script: `experiments/frontier_ramsey_20260405.py`
Results: `experiments/results/frontier_ramsey_20260405_133935.json`

## Frontier Ramsey v2 (correct models, full architecture) - 2026-04-05T14:44:00

Second frontier attack with v2 architecture: dual ideation (flash-lite + Opus), 3 branches × 6 iterations, cross-model verification, escalated revision, programmatic checker, synthesis round, multi-judge consensus.

**Models:** Opus (gen), Gemini 3.1 Pro (gen), Qwen3 Max Thinking (gen). Cross-verify and escalated revision between models.

**Results (programmatic check — |V| achieved):**

| Candidate | |V| found | Required | Gap |
|---|---|---|---|
| opus-branch | 3 | ≥64 | Regressed to trivial |
| **qwen-branch** | **59** | ≥64 | **5 short** |
| gemini-branch | 36 | ≥64 | 28 short |
| **synthesis** | **61** | ≥64 | **3 short** |

All judges: incorrect/partial. No valid solution.

**Key findings:**
- Qwen3-max-thinking was the strongest generator for this problem (|V|=59), not Opus
- Synthesis genuinely helped: combined insights pushed from 59 → 61 vertices
- Cross-verification ran full 6 iterations without false early-stop
- Opus regressed badly to |V|=3 despite 6 iterations — may have overthought into trivial construction
- Programmatic checker proved essential — immediately tells us how close each attempt is
- Total cost: ~$15-20 estimated, 4187s elapsed

Script: `experiments/frontier_ramsey_v2_20260405.py`
Results: `experiments/results/frontier_ramsey_v2_20260405_144406.json`

## Deep Dive: Why Ramsey-Hypergraphs Fails in Our Pipeline - 2026-04-05T15:00:00

### Epoch AI reference
Epoch solved this problem with Opus 4.6 (1/4 attempts), Gemini 3.1 Pro (2/4), GPT-5.4 (2/4). Their setup was fundamentally different from ours:
- **38 agentic turns** with Python REPL, bash, web search tools
- Model built its own brute-force verifier and tested small cases exhaustively
- Went through multiple failed approaches before breakthrough (multi-way splits + LP)
- Used ~256K/1M tokens over 36 tool calls
- 1 submission, correct first try (after extensive self-verification via code)
- Final solution: recursive DP construction with 2/3/4-way near-balanced splits and LP-optimized linking vertices

### Our pipeline failures explained

**Probe (generate-only, 27s):** Opus produced a sunflower construction claiming |V|=81, |H|=20. Agent log said "looks correct." Programmatic checker reveals: |V|=81 ✓ but |H|=22 ✗ and max_partition=21 ✗. The approach was sound but execution had off-by-two errors. No code execution to self-check.

**v2 pipeline (cross-verify + escalated revision, 6 iterations):**
- Opus generated a 73K char exploratory response — found the sunflower idea (lines 1183-1185: "20 edges size 20, all containing vertex 1: |V| up to 381") but kept analyzing and got stuck in an averaging argument that seemed to prove |V| ≤ 38. Response trails off mid-sentence.
- Parser extracted only small inline examples → |V|=14 (not the intended construction)
- Gemini Pro cross-verifier correctly found issues each iteration
- Gemini Pro reviser progressively simplified the response, and by iteration 6, the solution had **completely changed approach**: instead of constructing a hypergraph, it argued "the problem is definitively unsolvable under the given bounds" — which is mathematically WRONG (known to be solvable)
- 6 iterations of cross-verify + revise transformed a promising (if confused) exploration into a confidently wrong impossibility claim

### Root cause analysis

1. **Wrong problem type for our pipeline.** This is a constructive coding problem, not a proof problem. Epoch's Opus used iterative code execution (build verifier → test construction → debug → improve). Our pipeline treats it as "write a proof, have another model check it."

2. **LLM verifiers can't catch construction errors.** The probe's sunflower had |H|=22 (should be ≤20) and max_partition=21 (should be ≤20). No LLM verifier can exhaustively check 2^20 subsets. Only programmatic checking catches this.

3. **Cross-verification actively destructive here.** Opus's initial generation contained the right idea buried in 73K chars of exploration. Cross-verifier (Gemini) correctly noted confusion. But reviser (Gemini) "fixed" it by simplifying away the construction and eventually arguing impossibility. The pipeline's verify→revise loop is designed for proof refinement, not construction debugging.

4. **Model needs tools, not critics.** Epoch's key insight: give the model a Python REPL and let it build/test/iterate. Our pipeline gives no tools — the model can only reason in text. For constructive problems, code execution IS the verification.

### Architectural implications for open problems

For constructive problems (Hadamard, Steiner systems, Ramsey), the pipeline should be:
1. **Give the model code execution** (Python REPL with numpy, scipy, itertools)
2. **Programmatic verification in the loop** (our checkers), not LLM verification
3. **More turns, not more cross-verification** — let the model iterate on its own code
4. **Preserve the construction** — never let a reviser rewrite a construction from scratch; instead, feed back specific programmatic failure modes for targeted fixes

The verify→revise loop is valuable for proof problems. For construction problems, it should be replaced with: generate code → execute → check output → feed errors back → iterate.

## Frontier Hard Problems — GT Judge Re-run - 2026-04-05T14:35:00

Re-ran the same 6 solutions (from frontier_hardproblems_20260405_140538.json) against ground truth judge, both inline and via a fresh generation+judge run. Scores were identical both ways.

| Problem | claude-opus-4.6 | gemini-3.1-pro-preview |
|---|---|---|
| erdos-659 | 0/7 | 0/7 |
| ramsey-hypergraphs | **7/7** | 0/7 |
| erdos-1051-aletheia | 0/7 | 0/7 |

- **ramsey/opus**: Sunflower construction confirmed correct by judge (twice). My manual critique was wrong.
- **erdos-659/opus**: Self-correction mid-solution left no valid construction. 0/7.
- **erdos-1051/opus**: Argued "no" (counterexample exists); ground truth says "yes" (provably irrational). Wrong direction. 0/7.
- **All gemini**: Truncated or incomplete responses. 0/7 across the board.

Scripts: `experiments/frontier_hardproblems_20260405.py` (updated with GT judge)
Results: `experiments/results/frontier_hardproblems_20260405_142957.json`

## Hadamard Agentic Attack v1 — 2026-04-05T16:32:00

**Goal**: Construct Hadamard matrix of order 668 using agentic coding loop (inspired by Epoch AI approach).
**Architecture**: Multi-turn code execution with programmatic verification (hadamard_checker.py), NO LLM verification. 3 parallel branches, 20 turns each.

**Branches**:
| Branch | Model | Approach | Turns | Best Order | Result |
|--------|-------|----------|-------|------------|--------|
| opus-paley | claude-opus-4.6 | Paley construction | 20 | 4 | unsolved, 1567s |
| gemini-tensor | gemini-3.1-pro-preview | Tensor/Williamson | 20 | 4 | unsolved, 2623s |
| relay-opus-gemini | opus(10t)→gemini(10t) | Algebraic | 20 | 3 | unsolved, 1868s |

**Failure analysis**:
1. **Gemini catastrophic**: 19/20 turns produced NO executable Python code (just mathematical prose). Code extraction regex found no ```python blocks. The `finish_reason: error` from OpenRouter suggests response format issues too. Essentially burned ~$10 producing math essays.
2. **Opus stuck on small tests**: Ran code every turn but never produced a matrix larger than 4×4. Spent all 20 turns verifying small Paley/Kronecker constructions without ever attempting the full 668 build. Two execution timeouts (turns 16, 18) suggest it may have tried larger computation but hit 120s limit.
3. **Relay branch**: Opus phase similar to above. After handoff at turn 11, Gemini also failed to produce code (same issue as solo Gemini branch).

**Key lessons for v2**:
- **Gemini needs stronger code-forcing**: The prompt says "Write Python code" but Gemini ignores it. Need to either: (a) use a stronger system prompt demanding ONLY code output, or (b) post-process to detect prose-only responses and re-prompt with "You must write Python code. No explanations."
- **Models need explicit "scale up now" nudge**: Opus validated small cases endlessly. The prompt should include explicit milestones: "Turn 1-3: test small cases. Turn 4+: build the full 668×668 matrix."
- **120s timeout too short for search**: Williamson sequence search over length 167 needs more compute time. Consider 300-600s.
- **The prompt overloads with too many construction strategies**: Models get paralyzed by choice. Better to assign ONE specific construction with concrete pseudocode.

Results: `experiments/hadamard_agentic/results/hadamard_agentic_20260405_163204.json`
Log: `logs/hadamard_agentic_20260405_154821.jsonl`

## Hadamard Agentic Attack v2 — 2026-04-05T21:47:00

**Architecture changes from v1**: Opus↔Gemini alternating every turn, 50 turns, `reasoning_effort="high"`, 300s exec timeout, Epoch-style prompts (think out loud + stateless code), concrete Williamson pseudocode, phase nudges, full conversation logging.

**Terminated early**: OpenRouter monthly API key limit hit at turn 35/50 (search) and 26/50 (qr).

| Branch | Turns completed | Best order | No-code turns |
|--------|----------------|------------|---------------|
| williamson-search | 35/50 | 4 | 12 (all Opus) |
| williamson-qr | 26/50 | 2 | 4 (3 Opus, 1 Gemini) |

**Key observations**:
1. **Gemini fixed**: Alternation completely solved Gemini's no-code problem from v1. Gemini wrote code on nearly every turn (34/35 in search, 22/26 in qr). Seeing Opus's reasoning as context triggers code-writing behavior.
2. **Opus regressed with reasoning_effort="high"**: High reasoning mode made Opus produce long thinking prose WITHOUT code blocks on ~40% of its turns. Ironic reversal from v1 where Opus always coded. Consider `reasoning_effort="medium"` for Opus or stripping the "think out loud" permission from Opus-specific turns.
3. **Still stuck on small matrices**: Neither branch produced anything >order 4. Models are implementing and testing Williamson framework correctly but not scaling to p=167 search.
4. **Full conversations saved**: Can pick up from saved state after API budget resets.

**Conversations saved**: `experiments/hadamard_agentic/results/conversation_williamson-{search,qr}_20260405_214710.json`
Results: `experiments/hadamard_agentic/results/hadamard_agentic_v2_20260405_214710.json`
Log: `logs/hadamard_agentic_20260405_203834.jsonl`

## Hadamard Agentic v2 Resume — 2026-04-06T00:32:00

Resumed both branches using OPENROUTER_API_KEY_2. Opus=medium reasoning, Gemini=high. Both ran to completion (50 turns total each).

| Branch | New turns | Total turns | Best order | Best PAF defect |
|--------|-----------|-------------|------------|-----------------|
| williamson-search | 15 | 50 | 4 | ~2688 |
| williamson-qr | 24 | 50 | 4 | ~2752 |

**Critical finding — stdout truncation bug**: The sandbox captures stdout with an 8KB limit. A 668×668 CSV matrix is ~900KB. When models output a candidate matrix, it gets truncated, and the checker parses the fragment as a ~4×668 matrix. The "best_order=4" was actually the checker seeing truncated output, NOT the models producing 4×4 matrices. The models were producing full 668×668 candidates but we couldn't verify them!

**Reflection summaries (both branches converged independently):**
- Correctly implemented Williamson + Goethals-Seidel frameworks
- Legendre symbol seeding: starting PAF defect ~36K (vs millions for random init)
- FFT-based PAF computation O(p log p)
- Fast incremental PAF updates for greedy descent
- Best PAF defect achieved: ~2688 (search) / ~2752 (qr) — needs to reach 0
- SA and greedy both trapped in local minima around defect ~2700
- Models suggested next: SAT solvers, cyclotomic class reduction, write matrix to file

**Fixes needed for v3:**
1. Write matrix to file instead of stdout — bypass 8KB truncation
2. Have the checker read from file, not parse stdout
3. Consider providing the models with a known Williamson(167) solution or reference to break the search barrier

Conversations: `experiments/hadamard_agentic/results/conversation_williamson-{search,qr}_20260406_003233.json`
Results: `experiments/hadamard_agentic/results/hadamard_agentic_v2_20260406_003233.json`
Log: `logs/hadamard_agentic_20260405_233749.jsonl`

## Iteration Depth Experiment — 2026-04-05 (killed)

Process hung for 6+ hours at 0% CPU. Never completed a single trial — likely deadlocked on first API call or thread pool init. Killed with no partial results. Needs relaunch.

## Hadamard Agentic v3 — Pipeline Fix & E2E Test — 2026-04-05T21:00:00

**Critical bug fixed**: v2 had stdout truncation (8KB cap in sandbox_exec.py) that broke the feedback loop for 668×668 matrices. Models never got real verification signal across 100+ turns and ~$15-20 of API spend.

**v3 changes**:
- `sandbox_exec.py`: Added `shared_dir` parameter, passes `HADAMARD_OUTPUT_DIR` env var to subprocess. Model writes `candidate.csv` to shared dir, checker reads from file.
- `agentic_loop.py`: File-based matrix I/O with stdout fallback for small matrices. Rich partial-progress feedback: orthogonality %, perfect rows, max off-diagonal, quality score (0-100). Tracks `best_quality` instead of just `best_order`. Stale file cleanup between turns.
- `prompts.py`: Updated system prompt and both initial prompts to instruct models to write `candidate.csv` to `HADAMARD_OUTPUT_DIR` instead of printing to stdout.

**E2E test suite** (`test_pipeline_e2e.py`): 58/58 checks passed. Tests:
1. Sandbox file I/O (16×16 valid Hadamard written to and read from file)
2. 668×668 matrix through file (exact failure scenario from v2 — now works)
3. Valid matrix checker feedback (quality=100, all metrics correct)
4. 668×668 near-miss partial progress (3.12% orthogonal pairs, quality=51.56)
5. No matrix graceful handling
6. Wrong order detection
7. Stdout fallback for small matrices
8. Stale file cleanup between turns
9. Error/timeout handling
10. Quality score ordering

Pipeline is ready for a real run.
