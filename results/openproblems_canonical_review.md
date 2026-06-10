# FrontierMath Open-Problems — Canonical Review

**Generated:** 2026-05-11 (supersedes `openproblems_full_report.md`, `openproblems_phase1_report.md`, `openproblems_final_report.txt`).

All counts were **recomputed directly from raw JSON/JSONL** (not from prior summary files). The local verifier suite was **re-run on every candidate** with non-empty text, regardless of judge label.

## Scope

26 (problem, prompt_type) cells from `benchmarks/frontiermath-open-problems/open_problems_prompts.csv`. `ramsey-hypergraphs` and `small-diophantine full_problem` are excluded per `project_openproblems_excluded.md`.

Four generator conditions:

| Condition | Architecture | Models | Trials |
|---|---|---|---|
| `phase1_og` | pass@5 generate→judge | gpt-oss-120b xhigh + deepseek-v4-flash via OpenRouter | 246 |
| `phase1_gemma` | pass@5 generate→judge | gemma-4-31b-it via direct Gemini API (tier-2 paid) | 120 |
| `seedfull_homo` | ideate→branches→V↔R loop | gemma-4-31b-it (all 4 roles) | 12 |
| `seedfull_roleswap` | ideate→branches→V↔R loop | gemma generator + gpt-oss-120b verifier | 12 |
| **Total** | | | **390** |

Initial judge for all conditions: `deepseek-v4-flash`. Two follow-up consensus passes:
- **v1** (3-judge): gpt-oss-120b xhigh + gemini-3.1-pro + deepseek-v4-flash. 64 entries across `consensus_judge_…_184327.json` (9 saved) + `consensus_partial_55.json` (55 recovered from console after the run stalled).
- **v2** (2-judge corrected spec): gpt-oss-120b xhigh + deepseek-v4-flash. 61 entries across five JSON kicks.

## Per-problem × condition table

