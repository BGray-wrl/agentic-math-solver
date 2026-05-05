#!/usr/bin/env python3
"""
Re-run the 6 v4-flash trials whose original ideate call returned non-JSON,
silently falling back to default-N placeholder ideas.

Targets:
  seed_full   (judge = gemini-3-flash, matches Phase 3): first-proof-4-official
  seed_generate (judge = v4-pro, matches Phase 1):
    erdos-1051, erdos-333, erdos-654, first-proof-4-official, ramsey-hypergraphs

Mitigation: do_ideate retries up to 3 attempts before giving up — if v4-flash
emits prose on attempt 1, we re-prompt with the same call.

Output: per-trial JSONs saved to a fresh run dir; manifest.jsonl appended.
Key:    OPENROUTER_API_KEY_seedgen (single, no rotation).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import litellm
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from problemset_70 import load_70_problems, SPECIAL_10  # noqa: E402

load_dotenv()
KEY = os.getenv("OPENROUTER_API_KEY_seedgen")
if not KEY:
    raise SystemExit("OPENROUTER_API_KEY_seedgen not set")

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"

MODEL = "openrouter/deepseek/deepseek-v4-flash"
MODEL_PRICE = 0.28

# Judges per mode
JUDGE_GEMINI = "openrouter/google/gemini-3-flash-preview"
JUDGE_GEMINI_PRICE = 3.00
JUDGE_V4PRO  = "openrouter/deepseek/deepseek-v4-pro"
JUDGE_V4PRO_PRICE = 0.87

NUM_IDEAS = 3
ITERATIONS = 2
MAX_TOKENS_GEN     = 65536
MAX_TOKENS_VERIFY  = 65536
MAX_TOKENS_REVISE  = 65536
MAX_TOKENS_IDEATE  = 16000
MAX_TOKENS_JUDGE   = 131072    # higher for v4-pro judge to avoid truncation
TIMEOUT = 1800
INNER_WORKERS = 3              # parallel branches per trial
OUTER_WORKERS = 6              # one per trial (we have 6)

# Re-run targets
TARGETS = [
    ("seed_full",     "first-proof-4-official"),
    ("seed_generate", "erdos-1051"),
    ("seed_generate", "erdos-333"),
    ("seed_generate", "erdos-654"),
    ("seed_generate", "first-proof-4-official"),
    ("seed_generate", "ramsey-hypergraphs"),
]

RUN_DIR = (
    Path(__file__).parent / "results"
    / f"rerun_parse_failures_v4flash_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
)
RUN_DIR.mkdir(parents=True, exist_ok=True)


# === call_model with reasoning fallback (works for any model) ===

def call_model(model, system, user, max_tokens, retries=2, backoff=5.0,
               extra_body=None) -> tuple[str, dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    last_err = None
    for attempt in range(retries + 1):
        try:
            kwargs = dict(
                model=model, messages=messages,
                max_tokens=max_tokens, api_key=KEY, timeout=TIMEOUT,
            )
            if extra_body:
                kwargs["extra_body"] = extra_body
            resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message
            text = msg.content
            if not text:
                text = getattr(msg, "reasoning_content", "") or ""
            usage = getattr(resp, "usage", None)
            usage_dict = {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
            }
            if not text:
                raise ValueError(f"{model} returned empty content+reasoning")
            return text, usage_dict
        except Exception as e:
            last_err = e
            msg = str(e)
            if "402" in msg or "Insufficient credits" in msg or "Key limit exceeded" in msg:
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[retry] {model.split('/')[-1]} attempt {attempt+1} failed: {e} - retry in {wait:.0f}s",
                      flush=True)
                time.sleep(wait)
    raise last_err


# === pipeline calls ===

def load_prompt(name): return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()
PROMPTS = {
    "ideator":         load_prompt("ideator.md"),
    "generator_seeded": load_prompt("generator_seeded.md"),
    "verifier":        load_prompt("verifier.md"),
    "reviser":         load_prompt("reviser.md"),
    "judge_gt":        load_prompt("judge_gt.md"),
}


def parse_ideas(text):
    def _fix(t): return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', t)
    for pattern in (r"```json\s*(\[.*?\])\s*```", r"(\[.*\])"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            for attempt in (m.group(1), _fix(m.group(1))):
                try:
                    out = json.loads(attempt)
                    if isinstance(out, list) and out and all(isinstance(i, dict) for i in out):
                        return out
                except json.JSONDecodeError:
                    continue
    return None


def do_ideate_with_retry(problem_text, calls):
    """Up to 3 ideate attempts before falling back to default-N."""
    prompt = PROMPTS["ideator"].replace("{problem}", problem_text).replace("{num_ideas}", str(NUM_IDEAS))
    last_text = ""
    for attempt in range(3):
        text, usage = call_model(MODEL, "", prompt, MAX_TOKENS_IDEATE)
        cost = MODEL_PRICE * usage["total_tokens"] / 1_000_000
        calls.append({"kind": f"ideate(attempt {attempt+1})", "model": MODEL, "usage": usage,
                      "cost_usd": round(cost, 6), "response_text": text})
        ideas = parse_ideas(text)
        last_text = text
        if ideas:
            return ideas[:NUM_IDEAS], text, False
    print(f"  [WARN] ideate parse failed after 3 attempts; falling back to defaults", flush=True)
    return ([{"name": f"default-{i}", "description": "Solve naturally."} for i in range(NUM_IDEAS)],
            last_text, True)


def parse_score(t):
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", t, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", t, re.I)
    if m: return int(m.group(1))
    return None


def do_seeded_generate(problem_text, idea, calls):
    sys_filled = PROMPTS["generator_seeded"].replace(
        "{idea}", f"**{idea.get('name','')}**: {idea.get('description','')}")
    text, usage = call_model(MODEL, sys_filled, problem_text, MAX_TOKENS_GEN)
    cost = MODEL_PRICE * usage["total_tokens"] / 1_000_000
    calls.append({"kind": "seeded_generate", "model": MODEL, "usage": usage,
                  "cost_usd": round(cost, 6), "response_text": text})
    return text


def do_verify(problem_text, solution, calls):
    sys_part, _, content_part = PROMPTS["verifier"].partition("\n**PROBLEM:**\n")
    if not _: sys_part, content_part = "", PROMPTS["verifier"]
    else: content_part = "**PROBLEM:**\n" + content_part
    user = content_part.replace("{problem}", problem_text).replace("{solution}", solution)
    text, usage = call_model(MODEL, sys_part, user, MAX_TOKENS_VERIFY)
    cost = MODEL_PRICE * usage["total_tokens"] / 1_000_000
    calls.append({"kind": "verify", "model": MODEL, "usage": usage,
                  "cost_usd": round(cost, 6), "response_text": text})
    return text


def do_revise(problem_text, solution, critique, calls):
    sys_part, _, content_part = PROMPTS["reviser"].partition("\n**PROBLEM:**\n")
    if not _: sys_part, content_part = "", PROMPTS["reviser"]
    else: content_part = "**PROBLEM:**\n" + content_part
    user = (content_part.replace("{problem}", problem_text)
            .replace("{solution}", solution).replace("{critique}", critique))
    text, usage = call_model(MODEL, sys_part, user, MAX_TOKENS_REVISE)
    cost = MODEL_PRICE * usage["total_tokens"] / 1_000_000
    calls.append({"kind": "revise", "model": MODEL, "usage": usage,
                  "cost_usd": round(cost, 6), "response_text": text})
    return text


def do_judge(problem_text, candidate, ground_truth, judge_model, judge_price, calls):
    user = (PROMPTS["judge_gt"].replace("{problem}", problem_text)
            .replace("{ground_truth}", ground_truth).replace("{candidate}", candidate))
    extra_body = None
    if judge_model == JUDGE_V4PRO:
        extra_body = {"reasoning": {"max_tokens": 100000}}
    text, usage = call_model(judge_model, "", user, MAX_TOKENS_JUDGE, extra_body=extra_body)
    cost = judge_price * usage["total_tokens"] / 1_000_000
    calls.append({"kind": "judge", "model": judge_model, "usage": usage,
                  "cost_usd": round(cost, 6), "response_text": text})
    return text, parse_score(text)


# === branch + trial runners ===

def run_branch_seed_full(problem, idea, judge_model, judge_price):
    calls = []
    sol = do_seeded_generate(problem["text"], idea, calls)
    stopped_early = False
    loop_log = []
    for i in range(ITERATIONS):
        critique = do_verify(problem["text"], sol, calls)
        if "VERDICT: correct" in critique:
            stopped_early = True
            loop_log.append({"iteration": i+1, "verdict": "correct"})
            break
        new = do_revise(problem["text"], sol, critique, calls)
        loop_log.append({"iteration": i+1, "verdict": "issues_found"})
        sol = new
    verdict, score = do_judge(problem["text"], sol, problem["ground_truth"],
                               judge_model, judge_price, calls)
    return {"idea": idea, "final_solution": sol, "verdict": verdict, "score": score,
            "loop_log": loop_log, "stopped_early": stopped_early, "calls": calls}


def run_branch_seed_gen(problem, idea, judge_model, judge_price):
    calls = []
    sol = do_seeded_generate(problem["text"], idea, calls)
    verdict, score = do_judge(problem["text"], sol, problem["ground_truth"],
                               judge_model, judge_price, calls)
    return {"idea": idea, "solution": sol, "verdict": verdict, "score": score, "calls": calls}


def run_trial(mode, pid, problem):
    judge_model, judge_price = ((JUDGE_GEMINI, JUDGE_GEMINI_PRICE) if mode == "seed_full"
                                 else (JUDGE_V4PRO, JUDGE_V4PRO_PRICE))
    print(f"[{datetime.now().strftime('%H:%M:%S')}] start {mode} {pid}", flush=True)
    t0 = time.time()
    outer_calls = []
    try:
        ideas, ideate_text, used_default = do_ideate_with_retry(problem["text"], outer_calls)
    except Exception as e:
        print(f"[ERR ideate] {pid}: {e}", flush=True)
        return None

    branch_runner = run_branch_seed_full if mode == "seed_full" else run_branch_seed_gen
    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        branches = list(ex.map(lambda i: branch_runner(problem, i, judge_model, judge_price), ideas))

    for i, b in enumerate(branches):
        b["idea_idx"] = i
        outer_calls.extend(b.pop("calls"))
    scored = [b for b in branches if b.get("score") is not None]
    best = max(scored, key=lambda b: b["score"]) if scored else None
    elapsed = round(time.time() - t0, 1)
    cost = round(sum(c["cost_usd"] for c in outer_calls), 6)
    trial = {
        "mode":         mode,
        "model":        MODEL,
        "judge":        judge_model,
        "problem_id":   pid,
        "score":        (best or {}).get("score"),
        "best_solution": (best or {}).get("final_solution") or (best or {}).get("solution"),
        "best_verdict": (best or {}).get("verdict"),
        "branches":     branches,
        "mode_extras": {
            "ideas":           ideas,
            "ideate_response": ideate_text,
            "used_default_ideas": used_default,
            "iterations": ITERATIONS if mode == "seed_full" else 0,
        },
        "calls":      outer_calls,
        "cost_usd":   cost,
        "elapsed_s":  elapsed,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    out = RUN_DIR / f"{mode}__{pid}.json"
    tmp = out.with_suffix(".json.tmp")
    with open(tmp, "w") as f: json.dump(trial, f, indent=2, ensure_ascii=False)
    tmp.replace(out)
    fb_tag = " (still fell back to defaults!)" if used_default else ""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] done  {mode} {pid}  "
          f"score={trial['score']}/7  ${cost:.4f}  {elapsed}s{fb_tag}", flush=True)
    return trial


def main():
    problems = load_70_problems()
    print(f"Re-running {len(TARGETS)} parse-failure trials")
    print(f"Output: {RUN_DIR}\n", flush=True)
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=OUTER_WORKERS) as ex:
        results = list(ex.map(lambda mp: run_trial(mp[0], mp[1], problems[mp[1]]), TARGETS))
    wall = round(time.time() - t0, 1)
    cost = sum((r or {}).get("cost_usd", 0) for r in results)
    print(f"\nDone. Wall {wall}s. Cost ${cost:.3f}.")
    summary = []
    for r, t in zip(results, TARGETS):
        if r is None:
            summary.append({"mode": t[0], "pid": t[1], "result": "ERROR"})
        else:
            summary.append({
                "mode": r["mode"], "pid": r["problem_id"],
                "score": r["score"],
                "used_default_ideas": r["mode_extras"]["used_default_ideas"],
                "ideas": [i.get("name") for i in r["mode_extras"]["ideas"]],
                "cost_usd": r["cost_usd"],
            })
    print("\nSummary:")
    for s in summary:
        print(f"  {s}")
    with open(RUN_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
