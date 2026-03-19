# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This project is a generic instance for rapid research development and testing on (TODO update with project details).

## Off-Limits Files

Do NOT edit these files under any circumstances:
- `human_testing.py`
- `human_log.md`
- `docs/human_notes.md`

## Environment Setup

```bash
uv venv
source .venv/bin/activate
uv pip install matplotlib requests python-dotenv # TODO update as needed
```

Run a script:
```bash
uv run train_baseline.py
```

## Instance & API
- **OpenRouter API key**: loaded from `.env` as `OPENROUTER_API_KEY` — use for inference
IF REMOTE INSTANCE CONNECTED (TODO update/confirm instance details)

## Assignment Structure

Unclear yet. Will update when task begins.

Writeup is in `docs/writeup.md`. TODO Writing/drafting details.

## Key Implementation Patterns
- Always report results as `mean ± std` over multiple seeds (≥3)
- Use e.g. `numpy.random.seed` + `torch.manual_seed`  for reproducibility
- Keep a running log of experiments tried, expected outcomes, and actual results.

IMPORTANT: After every experiment run, and after completing any major task, append a short description and results summary to agent_log.md in this format:
> ## [Event Name] - [YYYY-MM-DDTHH:mm:ss]
> short description & detail 

include experiment results, hyperparameters and seed count when applicable.

## Utility Templates

### OpenRouter Utility 
`src/utils.openrouter()` — call any OpenRouter model

```python
from utils import openrouter
text = openrouter("Your prompt here")   # default: google/gemini-3.1-flash-lite-preview
text = openrouter("prompt", model="z-ai/glm-4.7-flash", system="You are...")
```

Reads `OPENROUTER_API_KEY` from `.env`. Returns response as a plain string. Use for quick LLM calls without loading a local model.

---
