"""Aggregate all klt_iter_exp*.json results into a single report."""
import json, glob, sys
from pathlib import Path

ROOT = Path("/Users/benjamingrayzel/sandbox/agentic-math-solver")
RES = ROOT / "experiments" / "results"
OUT = ROOT / "klt-del-pezzo-iteration" / "RESULTS_AGGREGATE.md"

def main():
    files = sorted(glob.glob(str(RES / "klt_iter_exp*.json")))
    print(f"Found {len(files)} result files.")
    rows = []
    pass_candidates = []
    for f in files:
        with open(f) as fh: d = json.load(fh)
        exp = d.get("experiment", Path(f).stem)
        for r in d.get("results", []):
            row = {
                "experiment": exp,
                "model": r.get("model"),
                "seed": r.get("seed"),
                "problem_type": r.get("problem_type", "full"),
                "status": r.get("status"),
                "best_score": r.get("best_score", 0),
                "n_rounds": len(r.get("rounds", [])),
            }
            # Best round details
            best_round = None
            for rd in r.get("rounds", []):
                v = rd.get("verification", {})
                if v.get("score", 0) == row["best_score"]:
                    best_round = rd
            if best_round:
                v = best_round.get("verification", {})
                row["weights"] = v.get("weights")
                row["eqns"] = v.get("eqns")
                row["sing_count"] = v.get("sing_count")
                row["reason"] = v.get("reason", "")[:200]
                if row["status"] == "PASS":
                    pass_candidates.append({"exp": exp, **row})
            rows.append(row)

    rows.sort(key=lambda r: (-r["best_score"], r["model"] or "", r["seed"] or 0))

    out_lines = ["# klt-del-pezzo iteration: aggregate results\n"]
    out_lines.append(f"Sources: {len(files)} experiment files, {len(rows)} trials total.\n")
    out_lines.append(f"PASSING candidates: {len(pass_candidates)}\n")
    out_lines.append("\n## PASS candidates (score = 7, verified klt del Pezzo)\n")
    if pass_candidates:
        for p in pass_candidates:
            out_lines.append(f"\n### {p['exp']} | {p['model']} | seed={p['seed']} | {p['problem_type']}\n")
            out_lines.append(f"Weights: `{p.get('weights')}`\n")
            out_lines.append(f"Equations: `{p.get('eqns')}`\n")
            out_lines.append(f"Singular points: {p.get('sing_count')}\n")
    else:
        out_lines.append("\n*(no PASS candidates yet)*\n")

    out_lines.append("\n## Top 20 by partial signal\n")
    out_lines.append("| Experiment | Model | Seed | Type | Score | Sing | Weights | Equations |\n")
    out_lines.append("|---|---|---|---|---:|---:|---|---|\n")
    for r in rows[:20]:
        eqns_str = ", ".join(r.get("eqns") or []) if r.get("eqns") else "-"
        out_lines.append(f"| {r['experiment']} | {r['model']} | {r['seed']} | {r['problem_type']} | "
                         f"{r['best_score']} | {r.get('sing_count', '-')} | {r.get('weights') or '-'} | `{eqns_str[:80]}` |\n")

    out_lines.append("\n## Per-cell best score\n")
    from collections import defaultdict
    cells = defaultdict(lambda: 0)
    for r in rows:
        k = (r["experiment"], r["model"], r["problem_type"])
        cells[k] = max(cells[k], r["best_score"])
    for (exp, m, pt), s in sorted(cells.items()):
        out_lines.append(f"- {exp} / {m} / {pt}: best_score = {s}\n")

    OUT.write_text("".join(out_lines))
    print(f"Wrote: {OUT}")
    if pass_candidates:
        print(f"\n*** {len(pass_candidates)} PASSING candidates! ***")
        for p in pass_candidates:
            print(f"  {p['model']} seed={p['seed']} {p['problem_type']}: weights={p.get('weights')}")

if __name__ == "__main__":
    main()