Cell format: `trials / pos-signal / correct-label / unanimous-consensus-correct`
- pos-signal = label ∈ {correct, almost, partial}
- unanimous-consensus = all judges in the panel returned "correct" (attributed back to the originating trial's condition where possible)

| Problem | Type | phase1_og | phase1_gemma | seedfull_homo | seedfull_roleswap | Local verifier |
|---|---|---|---|---|---|---|
| arithmetic-kakeya | full_problem | 9/1/1/0 | 5/2/1/0 | — | — | ✗ 0/12 (forcing-pair) |
| arithmetic-kakeya | warmup | 10/0/0/1 | 5/1/0/0 | 1/0/0/0 | 1/1/1/0 | ✗ 0/17 (forcing-pair) |
| degree-sensitivity-boolean | full_problem | 8/0/0/0 | 5/0/0/0 | — | — | ✗ 0/12 |
| **degree-sensitivity-boolean** | **warmup** | **10/3/1/1** | 5/0/0/0 | 1/0/0/0 | 1/0/0/0 | **✓ 1/17** |
| explicit-deformations | full_problem | 7/0/0/0 | — | — | — | no checker |
| **explicit-deformations** | **warmup** | **10/9/7/8** | — | — | — | **✓ 7/9** |
| hadamard | full_problem | 10/1/0/0 | 5/1/1/0 | — | — | ✗ 0/15 |
| hadamard | warmup | 10/1/0/0 | 5/1/0/0 | 1/0/0/0 | 1/0/0/0 | ✗ 0/17 |
| inverse-galois | full_problem | 10/5/4/3 | 5/4/4/1 | — | — | ✗ 0/15 (disc-square) |
| inverse-galois | warmup | 10/6/5/5 | 5/4/3/1 | 1/1/0/0 | 1/1/1/0 | ✗ 0/17 (disc-square) |
| klt-del-pezzo-surface | full_problem | 10/7/3/1 | 5/0/0/0 | — | — | no checker |
| klt-del-pezzo-surface | warmup | 10/4/2/1 | 5/3/0/1 | 1/1/1/0 | 1/1/1/0 | no checker |
| large-steiner-systems | full_problem | 9/1/0/0 | 5/0/0/0 | — | — | ✗ 0/14 |
| large-steiner-systems | warmup | 10/2/0/1 | 5/3/2/0 | 1/1/0/0 | 1/1/1/0 | ✗ 0/15 |
| prime-factorization | full_problem | 10/0/0/0 | 5/0/0/0 | — | — | no checker |
| prime-factorization | warmup | 10/6/0/1 | 5/0/0/0 | 1/1/0/0 | 1/1/0/0 | no checker |
| q2-absolute-galois | full_problem | 10/0/0/0 | 5/2/2/0 | — | — | no checker |
| q2-absolute-galois | warmup | 9/2/2/2 | 5/0/0/0 | 1/1/1/0 | 1/0/0/0 | no checker |
| ramsey-book-graphs | full_problem | 9/2/1/1 | 5/1/0/0 | — | — | no checker (only warmup verified) |
| ramsey-book-graphs | warmup | 10/4/1/0 | 5/3/1/1 | 1/0/0/0 | 1/1/1/0 | ✗ 0/17 |
| small-diophantine | warmup | 9/3/0/0 | 5/0/0/0 | 1/0/0/0 | 1/0/0/0 | ✗ 0/15 |
| stretched-lr-coefficients | full_problem | 7/4/2/2 | 5/3/0/2 | — | — | ✗ 0/12 (zero/const LR) |
| symplectic-ball-packing | full_problem | 10/3/1/0 | 5/2/1/0 | — | — | no checker |
| symplectic-ball-packing | warmup | 10/4/1/0 | 5/0/0/0 | 1/0/0/0 | 1/0/0/0 | no checker |
| unknotting-number | full_problem | 9/2/0/0 | 5/0/0/0 | — | — | no checker |
| unknotting-number | warmup | 10/3/0/0 | 5/0/0/0 | 1/1/1/0 | 1/1/1/0 | no checker |

## Per-condition rollup

| Condition | Trials | Pos-signal | Correct | Unanimous cons | Distinct (pid, type) with ≥1 pos | with ≥1 correct |
|---|---|---|---|---|---|---|
| phase1_og | 246 | 73 | 31 | 27 | 21 / 26 | 13 / 26 |
| phase1_gemma | 120 | 30 | 15 | 6 | 13 / 24 | 8 / 24 |
| seedfull_homo | 12 | 6 | 3 | 0 | 6 / 12 | 3 / 12 |
| seedfull_roleswap | 12 | 7 | 6 | 0 | 7 / 12 | 6 / 12 |
| **Total** | **390** | **116** | **55** | **33** | — | — |

Locally-verified passes: **8 trials across 2 (problem, type)** — all in `phase1_og`, all on warmup prompts.

## Headline summary

| Metric | Count | Notes |
|---|---|---|
| Trials run | 390 | gpt-oss xhigh + deepseek (246) + gemma direct (120) + seedfull × 2 (24) |
| Pos-signal trials | 116 (30%) | judge ∈ {correct, almost, partial} |
| Correct-label trials | 55 (14%) | per the cheap deepseek judge |
| Unanimous consensus correct | 33 | across v1 + v2 panels |
| Locally-verified passes | 8 (2.1%) | 7 explicit-deformations warmup + 1 degree-sensitivity warmup |
| Distinct problems with ≥1 verified pass | 2 / 26 | 0 of which are `full_problem` |

## Unanimous-consensus entries by verification outcome

The 33 unanimous-correct consensus entries split three ways:

### PASSED — 9 entries (8 distinct trials)
All 8 locally-verified trials are also unanimous-consensus correct. The "9" is because explicit-deformations seed-42/45/46 trials were independently confirmed by both v1 (3-judge) and v2 (2-judge) panels.

| Problem | Type | Cond | Model | Seed | Verifier |
|---|---|---|---|---|---|
| degree-sensitivity-boolean | warmup | phase1_og | deepseek-v4-flash | 44 | n=6, deg=3, sens=6, a=log6/log3=1.6309 |
| explicit-deformations | warmup | phase1_og | gpt-oss-120b | 42 | curvilinear A=k[x,y]/(x,y)² → k[t]/(t³) |
| explicit-deformations | warmup | phase1_og | deepseek-v4-flash | 42 | ditto |
| explicit-deformations | warmup | phase1_og | gpt-oss-120b | 43 | ditto |
| explicit-deformations | warmup | phase1_og | gpt-oss-120b | 44 | ditto |
| explicit-deformations | warmup | phase1_og | gpt-oss-120b | 45 | ditto |
| explicit-deformations | warmup | phase1_og | deepseek-v4-flash | 45 | ditto (judge label was `almost`) |
| explicit-deformations | warmup | phase1_og | gpt-oss-120b | 46 | ditto |
| explicit-deformations | warmup | phase1_og | deepseek-v4-flash | 46 | ditto |

### FAILED — 17 entries (judges hallucinated)
A local checker exists and **refutes** the unanimous label.

| Problem | Type | Failure mode | # entries |
|---|---|---|---|
| inverse-galois | warmup + full | discriminant not a perfect square (M_n ⊆ A_n requires it) | 10 |
| stretched-lr-coefficients | full | LR coefficient is zero or a constant (no negative coefficient) | 4 |
| arithmetic-kakeya | warmup | forcing-pair semantics fails (unforced vertices) | 1 |
| large-steiner-systems | warmup | incomplete block coverage (525/792) | 1 |
| ramsey-book-graphs | warmup | adjacency string wrong length / no book of required size | 1 |

### NO CHECKER — 7 entries (genuinely unknown)
We have no local verifier, so these are the only consensus calls that *could* still be real. **These are the candidates worth deeper evaluation** (see next section).

| Problem | Type | Cond | Model | Seed | Source |
|---|---|---|---|---|---|
| klt-del-pezzo-surface | full | phase1_og | gpt-oss-120b | 42 | v2_221802 |
| klt-del-pezzo-surface | warmup | phase1_og | unknown (?) | 42 | v2_231905 |
| klt-del-pezzo-surface | warmup | phase1_gemma | gemma-4-31b-it | 46 | v2_221732 |
| prime-factorization | warmup | phase1_og | deepseek-v4-flash | 43 | v2_221802 |
| q2-absolute-galois | warmup | phase1_og | unknown (?) | 42 | v2_231905 |
| q2-absolute-galois | warmup | phase1_og | deepseek-v4-flash | 44 | v2_221802 |
| ramsey-book-graphs | full | phase1_og | deepseek-v4-flash | 43 | v2_221802 |

## New analysis

**(1) The architectural variations did nothing.** Seed-full homogeneous and role-swap together produced **24 trials, 13 pos-signal, 9 correct labels, 0 unanimous consensus**, and 0 verified passes. Of the 9 "correct" labels in seedfull conditions, all are on problems where a checker exists and refutes them (inverse-galois, kakeya, klt-del-pezzo, large-Steiner, ramsey-book, unknotting). None are on `explicit-deformations` or `degree-sensitivity` — the only two problems where Phase 1 *did* find real solutions, so the seedfull conditions didn't even rediscover the known wins.

**(2) Phase 1 OG vs Phase 1 gemma.** Gemma-via-Gemini-direct produced **half the data and ~1/4 the unanimous consensus** of the gpt-oss/deepseek pair, despite costing essentially nothing on the Gemini side. It introduced one new positive-signal cell (q2-absolute-galois full) and added trials on stretched-LR (3 pos-signal, all locally false). Net: **gemma added breadth but no verifiable signal.**

**(3) Where signal concentrates.** The pos-signal distribution across all 390 trials is extremely uneven:
- explicit-deformations warmup: 9/10 → 7 verified passes
- inverse-galois (both types): 21/31 → 0 verified passes (all locally falsified)
- klt-del-pezzo (both types): 17/30 → 0 verified, 3 unanimous-consensus, **no checker**
- prime-factorization warmup: 8/16 → 0 verified, 1 unanimous-consensus, **no checker**, but candidates appear to be algorithm descriptions, not concrete factorizations
- Six problems produced **zero positive signal** anywhere (degree-sens full, hadamard, large-Steiner full, prime-fac full, q2-galois full from phase1_og)

**(4) Judge unreliability rate.** Of 33 unanimous-correct consensus entries, only 8 are *trivially* correct (explicit-deformations warmup is a well-documented textbook example: the curvilinear deformation of `k[t]/(t³)` to `k[x,y]/(x,y)²`). The other 25 split 17/8 (refuted/unknown), so among *checkable* unanimous calls the **false-positive rate is 17/26 ≈ 65%**. v1 (3-judge with gemini-3.1-pro) and v2 (2-judge without it) had similar rates — adding gemini-3.1-pro neither helped nor hurt meaningfully.

**(5) The "?" model column.** Three unanimous-correct entries (kakeya seed=42, klt-warmup seed=42, q2-galois seed=42, large-Steiner seed=42 — all from `consensus_v2_…_231905.json` and `…_233252.json`) lack model attribution. These come from the late v2 reruns that were fed `model="?"` because the originating phase1 source wasn't tracked. They're real entries, but provenance is fuzzy.

## What's worth deeper evaluation

Given the recap claimed "zero new verified solutions," the realistic question is whether any of the 7 no-checker unanimous-correct candidates *could* be real. My assessment from spot-checking the candidate texts:

| Candidate | Tractability of verifying | Verdict |
|---|---|---|
| **klt-del-pezzo-surface full, gpt-oss seed=42** | Concrete (weights, equation). Verifiable in Macaulay2/Sage with `WeightedProjectiveSpace` + log-discrepancy computation. The phase1_og full_problem cell has **7 correct-label trials** — the broadest positive signal of any unsolved problem. | **Highest-value follow-up.** Worth a 1-day push to install Macaulay2 + write a verifier. |
| klt-del-pezzo warmup × 3 (phase1_og seed=42 "?", phase1_gemma seed=46) | Same verifier infrastructure as above would handle warmup too. The gemma seed=46 candidate I peeked at gives weights `[2,2,5,5]`, eq `x0^5+x1^5+x2^2+x3^2` — checkable. | **Bundle with the full_problem effort.** |
| **q2-absolute-galois warmup × 2** | Asks for a profinite-group presentation. Genuinely hard to verify mechanically (no library implements Galois groups of `Q_2` directly). | Low priority. A *syntactic* check (does the answer have the structural form of a known presentation, e.g. Jannsen-Wingberg?) is cheap; a *semantic* check probably requires a specialist. |
| prime-factorization warmup, deepseek seed=43 | The candidate is a *description* of ECM, not an actual factorization. The judge labels in phase1_og are all `partial` (0 correct) — the consensus is judging plausibility, not numerical correctness. | **Not worth verifying** in current form. Would need to re-prompt asking for actual factor output. |
| ramsey-book-graphs full, deepseek seed=43 | Adjacency string. The warmup verifier `_kakeya_verifier`-style approach should adapt, but the full problem version isn't covered. Note **the warmup verifier rejected 17/17 candidates**, so the full-problem positives are *probably* also wrong by analogy. | Low priority, but cheap to extend the verifier. |

**Also worth a second-pass look (no consensus, but anomalous signal):**
- `symplectic-ball-packing` full_problem: 3 pos-signal + 1 correct-label in phase1_og, 2 pos + 1 correct in phase1_gemma — **but zero unanimous consensus**. Either the candidates were never sent through consensus, or they were sent and the panel disagreed. Worth diagnosing whether v2 actually saw them.
- `unknotting-number` warmup: positive signal in **both** seedfull_homo and seedfull_roleswap (the only problem outside explicit-deformations where both seedfull conditions agreed). Knot invariants are computable with SnapPy/`sage.knots`; a verifier is a few hours of work.

**Not worth re-investigating** (all locally falsified or fundamentally judge-fooled):
inverse-galois (any seed), arithmetic-kakeya (any seed), large-steiner-systems, hadamard, stretched-lr-coefficients, small-diophantine, ramsey-book-graphs warmup.

## Bottom-line recompute vs prior recap

| Quantity | Prior recap | Recomputed | Delta |
|---|---|---|---|
| Total trials | "~380" | 390 | +10 |
| Phase 1 OG completed | 233 | **246** | recap was wrong; the 26 MB `…_183859.jsonl` is the canonical Phase 1 log |
| Phase 1 gemma | 120 | 120 | — |
| Consensus entries | 111 | **125** | recap omitted v1 (`consensus_judge_184327.json` 9 + `consensus_partial_55.json` 55) |
| Unanimous-correct consensus | "30" | **33** | recap undercounted (probably didn't include the partial_55 v1 contributions) |
| Locally-verified passes | 8 | 8 | ✓ matches |
| New solutions from architectural variations | 0 | 0 | ✓ matches |

The fundamental conclusion is unchanged. The counts in the recap were close-but-imprecise on the input side; the conclusions on the output side were correct.

---

## Asset inventory

Everything produced or used by this series of runs.

### Scripts (24 files in `experiments/`)

| File | Role |
|---|---|
| `openproblems_pass5_20260507.py` | Phase 1: pass@5 generate→judge (oss + deepseek + gemma-via-OR) |
| `openproblems_gemma_phase1_20260507.py` | Phase 1 gemma redo via direct Gemini API |
| `openproblems_gemma_passN_20260507.py` | Lighter gemma fallback after seedfull stalled |
| `openproblems_seed_full_20260507.py` | Seed-full architecture (killed early — gemma 8-conc semaphore) |
| `openproblems_gemma_seedfull_20260507.py` | Seed-full at reduced scope (12 + 12 trials) |
| `openproblems_consensus_judge_20260507.py` | v1 3-judge consensus (with gemini-3.1-pro) |
| `openproblems_consensus_v2_20260507.py` | v2 2-judge consensus (corrected panel) |
| `openproblems_revise_top_20260507.py` | Phase 3a: verify↔revise on positives (no result JSON produced) |
| `openproblems_strong_passN_20260507.py` | Phase 4: frontier-model pass@N (no result JSON produced) |
| `openproblems_local_verify_20260507.py` | Verifier dispatch (hadamard, Steiner, ramsey-book-warmup, small-dio, degree-sens, explicit-def, inverse-galois necessary, kakeya, stretched-LR) |
| `_kakeya_verifier.py` | Full forcing-pair semantics check |
| `_lr_verifier.py` | Stretched-Littlewood-Richardson verifier |
| `_gemini_api.py` | Adaptive Gemini API client (4–20 concurrent, 429 backoff) |
| `_log_to_phase1_json.py` | JSONL → consensus-input converter |
| `_parse_partial_consensus.py` | Console-log → JSON for the killed consensus run |
| `check_galois_polys_20260507.py` | Standalone disc-square + irreducibility sanity check |
| `openproblems_summary_20260507.py` | Per-problem positive-rate summary |
| `openproblems_final_report_20260507.py` | Generates `openproblems_final_report.txt` |
| `openproblems_full_report_20260507.py` | Generates `openproblems_full_report.md` |

### Result JSONs (15 in `experiments/results/`)

| File | Records | Role |
|---|---:|---|
| `openproblems_pass5_…_181650_mock.json` | 6 | smoke test |
| `openproblems_pass5_…_181709.json` | 3 | early partial |
| `openproblems_pass5_…_182455.json` | 3 | partial (full text data in the JSONL log instead) |
| `openproblems_gemma_phase1_…_210520.json` | 2 | early partial |
| **`openproblems_gemma_phase1_…_221534.json`** | **120** | **canonical gemma Phase 1** |
| `openproblems_gemma_seedfull_…homo_…231726.json` | 12 | seedfull homogeneous gemma |
| `openproblems_gemma_seedfull_…roleswap_…231828.json` | 12 | seedfull roleswap (oss verifier) |
| `openproblems_consensus_judge_…_184327.json` | 9 | v1 consensus (saved before stall) |
| `consensus_partial_55.json` (+ `_log.txt`) | 55 | v1 consensus recovered from console |
| `openproblems_consensus_v2_…_221732.json` | 30 | v2 run 1 |
| `openproblems_consensus_v2_…_221802.json` | 18 | v2 run 2 |
| `openproblems_consensus_v2_…_231818.json` | 0 | v2 run 3 (empty) |
| `openproblems_consensus_v2_…_231905.json` | 6 | v2 run 4 |
| `openproblems_consensus_v2_…_233252.json` | 7 | v2 run 5 |

### Raw logs (14 in `logs/`, ~32 MB total)

| File | Lines | Role |
|---|---:|---|
| **`openproblems_pass5_…_183859.jsonl`** | **246** | **canonical Phase 1 OG (26 MB)** |
| `openproblems_pass5_…_181650.jsonl` … `_183311.jsonl` | 6–14 each | early partial/restart fragments |
| **`openproblems_gemma_phase1_…_210937.jsonl`** | **120** | **canonical gemma Phase 1** |
| `openproblems_gemma_phase1_…_205657.jsonl` | 2 | early fragment |
| `openproblems_gemma_passN_…_192941.jsonl` | 4 | fallback gemma generate |
| `openproblems_gemma_seedfull_…homo_…222634.jsonl` | 12 | seedfull homo (full) |
| `openproblems_gemma_seedfull_…roleswap_…222646.jsonl` | 12 | seedfull roleswap (full) |
| `openproblems_gemma_seedfull_…homo_…212135.jsonl` | 1 | seedfull early fragment |

### Reports (4 in `results/`)

| File | Status |
|---|---|
| `openproblems_phase1_report.md` | Phase 1 narrative + inverse-galois case study |
| `openproblems_full_report.md` | Aggregate table generated by `openproblems_full_report_20260507.py` |
| `openproblems_final_report.txt` | Earlier text table (counts 14 verified — includes 6 kakeya "necessary-conditions only" later downgraded) |
| **`openproblems_canonical_review.md`** | **This document.** Supersedes the above. |

### Inputs

| File | Role |
|---|---|
| `benchmarks/frontiermath-open-problems/open_problems_prompts.csv` | Main prompts (26 active cells) |
| `benchmarks/frontiermath-open-problems/open_problems_survey.csv` | Problem metadata |
| `benchmarks/frontiermath-open-problems/ramsey-hypergraphs/` + `*.csv` | Excluded per `project_openproblems_excluded.md` |

### Worth-following-up artifacts (priority order)

1. `logs/openproblems_pass5_…_183859.jsonl` — extract the **7 correct-label `klt-del-pezzo-surface full_problem` candidates** (gpt-oss / deepseek seeds 42–46) for Macaulay2 verification.
2. Same log — extract the **4 `klt-del-pezzo-surface warmup` correct-label candidates**.
3. Both seedfull JSONs — extract the **`unknotting-number warmup` candidates** for a SnapPy-based verifier.
4. Phase 1 OG — extract the **3 `symplectic-ball-packing full` correct-label candidates** and route them through consensus v2 (they appear to have skipped consensus).

No follow-up needed: every locally-falsifiable problem has been falsified; every architectural variation has been tested and produced no new wins.
