#!/usr/bin/env python3
"""
Plot gallery for "Cost-Effective Automated Judging of Natural-Language
Mathematical Proofs" (ICML 2026 AI4Math workshop).

Regenerates the paper's five figures as PDFs into ../results/figures/
(figure1..figure5).

Generates the paper figures. Paper Figures 1-5 correspond to the candidate names
below: Fig 1 = fig7_forest, Fig 2 = fig6_leader_rank_flip, Fig 3 =
fig3_precision_recall_dial, Fig 4 = fig4_run_stability, Fig 5 =
fig2_passfail_vs_rank (the shipped PDFs are in ../results/figures/). Figs 1 and 5
of the candidate set are unused alternatives.

Data sources (run compute_metrics.py first to (re)generate the table CSVs):
  - ../results/tables/table1_validation.csv  (validation n=200; Figs 1, 2, 5)
  - ../results/tables/table3_runtorun.csv    (run-to-run; Fig 4)
  - ../data/full1000_metrics.csv   (full benchmark, n=1000; Figs 3 and 6)
  - ../data/consensus_analysis.csv (per-instance scores)

Run:
  python make_plots.py
"""
import csv
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patheffects as pe
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch

# white "shadowtext" halo so labels stay legible over contour/grid lines
HALO = [pe.withStroke(linewidth=2.0, foreground="white")]

warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data"))  # supplement/data/

# ----------------------------------------------------------------------------
# Publication style (matched to ICML two-column: Times-like serif, compact)
# ----------------------------------------------------------------------------
_serif = [f for f in ["Times New Roman", "Times", "Nimbus Roman",
                      "DejaVu Serif"] if f in {x.name for x in fm.fontManager.ttflist}]
plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "font.family": "serif",
    "font.serif": _serif or ["DejaVu Serif"],
    "mathtext.fontset": "cm",
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "axes.linewidth": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "legend.fontsize": 6.8,
    "legend.frameon": False,
    "lines.linewidth": 1.3,
    "lines.markersize": 5,
    "axes.grid": False,
    "grid.linewidth": 0.5,
    "grid.alpha": 0.35,
})

COL = 3.35   # single-column width (in)
DBL = 6.9    # full (two-column) width (in)

# Okabe-Ito colorblind-safe palette, fixed per system across all figures.
C = {
    "gptoss":   "#009E73",  # bluish green   (cheap)
    "deepseek": "#0072B2",  # blue           (cheap)
    "gemma":    "#56B4E9",  # sky blue       (cheap)
    "trio":     "#CC79A7",  # reddish purple (consensus)
    "allthree": "#7B3294",  # purple         (consensus, strict)
    "opus":     "#D55E00",  # vermillion     (frontier)
    "gemini":   "#E69F00",  # orange         (frontier)
    "iso":      "#9aa0a6",  # iso-F1 contour gray
    "band":     "#bdbdbd",
}

# ----------------------------------------------------------------------------
# Data, read from the regenerated tables -- run compute_metrics.py first.
# ----------------------------------------------------------------------------
TABLES = os.path.join(HERE, "..", "results", "tables")
PERINST = os.path.join(DATA, "consensus_analysis.csv")
FULL1000 = os.path.join(DATA, "full1000_metrics.csv")


def _f(x):
    x = (x or "").strip()
    return None if x in ("", "—", "-") else float(x)


def _load_val():
    """Table 1 (validation) from results/tables/table1_validation.csv."""
    rows = {r["judge"]: r for r in csv.DictReader(open(os.path.join(TABLES, "table1_validation.csv")))}
    spec = [("gptoss", "GPT-OSS-120B", "GPT-OSS-120B", "cheap"),
            ("deepseek", "DeepSeek-V4-Flash", "DeepSeek-V4-Flash", "cheap"),
            ("trio", "Cheap consensus (trio)", "Cheap consensus", "consensus"),
            ("opus", "Claude Opus 4.7", "Claude Opus 4.7", "frontier"),
            ("gemini", "Gemini 3.1 Pro", "Gemini 3.1 Pro", "frontier"),
            ("gemma", "Gemma-4-31B", "Gemma-4-31B", "cheap")]
    out = {}
    for key, csvname, label, tier in spec:
        r = rows[csvname]
        out[key] = (label, _f(r["pass_agree"]), _f(r["ci_lo"]), _f(r["ci_hi"]),
                    _f(r["spearman_rho"]), _f(r["cost_per_200"]), tier)
    return out


