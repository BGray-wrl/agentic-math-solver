#!/usr/bin/env python3
"""
FrontierMath open-problems probe — Phase 1: pass@5 generation across
gpt-oss-120b (xhigh), gemma-4-31b-it (xhigh), deepseek-v4-flash (default).

No ground truth. Initial judge: deepseek-v4-flash (cheap, fast). Any positive
signal (correct/almost/partial) gets surfaced; phase 2 escalates these to
3-judge consensus.

Direct OpenRouter API. Parallel across all (problem × model × seed).
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, os, random, re, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(str(ROOT / ".env"))

EXPERIMENT_NAME = "openproblems_pass5_20260507"

# --- Problem set ---
PROBLEMS_CSV = ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv"
EXCLUDE_PIDS = {"ramsey-hypergraphs"}
# small-diophantine full_problem has literal "___" placeholder where the equation should be
SKIP_PAIRS = {("small-diophantine", "full_problem")}

# --- Models ---
MODELS = [
    {"name": "openai/gpt-oss-120b",       "reasoning": {"effort": "xhigh"}},
    # gemma-4-31b dropped — provider-side rate limits prevented progress in v1
    {"name": "deepseek/deepseek-v4-flash","reasoning": None},
]
JUDGE_MODEL = "deepseek/deepseek-v4-flash"

# --- Pass@k ---
SEEDS = [42, 43, 44, 45, 46]  # pass@5

# --- Limits ---
MAX_TOKENS_GEN   = 24000   # balance reasoning depth vs throughput / cost
MAX_TOKENS_JUDGE = 4000
GEN_HTTP_TIMEOUT   = 900
JUDGE_HTTP_TIMEOUT = 180
TRIAL_TIMEOUT      = 1100
MAX_WORKERS        = 100  # increase global to keep gpt-oss + deepseek pipelines busy

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Primary key is exhausted; round-robin across these working keys
API_KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k]
if not API_KEYS: raise SystemExit("no working OPENROUTER keys found")

_key_lock = threading.Lock()
_key_idx = [0]
def next_key():
    with _key_lock:
        k = API_KEYS[_key_idx[0] % len(API_KEYS)]
        _key_idx[0] += 1
        return k

def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts():  return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# OpenRouter wrapper
# ---------------------------------------------------------------------------
# Per-model semaphores to avoid hammering rate-limited routes
_model_sem = {
    "google/gemma-4-31b-it":      threading.Semaphore(8),
    "openai/gpt-oss-120b":        threading.Semaphore(40),
    "deepseek/deepseek-v4-flash": threading.Semaphore(60),
}

def _sem_for(model):
    return _model_sem.get(model)

def or_chat(model, messages, max_tokens, key, http_timeout, reasoning=None,
            retries=6, backoff=8.0):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning is not None:
        body["reasoning"] = reasoning
    last_err = None
    sem = _sem_for(model)
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
                # Honor Retry-After if present
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace('.','',1).isdigit() else min(backoff * (2 ** attempt), 90.0)
                if attempt < retries:
                    time.sleep(wait + (attempt * 0.3))  # slight jitter
                    continue
                raise RuntimeError(f"429 after retries: {r.text[:120]}")
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content")
            reasoning_text = choice.get("reasoning") or choice.get("reasoning_content")
            if not content: content = reasoning_text
            if not content: raise ValueError("empty response")
            usage = j.get("usage", {})
            cd = usage.get("completion_tokens_details") or {}
            return content, {
                "prompt_tokens":     int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens":      int(usage.get("total_tokens", 0) or 0),
                "reasoning_tokens":  int(cd.get("reasoning_tokens", 0) or 0),
                "cost":              float(usage.get("cost", 0) or 0),
            }, reasoning_text
        except Exception as e:
            last_err = e
            msg = str(e)
            if "402" in msg or "insufficient" in msg.lower(): raise
            if attempt < retries:
                wait = backoff * (2 ** min(attempt, 4))
                # quieter: don't spam retries until 3rd attempt
                if attempt >= 2:
                    print(f"[{_ts()}] [retry] {model} attempt {attempt+1}: {e}, retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
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
 If the problem requests a multi-line string in a specific format, provide it.
 The verifier will read what comes after `## Answer` so make sure ONLY the answer is there.]
"""

JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate solution to a research-level open problem.
The problem asks for an explicit construction or algorithm whose correctness will ultimately be checked by a programmatic verifier.

