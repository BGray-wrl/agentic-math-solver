#!/usr/bin/env python3
"""
Wave 2 only: run gpt-5.4 (full) at xhigh on the 6 PIDs it got wrong at default
effort. Wave 1 was killed because of a stuck nano trial; load the partial and
merge wave 2 results into a final JSON.
"""
import sys, os, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
# Import the shared module's run_wave + helpers.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "xhigh_compare",
    str(Path(__file__).parent / "gpt5_xhigh_compare_20260504.py"),
)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)  # type: ignore

PARTIAL = Path(__file__).parent / "results" / "gpt5_xhigh_compare_20260504_20260505_031208_partial.json"

def main():
    with open(PARTIAL) as f:
        partial = json.load(f)
    all_results = list(partial["results"])
    print(f"Loaded {len(all_results)} results from partial.")

    problems = m.load_problems()
    prompts = {
        "generator": m.load_prompt("generator.md"),
        "judge":     m.load_prompt("answerbench_judge.md"),
    }

    # Wave 2: gpt-5.4 on its 6 failed PIDs
    wave2 = [(f"openrouter/openai/gpt-5.4", pid) for pid in m.GPT54_FAILED_PIDS]
    out_path_partial = Path(__file__).parent / "results" / f"gpt5_xhigh_wave2_20260505_partial.json"
    print(f"Partial saves: {out_path_partial}")

    st = m.poll_key_usage(force=True)
    if st["usage_usd"] is not None:
        print(f"Pre-wave usage: ${st['usage_usd']:.4f}")

    t0 = time.time()
    m.run_wave("2 (gpt-5.4)", wave2, problems, prompts, False, all_results, out_path_partial)
    print(f"Wall-clock: {round(time.time()-t0,1)}s")
    m.report(all_results, problems, False, suffix="_wave2_merged")

if __name__ == "__main__":
    main()
