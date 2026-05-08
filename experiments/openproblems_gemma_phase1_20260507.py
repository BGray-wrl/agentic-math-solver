#!/usr/bin/env python3
"""
Phase 1 pass@5 with gemma-4-31b-it via Gemini API (tier 2 paid).
Judge: deepseek-v4-flash via OpenRouter (cheap).
Same problem set as the original phase1.

Usage:
  uv run experiments/openproblems_gemma_phase1_20260507.py
  uv run experiments/openproblems_gemma_phase1_20260507.py --pids inverse-galois,arithmetic-kakeya
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, os, re, sys, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(str(ROOT / ".env"))

from _gemini_api import gemini_generate

EXPERIMENT_NAME = "openproblems_gemma_phase1_20260507"

GEMMA_MODEL = "gemma-4-31b-it"
JUDGE_MODEL = "deepseek/deepseek-v4-flash"

PROBLEMS_CSV = ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv"
EXCLUDE_PIDS = {"ramsey-hypergraphs", "explicit-deformations"}
SKIP_PAIRS = {("small-diophantine", "full_problem")}
SEEDS = [42, 43, 44, 45, 46]

MAX_TOKENS_GEN   = 24000
MAX_TOKENS_JUDGE = 4000
HTTP_TIMEOUT_GEN = 1500
HTTP_TIMEOUT_JUDGE = 180
MAX_WORKERS_OUTER = int(os.getenv("MAX_WORKERS", "20"))
TRIAL_TIMEOUT = 1800

# OpenRouter keys for judge
OR_KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k]
_or_lock = threading.Lock(); _or_idx = [0]
def next_or_key():
    with _or_lock:
        k = OR_KEYS[_or_idx[0] % len(OR_KEYS)]; _or_idx[0] += 1
        return k

DEEPSEEK_SEM = threading.Semaphore(40)

def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts():  return datetime.now(timezone.utc).strftime("%H:%M:%S")


GENERATOR_SYSTEM = """You are a research mathematician working on open / unsolved problems.
The user gives you a problem that asks for an EXPLICIT CONSTRUCTION, EXAMPLE, or ALGORITHM.
The output will be checked by an automated verifier, so your final answer must EXACTLY match the format requested in the problem.

Approach:
1. Read the problem carefully. Identify what specific object, expression, or program is being requested and the EXACT output format.
2. Think hard. Try multiple approaches if necessary.
3. Produce your best attempt — even a partial / heuristic construction beats nothing.
4. Make absolutely sure the FINAL answer is in the format the problem specifies (CSV, Magma syntax, Python script, list, etc.).

Structure your response as:

## Approach
[1-3 paragraphs: what you tried and why]

## Answer
[The final answer in EXACTLY the format the problem requests, and nothing else.
 If the problem requests a Python script, provide a complete, runnable script.
 If the problem requests a CSV, provide the CSV with no surrounding prose.
 If the problem requests a multi-line string in a specific format, provide it.]
"""

JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate solution to a research-level open problem.
Classify the candidate based on:
* **correct:** Construction/algorithm appears fully correct AND in the requested format.
* **almost:** Core construction looks essentially right but has a small format issue or minor bug.
* **partial:** Meaningful mathematical progress but incomplete or significantly flawed.
* **incorrect:** No real progress, refusal, or unparseable output.

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


def or_chat(model, messages, max_tokens, http_timeout=HTTP_TIMEOUT_JUDGE,
            sem=None, retries=4, backoff=8.0):
    """Direct OpenRouter call for the judge."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    last_err = None
    for attempt in range(retries + 1):
        if sem: sem.acquire()
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {next_or_key()}", "Content-Type": "application/json"},
                json=body, timeout=http_timeout,
            )
        finally:
            if sem: sem.release()
        try:
            if r.status_code == 402: raise RuntimeError(f"402: {r.text[:200]}")
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace('.','',1).isdigit() else min(backoff * (2**attempt), 90.0)
                if attempt < retries: time.sleep(wait); continue
                raise RuntimeError(f"429 after retries")
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content") or choice.get("reasoning") or choice.get("reasoning_content")
            if not content: raise ValueError("empty")
            return content, {"cost": float(j.get("usage", {}).get("cost", 0) or 0)}
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            if attempt < retries: time.sleep(backoff * (2 ** min(attempt, 4)))
    raise last_err


