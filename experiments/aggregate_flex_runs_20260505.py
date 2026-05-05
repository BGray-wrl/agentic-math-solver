#!/usr/bin/env python3
"""
Aggregate the flex-budget experiment runs into a single comparison table.

Inputs (auto-discovered by glob):
  - cross_ideator_v4flash_20260505_*/  (per-condition trial JSONs)
  - strong_critic_v4flash_20260505_*/  (per-condition trial JSONs)
  - passN_v4flash_20260505_*/          (per-(pid,k) sample JSONs)

Output:
  - experiments/results/flex_summary_20260505.json
  - prints comparison tables to stdout
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"


def load_trials(run_dir: Path):
    out = {}
    td = run_dir / "trials"
    if not td.exists(): return out
    for cond_dir in td.iterdir():
        if not cond_dir.is_dir(): continue
        for f in cond_dir.glob("*.json"):
            try:
                with open(f, encoding="utf-8") as fh:
                    t = json.load(fh)
                out.setdefault(cond_dir.name, []).append(t)
            except Exception:
                pass
    return out


def load_passN(run_dir: Path):
    """Returns {pid: {k: score}}."""
    out = {}
    sd = run_dir / "samples"
    if not sd.exists(): return out
    for pdir in sd.iterdir():
        if not pdir.is_dir(): continue
        scores = {}
        for f in pdir.glob("k*.json"):
            try:
                with open(f, encoding="utf-8") as fh:
                    s = json.load(fh)
                if s.get("score") is not None:
                    scores[s["k"]] = s["score"]
            except Exception:
                pass
        out[pdir.name] = scores
    return out


def latest_run(prefix: str) -> Path | None:
    candidates = sorted(RESULTS.glob(f"{prefix}_2026*"))
    candidates = [c for c in candidates if c.is_dir()
                  and not c.name.endswith(("_mock", "_smoke"))]
    return candidates[-1] if candidates else None


def summarize_conditions(by_cond):
    rows = []
    for cond, ts in by_cond.items():
        valid = [t for t in ts if t.get("score") is not None and not t.get("error")]
        scores = [t["score"] for t in valid]
        if not scores:
            continue
        passes = sum(1 for t in valid if t.get("passed"))
        costs = [t.get("cost_usd", 0) or 0 for t in ts]
        rows.append({
            "condition": cond,
            "n":         len(valid),
            "mean":      round(float(np.mean(scores)), 3),
            "std":       round(float(np.std(scores)), 3),
            "passes":    passes,
            "mean_cost": round(float(np.mean(costs)), 4) if costs else 0,
            "total_cost": round(float(sum(costs)), 3),
        })
    return rows


def passN_curve(scores_by_problem):
    """Compute pass@k mean and pass-count for k = 1, 2, 3, 5, 7, 8."""
    out = []
    for k in [1, 2, 3, 5, 7, 8]:
        means = []; passes = 0
        for pid, scores in scores_by_problem.items():
            avail = [scores[i] for i in range(k) if i in scores]
            if not avail:
                continue
            m = max(avail)
            means.append(m)
            if m >= 6: passes += 1
        if means:
            out.append({
                "k":      k,
                "n":      len(means),
                "mean":   round(float(np.mean(means)), 3),
                "passes": passes,
            })
    return out


def main():
    summary = {}

    print("\n========== EXPERIMENT 1: Cross-ideator =========\n")
    rd1 = latest_run("cross_ideator_v4flash_20260505")
    if rd1:
        print(f"Run: {rd1.name}")
        by_cond = load_trials(rd1)
        rows = summarize_conditions(by_cond)
        summary["cross_ideator"] = {"run_dir": str(rd1), "rows": rows}
        for r in rows:
            print(f"  {r['condition']:<22}  n={r['n']:>3}  mean={r['mean']:>5.2f}  "
                  f"std={r['std']:>5.2f}  pass={r['passes']:>2}  "
                  f"avg=${r['mean_cost']:.4f}  tot=${r['total_cost']:.3f}")

        # Per-problem head-to-head
        if len(rows) >= 2:
            print(f"\n  Per-problem deltas (first cond vs second):")
            cond_a, cond_b = list(by_cond.keys())[:2]
            ts_a = {t["problem_id"]: t for t in by_cond[cond_a]}
            ts_b = {t["problem_id"]: t for t in by_cond[cond_b]}
            both = sorted(set(ts_a) & set(ts_b))
            wins_a = wins_b = ties = 0
            for pid in both:
                sa, sb = ts_a[pid].get("score"), ts_b[pid].get("score")
                if sa is None or sb is None: continue
                if sb > sa: wins_b += 1
                elif sa > sb: wins_a += 1
                else: ties += 1
            print(f"    {cond_a}={wins_a} | tie={ties} | {cond_b}={wins_b}  "
                   f"(of {wins_a+wins_b+ties})")
    else:
        print("  no run yet")

    print("\n========== EXPERIMENT 2: Strong critic =========\n")
    rd2 = latest_run("strong_critic_v4flash_20260505")
    if rd2:
        print(f"Run: {rd2.name}")
        by_cond = load_trials(rd2)
        rows = summarize_conditions(by_cond)
        summary["strong_critic"] = {"run_dir": str(rd2), "rows": rows}
        for r in rows:
            print(f"  {r['condition']:<22}  n={r['n']:>3}  mean={r['mean']:>5.2f}  "
                  f"std={r['std']:>5.2f}  pass={r['passes']:>2}  "
                  f"avg=${r['mean_cost']:.4f}  tot=${r['total_cost']:.3f}")
    else:
        print("  no run yet")

    print("\n========== EXPERIMENT 3: pass@N curve =========\n")
    rd3 = latest_run("passN_v4flash_20260505")
    if rd3:
        print(f"Run: {rd3.name}")
        sc = load_passN(rd3)
        curve = passN_curve(sc)
        summary["passN"] = {"run_dir": str(rd3), "curve": curve, "n_problems": len(sc)}
        for r in curve:
            print(f"  k={r['k']:<2}  n={r['n']:>3}  mean@k={r['mean']:>5.2f}  passes={r['passes']:>2}/{r['n']}")
    else:
        print("  no run yet")

    out = RESULTS / "flex_summary_20260505.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSaved aggregated summary to {out}")


if __name__ == "__main__":
    main()
