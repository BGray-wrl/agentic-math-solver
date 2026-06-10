#!/usr/bin/env python3
"""
Reference runner (provenance): the run-to-run replicate study. Requires
IMO-GradingBench (Luong et al., 2025; not redistributed -- see README) with its
path in the GRADINGBENCH environment variable, and OPENROUTER_API_KEY in the
environment. The prompt and the validation anchor are read from the packaged
../prompt/ and ../data/ directories.

Run-to-run (replicate) variance of the cheap judge tier on IMO-GradingBench (validation).

We re-run three cheap open-weight judges on the fixed 200-instance validation sample
across N independent replicates and report the variance of their agreement with human
pass/fail labels. This quantifies how stable each judge — and the cheap consensus — is
from run to run, the missing piece in the single-run study.

IMPORTANT — no inference seed is sent. OpenRouter honours `seed` only on some backends,
and for `openai/gpt-oss-120b` (served by a large, heterogeneous third-party provider
pool) we found that passing `seed` perturbs the model's calibration. Replicates here
therefore capture genuine run-to-run variance from natural sampling and provider
routing. We log the serving provider per call.

Judges (each at the strongest reasoning setting it exposes; not normalised across
providers): deepseek/deepseek-v4-flash (default), openai/gpt-oss-120b ({"effort":"xhigh"}),
google/gemma-4-31b-it ({"effort":"high"}).

Validation sample: 200 instances drawn with seed 7 from the 800 not in the seed-42
exploratory sample (disjoint by construction; identical to the main study).

Usage:
    python multi_seed_cheap_judges.py --reps 3
    python multi_seed_cheap_judges.py --reps 3 --mock     # offline smoke test
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, json, math, os, random, re, time
import statistics as st
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv, find_dotenv

HERE = Path(__file__).resolve().parent
DATA_CSV = Path(os.environ.get("GRADINGBENCH") or (HERE.parent / "gradingbench.csv"))  # external benchmark
CONS_CSV = HERE.parent / "data" / "consensus_analysis.csv"  # original (no-seed) validation anchor (packaged)
PROMPT_MD = HERE.parent / "prompt" / "judge_gt.md"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

PRIOR_SEED, PRIOR_N, VAL_SEED, VAL_N = 42, 200, 7, 200
MAX_TOKENS, TIMEOUT = 32768, 600                            # kept high: do not truncate reasoning
DEFAULT_WORKERS, RETRIES, BACKOFF = 256, 3, 4.0

JUDGES = [
    {"judge_id": "deepseek-v4-flash", "model": "deepseek/deepseek-v4-flash", "reasoning": None,
     "reasoning_label": "default", "flat_per_M": 0.28, "col": "deepseek_v4_flash_default_score"},
    {"judge_id": "gpt-oss-120b", "model": "openai/gpt-oss-120b", "reasoning": {"effort": "xhigh"},
     "reasoning_label": "xhigh", "flat_per_M": 0.15, "col": "gpt_oss_120b_xhigh_score"},
    {"judge_id": "gemma-4-31b-it", "model": "google/gemma-4-31b-it", "reasoning": {"effort": "high"},
     "reasoning_label": "high", "flat_per_M": 0.38, "col": "gemma_4_31b_it_high_score"},
]

load_dotenv(find_dotenv(), override=True)
API_KEY = os.getenv("OPENROUTER_API_KEY")
_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(pool_connections=64, pool_maxsize=DEFAULT_WORKERS))


def load_validation_sample() -> list[dict]:
    rows = []
    with open(DATA_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"grading_id": r["Grading ID"], "problem_id": r["Problem ID"],
                         "problem": r["Problem"], "solution": r["Solution"],
                         "response": r["Response"], "human_points": int(r["Points"])})
    prior = {r["grading_id"] for r in random.Random(PRIOR_SEED).sample(rows, PRIOR_N)}
    val = random.Random(VAL_SEED).sample([r for r in rows if r["grading_id"] not in prior], VAL_N)
    assert not (prior & {r["grading_id"] for r in val})
    return val


def parse_score(t):
    if not t:
        return None
    m = re.search(r"<points>\s*(\d+)\s*out of 7\s*</points>", t, re.I)
    if m:
        v = int(m.group(1)); return v if 0 <= v <= 7 else None
    m = re.search(r"\b([0-7])\s*(?:/\s*7|out of 7)", t, re.I)
    return int(m.group(1)) if m else None


def call_judge(judge, prompt):
    body = {"model": judge["model"], "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS}                        # NO seed (see module docstring)
    if judge["reasoning"]:
        body["reasoning"] = judge["reasoning"]
    last = None
    for attempt in range(RETRIES + 1):
        try:
            r = _SESSION.post(API_URL, json=body, timeout=TIMEOUT,
                              headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
            d = r.json()
            if r.status_code != 200 or "error" in d:
                msg = str(d.get("error", d))
                if "insufficient" in msg.lower() or "credit" in msg.lower():
                    raise RuntimeError(msg)
                raise ValueError(f"HTTP {r.status_code}: {msg[:140]}")
            ch = d["choices"][0]; u = d.get("usage", {}) or {}
            cd = u.get("completion_tokens_details", {}) or {}
            content = ch["message"].get("content") or ch["message"].get("reasoning") or ""
            total = u.get("total_tokens", 0) or 0
            return {"score": parse_score(content), "provider": d.get("provider"),
                    "reasoning_tokens": cd.get("reasoning_tokens", 0),
                    "cost": u.get("cost") or round(judge["flat_per_M"] * total / 1e6, 6),
                    "finish_reason": ch.get("finish_reason")}
        except Exception as e:                               # noqa: BLE001
            last = e
            if attempt < RETRIES:
                time.sleep(BACKOFF * (2 ** attempt))
    raise last


def _bin(decisions):
    tp = sum(1 for j, h in decisions if j and h); fp = sum(1 for j, h in decisions if j and not h)
    tn = sum(1 for j, h in decisions if not j and not h); fn = sum(1 for j, h in decisions if not j and h)
    n = tp + fp + tn + fn
    prec = tp / (tp + fp) if tp + fp else float("nan"); rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec == prec and prec and rec else 0.0
    return {"n": n, "pass_agree": round((tp + tn) / n, 4) if n else None,
            "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn}


def single_stats(recs):
    valid = [r for r in recs if r["score"] is not None]
    s = _bin([(r["score"] >= 6, r["human_points"] >= 6) for r in valid])
    s["n_valid"] = len(valid)
    return s


def consensus(by_judge):
    """by_judge: {jid: {gid: (score, human_pass)}}. -> majority + all-three (unanimous) stats."""
    gids = set().union(*[set(d) for d in by_judge.values()])
    maj, allp = [], []
    for g in gids:
        scored = [by_judge[j][g] for j in by_judge if by_judge[j].get(g) and by_judge[j][g][0] is not None]
        if not scored:
            continue
        hp = scored[0][1]; passes = [s >= 6 for s, _ in scored]
        maj.append((sum(passes) * 2 > len(passes), hp))
        if len(scored) == len(by_judge):
            allp.append((all(passes), hp))
    return {"majority_vote": _bin(maj), "all_three_pass": _bin(allp)}


def original_anchor():
    """Original (no-seed) validation scores from consensus_analysis.csv, as replicate 'orig'."""
    by = {j["judge_id"]: {} for j in JUDGES}
    try:
        for r in csv.DictReader(open(CONS_CSV)):
            if r["sample"] != "validation":
                continue
            hp = int(float(r["human_score"])) >= 6
            for j in JUDGES:
                v = r.get(j["col"])
                if v not in (None, ""):
                    by[j["judge_id"]][r["grading_id"]] = (int(float(v)), hp)
    except FileNotFoundError:
        return None
    return by


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=3, help="number of independent no-seed replicates")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    sample = load_validation_sample()
    if args.mock:
        print(f"MOCK: validation n={len(sample)}, reps={args.reps}, no seed sent")
        return
    if not API_KEY:
        raise SystemExit("OPENROUTER_API_KEY not found")

    tpl = PROMPT_MD.read_text()
    print(f"No-seed replicate variance | n={len(sample)} reps={args.reps} workers={args.workers}", flush=True)
    tasks = [(rep, j, rec) for rep in range(1, args.reps + 1) for j in JUDGES for rec in sample]
    t0 = time.time(); spent = 0.0
    # results[rep][judge_id] = [rec, ...]
    results = {rep: {j["judge_id"]: [] for j in JUDGES} for rep in range(1, args.reps + 1)}

    def work(task):
        rep, j, rec = task
        p = (tpl.replace("{problem}", rec["problem"]).replace("{ground_truth}", rec["solution"])
                .replace("{candidate}", rec["response"]))
        try:
            o = call_judge(j, p)
            return rep, j["judge_id"], {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                                        "score": o["score"], "provider": o["provider"],
                                        "reasoning_tokens": o["reasoning_tokens"], "cost": o["cost"],
                                        "finish_reason": o["finish_reason"]}
        except Exception as e:                               # noqa: BLE001
            return rep, j["judge_id"], {"grading_id": rec["grading_id"], "human_points": rec["human_points"],
                                        "score": None, "error": str(e)[:140], "cost": 0.0}

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(work, t) for t in tasks]):
            rep, jid, rec = fut.result(); results[rep][jid].append(rec); spent += rec.get("cost", 0); done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(tasks)} calls  (${spent:.2f})", flush=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    anchor = original_anchor()
    rep_labels = (["orig"] if anchor else []) + [f"rep{r}" for r in range(1, args.reps + 1)]
    per_judge = {j["judge_id"]: {} for j in JUDGES}
    per_consensus = {"majority_vote": {}, "all_three_pass": {}}
    provider_mix = {j["judge_id"]: Counter() for j in JUDGES}

    # original anchor metrics
    if anchor:
        for j in JUDGES:
            # encode human pass/fail via a >=6 sentinel so single_stats can read it
            recs = [{"score": v[0], "human_points": 6 if v[1] else 0} for v in anchor[j["judge_id"]].values()]
            per_judge[j["judge_id"]]["orig"] = single_stats(recs)["pass_agree"]
        cs = consensus(anchor)
        per_consensus["majority_vote"]["orig"] = cs["majority_vote"]["pass_agree"]
        per_consensus["all_three_pass"]["orig"] = cs["all_three_pass"]["pass_agree"]

    # per-replicate metrics + save per-(judge,rep) artefacts
    for rep in range(1, args.reps + 1):
        by = {}
        for j in JUDGES:
            jid = j["judge_id"]; recs = results[rep][jid]
            for r in recs:
                if r.get("provider"):
                    provider_mix[jid][r["provider"]] += 1
            s = single_stats(recs)
            per_judge[jid][f"rep{rep}"] = s["pass_agree"]
            by[jid] = {r["grading_id"]: (r["score"], r["human_points"] >= 6) for r in recs}
            json.dump({"judge_id": jid, "model": j["model"], "reasoning": j["reasoning"], "rep": rep,
                       "seeded": False, "stats": s, "results": recs},
                      open(HERE / f"judge_{jid}_{j['reasoning_label']}_rep{rep}_{ts}.json", "w"),
                      indent=2, ensure_ascii=False)
        cs = consensus(by)
        per_consensus["majority_vote"][f"rep{rep}"] = cs["majority_vote"]["pass_agree"]
        per_consensus["all_three_pass"][f"rep{rep}"] = cs["all_three_pass"]["pass_agree"]

    def mean_std(d):
        vals = [d[k] for k in d if d[k] is not None]
        return (round(st.mean(vals), 4), round(st.stdev(vals), 4) if len(vals) > 1 else 0.0)

    summary = {"experiment": "cheap_tier_noseed_replicate_variance", "date": datetime.now(timezone.utc).isoformat(),
               "n": len(sample), "reps": args.reps, "seeded": False, "rep_labels": rep_labels,
               "wall_clock_s": round(time.time() - t0, 1), "total_cost_usd": round(spent, 4),
               "per_judge_pass_agree": per_judge, "per_consensus_pass_agree": per_consensus,
               "mean_std": {**{j["judge_id"]: mean_std(per_judge[j["judge_id"]]) for j in JUDGES},
                            **{k: mean_std(per_consensus[k]) for k in per_consensus}},
               "provider_mix": {k: dict(v) for k, v in provider_mix.items()}}
    json.dump(summary, open(HERE / f"summary_noseed_reps_{ts}.json", "w"), indent=2, ensure_ascii=False)

    # ---- report ----
    print(f"\n{'='*82}\nNO-SEED REPLICATE VARIANCE  (n={len(sample)}, reps={args.reps}, "
          f"wall={summary['wall_clock_s']}s, cost=${spent:.2f})\n{'='*82}")
    cols = rep_labels
    print(f"{'system':22s} " + " ".join(f"{c:>7}" for c in cols) + f" {'mean':>7} {'std':>6}")
    for j in JUDGES:
        d = per_judge[j["judge_id"]]; m, sd = mean_std(d)
        print(f"{j['judge_id']:22s} " + " ".join(f"{d.get(c, float('nan')):7.3f}" for c in cols) + f" {m:7.3f} {sd:6.3f}")
    for k in per_consensus:
        d = per_consensus[k]; m, sd = mean_std(d)
        print(f"{k:22s} " + " ".join(f"{d.get(c, float('nan')):7.3f}" for c in cols) + f" {m:7.3f} {sd:6.3f}")
    print("\nprovider mix (across reps):")
    for jid, mix in summary["provider_mix"].items():
        print(f"  {jid:22s} {mix}")
    print(f"\nsaved: summary_noseed_reps_{ts}.json (+ per-judge/rep JSONs)")


if __name__ == "__main__":
    main()
