# `multi-seed-cheap/` — run-to-run variance of the cheap judge tier

**Directory guide + data dictionary for folding these results into the paper.**
Date of canonical run: 2026-05-26 (run id `20260526_021655`).

---

## TL;DR — what this directory establishes

We measured the **run-to-run (replicate) variance** of the three cheap judges
(deepseek-v4-flash, gpt-oss-120b @ xhigh, gemma-4-31b-it @ high) on the fixed
**200-instance validation sample**, over the original run + 3 fresh **no-seed** replicates.

**The result to fold in (canonical, clean, no caveats needed):**

| System | orig | rep1 | rep2 | rep3 | **mean** | **std** |
|---|---|---|---|---|---|---|
| DeepSeek-V4-Flash | 0.860 | 0.861 | 0.898 | 0.905 | **0.881** | 0.024 |
| GPT-OSS-120B @ xhigh | 0.875 | 0.863 | 0.829 | 0.835 | 0.851 | 0.022 |
| Gemma-4-31B @ high | 0.795 | 0.820 | 0.810 | 0.814 | 0.810 | **0.011** |
| Majority vote (trio) | 0.855 | 0.875 | 0.890 | 0.875 | 0.874 | 0.014 |
| **All-three-pass** (unanimous) | 0.895 | 0.895 | 0.903 | 0.915 | **0.902** | **0.009** |

Metric = pass-agreement (≥6) vs human. `orig` = the original (no-seed) validation run
from `../consensus_analysis.csv`; `rep1–3` = fresh no-seed replicates.

**Claims this supports (use these exact framings):**
1. **All-three-pass is the best configuration on this sample: highest mean (0.902) *and* lowest run-to-run variance (0.009).**
2. **Majority voting stabilizes against the volatile multi-provider single judges** (std 0.014 vs gpt-oss/deepseek 0.022–0.024).
3. **DeepSeek is the most reliable single judge (mean 0.881); GPT-OSS is mid (0.851)** — consistent with the full-1000 result, and GPT-OSS's headline 0.875 is the *top* of its 0.83–0.88 range, not a stable value.

**Do NOT claim** "consensus halves single-judge variance" — Gemma alone (single-provider,
std 0.011) is *more* stable than majority vote. The accurate statement is #1 and #2 above.

---

## Root-cause context (needed for Methods/Limitations)

GPT-OSS's run-to-run swing is driven by **OpenRouter's provider lottery**, not by an
inference seed or model drift. `openai/gpt-oss-120b` is served by a large, shifting
third-party provider pool at heterogeneous quantizations (this run: ~80% "Ambient";
an earlier run: DekaLLM/DeepInfra/Novita with no Ambient). DeepSeek is also multi-provider
(similar variance). **Gemma is ~93% single-provider (Chutes) → lowest variance.** The
frontier baselines (Opus, Gemini) are first-party single-provider and stable (Opus drift
screen: 0/20 pass-fail flips, 17/20 exact-score, all Anthropic-served).

→ **Methods caveat to add:** cheap open-weight judges are served by multiple OpenRouter
providers at varying quantization; for a reproducible number, pin a provider
(`extra_body={"provider":{"order":[...],"allow_fallbacks":false}}`) and log the
response `provider` field. Per-judge provider mixes are in `summary_noseed_reps_*.json → provider_mix`.

---

## Directory map

| File | What it is | Use it for |
|---|---|---|
| **`summary_noseed_reps_20260526_021655.json`** | **Canonical result.** Per-judge & per-consensus pass-agree per replicate, mean±std, provider mix. | The variance table above; the paper. |
| `judge_<model>_<reasoning>_rep{1,2,3}_20260526_021655.json` | Per-(judge, replicate) full records: per-problem score, provider, reasoning_tokens, cost, finish_reason + `stats`. | Recompute any metric (F1, confusion, per-problem flips); provider analysis. |
| `multi_seed_cheap_judges.py` | The runner (no seed sent; `--reps N`; provider capture). Self-contained, publishable. | Reproduce / add more replicates. |
| `gptoss_noseed_provider_check.py` / `_results.json` | Diagnostic: gpt-oss no-seed on all 200 + provider capture (the run that exposed the provider lottery). 200 recs. | Provider-lottery evidence; an extra gpt-oss no-seed point (0.852). |
| `opus_drift_check.py` / `_results.json` | Diagnostic: Opus 4.7 re-run on 20 problems vs original (drift screen). 20 recs. | Evidence the frontier anchor is stable (0/20 flips). |
| `archive/` | **Confounded seeded runs — DO NOT USE.** | See warning below. |

