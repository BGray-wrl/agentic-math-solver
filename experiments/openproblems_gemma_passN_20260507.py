#!/usr/bin/env python3
"""
Gemma-4-31b-it (xhigh) generate-only pass@N on the FrontierMath open-problems set.
Smaller, faster than the full seed_full architecture.

Usage:
  uv run experiments/openproblems_gemma_passN_20260507.py --pids inverse-galois,explicit-deformations,degree-sensitivity-boolean,arithmetic-kakeya
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, os, re, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(str(ROOT / ".env"))

EXPERIMENT_NAME = "openproblems_gemma_passN_20260507"

GEN_MODEL = "google/gemma-4-31b-it"
JUDGE_MODEL = "deepseek/deepseek-v4-flash"

MAX_TOKENS_GEN = 24000
MAX_TOKENS_JUDGE = 4000
GEN_HTTP_TIMEOUT = 900
JUDGE_HTTP_TIMEOUT = 180
MAX_WORKERS = 16

GEMMA_SEM = threading.Semaphore(8)
DEEPSEEK_SEM = threading.Semaphore(40)

PROBLEMS_CSV = ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv"
EXCLUDE_PIDS = {"ramsey-hypergraphs"}
SKIP_PAIRS = {("small-diophantine", "full_problem")}

API_KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k]
_lock = threading.Lock(); _idx = [0]
def next_key():
    with _lock:
        k = API_KEYS[_idx[0] % len(API_KEYS)]; _idx[0] += 1
        return k

def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts():  return datetime.now(timezone.utc).strftime("%H:%M:%S")

GENERATOR_SYSTEM = """You are a research mathematician. The problem asks for an EXPLICIT CONSTRUCTION, EXAMPLE, or ALGORITHM.
Your output will be checked by an automated verifier, so the FINAL answer must EXACTLY match the format requested.

## Approach
[Brief: what you tried]

## Answer
[The final answer in EXACTLY the format the problem requests, and nothing else.]
"""
JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate to a research-level open problem.
Classify:
* correct: appears fully correct and in requested format.
* almost: looks essentially right with a minor format/off-by-one issue.
* partial: meaningful progress but incomplete.
* incorrect: no real progress, refusal, or unparseable.

Output reasoning, then on final line:
CLASSIFICATION: <correct|almost|partial|incorrect>

---

**PROBLEM:**
{problem}

**CANDIDATE SOLUTION:**
{candidate}
"""

CLASSIF_RE = re.compile(r"CLASSIFICATION:\s*(correct|almost|partial|incorrect)", re.I)
SCORE_MAP = {"correct": 3, "almost": 2, "partial": 1, "incorrect": 0}
def parse_classif(text):
    m = CLASSIF_RE.search(text or "")
    if m: return m.group(1).lower()
    low = (text or "").lower()
    for lab in ("correct","almost","partial","incorrect"):
        if lab in low: return lab
    return "incorrect"


def or_chat(model, messages, max_tokens, key, http_timeout, reasoning=None,
            sem=None, retries=4, backoff=8.0):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning is not None: body["reasoning"] = reasoning
    last_err = None
    for attempt in range(retries + 1):
        if sem: sem.acquire()
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"},
                json=body, timeout=http_timeout)
        finally:
            if sem: sem.release()
        try:
            if r.status_code == 402: raise RuntimeError(f"402: {r.text[:200]}")
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace('.','',1).isdigit() else min(backoff * (2**attempt), 90.0)
                if attempt < retries:
                    time.sleep(wait); continue
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content") or choice.get("reasoning") or choice.get("reasoning_content")
            if not content: raise ValueError("empty response")
            return content, {"cost": float(j.get("usage", {}).get("cost", 0) or 0)}
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            if attempt < retries: time.sleep(backoff * (2**min(attempt, 4)))
    raise last_err


