"""
Agentic math-solving pipeline: generator → verifier ↔ reviser loop → final judge.

Usage:
    uv run src/pipeline.py <problem_file>
    uv run src/pipeline.py --problem "Find all primes p such that..."
    uv run src/pipeline.py benchmarks/winning-gold/imo01.txt --mock
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure src/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def make_logger(log_path: str):
    """Return a logger function that appends JSON records to log_path."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    def log(call_type: str, iteration: int, model: str,
            system: str, prompt: str, response: str, elapsed_s: float):
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "call_type": call_type,
            "iteration": iteration,
            "model": model,
            "system": system,
            "prompt": prompt,
            "response": response,
            "elapsed_s": round(elapsed_s, 3),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    return log


# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------

MOCK_RESPONSES = {
    "generate": (
        "## Summary\n\n**Verdict:** Solved\n**Method sketch:** Mock solution using standard techniques.\n\n"
        "## Detailed Solution\n\nThis is a mock solution. All steps are trivially justified for testing purposes."
    ),
    "verify": (
        "## Verdict\nThe solution appears correct.\n\n## Findings\n1. None found.\n\n## Log\nChecked all steps.\n\n"
        "VERDICT: correct"
    ),
    "verify_issues": (
        "## Verdict\nIssues found.\n\n## Findings\n"
        "1. [Critical Error] Step 2: The jump from line 3 to line 4 is not justified.\n\n## Log\nFound one error.\n\n"
        "VERDICT: issues_found"
    ),
    "revise": (
        "## Summary\n\n**Verdict:** Solved\n**Method sketch:** Revised mock solution.\n"
        "**Changes from previous attempt:** Fixed the unjustified step.\n\n"
        "## Detailed Solution\n\nThis is a revised mock solution with the error corrected."
    ),
    "judge_with_gt": (
        "The solution is complete and correct.\n\n<points>7 out of 7</points>"
    ),
    "judge_no_gt": (
        "The solution is complete and rigorous.\n\nCLASSIFICATION: correct"
    ),
}


# ---------------------------------------------------------------------------
# Core atomic functions
# ---------------------------------------------------------------------------

def _call_llm(system: str, prompt: str, model: str, max_tokens: int) -> str:
    from utils import llm
    return llm(prompt, model=model, system=system, max_tokens=max_tokens)


def generate(
    problem: str,
    system: str,
    model: str,
    max_tokens: int,
    logger,
    iteration: int = 0,
    mock: bool = False,
) -> str:
    t0 = time.time()
    if mock:
        response = MOCK_RESPONSES["generate"]
        time.sleep(0.01)
    else:
        response = _call_llm(system, problem, model, max_tokens)
    logger("generate", iteration, model, system, problem, response, time.time() - t0)
    return response


def _split_prompt_template(template: str) -> tuple[str, str]:
    """Split a prompt template into (system_instructions, content_template).

    Templates share the convention that role/instructions come before the
    '**PROBLEM:**' section, which starts the per-call content.
    """
    sys_part, sep, content = template.partition("\n**PROBLEM:**\n")
    if not sep:
        return "", template  # no split marker — treat entire template as content
    return sys_part.strip(), "**PROBLEM:**\n" + content


def verify(
    problem: str,
    solution: str,
    system: str,
    model: str,
    max_tokens: int,
    logger,
    iteration: int = 0,
    mock: bool = False,
    mock_has_issues: bool = False,
) -> str:
    sys_instructions, content_template = _split_prompt_template(system)
    prompt = content_template.replace("{problem}", problem).replace("{solution}", solution)
    t0 = time.time()
    if mock:
        key = "verify_issues" if mock_has_issues else "verify"
        response = MOCK_RESPONSES[key]
        time.sleep(0.01)
    else:
        response = _call_llm(sys_instructions, prompt, model, max_tokens)
    logger("verify", iteration, model, sys_instructions, prompt, response, time.time() - t0)
    return response


def revise(
    problem: str,
    solution: str,
    critique: str,
    system: str,
    model: str,
    max_tokens: int,
    logger,
    iteration: int = 0,
    mock: bool = False,
) -> str:
    sys_instructions, content_template = _split_prompt_template(system)
    prompt = (
        content_template
        .replace("{problem}", problem)
        .replace("{solution}", solution)
        .replace("{critique}", critique)
    )
    t0 = time.time()
    if mock:
        response = MOCK_RESPONSES["revise"]
        time.sleep(0.01)
    else:
        response = _call_llm(sys_instructions, prompt, model, max_tokens)
    logger("revise", iteration, model, sys_instructions, prompt, response, time.time() - t0)
    return response


