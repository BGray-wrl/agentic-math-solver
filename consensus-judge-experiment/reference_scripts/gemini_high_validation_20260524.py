#!/usr/bin/env python3
"""Gemini-3.1-pro @ reasoning effort=HIGH on the 200-problem seed=7 validation
sample, via DIRECT OpenRouter HTTP (litellm mis-reports this key). Tests whether
high reasoning lifts Gemini above gpt-oss-120b@xhigh on pass-agreement.

PRESERVES max_tokens=32768, timeout=600 (do not shorten — cuts off thought).
Uses OpenRouter usage.cost (exact billing). $35 cost cap.
"""
import concurrent.futures, csv, json, math, os, random, time, threading, requests
import statistics as st
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

csv.field_size_limit(10**7)
load_dotenv(override=True)
KEY = os.getenv("OPENROUTER_API_KEY")

MODEL = "google/gemini-3.1-pro-preview"
REASONING = {"effort": "high"}
MAX_TOKENS = 32768          # preserved
TIMEOUT = 600               # preserved
MAX_WORKERS = 40
COST_CAP = 35.0
PRIOR_SEED, PRIOR_N, VAL_SEED, VAL_N = 42, 200, 7, 200
URL = "https://openrouter.ai/api/v1/chat/completions"
PROMPT = Path("../prompts/pipeline/judge_gt.md").read_text()


def load_validation_sample():
    rows = []
    with open("gradingbench.csv", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"grading_id": r["Grading ID"], "problem_id": r["Problem ID"],
                         "problem": r["Problem"], "solution": r["Solution"],
                         "response": r["Response"], "human_points": int(r["Points"]),
                         "source": r["Problem Source"]})
    old_ids = {r["grading_id"] for r in random.Random(PRIOR_SEED).sample(rows, PRIOR_N)}
    remaining = [r for r in rows if r["grading_id"] not in old_ids]
    new_sample = random.Random(VAL_SEED).sample(remaining, VAL_N)
    assert not (old_ids & {r["grading_id"] for r in new_sample}), "OVERLAP"
    return new_sample


def parse_score(text):
    import re
    if not text:
        return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m:
        v = int(m.group(1)); return v if 0 <= v <= 7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    return int(m.group(1)) if m else None


def call(prompt, retries=2, backoff=4.0):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS, "reasoning": REASONING}
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(URL, headers={"Authorization": f"Bearer {KEY}",
                              "Content-Type": "application/json"}, json=body, timeout=TIMEOUT)
            d = r.json()
            if r.status_code != 200 or "error" in d:
                msg = str(d.get("error", d))
                if "insufficient" in msg.lower() or "credit" in msg.lower():
                    raise RuntimeError(msg)  # non-retryable
                raise ValueError(f"HTTP {r.status_code}: {msg[:160]}")
            ch = d["choices"][0]; u = d.get("usage", {})
            cd = u.get("completion_tokens_details", {}) or {}
            msg = ch["message"]
            content = msg.get("content") or msg.get("reasoning") or ""
            return content, {
                "prompt_tokens": u.get("prompt_tokens", 0),
                "completion_tokens": u.get("completion_tokens", 0),
                "reasoning_tokens": cd.get("reasoning_tokens", 0),
                "total_tokens": u.get("total_tokens", 0),
                "cost": u.get("cost", 0.0),
                "finish_reason": ch.get("finish_reason"),
            }
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last


def pearson(xs, ys):
    if len(xs) < 2: return 0.0
    mx, my = st.mean(xs), st.mean(ys)
    n = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs)); dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return n / (dx * dy) if dx > 0 and dy > 0 else 0.0


def stats_block(results):
    valid = [r for r in results if r.get("score") is not None]
    nv = len(valid)
    if nv == 0:
        return {"n": len(results), "n_valid": 0}
    h = [r["human_points"] for r in valid]; j = [r["score"] for r in valid]
    hp = [x >= 6 for x in h]; jp = [x >= 6 for x in j]
    tp = sum(1 for a, b in zip(hp, jp) if a and b); fp = sum(1 for a, b in zip(hp, jp) if not a and b)
    tn = sum(1 for a, b in zip(hp, jp) if not a and not b); fn = sum(1 for a, b in zip(hp, jp) if a and not b)
    prec = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"n": len(results), "n_valid": nv,
            "pass_agree_at_6": round((tp + tn) / nv, 4), "precision_at_6": round(prec, 4),
            "recall_at_6": round(rec, 4), "f1_at_6": round(f1, 4),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "pearson_r": round(pearson([float(x) for x in j], [float(x) for x in h]), 4),
            "mean_J": round(st.mean(j), 3), "mean_H": round(st.mean(h), 3),
            "mean_reasoning_tok": int(st.mean([r["usage"].get("reasoning_tokens", 0) for r in valid])),
            "cost_usd": round(sum(r.get("cost", 0) for r in results), 4)}


