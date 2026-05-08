#!/usr/bin/env python3
"""
Phase 2: 3-judge consensus on positive-signal solutions from Phase 1.

Loads a Phase 1 results JSON, re-judges every (problem, solution) where
the initial label was correct/almost/partial using all THREE judges:
  gpt-oss-120b (xhigh), gemma-4-31b-it (xhigh), deepseek-v4-flash.
Reports per-solution consensus.

Usage:
  uv run experiments/openproblems_consensus_judge_20260507.py <phase1_results.json>
"""
from __future__ import annotations
import argparse, concurrent.futures, json, os, re, sys, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(str(ROOT / ".env"))

EXPERIMENT_NAME = "openproblems_consensus_judge_20260507"

JUDGES = [
    {"name": "openai/gpt-oss-120b",          "reasoning": {"effort": "xhigh"}},
    {"name": "google/gemini-3.1-pro-preview","reasoning": None},
    {"name": "deepseek/deepseek-v4-flash",   "reasoning": None},
]
MAX_TOKENS_JUDGE = 8000
HTTP_TIMEOUT = 1500
MAX_WORKERS = 60

API_KEYS = [k for k in [
    os.getenv("OPENROUTER_API_KEY_2"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k]
if not API_KEYS: raise SystemExit("no working OPENROUTER keys found")

_lock = threading.Lock()
_idx = [0]
def next_key():
    with _lock:
        k = API_KEYS[_idx[0] % len(API_KEYS)]
        _idx[0] += 1
        return k

JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate solution to a research-level open problem.
The problem asks for an explicit construction or algorithm whose correctness will ultimately be checked by a programmatic verifier.

You should classify the candidate's quality based on these criteria:
* **correct:** The construction/algorithm appears fully correct AND is in the requested output format. A reasonable verifier should accept it.
* **almost:** The core construction looks essentially right but has a small format issue, off-by-one, or minor bug that would prevent verification but is fixable.
* **partial:** Meaningful mathematical progress — a related but incomplete construction, an attempt at the right structure that doesn't quite satisfy all requirements, or an algorithm that handles only easy cases.
* **incorrect:** No real progress, refusal, fundamentally wrong approach, or completely unparseable output.

Be STRICT but FAIR. Refusals or trivial outputs are 'incorrect'.

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
    for lab in ("correct", "almost", "partial", "incorrect"):
        if lab in low: return lab
    return "incorrect"


def or_chat(model, messages, max_tokens, key, http_timeout, reasoning=None,
            retries=2, backoff=4.0):
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
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content")
            reasoning_text = choice.get("reasoning") or choice.get("reasoning_content")
            if not content: content = reasoning_text
            if not content: raise ValueError("empty response")
            usage = j.get("usage", {})
            return content, {"cost": float(usage.get("cost", 0) or 0)}
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            if attempt < retries: time.sleep(backoff * (2 ** attempt))
    raise last_err


def judge_one(problem_text, candidate, judge_cfg, key):
    text, meta = or_chat(
        model=judge_cfg["name"],
        messages=[{"role":"user","content": JUDGE_SYSTEM
                    .replace("{problem}", problem_text)
                    .replace("{candidate}", candidate)}],
        max_tokens=MAX_TOKENS_JUDGE,
        key=key,
        http_timeout=HTTP_TIMEOUT,
        reasoning=judge_cfg["reasoning"],
    )
    return parse_classification(text), text, meta


def run_consensus_for(item, problem_lookup):
    """item: a phase-1 result dict with positive signal. Return per-judge labels."""
    pid = item["problem_id"]; ptype = item["prompt_type"]
    problem_text = problem_lookup[(pid, ptype)]
    candidate = item["gen_text"] or ""

    labels = {}
    raw = {}
    cost = 0.0
    for jcfg in JUDGES:
        try:
            lab, text, meta = judge_one(problem_text, candidate, jcfg, next_key())
            labels[jcfg["name"]] = lab
            raw[jcfg["name"]] = text
            cost += meta.get("cost", 0)
        except Exception as e:
            labels[jcfg["name"]] = f"ERROR: {type(e).__name__}: {e}"
            raw[jcfg["name"]] = None

    # Consensus: majority of {correct, almost, partial, incorrect}
    valid_labels = [v for v in labels.values() if v in SCORE_MAP]
    if valid_labels:
        from collections import Counter
        counts = Counter(valid_labels).most_common()
        consensus = counts[0][0]
        agreed = counts[0][1]
    else:
        consensus = "ERROR"; agreed = 0

    return {
        "problem_id": pid, "prompt_type": ptype, "model": item["model"],
        "seed": item["seed"],
        "phase1_label": item.get("label"),
        "judge_labels": labels,
        "judge_raw": raw,
        "consensus": consensus,
        "n_agree": agreed,
        "cost": cost,
    }


def load_problems():
    import csv
    rows = list(csv.DictReader(open(ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv", encoding="utf-8")))
    return {(r["problem_id"], r["prompt_type"]): r["prompt"] for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase1_json")
    ap.add_argument("--include-incorrect", action="store_true",
                    help="Also re-judge phase-1 'incorrect' results (expensive!)")
    ap.add_argument("--label-min", default="partial",
                    choices=["correct","almost","partial","incorrect"],
                    help="Minimum phase-1 label to escalate (default: partial)")
    args = ap.parse_args()

    with open(args.phase1_json) as f:
        phase1 = json.load(f)
    problem_lookup = load_problems()

    rank = {"incorrect":0, "partial":1, "almost":2, "correct":3}
    min_rank = rank[args.label_min]

    items = [r for r in phase1["results"]
             if r.get("label") and rank.get(r["label"], -1) >= min_rank
             and r.get("gen_text")]
    print(f"Phase-1 file: {args.phase1_json}")
    print(f"Items to re-judge: {len(items)}")
    if not items:
        print("Nothing to escalate.")
        return

    out_path = Path(__file__).parent / "results" / f"{EXPERIMENT_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    results = []
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(run_consensus_for, it, problem_lookup): it for it in items}
        for fut in concurrent.futures.as_completed(futs):
            completed += 1
            try:
                r = fut.result()
                results.append(r)
                ms = r["model"].split("/")[-1]
                lab_str = " ".join(f"{k.split('/')[-1]}={v}" for k,v in r["judge_labels"].items())
                print(f"[{completed}/{len(items)}] {r['problem_id']:<26} {r['prompt_type']:<14} {ms:<24} seed={r['seed']}  consensus={r['consensus']} ({r['n_agree']}/3)  | {lab_str}", flush=True)
            except Exception as e:
                print(f"[{completed}/{len(items)}] FAIL: {e}", flush=True)

    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"phase1_source": args.phase1_json, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")

    # Top consensus picks
    print("\n=== Strongest consensus ===")
    for r in sorted(results, key=lambda x: -SCORE_MAP.get(x["consensus"],0)):
        if r["consensus"] in ("correct","almost","partial"):
            print(f"  {r['problem_id']:<26} {r['prompt_type']:<14} {r['model'].split('/')[-1]:<22} seed={r['seed']}  consensus={r['consensus']} ({r['n_agree']}/3)")


if __name__ == "__main__":
    main()
