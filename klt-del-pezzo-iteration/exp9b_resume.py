"""
Experiment 9b: resume the 19 trials that exp9 didn't complete.

Differences from exp9:
1. Wall-clock guard on every model_chat call (default 3600s = 60 min). Prevents the
   "slow-stream HTTP response → indefinite hang" failure mode that stalled exp9.
2. Incremental JSON writes (atomic temp+rename) after EACH trial completes, so the
   results artifact is always current even if the process is killed mid-run.
3. Stagnation watchdog: if the results JSON file hasn't been updated in
   --stagnation-s seconds (default 5400s = 90 min), the process aborts via os._exit.
   This is the automated equivalent of "check back in 2 hours and kill manually if
   no progress."
4. Higher parallelism (12 workers).
5. Hardcoded list of (model, framework, seed) tuples — only the missing trials.

Frameworks are re-imported from exp9 so prompts stay identical.
"""
from __future__ import annotations
import os, sys, json, time, threading, argparse, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from datetime import datetime, timezone

ROOT = Path("/Users/benjamingrayzel/sandbox/agentic-math-solver")
ITER_DIR = ROOT / "klt-del-pezzo-iteration"
sys.path.insert(0, str(ITER_DIR))
sys.path.insert(0, str(ROOT / "experiments"))

from exp9_frontier_diverse_deep import FRAMEWORKS, make_user_prompt
import klt_pipeline
from klt_pipeline import (
    MODELS, log_jsonl, extract_with_fallback,
    PROBLEM_PROMPT, GENERATOR_SYSTEM, REVISION_PROMPT,
)
from frontier_adapter import verify_method_b, feedback_for_revision

EXP_NAME = "klt_iter_exp9b_resume"

# 7 missing deepseek + 12 missing gemma = 19 trials.
MISSING_TRIALS = [
    # deepseek (7)
    ("deepseek-v4-flash", 0, 43),  # framework index, seed
    ("deepseek-v4-flash", 1, 44),
    ("deepseek-v4-flash", 2, 42),
    ("deepseek-v4-flash", 2, 44),
    ("deepseek-v4-flash", 3, 42),
    ("deepseek-v4-flash", 3, 43),
    ("deepseek-v4-flash", 3, 44),
    # gemma (12)
    ("gemma-max", 0, 42), ("gemma-max", 0, 43), ("gemma-max", 0, 44),
    ("gemma-max", 1, 42), ("gemma-max", 1, 43), ("gemma-max", 1, 44),
    ("gemma-max", 2, 42), ("gemma-max", 2, 43), ("gemma-max", 2, 44),
    ("gemma-max", 3, 42), ("gemma-max", 3, 43), ("gemma-max", 3, 44),
]


def model_chat_safe(model_key, system, user, max_tokens=None, wallclock=900):
    """Wall-clock-protected wrapper around klt_pipeline.model_chat.

    Submits the chat into a tiny dedicated ThreadPoolExecutor and bounds the wait
    via Future.result(timeout=...). On timeout we raise; the underlying thread
    leaks but the parent run_one_trial loop bails the trial cleanly.
    """
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat") as ex:
        fut = ex.submit(klt_pipeline.model_chat, model_key, system, user, max_tokens)
        try:
            return fut.result(timeout=wallclock)
        except FuturesTimeout:
            raise RuntimeError(f"model_chat exceeded wallclock {wallclock}s for {model_key}")


def run_one_trial_safe(model_key, n_sing_required, seed=42, extra_user_prompt="", revisions=8, wallclock=900):
    """Same structure as klt_pipeline.run_one_trial, but uses model_chat_safe."""
    trial_log = {"model": model_key, "seed": seed, "n_sing_required": n_sing_required, "rounds": []}
    user_prompt = PROBLEM_PROMPT.format(N_sing=n_sing_required)
    if extra_user_prompt:
        user_prompt = extra_user_prompt + "\n\n" + user_prompt
    cur_user = user_prompt
    last_extracted = None

    for round_idx in range(1 + revisions):
        round_log = {"round": round_idx}
        t0 = time.time()
        try:
            content, reasoning_text, usage = model_chat_safe(
                model_key, GENERATOR_SYSTEM, cur_user, wallclock=wallclock,
            )
        except Exception as e:
            round_log["error"] = f"generation error: {e}"
            round_log["elapsed_s"] = round(time.time() - t0, 1)
            trial_log["rounds"].append(round_log)
            break
        round_log["elapsed_s"] = round(time.time() - t0, 1)
        round_log["usage"] = usage
        round_log["content"] = content
        round_log["reasoning"] = reasoning_text

        extracted, extract_method = extract_with_fallback(content)
        round_log["extracted"] = extracted
        round_log["extract_method"] = extract_method
        if not extracted:
            round_log["error"] = "Failed to extract Method B answer (both regex and judge)"
            trial_log["rounds"].append(round_log)
            break

        t1 = time.time()
        try:
            v = verify_method_b(weights=extracted["weights"], eqns=extracted["eqns"], n_sing_required=n_sing_required)
        except Exception as e:
            round_log["error"] = f"verifier error: {e}"
            trial_log["rounds"].append(round_log)
            break
        v["m2_elapsed_s"] = round(time.time() - t1, 1)
        round_log["verification"] = v
        last_extracted = extracted
        trial_log["rounds"].append(round_log)

        if v["verdict"] == "PASS":
            trial_log["status"] = "PASS"
            break

        if round_idx < revisions and v["score"] >= 2:
            feedback = feedback_for_revision(v)
            cur_user = user_prompt + "\n\n" + REVISION_PROMPT.format(
                verifier_feedback=feedback,
                weights=extracted["weights"],
                eqns=extracted["eqns"],
            )
        else:
            break

    if "status" not in trial_log:
        trial_log["status"] = "FAIL"
    best_score = max((r.get("verification", {}).get("score", 0) for r in trial_log["rounds"]), default=0)
    trial_log["best_score"] = best_score
    return trial_log


