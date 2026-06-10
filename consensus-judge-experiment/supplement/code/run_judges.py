#!/usr/bin/env python3
"""Reference runner (provenance): how we queried the cheap judges.

Grades the three cheap judges across the 600 GradingBench problems not in the
prior (seed 42) or validation (seed 7) samples, via direct OpenRouter HTTP.
Preserves each model's reasoning params; max_tokens=32768, timeout=600; records
OpenRouter's exact usage.cost (falls back to flat $/M if absent). Parallel: 80
workers per model, 3 models concurrent.

To run you need: (1) IMO-GradingBench (Luong et al., 2025; not redistributed --
see README), with its path in the GRADINGBENCH environment variable, and (2)
OPENROUTER_API_KEY in the environment. The prompt is read from ../prompt/judge_gt.md.
"""
import concurrent.futures, csv, json, math, os, random, time, threading, requests
import statistics as st
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

csv.field_size_limit(10**7)
load_dotenv(override=True)
KEY = os.getenv("OPENROUTER_API_KEY")

MAX_TOKENS = 32768          # preserved
TIMEOUT = 600               # preserved
WORKERS_PER_MODEL = 80
PRIOR_SEED, PRIOR_N, VAL_SEED, VAL_N = 42, 200, 7, 200
URL = "https://openrouter.ai/api/v1/chat/completions"
GRADINGBENCH = os.environ.get("GRADINGBENCH", "gradingbench.csv")  # external benchmark; not redistributed
PROMPT = (Path(__file__).resolve().parent.parent / "prompt" / "judge_gt.md").read_text()

CONFIGS = [
    {"judge_id": "deepseek-v4-flash", "model": "deepseek/deepseek-v4-flash",
     "reasoning_config": "default", "reasoning": None,
     "flat_per_M": 0.28, "cost_cap": 8.0},
    {"judge_id": "gpt-oss-120b", "model": "openai/gpt-oss-120b",
     "reasoning_config": "xhigh", "reasoning": {"effort": "xhigh"},
     "flat_per_M": 0.15, "cost_cap": 8.0},
    {"judge_id": "gemma-4-31b-it", "model": "google/gemma-4-31b-it",
     "reasoning_config": "high", "reasoning": {"effort": "high"},
     "flat_per_M": 0.38, "cost_cap": 8.0},
]

_print_lock = threading.Lock()
def log(msg):
    with _print_lock:
        print(msg, flush=True)


def load_remaining_sample():
    rows = []
    with open(GRADINGBENCH, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"grading_id": r["Grading ID"], "problem_id": r["Problem ID"],
                         "problem": r["Problem"], "solution": r["Solution"],
                         "response": r["Response"], "human_points": int(r["Points"]),
                         "source": r["Problem Source"]})
    prior_ids = {r["grading_id"] for r in random.Random(PRIOR_SEED).sample(rows, PRIOR_N)}
    after_prior = [r for r in rows if r["grading_id"] not in prior_ids]
    val_ids = {r["grading_id"] for r in random.Random(VAL_SEED).sample(after_prior, VAL_N)}
    used = prior_ids | val_ids
    remaining = [r for r in rows if r["grading_id"] not in used]
    assert not (used & {r["grading_id"] for r in remaining}), "OVERLAP with prior/validation"
    return rows, remaining


def parse_score(text):
    import re
    if not text:
        return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m:
        v = int(m.group(1)); return v if 0 <= v <= 7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    return int(m.group(1)) if m else None


