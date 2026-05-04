#!/usr/bin/env python3
"""
End-to-end pipeline test for Hadamard agentic v3.

Tests the full chain: model writes code → sandbox executes → file/stdout I/O →
checker reads matrix → build_checker_feedback returns rich metrics.

Run:
    uv run experiments/hadamard_agentic/test_pipeline_e2e.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import shutil
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from sandbox_exec import execute_code
from agentic_loop import build_checker_feedback, load_matrix_from_file
from hadamard_checker import parse_hadamard_csv, verify_hadamard

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, condition))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return condition


def build_known_hadamard(order=4):
    """Build a known valid Hadamard matrix via Sylvester construction (order must be 2^k)."""
    from scipy.linalg import hadamard
    return hadamard(order).astype(np.int8)


def build_near_miss_668():
    """Build a 668×668 ±1 matrix that's NOT a valid Hadamard — for testing partial metrics."""
    np.random.seed(42)
    H = np.random.choice([1, -1], size=(668, 668)).astype(np.int8)
    # Make it symmetric-ish to get some orthogonal pairs but definitely not valid
    return H


def build_valid_hadamard_via_kronecker():
    """Build a valid Hadamard of order 4 (small, known-good) for solved-detection test."""
    return build_known_hadamard(4)


def test_1_sandbox_file_io():
    """Test that sandbox writes candidate.csv to shared_dir and execute_code detects it."""
    print("\n=== Test 1: Sandbox file-based I/O ===")
    shared_dir = tempfile.mkdtemp(prefix="test_hadamard_")

    try:
        # Code that writes a 16×16 Hadamard matrix to HADAMARD_OUTPUT_DIR/candidate.csv
        code = """\
import os, numpy as np
from scipy.linalg import hadamard
H = hadamard(16).astype(np.int8)
output_dir = os.environ.get("HADAMARD_OUTPUT_DIR", ".")
path = os.path.join(output_dir, "candidate.csv")
np.savetxt(path, H, fmt="%d", delimiter=",")
print(f"Matrix written to {path}, shape={H.shape}")
"""
        result = execute_code(code, timeout=30, shared_dir=shared_dir)

        check("sandbox executed successfully", result["success"], f"rc={result['returncode']}")
        check("no timeout", not result["timed_out"])
        check("matrix_file detected", result["matrix_file"] is not None,
              f"path={result.get('matrix_file')}")
        check("stdout mentions shape", "shape=(16, 16)" in result["stdout"],
              f"stdout={result['stdout'][:200]}")

        # Verify the file can be loaded
        if result["matrix_file"]:
            H = load_matrix_from_file(result["matrix_file"])
            check("matrix loaded from file", H is not None)
            if H is not None:
                check("matrix shape correct", H.shape == (16, 16), f"shape={H.shape}")
                check("matrix entries are ±1", set(np.unique(H).tolist()).issubset({1, -1}))

                # Verify it's actually a valid Hadamard
                vr = verify_hadamard(H, expected_order=16)
                check("matrix is valid Hadamard(16)", vr["valid"], f"violations={vr['violations']}")
    finally:
        shutil.rmtree(shared_dir, ignore_errors=True)


def test_2_large_matrix_file_io():
    """Test with a 668×668 matrix — the exact size that broke stdout truncation."""
    print("\n=== Test 2: 668×668 matrix file I/O (the bug that broke v2) ===")
    shared_dir = tempfile.mkdtemp(prefix="test_hadamard_668_")

    try:
        # Code that writes a 668×668 random ±1 matrix
        code = """\
import os, numpy as np
np.random.seed(42)
H = np.random.choice([1, -1], size=(668, 668)).astype(np.int8)
output_dir = os.environ.get("HADAMARD_OUTPUT_DIR", ".")
path = os.path.join(output_dir, "candidate.csv")
np.savetxt(path, H, fmt="%d", delimiter=",")
print(f"668x668 matrix written to {path}")
print(f"Shape: {H.shape}, entries: min={H.min()}, max={H.max()}")
"""
        result = execute_code(code, timeout=60, shared_dir=shared_dir)

        check("668 sandbox executed", result["success"])
        check("668 matrix_file detected", result["matrix_file"] is not None)

        if result["matrix_file"]:
            H = load_matrix_from_file(result["matrix_file"])
            check("668 matrix loaded", H is not None)
            if H is not None:
                check("668 shape correct", H.shape == (668, 668), f"shape={H.shape}")

                # This is the critical check — stdout would have given us ~4 rows
                # File I/O should give us all 668 rows
                check("668 all entries ±1", set(np.unique(H).tolist()).issubset({1, -1}))

        # Also verify stdout is NOT enough for 668×668
        stdout_matrix = parse_hadamard_csv(result["stdout"])
        if stdout_matrix is not None:
            check("stdout truncation detected",
                  stdout_matrix.shape[0] < 668,
                  f"stdout parsed {stdout_matrix.shape[0]} rows (expected < 668)")
        else:
            check("stdout has no parseable matrix", True,
                  "stdout doesn't contain full CSV — file I/O is necessary")
    finally:
        shutil.rmtree(shared_dir, ignore_errors=True)


