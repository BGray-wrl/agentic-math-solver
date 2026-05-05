#!/usr/bin/env python3
"""
Compute the headline numbers for results/dataset_20260505_REPORT.md from the JSONL
dataset and emit a populated REPORT_FILLED.md.

Reads:  results/dataset_20260505.jsonl
Writes: results/dataset_20260505_REPORT.md  (overwritten with TBDs filled in)

Run after every dataset rebuild.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
JSONL = ROOT / "results" / "dataset_20260505.jsonl"
OUT_REPORT = ROOT / "results" / "dataset_20260505_REPORT.md"


def short(m: str) -> str:
    return m.split("/")[-1] if m else "(no model)"


def jscore(row: dict, j: str) -> int | None:
    return row.get("judges", {}).get(j, {}).get("score")


def safe_mean(xs: list, prec: int = 2) -> str:
    xs = [x for x in xs if x is not None]
    if not xs: return "—"
    return f"{statistics.mean(xs):.{prec}f}"


def fmt(n: int | str | None) -> str:
    if n is None: return "—"
    return f"{n}"


def coverage_table(rows: list[dict]) -> str:
    out = []
    out.append("|              | rows | with v4pro | with gemini | with v4flash | branch-rows | branch-v4pro | branch-gemini | branch-v4flash |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    by_exp = defaultdict(list)
    for r in rows:
        by_exp[r["experiment"]].append(r)
    totals = {"rows":0,"v4p":0,"gem":0,"v4f":0,"br":0,"brv4p":0,"brgem":0,"brv4f":0}
    for exp in ("phase1","phase2","phase3","roleswap","scaling",
                "phase1_reasoning","scaling_reasoning","scaling_v4flash","gpt5_nano_pass3"):
        sub = by_exp.get(exp, [])
        v4p = sum(1 for r in sub if jscore(r,"v4pro") is not None)
        gem = sum(1 for r in sub if jscore(r,"gemini") is not None)
        v4f = sum(1 for r in sub if jscore(r,"v4flash") is not None)
        br_total = sum(len(r.get("branches",[])) for r in sub)
        brv4p = sum(1 for r in sub for b in r.get("branches",[]) if b["judges"]["v4pro"]["score"] is not None)
        brgem = sum(1 for r in sub for b in r.get("branches",[]) if b["judges"]["gemini"]["score"] is not None)
        brv4f = sum(1 for r in sub for b in r.get("branches",[]) if b["judges"]["v4flash"]["score"] is not None)
        out.append(f"| {exp:<13}|{len(sub):>5} | {v4p:>10} | {gem:>11} | {v4f:>12} | {br_total:>11} | {brv4p:>12} | {brgem:>13} | {brv4f:>14} |")
        totals["rows"] += len(sub); totals["v4p"] += v4p; totals["gem"] += gem; totals["v4f"] += v4f
        totals["br"] += br_total; totals["brv4p"] += brv4p; totals["brgem"] += brgem; totals["brv4f"] += brv4f
    out.append(f"| **total**     | {totals['rows']:>4} | {totals['v4p']:>10} | {totals['gem']:>11} | {totals['v4f']:>12} | {totals['br']:>11} | {totals['brv4p']:>12} | {totals['brgem']:>13} | {totals['brv4f']:>14} |")
    return "\n".join(out)


def triple_judge_agreement(rows: list[dict]) -> str:
    """Cross-judge agreement on cells where all three scored."""
    pairs = []
    for r in rows:
        v4p = jscore(r, "v4pro"); gem = jscore(r, "gemini"); v4f = jscore(r, "v4flash")
        if v4p is None or gem is None or v4f is None: continue
        pairs.append((v4p, gem, v4f))

    def agreement(idx_a: int, idx_b: int, label_a: str, label_b: str) -> tuple[str, str, str, str]:
        if not pairs: return ("—", "—", "—", "—")
        n = len(pairs)
        exact = sum(1 for p in pairs if p[idx_a] == p[idx_b]) / n
        within1 = sum(1 for p in pairs if abs(p[idx_a] - p[idx_b]) <= 1) / n
        flips = sum(1 for p in pairs if (p[idx_a]>=6) != (p[idx_b]>=6)) / n
        delta = statistics.mean(p[idx_b] - p[idx_a] for p in pairs)
        return (f"{exact:.0%}", f"{within1:.0%}", f"{flips:.0%}", f"{delta:+.2f}")

    a = agreement(0, 1, "v4pro", "gemini")
    b = agreement(0, 2, "v4pro", "v4flash")
    c = agreement(1, 2, "gemini", "v4flash")

    out = []
    out.append(f"Triple-judge cells (all 3 scored): n={len(pairs)}")
    out.append("")
    out.append("|                          | v4pro vs gemini | v4pro vs v4flash | gemini vs v4flash |")
    out.append("|---|---|---|---|")
    out.append(f"| Exact-match rate         | {a[0]} | {b[0]} | {c[0]} |")
    out.append(f"| Within-1 (\\|Δ\\|≤1) rate | {a[1]} | {b[1]} | {c[1]} |")
    out.append(f"| Pass-flip (≥6 vs <6) rate| {a[2]} | {b[2]} | {c[2]} |")
    out.append(f"| Mean Δ (col − row)       | {a[3]} | {b[3]} | {c[3]} |")
    return "\n".join(out)


def phase1_means(rows: list[dict]) -> str:
    sub = [r for r in rows if r["experiment"] == "phase1"]
    by_cell = defaultdict(lambda: {"v4pro":[], "gemini":[], "v4flash":[]})
    for r in sub:
        if r.get("error"): continue
        cell = (r["model"], r["condition"])
        for j in ("v4pro","gemini","v4flash"):
            s = jscore(r, j)
            if s is not None:
                by_cell[cell][j].append(s)
    rows_md = ["| Model × Mode | n | v4pro | gemini | v4flash |", "|---|---|---|---|---|"]
    for (m, c), j in sorted(by_cell.items()):
        rows_md.append(f"| {short(m):<22} × {c:<14} | {len(j['v4pro']):>3} | {safe_mean(j['v4pro'])} | {safe_mean(j['gemini'])} | {safe_mean(j['v4flash'])} |")
    return "\n".join(rows_md)


def phase2_phase3_table(rows: list[dict]) -> str:
    """Headline numbers for the Phase 1 best vs Phase 2/3 seed_full comparison."""
    p1_best_under_judge = defaultdict(lambda: defaultdict(list))   # judge -> model -> list of (pid, best_score)
    for r in rows:
        if r["experiment"] != "phase1" or r.get("error"): continue
        # Compute per-(model, problem) best-of-modes under each judge
        # by aggregating after this loop
    # Easier: aggregate per (model, pid, mode) then for each (model, pid) take the max
    p1_score = defaultdict(lambda: defaultdict(dict))   # judge -> (model, pid) -> {mode: score}
    for r in rows:
        if r["experiment"] != "phase1" or r.get("error"): continue
        for j in ("v4pro","gemini","v4flash"):
            s = jscore(r, j)
            if s is not None:
                p1_score[j][(r["model"], r["problem_id"])][r["condition"]] = s

    p2_p3 = defaultdict(lambda: defaultdict(list))   # judge -> ("phase2"|"phase3", model) -> [scores]
    for r in rows:
        if r["experiment"] not in ("phase2","phase3") or r.get("error"): continue
        for j in ("v4pro","gemini","v4flash"):
            s = jscore(r, j)
            if s is not None:
                p2_p3[j][(r["experiment"], r["model"])].append(s)

    # Phase 1 best-mode mean per (judge, model)
    out = ["| Model | Phase1-best (v4pro) | Phase1-best (gemini) | Phase1-best (v4flash) | P2 seed_full (v4pro) | (gemini) | (v4flash) | P3 (v4pro) | (gemini) | (v4flash) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    p1_models = sorted({m for j in p1_score.values() for (m, _) in j.keys()})
    for m in p1_models:
        cells = []
        for j in ("v4pro","gemini","v4flash"):
            best_scores = [max(modes.values()) for (mm, _), modes in p1_score[j].items() if mm == m and modes]
            cells.append(safe_mean(best_scores))
        for exp in ("phase2","phase3"):
            for j in ("v4pro","gemini","v4flash"):
                cells.append(safe_mean(p2_p3[j].get((exp, m), [])))
        out.append(f"| {short(m):<22} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def roleswap_means(rows: list[dict]) -> str:
    sub = [r for r in rows if r["experiment"] == "roleswap" and not r.get("error")]
    by_cond = defaultdict(lambda: {"v4pro":[], "gemini":[], "v4flash":[]})
    for r in sub:
        for j in ("v4pro","gemini","v4flash"):
            s = jscore(r, j)
            if s is not None:
                by_cond[r["condition"]][j].append(s)
    out = ["| Condition | n | gemini | v4pro (special-10 only) | v4flash |",
           "|---|---|---|---|---|"]
    for cond, j in sorted(by_cond.items()):
        out.append(f"| {cond:<22} | {len(j['gemini']):>3} | {safe_mean(j['gemini'])} | {safe_mean(j['v4pro'])} (n={len(j['v4pro'])}) | {safe_mean(j['v4flash'])} |")
    return "\n".join(out)


def scaling_pass_at_k(rows: list[dict]) -> str:
    """For each (model, k) compute per-judge mean of best-of-k."""
    sub = [r for r in rows if r["experiment"] == "scaling"]
    # Build per-(model, pid) lookup: branches by k
    by_cell = defaultdict(lambda: defaultdict(dict))   # (model, pid) -> k -> {judge: score}
    for r in sub:
        for b in r.get("branches", []):
            k = b.get("k")
            if k is None: continue
            cell = (r["model"], r["problem_id"])
            entry = by_cell[cell].setdefault(k, {})
            for j in ("v4pro","gemini","v4flash"):
                s = b["judges"][j]["score"]
                if s is not None: entry[j] = s

    out = ["| Model | k | gemini mean (best-of-k) | v4pro | v4flash |",
           "|---|---|---|---|---|"]
    models = sorted({m for (m, _) in by_cell.keys()})
    for m in models:
        for n in (1, 3, 5, 7):
            best_by_pid = defaultdict(lambda: {"v4pro":None, "gemini":None, "v4flash":None})
            for (mm, pid), kmap in by_cell.items():
                if mm != m: continue
                ks_avail = sorted(kmap.keys())[:n]   # take the first n branches by k
                for j in ("v4pro","gemini","v4flash"):
                    scores = [kmap[k][j] for k in ks_avail if j in kmap[k]]
                    if scores:
                        best_by_pid[pid][j] = max(scores)
            cells = []
            for j in ("gemini","v4pro","v4flash"):
                cells.append(safe_mean([d[j] for d in best_by_pid.values() if d[j] is not None]))
            out.append(f"| {short(m):<22} | {n} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def phase1_reasoning_means(rows: list[dict]) -> str:
    sub = [r for r in rows if r["experiment"] == "phase1_reasoning" and not r.get("error")]
    by_cell = defaultdict(list)
    for r in sub:
        s = jscore(r, "v4flash")
        if s is not None:
            by_cell[(r["model"], r["condition"])].append(s)
    out = ["| Model × Mode | n | v4flash mean | passes (≥6/7) |", "|---|---|---|---|"]
    for k in sorted(by_cell):
        scores = by_cell[k]
        passes = sum(1 for s in scores if s >= 6)
        out.append(f"| {short(k[0]):<22} × {k[1]:<14} | {len(scores)} | "
                   f"{statistics.mean(scores):.2f} | {passes}/{len(scores)} |")
    return "\n".join(out)


def gpt5_nano_table(rows: list[dict]) -> str:
    sub = [r for r in rows if r["experiment"] == "gpt5_nano_pass3"]
    # pass@1 and pass@3 best-of from branches
    pass1 = []; pass3 = []
    for r in sub:
        bs = [b["judges"]["v4flash"]["score"] for b in r.get("branches", [])
              if b["judges"]["v4flash"]["score"] is not None]
        if not bs: continue
        pass1.append(bs[0])
        pass3.append(max(bs[:3]) if len(bs) >= 1 else bs[0])
    if not pass1: return "_(no data)_"
    p1m = statistics.mean(pass1); p3m = statistics.mean(pass3)
    p1p = sum(1 for s in pass1 if s >= 6); p3p = sum(1 for s in pass3 if s >= 6)
    return (f"| N | n | v4flash mean | passes |\n|---|---|---|---|\n"
            f"| 1 | {len(pass1)} | {p1m:.2f} | {p1p}/{len(pass1)} |\n"
            f"| 3 | {len(pass3)} | {p3m:.2f} | {p3p}/{len(pass3)} |")


def scaling_reasoning_table(rows: list[dict]) -> str:
    sub = [r for r in rows if r["experiment"] == "scaling_reasoning"]
    by_cell = defaultdict(lambda: defaultdict(dict))
    for r in sub:
        for b in r.get("branches", []):
            k = b.get("k")
            if k is None: continue
            cell = (r["model"], r["problem_id"])
            entry = by_cell[cell].setdefault(k, {})
            s = b["judges"]["v4flash"]["score"]
            if s is not None: entry["v4flash"] = s
    out = ["| Model | k | v4flash mean (best-of-k) | passes |",
           "|---|---|---|---|"]
    models = sorted({m for (m, _) in by_cell.keys()})
    for m in models:
        for n in (1, 3, 5, 7, 9):
            best = []
            for (mm, _), kmap in by_cell.items():
                if mm != m: continue
                ks = sorted(kmap.keys())[:n]
                scores = [kmap[k]["v4flash"] for k in ks if "v4flash" in kmap[k]]
                if scores: best.append(max(scores))
            if best:
                pm = sum(1 for s in best if s >= 6)
                out.append(f"| {short(m):<22} | {n} | {statistics.mean(best):.2f} | {pm}/{len(best)} |")
    return "\n".join(out)


def scaling_v4flash_table(rows: list[dict]) -> str:
    sub = [r for r in rows if r["experiment"] == "scaling_v4flash"]
    by_pid = defaultdict(dict)
    for r in sub:
        for b in r.get("branches", []):
            k = b.get("k")
            s = b["judges"]["v4flash"]["score"]
            if k is None or s is None: continue
            by_pid[r["problem_id"]][k] = s
    out = ["| N | n | v4flash mean (best-of-N) | passes |", "|---|---|---|---|"]
    for n in (1, 3, 5, 7):
        best = []
        for pid, kmap in by_pid.items():
            ks = sorted(kmap.keys())[:n]
            if ks: best.append(max(kmap[k] for k in ks))
        if best:
            pm = sum(1 for s in best if s >= 6)
            out.append(f"| {n} | {len(best)} | {statistics.mean(best):.2f} | {pm}/{len(best)} |")
    return "\n".join(out)


def frontier_solves(rows: list[dict]) -> str:
    """For each special-10 problem, list which (experiment, model, condition) hit ≥6/7 under each judge."""
    SPECIAL = {"erdos-333","erdos-397","erdos-654","erdos-659","erdos-1051",
               "first-proof-4-official","first-proof-5-official","first-proof-6-official",
               "first-proof-10-official","ramsey-hypergraphs"}
    hits = defaultdict(lambda: defaultdict(list))   # pid -> judge -> [tags]
    for r in rows:
        if r["problem_id"] not in SPECIAL: continue
        if r.get("error"): continue
        tag = f"{r['experiment']}/{short(r['model']) if r['model'] else r['condition']}"
        # Also count per-branch hits
        for j in ("v4pro","gemini","v4flash"):
            if jscore(r, j) is not None and jscore(r, j) >= 6:
                hits[r["problem_id"]][j].append(tag + "(trial)")
            for b in r.get("branches", []):
                bs = b["judges"][j]["score"]
                if bs is not None and bs >= 6:
                    hits[r["problem_id"]][j].append(tag + "(branch)")

    out = ["| Problem | v4pro ≥6 | gemini ≥6 | v4flash ≥6 |", "|---|---|---|---|"]
    for pid in sorted(SPECIAL):
        def fmt_hits(tags):
            if not tags: return "—"
            ctr = Counter(tags)
            return ", ".join(f"{tag}×{n}" if n > 1 else tag for tag, n in ctr.most_common(4))
        out.append(f"| {pid:<28} | {fmt_hits(hits[pid].get('v4pro', []))} | {fmt_hits(hits[pid].get('gemini', []))} | {fmt_hits(hits[pid].get('v4flash', []))} |")
    return "\n".join(out)


# ============================================================================
# Main
# ============================================================================

REPORT_TEMPLATE = """# Agentic Math Solver — Dataset 2026-05-05 — Findings Report

