# Agentic Math Solver Project Report

Date reviewed: 2026-05-04

This report summarizes the current state of the repository, the implemented math-solving pipeline, the main experiments, and the key lessons recorded so far. It is based on a review of `CLAUDE.md`, `agent_log.md`, the source tree, prompts, benchmark files, experiment scripts, logs, and results.

Important note: `agent_log.md` is not guaranteed to be in strict chronological or dependency order. Some earlier conclusions were later superseded by bug fixes, reruns, or manual verification. This report treats later corrections and reruns as higher-confidence than earlier preliminary entries.

## Project Overview

The project is an agentic math-solving research repo. Its original core is a generator -> verifier -> reviser loop -> final judge pipeline for solving and grading mathematical problems. Over time, the project expanded into a broader testbed for:

- Comparing frontier and open models on proof-generation tasks.
- Testing verify/revise loops against generate-only baselines.
- Testing seed-idea and best-of-N orchestration.
- Studying cross-model verification, ideator strength, and ranker/pruning strategies.
- Applying programmatic verification loops to constructive open problems such as Ramsey hypergraphs and Hadamard matrices.

The main operational guidance is in `CLAUDE.md`. It identifies `src/pipeline.py` as the primary pipeline and defines the canonical architecture:

```text
generate -> verify <-> revise loop -> judge
```

`CLAUDE.md` also states that `human_testing.py`, `human_log.md`, and `docs/human_notes.md` are off-limits and should not be edited.

## Repository Structure

Key directories and files:

- `src/pipeline.py`: main pipeline implementation, CLI, mock mode, JSONL logging, idea generation helper, retry wrapper, final judging, and score extraction fallback.
- `src/utils.py`: LiteLLM/OpenRouter helpers.
- `src/batch_eval.py`: batch runner over selected IMO-bench proofbench problems.
- `src/ramsey_checker.py`: programmatic verifier for the Ramsey hypergraph construction problem.
- `src/hadamard_checker.py`: parser and verifier for Hadamard matrices.
- `src/initial_proof_grader.py`: older OpenRouter/PDF grading script for First Proof candidates.
- `prompts/pipeline/`: generator, verifier, reviser, judge, extraction, ideator, and idea-ranker prompts used by the pipeline experiments.
- `prompts/oai`, `prompts/epoch`, `prompts/deepmind`, `prompts/winning-gold`, `prompts/anthropic`: imported prompt patterns and references from external agentic math/proof systems.
- `benchmarks/`: assembled benchmark sources including IMO-bench, First Proof, Aletheia, Erdos-style problems, FrontierMath open problems, and Winning Gold IMO problems.
- `benchmarks/combined-benchmarks.csv`: unified benchmark CSV built from several source datasets.
- `experiments/`: dated experiment scripts and reusable template machinery.
- `experiments/results/`: 85 result JSON files at review time.
- `logs/`: JSONL and text logs from pipeline and experiment runs.
- `experiments/hadamard_agentic/`: tool-using coding loop for Hadamard matrix construction.
- `results/`: selected candidate solutions and grading artifacts.

The top-level `README.md` is currently empty or effectively placeholder-only.

## Implemented Pipeline

The core pipeline in `src/pipeline.py` now supports:

- Problem input from a file or `--problem`.
- Prompt file selection for generator, verifier, reviser, and judge.
- Mock mode for smoke tests with no API calls.
- JSONL logging of each model call.
- LiteLLM-backed calls through OpenRouter.
- Retry logic with exponential backoff for LLM calls.
- Ground-truth judging with 0-7 score tags.
- No-ground-truth judging with classification labels.
- An `ideate()` helper for seed-idea generation and JSON parsing.
- A judge extraction fallback when `<points>N out of 7</points>` is missing.

The main experiment template in `experiments/experiment_template.py` adds:

- CSV problem loading from `benchmarks/combined-benchmarks.csv`.
- Configurable model lists, judge model, seeds, pass threshold, worker counts, and timeouts.
- Generate-only vs full-pipeline modes.
- Ground-truth and no-ground-truth judging.
- Thread-safe logging.
- Full text preservation in result JSON.
- Retry support for failed runs.

## Benchmarks and Problem Sets

The repo contains and/or combines several problem sources:

- IMO-bench proof, answer, and grading data.
- Winning Gold IMO examples.
- First Proof official and Aletheia-style problems.
- General Aletheia problems.
- Erdos/Aletheia and Erdos-659 problem sets.
- FrontierMath open problems, including Ramsey hypergraphs.

A curated six-problem development set lives in `experiments/devset.py`. It is designed for fast iteration and includes:

- `PB-Basic-024`: sanity/regression canary.
- `PB-Basic-028`: boundary case where pipeline should help.
- `PB-Basic-012`: boundary case exposing verifier over-approval.
- `PB-Basic-017`: easy case where the pipeline should not degrade a correct solution.
- `PB-Basic-007`: hard stretch case.
- `erdos-659`: frontier-style target.

