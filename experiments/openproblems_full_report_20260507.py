#!/usr/bin/env python3
"""
End-to-end report combining ALL experiments on the FrontierMath open-problems benchmark:
  - Phase 1 (original): gpt-oss-120b xhigh + deepseek-v4-flash via OpenRouter
  - Phase 1 gemma: gemma-4-31b-it via Gemini API
  - Seed_full homogeneous gemma
  - Seed_full roleswap (gemma + oss verifier)
  - 3-judge consensus (partial)
  - Local verifiers (the ground-truth signal)

Outputs a comprehensive markdown table + summary stats.
"""
from __future__ import annotations
import argparse, json, sys, importlib.util
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))


def load_jsonl(path):
    if not Path(path).exists(): return []
    out = []
    with open(path) as f:
        for ln in f:
            try: out.append(json.loads(ln))
            except: pass
    return out


def load_json(path):
    if not Path(path).exists(): return None
    return json.load(open(path))


def collect_phase1_orig():
    """Phase 1 OG (gpt-oss + deepseek) trials from JSONL log."""
    rows = []
    for p in ROOT.glob("logs/openproblems_pass5_20260507_*.jsonl"):
        for r in load_jsonl(p):
            if r.get("kind") == "trial":
                r["_source"] = "phase1_orig"
                rows.append(r)
    # de-dup by (problem, type, model, seed)
    seen = set(); uniq = []
    for r in rows:
        k = (r["problem_id"], r["prompt_type"], r["model"].split("/")[-1], r["seed"])
        if k in seen: continue
        seen.add(k); uniq.append(r)
    return uniq


def collect_phase1_gemma():
    rows = []
    for p in ROOT.glob("logs/openproblems_gemma_phase1_*.jsonl"):
        for r in load_jsonl(p):
            r["_source"] = "phase1_gemma"
            r["kind"] = "trial"
            rows.append(r)
    return rows


def collect_seedfull(condition):
    """seed_full results from JSONL log + saved JSON."""
    rows = []
    for p in ROOT.glob(f"logs/openproblems_gemma_seedfull_*_{condition}_*.jsonl"):
        for r in load_jsonl(p):
            r["_source"] = f"seedfull_{condition}"
            rows.append(r)
    # Also try the saved JSON if log doesn't have all
    for p in ROOT.glob(f"experiments/results/openproblems_gemma_seedfull_*_{condition}_*.json"):
        d = load_json(p)
        if d:
            for r in d.get("results", []):
                r["_source"] = f"seedfull_{condition}"
                rows.append(r)
    # De-dup
    seen = set(); uniq = []
    for r in rows:
        k = (r["problem_id"], r["prompt_type"], r["seed"], r.get("condition", condition))
        if k in seen: continue
        seen.add(k); uniq.append(r)
    return uniq


def collect_consensus():
    """All consensus results: v1 (gpt-oss + gemini-3.1-pro + deepseek) and v2 (gpt-oss + deepseek)."""
    out = {}
    # v1
    p1 = ROOT / "experiments/results/consensus_partial_55.json"
    d1 = load_json(p1)
    if d1:
        for c in d1["results"]:
            k = (c["problem_id"], c["prompt_type"], c["model"].split("/")[-1], c["seed"])
            out[k] = {**c, "_version": "v1_3judge"}
    # v2
    for p2 in ROOT.glob("experiments/results/openproblems_consensus_v2_*.json"):
        d2 = load_json(p2)
        if d2:
            for c in d2["results"]:
                k = (c["problem_id"], c["prompt_type"], c["model"].split("/")[-1], c["seed"])
                # v2 takes precedence (more recent)
                out[k] = {**c, "_version": "v2_2judge"}
    return out


def run_local_verify(rows):
    """Run local verifiers on all trials."""
    spec = importlib.util.spec_from_file_location("ov", str(ROOT / "experiments/openproblems_local_verify_20260507.py"))
    ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)
    out = {}
    for r in rows:
        candidate = r.get("gen_text") or r.get("best_candidate") or r.get("final_solution")
        if not candidate: continue
        verifier = ov.VERIFIERS.get((r["problem_id"], r["prompt_type"]))
        if not verifier: continue
        key = (r["problem_id"], r["prompt_type"], r.get("model", "?").split("/")[-1] if "model" in r else r.get("_source"), r.get("seed"))
        try:
            ok, msg = verifier(candidate)
        except Exception as e:
            ok, msg = False, f"crash: {type(e).__name__}: {e}"
        out[key] = (ok, msg)
    return out


