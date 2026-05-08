#!/usr/bin/env python3
"""
seed_full architecture on FrontierMath open-problems using Gemini API for gemma.

Architecture: ideate(N) → N parallel branches of (seeded_generate → verify ↔ revise) → judge.
Best-of-branches by judge score reported.

Conditions (--condition):
  gemma_homogeneous:   ideator/gen/verify/revise = gemma-4-31b-it (Gemini API tier 2)
  roleswap_oss_verify: gemma everywhere except verifier = gpt-oss-120b (OpenRouter, xhigh reasoning)

Judge: deepseek-v4-flash via OpenRouter.

Usage:
  uv run experiments/openproblems_gemma_seedfull_20260507.py --condition gemma_homogeneous
  uv run experiments/openproblems_gemma_seedfull_20260507.py --condition roleswap_oss_verify --pids inverse-galois
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, os, random, re, sys, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(str(ROOT / ".env"))

from _gemini_api import gemini_generate

EXPERIMENT_NAME = "openproblems_gemma_seedfull_20260507"

GEMMA_MODEL = "gemma-4-31b-it"
OSS_MODEL   = "openai/gpt-oss-120b"
JUDGE_MODEL = "deepseek/deepseek-v4-flash"

CONDITIONS = {
    "gemma_homogeneous":   {"ideator":"gemma", "generator":"gemma", "verifier":"gemma",  "reviser":"gemma"},
    "roleswap_oss_verify": {"ideator":"gemma", "generator":"gemma", "verifier":"oss",    "reviser":"gemma"},
}

PROBLEMS_CSV = ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv"
EXCLUDE_PIDS = {"ramsey-hypergraphs", "explicit-deformations"}
SKIP_PAIRS = {("small-diophantine", "full_problem")}

NUM_IDEAS  = int(os.getenv("NUM_IDEAS", "2"))
ITERATIONS = int(os.getenv("ITERATIONS", "1"))

MAX_TOKENS_IDEATE = 4000
MAX_TOKENS_GEN    = 12000
MAX_TOKENS_VR     = 8000
MAX_TOKENS_JUDGE  = 3000

HTTP_TIMEOUT_GEM = 1500
HTTP_TIMEOUT_OSS = 900
HTTP_TIMEOUT_JUDGE = 180

MAX_WORKERS_OUTER = 12   # outer trial parallelism (each fans out to 3 branches)
INNER_WORKERS = 3        # branches per problem

OR_KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k]
_or_lock = threading.Lock(); _or_idx = [0]
def next_or_key():
    with _or_lock:
        k = OR_KEYS[_or_idx[0] % len(OR_KEYS)]; _or_idx[0] += 1; return k

OSS_SEM = threading.Semaphore(20)
DEEPSEEK_SEM = threading.Semaphore(40)

def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts():  return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
IDEATOR_SYSTEM = """You are an expert mathematician working on research-level open / unsolved problems.
Generate {n} distinct high-level approaches for solving the problem. Each approach should be a genuinely different strategy.