You should classify the candidate's quality based on these criteria:
* **correct:** The construction/algorithm appears fully correct AND is in the requested output format. A reasonable verifier should accept it.
* **almost:** The core construction looks essentially right but has a small format issue, off-by-one, or minor bug that would prevent verification but is fixable.
* **partial:** Meaningful mathematical progress — a related but incomplete construction, an attempt at the right structure that doesn't quite satisfy all requirements, or an algorithm that handles only easy cases.
* **incorrect:** No real progress, refusal, fundamentally wrong approach, or completely unparseable output.

Be STRICT but FAIR. If the candidate clearly attempted the problem and produced something nontrivial, that warrants at least 'partial'. Refusals or trivial outputs (e.g. just restating the problem, or "I cannot solve this") are 'incorrect'.

Output your reasoning, then on a final line:
CLASSIFICATION: <correct|almost|partial|incorrect>

---

**PROBLEM:**
{problem}

**CANDIDATE SOLUTION:**
{candidate}
"""

CLASSIF_RE = re.compile(r"CLASSIFICATION:\s*(correct|almost|partial|incorrect)", re.I)
SCORE_MAP = {"correct": 3, "almost": 2, "partial": 1, "incorrect": 0}

def parse_classification(text: str) -> str:
    m = CLASSIF_RE.search(text or "")
    if m: return m.group(1).lower()
    low = (text or "").lower()
    # Take the LAST occurrence of a label as the verdict
    for lab in ("correct", "almost", "partial", "incorrect"):
        if low.rfind(lab) != -1:
            # crude scan
            pass
    # fallback: pick the highest-priority label that appears
    for lab in ("correct", "almost", "partial", "incorrect"):
        if lab in low: return lab
    return "incorrect"


# ---------------------------------------------------------------------------
# Problem loading
# ---------------------------------------------------------------------------
def load_problems():
    rows = list(csv.DictReader(open(PROBLEMS_CSV, encoding="utf-8")))
    problems = []
    for r in rows:
        pid = r["problem_id"]
        ptype = r["prompt_type"]
        if pid in EXCLUDE_PIDS: continue
        if (pid, ptype) in SKIP_PAIRS: continue
        problems.append({
            "key": f"{pid}__{ptype}",
            "problem_id": pid,
            "prompt_type": ptype,
            "prompt": r["prompt"],
        })
    return problems


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def make_log_path():
    return ROOT / "logs" / f"{EXPERIMENT_NAME}_{_now()}.jsonl"

def log_record(log_path, lock, **rec):
    rec["ts"] = datetime.now(timezone.utc).isoformat()
    with lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Per-trial work
# ---------------------------------------------------------------------------
def run_trial(problem, model_cfg, seed, log_path, lock, mock=False):
    pid = problem["problem_id"]
    ptype = problem["prompt_type"]
    model = model_cfg["name"]
    reasoning = model_cfg["reasoning"]
    short = model.split("/")[-1]
    tag = f"[{pid}|{ptype}|{short}|seed={seed}]"

    t0 = time.time()
    try:
        if mock:
            time.sleep(0.05)
            gen_text = "## Approach\nMock\n\n## Answer\n0,1,1,0\n"
            gen_usage = {"prompt_tokens":100,"completion_tokens":50,"total_tokens":150,"reasoning_tokens":10,"cost":0.0}
            reasoning_text = None
        else:
            gen_text, gen_usage, reasoning_text = or_chat(
                model=model,
                messages=[
                    {"role":"system","content": GENERATOR_SYSTEM},
                    {"role":"user","content": problem["prompt"]},
                ],
                max_tokens=MAX_TOKENS_GEN,
                key=next_key(),
                http_timeout=GEN_HTTP_TIMEOUT,
                reasoning=reasoning,
            )
        gen_elapsed = round(time.time() - t0, 1)
        print(f"[{_ts()}] {tag} gen {gen_elapsed}s  in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']} reason={gen_usage['reasoning_tokens']} cost=${gen_usage.get('cost',0):.4f}",
              flush=True)

        # Initial cheap judge
        if mock:
            verdict_text = "looks ok\nCLASSIFICATION: incorrect"
            judge_usage = {"prompt_tokens":100,"completion_tokens":20,"total_tokens":120,"cost":0.0}
        else:
            jt0 = time.time()
            verdict_text, judge_usage, _ = or_chat(
                model=JUDGE_MODEL,
                messages=[
                    {"role":"user","content": JUDGE_SYSTEM
                        .replace("{problem}", problem["prompt"])
                        .replace("{candidate}", gen_text)},
                ],
                max_tokens=MAX_TOKENS_JUDGE,
                key=next_key(),
                http_timeout=JUDGE_HTTP_TIMEOUT,
                reasoning=None,
            )
        label = parse_classification(verdict_text)
        score = SCORE_MAP[label]
        elapsed = round(time.time() - t0, 1)

        log_record(
            log_path, lock,
            kind="trial",
            problem_id=pid, prompt_type=ptype, model=model, seed=seed,
            label=label, score=score,
            gen_elapsed=gen_elapsed, total_elapsed=elapsed,
            gen_usage=gen_usage, judge_usage=judge_usage,
            gen_text=gen_text, reasoning_text=reasoning_text,
            verdict=verdict_text,
        )
        print(f"[{_ts()}] {tag} → {label} ({score})  total {elapsed}s", flush=True)

        return {
            "problem_id": pid, "prompt_type": ptype, "model": model, "seed": seed,
            "label": label, "score": score,
            "gen_elapsed": gen_elapsed, "total_elapsed": elapsed,
            "gen_usage": gen_usage, "judge_usage": judge_usage,
            "gen_text": gen_text, "reasoning_text": reasoning_text,
            "verdict": verdict_text,
        }
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        tb = traceback.format_exc()
        print(f"[{_ts()}] {tag} FAIL {err}", flush=True)
        log_record(log_path, lock, kind="error",
                   problem_id=pid, prompt_type=ptype, model=model, seed=seed,
                   error=err, tb=tb)
        return {
            "problem_id": pid, "prompt_type": ptype, "model": model, "seed": seed,
            "label": None, "score": None, "error": err,
            "gen_text": None, "verdict": None,
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--limit", type=int, help="Run only N trials (smoke test)")
    ap.add_argument("--exclude-pid", action="append", default=[], help="Skip these problem_ids")
    args = ap.parse_args()

    problems = load_problems()
    skip = set(args.exclude_pid)
    if skip:
        problems = [p for p in problems if p["problem_id"] not in skip]

    trials = [(p, m, s) for p in problems for m in MODELS for s in SEEDS]
    if args.limit:
        trials = trials[:args.limit]

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Problems: {len(problems)}  ({len({p['problem_id'] for p in problems})} pids)")
    print(f"Models:   {[m['name'] for m in MODELS]}")
    print(f"Judge:    {JUDGE_MODEL}")
    print(f"Seeds:    {SEEDS}  → pass@{len(SEEDS)}")
    print(f"Trials:   {len(trials)}")
    if args.mock: print("[MOCK]")
    print()

    log_path = make_log_path()
    lock = threading.Lock()
    print(f"Log: {log_path}\n", flush=True)

    results = []
    completed = 0
    total = len(trials)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(run_trial, p, m, s, log_path, lock, args.mock): (p, m, s)
                for (p, m, s) in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            p, m, s = futs[fut]
            completed += 1
            try:
                results.append(fut.result(timeout=TRIAL_TIMEOUT))
            except Exception as e:
                results.append({
                    "problem_id": p["problem_id"], "prompt_type": p["prompt_type"],
                    "model": m["name"], "seed": s, "label": None, "score": None,
                    "error": str(e), "gen_text": None, "verdict": None,
                })
            print(f"[{_ts()}] Progress: {completed}/{total}", flush=True)

    # --- Summary ---
    out = {
        "experiment": EXPERIMENT_NAME,
        "date": datetime.now(timezone.utc).isoformat(),
        "models": [m["name"] for m in MODELS],
        "judge_model": JUDGE_MODEL,
        "seeds": SEEDS,
        "n_problems": len(problems),
        "results": results,
    }
    suffix = "_mock" if args.mock else ""
    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")

    # quick table
    print("\nPositive signals (label != incorrect):")
    pos = [r for r in results if r.get("label") and r["label"] != "incorrect"]
    if not pos:
        print("  (none)")
    else:
        for r in pos:
            print(f"  {r['problem_id']:<28} {r['prompt_type']:<14} {r['model'].split('/')[-1]:<24} seed={r['seed']}  → {r['label']}")

    # cost
    total_cost = sum(r.get("gen_usage", {}).get("cost", 0) or 0 for r in results) \
               + sum(r.get("judge_usage", {}).get("cost", 0) or 0 for r in results)
    print(f"\nTotal cost: ${total_cost:.2f}")


if __name__ == "__main__":
    main()
