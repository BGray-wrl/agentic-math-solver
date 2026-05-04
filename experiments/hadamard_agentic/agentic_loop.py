"""
Core agentic coding loop for Hadamard matrix construction (v3).

v3 fixes from v2:
  - File-based matrix I/O: model writes candidate.csv to a shared dir,
    checker reads from file — no stdout truncation
  - Rich partial-progress feedback: orthogonality %, perfect row count,
    max off-diagonal value, PAF-like metrics
  - Tracks best candidate by quality score, not just order
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import tempfile
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

import litellm

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from hadamard_checker import verify_hadamard, parse_hadamard_csv

from prompts import (
    SYSTEM_PROMPT, FEEDBACK_TEMPLATE, CHECKER_PASS, CHECKER_FAIL,
    CHECKER_DETAIL_ORTHOGONALITY, STALL_NUDGE, REFLECTION_PROMPT,
    PHASE_NUDGE_EARLY, PHASE_NUDGE_MID, PHASE_NUDGE_LATE,
)
from sandbox_exec import execute_code


def extract_code_blocks(text: str) -> list[str]:
    """Extract Python code blocks from model response."""
    blocks = re.findall(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if not blocks:
        blocks = re.findall(r"```\s*\n(.*?)```", text, re.DOTALL)
    return blocks


def load_matrix_from_file(path: str) -> np.ndarray | None:
    """Load a ±1 matrix from a CSV file."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return parse_hadamard_csv(text)
    except Exception:
        return None


def build_checker_feedback(
    H: np.ndarray | None,
    target_order: int,
    source: str = "stdout",
) -> tuple[str | None, dict]:
    """Run programmatic verification and build detailed feedback.

    Returns (feedback_string, metrics_dict).
    metrics_dict always has keys even if H is None.
    """
    empty_metrics = {
        "order": 0, "valid": False, "entries_ok": False,
        "orthogonality_pct": 0.0, "perfect_rows": 0,
        "max_off_diagonal": None, "nonzero_off_diag": None,
        "quality_score": 0.0, "source": source,
    }

    if H is None:
        return None, empty_metrics

    result = verify_hadamard(H, expected_order=target_order)
    n = H.shape[0]
    checks = result["checks"]

    metrics = {
        "order": result["order"],
        "valid": result["valid"],
        "entries_ok": checks.get("entries_pm1", False),
        "source": source,
    }

    if result["valid"]:
        metrics.update({
            "orthogonality_pct": 100.0,
            "perfect_rows": n,
            "max_off_diagonal": 0,
            "nonzero_off_diag": 0,
            "quality_score": 100.0,
        })
        return CHECKER_PASS.format(order=target_order), metrics

    # Compute detailed orthogonality metrics
    if checks.get("is_square", False) and checks.get("entries_pm1", False):
        H_int = H.astype(np.int32)
        product = H_int @ H_int.T

        # Count perfect rows (all off-diagonal entries are 0 for this row)
        perfect_rows = 0
        for i in range(n):
            row_ok = True
            for j in range(n):
                if i != j and product[i, j] != 0:
                    row_ok = False
                    break
            if row_ok:
                perfect_rows += 1

        # Count zero vs nonzero off-diagonal pairs
        total_pairs = n * (n - 1) // 2
        nonzero_pairs = 0
        worst_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                dp = int(product[i, j])
                if dp != 0:
                    nonzero_pairs += 1
                    if len(worst_pairs) < 15 or abs(dp) > abs(worst_pairs[-1][2]):
                        worst_pairs.append((i, j, dp))
                        worst_pairs.sort(key=lambda x: abs(x[2]), reverse=True)
                        worst_pairs = worst_pairs[:15]

        zero_pairs = total_pairs - nonzero_pairs
        orth_pct = round(100.0 * zero_pairs / total_pairs, 2) if total_pairs > 0 else 0.0
        max_off = int(np.max(np.abs(product - np.diag(np.diag(product)))))

        # Quality score: weighted combination of order match + orthogonality
        order_score = min(n / target_order, 1.0) * 50  # 0-50 points for size
        orth_score = orth_pct / 100.0 * 50              # 0-50 points for orthogonality
        quality_score = round(order_score + orth_score, 2)

        metrics.update({
            "orthogonality_pct": orth_pct,
            "perfect_rows": perfect_rows,
            "max_off_diagonal": max_off,
            "nonzero_off_diag": nonzero_pairs,
            "quality_score": quality_score,
        })

        worst_str = "\n".join(
            f"  rows ({i}, {j}): dot_product = {dp}" for i, j, dp in worst_pairs
        )

        detail = CHECKER_DETAIL_ORTHOGONALITY.format(
            nonzero_count=nonzero_pairs,
            max_off=max_off,
            worst_pairs=worst_str,
        )

        # Build rich feedback
        feedback = (
            f"**Programmatic verification of {n}×{n} candidate** (from {source}):\n"
            f"- Valid Hadamard: **{result['valid']}**\n"
            f"- Entries all ±1: {checks.get('entries_pm1', '?')}\n"
            f"- Orthogonal row pairs: {zero_pairs}/{total_pairs} "
            f"(**{orth_pct}%** orthogonal)\n"
            f"- Perfect rows (fully orthogonal to all others): "
            f"**{perfect_rows}/{n}**\n"
            f"- Max off-diagonal |dot product|: **{max_off}** (target: 0)\n"
            f"- Quality score: **{quality_score}/100**\n"
            f"\n{detail}\n"
            f"\nUse this feedback to improve your construction."
        )
        return feedback, metrics

    else:
        # Non-square or bad entries — basic feedback
        metrics.update({
            "orthogonality_pct": 0.0,
            "perfect_rows": 0,
            "max_off_diagonal": None,
            "nonzero_off_diag": None,
            "quality_score": 0.0,
        })
        return CHECKER_FAIL.format(
            order=result["order"],
            target=target_order,
            valid=result["valid"],
            violations="; ".join(result["violations"]),
            detail_section="",
        ), metrics


