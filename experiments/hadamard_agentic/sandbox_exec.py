"""
Safe subprocess execution for model-generated Python code.

Runs code in an isolated subprocess with timeout and captures stdout/stderr.
The subprocess gets a shared temp directory for writing large outputs (matrices).
"""

from __future__ import annotations

import os
import sys
import tempfile
import subprocess
from pathlib import Path


def execute_code(
    code: str,
    timeout: int = 300,
    cwd: str | None = None,
    shared_dir: str | None = None,
) -> dict:
    """Execute Python code in a subprocess.

    Args:
        code: Python source code to execute.
        timeout: Max seconds before killing the process.
        cwd: Working directory for the subprocess.
        shared_dir: A temp directory the subprocess can write files to.
            Passed as HADAMARD_OUTPUT_DIR env var. The model should write
            candidate matrices to {HADAMARD_OUTPUT_DIR}/candidate.csv.

    Returns dict with:
        success: bool
        stdout: str (last 8KB — use shared_dir for large outputs)
        stderr: str
        returncode: int
        timed_out: bool
        matrix_file: str | None — path to candidate.csv if it was written
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=cwd
    ) as f:
        f.write(code)
        tmp_path = f.name

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if shared_dir:
        env["HADAMARD_OUTPUT_DIR"] = shared_dir

    matrix_file = None

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )

        # Check if a candidate matrix was written to the shared dir
        if shared_dir:
            candidate_path = os.path.join(shared_dir, "candidate.csv")
            if os.path.exists(candidate_path):
                matrix_file = candidate_path

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-8000:] if len(result.stdout) > 8000 else result.stdout,
            "stderr": result.stderr[-4000:] if len(result.stderr) > 4000 else result.stderr,
            "returncode": result.returncode,
            "timed_out": False,
            "matrix_file": matrix_file,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Code execution timed out after {timeout}s",
            "returncode": -1,
            "timed_out": True,
            "matrix_file": None,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "timed_out": False,
            "matrix_file": None,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
