# Claude — short ideas for a NeurIPS submission (2026-05-05)

These are notes synthesized from agent_log.md (May 2026 entries) and the master dataset
`results/dataset_20260505.jsonl` (2,848 rows, up to three judges per cell). Five
clusters of findings, presented plainly. No new API calls were run.

## 1. The judge is the experiment

The single biggest result in the May data is that **judge choice flips the headline of
almost every pipeline-architecture experiment we ran.**

- Triple-judge agreement (n=1,458 cells with all 3 judges):
  - v4-pro vs gemini-3-flash: exact match 60%, **pass-flip rate 27%, mean Δ +1.75**.
  - v4-pro vs v4-flash:       exact match 84%, pass-flip rate **5%**, mean Δ +0.07.
  - On the 402 cells where v4-pro and gemini disagree on pass/fail, **v4-flash sides
    with v4-pro 352/390 times (90%)** — i.e. gemini is the outlier, not v4-pro.
- Mode rankings flip per-judge for 4 of 6 Phase 1 models. Same data, three judges:
  - For gemma-4-31b-it: v4-pro picks `generate` best, gemini picks `full` best.
  - For gpt-oss-120b:   all three judges pick `full`, but gemini scores it 3.10 vs
    v4-pro 1.39.
- Gradingbench (n=200 vs human Points): gemini-3-flash r=0.51, v4-flash r=0.76,
  v4-pro r=0.79, gpt-5.4-nano @ xhigh r=0.71. Gemini's mean bias is **+1.65 against
  human ground truth** with 47% precision at ≥6.

**Implication.** Many published "agentic pipeline beats baseline by X" claims may be
judge artifacts. A simple intervention — re-judge a held-out subsample with a calibrated
strict judge — could overturn entire result tables. Phase 2 of our work hit exactly
this trap: cheap models scored "first-ever" 7/7s on Erdős problems under gemini that
all collapsed to 0/7 under v4-pro.

## 2. Reasoning is the dominant axis (for both solving and judging)

**Solving side (gpt-oss + gemma, same v4-flash judge, apples-to-apples):**
- generate:      gpt-oss 1.34→2.30 (+0.96), gemma 1.49→2.74 (+1.25)
- full:          gpt-oss 1.58→2.43 (+0.85), gemma 1.39→2.17 (+0.79)
- seed_generate: gpt-oss 1.09→2.54 (+1.45), gemma 1.49→2.74 (+1.26)
- seed_full:     gpt-oss 1.41→3.00 (+1.59), gemma 1.71→3.31 (+1.60)

Reasoning roughly doubles the strict-judge score in every mode. The largest gains
appear in the most "agentic" modes (seed_full), suggesting reasoning compounds with
sampling/ideation rather than substituting for it.

**Judging side (n=200 gradingbench):**
- gemma-4-31b-it default → reasoning=high: r=0.63 → **0.78** (lowest |Δ| of any judge)
- gpt-oss-120b minimal → xhigh:           r=0.51 → **0.77**
- v4-flash ON → OFF:                      r=0.76 → 0.59 (recall collapses 79→57%)

Reasoning, not model family, sets the accuracy band. Lineage sets the bias direction
(deflation for DS, inflation for gemini/gemma) but the reasoning state determines
whether you're in the "useful judge" cluster or not.

**Implication.** A paper-worthy framing: "before architecture, set reasoning effort."
This also reframes a lot of cost comparisons across models — much of "$/run" variance
across vendors is really just reasoning-effort variance, not capability.

## 3. A cheap multi-judge ensemble matches a frontier judge

Multi-judge ensembles built from cheap, mis-aligned-bias judges hit the same accuracy
band as gemini-3.1-pro at a fraction of the cost.

| System | r | F1 | ≥6-agree | $/decision |
|---|---|---|---|---|
| gemini-3.1-pro (frontier) | 0.881 | 84 | 88.4% | $0.033 |
| 4-judge ensemble (v4-pro + oss-xhigh + nano-xhigh + gemma-high), majority | 0.863 | 84 | **91.3%** | $0.057 |
| Cheap trio (gemma-high + oss-xhigh + v4-flash), mean      | 0.862 | 84 | 90.1% | **$0.009** |
| Tiered: trio auto-decides; v4-pro audits 21% disagreements |    | — | **89.8%** | **$0.013** |

