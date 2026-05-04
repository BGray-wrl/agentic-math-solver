from __future__ import annotations

import csv
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROBLEMS_DIR = BASE_DIR / "problems"
SOLUTIONS_DIR = BASE_DIR / "author-solutions"
OUTPUT_PATH = BASE_DIR / "first-proof-official.csv"
SOURCE = "https://github.com/1stproof/batch-1/tree/main/author-solutions"
FIELDNAMES = [
    "Problem ID",
    "Problem",
    "Solution",
    "Grading guidelines",
    "Category",
    "Level",
    "Short Answer",
    "Source",
]
CATEGORY_BY_NUMBER = {
    "1": "Analysis",
    "2": "Algebra",
    "3": "Combinatorics",
    "4": "Algebra",
    "5": "Geometry",
    "6": "Combinatorics",
    "7": "Geometry",
    "8": "Geometry",
    "9": "Algebra",
    "10": "Algebra",
}
LEVEL_BY_NUMBER = {
    "1": "4",
    "2": "2",
    "3": "4",
    "4": "3",
    "5": "2",
    "6": "3",
    "7": "3",
    "8": "3",
    "9": "1",
    "10": "1",
}


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def document_body(text: str) -> str:
    match = re.search(r"\\begin\{document\}(.*)\\end\{document\}", text, re.S)
    if match:
        return match.group(1)
    return text


def problem_number_from_path(path: Path) -> str:
    match = re.fullmatch(r"q(\d+)", path.stem)
    if not match:
        raise ValueError(f"Unexpected problem filename: {path.name}")
    return match.group(1)


def solution_path_for_number(number: str) -> Path:
    matches = sorted(SOLUTIONS_DIR.glob(f"{number}-*.tex"))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one solution file for {number}, found {len(matches)}")
    return matches[0]


def build_row(problem_path: Path) -> dict[str, str]:
    number = problem_number_from_path(problem_path)
    solution_path = solution_path_for_number(number)
    problem = collapse_whitespace(problem_path.read_text(encoding="utf-8"))
    solution_text = solution_path.read_text(encoding="utf-8")
    solution = collapse_whitespace(document_body(solution_text))

    return {
        "Problem ID": f"first-proof-{number}-official",
        "Problem": problem,
        "Solution": solution,
        "Grading guidelines": "",
        "Category": CATEGORY_BY_NUMBER[number],
        "Level": LEVEL_BY_NUMBER[number],
        "Short Answer": "",
        "Source": SOURCE,
    }


def sort_key(path: Path) -> int:
    return int(problem_number_from_path(path))


def main() -> None:
    problem_paths = sorted(
        [path for path in PROBLEMS_DIR.glob("q*.tex") if path.stem != "q9b"],
        key=sort_key,
    )
    rows = [build_row(path) for path in problem_paths]

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
