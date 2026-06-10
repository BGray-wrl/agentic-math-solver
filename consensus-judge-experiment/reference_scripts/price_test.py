#!/usr/bin/env python3
"""Tiny price probe via DIRECT OpenRouter HTTP (litellm mis-reports this key as
'monthly limit exceeded'; raw HTTP works). gemini-3.1-pro & claude-opus-4.7 at
reasoning effort=high, 4 length-spanning validation problems, 8 workers.
Uses OpenRouter's own reported usage.cost (exact billing).

PRESERVES max_tokens=32768 and timeout=600 (do not shorten — cuts off thought)."""
import concurrent.futures, csv, os, time, requests
from pathlib import Path
from dotenv import load_dotenv

csv.field_size_limit(10**7)
load_dotenv(override=True)
KEY = os.getenv("OPENROUTER_API_KEY")

MAX_TOKENS = 32768   # preserved
TIMEOUT = 600        # preserved
URL = "https://openrouter.ai/api/v1/chat/completions"

PROMPT = Path("../prompts/pipeline/judge_gt.md").read_text()
CHOSEN = ['GB-0529', 'GB-0318', 'GB-0089', 'GB-0912']  # 4k->51k input chars; GB-0912 is an Opus FP

CONFIGS = [
    {"judge_id": "gemini-3.1-pro",  "model": "google/gemini-3.1-pro-preview", "n_full": 200, "label": "full 200"},
    {"judge_id": "claude-opus-4.7", "model": "anthropic/claude-opus-4.7",     "n_full": 25,  "label": "FP subset 25"},
]

recs = {}
with open("gradingbench.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["Grading ID"] in CHOSEN:
            recs[r["Grading ID"]] = r
tasks = [(cfg, recs[g]) for cfg in CONFIGS for g in CHOSEN]

def run(task):
    cfg, r = task
    prompt = (PROMPT.replace("{problem}", r["Problem"])
                    .replace("{ground_truth}", r["Solution"])
                    .replace("{candidate}", r["Response"]))
    body = {"model": cfg["model"], "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS, "reasoning": {"effort": "high"}}
    t0 = time.time()
    try:
        resp = requests.post(URL, headers={"Authorization": f"Bearer {KEY}",
                             "Content-Type": "application/json"}, json=body, timeout=TIMEOUT)
        el = time.time() - t0
        d = resp.json()
        if resp.status_code != 200 or "error" in d:
            return {"judge": cfg["judge_id"], "gid": r["Grading ID"], "ok": False,
                    "err": f"HTTP {resp.status_code}: {str(d.get('error', d))[:160]}", "el": el}
        ch = d["choices"][0]; u = d.get("usage", {})
        cd = u.get("completion_tokens_details", {}) or {}
        return {"judge": cfg["judge_id"], "gid": r["Grading ID"], "ok": True,
                "pt": u.get("prompt_tokens", 0), "ct": u.get("completion_tokens", 0),
                "rt": cd.get("reasoning_tokens", 0), "cost": u.get("cost", 0.0),
                "el": el, "finish": ch.get("finish_reason")}
    except Exception as e:
        return {"judge": cfg["judge_id"], "gid": r["Grading ID"], "ok": False,
                "err": str(e)[:160], "el": time.time() - t0}

print(f"Direct-HTTP probe: {len(tasks)} calls (4 problems x 2 models) @ effort=high, "
      f"8 workers, max_tokens={MAX_TOKENS}, timeout={TIMEOUT}s\n", flush=True)
results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    for fut in concurrent.futures.as_completed([ex.submit(run, t) for t in tasks]):
        x = fut.result(); results.append(x)
        if x["ok"]:
            trunc = " <<TRUNCATED!>>" if x["finish"] == "length" else ""
            print(f"[done] {x['judge']:16s} {x['gid']}  in={x['pt']:6d} out={x['ct']:6d} "
                  f"reason={x['rt']:6d}  ${x['cost']:.4f}  {x['el']:.0f}s  finish={x['finish']}{trunc}", flush=True)
        else:
            print(f"[FAIL] {x['judge']:16s} {x['gid']}  {x['err']}", flush=True)

print("\n" + "=" * 70)
for cfg in CONFIGS:
    j = cfg["judge_id"]
    ok = [r for r in results if r["judge"] == j and r["ok"]]
    if not ok:
        print(f"\n{j}: ALL FAILED"); continue
    costs = sorted(r["cost"] for r in ok)
    mean = sum(costs) / len(ok)
    trunc = sum(1 for r in ok if r["finish"] == "length")
    print(f"\n{j}  ({len(ok)}/4 ok, {trunc} truncated)  [OpenRouter-reported cost]")
    print(f"  per-call: min=${costs[0]:.4f}  mean=${mean:.4f}  max=${costs[-1]:.4f}")
    print(f"  mean reasoning tok={sum(r['rt'] for r in ok)/len(ok):.0f}  mean out tok={sum(r['ct'] for r in ok)/len(ok):.0f}")
    print(f"  -> {cfg['label']}:  ${costs[0]*cfg['n_full']:.2f} (all short) .. "
          f"${mean*cfg['n_full']:.2f} (test mean) .. ${costs[-1]*cfg['n_full']:.2f} (all worst-case)")
print("\nNOTE: Opus FP cases skew long (median 11350 vs 10172 chars) -> use upper half of its range.")
print("Gemini's 200 include many short {0,7} cases -> true mean likely below the 4-call mean.")
