# Data dictionary

All scores are on the IMO 0--7 scale. Judges are *instructed* to emit one of {0, 1, 6, 7};
the parser accepts any integer 0--7, and a handful of off-bucket scores (4 across all runs)
occurred and are used as parsed. "Pass" means score ≥ 6. A `score` of `null`/empty means
the call failed or did not parse (< 2% of calls; see the paper's coverage note).

---

## `data/consensus_analysis.csv` — per-instance scores (400 rows)

One row per grading instance, for the prior (200, seed 42) and validation (200, seed 7)
samples. **No benchmark text** (problem/solution/candidate) is included.

| Column | Meaning |
|---|---|
| `grading_id` | benchmark instance id (e.g. `GB-0094`) |
| `sample` | `prior` or `validation` |
| `gpt_oss_120b_xhigh_score` | GPT-OSS-120B @ effort=xhigh |
| `deepseek_v4_flash_default_score` | DeepSeek-V4-Flash @ default |
| `gemma_4_31b_it_high_score` | Gemma-4-31B @ effort=high |
| `gemini_3_1_pro_score` | **Gemini 3.1 Pro at DEFAULT reasoning** (used for Table A1 "default" and the prior sample). Table 1 reports Gemini at HIGH reasoning, which lives in `gemini_high_validation.json`. |
| `claude_opus_4_7_score` | Claude Opus 4.7 (validation rows only) |
| `human_score` | expert human grade, 0--7 (ground truth) |
| `human_pass_at_6`, `human_signal_at_1` | `human_score >= 6`, `>= 1` |
| `trio_*` | precomputed cheap-consensus fields (majority pass/signal, mean, median, n_valid, match). `compute_metrics.py` recomputes the consensus independently and does not depend on these. |
| `gemini_3_1_pro_*`, `claude_opus_4_7_*` | per-judge precomputed pass/match flags |
| `problem_id`, `problem_source` | problem identifier and origin (e.g. `USAMO 2025`, `Novel Problem`) |

## `data/remaining600_<model>.json` — the other 600 problems (cheap judges)

Run record for one cheap judge over the 600 instances not in prior+validation. Top level:
`judge_id, model, reasoning_config, reasoning, max_tokens, sample, n, total_cost_usd,
stats, date, results`. Each `results[]` entry: `grading_id, problem_id, source,
human_points, score, verdict` (judge output text), `usage` (token counts + `cost` +
`finish_reason`), `cost`, `finish_reason`. Merged with `consensus_analysis.csv` to form
the n=1000 benchmark (Table 2).

## `data/gemini_high_validation.json` — Gemini 3.1 Pro @ HIGH, validation 200

Same shape as above for Gemini at high reasoning. Backs the Gemini row of Table 1 and the
"high" row of Table A1. `usage.reasoning_tokens` gives the per-call reasoning budget used.

## `data/multi_seed/` — run-to-run replicates (Table 3, §6.2)

- `judge_<model>_<reasoning>_rep{1,2,3}_*.json` — one cheap judge, one replicate, on the
  validation 200. `results[]`: `grading_id, human_points, score, provider` (the OpenRouter
  backend that served the call), `reasoning_tokens, cost, finish_reason`. No inference seed
  was sent (see paper §6.2).
- `summary_noseed_reps.json` — aggregated: `rep_labels`, `per_judge_pass_agree`,
  `per_consensus_pass_agree`, `mean_std` (the Table 3 mean±std), and `provider_mix`
  (`{judge: {provider: call_count}}`, the basis of `ext_provider_mix.csv`).
  Note: the "orig" replicate equals the validation column of `consensus_analysis.csv`.

## `data/trials_validation.jsonl` — raw per-call records, validation (5 judges)

One JSON object per line, per (judge, instance). Includes `judge_id, model_id,
reasoning_config, grading_id, problem_id, problem_source, human_score, judge_score,
judge_pass_at_6, pass_match_at_6, delta, prompt_tokens, completion_tokens,
reasoning_tokens, total_tokens, cost_usd, elapsed_s, error`, and **`verdict`** (the
judge's full output text — model output, which may quote candidate fragments). Use this to
audit or re-grade any individual decision. The 15 calls that were rate-limited on the
original run carry their final backfilled score (from `consensus_analysis.csv`) with the
fields `backfill: true`, `original_error`, and `backfill_note`; per-call verdict/token
telemetry was not retained for those reruns.

## `data/full1000_metrics.csv` — per-system full-benchmark metrics

Precomputed per-system summary used as input to the figures. Columns: `system, group`
(individual / pair / combined), `rule` (single / unanimous_pass / majority_vote), `n,
pass_agree, pa_ci_lo, pa_ci_hi, precision, recall, f1, f1_ci_lo, f1_ci_hi, spearman_rho,
tp, fp, tn, fn`. `spearman_rho` is populated for single judges and blank for consensus
rows. `compute_metrics.py` regenerates the same numbers into `results/tables/table2_full1000.csv`.

## `data/pricing_snapshot.json`

Per-model token pricing (USD per million tokens) used to attribute cost, best-effort as of
the run date. Real billing may differ; reported costs use OpenRouter's returned `usage.cost`.

---

## `results/tables/*.csv` (emitted by `compute_metrics.py`)

`table1_validation.csv`, `table2_full1000.csv`, `table3_runtorun.csv`,
`tableA1_gemini_reasoning.csv` mirror the paper's tables. Extended tables:
`ext_confusion_matrices.csv` (TP/FP/TN/FN per system × sample), `ext_self_consensus.csv`
(self-majority / self-all-3 P/R/F1), `ext_prior_sample.csv`, `ext_calibration_bias.csv`
(mean judge − human), `ext_provider_mix.csv`. See `EXTENDED_RESULTS.md`.
