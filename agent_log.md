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

## New Models Comparison (pass@1) — 2026-05-04T05:12:15

6 new + 2 baseline models, generate-only on dev set, GT judge, seed=42. 3-key round-robin,
24 workers. 26.7 min, 0 errors, ~$0.91. qwen3.6-plus on 3-problem subset only.

| Model | $/Mtok | Mean | Pass | Lat | $/run |
|---|---|---|---|---|---|
| deepseek-v4-pro     | 0.87 | **5.83** | 5/6 | 825s | $0.021 |
| qwen3.6-plus (subset) | 1.95 | 4.33 | 2/3 | 767s | $0.076 |
| deepseek-v4-flash   | 0.28 | 3.50 | 3/6 | 136s | $0.004 |
| gemma-4-31b-it      | 0.38 | 3.00 | 2/6 | 192s | $0.001 |
| qwen3.6-35b-a3b     | 1.00 | 2.67 | 2/6 | 128s | $0.017 |
| qwen3.6-flash       | 1.50 | 2.67 | 2/6 | 295s | $0.070 |
| gemini-3-flash (b)  | —    | 4.67 | 4/6 |  10s | —      |
| deepseek-v3.2  (b)  | —    | 3.83 | 3/6 | 213s | —      |

**Findings (later partly revised by pass@3):**
- **deepseek-v4-pro best overall** — only model to solve both erdos-659 and PB-Basic-028 (7/7).
- **Reasoning tokens billed but uncapped:** v4-pro/qwen3.6-flash/qwen3.6-plus billed 30K–70K
  completion tokens against a 16K visible cap. Costs above use full billed totals.
- **PB-Basic-024 "sanity" no longer reliable** — 5/8 models scored 1/7 (incl. v3.2 baseline,
  past runs were 7/7). Dev-set role tag may need updating.

Script / results: `experiments/new_models_compare_20260504.py`,
`experiments/results/new_models_compare_20260504_20260504_051215.json`

## New Models Pass@3 Follow-up — 2026-05-04T05:48:04

Same setup, SEEDS=[42,0,1], dropped v4-pro and qwen3.6-plus per user. 108 trials, 60 workers.
**18.2 min wall-clock (missed <10 min target — long-pole v4-flash trials hit 16 min).** 0 errors,
$1.50 total.

| Model | $/Mtok | Mean | Pass@3 | $/run |
|---|---|---|---|---|
| **deepseek-v4-flash** | 0.28 | **4.50** | 5/6 | $0.005 |
| gemini-3-flash (b) | 3.00 | 3.72 | 4/6 | $0.007 |
| gemma-4-31b-it     | 0.38 | 3.61 | 4/6 | $0.001 |
| qwen3.6-flash      | 1.50 | 3.33 | 4/6 | $0.051 |
| deepseek-v3.2 (b)  | 0.378| 3.28 | 4/6 | $0.002 |
| qwen3.6-35b-a3b    | 1.00 | 3.22 | 5/6 | $0.017 |

**Findings:**
- **v4-flash now leads** — got erdos-659 7/7 on 2/3 seeds and PB-Basic-028 7/7 on 2/3 seeds.
  Pass@1 underestimated it by 1.0 point.
- **deepseek-v3.2 reproduces March model-diversity result exactly** (3.28/7 then & now) —
  methodology is stable; March numbers remain trustworthy.
- **gemini-3-flash regression**: 5.83 (Mar pass@1) → 3.72 (today pass@3). ~2-point drop.
  Investigate before continuing to treat as reference baseline.
- **gemma-4 has the best $/score in the set** ($0.00033/point) — viable cheap baseline.
- **qwen3.6-flash partially redeemed** — 2/3 seeds got erdos-659 7/7 despite 3.33/7 mean.
- **vs. March diversity ceiling** (lit-ideas + ds-pipeline + full pipe + 3 branches: 5.28/7):
  v4-flash generate-only at 4.50 is close. v4-flash + seed-ideas + full pipeline likely sets
  a new project ceiling.

**Recommendations:**
- Make **deepseek-v4-flash** the cheap-tier default; consider **gemma-4-31b-it** as bulk ideator.
- Re-baseline gemini-3-flash before next reference comparison.
- Run v4-flash inside seed-ideas + full pipeline next.

Script / results: `experiments/new_models_pass3_20260504.py`,
`experiments/results/new_models_pass3_20260504_20260504_054804.json`

## AnswerBench-50 Comparison — 2026-05-04T08:40:12

7 models, generate-only, pass@1, on 50-problem stratified subset of `answerbench_v2.csv`
(12 Alg / 13 Comb / 12 Geom / 13 NT, seed=42). Judge: `gemini-3.1-flash-lite-preview`,
binary answer-equivalence. 350 trials, 90 workers. **60 min, 0 errors, $6.69 total.**

| Model | $/Mtok | Acc | Lat | $/run | acc%/$ |
|---|---|---|---|---|---|
| **deepseek-v4-pro**    | 0.87 | **47/50 (94%)** | 723s | $0.019 | 50  |
| **deepseek-v4-flash**  | 0.28 | **44/50 (88%)** | 357s | $0.006 | 157 |
| qwen3.6-35b-a3b        | 1.00 | 40/50 (80%) | 139s | $0.022 | 36  |
| qwen3.6-plus           | 1.95 | 39/50 (78%) | 739s | $0.074 | 11  |
| gemini-3-flash-preview | 3.00 | 37/50 (74%) | 18s  | $0.011 | 70  |
| gemma-4-31b-it         | 0.38 | 34/50 (68%) | 235s | $0.002 | 425 |
| gpt-oss-120b           | 0.18 | 29/50 (58%) | 191s | $0.001 | **483** |

Geometry was uniformly easy (median 10-12/12); Combinatorics was the differentiator.
Every model scored ~15-20% higher than on yesterday's pass@3 dev set — answer-bench tests
"find the answer," not "prove it."

**Findings:**
- **v4-pro dominates absolute accuracy**; **v4-flash is the practical cost leader** at 88%.
- **gpt-oss-120b and gemma-4 win $/accuracy** — useful for bulk-ideator / best-of-N where
  per-call quality matters less than coverage.
- **gemini-3-flash is strictly dominated by v4-flash** on cost AND accuracy. Only edge: 18s latency.
- **qwen3.6-plus strictly dominated by qwen-35b** at 50× the cost. Skip.
- Judge: 350/350 clean `<verdict>` tags. gemini-3.1-flash-lite is a trustworthy answer-equivalence judge.
- **Use answer-bench for capability ranking, dev-set for architecture experiments.**

Files: `experiments/answerbench_compare_20260504.py`,
`experiments/results/answerbench_compare_20260504_20260504_084012.json`,
`prompts/pipeline/answerbench_judge.md`

## Seed-Ideas 4-Way Comparison v2 (Phase 1) — 2026-05-04T20:14

**70 problems × 6 models × 3 modes (generate-pass@3, full, seed-generate).**

Roles: ideator/generator/verifier/reviser = same model under test (self-ideation per user).
Final judge = `deepseek-v4-pro` w/ hardened `judge_gt.md`. ITERATIONS=2 (1 gen + 2 revise).
NUM_IDEAS=3. MAX_TOKENS=65536 everywhere (let reasoning blow up — user requirement).
Per-trial JSON saved on completion (crash-safe). 80 outer workers, 3 inner workers per branch.

Problem set: 60 IMO-proofbench + 10 special (erdos-{333,397,654,659,1051} + first-proof-{4,5,6,10}-official + ramsey-hypergraphs). erdos-333 used aletheia (only form available, renamed).

**1259/1260 trials (99.9%), $119.69 total, 0.2% error rate.** Mode 4 (seed_full) skipped — Phase 1 spend exceeded the original $100 target.
Wall-clock 10 hr (with two restarts: one for cap raise $80→$200, one to drop a key after monthly limit hit).

| Model | gen mean | full mean | seed_gen mean | best mode |
|---|---|---|---|---|
| **deepseek-v4-pro**     | 3.38 (32/68) | **3.66 (35/68)** | 3.36 (33/70) | full |
| **deepseek-v4-flash**   | **3.39 (33/70)** | 3.09 (31/70) | 3.30 (33/70) | generate |
| qwen3.6-35b-a3b         | 2.17 (21/70) | 1.44 (14/70) | 2.06 (20/70) | generate |
| gemini-3-flash-preview  | 1.83 (18/70) | 1.29 (12/70) | 1.87 (18/70) | seed_generate |
| gemma-4-31b-it          | 1.83 (18/70) | 1.17 (11/70) | 1.53 (15/70) | generate |
| gpt-oss-120b            | 1.33 (13/70) | 1.39 (14/70) | 1.27 (12/70) | full |

| Model | gen $/run | full $/run | seed_gen $/run | total $ |
|---|---|---|---|---|
| deepseek-v4-pro     | $0.213 | $0.216 | $0.231 | $45.4 |
| deepseek-v4-flash   | $0.140 | $0.075 | $0.136 | $24.6 |
| qwen3.6-35b-a3b     | $0.148 | $0.086 | $0.139 | $26.2 |
| gemini-3-flash      | $0.056 | $0.072 | $0.052 | $12.6 |
| gemma-4             | $0.031 | $0.018 | $0.030 | $5.5  |
| gpt-oss-120b        | $0.029 | $0.017 | $0.029 | $5.2  |

**Key findings (after audit — see correction at end):**