def main():
    sample = load_validation_sample()
    from collections import Counter
    print(f"Gemini @ effort=high | {len(sample)} problems (seed={VAL_SEED}) | "
          f"dist={dict(sorted(Counter(r['human_points'] for r in sample).items()))}", flush=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(f"gemini_high_validation_20260524_{ts}.json")
    partial = out_path.with_name(out_path.stem + "_partial.json")
    cost_state = {"spent": 0.0, "capped": False}; lock = threading.Lock()

    def worker(rec):
        with lock:
            if cost_state["capped"]:
                return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                        "score": None, "error": "cost cap", "cost": 0.0, "elapsed": 0.0}
        prompt = (PROMPT.replace("{problem}", rec["problem"])
                        .replace("{ground_truth}", rec["solution"])
                        .replace("{candidate}", rec["response"]))
        t0 = time.time()
        try:
            content, u = call(prompt)
            el = round(time.time() - t0, 1)
            score = parse_score(content)
            with lock:
                cost_state["spent"] += u["cost"]
                if cost_state["spent"] >= COST_CAP and not cost_state["capped"]:
                    cost_state["capped"] = True
                    print(f"\n[!! COST CAP ${cost_state['spent']:.2f} >= ${COST_CAP} !!]\n", flush=True)
            d = (score - rec["human_points"]) if score is not None else None
            trunc = " TRUNC!" if u["finish_reason"] == "length" else ""
            print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {rec['grading_id']:8s} pts={rec['human_points']} "
                  f"score={score} D={d if d is not None else 'NA'} ${u['cost']:.4f} {el}s "
                  f"rt={u['reasoning_tokens']} cum=${cost_state['spent']:.2f}{trunc}", flush=True)
            return {"grading_id": rec["grading_id"], "problem_id": rec["problem_id"],
                    "human_points": rec["human_points"], "source": rec["source"],
                    "score": score, "verdict": content, "usage": u,
                    "cost": u["cost"], "elapsed": el, "finish_reason": u["finish_reason"]}
        except Exception as e:
            print(f"[FAIL] {rec['grading_id']}: {str(e)[:140]}", flush=True)
            return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                    "score": None, "error": str(e), "cost": 0.0, "elapsed": round(time.time() - t0, 1)}

    results = []; t0 = time.time(); last_save = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(worker, r) for r in sample]):
            results.append(fut.result())
            if len(results) - last_save >= 10:
                last_save = len(results)
                s = stats_block(results)
                print(f"  --- {len(results)}/{len(sample)} | valid={s.get('n_valid')} "
                      f">=6agr={s.get('pass_agree_at_6')} F1={s.get('f1_at_6')} r={s.get('pearson_r')} "
                      f"${s.get('cost_usd')} ---", flush=True)
                json.dump({"is_partial": True, "n_done": len(results), "stats": s, "results": results},
                          open(partial, "w"), ensure_ascii=False)

    el = round(time.time() - t0, 1); s = stats_block(results)
    final = {"experiment": "gemini_high_validation_20260524", "model": MODEL, "reasoning": REASONING,
             "max_tokens": MAX_TOKENS, "sample_seed": VAL_SEED, "n": len(sample),
             "n_done": len(results), "wall_clock_s": el, "cost_capped": cost_state["capped"],
             "total_cost_usd": round(cost_state["spent"], 4), "stats": s,
             "date": datetime.now(timezone.utc).isoformat(), "results": results}
    json.dump(final, open(out_path, "w"), indent=2, ensure_ascii=False)
    n_trunc = sum(1 for r in results if r.get("finish_reason") == "length")
    print(f"\n{'='*70}\nFINAL: n_valid={s.get('n_valid')}/{len(sample)} truncated={n_trunc} "
          f"wall={el}s cost=${cost_state['spent']:.2f}")
    print(f"  pass_agree@6={s.get('pass_agree_at_6')} prec={s.get('precision_at_6')} "
          f"rec={s.get('recall_at_6')} F1={s.get('f1_at_6')} r={s.get('pearson_r')} "
          f"mean_reasoning_tok={s.get('mean_reasoning_tok')}")
    print(f"  confusion TP={s.get('tp')} FP={s.get('fp')} TN={s.get('tn')} FN={s.get('fn')}")
    print(f"  Saved: {out_path}\n  (gpt-oss@xhigh ref: 0.875/0.806/0.676 | gemini-default ref: 0.840/0.771/0.766)")
    if partial.exists():
        partial.unlink()


if __name__ == "__main__":
    main()