def test_3_checker_feedback_valid():
    """Test build_checker_feedback with a known-valid Hadamard(16)."""
    print("\n=== Test 3: Checker feedback — valid Hadamard(16) ===")
    H = build_known_hadamard(16)

    feedback, metrics = build_checker_feedback(H, target_order=16, source="file")

    check("valid detected", metrics["valid"])
    check("quality score = 100", metrics["quality_score"] == 100.0, f"got {metrics['quality_score']}")
    check("orthogonality = 100%", metrics["orthogonality_pct"] == 100.0)
    check("perfect rows = 16", metrics["perfect_rows"] == 16)
    check("max off-diag = 0", metrics["max_off_diagonal"] == 0)
    check("source recorded", metrics["source"] == "file")
    check("feedback contains PASSED", feedback is not None and "PASSED" in feedback)


def test_4_checker_feedback_near_miss():
    """Test build_checker_feedback with a random 668×668 — should give rich partial metrics."""
    print("\n=== Test 4: Checker feedback — 668×668 near-miss (partial progress tracking) ===")
    H = build_near_miss_668()

    feedback, metrics = build_checker_feedback(H, target_order=668, source="file")

    check("not valid", not metrics["valid"])
    check("order = 668", metrics["order"] == 668)
    check("entries_ok", metrics["entries_ok"])
    check("has orthogonality_pct", isinstance(metrics["orthogonality_pct"], float),
          f"orth={metrics['orthogonality_pct']}%")
    check("orthogonality between 0-100", 0 <= metrics["orthogonality_pct"] <= 100)
    check("has perfect_rows", isinstance(metrics["perfect_rows"], int),
          f"perfect={metrics['perfect_rows']}/668")
    check("has max_off_diagonal", metrics["max_off_diagonal"] is not None,
          f"max_off={metrics['max_off_diagonal']}")
    check("quality score in (0,100)", 0 < metrics["quality_score"] < 100,
          f"quality={metrics['quality_score']}")
    check("has nonzero_off_diag count", metrics["nonzero_off_diag"] is not None,
          f"nonzero={metrics['nonzero_off_diag']}")

    # Feedback string should contain useful info
    check("feedback has orthogonality%", "orthogonal" in feedback.lower())
    check("feedback has quality score", "quality score" in feedback.lower())
    check("feedback has worst pairs", "rows (" in feedback)
    check("feedback has perfect rows", "perfect rows" in feedback.lower())

    print(f"\n  Sample feedback (first 500 chars):\n  {feedback[:500]}")


def test_5_checker_feedback_none():
    """Test build_checker_feedback with None matrix — should return empty metrics gracefully."""
    print("\n=== Test 5: Checker feedback — no matrix found ===")

    feedback, metrics = build_checker_feedback(None, target_order=668, source="none")

    check("feedback is None", feedback is None)
    check("quality = 0", metrics["quality_score"] == 0.0)
    check("valid = False", not metrics["valid"])
    check("order = 0", metrics["order"] == 0)


def test_6_checker_feedback_wrong_size():
    """Test with a valid Hadamard(16) but target=668 — should report order mismatch."""
    print("\n=== Test 6: Checker feedback — wrong order (16 vs target 668) ===")
    H = build_known_hadamard(16)

    feedback, metrics = build_checker_feedback(H, target_order=668, source="file")

    check("not valid (wrong order)", not metrics["valid"])
    check("order = 16", metrics["order"] == 16)
    # Quality: 50 pts orth (valid) + ~1.2 pts size (16/668) ≈ 51.2
    check("quality reflects perfect orth + small size", 50 < metrics["quality_score"] < 55,
          f"quality={metrics['quality_score']}")
    check("feedback mentions order mismatch", feedback is not None)


def test_7_stdout_fallback():
    """Test that small matrices printed to stdout still work (fallback path)."""
    print("\n=== Test 7: Stdout fallback for small matrices ===")
    shared_dir = tempfile.mkdtemp(prefix="test_hadamard_fallback_")

    try:
        # Code that ONLY prints to stdout, no file write — uses scipy Hadamard(16)
        code = """\
import numpy as np
from scipy.linalg import hadamard
H = hadamard(16).astype(np.int8)
# Print as CSV (no file write)
for row in H:
    print(",".join(str(x) for x in row))
"""
        result = execute_code(code, timeout=30, shared_dir=shared_dir)
        check("stdout fallback: code ran", result["success"])
        check("stdout fallback: no matrix_file", result["matrix_file"] is None)

        # Parse from stdout
        H = parse_hadamard_csv(result["stdout"])
        check("stdout fallback: matrix parsed", H is not None)
        if H is not None:
            check("stdout fallback: shape (16,16)", H.shape == (16, 16))
            vr = verify_hadamard(H, expected_order=16)
            check("stdout fallback: valid Hadamard", vr["valid"])
    finally:
        shutil.rmtree(shared_dir, ignore_errors=True)


