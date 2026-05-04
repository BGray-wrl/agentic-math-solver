from __future__ import annotations

import csv
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "first-proof-aletheia.csv"
SOURCE = "https://github.com/google-deepmind/superhuman/tree/main/aletheia/FirstProof"
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
    "2": "Algebra",
    "5": "Geometry",
    "7": "Geometry",
    "9": "Algebra",
    "10": "Algebra",
}
LEVEL_BY_NUMBER = {
    "2": "2",
    "5": "2",
    "7": "3",
    "9": "1",
    "10": "1",
}


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


def extract_env(text: str, env: str) -> tuple[str, str]:
    token = f"\\begin{{{env}}}"
    start = text.find(token)
    if start == -1:
        raise ValueError(f"Missing {token}")

    title, body_start = parse_braced(text, start + len(token))
    end_token = f"\\end{{{env}}}"
    end = text.find(end_token, body_start)
    if end == -1:
        raise ValueError(f"Missing {end_token}")

    body = text[body_start:end]
    return title, collapse_whitespace(body)


def problem_id_from_path(tex_path: Path) -> str:
    match = re.search(r"FP(\d+)_", tex_path.stem)
    if not match:
        raise ValueError(f"Could not parse problem number from filename: {tex_path.name}")
    return f"first-proof-{match.group(1)}-aletheia"


def problem_number_from_path(tex_path: Path) -> str:
    match = re.search(r"FP(\d+)_", tex_path.stem)
    if not match:
        raise ValueError(f"Could not parse problem number from filename: {tex_path.name}")
    return match.group(1)


def build_row(tex_path: Path) -> dict[str, str]:
    text = tex_path.read_text(encoding="utf-8")
    _, problem = extract_env(text, "problem")
    _, solution = extract_env(text, "solution")
    number = problem_number_from_path(tex_path)

    return {
        "Problem ID": f"first-proof-{number}-aletheia",
        "Problem": problem,
        "Solution": solution,
        "Grading guidelines": "",
        "Category": CATEGORY_BY_NUMBER[number],
        "Level": LEVEL_BY_NUMBER[number],
        "Short Answer": "",
        "Source": SOURCE,
    }


def sort_key(path: Path) -> int:
    match = re.search(r"FP(\d+)_", path.stem)
    if not match:
        raise ValueError(f"Could not parse numeric order from filename: {path.name}")
    return int(match.group(1))


def main() -> None:
    rows = [build_row(path) for path in sorted(BASE_DIR.glob("*.tex"), key=sort_key)]

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
