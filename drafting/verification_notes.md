# Verification Notes (Stage 0)

Recomputed from `results/architecture_20260506/trials.jsonl` and `results/answerbench_calibration_20260506/summary.csv`. No new API calls.

## 1. Per-cell judge means — 6 model × 4 mode grid

(architecture trials.jsonl, n=2,098 rows. Defaults to `phase1` cells unless model+mode+reasoning indicates otherwise. v4-flash is canonical; v4-pro and gemini are audit. Phase 1 default-reasoning cells have all three judges; reasoning=max cells have v4-flash only.)

### 1a. Default reasoning, v4-flash judge

| Model | generate | seed_generate | full | seed_full |
|---|---:|---:|---:|---:|
| deepseek-v4-flash | 3.22 | 3.41 | 3.38 | 3.49 (phase 3) |
| deepseek-v4-pro | 3.53 | 3.41 | 3.85 | — |
| gemini-3-flash-preview | 1.83 | 1.54 | 1.59 | — |
| gemma-4-31b-it | 1.49 | 1.49 | 1.39 | 1.71 (phase 2) |
| gpt-oss-120b | 1.34 | 1.09 | 1.58 | 1.41 (phase 2) |
| qwen3.6-35b-a3b | 2.09 | 2.10 | 1.62 | — |

### 1b. Reasoning=max (cheap models only, v4-flash judge)

| Model | generate | seed_generate | full | seed_full |
|---|---:|---:|---:|---:|
| gemma-4-31b-it | 2.74 | 2.74 | 2.17 | **3.31** |
| gpt-oss-120b | 2.30 | 2.54 | 2.43 | **3.00** |

### 1c. Same cells, gemini judge (phase 1 only — no reasoning=max coverage)

| Model | generate | seed_generate | full | seed_full |
|---|---:|---:|---:|---:|
| deepseek-v4-flash | 4.81 | 5.01 | 4.63 | **5.83** (phase 3) |
| deepseek-v4-pro | 5.56 | 5.30 | 5.35 | — |
| gemini-3-flash-preview | 2.93 | 3.39 | 3.76 | — |
| gemma-4-31b-it | 3.21 | 2.99 | 3.51 | **4.26** (phase 2) |
| gpt-oss-120b | 2.59 | 2.40 | 3.10 | **3.99** (phase 2) |
| qwen3.6-35b-a3b | 3.60 | 3.21 | 3.74 | — |

### 1d. Same cells, v4-pro judge

| Model | generate | seed_generate | full | seed_full |
|---|---:|---:|---:|---:|
| deepseek-v4-flash | 3.39 | 3.30 | 3.09 | 3.19 (phase 3) |
| deepseek-v4-pro | 3.38 | 3.36 | 3.66 | — |
| gemini-3-flash-preview | 1.83 | 1.87 | 1.29 | — |
| gemma-4-31b-it | 1.83 | 1.53 | 1.17 | 1.67 (phase 2) |
| gpt-oss-120b | 1.33 | 1.27 | 1.39 | 1.37 (phase 2) |
| qwen3.6-35b-a3b | 2.17 | 2.06 | 1.44 | — |

## 2. Architecture deltas (full vs generate, default reasoning)

| Model | v4flash Δ | v4pro Δ | gemini Δ |
|---|---:|---:|---:|
| deepseek-v4-flash | +0.16 | -0.30 | -0.18 |
| deepseek-v4-pro | +0.32 | +0.28 | -0.21 |
| gemini-3-flash-preview | -0.24 | -0.54 | **+0.83** |
| gemma-4-31b-it | -0.10 | -0.66 | **+0.30** |
| gpt-oss-120b | +0.24 | +0.06 | **+0.51** |
| qwen3.6-35b-a3b | -0.47 | -0.73 | **+0.14** |

**Finding.** Pipeline (full vs generate) gives **mixed-but-mostly-flat** results under v4-flash and v4-pro across all six models. Under Gemini, four of six models (the cheap ones) show clean +0.14 to +0.83 lift. The two strong DeepSeek models show no Gemini lift either.

## 3. seed_full lift over generate (where data exists)