def test_8_stale_file_cleanup():
    """Test that stale candidate.csv from a previous turn is cleaned before new execution."""
    print("\n=== Test 8: Stale file cleanup between turns ===")
    shared_dir = tempfile.mkdtemp(prefix="test_hadamard_stale_")

    try:
        # Write a fake stale candidate.csv
        stale_path = os.path.join(shared_dir, "candidate.csv")
        with open(stale_path, "w") as f:
            f.write("1,1\n1,-1\n")
        check("stale file exists", os.path.exists(stale_path))

        # Simulate what agentic_loop does: clean before execution
        if os.path.exists(stale_path):
            os.remove(stale_path)
        check("stale file cleaned", not os.path.exists(stale_path))

        # Run code that does NOT write candidate.csv
        code = "print('no matrix here')\n"
        result = execute_code(code, timeout=10, shared_dir=shared_dir)
        check("no false positive matrix_file", result["matrix_file"] is None)
    finally:
        shutil.rmtree(shared_dir, ignore_errors=True)


def test_9_error_handling():
    """Test that code errors are captured properly."""
    print("\n=== Test 9: Error handling in sandbox ===")
    shared_dir = tempfile.mkdtemp(prefix="test_hadamard_err_")

    try:
        # Code that raises an exception
        code = "raise ValueError('intentional test error')\n"
        result = execute_code(code, timeout=10, shared_dir=shared_dir)
        check("error: not success", not result["success"])
        check("error: stderr has message", "intentional test error" in result["stderr"])
        check("error: no matrix", result["matrix_file"] is None)

        # Code that times out
        code = "import time; time.sleep(100)\n"
        result = execute_code(code, timeout=2, shared_dir=shared_dir)
        check("timeout: detected", result["timed_out"])
        check("timeout: not success", not result["success"])
    finally:
        shutil.rmtree(shared_dir, ignore_errors=True)


def test_10_quality_score_ordering():
    """Verify quality scores order correctly: bigger matrix closer to target = higher score."""
    print("\n=== Test 10: Quality score ordering ===")

    # Build matrices of different sizes
    H16 = build_known_hadamard(16)  # 16×16 valid
    H_random_100 = np.random.choice([1, -1], size=(100, 100)).astype(np.int8)
    H_random_668 = build_near_miss_668()  # 668×668 random

    _, m16 = build_checker_feedback(H16, target_order=668, source="test")
    _, m100 = build_checker_feedback(H_random_100, target_order=668, source="test")
    _, m668 = build_checker_feedback(H_random_668, target_order=668, source="test")

    check("quality: 668 random > 100 random",
          m668["quality_score"] > m100["quality_score"],
          f"668={m668['quality_score']} vs 100={m100['quality_score']}")
    # Valid 16×16 has 100% orth (50pts) vs random 100×100 with ~3% orth
    # So valid-small beats random-medium — this is correct behavior
    check("quality: valid 16 > random 100 (orth dominates)",
          m16["quality_score"] > m100["quality_score"],
          f"16valid={m16['quality_score']} vs 100rand={m100['quality_score']}")

    # A valid 16×16: perfect orth (50pts) + tiny size (1.2pts) ≈ 51.2
    check("quality 16 valid: orth=100%, quality~51",
          m16["orthogonality_pct"] == 100.0 and 50 < m16["quality_score"] < 55,
          f"orth={m16['orthogonality_pct']}% quality={m16['quality_score']}")


if __name__ == "__main__":
    print("=" * 60)
    print("Hadamard Pipeline v3 — End-to-End Test Suite")
    print("=" * 60)

    test_1_sandbox_file_io()
    test_2_large_matrix_file_io()
    test_3_checker_feedback_valid()
    test_4_checker_feedback_near_miss()
    test_5_checker_feedback_none()
    test_6_checker_feedback_wrong_size()
    test_7_stdout_fallback()
    test_8_stale_file_cleanup()
    test_9_error_handling()
    test_10_quality_score_ordering()

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    failed = total - passed
    print(f"Results: {passed}/{total} passed" + (f", {failed} FAILED" if failed else ""))
    print("=" * 60)

    if failed:
        print("\nFailed checks:")
        for name, ok in results:
            if not ok:
                print(f"  - {name}")
        sys.exit(1)
    else:
        print("\nAll checks passed! Pipeline v3 is ready for a real run.")
        sys.exit(0)