The dev set replaced slower PB-Advanced problems with faster PB-Basic alternatives after timing analysis.

## Experiment Timeline and Progress

### Initial pipeline bring-up

The first major milestone was implementing the generator -> verifier -> reviser -> judge loop, with prompts and logging. Mock smoke testing passed. Early real runs showed the verifier could catch obvious mistakes, but the generator/reviser could oscillate between wrong answers.

Initial IMO-bench runs showed strong performance on pre-IMO and easier problems, with sharp degradation on IMO-hard problems. A 20-problem proofbench run produced:

- Pre-IMO: 8/8 correct, average 7.0/7.
- IMO-easy: 4/6 correct, average 5.4/7.
- IMO-medium: 3/4 correct, average 6.5/7.
- IMO-hard: 0/2 correct, average 1.5/7.

Early failures often came from verifier leniency: the verifier sometimes approved incomplete solutions, missing solution families, or wrong degree bounds.

### Model comparisons

Several model-comparison runs tested generate-only baselines and full-pipeline variants. Important early findings:

- `qwen3.5-flash-02-23` was strong and consistent on a 60-problem generate-only comparison.
- `deepseek-v3.2-speciale` produced many API errors and very slow calls, making results unreliable.
- `gemini-3.1-flash-lite-preview` was too weak above pre-IMO difficulty.
- `nemotron-3-super-120b-a12b` was inconsistent and later dropped from some fast baselines due to output issues.
- `gpt-5.4-mini` showed some partial progress on hard/open problems but was weak in several benchmark batches.

On two hard/open problems (`erdos-659` and `ramsey-hypergraphs`), most models scored 0/7 in simple generate -> judge setups. `gpt-5.4-mini` got 3/7 on `erdos-659` in one run, but no model made useful progress on Ramsey in that baseline.

### Judge truncation and retry fixes

Two important infrastructure bugs changed the interpretation of early experiment results:

1. Judge truncation: Gemini judge outputs were often truncated before emitting the `<points>` tag, causing scores to default to 0. The judge prompt was restructured to put `<points>` at the beginning, `MAX_TOKENS_JUDGE` was increased in many scripts, and an extraction fallback prompt was added.

2. API connection drops: Full-pipeline trials had more API calls and therefore more failure chances. Before retries, this made the full pipeline look worse than it really was. Adding two retries with exponential backoff eliminated many errors and reversed part of the earlier "pipeline hurts" conclusion.

After retry logic, a fast baseline run had 0 errors and 100% judge parsing. In that corrected setting, the full pipeline improved stronger models:

- `gemini-3-flash-preview`: generate 2.50/7 -> full 5.00/7.
- `qwen3.5-flash-02-23`: generate 2.50/7 -> full 3.83/7.
- `gpt-oss-120b`: generate 1.00/7 -> full 1.33/7.

The corrected narrative is: verify/revise can help, but its value is model- and problem-dependent, and it was previously obscured by infrastructure failures.

### New dev-set baselines

On the newer six-problem dev set, a full baseline run with six models produced:

- `gemini-3-flash-preview`: generate 5.83/7, full 6.83/7.
- `qwen3.5-flash-02-23`: generate 3.83/7, full 4.83/7.
- `gpt-oss-120b`: generate 2.67/7, full 4.67/7.
- `deepseek-v3.2`: generate 1.50/7, full 2.33/7.
- `gemini-flash-lite`: generate 1.17/7, full 1.33/7.
- `gpt-5.4-mini`: generate 0.33/7, full 0.00/7.

The full pipeline helped most models except `gpt-5.4-mini`.

### Seed-ideas and best-of-N

Seed-idea orchestration became the strongest general-purpose architecture tested so far. The seed-ideas pipeline is:

```text
ideate N ideas -> run N solution branches -> judge each branch -> select best
```

In the first dev-set seed-ideas run, `qwen3.5-flash-02-23` and `gemini-3-flash-preview` reached perfect 7.00/7 on the new six-problem dev set with seed+full. `deepseek-v3.2` improved from 1.50/7 generate-only to 5.83/7 seed+full.

A four-way comparison showed:

- Generate-only is cheapest but leaves many hard cases unsolved.
- Full pipeline improves several models.
- Seed+generate often matches or beats full pipeline.
- Seed+full is best overall, but slower.

The main conclusion is that idea diversity is often more valuable than repeated self-correction.

### Idea-prediction and rankers

Analysis of 132 branched trials found:

- Branch scores are strongly bimodal: most are either 0-1 or 6-7.
- Ideas matter in about 43% of trials.
- When ideas matter, the gap between branches is large, often the difference between total failure and a correct proof.
- First generated idea has a position advantage.
- Best-of-3 improved mean branch score from 3.40 to 4.48 and pass rate from 47.5% to 63.6%.

