"""
Experiment 5: Polynomial perturbations of the warmup solution.

Idea: start from the known passing warmup F_0 = x_0^5 + x_1^5 + x_2^2 + x_3^2 in P(2,2,5,5)
(which gives exactly 7 singular points), and ask each model to propose K different MINIMAL
PERTURBATIONS of F_0 that either:
  (a) add an additional isolated A_n surface singularity at a non-strata point, OR
  (b) move to a slightly different ambient where one extra coord-point singularity appears.

Each model returns ~5 distinct perturbation candidates; verify all via M2; pick best.

Pipeline-wise: a SINGLE generation call returns multiple candidates (saves cost) but pipeline
needs to handle multi-candidate extraction. We'll do simple version: single trial per (model, seed)
but with a prompt that explicitly enumerates 5 candidates, each in its own '## Answer N' block.

Then in Python we parse each '## Answer N' block independently and verify all of them.
"""
from __future__ import annotations
import os, sys, json, re, time, threading, argparse, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

ROOT = Path("/Users/benjamingrayzel/sandbox/agentic-math-solver")
ITER_DIR = ROOT / "klt-del-pezzo-iteration"
sys.path.insert(0, str(ITER_DIR))

from klt_pipeline import (
    model_chat, log_jsonl, MODELS, GENERATOR_SYSTEM,
    extract_method_b, judge_extract, REVISION_PROMPT,
)
from klt_verifier import verify_method_b, feedback_for_revision

EXP_NAME = "klt_iter_exp5_warmup_perturbations"

PROMPT = """## Verified WARMUP baseline (giving exactly 7 singular points)

Weights: [2, 2, 5, 5]
F_0 = x_0^5 + x_1^5 + x_2^2 + x_3^2  (degree 10)

This is a quasi-smooth klt del Pezzo with rho=1 in characteristic 3, with 5 (mu_2) + 2 (mu_5) = 7 singular points.

## Goal: find a related construction that has at least 8 distinct singular points

Propose **{K} DIFFERENT candidate constructions**, each a small modification of F_0 OR a different
ambient with similar structure. Number them as "## Answer 1", "## Answer 2", ...

Each answer should be format:

## Answer N
Weights: [w_0, w_1, ...]
Equation: <polynomial in x0, x1, ...>
(or for CI:)
Weights: [...]
F1: <polynomial>
F2: <polynomial>

Encouraged variations:
- (a) Different ambient: add a 5th variable with weight w prime to 3, e.g. w=7 or w=11; use CI of 2.
- (b) Same ambient P(2,2,5,5) but different polynomial: more general F = a x_0^5 + b x_1^5 + c x_2^2 + d x_3^2 + e x_2 x_3 + f x_0^a x_1^b (some cross terms; check that no new POSITIVE-DIM singular locus appears).
- (c) Different weights altogether: e.g. P(1,2,2,5,5,11) CI of 3 (surface), or P(2,2,5,7) CI of 2.
- (d) Method C basket (HJ chains) only as a last resort; show the Picard arithmetic.

In char 3:
- weights divisible by 3 are forbidden (not tame).
- pure powers like x_i^k with k divisible by 3 have ZERO derivative — avoid.
- symmetric polynomial pairs like x^a + y^a vs x^b + y^b often have NO common zero on the singular stratum in F_3-bar — VERIFY transversality per candidate.

For each of your {K} candidates, ALSO list:
  - Expected count of singular points on each stratum.
  - The specific check that distinguishes it from F_0 (i.e., where the 8th singular point comes from).

CRITICAL: use plain ASCII variables x0, x1, ..., x_, no LaTeX, no subscript {{}}.
"""

ANSWER_BLOCK_NUM_RE = re.compile(r"##\s*Answer\s*(\d+)\b(.*?)(?=^\s*##\s*Answer\s*\d+|\Z)", re.DOTALL | re.M | re.I)


