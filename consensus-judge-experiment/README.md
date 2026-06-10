# consensus-judge-experiment

Cheap-LLM consensus judging of natural-language math proofs (IMO-GradingBench).

## Layout

| Path | What it holds |
|---|---|
| `supplement/` | **Canonical, self-contained reproducibility package** — regenerates every paper table/figure from per-instance scores. Start here. See `supplement/README.md`. |
| `draft/` | Paper drafts (`working_draft_v5.md` is current), lit review, plot candidates, ICML format. |
| `multi-seed-cheap/` | Run-to-run replicate study (3 cheap judges × 3 reps) — self-contained with its own README/archive. |
| `report.md`, `data_dictionary.md` | Earlier full write-up and data schema. |
| `data/` | Datasets and per-instance score tables: `gradingbench.csv` (benchmark input), `consensus_analysis.csv`, `trials_*`, `pricing_snapshot.json`. |
| `results/` | Timestamped judge-run dumps + aggregate metrics CSVs (validation, remaining-600 backfill, full-1000 metrics, `summary.csv`). |
| `reference_scripts/` | One-off runner / validation / backfill / summary scripts. Provided for transparency; already run. |
| `archive/` | Superseded / scratch: run logs (`*.out`), build artifact (`supplement.zip`), `preliminary_draft.md`. |

> Note: scripts in `reference_scripts/` read inputs by bare relative path (e.g. `gradingbench.csv`,
> `consensus_analysis.csv`), which now live under `data/`. Adjust the path or run from `data/`
> if re-executing them.
