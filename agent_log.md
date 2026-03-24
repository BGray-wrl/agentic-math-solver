
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