Companion to `dataset_20260505.jsonl` and `dataset_20260505_README.md`.

> Generated from the live JSONL by `experiments/build_report_20260505.py`.

## 0.  Coverage

{coverage}

## 1.  Triple-judge agreement

Cross-judge agreement statistics on cells where all three judges scored.

{triple}

**Interpretation guide**: high pass-flip rate between two judges means they disagree on
who passes; mean Δ shows the systematic offset (e.g. v4pro − gemini < 0 means v4pro
scores lower).  Gradingbench correlations: v4pro r=0.79, v4flash r=0.76, gemini r=0.51.

## 2.  Phase 1 — 4-way mode comparison, three judges

{phase1}

## 3.  Phase 2 / Phase 3 vs Phase 1-best

{p2p3}

`agent_log.md` headlines:
- Under gemini: Phase 2 seed_full beats every Phase 1 mode for both cheap models (+0.6-0.9).
- Under v4-pro: Phase 2 seed_full collapses to the Phase 1 baseline (within ±0.1).

The v4flash column above is the third opinion.

## 4.  Roleswap — does cross-model diversity help?

{roleswap}

## 4b.  Phase 1 RE-RUN with reasoning ON (gpt-oss + gemma, v4-flash judge)

{phase1_reasoning}

## 4c.  GPT-5.4-nano pass@3 with reasoning xhigh (v4-flash judge)