def _load_runs():
    """Table 3 (run-to-run) from results/tables/table3_runtorun.csv."""
    rows = {r["system"]: r for r in csv.DictReader(open(os.path.join(TABLES, "table3_runtorun.csv")))}
    spec = [("DeepSeek-V4-Flash", "DeepSeek-V4-Flash", C["deepseek"]),
            ("GPT-OSS-120B", "GPT-OSS-120B", C["gptoss"]),
            ("Gemma-4-31B", "Gemma-4-31B", C["gemma"]),
            ("Majority vote (trio)", "Majority vote", C["trio"]),
            ("All-three-pass", "All-three-pass", C["allthree"])]
    out = {}
    for csvname, label, color in spec:
        r = rows[csvname]
        out[label] = ([_f(r["orig"]), _f(r["rep1"]), _f(r["rep2"]), _f(r["rep3"])],
                      _f(r["mean"]), _f(r["std"]), color)
    return out


VAL = _load_val()
RUNS = _load_runs()


def _finish(ax):
    ax.tick_params(length=2.5)


FIGDIR = os.path.join(HERE, "..", "results", "figures")
SHIPPED = {"fig7_forest": "figure1_forest",
           "fig6_leader_rank_flip": "figure2_leader_flip",
           "fig3_precision_recall_dial": "figure3_precision_recall",
           "fig4_run_stability": "figure4_run_stability",
           "fig2_passfail_vs_rank": "figure5_passfail_vs_rank"}


def _save(fig, name):
    shipped = SHIPPED.get(name)
    if shipped:
        os.makedirs(FIGDIR, exist_ok=True)
        fig.savefig(os.path.join(FIGDIR, shipped + ".pdf"))
        print(f"  wrote results/figures/{shipped}.pdf")
    plt.close(fig)


# ============================================================================
# Fig 1 -- Cost-accuracy frontier (THE money plot)
# ============================================================================
def fig1_cost_frontier_clean():
    fig, ax = plt.subplots(figsize=(COL, 2.75))
    band_lo = min(VAL[k][2] for k in ("opus", "gemini"))
    band_hi = max(VAL[k][3] for k in ("opus", "gemini"))
    ax.axhspan(band_lo, band_hi, color=C["opus"], alpha=0.07, lw=0, zorder=0)
    ax.text(0.19, band_hi - 0.004, "frontier 95% CI band", color=C["opus"],
            fontsize=6.0, va="top", ha="left", alpha=0.95)

    marker = {"cheap": "o", "consensus": "*", "frontier": "D"}
    msize = {"cheap": 6, "consensus": 13, "frontier": 6}
    # label placement: (ha, dx_pts, dy_pts)
    lab_pos = {
        "gptoss":   ("left",   7,  2),
        "deepseek": ("left",   7,  3),
        "trio":     ("left",   8, -3),
        "opus":     ("right", -8,  3),
        "gemini":   ("right", -8, -9),
        "gemma":    ("left",   7, -2),
    }
    for key, (lab, pa, lo, hi, rho, cost, tier) in VAL.items():
        ax.errorbar(cost, pa, yerr=[[pa - lo], [hi - pa]], fmt=marker[tier],
                    ms=msize[tier], color=C[key], ecolor=C[key], elinewidth=1.0,
                    capsize=2.0, mec="white", mew=0.6, zorder=5)
        ha, dx, dy = lab_pos[key]
        ax.annotate(lab, (cost, pa), xytext=(dx, dy), textcoords="offset points",
                    fontsize=6.4, color=C[key], ha=ha, va="center", fontweight="bold")

    y_arrow = 0.758
    ax.annotate("", xy=(VAL["opus"][5], y_arrow), xytext=(VAL["gptoss"][5], y_arrow),
                arrowprops=dict(arrowstyle="<->", color="0.35", lw=0.9))
    ax.text(np.sqrt(VAL["opus"][5] * VAL["gptoss"][5]), y_arrow + 0.003,
            r"$\approx\,100\times$ cheaper, same accuracy", ha="center", va="bottom",
            fontsize=6.6, color="0.2")

    ax.set_xscale("log")
    ax.set_xlim(0.18, 70)
    ax.set_ylim(0.745, 0.935)
    ax.set_xlabel("Cost per 200 gradings (log scale)")
    ax.set_ylabel("Pass / fail agreement with humans")
    ax.set_xticks([0.2, 0.5, 1, 2, 5, 10, 20, 50])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"${v:g}"))
    leg = [Line2D([0], [0], marker="o", color="w", mfc="0.4", mec="w", ms=6, label="Cheap open-weight"),
           Line2D([0], [0], marker="*", color="w", mfc="0.4", mec="w", ms=11, label="Cheap consensus"),
           Line2D([0], [0], marker="D", color="w", mfc="0.4", mec="w", ms=6, label="Frontier")]
    ax.legend(handles=leg, loc="upper right", handletextpad=0.3, borderpad=0.3)
    _finish(ax)
    _save(fig, "fig1_cost_frontier")