def run_trial(p, seed, log_path, log_lock, mock=False):
    pid, ptype = p["problem_id"], p["prompt_type"]
    tag = f"[{pid}|{ptype}|gemma|seed={seed}]"
    t0 = time.time()
    try:
        gen, gmeta = gemini_generate(
            model=GEMMA_MODEL,
            prompt=p["prompt"],
            system=GENERATOR_SYSTEM,
            max_tokens=MAX_TOKENS_GEN,
            temperature=0.7 + (seed % 5) * 0.05,  # vary slightly across seeds
            http_timeout=HTTP_TIMEOUT_GEN,
        )
    except Exception as e:
        print(f"[{_ts()}] {tag} GEN FAIL: {type(e).__name__}: {str(e)[:120]}", flush=True)
        return {"problem_id":pid, "prompt_type":ptype, "seed":seed, "model":GEMMA_MODEL,
                "label":None, "error":f"gen: {type(e).__name__}: {e}"}
    gen_dt = round(time.time() - t0, 1)
    print(f"[{_ts()}] {tag} gen {gen_dt}s prompt={gmeta['prompt_tokens']} cand={gmeta['candidate_tokens']} thoughts={gmeta['thoughts_tokens']}", flush=True)

    try:
        v_text, vmeta = or_chat(JUDGE_MODEL, [
            {"role":"user","content": JUDGE_SYSTEM.replace("{problem}",p["prompt"]).replace("{candidate}",gen)},
        ], MAX_TOKENS_JUDGE, sem=DEEPSEEK_SEM)
    except Exception as e:
        v_text = f"ERROR: {e}"; vmeta = {"cost": 0}
    label = parse_classification(v_text)

    rec = {
        "problem_id":pid, "prompt_type":ptype, "seed":seed, "model":GEMMA_MODEL,
        "label":label, "score":SCORE_MAP[label], "gen_text":gen, "verdict":v_text,
        "elapsed":round(time.time()-t0,1), "gen_tokens":gmeta,
        "judge_cost":vmeta.get("cost",0),
    }
    with log_lock:
        with open(log_path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{_ts()}] {tag} → {label} (total {rec['elapsed']}s, judge ${vmeta.get('cost',0):.4f})", flush=True)
    return rec


def load_problems(pids_filter=None, ptypes_filter=None):
    rows = list(csv.DictReader(open(PROBLEMS_CSV, encoding="utf-8")))
    out = []
    for r in rows:
        if r["problem_id"] in EXCLUDE_PIDS: continue
        if (r["problem_id"], r["prompt_type"]) in SKIP_PAIRS: continue
        if pids_filter and r["problem_id"] not in pids_filter: continue
        if ptypes_filter and r["prompt_type"] not in ptypes_filter: continue
        out.append({"problem_id": r["problem_id"], "prompt_type": r["prompt_type"], "prompt": r["prompt"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pids", help="comma-separated problem_ids")
    ap.add_argument("--ptypes", default="warmup,full_problem")
    ap.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    pids = set(args.pids.split(",")) if args.pids else None
    ptypes = set(args.ptypes.split(","))
    seeds = [int(s) for s in args.seeds.split(",")]
    problems = load_problems(pids, ptypes)
    trials = [(p, s) for p in problems for s in seeds]

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Model: gemma-4-31b-it (Gemini API tier 2)")
    print(f"Judge: {JUDGE_MODEL}")
    print(f"Trials: {len(trials)} = {len(problems)} problems × {len(seeds)} seeds")
    print()

    log_path = ROOT / "logs" / f"{EXPERIMENT_NAME}_{_now()}.jsonl"
    log_lock = threading.Lock()
    print(f"Log: {log_path}\n")

    results = []
    completed = 0
    total = len(trials)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_OUTER) as ex:
        futs = {ex.submit(run_trial, p, s, log_path, log_lock, args.mock): (p, s) for (p, s) in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                p, s = futs[fut]
                print(f"FAIL {p['problem_id']}|{p['prompt_type']} seed={s}: {e}", flush=True)
                results.append({"problem_id":p["problem_id"], "prompt_type":p["prompt_type"],
                               "seed":s, "model":GEMMA_MODEL, "label":None, "error":str(e)})
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    out_path = ROOT / "experiments" / "results" / f"{EXPERIMENT_NAME}_{_now()}.json"
    with open(out_path, "w") as f:
        json.dump({"experiment": EXPERIMENT_NAME, "model": GEMMA_MODEL, "judge": JUDGE_MODEL,
                   "seeds": seeds, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")

    pos = [r for r in results if r.get("label") and r["label"] != "incorrect"]
    print(f"\nPositives: {len(pos)}")
    for r in pos:
        print(f"  {r['problem_id']:<26} {r['prompt_type']:<14} seed={r['seed']} → {r['label']}")
    print(f"\nTotal judge cost: ${sum(r.get('judge_cost', 0) for r in results):.2f}")


if __name__ == "__main__":
    main()