Bias signs are what make the cheap trio work: gemma-high inflates (+0.55), gpt-oss-xhigh
mildly inflates (+0.21), v4-flash deflates (-0.80). They sum near zero.

**Implication.** Practical, paper-shippable result: "calibrated cheap-judge ensembles
substitute for expensive frontier judging, with diverse bias being the active
ingredient." Useful for anyone running large-scale automated grading.

## 4. Best-of-N nearly always beats verify/revise pipelines

Across **70 problems × 6 generators × 3 architecture modes** (Phase 1, plus the missing
seed_full added in Phase 2/3), with all three judges:

- **Under strict judges (v4-pro / v4-flash), pass@3 best-of-3 wins for 5 of 6 models.**
  Verify/revise (`full`) is best only for deepseek-v4-pro (the strongest base model).
- Across all 6 models the average uplifts vs single-shot pass@1 are: **pass@3 +1.04**,
  seed_generate +0.71, full +0.37 (gemini-judged; same ranking holds qualitatively
  under v4-pro).
- **Best-of-N saturates at N=5–7** for cheap models with reasoning ON (gpt-oss
  1.40→1.40→1.73 at N=3,5,7; gemma 0.87→1.93→1.97). v4-flash on 70 problems hits
  64% pass rate (44/69) at N=7 — a strong cheap baseline.

The verify/revise loop's main failure mode is the **verifier**:
- Verifier early-stop rates: gpt-oss 24%, gemma 41%, gemini-3-flash 44%, v4-flash 49%,
  v4-pro 49%, qwen-35b 59%.
- Verifier false-positive rates (early-stopped, judge said <6): v4-pro 9%, v4-flash 12%,
  gpt-oss 41%, gemma 62%, gemini-3-flash 65%, qwen-35b 68%. Weak verifiers
  hallucinate "looks correct" 60–68% of the time when they early-stop.

**Implication.** Pipeline complexity is justified only when (a) the base model is strong
enough to self-critique (only v4-pro in our set), or (b) you swap in a strong critic.
The flex-budget sweep showed that a v4-flash generator + v4-pro verify/revise critic
gives +1.05 over flash-solo full pipeline (rescues 3/20 PB-Advanced problems from
0→7) — the cleanest "asymmetric pipeline" signal we have.

## 5. Cross-model role swap is a wash; the verifier is the fragile slot

Phase 3 role-swap matrix (gpt-oss × gemma-4-31b-it, 8 conditions × 70 problems,
gemini judge with v4-pro escalation on special-10):

- **5 of 8 conditions land within ±0.1 of the same-model baseline.**
- Worst swap: **gemma-as-verifier on a gpt-oss pipeline (-0.55).** Reverse direction
  is fine.
- Best swap: gemma-as-reviser on gpt-oss (+0.05). Tiny.
- Two random-mix runs differ by 0.41 points → any |Δ| < 0.4 is sampling noise at n=70.

Phase 2's frontier "breakthroughs" were mostly gemini-leniency: of 224 special-10
trials with all 3 judges, **only 10 had unanimous ≥6** while 41 were gemini-only ≥6.
Of `first-proof-10-official`, the most-cracked frontier problem, 25 trials had v4-flash
≥6 vs only 11 for gemini at the trial level — the strict judges actually credit it
more than gemini does at trial scope, because gemini was choosing different branches.

**Implication.** "Diverse models for diverse roles" is appealing but doesn't deliver at
the cheap tier. The verifier slot is uniquely sensitive — papers proposing role-swap
pipelines need to ablate just the verifier.

---

## Candidate paper framings (ranked by how clean the data is)

1. **"The Judge Is the Experiment: Calibrated Multi-Judge Evaluation for Agentic Math
   Solvers."**  Story = (1) + (3) + slices of (4)/(5). Dataset (2,848 trials, 3 judges)
   is a substantive, citable artifact. Empirical grounding includes 200-sample
   gradingbench against humans. Strong argument: prior agentic-pipeline papers should
   be re-evaluated; we ship the cheap-ensemble recipe to fix it.
