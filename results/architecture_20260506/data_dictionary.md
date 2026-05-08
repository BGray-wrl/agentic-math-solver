# Architecture Bucket — Data Dictionary

Cross-mode, cross-model architecture comparison. Sources: phase1, phase1_reasoning,
phase2, phase3, gpt5_nano_pass3 from `results/dataset_20260505.jsonl`.

## Files

- **`trials.jsonl`** — long format, one JSON object per trial. Carries enriched
  rows from the master JSONL (judges{}, branches[], mode_extras), plus the new
  `mode`, `reasoning`, `difficulty`, `is_26_research`, and `pass_at_1_v4flash`
  fields.
- **`trials.csv`** — flat tabular view, canonical judge column = v4flash. Nested
  fields are in the JSONL only.
- **`summary.csv`** — wide aggregate, one row per (source_experiment, mode,
  model_short, reasoning).

## `trials.csv` columns

| Column | Type | Meaning |
|---|---|---|
| `experiment` | str | Always `architecture` for this bucket. |
| `source_experiment` | str | Origin in master: `phase1` / `phase1_reasoning` / `phase2` / `phase3` / `gpt5_nano_pass3`. |
| `mode` | str | Architecture mode: `generate` / `seed_generate` / `full` / `seed_full`. For `gpt5_nano_pass3` (originally `pass3_xhigh`) we normalize to `generate` since it's a pass@3 baseline. |
| `condition` | str | Original master `condition` value (raw). For most rows `mode == condition`; for gpt5_nano_pass3, `condition='pass3_xhigh'` and `mode='generate'`. |
| `model_short` | str | Last path segment, e.g. `gpt-oss-120b`. |
| `model_id` | str | Full OpenRouter model id. |
| `reasoning` | str | One of `default` / `max` / `min`. See README. |
| `problem_id` | str | e.g. `PB-Advanced-001`, `erdos-397`, `ramsey-hypergraphs`. |
| `level` | str | Native ProofBench label or frontier-novelty tag (preserved for granular analysis). |
| `difficulty` | int (0-5) | Unified frontier-emphasis scale. See `experiments/difficulty_20260506.py`. |
| `difficulty_label` | str | Human-readable mirror, e.g. `competition-hard`. |
| `is_26_research` | bool | True for the 10 problems in the 2026 research-tier set. |
| `v4flash_score` | int (0-7) or null | **Canonical judge.** From `judges.v4flash.score` in master. |
| `v4flash_pass` | bool or null | `v4flash_score >= 6`. Null when score is null. |
| `v4pro_score` | int (0-7) or null | Audit judge. |
| `gemini_score` | int (0-7) or null | Audit judge. |
| `pass_at_1_v4flash` | int (0-7) or null | For `mode='generate'` only: v4flash judge score on `branches[0]`. **Correlated with the trial-level pass@3 score** (it is the first sample of pass@3, NOT an independent draw). Surfaces the pass@1→pass@3 delta visually. Null for non-generate rows. |
| `n_branches` | int | Number of branches in the original master row. |
| `cost_usd` | float or null | Wall-cost from master row. |
| `elapsed_s` | float or null | Wall-time from master row. |
| `error` | str or null | Non-null if the trial errored. |

## `summary.csv` columns

| Column | Meaning |
|---|---|
| `source_experiment`, `mode`, `model_short`, `reasoning` | Group key. |
| `n_trials` | Rows in this group. |
| `n_valid_v4flash` | Rows with non-null v4flash_score. |
| `mean_score_v4flash` | Mean over valid v4flash scores (0-7). |
| `pass_rate_v4flash` | Fraction with v4flash_score ≥ 6. |
| `mean_score_pre_imo` | Mean v4flash on difficulty=0 rows. |
| `mean_score_imo` | Mean v4flash on difficulty=1 rows. |
| `mean_score_research` | Mean v4flash on difficulty ≥ 2 rows. |
| `research_solves` | Count of difficulty ≥ 2 rows that scored ≥ 6. |
| `mean_cost_usd` | Mean of per-row cost_usd. |

## Coverage matrix (mode × model)

See `report.md` for the full coverage table. Brief: Phase 1 covers 6 models on
generate / seed_generate / full (NOT seed_full); seed_full only comes from
Phase 2 (gpt-oss + gemma), Phase 3 (v4-flash), and phase1_reasoning (gpt-oss +
gemma reasoning=max). gpt5_nano_pass3 is a 1-cell asymmetric extension on the
generate axis only (gpt-5.4-nano @ reasoning=max).

## Loading recipes

```python
import pandas as pd
df = pd.read_csv("results/architecture_20260506/trials.csv")
# Phase 1 cross-model means at v4-flash judge:
g = df[df.source_experiment == "phase1"].groupby(["model_short", "mode"]).v4flash_score.mean()
```
