#!/usr/bin/env python3
"""DeepSeek-V4-Flash @ reasoning effort=XHIGH on the 200-problem seed=7 validation
sample, via direct OpenRouter HTTP. Tests whether xhigh beats v4-flash's default
(0.856 pass-agree). Reuses the tested gemini-runner machinery.

PRESERVES max_tokens=32768, timeout=600. Uses OpenRouter usage.cost. $8 cap.
"""
import json, time, threading, concurrent.futures, importlib.util
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("runner", "gemini_high_validation_20260524.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)

R.MODEL = "deepseek/deepseek-v4-flash"
R.REASONING = {"effort": "xhigh"}
COST_CAP = 8.0
MAX_WORKERS = 60  # v4-flash is cheap; parallelize hard


def main():
    sample = R.load_validation_sample()
    from collections import Counter
    print(f"v4-flash @ xhigh | {len(sample)} problems | "
          f"dist={dict(sorted(Counter(r['human_points'] for r in sample).items()))}", flush=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(f"v4flash_xhigh_validation_20260524_{ts}.json")
    partial = out_path.with_name(out_path.stem + "_partial.json")
    cost_state = {"spent": 0.0, "capped": False}; lock = threading.Lock()

    def worker(rec):
        with lock:
            if cost_state["capped"]:
                return {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                        "score": None, "error": "cost cap", "cost": 0.0}
        prompt = (R.PROMPT.replace("{problem}", rec["problem"])
                          .replace("{ground_truth}", rec["solution"])
                          .replace("{candidate}", rec["response"]))
        t0 = time.time()
        try:
            content, u = R.call(prompt)
            el = round(time.time() - t0, 1)
            score = R.parse_score(content)
            with lock:
                cost_state["spent"] += u["cost"]
                if cost_state["spent"] >= COST_CAP and not cost_state["capped"]:
                    cost_state["capped"] = True
                    print(f"\n[!! COST CAP ${cost_state['spent']:.2f} !!]\n", flush=True)
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
                    "score": None, "error": str(e), "cost": 0.0}

    results = []; t0 = time.time(); last = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(worker, r) for r in sample]):
            results.append(fut.result())
            if len(results) - last >= 20:
                last = len(results); s = R.stats_block(results)
                print(f"  --- {len(results)}/{len(sample)} valid={s.get('n_valid')} "
                      f">=6agr={s.get('pass_agree_at_6')} F1={s.get('f1_at_6')} r={s.get('pearson_r')} "
                      f"${s.get('cost_usd')} ---", flush=True)
                json.dump({"is_partial": True, "n_done": len(results), "stats": s, "results": results},
                          open(partial, "w"), ensure_ascii=False)

    el = round(time.time() - t0, 1); s = R.stats_block(results)
    n_trunc = sum(1 for r in results if r.get("finish_reason") == "length")
    final = {"experiment": "v4flash_xhigh_validation_20260524", "model": R.MODEL, "reasoning": R.REASONING,
             "max_tokens": R.MAX_TOKENS, "sample_seed": R.VAL_SEED, "n": len(sample),
             "n_done": len(results), "wall_clock_s": el, "cost_capped": cost_state["capped"],
             "n_truncated": n_trunc, "total_cost_usd": round(cost_state["spent"], 4), "stats": s,
             "date": datetime.now(timezone.utc).isoformat(), "results": results}
    json.dump(final, open(out_path, "w"), indent=2, ensure_ascii=False)
    print(f"\n{'='*70}\nFINAL v4-flash@xhigh: n_valid={s.get('n_valid')}/{len(sample)} truncated={n_trunc} "
          f"wall={el}s cost=${cost_state['spent']:.2f}")
    print(f"  pass_agree@6={s.get('pass_agree_at_6')} prec={s.get('precision_at_6')} "
          f"rec={s.get('recall_at_6')} F1={s.get('f1_at_6')} r={s.get('pearson_r')} "
          f"mean_reasoning_tok={s.get('mean_reasoning_tok')}")
    print(f"  confusion TP={s.get('tp')} FP={s.get('fp')} TN={s.get('tn')} FN={s.get('fn')}")
    print(f"  Saved: {out_path}")
    print(f"  (v4-flash@default ref: 0.856/0.759/0.669 | gpt-oss@xhigh ref: 0.875/0.806/0.676)")
    if partial.exists():
        partial.unlink()


if __name__ == "__main__":
    main()