# ============================================================================
# Fig 2 -- Pass/fail vs. ranking: cheap wins one axis, frontier the other
# ============================================================================
def fig2_passfail_vs_rank():
    fig, ax = plt.subplots(figsize=(COL, 2.7))
    pts = {k: v for k, v in VAL.items() if v[4] is not None}  # drop consensus
    lab_pos = {
        "gptoss":   ("left",   7,  -1),
        "deepseek": ("left",   7,   3),
        "opus":     ("right", -8,   3),
        "gemini":   ("right", -8,  -3),
        "gemma":    ("left",   7,   2),
    }
    for key, (lab, pa, lo, hi, rho, cost, tier) in pts.items():
        mk = "D" if tier == "frontier" else "o"
        ax.scatter(pa, rho, s=58 if mk == "o" else 46, marker=mk, color=C[key],
                   edgecolor="white", linewidth=0.6, zorder=5)
        ha, dx, dy = lab_pos[key]
        ax.annotate(lab, (pa, rho), xytext=(dx, dy), textcoords="offset points",
                    fontsize=6.4, color=C[key], ha=ha, va="center", fontweight="bold")

    # guidance annotations (placed in guaranteed-empty regions)
    ax.annotate("frontier leads\non rank correlation", xy=(0.7815, 0.732),
                fontsize=6.4, color=C["opus"], ha="left", va="top", style="italic")
    ax.annotate("cheap judges stay competitive\non the pass / fail decision", xy=(0.818, 0.632),
                fontsize=6.4, color=C["gptoss"], ha="center", va="center", style="italic")

    ax.set_xlabel("Pass / fail agreement with humans  (higher →)")
    ax.set_ylabel(r"Spearman $\rho$ with human score  (higher $\uparrow$)")
    ax.set_xlim(0.78, 0.90)
    ax.set_ylim(0.595, 0.74)
    ax.grid(True, axis="both")
    leg = [Line2D([0], [0], marker="o", color="w", mfc="0.4", mec="w", ms=6, label="Cheap open-weight"),
           Line2D([0], [0], marker="D", color="w", mfc="0.4", mec="w", ms=6, label="Frontier")]
    ax.legend(handles=leg, loc="lower left", handletextpad=0.3, borderpad=0.3)
    _finish(ax)
    _save(fig, "fig2_passfail_vs_rank")


# ============================================================================
# Fig 3 -- Precision / recall dial across consensus rules (n=1000)
# ============================================================================
def _load_full1000():
    rows = list(csv.DictReader(open(FULL1000)))
    return rows


