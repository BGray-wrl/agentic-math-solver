#!/usr/bin/env python3
"""
3-judge consensus v2: gpt-oss-120b xhigh (OpenRouter) + gemma-4-31b-it (Gemini API)
+ deepseek-v4-flash (OpenRouter).

This is the spec the user originally asked for in the kickoff message; v1
(consensus_judge_20260507.py) substituted gemini-3.1-pro for gemma due to
rate-limit issues, which was an error.

Usage:
  uv run experiments/openproblems_consensus_v2_20260507.py <phase1_results.json>
  uv run experiments/openproblems_consensus_v2_20260507.py <log.jsonl>
"""
from __future__ import annotations
import argparse, concurrent.futures, json, os, re, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(str(ROOT / ".env"))

from _gemini_api import gemini_generate

EXPERIMENT_NAME = "openproblems_consensus_v2_20260507"

GEMMA_MODEL = "gemma-4-31b-it"
OSS_MODEL = "openai/gpt-oss-120b"
DEEPSEEK_MODEL = "deepseek/deepseek-v4-flash"

MAX_TOKENS_JUDGE = 6000
MAX_WORKERS = 12
HTTP_TIMEOUT_GEMINI = 600
HTTP_TIMEOUT_OR = 180

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


JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate solution to a research-level open problem.
The problem asks for an explicit construction or algorithm whose correctness will ultimately be checked by a programmatic verifier.

Classify based on these criteria:
* **correct:** Construction/algorithm appears fully correct AND in the requested format. A reasonable verifier should accept it.
* **almost:** Core construction looks essentially right but has a small format issue, off-by-one, or minor bug.
* **partial:** Meaningful mathematical progress — incomplete or significantly flawed.
* **incorrect:** No real progress, refusal, or unparseable output.

Be STRICT but FAIR. Refusals or trivial outputs are 'incorrect'.

Output your reasoning, then on a final line:
CLASSIFICATION: <correct|almost|partial|incorrect>
"""

JUDGE_USER_TMPL = """**PROBLEM:**
{problem}

