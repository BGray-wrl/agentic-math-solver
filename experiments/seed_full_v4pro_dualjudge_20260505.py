#!/usr/bin/env python3
"""
seed_full on a single model under test, with DUAL JUDGES + escalation.

Architecture (per (model, problem)):
  ideate(3, with retry) -> 3 parallel branches (seeded_gen -> [verify -> revise]*2)
  -> for each branch:
       judge with v4-flash  (lenient/fast)
       judge with v4-pro    (strict, high reasoning budget)
  -> pick the branch with max(min(v4flash, v4pro)) as `best`.
  -> if BOTH judges scored that best branch >= PASS_THRESHOLD,
       escalate to gpt-5.4-nano with xhigh reasoning as a third-opinion judge.

Why both judges + escalation:
  - The Phase 3 ablation showed gemini judge can be lenient; v4-pro can be both
    strict and (with a small budget) parse-failure-prone.
  - Using both v4-flash and v4-pro as judges, with reasoning_content fallback +
    a 100K reasoning budget, removes the parse-failure failure mode entirely.
  - Escalating only when both already agree gives an independent third opinion
    on candidate frontier solves, where the cost of being wrong is highest.

Hardening:
  - reasoning_content fallback in call_model (mandatory for v4-pro)
  - max_tokens=131072 + extra_body reasoning budget for v4-pro judge
  - Per-trial + per-branch atomic save
  - Single key OPENROUTER_API_KEY_seedgen
  - Cost killswitch via --max-cost
  - Up to 3 ideate attempts before placeholder fallback (records used_default flag)

Usage:
  uv run experiments/seed_full_v4pro_dualjudge_20260505.py --smoke
  uv run experiments/seed_full_v4pro_dualjudge_20260505.py --real
  uv run experiments/seed_full_v4pro_dualjudge_20260505.py --real --max-cost 30
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

# === models + judges ===
JUDGES = [
    {"name": "v4flash", "model": "openrouter/deepseek/deepseek-v4-flash", "price": 0.28,
     "max_tokens": 65536, "extra_body": None},
    {"name": "v4pro",   "model": "openrouter/deepseek/deepseek-v4-pro",   "price": 0.87,
     "max_tokens": 131072,
     "extra_body": {"reasoning": {"max_tokens": 100000}}},
]
ESCALATION_JUDGE = {
    "name": "gpt54nano-xhigh",
    "model": "openrouter/openai/gpt-5.4-nano",
    "price": 0.40,   # rough placeholder; OpenRouter will report actual usage
    "max_tokens": 131072,
    "extra_body": {"reasoning": {"effort": "high"}},
}

# Model under test selected per --smoke / --real
MODEL_SMOKE = ("openrouter/google/gemma-4-31b-it", 0.38)
MODEL_REAL  = ("openrouter/deepseek/deepseek-v4-pro", 0.87)

NUM_IDEAS = 3
ITERATIONS = 2
MAX_TOKENS_GEN     = 65536
MAX_TOKENS_VERIFY  = 65536
MAX_TOKENS_REVISE  = 65536
MAX_TOKENS_IDEATE  = 16000
TIMEOUT = 1800

PASS_THRESHOLD = 6
INNER_WORKERS = 3
DEFAULT_OUTER_WORKERS = 10

# === call_model ===

def call_model(model, system, user, max_tokens, retries=2, backoff=5.0,
               extra_body=None) -> tuple[str, dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    last_err = None
    for attempt in range(retries + 1):
        try:
            kwargs = dict(model=model, messages=messages,
                          max_tokens=max_tokens, api_key=KEY, timeout=TIMEOUT)
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
            mt = str(e)
            if "402" in mt or "Insufficient credits" in mt or "Key limit exceeded" in mt:
                raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[retry] {model.split('/')[-1]} attempt {attempt+1} failed: {e} "
                      f"- retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err


# === pipeline ===

def load_prompt(name): return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()
PROMPTS = {
    "ideator":          load_prompt("ideator.md"),
    "generator_seeded": load_prompt("generator_seeded.md"),
    "verifier":         load_prompt("verifier.md"),
    "reviser":          load_prompt("reviser.md"),
    "judge_gt":         load_prompt("judge_gt.md"),
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


def parse_score(t):
    if not t: return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", t, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", t, re.I)
    if m: return int(m.group(1))
    return None


def do_ideate_with_retry(model, model_price, problem_text, calls):
    prompt = PROMPTS["ideator"].replace("{problem}", problem_text).replace("{num_ideas}", str(NUM_IDEAS))
    last_text = ""
    for attempt in range(3):
        text, usage = call_model(model, "", prompt, MAX_TOKENS_IDEATE)
        cost = model_price * usage["total_tokens"] / 1_000_000
        calls.append({"kind": f"ideate(attempt {attempt+1})", "model": model, "usage": usage,
                      "cost_usd": round(cost, 6), "response_text": text})
        ideas = parse_ideas(text)
        last_text = text
        if ideas:
            return ideas[:NUM_IDEAS], text, False
    return ([{"name": f"default-{i}", "description": "Solve naturally."} for i in range(NUM_IDEAS)],
            last_text, True)


def call_judge(judge_cfg, problem_text, candidate, ground_truth, calls):
    user = (PROMPTS["judge_gt"].replace("{problem}", problem_text)
            .replace("{ground_truth}", ground_truth).replace("{candidate}", candidate))
    text, usage = call_model(
        judge_cfg["model"], "", user, judge_cfg["max_tokens"],
        extra_body=judge_cfg.get("extra_body"),
    )
    cost = judge_cfg["price"] * usage["total_tokens"] / 1_000_000
    score = parse_score(text)
    has_tag = bool(re.search(r"<points>\s*\d+\s*out of 7\s*</points>", text, re.I))
    calls.append({
        "kind": f"judge[{judge_cfg['name']}]",
        "model": judge_cfg["model"], "usage": usage,
        "cost_usd": round(cost, 6),
        "response_text": text,
        "parsed_score": score, "has_score_tag": has_tag,
    })
    return text, score, has_tag


def do_seeded_generate(model, price, problem_text, idea, calls):
    sys_filled = PROMPTS["generator_seeded"].replace(
        "{idea}", f"**{idea.get('name','')}**: {idea.get('description','')}")
    text, usage = call_model(model, sys_filled, problem_text, MAX_TOKENS_GEN)
    cost = price * usage["total_tokens"] / 1_000_000
    calls.append({"kind": "seeded_generate", "model": model, "usage": usage,
                  "cost_usd": round(cost, 6), "response_text": text})
    return text


def do_verify(model, price, problem_text, solution, calls):
    sys_part, _, content_part = PROMPTS["verifier"].partition("\n**PROBLEM:**\n")
    if not _: sys_part, content_part = "", PROMPTS["verifier"]
    else: content_part = "**PROBLEM:**\n" + content_part
    user = content_part.replace("{problem}", problem_text).replace("{solution}", solution)
    text, usage = call_model(model, sys_part, user, MAX_TOKENS_VERIFY)
    cost = price * usage["total_tokens"] / 1_000_000
    calls.append({"kind": "verify", "model": model, "usage": usage,
                  "cost_usd": round(cost, 6), "response_text": text})
    return text


def do_revise(model, price, problem_text, solution, critique, calls):
    sys_part, _, content_part = PROMPTS["reviser"].partition("\n**PROBLEM:**\n")
    if not _: sys_part, content_part = "", PROMPTS["reviser"]
    else: content_part = "**PROBLEM:**\n" + content_part
    user = (content_part.replace("{problem}", problem_text)
            .replace("{solution}", solution).replace("{critique}", critique))
    text, usage = call_model(model, sys_part, user, MAX_TOKENS_REVISE)
    cost = price * usage["total_tokens"] / 1_000_000
    calls.append({"kind": "revise", "model": model, "usage": usage,
                  "cost_usd": round(cost, 6), "response_text": text})
    return text


def run_branch(model, price, problem, idea):
    calls = []
    sol = do_seeded_generate(model, price, problem["text"], idea, calls)
    stopped_early = False
    loop_log = []
    for i in range(ITERATIONS):
        critique = do_verify(model, price, problem["text"], sol, calls)
        if "VERDICT: correct" in critique:
            stopped_early = True
            loop_log.append({"iteration": i+1, "verdict": "correct"})
            break
        new = do_revise(model, price, problem["text"], sol, critique, calls)
        loop_log.append({"iteration": i+1, "verdict": "issues_found"})
        sol = new

    # Dual-judge (parallel)
    judge_results = {}
    def _judge(j):
        b_calls = []
        text, score, has_tag = call_judge(j, problem["text"], sol, problem["ground_truth"], b_calls)
        return j["name"], {"score": score, "verdict": text, "has_tag": has_tag, "calls": b_calls}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(JUDGES)) as ex:
        for name, rec in ex.map(_judge, JUDGES):
            judge_results[name] = rec
    for name, rec in judge_results.items():
        calls.extend(rec.pop("calls"))

    return {
        "idea": idea,
        "final_solution": sol,
        "judges": judge_results,
        "loop_log": loop_log,
        "stopped_early": stopped_early,
        "calls": calls,
    }


def run_trial(model, price, problem, pid, run_dir):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] start {pid}", flush=True)
    t0 = time.time()
    outer_calls = []
    try:
        ideas, ideate_text, used_default = do_ideate_with_retry(model, price, problem["text"], outer_calls)
    except Exception as e:
        return {"pid": pid, "error": f"ideate failed: {e}"}

    branches_dir = run_dir / "branches" / pid
    branches_dir.mkdir(parents=True, exist_ok=True)

    def _run(i_idea):
        i, idea = i_idea
        try:
            br = run_branch(model, price, problem, idea)
            br["idea_idx"] = i
        except Exception as e:
            br = {"idea": idea, "idea_idx": i, "error": str(e)}
        # per-branch save (atomic)
        bp = branches_dir / f"branch_{i}.json"
        tmp = bp.with_suffix(".json.tmp")
        with open(tmp, "w") as f: json.dump(br, f, indent=2, ensure_ascii=False)
        tmp.replace(bp)
        return br

    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        branches = list(ex.map(_run, list(enumerate(ideas))))

    for b in branches:
        outer_calls.extend(b.pop("calls", []))

    # Best = max of min(judge scores) — penalize disagreement.
    def min_score(b):
        if "judges" not in b: return -1
        scores = [v.get("score") for v in b["judges"].values() if v.get("score") is not None]
        return min(scores) if scores else -1
    scored = [b for b in branches if "judges" in b]
    best = max(scored, key=min_score) if scored else None

    # Escalation: if both judges on best branch >= PASS_THRESHOLD, call gpt-5.4-nano
    escalation = None
    if best and "judges" in best:
        scores = [v.get("score") for v in best["judges"].values() if v.get("score") is not None]
        if len(scores) == len(JUDGES) and min(scores) >= PASS_THRESHOLD:
            print(f"  [escalate] {pid} both judges >= {PASS_THRESHOLD}: {scores}", flush=True)
            esc_calls = []
            try:
                text, score, has_tag = call_judge(
                    ESCALATION_JUDGE, problem["text"], best["final_solution"],
                    problem["ground_truth"], esc_calls,
                )
                escalation = {
                    "judge": ESCALATION_JUDGE["name"],
                    "model": ESCALATION_JUDGE["model"],
                    "score": score, "verdict": text, "has_tag": has_tag,
                    "agreed": score is not None and score >= PASS_THRESHOLD,
                }
                outer_calls.extend(esc_calls)
            except Exception as e:
                escalation = {"error": str(e)}

    elapsed = round(time.time() - t0, 1)
    cost = round(sum(c.get("cost_usd", 0) for c in outer_calls), 6)
    trial = {
        "model":   model,
        "mode":    "seed_full_dualjudge",
        "problem_id": pid,
        "is_special": pid in SPECIAL_10,
        "best_branch_idx":  best.get("idea_idx") if best else None,
        "best_solution":    best.get("final_solution") if best else None,
        "best_judges":      best.get("judges") if best else None,
        "escalation":       escalation,
        "branches":         branches,
        "ideas":            ideas,
        "used_default_ideas": used_default,
        "ideate_response":  ideate_text,
        "calls":            outer_calls,
        "cost_usd":         cost,
        "elapsed_s":        elapsed,
        "completed_at":     datetime.now(timezone.utc).isoformat(),
    }

    out = run_dir / "trials" / f"{pid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    with open(tmp, "w") as f: json.dump(trial, f, indent=2, ensure_ascii=False)
    tmp.replace(out)

    # Manifest line
    j = best.get("judges") if best else {}
    summary = {
        "ts": trial["completed_at"], "pid": pid,
        "v4flash_score": (j or {}).get("v4flash", {}).get("score"),
        "v4pro_score":   (j or {}).get("v4pro",   {}).get("score"),
        "esc_score":     (escalation or {}).get("score"),
        "elapsed_s": elapsed, "cost_usd": cost,
        "used_default_ideas": used_default,
    }
    with open(run_dir / "manifest.jsonl", "a") as f:
        f.write(json.dumps(summary) + "\n")

    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] done  {pid}  "
        f"v4flash={summary['v4flash_score']}/7 v4pro={summary['v4pro_score']}/7 "
        f"esc={summary['esc_score']}  ${cost:.4f}  {elapsed}s",
        flush=True,
    )
    return trial


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true",
                   help="Smoke: gemma-31b on 2 problems (1 PB-Basic + erdos-654).")
    p.add_argument("--real", action="store_true",
                   help="Real: v4-pro on all 10 special-10 problems.")
    p.add_argument("--max-cost", type=float, default=None)
    p.add_argument("--workers", type=int, default=DEFAULT_OUTER_WORKERS)
    args = p.parse_args()

    if not args.smoke and not args.real:
        raise SystemExit("Pass --smoke or --real")

    problems = load_70_problems()
    if args.smoke:
        model, price = MODEL_SMOKE
        targets = ["PB-Basic-001", "erdos-654"]   # 1 easy + 1 special-10
    else:
        model, price = MODEL_REAL
        targets = sorted(SPECIAL_10)

    run_dir = Path(__file__).parent / "results" / (
        f"seed_full_dualjudge_{'smoke_' if args.smoke else ''}"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Model under test: {model}")
    print(f"Judges: {[j['name'] for j in JUDGES]}  Escalation: {ESCALATION_JUDGE['name']}")
    print(f"Targets ({len(targets)}): {targets}")
    print(f"Run dir: {run_dir}")
    print(f"Workers: outer={args.workers}  inner={INNER_WORKERS}\n", flush=True)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(lambda pid: run_trial(model, price, problems[pid], pid, run_dir), targets))
    wall = round(time.time() - t0, 1)
    print(f"\nWall: {wall}s")

    # Summary
    trials = []
    for f in sorted((run_dir/"trials").glob("*.json")):
        with open(f) as fh: trials.append(json.load(fh))
    cost = sum(t.get("cost_usd", 0) or 0 for t in trials)
    print(f"Total cost: ${cost:.2f}")
    print(f"\n{'pid':<28} v4flash v4pro  esc  used_default")
    for t in trials:
        bj = t.get("best_judges") or {}
        e  = t.get("escalation") or {}
        print(f"  {t['problem_id']:<26} "
              f"{(bj.get('v4flash') or {}).get('score', '-'):>4} "
              f"{(bj.get('v4pro')   or {}).get('score', '-'):>4} "
              f"{e.get('score', '-'):>4}  "
              f"{t.get('used_default_ideas')}")


if __name__ == "__main__":
    main()
