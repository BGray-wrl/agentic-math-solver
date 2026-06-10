"""
Generate → M2 verify → revise pipeline for klt del Pezzo candidates.

Three models supported:
- openai/gpt-oss-120b @ xhigh (OpenRouter)
- deepseek/deepseek-v4-flash @ default (OpenRouter)
- gemma-4-31b-it @ max reasoning (direct Gemini API, via _gemini_api.py)

Pipeline:
  1. Generate with high max_tokens (50K+) to address truncation.
  2. Extract committed answer from response.
  3. Run M2 verifier.
  4. If FAIL and score >= 3 (i.e., framework valid, just polynomials off), revise once with M2 feedback.
"""
from __future__ import annotations
import os, sys, re, time, json, threading
from pathlib import Path

ROOT = Path("/Users/benjamingrayzel/sandbox/agentic-math-solver")
ITER_DIR = ROOT / "klt-del-pezzo-iteration"
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ITER_DIR))

from frontier_adapter import verify_method_b, feedback_for_revision  # was klt_verifier (2026-05-12)

# Import gemini API wrapper (gemma direct, tier-2 paid)
try:
    from _gemini_api import gemini_generate
except Exception as e:
    gemini_generate = None
    print(f"[warn] gemini_generate import failed: {e}")

# OpenRouter chat helper
import requests
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
# Primary key is over monthly limit; use working backups (cycle through).
_OR_KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_3"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k]
_or_key_idx = [0]
def _next_or_key():
    if not _OR_KEYS: return os.getenv("OPENROUTER_API_KEY")
    k = _OR_KEYS[_or_key_idx[0] % len(_OR_KEYS)]
    _or_key_idx[0] += 1
    return k
OPENROUTER_KEY = _OR_KEYS[0] if _OR_KEYS else os.getenv("OPENROUTER_API_KEY")


# ---------------------------------------------------------------------------
# Model configurations
# ---------------------------------------------------------------------------
MODELS = {
    "gpt-oss-xhigh": {
        "provider": "openrouter",
        "id": "openai/gpt-oss-120b",
        "reasoning": {"effort": "xhigh"},
        "max_tokens": 60000,
    },
    "deepseek-v4-flash": {
        "provider": "openrouter",
        "id": "deepseek/deepseek-v4-flash",
        "reasoning": None,
        "max_tokens": 60000,
    },
    "gemma-max": {
        "provider": "gemini",
        "id": "gemma-4-31b-it",
        "reasoning_max": True,
        "max_tokens": 50000,
    },
}

# Per-model semaphores
_sem = {
    "openai/gpt-oss-120b": threading.Semaphore(8),
    "deepseek/deepseek-v4-flash": threading.Semaphore(20),
}


