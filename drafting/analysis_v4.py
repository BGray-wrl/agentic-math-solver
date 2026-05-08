"""V4 analysis: difficulty-tier breakdowns, all-trial frontier solves, bootstrap CIs.

Run from repo root:
    source .venv/bin/activate
    python3 drafting/analysis_v4.py > drafting/analysis_v4_output.txt
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ARCH_CSV = Path("results/architecture_20260506/trials.csv")
SCALE_CSV = Path("results/scaling_20260506/trials.csv")
SCALE_JSONL = Path("results/scaling_20260506/trials.jsonl")

RNG = np.random.default_rng(20260507)
N_BOOT = 5000
N_PERM = 10000


def to_float(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def to_bool(x):
    if isinstance(x, bool):
        return x
    if x is None:
        return None
    return str(x).strip().lower() in ("true", "1", "yes", "t")


def load_csv(p):
    with open(p) as f:
        return list(csv.DictReader(f))


def bootstrap_ci(values, statistic=np.mean, alpha=0.05, n_boot=N_BOOT):
    values = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))],
                         dtype=float)
    if len(values) == 0:
        return (np.nan, np.nan, np.nan)
    boot = np.empty(n_boot)
    n = len(values)
    for i in range(n_boot):
        idx = RNG.integers(0, n, n)
        boot[i] = statistic(values[idx])
    lo = float(np.quantile(boot, alpha / 2))
    hi = float(np.quantile(boot, 1 - alpha / 2))
    return float(statistic(values)), lo, hi


def paired_bootstrap_ci(a, b, alpha=0.05, n_boot=N_BOOT):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    if len(a) == 0:
        return (np.nan, np.nan, np.nan, 0)
    diff = a - b
    n = len(diff)
    boot = np.empty(n_boot)
    for i in range(n_boot):
        idx = RNG.integers(0, n, n)
        boot[i] = diff[idx].mean()
    lo = float(np.quantile(boot, alpha / 2))
    hi = float(np.quantile(boot, 1 - alpha / 2))
    return float(diff.mean()), lo, hi, n


def permutation_pvalue(a, b, n_perm=N_PERM):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    if len(a) == 0:
        return np.nan
    diff = a - b
    obs = diff.mean()
    n = len(diff)
    signs = RNG.choice([-1.0, 1.0], size=(n_perm, n))
    null_means = (signs * diff).mean(axis=1)
    return float(((np.abs(null_means) >= abs(obs)).sum() + 1) / (n_perm + 1))


# ----------------------------------------------------------------------------
# Load
# ----------------------------------------------------------------------------

arch = load_csv(ARCH_CSV)
for r in arch:
    r["v4flash_score"] = to_float(r.get("v4flash_score"))
    r["v4pro_score"] = to_float(r.get("v4pro_score"))
    r["gemini_score"] = to_float(r.get("gemini_score"))
    r["difficulty"] = int(r["difficulty"]) if r.get("difficulty") not in (None, "") else None
    r["is_26_research"] = to_bool(r.get("is_26_research"))

scale = load_csv(SCALE_CSV)
for r in scale:
    for k in ["pass_at_n_mean_v4flash", "pass_at_n_std_v4flash",
              "pass_at_n_pass_rate_v4flash", "pass_at_n_mean_v4pro",
              "pass_at_n_mean_gemini"]:
        r[k] = to_float(r.get(k))
    r["n"] = int(r["n"])
    r["difficulty"] = int(r["difficulty"]) if r.get("difficulty") not in (None, "") else None
    r["is_26_research"] = to_bool(r.get("is_26_research"))

# Scale jsonl for branch_scores
scale_jsonl = [json.loads(l) for l in open(SCALE_JSONL)]

print(f"# Architecture rows: {len(arch)}")
print(f"# Scaling rows: {len(scale)}")
print(f"# Scaling jsonl rows: {len(scale_jsonl)}")
print()


# ----------------------------------------------------------------------------
# 1) DIFFICULTY-TIER BREAKDOWN
# ----------------------------------------------------------------------------

print("=" * 90)
print("1. DIFFICULTY-TIER BREAKDOWN (architecture trials, v4-flash judge)")
print("=" * 90)

modes = ["generate", "seed_generate", "full", "seed_full"]
diff_labels = {0: "pre-comp (PB-Basic)", 1: "comp-hard (PB-Adv+E397)",
               2: "research-easy", 3: "research-medium",
               4: "research-hard", 5: "research-frontier"}

print()
print(f"{'tier':<26}{'mode':<16}{'n':>6}{'mean':>8}{'95% CI':>20}{'pass':>8}{'95% CI':>20}")
for d in sorted(diff_labels.keys()):
    for m in modes:
        scores = [r["v4flash_score"] for r in arch
                  if r["difficulty"] == d and r["mode"] == m
                  and r["v4flash_score"] is not None]
        if not scores:
            continue
        mean, mlo, mhi = bootstrap_ci(scores, np.mean)
        passes = [1.0 if s >= 6 else 0.0 for s in scores]
        prate, plo, phi = bootstrap_ci(passes, np.mean)
        print(f"{diff_labels[d]:<26}{m:<16}{len(scores):>6}"
              f"{mean:>8.2f}  [{mlo:>5.2f},{mhi:>5.2f}]"
              f"{prate:>8.2f}  [{plo:>5.2f},{phi:>5.2f}]")
    print()


# ----------------------------------------------------------------------------
# 1b) Aggregate by tier across all modes (for difficulty gradient table)
# ----------------------------------------------------------------------------

print("Aggregate (all modes pooled) by tier:")
print(f"{'tier':<28}{'n':>6}{'mean':>8}{'95% CI':>20}{'pass':>8}{'95% CI':>20}")
for d in sorted(diff_labels.keys()):
    scores = [r["v4flash_score"] for r in arch
              if r["difficulty"] == d and r["v4flash_score"] is not None]
    if not scores:
        continue
    mean, mlo, mhi = bootstrap_ci(scores, np.mean)
    passes = [1.0 if s >= 6 else 0.0 for s in scores]
    prate, plo, phi = bootstrap_ci(passes, np.mean)
    print(f"{diff_labels[d]:<28}{len(scores):>6}"
          f"{mean:>8.2f}  [{mlo:>5.2f},{mhi:>5.2f}]"
          f"{prate:>8.2f}  [{plo:>5.2f},{phi:>5.2f}]")
print()


# ----------------------------------------------------------------------------
# 2) ARCHITECTURE LIFT BY DIFFICULTY (paired diff per (model, reasoning, problem))
# ----------------------------------------------------------------------------

print("=" * 90)
print("2. ARCHITECTURE LIFT BY DIFFICULTY (paired (model, reasoning, problem) diffs, v4-flash)")
print("=" * 90)
print()

# Build (model, reasoning, problem) -> {mode -> v4flash_score}
arch_by_cell = defaultdict(dict)
arch_diff = {}
for r in arch:
    if r["v4flash_score"] is None:
        continue
    key = (r["model_short"], r["reasoning"], r["problem_id"])
    arch_by_cell[key][r["mode"]] = r["v4flash_score"]
    arch_diff[key] = r["difficulty"]


def lift_table_strat(mode_a, mode_b, restrict_difficulty=None, restrict_reasoning=None):
    diffs = []
    for key, modemap in arch_by_cell.items():
        m, rea, pid = key
        if restrict_reasoning is not None and rea != restrict_reasoning:
            continue
        if restrict_difficulty is not None and arch_diff.get(key) not in restrict_difficulty:
            continue
        if mode_a in modemap and mode_b in modemap:
            diffs.append(modemap[mode_a] - modemap[mode_b])
    return diffs


tier_sets = [
    ("all", None),
    ("pre-comp (d=0)", {0}),
    ("comp-hard (d=1)", {1}),
    ("research-easy (d=2)", {2}),
    ("research-med+ (d≥3)", {3, 4, 5}),
    ("PB-Adv+R26 (d≥1)", {1, 2, 3, 4, 5}),
    ("R26 only (d≥2)", {2, 3, 4, 5}),
]

for contrast_name, ma, mb in [("full - generate", "full", "generate"),
                              ("seed_generate - generate", "seed_generate", "generate"),
                              ("seed_full - generate", "seed_full", "generate")]:
    print(f"--- {contrast_name} ---")
    print(f"{'tier':<26}{'n':>6}{'mean Δ':>10}{'95% CI':>22}{'p':>10}")
    for label, tier in tier_sets:
        diffs = lift_table_strat(ma, mb, tier)
        if not diffs:
            print(f"{label:<26}{0:>6}    no pairs")
            continue
        mean = float(np.mean(diffs))
        boot = np.empty(N_BOOT)
        for i in range(N_BOOT):
            idx = RNG.integers(0, len(diffs), len(diffs))
            boot[i] = np.mean(np.array(diffs)[idx])
        lo = float(np.quantile(boot, 0.025))
        hi = float(np.quantile(boot, 0.975))
        p = permutation_pvalue(diffs, [0.0] * len(diffs))
        print(f"{label:<26}{len(diffs):>6}{mean:>10.3f}  [{lo:>6.3f},{hi:>6.3f}]{p:>10.4f}")
    print()


# Also: stratified by reasoning (default vs max) for seed_full vs generate
print("--- seed_full - generate, stratified by reasoning ---")
print(f"{'reasoning':<14}{'tier':<22}{'n':>6}{'mean Δ':>10}{'95% CI':>22}{'p':>10}")
for reasoning in ["default", "max"]:
    for label, tier in [("all", None), ("research-easy", {2}), ("research-med+", {3, 4, 5})]:
        diffs = lift_table_strat("seed_full", "generate", tier, restrict_reasoning=reasoning)
        if not diffs:
            continue
        mean = float(np.mean(diffs))
        boot = np.empty(N_BOOT)
        for i in range(N_BOOT):
            idx = RNG.integers(0, len(diffs), len(diffs))
            boot[i] = np.mean(np.array(diffs)[idx])
        lo = float(np.quantile(boot, 0.025))
        hi = float(np.quantile(boot, 0.975))
        p = permutation_pvalue(diffs, [0.0] * len(diffs))
        print(f"{reasoning:<14}{label:<22}{len(diffs):>6}{mean:>10.3f}  [{lo:>6.3f},{hi:>6.3f}]{p:>10.4f}")
print()


# ----------------------------------------------------------------------------
# 3) ALL-TRIAL FRONTIER SOLVES on R26 (architecture ∪ scaling)
# ----------------------------------------------------------------------------

print("=" * 90)
print("3. ALL-TRIAL FRONTIER SOLVES on R26 (cells = distinct trial setups)")
print("=" * 90)
print()
print("A 'cell' = (model, mode_or_n_label, reasoning, source_experiment).")
print("Architecture: cell solves under judge J  ⇔  trial-level judge score ≥ 6.")
print("Scaling: cell solves under judge J       ⇔  max(branch_scores under J) ≥ 6.")
print()

# Architecture: trial-level cell solves
arch_frontier = defaultdict(lambda: {
    "v4f_solves": [], "v4p_solves": [], "gem_solves": [], "all_cells": [],
})
for r in arch:
    if not r["is_26_research"]:
        continue
    pid = r["problem_id"]
    cell = (r["model_short"], r["mode"], r["reasoning"], r.get("source_experiment", "?"))
    rec = arch_frontier[pid]
    rec["all_cells"].append(cell)
    if r["v4flash_score"] is not None and r["v4flash_score"] >= 6:
        rec["v4f_solves"].append(cell)
    if r["v4pro_score"] is not None and r["v4pro_score"] >= 6:
        rec["v4p_solves"].append(cell)
    if r["gemini_score"] is not None and r["gemini_score"] >= 6:
        rec["gem_solves"].append(cell)

# Scaling: per (problem, model, reasoning, source) get max branch score
scale_frontier = defaultdict(lambda: {
    "v4f_solves": [], "v4p_solves": [], "gem_solves": [], "all_cells": [],
})
seen = set()
for r in scale_jsonl:
    if not r.get("is_26_research"):
        continue
    if r.get("n") != 1:  # one row per cell at n=1
        continue
    pid = r["problem_id"]
    cell = (r["model_short"], f"scale-N={r['branches_available']}", r["reasoning"],
            r.get("source_experiment", "?"))
    if (pid, cell) in seen:
        continue
    seen.add((pid, cell))
    rec = scale_frontier[pid]
    rec["all_cells"].append(cell)
    bsf = r.get("branch_scores_v4flash") or []
    bsp = r.get("branch_scores_v4pro") or []
    bsg = r.get("branch_scores_gemini") or []
    if bsf and any(s is not None and s >= 6 for s in bsf):
        rec["v4f_solves"].append(cell)
    if bsp and any(s is not None and s >= 6 for s in bsp):
        rec["v4p_solves"].append(cell)
    if bsg and any(s is not None and s >= 6 for s in bsg):
        rec["gem_solves"].append(cell)

# Roleswap is in architecture (mode='seed_full' with various conditions); already counted.
# Combine
R26 = sorted(set(list(arch_frontier.keys()) + list(scale_frontier.keys())))

print(f"{'problem':<28}{'cells_arch':>11}{'cells_scl':>11}"
      f"{'v4f arch':>10}{'v4f scl':>10}{'v4p arch':>10}{'v4p scl':>10}"
      f"{'gem arch':>10}{'gem scl':>10}")
for pid in R26:
    a = arch_frontier[pid]
    s = scale_frontier[pid]
    print(f"{pid:<28}{len(a['all_cells']):>11}{len(s['all_cells']):>11}"
          f"{len(a['v4f_solves']):>10}{len(s['v4f_solves']):>10}"
          f"{len(a['v4p_solves']):>10}{len(s['v4p_solves']):>10}"
          f"{len(a['gem_solves']):>10}{len(s['gem_solves']):>10}")

print()
print("Combined (architecture + scaling) cell counts and pass-rates:")
print(f"{'problem':<28}{'difficulty':<22}"
      f"{'cells':>7}{'v4f':>6}{'v4f%':>7}"
      f"{'v4p':>6}{'v4p%':>7}{'gem':>6}{'gem%':>7}")
problem_diff = {}
for r in arch:
    if r["is_26_research"]:
        problem_diff[r["problem_id"]] = r.get("difficulty_label", "?")
for pid in R26:
    a, s = arch_frontier[pid], scale_frontier[pid]
    cells = len(a["all_cells"]) + len(s["all_cells"])
    v4f = len(a["v4f_solves"]) + len(s["v4f_solves"])
    v4p = len(a["v4p_solves"]) + len(s["v4p_solves"])
    gem = len(a["gem_solves"]) + len(s["gem_solves"])
    dlabel = problem_diff.get(pid, "?")
    pr = lambda k: f"{k/cells*100:>5.1f}%" if cells else "  -  "
    print(f"{pid:<28}{dlabel:<22}{cells:>7}{v4f:>6}{pr(v4f):>7}"
          f"{v4p:>6}{pr(v4p):>7}{gem:>6}{pr(gem):>7}")

print()
print("Solving cells listing (architecture + scaling), v4-flash & v4-pro only:")
for pid in R26:
    a, s = arch_frontier[pid], scale_frontier[pid]
    all_solves = [(c, "v4f", "arch") for c in a["v4f_solves"]] + \
                 [(c, "v4f", "scl") for c in s["v4f_solves"]] + \
                 [(c, "v4p", "arch") for c in a["v4p_solves"]] + \
                 [(c, "v4p", "scl") for c in s["v4p_solves"]]
    if not all_solves:
        continue
    print(f"  {pid} ({problem_diff.get(pid, '?')}):")
    seen_lines = set()
    for cell, judge, bucket in all_solves:
        line = f"    {cell[0]:<22} {cell[1]:<18} reas={cell[2]:<7} src={cell[3]:<22} judge={judge} ({bucket})"
        if line in seen_lines:
            continue
        seen_lines.add(line)
        print(line)


# ----------------------------------------------------------------------------
# 4) PASS@k BOOTSTRAP CIs
# ----------------------------------------------------------------------------

print()
print("=" * 90)
print("4. PASS@k BOOTSTRAP CIs (per-problem mean, v4-flash judge, scaling bucket)")
print("=" * 90)
print()

scale_by_cell = defaultdict(list)
for r in scale:
    key = (r["model_short"], r["reasoning"], r.get("source_experiment"), r["n"])
    scale_by_cell[key].append(r)

print(f"{'model':<22}{'reas':<10}{'src':<22}{'n':>4}"
      f"{'n_prob':>8}{'mean':>8}{'95% CI':>22}{'pass':>8}{'95% CI':>22}")
for key in sorted(scale_by_cell.keys()):
    rows = scale_by_cell[key]
    means = [r.get("pass_at_n_mean_v4flash") for r in rows
             if r.get("pass_at_n_mean_v4flash") is not None]
    rates = [r.get("pass_at_n_pass_rate_v4flash") for r in rows
             if r.get("pass_at_n_pass_rate_v4flash") is not None]
    if not means:
        continue
    m, mlo, mhi = bootstrap_ci(means, np.mean)
    pr, plo, phi = bootstrap_ci(rates, np.mean) if rates else (np.nan, np.nan, np.nan)
    model, reas, src, n = key
    print(f"{model:<22}{(reas or ''):<10}{(src or ''):<22}{n:>4}"
          f"{len(means):>8}{m:>8.2f}  [{mlo:>5.2f},{mhi:>5.2f}]"
          f"{pr:>8.2f}  [{plo:>5.2f},{phi:>5.2f}]")


# Pass@k delta CIs (paired across problems within a cell)
print()
print("Paired pass@k deltas within (model, reasoning, source) cells:")
print(f"{'model':<22}{'reas':<10}{'src':<22}{'contrast':<14}{'n':>5}{'mean Δ':>10}{'95% CI':>22}{'p':>10}")
for (model, reas, src), _ in sorted({(k[0], k[1], k[2]): None for k in scale_by_cell}.items()):
    # gather per-problem pass_at_n_mean by n
    by_n = defaultdict(dict)
    for r in scale:
        if r["model_short"] == model and r["reasoning"] == reas and r.get("source_experiment") == src:
            if r.get("pass_at_n_mean_v4flash") is not None:
                by_n[r["n"]][r["problem_id"]] = r["pass_at_n_mean_v4flash"]
    for (na, nb) in [(7, 1), (7, 3), (3, 1)]:
        if na not in by_n or nb not in by_n:
            continue
        common = sorted(set(by_n[na]) & set(by_n[nb]))
        if not common:
            continue
        a = [by_n[na][p] for p in common]
        b = [by_n[nb][p] for p in common]
        mean, lo, hi, n = paired_bootstrap_ci(a, b)
        p = permutation_pvalue(a, b)
        print(f"{model:<22}{reas:<10}{src:<22}{f'pass@{na}-pass@{nb}':<14}{n:>5}"
              f"{mean:>10.3f}  [{lo:>6.3f},{hi:>6.3f}]{p:>10.4f}")


# ----------------------------------------------------------------------------
# 5) KEY ARCH LIFT CELLS — paired diffs with p-values + pass-rate diffs
# ----------------------------------------------------------------------------

print()
print("=" * 90)
print("5. KEY ARCH LIFT CELLS — paired diffs and pass-rate diffs (v4-flash)")
print("=" * 90)
print()

key_cells = [
    ("gemma-4-31b-it",   "max",     "seed_full", "generate"),
    ("gpt-oss-120b",     "max",     "seed_full", "generate"),
    ("gemma-4-31b-it",   "max",     "full",      "generate"),
    ("gpt-oss-120b",     "max",     "full",      "generate"),
    ("deepseek-v4-flash","default", "seed_full", "generate"),
    ("deepseek-v4-pro",  "default", "full",      "generate"),
    ("gemma-4-31b-it",   "default", "seed_full", "generate"),
    ("gpt-oss-120b",     "default", "seed_full", "generate"),
    ("gemma-4-31b-it",   "default", "full",      "generate"),
    ("gpt-oss-120b",     "default", "full",      "generate"),
]

# Build (model, reasoning, problem, mode) -> v4flash_score
arch_score = {}
for r in arch:
    if r["v4flash_score"] is None:
        continue
    arch_score[(r["model_short"], r["reasoning"], r["problem_id"], r["mode"])] = r["v4flash_score"]

print(f"{'model':<22}{'reas':<8}{'contrast':<28}{'n':>4}"
      f"{'mean Δ':>10}{'95% CI':>22}{'p':>9}"
      f"{'Δ pass':>10}{'95% CI':>22}{'p':>9}")
for model, reas, mode_a, mode_b in key_cells:
    a_scores, b_scores, a_pass, b_pass = [], [], [], []
    for (m, rr, pid, mode), s in arch_score.items():
        if m == model and rr == reas and mode == mode_a:
            b = arch_score.get((m, rr, pid, mode_b))
            if b is not None:
                a_scores.append(s)
                b_scores.append(b)
                a_pass.append(1.0 if s >= 6 else 0.0)
                b_pass.append(1.0 if b >= 6 else 0.0)
    if not a_scores:
        print(f"{model:<22}{reas:<8}{(mode_a + ' - ' + mode_b):<28}    no pairs")
        continue
    m_, lo, hi, n = paired_bootstrap_ci(a_scores, b_scores)
    p = permutation_pvalue(a_scores, b_scores)
    pm, plo, phi, _ = paired_bootstrap_ci(a_pass, b_pass)
    pp = permutation_pvalue(a_pass, b_pass)
    print(f"{model:<22}{reas:<8}{(mode_a + ' - ' + mode_b):<28}{n:>4}"
          f"{m_:>10.3f}  [{lo:>6.3f},{hi:>6.3f}]{p:>9.4f}"
          f"{pm:>10.3f}  [{plo:>6.3f},{phi:>6.3f}]{pp:>9.4f}")


# ----------------------------------------------------------------------------
# 6) JUDGE PASS/FAIL AGREEMENT with bootstrap CIs
# ----------------------------------------------------------------------------

print()
print("=" * 90)
print("6. JUDGE PASS/FAIL AGREEMENT with bootstrap CIs")
print("=" * 90)
print()

triples = []
for r in arch:
    if any(r[k] is None for k in ["v4flash_score", "v4pro_score", "gemini_score"]):
        continue
    triples.append({
        "v4f_pass": r["v4flash_score"] >= 6,
        "v4p_pass": r["v4pro_score"] >= 6,
        "gem_pass": r["gemini_score"] >= 6,
    })
print(f"# triple-judged trials: {len(triples)}")

def agree_ci(pred):
    vals = [1.0 if pred(t) else 0.0 for t in triples]
    return bootstrap_ci(vals, np.mean)

m, lo, hi = agree_ci(lambda t: t["v4f_pass"] == t["v4p_pass"])
print(f"v4-flash vs v4-pro agree:  {m:.3f}  [{lo:.3f}, {hi:.3f}]")
m, lo, hi = agree_ci(lambda t: t["v4f_pass"] == t["gem_pass"])
print(f"v4-flash vs Gemini agree:  {m:.3f}  [{lo:.3f}, {hi:.3f}]")
m, lo, hi = agree_ci(lambda t: t["v4p_pass"] == t["gem_pass"])
print(f"v4-pro vs Gemini agree:    {m:.3f}  [{lo:.3f}, {hi:.3f}]")

v4f_fail = [t for t in triples if not t["v4f_pass"]]
m, lo, hi = bootstrap_ci([1.0 if t["gem_pass"] else 0.0 for t in v4f_fail], np.mean)
print(f"P(Gemini pass | v4-flash fail): {m:.3f}  [{lo:.3f}, {hi:.3f}]   n={len(v4f_fail)}")
v4f_pass = [t for t in triples if t["v4f_pass"]]
m, lo, hi = bootstrap_ci([1.0 if not t["gem_pass"] else 0.0 for t in v4f_pass], np.mean)
print(f"P(Gemini fail | v4-flash pass): {m:.3f}  [{lo:.3f}, {hi:.3f}]   n={len(v4f_pass)}")

print()
print("DONE.")
