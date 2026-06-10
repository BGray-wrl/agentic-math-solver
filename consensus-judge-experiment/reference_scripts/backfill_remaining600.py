#!/usr/bin/env python3
"""Backfill score=None incompletes in the remaining-600 result JSONs and merge.
Reuses the runner's call/parse/stats and config. Same params, parallel."""
import csv, json, glob, concurrent.futures, importlib.util
csv.field_size_limit(10**7)

spec = importlib.util.spec_from_file_location("runner", "judge_remaining600_20260524.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
CFG = {c["judge_id"]: c for c in R.CONFIGS}

all_rows, _ = R.load_remaining_sample()
byid = {r["grading_id"]: r for r in all_rows}

# newest JSON per judge
files = {}
for f in glob.glob("judge_remaining600_*_20260524_*.json"):
    if f.endswith("_partial.json"): continue
    jid = json.load(open(f))["judge_id"]
    files[jid] = max(files.get(jid, ""), f)  # latest by name (timestamp)

for jid, jf in files.items():
    d = json.load(open(jf))
    cfg = CFG[jid]
    missing = [r["grading_id"] for r in d["results"] if r["score"] is None]
    if not missing:
        print(f"{jid}: nothing to backfill"); continue
    print(f"{jid}: backfilling {len(missing)} -> {missing}")

    def redo(gid):
        rec = byid[gid]
        prompt = (R.PROMPT.replace("{problem}", rec["problem"])
                          .replace("{ground_truth}", rec["solution"])
                          .replace("{candidate}", rec["response"]))
        content, u = R.call(cfg, prompt)
        score = R.parse_score(content)
        print(f"  {jid} {gid}: score={score} finish={u['finish_reason']} "
              f"out={u['completion_tokens']} ${u['cost']:.4f}", flush=True)
        return gid, {"grading_id": gid, "problem_id": rec["problem_id"],
                     "human_points": rec["human_points"], "source": rec["source"],
                     "score": score, "verdict": content, "usage": u,
                     "cost": u["cost"], "finish_reason": u["finish_reason"]}

    fixed = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, len(missing))) as ex:
        for gid, newrec in ex.map(redo, missing):
            fixed[gid] = newrec

    d["results"] = [fixed.get(r["grading_id"], r) for r in d["results"]]
    d["total_cost_usd"] = round(sum(r.get("cost", 0) for r in d["results"]), 4)
    d["stats"] = R.stats_block(d["results"])
    d["backfilled"] = missing
    json.dump(d, open(jf, "w"), indent=2, ensure_ascii=False)
    s = d["stats"]; still = [r["grading_id"] for r in d["results"] if r["score"] is None]
    print(f"  -> {jid}: valid={s['n_valid']}/600 still_missing={still} cost=${d['total_cost_usd']} "
          f">=6agr={s['pass_agree_at_6']} F1={s['f1_at_6']} r={s['pearson_r']}")