def call(cfg, prompt, retries=2, backoff=4.0):
    body = {"model": cfg["model"], "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS}
    if cfg["reasoning"]:
        body["reasoning"] = cfg["reasoning"]
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
            ch = d["choices"][0]; u = d.get("usage", {}) or {}
            cd = u.get("completion_tokens_details", {}) or {}
            content = ch["message"].get("content") or ch["message"].get("reasoning") or ""
            tot = u.get("total_tokens", 0) or 0
            cost = u.get("cost")
            if not cost:  # fall back to flat $/M total tokens
                cost = round(cfg["flat_per_M"] * tot / 1e6, 6)
            return content, {"prompt_tokens": u.get("prompt_tokens", 0),
                             "completion_tokens": u.get("completion_tokens", 0),
                             "reasoning_tokens": cd.get("reasoning_tokens", 0),
                             "total_tokens": tot, "cost": cost,
                             "finish_reason": ch.get("finish_reason")}
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
    sig_agree = sum(1 for a, b in zip(h, j) if (a >= 1) == (b >= 1)) / nv
    return {"n": len(results), "n_valid": nv,
            "pass_agree_at_6": round((tp + tn) / nv, 4), "precision_at_6": round(prec, 4),
            "recall_at_6": round(rec, 4), "f1_at_6": round(f1, 4),
            "signal_agree_at_1": round(sig_agree, 4),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "pearson_r": round(pearson([float(x) for x in j], [float(x) for x in h]), 4),
            "mean_judge": round(st.mean(j), 3), "mean_human": round(st.mean(h), 3),
            "mean_reasoning_tok": int(st.mean([r["usage"].get("reasoning_tokens", 0) for r in valid])),
            "cost_usd": round(sum(r.get("cost", 0) for r in results), 4)}


def run_config(cfg, sample, ts):
    jid, rc = cfg["judge_id"], cfg["reasoning_config"]
    tag = f"{jid}@{rc}"
    out_path = Path(f"judge_remaining600_{jid}_{rc}_20260524_{ts}.json")
    partial = out_path.with_name(out_path.stem + "_partial.json")
    cost_state = {"spent": 0.0, "capped": False}; lock = threading.Lock()

    def worker(rec):
        with lock:
            if cost_state["capped"]:
                return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                        "score": None, "error": "cost cap", "cost": 0.0}
        prompt = (PROMPT.replace("{problem}", rec["problem"])
                        .replace("{ground_truth}", rec["solution"])
                        .replace("{candidate}", rec["response"]))
        try:
            content, u = call(cfg, prompt)
            score = parse_score(content)
            with lock:
                cost_state["spent"] += u["cost"]
                if cost_state["spent"] >= cfg["cost_cap"] and not cost_state["capped"]:
                    cost_state["capped"] = True
                    log(f"[!! {tag} COST CAP ${cost_state['spent']:.2f} !!]")
            return {"grading_id": rec["grading_id"], "problem_id": rec["problem_id"],
                    "human_points": rec["human_points"], "source": rec["source"],
                    "score": score, "verdict": content, "usage": u,
                    "cost": u["cost"], "finish_reason": u["finish_reason"]}
        except Exception as e:
            return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                    "score": None, "error": str(e), "cost": 0.0}

    results = []; t0 = time.time(); last = 0
    log(f"START {tag}: {len(sample)} problems, {WORKERS_PER_MODEL} workers")
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS_PER_MODEL) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(worker, r) for r in sample]):
            results.append(fut.result())
            if len(results) - last >= 50:
                last = len(results); s = stats_block(results)
                log(f"  [{tag}] {len(results)}/{len(sample)} valid={s.get('n_valid')} "
                    f">=6agr={s.get('pass_agree_at_6')} F1={s.get('f1_at_6')} ${s.get('cost_usd')}")
                json.dump({"is_partial": True, "n_done": len(results), "stats": s,
                           "results": results}, open(partial, "w"), ensure_ascii=False)

    el = round(time.time() - t0, 1); s = stats_block(results)
    n_trunc = sum(1 for r in results if r.get("finish_reason") == "length")
    final = {"experiment": "judge_remaining600", "judge_id": jid, "model": cfg["model"],
             "reasoning_config": rc, "reasoning": cfg["reasoning"], "max_tokens": MAX_TOKENS,
             "sample": "remaining_600", "n": len(sample), "n_done": len(results),
             "wall_clock_s": el, "cost_capped": cost_state["capped"],
             "total_cost_usd": round(cost_state["spent"], 4), "n_truncated": n_trunc,
             "stats": s, "date": datetime.now(timezone.utc).isoformat(), "results": results}
    json.dump(final, open(out_path, "w"), indent=2, ensure_ascii=False)
    if partial.exists(): partial.unlink()
    log(f"DONE {tag}: valid={s.get('n_valid')}/{len(sample)} trunc={n_trunc} wall={el}s "
        f"cost=${cost_state['spent']:.2f} >=6agr={s.get('pass_agree_at_6')} "
        f"F1={s.get('f1_at_6')} r={s.get('pearson_r')} -> {out_path}")
    return jid, final


def main():
    import sys
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    all_rows, sample = load_remaining_sample()
    from collections import Counter
    log(f"GradingBench total={len(all_rows)} | remaining (not in prior+val) = {len(sample)}")
    log(f"score dist (remaining): {dict(sorted(Counter(r['human_points'] for r in sample).items()))}")
    if "--dry" in sys.argv:
        log("DRY RUN — no API calls"); return
    # all three models concurrently, each with its own 80-worker pool
    summary = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(CONFIGS)) as ex:
        for jid, final in ex.map(lambda c: run_config(c, sample, ts), CONFIGS):
            summary[jid] = final["stats"]
    log("\n" + "=" * 70 + "\nALL DONE — remaining 600")
    for jid, s in summary.items():
        log(f"  {jid:20s} valid={s.get('n_valid')}/600 >=6agr={s.get('pass_agree_at_6')} "
            f"F1={s.get('f1_at_6')} r={s.get('pearson_r')} cost=${s.get('cost_usd')}")


if __name__ == "__main__":
    main()