def extract_multi(text):
    """Extract multiple '## Answer N' blocks; return list of dicts."""
    candidates = []
    for m in ANSWER_BLOCK_NUM_RE.finditer(text):
        idx = int(m.group(1))
        body = "## Answer\n" + m.group(2)  # rewrap for the standard parser
        ext = extract_method_b(body)
        if ext:
            ext["_idx"] = idx
            candidates.append(ext)
    if not candidates:
        # Fall back to single extraction
        ext = extract_method_b(text)
        if ext:
            ext["_idx"] = 0
            candidates.append(ext)
    return candidates


def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_one_multi_trial(model_key, seed, K=5):
    """Run one multi-candidate trial. Generate, parse all candidates, verify each."""
    trial = {"model": model_key, "seed": seed, "K": K}
    user = PROMPT.format(K=K)
    t0 = time.time()
    try:
        content, reasoning_text, usage = model_chat(model_key, GENERATOR_SYSTEM, user)
    except Exception as e:
        trial["error"] = f"generation error: {e}"
        return trial
    trial["elapsed_gen_s"] = round(time.time() - t0, 1)
    trial["usage"] = usage
    trial["content"] = content
    trial["reasoning"] = reasoning_text

    # Multi-candidate extraction
    cands = extract_multi(content)
    if not cands:
        # Try judge fallback
        je = judge_extract(content)
        if je: cands = [{**je, "_idx": 0}]
    trial["n_candidates"] = len(cands)

    # Verify each candidate
    verifications = []
    best_score = 0
    best_ver = None
    for c in cands:
        t1 = time.time()
        v = verify_method_b(weights=c["weights"], eqns=c["eqns"], n_sing_required=8)
        v["m2_elapsed_s"] = round(time.time() - t1, 1)
        v["candidate"] = c
        verifications.append(v)
        if v["score"] > best_score:
            best_score = v["score"]
            best_ver = v

    trial["verifications"] = verifications
    trial["best_score"] = best_score
    trial["status"] = "PASS" if best_ver and best_ver["verdict"] == "PASS" else "FAIL"
    return trial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--K", type=int, default=5, help="Candidates per trial")
    ap.add_argument("--models", default="all")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    models = list(MODELS.keys()) if args.models == "all" else args.models.split(",")

    ts = _ts()
    out_dir = ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{EXP_NAME}_{ts}.json"
    log_path = ROOT / "logs" / f"{EXP_NAME}_{ts}.jsonl"
    log_lock = threading.Lock()

    print(f"Models: {models}, K={args.K}, seeds={args.seeds}")
    work = [(m, s) for m in models for s in range(42, 42 + args.seeds)]
    print(f"Total trials: {len(work)}")

    results = []
    t_start = time.time()

    def go(model_key, seed):
        tag = f"[{model_key}|seed={seed}]"
        print(f"{tag} START", flush=True)
        try:
            tr = run_one_multi_trial(model_key=model_key, seed=seed, K=args.K)
            print(f"{tag} status={tr.get('status','?')} best_score={tr.get('best_score','?')} n_cand={tr.get('n_candidates','?')}", flush=True)
            with log_lock: log_jsonl(tr, log_path)
            return tr
        except Exception as e:
            print(f"{tag} ERROR: {e}\n{traceback.format_exc()[:500]}", flush=True)
            err = {"model": model_key, "seed": seed, "error": str(e), "status": "ERROR"}
            with log_lock: log_jsonl(err, log_path)
            return err

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(go, *w): w for w in work}
        for fu in as_completed(futs):
            results.append(fu.result())

    elapsed = round(time.time() - t_start, 1)
    summary = {
        "experiment": EXP_NAME, "timestamp": ts, "elapsed_s": elapsed,
        "models": models, "K": args.K, "n_seeds": args.seeds,
        "n_pass": sum(1 for r in results if r.get("status") == "PASS"),
        "n_fail": sum(1 for r in results if r.get("status") == "FAIL"),
        "n_error": sum(1 for r in results if r.get("status") == "ERROR"),
        "results": results,
    }
    with open(out_path, "w") as f: json.dump(summary, f, indent=1, default=str)

    print("")
    print(f"PASS: {summary['n_pass']} / {len(work)}")
    for m in models:
        cell = [r for r in results if r.get("model")==m]
        best = max((r.get("best_score",0) for r in cell), default=0)
        print(f"  {m:18}: best_score={best}, n_trials={len(cell)}")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
