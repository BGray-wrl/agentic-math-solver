#!/usr/bin/env python3
"""Parse the killed consensus log into a structured JSON."""
import json, re, sys
from pathlib import Path

log = sys.argv[1]
out = sys.argv[2]
results = []
pat = re.compile(r"^\[(\d+)/\d+\]\s+(\S+)\s+(\S+)\s+(\S+)\s+seed=(\d+)\s+consensus=(\S+)\s+\((\d+)/3\)\s+\|\s+(.*)$")
with open(log) as f:
    for ln in f:
        m = pat.match(ln.strip())
        if not m: continue
        idx, pid, ptype, model, seed, consensus, n_agree, judges_str = m.groups()
        labels = {}
        for jpart in judges_str.split():
            if "=" in jpart:
                k,v = jpart.split("=",1)
                labels[k] = v
        results.append({
            "idx": int(idx), "problem_id": pid, "prompt_type": ptype,
            "model": model, "seed": int(seed),
            "consensus": consensus, "n_agree": int(n_agree),
            "judge_labels": labels,
        })
with open(out, "w") as f:
    json.dump({"results": results, "n": len(results), "source": log}, f, indent=2)
print(f"Wrote {len(results)} consensus results to {out}")