PASS = {"correct", "almost"}
SCORE = {"correct":7, "almost":6, "partial":1, "incorrect":0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results/openproblems_full_report.md"))
    args = ap.parse_args()

    p1_orig = collect_phase1_orig()
    p1_gemma = collect_phase1_gemma()
    sf_homo = collect_seedfull("gemma_homogeneous")
    sf_role = collect_seedfull("roleswap_oss_verify")
    cons = collect_consensus()

    print(f"Phase 1 OG: {len(p1_orig)}")
    print(f"Phase 1 gemma: {len(p1_gemma)}")
    print(f"seed_full homogeneous: {len(sf_homo)}")
    print(f"seed_full roleswap: {len(sf_role)}")
    print(f"Consensus entries: {len(cons)}")

    all_rows = p1_orig + p1_gemma
    verify = run_local_verify(all_rows)
    # Verify seed_full too
    verify_sf = run_local_verify(sf_homo + sf_role)
    verify.update(verify_sf)

    n_verified = sum(1 for k,(v,_) in verify.items() if v is True)
    n_failed = sum(1 for k,(v,_) in verify.items() if v is False)
    print(f"Local verifier: {n_verified} verified, {n_failed} failed (others have no checker)")

    # Output
    out_lines = []
    out_lines.append(f"# FrontierMath open-problems — full report")
    out_lines.append(f"")
    out_lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    out_lines.append(f"")
    out_lines.append(f"## Datasets")
    out_lines.append(f"")
    out_lines.append(f"| Source | Trials |")
    out_lines.append(f"|---|---|")
    out_lines.append(f"| Phase 1 (gpt-oss-120b xhigh + deepseek-v4-flash via OpenRouter) | {len(p1_orig)} |")
    out_lines.append(f"| Phase 1 gemma (gemma-4-31b-it via Gemini API) | {len(p1_gemma)} |")
    out_lines.append(f"| seed_full homogeneous gemma | {len(sf_homo)} |")
    out_lines.append(f"| seed_full roleswap (gemma + oss verifier) | {len(sf_role)} |")
    out_lines.append(f"| 3-judge consensus entries | {len(cons)} |")
    out_lines.append(f"")

    # Verified passes
    verified = [k for k,(v,_) in verify.items() if v is True]
    out_lines.append(f"## Locally verified passes ({len(verified)})")
    out_lines.append(f"")
    if verified:
        out_lines.append(f"| Problem | Type | Source | Seed | Verifier message |")
        out_lines.append(f"|---|---|---|---|---|")
        for k in sorted(verified):
            pid, ptype, src, seed = k
            msg = verify[k][1]
            out_lines.append(f"| {pid} | {ptype} | {src} | {seed} | {msg[:80]} |")
    else:
        out_lines.append("(none)")
    out_lines.append("")

    # Helper: extract per-judge labels uniformly (v1 has 'judge_labels', v2 has 'judges')
    def get_judge_labels(c):
        if "judge_labels" in c: return c["judge_labels"]
        if "judges" in c: return {k: v["label"] for k, v in c["judges"].items()}
        return {}

    # Consensus 2/2 (v2) or 3/3 (v1) unanimous correct
    n_unanim = 0
    for c in cons.values():
        labels = get_judge_labels(c)
        valid = [v for v in labels.values() if v in SCORE]
        if c.get('consensus') == 'correct' and c.get('n_agree') == len(valid) and len(valid) >= 2:
            n_unanim += 1
    out_lines.append(f"## Consensus unanimous correct ({n_unanim})")
    out_lines.append(f"")
    out_lines.append(f"| Problem | Type | Source | Seed | Consensus version | Judges |")
    out_lines.append(f"|---|---|---|---|---|---|")
    for k, c in sorted(cons.items()):
        labels = get_judge_labels(c)
        valid = [v for v in labels.values() if v in SCORE]
        if c.get("consensus") == "correct" and c.get("n_agree") == len(valid) and len(valid) >= 2:
            judges_str = " ".join(f"{j}={v}" for j, v in labels.items())
            out_lines.append(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {c.get('_version','?')} | {judges_str} |")
    out_lines.append(f"")

    # Per-problem aggregate
    out_lines.append(f"## Per-problem signal")
    out_lines.append(f"")
    out_lines.append(f"| Problem | Type | OG pos | Gemma pos | seed_full homo | roleswap | Cons-correct | Verified |")
    out_lines.append(f"|---|---|---|---|---|---|---|---|")

    by_prob = defaultdict(lambda: {"og":0, "gemma":0, "sf_homo":0, "sf_role":0, "verified":0, "cons_correct":0})
    for r in p1_orig:
        if r.get("label") in PASS:
            by_prob[(r["problem_id"], r["prompt_type"])]["og"] += 1
    for r in p1_gemma:
        if r.get("label") in PASS:
            by_prob[(r["problem_id"], r["prompt_type"])]["gemma"] += 1
    for r in sf_homo:
        if r.get("best_label") in PASS:
            by_prob[(r["problem_id"], r["prompt_type"])]["sf_homo"] += 1
    for r in sf_role:
        if r.get("best_label") in PASS:
            by_prob[(r["problem_id"], r["prompt_type"])]["sf_role"] += 1
    for k in verify:
        if verify[k][0] is True:
            by_prob[(k[0], k[1])]["verified"] += 1
    for k, c in cons.items():
        labels = get_judge_labels(c)
        valid = [v for v in labels.values() if v in SCORE]
        if c.get("consensus") == "correct" and c.get("n_agree") == len(valid) and len(valid) >= 2:
            by_prob[(k[0], k[1])]["cons_correct"] += 1

    for k in sorted(by_prob):
        s = by_prob[k]
        out_lines.append(f"| {k[0]} | {k[1]} | {s['og']} | {s['gemma']} | {s['sf_homo']} | {s['sf_role']} | {s['cons_correct']} | {s['verified']} |")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines))
    print(f"\nReport written: {out_path}")


if __name__ == "__main__":
    main()