def fig3_pr_dial():
    rows = _load_full1000()
    fig, ax = plt.subplots(figsize=(COL, 2.85))

    # iso-F1 contours (labelled once, in a corner, to avoid clutter)
    P = np.linspace(0.55, 0.97, 400)
    for f1 in (0.78, 0.80, 0.82, 0.84):
        R = (f1 * P) / (2 * P - f1)
        R[(R <= 0) | (R > 1.02)] = np.nan
        ax.plot(P, R, color=C["iso"], lw=0.6, ls=(0, (3, 3)), zorder=1)
    ax.text(0.845, 0.992, "dashed: iso-F1\ncontours 0.78–0.84",
            color=C["iso"], fontsize=5.8, ha="left", va="top", style="italic",
            path_effects=HALO)

    style = {  # name substr -> (color, marker, size, family)
    }
    def classify(name, group, rule):
        n = name.lower()
        if group == "individual":
            if "deepseek" in n: return C["deepseek"], "o", 55, "DeepSeek"
            if "gpt-oss" in n:  return C["gptoss"], "o", 55, "GPT-OSS"
            return C["gemma"], "o", 55, "Gemma"
        if group == "pair":
            return "0.45", "s", 34, "pair"
        if name.startswith("Majority"):
            return C["trio"], "*", 150, "majority"
        return C["allthree"], "D", 46, "all-three"

    seen = set()
    for r in rows:
        col, mk, sz, fam = classify(r["system"], r["group"], r["rule"])
        prec, rec = float(r["precision"]), float(r["recall"])
        ax.scatter(prec, rec, s=sz, marker=mk, color=col, edgecolor="white",
                   linewidth=0.6, zorder=5)
        # label
        short = (r["system"].replace(" @ xhigh", "").replace(" @ high", "")
                 .replace("DeepSeek-V4-Flash", "DeepSeek")
                 .replace("GPT-OSS-120B", "GPT-OSS").replace("Gemma-4-31B", "Gemma")
                 .replace("oss", "OSS").replace("ds", "DS").replace(" + ", "+")
                 .replace("Majority vote (trio)", "Majority").replace("All-three-pass", "All-three"))
        dx, dy = 6, 0
        if "All-three" in short: dx, dy = 7, -7
        if "DS+OSS" in short: dx, dy = 7, 6
        if short == "Majority": dx, dy = 8, 5
        if short == "GPT-OSS": dx, dy = 7, 5
        if short == "DeepSeek": dx, dy = -7, -8
        if short == "Gemma": dx, dy = 7, 3
        if short == "DS+gemma": dx, dy = 8, 0
        if short == "OSS+gemma": dx, dy = 8, 0
        ha = "left" if dx >= 0 else "right"
        ax.annotate(short, (prec, rec), xytext=(dx, dy), textcoords="offset points",
                    fontsize=5.9, color=col if col != "0.45" else "0.3", ha=ha, va="center",
                    path_effects=HALO, zorder=6)

    # "dial" guidance, placed near each end of the precision/recall trade-off
    ax.annotate("majority vote\n→ high recall", xy=(0.618, 0.905), fontsize=6.2,
                color=C["trio"], ha="left", va="center", style="italic", path_effects=HALO)
    ax.annotate("unanimous rules\n→ high precision", xy=(0.742, 0.775), fontsize=6.2,
                color=C["allthree"], ha="left", va="center", style="italic", path_effects=HALO)

    ax.set_xlabel("Precision (passed proofs that humans passed)")
    ax.set_ylabel("Recall (human-passed proofs caught)")
    ax.set_xlim(0.60, 0.90)
    ax.set_ylim(0.74, 1.0)
    leg = [Line2D([0], [0], marker="o", color="w", mfc="0.4", mec="w", ms=6, label="Single model"),
           Line2D([0], [0], marker="s", color="w", mfc="0.45", mec="w", ms=5.5, label="Pair (unanimous)"),
           Line2D([0], [0], marker="*", color="w", mfc=C["trio"], mec="w", ms=11, label="Majority vote"),
           Line2D([0], [0], marker="D", color="w", mfc=C["allthree"], mec="w", ms=5.5, label="All-three-pass")]
    ax.legend(handles=leg, loc="lower left", handletextpad=0.3, borderpad=0.3)
    _finish(ax)
    _save(fig, "fig3_precision_recall_dial")


