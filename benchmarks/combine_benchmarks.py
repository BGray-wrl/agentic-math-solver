from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "combined-benchmarks.csv"
FIELDNAMES = ["Problem ID", "Problem", "Solution", "Category", "Level", "Source"]
GENERATORS = [
    (BASE_DIR / "erdos-659" / "extract_to_csv.py", BASE_DIR / "erdos-659"),
    (BASE_DIR / "first-proof" / "official" / "extract_to_csv.py", BASE_DIR / "first-proof" / "official"),
    (BASE_DIR / "first-proof" / "aletheia" / "extract_to_csv.py", BASE_DIR / "first-proof" / "aletheia"),
    (BASE_DIR / "general-aletheia" / "extract_to_csv.py", BASE_DIR / "general-aletheia"),
]
SOURCES = [
    BASE_DIR / "erdos-659" / "erdos-659.csv",
    BASE_DIR / "erdos-aletheia" / "erdos_problem_solution_pairs.csv",
    BASE_DIR / "first-proof" / "official" / "first-proof-official.csv",
    BASE_DIR / "first-proof" / "aletheia" / "first-proof-aletheia.csv",
    BASE_DIR / "general-aletheia" / "general-aletheia.csv",
    BASE_DIR / "frontiermath-open-problems" / "ramsey-hypergraphs-solution.csv",
    BASE_DIR / "IMO-bench" / "proofbench.csv",
]


def run_generators() -> None:
    for script_path, cwd in GENERATORS:
        subprocess.run(
            [sys.executable, str(script_path.relative_to(cwd))],
            cwd=cwd,
            check=True,
        )


def normalized_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append(
                {
                    "Problem ID": row.get("Problem ID", ""),
                    "Problem": row.get("Problem", ""),
                    "Solution": row.get("Solution", ""),
                    "Category": row.get("Category", ""),
                    "Level": row.get("Level", ""),
                    "Source": row.get("Source", ""),
                }
            )
        return rows


def main() -> None:
    run_generators()

    rows: list[dict[str, str]] = []
    for csv_path in SOURCES:
        rows.extend(normalized_rows(csv_path))

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