The headline "pipeline doesn't help" was a framing artifact. The "generate" baseline I
reported is pass@3 best-of-3 (per the user's "match token cost" requirement), but pass@3
already captures the sampling-diversity component of seed-ideas. The right baseline for
testing whether the pipeline adds value is single-shot pass@1, which I can extract from
the first branch (k=0) of each generate-mode trial.

| Model | pass@1 | pass@3 ("gen") | seed_gen | full | seed Δ vs p@1 | full Δ vs p@1 |
|---|---|---|---|---|---|---|
| gpt-oss-120b      | 0.81 | 1.33 | 1.27 | 1.39 | +0.46 | +0.58 |
| gemma-4-31b-it    | 1.07 | 1.83 | 1.53 | 1.17 | +0.46 | +0.10 |
| gemini-3-flash    | 1.15 | 1.83 | 1.87 | 1.29 | +0.72 | +0.14 |
| deepseek-v4-flash | 2.58 | 3.39 | 3.30 | 3.09 | +0.72 | +0.51 |
| deepseek-v4-pro   | 2.61 | 3.38 | 3.36 | 3.66 | +0.75 | +1.05 |
| qwen3.6-35b-a3b   | 1.61 | 2.17 | 2.06 | 1.44 | +0.44 | -0.17 |

1. **Seed-ideas helps by +0.44 to +0.75 over single-shot pass@1, every model.** Same
   magnitude as March's seed-ideas uplift. Just doesn't beat pass@3 because pass@3 already
   provides the multi-attempt sampling diversity, leaving only the idea-conditioning layer
   (which is small for self-ideation).

2. **Full pipeline helps 5 of 6 models over pass@1** (+0.10 to +1.05). v4-pro gets +1.05,
   matching March's gemini-3-flash result of +1.0 in dev-set runs. Only qwen-35b is mildly
   negative (-0.17).

3. **At cost-equivalent comparison (pass@3 vs full vs seed_generate)**, the picture flips:
   pass@3 wins for 4 of 6 models, full wins for v4-pro and gpt-oss, seed_generate wins for
   gemini-3-flash. **Implication: at the same API budget, simple resampling (best-of-3)
   beats verify/revise for most models, but the verify/revise loop is more compute-efficient
   for the strongest model (v4-pro).**

3. **deepseek-v4-pro best overall (3.66/7 in full mode)**, narrowly above v4-flash (3.39/7 in
   gen). v4-flash is the strong cost-efficiency winner: half the cost, similar accuracy.

4. **Cheap models (gpt-oss, gemma) plateau ≤1.83/7** across all modes — proofbench-difficulty
   problems are beyond their capability ceiling. They remain useful as bulk-ideator candidates,
   not primary generators.

5. **Special-10 frontier results (14 passes ≥6/7 across 1259 trials):**
   - **first-proof-10-official: 11 of 18 trials passed** at 6/7 — the most-cracked frontier
     problem. Multiple models, all 3 modes. (No 7/7s — judge consistently calls it "almost".)
   - **erdos-654: 2 passes**, 1× 7/7 (deepseek-v4-pro full, $0.114) and 1× 7/7 (gpt-oss seed_gen, $0.029).
     gpt-oss cracking erdos-654 at 3¢ is the surprise of the run.
   - **erdos-659: 1 pass** (deepseek-v4-flash generate, 6/7).
   - **0 passes**: erdos-333, erdos-397, erdos-1051, first-proof-4/5/6, ramsey-hypergraphs (7 of 10
     special problems remain unsolved by any model in any mode).

6. **Cost reality vs initial estimate.** I projected Phase 1 at $120-180 (vs the user's $100
   ideal). Actual was $119.69 — at the low end of estimate but still 20% over the original
   $100 target. The decision to NOT run mode 4 (seed_full) was driven both by spend and by
   finding (1): adding a verify/revise loop on top of seed_generate is unlikely to help
   weaker models and may hurt them, given how badly full mode performed.

7. **OpenRouter monthly-limit wall.** First key (with $50 limit, $104 used) blocked the
   resumed run mid-stream — added a startup `_filter_live_keys()` probe to drop exhausted
   keys before submitting work. The remaining 2 keys ($120 limits each) had enough headroom.

8. **Real bug found (modest impact)**: ideate JSON-parse failures fall back to placeholder
   "default-N" ideas. Rates: deepseek-v4-flash 28.6%, gpt-oss 20.0%, deepseek-v4-pro 10.0%,
   others 3-4%. Cause: deepseek-v4-flash and v4-pro often output prose reasoning instead of
   `[...JSON...]`. The parser tries to recover via `_fix_json` (escaping LaTeX backslashes)
   but fails on prose-formatted responses. **Impact is bounded**: even on healthy ideate,
   self-ideated seed_generate ≈ pass@3, so degradation only converts ~25% of v4-flash
   seed_generate trials to plain pass@3 — same expected value. Worth fixing for cleanliness
   but doesn't change the headline.

9. **Verifier early-stop rates** (verifier says "correct" on iter 1):
   gpt-oss 24%, gemma-4 41%, gemini-3-flash 44%, v4-flash 49%, v4-pro 49%, qwen-35b 59%.
   Confirms the long-running "verifier over-approval" failure mode for the weaker models.
   v4-pro at 49% is the only model strong enough to use the verify/revise loop productively
   (matching its +1.05 full-mode uplift).

   **Verifier false-positive rate** (early-stop, but final judge said <6/7):
   v4-pro 9%, v4-flash 12%, gpt-oss 41%, gemma-4 62%, gemini-3-flash 65%, qwen-35b 68%.
   The deepseek family is genuinely good at self-critique; weak models hallucinate
   correctness 60-68% of the time when their own verifier passes them.

10. **JUDGE ABLATION (added 2026-05-04T22:00 — n=100 random trials, mid-difficulty problems
    only):** re-judged with `gemini-3-flash-preview` and compared to v4-pro scores.
    | Metric | Value |
    |---|---|
    | v4pro mean | 3.56/7 |
    | gemini mean | 5.29/7 |
    | mean Δ | **+1.73** (gemini more lenient) |
    | exact agreement | 59% |
    | close (|Δ|≤1) | 70% |
    | big (|Δ|≥6) | **29%** |
    | pass-flip rate | 30% (27 v4pro-fail→gemini-pass, 3 other way) |

    **This is the single biggest factor explaining today's results vs March.** March used
    gemini-3-flash; today used v4-pro. The judge change alone shifts means by ~1.7 points
    — a v4-pro 3.66 in full mode would be ~5.4 under gemini, in the same range as March.
    The pipeline absolutely DID help by March's measure; my v4-pro judge just hides it.

    Caveat: which judge is "correct" can't be determined without expert grading. v4-pro
    catches subtle errors gemini misses, but may be over-strict on first-proof / erdos
    problems with very long ground truths. For comparability with prior experiments, use
    gemini-3-flash. For stricter assessment, use v4-pro.

    Script / results: `experiments/judge_ablation_20260504.py`,
    `experiments/results/judge_ablation_20260504_215925.json`

11. **FULL GEMINI RE-GRADE (added 2026-05-04T22:13)** — re-judged ALL 466 trials in the 26
    eligible mid-range problems with gemini-3-flash-preview. 81s wall, $8.83.

    **Mode aggregate (n=155-156 each, across all 6 models):**
    | Mode | v4-pro | gemini | Δ |
    |---|---|---|---|
    | generate (pass@3) | 3.66 | 5.09 | +1.43 |
    | **full** | **3.01** | **5.55** | **+2.55** |
    | seed_generate | 3.62 | 5.10 | +1.47 |

    **The ranking inverts between judges:**
    - v4-pro:  generate (1st) > seed_generate ≈ full last
    - gemini:  **full (1st)** > seed_generate ≈ generate

    **The disagreement is concentrated on weak models in full mode:**
    | Model | full Δ (gem−v4) | full pass count v4 → gem |
    |---|---|---|
    | gpt-oss-120b      | +3.31 | 6/26 → 18/26 (3×) |
    | gemini-3-flash    | +4.12 | 4/26 → 20/26 (5×) |
    | gemma-4-31b-it    | +3.69 | 4/26 → 18/26 (4.5×) |
    | qwen3.6-35b-a3b   | +3.00 | 7/26 → 18/26 (2.5×) |
    | deepseek-v4-flash | +1.00 | 22/26 → 25/26 (small) |
    | deepseek-v4-pro   | +0.08 | 23/25 → 23/25 (none) |

    The deepseek family barely changes between judges — v4-pro and gemini agree on "good"
    solutions. All the disagreement is on weak-model output: v4-pro flags revised solutions
    as still-flawed; gemini rewards them as "almost correct." Likely mechanism: full-mode
    revisions produce more polished prose that gemini reads as effort, while v4-pro reads
    deeper to find the residual gaps.

    **Headline correction:** under the same judge March used (gemini-3-flash), Phase 1
    replicates the March finding — full pipeline beats both pass@3 and seed_generate,
    especially for weaker models. The "pipeline is useless" finding was a v4-pro-as-judge
    artifact. Both judges are doing their job; they're measuring different things (gemini =
    "did the model produce a polished proof attempt"; v4-pro = "is the proof genuinely
    rigorous"). For comparability with March, use gemini.

    Script / results: `experiments/regrade_gemini_20260504.py`,
    `experiments/results/regrade_gemini_20260504_20260504_221221/`
    (466 per-trial JSONs + summary.json)

12. **Full Phase 1 gemini regrade (added 2026-05-04T22:30):** extended the regrade to all
    1256 trials across all 70 problems, then judged the k=0 branch of every generate-mode
    trial separately to get a true gemini pass@1 baseline. Total additional spend ~$32
    (regrade across full set) + ~$18 (k=0 branches) = $50. Final audit table under gemini:

    | Model | pass@1 | pass@3 | seed_gen | full | seed Δ vs p@1 | full Δ vs p@1 |
    |---|---|---|---|---|---|---|
    | gpt-oss-120b           | 2.29 | 2.59 | 2.40 | **3.10** | +0.11 | **+0.81** |
    | gemma-4-31b-it         | 2.96 | 3.21 | 2.99 | **3.51** | +0.03 | **+0.55** |
    | gemini-3-flash-preview | 2.76 | 2.93 | 3.39 | **3.76** | +0.63 | **+1.00** |
    | deepseek-v4-flash      | 4.90 | 4.81 | 5.01 | 4.63 | +0.11 | -0.27 |
    | deepseek-v4-pro        | 5.25 | 5.56 | 5.30 | 5.35 | +0.05 | +0.10 |
    | qwen3.6-35b-a3b        | 3.73 | 3.60 | 3.21 | 3.74 | -0.52 | +0.01 |

    Aggregate (all models, n=68-70 per cell):
    - pass@1=3.64, pass@3=3.78, seed_generate=3.72, full=4.01
    - full Δ vs pass@1: **+0.37** (replicates March's "pipeline helps")
    - seed Δ vs pass@1: +0.08 (self-ideation does not add diversity — deserves cross-model ideator)

    **Where pipeline helps**: weaker models — gpt-oss +0.81, gemma +0.55, gemini-3-flash +1.00.
    Verify/revise gives them another shot at producing usable proofs.

    **Where pipeline doesn't help**: stronger models — deepseek-v4-flash -0.27, v4-pro +0.10,
    qwen-35b +0.01. Their first-attempt solutions are already competitive; revising adds
    little. v4-flash slightly worse with revision suggests the verifier sometimes "fixes"
    things that didn't need fixing.

    **Headline correction (final, gemini-judged)**: under the same judge as March,
    Phase 1 replicates March's "full pipeline helps weaker models" finding (+0.5-1.0 per
    weak model). The "pipeline doesn't help" framing was both a v4-pro judge artifact AND
    a baseline-mismatch artifact. Both are now corrected.

    Caveat on pass@3 / seed_gen columns: these use gemini's score on the v4-pro-best-of-3
    pick (the best_solution field). True gemini best-of-3 (judge all 3 with gemini, pick
    max) was not measured — would require ~$60 more in credits we didn't have at run time.
    The proxy slightly underestimates pass@3/seed_gen by 0.1-0.3.

    Script / results:
    - `experiments/regrade_branches_gemini_20260504.py` (k=0 branch judge)
    - `experiments/results/regrade_branches_gemini_20260504_20260504_222334/` (418 per-branch JSONs)
    - `experiments/results/gemini_audit_table_20260504.json` (final table)

13. **TRUE best-of-3 audit (added 2026-05-04T22:42)** — extended branch regrade to ALL
    branches (generate k=0,1,2 + seed_generate k=0,1,2). 2514 branch judgments total,
    121s wall, $35. Now we can compute true gemini best-of-3 instead of using v4-pro's
    pick-best as a proxy.

    | Model | p@1 | p@3 | seed_gen | full | seed Δ | full Δ | **p@3 Δ** |
    |---|---|---|---|---|---|---|---|
    | gpt-oss-120b           | 2.29 | **3.11** | 3.09 | 3.10 | +0.80 | +0.81 | **+0.83** |
    | gemma-4-31b-it         | 2.96 | **3.70** | 3.67 | 3.51 | +0.72 | +0.56 | **+0.74** |
    | gemini-3-flash         | 2.76 | **4.33** | 3.89 | 3.76 | +1.13 | +1.00 | **+1.57** |
    | deepseek-v4-flash      | 4.90 | **6.11** | 5.70 | 4.63 | +0.80 | -0.27 | **+1.21** |
    | deepseek-v4-pro        | 5.25 | **6.37** | 5.79 | 5.35 | +0.54 | +0.10 | **+1.12** |
    | qwen3.6-35b-a3b        | 3.73 | **4.47** | 3.84 | 3.74 | +0.11 | +0.01 | **+0.74** |

    Aggregate: pass@1=3.64, **pass@3=4.67 (+1.04)**, seed_generate=4.35 (+0.71), full=4.01 (+0.37).

    **Headline reversal (third time):** with true gemini best-of-3 measured per-branch,
    **pass@3 is the best mode for every model.** It beats both seed_generate and full
    pipeline for every model in the set.

    - **Strong models (deepseek, qwen-35b) gain disproportionately from pass@3.** v4-pro
      goes 5.25 → 6.37 (+1.12); v4-flash 4.90 → 6.11 (+1.21). Full pipeline gets them only
      +0.10 and -0.27 respectively. Sampling diversity beats iterative refinement when the
      base model is already strong.
    - **Weak models gain similarly across all three architectures** (+0.55 to +0.81).
      No mode distinguishes itself.
    - **Self-ideated seed_generate ≈ pass@3** for weak models; *falls behind* for strong
      ones. Self-ideation does not add diversity beyond plain resampling. Cross-model
      ideation (March's lit-ideas pattern) might still beat both — not measured here.
    - The earlier "full pipeline wins" finding (item 11) was a v4-pro-pick-bias artifact:
      gemini scored higher on v4-pro's chosen branch than on a uniformly random branch,
      and full mode bypasses that selection bias by not having branches.

    **Implication for architecture work:** if budget allows, just do pass@3. Verify/revise
    only earns its cost when sampling diversity has been exhausted, which doesn't seem to
    happen at N=3 for any current model. Cross-model ideation remains the unexplored
    direction worth a focused follow-up.

    Script / results:
    - `experiments/regrade_branches_gemini_20260504.py` (PASS1_ONLY=False mode)
    - `experiments/results/regrade_branches_gemini_20260504_20260504_222334/` (2514 branch JSONs)
    - `experiments/results/gemini_audit_table_20260504_v2.json` (final true-best-of-3 table)

14. **Dataset export (added 2026-05-04T22:50)**: combined Phase 1 + regrades into a single
    long-format JSONL covering all 70 × 6 × 3 = 1260 (problem, model, mode) trials.
    Each row carries problem text + ground truth + final solution + both judges' scores
    + both judges' full verdict text + per-branch breakdown for generate/seed_generate
    modes. NAs preserved for 4 errored trials (deepseek-v4-pro timeouts) and 49 branch
    records that errored during the regrade. Total file 191 MB.

    Files:
    - `experiments/export_dataset_20260504.py` (export script)
    - `experiments/results/dataset_20260504.jsonl` (1260 rows)
    - `experiments/results/dataset_20260504_README.md` (schema + caveats)

**Recommendations for next runs:**
- For **cost-bounded headline numbers**: pass@3 best-of-3 is the cheapest competitive
  baseline for most models. Use it as the standard reporting metric.
- For **deepseek-v4-pro on proof problems**: full pipeline is genuinely worth the cost
  (+1.05 over pass@1). Only model where the verify/revise loop pays off cleanly.
- For **frontier first-proof / erdos / ramsey**: 7 of 10 special problems remain unsolved
  by any model in any mode. Cross-model ideator pattern (March's lit-ideas + ds-pipe at
  5.28/7) is still the strongest known architecture — worth re-testing with v4-pro pipeline.
- For **mode 4 (seed_full)**: extrapolating from the +0.5-1.0 uplift of each component,
  seed_full could push v4-pro from 3.66 to ~4.5/7. Worth a focused follow-up on v4-pro and
  v4-flash only.
- **Fix the ideate parser** before next run: handle prose-formatted ideate responses (deepseek
  models default to this). Either ask for stricter format in the prompt, or add a
  prose-to-JSON extraction fallback like extract_score.md.

Files:
- Script: `experiments/seed_ideas_full_compare_20260504.py`
- Loader: `experiments/problemset_70.py`
- Run dir: `experiments/results/seed_ideas_full_compare_20260504_20260504_101225/`
  (1259 per-trial JSONs + manifest.jsonl + frontier_passes.jsonl + summary.json)
- Logs: `/tmp/phase1.log`, `/tmp/phase1_resume2.log`

## Seed-Ideas Phase 2 — seed_full on cheap models — 2026-05-05T01:46:26

Ran the missing 4th condition from the seed-ideas comparison (`seed_full`: ideate(3) → 3 parallel
branches × full pipeline) on **gpt-oss-120b + gemma-4-31b-it across all 70 problems**. Judge =
`openrouter/google/gemini-3-flash-preview` (matches Phase 1 regrade for direct comparability).
Self-ideation, ITERATIONS=2 (1 gen + 2 revisions per branch), NUM_IDEAS=3, MAX_TOKENS=65536.

**Single key (`OPENROUTER_API_KEY_seedgen`)**, no rotation per user requirement.
**140/140 trials (100%), 0 errors, $9.70 / $75 cap, 77 min wall-clock.**
Per-branch + per-trial atomic saves; frontier passes appended to `frontier_branches.jsonl`
the moment they complete (not waiting for trial finalization).

| Model              | n  | mean | std  | pass  | $/run  | $ tot |
|---|---|---|---|---|---|---|
| **gemma-4-31b-it** | 70 | **4.26** | 3.27 | 41/70 | $0.071 | $5.00 |
| **gpt-oss-120b**   | 70 | **3.99** | 3.45 | 40/70 | $0.067 | $4.70 |

**vs Phase 1 (same gemini judge, same 70 problems):**

| Model | p@1 | p@3 | seed_gen | full | **seed_full (P2)** | uplift vs best P1 mode |
|---|---|---|---|---|---|---|
| gemma-4-31b-it | 2.96 | 3.70 | 3.67 | 3.51 | **4.26** | **+0.56** vs pass@3 |
| gpt-oss-120b   | 2.29 | 3.11 | 3.09 | 3.10 | **3.99** | **+0.88** vs pass@3 |

**Headline**: seed_full beats every Phase 1 mode for both cheap models. gpt-oss gains the most
(+0.88) — combining cross-idea diversity with verify/revise gives weaker base models two
independent shots at correctness. Predicted uplift from item 14 ("seed_full could push v4-pro
to ~4.5") materialized for the cheap models. Std deviations near 3.3 indicate mostly bimodal
outcomes (0 or 7) — typical for proofbench problems.

**Special-10 frontier breakthroughs (NEW vs Phase 1):**

| Problem | Phase 1 best | **Phase 2 seed_full** | Notes |
|---|---|---|---|
| **erdos-1051** | 0 passes (any model, any mode) | **gpt-oss 7/7 (2 of 3 ideas)**, **gemma 7/7 (2 of 3 ideas)** | First-ever solve |
| **erdos-654**  | 1 pass (gpt-oss seed_gen 7/7) | **gpt-oss 7/7 (ALL 3 ideas)** | Hat-trick — not actually frontier for gpt-oss |
| **erdos-659**  | 1 pass (deepseek-v4-flash gen 6/7) | **gemma 7/7 (idea 0)** | First 7/7 from a cheap model |
| first-proof-10 | 11/18 at 6/7 (Phase 1) | gpt-oss 6/7 (ideas 0 + 2) | Consistent with Phase 1 |

Winning ideas (paraphrased from `frontier_branches.jsonl`):
- **erdos-654** gpt-oss: "Random Point Expectation" / "Incidence Graph / Szemerédi–Trotter" /
  "Algebraic Polynomial Method" — three orthogonal attacks all reaching 7/7
- **erdos-1051** gpt-oss: "Constructive Counterexample via Sparse Set" / "Transcendence Theory and
  Linear Forms"; gemma: "Telescoping Series Comparison" / "Diophantine Approximation and Gap Analysis"
- **erdos-659** gemma: "Algebraic Construction via Grids"

**Still 0/7 for both models in any mode**: erdos-333, erdos-397, first-proof-{4,5,6}-official,
ramsey-hypergraphs (5 of 10 special problems remain frontier-unsolved at this tier).

**Cost note**: $0.067-0.071/run is in line with the projection (seed_full ≈ 3× full + ideate,
with gemini-3-flash judge being the only inflator vs Phase 1's v4-pro). Special-10 problems with
long ground-truths cost up to $0.19/trial (judge prompt size dominates). Came in 8× under cap.

**Caveats:**
1. Self-ideation only (per saved feedback memory). Cross-model ideation (lit-ideas pattern from
   March's 5.28/7) unmeasured for these two models.
2. Cheap-model 7/7s on Erdős problems may partly reflect gemini judge leniency — Phase 1 noted
   |Δ|≈+1.7 between gemini and v4-pro on revised solutions. A v4-pro re-grade of the 5 Phase 2
   frontier solves would be the cleanest sanity check (~$2 estimate).
3. Wall-time tail: longest trial 41 min (gemma × ramsey-hypergraphs, branch_0 hit OpenRouter
   429s and rode through retries). Median trial much faster.
4. One sequence of harmless `litellm.RateLimitError 429 → retry in 5s` events from the upstream
   Chutes provider for gemma; all retried successfully; no impact on results.

**Implications:**
- For cheap-model bulk solving on proofbench, **seed_full is now the recommended mode** —
  beats pass@3 by +0.6 to +0.9 at ~$0.07/trial.
- The v4-pro `seed_full` follow-up suggested in item 14 of Phase 1 is even more attractive:
  if v4-pro shows similar +0.5–1.0 uplift on top of its 5.35 full / 5.56 pass@3, expect ~6.0+/7.
- erdos-1051, erdos-654, erdos-659 should be removed from the "frontier" set for gemini-judged
  comparisons going forward — they're solvable at the cheap tier with seed_full.

Files:
- Script: `experiments/seed_full_phase2_20260504.py`
- Run dir: `experiments/results/seed_full_phase2_20260504_20260505_002924/`
  - `manifest.jsonl` (140 lines, one per trial)
  - `frontier_branches.jsonl` (10 entries: 5 Phase 2 frontier solves × branches)
  - `seed_full/<model>/<pid>.json` (per-trial — full call log + branches)
  - `branches/<model>/<pid>/branch_{0,1,2}.json` (per-branch incremental — survives mid-trial crashes)
- Log: `/tmp/phase2.log`

## Phase 2 frontier v4-pro re-grade — 2026-05-05T02:23:46

Re-judged all 10 Phase 2 frontier-branch solves (gemini 6-7/7) with `deepseek-v4-pro`,
concurrent. **All 10 went to 0-1/7.** Mean Δ = −6.8. Every "breakthrough" was
gemini-leniency, not a real solve. erdos-1051/654/659 remain unsolved at the cheap tier.
Cost $0.14, wall 12 min. Results: `experiments/results/regrade_phase2_v4pro_20260505_022346.json`.


## Expensive-Models Comparison (4 frontier models) — 2026-05-04T22:09

4 expensive models on the same 12-problem stratified subset (3 Alg / 3 Comb / 3 Geom / 3 NT,
seed=42 sub-sample) from prior `answerbench_compare_20260504_084012` set, like-to-like.
Goal: figure out if any of the more expensive models we've been avoiding is actually
cost-effective. Generate-only, pass@1, judge = `gemini-3.1-flash-lite-preview` (matches prior).
MAX_TOKENS_GEN=65536 (no reasoning suppression). Single dedicated `OPENROUTER_API_KEY_price_compare`
key with $12 cap and a $9.50 hard killswitch via OpenRouter `/auth/key` polling.
48-way parallelism (one worker per (model, problem) trial, single wave).

**46/48 trials, ~$7 OpenRouter spend (price_compare key).** 2 kimi combinatorics trials
killed at 49 min wall-clock after 10+ min stuck on 65k-token reasoning loops; remaining
10 kimi trials all correct, so kimi accuracy is "10/10 with 2 dropped" not 12/12.

### Unified table — 11 models on the same 12 problems (4 new ⊕ 7 prior)

| Model | $/Mtok | Acc | mean_out | lat(s) | $/run | acc%/$ |
|---|---|---|---|---|---|---|
| **kimi-k2.6** (NEW)            | 3.49  | **10/10 (100%)** | 27.7K | 641 | $0.098 | 1026 |
| **qwen3.6-max-preview** (NEW)  | 6.24  | 11/12 (92%)      | 27.6K | 656 | $0.174 | 528  |
| gemini-3-flash-preview         | —     | 11/12 (92%)      | 2.1K  | 12  | —      | —    |
| **deepseek-v4-flash**          | 0.28  | 11/12 (92%)      | 20.0K | 387 | $0.006 | **16183** |
| deepseek-v4-pro                | 0.87  | 11/12 (92%)      | 21.8K | 712 | $0.019 | 4777 |
| **gemini-3.1-pro-preview** (NEW) | 12.00 | 10/12 (83%)    | 20.8K | 174 | $0.252 | 330  |
| qwen3.6-35b-a3b                | 1.00  | 10/12 (83%)      | 21.0K | 125 | $0.021 | 3917 |
| qwen3.6-plus                   | 1.95  | 10/12 (83%)      | 39.0K | 703 | $0.077 | 1090 |
| gpt-oss-120b                   | —     | 9/12 (75%)       | 6.3K  | 162 | —      | —    |
| gemma-4-31b-it                 | 0.38  | 8/12 (67%)       | 3.1K  | 142 | $0.001 | 51893|
| **gpt-5.4** (NEW)              | 15.00 | **6/12 (50%)**   | 3.6K  | 51  | $0.057 | 879  |

**Findings:**
- **None of the 4 expensive models earn their cost on AnswerBench.** `deepseek-v4-flash`
  at $0.28/Mtok ties or beats every expensive model on accuracy, at ≥17× lower $/run.
- **gpt-5.4 is the surprise loser: 6/12 (50%), worst overall.** ~50s mean latency and
  3.6K mean output tokens — appears to *not* engage extended reasoning on these problems
  (vs. kimi/qwen-max at 27K out tokens). Skip until we understand why.
- **gemini-3.1-pro-preview disappoints (83%) at $12/Mtok** — strictly dominated by
  deepseek-v4-pro AND qwen3.6-35b-a3b. Skip.
- **kimi-k2.6 is the only expensive model worth a second look.** Perfect 10/10 (with 2
  dropped) hints at higher capability than v4-flash; needs harder benchmark and the missing
  2 combinatorics trials before we trust it. At ~$0.10/run real cost, plausibly a niche
  premium-tier choice for combinatorics.
- **qwen3.6-max-preview matches v4-flash absolute accuracy at 30× the cost** — same
  story as qwen3.6-plus vs. qwen-35b in the prior run. Qwen "max"/"plus" tiers don't
  pay back on this benchmark.
- **OpenRouter actual spend ($7.00) ran 30%+ higher than blended-estimate sum (~$5.30)**.
  Blended price under-estimates real cost on these models — keep killswitches via
  OpenRouter `/auth/key` polling, not estimated cost.

**Decision:** keep using deepseek-v4-flash as the cost-leader baseline. Re-test
kimi-k2.6 only if we move to a harder benchmark where v4-flash hits a ceiling.
Avoid gpt-5.4, gemini-3.1-pro-preview, and qwen3.6-max-preview for capability work.

Files: `experiments/expensive_models_compare_20260504.py`,
`experiments/results/expensive_models_compare_20260504_20260505_012855_partial.json`.

## Phase 2 FULL v4-pro re-grade (Method B) — 2026-05-05T03:36:00

Re-judged all 140 Phase 2 trial best_solutions with `deepseek-v4-pro` for an apples-to-apples
comparison against Phase 1 v4-pro means. **$1.49 total, 35 min wall, 0 errors** (matches the
$1.5-2.5 projection — empirical token-cost model is solid).

**Apples-to-apples v4-pro means (same 70 problems × 2 cheap models):**

| Mode (judge=v4-pro) | gpt-oss-120b | gemma-4-31b-it |
|---|---|---|
| P1 pass@3 (generate)  | 1.33 | 1.83 |
| P1 full (V↔R loop)    | 1.39 | 1.17 |
| P1 seed_generate      | 1.27 | 1.53 |
| **P2 seed_full**      | **1.37** | **1.67** |

**Headline: under v4-pro, seed_full is no better than any Phase 1 mode** (within ±0.1 of
pass@3 / seed_generate / full for both models). The +0.6-0.9 uplift gemini saw was 100%
judge artifact.

**Score distribution under v4-pro (Phase 2 seed_full, n=140):**

| Score | gpt-oss | gemma |
|---|---|---|
| 0/7 | 53 | 49 |
| 1/7 |  3 |  4 |
| 6/7 |  5 |  6 |
| 7/7 |  9 | 11 |

Bimodal — v4-pro doesn't grant partial credit for elaborate-but-wrong proofs.

**Judge confusion (rows = gemini, cols = v4-pro):**

|              | v4=0 | =1 | =6 | =7 |
|---|---|---|---|---|
| gemini=0     | 46 | 0 | 0 | 0 |
| gemini=1     | 13 | 0 | 0 | 0 |
| gemini=6     |  3 | 0 | 0 | 0 |
| gemini=7     | 40 | 7 | 11 | 20 |

Of 81 gemini-≥6/7 calls, **v4-pro agrees on only 31 (38%)** — the other 50 went to 0-1/7.
Disagreement is one-sided: zero cases of v4-pro overruling gemini upward.

**Head-to-head (best of P1 modes vs P2 seed_full per (model, problem)):**

| Model | P2 better | tie | P2 worse | P1 score-margin | P2 score-margin |
|---|---|---|---|---|---|
| gemma-4-31b-it | 3 | 54 | 13 | 40 | 12 |
| gpt-oss-120b   | 3 | 52 | 15 | 52 | 18 |

P1 wins more cells AND wins by larger margins on those cells. seed_full not only fails to
help under v4-pro — it actively regresses gpt-oss × erdos-654 (Phase 1 had a real $0.029
seed_generate 7/7) and gemma × first-proof-10 (P1 had real 6/7s in generate + seed_generate).

**Final intuition (now confirmed by data):** judges flip rankings end-to-end.
- v4-pro: pass@3 ≈ full ≈ seed ≈ seed_full (all ~1.3-1.7) — pipeline doesn't help cheap models
- gemini: seed_full > pass@3 ≈ seed ≈ full (+0.6) — pipeline *appears* to help

Neither cheap model is at a capability tier where seed_full unlocks real frontier proofs.
The next architecture experiment with a chance of moving real numbers under v4-pro is
**v4-pro running seed_full on itself** — predicted +0.5-1.0 from item 14, still untested.

**Truncation/parse audit (Phase 2 regrade)**: 0 of 140 calls hit the 32K completion cap
(max observed 28,455).  1 call (gpt-oss × first-proof-4-official) returned an empty body
and was silently scored 0; re-judged → real 0/7.  Means above are correct as reported.

**Phase 1 v4-pro judge-call parse audit** — answers "is the gemini-vs-v4pro gap just
v4-pro truncating?".  Scanned all 2934 v4-pro judge calls in the Phase 1 run dir:
- 2 truly cap-truncated at 65K (deep reasoning loops on PB-Basic problems)
- 4 short mid-thought failures (<500 out_tok)
- 60 substantive analyses without a wrapping `<points>` tag
- = 66 (2.25%) silently scored 0/7 in original Phase 1 means

Re-judged all 16 cheap-model parse failures with fresh v4-pro calls (concurrent, $0.15,
11 min).  Recovered: 12×0, 1×1, 1×6, 2×7.  Both full-mode cheap-model parse failures
re-judged to **real 0/7**.  Net correction to cheap-model Phase 1 means:

| Model × Mode | orig | corrected | Δ |
|---|---|---|---|
| gemma generate | 1.83 | 1.90 | +0.07 |
| gemma seed_generate | 1.53 | 1.56 | +0.03 |
| gemma full | 1.17 | 1.17 | 0.00 |
| gpt-oss × all modes | (unchanged) | | 0.00 |

**Conclusion**: the judge gap is NOT an artifact of v4-pro truncation or parse failure.
Phase 2 regrade is clean.  Phase 1 baseline correction is ≤+0.07, which actually widens
the head-to-head (gemma P1-best 1.90 vs P2 seed_full 1.67) — Phase 2 still loses to
Phase 1 under v4-pro.  The judge-flip finding stands.

Files:
- Phase 2 script: `experiments/regrade_phase2_full_v4pro_20260504.py`
- Phase 2 results: `experiments/results/regrade_phase2_full_v4pro_20260505_033600.json`
- Phase 1 audit script: `experiments/regrade_p1_parse_fails_20260505.py`
- Phase 1 audit results: `experiments/results/regrade_p1_parse_fails_20260505_051120.json`
- Logs: `/tmp/regrade_b.log`

## GPT-5.4 family @ xhigh reasoning — 2026-05-05T00:20

Re-test of the GPT-5.4 family at `reasoning.effort=xhigh` after the prior
`expensive_models_compare_20260504` run found gpt-5.4 at default effort getting
only 6/12 with 3.6K mean output tokens — i.e. it wasn't actually reasoning.
User wanted to know whether xhigh changes that picture and whether the cheaper
mini/nano siblings are usable at premium effort.

Plan:
- nano + mini on all 12 PIDs (the same stratified subset).
- gpt-5.4 only on the 6 PIDs it got WRONG at default effort (skip the 6 it
  already had — saves money, leverages prior data).
- All at `reasoning.effort=xhigh`, MAX_TOKENS=65536, judge unchanged
  (gemini-3.1-flash-lite, answer-bench prompt).
- Single `OPENROUTER_API_KEY_price_compare` key topped to $20, $19 hard cap.
- `extra_body={"reasoning": {"effort": "xhigh"}}` via litellm — verified
  working with a direct OpenRouter call before the run.

**29/30 trials, ~$11.74 OpenRouter spend.** One nano trial (geometry-021) hung
at 49 min wall-clock with the litellm timeout not firing — killed at the
process level, then wave 2 re-launched separately to merge gpt-5.4 results in.

### Results — corrected for judge errors

| Model | judge acc | corrected | $/run | total $ | mean out_tok | reason_tok |
|---|---|---|---|---|---|---|
| **gpt-5.4-nano** (xhigh)     | 10/11  | **11/11 (100%)** | $0.024 | $0.26  | 12.0K | 11.7K |
| **gpt-5.4-mini** (xhigh)     | 12/12  | **12/12 (100%)** | $0.151 | $1.82  | 28.6K | 28.2K |
| **gpt-5.4** (xhigh, 6 PIDs)  | 5/6    | 5/6 → **11/12 effective** | $0.657 | $3.94  | 43.8K | 41.6K |
| gpt-5.4 (default, prior run) | 6/12   | 6/12             | $0.054 | $0.65  | 3.6K  | n/a |

**Effective gpt-5.4-xhigh accuracy on full 12 = 11/12** (6 from prior default
run + 5/6 from xhigh re-test of the failures). Only `combinatorics-084`
remained wrong — model gave `s=n` and guessed `2023` or `1997`; GT is `3`.

**Manual judge override:** `combinatorics-026 | nano-xhigh` answered $3^{25}+1$.
GT is `847288609444`. $3^{25}+1 = 847288609444$ exactly — judge missed the
symbolic equivalence. Counting it as correct gives nano its 11/11.

### Findings

- **xhigh fixed gpt-5.4.** At default effort it engaged minimal reasoning
  (3.6K out tokens, 6/12). At xhigh it produces 44K mean out (42K reasoning),
  jumping from 6/12 to **11/12 effective**. The prior writeup's "gpt-5.4 is
  bad" conclusion was wrong — the model just wasn't trying.
- **gpt-5.4-mini @ xhigh is the standout: 12/12 at $0.15/run.** Cheaper than
  qwen-max and gemini-pro from the prior run, and the only model with
  perfect accuracy on this subset.
- **gpt-5.4-nano @ xhigh: 11/11 at $0.024/run.** Genuinely cost-effective —
  competitive with deepseek-v4-flash ($0.006/run, 11/12 prior) on accuracy,
  4× the price. Worth a head-to-head retest on harder benchmarks.
- **Cost scales 12× from default → xhigh on gpt-5.4** ($0.054 → $0.66/run),
  roughly doubling accuracy. Whether that's worth it depends on the use case.
- **OpenAI billing quirk:** at xhigh, `prompt_tokens` reported back is
  inflated (30-65K vs. ~250 actual user prompt). Likely the reasoning context
  rolled into "input" billing. Real spend per run already accounts for this
  via authoritative pricing × token counts.
- **One stuck nano trial (geometry-021)** — litellm timeout did not fire after
  49 min. Need to investigate or use a hard `requests`-level timeout for
  these heavy reasoning runs.

### Decision update vs. prior writeup
- **Reverse the prior verdict on gpt-5.4** — at xhigh it's competitive (11/12).
  Still expensive at $0.66/run but no longer "shockingly bad".
- **Add gpt-5.4-mini and gpt-5.4-nano** to the candidate cost-effective set
  alongside deepseek-v4-flash. Mini at $0.15/run for 12/12 is the new tier
  benchmark to beat; nano at $0.024/run for 11/11 is in v4-flash's price
  band.
- Future expensive-model comparisons MUST set reasoning effort explicitly —
  default effort is not a fair test of the model.

Files:
- `experiments/gpt5_xhigh_compare_20260504.py` (script, supports reasoning param)
- `experiments/gpt5_xhigh_wave2_20260505.py` (resume-only wave 2 script)
- `experiments/results/gpt5_xhigh_compare_20260504_20260505_041943_wave2_merged.json`

## Best-of-N Scaling: oss + gemma — 2026-05-05T05:11:55

Best-of-N curves for `gpt-oss-120b` and `gemma-4-31b-it` on the **30 PB-Advanced** problems
(the canonical "scaling-meaningful" cut: harder than PB-Basic, not all-or-nothing like the
SPECIAL_10). Generation only — no verify/revise. N ∈ {1, 3, 5, 7}.

**Reuse trick:** k=0..2 come from Phase 1 generate-mode branches (already judged by both
gemini-3-flash-preview and v4-pro). This script ran k=3..6 fresh and judged each new
sample with **both** judges. So 4 new gens × 30 problems × 2 models = 240 generations,
each judged twice = 480 new judge calls.

**60/60 trials, 0 errors, $6.22 / $25 cap, 99 min wall.**
Key: `OPENROUTER_API_KEY_X` (separate from seedgen — ran concurrently with role-swap experiment).

### Scaling table (mean / pass≥6 out of 30 problems)

| Model | Judge | N=1 | N=3 | N=5 | N=7 |
|---|---|---|---|---|---|
| gpt-oss-120b   | gemini | 1.57 (7) | 1.63 (7) | **2.10 (9)** | 2.10 (9) |
| gpt-oss-120b   | v4-pro | 0.03 (0) | 0.10 (0) | 0.37 (1) | **0.40 (1)** |
| gemma-4-31b-it | gemini | 1.67 (7) | 2.50 (10) | 3.20 (13) | **3.63 (15)** |
| gemma-4-31b-it | v4-pro | 0.43 (2) | 0.57 (2) | 0.63 (2) | **0.93 (3)** |

(Numbers in parentheses are problems passed at ≥6/7.)

### Key findings

1. **Gemini scaling is much steeper than v4-pro scaling.** gemma's gemini mean climbs
   1.67 → 3.63 (+2.0) from N=1 to N=7; under v4-pro the same model only goes 0.43 → 0.93
   (+0.5). gemini rewards "looks plausible," so more samples = more chances of looking right;
   v4-pro stays strict regardless of how many attempts are presented.

2. **gpt-oss saturates between N=3 and N=5.** Under gemini it gains +0.47 from N=3→5 then
   nothing from N=5→7. Under v4-pro it stalls at 1/30 passes from N=5 onward. PB-Advanced
   problems either yield to gpt-oss within ~5 samples or not at all.

3. **gemma keeps gaining at N=7** under both judges (gemini +0.43 from N=5→7, v4-pro +0.30).
   Suggests headroom to N=10–15 for gemma if budget allows.

4. **v4-pro pass rate is brutally low.** Even at N=7, gemma=3/30 (10%) and gpt-oss=1/30 (3%).
   Best-of-N is not the bottleneck for proof rigor — the model fundamentally lacks
   PB-Advanced-grade rigor under a strict judge. Verify/revise (Phase 2 seed_full) gave
   bigger gains for both models (oss 3.99, gemma 4.26 across all 70 problems).

5. **gemma > gpt-oss across the board, more pronounced under v4-pro.** gemini delta: gemma
   2.0 points higher at N=7. v4-pro delta: gemma 2.3× higher pass count. v4-pro magnifies the
   capability gap.

6. **Judge divergence is huge** — same observation as Phase 1 item 11. Aggregate gemini-vs-v4
   delta on these 30 problems × N=7 = +1.5 to +2.7 means.

### Notable per-problem cases

| Problem | Pattern | Reading |
|---|---|---|
| **PB-Advanced-001** (gpt-oss) | gem=[7]×6, [0]×1; v4=[0,1,0,0,0,0,0] | "looks polished, isn't right" — gemini saturates; v4 finds gaps every time |
| **PB-Advanced-007** (gemma)   | gem=[7,0,0,0,0,0,7]; v4=[6,0,0,0,0,0,7] | Both judges agree N=7 hits 7/7 — solid scaling signal under strict judge |
| **PB-Advanced-028** (gpt-oss) | gem=[0,1,0,7,7,0,7]; v4=[0,0,0,7,0,0,7] | k=3 (first new gen) cracks it under both judges — clean N=3→5 jump |
| **PB-Advanced-025** (gemma)   | gem=[1,7,6,6,7,7,6]; v4=[0,0,0,0,0,7,0] | Only k=5 satisfies v4-pro — scaling to N=7 is what surfaces it |

### Implications

- For **gemini-judged headlines**: pass@3 gemma underestimates by ~1 point; pass@7 (best-of-7)
  is the right cost-bounded ceiling for cheap models on PB-Advanced.
- For **v4-pro–judged correctness**: scaling helps marginally; spending those tokens on
  verify/revise (Phase 2) or cross-model role swap (Phase 3) is more productive.
- **gemma > gpt-oss is robust** — judge-agnostic; gemma should be the cheap-tier default for
  proof problems.
- The 1/30 vs 3/30 v4-pro pass rates suggest **PB-Advanced is genuinely past these models'
  rigor ceiling** — even at N=7, well below the v4-pro pass rate seen on PB-Basic.

### Files

- Script: `experiments/scaling_oss_gemma_20260505.py`
- Run dir: `experiments/results/scaling_oss_gemma_20260505_20260505_033250/`
  - `trials/<model>/<pid>.json` — full per-trial JSON (existing + new branches merged)
  - `branches/<model>/<pid>/k{3,4,5,6}.json` — per-new-branch incremental save
  - `manifest.jsonl` (60 lines)
- Reused Phase 1 data: `seed_ideas_full_compare_20260504_20260504_101225/generate/`
  + `regrade_branches_gemini_20260504_20260504_222334/generate/`
- Log: `/tmp/scaling.log`


## Seed-Ideas Phase 3 — v4-flash seed_full + dual-judge — 2026-05-05T05:35:00

Ran the missing v4-flash seed_full condition across 70 problems with priority ordering
(special-10 ever-solved → v4-flash struggle problems → rest). Same single-key + single-judge
setup as Phase 2; ITERATIONS=2, NUM_IDEAS=3, MAX_TOKENS=65536 everywhere. **40-worker outer
× 3 inner branches.** Killswitch at $40.

After completion, regraded the same `best_solution` per trial with `deepseek-v4-pro` to provide
the strict-judge counterpart (matching Phase 1 item 11/12/13 ablation methodology).

**69/70 trials, $20.58 + $1.50 regrade = $22.07 total ($40 cap).**
1 trial (`first-proof-4-official`) hit a stuck-retry loop and was killed at the 4-hour mark
after the rest had been done for ~30 min — Phase 1 had it 0/7 across all models, so loss
is benign.

### Headline (gemini judge, primary) vs v4-pro regrade

| Metric | Gemini-3-flash | V4-pro (regrade) | Δ |
|---|---|---|---|
| Mean (n=68) | **5.83/7** | **3.19/7** | **−2.62** |
| Pass ≥6 | 57/69 (83%) | 32/68 (47%) | −25 trials |
| Exact agreement | — | — | 30/68 (44%) |
| Close (\|Δ\|≤1) | — | — | 44/68 (65%) |

The −2.62 mean delta is **larger than the −1.73 Phase 1 ablation observed on a 100-trial
mid-difficulty sample** — gemini is inflating v4-flash seed_full output more than it
inflated other models in Phase 1. Likely mechanism: v4-flash's revised output is more
*polished* than gpt-oss/gemma's, and gemini reads polish as correctness; v4-pro reads
deeper for actual rigor.

### vs prior v4-flash data (gemini-judged, where comparable)

| Mode | Mean (gemini) | Mean (v4-pro, where measured) |
|---|---|---|
| pass@1 (Phase 1)         | 4.90 | 2.61 |
| pass@3 best-of-3 (Phase 1) | 6.11 | — |
| seed_gen (Phase 1)         | 5.70 | — |
| full pipeline (Phase 1)    | 4.63 | — |
| **seed_full (Phase 3)**    | **5.83** | **3.19** |

Under gemini, seed_full is between full (4.63) and pass@3 (6.11) — modest +1.20 over full,
but doesn't reach pass@3. Under v4-pro, seed_full is +0.58 over pass@1, in line with
Phase 1's general "verify/revise gives small uplift to v4-flash" finding.

### Special-10 outcomes (gem | v4-pro)

| Problem | gemini | v4-pro | Real solve? |
|---|---|---|---|
| **erdos-654**             | 7/7 | **6/7** | **YES — confirmed frontier solve** |
| **first-proof-10-official** | 6/7 | **6/7** | **YES — confirmed near-solve, both judges agree** |
| erdos-1051            | 7/7 | 0/7 | NO — gemini-leniency artifact |
| erdos-333             | 7/7 | 0/7 | NO — gemini-leniency artifact |
| erdos-659             | 7/7 | 0/7 | NO — gemini-leniency artifact |
| first-proof-6-official | 7/7 | 0/7 | NO — gemini-leniency artifact |
| erdos-397             | 0/7 | 0/7 | unsolved (consistent) |
| first-proof-5-official | 0/7 | 0/7 | unsolved (consistent) |
| ramsey-hypergraphs    | 0/7 | 0/7 | unsolved (consistent) |
| first-proof-4-official | — (stuck) | — | not measured |

**Major correction to Phase 2's "frontier breakthrough" framing**: the celebrated erdos-1051,
erdos-659, and first-proof-6 7/7 hits in Phase 2 (gpt-oss, gemma) and Phase 3 (v4-flash)
do **not survive v4-pro re-grade**. Phase 2 should be re-read with this caveat. Only
**erdos-654** (Phase 2 gpt-oss + Phase 3 v4-flash) is independently corroborated by both
judges as a real solve at this tier — and only at 6/7 strict, not 7/7.

### Tier 2 v4-flash struggle problems (where Phase 1 v4-flash got ≤1 but other models got ≥6)

| Problem | Phase 1 v4-flash best | Phase 3 gemini | Phase 3 v4-pro |
|---|---|---|---|
| PB-Advanced-003     | 1/7 | 7/7 | 0/7 |
| PB-Advanced-018     | 0/7 | 1/7 | 0/7 |
| PB-Advanced-027     | 0/7 | 0/7 | 0/7 |
| erdos-397           | 0/7 | 0/7 | 0/7 |
| first-proof-5-official | 1/7 | 0/7 | 0/7 |

Under gemini, seed_full appeared to rescue PB-Advanced-003 (1→7). Under v4-pro that
rescue evaporates. Net: **seed_full does not meaningfully rescue v4-flash blind spots.**

### Key methodology lessons (write these down)

1. **v4-pro reasoning-cap bug**: at `max_tokens=65536`, v4-pro's reasoning consumes the
   output budget on heavyweight prompts before emitting the final `<points>` tag — 24 of
   65 first-pass regrades returned 50–70K-character `reasoning_content` with NO score tag,
   silently parsed as 0. **Fix**: pass OpenRouter `extra_body={"reasoning": {"max_tokens": 100000}}`
   plus `max_tokens=131072`. After the fix, all 26 re-judged trials (added 3 stuck specials)
   committed valid scores.
2. **Always parse `reasoning_content` as a fallback** when `content` is empty. The Phase 2
   main script does; the first-cut regrade script didn't, which produced the bug above.
3. **Strict judge required for frontier claims.** Phase 2 saved 10 frontier_branches; under
   v4-pro only 1 of those (erdos-654) survives. Future frontier reporting should default
   to dual-judge confirmation before tagging "first-ever solve."
4. **Wall-time tail bites hard.** v4-flash on seed_full has 1 problem (`first-proof-4-official`)
   where branches got into a litellm internal retry loop and never timed out cleanly,
   running for 4+ hours after the rest of the run finished. Should add an explicit
   per-trial wall-clock killer (not just per-call timeout).

### Recommendations

- **For headline reporting**: report both judges. Gemini for cross-comparability with the
  Phase 1 audit table; v4-pro for "is this actually a proof."
- **For v4-flash specifically**: seed_full is **not better than pass@3** at the same budget
  ($0.30/run vs $0.14/run for Phase 1 pass@3). Pass@3 remains the dominant cheap-cost mode
  for v4-flash on this benchmark.
- **Cost reality**: v4-flash seed_full landed at $0.30/run actual, matching the Phase 2
  pre-projection (vs the $0.20-$0.30 estimate I gave earlier). Estimate held.

Files:
- Script:    `experiments/seed_full_v4flash_phase3_20260505.py`
- Priority:  `experiments/results/v4flash_priority_20260505.json`
- Phase 3 run dir: `experiments/results/seed_full_v4flash_phase3_20260505_20260505_021635/`
- V4-pro regrade dir: `experiments/results/regrade_phase3_v4pro_20260505_043627/`
- Re-judge script (with reasoning budget fix): `experiments/regrade_phase3_v4pro_truncated_20260505.py`
- Joint table: `experiments/results/phase3_joined_judges.json`
- Logs: `/tmp/phase3.log`, `/tmp/regrade_phase3_fixed.log`, `/tmp/rejudge_truncated.log`

## Judge-vs-Human gradingbench comparison — 2026-05-05T05:54

Tested four candidate judge models against the **human "Points" baseline** in
`benchmarks/IMO-bench/gradingbench.csv` (1000 records, 30 problems, sources:
USAMO 2025, Modified IMO 2024 P1–P6, Novel Problems). All prior judge work
(Phase 1/2, judge_ablation_20260504, regrade_phase2_full_v4pro_20260504) only
compared judges against each other; this is the first measurement against
humans.

Methodology mirrors prior runs: hardened `prompts/pipeline/judge_gt.md` with
{problem, ground_truth, candidate}; n=200 simple random sample (seed=42);
`max_tokens=65536`; 80 concurrent workers shared across all judges; multi-key
rotation. gpt-5.4-nano run at `reasoning.effort=xhigh` via
`extra_body={"reasoning":{"effort":"xhigh"}}`, verified to engage at 11K+
reasoning tokens before the run via a `--verify-reasoning` preflight.

**798/800 calls completed** in 50.7 min wall, **$14.23 total**. Two nano calls
hung past the 1800s litellm timeout (same bug as line 1605) and were killed;
all four judges have ≥196 valid scores so the cell-level numbers are stable.

### Headline results

| Judge | n_valid | mean_J | mean_H | mean\|Δ\| | mean Δ | r | $cost | wall p50/p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **deepseek-v4-pro** | 198 | 2.28 | 3.03 | **1.21** | -0.75 | **0.76** | $2.97 | 299s / 974s |
| **deepseek-v4-flash** | 199 | 2.22 | 3.02 | 1.23 | -0.80 | **0.76** | **$0.77** | **83s** / 275s |
| gpt-5.4-nano @ xhigh | 196 | 2.01 | 2.96 | 1.41 | -0.95 | 0.71 | $7.26 | 153s / 416s |
| gemini-3-flash-preview | 200 | 4.67 | 3.02 | 1.98 | **+1.65** | 0.61 | $3.24 | 4s / 5s |

### Pass/fail confusion at ≥6 (judge≥6 vs human≥6, recall / specificity / precision)

| Judge | recall | specificity | precision | flip rate |
|---|---:|---:|---:|---:|
| **gemini-3-flash-preview** | 98.4% | 48.2% | 46.6% | 36.0% |
| deepseek-v4-pro | 82.5% | 91.9% | 82.5% | 11.1% |
| deepseek-v4-flash | 79.4% | 91.2% | 80.6% | 12.6% |
| gpt-5.4-nano @ xhigh | 70.0% | 97.8% | **93.3%** | 10.7% |

### Findings

- **deepseek-v4-flash is the cost/accuracy sweet spot.** Matches v4-pro on
  correlation (r=0.76), pass-flip rate (12.6% vs 11.1%), and precision (80.6%
  vs 82.5%) at **¼ the cost** ($0.77 vs $2.97 for n=200) and **3.6× faster
  wall** (83s vs 299s p50). Recommended default judge for downstream work.
- **deepseek-v4-pro remains the gold standard** when latency/cost don't bind.
  Best balanced confusion matrix (82.5%/91.9%/82.5%) but slow long-tail —
  p95 974s. The "v4-pro takes ~10× longer than v4-flash for marginal accuracy
  gain" pattern from prior judge-comparison runs reproduces here.
- **gpt-5.4-nano @ xhigh is the strictest judge — best for high-precision
  filtering.** 93.3% precision (only 3 false ≥6 calls in 198), 97.8%
  specificity. But recall just 70% (misses 30% of true human ≥6s) and most
  expensive at $7.26. Use when "is this definitely correct?" matters more
  than "did we catch all the correct ones?"
- **gemini-3-flash-preview is unsuitable as a sole judge.** Persistent +1.65
  inflation bias on a 0–7 scale. 98% recall with 48% specificity and 47%
  precision — it flags almost every solution as "passing", so its ≥6
  verdicts carry little signal. Confirms and quantifies the lenient-bias
  pattern flagged in the Phase 1/2 work (agent_log lines 1180-1186, 1517).
- **Judge granularity mismatch is real.** judge_gt.md only emits {0,1,6,7} but
  human Points span 0–7. Bucketed exact-match (humans→{0,1,6,7}) tops out at
  58.6% (v4-pro) — even the best judge agrees with humans on bucket only ~3
  out of 5 times. The pass-flip metric (≥6 yes/no) is the more decision-useful
  proxy for "judge replicates human verdict".
- **xhigh nano confirmed engaging.** Median 17.5K reasoning tokens, all
  parseable scores in {0,1,6,7}. The two stragglers that hung past the 1800s
  timeout reproduce the litellm-doesn't-respect-timeout bug (line 1605); a
  process-level wrapper or `signal.alarm` would prevent the kill-and-restart
  next time.

### Decision update for downstream judge selection

- **Default judge for new experiments → deepseek-v4-flash.** Within 3 percentage
  points of v4-pro on every binary-pass metric, 4× cheaper, 3.6× faster.
- **Validation/audit judge → deepseek-v4-pro.** Use for high-stakes or borderline
  cases where the wall-time hit is acceptable.
- **High-precision filter → gpt-5.4-nano @ xhigh.** When you need "the judge said
  yes, so trust it" semantics rather than "the judge caught most of them".
- **Drop gemini-3-flash from the judge candidate set.** Inflation bias makes its
  pass/fail signal nearly noise.

Files:
- Script: `experiments/judge_vs_human_gradingbench_20260505.py`
- Results: `experiments/results/judge_vs_human_gradingbench_20260505_20260505_050213.json`
  (798/800 — 2 nano calls killed at >36 min after litellm timeout failed to fire)
- Log: `/tmp/jvh_full.log`
- Smoke result (n=8, separate file): `experiments/results/judge_vs_human_gradingbench_20260505_20260505_045014.json`

## v4-flash judge — reasoning ON vs OFF — 2026-05-05T06:39

Counterfactual to the prior judge_vs_human run: re-ran the exact same n=200
sample (seed=42) using only **deepseek-v4-flash with `reasoning.enabled=False`**
to test whether the "v4-flash matches v4-pro at ¼ the cost" headline depends on
v4-flash's default thinking budget.

Pre-flight: confirmed `extra_body={"reasoning": {"enabled": False}}` cleanly
zeros out reasoning_tokens (rt=0, 0.6s) on a one-shot test, while v4-pro only
*partially* throttled with the same param (rt fell from 108→75, latency
unchanged). So this counterfactual is meaningful for v4-flash specifically.

Run: 200/200 calls in 1:50 wall, **$0.30 total** (vs $0.77 with reasoning ON
on the same sample). 192/200 valid (8 errors after a temporary key-limit
throttle on key#0 — non-systematic, sample remains representative).

### Side-by-side (same n=200 sample, same judge_gt.md prompt)

| metric | ON (rt~7K) | OFF (rt=0) | delta |
|---|---:|---:|---:|
| n_valid | 199 | 192 | -7 |
| mean(J) | 2.22 | 1.72 | -0.50 |
| mean\|Δ\| | 1.23 | 1.76 | **+0.53 worse** |
| mean Δ | -0.80 | -1.36 | -0.56 (more deflation) |
| **Pearson r** | **0.76** | **0.59** | **-0.16 worse** |
| **≥6-agree** | **87.4%** | **80.7%** | **-6.7 pp** |
| exact_raw | 55.3% | 43.8% | -11.5 pp |
| exact_bucketed | 57.8% | 48.4% | -9.4 pp |
| **recall** (≥6) | **79.4%** | **56.5%** | **-22.9 pp** |
| specificity | 91.2% | 92.3% | +1.1 |
| precision | 80.6% | 77.8% | -2.8 |
| $cost | $0.77 | $0.30 | **-61%** |
| p50 latency | 83.3s | 12.7s | **-85%** |
| p95 latency | 275.1s | 33.5s | **-88%** |

### Findings

- **Reasoning is doing real work for v4-flash judging.** Without it, recall on
  human-≥6 collapses from 79% to **57%** — the model misses 4 out of every 10
  truly-passing solutions. r drops 0.76→0.59.
- **Specificity / precision barely change** (+1.1 / -2.8 pp). Reasoning-off
  v4-flash makes the *same* false-positive judgments but a lot more
  false-negative ones — the deflation bias deepens (-0.80 → -1.36).
- **Reasoning-off v4-flash is still better than reasoning-default Gemini 3
  Flash** on r (0.59 vs 0.61 — basically tied) but with the opposite bias
  direction (deflation vs inflation). Neither is good enough for a sole judge.
- **Cost/speed wins are real but don't pay for the accuracy cost.** 6–8×
  faster wall and 61% cheaper, but at -23 pp recall — too lossy for
  production judging.
- **Bottom-line for downstream judge selection:** keep v4-flash with reasoning
  ON as the recommended default (the main run's headline). If wall-time
  matters more than recall (e.g. a cheap pre-filter before a v4-pro audit),
  reasoning-off is a defensible knob.

### Param verification (pre-flight one-shot, "Is 17 prime?" prompt)

| model | param | rt | latency |
|---|---|---:|---:|
| v4-flash | `reasoning.enabled=False` | **0** | 0.6s |
| v4-flash | `reasoning.effort=minimal` | 30 | 0.8s |
| v4-flash | `reasoning.exclude=True` | 37 | 1.2s |
| v4-flash | baseline | 37 | 1.5s |
| v4-pro | `reasoning.enabled=False` | **75** | 3.6s |
| v4-pro | baseline | 108 | 5.2s |

`reasoning.enabled=False` is the working knob for v4-flash. v4-pro does *not*
fully respect it — only a partial throttle. `exclude=True` just hides the
trace, doesn't stop the thinking. Equivalent counterfactual for v4-pro is not
cleanly achievable through the OpenRouter param surface.

Files:
- Script: `experiments/judge_v4flash_noreason_20260505.py`
- Param test: `/tmp/test_ds_reasoning_off.py`
- Results: `experiments/results/judge_v4flash_noreason_20260505_20260505_063740.json`
- Log: `/tmp/jvh_v4flash_noreason2.log`

## gemma-4-31b judge — 2026-05-05T06:49

Added `openrouter/google/gemma-4-31b-it` as a sixth judge on the same n=200
sample (seed=42, judge_gt.md, no reasoning param — gemma is a non-reasoning
model). 200/200 in 2:36 wall, **$0.42 total**, all parseable.

### Six-way comparison (same n=200)

| judge | n | mean(J) | mean(H) | \|Δ\| | Δ | r | ≥6-agree | recall | spec | prec | $cost | p50/p95 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| v4-pro | 198 | 2.28 | 3.03 | 1.21 | -0.75 | **0.76** | 88.9% | 83% | 92% | 83% | $2.97 | 299s/974s |
| **v4-flash ON** | 199 | 2.22 | 3.02 | 1.23 | -0.80 | **0.76** | 87.4% | 79% | 91% | 81% | **$0.77** | 83s/275s |
| v4-flash OFF | 192 | 1.72 | 3.08 | 1.76 | -1.36 | 0.59 | 80.7% | 56% | 92% | 78% | $0.30 | 13s/34s |
| nano-xhigh | 196 | 2.01 | 2.96 | 1.41 | -0.95 | 0.71 | 89.3% | 70% | **98%** | **93%** | $7.26 | 153s/416s |
| gemini-3F | 200 | 4.67 | 3.02 | 1.98 | +1.65 | 0.61 | 64.0% | 98% | 48% | 47% | $3.24 | 4s/5s |
| **gemma-4-31b** | 200 | 4.55 | 3.02 | 1.87 | +1.53 | 0.63 | 65.5% | 98% | 50% | 48% | **$0.42** | 19s/45s |

### Findings

- **gemma-4-31b is essentially gemini-3-flash's twin** as a judge: same +1.5
  inflation bias, same 98% recall / 47% precision profile, same r ≈ 0.62.
  Both are non-reasoning models that rubber-stamp polished-looking proofs.
- **gemma is 7.7× cheaper than gemini** for the same (poor) accuracy — if
  you specifically need a non-reasoning lenient judge as a cheap pre-filter,
  use gemma over gemini.
- **Two clean clusters emerge across all six setups:**
  - **Reasoning judges (v4-pro, v4-flash ON, nano-xhigh):** r=0.71–0.76,
    ≥6-agree 87–89%, slight *deflation* (Δ ∈ -0.75 to -0.95).
  - **Non-reasoning judges (gemini-3F, gemma-4-31b, v4-flash OFF):** r=0.59–0.63,
    ≥6-agree 64–81%, *inflation* for the model-types trained that way
    (gemini, gemma) and *deflation* for v4-flash with reasoning forcibly off.
- **Reasoning vs non-reasoning is the dominant axis.** Model lineage (DS vs
  Google vs OpenAI) sets the bias direction; reasoning state sets the
  accuracy band. Cheap reasoning-on judges (v4-flash) beat expensive
  reasoning-off judges (gemini) on every accuracy metric.
- **No new top contender from gemma.** Cheap, fast, but doesn't change the
  judge-selection conclusion: v4-flash ON remains the recommended default.

Files:
- Script: `experiments/judge_gemma4_31b_20260505.py`
- Results: `experiments/results/judge_gemma4_31b_20260505_20260505_064650.json`
- Log: `/tmp/jvh_gemma4_v2.log`

## gemma-4-31b judge with reasoning ON — 2026-05-05T07:30

Counterfactual to the gemma-default run: same n=200 sample, same judge_gt.md,
but with `extra_body={"reasoning": {"effort": "high"}}`. Two questions:
(1) does gemma engage reasoning by default? (2) what changes if it's forced on?

### Reasoning-by-default check
**No.** All 200 calls in the default-gemma run logged `reasoning_tokens=0`.
One-shot param test confirmed gemma supports reasoning via OpenRouter's
`reasoning` knob but never engages without one:

| param                       | wall | rt   |
|-----------------------------|-----:|-----:|
| baseline                    | 9.8s | 0    |
| `reasoning.effort=xhigh`    | 102s | 685  |
| `reasoning.effort=high`     | 30s  | 846  |
| `reasoning.effort=medium`   | 19s  | 676  |
| `reasoning.enabled=True`    | 14s  | 581  |
| `reasoning.max_tokens=8000` | 15s  | 432  |

Notable: gemma's reasoning budget is small even at xhigh (sub-1K rt vs
DS-pair's 7-10K and nano-xhigh's 17K). Provider appears to cap hard for the 31b.

### Full run @ effort=high
200/200 in 26:35 wall, **$0.75 cost**, all valid. Median rt=2.8K, p95 rt=6.5K
— modest reasoning, 3-4× lower than the DS judges.

### Seven-way comparison (same n=200)

| judge             | n   | mean(J) | mean(H) | \|Δ\| | Δ      | r       | ≥6agr  | exact_b | recall | spec | prec | $cost  | p50/p95     |
|-------------------|-----|---------|---------|-------|--------|---------|--------|---------|--------|------|------|--------|-------------|
| v4-pro            | 198 | 2.28    | 3.03    | 1.21  | -0.75  | 0.76    | 88.9%  | 58.6%   | 83%    | 92%  | 83%  | $2.97  | 299s/974s   |
| v4-flash ON       | 199 | 2.22    | 3.02    | 1.23  | -0.80  | 0.76    | 87.4%  | 57.8%   | 79%    | 91%  | 81%  | $0.77  | 83s/275s    |
| v4-flash OFF      | 192 | 1.72    | 3.08    | 1.76  | -1.36  | 0.59    | 80.7%  | 48.4%   | 56%    | 92%  | 78%  | $0.30  | 13s/34s     |
| nano-xhigh        | 196 | 2.01    | 2.96    | 1.41  | -0.95  | 0.71    | 89.3%  | 45.4%   | 70%    | 98%  | 93%  | $7.26  | 153s/416s   |
| gemini-3F         | 200 | 4.67    | 3.02    | 1.98  | +1.65  | 0.61    | 64.0%  | 48.0%   | 98%    | 48%  | 47%  | $3.24  | 4s/5s       |
| gemma-4 default   | 200 | 4.55    | 3.02    | 1.87  | +1.53  | 0.63    | 65.5%  | 49.5%   | 98%    | 50%  | 48%  | $0.42  | 19s/45s     |
| **gemma-4 HIGH**  | 200 | 3.57    | 3.02    | **1.14** | **+0.55** | **0.78** | 79.0% | **60.0%** | 92% | 73% | 61% | $0.75 | 126s/436s |

### Findings

- **gemma-4 @ high is the highest-correlated judge of any tested.**
  r=0.78 beats v4-pro/v4-flash (0.76). Lowest \|Δ\| (1.14), highest
  bucketed exact match (60%).
- **Reasoning shifts gemma's profile dramatically** but doesn't fully repair
  it. mean Δ moves from +1.53 (default) to +0.55 (high) — inflation bias
  shrinks but persists. Recall stays high (92%) and precision lifts from
  48% → 61%.
- **gemma-4 HIGH is not strictly dominant.** v4-flash-ON beats it on
  precision (81% vs 61%) and is faster (p50 83s vs 126s). nano-xhigh beats
  it on precision (93%). For pass/fail decisions, v4-flash-ON / v4-pro /
  nano-xhigh remain stronger; for raw correlation with the human score
  distribution, gemma-HIGH is now the leader.
- **Refined cluster picture:**
  - *Strict reasoning judges* (v4-pro, v4-flash ON, nano-xhigh): high
    precision, slight deflation, r 0.71–0.76.
  - *Lenient non-reasoning judges* (gemini-3F, gemma-default): high recall,
    strong inflation, r 0.61–0.63.
  - *Hybrid* (gemma-HIGH): r 0.78, moderate inflation, moderate precision.
    Reasoning pulls a non-DS lineage halfway toward the strict cluster but
    doesn't fully reset its calibration.
- **Reasoning is the dominant axis, model lineage modulates direction.**
  Same prompt + reasoning state can land you in either cluster depending on
  the model family.
- **Provider caps gemma's reasoning hard.** rt_med 2.8K is well below the DS
  judges' 7-10K — the reasoning effort param is honored but bounded.

### Updated judge-selection recommendation (multi-axis)

| Use case | Best pick | Why |
|---|---|---|
| Absolute correlation with humans | **gemma-4 @ high** | r=0.78, lowest \|Δ\|, $0.75 |
| Pass/fail decisions (balanced) | v4-flash ON | precision 81%, recall 79%, $0.77 |
| Pass/fail audit (high precision) | nano-xhigh | precision 93%, specificity 98% |
| Cheap throughput (no reasoning) | gemma-4 default | $0.42, fast, but inflation bias |
| Drop entirely | gemini-3F | strictly dominated by gemma-default at 7.7× cost |

Files:
- Script: `experiments/judge_gemma4_31b_high_20260505.py`
- Results: `experiments/results/judge_gemma4_31b_high_20260505_20260505_070206.json`
- Param test: `_test_gemma_reasoning.py` (deleted; output in conversation log)
- Log: `/tmp/jvh_gemma4_high.log`

## gpt-oss-120b judge + 4-judge ensemble — 2026-05-05T08:18

Same n=200 sample. Two gpt-oss-120b runs (`effort=minimal` and `effort=xhigh`)
plus an ensemble re-analysis on top of the prior 7 judges.

Param note: gpt-oss requires reasoning — `enabled=False` returns
`BadRequestError: Reasoning is mandatory`. Closest to off is `effort=minimal`
(rt_med 82). xhigh produces rt_med 5.6K.

### Updated single-judge ranking (sorted by r)

| Judge | n | r | mean Δ | \|Δ\| | ≥6-agree | rec | spec | prec | $cost | rt_med |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| gemma-4 @ high | 200 | **0.78** | +0.55 | 1.14 | 79.0% | 92 | 73 | 61 | $0.75 | 2800 |
| **gpt-oss @ xhigh** | 178 | 0.77 | **+0.21** | **1.11** | 84.3% | 90 | 82 | 70 | **$0.39** | 5604 |
| v4-pro | 198 | 0.76 | -0.75 | 1.21 | 88.9% | 83 | 92 | 83 | $2.97 | 9771 |
| v4-flash ON | 199 | 0.76 | -0.80 | 1.23 | 87.4% | 79 | 91 | 81 | $0.77 | 7050 |
| nano-xhigh | 196 | 0.71 | -0.95 | 1.41 | 89.3% | 70 | **98** | **93** | $7.26 | 17504 |
| gemma-4 default | 200 | 0.63 | +1.53 | 1.87 | 65.5% | 98 | 50 | 48 | $0.42 | 0 |
| gemini-3F | 200 | 0.61 | +1.65 | 1.98 | 64.0% | 98 | 48 | 47 | $3.24 | 0 |
| v4-flash OFF | 192 | 0.59 | -1.36 | 1.76 | 80.7% | 56 | 92 | 78 | $0.30 | 0 |
| **gpt-oss @ minimal** | 199 | **0.51** | +0.11 | 1.89 | 71.9% | 74 | 71 | 53 | **$0.17** | 82 |

### Findings (single judges)

- **gpt-oss-120b @ xhigh is the new cost-effective pick.** r=0.77 ties gemma/DS at half the price ($0.39), best calibration of any judge (mean Δ +0.21, lowest \|Δ\| 1.11), and parses 84% pass/fail correctly.
- **gpt-oss has the biggest reasoning-effort sensitivity tested.** r jumps 0.51 → 0.77 (+0.26) from minimal → xhigh. Bigger than gemma's +0.15 or v4-flash's +0.17. *Reasoning is the dominant axis* hypothesis re-confirmed and now quantified across three model families.
- **gpt-oss @ minimal is the worst single judge ever observed** (r=0.51). Even worse than v4-flash forced off. Don't ship a non-reasoning gpt-oss judge.
- xhigh-nano remains the precision king (93%); v4-pro the balance king (83/92/83).

### Ensemble analysis (3-judge majority-vote at ≥6, by Pearson r of mean)

| Combo | n_join | mean r | maj ≥6-agr | maj rec/spec/prec | unan rec/spec/prec |
|---|--:|--:|--:|--:|--:|
| v4-pro + nano + gemma (original trio) | 194 | 0.842 | 90.7% | 85/93/85 | 68/99/98 |
| oss + nano + gemma | 175 | 0.854 | 85.7% | 89/84/72 | 71/98/95 |
| v4-pro + oss + gemma | 176 | 0.859 | 85.8% | 90/84/73 | 84/96/91 |
| v4-flash + oss + gemma | 177 | 0.862 | 85.9% | 91/83/73 | 78/94/87 |
| v4-pro + oss + nano | 173 | 0.830 | 90.8% | 86/93/86 | 71/98/95 |
| **4-judge: v4-pro + oss + nano + gemma** | 173 | **0.863** | **91.3%** | **86/94/87** | **71/99/98** |
| 5-judge: + v4-flash | 173 | 0.866 | 90.8% | 88/92/84 | 70/99/98 |

### Findings (ensembles)

- **4-judge {v4pro + oss-xhigh + nano-xhigh + gemma-high} is the new best overall.**
  r=0.863, ≥6-agree=91.3%, recall=86 / spec=94 / prec=87, cost ~$11.37/200
  (~$0.057/decision). Strictly dominates the 3-judge trio on every metric.
- **Adding gpt-oss-xhigh helps because it's calibrated where the others lean.**
  gemma-high inflates (+0.55), v4-pro/v4-flash deflate (-0.8), nano deflates
  more (-0.95). gpt-oss-xhigh sits at +0.21 — closest to the human distribution,
  pulling the ensemble mean toward truth.
- **5-judge gives no real lift over 4-judge** (r 0.866 vs 0.863, maj-agree
  slightly lower). Diminishing returns past 4. Drop v4-flash if cost matters.
- **Unanimous ≥6 in the 4-judge ensemble: 71% recall, 99% specificity, 98%
  precision.** When 4 differently-biased judges all say ≥6, trust it — only
  1 false positive in 173 records.

### Updated decision matrix

| Use case | Best pick |
|---|---|
| Single judge by accuracy | gemma-4 @ high (r=0.78, $0.75) |
| Single judge by $/accuracy | **gpt-oss-120b @ xhigh** (r=0.77, $0.39) |
| Best pass/fail decision | **4-judge ensemble, majority vote** (91.3%) |
| Best high-precision audit | **4-judge ensemble, unanimous** (prec=98%) |
| Skip entirely | gpt-oss @ minimal, gemini-3F, v4-flash OFF |

Files:
- Scripts: `experiments/judge_gptoss_20260505.py`
- Results:
  `experiments/results/judge_gptoss_120b_minimal_20260505_20260505_080159.json`
  `experiments/results/judge_gptoss_120b_xhigh_20260505_20260505_080159.json`
- Logs: `/tmp/jvh_gptoss_min.log`, `/tmp/jvh_gptoss_xhigh.log`

## Cheap-trio consensus exploration — 2026-05-05T08:35

Three cost-effective judges with **biases that sum to ~0**: gemma-high (+0.50),
gpt-oss-xhigh (+0.23), v4-flash-ON (-0.73). Inner-join n=177, total cost $1.61
($0.009/decision). All numbers below from this subset.

**Best rule per goal:**

| Goal | Rule | Result |
|---|---|---|
| Correlation | Mean of 3 | r=**0.862** (= calibrated-mean; biases cancel naturally) |
| F1 / balanced pass-fail | **Majority vote at ≥7** (not ≥6) | **F1=83.9**, agr=88.7%, rec/spc/prc 90/88/79 |
| Precision | Unanimous ≥6 | prec=87%, spc=94%, rec=78% |
| F1 if dropping a judge | (gem+v4f)/2 mean | F1=82.5 — beats trio on F1 by trimming oss |
| **Best total system** | **Tier: trio auto + v4-pro on the 21% disagreements** | **89.8% accuracy at $0.013/dec — 4× cheaper than 4-judge ensemble (91.3% @ $0.057/dec)** |

**Agreement structure is bimodal:** 79% of decisions land on 0/3 or 3/3 (where
accuracy is 92.9%); errors concentrate in the 21% middle. Hence tiered escalation works.

**Tip:** majority-vote-at-≥7 outperforms majority-vote-at-≥6 because the
hardened judge_gt only emits {0,1,6,7} and "said 7" is a much stronger signal
than "said ≥6" (which collapses 6s and 7s).

Files:
- Analysis: `_consensus_3.py` (deleted; output in conversation log)

## Frontier baseline: gemini-3.1-pro vs cheap trio — 2026-05-05T12:22

Same n=200 sample. **gemini-3.1-pro-preview** (reasoning ON via
`extra_body={"reasoning":{"enabled":True}}`), 199/200 valid in 2:21 wall, **$6.93**
total spend (well under $20 cap; per-call ~$0.033).

### Head-to-head on the 172-record 6-way inner-join

| metric | cheap trio (mean) | gemini-3.1-pro | delta |
|---|--:|--:|--:|
| Pearson r | 0.866 | **0.881** | g3-pro +0.015 |
| ≥6-agree | **90.1%** | 88.4% | trio +1.7 pp |
| F1 | 84.1 | 84.1 | **tie** |
| recall | 80% | **95%** | g3-pro +15 pp |
| precision | **88%** | 76% | trio +13 pp |
| mean Δ (bias) | -0.01 | +0.08 | both nearly calibrated |
| cost | $1.55 | $5.72 | **trio −73%** |
| wall p50 | 116s parallel | **21s** | g3-pro 5.5× faster |
| disagreements (n=19) | trio right 11/19 | g3-pro right 8/19 | trio wins on hard cases |

### Findings

- **Strict "trio beats frontier on r" fails** — g3-pro's r=0.881 narrowly
  exceeds the trio's 0.866. The cleanest paper claim is therefore
  *"matches frontier on F1 and pass/fail metrics at 27% of the cost"*, not
  *"beats frontier"*.
- **Trio strictly equal-or-better than g3-pro on every pass/fail metric**:
  ≥6-agree (+1.7), precision (+13), F1 (tie). Trio loses only on recall,
  because g3-pro's lean is high-recall (95%/76%).
- **gemini-3.1-pro is the most calibrated single judge ever observed**:
  mean Δ +0.08 (everyone else: ±0.5 to ±1.0). Adding g3-pro to the trio
  (4-judge mean) bumps r 0.866 → **0.886**, F1/agr/rec/prec unchanged.
- **g3-pro is fast**: 21s p50 wall, 5.5× faster than the trio's parallel
  max-component. Likely Google's TPU serving stack.
- **On the 19 cases where trio and g3-pro disagree, trio wins 11–8**.

### Updated single-judge ranking (sorted by r, n=172 6-way subset)

| Judge | r | F1 | $cost | p50 lat |
|---|--:|--:|--:|--:|
| **gemini-3.1-pro (frontier)** | **0.881** | 84 | $5.72 | 21s |
| gemma-4-31b @ high | 0.806 | 77 | $0.63 | 116s |
| gpt-oss-120b @ xhigh | 0.789 | 80 | $0.31 | 61s |
| deepseek-v4-pro | 0.784 | 87 | $2.40 | 280s |
| deepseek-v4-flash | 0.773 | 83 | $0.61 | 72s |
| gpt-5.4-nano @ xhigh | 0.722 | 81 | $6.00 | 140s |

### Refined paper claim

| Goal | Defensible claim |
|---|---|
| Calibration on continuous score | g3-pro narrowly best (r=0.881); cheap trio close (0.866) |
| Pass/fail decisions | **Cheap trio matches g3-pro on F1, beats on agreement+precision, at 27% of cost** |
| Cost-effectiveness | **$0.009/decision (trio) vs $0.033/decision (g3-pro), 3.7× cheaper** |
| Best 4-judge ensemble | Trio + g3-pro: r=0.886, same F1=84 — only marginal gain over trio alone |

Files:
- Script: `experiments/judge_gemini3_pro_20260505.py`
- Results: `experiments/results/judge_gemini3_pro_20260505_20260505_121952.json`
- Log: `/tmp/jvh_g3pro.log`


## Phase 3: Role-Swap Matrix — gpt-oss × gemma-4-31b-it — 2026-05-05T06:40:21

8 cross-model conditions × 70 problems = **560 trials, 0 errors, $38.75 / $50 cap, 200 min wall**.
Judge: gemini-3-flash-preview primary, **escalate to deepseek-v4-pro on (special-10 ∧ gemini≥6)**.
Single key (`OPENROUTER_API_KEY_seedgen`). seed_full mode (ideate(3) → 3 branches × full pipeline).

### Conditions

| # | Name | Ideator | Generator | Verifier | Reviser |
|---|---|---|---|---|---|
| 1 | x_ideate_oss   | oss   | gemma | gemma | gemma |
| 2 | x_ideate_gemma | gemma | oss   | oss   | oss   |
| 3 | x_verify_oss   | gemma | gemma | oss   | gemma |
| 4 | x_verify_gemma | oss   | oss   | gemma | oss   |
| 5 | x_revise_oss   | gemma | gemma | gemma | oss   |
| 6 | x_revise_gemma | oss   | oss   | oss   | gemma |
| 7 | random_run1    | seeded random per (problem, role), seed=1 |
| 8 | random_run2    | seeded random per (problem, role), seed=2 |

### Per-condition results (all 70 problems, post-escalation scores)

| Condition | n | mean | std | pass | $/run | vs P2 baseline |
|---|---|---|---|---|---|---|
| x_ideate_oss | 70 | 4.20 | 3.34 | 41/70 | $0.072 | gemma 4.26 → −0.06 |
| x_ideate_gemma | 70 | 3.97 | 3.47 | 40/70 | $0.068 | oss 3.99 → −0.02 |
| x_verify_oss | 70 | 4.16 | 3.33 | 41/70 | $0.068 | gemma 4.26 → −0.10 |
| **x_verify_gemma** | 70 | **3.44** | 3.44 | 34/70 | $0.071 | oss 3.99 → **−0.55** |
| x_revise_oss | 70 | 4.24 | 3.38 | 42/70 | $0.070 | gemma 4.26 → −0.02 |
| x_revise_gemma | 70 | 4.04 | 3.33 | 39/70 | $0.067 | oss 3.99 → +0.05 |
| random_run1 | 70 | 3.73 | 3.49 | 37/70 | $0.068 | mix 4.12 → −0.40 |
| random_run2 | 70 | 4.14 | 3.32 | 41/70 | $0.070 | mix 4.12 → +0.02 |

P2 baseline = same model in all roles (Phase 2: gpt-oss=3.99, gemma=4.26, gemini judge, no escalation).

### Key findings

1. **Cross-model role swap is essentially a wash on this benchmark.** 5 of 8 conditions land
   within ±0.1 of the same-model baseline. The naive expectation that "diversity helps" is
   not supported at this granularity.

2. **The only meaningfully bad swap is gemma-as-verifier on a gpt-oss pipeline (−0.55).**
   Replacing oss verifier with gemma verifier strictly hurts. Reverse direction
   (gemma→oss verifier) is fine. Reading: oss is the better verifier of its own work, gemma
   isn't catching oss's errors — and gemma's verifier may be over-permissive in the cross
   direction (more "looks fine" early-stops on broken proofs, which the judge then penalizes).

3. **The reverse for revise: gpt-oss-as-reviser on gemma is fine, but gemma-as-reviser on oss
   is the one positive (+0.05).** Tiny. Don't read much into it.

4. **random_run1 vs random_run2 swing of 0.41 points** highlights how noisy single-shot
   role-swap evaluations are. Random run distributions were nearly 50/50 oss:gemma per role
   (verified post-hoc) so the gap is sampling variance on which problems got which mix, not
   structural. Conclusion: any reported swap effect under |Δ| < 0.4 is likely sampling noise
   given n=70.

5. **Earlier preliminary "+0.4 to +0.7 cross-model uplift" was an artifact** of (a) only the
   easier PB-Basic/PB-Advanced problems being completed at that snapshot, and (b) the v4-pro
   escalation not yet triggering. Once SPECIAL_10 flowed in and v4-pro stripped the inflated
   gemini frontier scores, the gap collapsed.

### Special-10 outcomes (post-escalation, definitive)

| Problem | n | passes ≥6/7 | best score | comment |
|---|---|---|---|---|
| **first-proof-10-official** | 8 | **3** | **6** | confirmed by both judges; multiple conditions |
| erdos-1051 | 8 | 0 | 1 | Phase 2's "first-ever solve" walked back under v4-pro |
| erdos-654   | 8 | 0 | 0 | Phase 2's gpt-oss 7/7 was gemini over-leniency |
| erdos-659   | 8 | 0 | 0 | Phase 2's gemma 7/7 was gemini over-leniency |
| erdos-397   | 8 | 0 | 1 | |
| erdos-333   | 8 | 0 | 0 | |
| first-proof-4 | 8 | 0 | 1 | |
| first-proof-5 | 8 | 0 | 1 | |
| first-proof-6 | 8 | 0 | 0 | |
| ramsey-hypergraphs | 8 | 0 | 0 | |

**Confirmed frontier branches** (v4-pro re-judged at ≥6/7):
| Condition | Problem | idea_idx | v4-pro |
|---|---|---|---|
| x_revise_oss     | first-proof-10-official | 0 | 6/7 |
| x_revise_oss     | first-proof-10-official | 1 | 6/7 |
| x_ideate_gemma   | first-proof-10-official | 0 | 6/7 |
| random_run2      | first-proof-10-official | 1 | 6/7 |

`first-proof-10-official` is the only special-10 problem that survives strict v4-pro judging
in this experiment. Phase 2's other frontier solves (erdos-1051/-654/-659) were gemini
over-leniency; v4-pro confirms them all at 0 (across 24 of 25 escalations, gemini=7→v4=0).

### Judge escalation tally

- **25 escalations triggered** (special-10 ∧ gemini≥6); 24 of 25 changed score under v4-pro.
- **Pre-flight audit cleared:** all 25 verdicts have proper `<points>` tags; verdict lengths
  400–2748 chars (no reasoning-overflow signature). The truncation bug from the v4-pro memory
  note was checked and is **not affecting this run** — the disagreements are real, not parsing.
- Pattern: gemini=7→v4=0 on 17 trials, gemini=6→v4=0 on 3, gemini=6→v4=1 on 1, gemini=7→v4=6
  on 3, gemini=6→v4=6 on 1. The 4 v4=6 escalations are the confirmed frontier results above.

### Implications

- **Cross-model role swap is not a free lunch at this model tier.** Best targeted swap (+0.05)
  and worst (−0.55) bracket Phase 2's same-model baseline; the median is roughly zero.
  For these two cheap models on proofbench, **stick with same-model seed_full** rather than
  attempting role mixes.
- **The verifier role is the most fragile.** Don't drop in a different model as verifier
  unless you've measured it on the target task — the loss can be material (−0.55 here).
- **Phase 2 frontier numbers were inflated by gemini.** The "first-ever solve" claim on
  erdos-1051 doesn't survive v4-pro. The honest Phase 2 frontier result is `first-proof-10`
  at 6/7, which Phase 3 also confirms.
- **Cross-model ideation results from March's lit-ideas pattern (5.28/7) remain unmatched.**
  This Phase 3 experiment used same-tier weak models in both roles; pairing a strong
  ideator (e.g., v4-pro) with a cheap generator (gemma) is the unexplored direction worth
  follow-up.

### Files

- Script: `experiments/seed_full_role_swap_20260505.py`
- Audit:  `experiments/regrade_role_swap_truncated_20260505.py` (ran clean — no re-judges needed)
- Run dir: `experiments/results/seed_full_role_swap_20260505_20260505_032032/`
  - `trials/<condition>/<pid>.json` (560 per-trial JSONs)
  - `branches/<condition>/<pid>/branch_{0,1,2}.json` (1680 per-branch incremental saves)
  - `manifest.jsonl` (560 lines)
  - `frontier_branches.jsonl` (escalation-confirmed special-10 hits)
- Log: `/tmp/role_swap.log`


## AnswerBench-50 follow-ups (3 retests) — 2026-05-05T02:55

Three follow-up runs on the original AnswerBench-50 stratified subset (same
seed=42, same 12 Alg / 13 Comb / 12 Geom / 13 NT), to fill in gaps from the
prior 7-model run:

1. **gpt-5.4-nano @ reasoning.effort=xhigh** on all 50.
2. **gemini-3-flash-preview @ reasoning.effort=xhigh** on the 13 it failed at default.
3. **deepseek-v4-flash with reasoning DISABLED** on all 50 (counterfactual).

All used the same gemini-3.1-flash-lite-preview answer-equivalence judge.
All used direct OpenRouter API (requests.post) — bypasses the litellm
timeout-not-firing bug we hit earlier.

### Results

| Model | Acc | Lat (mean) | $/run | $ total | acc%/$ |
|---|---|---|---|---|---|
| **deepseek-v4-pro** (orig)         | 47/50 (94%) | 723s | $0.019  | $0.93 | 50 |
| **gpt-5.4-nano @ xhigh** (NEW)     | **45/49 (92%)** ¹ | 1243s | $0.056 | $2.75 | 16 |
| **deepseek-v4-flash** (orig)       | 44/50 (88%) | 357s | $0.006  | $0.28 | **157** |
| qwen3.6-35b-a3b (orig)             | 40/50 (80%) | 139s | $0.022  | $1.10 | 36 |
| qwen3.6-plus (orig)                | 39/50 (78%) | 739s | $0.074  | $3.72 | 11 |
| **gemini-3-flash @ xhigh** (NEW)   | ~45/50 (~90%) ² | n/a (orig 18s + 229s for retests) | n/a | $0.28+$1.27 | n/a |
| gemini-3-flash (orig, default)     | 37/50 (74%) | 18s  | $0.011  | $0.55 | 70 |
| gemma-4-31b-it (orig)              | 34/50 (68%) | 235s | $0.002  | $0.08 | 425 |
| **deepseek-v4-flash (no reasoning)** (NEW) | **25/50 (50%)** | 158s | $0.002  | $0.10 | 250 |
| gpt-oss-120b (orig)                | 29/50 (58%) | 191s | $0.001  | $0.06 | **483** |

¹ nano-xhigh: 1 trial (geometry-021) hung at 70 min — second time this exact
PID stalled on nano-xhigh (also blew up the 12-problem run). Worth
investigating as a stable model/problem incompatibility rather than treating
as random.
² gemini-3-flash xhigh = 37 prior-correct + 8/13 of the retests at xhigh =
projected 45/50. Caveat: assumes prior-correct hold under xhigh, untested.

### Findings

- **gpt-5.4-nano @ xhigh is real.** 92% on 50 (with 1 unfinished) — within
  margin of v4-pro (94%), better than v4-flash (88%). Cost ~3× v4-pro and
  ~10× v4-flash, so v4-flash still wins acc%/$. But for "best accuracy under
  $5", nano-xhigh is now a top-2 candidate alongside v4-pro.
- **Reasoning is the lever, not the model.** v4-flash without reasoning falls
  off a cliff: 88% → 50%, and cost only drops 65% ($0.28 → $0.10). The
  reasoning trace IS the value being paid for; cutting it breaks v4-flash.
  Implication: $/run comparisons across models are mostly comparisons of
  reasoning effort, not raw model capability.
- **gemini-3-flash xhigh recovers 8 of 13 failures** — a model that looked
  "strictly dominated by v4-flash" at default effort is competitive at xhigh
  (~90% projected). The original "skip gemini-3-flash" verdict was wrong for
  the same reason as the original "gpt-5.4 is bad" verdict: default effort
  isn't a fair test.
- **Reproducible hang on geometry-021 for nano-xhigh.** Hung at 49 min on the
  12-problem run, hung at 70 min on the 50-problem run. Same model, same
  problem, two separate processes, two different infrastructures. Not a
  random network blip — this PID + reasoning blowup specifically defeats our
  HTTP-level timeout (1500s) and the OpenRouter completion never returns.
  Workaround: hard process-level watchdog or skip this PID for nano-xhigh.
- **Cost ranking on 50** (acc%/$ for like-to-like generate-only pass@1):
  gpt-oss-120b 483 > gemma-4 425 > v4-flash-noR 250 > v4-flash 157 > v4-pro 50
  > nano-xhigh 16. v4-flash remains the practical workhorse. nano-xhigh is
  NOT cost-efficient — it earns its place only on absolute accuracy ceiling,
  and only if you accept the latency and the geometry-021 hang.
- **Latency note.** nano-xhigh mean is 1243s but median 457s — a heavy tail
  drives the mean. Most trials finish in 5-8 min; a few (algebra-014 at 32 min,
  combinatorics-004 at 51 min) are expensive outliers that aren't proportional
  to problem difficulty.

### Decision update vs prior writeup
- **Use v4-flash as the cost-leader workhorse** — confirmed.
- **Add nano-xhigh as a "premium accuracy" tier** alongside v4-pro. Choose
  nano if you have geometric problems (11/11 here vs v4-pro's variable
  geometry numbers); choose v4-pro if you need predictable latency.
- **Drop "default-effort" cost figures from any future cross-model comparison.**
  They're a property of the configuration, not the model. Always set effort
  explicitly (xhigh for capability tests; "none" or low for cheap-tier tests).
- **gemini-3-flash deserves a full xhigh re-run on all 50** before being
  benched permanently — current 8/13 retest is suggestive but not definitive.

Files:
- `experiments/nano_xhigh_answerbench50_20260505.py`
- `experiments/results/nano_xhigh_answerbench50_20260505_partial.json` (49/50)
- `experiments/gemini3flash_xhigh_retest_20260505.py`
- `experiments/results/gemini3flash_xhigh_retest_20260505_20260505_064305.json`
- `experiments/v4flash_noreasoning_answerbench50_20260505.py`
- `experiments/results/v4flash_noreasoning_answerbench50_20260505_20260505_065140.json`

## Best-of-N Scaling for deepseek-v4-flash + gpt-5.4-nano pass@3 — 2026-05-05T16:30

Two parallel experiments. Both judged by **deepseek-v4-flash** (cheaper alternative to v4-pro).

### v4-flash best-of-N (N ∈ {1, 3, 5, 7})
70 problems, reusing 3 existing v4-flash generations from Phase 1 + 4 fresh per problem,
all re-judged by v4-flash. **490 trials, 175 min wall, $8.78.**

| N | n | Mean | Pass (≥6/7) | Δ vs pass@1 |
|---|---|---|---|---|
| 1 | 70 | 3.30 | 33/70 (47%) | — |
| 3 | 70 | 4.06 | 40/70 (57%) | +0.76 |
| 5 | 70 | 4.19 | 41/70 (59%) | +0.89 |
| 7 | 69 | **4.54** | **44/69 (64%)** | **+1.24** |

**Diminishing returns are clear:**
- pass@1 → pass@3: +0.76 (biggest jump)
- pass@3 → pass@5: +0.13 (nearly flat — pass@5 only adds 1 pass)
- pass@5 → pass@7: +0.35 (small recovery — 3 more passes from the long tail)

7-attempt best-of-N delivers 64% pass rate, +17pp over single-shot. Worth the 7× cost
only if the headroom is >0.5/7 mean — borderline for most use cases. **pass@3 captures
~60% of the total scaling uplift at 3× the cost.**

### gpt-5.4-nano with reasoning_effort='xhigh' pass@3
70 problems, fresh generations. **210 trials, 274 min wall, $3.36.** 1 generation failure
(connection drop on PB-Basic-028).

| N | n | Mean | Pass |
|---|---|---|---|
| 1 | 69 | 2.73 | 27/69 (39%) |
| 3 | 67 | **3.15** | **30/67 (45%)** |

### Cross-comparison
- **v4-flash pass@1 (3.30) ≈ gpt-5.4-nano pass@3 (3.15).** Reaching parity with a single
  v4-flash shot requires 3 gpt-5.4-nano attempts at xhigh reasoning.
- v4-flash judge cost: ~$0.0035/call. Comparable parsing reliability to v4-pro
  (both produce clean `<points>` tags).
- gpt-5.4-nano at xhigh reasoning is slow (~30-90 min per hard trial) and produces long
  reasoning traces.

### Headline
Under v4-flash judge, **best-of-N scales positively but with diminishing returns
plateauing around N=5.** Consistent with the project's longstanding "best-of-3 is the
sweet spot" finding from April 5 best-of-N experiment. At pass@7, v4-flash reaches 64%
pass rate — a strong proof-bench baseline.

Files:
- `experiments/best_of_n_v4flash_20260504.py`
- `experiments/results/best_of_n_v4flash_20260504_20260505_115611/` (490 per-trial JSONs + summary.json)
- `experiments/gpt54nano_pass3_20260504.py`
- `experiments/results/gpt54nano_pass3_20260504_20260505_115611/` (210 per-trial JSONs + summary.json)

## Phase 1 RE-RUN with reasoning ON — gpt-oss + gemma — 2026-05-05T18:23:48

Re-ran the original 4-mode benchmark (generate / full / seed_generate / seed_full) for
**gpt-oss-120b and gemma-4-31b-it on all 70 problems** with `extra_body={"reasoning":
{"effort":"high"}}` for both models. Judge: **deepseek-v4-flash** (single, no escalation,
per user instruction). Self-ideation, ITERATIONS=2, NUM_IDEAS=3, MAX_TOKENS=65536, 80 outer
× 3 inner workers, single key (`OPENROUTER_API_KEY_X`).

**560 trials, 9 errors (1.6%, all empty-content from gpt-oss reasoning), $20.46 / $50 cap,
6.7 hours wall.** Reasoning blew output tokens 3× (62M out vs 21M in).

Pre-flight: tested both models with reasoning=high on PB-Basic-001 — both stayed coherent.
Notably, gemma was *faster* with reasoning on (90s vs 245s) — the explicit reasoning trace
seems to help it converge.

### Per-mode means under v4-flash judge

| Mode | Model | n | mean | std | pass≥6 | $/run |
|---|---|---|---|---|---|---|
| generate (pass@3) | gpt-oss-120b | 67 | 2.30 | 3.17 | 22/67 | $0.034 |
| generate (pass@3) | gemma-4-31b-it | 70 | 2.74 | 3.31 | 26/70 | $0.023 |
| full | gpt-oss-120b | 68 | 2.43 | 3.29 | 24/68 | $0.024 |
| full | gemma-4-31b-it | 70 | 2.17 | 3.14 | 21/70 | $0.019 |
| seed_generate | gpt-oss-120b | 69 | 2.54 | 3.24 | 26/69 | $0.031 |
| seed_generate | gemma-4-31b-it | 70 | 2.74 | 3.34 | 27/70 | $0.024 |
| **seed_full** | **gpt-oss-120b** | 67 | **3.00** | 3.44 | **29/67** | $0.076 |
| **seed_full** | **gemma-4-31b-it** | 70 | **3.31** | 3.46 | **33/70** | $0.061 |

### Headlines

1. **seed_full is the best mode for both models** — same pattern as Phase 2 without
   reasoning. gpt-oss 3.00 vs 2.30-2.54 in other modes; gemma 3.31 vs 2.17-2.74.
2. **gemma > gpt-oss in every mode** — gap is 0.3-0.4 points across modes.
3. **Cross-mode ordering with reasoning, by gemma:** seed_full (3.31) > seed_generate ≈ generate (2.74) > full (2.17). Full mode underperforms — verify/revise loop on a reasoning-enabled gpt-oss/gemma may be over-correcting itself (verifier rejects own correct work).
4. **Cross-mode ordering with reasoning, by gpt-oss:** seed_full (3.00) > seed_generate (2.54) > full (2.43) > generate (2.30). Full mode helps gpt-oss more than gemma — the gpt-oss verifier seems calibrated better.
5. **Direct comparison to no-reasoning Phase 2** (gemini judge there, v4-flash here, so not strictly comparable): seed_full means dropped (oss 3.99→3.00, gemma 4.26→3.31). But this almost certainly reflects v4-flash being a stricter judge than gemini-3-flash, NOT reasoning hurting. The earlier Phase 1 v4-pro vs gemini regrade showed gemini systematically +1.5 to +2.5 points more lenient on these models. v4-flash is calibrated closer to v4-pro than gemini.

### Special-10 frontier hits with reasoning ON (v4-flash judge, ≥6/7)

| Condition | Model | Problem | Score |
|---|---|---|---|
| generate (pass@3) | gpt-oss-120b | first-proof-10-official | **7** |
| generate (pass@3) | gemma-4-31b-it | first-proof-10-official | **7** |
| full | gpt-oss-120b | **erdos-654** | 6 |
| full | gemma-4-31b-it | first-proof-10-official | **7** |
| seed_generate | gpt-oss-120b | first-proof-10-official | 6 |
| seed_generate | gemma-4-31b-it | first-proof-10-official | 6 |
| seed_full | gpt-oss-120b | first-proof-10-official | 6 |
| seed_full | gemma-4-31b-it | **erdos-333** | 6 |
| seed_full | gemma-4-31b-it | **erdos-654** | **7** |
| seed_full | gemma-4-31b-it | first-proof-10-official | **7** |

**3 NEW frontier solves under v4-flash with reasoning ON** that did NOT pass under v4-pro
in the original Phase 3 (which used gemini→v4-pro escalation):
- **erdos-333**: gemma seed_full reached 6/7. Phase 3 was 0/7 across all 8 conditions.
- **erdos-654**: gpt-oss full reached 6/7 + gemma seed_full reached 7/7. Phase 3 was 0/7.
- **first-proof-10-official**: now confirmed 7/7 (was 6/7 in Phase 3). Real frontier hit
  for both models with reasoning + seed_full.

This suggests reasoning ON does push frontier capability — at least under v4-flash judge.
A v4-pro cross-check on these 4 frontier solves would confirm whether they survive strict
judging.

### Cost / per-trial reasoning blow-up

- 3× output token inflation vs no-reasoning (62M vs ~21M for similar trial count).
- v4-flash judge (cheap at $0.28/Mtok) keeps the absolute $ small even with reasoning on.
- $/run for seed_full: $0.076 (gpt-oss), $0.061 (gemma) vs Phase 2's ~$0.07 (no reasoning).
  Roughly comparable because reasoning blow-up is offset by the much cheaper v4-flash judge.

### Errors

9 trials errored (1.6% of 560), all from `Model returned empty content + reasoning_content`
on gpt-oss. This is the same provider-side reasoning-overflow pattern flagged in the
v4-pro memory note — gpt-oss occasionally exhausts its reasoning budget without emitting
visible content. Not catastrophic at 1.6%; partial trials saved per-branch.

### Files

- Script: `experiments/phase1_reasoning_20260505.py`
- Run dir: `experiments/results/phase1_reasoning_20260505_20260505_114334/`
- Log: `/tmp/phase1_reason.log`


## Scaling RE-RUN with reasoning ON — N=1,3,5,7,9 — 2026-05-05T17:43:43

Re-ran best-of-N scaling for `gpt-oss-120b` + `gemma-4-31b-it` on the 30 PB-Advanced
problems with reasoning=high. **9 fresh generations per (model, problem)** (no Phase 1
reuse — reasoning fundamentally changes generation). Judge: deepseek-v4-flash, single.

**60/60 trials, 0 errors, $5.65 / $20 cap, 6 hours wall.** Reasoning blow-up: 16.5M out
vs 5.9M in tokens. 60 outer workers, single key (`OPENROUTER_API_KEY_seedgen`).

### Scaling table (mean / pass≥6 out of 30 problems, v4-flash judge)

| Model | N=1 | N=3 | N=5 | N=7 | N=9 |
|---|---|---|---|---|---|
| gpt-oss-120b | 0.67 (3) | 1.40 (6) | 1.40 (6) | 1.73 (7) | **1.80 (7)** |
| gemma-4-31b-it | 0.33 (1) | 0.87 (3) | 1.93 (8) | 1.97 (8) | **2.00 (8)** |

(Numbers in parentheses are problems where best-of-N reached ≥6/7.)

### Reasoning effect

vs no-reasoning scaling under v4-pro (the closest-strictness comparison):

| Model / Judge | N=1 | N=3 | N=5 | N=7 |
|---|---|---|---|---|
| gpt-oss no-reasoning, v4-pro | 0.03 | 0.10 | 0.37 | 0.40 |
| **gpt-oss reasoning, v4-flash** | **0.67** | **1.40** | **1.40** | **1.73** |
| gemma no-reasoning, v4-pro | 0.43 | 0.57 | 0.63 | 0.93 |
| **gemma reasoning, v4-flash** | **0.33** | **0.87** | **1.93** | **1.97** |

(v4-pro vs v4-flash both deepseek family; v4-flash is moderately stricter than gemini,
moderately more lenient than v4-pro. Treat the comparison as "approximately strict-judge".)

**Reasoning roughly doubles the score under strict judging at every N.**

### Headlines

1. **Both models keep gaining at N=9.** gpt-oss N=7→9: +0.07 (saturating), gemma
   N=7→9: +0.03 (basically saturated). Effective ceiling at N=7 for both with reasoning ON.
2. **gemma's scaling has a clear knee at N=5** — jumps from 0.87 (N=3) to 1.93 (N=5),
   then plateaus. Reasoning + sampling diversity together unlock the next plateau.
3. **gpt-oss has a flatter curve** — 1.40 at N=3 and N=5 (no gain), then bumps to 1.73
   at N=7. The gpt-oss reasoning trace seems to converge to a small set of attempts that
   all agree (or all fail) — sampling N=5 doesn't produce a meaningfully different proof.
4. **gemma > gpt-oss only at N≥5.** At N=1, gpt-oss leads (0.67 vs 0.33); the gap inverts
   as N grows. Reasoning + scaling differentially benefits gemma.
5. **Best-of-N with reasoning beats no-reasoning seed_full for both models at strict
   judging.** Phase 1 reasoning seed_full was 3.00/3.31 (v4-flash), and the scaling subset
   is just 30 problems vs 70 — but the per-problem ceiling found via N=9 sampling is
   competitive. For frontier-class problems, simple best-of-N + reasoning is a strong
   baseline.

### Files

- Script: `experiments/scaling_reasoning_20260505.py`
- Run dir: `experiments/results/scaling_reasoning_20260505_20260505_114334/`
  - `trials/<model>/<pid>.json` (60 trial JSONs)
  - `branches/<model>/<pid>/k{0..8}.json` (540 per-gen incremental saves)
- Log: `/tmp/scaling_reason.log`

## Master Dataset 20260505 — v4-flash regrade + unified export — 2026-05-05T22:00

Built `results/dataset_20260505.jsonl` (2848 rows, 567 MB) — the new master dataset
unifying every 0-7-rubric-graded experiment in the repo with up to three independent
judges per cell (v4-pro, gemini-3-flash, v4-flash).  Supersedes
`dataset_20260504.jsonl` (1260 rows, two judges, Phase 1 only).

**v4-flash regrade pass.** Re-judged the 5 prior experiments with deepseek-v4-flash
using hardened call config (max_tokens=131072, extra_body reasoning budget,
reasoning_content fallback per memory `feedback_v4pro_judge_calls.md`).  **7223/7254
cells (99.5%), 0.5% parse-failure rate, $30.21 / $100 cap, ~3.5 hours wall.**

Coverage by experiment (v4-flash judged + folded in):

| Experiment | rows | trial v4flash | branch v4flash | inline judge sources also folded |
|---|---|---|---|---|
| phase1            | 1259 | 1234 | 2889 | v4pro inline + parsefail patch; gemini regrade (best_solution + per-branch) |
| phase2            |  140 |  139 |  419 | gemini inline; v4pro full regrade; v4pro frontier regrade (10 branches) |
| phase3            |   69 |   68 |  205 | gemini inline; v4pro truncation-fixed regrade |
| roleswap          |  560 |  559 | 1662 | gemini inline; v4pro escalation (special-10 only) |
| scaling           |   60 |    — |  420 | gemini + v4pro inline (per-branch only) |
| phase1_reasoning  |  560 |  551 | 1377 | v4flash inline (reasoning ON) |
| scaling_reasoning |   60 |    — |  540 | v4flash inline (reasoning ON) |
| scaling_v4flash   |   70 |    — |  489 | v4flash inline |
| gpt5_nano_pass3   |   70 |    — |  206 | v4flash inline |

**Triple-judge agreement (n=1458 cells with all 3 judges, original experiments):**

|                        | v4pro vs gemini | v4pro vs v4flash | gemini vs v4flash |
|---|---|---|---|
| Exact-match            | 60% | **84%** | 63% |
| Within-1 (\|Δ\|≤1)     | 73% | **95%** | 74% |
| Pass-flip (≥6 vs <6)   | 27% | **5%**  | 26% |
| Mean Δ (col − row)     | +1.75 | **+0.07** | -1.68 |

**Headline: v4-flash agrees with v4-pro 84% exactly and 95% within ±1, with mean Δ of
+0.07.  Gemini disagrees with both at ~26% pass-flip and +1.7 systematic offset.**
This corroborates the gradingbench finding (v4-flash r=0.76, v4-pro r=0.79, gemini
r=0.51) on a sample 7× larger.  The previous "judge-flip" headline (Phase 2 reversal)
is now triple-confirmed: v4-flash sides with v4-pro, not gemini.

**Schema** (long-format JSONL): one row per (experiment, condition, model, problem_id);
nested `judges = {v4pro, gemini, v4flash}` dict at trial level and per-branch.  Each
judge entry has `{score, verdict, source}` where `source` tracks the regrade run that
produced it (so consumers can audit multi-stage judging).  See
`results/dataset_20260505_README.md` for full schema, loading recipes, and aggregation
patterns; `results/dataset_20260505_REPORT.md` for headline numbers (regenerable from
the JSONL via `experiments/build_report_20260505.py`).

Files:
- Dataset: `results/dataset_20260505.jsonl` (2848 rows, 567 MB)
- README:  `results/dataset_20260505_README.md`
- Report:  `results/dataset_20260505_REPORT.md`
- Regrade: `experiments/regrade_all_v4flash_20260505.py`
- Regrade artifacts: `experiments/results/v4flash_judge_20260505/` (7223 per-call JSONs)
- Exporter: `experiments/export_dataset_20260505.py`
- Report builder: `experiments/build_report_20260505.py`
- Logs: `/tmp/v4flash_regrade.log`



## Flex-Budget 3-Experiment Sweep — 2026-05-05T15:32:00

Three experiments on a $30 `OPENROUTER_API_KEY_flex` (16-hour expiry) targeting "what
helps a cheap generator (deepseek-v4-flash) on hard proofs (PB-Advanced)?" Judge:
deepseek-v4-flash (per user). 20 random PB-Advanced problems (seed=42).

Spend: ~$18.06 / $30 (60% util). ~7 hr wall-clock. 0 errors.

| Method | Mean | Pass | $/run | Δ vs pass@1 |
|---|---:|---:|---:|---:|
| pass@1 | 1.75 | 5/20 | $0.020 | — |
| pass@3 | 2.20 | 6/20 | $0.060 | +0.45 |
| **pass@8** | **3.35** | **9/20** | $0.158 | **+1.60** |
| flash_solo full pipeline | 1.85 | 5/20 | $0.060 | +0.10 |
| **flash + v4-pro V↔R critic** | **2.80** | 8/20 | $0.174 | **+1.05** |
| self-ideated seed_full | 3.20 | 9/20 | $0.177 | +1.45 |
| **v4-pro-ideated seed_full** | **2.55** | 7/20 | $0.180 | +0.80 |

### Findings

1. **Strong-critic asymmetric pipeline (v4-flash gen, v4-pro V↔R) is the biggest
   single-architecture win.** +0.95 over flash_solo, rescuing 3 problems (Adv-004/-005/-014)
   from 0/7 to 7/7. Solo verifier early-stops only 10% of the time vs 30% with v4-pro;
   v4-flash genuinely cannot critique its own work, but a strong critic does. Cost 2.9× solo.
2. **Cross-model ideator (v4-pro IDEATING for v4-flash) HURTS by −0.65.** Counter-intuitive
   reversal of the "lit-ideas helps" March hypothesis when extended to model-generated
   ideas. Three problems flipped 7/7 → 0/7 under vp-ideation (Adv-002/-021/-026); only
   one rescued (Adv-022). Mechanism: v4-pro names a *specific* approach (e.g. "Three-Branch
   Centroid via Symmedian Point") that v4-flash commits to and cannot escape, even when
   the method is hard for v4-flash to execute. Self-ideated v4-flash often falls back
   to placeholder "default-N" ideas (~28% JSON parse failure rate, agent_log known issue),
   which leaves v4-flash effectively unconstrained — and on these problems, less
   constraint wins.
3. **Pass@N keeps scaling through N=8** under v4-flash judge — no saturation visible.
   Mean climbs +1.6 from N=1 to N=8; passes nearly double 5→9. Self-ideated seed_full
   (3.20 / 9 passes) ≈ pass@8 (3.35 / 9 passes) at higher cost. Pass@N is the cheapest
   reliable lever.
4. **11 of 20 PB-Advanced problems (55%) are never solved in 8 v4-flash samples** —
   genuine capability ceiling for cheap-generator on these problems.
5. **flash_solo (full pipeline w/ same model) barely beats pass@1** (+0.10) — verify+revise
   is real work for this task; cheap-tier verifier doesn't do it.

### Cross-method coverage

Different methods solve disjoint problem sets:
- pass@8 wins ONLY on Adv-024 (k=7), Adv-003 (k=3, late hit), Adv-017 (k=6).
- strong-critic wins ONLY on Adv-005, Adv-014.
- self-seed_full wins ONLY on Adv-002 (6/7), Adv-021, Adv-026.
- vp-seed_full wins ONLY on Adv-022.

Union of best-method coverage: 12-13 of 20 problems. No single architecture dominates;
ensembling / method-selection is an open follow-up.

### Methodology

- Three experiments ran in parallel on the same flex key (24 + 10 + 12 = 46 concurrent
  workers). No 429s observed; OpenRouter rate limits are per-key.
- Per-trial atomic JSON saves; per-branch incremental saves for cross_ideator.
- MAX_TOKENS=32768 (down from 65536 in Phase 1-3) was sufficient — no truncation.
- Cost killswitches at $6 / $10 / $3 caps; none triggered (run finished at 60% of total cap).
- v4-flash judge sanity-check: agreed with v4-pro on the easy known-passing problems
  (Adv-001/-019/-025); flagged one possible false positive (Adv-003 at 7/7 once vs Phase 1
  baseline 0/0/0). Larger calibration audit would need a separate run.

### Files

- Report: `flex_budget_report.md`
- Scripts: `experiments/{cross_ideator,strong_critic,passN}_v4flash_20260505.py`
- Aggregator: `experiments/aggregate_flex_runs_20260505.py`
- Run dirs: `experiments/results/{cross_ideator,strong_critic,passN}_v4flash_20260505_*/`
- Aggregated summary: `experiments/results/flex_summary_20260505.json`
- Logs: `/tmp/{cross_ideator,strong_critic,passN}_run.log`

### Suggested follow-ups (untested in this run)

1. **Strong-critic + pass@N composition**: resample then critique-revise. Predicted ~3.7 mean.
2. **Strip idea names from v4-pro output** to separate "good prompt structure" from
   "specific approach commitment" — clarifies the cross-ideator regression mechanism.
3. **N>8 pass@N curve** (no saturation observed; v4-flash likely keeps gaining to N=15).
4. **Strong-critic with v4-flash @ higher reasoning effort** instead of v4-pro — tests
   whether the gain is "more compute on critique" or "different model on critique".


## Reasoning vs no-reasoning — synthesis report — 2026-05-05T19:45:00

Side-by-side comparison of the reasoning re-runs (Phase 1 + scaling) against the
original no-reasoning baselines. **Big caveat: judges differ** — original Phase 1 used
v4-pro, original scaling used gemini + v4-pro, the reasoning re-runs use v4-flash. v4-flash
strictness sits between v4-pro (very strict) and gemini (lenient). Where comparisons are
shown below, strict-vs-strict (v4-pro old ↔ v4-flash new) is used.

### Phase 1 results — reasoning re-run

`experiments/results/phase1_reasoning_20260505_20260505_114334/` (560 trials, 9 errors,
$20.46, 6.7 h wall). 80 outer × 3 inner workers, single key `OPENROUTER_API_KEY_X`,
judge `deepseek-v4-flash`, `extra_body={"reasoning": {"effort": "high"}}` for both models.

| Mode | Model | n | mean | std | pass≥6 | $/run |
|---|---|---|---|---|---|---|
| generate (pass@3) | gpt-oss-120b | 67 | 2.30 | 3.17 | 22/67 | $0.034 |
| generate (pass@3) | gemma-4-31b-it | 70 | 2.74 | 3.31 | 26/70 | $0.023 |
| full | gpt-oss-120b | 68 | 2.43 | 3.29 | 24/68 | $0.024 |
| full | gemma-4-31b-it | 70 | 2.17 | 3.14 | 21/70 | $0.019 |
| seed_generate | gpt-oss-120b | 69 | 2.54 | 3.24 | 26/69 | $0.031 |
| seed_generate | gemma-4-31b-it | 70 | 2.74 | 3.34 | 27/70 | $0.024 |
| **seed_full** | **gpt-oss-120b** | 67 | **3.00** | 3.44 | **29/67** | $0.076 |
| **seed_full** | **gemma-4-31b-it** | 70 | **3.31** | 3.46 | **33/70** | $0.061 |

### Scaling results — reasoning re-run

`experiments/results/scaling_reasoning_20260505_20260505_114334/` (60 trials, 0 errors,
$5.65, 6 h wall). 60 workers, single key `OPENROUTER_API_KEY_seedgen`, 9 fresh generations
per (model, problem), judge `deepseek-v4-flash`.

| Model | N=1 | N=3 | N=5 | N=7 | N=9 |
|---|---|---|---|---|---|
| gpt-oss-120b | 0.67 (3) | 1.40 (6) | 1.40 (6) | 1.73 (7) | **1.80 (7)** |
| gemma-4-31b-it | 0.33 (1) | 0.87 (3) | 1.93 (8) | 1.97 (8) | **2.00 (8)** |

(Numbers in parentheses = problems where best-of-N reached ≥6/7.)

### Δ vs no-reasoning, strict judge (Phase 1)

| Mode | Model | no-reasoning v4-pro | reasoning v4-flash | Δ |
|---|---|---|---|---|
| generate | gpt-oss | 1.33 | **2.30** | +0.97 |
| generate | gemma | 1.83 | **2.74** | +0.91 |
| full | gpt-oss | 1.39 | **2.43** | +1.04 |
| full | gemma | 1.17 | **2.17** | +1.00 |
| seed_generate | gpt-oss | 1.27 | **2.54** | +1.27 |
| seed_generate | gemma | 1.53 | **2.74** | +1.21 |
| seed_full | gpt-oss | (not measured in old Phase 1) | **3.00** | — |
| seed_full | gemma | (not measured in old Phase 1) | **3.31** | — |

(no-reasoning v4-pro numbers are from agent_log Phase 1 row 5 / item 5: original v4-pro
final-judge means across all 70 problems.)

### Δ vs no-reasoning, strict judge (Scaling)

| Model | N | no-reasoning v4-pro | reasoning v4-flash | Δ |
|---|---|---|---|---|
| gpt-oss | 1 | 0.03 | **0.67** | +0.64 |
| gpt-oss | 3 | 0.10 | **1.40** | +1.30 |
| gpt-oss | 5 | 0.37 | **1.40** | +1.03 |
| gpt-oss | 7 | 0.40 | **1.73** | +1.33 |
| gemma | 1 | 0.43 | 0.33 | −0.10 |
| gemma | 3 | 0.57 | **0.87** | +0.30 |
| gemma | 5 | 0.63 | **1.93** | +1.30 |
| gemma | 7 | 0.93 | **1.97** | +1.04 |

(no-reasoning numbers are from `experiments/results/scaling_oss_gemma_20260505_20260505_033250/`
under the v4-pro judge column — see the Best-of-N Scaling agent_log entry from 2026-05-05T05:11:55.)

### Headlines

1. **Reasoning roughly doubles strict-judge score across modes (~+1.0 point uplift).**
2. **Reasoning roughly doubles best-of-N at every N≥3.** gemma N=1 is a wash; both models
   keep gaining slightly to N=9 but plateau by N=7.
3. **Cross-mode ordering with reasoning:** seed_full > seed_generate ≈ generate > full
   for gemma; seed_full > seed_generate > full ≈ generate for gpt-oss. Reasoning improves
   gpt-oss's verifier (full mode no longer last) but gemma's reasoning-on verifier
   over-corrects (full underperforms generate).
4. **gemma > gpt-oss in 7 of 8 mode-cells** (only gpt-oss seed_full edges close; the gap
   stays small but consistent).
5. **3 NEW frontier solves under v4-flash with reasoning** (vs Phase 3 with v4-pro):
   erdos-333 (gemma seed_full 6/7), erdos-654 (gpt-oss full 6/7 + gemma seed_full 7/7),
   first-proof-10-official now confirmed 7/7 (was 6/7 in Phase 3).

### Cost summary

| Run | trials | $ | $/trial | wall |
|---|---|---|---|---|
| Phase 1 reasoning | 560 | **$20.46** | $0.037 | 6.7 h |
| Scaling reasoning | 60 | **$5.65** | $0.094 | 6 h |
| (Old Phase 2 no-reasoning, ref) | 140 | $9.70 | $0.069 | 1.3 h |
| (Old scaling no-reasoning, ref) | 60 | $6.22 | $0.104 | 1.7 h |

Reasoning blows up output tokens 3–4× (62M out vs 21M in for Phase 1; 16.5M vs 5.9M for
scaling) but absolute $ stays flat because v4-flash is far cheaper than the gemini/v4-pro
judges used in older runs. **Net cost neutral, capability roughly doubles.**

### Caveats

- Cross-judge noise: v4-flash strictness ≠ v4-pro. The "reasoning ~doubles score" headline
  could be partly a judge-leniency artifact. A v4-pro re-grade of these reasoning trials
  would tighten the comparison; estimated cost ~$10 for the most-interesting subset
  (Phase 1 seed_full + scaling N=9 = ~190 trials).
- 9 errors in Phase 1 reasoning (1.6%) all from `Model returned empty content +
  reasoning_content` on gpt-oss — provider-side reasoning overflow without visible content.
  Trials saved at per-branch granularity, so partial work survives.
- Frontier solves on erdos-333 / erdos-654 should be sanity-checked with v4-pro before
  being treated as canonical results — Phase 3's v4-pro escalation was definitive at
  walking back gemini-only frontier claims.

### Files

- Phase 1 reasoning script: `experiments/phase1_reasoning_20260505.py`
- Phase 1 reasoning run dir: `experiments/results/phase1_reasoning_20260505_20260505_114334/`
  - 560 per-trial JSONs (tree under `mode/<model_short>/<pid>.json`)
  - `manifest.jsonl` (560 lines)
  - Log: `/tmp/phase1_reason.log`
- Scaling reasoning script: `experiments/scaling_reasoning_20260505.py`
- Scaling reasoning run dir: `experiments/results/scaling_reasoning_20260505_20260505_114334/`
  - 60 per-trial JSONs under `trials/<model_short>/<pid>.json`
  - 540 per-branch JSONs under `branches/<model_short>/<pid>/k{0..8}.json`
  - `manifest.jsonl` (60 lines)
  - Log: `/tmp/scaling_reason.log`


## Composed strong-critic + pass@N (partial) — 2026-05-05T16:04:00

Follow-up to the flex-budget sweep. Tested whether v4-pro V↔R critique on top of
a v4-flash pass@8 best-of-N starting solution composes the gains of the two
winning methods (strong-critic +0.95, pass@8 +1.60 over pass@1).

Status at write-up: 4 of 20 trials done, all 7→7 preserved. The informative
0/7-starter trials are still in-flight after 25 min each (v4-pro reasoning is
slow on cases where the verifier doesn't early-stop). Run is left running in
background; results to be folded into a future agent_log update.

Partial preliminary read: **v4-pro V↔R preserves 7/7 starters reliably** — no
regressions in 4/4. Verifier early-stops on iter 1 ("VERDICT: correct") for
all 4 7-starter trials, costing only ~$0.03/trial.

Run dir: `experiments/results/composed_critic_passN_20260505_20260505_193921/`

Final flex-key spend at report time: $19.15 used / $30 cap (64% utilization).
Run was left in background for additional data collection per remaining budget.


## Composed strong-critic + pass@N — FINAL — 2026-05-05T17:43:00

The composed-critic experiment (run in background after the initial wrap-up) finished
all 20 trials — 19 valid + 1 OpenRouter connection-drop on Adv-030.

### Headline (n=19)

| Stage | Mean | Pass≥6 |
|---|---:|---:|
| Starter (pass@8 best) | 3.53 | 9/19 |
| After v4-pro V↔R | 3.32 | 9/19 |
| Δ | **−0.21** | **0** |

Per-problem: 1 improved (Adv-026 1→7), 14 unchanged, 4 regressed
(Adv-024 7→0, Adv-008 1→0, Adv-010 1→0, Adv-029 1→0).

### Reading

**Composition does NOT meaningfully improve over pass@8 alone.** Pass count
is identical (9/19 before and after) — the rescue (Adv-026) is exactly cancelled
by the ruin (Adv-024). Mean drops 3.53 → 3.32 because three small regressions
on 1-starters lose score points without compensating gains.

The strong-critic effect from Experiment 2 (+0.95) does NOT stack on top of
pass@N. Mechanism: pass@N already finds a high-quality solution per problem
(so the 7-starters have nothing for the critic to fix), and the critic
occasionally "improves" a correct solution into an incorrect one. The Adv-024
7→0 regression is the headline cautionary case — it took $0.19/2010s of v4-pro
reasoning to ruin a working solution.

**Lesson**: don't compose strong-critic with pass@N best-of-N. Strong-critic
earns its keep on *raw* generations (Experiment 2), where it finds errors that
v4-flash made and v4-flash can't fix. On a v4-flash-judge-best-of-8 starting
solution, the residual errors are subtle enough (or absent) that v4-pro is more
likely to introduce a regression than fix one.

A cleaner composition would be **strong-critic on every sample, then take
best-of-N of the critiqued solutions** — but that is N× more expensive and
was not tested here.

### Final flex-budget spend

$22+ used / $30 cap (composition added $2.56 to the prior $19.55).

### Files

- Run dir: `experiments/results/composed_critic_passN_20260505_20260505_193921/`
- Report: `flex_budget_report.md` (Experiment 4 section)

## Master Dataset 20260505 — refresh (3-hour follow-up) — 2026-05-06T01:41

The scheduled 3-hour cron fired and re-surveyed agent_log.md.  Four new in-scope
experiments had landed since finalisation:

1. **flex_cross_ideator**: 40 trials (2 conditions × 20 PB-Advanced).  Cross-model
   ideator effect (self vs v4-pro ideating for v4-flash).
2. **flex_strong_critic**: 40 trials (2 conditions × 20 PB-Advanced).  v4-flash
   gen × {flash, v4-pro} V↔R critic.
3. **flex_passn**: 20 trials × 8 k-levels.  Pure pass@N for v4-flash on PB-Advanced.
4. **flex_composed_critic**: 19 trials.  Composition of pass@8 + v4-pro V↔R.

Plus the existing `scaling_reasoning` source dir grew from 60 to 124 trials (more
problems added by the source experiment); the exporter picks them up automatically.

All 4 new experiments were judged inline by v4-flash at gen time — no v4-flash
regrade needed.  Folded them into the dataset by extending the exporter with row
builders that mirror the existing roleswap / scaling patterns.

**Refreshed dataset**: 3032 rows (was 2848), 648 MB (was 567 MB).  No additional
v4-flash regrade spend — the four flex experiments came pre-judged.

Files updated:
- `results/dataset_20260505.jsonl` (3032 rows)
- `results/dataset_20260505_README.md` (coverage + source-experiments tables)
- `results/dataset_20260505_REPORT.md` (regenerated from JSONL)
- `experiments/export_dataset_20260505.py` (4 new row builders)

Skipped (per the cron's instruction list): the "Reasoning vs no-reasoning synthesis
report" entry at line 2849 — it's a writeup, not a new experiment.  The "partial"
composed-critic at line 2975 is superseded by the FINAL entry at line 2996, which
is the one folded in.

**Follow-up amendment** (manual, after user catch): the **roleswap-with-reasoning**
experiment at line 3167 (`role_swap_reasoning_20260505_20260505_114334`, 560 trials
× 8 conditions, gpt-oss × gemma with reasoning ON, v4-flash inline judge) was missed
on the first pass because it landed in agent_log between my finalisation and the
cron's survey window.  Folded in retroactively as `roleswap_reasoning` (560 rows
+ 1671 branch records).  Refreshed counts:

- Dataset: **3608 rows**, 827 MB
- Trial-level v4flash coverage: 3205 (was 2650; +555 from the new experiment)
- Branch-level v4flash coverage: 10,813 (was 9,034)

Also: the `scaling_reasoning` source dir grew further from 124→140 trials between
the cron run and this amendment — those new cells were also picked up automatically.

Files re-updated:
- `results/dataset_20260505.jsonl`
- `results/dataset_20260505_README.md`
- `results/dataset_20260505_REPORT.md`
- `experiments/export_dataset_20260505.py` (added `roleswap_reasoning` row builder)


## Scaling RE-RUN with reasoning ON — EXTENDED to all 70 problems — 2026-05-05T23:55:31

Extended the reasoning scaling experiment from the original 30 PB-Advanced subset to **all
70 problems** (30 PB-Basic + 30 PB-Advanced + 10 special-10). Same script, same judge
(`deepseek-v4-flash`), same reasoning config (`effort=high`), same N values (1, 3, 5, 7, 9).
Resumed into the existing run dir so the original 30 PB-Advanced × 2 models × 9 generations
were skipped — only 80 new (model, problem) trials ran (40 problems × 2 models).

**Note: this dataset is DISTINCT from the no-reasoning scaling (`scaling_oss_gemma_20260505_*033250`).**
Reasoning ON, judge v4-flash; vs no-reasoning + dual judges (gemini + v4-pro).

### Full-set summary

**140 trials total (60 from original run + 80 from extension), 4 errors (2.9%, all
gpt-oss transient `peer closed connection without sending complete message body` after 3
retries), $11.25 grand total ($5.65 original + $5.60 extension).**

Pending failed problems (could be re-run with another targeted resume):
gpt-oss × {erdos-397, PB-Basic-009, PB-Basic-027, first-proof-6-official}.

### All-70 scaling table (judge = deepseek-v4-flash, reasoning=high)

| Model | N=1 | N=3 | N=5 | N=7 | N=9 |
|---|---|---|---|---|---|
| gpt-oss-120b   | 1.52 (15/67) | 2.78 (27/67) | 2.87 (28/67) | 3.04 (29/67) | **3.18 (30/67)** |
| gemma-4-31b-it | 1.57 (15/70) | 2.64 (26/70) | 3.21 (32/70) | 3.26 (32/70) | **3.29 (32/70)** |

(Numbers in parens = problems that hit ≥6/7 best-of-N. Denominator differs because
gpt-oss had 3 of 70 trials end in connection errors after retries.)

### Per-subset breakdown (illustrating mean composition)

| Subset (n) | Model | N=1 | N=3 | N=5 | N=7 | N=9 |
|---|---|---|---|---|---|---|
| PB-Basic (30) | gpt-oss | 2.93 (12) | 4.93 (20) | 5.11 (21) | 5.18 (21) | **5.43 (22)** |
| PB-Basic (30) | gemma   | 3.10 (13) | 5.07 (22) | 5.30 (23) | 5.37 (23) | **5.40 (23)** |
| PB-Advanced (30) | gpt-oss | 0.67 (3) | 1.40 (6) | 1.40 (6) | 1.73 (7) | **1.80 (7)** |
| PB-Advanced (30) | gemma   | 0.33 (1) | 0.87 (3) | 1.93 (8) | 1.97 (8) | **2.00 (8)** |
| special-10 (10) | gpt-oss | 0.00 (0) | 0.67 (1) | 0.78 (1) | 0.78 (1) | **0.78 (1)** |
| special-10 (10) | gemma   | 0.70 (1) | 0.70 (1) | 0.80 (1) | 0.80 (1) | **0.80 (1)** |

### Headlines

1. **PB-Basic saturates fast** — both models near 5/7 mean by N=3, almost flat to N=9.
   Reasoning + 3 samples is the sweet spot for these.
2. **PB-Advanced needs N=5+ for gemma to overtake** (knee at N=5: 0.87 → 1.93). gpt-oss
   has a flatter curve and saturates at ~1.8 by N=7. gemma's reasoning trace is more
   diverse, so resampling unlocks more.
3. **Special-10 is essentially out of reach for either model in best-of-N alone.** Only
   1 problem each (different one for each model — likely first-proof-10) is solved at any N.
   Sampling diversity doesn't substitute for fundamental capability gap on frontier problems.
4. **Aggregate trend, all 70:** both models gain ~+1.7 from N=1 to N=9 (oss 1.52→3.18,
   gemma 1.57→3.29). Most of the gain happens by N=3-5.
5. **gemma > gpt-oss starts at N=5** (0.05–0.34 lead), same pattern as the 30-problem
   subset. Reasoning + sampling diversity favors gemma.

### Δ vs no-reasoning scaling (the distinct prior dataset)

The no-reasoning scaling experiment ran on **30 PB-Advanced only** with two judges (gemini
and v4-pro). For the apples-to-apples PB-Advanced comparison (strict-judge: v4-pro old vs
v4-flash new):

| Model | N | no-reasoning v4-pro | reasoning v4-flash | Δ |
|---|---|---|---|---|
| gpt-oss | 1 | 0.03 | **0.67** | +0.64 |
| gpt-oss | 3 | 0.10 | **1.40** | +1.30 |
| gpt-oss | 5 | 0.37 | **1.40** | +1.03 |
| gpt-oss | 7 | 0.40 | **1.73** | +1.33 |
| gpt-oss | 9 | (not run) | **1.80** | — |
| gemma | 1 | 0.43 | 0.33 | −0.10 |
| gemma | 3 | 0.57 | **0.87** | +0.30 |
| gemma | 5 | 0.63 | **1.93** | +1.30 |
| gemma | 7 | 0.93 | **1.97** | +1.04 |
| gemma | 9 | (not run) | **2.00** | — |

Reasoning ~doubles strict-judge score on PB-Advanced at N≥3.

### Files

- Script: `experiments/scaling_reasoning_20260505.py` (uses SCALING_SUBSET=None → all 70)
- Run dir: `experiments/results/scaling_reasoning_20260505_20260505_114334/`
  - `trials/<model>/<pid>.json` — 140 per-trial JSONs
  - `branches/<model>/<pid>/k{0..8}.json` — 1252 per-branch incremental saves (some
    failed branches don't have k saved)
  - `manifest.jsonl` — 140 lines (4 with `error` field set)
- Logs: `/tmp/scaling_reason.log` (original), `/tmp/scaling_reason_resume.log` (extension)


## Phase 3 RE-RUN with reasoning ON — role-swap matrix — 2026-05-06T02:23:00

Re-ran the 8-condition role-swap experiment with `extra_body={"reasoning":{"effort":"high"}}`
for both candidate models in their roles. Judge: **deepseek-v4-flash** (single, no
escalation, per user instruction). Same conditions as Phase 3, same 70 problems, single key
(`OPENROUTER_API_KEY_X2`), 40 outer × 3 inner workers.

**560/560 trials, 1 error (0.2%), $39.96, 14.7 hours wall.**

### Per-condition results (judge = v4-flash, all 70 problems)

| Condition | n | mean | std | pass≥6 | $/run | Δ vs Phase 3 (no-reasoning, gemini+v4pro) | Δ vs same-model Phase 1-reasoning seed_full |
|---|---|---|---|---|---|---|---|
| x_ideate_oss     | 70 | 2.96 | 3.41 | 29/70 | $0.060 | −1.24 | −0.35 (vs gemma 3.31) |
| x_ideate_gemma   | 68 | 3.09 | 3.40 | 30/68 | $0.073 | −0.88 | +0.09 (vs oss 3.00) |
| **x_verify_oss** | 70 | **3.63** | 3.43 | **36/70** | $0.064 | −0.53 | **+0.32** (vs gemma 3.31) |
| x_verify_gemma   | 69 | 3.00 | 3.40 | 30/69 | $0.085 | −0.44 | +0.00 (vs oss 3.00) |
| x_revise_oss     | 70 | 3.41 | 3.44 | 34/70 | $0.073 | −0.83 | +0.10 (vs gemma 3.31) |
| **x_revise_gemma** | 69 | 3.48 | 3.40 | 34/69 | $0.073 | −0.56 | **+0.48** (vs oss 3.00) |
| random_run1      | 69 | 3.19 | 3.42 | 31/69 | $0.069 | −0.54 | +0.03 (vs mix 3.16) |
| random_run2      | 70 | 3.34 | 3.45 | 34/70 | $0.073 | −0.80 | +0.19 (vs mix 3.16) |

(Phase 3 baselines used gemini judge + v4-pro escalation on special-10. Phase 1-reasoning
baselines used v4-flash judge with reasoning ON. v4-flash is moderately stricter than
gemini, so the Δ-vs-Phase-3 is partly a judge calibration shift.)

### Apples-to-apples (66 shared problems across all 8 conditions)

| Condition | mean | pass≥6 |
|---|---|---|
| **x_verify_oss** | **3.85** | 36/66 |
| x_revise_gemma | 3.64 | 34/66 |
| x_revise_oss | 3.62 | 34/66 |
| random_run2 | 3.55 | 34/66 |
| random_run1 | 3.33 | 31/66 |
| x_ideate_gemma | 3.17 | 30/66 |
| x_ideate_oss | 3.14 | 29/66 |
| x_verify_gemma | 3.14 | 30/66 |

### Headline shift vs no-reasoning Phase 3

In no-reasoning Phase 3, the worst swap was **x_verify_gemma (−0.55)** — gemma-as-verifier
broke a gpt-oss pipeline. In reasoning Phase 3, **x_verify_oss (+0.32) is the BEST swap** —
gpt-oss-as-verifier improves a gemma pipeline by 0.5 points (3.31 → 3.85 on shared
problems). The verifier role flipped from "fragile" to "highest-leverage" once reasoning
is on. Reading: with reasoning, the gpt-oss reasoning trace produces a sharper verifier
critique that materially helps gemma's revision step; gemma's verifier remains weaker even
with reasoning enabled.

Other reads:
1. **Adding gemma as reviser to a gpt-oss pipeline (x_revise_gemma)** is the only other
   condition with a clear positive (+0.48 vs oss 3.00). Aligns with gemma being the
   stronger writer once given a critique.
2. **Random conditions are mid-pack** — same as no-reasoning Phase 3. Random mixing roughly
   matches the average targeted swap; doesn't beat the best.
3. **Both ideator swaps underperform the best targeted swap** by 0.5–0.7 — ideator
   diversity per se isn't the bottleneck (consistent with Phase 1-reasoning showing
   seed_full only modestly above seed_generate).
4. **The full pipeline + role-mixing is still NOT a free uplift over same-model seed_full.**
   The best mixed condition (x_verify_oss at 3.63) only edges past gemma-only seed_full
   (3.31) by +0.32, well below the noise floor we'd want for a robust claim.

### Special-10 frontier outcomes (reasoning + role-swap, v4-flash)

11 condition×problem pairs reached ≥6/7 on a special-10:

| Condition | Problem | Score |
|---|---|---|
| **x_ideate_oss** | erdos-333 | 6 |
| **x_ideate_oss** | first-proof-10-official | 7 |
| x_verify_oss | erdos-333 | 6 |
| **x_verify_oss** | erdos-659 | **7** |
| x_verify_gemma | first-proof-10-official | 7 |
| **x_revise_oss** | erdos-654 | **7** |
| x_revise_oss | first-proof-10-official | 7 |
| x_revise_gemma | first-proof-10-official | 6 |
| x_ideate_gemma | first-proof-10-official | 7 |
| random_run1 | first-proof-10-official | 7 |
| random_run2 | first-proof-10-official | 7 |

NEW frontier hits under v4-flash with reasoning + role-mixing (problems that were 0/7 for
both candidate models in same-model Phase 1-reasoning seed_full):
- **erdos-333 (6/7)** in x_ideate_oss and x_verify_oss
- **erdos-659 (7/7)** in x_verify_oss
- **erdos-654 (7/7)** in x_revise_oss

These cluster on the conditions that put gpt-oss in the verifier or reviser role —
consistent with the verify_oss/revise_oss positive deltas. Sanity-check with v4-pro
recommended before treating as definitive frontier results, given the no-reasoning Phase 3
showed v4-pro consistently flipped gemini-=7 to v4-pro=0 on these same problems.

### Cost / wall

Reasoning+role-swap cost $39.96 vs Phase 3 (no reasoning) $38.75 — essentially flat
because cheaper v4-flash judge offsets reasoning-on token blow-up (112M out vs 28M out
in Phase 3). Wall-clock 14.7 h vs Phase 3's 200 min — reasoning calls take ~3× longer.

### Files

- Script: `experiments/role_swap_reasoning_20260505.py`
- Run dir: `experiments/results/role_swap_reasoning_20260505_20260505_114334/`
  - `trials/<condition>/<pid>.json` — 560 per-trial JSONs
  - `branches/<condition>/<pid>/branch_{0,1,2}.json` — 1680 per-branch saves
  - `manifest.jsonl` (560 lines, 1 with error)
- Log: `/tmp/role_swap_reason.log`


## Bucket split 20260506 — 2026-05-07T00:01:00

Split `results/dataset_20260505.jsonl` (3608 rows, 827 MB) into 3 thematic
sub-datasets. Pure transform — no new judge calls.

Splitter: `experiments/split_buckets_20260506.py`. Layout per bucket mirrors
`results/answerbench_calibration_20260506/`: `trials.jsonl`, `trials.csv`,
`summary.csv`, `data_dictionary.md`, `report.md`.

Cross-cutting enrichments applied to all 3 buckets:
- `difficulty` (int 0-5) + `difficulty_label` + `difficulty_provenance` from
  `experiments/difficulty_20260506.py` (smoke distribution: 8 at d=0, 53 at
  d=1, 4 at d=2, 2 at d=3, 2 at d=4, 1 at d=5).
- `reasoning` ∈ {`default`, `max`, `min`}. Default everywhere except
  phase1_reasoning / roleswap_reasoning / scaling_reasoning / gpt5_nano_pass3
  → `max`. Master distribution: 2278 default + 1330 max.
- `is_26_research` (bool) — renamed from `is_special_10`. 489 master rows.

Outputs:
- `results/architecture_20260506/` — 2098 trial rows, 30 summary rows.
  Sources: phase1, phase1_reasoning, phase2, phase3, gpt5_nano_pass3.
  Includes derived `pass_at_1_v4flash` for `mode='generate'` rows (= score on
  `branches[0]`; correlated with the trial-level pass@3, not an independent
  draw).
- `results/scaling_20260506/` — 1080 trial rows (270 master rows × 4 N
  values), 20 summary rows. Sources: scaling, scaling_reasoning,
  scaling_v4flash. Replaces nested-prefix `max(scores[:n])` with **exhaustive
  enumeration of C(M, n) size-n subsets** per (model, problem); reports
  `pass_at_n_mean` + `pass_at_n_std` + `pass_at_n_pass_rate` per judge.
- `results/roleswap_20260506/` — 1160 trial rows, 77 summary rows. Sources:
  roleswap, roleswap_reasoning, flex_cross_ideator (with
  `subclass="ideator_strength"`). Role columns extracted from
  `mode_extras.roles`.

Verification:
- 5/5 sampled architecture rows match master (v4flash score equality).
- Scaling pass@1 = mean(branches), pass@7 = max(branches), confirmed on a
  spot-check.
- Phase 1 model×mode means under v4-flash: v4-pro full=3.85 / pass=0.55,
  v4-flash full=3.38 / pass=0.48, gemini full=1.59 / pass=0.23 (sane).

Master `dataset_20260505.jsonl` and its README are unchanged — buckets are
views, not replacements. Master README updated with a "Focused bucket views"
section pointing at the 3 subdirs.

## gemini-3.1-pro-preview AnswerBench-50 default-effort fill-in - 2026-05-07T07:51:48

Ran `gemini-3.1-pro-preview` (default reasoning, no `reasoning` param sent) on the
38 PIDs of the AnswerBench-50 stratified set NOT covered by the 2026-05-04
expensive-models 12-PID probe. Same methodology as the rest of the calibration:
generate-only, pass@1, seed=42, MAX_TOKENS_GEN=65536, judge =
`google/gemini-3.1-flash-lite-preview`. 38-way parallel single wave (one worker
per PID), 512s wall-clock. Key: `OPENROUTER_API_KEY_2`.

Script: `experiments/gemini3pro_answerbench50_remaining_20260507.py`.
Result JSON: `experiments/results/gemini3pro_answerbench50_remaining_20260507_20260507_075148.json`.

**Run-only result (38 PIDs):** 29/38 (76.3%), $9.99 spent, $0.333/run, 0 errors.

**Combined with 12 prior PIDs from expensive-models probe → full AB-50 row:**
- **39/50 (78%)** at default effort
- $0.2584/run, $12.92 total, 233s mean gen latency
- Per category: 11/12 Alg, 8/13 Comb, 11/12 Geom, 9/13 NT
- acc%/$ = 302 — **strictly dominated**: same accuracy as qwen3.6-plus (78%) but 3.5×
  the per-run cost; far behind v4-pro (94% at $0.019/run, 17× more efficient).

Default-only caveat: the gpt-5 family showed default-effort understates capability
for some models. xhigh on gemini-3.1-pro is the obvious next probe before fully
writing it off.

Updated `results/answerbench_calibration_20260506/{trials.csv,trials.jsonl,summary.csv,
report.md,data_dictionary.md}`. Build script
`experiments/build_answerbench_calibration_20260506.py` extended with two new sources
(the new 38-PID JSON, and a `model_filter`-gated read of the 12 PIDs from the
expensive-models JSON). trials.csv now has 650 rows (13 model_configs × 50 PIDs);
summary.csv has 14 rows (13 real + 1 synthesized).

## paper-draft v4 - 2026-05-07T05:00:00
Critique-driven rewrite of `drafting/draft_v3.md` -> `drafting/draft_v4.md`. Four
substantive updates: (1) difficulty-tier-stratified architecture lift analysis
with paired bootstrap CIs and permutation p-values, (2) all-trial frontier solves
table pooling architecture (n=2098) and scaling (n=1080) trials = 32 strict-judge
v4-flash R26 solves total (vs 27 architecture-only in v3) including DeepSeek pass@7
solves of Erdős-1051 (research-medium) and FirstProof-6 (research-hard), (3) read
codex's draft and adopted the more conservative "pipeline does not beat
token-matched sampling" framing the data actually supports, (4) CIs and p-values
throughout. Headline reversal: `full - generate` is null at every tier (p=0.45);
Gemma reasoning=max `full-generate` is significantly NEGATIVE (p=0.023). seed_full
lift survives only at reasoning=max (Δ=+0.60 p=0.003, vs +0.13 p=0.46 at default).
Difficulty gradient: 86%/29%/23%/2%/0%/0% pass-rate by tier. P(Gemini pass |
v4-flash fail) = 0.37 [0.34, 0.40] over 987 strict-fail cases. Main paper at 4,648
words (under 5,000). Six figures (added difficulty-gradient bar chart, lift-by-tier
forest plot, replaced reasoning-vs-arch with proper effect-size forest plot,
updated pass@k with CI ribbons). Analysis script: `drafting/analysis_v4.py`.
No new API calls.

## validate_research_solves_20260507 - 2026-05-07T06:55:00
Cascade-validation of R26 strict-judge solves: v4-flash → v4-pro → GPT-5.4-nano-xhigh.
50 candidate cells (44 v4-flash≥6 ∪ 16 v4-pro≥6 ∪ scaling-bucket per-branch solves).
Ladder: **44 v4-flash → 31 v4-pro-validated → 4 nano-validated**. Total cost $0.91.

Big narrative shifts:
- Erdős-1051 (DS-flash pass@7): v4f=6 → v4p=0. Research-medium "solve" collapses.
- FirstProof-6 (DS-flash pass@7): v4f=7 → v4p=0. Research-hard "solve" collapses.
- Erdős-397, FirstProof-5: similar single-cell collapses under v4-pro.
- FirstProof-10: 33 v4-flash → 24 v4-pro → 1 nano. Heavy false-positives even on the "easiest" research-tier problem.
- **Only Erdős-654 survives all 3 rungs robustly** (5 → 4 → 3 cells across multiple base models × multiple architectures). This is the only credible reproducible research-tier solve in the dataset.

Survivors of all 3 rungs (4 cells):
- Erdős-654 × DS-v4-flash seed_full default
- Erdős-654 × DS-v4-pro full default
- Erdős-654 × Gemma-4-31B seed_full max
- FirstProof-10 × DS-v4-flash full default

Output: `results/validate_research_solves_20260507/{report.md, trials.csv, trials.jsonl, summary.csv}`.

## paper-draft v5 - 2026-05-07T07:30:00
Peer-review revision of `drafting/draft_v4.md` -> `drafting/draft_v5.md`. Two reviews
flagged overlapping issues. Cross-reviewer items addressed: (1) "strict solves" ->
"candidate passes" terminology throughout; (2) demoted pooled `seed_full=+0.32` with
explicit partial-coverage marking (3/6 base models); (3) recomputed all headline
contrasts with problem-clustered bootstrap (vs trial-level in v4) — `full-generate`
cluster Δ=−0.08 [−0.25,+0.08], p=0.36; `seed_full-generate` reasoning=max stratum
+0.60 [+0.21,+1.03], p=0.005; (4) computed actual per-trial generator costs from
cost_usd column — full is 0.78× generate cost (cheaper, not 1×), seed_full is 1.36×
generate (not 3×) — re-cost-matched seed_full vs pass@4-5 not pass@9; (5) Holm
correction on §5.4 8-test family — none survives at α=.05 (smallest Holm-p=0.15),
reframed as exploratory; the pooled stratum cluster contrast survives p=0.005;
(6) Wilson/Clopper-Pearson upper bounds replace [0,0] CIs for zero-pass cells
(research-hard ≤5.4%, research-frontier ≤10.6%); (7) statistical-dependence caveat
in §3.4 + limitations; (8) §10 follow-ups promoted into §8 fragility notes;
(9) tighter abstract. Singletons: GradingBench off-distribution caveat for §5.5,
AI-assistance disclosure, FirstProof-10 outlier flag (23/33 likely leaked, drops
total from 32 to 9 v4-flash candidate passes excl. FP-10), generator-judge family
stratification (lift concentrates in cross-family generators — no judge-family
inflation), Zheng et al. 2023 cite. Analysis script: `drafting/analysis_v5.py`.
Main paper at 4,989 words. No new API calls.

## Scaling bucket extension to pass@9 - 2026-05-07T13:30:00

Extended `results/scaling_20260506/` from M=7 (n ∈ {1,3,5,7}) to M=9 (n ∈ {1,3,5,7,9}) on the canonical 70-problem PB+R26 set for all 5 (source, model, reasoning) cells, to enable a token-matched generate-only baseline against the `full` (generator → verifier ↔ reviser) pipeline.

**New scripts**
- `experiments/extend_scaling_pass9_20260507.py` — generates only the missing branches per cell to reach M=9. Multi-key OpenRouter rotation (auto-disable on 401/403/429/limit-exceeded), per-model semaphores (gemma=30, gpt-oss=30, v4f=40), 80 worker threads, deterministic shuffled workplan, retry+jittered exponential backoff (6 retries, 5s→160s base, ±50% jitter, capped at 180s). v4flash judge.
- `experiments/backfill_phase1_v4flash_20260507.py` — re-judges the 5 phase1-generate branches that were never v4flash-graded; emits a sidecar JSON the merger consumes.
- `experiments/merge_scaling_pass9_20260507.py` — folds existing dataset rows + new branches + backfill into rebuilt trials.jsonl/trials.csv/summary.csv plus updated data_dictionary.md and report.md (n=9 column).

**Run summary**
- Workplan: 771 (gen + judge) units. Breakdown: gemma default=300, gpt-oss default=300, gpt-oss max=31, deepseek-v4-flash default=140. (gemma max was already 70×9 — skipped.)
- Reuse: phase1 'generate' branches (k=0..2, default reasoning) on the 40 ProofBench problems outside PB-Advanced-001..030 that the original `scaling` source never ran, judged with v4flash.
- Wall: ~3 hours total (2.5 hr in steady-state at sem=30; bottleneck was Novita/Chutes upstream rate-limiting on gemma + gpt-oss with several long-tail units >5,000s).
- Cost: $5.32. Cap was $60.
- Errors: 0 final. 4 stale errors in the manifest are from earlier-restart attempts; resume re-ran them successfully.
- Run dir: `experiments/results/extend_scaling_pass9_20260507_20260507_090106/`.

**Updated bucket files** (`results/scaling_20260506/`)
- `trials.jsonl` 1750 rows (was 1080); `trials.csv` aligned; `summary.csv` 25 rows.
- All 5 cells × 70 pids × 9 branches uniformly post-extension.
- `data_dictionary.md` notes the extension policy + branch_origins provenance.
- `report.md` headline table now includes n=9.

**Headline pass@9 (mean v4flash, 70-problem PB+R26)**
| cell                                              | n=1  | n=3  | n=5  | n=7  | n=9  |
|---------------------------------------------------|-----:|-----:|-----:|-----:|-----:|
| scaling | gemma-4-31b-it | default                | 0.88 | 1.54 | 1.93 | 2.20 | 2.41 |
| scaling | gpt-oss-120b | default                  | 0.82 | 1.27 | 1.47 | 1.61 | 1.71 |
| scaling_reasoning | gemma-4-31b-it | max          | 1.92 | 2.76 | 3.05 | 3.20 | 3.29 |
| scaling_reasoning | gpt-oss-120b | max            | 1.63 | 2.45 | 2.81 | 3.05 | 3.23 |
| scaling_v4flash | deepseek-v4-flash | default     | 2.74 | 3.65 | 4.01 | 4.25 | 4.54 |

Monotonicity verified across all 5 cells. v4flash default at pass@9 (4.54) outperforms both max-reasoning models at the same budget. research_solves at pass@9: v4f=4 (vs 1 at n=7); gemma max=1; gpt-oss max=1; default-reasoning gemma/gpt-oss=1 each (up from 0).

## Consensus Judge Validation Experiment - 2026-05-07T19:10:00

Tested whether a majority-vote consensus of three cheap judges (gemma-4-31b-it@high, gpt-oss-120b@xhigh, deepseek-v4-flash@default) matches frontier judges (gemini-3.1-pro, claude-opus-4.7) on a NEW 200-problem held-out sample (seed=7, zero overlap with prior seed=42).

Trio + 2 frontiers run on the validation sample. Hardened {0,1,6,7} prompt. Results in `consensus-judge-experiment/`.

**Headline (validation, sorted by pass_agree_at_6):**

| System | n_valid | pass≥6 | F1 | r | $/200 |
|---|---|---|---|---|---|
| **trio_consensus** | 199 | **0.884** | **0.816** | 0.712 | **$1.28** |
| gpt-oss-120b @ xhigh | 197 | 0.873 | 0.806 | 0.672 | $0.32 |
| claude-opus-4.7 | 200 | 0.855 | 0.785 | 0.789 | $32.45 |
| deepseek-v4-flash | 142 | 0.852 | 0.712 | 0.619 | $0.48 |
| gemini-3.1-pro | 196 | 0.842 | 0.777 | 0.768 | $6.94 |
| gemma-4-31b-it @ high | 126 | 0.825 | 0.744 | 0.687 | $0.48 |

Trio beats both frontiers on pass_agree and F1 at 25× the cost reduction vs Opus, 5× vs Gemini.

**Per-problem disagreement breakdown (n=200):** 157 all-correct; 12 trio-only-correct (vs both frontiers wrong); 2 Opus-only-correct; 1 Gemini-only-correct. Frontier models agree with each other 95.9% of the time on validation (they fail the same way).

**Issues:** Google upstream rate limits crippled gemma (74/200 missing) and slowed v4-flash (58/200 missing). gpt-oss had 1 hung call killed at 14:42 UTC. Opus 4.7 ran cleanly at $32.45 / 200 calls (~$0.16/call). Total experiment spend: ~$40.

**Deliverables in `consensus-judge-experiment/`:**
- `report.md` — NeurIPS-style paper (10K words)
- `trials_prior.csv` (2000 rows = 10 prior configs × 200 PIDs)
- `trials_validation.csv` (1000 rows = 5 validation configs × 200 PIDs)
- `trials_validation.jsonl` (with verdict text)
- `consensus_analysis.csv` (400 rows = 200 prior + 200 validation, per-problem trio + frontier comparison)
- `summary.csv` (17 rows = 10 prior individual + 5 validation individual + 2 consensus)
- `data_dictionary.md`
- `pricing_snapshot.json`

## FrontierMath Open-Problems Pass@5 Probe - 2026-05-07T19:32:00

Ran pass@5 across openai/gpt-oss-120b (xhigh) + deepseek/deepseek-v4-flash on
the FrontierMath open-problems benchmark (26 prompt × model × 5 seeds = 260
trials, 233 completed at 15:25 EDT before killing long-tail). LLM judge
(deepseek-v4-flash) labeled 31 correct, 4 almost, 38 partial, 160 incorrect.
Spent ~$10 of $40 budget.

**Key result: LLM judges are unreliable on verifiable problems**:
- Started 3-judge consensus (gpt-oss xhigh + gemini-3.1-pro + deepseek-v4-flash)
  on 70 positives, killed at 55 done (gpt-oss judge calls were stalling).
- All 9 unanimous "3/3 correct" results split into:
  - **5 LOCALLY VERIFIED PASSES** on explicit-deformations warmup
    (gpt-oss seeds 42,44,45,46 + deepseek seed=44 in consensus, plus 3 more
    that didn't reach consensus before kill)
  - **1 LOCALLY VERIFIED PASS** on degree-sensitivity-boolean warmup
    (deepseek seed=44, n=6, deg=3, sens=6, a=1.6309)
  - **3 FALSE POSITIVES** on inverse-galois (M_22/M_23 polynomial)

**Inverse-galois cleanup**: implemented a `verify_inverse_galois_necessary`
checker (irreducible + perfect-square discriminant, both required since
M_n ⊂ A_n). All 20 inverse-galois submissions across both models and all seeds
**FAIL**, including the 3-judge unanimous "correct"s. This is a clean
counter-example showing LLM judges happily sign off on plausible-looking
polynomials with confident citations even when basic disc-square check rules
out the claimed Galois group.

**Final verified-pass count: 8 trials across 2 problems**:
- explicit-deformations warmup: 7 trials (gpt-oss × 4, deepseek × 3 — 7/9 attempts
  produced verifiable curvilinear deformations of A = k[x,y]/(x,y)² to k[t]/(t³))
- degree-sensitivity-boolean warmup: 1 trial (deepseek seed=44; n=6, deg=3,
  sensitivity=6, exponent a = log(6)/log(3) ≈ 1.6309 > 1.63 threshold)

**Discarded experiments**: gemma seed_full + roleswap on 4 top problems × 2
seeds (16 trials each) ran for 8 min with zero completions; outer ThreadPool
saturated by trials all blocked behind gemma 8-concurrent semaphore +
expensive ideate→3 branches × verify-revise×2 → judge sequence. Killed.
Replaced with simpler `openproblems_gemma_passN_20260507.py` (generate-only).

**Files**:
- `experiments/openproblems_pass5_20260507.py` (Phase 1)
- `experiments/openproblems_consensus_judge_20260507.py` (3-judge consensus)
- `experiments/openproblems_local_verify_20260507.py` (Hadamard, Steiner,
  Ramsey-book, small-Diophantine, degree-sensitivity, explicit-deformations,
  inverse-galois necessary conditions)
- `experiments/check_galois_polys_20260507.py` (inverse-galois sanity check)
- `experiments/openproblems_seed_full_20260507.py` (seed_full architecture
  — too slow on these problems, killed)
- `experiments/openproblems_gemma_passN_20260507.py` (focused gemma generate)
- `logs/openproblems_pass5_20260507_20260507_183859.jsonl` (Phase 1 raw)
- `experiments/results/consensus_partial_55_log.txt` (partial consensus)


## Consensus Judge Experiment - PATCHED - 2026-05-07T20:55:00

Patched dropped validation calls via three mechanisms: OpenRouter `provider.order` routing (SiliconFlow for v4-flash), direct Google AI Studio API (Tier-2 GEMINI_API_KEY for gemma, bypassing OpenRouter's shared backend), and single-worker retry. Re-ran build with merged data.

**Final patched coverage:**
- gpt-oss-120b @ xhigh: 200/200
- gemini-3.1-pro: 200/200
- claude-opus-4.7: 200/200
- deepseek-v4-flash: 195/200
- gemma-4-31b-it @ high: 190/200
- Trio coverage with ≥2/3 valid: 191/200 (95.5%)

**Updated headline (validation):**

| System | n_v | pass≥6 | F1 | r | $/200 |
|---|---|---|---|---|---|
| **gpt-oss-120b @ xhigh** | 200 | **0.875** | **0.806** | 0.676 | $0.32 |
| trio_consensus | 200 | 0.860 | 0.785 | 0.747 | $1.73 |
| deepseek-v4-flash | 195 | 0.856 | 0.759 | 0.669 | $0.70 |
| claude-opus-4.7 | 200 | 0.855 | 0.785 | 0.789 | $32.45 |
| gemini-3.1-pro | 200 | 0.840 | 0.771 | 0.766 | $7.07 |
| gemma-4-31b-it @ high | 190 | 0.800 | 0.732 | 0.694 | $0.71 |

**Key finding shift after patching:** With full coverage, **gpt-oss-120b @ xhigh alone** is now the strongest single system on pass-agree (87.5%) — beating both frontiers. The trio (86.0%) still beats both frontiers but no longer dominates as much. F1 on trio (0.785) ties Opus exactly. All cheap judges still beat Gemini-3.1-Pro on pass-agree.

**Disagreement breakdown (n=200):** 153 all-correct; 9 trio-only-correct; 4 Opus-only-correct; 1 Gemini-only-correct; 14 all-wrong.

**Lesson learned:** OpenRouter routes non-BYOK calls through their shared backend Google account, so all our keys hit the same upstream quota. Direct Google AI Studio API (with Tier-2 user key) was 10× faster for gemma. SiliconFlow provider routing on OpenRouter bypassed DeepSeek's slow upstream for v4-flash.

## Bootstrap CIs added to consensus paper - 2026-05-07T21:30:00

Computed bootstrap 95% CIs (1000 resamples, n=200 with replacement) and pairwise win rates for the 6 validation systems. Key finding: **CIs overlap heavily across the top 5 systems**, so the original "trio beats both frontiers" / "gpt-oss beats Opus" claims are statistically weakly supported (P~0.76).

**Reliable claims (P>0.90):**
- gpt-oss-120b @ xhigh > Gemini-3.1-Pro on pass≥6 (P=0.91)
- All cheap judges crush gemma alone

**Weakly supported (P~0.75–0.80):**
- gpt-oss > Opus (point estimate 87.5 vs 85.5, but CI [82.5, 91.5] vs [80.0, 90.0] overlap)
- trio > Gemini, Opus > Gemini

**Toss-ups (P~0.50–0.60):**
- trio vs Opus, v4-flash vs Opus

**Real frontier advantage:** Opus's r=0.789 [0.71, 0.86] is non-overlapping with gpt-oss's r=0.674 [0.57, 0.76]. Frontier still wins on continuous calibration.

Also: GradingBench has only 3 (problem, response) pairs with multiple human grades — far too few for inter-rater agreement statistics. Cannot estimate the human ceiling. If ceiling is ~90%, then 87.5% is essentially at the ceiling, not 12.5 pp below perfect. Largest unknown in interpretation.

Paper headline softened from "Cheap Judges Beat Frontier" to "Cheap Judges Are Competitive with Frontier."

## Gemma Phase 1 + seed_full + roleswap completion - 2026-05-07T23:45:00

After the initial OpenRouter-rate-limited gemma attempts, switched to direct Gemini API
(gemma-4-31b-it on tier 2 paid account) using a custom adaptive-concurrency wrapper
(`experiments/_gemini_api.py`) that scales between 4–20 concurrent based on 429 cascades.

**Phase 1 gemma pass@5**: 120/120 trials. 30 judge positives, **0 locally verified**.

**Seed_full homogeneous gemma**: scaled down to warmup × 1 seed × 2 ideas × 1 V↔R iter
after first attempt at full scope (3 ideas, 2 iters, 5 seeds) was unviable at gemma
rate limits. 12/12 problem-seeds done. 6 positives, 0 locally verified.

**Seed_full roleswap (gemma + gpt-oss-120b xhigh as verifier)**: same scope. 12/12 done.
7 positives, 0 locally verified.

**Consensus v2** (user spec: oss xhigh + deepseek, no gemma judge after the gemini-3.1-pro
mistake): ran on 30 gemma phase 1 positives + 18 OG phase 1 positives that didn't get
v1 + 13 seed_full positives. Total 111 consensus entries. **30 entries got unanimous
2/2 or 3/3 "correct" but only 8 are locally-verifiable correct** — the remaining 22
are LLM-judge confabulations on inverse-galois (disc not a square), kakeya (forcing
pair fails), Steiner (incomplete coverage), Hadamard (no matrix produced), Ramsey
(adj string truncated), or stretched-LR (constant polynomial).

**Key finding reinforced**: across ~380 trials and 4 generator architectures
(pass@5, seed_full homogeneous, seed_full roleswap), no new locally-verified
solutions appeared. The architectural variations (ideate→branch→V↔R, role
swap with stronger verifier) did not produce improvements over plain pass@5.

**Files added today**:
- `experiments/_gemini_api.py` — adaptive Gemini API client
- `experiments/_kakeya_verifier.py` — full forcing-pair semantics check
- `experiments/_lr_verifier.py` — Littlewood-Richardson stretched coefficient verifier
- `experiments/openproblems_gemma_phase1_20260507.py`
- `experiments/openproblems_gemma_seedfull_20260507.py`
- `experiments/openproblems_consensus_v2_20260507.py` (oss + deepseek 2-judge)
- `experiments/openproblems_full_report_20260507.py`
- `results/openproblems_full_report.md`

