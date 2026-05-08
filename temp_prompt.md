Context: We need a pass@2 baseline for three (model, reasoning) cells to enable like-for-like comparison against the `full` (generator-verifier-revisor) pipeline mode evaluated on PB+R26. The `full` mode is roughly equivalent in generation calls to pass@2 (1 initial gen + verify-revise iterations that early-stop), so pass@2 is the right token-matched baseline.

The three cells:
  - gemma-4-31b-it × default reasoning
  - gpt-oss-120b × default reasoning
  - deepseek-v4-flash × default reasoning

All three on the canonical 70-problem PB+R26 set (60 IMO-ProofBench + 10 R26). Judge: deepseek-v4-flash (canonical), at minimum; v4-pro grades welcome but not required.

Approach:
  1. First check `results/scaling_20260506/trials.jsonl` and the underlying scaling experiments. The scaling buckets store M=7 (or M=9) branches per (model, problem) cell and enumerate pass@n via C(M, n) subsets. If the existing branches cover all 70 problems for these three cells, just re-aggregate with n=2 added — no new model calls needed. The current headline curves only enumerate n ∈ {1, 3, 5, 7}; pass@2 is missing.
  2. If existing branches don't cover all 70 problems for any cell (e.g. the default-reasoning gemma/oss data is on the 30-problem subset), generate enough additional independent samples to bring coverage to 70 × M≥2 per cell, then enumerate.
  3. Append the new pass@2 rows to `results/scaling_20260506/trials.csv`, `trials.jsonl`, and `summary.csv` following the existing schema in `data_dictionary.md`. Update `report.md` headline scaling-curve table to include the n=2 column.

Smoke-test with --mock first. Then run real. Log to agent_log.md per CLAUDE.md convention.