def or_chat(model_id, system, user, max_tokens, reasoning=None, retries=5, timeout=600):
    """Call OpenRouter. Returns (content, reasoning_text, usage_dict)."""
    body = {
        "model": model_id,
        "messages": [
            *([{"role": "system", "content": system}] if system else []),
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    if reasoning is not None:
        body["reasoning"] = reasoning
    sem = _sem.get(model_id)
    last_err = None
    for attempt in range(retries + 1):
        if sem: sem.acquire()
        cur_key = _next_or_key() if _OR_KEYS else OPENROUTER_KEY
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {cur_key}", "Content-Type": "application/json"},
                json=body, timeout=timeout,
            )
        except Exception as e:
            if sem: sem.release()
            last_err = e
            time.sleep(min(8 * (2 ** attempt), 60))
            continue
        if sem: sem.release()
        try:
            if r.status_code == 402:
                raise RuntimeError(f"402: {r.text[:200]}")
            if r.status_code == 403:
                # key over monthly limit; try next key
                last_err = RuntimeError(f"403: {r.text[:120]}")
                time.sleep(2)
                continue
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", "30") or 30)
                time.sleep(min(wait, 90))
                continue
            r.raise_for_status()
            j = r.json()
            msg = j["choices"][0]["message"]
            content = msg.get("content")
            reasoning_text = msg.get("reasoning") or msg.get("reasoning_content")
            if not content: content = reasoning_text
            if not content: raise ValueError("empty response")
            usage = j.get("usage", {})
            cd = usage.get("completion_tokens_details") or {}
            return content, reasoning_text, {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "reasoning_tokens": int(cd.get("reasoning_tokens", 0) or 0),
                "cost": float(usage.get("cost", 0) or 0),
            }
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            time.sleep(min(8 * (2 ** attempt), 60))
    raise last_err or RuntimeError("or_chat: retries exhausted")


def gemma_chat(system, user, max_tokens, reasoning_max=True):
    """Gemma via Gemini API. Returns (content, reasoning_text=None, usage_dict)."""
    if gemini_generate is None:
        raise RuntimeError("gemini_generate not available")
    text, meta = gemini_generate(
        model="gemma-4-31b-it",
        prompt=user,
        system=system,
        max_tokens=max_tokens,
    )
    return text, None, {
        "prompt_tokens": meta.get("prompt_tokens", 0),
        "completion_tokens": meta.get("candidate_tokens", 0),
        "reasoning_tokens": meta.get("thoughts_tokens", 0),
        "cost": 0.0,
        "finish_reason": meta.get("finish_reason"),
    }


def model_chat(model_key, system, user, max_tokens=None):
    """Dispatch to OpenRouter or Gemini based on model."""
    cfg = MODELS[model_key]
    mt = max_tokens or cfg["max_tokens"]
    if cfg["provider"] == "openrouter":
        return or_chat(cfg["id"], system, user, mt, reasoning=cfg.get("reasoning"))
    elif cfg["provider"] == "gemini":
        return gemma_chat(system, user, mt, reasoning_max=cfg.get("reasoning_max", True))
    else:
        raise ValueError(f"Unknown provider: {cfg['provider']}")


# ---------------------------------------------------------------------------
# Answer extraction
# ---------------------------------------------------------------------------
WEIGHTS_RE = re.compile(r"(?:Weights|weights)\s*[:=]?\s*\[?\s*([0-9\s,]+?)\s*\]?\s*$", re.M)
ANSWER_BLOCK_RE = re.compile(r"##\s*Answer\b(.*?)(?:\Z|^##\s)", re.DOTALL | re.M | re.I)

def extract_method_b(text):
    """
    Try to extract a Method B answer from model output.
    Returns dict with keys: weights (list[int]), eqns (list[str]), method ("B"),
    or None if extraction fails.
    """
    if not text: return None
    # Normalize LaTeX / Unicode operators
    body0 = text
    body0 = body0.replace("\\cdot", "*").replace("·", "*").replace("×", "*")
    body0 = body0.replace("\\,", "").replace("\\ ", " ")
    body0 = re.sub(r"x_\{(\d+)\}", r"x\1", body0)
    body0 = re.sub(r"x_(\d)", r"x\1", body0)
    body0 = body0.replace("$", "")
    # Prefer the last '## Answer' section
    last_answer = None
    for m in ANSWER_BLOCK_RE.finditer(body0):
        last_answer = m.group(1)
    body = last_answer if last_answer else body0

    # Look for weights — try multiple patterns
    weights = None
    # Pattern 1: "Weights: [a, b, c, d]" or "Weights = [a, b, c, d]"
    m = re.search(r"(?:Weights|weights)\s*[:=]?\s*\[\s*([0-9\s,]+?)\s*\]", body)
    if m:
        weights = [int(x.strip()) for x in m.group(1).split(",") if x.strip().isdigit()]
    if not weights:
        # Pattern 2: just a [list] at top, like "[2, 2, 5, 5]"
        m = re.search(r"^\s*\[\s*([0-9\s,]+?)\s*\]\s*$", body, re.M)
        if m:
            weights = [int(x.strip()) for x in m.group(1).split(",") if x.strip().isdigit()]
    if not weights or len(weights) < 3 or len(weights) > 7:
        return None

    # Collect equation lines: any line that contains x_i variables with operators
    eqn_lines = []
    for ln in body.splitlines():
        ln_strip = ln.strip()
        if not ln_strip: continue
        # Skip the weights line
        if "weight" in ln_strip.lower() or ln_strip.startswith("["): continue
        # Skip method/section labels
        if ln_strip.lower().startswith(("method", "answer", "f1 =", "f2 =", "f =", "equation")):
            # Extract RHS if line is like "F1 = ...":
            rhs = re.split(r"[:=]", ln_strip, maxsplit=1)
            if len(rhs) == 2:
                ln_strip = rhs[1].strip()
        # Strip any leading "F1:", "F:", "- " bullets
        ln_strip = re.sub(r"^[-*]\s*", "", ln_strip)
        ln_strip = re.sub(r"^F\d*\s*[:=]\s*", "", ln_strip)
        ln_strip = re.sub(r"^Equation\s*[:=]?\s*", "", ln_strip, flags=re.I)
        # Strip leading "**" and trailing "**" markdown
        ln_strip = ln_strip.strip("*").strip()
        # Strip latex math markers
        ln_strip = ln_strip.replace("$", "").strip()
        # Must contain x_i pattern
        if not re.search(r"x\d", ln_strip): continue
        # Must contain at least one + or - or * (likely a polynomial)
        if not re.search(r"[+\-*]", ln_strip): continue
        # Clean cdot, ^, and any LaTeX
        ln_strip = ln_strip.replace("·", "*").replace("\\cdot", "*").replace("\\,", "")
        ln_strip = re.sub(r"\\[a-zA-Z]+", "", ln_strip)
        # Restrict to safe characters
        if not re.match(r"^[\dx\+\-\*\^\s\(\)]+$", ln_strip): continue
        eqn_lines.append(ln_strip)

    if not eqn_lines:
        return None

    # Dedupe consecutive duplicates
    final_eqns = []
    seen = set()
    for e in eqn_lines:
        if e in seen: continue
        seen.add(e)
        final_eqns.append(e)

    # In M2: replace ^ with ^, * is OK. We need leading 'x' to be x0, x1, etc. M2 wants x0, not x_0.
    final_eqns = [re.sub(r"x_\{?(\d+)\}?", r"x\1", e) for e in final_eqns]

    return {"method": "B", "weights": weights, "eqns": final_eqns}


# ---------------------------------------------------------------------------
# Judge-based fallback extraction (when regex extractor fails)
# ---------------------------------------------------------------------------
JUDGE_SYSTEM = """You parse a math-research candidate solution and return JSON.
The candidate is a klt del Pezzo surface in P(w) for some weights w, given as Method B (weighted hypersurface or CI).
Return JSON ONLY (no prose). Format:
{"method":"B","weights":[w0,w1,...],"eqns":["polynomial 1","polynomial 2 if CI"]}
Use plain ASCII: x0, x1, ..., ^ for exponent, * for product, + and -.
If you cannot identify a clear answer, return: {"method":"none"}.
"""

JUDGE_USER = """Extract the final Method B answer from this candidate text. Return JSON only.

CANDIDATE TEXT:
{text}
"""

def judge_extract(text, model_key="deepseek-v4-flash"):
    """Fallback: ask a cheap LLM to extract weights and equations."""
    if not text: return None
    try:
        prompt = JUDGE_USER.format(text=text[-6000:])  # last 6K chars where answer typically is
        content, _, _ = model_chat(model_key, JUDGE_SYSTEM, prompt, max_tokens=2000)
    except Exception as e:
        return None
    # Find JSON in response
    m = re.search(r"\{[^{}]*\"method\"[^{}]*\}", content, re.DOTALL)
    if not m:
        # try multi-line JSON
        m = re.search(r"\{.*?\"method\".*?\}", content, re.DOTALL)
    if not m: return None
    try:
        import json as _json
        d = _json.loads(m.group(0))
    except Exception:
        return None
    if d.get("method") != "B": return None
    w = d.get("weights")
    e = d.get("eqns") or d.get("equations")
    if not (isinstance(w, list) and isinstance(e, list) and w and e): return None
    # sanitize
    w = [int(x) for x in w if isinstance(x, (int, float))]
    e = [str(x).strip() for x in e if x]
    return {"method": "B", "weights": w, "eqns": e}


def extract_with_fallback(text):
    r = extract_method_b(text)
    if r: return r, "regex"
    r = judge_extract(text)
    if r: return r, "judge"
    return None, "fail"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
GENERATOR_SYSTEM = """You are a research mathematician working on an unsolved problem.

IMPORTANT verification context:
- The output will be checked by Macaulay2 (M2).
- The M2 verifier checks (in order): weight-homogeneity, char-3 tameness (no weight divisible by 3), well-formedness (gcd of any n-1 weights = 1), Fano index = sum(weights) - sum(degrees) > 0, quasi-smoothness (affine cone smooth outside origin), then counts ISOLATED SINGULAR POINTS of X via stratum intersections with isotropy gcd > 1, then computes ρ(X).
- Counts are computed over the algebraic closure of F_3; you must check that your specific polynomials are *transverse* on each singular stratum, NOT just that Bezout would generically give the right number.
- In characteristic 3, weights 3, 6, 9, ... are FORBIDDEN (not tame).
- Symmetric polynomials like x_1^2 + x_2^2 paired with x_1^5 + x_2^5 have NO common zero on the stratum (only origin) in F_3-bar, because t^2 = -1 forces order(t)=4 while t^5 = -1 forces order(t) | 10, contradiction.

CRITICAL: Picard rank ρ(X) = 1 constraint is SUBTLE.
- Lefschetz hyperplane theorem does NOT give ρ(X) = 1 for surfaces; Pic(X) can be larger than Z.
- For a quasi-smooth hypersurface in P(w_0, w_1, w_2, w_3) of degree d, with singular line L_{ij} (gcd k = gcd(w_i, w_j)), the singularity TYPE at a generic L_{ij} ∩ X point is the cyclic quotient 1/k(a, b) where (a, b) are the mu_k weights of the two OTHER coords (the ones not on L_{ij}) projected onto the tangent of X.
- For Fermat-style F = x_0^p + x_1^p + x_2^q + x_3^q in P(w, w, w*p/q, w*p/q): the singular points at L_{23} ∩ X have type 1/k(1, 1), NOT Du Val A_{k-1}. The 1/k(1, 1) singularities have HJ chain [k] (single (-k)-curve) and K^2 correction (k-2)^2/k. This typically gives ρ(X) > 1.
- To achieve ρ(X) = 1, you need either:
  (i) Du Val (A_n, D_n, E_n) singularities everywhere (these are crepant, contribute 0 to K^2 correction). For A_{k-1} at a stratum point, the two "tangent" coords must have OPPOSITE mu_k weights (one weight 1, other weight k-1 mod k after standardization).
  (ii) A specific numerical balance: ρ(X) = 10 - K_res^2 - R, where K_res^2 = K_X^2 - Σ corrections, and R = sum of HJ chain lengths.
  (iii) NON-Fermat polynomial structure that breaks the symmetry between "other coords" at singular strata.

The verifier returns the full ρ-computation in its feedback. Use it to diagnose which singular points have non-Du-Val types and adjust.

Use Method B (weighted hypersurface or weighted complete intersection in P(w) over Z/3).

Structure your response as:

## Approach
[1-2 paragraphs explaining your construction]

## Singular point count
[Show explicitly: for each singular stratum (pair of coordinates with gcd of weights > 1), compute the intersection number with X and verify the zeros are over F_3-bar. For coordinate points, verify whether they are ON X or OFF X.]

## Answer
Weights: [w_0, w_1, ...]
Equation: <single weight-homogeneous polynomial in x0, x1, ...>
(or, for CI of 2)
Weights: [w_0, w_1, ...]
F1: <polynomial>
F2: <polynomial>

CRITICAL: use plain ASCII variables x0, x1, x2, x3, x4 (no subscripts, no LaTeX). Use ^ for exponentiation and * for multiplication.
"""

PROBLEM_PROMPT = """Working in characteristic 3, produce an example of a klt del Pezzo surface X with Picard number rho(X)=1 and with at least {N_sing} singular points, using Method B (weighted hypersurface or complete intersection).

Constraints:
- Working over F_3 (Z/3).
- Choose weights all coprime to 3 (tame).
- P(w) must be well-formed (gcd of any n-1 weights = 1).
- Fano index = sum(weights) - sum(degrees) > 0.
- Affine cone must be smooth outside origin (quasi-smoothness ⇒ all singularities of X are cyclic-quotient klt singularities).
- The surface X has Picard rho=1 (typically holds automatically for quasi-smooth weighted CIs in well-formed P(w)).
- Number of singular points of X = sum over singular strata (coord pts with weight > 1 + lines with gcd of pair of weights > 1) of (X ∩ stratum) point count, over F_3-bar.

The answer format will be verified by Macaulay2."""

REVISION_PROMPT = """Your previous attempt was rejected by the Macaulay2 verifier. Here is the verifier output:

{verifier_feedback}

Your previous answer was:
Weights: {weights}
Equations: {eqns}

Please diagnose the specific failure and propose a CORRECTED candidate. Focus on what the verifier explicitly flagged. Use the same response format (## Approach, ## Singular point count, ## Answer).
"""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run_one_trial(model_key, n_sing_required, seed=42, extra_user_prompt="", revisions=1, log_dir=None):
    """One trial: generate → verify → optionally revise."""
    trial_log = {"model": model_key, "seed": seed, "n_sing_required": n_sing_required, "rounds": []}
    user_prompt = PROBLEM_PROMPT.format(N_sing=n_sing_required)
    if extra_user_prompt:
        user_prompt = extra_user_prompt + "\n\n" + user_prompt

    cur_user = user_prompt
    last_extracted = None

    for round_idx in range(1 + revisions):
        round_log = {"round": round_idx}
        t0 = time.time()
        try:
            content, reasoning_text, usage = model_chat(model_key, GENERATOR_SYSTEM, cur_user)
        except Exception as e:
            round_log["error"] = f"generation error: {e}"
            round_log["elapsed_s"] = round(time.time() - t0, 1)
            trial_log["rounds"].append(round_log)
            break
        round_log["elapsed_s"] = round(time.time() - t0, 1)
        round_log["usage"] = usage
        round_log["content"] = content
        round_log["reasoning"] = reasoning_text

        # Extract answer (regex first, fall back to judge if regex fails)
        extracted, extract_method = extract_with_fallback(content)
        round_log["extracted"] = extracted
        round_log["extract_method"] = extract_method
        if not extracted:
            round_log["error"] = "Failed to extract Method B answer (both regex and judge)"
            trial_log["rounds"].append(round_log)
            break

        # Verify with M2
        t1 = time.time()
        v = verify_method_b(weights=extracted["weights"], eqns=extracted["eqns"], n_sing_required=n_sing_required)
        v["m2_elapsed_s"] = round(time.time() - t1, 1)
        round_log["verification"] = v
        last_extracted = extracted

        trial_log["rounds"].append(round_log)

        if v["verdict"] == "PASS":
            trial_log["status"] = "PASS"
            break

        # Decide if we should revise
        if round_idx < revisions and v["score"] >= 2:
            feedback = feedback_for_revision(v)
            cur_user = user_prompt + "\n\n" + REVISION_PROMPT.format(
                verifier_feedback=feedback,
                weights=extracted["weights"],
                eqns=extracted["eqns"],
            )
        else:
            break

    if "status" not in trial_log:
        trial_log["status"] = "FAIL"

    # Best score across rounds
    best_score = max((r.get("verification", {}).get("score", 0) for r in trial_log["rounds"]), default=0)
    trial_log["best_score"] = best_score

    return trial_log


def log_jsonl(record, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


# Quick self-test
if __name__ == "__main__":
    # Test extraction
    sample = """## Approach
We use the weighted projective space P(2,2,5,5).

## Answer
Weights: [2, 2, 5, 5]
Equation: x0^5 + x1^5 + x2^2 + x3^2
"""
    print("Extraction test:")
    print(extract_method_b(sample))