def get_phase_nudge(turn: int, max_turns: int) -> str:
    """Return phase-appropriate nudge based on turn progress."""
    frac = turn / max_turns
    if frac < 0.15:
        return PHASE_NUDGE_EARLY
    elif frac < 0.5:
        return PHASE_NUDGE_MID
    elif frac < 0.9:
        return PHASE_NUDGE_LATE
    return ""


def trim_conversation(messages: list[dict], max_messages: int = 14) -> list[dict]:
    """Trim conversation keeping system + first user + last N turns."""
    if len(messages) <= max_messages:
        return messages
    kept = messages[:2]
    kept.extend(messages[-(max_messages - 2):])
    return kept


def rebuild_messages_from_conversation(
    conv_path: str, system_prompt: str, initial_prompt: str,
) -> tuple[list[dict], int, int, float]:
    """Rebuild messages from saved conversation for resume.

    Returns (messages, best_order, last_turn, best_quality).
    """
    with open(conv_path, encoding="utf-8") as f:
        data = json.load(f)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_prompt},
    ]

    best_order = data.get("best_order", 0)
    last_turn = 0

    for entry in data.get("full_conversation", []):
        messages.append({"role": "assistant", "content": entry["text"]})
        if entry.get("stdout"):
            feedback = f"Your code produced:\n```\n{entry['stdout'][-2000:]}\n```\nContinue."
        elif entry.get("event") == "no_code":
            feedback = "No code was found. Please write Python code in a ```python block."
        else:
            feedback = "Continue working on the construction."
        messages.append({"role": "user", "content": feedback})
        last_turn = entry["turn"]

    return messages, best_order, last_turn, 0.0