def _atomic_write_json(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, default=str)
    os.replace(tmp, path)


def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _start_stagnation_watchdog(path: Path, stagnation_s: int, t_start: float):
    """Background thread: if `path` mtime hasn't advanced in stagnation_s seconds AND
    at least stagnation_s seconds have elapsed since t_start, abort via os._exit(2)."""
    def run():
        while True:
            time.sleep(60)
            now = time.time()
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                mtime = t_start
            since_mtime = now - mtime
            since_start = now - t_start
            if since_mtime > stagnation_s and since_start > stagnation_s:
                print(f"\n[watchdog] No JSON update in {since_mtime:.0f}s (> {stagnation_s}s). Aborting.", flush=True)
                os._exit(2)
    t = threading.Thread(target=run, daemon=True, name="stagnation-watchdog")
    t.start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--revisions", type=int, default=8)
    ap.add_argument("--wallclock", type=int, default=3600,
                    help="per-call wall-clock timeout in seconds (default 3600 = 60 min)")
    ap.add_argument("--stagnation-s", type=int, default=5400,
                    help="abort if no JSON update for this many seconds (default 5400 = 90 min)")
    args = ap.parse_args()

    ts = _ts()
    out_dir = ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{EXP_NAME}_{ts}.json"
    log_path = ROOT / "logs" / f"{EXP_NAME}_{ts}.jsonl"
    log_lock = threading.Lock()
    state_lock = threading.Lock()

    print(f"Total trials to resume: {len(MISSING_TRIALS)} ({args.revisions} revisions each, "
          f"{args.workers} workers, wallclock={args.wallclock}s)")
    print(f"Output JSON:  {out_path}")
    print(f"Logs:         {log_path}")
    results = []
    t_start = time.time()

    summary_skeleton = {
        "experiment": EXP_NAME, "timestamp": ts, "elapsed_s": None,
        "frameworks": [f["name"] for f in FRAMEWORKS],
        "revisions": args.revisions, "wallclock_s": args.wallclock,
        "workers": args.workers,
        "n_pass": 0, "n_fail": 0, "n_error": 0,
        "results": results,
    }
    # Write empty skeleton up front so the file always exists.
    _atomic_write_json(out_path, summary_skeleton)
    _start_stagnation_watchdog(out_path, args.stagnation_s, t_start)

    def go(model_key, fw_idx, seed):
        framework = FRAMEWORKS[fw_idx]
        tag = f"[{model_key}|{framework['name'][:30]}|seed={seed}]"
        print(f"{tag} START", flush=True)
        try:
            tr = run_one_trial_safe(
                model_key=model_key, n_sing_required=8, seed=seed,
                extra_user_prompt=make_user_prompt(framework, 8),
                revisions=args.revisions, wallclock=args.wallclock,
            )
            tr["seed"] = seed; tr["model"] = model_key; tr["framework"] = framework["name"]
            print(f"{tag} status={tr['status']} best_score={tr['best_score']} rounds={len(tr.get('rounds',[]))}", flush=True)
            with log_lock: log_jsonl(tr, log_path)
            return tr
        except Exception as e:
            print(f"{tag} ERROR: {e}", flush=True)
            err = {"model": model_key, "framework": framework["name"], "seed": seed, "error": str(e), "status": "ERROR"}
            with log_lock: log_jsonl(err, log_path)
            return err

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(go, *w): w for w in MISSING_TRIALS}
        for fu in as_completed(futs):
            r = fu.result()
            with state_lock:
                results.append(r)
                summary_skeleton["n_pass"] = sum(1 for x in results if x.get("status") == "PASS")
                summary_skeleton["n_fail"] = sum(1 for x in results if x.get("status") == "FAIL")
                summary_skeleton["n_error"] = sum(1 for x in results if x.get("status") == "ERROR")
                summary_skeleton["elapsed_s"] = round(time.time() - t_start, 1)
                _atomic_write_json(out_path, summary_skeleton)

    summary_skeleton["elapsed_s"] = round(time.time() - t_start, 1)
    _atomic_write_json(out_path, summary_skeleton)
    print(f"\nPASS: {summary_skeleton['n_pass']} / {len(MISSING_TRIALS)}")
    print(f"elapsed: {summary_skeleton['elapsed_s']}s")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
