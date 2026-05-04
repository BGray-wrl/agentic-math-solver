# Seed-Ideas 4-Way Comparison v2 — Dataset

Generated 2026-05-04 by `experiments/export_dataset_20260504.py`.

## Files

- `dataset_20260504.jsonl` — 1260 records, 191 MB, one JSON object per line
- `dataset_20260504_README.md` — this file

## Source

Combines three runs:

| Source | Path | Provides |
|---|---|---|
| Phase 1 | `seed_ideas_full_compare_20260504_20260504_101225/` | Solutions + deepseek-v4-pro judge scores/verdicts |
| Regrade (best_solution) | `regrade_gemini_20260504_20260504_221221/` | gemini-3-flash judge on each trial's final solution |
| Branch regrade | `regrade_branches_gemini_20260504_20260504_222334/` | gemini-3-flash judge on each individual branch (generate + seed_generate) |

## Shape

70 problems × 6 models × 3 modes = **1260 rows**, long-format JSONL.

- 70 problems = 60 IMO-proofbench + 10 special (5 erdos + 4 first-proof + ramsey-hypergraphs)
- 6 models = gpt-oss-120b, gemma-4-31b-it, gemini-3-flash-preview, deepseek-v4-flash, deepseek-v4-pro, qwen3.6-35b-a3b
- 3 modes = generate (pass@3 best-of-3), full (verify↔revise×2), seed_generate (3 seeded branches)

## Schema (per record)

```jsonc
{
  // -- Problem ----------------------------------------------------------------
  "problem_id":     "PB-Advanced-001",       // unique problem identifier
  "problem_text":   "<full text>",
  "ground_truth":   "<full text>",
  "category":       "Algebra" | "Combinatorics" | "Geometry" | "Number theory" | ...,
  "level":          "IMO-easy" | "IMO-medium" | "IMO-hard" | "Negligible Novelty" | ...,
  "source":         "proofbench" | "combined-benchmarks" | "first-proof-official" | ...,
  "is_special_10":  bool,                    // true for the 10 frontier targets

  // -- Trial id ---------------------------------------------------------------
  "model":          "openrouter/.../...",
  "mode":           "generate" | "full" | "seed_generate",

  // -- Trial run metadata -----------------------------------------------------
  "started_at":     ISO-8601 string | null,
  "completed_at":   ISO-8601 string | null,
  "elapsed_s":      float | null,
  "cost_usd":       float | null,
  "error":          string | absent,         // present only on error/missing trials

  // -- Final solution + both judges' results on it ----------------------------
  "final_solution": "<full text>" | null,    // best_solution from Phase 1 (v4-pro picked)
  "v4pro_score":    int 0..7 | null,
  "v4pro_verdict":  "<full text>" | null,
  "gemini_score":   int 0..7 | null,
  "gemini_verdict": "<full text>" | null,

  // -- Branches (per-branch judge data) ---------------------------------------
  "branches":       [],                      // empty if errored or full-mode branch missing

  // -- Mode-specific extras ---------------------------------------------------
  "mode_extras":    object | null            // e.g. {pass_k:3} | {iterations:2,stopped_early:bool} | {num_ideas:3, ideas:[...], ideate_response:str}
}
```

### `branches` element shapes

**generate** (3 branches per trial, k=0,1,2):
```jsonc
{
  "k": 0|1|2,
  "solution":      "<full text>",            // this branch's solution
  "v4_score":      int 0..7,
  "v4_verdict":    "<full text>",            // v4-pro judge on this branch
  "gemini_score":  int 0..7 | null,          // gemini judge on this branch (from branch regrade)
  "gemini_verdict": "<full text>" | null
}
```

**seed_generate** (3 branches, idea_idx=0,1,2 — one per ideated approach):
```jsonc
{
  "idea_idx": 0|1|2,
  "idea":          {"name": str, "description": str},   // idea this branch was conditioned on
  "solution":      "<full text>",
  "v4_score":      int 0..7,
  "v4_verdict":    "<full text>",
  "gemini_score":  int 0..7 | null,
  "gemini_verdict": "<full text>" | null
}
```

**full** (1 branch only):
```jsonc
{
  "k": 0,
  "initial_solution": "<text>",                          // pre-revision solution
  "final_solution":   "<text>",                          // post-revision solution
  "v4_score":         int 0..7,                          // v4-pro on final
  "v4_verdict":       "<text>",
  "loop_log":         [{"iteration":1,"verdict":"issues_found"|"correct","critique":str,"solution_before":str,"solution_after":str}, ...],
  "stopped_early":    bool                               // whether verifier passed before max iters
  // NOTE: no per-branch gemini fields — full mode wasn't branch-regraded since it has only one branch.
  // The trial-level gemini_score / gemini_verdict in the parent record IS the gemini judgment of this branch.
}
```

## NAs

- **4 errored / missing trials** out of 1260 (0.3%). All deepseek-v4-pro on PB-Basic-028/030
  hitting timeouts or never starting. Their rows have `final_solution=null`, both
  judges' scores/verdicts `null`, and `error` populated.
- **49 branch records lack gemini_score/verdict** in seed_generate mode (errored during
  the branch regrade run). Those branches' `gemini_score` and `gemini_verdict` are null.
- **All 418 full-mode branch records lack per-branch gemini fields** by design — full
  mode has only one branch, and the trial-level `gemini_score` already covers it.

## Coverage summary

|              | rows | with v4 | with gemini | branch records | with branch gemini |
|---|---|---|---|---|---|
| generate     | 420  | 418 | 418 | 1254 | 1254 |
| full         | 420  | 418 | 418 | 418  | 0 (by design — see above) |
| seed_generate| 420  | 420 | 420 | 1260 | 1211 |
| **total**    | 1260 | 1256 | 1256 | 2932 | 2465 |

## Loading

```python
import json
with open("dataset_20260504.jsonl") as f:
    rows = [json.loads(line) for line in f]

# Or with pandas (note: branches column will hold a list of dicts):
import pandas as pd
df = pd.read_json("dataset_20260504.jsonl", lines=True)
```

## Replicating Phase 1's audit table

For each (model, mode), aggregate `gemini_score` (or `v4pro_score`) across all 70 problems.
For pass@1 vs pass@3 etc., consult `branches[].gemini_score` (or `.v4_score`) for
generate-mode rows: `pass@1 = score where k=0`, `pass@3 = max over k=0,1,2`.

## Cautions

- Solution texts can be 5,000–50,000 characters. Verdict texts can be 1,000–10,000.
  File is 191 MB.
- Costs reported are gen-side only (model-under-test costs). Judge costs (v4-pro at
  generation time, gemini-3-flash for regrades) are not in the per-row `cost_usd`.
- All scores 0–7 (IMO rubric). 6/7 = "almost correct"; 7/7 = "complete and rigorous".
  Pass threshold used in Phase 1 reporting: ≥6/7.