def run_agentic_loop(
    branch_name: str,
    model: str,
    initial_prompt: str,
    target_order: int = 668,
    max_turns: int = 50,
    max_tokens: int = 16384,
    exec_timeout: int = 300,
    log_path: str | None = None,
    mock: bool = False,
    mock_responses: list[str] | None = None,
    alternating_models: list[str] | None = None,
    resume_from: str | None = None,
    reasoning_efforts: dict[str, str] | None = None,
) -> dict:
    """Run the full agentic coding loop for one branch."""
    t0 = time.time()
    tag = f"[{branch_name}]"

    # Create a persistent shared temp dir for this branch
    shared_dir = tempfile.mkdtemp(prefix=f"hadamard_{branch_name}_")

    start_turn = 0
    best_quality = 0.0

    if resume_from:
        messages, best_order_resumed, last_turn, _ = rebuild_messages_from_conversation(
            resume_from, SYSTEM_PROMPT, initial_prompt
        )
        start_turn = last_turn
        best_order = best_order_resumed
        print(f"{tag} Resuming from turn {start_turn}, best_order={best_order}", flush=True)
    else:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": initial_prompt},
        ]
        best_order = 0

    best_violations = float("inf")
    best_matrix_csv = None
    solved = False
    stall_count = 0
    no_code_streak = 0
    turn_summaries = []
    full_conversation = []

    def _log(event, data):
        if log_path:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "branch": branch_name,
                "event": event,
                **data,
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    for turn in range(start_turn, max_turns):
        turn_t0 = time.time()
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        turns_remaining = max_turns - turn - 1
        is_last_turn = (turn == max_turns - 1)

        if alternating_models:
            current_model = alternating_models[turn % len(alternating_models)]
        else:
            current_model = model
        model_short = current_model.split("/")[-1][:20]

        print(f"{tag} [{ts}] Turn {turn + 1}/{max_turns} ({model_short}) "
              f"[best_q={best_quality}]", flush=True)

        if is_last_turn:
            messages.append({"role": "user", "content": REFLECTION_PROMPT})

        # --- Step 1: Call LLM ---
        if mock and mock_responses:
            response_text = mock_responses[min(turn, len(mock_responses) - 1)]
            time.sleep(0.05)
        else:
            effort = "high"
            if reasoning_efforts and current_model in reasoning_efforts:
                effort = reasoning_efforts[current_model]

            for attempt in range(2):
                try:
                    trimmed = trim_conversation(messages, max_messages=14)
                    resp = litellm.completion(
                        model=current_model,
                        messages=trimmed,
                        max_tokens=max_tokens,
                        timeout=540,
                        reasoning_effort=effort,
                    )
                    response_text = resp.choices[0].message.content
                    if response_text is None:
                        response_text = getattr(resp.choices[0].message, "reasoning_content", "") or ""
                    break
                except Exception as e:
                    if attempt == 0:
                        print(f"{tag} LLM error (attempt 1): {e}", flush=True)
                        _log("llm_error", {"turn": turn + 1, "error": str(e), "model": current_model})
                        time.sleep(5)
                    else:
                        print(f"{tag} LLM retry failed: {e}", flush=True)
                        _log("llm_retry_failed", {"turn": turn + 1, "error": str(e)})
                        response_text = None
            if response_text is None:
                break

        messages.append({"role": "assistant", "content": response_text})
        _log("llm_response", {
            "turn": turn + 1, "model": current_model,
            "length": len(response_text), "text": response_text,
        })

        if is_last_turn:
            full_conversation.append({
                "turn": turn + 1, "role": "assistant", "model": current_model,
                "text": response_text, "event": "reflection",
            })
            turn_summaries.append({
                "turn": turn + 1, "event": "reflection", "model": current_model,
                "elapsed": round(time.time() - turn_t0, 1),
            })
            break

        # --- Step 2: Extract and run code ---
        code_blocks = extract_code_blocks(response_text)

        if not code_blocks:
            no_code_streak += 1
            stall_count += 1
            if no_code_streak >= 3:
                feedback = (
                    f"**Turn {turn + 1}/{max_turns}** ({turns_remaining} remaining)\n\n"
                    f"You have not written Python code for {no_code_streak} consecutive turns. "
                    f"You MUST include executable Python code in a ```python block.\n\n"
                    + STALL_NUDGE
                )
            else:
                feedback = (
                    f"**Turn {turn + 1}/{max_turns}** ({turns_remaining} remaining)\n\n"
                    f"No Python code found. Please include executable code in a ```python block."
                )
            messages.append({"role": "user", "content": feedback})
            full_conversation.append({
                "turn": turn + 1, "role": "assistant", "model": current_model,
                "text": response_text, "event": "no_code",
            })
            turn_summaries.append({
                "turn": turn + 1, "event": "no_code", "model": current_model,
                "no_code_streak": no_code_streak,
                "elapsed": round(time.time() - turn_t0, 1),
            })
            continue

        no_code_streak = 0

        # Clean candidate.csv before each execution so we don't re-read stale files
        candidate_path = os.path.join(shared_dir, "candidate.csv")
        if os.path.exists(candidate_path):
            os.remove(candidate_path)

        # Execute each code block
        all_stdout = []
        all_stderr = []
        any_timeout = False
        any_success = False
        matrix_file = None

        for i, code in enumerate(code_blocks):
            if mock:
                exec_result = {
                    "success": True,
                    "stdout": f"Mock output block {i+1}, turn {turn + 1}",
                    "stderr": "", "returncode": 0, "timed_out": False,
                    "matrix_file": None,
                }
            else:
                exec_result = execute_code(
                    code, timeout=exec_timeout, shared_dir=shared_dir,
                )

            all_stdout.append(exec_result["stdout"])
            if exec_result["stderr"]:
                all_stderr.append(f"[block {i+1}] {exec_result['stderr']}")
            if exec_result["timed_out"]:
                any_timeout = True
            if exec_result["success"]:
                any_success = True
            if exec_result.get("matrix_file"):
                matrix_file = exec_result["matrix_file"]

        combined_stdout = "\n".join(s for s in all_stdout if s)
        combined_stderr = "\n".join(all_stderr)

        _log("code_exec", {
            "turn": turn + 1, "model": current_model,
            "num_blocks": len(code_blocks),
            "code": "\n\n# --- BLOCK SEPARATOR ---\n\n".join(code_blocks),
            "success": any_success, "timed_out": any_timeout,
            "stdout": combined_stdout[-4000:],
            "stderr": combined_stderr[-2000:],
            "matrix_file": matrix_file,
        })

        # --- Step 3: Check for matrix and build feedback ---
        error_section = ""
        if combined_stderr:
            error_section = f"**Errors/warnings:**\n```\n{combined_stderr[-3000:]}\n```"
        if any_timeout:
            error_section += f"\n**TIMEOUT:** Code exceeded {exec_timeout}s limit."

        # Try to find a matrix: prefer file, fall back to stdout
        H = None
        matrix_source = None

        if matrix_file and os.path.exists(matrix_file):
            H = load_matrix_from_file(matrix_file)
            if H is not None:
                matrix_source = "file"

        if H is None:
            H = parse_hadamard_csv(combined_stdout)
            if H is not None:
                matrix_source = "stdout"

        checker_feedback, metrics = build_checker_feedback(H, target_order, matrix_source or "none")

        if checker_feedback:
            q = metrics["quality_score"]
            if metrics["valid"]:
                solved = True
                best_order = metrics["order"]
                best_quality = 100.0
                best_violations = 0
                if H is not None:
                    best_matrix_csv = "\n".join(
                        ",".join(str(x) for x in row) for row in H.tolist()
                    )
                print(f"{tag} *** SOLVED! order={metrics['order']} ***", flush=True)
                _log("solved", {"turn": turn + 1, "order": metrics["order"]})

            elif q > best_quality:
                best_quality = q
                best_order = metrics["order"]
                best_violations = metrics.get("nonzero_off_diag", float("inf"))
                stall_count = 0
                print(f"{tag} New best: quality={q}/100 order={metrics['order']} "
                      f"orth={metrics['orthogonality_pct']}% "
                      f"perfect_rows={metrics['perfect_rows']}/{metrics['order']}",
                      flush=True)
            else:
                stall_count += 1
        else:
            stall_count = 0  # no matrix = still building, not stalling

        _log("checker", {
            "turn": turn + 1, "metrics": metrics,
        })

        phase_nudge = get_phase_nudge(turn, max_turns)
        if stall_count >= 4:
            phase_nudge += "\n\n" + STALL_NUDGE
            stall_count = 0

        feedback = FEEDBACK_TEMPLATE.format(
            turn=turn + 1,
            max_turns=max_turns,
            turns_remaining=turns_remaining,
            stdout=combined_stdout[-4000:],
            error_section=error_section,
            checker_section=checker_feedback or "",
            phase_nudge=phase_nudge,
        )

        messages.append({"role": "user", "content": feedback})

        full_conversation.append({
            "turn": turn + 1, "role": "assistant", "model": current_model,
            "text": response_text, "code": code_blocks,
            "stdout": combined_stdout[-4000:],
            "stderr": combined_stderr[-2000:],
            "metrics": metrics,
        })

        turn_summaries.append({
            "turn": turn + 1, "model": current_model,
            "code_success": any_success, "timed_out": any_timeout,
            "num_blocks": len(code_blocks),
            "quality_score": metrics["quality_score"],
            "orthogonality_pct": metrics.get("orthogonality_pct", 0),
            "best_quality": best_quality,
            "solved": solved,
            "elapsed": round(time.time() - turn_t0, 1),
        })

        if solved:
            break

    elapsed = round(time.time() - t0, 1)
    print(f"{tag} Done: {'SOLVED' if solved else 'UNSOLVED'} after {len(turn_summaries)} turns, "
          f"{elapsed}s, best_quality={best_quality}", flush=True)

    return {
        "branch": branch_name,
        "model": model,
        "alternating_models": alternating_models,
        "turns": len(turn_summaries),
        "solved": solved,
        "best_order": best_order,
        "best_quality": best_quality,
        "best_violations": best_violations if best_violations != float("inf") else None,
        "best_matrix_csv": best_matrix_csv,
        "elapsed_s": elapsed,
        "turn_summaries": turn_summaries,
        "full_conversation": full_conversation,
    }
