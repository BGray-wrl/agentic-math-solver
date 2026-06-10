#!/usr/bin/env python3
"""Score experiment JSON files with frontier_verifier.py.

This is a lightweight triage helper for model runs.  It does not make any
network calls; it only re-verifies saved model text with the local verifier.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from frontier_verifier import verify_text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_files", nargs="+")
    ap.add_argument("--target-sing", type=int, default=8)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    rows = []
    for filename in args.json_files:
        path = Path(filename)
        data = json.loads(path.read_text())
        for trial_idx, trial in enumerate(data.get("results", [])):
            model = trial.get("model")
            seed = trial.get("seed")
            framework = trial.get("framework", "")
            for round_obj in trial.get("rounds", []):
                content = round_obj.get("content") or ""
                if not content:
                    continue
                res = verify_text(content, target_sing=args.target_sing)
                rows.append({
                    "file": path.name,
                    "trial": trial_idx,
                    "round": round_obj.get("round"),
                    "model": model,
                    "seed": seed,
                    "framework": framework,
                    "score": res.score,
                    "verdict": res.verdict,
                    "trust": res.trust,
                    "method": res.method,
                    "reason": res.reason,
                    "sing_count": res.details.get("sing_count"),
                })

    rank = {
        "PASS": 6,
        "ONE_SHORT": 5,
        "ESCALATE": 4,
        "PARTIAL": 3,
        "FAIL": 2,
        "UNSUPPORTED": 1,
    }
    rows.sort(key=lambda r: (r["score"], rank.get(r["verdict"], 0)), reverse=True)
    for row in rows[: args.top]:
        print(
            f"score={row['score']} verdict={row['verdict']} trust={row['trust']} "
            f"method={row['method']} model={row['model']} seed={row['seed']} "
            f"round={row['round']} framework={row['framework']}"
        )
        print(f"  file={row['file']} sing_count={row['sing_count']}")
        print(f"  reason={row['reason']}")


if __name__ == "__main__":
    main()