### ⚠️ `archive/` — do not fold into the paper
`archive/summary_seed{1,2,3}_*.json` and `judge_*_seed{1,2,3}_*.json` are from an earlier
study that passed an inference `seed` param. We found this confounds the cheap-tier numbers
(it interacts with provider routing) and **inflates** the apparent single-judge variance.
They are kept only for provenance. **Use the no-seed `*_rep*` / `summary_noseed_reps_*` files.**

---

## Data dictionary

### `summary_noseed_reps_*.json`
| Key | Meaning |
|---|---|
| `experiment`, `date`, `n` (200), `reps` (3), `seeded` (false) | run metadata |
| `rep_labels` | `["orig","rep1","rep2","rep3"]` (column order) |
| `per_judge_pass_agree` | `{judge_id: {label: pass_agree}}` |
| `per_consensus_pass_agree` | `{"majority_vote"/"all_three_pass": {label: pass_agree}}` |
| `mean_std` | `{system: [mean, std]}` over all labels — **the table above** |
| `provider_mix` | `{judge_id: {provider: call_count}}` aggregated across reps |
| `wall_clock_s`, `total_cost_usd` | $4.54 total |

### `judge_<...>_rep{k}_*.json`
| Key | Meaning |
|---|---|
| `judge_id`, `model`, `reasoning`, `rep`, `seeded` (false) | config |
| `stats` | `n`, `n_valid`, `pass_agree`, `precision`, `recall`, `f1`, `tp/fp/tn/fn` |
| `results[]` | per problem: `grading_id`, `human_points` (0–7), `score` ({0,1,6,7} or null), `provider`, `reasoning_tokens`, `cost`, `finish_reason` |

Pass/fail uses raw human score ≥6. `score=null` = call failed/unparsed (rare; <2%).

### `gptoss_noseed_provider_check_results.json` (200) / `opus_drift_check_results.json` (20)
List of per-problem records. Keys: `grading_id`, `human_points`(/`human`), `score`,
`provider`, `served_model`, `cost`, `finish_reason` (+ `reasoning_tokens` for gpt-oss).

---

## How to fold into the paper (`../draft/working_draft_v2.md`)

1. **§6 / a "Robustness" subsection:** add the variance table above (mean±std over 4 runs).
   Lead claim: *all-three-pass is both the most accurate and the most stable configuration;
   majority voting damps the volatility of the multi-provider single judges.*
2. **Methods:** add the provider-lottery caveat (above) and note replicates used **no seed**
   (natural sampling + provider routing). Update the existing "within-model variance is
   unclear" limitation → now quantified (this study).
3. **Frontier stability:** cite the Opus drift screen (0/20 flips, single-provider) to
   support that the frontier anchors are stable — i.e. the variance issue is a cheap-tier
   (open, multi-provider) phenomenon, which does not threaten the headline comparison.
4. **Keep the precise wording** — do not overclaim consensus variance reduction (see TL;DR).

---

## Reproduce / extend

```bash
# from this directory; needs OPENROUTER_API_KEY in repo .env
python multi_seed_cheap_judges.py --reps 3            # no seed, provider captured
python multi_seed_cheap_judges.py --reps 3 --mock     # offline sample-load check
```
Cost ≈ $1.5/replicate for the cheap tier (≈ $4.5 for 3). Full log of the investigation
(incl. the two corrected hypotheses: drift → seed → provider lottery) is in
`../../agent_log.md` (search "no-seed replicate variance" / "provider lottery").
