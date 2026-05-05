#!/usr/bin/env python3
"""
gpt-5.4-nano on the same 12 PIDs at reasoning.effort=high (vs xhigh from
the prior gpt5_xhigh_compare run). Goal: see whether dropping from xhigh to
high meaningfully changes accuracy or cost.

Reuses helpers from gpt5_xhigh_compare_20260504.py via importlib.
"""
import sys, os, json, time, importlib.util
from pathlib import Path

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location(
    "xhigh_compare", str(ROOT / "gpt5_xhigh_compare_20260504.py"),
)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)  # type: ignore

# Override the effort on the imported module before any calls.
m.REASONING_EFFORT = "high"
EXPERIMENT_NAME = "nano_high_compare_20260505"
m.EXPERIMENT_NAME = EXPERIMENT_NAME

def main():
    problems = m.load_problems()
    prompts = {
        "generator": m.load_prompt("generator.md"),
        "judge":     m.load_prompt("answerbench_judge.md"),
    }
    out_path_partial = ROOT / "results" / f"{EXPERIMENT_NAME}_partial.json"
    print(f"Effort: {m.REASONING_EFFORT}  Partial: {out_path_partial}")

    st = m.poll_key_usage(force=True)
    if st["usage_usd"] is not None:
        print(f"Pre-run usage: ${st['usage_usd']:.4f}")

    NANO = "openrouter/openai/gpt-5.4-nano"
    trials = [(NANO, pid) for pid in m.ALL_12_PIDS]
    all_results = []
    t0 = time.time()
    m.run_wave("high (nano only)", trials, problems, prompts, False, all_results, out_path_partial)
    print(f"\nWall-clock: {round(time.time()-t0,1)}s")
    m.report(all_results, problems, False, suffix="_high")

if __name__ == "__main__":
    main()
