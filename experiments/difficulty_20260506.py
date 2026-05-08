"""Difficulty annotations for the 70-problem benchmark.

Two parallel fields per problem:
  - difficulty (int 0-5): unified frontier-emphasis scale
        0  pre-competition
        1  competition-hard          (all IMO-tier ProofBench, plus rediscovered erdos-397)
        2  research-easy             (negligibly-novel erdős, model-already-solved first-proof-10)
        3  research-medium           (minor-novelty erdős, sketch-tier first-proof-5)
        4  research-hard             (publishable-borderline first-proof-4 / 6)
        5  research-frontier         (ramsey-hypergraphs — only Epoch entry to fall)
  - difficulty_label (str): human-readable mirror of the int.

Plus, for the frontier-10 only:
  - difficulty_provenance (str): justification text (where the rating came from).

The native `level` string from problemset_70 (pre-IMO / IMO-easy / IMO-medium /
IMO-hard, plus the novelty labels for frontier-10) is preserved separately on every
row, so granular ProofBench analysis is still available without committing to the
0-5 scale.

User's manual rating table (2026-05-06):
  erdos-397             1   Rediscovered in a Chinese math competition (per user).
  erdos-333             2   GPT recommendation; user notes it as a wild card.
  erdos-654             2   DeepMind listed as negligibly novel.
  erdos-659             2   User worked on it directly; rates it research-easy.
  first-proof-10        2   First-proof team reported it was solved by the model.
  erdos-1051            3   Aletheia minor-novelty tier.
  first-proof-5         3   FP team: sketch was nearly appropriate but not complete.
  first-proof-4         4   FP team: model totally off; OpenAI special team solved
                            with custom orchestration. Borderline-publishable.
  first-proof-6         4   Same provenance / tier as first-proof-4.
  ramsey-hypergraphs    5   Epoch reports only this entry has fallen — publishable.
"""

from __future__ import annotations

LABELS = {
    0: "pre-competition",
    1: "competition-hard",
    2: "research-easy",
    3: "research-medium",
    4: "research-hard",
    5: "research-frontier",
}

# Native ProofBench level → unified difficulty score.
# All IMO-tier problems collapse to 1 (competition-hard); the granular IMO-easy /
# IMO-medium / IMO-hard distinction is preserved in the row-level `level` field
# for analyses that need it.
LEVEL_TO_DIFFICULTY = {
    "pre-IMO":    0,
    "IMO-easy":   1,
    "IMO-medium": 1,
    "IMO-hard":   1,
}

# Frontier-10 manual ratings + provenance. Keys match problemset_70 IDs exactly.
FRONTIER_DIFFICULTY = {
    "erdos-397":               (1, "Rediscovered in a Chinese math competition (per user); rates as competition-hard rather than research-novel."),
    "erdos-333":               (2, "GPT-suggested research-easy. User flagged as wild card — defer to label."),
    "erdos-654":               (2, "DeepMind reported negligible novelty when their solver hit it."),
    "erdos-659":               (2, "User worked the problem directly and rates it research-easy."),
    "first-proof-10-official": (2, "First-proof team reported the model solved this one cleanly."),
    "erdos-1051":              (3, "Aletheia minor-novelty tier; harder than the negligibly-novel cluster but not borderline-publishable."),
    "first-proof-5-official":  (3, "First-proof team: sketch was nearly correct, full solution missing. Research-medium."),
    "first-proof-4-official":  (4, "First-proof team: model totally off. OpenAI's special team reportedly solved with custom orchestration. Borderline-publishable."),
    "first-proof-6-official":  (4, "Same provenance / tier as first-proof-4."),
    "ramsey-hypergraphs":      (5, "Epoch reports this is the only entry from their open-problem set to have fallen — research-frontier / publishable result."),
}


def annotate(problem_id: str, level: str | None) -> dict:
    """Return difficulty annotation dict for a given problem.

    Keys returned: difficulty (int|None), difficulty_label (str|None),
    difficulty_provenance (str|None).
    """
    if problem_id in FRONTIER_DIFFICULTY:
        d, prov = FRONTIER_DIFFICULTY[problem_id]
        return {
            "difficulty": d,
            "difficulty_label": LABELS[d],
            "difficulty_provenance": prov,
        }
    d = LEVEL_TO_DIFFICULTY.get(level or "")
    if d is None:
        return {"difficulty": None, "difficulty_label": None, "difficulty_provenance": None}
    return {
        "difficulty": d,
        "difficulty_label": LABELS[d],
        "difficulty_provenance": None,
    }


def is_frontier(problem_id: str) -> bool:
    return problem_id in FRONTIER_DIFFICULTY


if __name__ == "__main__":
    # Smoke test — print annotations for the full 70-problem set.
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from problemset_70 import load_70_problems

    ps = load_70_problems()
    rows = []
    for pid, p in ps.items():
        ann = annotate(pid, p.get("level"))
        rows.append((pid, p.get("level"), ann["difficulty"], ann["difficulty_label"]))

    rows.sort(key=lambda r: (r[2] if r[2] is not None else 99, r[0]))
    print(f"{'problem_id':32s} {'level':25s} {'d':>2s}  label")
    print("-" * 80)
    for pid, lvl, d, lbl in rows:
        print(f"{pid:32s} {str(lvl):25s} {str(d):>2s}  {lbl}")
    from collections import Counter
    print()
    print("DISTRIBUTION:", dict(Counter(r[2] for r in rows)))
