import os

import numpy as np
import random
import requests
from dotenv import load_dotenv

# # Temporararily deactivated to avoid torch dependency for non-local LLM code. Re-enable if needed for local LLMs or other torch-based utilities.
# import torch
# import torch.nn as nn


# # Temporararily deactivated to avoid torch dependency for non-local LLM code. Re-enable if needed for local LLMs or other torch-based utilities.
# def set_seed(seed: int):
#     torch.manual_seed(seed)
#     np.random.seed(seed)
#     random.seed(seed)
#     if torch.cuda.is_available():
#         torch.cuda.manual_seed_all(seed)

# def get_device():
#     return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def llm(prompt, model="openrouter/google/gemini-3.1-flash-lite-preview", system=None, max_tokens=2048):
    """
    LiteLLM wrapper for OpenRouter. Returns response text.
    model format: 'openrouter/<provider>/<model>'
    Reads OPENROUTER_API_KEY from .env.
    """
    import litellm
    load_dotenv()
    os.environ["OPENROUTER_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = litellm.completion(model=model, messages=messages, max_tokens=max_tokens)
    content = resp.choices[0].message.content
    # Some thinking models (e.g. Gemini Pro) put the answer in reasoning_content
    # when content is None
    if content is None:
        content = getattr(resp.choices[0].message, "reasoning_content", None)
    if content is None:
        raise ValueError(f"Model {model} returned None content. Full response: {resp}")
    return content


def openrouter(prompt, model="google/gemini-3.1-flash-lite-preview", system=None, max_tokens=512):
    """
    Call any OpenRouter model. Returns the response text string.

    Args:
        prompt:     User message (str)
        model:      OpenRouter model ID (default: gemini-flash-3.5-lite-preview)
        system:     Optional system prompt (str)
        max_tokens: Max tokens to generate

    Example:
        text = openrouter("What is 2+2?")
    """
    load_dotenv()
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY not found in environment / .env")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "max_tokens": max_tokens},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
