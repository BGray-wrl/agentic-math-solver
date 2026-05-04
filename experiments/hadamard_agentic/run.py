#!/usr/bin/env python3
"""
Hadamard Agentic Attack v2 — Orchestrator

Two branches, each alternating opus↔gemini every turn.
50 turns per branch with forced reflection at end.
Full conversation logging for post-mortem and pickup.
Per-model reasoning effort (medium for Opus, high for Gemini).

Usage:
    uv run experiments/hadamard_agentic/run.py --mock    # smoke test
    uv run experiments/hadamard_agentic/run.py           # real run
    uv run experiments/hadamard_agentic/run.py --branch 0  # single branch
    uv run experiments/hadamard_agentic/run.py --resume experiments/hadamard_agentic/results/conversation_williamson-search_20260405_214710.json
    uv run experiments/hadamard_agentic/run.py --api-key-2  # use OPENROUTER_API_KEY_2
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import litellm

from branch_config import BRANCHES, TARGET_ORDER, EXEC_TIMEOUT, LITELLM_TIMEOUT, OPUS, GEMINI
from agentic_loop import run_agentic_loop
from mock_responses import MOCK_RESPONSES

# Per-model reasoning effort: medium for Opus (to keep it coding), high for Gemini
REASONING_EFFORTS = {
    OPUS: "medium",
    GEMINI: "high",
}


def _now():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main():
    parser = argparse.ArgumentParser(description="Hadamard Agentic Attack v2")
    parser.add_argument("--mock", action="store_true", help="Mock mode (no API calls)")
    parser.add_argument("--branch", type=int, default=None, help="Run single branch by index")
    parser.add_argument("--max-turns", type=int, default=None, help="Override max turns")
    parser.add_argument("--order", type=int, default=TARGET_ORDER, help="Target Hadamard order")
    parser.add_argument("--resume", nargs="+", default=None,
                        help="Resume from conversation JSON file(s). One per branch, matched by name.")
    parser.add_argument("--api-key-2", action="store_true",
                        help="Use OPENROUTER_API_KEY_2 instead of default")
    args = parser.parse_args()

    # API key selection
    if args.api_key_2:
        key2 = os.getenv("OPENROUTER_API_KEY_2")
        if key2:
            os.environ["OPENROUTER_API_KEY"] = key2
            print("Using OPENROUTER_API_KEY_2")
        else:
            print("WARNING: OPENROUTER_API_KEY_2 not found, using default")

    litellm.request_timeout = LITELLM_TIMEOUT

    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = str(log_dir / f"hadamard_agentic_{_now()}.jsonl")

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    if args.branch is not None:
        branch_ids = [args.branch]
    else:
        branch_ids = sorted(BRANCHES.keys())

    branches_to_run = {bid: BRANCHES[bid] for bid in branch_ids}

    # Match resume files to branches by name
    resume_map = {}
    if args.resume:
        for path in args.resume:
            with open(path) as f:
                data = json.load(f)
            branch_name = data.get("branch", "")
            resume_map[branch_name] = path
            print(f"Resume: {branch_name} from {path} (turn {data.get('turns', '?')})")

    print(f"\n=== Hadamard Agentic Attack v2 ===")
    print(f"Target order: {args.order}")
    print(f"Branches: {len(branches_to_run)}")
    for bid, cfg in branches_to_run.items():
        max_t = args.max_turns or cfg["max_turns"]
        if cfg.get("alternating"):
            model_desc = " ↔ ".join(m.split("/")[-1] for m in cfg["models"])
        else:
            model_desc = cfg.get("model", "unknown").split("/")[-1]
        resume_tag = ""
        if cfg["name"] in resume_map:
            resume_tag = " [RESUMING]"
        print(f"  [{bid}] {cfg['name']} — {model_desc} — {max_t} turns{resume_tag}")
    print(f"Exec timeout: {EXEC_TIMEOUT}s")
    print(f"Reasoning effort: Opus=medium, Gemini=high")
    if args.mock:
        print("[MOCK MODE]")
    print(f"Log: {log_path}")
    print()

    all_results = {}

    def run_branch(bid, cfg):
        max_t = args.max_turns or cfg["max_turns"]
        resume_path = resume_map.get(cfg["name"])
        return run_agentic_loop(
            branch_name=cfg["name"],
            model=cfg.get("models", ["unknown"])[0],
            initial_prompt=cfg["initial_prompt"],
            target_order=args.order,
            max_turns=max_t,
            max_tokens=cfg["max_tokens"],
            exec_timeout=EXEC_TIMEOUT,
            log_path=log_path,
            mock=args.mock,
            mock_responses=MOCK_RESPONSES if args.mock else None,
            alternating_models=cfg.get("models") if cfg.get("alternating") else None,
            resume_from=resume_path,
            reasoning_efforts=REASONING_EFFORTS,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(branches_to_run)) as ex:
        futs = {
            ex.submit(run_branch, bid, cfg): (bid, cfg)
            for bid, cfg in branches_to_run.items()
        }

        for fut in concurrent.futures.as_completed(futs):
            bid, cfg = futs[fut]
            try:
                result = fut.result(timeout=7200)
                all_results[bid] = result
                if result["solved"]:
                    print(f"\n*** BRANCH {cfg['name']} SOLVED IT! ***\n", flush=True)
                    for other_fut in futs:
                        if other_fut != fut and not other_fut.done():
                            other_fut.cancel()
            except Exception as e:
                print(f"Branch {cfg['name']} failed: {e}", flush=True)
                all_results[bid] = {
                    "branch": cfg["name"],
                    "model": str(cfg.get("models", "?")),
                    "error": str(e),
                    "solved": False,
                }

    # Summary
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")

    any_solved = False
    for bid in sorted(all_results.keys()):
        r = all_results[bid]
        name = r.get("branch", f"branch-{bid}")
        if r.get("error"):
            print(f"  {name}: ERROR — {r['error']}")
        else:
            status = "SOLVED" if r["solved"] else "unsolved"
            print(f"  {name}: {status} | turns={r['turns']} | best_order={r['best_order']} | "
                  f"violations={r.get('best_violations', '?')} | {r['elapsed_s']}s")
            if r["solved"]:
                any_solved = True

    # Save results
    ts = _now()
    suffix = "_mock" if args.mock else ""

    for bid, r in all_results.items():
        if not r.get("error"):
            conv_path = results_dir / f"conversation_{r['branch']}_{ts}.json"
            with open(conv_path, "w", encoding="utf-8") as f:
                json.dump({
                    "branch": r["branch"],
                    "turns": r["turns"],
                    "solved": r["solved"],
                    "best_order": r["best_order"],
                    "full_conversation": r.get("full_conversation", []),
                }, f, indent=2, ensure_ascii=False, default=str)
            print(f"  Conversation saved: {conv_path}")

    output = {
        "experiment": "hadamard_agentic_v2",
        "target_order": args.order,
        "date": datetime.now(timezone.utc).isoformat(),
        "mock": args.mock,
        "solved": any_solved,
        "exec_timeout": EXEC_TIMEOUT,
        "reasoning_efforts": REASONING_EFFORTS,
        "resumed_from": resume_map or None,
        "branches": {},
    }

    for bid, r in all_results.items():
        branch_summary = {k: v for k, v in r.items()
                         if k not in ("full_conversation", "best_matrix_csv")}

        if r.get("best_matrix_csv"):
            csv_path = results_dir / f"hadamard_{args.order}_{r['branch']}_{ts}.csv"
            with open(csv_path, "w") as f:
                f.write(r["best_matrix_csv"])
            branch_summary["matrix_csv_path"] = str(csv_path)
            print(f"\n  Matrix saved to: {csv_path}")

        output["branches"][str(bid)] = branch_summary

    out_path = results_dir / f"hadamard_agentic_v2_{ts}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nResults: {out_path}")
    print(f"Log:     {log_path}")

    if any_solved:
        print(f"\n*** A Hadamard matrix of order {args.order} was found! ***")

    return 0 if any_solved else 1


if __name__ == "__main__":
    sys.exit(main())
