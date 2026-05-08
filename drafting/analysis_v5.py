"""V5 reanalysis: clustered bootstrap, Holm correction, Wilson CIs, token cost,
generator-judge family stratification.

Run from repo root:
    source .venv/bin/activate
    python3 drafting/analysis_v5.py > drafting/analysis_v5_output.txt
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ARCH_CSV = Path("results/architecture_20260506/trials.csv")

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


arch = load_csv(ARCH_CSV)
for r in arch:
    r["v4flash_score"] = to_float(r.get("v4flash_score"))
    r["v4pro_score"] = to_float(r.get("v4pro_score"))
    r["gemini_score"] = to_float(r.get("gemini_score"))
    r["cost_usd"] = to_float(r.get("cost_usd"))
    r["elapsed_s"] = to_float(r.get("elapsed_s"))
    r["difficulty"] = int(r["difficulty"]) if r.get("difficulty") not in (None, "") else None
    r["is_26_research"] = to_bool(r.get("is_26_research"))


# ----------------------------------------------------------------------------
# 1) PROBLEM-CLUSTERED BOOTSTRAP on headline contrasts
# ----------------------------------------------------------------------------

print("=" * 90)
print("1. PROBLEM-CLUSTERED BOOTSTRAP on headline contrasts (v4-flash judge)")
print("=" * 90)
print()
print("Resampling unit = problem (cluster). All paired diffs for that problem")
print("travel together. This corrects under-coverage of trial-level CIs.")
print()


def clustered_bootstrap_paired(arch, mode_a, mode_b,
                                restrict_difficulty=None, restrict_reasoning=None):
    """Returns (mean Δ, problem-cluster bootstrap 95% CI, p, n_pairs, n_problems)."""
    score = {}
    for r in arch:
        if r["v4flash_score"] is None:
            continue
        score[(r["model_short"], r["reasoning"], r["problem_id"], r["mode"])] = r["v4flash_score"]
    pairs_by_problem = defaultdict(list)
    for (m, rea, pid, mode), s in score.items():
        if mode != mode_a:
            continue
        if restrict_reasoning is not None and rea != restrict_reasoning:
            continue
        b = score.get((m, rea, pid, mode_b))
        if b is None:
            continue
        # difficulty per problem from any matching row
        d = next((r["difficulty"] for r in arch if r["problem_id"] == pid), None)
        if restrict_difficulty is not None and d not in restrict_difficulty:
            continue
        pairs_by_problem[pid].append(s - b)
    problems = list(pairs_by_problem.keys())
    n_problems = len(problems)
    if n_problems == 0:
        return (np.nan, np.nan, np.nan, np.nan, 0, 0)
    # All paired diffs flat for the point estimate (paired-cell mean)
    all_diffs = [d for pid in problems for d in pairs_by_problem[pid]]
    mean = float(np.mean(all_diffs))
    # Cluster bootstrap: resample problems with replacement; for each draw,
    # take the mean over all paired diffs in those problems.
    boot = np.empty(N_BOOT)
    for i in range(N_BOOT):
        sample = RNG.choice(n_problems, n_problems, replace=True)
        diffs = []
        for j in sample:
            diffs.extend(pairs_by_problem[problems[j]])
        boot[i] = float(np.mean(diffs)) if diffs else np.nan
    boot = boot[~np.isnan(boot)]
    lo = float(np.quantile(boot, 0.025))
    hi = float(np.quantile(boot, 0.975))
    # Cluster permutation p: flip sign per cluster.
    obs = abs(mean)
    n_perm = N_PERM
    count = 0
    diffs_per_problem = [pairs_by_problem[p] for p in problems]
    sums = np.array([sum(d) for d in diffs_per_problem])
    counts = np.array([len(d) for d in diffs_per_problem])
    total_n = counts.sum()
    for _ in range(n_perm):
        signs = RNG.choice([-1.0, 1.0], size=n_problems)
        perm_mean = (signs * sums).sum() / total_n
        if abs(perm_mean) >= obs:
            count += 1
    p = (count + 1) / (n_perm + 1)
    return (mean, lo, hi, p, len(all_diffs), n_problems)


print(f"{'contrast':<35}{'restrict':<24}{'n_pairs':>8}{'n_prob':>8}"
      f"{'mean Δ':>10}{'95% CI (cluster)':>24}{'p (cluster)':>14}")
contrasts = [
    ("full - generate", "full", "generate", None, None),
    ("seed_generate - generate", "seed_generate", "generate", None, None),
    ("seed_full - generate", "seed_full", "generate", None, None),
    ("seed_full - generate", "seed_full", "generate", None, "max"),
    ("seed_full - generate", "seed_full", "generate", None, "default"),
    ("full - generate (R26 only)", "full", "generate", {2,3,4,5}, None),
    ("seed_full - generate (R26 only)", "seed_full", "generate", {2,3,4,5}, None),
    ("seed_generate - generate (R26 only)", "seed_generate", "generate", {2,3,4,5}, None),
]
for name, ma, mb, restrict_d, restrict_r in contrasts:
    m, lo, hi, p, npairs, nprob = clustered_bootstrap_paired(arch, ma, mb,
                                                              restrict_d, restrict_r)
    rstr = ""
    if restrict_d is not None:
        rstr += "d∈" + str(sorted(restrict_d))
    if restrict_r is not None:
        rstr += " r=" + restrict_r
    print(f"{name:<35}{rstr:<24}{npairs:>8}{nprob:>8}"
          f"{m:>10.3f}  [{lo:>6.3f},{hi:>6.3f}]{p:>14.4f}")


# ----------------------------------------------------------------------------
# 2) HOLM-CORRECTED p-values for §5.4 per-cell tests (8 family contrasts)
# ----------------------------------------------------------------------------

print()
print("=" * 90)
print("2. HOLM CORRECTION for §5.4 per-cell tests (8-test family)")
print("=" * 90)
print()

# Per-cell paired permutation p-values from analysis_v4_output (recomputed inline
# for self-containment).
def paired_perm_p(arch, model, reas, mode_a, mode_b):
    score = {}
    for r in arch:
        if r["v4flash_score"] is None:
            continue
        if r["model_short"] != model or r["reasoning"] != reas:
            continue
        score[(r["problem_id"], r["mode"])] = r["v4flash_score"]
    diffs = []
    for (pid, mode), s in score.items():
        if mode != mode_a:
            continue
        b = score.get((pid, mode_b))
        if b is None:
            continue
        diffs.append(s - b)
    diffs = np.array(diffs)
    if len(diffs) == 0:
        return None, None, 0
    obs = abs(diffs.mean())
    n = len(diffs)
    signs = RNG.choice([-1.0, 1.0], size=(N_PERM, n))
    null_means = (signs * diffs).mean(axis=1)
    p = float(((np.abs(null_means) >= obs).sum() + 1) / (N_PERM + 1))
    return float(diffs.mean()), p, n


cells = [
    ("gemma-4-31b-it",    "max",     "seed_full", "generate"),
    ("gpt-oss-120b",      "max",     "seed_full", "generate"),
    ("gemma-4-31b-it",    "max",     "full",      "generate"),
    ("gpt-oss-120b",      "max",     "full",      "generate"),
    ("deepseek-v4-flash", "default", "seed_full", "generate"),
    ("deepseek-v4-pro",   "default", "full",      "generate"),
    ("gemma-4-31b-it",    "default", "seed_full", "generate"),
    ("gpt-oss-120b",      "default", "seed_full", "generate"),
]
results = []
for model, reas, ma, mb in cells:
    mean, p, n = paired_perm_p(arch, model, reas, ma, mb)
    results.append((model, reas, ma, mb, n, mean, p))

# Holm-Bonferroni at α=0.05
sorted_idx = sorted(range(len(results)), key=lambda i: results[i][6])
m = len(results)
holm_p = [None] * len(results)
last = 0.0
for rank, i in enumerate(sorted_idx):
    raw = results[i][6]
    adj = min(1.0, raw * (m - rank))
    adj = max(adj, last)  # monotonicity
    holm_p[i] = adj
    last = adj

print(f"{'cell':<55}{'n':>5}{'Δ':>8}{'p_raw':>10}{'p_Holm':>10}{'sig α=.05?':>14}")
for (model, reas, ma, mb, n, mean, p), hp in zip(results, holm_p):
    sig = "yes" if hp < 0.05 else "no"
    print(f"{model+' '+reas+' '+ma+'-'+mb:<55}{n:>5}{mean:>8.3f}{p:>10.4f}{hp:>10.4f}{sig:>14}")


# ----------------------------------------------------------------------------
# 3) WILSON / CLOPPER-PEARSON CIs for all-zero cells
# ----------------------------------------------------------------------------

print()
print("=" * 90)
print("3. WILSON 95% UPPER BOUNDS for zero-pass cells")
print("=" * 90)
print()


def wilson_ci(x, n, alpha=0.05):
    """Two-sided Wilson interval; returns (point, lo, hi)."""
    if n == 0:
        return (np.nan, 0.0, 1.0)
    z = 1.96  # 95%
    phat = x / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n) / denom
    return (phat, max(0.0, centre - half), min(1.0, centre + half))


def clopper_pearson_upper(x, n, alpha=0.05):
    """One-sided 95% upper bound (Clopper-Pearson). For x=0, equals 1-(α)^(1/n)."""
    if x == 0:
        return 1 - alpha ** (1.0 / n) if n > 0 else 1.0
    # general inverse beta — use scipy if available; here we use a manual
    # for x=0 only (which is what we need for zero-pass cells)
    return None


tier_labels = {0: "pre-comp (PB-Basic)",
               1: "comp-hard (PB-Adv+E397)",
               2: "research-easy",
               3: "research-medium",
               4: "research-hard",
               5: "research-frontier"}

print(f"{'tier':<26}{'mode':<16}{'n':>5}{'x':>4}{'rate':>8}{'95% CI (Wilson)':>22}{'1-sided 95% upper':>20}")
for d in sorted(tier_labels):
    for m_ in ["generate", "seed_generate", "full", "seed_full"]:
        scores = [r["v4flash_score"] for r in arch
                  if r["difficulty"] == d and r["mode"] == m_
                  and r["v4flash_score"] is not None]
        if not scores:
            continue
        x = sum(1 for s in scores if s >= 6)
        n = len(scores)
        p, lo, hi = wilson_ci(x, n)
        upper = clopper_pearson_upper(0, n) if x == 0 else None
        upper_str = f"{upper*100:>5.1f}%" if upper is not None else "  -  "
        print(f"{tier_labels[d]:<26}{m_:<16}{n:>5}{x:>4}{p:>8.3f}"
              f"  [{lo:>5.3f},{hi:>5.3f}]{upper_str:>20}")
    print()


# ----------------------------------------------------------------------------
# 4) ACTUAL TOKEN/COST per architecture from logs
# ----------------------------------------------------------------------------

print()
print("=" * 90)
print("4. ACTUAL COST per architecture (cost_usd field, architecture trials)")
print("=" * 90)
print()

cost_by_mode = defaultdict(list)
elapsed_by_mode = defaultdict(list)
for r in arch:
    if r.get("cost_usd") is not None and r["cost_usd"] > 0:
        cost_by_mode[r["mode"]].append(r["cost_usd"])
    if r.get("elapsed_s") is not None and r["elapsed_s"] > 0:
        elapsed_by_mode[r["mode"]].append(r["elapsed_s"])

print(f"{'mode':<18}{'n_w_cost':>10}{'mean $':>10}{'median $':>10}{'p90 $':>10}"
      f"{'mean s':>10}{'median s':>10}{'p90 s':>10}")
for m_ in ["generate", "seed_generate", "full", "seed_full"]:
    c = cost_by_mode[m_]
    e = elapsed_by_mode[m_]
    if not c:
        print(f"{m_:<18}    no cost data")
        continue
    print(f"{m_:<18}{len(c):>10}{np.mean(c):>10.4f}{np.median(c):>10.4f}{np.quantile(c,0.9):>10.4f}"
          f"{np.mean(e):>10.1f}{np.median(e):>10.1f}{np.quantile(e,0.9):>10.1f}")

# Cost ratios vs generate
print()
print("Cost ratio (mean/generate-mean) by mode:")
gen_mean = float(np.mean(cost_by_mode["generate"])) if cost_by_mode["generate"] else None
for m_ in ["generate", "seed_generate", "full", "seed_full"]:
    if cost_by_mode[m_] and gen_mean:
        ratio = float(np.mean(cost_by_mode[m_])) / gen_mean
        print(f"  {m_:<18}: {ratio:.2f}× generate mean")

# Per-(model, mode) cost ratios
print()
print("Per-(model, mode) median cost (USD) — to detect generation-cost asymmetry:")
print(f"{'model':<22}{'generate':>10}{'seed_gen':>10}{'full':>10}{'seed_full':>10}{'full/gen':>10}{'sf/gen':>10}")
models = sorted({r["model_short"] for r in arch})
for model in models:
    by_mode = defaultdict(list)
    for r in arch:
        if r["model_short"] == model and r["reasoning"] == "default" and r.get("cost_usd"):
            by_mode[r["mode"]].append(r["cost_usd"])
    if not by_mode["generate"]:
        continue
    g = float(np.median(by_mode["generate"]))
    sg = float(np.median(by_mode["seed_generate"])) if by_mode["seed_generate"] else float("nan")
    f_ = float(np.median(by_mode["full"])) if by_mode["full"] else float("nan")
    sf = float(np.median(by_mode["seed_full"])) if by_mode["seed_full"] else float("nan")
    fg = f_ / g if not math.isnan(f_) else float("nan")
    sfg = sf / g if not math.isnan(sf) else float("nan")
    print(f"{model:<22}{g:>10.4f}{sg:>10.4f}{f_:>10.4f}{sf:>10.4f}{fg:>10.2f}{sfg:>10.2f}")


# ----------------------------------------------------------------------------
# 5) GENERATOR-JUDGE FAMILY OVERLAP
# ----------------------------------------------------------------------------

print()
print("=" * 90)
print("5. GENERATOR-JUDGE FAMILY OVERLAP (canonical judge = v4-flash)")
print("=" * 90)
print()

# Family map
family = {
    "deepseek-v4-flash": "deepseek",
    "deepseek-v4-pro":   "deepseek",
    "gemini-3-flash-preview": "gemini",
    "gemma-4-31b-it":    "google",
    "gpt-oss-120b":      "openai",
    "qwen3.6-35b-a3b":   "qwen",
}
JUDGE_FAMILY = "deepseek"  # canonical = v4-flash

print("Same-family generators (judged by v4-flash, generator family = deepseek):")
print("  deepseek-v4-flash, deepseek-v4-pro")
print("Different-family generators: gemini-3-flash-preview, gemma-4-31B, gpt-oss-120b, qwen")
print()

# For each contrast, compute mean Δ stratified by same/different family
def family_stratified(arch, mode_a, mode_b):
    score = {}
    for r in arch:
        if r["v4flash_score"] is None:
            continue
        score[(r["model_short"], r["reasoning"], r["problem_id"], r["mode"])] = r["v4flash_score"]
    same, diff = [], []
    for (m, rea, pid, mode), s in score.items():
        if mode != mode_a:
            continue
        b = score.get((m, rea, pid, mode_b))
        if b is None:
            continue
        gen_fam = family.get(m, "?")
        if gen_fam == JUDGE_FAMILY:
            same.append(s - b)
        else:
            diff.append(s - b)
    return same, diff


print(f"{'contrast':<28}{'group':<22}{'n':>6}{'mean Δ':>10}{'95% CI':>22}")
for name, ma, mb in [("full - generate", "full", "generate"),
                     ("seed_generate - generate", "seed_generate", "generate"),
                     ("seed_full - generate", "seed_full", "generate")]:
    same, diff = family_stratified(arch, ma, mb)
    for label, vals in [("same family (DS-flash judge)", same), ("different family", diff)]:
        if not vals:
            continue
        vals = np.array(vals)
        mean = float(vals.mean())
        boot = np.empty(N_BOOT)
        for i in range(N_BOOT):
            idx = RNG.integers(0, len(vals), len(vals))
            boot[i] = vals[idx].mean()
        lo, hi = float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))
        print(f"{name:<28}{label:<22}{len(vals):>6}{mean:>10.3f}  [{lo:>6.3f},{hi:>6.3f}]")
    print()


# ----------------------------------------------------------------------------
# 6) BROKEN-IDEATOR fallback rates (per model, mode) from existing data
# ----------------------------------------------------------------------------

# Best proxy: for seed_generate trials, did the v4flash_score on the
# "generate" first-branch (pass_at_1_v4flash) effectively equal the
# trial-level seed_generate score? We don't have ideator-output flags directly
# in trials.csv — skip if not available.

print()
print("=" * 90)
print("6. BROKEN-IDEATOR PROXY (seed_generate trials)")
print("=" * 90)
print()
print("We do not have direct ideator-output flags in trials.csv; the original")
print("Phase 1 reports note ~10–28% fallback rates. We surface this in v5 as a")
print("caveat near the first seeded-result table; no new quantification possible")
print("without the raw mode_extras field in trials.jsonl.")
print()

# Quick check: how many seed_generate trials in phase1 vs later phases?
counts = defaultdict(int)
for r in arch:
    if r["mode"] == "seed_generate":
        counts[r.get("source_experiment", "?")] += 1
print("seed_generate row counts by source_experiment:")
for k, v in sorted(counts.items()):
    print(f"  {k}: {v}")

print()
print("DONE.")
