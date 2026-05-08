#!/usr/bin/env python3
"""
Comprehensive summary of FrontierMath open-problems Phase 1 + verification.
Shows: judge label distribution, per-problem positive rate, candidates that
passed local verification, and pointers to specific solutions worth manual review.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from collections import Counter, defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", help="phase 1 jsonl log")
    args = ap.parse_args()

    rows = []
    with open(args.log) as f:
        for ln in f:
            r = json.loads(ln)
            if r.get("kind") == "trial":
                rows.append(r)

    print(f"=== Phase 1 summary: {args.log} ===")
    print(f"Total trials: {len(rows)}")
    print()

    # Label distribution
    label_counts = Counter(r.get("label") for r in rows)
    print("Label distribution:")
    for k in ("correct","almost","partial","incorrect", None):
        print(f"  {str(k):<12} {label_counts.get(k,0)}")
    print()

    # Per-model x label
    by_model = defaultdict(Counter)
    for r in rows:
        m = r.get("model","?").split("/")[-1]
        by_model[m][r.get("label")] += 1
    print("Per-model:")
    for m, c in sorted(by_model.items()):
        total = sum(c.values())
        pos = c.get("correct",0) + c.get("almost",0) + c.get("partial",0)
        print(f"  {m:<22} pos={pos}/{total}  | correct={c.get('correct',0)}  almost={c.get('almost',0)}  partial={c.get('partial',0)}  incorrect={c.get('incorrect',0)}")
    print()

    # Per-problem positive rate (any seed positive?)
    by_prob = defaultdict(list)
    for r in rows:
        by_prob[(r["problem_id"], r["prompt_type"])].append(r.get("label"))
    print("Per-problem (any positive across all seeds×models):")
    rank = {"incorrect":0, "partial":1, "almost":2, "correct":3, None:-1}
    for k in sorted(by_prob.keys()):
        labels = by_prob[k]
        max_lab = max(labels, key=lambda x: rank.get(x, -1))
        pos_count = sum(1 for l in labels if rank.get(l, -1) >= 1)
        marker = "✓" if max_lab == "correct" else ("~" if max_lab in ("almost","partial") else "✗")
        print(f"  {marker} {k[0]:<26} {k[1]:<14}  best={max_lab}  pos_seeds={pos_count}/{len(labels)}")
    print()

    # Top positives sorted by score
    positives = sorted(
        [r for r in rows if rank.get(r.get("label"), -1) >= 1],
        key=lambda r: -rank.get(r.get("label"), -1),
    )
    print(f"Total positive trials: {len(positives)}")
    if positives:
        print("\nFirst 30 positives:")
        for r in positives[:30]:
            print(f"  {r['label']:<8} {r['problem_id']:<26} {r['prompt_type']:<14} {r['model'].split('/')[-1]:<22} seed={r['seed']}")


if __name__ == "__main__":
    main()
