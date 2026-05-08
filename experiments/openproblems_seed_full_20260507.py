#!/usr/bin/env python3
"""
seed_full architecture on FrontierMath open problems.

Architecture: ideate(N) → N parallel branches of (seeded_generate → verify ↔ revise) → judge
Best-of-branches by judge score is reported.

Conditions (--condition):
  gemma_homogeneous  : ideator/gen/verify/revise = gemma-4-31b-it (xhigh) for all
  oss_homogeneous    : same with gpt-oss-120b (xhigh)
  roleswap_oss_verify: gemma everywhere except verifier=gpt-oss-120b (xhigh)

Judge: deepseek-v4-flash (cheap; consensus is a separate phase).

Usage:
  uv run experiments/openproblems_seed_full_20260507.py --condition gemma_homogeneous
  uv run experiments/openproblems_seed_full_20260507.py --condition roleswap_oss_verify --pids inverse-galois,arithmetic-kakeya
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, os, random, re, sys, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(str(ROOT / ".env"))

EXPERIMENT_NAME = "openproblems_seed_full_20260507"

OSS    = "openai/gpt-oss-120b"
GEMMA  = "google/gemma-4-31b-it"
JUDGE  = "deepseek/deepseek-v4-flash"

CONDITIONS = {
    "gemma_homogeneous":   {"ideator": GEMMA, "generator": GEMMA, "verifier": GEMMA, "reviser": GEMMA},
    "oss_homogeneous":     {"ideator": OSS,   "generator": OSS,   "verifier": OSS,   "reviser": OSS},
    "roleswap_oss_verify": {"ideator": GEMMA, "generator": GEMMA, "verifier": OSS,   "reviser": GEMMA},
}

REASONING_BY_MODEL = {
    OSS:   {"effort": "xhigh"},
    GEMMA: {"effort": "xhigh"},
    JUDGE: None,
}

# Per-model semaphores
_model_sem = {
    GEMMA: threading.Semaphore(8),
    OSS:   threading.Semaphore(40),
    JUDGE: threading.Semaphore(60),
}

PROBLEMS_CSV = ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv"
EXCLUDE_PIDS = {"ramsey-hypergraphs"}
SKIP_PAIRS = {("small-diophantine", "full_problem")}

NUM_IDEAS  = 3
ITERATIONS = 2

MAX_TOKENS_IDEATE = 8000
MAX_TOKENS_GEN    = 24000
MAX_TOKENS_VR     = 16000
MAX_TOKENS_JUDGE  = 4000

GEN_HTTP_TIMEOUT = 900
JUDGE_HTTP_TIMEOUT = 180

MAX_WORKERS = 30  # outer (problems × seeds)
INNER_WORKERS = 3  # per-problem branch parallelism

API_KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k]

_lock = threading.Lock()
_idx = [0]
def next_key():
    with _lock:
        k = API_KEYS[_idx[0] % len(API_KEYS)]
        _idx[0] += 1
        return k

def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts():  return datetime.now(timezone.utc).strftime("%H:%M:%S")


def or_chat(model, messages, max_tokens, key, http_timeout, reasoning=None,
            retries=6, backoff=8.0):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning is not None: body["reasoning"] = reasoning
    last_err = None
    sem = _model_sem.get(model)
    for attempt in range(retries + 1):
        if sem: sem.acquire()
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"},
                json=body, timeout=http_timeout,
            )
        finally:
            if sem: sem.release()
        try:
            if r.status_code == 402: raise RuntimeError(f"402: {r.text[:200]}")
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace('.','',1).isdigit() else min(backoff * (2 ** attempt), 90.0)
                if attempt < retries:
                    time.sleep(wait + (attempt * 0.3))
                    continue
                raise RuntimeError(f"429 after retries")
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content") or choice.get("reasoning") or choice.get("reasoning_content")
            if not content: raise ValueError("empty response")
            usage = j.get("usage", {}) or {}
            return content, {"cost": float(usage.get("cost", 0) or 0),
                             "completion_tokens": int(usage.get("completion_tokens", 0) or 0)}
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            if attempt < retries: time.sleep(backoff * (2 ** min(attempt, 4)))
    raise last_err


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
IDEATOR_SYSTEM = """You are an expert mathematician working on research-level open problems.
Generate {n} distinct high-level approaches for solving the problem. Each approach should be a genuinely different strategy.

