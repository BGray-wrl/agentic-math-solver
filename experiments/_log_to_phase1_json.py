#!/usr/bin/env python3
"""Convert a Phase 1 JSONL log to a results JSON suitable for consensus judging."""
import json, sys
from pathlib import Path

if len(sys.argv) != 3:
    print("usage: _log_to_phase1_json.py <jsonl> <out.json>"); sys.exit(1)

results = []
with open(sys.argv[1]) as f:
    for line in f:
        r = json.loads(line)
        if r.get("kind") != "trial": continue
        results.append({
            "problem_id": r["problem_id"],
            "prompt_type": r["prompt_type"],
            "model": r["model"],
            "seed": r["seed"],
            "label": r.get("label"),
            "score": r.get("score"),
            "gen_text": r.get("gen_text"),
            "verdict": r.get("verdict"),
        })
out = {"results": results}
with open(sys.argv[2], "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"Wrote {len(results)} results to {sys.argv[2]}")
