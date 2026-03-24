# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This project is an agentic math-solving pipeline (generator → verifier ↔ reviser loop → final judge).

## Off-Limits Files

Do NOT edit these files under any circumstances:
- `human_testing.py`
- `human_log.md`
- `docs/human_notes.md`

## Environment Setup

```bash
uv venv
source .venv/bin/activate
uv pip install matplotlib requests python-dotenv litellm
```

Run the pipeline:
```bash
uv run src/pipeline.py benchmarks/winning-gold/imo01.txt
uv run src/pipeline.py --problem "Find all primes p such that..." --iterations 3
uv run src/pipeline.py benchmarks/winning-gold/imo01.txt --mock   # smoke test, no API calls
```

## Instance & API
- **OpenRouter API key**: loaded from `.env` as `OPENROUTER_API_KEY` — use for inference
IF REMOTE INSTANCE CONNECTED (TODO update/confirm instance details)

## Assignment Structure

Main pipeline: `src/pipeline.py`

### Pipeline
`generator → verifier ↔ reviser loop (up to N iterations) → final judge`

- **generate**: produce an initial solution given a problem
- **verify**: check the solution step-by-step; output `VERDICT: correct` or `VERDICT: issues_found`
- **revise**: fix issues identified by the verifier; produce an updated solution
- **judge**: final evaluation (0–7 score with ground truth, or `incorrect|partial|almost|correct` without)

### Running against IMO problems
```bash
# Smoke test (no API calls)
uv run src/pipeline.py benchmarks/winning-gold/imo01.txt --mock

# Real run, 3 verify/revise iterations
uv run src/pipeline.py benchmarks/winning-gold/imo01.txt --iterations 3

# With ground-truth judge
uv run src/pipeline.py benchmarks/winning-gold/imo01.txt --ground-truth benchmarks/winning-gold/solution_imo01.log

# Write result JSON to file
uv run src/pipeline.py benchmarks/winning-gold/imo01.txt -o results/run1.json
```

### Logs
Every model call is appended as a JSON record to `logs/pipeline_<YYYYMMDD_HHMMSS>.jsonl`.

## Key Implementation Patterns
- Always report results as `mean ± std` over multiple seeds (≥3)
- Use e.g. `numpy.random.seed` + `torch.manual_seed`  for reproducibility
- Keep a running log of experiments tried, expected outcomes, and actual results.

IMPORTANT: After every experiment run, and after completing any major task, append a short description and results summary to agent_log.md in this format:
> ## [Event Name] - [YYYY-MM-DDTHH:mm:ss]
> short description & detail 

include experiment results, hyperparameters and seed count when applicable.

## Utility Templates

### LiteLLM Wrapper (preferred)
`src/utils.llm()` — LiteLLM wrapper for OpenRouter

```python
from utils import llm
text = llm("Your prompt here")   # default: openrouter/google/gemini-3.1-flash-lite-preview
text = llm("prompt", model="openrouter/z-ai/glm-4.7-flash", system="You are...")
```

### OpenRouter Utility (legacy)
`src/utils.openrouter()` — direct OpenRouter API call

```python
from utils import openrouter
text = openrouter("Your prompt here")   # default: google/gemini-3.1-flash-lite-preview
text = openrouter("prompt", model="z-ai/glm-4.7-flash", system="You are...")
```

Both read `OPENROUTER_API_KEY` from `.env`. Return response as a plain string.

---
