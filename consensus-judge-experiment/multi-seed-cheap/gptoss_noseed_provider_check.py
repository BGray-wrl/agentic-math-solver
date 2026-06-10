#!/usr/bin/env python3
"""Audit: re-run gpt-oss-120b @ xhigh on the 200-problem validation set with NO seed
(replicating the original validation call as closely as possible) and CAPTURE the
OpenRouter serving provider per call. Tests whether the seed param explains the
leniency shift (0.875 -> ~0.84) or whether it is server-side, and records which
backend(s) serve the model now (the original run did not log this)."""
import concurrent.futures, csv, json, math, os, random, re, time
import statistics as st
from collections import Counter
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv, find_dotenv

HERE = Path(__file__).resolve().parent
DATA_CSV = HERE.parent / "gradingbench.csv"
PROMPT_MD = HERE.parent.parent / "prompts" / "pipeline" / "judge_gt.md"
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
REASONING = {"effort": "xhigh"}
MAX_TOKENS, TIMEOUT, WORKERS = 32768, 600, 200
PRIOR_SEED, PRIOR_N, VAL_SEED, VAL_N = 42, 200, 7, 200

load_dotenv(find_dotenv(), override=True)
KEY = os.getenv("OPENROUTER_API_KEY")
S = requests.Session(); S.mount("https://", HTTPAdapter(pool_connections=64, pool_maxsize=WORKERS))


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
            cd = u.get("completion_tokens_details", {}) or {}
            return {"score": parse_score(ch["message"].get("content") or ch["message"].get("reasoning") or ""),
                    "provider": d.get("provider"), "served_model": d.get("model"),
                    "reasoning_tokens": cd.get("reasoning_tokens", 0),
                    "cost": u.get("cost") or 0.0, "finish_reason": ch.get("finish_reason")}
        except Exception as e:
            last = e
            if a < retries: time.sleep(backoff * (2 ** a))
    raise last


def main():
    sample = validation_sample()
    print(f"gpt-oss @ xhigh, NO seed, capturing provider | n={len(sample)} workers={WORKERS}", flush=True)
    tpl = PROMPT_MD.read_text(); t0 = time.time(); recs = []

    def work(rec):
        p = (tpl.replace("{problem}", rec["problem"]).replace("{ground_truth}", rec["solution"])
                .replace("{candidate}", rec["response"]))
        try:
            out = call(p); out.update(grading_id=rec["grading_id"], human_points=rec["human_points"]); return out
        except Exception as e:
            return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                    "score": None, "provider": None, "error": str(e)[:120], "cost": 0.0, "reasoning_tokens": 0}

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(work, r) for r in sample]):
            recs.append(fut.result())

    valid = [r for r in recs if r["score"] is not None]
    j = [r["score"] for r in valid]; h = [r["human_points"] for r in valid]
    tp = sum(1 for r in valid if r["score"] >= 6 and r["human_points"] >= 6)
    fp = sum(1 for r in valid if r["score"] >= 6 and r["human_points"] < 6)
    tn = sum(1 for r in valid if r["score"] < 6 and r["human_points"] < 6)
    fn = sum(1 for r in valid if r["score"] < 6 and r["human_points"] >= 6)
    n = tp + fp + tn + fn
    mx, my = st.mean(j), st.mean(h)
    rr = sum((a-mx)*(b-my) for a, b in zip(j, h)) / (
        math.sqrt(sum((a-mx)**2 for a in j)) * math.sqrt(sum((b-my)**2 for b in h)))
    cost = sum(r.get("cost", 0) for r in recs)
    rt = [r["reasoning_tokens"] for r in valid if r.get("reasoning_tokens")]

    print(f"\n{'='*70}\ngpt-oss @ xhigh, NO seed  (n_valid={n}, wall={round(time.time()-t0)}s, cost=${cost:.2f})")
    print(f"  pass_agree={ (tp+tn)/n :.3f}  mean_score={mx:.3f}  judge_pass%={100*sum(1 for x in j if x>=6)/n:.1f}%")
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn}  prec={tp/(tp+fp):.3f} rec={tp/(tp+fn):.3f} r={rr:.3f}  mean_RT={st.mean(rt):.0f}")
    print(f"  PROVIDER distribution: {dict(Counter(r['provider'] for r in valid))}")
    print(f"  served_model examples: {dict(Counter(r['served_model'] for r in valid))}")
    print(f"\n  vs original (May 7): pass_agree=0.875 mean_score=2.84 FP=20 RT~6807")
    print(f"  vs seeded reruns:    pass_agree 0.829/0.835/0.849 mean_score ~3.00 FP 24-27")
    json.dump(recs, open(HERE / "gptoss_noseed_provider_check_results.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