# ============================================================================
# Fig 4 -- Run-to-run stability (4 runs, mean +/- std)
# ============================================================================
def fig4_stability():
    fig, ax = plt.subplots(figsize=(COL, 2.85))
    order = ["All-three-pass", "Majority vote", "Gemma-4-31B",
             "DeepSeek-V4-Flash", "GPT-OSS-120B"]  # bottom..top by interest
    ys = np.arange(len(order))
    rng = np.random.default_rng(0)
    for y, name in zip(ys, order):
        runs, mean, std, col = RUNS[name]
        jit = (rng.random(len(runs)) - 0.5) * 0.16
        ax.scatter(runs, np.full(len(runs), y) + jit, s=16, color=col, alpha=0.55,
                   edgecolor="none", zorder=3)
        ax.errorbar(mean, y, xerr=std, fmt="o", ms=6, color=col, ecolor=col,
                    elinewidth=1.4, capsize=3, mec="white", mew=0.7, zorder=5)
        ax.text(0.928, y, f"std {std:.3f}", fontsize=6.0, color=col,
                va="center", ha="left", fontweight="bold")

    ax.set_yticks(ys)
    ax.set_yticklabels([n.replace("-V4-Flash", "").replace("-4-31B", "")
                        for n in order])
    # bold the consensus tick labels
    for t, name in zip(ax.get_yticklabels(), order):
        if name in ("All-three-pass", "Majority vote"):
            t.set_fontweight("bold")
    ax.set_xlim(0.78, 0.955)
    ax.set_ylim(-0.5, len(order) - 0.5)
    ax.set_xlabel("Pass / fail agreement across 4 independent runs (n=200)")
    ax.grid(True, axis="x")
    # separate single models (top) from consensus rules (bottom)
    ax.axhline(1.5, color="0.8", lw=0.7, ls=(0, (2, 2)), zorder=1)
    ax.text(0.783, 3.45, "single models", fontsize=5.9, color="0.5", style="italic", va="center")
    ax.text(0.783, 0.5, "consensus", fontsize=5.9, color="0.5", style="italic", va="center")
    # annotate
    ax.text(RUNS["All-three-pass"][1], len(order) - 0.5 + 0.0, "", )
    leg = [Line2D([0], [0], marker="o", color="w", mfc="0.5", mec="w", ms=5.5, label="individual run"),
           Line2D([0], [0], marker="o", color="w", mfc="0.3", mec="w", ms=6.5,
                  label=r"mean $\pm$ std")]
    ax.legend(handles=leg, loc="lower left", handletextpad=0.3, borderpad=0.3)
    _finish(ax)
    _save(fig, "fig4_run_stability")


# ============================================================================
# Fig 5 -- Calibration / offsetting biases (per-instance, n=400)
# ============================================================================
def fig5_calibration():
    rows = list(csv.DictReader(open(PERINST)))
    def fnum(r, k):
        v = r[k].strip()
        return float(v) if v else None
    models = [("deepseek_v4_flash_default_score", "DeepSeek-V4-Flash", C["deepseek"], "under-credits"),
              ("gpt_oss_120b_xhigh_score", "GPT-OSS-120B", C["gptoss"], "calibrated"),
              ("gemma_4_31b_it_high_score", "Gemma-4-31B", C["gemma"], "over-credits")]
    hscores = sorted({int(float(r["human_score"])) for r in rows})

    fig, ax = plt.subplots(figsize=(COL, 2.75))
    # human pass threshold (>=6) as a light shaded column
    ax.axvspan(5.5, 7.4, color="0.93", zorder=0)
    ax.text(5.6, 0.15, "human pass (≥6)", fontsize=5.8, color="0.45",
            ha="left", va="bottom", rotation=90)
    ax.plot([0, 7], [0, 7], color="0.55", lw=0.9, ls=(0, (4, 3)), zorder=1)
    ax.text(6.95, 6.55, "perfect\ncalibration", fontsize=5.8, color="0.5",
            ha="right", va="top", rotation=0)

    for mk, lab, col, bias in models:
        xs, ys = [], []
        for h in hscores:
            vals = [fnum(r, mk) for r in rows
                    if int(float(r["human_score"])) == h and fnum(r, mk) is not None]
            if vals:
                xs.append(h); ys.append(np.mean(vals))
        ax.plot(xs, ys, "-o", color=col, ms=3.5, lw=1.2, label=f"{lab}", zorder=5)

    ax.set_xlabel("Human score (0–7 IMO scale)")
    ax.set_ylabel("Mean judge score")
    ax.set_xlim(-0.3, 7.4)
    ax.set_ylim(-0.3, 7.4)
    ax.set_xticks(range(0, 8))
    ax.set_yticks(range(0, 8))
    # bias annotations as legend-ish text
    ax.text(0.05, 7.25, "Gemma over-credits", color=C["gemma"], fontsize=6.2, va="top")
    ax.text(0.05, 6.75, "GPT-OSS ≈ calibrated", color=C["gptoss"], fontsize=6.2, va="top")
    ax.text(0.05, 6.25, "DeepSeek under-credits", color=C["deepseek"], fontsize=6.2, va="top")
    ax.legend(loc="lower right", handletextpad=0.4, borderpad=0.3)
    _finish(ax)
    _save(fig, "fig5_calibration_bias")


