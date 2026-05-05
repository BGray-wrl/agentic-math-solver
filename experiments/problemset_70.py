"""
Loader for the 70-problem set used by the seed-ideas 4-way comparison.

70 problems = 60 IMO-proofbench + 10 special:
  - 60 from benchmarks/IMO-bench/proofbench.csv (PB-Basic-001..030, PB-Advanced-001..030)
  - erdos-659              from benchmarks/combined-benchmarks.csv (non-aletheia, 11.9K-char solution)
  - erdos-397, 654, 1051   from benchmarks/erdos-aletheia/erdos_problem_solution_pairs_reduced.csv
  - erdos-333              from benchmarks/erdos-aletheia/erdos_problem_solution_pairs.csv
                           (loaded as erdos-333-aletheia, renamed to erdos-333 — only available form)
  - first-proof-4,5,6,10   from benchmarks/first-proof/official/first-proof-official.csv
  - ramsey-hypergraphs     from benchmarks/frontiermath-open-problems/ramsey-hypergraphs-solution.csv

Usage:
    from problemset_70 import load_70_problems, SPECIAL_10
    problems = load_70_problems()         # dict: pid -> {text, ground_truth, source, category, level}
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).parent.parent

PROOFBENCH_CSV     = ROOT / "benchmarks" / "IMO-bench" / "proofbench.csv"
COMBINED_CSV       = ROOT / "benchmarks" / "combined-benchmarks.csv"
ERDOS_REDUCED_CSV  = ROOT / "benchmarks" / "erdos-aletheia" / "erdos_problem_solution_pairs_reduced.csv"
ERDOS_FULL_CSV     = ROOT / "benchmarks" / "erdos-aletheia" / "erdos_problem_solution_pairs.csv"
FIRST_PROOF_CSV    = ROOT / "benchmarks" / "first-proof" / "official" / "first-proof-official.csv"
RAMSEY_CSV         = ROOT / "benchmarks" / "frontiermath-open-problems" / "ramsey-hypergraphs-solution.csv"

SPECIAL_10 = {
    "erdos-333", "erdos-397", "erdos-654", "erdos-659", "erdos-1051",
    "first-proof-4-official", "first-proof-5-official",
    "first-proof-6-official", "first-proof-10-official",
    "ramsey-hypergraphs",
}


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _normalize(row: dict, source: str) -> dict:
    return {
        "text":         row["Problem"].strip(),
        "ground_truth": row.get("Solution", "").strip(),
        "category":     row.get("Category", "").strip(),
        "level":        row.get("Level", "").strip(),
        "source":       source,
    }


def load_70_problems() -> dict[str, dict]:
    problems: dict[str, dict] = {}

    # 1. 60 IMO-proofbench rows
    for r in _read(PROOFBENCH_CSV):
        problems[r["Problem ID"]] = _normalize(r, "proofbench")

    # 2. erdos-659 (non-aletheia, full solution) from combined-benchmarks.csv
    combined = {r["Problem ID"]: r for r in _read(COMBINED_CSV)}
    if "erdos-659" not in combined:
        raise RuntimeError("erdos-659 missing from combined-benchmarks.csv")
    problems["erdos-659"] = _normalize(combined["erdos-659"], "combined-benchmarks")

    # 3. erdos-397, erdos-654, erdos-1051 from the "reduced" (non-aletheia-named) file
    erdos_reduced = {r["Problem ID"]: r for r in _read(ERDOS_REDUCED_CSV)}
    for pid in ("erdos-397", "erdos-654", "erdos-1051"):
        if pid not in erdos_reduced:
            raise RuntimeError(f"{pid} missing from erdos_problem_solution_pairs_reduced.csv")
        problems[pid] = _normalize(erdos_reduced[pid], "erdos-reduced")

    # 4. erdos-333: only aletheia version exists. Per user, load it as erdos-333.
    erdos_full = {r["Problem ID"]: r for r in _read(ERDOS_FULL_CSV)}
    if "erdos-333-aletheia" not in erdos_full:
        raise RuntimeError("erdos-333-aletheia missing from erdos_problem_solution_pairs.csv")
    e333 = _normalize(erdos_full["erdos-333-aletheia"], "erdos-aletheia(renamed)")
    problems["erdos-333"] = e333

    # 5. First Proof 4, 5, 6, 10
    fp_rows = {r["Problem ID"]: r for r in _read(FIRST_PROOF_CSV)}
    for n in (4, 5, 6, 10):
        pid = f"first-proof-{n}-official"
        if pid not in fp_rows:
            raise RuntimeError(f"{pid} missing from first-proof-official.csv")
        problems[pid] = _normalize(fp_rows[pid], "first-proof-official")

    # 6. Ramsey-Hypergraphs
    ram = _read(RAMSEY_CSV)
    if not ram or ram[0]["Problem ID"] != "ramsey-hypergraphs":
        raise RuntimeError("ramsey-hypergraphs row not found")
    problems["ramsey-hypergraphs"] = _normalize(ram[0], "ramsey-hypergraphs-solution")

    if len(problems) != 70:
        raise RuntimeError(f"Expected 70 problems, got {len(problems)}")

    # Validate all have non-empty text and ground truth.
    for pid, p in problems.items():
        if not p["text"]:
            raise RuntimeError(f"{pid}: empty problem text")
        if not p["ground_truth"]:
            raise RuntimeError(f"{pid}: empty ground truth")

    return problems


def summarize(problems: dict[str, dict]) -> None:
    """Print a short summary — useful before launching real runs."""
    print(f"Loaded {len(problems)} problems.")
    print(f"  60 proofbench: PB-Basic-001..030 (30) + PB-Advanced-001..030 (30)")
    print(f"  10 special:")
    for pid in sorted(SPECIAL_10):
        p = problems[pid]
        print(f"    {pid:<32}  prob={len(p['text']):>5}  gt={len(p['ground_truth']):>6}  src={p['source']}")


if __name__ == "__main__":
    ps = load_70_problems()
    summarize(ps)