def run_trial(p, seed, log_path, log_lock):
    pid, ptype = p["problem_id"], p["prompt_type"]
    tag = f"[{pid}|{ptype}|gemma|seed={seed}]"
    t0 = time.time()
    try:
        gen, gmeta = or_chat(GEN_MODEL, [
            {"role":"system","content": GENERATOR_SYSTEM},
            {"role":"user","content": p["prompt"]},
        ], MAX_TOKENS_GEN, next_key(), GEN_HTTP_TIMEOUT, reasoning={"effort":"xhigh"}, sem=GEMMA_SEM)
    except Exception as e:
        print(f"[{_ts()}] {tag} GEN FAIL: {e}", flush=True)
        return {"problem_id":pid,"prompt_type":ptype,"seed":seed,"error":str(e),"label":None}
    try:
        v_text, vmeta = or_chat(JUDGE_MODEL, [
            {"role":"user","content": JUDGE_SYSTEM.replace("{problem}",p["prompt"]).replace("{candidate}",gen)},
        ], MAX_TOKENS_JUDGE, next_key(), JUDGE_HTTP_TIMEOUT, sem=DEEPSEEK_SEM)
    except Exception as e:
        v_text = f"ERROR: {e}"
        vmeta = {"cost": 0}
    label = parse_classif(v_text)
    rec = {"problem_id":pid, "prompt_type":ptype, "seed":seed, "model":GEN_MODEL,
           "label":label, "score":SCORE_MAP[label], "gen_text":gen, "verdict":v_text,
           "elapsed":round(time.time()-t0,1),
           "cost":gmeta.get("cost",0)+vmeta.get("cost",0)}
    with log_lock:
        with open(log_path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{_ts()}] {tag} → {label}  ({rec['elapsed']}s, ${rec['cost']:.3f})", flush=True)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pids", help="comma-separated problem_ids (default: all)")
    ap.add_argument("--ptypes", default="warmup,full_problem")
    ap.add_argument("--seeds", default="42,43,44")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",")]
    pids_filter = set(args.pids.split(",")) if args.pids else None
    ptypes_filter = set(args.ptypes.split(","))

    rows = list(csv.DictReader(open(PROBLEMS_CSV, encoding="utf-8")))
    problems = []
    for r in rows:
        if r["problem_id"] in EXCLUDE_PIDS: continue
        if (r["problem_id"], r["prompt_type"]) in SKIP_PAIRS: continue
        if pids_filter and r["problem_id"] not in pids_filter: continue
        if r["prompt_type"] not in ptypes_filter: continue
        problems.append({"problem_id":r["problem_id"], "prompt_type":r["prompt_type"], "prompt":r["prompt"]})

    trials = [(p, s) for p in problems for s in seeds]
    print(f"Gemma pass@{len(seeds)}: {len(problems)} problems × {len(seeds)} seeds = {len(trials)} trials")

    log_path = ROOT / "logs" / f"{EXPERIMENT_NAME}_{_now()}.jsonl"
    log_lock = threading.Lock()
    print(f"Log: {log_path}\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(run_trial, p, s, log_path, log_lock): (p, s) for p, s in trials}
        for fut in concurrent.futures.as_completed(futs):
            try: results.append(fut.result(timeout=1500))
            except Exception as e:
                p, s = futs[fut]
                print(f"FAIL {p['problem_id']} seed={s}: {e}")
                results.append({"problem_id":p["problem_id"], "prompt_type":p["prompt_type"], "seed":s, "error":str(e), "label":None})

    out = {"experiment":EXPERIMENT_NAME, "model":GEN_MODEL, "judge":JUDGE_MODEL, "seeds":seeds,
           "results":results}
    out_path = ROOT / "experiments" / "results" / f"{EXPERIMENT_NAME}_{_now()}.json"
    with open(out_path, "w") as f: json.dump(out, f, indent=2, ensure_ascii=False)
    cost = sum(r.get("cost",0) for r in results if isinstance(r, dict))
    print(f"\nSaved: {out_path}\nTotal cost: ${cost:.2f}")

    pos = [r for r in results if r.get("label") and r["label"] != "incorrect"]
    print(f"\nPositives: {len(pos)}")
    for r in pos:
        print(f"  {r['problem_id']:<26} {r['prompt_type']:<14} seed={r['seed']} → {r['label']}")


if __name__ == "__main__":
    main()