# ============================================================================
# Fig 6 -- The single-model leader is sample-dependent (rank flip)
# ============================================================================
def fig6_rank_flip():
    rows = _load_full1000()
    full = {}
    for r in rows:
        if r["group"] == "individual":
            n = r["system"].lower()
            key = "gptoss" if "gpt-oss" in n else "deepseek" if "deepseek" in n else "gemma"
            full[key] = (float(r["pass_agree"]), float(r["pa_ci_lo"]), float(r["pa_ci_hi"]))

    fig, ax = plt.subplots(figsize=(COL, 2.7))
    x0, x1 = 0, 1
    models = ["gptoss", "deepseek", "gemma"]
    labs = {"gptoss": "GPT-OSS", "deepseek": "DeepSeek", "gemma": "Gemma"}
    # small per-model horizontal offset so the overlapping CIs are legible
    xoff = {"gptoss": -0.015, "deepseek": 0.015, "gemma": 0.0}
    for key in models:
        pa0, lo0, hi0 = VAL[key][1], VAL[key][2], VAL[key][3]
        pa1, lo1, hi1 = full[key]
        col = C[key]
        ox = xoff[key]
        xa, xb = x0 + ox, x1 + ox
        ax.plot([xa, xb], [pa0, pa1], "-", color=col, lw=1.6, zorder=4)
        ax.errorbar(xa, pa0, yerr=[[pa0 - lo0], [hi0 - pa0]], fmt="o", ms=5.5,
                    color=col, ecolor=col, elinewidth=1.0, capsize=2, mec="white", mew=0.6, zorder=5)
        ax.errorbar(xb, pa1, yerr=[[pa1 - lo1], [hi1 - pa1]], fmt="o", ms=5.5,
                    color=col, ecolor=col, elinewidth=1.0, capsize=2, mec="white", mew=0.6, zorder=5)
        ax.annotate(labs[key], (xa, pa0), xytext=(-9, 0), textcoords="offset points",
                    fontsize=6.4, color=col, ha="right", va="center", fontweight="bold")
        ax.annotate(f"{pa1:.3f}", (xb, pa1), xytext=(9, 0), textcoords="offset points",
                    fontsize=6.4, color=col, ha="left", va="center")

    ax.text((x0 + x1) / 2, 0.9125,
            "leader flips:\nGPT-OSS ↔ DeepSeek", ha="center", va="center",
            fontsize=6.4, color="0.25", style="italic")
    ax.set_xticks([x0, x1])
    ax.set_xticklabels(["Validation\n(n = 200)", "Full benchmark\n(n = 1000)"])
    ax.set_xlim(-0.46, 1.40)
    ax.set_ylim(0.733, 0.93)
    ax.set_ylabel("Pass / fail agreement with humans")
    ax.grid(True, axis="y")
    _finish(ax)
    _save(fig, "fig6_leader_rank_flip")


