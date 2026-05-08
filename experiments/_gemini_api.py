"""
Gemini API wrapper for gemma-4-31b-it.
"""
from __future__ import annotations
"""
Tier 2 paid account — generous rate limits. Uses exponential backoff for 429s.

Usage:
    from _gemini_api import gemini_generate
    text, meta = gemini_generate(model="gemma-4-31b-it", prompt="...", system="...")
"""
import os, time, threading, requests, random
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY not set")

# Adaptive concurrency cap. Start moderate; trim down on rate-limit cascades.
_concurrency_lock = threading.Lock()
_active_calls = [0]
_max_concurrent = [int(os.getenv("GEMINI_INITIAL_CONCURRENCY", "20"))]
_concurrency_ceiling = [int(os.getenv("GEMINI_MAX_CONCURRENCY", "30"))]
_concurrency_floor = [int(os.getenv("GEMINI_MIN_CONCURRENCY", "4"))]
_consecutive_429 = [0]
_last_429_ts = [0.0]
_successes_since_shrink = [0]


def _adapt_after_429():
    """Triggered on 429: shrink concurrency."""
    with _concurrency_lock:
        _consecutive_429[0] += 1
        _last_429_ts[0] = time.time()
        _successes_since_shrink[0] = 0
        if _consecutive_429[0] >= 3:
            old = _max_concurrent[0]
            new = max(_concurrency_floor[0], old - 4)
            if new < old:
                _max_concurrent[0] = new
                print(f"[gemini-api] rate-limit cascade — shrinking concurrency {old} → {new}", flush=True)
            _consecutive_429[0] = 0


def _adapt_after_success():
    """On clean successes, slowly relax back up."""
    with _concurrency_lock:
        _successes_since_shrink[0] += 1
        if _consecutive_429[0] > 0 and time.time() - _last_429_ts[0] > 30:
            _consecutive_429[0] = max(0, _consecutive_429[0] - 1)
        # After enough successes since last shrink, try to grow concurrency back up
        if (_successes_since_shrink[0] >= 8
            and time.time() - _last_429_ts[0] > 30
            and _max_concurrent[0] < _concurrency_ceiling[0]):
            old = _max_concurrent[0]
            new = min(_concurrency_ceiling[0], old + 2)
            _max_concurrent[0] = new
            _successes_since_shrink[0] = 0
            print(f"[gemini-api] grew concurrency {old} → {new}", flush=True)


def _acquire():
    """Block until we are under the current concurrency cap."""
    while True:
        with _concurrency_lock:
            if _active_calls[0] < _max_concurrent[0]:
                _active_calls[0] += 1
                return
        time.sleep(0.05 + random.random() * 0.1)


def _release():
    with _concurrency_lock:
        _active_calls[0] -= 1


def gemini_generate(
    model: str,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 24000,
    temperature: float = 0.7,
    http_timeout: int = 1200,
    retries: int = 8,
    base_backoff: float = 6.0,
    max_backoff: float = 180.0,
) -> tuple[str, dict]:
    """
    Returns (text, meta) where meta has prompt_tokens, candidate_tokens, thoughts_tokens.
    Raises on terminal failure.
    """
    parts = [{"text": prompt}]
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"

    last_err = None
    for attempt in range(retries + 1):
        _acquire()
        try:
            r = requests.post(url, json=body, timeout=http_timeout)
        except Exception as e:
            _release()
            last_err = e
            wait = min(base_backoff * (2 ** attempt), max_backoff)
            time.sleep(wait + random.random() * 2)
            continue
        else:
            _release()

        if r.status_code == 200:
            d = r.json()
            try:
                cand = d["candidates"][0]
                content_parts = cand.get("content", {}).get("parts", [])
                # Concatenate non-thought text parts
                visible = []
                for p in content_parts:
                    if p.get("thought") is True: continue
                    if "text" in p: visible.append(p["text"])
                # Some responses have all parts marked thought=True (rare). Fallback: include all text.
                if not visible:
                    for p in content_parts:
                        if "text" in p: visible.append(p["text"])
                text = "\n".join(visible)
                if not text:
                    raise ValueError(f"empty content; finishReason={cand.get('finishReason')}")
                usage = d.get("usageMetadata", {})
                _adapt_after_success()
                return text, {
                    "prompt_tokens":     int(usage.get("promptTokenCount", 0) or 0),
                    "candidate_tokens":  int(usage.get("candidatesTokenCount", 0) or 0),
                    "thoughts_tokens":   int(usage.get("thoughtsTokenCount", 0) or 0),
                    "total_tokens":      int(usage.get("totalTokenCount", 0) or 0),
                    "finish_reason":     cand.get("finishReason"),
                }
            except (KeyError, IndexError, ValueError) as e:
                last_err = ValueError(f"parse error: {e}; payload: {str(d)[:500]}")
                if attempt < retries:
                    time.sleep(min(base_backoff * (2 ** attempt), max_backoff))
                    continue
                raise last_err

        # Status != 200
        body_text = r.text[:300]
        if r.status_code == 429:
            _adapt_after_429()
            # Honor Retry-After if present
            ra = r.headers.get("Retry-After")
            wait = float(ra) if ra and ra.replace('.','',1).isdigit() else min(base_backoff * (2 ** attempt), max_backoff)
            wait += random.random() * 3
            if attempt < retries:
                time.sleep(wait)
                continue
            raise RuntimeError(f"429 after {retries+1} retries: {body_text}")

        if r.status_code in (500, 502, 503, 504):
            if attempt < retries:
                time.sleep(min(base_backoff * (2 ** attempt), max_backoff) + random.random() * 2)
                continue
            raise RuntimeError(f"5xx after retries: {r.status_code} {body_text}")

        # 4xx other than 429 — non-retriable
        raise RuntimeError(f"HTTP {r.status_code}: {body_text}")

    raise last_err if last_err else RuntimeError("unreachable")
