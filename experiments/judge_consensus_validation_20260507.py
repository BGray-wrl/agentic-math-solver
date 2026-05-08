#!/usr/bin/env python3
"""Consensus validation experiment: 5 judge configs on a NEW 200-problem sample
(seed=7, zero overlap with prior seed=42 sample). Runs configs sequentially,
parallelizes calls within each config.
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, itertools, json, math, os, random, re
import statistics as st, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import litellm  # noqa: E402

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts" / "pipeline"
RESULTS_DIR = Path(__file__).parent / "results"
DATA_CSV = ROOT / "benchmarks" / "IMO-bench" / "gradingbench.csv"

PRIOR_SEED = 42
PRIOR_N = 200
VAL_SEED = 7
VAL_N = 200

CONFIGS = [
    {
        "judge_id": "deepseek-v4-flash",
        "model": "openrouter/deepseek/deepseek-v4-flash",
        "extra_body": None,
        "reasoning_config": "default",
        "price_input_per_M": 0.28,
        "price_output_per_M": 0.28,
        "price_mode": "flat",
        "cost_cap": 3.0,
        "max_workers": 80,
    },
    {
        "judge_id": "gpt-oss-120b",
        "model": "openrouter/openai/gpt-oss-120b",
        "extra_body": {"reasoning": {"effort": "xhigh"}},
        "reasoning_config": "xhigh",
        "price_input_per_M": 0.15,
        "price_output_per_M": 0.15,
        "price_mode": "flat",
        "cost_cap": 3.0,
        "max_workers": 80,
    },
    {
        "judge_id": "gemma-4-31b-it",
        "model": "openrouter/google/gemma-4-31b-it",
        "extra_body": {"reasoning": {"effort": "high"}},
        "reasoning_config": "high",
        "price_input_per_M": 0.38,
        "price_output_per_M": 0.38,
        "price_mode": "flat",
        "cost_cap": 3.0,
        "max_workers": 80,
    },
    {
        "judge_id": "gemini-3.1-pro",
        "model": "openrouter/google/gemini-3.1-pro-preview",
        "extra_body": {"reasoning": {"enabled": True}},
        "reasoning_config": "default",
        "price_input_per_M": 1.25,
        "price_output_per_M": 10.00,
        "price_mode": "split",
        "cost_cap": 15.0,
        "max_workers": 40,
    },
    {
        "judge_id": "claude-opus-4.7",
        "model": "openrouter/anthropic/claude-opus-4.7",
        "extra_body": {"reasoning": {"enabled": True}},
        "reasoning_config": "default",
        "price_input_per_M": 5.00,
        "price_output_per_M": 25.00,
        "price_mode": "split",
        "cost_cap": 45.0,
        "max_workers": 40,
    },
]

MAX_TOKENS = 32768
TIMEOUT = 600
ROLL_EVERY_N = 10
ROLL_EVERY_S = 30.0

load_dotenv()

def _filter_live_keys(keys):
    import requests
    live = []
    for i, k in enumerate(keys):
        try:
            r = requests.get("https://openrouter.ai/api/v1/key",
                             headers={"Authorization": f"Bearer {k}"}, timeout=8)
            if not r.ok:
                live.append(k); continue
            d = r.json().get("data", {}) or {}
            limit = d.get("limit"); usage = d.get("usage", 0) or 0
            if limit is not None and usage >= limit:
                print(f"[startup] key#{i}: EXHAUSTED ({usage:.2f}/{limit}) — dropped")
            else:
                rem = (limit - usage) if limit else "unlimited"
                print(f"[startup] key#{i}: live (usage={usage:.2f}/{limit}, remain={rem})")
                live.append(k)
        except Exception as e:
            print(f"[startup] key#{i}: probe failed ({e}), including"); live.append(k)
    return live

KEYS = _filter_live_keys([k for k in [
    os.getenv("OPENROUTER_API_KEY"),
    os.getenv("OPENROUTER_API_KEY_X"),
    os.getenv("OPENROUTER_API_KEY_X2"),
    os.getenv("OPENROUTER_API_KEY_draft_exps"),
    os.getenv("OPENROUTER_API_KEY_seedgen"),
] if k])
if not KEYS:
    raise SystemExit("No live keys")
_iter = itertools.cycle(KEYS); _lock = threading.Lock()
def next_key():
    with _lock: return next(_iter)


def _ts(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def _now(): return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
def _mmss(s): s = max(0, int(s)); return f"{s//60:02d}:{s%60:02d}"


def call_judge(prompt, model, extra_body, retries=2, backoff=4.0):
    last = None
    for attempt in range(retries + 1):
        try:
            kwargs = dict(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                api_key=next_key(),
                timeout=TIMEOUT,
            )
            if extra_body:
                kwargs["extra_body"] = extra_body
            resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message
            content = msg.content or getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
            if content is None:
                raise ValueError("None content")
            usage = resp.usage
            cd = getattr(usage, "completion_tokens_details", None)
            return content, {
                "prompt_tokens":     int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens":      int(getattr(usage, "total_tokens", 0) or 0),
                "reasoning_tokens":  int(getattr(cd, "reasoning_tokens", 0) or 0) if cd else 0,
            }
        except Exception as e:
            last = e
            err = str(e)
            if "402" in err or "credit" in err.lower() or "insufficient" in err.lower() or "Key limit" in err:
                raise
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last


def parse_score(text):
    if not text:
        return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", text, re.I)
    if m:
        v = int(m.group(1)); return v if 0 <= v <= 7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", text, re.I)
    return int(m.group(1)) if m else None


def bucket(s): return 0 if s <= 0 else (1 if s <= 3 else (6 if s <= 6 else 7))

def pearson(xs, ys):
    if len(xs) < 2: return 0
    mx, my = st.mean(xs), st.mean(ys)
    n = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return n / (dx * dy) if dx > 0 and dy > 0 else 0

def pct(v, p):
    if not v: return 0
    s = sorted(v); k = (len(s) - 1) * p / 100
    f, c = math.floor(k), math.ceil(k)
    return s[int(k)] if f == c else s[f] * (c - k) + s[c] * (k - f)


def stats_block(results):
    valid = [r for r in results if r.get("score") is not None]
    n = len(results); nv = len(valid)
    if nv == 0:
        return {"n": n, "n_valid": 0}
    h = [r["human_points"] for r in valid]; j = [r["score"] for r in valid]
    abs_d = [abs(a - b) for a, b in zip(j, h)]
    deltas = [a - b for a, b in zip(j, h)]
    h_pass = [x >= 6 for x in h]; j_pass = [x >= 6 for x in j]
    agr6 = sum(1 for a, b in zip(h_pass, j_pass) if a == b) / nv
    raw = sum(1 for a, b in zip(h, j) if a == b) / nv
    bk = sum(1 for a, b in zip(h, j) if bucket(a) == b) / nv
    r = pearson([float(x) for x in j], [float(x) for x in h])
    lat = [rr["elapsed"] for rr in results if rr.get("elapsed")]
    rts = [rr["usage"].get("reasoning_tokens", 0) for rr in valid if rr.get("usage")]
    cost = sum(rr.get("cost", 0) for rr in results)
    tp = sum(1 for a, b in zip(h_pass, j_pass) if a and b)
    fp = sum(1 for a, b in zip(h_pass, j_pass) if not a and b)
    tn = sum(1 for a, b in zip(h_pass, j_pass) if not a and not b)
    fn = sum(1 for a, b in zip(h_pass, j_pass) if a and not b)
    rec6 = tp / (tp + fn) if (tp + fn) > 0 else 0
    prec6 = tp / (tp + fp) if (tp + fp) > 0 else 0
    spec6 = tn / (tn + fp) if (tn + fp) > 0 else 0
    f1_6 = 2 * prec6 * rec6 / (prec6 + rec6) if (prec6 + rec6) > 0 else 0
    return {
        "n": n, "n_valid": nv,
        "mean_J": round(st.mean(j), 3), "mean_H": round(st.mean(h), 3),
        "mean_abs_dev": round(st.mean(abs_d), 3), "mean_delta": round(st.mean(deltas), 3),
        "pearson_r": round(r, 4), "pass_agree_at_6": round(agr6, 4),
        "recall_at_6": round(rec6, 4), "precision_at_6": round(prec6, 4),
        "specificity_at_6": round(spec6, 4), "f1_at_6": round(f1_6, 4),
        "tp_at_6": tp, "fp_at_6": fp, "tn_at_6": tn, "fn_at_6": fn,
        "exact_raw": round(raw, 4), "exact_bucketed": round(bk, 4),
        "cost_usd": round(cost, 4),
        "latency_p50": round(pct(lat, 50), 1), "latency_p95": round(pct(lat, 95), 1),
        "mean_rt": int(st.mean(rts)) if rts else 0,
    }


def print_rolling(results, n_total, t0, cost_state, cap):
    el = time.time() - t0; nd = len(results)
    eta = (el / max(nd, 1)) * (n_total - nd) if nd else 0
    s = stats_block(results)
    print(f"\n=== ROLLING [elapsed {_mmss(el)}, {nd}/{n_total} done, ETA ~{_mmss(eta)}, "
          f"$spent={cost_state['spent']:.2f}/${cap}] ===", flush=True)
    if s.get("n_valid", 0):
        print(f"  n_v={s['n_valid']} mJ={s['mean_J']:.2f} mH={s['mean_H']:.2f} "
              f"|D|={s['mean_abs_dev']:.2f} r={s['pearson_r']:.3f} "
              f">=6agr={s['pass_agree_at_6']*100:.1f}% prec={s['precision_at_6']*100:.1f}% "
              f"rec={s['recall_at_6']*100:.1f}% F1={s['f1_at_6']*100:.1f}% "
              f"${s['cost_usd']:.2f} p50={s['latency_p50']:.1f}s", flush=True)


def load_validation_sample():
    rows = []
    with open(DATA_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "grading_id": r["Grading ID"], "problem_id": r["Problem ID"],
                "problem": r["Problem"], "solution": r["Solution"],
                "response": r["Response"], "human_points": int(r["Points"]),
                "source": r["Problem Source"],
            })
    old_sample = random.Random(PRIOR_SEED).sample(rows, PRIOR_N)
    old_ids = set(r["grading_id"] for r in old_sample)
    remaining = [r for r in rows if r["grading_id"] not in old_ids]
    new_sample = random.Random(VAL_SEED).sample(remaining, VAL_N)
    overlap = old_ids & set(r["grading_id"] for r in new_sample)
    assert len(overlap) == 0, f"OVERLAP DETECTED: {overlap}"
    return new_sample


def run_config(cfg, sample, judge_template, skip_list):
    jid = cfg["judge_id"]
    rc = cfg["reasoning_config"]
    tag = f"{jid}_{rc}"
    if tag in skip_list:
        print(f"\n{'='*80}\nSKIPPING {tag} (in --skip list)\n{'='*80}\n", flush=True)
        return None

    cap = cfg["cost_cap"]
    model = cfg["model"]
    extra_body = cfg["extra_body"]
    max_w = cfg["max_workers"]

    print(f"\n{'='*80}\nCONFIG: {jid} @ {rc}  model={model}  cap=${cap}  workers={max_w}\n{'='*80}\n", flush=True)

    out_path = RESULTS_DIR / f"judge_validation_{jid}_{rc}_20260507_{_now()}.json"
    out_partial = out_path.with_name(out_path.stem + "_partial.json")
    cost_state = {"spent": 0.0, "capped": False}
    cost_lock = threading.Lock()

    def compute_cost(usage):
        if cfg["price_mode"] == "flat":
            return round(cfg["price_input_per_M"] * usage["total_tokens"] / 1_000_000, 6)
        else:
            return round((cfg["price_input_per_M"] * usage["prompt_tokens"] +
                         cfg["price_output_per_M"] * usage["completion_tokens"]) / 1_000_000, 6)

    def worker(rec):
        with cost_lock:
            if cost_state["spent"] >= cap or cost_state["capped"]:
                return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                        "score": None, "error": "cost cap", "cost": 0.0, "elapsed": 0.0}
        prompt = (judge_template
                  .replace("{problem}", rec["problem"])
                  .replace("{ground_truth}", rec["solution"])
                  .replace("{candidate}", rec["response"]))
        t0 = time.time()
        try:
            content, usage = call_judge(prompt, model, extra_body)
            el = round(time.time() - t0, 2)
            score = parse_score(content)
            cost = compute_cost(usage)
            with cost_lock:
                cost_state["spent"] += cost
                if cost_state["spent"] >= cap and not cost_state["capped"]:
                    cost_state["capped"] = True
                    print(f"\n[!! COST CAP HIT: ${cost_state['spent']:.2f} >= ${cap} !!]\n", flush=True)
            d = (score - rec["human_points"]) if score is not None else None
            ds = f"D={d:+d}" if d is not None else "D=NA"
            print(f"[{_ts()}] {rec['grading_id']:<8} pts={rec['human_points']} score={score} {ds}  "
                  f"${cost:.4f}  {el}s  rt={usage.get('reasoning_tokens', 0)}  "
                  f"cum=${cost_state['spent']:.2f}", flush=True)
            return {"grading_id": rec["grading_id"], "problem_id": rec["problem_id"],
                    "human_points": rec["human_points"], "source": rec["source"],
                    "score": score, "verdict": content, "usage": usage,
                    "cost": cost, "elapsed": el}
        except Exception as e:
            el = round(time.time() - t0, 2)
            print(f"[{_ts()}] FAIL {rec['grading_id']}: {str(e)[:120]}", flush=True)
            return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                    "score": None, "error": str(e), "cost": 0.0, "elapsed": el}

    results = []; t0 = time.time(); last_n, last_t = 0, t0
    print(f"Starting {tag} at {_ts()} UTC ...\n", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_w) as ex:
        futs = [ex.submit(worker, r) for r in sample]
        for fut in concurrent.futures.as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"outer fail: {e}", flush=True)
            now = time.time()
            if (len(results) - last_n) >= ROLL_EVERY_N or (now - last_t) >= ROLL_EVERY_S:
                print_rolling(results, len(sample), t0, cost_state, cap)
                with open(out_partial.with_suffix(".tmp"), "w") as f:
                    json.dump({"is_partial": True, "n_done": len(results),
                               "stats": stats_block(results), "results": results},
                              f, ensure_ascii=False)
                os.replace(out_partial.with_suffix(".tmp"), out_partial)
                last_n, last_t = len(results), now

    el = round(time.time() - t0, 1)
    s = stats_block(results)
    print(f"\n{'='*80}\nFINAL {tag}  n={len(sample)} done={len(results)} valid={s.get('n_valid',0)} "
          f"wall={_mmss(el)} cost=${cost_state['spent']:.2f}\n{'='*80}\n", flush=True)
    print_rolling(results, len(sample), t0, cost_state, cap)

    final = {
        "experiment": f"judge_validation_{tag}_20260507",
        "is_partial": False,
        "date": datetime.now(timezone.utc).isoformat(),
        "judge": model,
        "judge_id": jid,
        "reasoning_config": rc,
        "extra_body": extra_body,
        "price_input_per_M": cfg["price_input_per_M"],
        "price_output_per_M": cfg["price_output_per_M"],
        "price_mode": cfg["price_mode"],
        "cost_capped": cost_state["capped"],
        "cost_cap": cap,
        "sample_seed": VAL_SEED,
        "prior_seed_excluded": PRIOR_SEED,
        "n_sampled": len(sample),
        "n_done": len(results),
        "wall_clock_s": el,
        "total_cost_usd": round(cost_state["spent"], 4),
        "stats": s,
        "results": results,
    }
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}", flush=True)
    if out_partial.exists():
        try: out_partial.unlink()
        except OSError: pass
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", type=str, default="",
                    help="Comma-separated config tags to skip (e.g. deepseek-v4-flash_default,gemini-3.1-pro_default)")
    ap.add_argument("--only", type=str, default="",
                    help="Run only this config tag")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    skip_list = set(args.skip.split(",")) if args.skip else set()

    judge_template = (PROMPTS_DIR / "judge_gt.md").read_text()
    sample = load_validation_sample()
    print(f"Validation sample: {len(sample)} problems (seed={VAL_SEED}, excluding prior seed={PRIOR_SEED})")
    from collections import Counter
    dist = Counter(r["human_points"] for r in sample)
    print(f"Score distribution: {dict(sorted(dist.items()))}\n")

    if args.mock:
        print("MOCK MODE — no API calls")
        return

    saved = []
    for cfg in CONFIGS:
        tag = f"{cfg['judge_id']}_{cfg['reasoning_config']}"
        if args.only and tag != args.only:
            continue
        path = run_config(cfg, sample, judge_template, skip_list)
        if path:
            saved.append(str(path))

    print(f"\n{'='*80}\nALL DONE. Saved {len(saved)} result files:")
    for p in saved:
        print(f"  {p}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