# ============================================================================
# Fig 7 -- Forest plot (alt. headline): pass-agreement CIs + cost
# ============================================================================
def fig7_forest():
    fig, ax = plt.subplots(figsize=(COL, 2.7))
    # sort by pass-agree ascending so best on top
    items = sorted(VAL.items(), key=lambda kv: kv[1][1])
    ys = np.arange(len(items))
    for y, (key, (lab, pa, lo, hi, rho, cost, tier)) in zip(ys, items):
        col = C[key]
        # CI as an error bar with little end-tips
        ax.errorbar(pa, y, xerr=[[pa - lo], [hi - pa]], fmt="none", ecolor=col,
                    elinewidth=2.2, capsize=3.5, capthick=1.2, alpha=0.9, zorder=3)
        ax.scatter(pa, y, s=34, color=col, edgecolor="white", linewidth=0.7, zorder=5)
        cost_str = f"${cost:,.2f}"
        if tier == "frontier":
            # draw the eye to how costly the frontier is: larger + outlined
            ax.text(0.966, y, cost_str, fontsize=7.8, color=col, va="center",
                    ha="right", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=col, lw=0.8))
        else:
            ax.text(0.966, y, cost_str, fontsize=6.8, color=col, va="center",
                    ha="right", fontweight="bold")
    # vertical guide at top point estimate
    top_pa = max(v[1] for v in VAL.values())
    ax.axvline(top_pa, color="0.7", lw=0.7, ls=(0, (3, 3)), zorder=1)

    ax.set_yticks(ys)
    ax.set_yticklabels([v[0] for _, v in items])
    for t, (key, v) in zip(ax.get_yticklabels(), items):
        t.set_color(C[key])
    ax.set_xlim(0.72, 0.985)
    ax.set_ylim(-0.6, len(items) - 0.35)
    ax.set_xlabel("Pass / fail agreement with humans  (95% CI)")
    ax.text(0.966, len(items) - 0.45, "cost / 200", fontsize=6.4, color="0.3",
            va="bottom", ha="right", style="italic")
    ax.grid(True, axis="x")
    _finish(ax)
    _save(fig, "fig7_forest")


# ============================================================================
# Gallery contact sheet
# ============================================================================
def gallery():
    names = ["fig1_cost_frontier", "fig2_passfail_vs_rank", "fig3_precision_recall_dial",
             "fig4_run_stability", "fig5_calibration_bias", "fig6_leader_rank_flip",
             "fig7_forest"]
    titles = ["1. Cost–accuracy frontier (alt. headline)",
              "2. Pass/fail vs. rank correlation (appendix)",
              "3. Precision/recall dial, n=1000 (rec.)",
              "4. Run-to-run stability, 4 runs (rec.)",
              "5. Calibration / offsetting biases",
              "6. Leader is sample-dependent",
              "7. Forest plot (HEADLINE — rec.)"]
    ncol, nrow = 3, 3
    fig, axes = plt.subplots(nrow, ncol, figsize=(11, 9.2))
    for ax in axes.ravel():
        ax.axis("off")
    for i, (nm, ti) in enumerate(zip(names, titles)):
        ax = axes.ravel()[i]
        img = plt.imread(os.path.join(HERE, f"{nm}.png"))
        ax.imshow(img)
        ax.set_title(ti, fontsize=10, fontweight="bold", pad=4)
    fig.suptitle("Plot candidates — cheap LLM proof judges (ICML 2026 AI4Math)",
                 fontsize=12, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(os.path.join(HERE, "GALLERY.png"), dpi=140)
    plt.close(fig)
    print("  wrote GALLERY.png")


if __name__ == "__main__":
    print("Regenerating the paper figures (run compute_metrics.py first) ...")
    fig7_forest()            # Figure 1
    fig6_rank_flip()         # Figure 2
    fig3_pr_dial()           # Figure 3
    fig4_stability()         # Figure 4
    fig2_passfail_vs_rank()  # Figure 5
    print("Done. Figures written to", os.path.normpath(FIGDIR))