def judge(
    problem: str,
    candidate: str,
    ground_truth: str | None,
    system: str,
    model: str,
    max_tokens: int,
    logger,
    mock: bool = False,
) -> str:
    if ground_truth:
        gt_section = f"**GROUND TRUTH SOLUTION:**\n{ground_truth}"
        mock_key = "judge_with_gt"
    else:
        gt_section = ""
        mock_key = "judge_no_gt"

    sys_instructions, content_template = _split_prompt_template(system)
    prompt = (
        content_template
        .replace("{problem}", problem)
        .replace("{ground_truth_section}", gt_section)
        .replace("{candidate}", candidate)
    )
    t0 = time.time()
    if mock:
        response = MOCK_RESPONSES[mock_key]
        time.sleep(0.01)
    else:
        response = _call_llm(sys_instructions, prompt, model, max_tokens)
    logger("judge", 0, model, sys_instructions, prompt, response, time.time() - t0)
    return response


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    problem: str,
    generator_prompt: str,
    verifier_prompt: str,
    reviser_prompt: str,
    judge_prompt: str,
    model: str,
    iterations: int,
    max_tokens: int,
    log_path: str,
    ground_truth: str | None = None,
    run_judge: bool = True,
    mock: bool = False,
) -> dict:
    logger = make_logger(log_path)

    solution = generate(
        problem, generator_prompt, model, max_tokens, logger, iteration=0, mock=mock
    )

    loop_log = []
    stopped_early = False

    for i in range(iterations):
        # In mock mode, first iteration has issues, subsequent are correct
        mock_has_issues = mock and i == 0
        critique = verify(
            problem, solution, verifier_prompt, model, max_tokens, logger,
            iteration=i + 1, mock=mock, mock_has_issues=mock_has_issues,
        )

        if "VERDICT: correct" in critique:
            stopped_early = True
            loop_log.append({
                "iteration": i + 1,
                "solution": solution,
                "critique": critique,
                "stopped_early": True,
            })
            break

        new_solution = revise(
            problem, solution, critique, reviser_prompt, model, max_tokens, logger,
            iteration=i + 1, mock=mock,
        )
        loop_log.append({
            "iteration": i + 1,
            "solution": solution,
            "critique": critique,
            "revised_solution": new_solution,
            "stopped_early": False,
        })
        solution = new_solution

    result: dict = {
        "problem": problem,
        "model": model,
        "iterations_run": len(loop_log),
        "stopped_early": stopped_early,
        "loop_log": loop_log,
        "final_solution": solution,
        "log_path": log_path,
    }

    if run_judge and (ground_truth or not False):
        verdict = judge(
            problem, solution, ground_truth, judge_prompt, model, max_tokens, logger,
            mock=mock,
        )
        result["judge_verdict"] = verdict

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def build_log_path(log_dir: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return str(Path(log_dir) / f"pipeline_{ts}.jsonl")


def main():
    parser = argparse.ArgumentParser(
        description="Agentic math-solving pipeline: generator → verifier ↔ reviser → judge"
    )

    # Problem input (positional file or --problem string)
    parser.add_argument("problem_file", nargs="?", help="Path to a file containing the problem statement")
    parser.add_argument("--problem", help="Problem statement as a string (alternative to problem_file)")

    # Model / generation
    parser.add_argument("-m", "--model",
                        default=os.environ.get("PIPELINE_MODEL", "openrouter/google/gemini-3.1-flash-lite-preview"),
                        help="LiteLLM model string [env: PIPELINE_MODEL]")
    parser.add_argument("-n", "--iterations", type=int,
                        default=int(os.environ.get("PIPELINE_ITERATIONS", "3")),
                        help="Max verify/revise iterations [env: PIPELINE_ITERATIONS]")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="Max tokens per LLM call")

    # Prompt files
    script_dir = Path(__file__).parent.parent
    parser.add_argument("--generator-prompt",
                        default=str(script_dir / "prompts/pipeline/generator.md"))
    parser.add_argument("--verifier-prompt",
                        default=str(script_dir / "prompts/pipeline/verifier.md"))
    parser.add_argument("--reviser-prompt",
                        default=str(script_dir / "prompts/pipeline/reviser.md"))
    parser.add_argument("--judge-prompt",
                        default=str(script_dir / "prompts/pipeline/judge.md"))

    # Judge options
    parser.add_argument("--ground-truth", metavar="FILE",
                        help="Path to ground-truth solution file for the final judge")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip the final judge step")

    # Output / logging
    parser.add_argument("--log-dir", default="logs/", help="Directory for JSONL logs")
    parser.add_argument("-o", "--output", help="Write result JSON to this file (default: stdout)")

    # Mock mode
    parser.add_argument("--mock", action="store_true",
                        help="Use canned responses (no API calls)")

    args = parser.parse_args()

    # Resolve problem text
    if args.problem_file:
        problem = load_file(args.problem_file)
    elif args.problem:
        problem = args.problem
    else:
        parser.error("Provide a problem file (positional) or --problem '...'")

    # Load prompts
    generator_prompt = load_file(args.generator_prompt)
    verifier_prompt = load_file(args.verifier_prompt)
    reviser_prompt = load_file(args.reviser_prompt)
    judge_prompt = load_file(args.judge_prompt)

    # Ground truth
    ground_truth = load_file(args.ground_truth) if args.ground_truth else None

    # Log path
    log_path = build_log_path(args.log_dir)

    result = run_pipeline(
        problem=problem,
        generator_prompt=generator_prompt,
        verifier_prompt=verifier_prompt,
        reviser_prompt=reviser_prompt,
        judge_prompt=judge_prompt,
        model=args.model,
        iterations=args.iterations,
        max_tokens=args.max_tokens,
        log_path=log_path,
        ground_truth=ground_truth,
        run_judge=not args.no_judge,
        mock=args.mock,
    )

    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"Result written to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    print(f"Log: {log_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