**CANDIDATE SOLUTION:**
{candidate}
"""

CLASSIF_RE = re.compile(r"CLASSIFICATION:\s*(correct|almost|partial|incorrect)", re.I)
SCORE_MAP = {"correct":3, "almost":2, "partial":1, "incorrect":0}
def parse_classification(text):
    m = CLASSIF_RE.search(text or "")
    if m: return m.group(1).lower()
    low = (text or "").lower()
    for lab in ("correct","almost","partial","incorrect"):
        if lab in low: return lab
    return "incorrect"


def or_chat(model, system, user, max_tokens, sem=None, retries=4, backoff=8.0,
            reasoning=None, http_timeout=HTTP_TIMEOUT_OR):
    body = {"model": model, "messages": [
        {"role":"system","content": system},
        {"role":"user","content": user},
    ], "max_tokens": max_tokens}
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
                if attempt < retries: time.sleep(min(backoff*(2**attempt), 90.0)); continue
                raise RuntimeError("429 after retries")
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content") or choice.get("reasoning") or choice.get("reasoning_content")
            if not content: raise ValueError("empty")
            return content
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            if attempt < retries: time.sleep(backoff*(2**min(attempt,4)))
    raise last_err


def judge_one_trial(item, problem_text):
    """Run 2 judges (oss-xhigh + deepseek) in parallel on one trial. No gemma, no expensive models."""
    candidate = item.get("gen_text") or item.get("best_candidate") or ""
    user_prompt = JUDGE_USER_TMPL.replace("{problem}", problem_text).replace("{candidate}", candidate)

    results = {}

    def judge_oss():
        try:
            text = or_chat(OSS_MODEL, JUDGE_SYSTEM, user_prompt, MAX_TOKENS_JUDGE,
                          sem=OSS_SEM, reasoning={"effort":"xhigh"}, http_timeout=900)
            return ("oss-xhigh", parse_classification(text), text)
        except Exception as e:
            return ("oss-xhigh", "ERROR", str(e))

    def judge_deepseek():
        try:
            text = or_chat(DEEPSEEK_MODEL, JUDGE_SYSTEM, user_prompt, MAX_TOKENS_JUDGE, sem=DEEPSEEK_SEM)
            return ("deepseek", parse_classification(text), text)
        except Exception as e:
            return ("deepseek", "ERROR", str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(judge_oss), ex.submit(judge_deepseek)]
        for fut in concurrent.futures.as_completed(futs):
            name, label, text = fut.result()
            results[name] = {"label": label, "text": text}

    valid = [r["label"] for r in results.values() if r["label"] in SCORE_MAP]
    if valid:
        from collections import Counter
        c = Counter(valid).most_common()
        consensus = c[0][0]
        n_agree = c[0][1]
    else:
        consensus = "ERROR"; n_agree = 0
    n_total = len(valid)
    return {
        "problem_id": item["problem_id"],
        "prompt_type": item["prompt_type"],
        "model": item.get("model","?"),
        "seed": item["seed"],
        "phase1_label": item.get("label"),
        "judges": results,
        "consensus": consensus,
        "n_agree": n_agree,
    }


def load_trials(path: str):
    """Load trials from either a JSONL log or a results JSON."""
    p = Path(path)
    items = []
    if p.suffix == ".jsonl":
        with open(p) as f:
            for ln in f:
                r = json.loads(ln)
                if r.get("kind") == "trial" or (r.get("gen_text") and r.get("problem_id")):
                    items.append(r)
    else:
        d = json.load(open(p))
        items = d.get("results", d.get("all_results", []))
    return items


def load_problems():
    import csv
    rows = list(csv.DictReader(open(ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv", encoding="utf-8")))
    return {(r["problem_id"], r["prompt_type"]): r["prompt"] for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="JSONL log or JSON results")
    ap.add_argument("--label-min", default="partial",
                    choices=["correct","almost","partial","incorrect"])
    args = ap.parse_args()

    items = load_trials(args.source)
    rank = {"incorrect":0, "partial":1, "almost":2, "correct":3, None:-1}
    # Use 'label' or 'best_label' (seed_full uses best_label)
    def get_label(r): return r.get("label") or r.get("best_label")
    items = [r for r in items
             if get_label(r) and rank.get(get_label(r), -1) >= rank[args.label_min]
             and (r.get("gen_text") or r.get("best_candidate"))]
    # Add 'label' field for downstream
    for r in items:
        if "label" not in r: r["label"] = r.get("best_label")
    problems = load_problems()
    print(f"Source: {args.source}")
    print(f"Items to re-judge: {len(items)}")
    if not items: return

    out_path = ROOT / "experiments/results" / f"{EXPERIMENT_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(judge_one_trial, it, problems[(it["problem_id"], it["prompt_type"])]): it
                for it in items}
        for fut in concurrent.futures.as_completed(futs):
            completed += 1
            try:
                r = fut.result()
                results.append(r)
                ms = r["model"].split("/")[-1] if r["model"] else "?"
                jstr = " ".join(f"{k}={v['label']}" for k, v in r["judges"].items())
                n_total = sum(1 for v in r["judges"].values() if v['label'] != "ERROR")
                print(f"[{completed}/{len(items)}] {r['problem_id']:<26} {r['prompt_type']:<14} {ms:<22} seed={r['seed']}  consensus={r['consensus']} ({r['n_agree']}/{n_total})  | {jstr}", flush=True)
            except Exception as e:
                print(f"[{completed}/{len(items)}] FAIL: {e}", flush=True)

    with open(out_path, "w") as f:
        json.dump({"source": args.source, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")

    print("\n=== Unanimous correct (both judges agree) ===")
    for r in results:
        n_total = sum(1 for v in r["judges"].values() if v['label'] != "ERROR")
        if r["consensus"] == "correct" and r["n_agree"] == n_total and n_total >= 2:
            ms = r["model"].split("/")[-1] if r["model"] else "?"
            print(f"  {r['problem_id']:<26} {r['prompt_type']:<14} {ms:<22} seed={r['seed']}  ({r['n_agree']}/{n_total})")


if __name__ == "__main__":
    main()