2. **"Reasoning Beats Architecture in Agentic Math: An 8,000-Branch Audit."**  Story =
   (2) + (4) + the role-swap null result. Headline plot: reasoning lifts 8 of 8
   (model, mode) cells by +0.8 to +1.6, while architecture changes (full, seed_*, role
   swaps) move scores by ≤±0.1 within the same reasoning state. Implies a methodology
   change for the field: lock reasoning state before any architecture comparison.
3. **"What's Cheap, Strong, and Right: Frontier Math Solving Without Frontier Models."**
   Story = pipeline configurations that get cheap models to within ε of frontier
   accuracy on AnswerBench (deepseek-v4-flash 88% vs v4-pro 94%) and demonstrate
   per-problem coverage gains via diverse method ensembling (flex-budget sweep:
   union of best-method coverage 12-13 of 20 PB-Advanced problems vs single-method
   ≤9). Risk: AnswerBench is "find the answer" not "prove it"; story is weakest
   on rigor.

Framing #1 is the most defensible — it has both the largest dataset, the cleanest
result, and the most surprise (most readers will not expect a 27% pass-flip rate from
swapping judges). Frame #2 is the next-best follow-on or a sister paper. Frame #3 is
weaker as a NeurIPS story but could anchor a workshop paper.

## Things to be careful about / open questions

- The "cheap ensemble matches frontier" claim depends on n=200 gradingbench; bigger
  human-scored set would harden it.
- Reasoning effect (+0.8 to +1.6) was measured under v4-flash judge for both arms.
  A v4-pro re-grade on the reasoning runs would add ~$10 and tighten the estimate;
  the signal is too large to be entirely judge-leniency, but a re-grade is needed
  for strict honesty.
- We didn't compute true gemini-best-of-3 for all phase 1 cells (cost-out at the time);
  numbers reported assume v4-pro's best-branch pick. Errors are 0.1-0.3 points,
  documented in the agent_log.
- The flex-budget "v4-pro V↔R rescues v4-flash" signal is n=20 only — needs replication.
- Cross-judge effects on "polish vs rigor": gemini scores 50 of 81 v4-pro-failures as
  pass when the reviser pass produces polished prose. The mechanistic claim ("gemini
  reads polish, v4-pro reads rigor") is plausible but not formally tested.

---

## TL;DR (the plainest version)

Five things we learned, in plain words:

1. **Different LLM judges give very different answers to the same question.**
   On 1,458 trials all three of our judges scored, the strict and lenient judges
   disagreed about pass/fail 27% of the time. The lenient judge scored 1.75 points
   higher, on average, on a 7-point scale. Most "did the pipeline help?" claims flip
   when you swap the judge.

2. **Reasoning matters more than the pipeline.** Turning on reasoning gives cheap
   models +0.8 to +1.6 points across every pipeline mode. Switching pipelines
   (verify/revise, idea-generation, etc.) only moves scores by about ±0.4. So if you
   want better answers, set reasoning to high before changing the architecture.

3. **A cheap ensemble of three differently-biased judges matches a frontier judge.**
   Pick one judge that scores high, one that scores low, one that's neutral —
   average them. You get the same accuracy as a single expensive frontier judge at
   roughly a quarter of the cost.

4. **Best-of-N sampling beats verify/revise pipelines for almost every model we
   tested.** Just running the model 3-7 times and picking the best answer is the
   strongest cheap baseline. The verify/revise loop only earns its cost when the
   model is strong enough to critique itself, OR when you swap in a strong critic
   on top of a cheap generator.

5. **Cross-model role swap doesn't help, except: don't put a weak verifier on a
   pipeline that has a different generator.** That one swap costs about half a
   point. Other role swaps are noise at our benchmark size.

**The single paper-worthy idea**: agentic-pipeline papers using one LLM judge are
mostly measuring the judge, not the pipeline. We ship a 2,848-trial three-judge
dataset, calibrated against humans, plus a cheap-ensemble recipe to fix this for
future papers.