Output a JSON array inside a ```json block, with each entry having:
- "name": short label (2-5 words)
- "description": 2-4 sentence detailed plan, including specific construction techniques, references to known results, or algorithmic ideas

The user will pick one approach to fully execute.

```json
[
  {{"name": "...", "description": "..."}},
  ...
]
```
"""

GENERATOR_SEEDED_SYSTEM = """You are a research mathematician working on an open / unsolved problem.
The problem asks for an EXPLICIT CONSTRUCTION, EXAMPLE, or ALGORITHM.
The output will be checked by an automated verifier, so your final answer must EXACTLY match the format requested in the problem.

A specific approach has been suggested. Pursue this approach fully. If it leads to a dead end, say so explicitly.

## Suggested approach
{idea}

## Output structure

## Approach
[Brief: how you executed the suggested idea]

## Answer
[The final answer in EXACTLY the format the problem requests, and nothing else.
 If the problem requests a Python script, provide a complete, runnable script.
 If the problem requests a CSV, provide the CSV with no surrounding prose.]
"""

VERIFIER_SYSTEM = """You are an expert mathematician verifying a candidate solution to a research-level construction problem.
Identify CONCRETE FLAWS that would prevent it from passing a programmatic verifier:
- Output-format errors (wrong format/syntax/sections)
- Mathematical errors (wrong values, broken constraints, dimension mismatch)
- Off-by-one or sign errors
- Missing required pieces

Be specific: cite the exact location of the flaw and what should be there.

If the solution looks fully correct and well-formatted, end with: VERDICT: correct
If issues are found, end with: VERDICT: issues_found
"""

REVISER_SYSTEM = """You are an expert mathematician revising a candidate solution to a research-level construction problem based on verifier feedback.

Address EVERY flaw the verifier identified. Re-output the FULL solution.
Make sure the FINAL answer is in EXACTLY the format the problem specifies.

Structure:

## Approach
[Brief: what you changed and why]

## Answer
[Final answer in exactly the requested format, nothing else]
"""

JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate solution to a research-level open problem.
Classify based on:
* **correct:** Construction/algorithm appears fully correct AND in requested format.
* **almost:** Core construction looks right but has a small format issue, off-by-one, or minor bug.
* **partial:** Meaningful mathematical progress, incomplete or significantly flawed.
* **incorrect:** No real progress, refusal, or unparseable.

Output reasoning, then on a final line:
CLASSIFICATION: <correct|almost|partial|incorrect>

---

**PROBLEM:**
{problem}

**CANDIDATE SOLUTION:**
{candidate}
"""

CLASSIF_RE = re.compile(r"CLASSIFICATION:\s*(correct|almost|partial|incorrect)", re.I)
SCORE_MAP = {"correct": 3, "almost": 2, "partial": 1, "incorrect": 0}
def parse_classification(text):
    m = CLASSIF_RE.search(text or "")
    if m: return m.group(1).lower()
    low = (text or "").lower()
    for lab in ("correct","almost","partial","incorrect"):
        if lab in low: return lab
    return "incorrect"


def parse_ideas(text, n):
    """Extract ideas from generator response. Falls back to a single generic idea."""
    for pat in [r"```json\s*(\[.*?\])\s*```", r"(\[.*\])"]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                ideas = json.loads(m.group(1))
                if isinstance(ideas, list) and ideas:
                    return ideas[:n]
            except json.JSONDecodeError:
                fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', m.group(1))
                try:
                    ideas = json.loads(fixed)
                    if isinstance(ideas, list) and ideas: return ideas[:n]
                except: pass
    return [{"name": "Direct attempt", "description": "Attempt the problem with the most direct construction."}]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run_branch(idea, problem, models, log):
    """Run seeded_generate → verify ↔ revise loop for one idea. Return final candidate + history."""
    pid = problem["problem_id"]; ptype = problem["prompt_type"]
    cost = 0.0
    history = []

    # Seeded generate
    try:
        gen_text, gmeta = or_chat(
            model=models["generator"],
            messages=[
                {"role":"system","content": GENERATOR_SEEDED_SYSTEM.replace("{idea}", json.dumps(idea))},
                {"role":"user","content": problem["prompt"]},
            ],
            max_tokens=MAX_TOKENS_GEN, key=next_key(), http_timeout=GEN_HTTP_TIMEOUT,
            reasoning=REASONING_BY_MODEL.get(models["generator"]),
        )
        cost += gmeta["cost"]
        candidate = gen_text
        history.append({"phase":"generate","text":gen_text,"cost":gmeta["cost"]})
    except Exception as e:
        return {"idea": idea, "error": f"gen: {e}", "candidate": None, "history": history, "cost": cost}

    # Verify-revise loop
    for i in range(ITERATIONS):
        try:
            v_text, vmeta = or_chat(
                model=models["verifier"],
                messages=[
                    {"role":"system","content": VERIFIER_SYSTEM},
                    {"role":"user","content": f"**PROBLEM:**\n{problem['prompt']}\n\n**CANDIDATE:**\n{candidate}"},
                ],
                max_tokens=MAX_TOKENS_VR, key=next_key(), http_timeout=GEN_HTTP_TIMEOUT,
                reasoning=REASONING_BY_MODEL.get(models["verifier"]),
            )
            cost += vmeta["cost"]
            history.append({"phase":f"verify_{i+1}","text":v_text,"cost":vmeta["cost"]})
        except Exception as e:
            history.append({"phase":f"verify_{i+1}","error":str(e)})
            break
        if "VERDICT: correct" in v_text:
            break
        try:
            r_text, rmeta = or_chat(
                model=models["reviser"],
                messages=[
                    {"role":"system","content": REVISER_SYSTEM},
                    {"role":"user","content": f"**PROBLEM:**\n{problem['prompt']}\n\n**PREVIOUS CANDIDATE:**\n{candidate}\n\n**FEEDBACK:**\n{v_text}"},
                ],
                max_tokens=MAX_TOKENS_VR, key=next_key(), http_timeout=GEN_HTTP_TIMEOUT,
                reasoning=REASONING_BY_MODEL.get(models["reviser"]),
            )
            cost += rmeta["cost"]
            history.append({"phase":f"revise_{i+1}","text":r_text,"cost":rmeta["cost"]})
            candidate = r_text
        except Exception as e:
            history.append({"phase":f"revise_{i+1}","error":str(e)})
            break

    return {"idea": idea, "candidate": candidate, "history": history, "cost": cost}


def run_problem(problem, models, condition, seed, log_path, log_lock):
    pid = problem["problem_id"]; ptype = problem["prompt_type"]
    short_cond = condition
    tag = f"[{pid}|{ptype}|{short_cond}|seed={seed}]"
    print(f"[{_ts()}] {tag} start", flush=True)
    t0 = time.time()
    cost = 0.0

    # Ideate
    try:
        ideator_sys = IDEATOR_SYSTEM.replace("{n}", str(NUM_IDEAS))
        idea_text, imeta = or_chat(
            model=models["ideator"],
            messages=[
                {"role":"system","content": ideator_sys},
                {"role":"user","content": problem["prompt"]},
            ],
            max_tokens=MAX_TOKENS_IDEATE, key=next_key(), http_timeout=GEN_HTTP_TIMEOUT,
            reasoning=REASONING_BY_MODEL.get(models["ideator"]),
        )
        cost += imeta["cost"]
        ideas = parse_ideas(idea_text, NUM_IDEAS)
    except Exception as e:
        print(f"[{_ts()}] {tag} IDEATE FAIL: {e}", flush=True)
        return {"problem_id": pid, "prompt_type": ptype, "condition": condition, "seed": seed, "error": f"ideate: {e}"}

    # Run branches in parallel
    branches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        futs = {ex.submit(run_branch, idea, problem, models, log_path): idea for idea in ideas}
        for fut in concurrent.futures.as_completed(futs):
            try: branches.append(fut.result())
            except Exception as e:
                branches.append({"idea": futs[fut], "error": str(e)})
    cost += sum(b.get("cost",0) for b in branches)

    # Judge each branch
    for b in branches:
        if not b.get("candidate"):
            b["label"] = "incorrect"; b["score"] = 0; continue
        try:
            j_text, jmeta = or_chat(
                model=JUDGE,
                messages=[{"role":"user","content": JUDGE_SYSTEM
                            .replace("{problem}", problem["prompt"])
                            .replace("{candidate}", b["candidate"])}],
                max_tokens=MAX_TOKENS_JUDGE, key=next_key(), http_timeout=JUDGE_HTTP_TIMEOUT, reasoning=None,
            )
            cost += jmeta["cost"]
            b["label"] = parse_classification(j_text)
            b["score"] = SCORE_MAP[b["label"]]
            b["judge_text"] = j_text
        except Exception as e:
            b["label"] = "ERROR"; b["score"] = 0; b["judge_error"] = str(e)

    best = max(branches, key=lambda x: SCORE_MAP.get(x.get("label","incorrect"),0))
    elapsed = round(time.time() - t0, 1)
    print(f"[{_ts()}] {tag} → best={best.get('label','incorrect')}  cost=${cost:.3f}  {elapsed}s", flush=True)

    rec = {
        "problem_id": pid, "prompt_type": ptype, "condition": condition, "seed": seed,
        "models": {k: v.split("/")[-1] for k,v in models.items()},
        "ideas": ideas,
        "branches": branches,
        "best_label": best.get("label"),
        "best_score": best.get("score", 0),
        "best_candidate": best.get("candidate"),
        "cost": cost, "elapsed_s": elapsed,
    }
    with log_lock:
        with open(log_path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load_problems(pids_filter=None):
    rows = list(csv.DictReader(open(PROBLEMS_CSV, encoding="utf-8")))
    out = []
    for r in rows:
        pid = r["problem_id"]; ptype = r["prompt_type"]
        if pid in EXCLUDE_PIDS: continue
        if (pid, ptype) in SKIP_PAIRS: continue
        if pids_filter and pid not in pids_filter: continue
        out.append({"problem_id": pid, "prompt_type": ptype, "prompt": r["prompt"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True, choices=list(CONDITIONS.keys()))
    ap.add_argument("--seeds", default="42", help="Comma-separated seeds")
    ap.add_argument("--pids", help="Comma-separated problem_ids to include (default: all)")
    ap.add_argument("--ptypes", default="warmup,full_problem", help="Comma-separated prompt_types")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",")]
    pids_filter = set(args.pids.split(",")) if args.pids else None
    ptypes_filter = set(args.ptypes.split(","))

    problems = [p for p in load_problems(pids_filter) if p["prompt_type"] in ptypes_filter]
    models = {k: f"openrouter/{v}" if not v.startswith("openrouter/") else v for k,v in CONDITIONS[args.condition].items()}
    # Strip "openrouter/" because or_chat works with the openrouter API directly
    models = {k: v.replace("openrouter/", "") for k,v in models.items()}

    trials = [(p, s) for p in problems for s in seeds]
    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Condition: {args.condition}")
    print(f"Models: {models}")
    print(f"Problems: {len(problems)}  Seeds: {seeds}  Trials: {len(trials)}")

    log_path = ROOT / "logs" / f"{EXPERIMENT_NAME}_{args.condition}_{_now()}.jsonl"
    log_lock = threading.Lock()
    print(f"Log: {log_path}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(run_problem, p, models, args.condition, s, log_path, log_lock): (p, s)
                for p, s in trials}
        completed = 0
        for fut in concurrent.futures.as_completed(futs):
            completed += 1
            try:
                r = fut.result(timeout=3600)
                results.append(r)
            except Exception as e:
                p, s = futs[fut]
                print(f"FAIL {p['problem_id']}|{p['prompt_type']} seed={s}: {e}", flush=True)
                results.append({"problem_id": p["problem_id"], "prompt_type": p["prompt_type"],
                               "condition": args.condition, "seed": s, "error": str(e)})
            print(f"Progress: {completed}/{len(trials)}", flush=True)

    out_path = ROOT / "experiments" / "results" / f"{EXPERIMENT_NAME}_{args.condition}_{_now()}.json"
    with open(out_path, "w") as f:
        json.dump({"condition": args.condition, "models": models, "seeds": seeds,
                   "results": results}, f, indent=2, ensure_ascii=False)
    total_cost = sum(r.get("cost",0) for r in results if isinstance(r, dict))
    print(f"\nSaved: {out_path}")
    print(f"Total cost: ${total_cost:.2f}")
    print("\nPositives:")
    for r in sorted(results, key=lambda x: -x.get("best_score",0)):
        if isinstance(r, dict) and r.get("best_label") and r["best_label"] != "incorrect":
            print(f"  {r['problem_id']:<26} {r['prompt_type']:<14} seed={r['seed']} → {r['best_label']}")


if __name__ == "__main__":
    main()
