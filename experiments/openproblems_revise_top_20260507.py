#!/usr/bin/env python3
"""
Phase 3a: For each (problem, model) where Phase 1 produced a positive-signal
solution, run a verify→revise loop (3 iterations) starting from that solution
to try to push it from partial → almost → correct.

Usage:
  uv run experiments/openproblems_revise_top_20260507.py <phase1_results.json>
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, os, re, sys, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(str(ROOT / ".env"))

EXPERIMENT_NAME = "openproblems_revise_top_20260507"

# Use the same model that produced the original solution for verify+revise
JUDGE_MODEL = "deepseek/deepseek-v4-flash"
ITERATIONS  = 3
MAX_TOKENS_GEN   = 60000
MAX_TOKENS_JUDGE = 4000
HTTP_TIMEOUT = 1500
MAX_WORKERS = 12

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

# Per-model semaphores
_model_sem = {
    "google/gemma-4-31b-it":      threading.Semaphore(4),
    "openai/gpt-oss-120b":        threading.Semaphore(20),
    "deepseek/deepseek-v4-flash": threading.Semaphore(40),
}

VERIFIER_SYSTEM = """You are an expert mathematician acting as a rigorous verifier for a research-level construction.

You are given a problem (which asks for an explicit construction or algorithm) and a candidate solution.
Identify CONCRETE FLAWS in the candidate that would prevent it from passing a programmatic verifier:
- Output-format errors (wrong format, extra/missing sections, wrong syntax)
- Mathematical errors (wrong values, broken constraints, dimension mismatch)
- Off-by-one or sign errors
- Missing pieces (e.g., one of the required equations is not provided)

Be very specific: cite the exact location of the flaw and explain what should be there instead.

If the solution looks correct and well-formatted, end your response with "VERDICT: correct".
If issues are found, end your response with "VERDICT: issues_found".

---

**PROBLEM:**
{problem}

**CANDIDATE SOLUTION:**
{candidate}
"""

REVISER_SYSTEM = """You are an expert mathematician revising a candidate solution to a research-level construction problem based on specific feedback.

Address EVERY flaw the verifier identified. Re-output the FULL solution in the format the problem requires.
Make sure the FINAL answer is in EXACTLY the format the problem specifies.

Structure your response as:

## Approach
[Brief: what you changed and why]

## Answer
[The final answer in EXACTLY the format the problem requests, and nothing else.]

---

**PROBLEM:**
{problem}

**PREVIOUS CANDIDATE:**
{candidate}

**VERIFIER FEEDBACK:**
{feedback}
"""

JUDGE_SYSTEM = """You are an expert mathematician evaluating a candidate solution to a research-level open problem.
The problem asks for an explicit construction or algorithm whose correctness will ultimately be checked by a programmatic verifier.