| Model | v4flash Δ | v4pro Δ | gemini Δ | reasoning |
|---|---:|---:|---:|---|
| deepseek-v4-flash (phase 3) | +0.27 | -0.20 | **+1.02** | default |
| gemma-4-31b-it (phase 2) | +0.22 | -0.16 | **+1.05** | default |
| gpt-oss-120b (phase 2) | +0.07 | +0.04 | **+1.40** | default |
| gemma-4-31b-it (phase1_reasoning) | **+0.57** | n/a | n/a | max |
| gpt-oss-120b (phase1_reasoning) | **+0.70** | n/a | n/a | max |

**Finding.** Two distinct stories:

- **At default reasoning**, seed_full gives +0.07 to +0.27 v4-flash lift, ±0 v4-pro, but +1.0 to +1.4 Gemini lift. This is the Gemini-only mirage we feared.
- **At reasoning=max** (only on cheap models), seed_full gives a real +0.57 / +0.70 v4-flash lift. We have no v4-pro / Gemini scores to cross-validate, but the v4-flash lift is large enough to be real signal.

## 4. Pass-flip rates on 1,440 triple-judge cells

| Pair | Pass-rate agreement |
|---|---:|
| v4flash vs v4pro | **95.5%** (1375/1440) |
| v4flash vs gemini | 73.7% (1061/1440) |
| v4pro vs gemini | 72.9% (1050/1440) |

| Directional flip | Count | Share |
|---|---:|---:|
| v4flash pass, v4pro fail | 41 | 2.8% |
| v4flash fail, v4pro pass | 24 | 1.7% |
| v4flash pass, gemini fail | 16 | 1.1% |
| **v4flash fail, gemini pass** | **363** | **25.2%** |
| v4pro pass, gemini fail | 13 | 0.9% |
| **v4pro fail, gemini pass** | **377** | **26.2%** |

**Finding.** v4-flash and v4-pro are functionally interchangeable as binary pass/fail judges (95.5% agreement). Gemini is **wildly more lenient**: it calls "pass" on 25–26% of cases that the strict judges call "fail." The reverse error (Gemini fails what others pass) is ~1%. This is one-sided drift, not noise — Gemini systematically grants partial credit at the ≥6 threshold.

## 5. Reasoning effect — sanity check on AnswerBench-50

| Model | default-reasoning acc | high-reasoning acc | Δ |
|---|---:|---:|---:|
| gpt-oss-120b | 0.58 | 0.74 (xhigh) | +16 pp |
| gemini-3-flash | 0.74 | 0.90 (xhigh, synth)* | +16 pp |
| gemma-4-31b-it | 0.68 | 0.63 (xhigh) | -5 pp |
| deepseek-v4-flash | 0.88 (default = reasoning on) | 0.50 (forced off) | -38 pp |

*Synthesized: 37 default-effort + 13 real xhigh retests. Caveat noted in source.

**Finding.** Reasoning swing = 16–38 pp on AnswerBench-50 single-shot. **This is 3–5× the largest architecture effect we measured anywhere.** Gemma is the lone counter-example (its "reasoning on" mode hurts; flagged in source as not reasoning-trained).

## 6. seed_full coverage asymmetry

`seed_full` is tested on **3 models at default reasoning** (gemma + gpt-oss in phase 2; deepseek-v4-flash in phase 3) and **2 models at reasoning=max** (gemma + gpt-oss). Phase 1's six-model grid does **not** include seed_full — those rows do not exist. We cannot directly compare seed_full against generate for `deepseek-v4-pro`, `gemini-3-flash-preview`, or `qwen3.6-35b-a3b` at any reasoning setting. Any aggregate seed_full claim is over a non-representative subset; report this.

## 7. Implications for the paper

1. **Architecture effects are small to modest under strict judges, large under Gemini.** Spine of the paper holds, but the headline must be "judge-conditioned."
2. **The clearest architecture win is `seed_full` at reasoning=max on cheap models** (+0.57 / +0.70 v4-flash). This is also where the literature (Aletheia, Huang–Yang) reports their wins, so plausible.
3. **Reasoning is the single biggest knob in the dataset.** It deserves prominent placement (not headline, but stronger than tertiary).
4. **Gemini-judge results should be reported but de-emphasized.** Gemini's lenience is a one-sided drift, not noise; v4-flash and v4-pro tell the same story (95.5% agreement on pass/fail).
5. **Cite the seed_full coverage asymmetry honestly** — three-model subset for default, two for max.