Ranker/pruning experiments were mostly negative:

- Same-power rankers could not reliably predict which idea would lead to a correct solution.
- In a pruning experiment, ranker prune-to-3 underperformed random-3.
- Five ranker models performed at or below random for top-1/top-3 idea prediction.

The current recommendation from the logs is: run branches and judge their outputs rather than trying to rank idea descriptions ahead of time.

### Model diversity and ideator capability

Cross-model verification produced mixed results depending on the exact models:

- Earlier nemotron/deepseek cross-verification hurt relative to self-critique.
- Later DS/OSS experiments found useful cross-verification in some directions.
- Flash-lite was harmful as verifier but useful as ideator.

In the model diversity experiment:

- `deepseek` generator + `gpt-oss` verify/revise improved over the `deepseek` self baseline.
- `gpt-oss` generator + `deepseek` verify/revise improved over the `gpt-oss` self baseline.
- `flash-lite` as verifier hurt.
- `flash-lite` as ideator plus DS pipeline was the best tested condition in that experiment.

Ideator scaling results differed by model family:

- Gemini family: flash-lite ideator beat stronger Gemini ideators in full-pipeline settings, likely because it produced simpler, more executable ideas.
- OAI family: stronger ideator improved results, with the standard model best for OSS pipeline/generate-only in that set.

This suggests ideator quality is not monotonic with model strength across families; compatibility with the downstream solver matters.

### Harder IMO experiments

On 10 IMO-hard plus 5 IMO-medium PB-Advanced problems with flash-lite ideation and DS/OSS generators:

- Full pipeline helped more than generate-only.
- DS full scored 1.21/7 mean and passed 2/14 non-error cases.
- OSS full scored 0.93/7 mean and passed 2/15.
- Generate-only variants passed 0/15.
- Geometry was completely unsolved.
- Number theory was the strongest category.
- Nine of fifteen problems were 0/7 across all tested conditions.

The conclusion is that the pipeline helps at the margin, but DS/OSS hit a hard capability wall on many IMO-hard problems.

## Frontier/Open Problem Work

### Erdos-659

`erdos-659` is used as a frontier-style north-star problem. Results have been inconsistent:

- Early simple model comparisons mostly produced 0/7.
- `gpt-5.4-mini` got partial 3/7 in one generate-only run.
- A full-pipeline `qwen3.5-flash` result was judged 7/7, but later external/manual verification found inaccuracies, showing the judge could be too lenient on long ground-truth problems.
- A later `qwen3.6-plus:free` probe found a correct construction using the `Z + i sqrt(2) Z` lattice and Landau-Ramanujan-style distance counting, according to the log.

The practical lesson is that long frontier solutions require stronger verification than a single LLM judge.

### Ramsey hypergraphs

Ramsey hypergraphs exposed a major mismatch between the proof-refinement pipeline and constructive search problems.

Early notes contained conflicting interpretations. In a frontier probe, `claude-opus-4.6` produced a sunflower construction that was later ground-truth judged as correct, scoring 7/7. Earlier manual/programmatic critique had been marked wrong in the log.

A more ambitious Ramsey v2 architecture used dual ideation, cross-model verification, escalated revision, a programmatic checker, synthesis, and multi-judge consensus. It did not solve the problem:

- Qwen branch reached 59 vertices where 64 were required.
- Synthesis reached 61 vertices.
- Gemini branch reached 36 vertices.
- Opus branch regressed to a trivial small construction.

The deeper analysis concluded that constructive problems need code execution and programmatic verification in the loop. LLM verification/revision can actively destroy promising constructions by rewriting them into cleaner but wrong arguments.

The current architectural recommendation for constructive problems is:

```text
generate code -> execute -> programmatically check -> feed concrete failures back -> iterate
```

rather than:

```text
write proof -> LLM verifier -> LLM reviser
```

## Hadamard Matrix Work

The Hadamard work targets construction of a Hadamard matrix of order 668. This became a separate agentic coding loop under `experiments/hadamard_agentic/`.

### v1

v1 used three parallel branches with code execution and `hadamard_checker.py`, but no LLM proof verifier. It failed:

- Opus Paley branch: 20 turns, best recorded order 4.
- Gemini tensor/Williamson branch: 20 turns, best recorded order 4.
- Relay Opus->Gemini branch: 20 turns, best recorded order 3.

Main v1 lessons:

- Gemini often produced no executable code.
- Opus spent too much time on small tests.
- The prompt overloaded models with too many construction strategies.
- 120 second execution timeout may have been too short.

### v2

v2 alternated Opus and Gemini, increased to 50 turns, used higher execution timeout, Epoch-style prompts, concrete Williamson pseudocode, phase nudges, and full conversation logging.

