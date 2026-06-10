#!/usr/bin/env python3
"""Drift screen for Claude Opus 4.7 (the one stale headline anchor, May 7).
Re-run Opus on a small fixed subset of the validation set, replicating the original
call (reasoning enabled / adaptive, no seed), and compare per-problem to the original
scores in consensus_analysis.csv. Captures the serving provider. ~20 calls."""
import concurrent.futures, csv, json, math, os, random, re, time
import statistics as st
from collections import Counter
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv, find_dotenv

HERE = Path(__file__).resolve().parent
DATA_CSV = HERE.parent / "gradingbench.csv"
CONS_CSV = HERE.parent / "consensus_analysis.csv"
PROMPT_MD = HERE.parent.parent / "prompts" / "pipeline" / "judge_gt.md"
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-opus-4.7"
REASONING = {"enabled": True}                 # original Opus validation config (adaptive)
MAX_TOKENS, TIMEOUT = 32768, 600
N_SUBSET, SUBSET_SEED = 20, 2026
PRIOR_SEED, PRIOR_N, VAL_SEED, VAL_N = 42, 200, 7, 200

load_dotenv(find_dotenv(), override=True)
KEY = os.getenv("OPENROUTER_API_KEY")
S = requests.Session(); S.mount("https://", HTTPAdapter(pool_connections=32, pool_maxsize=32))


def validation_sample():
    rows = []
    with open(DATA_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"grading_id": r["Grading ID"], "problem": r["Problem"],
                         "solution": r["Solution"], "response": r["Response"],
                         "human_points": int(r["Points"])})
    prior = {r["grading_id"] for r in random.Random(PRIOR_SEED).sample(rows, PRIOR_N)}
    return random.Random(VAL_SEED).sample([r for r in rows if r["grading_id"] not in prior], VAL_N)


def parse_score(t):
    if not t: return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", t, re.I)
    if m: v = int(m.group(1)); return v if 0 <= v <= 7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", t, re.I)
    return int(m.group(1)) if m else None


def call(prompt, retries=3, backoff=4.0):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS, "reasoning": REASONING}        # NO seed
    last = None
    for a in range(retries + 1):
        try:
            r = S.post(URL, json=body, timeout=TIMEOUT,
                       headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            d = r.json()
            if r.status_code != 200 or "error" in d:
                msg = str(d.get("error", d))
                if "insufficient" in msg.lower() or "credit" in msg.lower(): raise RuntimeError(msg)
                raise ValueError(f"HTTP {r.status_code}: {msg[:120]}")
            ch = d["choices"][0]; u = d.get("usage", {}) or {}
            return {"score": parse_score(ch["message"].get("content") or ch["message"].get("reasoning") or ""),
                    "provider": d.get("provider"), "served_model": d.get("model"),
                    "cost": u.get("cost") or 0.0, "finish_reason": ch.get("finish_reason")}
        except Exception as e:
            last = e
            if a < retries: time.sleep(backoff * (2 ** a))
    raise last


def main():
    # original Opus scores + human from consensus_analysis
    orig, human = {}, {}
    for r in csv.DictReader(open(CONS_CSV)):
        if r["sample"] != "validation": continue
        human[r["grading_id"]] = int(float(r["human_score"]))
        orig[r["grading_id"]] = int(float(r["claude_opus_4_7_score"])) if r["claude_opus_4_7_score"] else None
    sample = validation_sample()
    subset = random.Random(SUBSET_SEED).sample([r for r in sample if orig.get(r["grading_id"]) is not None], N_SUBSET)
    print(f"Opus 4.7 drift screen: {len(subset)} problems, reasoning={REASONING}, no seed", flush=True)
    tpl = PROMPT_MD.read_text(); t0 = time.time()

    def work(rec):
        p = (tpl.replace("{problem}", rec["problem"]).replace("{ground_truth}", rec["solution"])
                .replace("{candidate}", rec["response"]))
        try:
            o = call(p); o.update(grading_id=rec["grading_id"], human=rec["human_points"]); return o
        except Exception as e:
            return {"grading_id": rec["grading_id"], "human": rec["human_points"], "score": None,
                    "provider": None, "error": str(e)[:120], "cost": 0.0}

    recs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=N_SUBSET) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(work, r) for r in subset]):
            recs.append(fut.result())

    valid = [r for r in recs if r["score"] is not None]
    exact = sum(1 for r in valid if r["score"] == orig[r["grading_id"]])
    flips = [(r["grading_id"], orig[r["grading_id"]], r["score"]) for r in valid
             if (orig[r["grading_id"]] >= 6) != (r["score"] >= 6)]
    o_pass_r_fail = sum(1 for g, o, s in flips if o >= 6 and s < 6)
    o_fail_r_pass = sum(1 for g, o, s in flips if o < 6 and s >= 6)
    mean_orig = st.mean(orig[r["grading_id"]] for r in valid)
    mean_rerun = st.mean(r["score"] for r in valid)
    agree_orig = sum(1 for r in valid if (orig[r["grading_id"]] >= 6) == (r["human"] >= 6)) / len(valid)
    agree_rerun = sum(1 for r in valid if (r["score"] >= 6) == (r["human"] >= 6)) / len(valid)

    print(f"\n{'='*68}\nOPUS 4.7 DRIFT SCREEN (n_valid={len(valid)}/{N_SUBSET}, "
          f"wall={round(time.time()-t0)}s, cost=${sum(r['cost'] for r in recs):.2f})")
    print(f"  exact-score match vs original: {exact}/{len(valid)}")
    print(f"  pass/fail decisions changed:   {len(flips)}/{len(valid)}  "
          f"(orig-pass->rerun-fail {o_pass_r_fail}, orig-fail->rerun-pass {o_fail_r_pass})")
    print(f"  mean score:  original {mean_orig:.3f}  ->  rerun {mean_rerun:.3f}   (Δ {mean_rerun-mean_orig:+.3f})")
    print(f"  pass-agree on this subset:  original {agree_orig:.3f}  ->  rerun {agree_rerun:.3f}")
    print(f"  provider: {dict(Counter(r['provider'] for r in valid))}")
    if flips: print(f"  flipped ids (orig->rerun): {[(g,o,s) for g,o,s in flips]}")
    print(f"\n  (reference: gpt-oss drifted +0.16 mean-score, ~10% decisions flipped net-lenient)")
    json.dump(recs, open(HERE / "opus_drift_check_results.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