{gpt5_nano}

`agent_log.md` line 2137 found role-swaps are within ±0.1 of the random_run baselines
under gemini.  v4flash provides an apples-to-apples strict-judge view across all 560
cells (not just special-10).

## 5.  Scaling — pass@k under each judge

{scaling}

## 5b.  Scaling RE-RUN with reasoning ON (v4-flash judge, k=0..8)

{scaling_reasoning}

## 5c.  Scaling on deepseek-v4-flash (70-problem, k=0..6, v4-flash judge)

{scaling_v4flash}

`agent_log.md` line 1649 (under gemini): N=1→7 yielded +2.0 / +1.5 (oss / gemma).
Under v4-pro: +0.5 / +0.5 — almost flat.

## 6.  Frontier solves — special-10 results

≥6/7 hits per judge.  "(trial)" = ≥6 on the trial's best_solution; "(branch)" = ≥6 on
any individual branch.

{frontier}

## 7.  Open questions

- Where v4-pro and gemini disagree on pass/no-pass, how does v4-flash break the tie?
- Does v4-flash agree with the v4-pro headline that Phase 2 seed_full was a gemini-only
  mirage?
- For frontier solves where only gemini calls ≥6, does v4-flash also call ≥6, or does
  it side with v4-pro?

## Regenerate

```bash
uv run experiments/regrade_all_v4flash_20260505.py --max-cost 100   # regrade
uv run experiments/export_dataset_20260505.py                       # export
uv run experiments/build_report_20260505.py                         # this script
```
"""


def main():
    if not JSONL.exists():
        raise SystemExit(f"{JSONL} not found — run export_dataset_20260505.py first")
    rows = [json.loads(l) for l in open(JSONL)]
    print(f"Loaded {len(rows)} rows from {JSONL}")

    body = REPORT_TEMPLATE.format(
        coverage = coverage_table(rows),
        triple   = triple_judge_agreement(rows),
        phase1   = phase1_means(rows),
        p2p3     = phase2_phase3_table(rows),
        roleswap = roleswap_means(rows),
        phase1_reasoning = phase1_reasoning_means(rows),
        gpt5_nano        = gpt5_nano_table(rows),
        scaling          = scaling_pass_at_k(rows),
        scaling_reasoning = scaling_reasoning_table(rows),
        scaling_v4flash   = scaling_v4flash_table(rows),
        frontier         = frontier_solves(rows),
    )

    OUT_REPORT.write_text(body)
    print(f"Wrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
