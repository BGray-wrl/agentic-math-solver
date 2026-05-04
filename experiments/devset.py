"""
Dev set: 6 problems for rapid pipeline iteration.

Designed for fast feedback (~5 min with a single model, pass@1).
Covers the full difficulty gradient with known behavioral signatures
so you can tell whether a pipeline change helped.

Usage:
    from devset import DEV_SET_IDS, select_devset

    # In an experiment's select_problems():
    def select_problems(all_rows):
        return select_devset(all_rows)
"""

# ── The 6 problems and why each is here ──────────────────────────────────

DEV_SET = {
    # ── SANITY (should always pass — regression alarm if it doesn't) ──
    "PB-Basic-024": {
        # IMO-medium, Number theory, short GT (1481 chars)
        # Pipeline: 7/7 both models. Generate-only: nemotron 7, deepseek 2.
        # Fast to judge. If this breaks, something is fundamentally wrong.
        "role": "sanity",
    },

    # ── BOUNDARY (where pipeline architecture changes show signal) ──
    "PB-Basic-028": {
        # IMO-medium. Generate-only: gemini-3-flash 7/7, others 0/7.
        # Pipeline should help weaker models reach partial/full credit.
        # Replaced PB-Advanced-014 (was 1124s mean) — runs in ~120s.
        "role": "boundary-pipeline-helps",
    },
    "PB-Basic-012": {
        # IMO-medium. Bimodal: strong models 6-7/7, weak models 0/7.
        # Verifier over-approval on wrong solutions would show clearly.
        # Replaced PB-Advanced-023 (was 616s mean) — runs in ~149s.
        "role": "boundary-verifier-bug",
    },
    "PB-Basic-017": {
        # pre-IMO. 4/5 models solve at 7/7 generate-only (mean 5.60/7).
        # Perfect canary: if pipeline degrades these correct solutions, it's clearly hurting.
        # Replaced PB-Advanced-026 (was 327s mean) — runs in ~79s.
        "role": "boundary-pipeline-hurts",
    },

    # ── HARD (currently 0/7 — the stretch goal) ──
    "PB-Basic-007": {
        # IMO-medium. Generate-only: 0.40/7 mean across 5 models — genuinely hard.
        # Replaced PB-Advanced-006 (was 1150s mean) — runs in ~120s.
        "role": "hard",
    },

    # ── FRONTIER (the north star) ──
    "erdos-659": {
        # "Negligible Novelty" (recently solved), Combinatorics, GT 11914 chars
        # gpt-5.4-mini got 3/7 (partial); all other models 0/7.
        # This is the target: replicate frontier performance with orchestration.
        "role": "frontier",
    },
}

DEV_SET_IDS = list(DEV_SET.keys())


def select_devset(all_rows: list[dict]) -> dict[str, dict]:
    """Drop-in replacement for select_problems() in the experiment template."""
    problems = {}
    for row in all_rows:
        pid = row["Problem ID"]
        if pid in DEV_SET_IDS:
            problems[pid] = {
                "text":     row["Problem"],
                "solution": row.get("Solution", ""),
                "level":    row.get("Level", ""),
                "category": row.get("Category", ""),
                "role":     DEV_SET[pid]["role"],
            }
    return problems
