# Roleswap Bucket — Data Dictionary

Cross-model role-assignment comparison. Sources: roleswap, roleswap_reasoning,
flex_cross_ideator from `results/dataset_20260505.jsonl`.

## Subclasses

| Subclass | Source experiments | Conditions | Roles varied |
|---|---|---|---|
| `oss_gemma_8cell` | roleswap, roleswap_reasoning | random_run1, random_run2, x_ideate_oss, x_ideate_gemma, x_revise_oss, x_revise_gemma, x_verify_oss, x_verify_gemma | gpt-oss-120b vs gemma-4-31b-it across ideator/generator/verifier/reviser; "x_*" = swap that one role to the other model |
| `ideator_strength` | flex_cross_ideator | self_v4flash, vp_v4flash, mini_v4flash | v4-flash held in gen+verify+revise; ideator varied across {v4-flash, v4-pro, gpt-5.4-mini@xhigh} |

**Problem-set asymmetry**: `oss_gemma_8cell` runs on the 70-problem benchmark.
`ideator_strength` runs on a different subset (20 random PB-Advanced problems).
Cross-subclass analysis must filter to overlapping problem IDs.

## Files

- **`trials.jsonl`** — one row per trial, with role columns + subclass.
- **`trials.csv`** — flat tabular view.
- **`summary.csv`** — one row per
  (subclass, condition, reasoning, ideator, generator, verifier, reviser).

## `trials.csv` columns

| Column | Type | Meaning |
|---|---|---|
| `experiment` | str | Always `roleswap`. |
| `source_experiment` | str | `roleswap` / `roleswap_reasoning` / `flex_cross_ideator`. |
| `subclass` | str | `oss_gemma_8cell` or `ideator_strength`. |
| `condition` | str | Original condition label from master. |
| `reasoning` | str | `default` / `max`. |
| `ideator_model`, `generator_model`, `verifier_model`, `reviser_model` | str | Full OpenRouter IDs. |
| `model_short`, `model_id` | str | The trial's "primary" model (the generator). |
| `problem_id`, `level`, `difficulty`, `difficulty_label`, `is_26_research` | — | See architecture data dictionary. |
| `v4flash_score` | int (0-7) or null | Canonical judge. |
| `v4flash_pass`, `v4pro_score`, `gemini_score`, `n_branches`, `cost_usd`, `elapsed_s`, `error` | — | See architecture data dictionary. |

## `summary.csv` columns

| Column | Meaning |
|---|---|
| `subclass`, `condition`, `reasoning`, `ideator_model`, `generator_model`, `verifier_model`, `reviser_model` | Group key. |
| `n_problems` | Rows in this group. |
| `n_valid_v4flash` | Rows with non-null v4flash_score. |
| `mean_score_v4flash` | Mean over valid v4flash scores. |
| `pass_rate_v4flash` | Fraction with v4flash_score ≥ 6. |
| `mean_score_imo` | Mean on difficulty=1 rows. |
| `mean_score_research` | Mean on difficulty ≥ 2 rows. |
| `research_solves` | Count of difficulty ≥ 2 rows that scored ≥ 6. |
| `mean_cost_usd` | Mean of per-row cost_usd. |

## Loading recipes

```python
import pandas as pd
df = pd.read_csv("results/roleswap_20260506/trials.csv")
oss_gemma = df[df.subclass == "oss_gemma_8cell"]
oss_gemma.groupby("condition").v4flash_score.mean().sort_values()
```
