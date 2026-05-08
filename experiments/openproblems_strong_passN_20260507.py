#!/usr/bin/env python3
"""
Phase 4: Use a stronger frontier model (claude-opus-4.6 or gemini-3.1-pro)
on the problems that showed any positive signal. pass@N attempts each.

Usage:
  uv run experiments/openproblems_strong_passN_20260507.py <phase1_results.json> --model gemini-3.1-pro --n 3
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, os, re, sys, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(str(ROOT / ".env"))

EXPERIMENT_NAME = "openproblems_strong_passN_20260507"

MODEL_MAP = {
    "claude-opus-4.6":   {"name": "anthropic/claude-opus-4.6",   "reasoning": None},
    "gemini-3.1-pro":    {"name": "google/gemini-3.1-pro-preview","reasoning": None},
    "gpt-5":             {"name": "openai/gpt-5",                "reasoning": {"effort": "high"}},
}

JUDGE_MODELS = [
    {"name": "openai/gpt-oss-120b",       "reasoning": {"effort": "xhigh"}},
    {"name": "deepseek/deepseek-v4-flash","reasoning": None},
]
MAX_TOKENS_GEN   = 32000
MAX_TOKENS_JUDGE = 4000
HTTP_TIMEOUT = 1500
MAX_WORKERS = 12

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
[The final answer in EXACTLY the format the problem requests, and nothing else.]
"""

JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate solution to a research-level open problem.
The problem asks for an explicit construction or algorithm whose correctness will ultimately be checked by a programmatic verifier.

Classify based on these criteria:
* **correct:** Construction/algorithm appears fully correct AND in the requested format.
* **almost:** Core construction looks essentially right but has a small format issue, off-by-one, or minor bug.
* **partial:** Meaningful mathematical progress but incomplete or significantly flawed.
* **incorrect:** No real progress, refusal, or completely unparseable output.

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


def or_chat(model, messages, max_tokens, key, http_timeout, reasoning=None,
            retries=4, backoff=8.0):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning is not None: body["reasoning"] = reasoning
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"},
                json=body, timeout=http_timeout,
            )
            if r.status_code == 402: raise RuntimeError(f"402: {r.text[:200]}")
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace('.','',1).isdigit() else min(backoff * (2 ** attempt), 90.0)
                if attempt < retries: time.sleep(wait); continue
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content") or choice.get("reasoning") or choice.get("reasoning_content")
            if not content: raise ValueError("empty response")
            return content, {"cost": float(j.get("usage", {}).get("cost", 0) or 0)}
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            if attempt < retries: time.sleep(backoff * (2 ** min(attempt, 4)))
    raise last_err


def run_one(problem, model_cfg, seed, judge_cfg=None):
    pid = problem["problem_id"]; ptype = problem["prompt_type"]
    short = model_cfg["name"].split("/")[-1]
    tag = f"[{pid}|{ptype}|{short}|seed={seed}]"

    cost = 0.0
    try:
        gen_text, gen_meta = or_chat(
            model=model_cfg["name"],
            messages=[
                {"role":"system","content": GENERATOR_SYSTEM},
                {"role":"user","content": problem["prompt"]},
            ],
            max_tokens=MAX_TOKENS_GEN,
            key=next_key(),
            http_timeout=HTTP_TIMEOUT,
            reasoning=model_cfg["reasoning"],
        )
        cost += gen_meta.get("cost", 0)
    except Exception as e:
        return {"problem_id": pid, "prompt_type": ptype, "model": model_cfg["name"], "seed": seed,
                "label": None, "gen_text": None, "error": str(e)}

    # Judges
    judge_results = {}
    for jcfg in JUDGE_MODELS:
        try:
            jt, jmeta = or_chat(
                model=jcfg["name"],
                messages=[{"role":"user","content": JUDGE_SYSTEM
                            .replace("{problem}", problem["prompt"])
                            .replace("{candidate}", gen_text)}],
                max_tokens=MAX_TOKENS_JUDGE, key=next_key(), http_timeout=HTTP_TIMEOUT,
                reasoning=jcfg["reasoning"],
            )
            cost += jmeta.get("cost", 0)
            judge_results[jcfg["name"]] = {"label": parse_classification(jt), "text": jt}
        except Exception as e:
            judge_results[jcfg["name"]] = {"label": "ERROR", "text": str(e)}

    labels = [v["label"] for v in judge_results.values() if v["label"] != "ERROR"]
    label = max(labels, key=lambda x: SCORE_MAP.get(x,0)) if labels else "incorrect"
    print(f"{tag} → {label} (cost ${cost:.3f})", flush=True)
    return {"problem_id": pid, "prompt_type": ptype, "model": model_cfg["name"], "seed": seed,
            "label": label, "gen_text": gen_text, "judges": judge_results, "cost": cost}


def load_problems():
    rows = list(csv.DictReader(open(ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv", encoding="utf-8")))
    return {(r["problem_id"], r["prompt_type"]): {"problem_id": r["problem_id"], "prompt_type": r["prompt_type"], "prompt": r["prompt"]} for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase1_json")
    ap.add_argument("--model", default="gemini-3.1-pro", choices=list(MODEL_MAP.keys()))
    ap.add_argument("--n", type=int, default=3, help="pass@N attempts per problem")
    ap.add_argument("--label-min", default="partial", choices=["correct","almost","partial","incorrect"])
    args = ap.parse_args()

    with open(args.phase1_json) as f:
        phase1 = json.load(f)
    plookup = load_problems()
    rank = {"incorrect":0, "partial":1, "almost":2, "correct":3}
    min_rank = rank[args.label_min]

    # Pick (pid, ptype) where any model/seed had label >= label_min
    promising = set()
    for r in phase1["results"]:
        if r.get("label") and rank.get(r["label"], -1) >= min_rank:
            promising.add((r["problem_id"], r["prompt_type"]))

    print(f"Promising problems: {len(promising)}")
    for k in sorted(promising): print(f"  {k}")

    model_cfg = MODEL_MAP[args.model]
    seeds = [42 + i for i in range(args.n)]
    trials = [(plookup[k], model_cfg, s) for k in promising for s in seeds]
    print(f"\nTrials: {len(trials)} ({args.model}, n={args.n})")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(run_one, p, m, s): (p, s) for p, m, s in trials}
        for fut in concurrent.futures.as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"FAIL: {e}")

    out_path = Path(__file__).parent / "results" / f"{EXPERIMENT_NAME}_{args.model}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"phase1_source": args.phase1_json, "model": args.model, "n": args.n, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")
    total_cost = sum(r.get("cost",0) for r in results)
    print(f"Total cost: ${total_cost:.2f}")

    print("\n=== Best per problem ===")
    by_pid = {}
    for r in results:
        k = (r["problem_id"], r["prompt_type"])
        sc = SCORE_MAP.get(r.get("label","incorrect"),0)
        if k not in by_pid or sc > SCORE_MAP.get(by_pid[k]["label"],0):
            by_pid[k] = r
    for k, r in sorted(by_pid.items(), key=lambda x: -SCORE_MAP.get(x[1].get("label","incorrect"),0)):
        if r.get("label") and r["label"] != "incorrect":
            print(f"  {k[0]:<26} {k[1]:<14} → {r['label']} seed={r['seed']}")


if __name__ == "__main__":
    main()