The first v2 run hit OpenRouter monthly limits before completion. A later resume used a second key and finished both branches. It appeared to remain stuck at order 4, but this turned out to be a feedback bug.

Critical v2 bug:

- The sandbox captured only the last 8 KB of stdout.
- A 668 x 668 matrix CSV is roughly 900 KB.
- When models printed a candidate matrix, stdout truncation caused the checker to parse only a fragment.
- The recorded "best_order=4" was a parser artifact, not necessarily the true model output.

Both branches had actually implemented meaningful Williamson/Goethals-Seidel tooling and reached PAF defects around 2688-2752, but the feedback loop could not verify full matrices.

### v3

v3 fixes the Hadamard feedback loop:

- `sandbox_exec.py` now supports a shared directory and exposes it through `HADAMARD_OUTPUT_DIR`.
- Models are instructed to write `candidate.csv` instead of printing large matrices.
- `agentic_loop.py` reads matrix files directly, with stdout fallback for small matrices.
- Feedback includes orthogonality percentage, perfect rows, max off-diagonal value, and a 0-100 quality score.
- Stale file cleanup prevents one turn's candidate from contaminating the next.
- `prompts.py` was updated to require file-based candidate output.

The e2e suite in `experiments/hadamard_agentic/test_pipeline_e2e.py` passed 58/58 checks. As of the last log entry, Hadamard v3 is ready for a real run, but no successful v3 open-problem run is recorded in `agent_log.md`.

## Key Findings

The strongest current findings are:

1. Seed-idea best-of-N is the most reliable orchestration improvement found so far.
2. Full verify/revise loops can help, but their measured value depends heavily on reliable API retries and robust judge parsing.
3. LLM verifiers are prone to over-approval, especially on missing cases and long/complex ground-truth problems.
4. Single LLM judges are insufficient for frontier/open problems; use programmatic checks or expert/manual review where possible.
5. Rankers cannot reliably predict successful ideas from descriptions alone, at least in the tested setups.
6. Cross-model verification is not uniformly good or bad; model pairing and role assignment matter.
7. Cheap or weaker models can be useful ideators even when they are bad solvers.
8. Constructive math problems need code execution and programmatic verification, not proof-style LLM critique loops.
9. Long-output infrastructure matters: truncation, token caps, malformed API responses, and OpenRouter timeouts changed several early conclusions.
10. Logs and result files must preserve full solution and verdict text; truncation prevents regrading and misleads analysis.

## Known Issues and Risks

- `agent_log.md` contains superseded conclusions and is not always in reliable order.
- Several experiment scripts are dated variants of each other; some may contain stale constants or modified configs from previous runs.
- The judge can still be too lenient on long frontier solutions.
- Some result files are marked mock and should not be treated as real model performance.
- API errors, monthly key limits, model rate limits, and provider-specific response truncation have materially affected results.
- The main `README.md` does not yet document the repo for a new human user.
- `src/initial_proof_grader.py` appears to reference older paths (`benchmarks/first-proof/problems`, `candidates`) that may not match the current tree.
- The iteration-depth experiment hung and was killed; it should be relaunched only after checking thread/API behavior.
- Hadamard v3 has passed local e2e tests but still needs a real run.

## Current Status

The repo is no longer just a simple pipeline prototype. It now contains:

- A working LLM math-solving pipeline.
- A reusable experiment framework.
- A curated fast dev set.
- Many benchmark conversion scripts and assembled benchmark CSVs.
- A large body of experiment results and logs.
- Programmatic checkers for Ramsey hypergraphs and Hadamard matrices.
- An agentic coding loop for constructive math searches.

The highest-confidence project direction is:

- Use seed-idea branching and best-of-N for proof-style problems.
- Keep full verify/revise loops for models and problem classes where corrected experiments show positive uplift.
- Avoid ranking idea descriptions as a pruning mechanism unless a new method is tested against the random and "first idea" baselines.
- For constructive open problems, use tool execution and programmatic feedback as the primary verifier.
- Treat LLM judges as useful screening tools, not final truth, on frontier problems.

## Recommended Next Steps

1. Run the Hadamard v3 agentic loop for real now that file-based matrix I/O is fixed.
2. Add a proper top-level `README.md` explaining setup, pipeline usage, mock tests, experiment workflow, and result interpretation.
3. Add an index of experiment scripts that labels each as current, superseded, mock-only, or exploratory.
4. Re-run the iteration-depth experiment after isolating the hang cause.
5. Harden frontier judging with programmatic checks, multi-judge consensus, or manual review before claiming solves.
6. Preserve full responses in all future result files and avoid result overwrites by keeping timestamped filenames.
7. For constructive tasks, build problem-specific checkers first, then wrap models around the checker feedback loop.

