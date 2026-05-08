#!/usr/bin/env python3
"""
For problems where we have a local verifier, compute judge-vs-truth confusion.
"""
from __future__ import annotations
import json, sys, importlib.util
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

spec = importlib.util.spec_from_file_location("ov", str(Path(__file__).parent / "openproblems_local_verify_20260507.py"))
ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)

# Treat arithmetic-kakeya necessary-conditions PASS as "false" (per manual trace)
# since the constructions submitted don't actually have valid forcing pairs.
# Inverse-galois necessary-conditions FAIL is "false". For other problems use the result directly.
LOCAL_TRUTH_OVERRIDE = {
    # (pid, ptype): function(verifier_result_bool, msg) -> truth_bool
}

def true_label(pid, ptype, ver_result, msg):
    """Ground truth: True/False/None (None = no verifier)."""
    if ver_result is None: return None
    # arithmetic-kakeya only checks necessary conditions; pass != truth.
    # Per manual trace, all submitted "passes" don't have working forcing pairs.
    # Mark as False since necessary conditions are insufficient.
    if pid == "arithmetic-kakeya":
        # Necessary cond pass doesn't prove correctness; necessary cond fail proves wrongness.
        return False if not ver_result else False  # always False for now (no submission verified semantically)
    if pid == "inverse-galois":
        # Necessary cond pass doesn't prove correctness either, but FAIL definitively rules out.
        # We have 0 passes (all 20 fail).
        return False  # all known false
    return ver_result


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "logs" / "openproblems_pass5_20260507_20260507_183859.jsonl")
    rows = []
    with open(log) as f:
        for ln in f:
            r = json.loads(ln)
            if r.get("kind") == "trial" or (r.get("gen_text") and r.get("problem_id")):
                rows.append(r)

    by_pid = defaultdict(list)
    overall = []
    for r in rows:
        key = (r["problem_id"], r["prompt_type"])
        verifier = ov.VERIFIERS.get(key)
        if not verifier: continue
        text = r.get("gen_text") or ""
        try:
            ok, msg = verifier(text)
        except Exception as e:
            ok, msg = False, f"crash: {e}"
        truth = true_label(r["problem_id"], r["prompt_type"], ok, msg)
        if truth is None: continue
        by_pid[key].append((r["label"], truth))
        overall.append((r["label"], truth, r["problem_id"], r["prompt_type"]))

    print("=== Per-problem judge accuracy ===\n")
    print(f"{'Problem':<26} {'Type':<14} {'Trials':<8}  Judge label distribution → truth")
    print("-"*100)
    for k in sorted(by_pid):
        pairs = by_pid[k]
        labels = [p[0] for p in pairs]
        truths = [p[1] for p in pairs]
        # Group: per judge label, how many true?
        per_label = defaultdict(lambda: [0,0])
        for lab, t in pairs:
            per_label[lab][1 if t else 0] += 1
        total = len(pairs)
        n_true = sum(truths)
        breakdown = "  ".join(f"{lab}:{per_label[lab][1]}T+{per_label[lab][0]}F" for lab in ("correct","almost","partial","incorrect") if per_label[lab][0]+per_label[lab][1])
        print(f"  {k[0]:<24} {k[1]:<14} {total:<8} {breakdown}")

    print("\n=== Aggregate confusion (verifiable problems only) ===\n")
    label_to_truth = defaultdict(lambda: [0,0])  # [F, T]
    for lab, t, pid, ptype in overall:
        label_to_truth[lab][1 if t else 0] += 1
    rank = {"correct":3, "almost":2, "partial":1, "incorrect":0}
    print(f"{'Judge label':<14} {'#true':<8} {'#false':<8} {'%true':<8}  {'precision-from-this-rank-and-up':<28}")
    cum_t = cum_f = 0
    for lab in ("correct","almost","partial","incorrect"):
        t = label_to_truth[lab][1]
        f = label_to_truth[lab][0]
        pct_t = (t/(t+f))*100 if (t+f) else 0
        cum_t += t; cum_f += f
        cum_pct = (cum_t/(cum_t+cum_f))*100 if (cum_t+cum_f) else 0
        print(f"  {lab:<12} {t:<8} {f:<8} {pct_t:>5.1f}%   {cum_pct:>5.1f}% ({cum_t}/{cum_t+cum_f})")

    # Excluding inverse-galois (fully checkable but model uniformly fabricates) and
    # arithmetic-kakeya (necessary-conditions only, treated as all-false above)
    print("\n=== Aggregate confusion EXCLUDING inverse-galois & arithmetic-kakeya ===\n")
    sub = [(lab,t,pid,ptype) for (lab,t,pid,ptype) in overall
           if pid not in ("inverse-galois", "arithmetic-kakeya")]
    label_to_truth_sub = defaultdict(lambda: [0,0])
    for lab, t, pid, ptype in sub:
        label_to_truth_sub[lab][1 if t else 0] += 1
    print(f"{'Judge label':<14} {'#true':<8} {'#false':<8} {'%true':<8}")
    for lab in ("correct","almost","partial","incorrect"):
        t = label_to_truth_sub[lab][1]
        f = label_to_truth_sub[lab][0]
        pct = (t/(t+f))*100 if (t+f) else 0
        print(f"  {lab:<12} {t:<8} {f:<8} {pct:>5.1f}%")

    # As filters
    print("\n=== Judge as filter ===\n")
    n_total_true = sum(1 for _,t,_,_ in overall if t)
    n_total_false = sum(1 for _,t,_,_ in overall if not t)
    print(f"Total verifiable trials: {n_total_true} true, {n_total_false} false")
    for thresh, name in [("correct","Only judge=correct"), ("almost","correct OR almost"),
                         ("partial","correct OR almost OR partial")]:
        accept = [p for p in overall if rank.get(p[0],-1) >= rank[thresh]]
        n_kept = len(accept)
        n_kept_true = sum(1 for p in accept if p[1])
        recall = n_kept_true / n_total_true if n_total_true else 0
        precision = n_kept_true / n_kept if n_kept else 0
        print(f"  {name:<35}  kept={n_kept}  true_kept={n_kept_true}  precision={precision:.0%}  recall={recall:.0%}")


if __name__ == "__main__":
    main()