Output a JSON array inside a ```json block, with each entry having:
- "name": short label (2-5 words)
- "description": 2-4 sentence detailed plan, including specific construction techniques, references to known results, or algorithmic ideas

The user will pick one approach to fully execute.

```json
[
  {"name": "...", "description": "..."},
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
[The final answer in EXACTLY the format the problem requests, and nothing else.]
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

Structure:

## Approach
[Brief: what you changed and why]

## Answer
[Final answer in exactly the requested format, nothing else]
"""

JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate solution to a research-level open problem.
Classify based on:
* **correct:** Construction/algorithm appears fully correct AND in requested format.
* **almost:** Core construction looks right but has a small format/off-by-one/minor bug.
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


def or_chat(model, messages, max_tokens, http_timeout=HTTP_TIMEOUT_OSS,
            sem=None, retries=4, backoff=8.0, reasoning=None):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning is not None: body["reasoning"] = reasoning
    last_err = None
    for attempt in range(retries + 1):
        if sem: sem.acquire()
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {next_or_key()}", "Content-Type":"application/json"},
                json=body, timeout=http_timeout)
        finally:
            if sem: sem.release()
        try:
            if r.status_code == 402: raise RuntimeError(f"402: {r.text[:200]}")
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace('.','',1).isdigit() else min(backoff*(2**attempt), 90.0)
                if attempt < retries: time.sleep(wait); continue
                raise RuntimeError("429 after retries")
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content") or choice.get("reasoning") or choice.get("reasoning_content")
            if not content: raise ValueError("empty")
            return content, {"cost": float(j.get("usage", {}).get("cost", 0) or 0)}
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            if attempt < retries: time.sleep(backoff*(2**min(attempt,4)))
    raise last_err


def call_role(role_model: str, system: str, prompt: str, max_tokens: int) -> tuple[str, dict]:
    """Dispatch a call based on role model."""
    if role_model == "gemma":
        text, meta = gemini_generate(GEMMA_MODEL, prompt, system=system, max_tokens=max_tokens,
                                     http_timeout=HTTP_TIMEOUT_GEM)
        return text, {"cost": 0.0, "usage": meta}  # gemma free on tier 2 (or near-free)
    elif role_model == "oss":
        # gpt-oss-120b xhigh
        text, meta = or_chat(OSS_MODEL, [
            {"role":"system","content": system},
            {"role":"user","content": prompt},
        ], max_tokens, sem=OSS_SEM, reasoning={"effort":"xhigh"})
        return text, {"cost": meta.get("cost",0), "usage": {}}
    else:
        raise ValueError(f"unknown role model: {role_model}")


def run_branch(idea, problem, role_assignment):
    pid, ptype = problem["problem_id"], problem["prompt_type"]
    cost = 0.0
    history = [{"phase":"idea","idea":idea}]

    # Seeded generate
    try:
        gen_sys = GENERATOR_SEEDED_SYSTEM.replace("{idea}", json.dumps(idea, ensure_ascii=False))
        gen_text, gmeta = call_role(role_assignment["generator"], gen_sys, problem["prompt"], MAX_TOKENS_GEN)
        cost += gmeta.get("cost",0)
        candidate = gen_text
        history.append({"phase":"generate","text":gen_text,"cost":gmeta.get("cost",0)})
    except Exception as e:
        return {"idea":idea, "error":f"gen: {type(e).__name__}: {e}", "candidate":None, "history":history, "cost":cost}

    for i in range(ITERATIONS):
        try:
            v_prompt = f"**PROBLEM:**\n{problem['prompt']}\n\n**CANDIDATE:**\n{candidate}"
            v_text, vmeta = call_role(role_assignment["verifier"], VERIFIER_SYSTEM, v_prompt, MAX_TOKENS_VR)
            cost += vmeta.get("cost",0)
            history.append({"phase":f"verify_{i+1}","text":v_text,"cost":vmeta.get("cost",0)})
        except Exception as e:
            history.append({"phase":f"verify_{i+1}","error":str(e)})
            break
        if "VERDICT: correct" in v_text:
            break
        try:
            r_prompt = f"**PROBLEM:**\n{problem['prompt']}\n\n**PREVIOUS CANDIDATE:**\n{candidate}\n\n**FEEDBACK:**\n{v_text}"
            r_text, rmeta = call_role(role_assignment["reviser"], REVISER_SYSTEM, r_prompt, MAX_TOKENS_VR)
            cost += rmeta.get("cost",0)
            history.append({"phase":f"revise_{i+1}","text":r_text,"cost":rmeta.get("cost",0)})
            candidate = r_text
        except Exception as e:
            history.append({"phase":f"revise_{i+1}","error":str(e)})
            break

    return {"idea":idea, "candidate":candidate, "history":history, "cost":cost}


def run_problem(problem, condition, seed, log_path, log_lock):
    pid, ptype = problem["problem_id"], problem["prompt_type"]
    role_assignment = CONDITIONS[condition]
    tag = f"[{pid}|{ptype}|{condition}|seed={seed}]"
    print(f"[{_ts()}] {tag} start", flush=True)
    t0 = time.time()
    cost = 0.0

    random.seed(seed)
    # Ideate
    try:
        ideator_sys = IDEATOR_SYSTEM.replace("{n}", str(NUM_IDEAS))
        idea_text, imeta = call_role(role_assignment["ideator"], ideator_sys, problem["prompt"], MAX_TOKENS_IDEATE)
        cost += imeta.get("cost",0)
        ideas = parse_ideas(idea_text, NUM_IDEAS)
        print(f"[{_ts()}] {tag} ideated ({len(ideas)} ideas)", flush=True)
    except Exception as e:
        print(f"[{_ts()}] {tag} IDEATE FAIL: {e}", flush=True)
        return {"problem_id":pid, "prompt_type":ptype, "condition":condition, "seed":seed, "error":f"ideate: {e}"}

    # Run branches in parallel
    branches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=INNER_WORKERS) as ex:
        futs = {ex.submit(run_branch, idea, problem, role_assignment): idea for idea in ideas}
        for fut in concurrent.futures.as_completed(futs):
            try: branches.append(fut.result())
            except Exception as e: branches.append({"idea":futs[fut], "error":str(e), "candidate":None, "cost":0})
    cost += sum(b.get("cost",0) for b in branches)

    # Judge each branch
    for b in branches:
        if not b.get("candidate"):
            b["label"] = "incorrect"; b["score"] = 0; continue
        try:
            j_text, jmeta = or_chat(JUDGE_MODEL, [
                {"role":"user","content": JUDGE_SYSTEM.replace("{problem}", problem["prompt"]).replace("{candidate}", b["candidate"])},
            ], MAX_TOKENS_JUDGE, sem=DEEPSEEK_SEM, http_timeout=HTTP_TIMEOUT_JUDGE)
            cost += jmeta.get("cost",0)
            b["label"] = parse_classification(j_text)
            b["score"] = SCORE_MAP[b["label"]]
            b["judge_text"] = j_text
        except Exception as e:
            b["label"] = "ERROR"; b["score"] = 0; b["judge_error"] = str(e)

    best = max(branches, key=lambda x: SCORE_MAP.get(x.get("label","incorrect"),0))
    elapsed = round(time.time() - t0, 1)
    print(f"[{_ts()}] {tag} → best={best.get('label','?')}  cost=${cost:.3f}  {elapsed}s", flush=True)

    rec = {
        "problem_id":pid, "prompt_type":ptype, "condition":condition, "seed":seed,
        "role_assignment":role_assignment,
        "ideas":ideas,
        "branches":branches,
        "best_label":best.get("label"),
        "best_score":best.get("score",0),
        "best_candidate":best.get("candidate"),
        "cost":cost, "elapsed_s":elapsed,
    }
    with log_lock:
        with open(log_path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load_problems(pids_filter=None, ptypes_filter=None):
    rows = list(csv.DictReader(open(PROBLEMS_CSV, encoding="utf-8")))
    out = []
    for r in rows:
        if r["problem_id"] in EXCLUDE_PIDS: continue
        if (r["problem_id"], r["prompt_type"]) in SKIP_PAIRS: continue
        if pids_filter and r["problem_id"] not in pids_filter: continue
        if ptypes_filter and r["prompt_type"] not in ptypes_filter: continue
        out.append({"problem_id":r["problem_id"], "prompt_type":r["prompt_type"], "prompt":r["prompt"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True, choices=list(CONDITIONS.keys()))
    ap.add_argument("--pids")
    ap.add_argument("--ptypes", default="warmup,full_problem")
    ap.add_argument("--seeds", default="42,43")
    args = ap.parse_args()

    pids = set(args.pids.split(",")) if args.pids else None
    ptypes = set(args.ptypes.split(","))
    seeds = [int(s) for s in args.seeds.split(",")]
    problems = load_problems(pids, ptypes)
    trials = [(p, s) for p in problems for s in seeds]

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Condition: {args.condition}  Roles: {CONDITIONS[args.condition]}")
    print(f"Trials: {len(trials)} = {len(problems)} problems × {len(seeds)} seeds")
    print()

    log_path = ROOT / "logs" / f"{EXPERIMENT_NAME}_{args.condition}_{_now()}.jsonl"
    log_lock = threading.Lock()
    print(f"Log: {log_path}\n")

    results = []
    completed = 0
    total = len(trials)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_OUTER) as ex:
        futs = {ex.submit(run_problem, p, args.condition, s, log_path, log_lock): (p, s)
                for (p, s) in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=3600 * total):
            completed += 1
            try:
                results.append(fut.result(timeout=3600))
            except Exception as e:
                p, s = futs[fut]
                print(f"FAIL {p['problem_id']}|{p['prompt_type']} seed={s}: {e}", flush=True)
                results.append({"problem_id":p["problem_id"], "prompt_type":p["prompt_type"],
                               "condition":args.condition, "seed":s, "error":str(e)})
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    out_path = ROOT / "experiments" / "results" / f"{EXPERIMENT_NAME}_{args.condition}_{_now()}.json"
    with open(out_path, "w") as f:
        json.dump({"experiment": EXPERIMENT_NAME, "condition": args.condition,
                   "role_assignment": CONDITIONS[args.condition], "seeds": seeds,
                   "results": results}, f, indent=2, ensure_ascii=False)
    total_cost = sum(r.get("cost",0) for r in results if isinstance(r, dict))
    print(f"\nSaved: {out_path}")
    print(f"Total cost: ${total_cost:.2f}")

    print("\nPositives (best label per problem):")
    for r in sorted(results, key=lambda x: -SCORE_MAP.get(x.get("best_label","incorrect"),0) if isinstance(x,dict) else 0):
        if isinstance(r, dict) and r.get("best_label") and r["best_label"] != "incorrect":
            print(f"  {r['problem_id']:<26} {r['prompt_type']:<14} seed={r['seed']} → {r['best_label']}")


if __name__ == "__main__":
    main()