Classify based on these criteria:
* **correct:** Construction/algorithm appears fully correct AND in the requested format. A reasonable verifier should accept it.
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
                raise RuntimeError(f"429 after retries: {r.text[:120]}")
            r.raise_for_status()
            j = r.json()
            choice = j["choices"][0]["message"]
            content = choice.get("content") or choice.get("reasoning") or choice.get("reasoning_content")
            if not content: raise ValueError("empty response")
            usage = j.get("usage", {})
            return content, {
                "cost": float(usage.get("cost", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0),
            }
        except Exception as e:
            last_err = e
            if "402" in str(e): raise
            if attempt < retries:
                wait = backoff * (2 ** min(attempt, 4))
                time.sleep(wait)
    raise last_err


def revise_one(item, problem_lookup):
    pid = item["problem_id"]; ptype = item["prompt_type"]
    problem_text = problem_lookup[(pid, ptype)]
    model = item["model"]
    reasoning = {"effort": "xhigh"} if "deepseek-v4-flash" not in model else None
    candidate = item["gen_text"]
    short = model.split("/")[-1]
    tag = f"[{pid}|{ptype}|{short}|seed={item['seed']}]"

    history = [{"iteration": 0, "candidate": candidate, "label": item.get("label")}]
    cost = 0.0
    for i in range(ITERATIONS):
        # Verify
        try:
            v_text, v_meta = or_chat(
                model=model,
                messages=[{"role":"user","content": VERIFIER_SYSTEM
                            .replace("{problem}", problem_text)
                            .replace("{candidate}", candidate)}],
                max_tokens=MAX_TOKENS_GEN, key=next_key(), http_timeout=HTTP_TIMEOUT, reasoning=reasoning,
            )
            cost += v_meta.get("cost", 0)
        except Exception as e:
            history.append({"iteration": i+1, "phase": "verify", "error": str(e)})
            break
        if "VERDICT: correct" in v_text:
            history.append({"iteration": i+1, "phase": "verify", "verdict": "correct", "feedback": v_text})
            break
        # Revise
        try:
            new_text, r_meta = or_chat(
                model=model,
                messages=[{"role":"user","content": REVISER_SYSTEM
                            .replace("{problem}", problem_text)
                            .replace("{candidate}", candidate)
                            .replace("{feedback}", v_text)}],
                max_tokens=MAX_TOKENS_GEN, key=next_key(), http_timeout=HTTP_TIMEOUT, reasoning=reasoning,
            )
            cost += r_meta.get("cost", 0)
        except Exception as e:
            history.append({"iteration": i+1, "phase": "revise", "error": str(e), "feedback": v_text})
            break
        history.append({"iteration": i+1, "feedback": v_text, "candidate": new_text})
        candidate = new_text
        print(f"[{tag}] iter {i+1} done", flush=True)

    # Final judge
    try:
        j_text, j_meta = or_chat(
            model=JUDGE_MODEL,
            messages=[{"role":"user","content": JUDGE_SYSTEM
                        .replace("{problem}", problem_text)
                        .replace("{candidate}", candidate)}],
            max_tokens=MAX_TOKENS_JUDGE, key=next_key(), http_timeout=HTTP_TIMEOUT, reasoning=None,
        )
        cost += j_meta.get("cost", 0)
        final_label = parse_classification(j_text)
    except Exception as e:
        j_text = f"ERROR: {e}"
        final_label = "ERROR"

    print(f"[{tag}] final={final_label}  (was {item.get('label')})  cost=${cost:.3f}", flush=True)
    return {
        "problem_id": pid, "prompt_type": ptype, "model": model, "seed": item["seed"],
        "phase1_label": item.get("label"),
        "final_label": final_label,
        "final_candidate": candidate,
        "history": history,
        "judge_text": j_text,
        "cost": cost,
    }


def load_problems():
    rows = list(csv.DictReader(open(ROOT / "benchmarks" / "frontiermath-open-problems" / "open_problems_prompts.csv", encoding="utf-8")))
    return {(r["problem_id"], r["prompt_type"]): r["prompt"] for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase1_json")
    ap.add_argument("--label-min", default="partial",
                    choices=["correct","almost","partial"])
    ap.add_argument("--max-items", type=int, default=20, help="Cap items processed (cost guard)")
    args = ap.parse_args()

    with open(args.phase1_json) as f:
        phase1 = json.load(f)
    problem_lookup = load_problems()

    rank = {"incorrect":0, "partial":1, "almost":2, "correct":3}
    min_rank = rank[args.label_min]
    items = [r for r in phase1["results"]
             if r.get("label") and rank.get(r["label"], -1) >= min_rank
             and r.get("gen_text")]
    items.sort(key=lambda x: -rank[x["label"]])
    items = items[:args.max_items]

    print(f"Items to revise: {len(items)} (label >= {args.label_min}, cap {args.max_items})")
    if not items: return

    out_path = Path(__file__).parent / "results" / f"{EXPERIMENT_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(exist_ok=True)
    results = []
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(revise_one, it, problem_lookup): it for it in items}
        for fut in concurrent.futures.as_completed(futs):
            completed += 1
            try:
                r = fut.result()
                results.append(r)
            except Exception as e:
                print(f"FAIL: {e}")
            print(f"Progress: {completed}/{len(items)}", flush=True)

    with open(out_path, "w") as f:
        json.dump({"phase1_source": args.phase1_json, "results": results}, f, indent=2, ensure_ascii=False)
    total_cost = sum(r["cost"] for r in results)
    print(f"\nSaved: {out_path}")
    print(f"Total cost: ${total_cost:.2f}")

    print("\n=== Improvements ===")
    for r in sorted(results, key=lambda x: -SCORE_MAP.get(x["final_label"],0)):
        delta = SCORE_MAP.get(r["final_label"],0) - SCORE_MAP.get(r["phase1_label"],0)
        sign = "+" if delta > 0 else ("=" if delta == 0 else "-")
        print(f"  {r['problem_id']:<26} {r['prompt_type']:<14} {r['model'].split('/')[-1]:<22} seed={r['seed']}  {r['phase1_label']} → {r['final_label']} [{sign}]")


if __name__ == "__main__":
    main()
