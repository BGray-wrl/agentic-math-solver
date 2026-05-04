"""
Branch configuration for Hadamard agentic attack v2.

Two branches, both alternating opus↔gemini every turn.
Different initial construction strategies for diversity.
"""

from prompts import INITIAL_PROMPT_WILLIAMSON_QR, INITIAL_PROMPT_WILLIAMSON_SEARCH

OPUS = "openrouter/anthropic/claude-opus-4.6"
GEMINI = "openrouter/google/gemini-3.1-pro-preview"

BRANCHES = {
    0: {
        "name": "williamson-qr",
        "alternating": True,
        "models": [OPUS, GEMINI],  # alternates: opus, gemini, opus, gemini, ...
        "initial_prompt": INITIAL_PROMPT_WILLIAMSON_QR,
        "max_turns": 50,
        "max_tokens": 16384,
    },
    1: {
        "name": "williamson-search",
        "alternating": True,
        "models": [OPUS, GEMINI],
        "initial_prompt": INITIAL_PROMPT_WILLIAMSON_SEARCH,
        "max_turns": 50,
        "max_tokens": 16384,
    },
}

TARGET_ORDER = 668
EXEC_TIMEOUT = 300       # seconds per code execution (up from 120)
LITELLM_TIMEOUT = 540    # seconds per LLM call
