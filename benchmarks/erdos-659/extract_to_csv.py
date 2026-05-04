from __future__ import annotations

import csv
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "erdos-659.csv"


def read_text_one_line(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = text.strip()
    return re.sub(r"\s+", " ", text)


def main() -> None:
    row = {
        "Problem ID": "erdos-659",
        "Problem": read_text_one_line(BASE_DIR / "problem.tex"),
        "Solution": read_text_one_line(BASE_DIR / "solution.tex"),
        "Grading guidelines": "None/NA",
        "Category": "Combinatorics",
        "Level": "Negligible Novelty",
        "Short Answer": read_text_one_line(BASE_DIR / "short-answer.tex"),
        "Source": "https://arxiv.org/pdf/2601.09102",
    }

    fieldnames = [
        "Problem ID",
        "Problem",
        "Solution",
        "Grading guidelines",
        "Category",
        "Level",
        "Short Answer",
        "Source",
    ]

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    main()
