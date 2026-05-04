from __future__ import annotations

import csv
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROMPTS_PATH = BASE_DIR / "open_problems_prompts.csv"
SOLUTION_PATH = BASE_DIR / "ramsey-hypergraphs" / "hypergraph-ramsey-gpt-5-4-pro-solution.tex"
OUTPUT_PATH = BASE_DIR / "ramsey-hypergraphs-solution.csv"
PROBLEM_ID = "ramsey-hypergraphs"
FIELDNAMES = ["Problem ID", "Problem", "Solution", "Category", "Level", "Source"]


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def document_body(text: str) -> str:
    match = re.search(r"\\begin\{document\}(.*)\\end\{document\}", text, re.S)
    if match:
        return match.group(1)
    return text


def load_problem() -> str:
    with PROMPTS_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("problem_id") == PROBLEM_ID:
                return row["prompt"]
    raise ValueError(f"Could not find problem_id={PROBLEM_ID!r} in {PROMPTS_PATH}")


def load_solution() -> str:
    text = SOLUTION_PATH.read_text(encoding="utf-8")
    return collapse_whitespace(document_body(text))


def main() -> None:
    row = {
        "Problem ID": PROBLEM_ID,
        "Problem": load_problem(),
        "Solution": load_solution(),
        "Category": "",
        "Level": "Moderately Interesting",
        "Source": "https://epoch.ai/frontiermath/open-problems/ramsey-hypergraphs",
    }

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    main()
