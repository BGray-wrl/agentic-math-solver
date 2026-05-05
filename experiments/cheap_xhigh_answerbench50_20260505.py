#!/usr/bin/env python3
"""
Re-test the two cheapest tier-3 models (gpt-oss-120b, gemma-4-31b-it) at
reasoning.effort=xhigh on the full AnswerBench-50 stratified subset.

Original (default-effort) numbers:
  gpt-oss-120b: 29/50 (58%) at $0.06
  gemma-4-31b: 34/50 (68%) at $0.08

Direct OpenRouter API. 100-wide single wave (2 models × 50 PIDs).
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, os, random, re, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, requests
from dotenv import load_dotenv
load_dotenv("/Users/benjamingrayzel/sandbox/agentic-math-solver/.env")

EXPERIMENT_NAME = "cheap_xhigh_answerbench50_20260505"
SEED = 42
REASONING_EFFORT = "xhigh"

MODELS = [
    "openai/gpt-oss-120b",
    "google/gemma-4-31b-it",
]
JUDGE_MODEL = "google/gemini-3.1-flash-lite-preview"

MAX_TOKENS_GEN = 65536
MAX_TOKENS_JUDGE = 4000
GEN_HTTP_TIMEOUT   = 1500
JUDGE_HTTP_TIMEOUT = 120
TRIAL_TIMEOUT      = 1700
MAX_WORKERS        = 100  # 2 × 50

STRATA = {"Algebra": 12, "Combinatorics": 13, "Geometry": 12, "Number theory": 13}

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
ANSWERBENCH_CSV = ROOT / "benchmarks" / "IMO-bench" / "answerbench_v2.csv"

PRICE_COMPARE_KEY = os.getenv("OPENROUTER_API_KEY_price_compare")
JUDGE_KEY = os.getenv("OPENROUTER_API_KEY_X") or os.getenv("OPENROUTER_API_KEY")
if not PRICE_COMPARE_KEY: raise SystemExit("price_compare key missing")
if not JUDGE_KEY:         raise SystemExit("judge key missing")

def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _ts():  return datetime.now(timezone.utc).strftime("%H:%M:%S")


def or_chat(model, messages, max_tokens, key, http_timeout, reasoning=None,
            retries=2, backoff=4.0):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning is not None:
        body["reasoning"] = reasoning
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
            if content is None: content = reasoning_text
            if content is None: raise ValueError("empty response")
            usage = j.get("usage", {})
            cd = usage.get("completion_tokens_details") or {}
            return content, {
                "prompt_tokens":     int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens":      int(usage.get("total_tokens", 0) or 0),
                "reasoning_tokens":  int(cd.get("reasoning_tokens", 0) or 0),
            }, reasoning_text
        except Exception as e:
            last_err = e
            msg = str(e)
            if "402" in msg or "insufficient" in msg.lower(): raise
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"[{_ts()}] [retry] {model} attempt {attempt+1}: {e}, retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
    raise last_err  # type: ignore


VERDICT_RE = re.compile(r"<verdict>\s*(correct|incorrect)\s*</verdict>", re.I)
def parse_verdict(text):
    if text is None: return None
    m = VERDICT_RE.search(text)
    if m: return 1 if m.group(1).lower() == "correct" else 0
    head = (text or "")[:200].lower()
    if "verdict>correct" in head: return 1
    if "verdict>incorrect" in head: return 0
    return None

def load_prompt(name): return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()

def load_problems():
    """Stratified 50 from answerbench_v2.csv with seed=42."""
    with open(ANSWERBENCH_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_cat = {}
    for r in rows:
        cat = r["Category"]
        if cat not in STRATA: continue
        by_cat.setdefault(cat, []).append(r)
    rng = random.Random(SEED)
    selected = {}
    for cat, n in STRATA.items():
        pool = sorted(by_cat[cat], key=lambda r: r["Problem ID"])
        chosen = rng.sample(pool, n)
        for row in chosen:
            pid = row["Problem ID"]
            selected[pid] = {
                "text": row["Problem"].strip(),
                "short_answer": row["Short Answer"].strip(),
                "category": row["Category"],
                "subcategory": row.get("Subcategory", "").strip(),
                "source": row.get("Source", "").strip(),
            }
    return selected


def run_trial(model, pid, problem, prompts, mock):
    np.random.seed(SEED); random.seed(SEED)
    short = model.split("/")[-1]
    tag = f"[{_ts()}] [{pid}|{short}-xhigh]"
    t0 = time.time()
    if mock:
        return _mk(model, pid, problem, 1, "Mock\n<answer>X</answer>",
                   "<verdict>correct</verdict>",
                   {"prompt_tokens":100,"completion_tokens":50,"total_tokens":150,"reasoning_tokens":40},
                   {"prompt_tokens":200,"completion_tokens":20,"total_tokens":220},
                   0.005, 0.005, 0.01, None)

    print(f"{tag} generate", flush=True)
    gen_t0 = time.time()
    try:
        gen_text, gen_usage, reasoning_text = or_chat(
            model=model,
            messages=[
                {"role":"system","content":prompts["generator"]},
                {"role":"user","content":problem["text"]},
            ],
            max_tokens=MAX_TOKENS_GEN,
            key=PRICE_COMPARE_KEY,
            http_timeout=GEN_HTTP_TIMEOUT,
            reasoning={"effort": REASONING_EFFORT},
        )
        gen_elapsed = round(time.time() - gen_t0, 2)
        print(f"{tag} gen {gen_elapsed}s in={gen_usage['prompt_tokens']} out={gen_usage['completion_tokens']} reason={gen_usage['reasoning_tokens']}", flush=True)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} GEN FAILED: {e} ({elapsed}s)", flush=True)
        return _err(model, pid, problem, str(e), elapsed)

    judge_prompt = (prompts["judge"]
                    .replace("{problem}", problem["text"])
                    .replace("{ground_truth}", problem["short_answer"])
                    .replace("{candidate}", gen_text))
    judge_t0 = time.time()
    try:
        judge_text, judge_usage, _ = or_chat(
            model=JUDGE_MODEL,
            messages=[{"role":"user","content":judge_prompt}],
            max_tokens=MAX_TOKENS_JUDGE,
            key=JUDGE_KEY, http_timeout=JUDGE_HTTP_TIMEOUT,
        )
        judge_elapsed = round(time.time() - judge_t0, 2)
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"{tag} JUDGE FAILED: {e} ({elapsed}s)", flush=True)
        return _err(model, pid, problem, f"judge: {e}", elapsed,
                    gen_text=gen_text, gen_usage=gen_usage, gen_elapsed=gen_elapsed)

    score = parse_verdict(judge_text)
    elapsed_total = round(time.time() - t0, 2)
    print(f"{tag} -> verdict={score} total={elapsed_total}s", flush=True)
    return _mk(model, pid, problem, score, gen_text, judge_text, gen_usage, judge_usage,
               gen_elapsed, judge_elapsed, elapsed_total, reasoning_text)


def _mk(model, pid, problem, score, gen_text, verdict, gen_usage, judge_usage,
        gen_elapsed, judge_elapsed, elapsed_total, reasoning_text):
    return {
        "problem_id": pid, "category": problem["category"], "subcategory": problem["subcategory"],
        "short_answer": problem["short_answer"], "model": f"openrouter/{model}",
        "reasoning_effort": REASONING_EFFORT, "seed": SEED,
        "score": score, "passed": bool(score) if score is not None else False,
        "elapsed_s": elapsed_total, "gen_elapsed_s": gen_elapsed, "judge_elapsed_s": judge_elapsed,
        "gen_usage": gen_usage, "judge_usage": judge_usage,
        "final_solution": gen_text, "reasoning_text": reasoning_text, "verdict": verdict,
    }

def _err(model, pid, problem, err, elapsed, gen_text=None, gen_usage=None, gen_elapsed=None):
    return {
        "problem_id": pid, "category": problem["category"], "subcategory": problem["subcategory"],
        "short_answer": problem["short_answer"], "model": f"openrouter/{model}",
        "reasoning_effort": REASONING_EFFORT, "seed": SEED,
        "score": None, "passed": False, "elapsed_s": elapsed,
        "gen_elapsed_s": gen_elapsed, "judge_elapsed_s": None,
        "gen_usage": gen_usage, "judge_usage": None,
        "final_solution": gen_text, "reasoning_text": None, "verdict": None, "error": err,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    problems = load_problems()
    prompts = {
        "generator": load_prompt("generator.md"),
        "judge":     load_prompt("answerbench_judge.md"),
    }
    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Models: {MODELS}  effort={REASONING_EFFORT}")
    print(f"Problems: {len(problems)}")
    if args.mock: print("[MOCK]")

    out_partial = RESULTS_DIR / f"{EXPERIMENT_NAME}_partial.json"
    print(f"Partial saves: {out_partial}\n", flush=True)

    pids = sorted(problems.keys())
    trials = [(m, pid) for m in MODELS for pid in pids]
    total = len(trials)
    results = []
    completed = 0

    def _run(m, pid): return run_trial(m, pid, problems[pid], prompts, args.mock)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_run, m, pid): (m, pid) for m, pid in trials}
        for fut in concurrent.futures.as_completed(futs, timeout=TRIAL_TIMEOUT * total):
            m, pid = futs[fut]
            completed += 1
            try:
                r = fut.result(timeout=TRIAL_TIMEOUT)
            except Exception as e:
                print(f"[{_ts()}] FAILED [{pid}|{m}]: {e}", flush=True)
                traceback.print_exc()
                r = _err(m, pid, problems[pid], str(e), 0)
            results.append(r)
            with open(out_partial, "w", encoding="utf-8") as f:
                json.dump({"experiment": EXPERIMENT_NAME, "n_results": len(results),
                           "results": results}, f, indent=2, ensure_ascii=False)
            print(f"[{_ts()}] Progress {completed}/{total}", flush=True)

    print(f"\nWall-clock: {round(time.time()-t0,1)}s")

    PRICES = {
        "openai/gpt-oss-120b":   (0.04e-6, 0.18e-6),
        "google/gemma-4-31b-it": (0.13e-6, 0.38e-6),
    }
    for model in MODELS:
        rs = [r for r in results if r["model"] == f"openrouter/{model}"]
        valid = [r for r in rs if r["score"] is not None]
        n_correct = sum(r["score"] for r in valid)
        in_t  = [r['gen_usage']['prompt_tokens']     for r in valid if r.get('gen_usage')]
        out_t = [r['gen_usage']['completion_tokens'] for r in valid if r.get('gen_usage')]
        rea_t = [r['gen_usage'].get('reasoning_tokens', 0) for r in valid if r.get('gen_usage')]
        pin, pout = PRICES[model]
        cost = sum(i*pin + o*pout for i,o in zip(in_t, out_t))
        print(f"\n=== {model} @ {REASONING_EFFORT} ===")
        print(f"Acc: {n_correct}/{len(valid)} = {100*n_correct/len(valid):.0f}%")
        print(f"Cost: ${cost:.4f} total, ${cost/len(valid):.5f}/run")
        print(f"Mean: in={int(np.mean(in_t)) if in_t else 0} out={int(np.mean(out_t)) if out_t else 0} reasoning={int(np.mean(rea_t)) if rea_t else 0}")
        if valid:
            lats = [r['gen_elapsed_s'] for r in valid if r.get('gen_elapsed_s')]
            if lats:
                print(f"Lat: mean {np.mean(lats):.1f}s median {np.median(lats):.1f}s")

    out_path = RESULTS_DIR / f"{EXPERIMENT_NAME}_{_now()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment": EXPERIMENT_NAME, "date": datetime.now(timezone.utc).isoformat(),
                   "models": MODELS, "reasoning_effort": REASONING_EFFORT,
                   "judge_model": JUDGE_MODEL, "all_results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
