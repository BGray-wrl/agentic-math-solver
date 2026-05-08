#!/usr/bin/env python3
"""
Final report aggregating all results:
  - Phase 1 pass@5 (gpt-oss + deepseek-v4-flash)
  - 3-judge consensus (gpt-oss xhigh + gemini-3.1-pro + deepseek)
  - Local verifiers (the only ground-truth signal we have)
  - Gemma seed_full + roleswap (if results available)

Outputs a markdown summary highlighting:
  - LOCALLY VERIFIED solutions (real wins)
  - 3/3 consensus correct (likely real, but unverified)
  - Per-problem signal strength
"""
from __future__ import annotations
import argparse, json, sys, re, importlib.util
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))


def load_phase1(log_path):
    rows = []
    with open(log_path) as f:
        for ln in f:
            r = json.loads(ln)
            if r.get("kind") == "trial":
                rows.append(r)
    return rows


def load_consensus(json_path):
    if not Path(json_path).exists(): return []
    with open(json_path) as f:
        d = json.load(f)
    return d.get("results", [])


def load_local_verify(phase1_log):
    """Run local verifiers, return {(pid,ptype,model_short,seed): (verified, msg)}."""
    spec = importlib.util.spec_from_file_location("ov", str(Path(__file__).parent / "openproblems_local_verify_20260507.py"))
    ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)  # type: ignore

    rows = load_phase1(phase1_log)
    out = {}
    for r in rows:
        key = (r["problem_id"], r["prompt_type"], r["model"].split("/")[-1], r["seed"])
        verifier = ov.VERIFIERS.get((r["problem_id"], r["prompt_type"]))
        if not verifier:
            out[key] = (None, "no local verifier")
            continue
        text = r.get("gen_text") or ""
        try:
            ok, msg = verifier(text)
        except Exception as e:
            ok, msg = False, f"verifier crash: {e}"
        out[key] = (ok, msg)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase1", default=str(ROOT / "logs" / "openproblems_pass5_20260507_20260507_183859.jsonl"))
    ap.add_argument("--consensus", default="")
    ap.add_argument("--seed-full-glob", default=str(ROOT / "experiments" / "results" / "openproblems_seed_full_*.json"))
    args = ap.parse_args()

    rows = load_phase1(args.phase1)
    print(f"# Phase 1 trials: {len(rows)}")

    # Find latest consensus json
    if not args.consensus:
        cs = sorted((Path(args.phase1).parent.parent / "experiments" / "results").glob("openproblems_consensus_judge_*.json"))
        if cs: args.consensus = str(cs[-1])

    cons = load_consensus(args.consensus) if args.consensus else []
    cons_lookup = {(c["problem_id"], c["prompt_type"], c["model"].split("/")[-1], c["seed"]): c
                   for c in cons}
    print(f"# Consensus entries: {len(cons)}")

    verify = load_local_verify(args.phase1)
    n_verified = sum(1 for k,(v,_) in verify.items() if v is True)
    n_unverif = sum(1 for k,(v,_) in verify.items() if v is False)
    n_no_check = sum(1 for k,(v,_) in verify.items() if v is None)
    print(f"# Local verifier: {n_verified} verified, {n_unverif} failed, {n_no_check} no-checker")

    # Build comprehensive per-problem table
    by_prob = defaultdict(list)
    for r in rows:
        k = (r["problem_id"], r["prompt_type"])
        by_prob[k].append(r)

    rank = {"incorrect":0, "partial":1, "almost":2, "correct":3, None:-1}

    # Gather seed_full / roleswap results
    sf_results = []
    for p in Path(args.phase1).parent.parent.glob("experiments/results/openproblems_seed_full_*.json"):
        try:
            with open(p) as f:
                d = json.load(f)
            for r in d.get("results", []):
                sf_results.append((d.get("condition","?"), r))
        except: pass
    print(f"# seed_full / roleswap trials: {len(sf_results)}")

    print()
    print("=" * 80)
    print("REAL WINS (locally verified)")
    print("=" * 80)
    real_wins = []
    for r in rows:
        key = (r["problem_id"], r["prompt_type"], r["model"].split("/")[-1], r["seed"])
        v = verify.get(key)
        if v and v[0] is True:
            real_wins.append((r, v[1]))
    if not real_wins:
        print("(none)")
    else:
        for r, msg in sorted(real_wins, key=lambda x: (x[0]["problem_id"], x[0]["prompt_type"], x[0]["seed"])):
            print(f"  ✓ {r['problem_id']:<26} {r['prompt_type']:<14} {r['model'].split('/')[-1]:<22} seed={r['seed']}  judge={r['label']}  | {msg}")

    print()
    print("=" * 80)
    print("3/3 CONSENSUS CORRECT (no local check available — possibly hallucinated)")
    print("=" * 80)
    cons_correct = [c for c in cons if c.get("consensus") == "correct" and c.get("n_agree") == 3]
    cons_correct_no_local = []
    for c in cons_correct:
        key = (c["problem_id"], c["prompt_type"], c["model"].split("/")[-1], c["seed"])
        if verify.get(key, (None,))[0] is None:
            cons_correct_no_local.append(c)
    if not cons_correct_no_local:
        print("(none)")
    else:
        for c in sorted(cons_correct_no_local, key=lambda x: (x["problem_id"], x["prompt_type"])):
            print(f"  ⚠ {c['problem_id']:<26} {c['prompt_type']:<14} {c['model'].split('/')[-1]:<22} seed={c['seed']}  → 3/3 unanimous correct (UNVERIFIED)")

    print()
    print("=" * 80)
    print("PER-PROBLEM SUMMARY")
    print("=" * 80)
    print(f"  {'Problem':<26} {'Type':<14} {'Trials':<8} {'Best judge':<10} {'Pos seeds':<10} {'Consensus 3/3':<14} {'Verified':<10}")
    for k in sorted(by_prob):
        trials = by_prob[k]
        best = max(trials, key=lambda r: rank.get(r.get("label"), -1))
        pos_count = sum(1 for r in trials if rank.get(r.get("label"), -1) >= 1)
        # consensus 3/3 correct count
        cs_count = sum(1 for c in cons if c["problem_id"] == k[0] and c["prompt_type"] == k[1]
                       and c.get("consensus") == "correct" and c.get("n_agree") == 3)
        # verified count
        ver_count = sum(1 for r in trials
                        if verify.get((r["problem_id"], r["prompt_type"], r["model"].split("/")[-1], r["seed"]),(None,))[0] is True)
        marker = "✓" if ver_count > 0 else ("~" if cs_count > 0 else ("·" if pos_count > 0 else " "))
        print(f"  {marker} {k[0]:<24} {k[1]:<14} {len(trials):<8} {best.get('label','?'):<10} {pos_count:<10} {cs_count:<14} {ver_count}")

    # Seed_full / roleswap summary
    if sf_results:
        print()
        print("=" * 80)
        print("seed_full / roleswap")
        print("=" * 80)
        for cond, r in sf_results:
            label = r.get("best_label", "?")
            if label and label != "incorrect":
                print(f"  {cond:<20} {r['problem_id']:<26} {r['prompt_type']:<14} seed={r.get('seed')}  → {label}")


if __name__ == "__main__":
    main()
