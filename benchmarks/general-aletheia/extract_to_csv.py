from __future__ import annotations

import csv
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "general-aletheia.csv"
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


def parse_braced(text: str, start: int) -> tuple[str, int]:
    if text[start] != "{":
        raise ValueError(f"Expected '{{' at index {start}")

    depth = 0
    out: list[str] = []
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
            if depth > 1:
                out.append(ch)
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return "".join(out), i + 1
            out.append(ch)
        else:
            out.append(ch)
        i += 1

    raise ValueError("Unmatched brace")


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def extract_envs(text: str, env: str) -> list[tuple[str, str]]:
    token = f"\\begin{{{env}}}"
    end_token = f"\\end{{{env}}}"
    items: list[tuple[str, str]] = []
    start = 0

    while True:
        idx = text.find(token, start)
        if idx == -1:
            break
        title, body_start = parse_braced(text, idx + len(token))
        body_end = text.find(end_token, body_start)
        if body_end == -1:
            raise ValueError(f"Missing {end_token}")
        body = collapse_whitespace(text[body_start:body_end])
        items.append((title, body))
        start = body_end + len(end_token)

    return items


def combine_turns(items: list[tuple[str, str]], label: str) -> str:
    parts = []
    for i, (_, body) in enumerate(items, start=1):
        parts.append(f"{label} {i}: {body}")
    return "\n\n".join(parts)


def build_hodgebundle_row() -> dict[str, str]:
    text = (BASE_DIR / "HodgeBundle.tex").read_text(encoding="utf-8")
    problems = extract_envs(text, "problem")
    solutions = extract_envs(text, "solution")
    if len(problems) != 1 or len(solutions) != 1:
        raise ValueError("Expected exactly one problem and one solution in HodgeBundle.tex")

    return {
        "Problem ID": "aletheia-hodgebundle",
        "Problem": problems[0][1],
        "Solution": solutions[0][1],
        "Grading guidelines": "",
        "Category": "Geometry",
        "Level": "Publishable Research",
        "Short Answer": "",
        "Source": "https://github.com/google-deepmind/superhuman/tree/main/aletheia/HodgeBundle",
    }


def build_f26_row() -> dict[str, str]:
    text = (BASE_DIR / "F26.tex").read_text(encoding="utf-8")
    problems = extract_envs(text, "problem")
    solutions = extract_envs(text, "solution")
    if len(problems) != 3 or len(solutions) != 3:
        raise ValueError("Expected exactly three problems and three solutions in F26.tex")

    return {
        "Problem ID": "aletheia-f26",
        "Problem": combine_turns(problems, "Turn"),
        "Solution": combine_turns(solutions, "Turn"),
        "Grading guidelines": "",
        "Category": "Algebra",
        "Level": "Publishable Research",
        "Short Answer": "",
        "Source": "https://github.com/google-deepmind/superhuman/tree/main/aletheia/F26",
    }


def main() -> None:
    rows = [build_f26_row(), build_hodgebundle_row()]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
