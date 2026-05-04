"""
Programmatic verifier for Hadamard matrix solutions.

A Hadamard matrix of order n is an n×n matrix H with entries ±1
such that H·H^T = n·I (rows are mutually orthogonal).

Equivalently:
  1. All entries are +1 or -1
  2. H·H^T = n·I_n (where I_n is the n×n identity matrix)

Property (2) implies:
  - Each row has norm sqrt(n)
  - Any two distinct rows are orthogonal (dot product = 0)
"""

from __future__ import annotations

import re
import io
import csv
import numpy as np


def parse_hadamard_csv(text: str) -> np.ndarray | None:
    """Parse a Hadamard matrix from CSV text embedded in a solution.

    Tries multiple formats:
      - Raw CSV lines of ±1 values
      - CSV wrapped in ```csv ... ``` blocks
      - Comma-separated rows with brackets
      - Space-separated rows

    Returns numpy array or None if parsing fails.
    """
    # Try to extract CSV block first
    csv_match = re.search(r"```(?:csv)?\s*\n(.*?)```", text, re.DOTALL)
    if csv_match:
        text = csv_match.group(1)

    # Try parsing as CSV
    rows = []

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Remove brackets/braces
        line = line.strip("[](){}")
        # Try comma-separated first, fall back to space-separated
        if "," in line:
            parts = [p.strip() for p in line.split(",") if p.strip()]
        else:
            parts = line.split()

        row = []
        for p in parts:
            p = p.strip().strip(",").strip()
            if p in ("1", "+1"):
                row.append(1)
            elif p in ("-1",):
                row.append(-1)
            elif p.lstrip("-").isdigit():
                val = int(p)
                if val in (1, -1):
                    row.append(val)
                else:
                    continue  # skip non ±1 values
            else:
                continue

        if len(row) >= 4:  # minimum useful row length
            rows.append(row)

    if not rows:
        return None

    # Check all rows have same length
    lengths = set(len(r) for r in rows)
    if len(lengths) > 1:
        # Try to find the most common length
        from collections import Counter
        most_common_len = Counter(len(r) for r in rows).most_common(1)[0][0]
        rows = [r for r in rows if len(r) == most_common_len]

    if not rows:
        return None

    return np.array(rows, dtype=np.int8)


def verify_hadamard(H: np.ndarray, expected_order: int | None = None) -> dict:
    """Verify that H is a valid Hadamard matrix.

    Returns dict with:
      valid: bool
      order: int (actual dimensions)
      checks: dict of individual check results
      violations: list of violation descriptions
    """
    violations = []
    checks = {}

    n = H.shape[0]
    checks["order"] = n

    # Check 1: Square matrix
    checks["is_square"] = H.shape[0] == H.shape[1]
    if not checks["is_square"]:
        violations.append(f"Matrix is {H.shape[0]}×{H.shape[1]}, not square")
        return {"valid": False, "order": n, "checks": checks, "violations": violations}

    # Check 2: Expected order (if specified)
    if expected_order is not None:
        checks["correct_order"] = n == expected_order
        if not checks["correct_order"]:
            violations.append(f"Order is {n}, expected {expected_order}")

    # Check 3: All entries are ±1
    unique_vals = set(np.unique(H).tolist())
    checks["entries_pm1"] = unique_vals.issubset({1, -1})
    if not checks["entries_pm1"]:
        violations.append(f"Entries include values other than ±1: {unique_vals - {1, -1}}")

    # Check 4: H·H^T = n·I
    # Use int32 to avoid overflow for large matrices
    H_int = H.astype(np.int32)
    product = H_int @ H_int.T

    expected = n * np.eye(n, dtype=np.int32)
    checks["orthogonality"] = bool(np.array_equal(product, expected))

    if not checks["orthogonality"]:
        # Diagnose: check diagonal and off-diagonal separately
        diag_correct = bool(np.all(np.diag(product) == n))
        checks["diagonal_correct"] = diag_correct
        if not diag_correct:
            bad_diag = np.where(np.diag(product) != n)[0]
            violations.append(f"Diagonal incorrect at {len(bad_diag)} positions "
                            f"(expected {n}, got values like {np.diag(product)[bad_diag[:3]].tolist()})")

        # Off-diagonal: should all be 0
        off_diag = product - np.diag(np.diag(product))
        max_off = int(np.max(np.abs(off_diag)))
        num_nonzero = int(np.count_nonzero(off_diag))
        checks["max_off_diagonal"] = max_off
        checks["nonzero_off_diagonal_count"] = num_nonzero
        if num_nonzero > 0:
            violations.append(f"{num_nonzero} non-zero off-diagonal entries in H·H^T "
                            f"(max absolute value: {max_off})")

    return {
        "valid": len(violations) == 0,
        "order": n,
        "checks": checks,
        "violations": violations,
    }


def verify_solution_text(solution_text: str, expected_order: int = 668) -> dict:
    """End-to-end: parse and verify a Hadamard matrix from solution text."""
    H = parse_hadamard_csv(solution_text)

    if H is None:
        return {
            "valid": False,
            "parse_error": True,
            "order": 0,
            "checks": {},
            "violations": ["Could not parse a matrix from the solution text"],
        }

    result = verify_hadamard(H, expected_order=expected_order)
    result["parse_error"] = False
    return result
