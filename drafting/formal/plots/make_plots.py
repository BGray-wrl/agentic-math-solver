"""Generate figures for the paper draft from existing per-experiment data.

Run from the repo root:
    source .venv/bin/activate
    python3 drafting/plots/make_plots.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

PLOTS_DIR = Path("drafting/plots")
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------
# Plot 1: Judge sensitivity — per-mode means under each judge, by model
# ----------------------------------------------------------------------------

phase1_cells = {
    "DS-v4-flash":   {"generate": (3.22, 3.39, 4.81), "seed_gen": (3.41, 3.30, 5.01), "full": (3.38, 3.09, 4.63)},
    "DS-v4-pro":     {"generate": (3.53, 3.38, 5.56), "seed_gen": (3.41, 3.36, 5.30), "full": (3.85, 3.66, 5.35)},
    "Gemini-3-flash":{"generate": (1.83, 1.83, 2.93), "seed_gen": (1.54, 1.87, 3.39), "full": (1.59, 1.29, 3.76)},
    "Gemma-4-31B":   {"generate": (1.49, 1.83, 3.21), "seed_gen": (1.49, 1.53, 2.99), "full": (1.39, 1.17, 3.51)},
    "GPT-OSS-120B":  {"generate": (1.34, 1.33, 2.59), "seed_gen": (1.09, 1.27, 2.40), "full": (1.58, 1.39, 3.10)},
    "Qwen3.6-35B":   {"generate": (2.09, 2.17, 3.60), "seed_gen": (2.10, 2.06, 3.21), "full": (1.62, 1.44, 3.74)},
}

modes = ["generate", "seed_gen", "full"]
judges = ["v4-flash", "v4-pro", "Gemini-3-flash"]
judge_colors = {"v4-flash": "#1f77b4", "v4-pro": "#2ca02c", "Gemini-3-flash": "#d62728"}

fig, axes = plt.subplots(2, 3, figsize=(11.5, 6.0), sharey=True)
for ax, (model, by_mode) in zip(axes.flat, phase1_cells.items()):
    x = np.arange(len(modes))
    width = 0.27
    for i, judge in enumerate(judges):
        vals = [by_mode[m][i] for m in modes]
        ax.bar(x + (i - 1) * width, vals, width, label=judge, color=judge_colors[judge])
    ax.set_title(model, fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(modes, fontsize=9)
    ax.set_ylim(0, 6.0)
    ax.grid(True, axis="y", alpha=0.25, linestyle=":")
    ax.set_axisbelow(True)
axes[0, 0].set_ylabel("Mean score (0-7)")
axes[1, 0].set_ylabel("Mean score (0-7)")
handles, labels = axes[0, 0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.02), frameon=False)
fig.suptitle("Mean PB+R26 score by architecture, under each judge (Phase 1, default reasoning)", fontsize=11, y=1.07)
fig.tight_layout()
fig.savefig(PLOTS_DIR / "fig1_judge_sensitivity.png", dpi=180, bbox_inches="tight")
plt.close(fig)

# ----------------------------------------------------------------------------
# Plot 2: Pass@k scaling curves WITH 95% bootstrap CIs as shaded ribbons
# ----------------------------------------------------------------------------

# (n, mean, ci_lo, ci_hi) — current scaling_20260506 data with M=9 expansion
# (all five cells now run on n=70 problems with 9 branches each).
scaling = {
    "Gemma-4-31B (default)": [
        (1, 0.88, 0.49, 1.32), (3, 1.54, 0.99, 2.13),
        (5, 1.93, 1.30, 2.59), (7, 2.20, 1.51, 2.92),
        (9, 2.41, 1.66, 3.18)],
    "Gemma-4-31B (max)": [
        (1, 1.92, 1.37, 2.51), (3, 2.76, 2.06, 3.49),
        (5, 3.05, 2.30, 3.81), (7, 3.20, 2.45, 4.00),
        (9, 3.29, 2.55, 4.05)],
    "GPT-OSS-120B (default)": [
        (1, 0.82, 0.42, 1.27), (3, 1.27, 0.74, 1.85),
        (5, 1.47, 0.86, 2.13), (7, 1.61, 0.95, 2.32),
        (9, 1.71, 1.04, 2.45)],
    "GPT-OSS-120B (max)": [
        (1, 1.63, 1.10, 2.20), (3, 2.45, 1.78, 3.16),
        (5, 2.81, 2.07, 3.55), (7, 3.05, 2.30, 3.81),
        (9, 3.23, 2.46, 3.96)],
    "DS-v4-flash (default)": [
        (1, 2.78, 2.13, 3.43), (3, 3.70, 3.00, 4.41),
        (5, 4.01, 3.30, 4.71), (7, 4.32, 3.58, 5.04),
        (9, 4.54, 3.78, 5.25)],
}

color_map = {
    "DS-v4-flash (default)":  "#7b3294",
    "Gemma-4-31B (max)":      "#e08214",
    "GPT-OSS-120B (max)":     "#b2182b",
    "Gemma-4-31B (default)":  "#67a9cf",
    "GPT-OSS-120B (default)": "#969696",
}

fig, ax = plt.subplots(figsize=(7.6, 4.6))
markers = {"DS-v4-flash (default)": "D", "Gemma-4-31B (max)": "s",
           "GPT-OSS-120B (max)": "^", "Gemma-4-31B (default)": "o",
           "GPT-OSS-120B (default)": "v"}
for label, points in scaling.items():
    ks = [p[0] for p in points]
    means = [p[1] for p in points]
    los = [p[2] for p in points]
    his = [p[3] for p in points]
    color = color_map[label]
    ax.plot(ks, means, marker=markers[label], linewidth=1.6, label=label,
            markersize=6, color=color)
    ax.fill_between(ks, los, his, color=color, alpha=0.13)

# overlay seed_full pipeline reference points at their token-equivalent k=9 budget
seed_full_refs = [
    ("DS-v4-flash seed_full",       9, 3.49, "#7b3294"),
    ("Gemma-4-31B (max) seed_full", 9, 3.31, "#e08214"),
    ("GPT-OSS-120B (max) seed_full",9, 3.00, "#b2182b"),
]
for label, x, y, color in seed_full_refs:
    ax.scatter([x], [y], marker="*", s=240, edgecolor="black",
               facecolor=color, zorder=5)

ax.text(9.2, 3.49, "seed_full DS-flash", fontsize=8, va="center", color="#7b3294")
ax.text(9.2, 3.31, "seed_full Gemma max", fontsize=8, va="center", color="#e08214")
ax.text(9.2, 3.00, "seed_full GPT-OSS max", fontsize=8, va="center", color="#b2182b")
ax.set_xlim(0.5, 13.5)

ax.set_xlabel("k (best-of-k samples)")
ax.set_ylabel("Mean v4-flash score (0-7)")
ax.set_title("pass@k scaling with 95% bootstrap CIs; seed_full plotted at k=9 token-equivalent")
ax.set_xticks([1, 3, 5, 7, 9])
ax.grid(True, alpha=0.25, linestyle=":")
ax.legend(loc="upper left", fontsize=8.5, framealpha=0.9)
fig.tight_layout()
fig.savefig(PLOTS_DIR / "fig2_passk_scaling.png", dpi=180, bbox_inches="tight")
plt.close(fig)

# ----------------------------------------------------------------------------
# Plot 3: Forest plot — paired effect sizes with 95% CIs
# ----------------------------------------------------------------------------

# (label, mean, lo, hi, color)
effects = [
    # reasoning toggle on PB+R26 (from A.4 + verification)
    ("reasoning  Gemma seed_full",      1.60, 1.07, 2.14, "#1f77b4"),
    ("reasoning  GPT-OSS seed_full",    1.59, 1.05, 2.13, "#1f77b4"),
    ("reasoning  GPT-OSS seed_gen",     1.45, 0.93, 1.97, "#1f77b4"),
    ("reasoning  Gemma seed_gen",       1.25, 0.74, 1.77, "#1f77b4"),
    ("reasoning  Gemma generate",       1.25, 0.74, 1.77, "#1f77b4"),
    ("reasoning  GPT-OSS generate",     0.96, 0.46, 1.46, "#1f77b4"),
    ("reasoning  GPT-OSS full",         0.85, 0.34, 1.36, "#1f77b4"),
    ("reasoning  Gemma full",           0.78, 0.27, 1.29, "#1f77b4"),
    # architecture deltas (from analysis_v4 section 5)
    ("arch  GPT-OSS max  seed_full–gen", 0.625, 0.094, 1.219, "#d62728"),
    ("arch  Gemma max  seed_full–gen",   0.571, 0.071, 1.114, "#d62728"),
    ("arch  GPT-OSS def  full–gen",      0.269,-0.194, 0.746, "#999999"),
    ("arch  DS-pro def  full–gen",       0.233,-0.467, 0.917, "#999999"),
    ("arch  GPT-OSS max  full–gen",      0.169,-0.492, 0.892, "#999999"),
    ("arch  DS-flash def  seed_full–gen",0.152,-0.485, 0.773, "#999999"),
    ("arch  Gemma def  seed_full–gen",   0.145,-0.377, 0.667, "#999999"),
    ("arch  GPT-OSS def  seed_full–gen", 0.088,-0.441, 0.603, "#999999"),
    ("arch  Gemma def  full–gen",       -0.087,-0.667, 0.449, "#999999"),
    ("arch  Gemma max  full–gen",       -0.571,-1.100,-0.100, "#fdae61"),
]

fig, ax = plt.subplots(figsize=(8.5, 5.6))
y = np.arange(len(effects))
for i, (label, m, lo, hi, color) in enumerate(effects):
    ax.errorbar(m, i, xerr=[[m - lo], [hi - m]], fmt="o", color=color,
                markersize=6, capsize=3, linewidth=1.4)
ax.axvline(0, color="black", linewidth=0.8)
ax.set_yticks(y)
ax.set_yticklabels([e[0] for e in effects], fontsize=8.5)
ax.invert_yaxis()
ax.set_xlabel("Δ mean v4-flash score (0-7), 95% bootstrap CI")
ax.set_title("Paired effect sizes — reasoning toggle (blue) vs. architecture (red=sig pos, "
             "orange=sig neg, grey=null)")
ax.grid(True, axis="x", alpha=0.25, linestyle=":")
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(PLOTS_DIR / "fig3_effect_sizes_forest.png", dpi=180, bbox_inches="tight")
plt.close(fig)

# ----------------------------------------------------------------------------
# Plot 4: Frontier-solves heatmap — ALL trials (architecture ∪ scaling)
# ----------------------------------------------------------------------------

# (problem, difficulty, v4f, v4p, gem, total_cells)
frontier = [
    ("FirstProof 10",      "research-easy",     23, 12,  8, 33),
    ("Erdős 654",          "research-easy",      5,  3,  6, 33),
    ("Erdős 333",          "research-easy",      1,  0,  2, 33),
    ("Erdős 659",          "research-easy",      1,  1,  7, 33),
    ("Erdős 397",          "competition-hard",   1,  0,  1, 33),
    ("FirstProof 5",       "research-medium",    1,  0,  1, 33),
    ("Erdős 1051",         "research-medium",    1,  0, 14, 33),
    ("FirstProof 4",       "research-hard",      0,  0,  1, 32),
    ("FirstProof 6",       "research-hard",      1,  0,  5, 33),
    ("Ramsey hypergraphs", "research-frontier",  0,  0,  3, 33),
]

problems = [f"{p}  ({d})" for (p, d, *_) in frontier]
v4f = [r[2] for r in frontier]
v4p = [r[3] for r in frontier]
gem = [r[4] for r in frontier]
totals = [r[5] for r in frontier]
mat = np.array([v4f, v4p, gem]).T

fig, ax = plt.subplots(figsize=(7.6, 5.0))
im = ax.imshow(mat, cmap="YlOrRd", aspect="auto")
ax.set_xticks([0, 1, 2])
ax.set_xticklabels(["v4-flash (canonical)", "v4-pro (strict audit)", "Gemini-3-flash (lenient)"])
ax.set_yticks(range(len(problems)))
ax.set_yticklabels(problems, fontsize=9)
ax.set_title("R26 frontier-solves per judge — all trials (architecture ∪ scaling)\n"
             "Cells = distinct (model × architecture-or-pass@n × reasoning × source). Total ≈ 33/problem.")
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        v = mat[i, j]
        denom = totals[i]
        ax.text(j, i, f"{int(v)}/{denom}", ha="center", va="center",
                color="white" if v > 8 else "black", fontsize=9)
fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03, label="solving cells")
fig.tight_layout()
fig.savefig(PLOTS_DIR / "fig4_frontier_solves_heatmap.png", dpi=180, bbox_inches="tight")
plt.close(fig)

# ----------------------------------------------------------------------------
# Plot 5: Difficulty gradient — pass rate by tier with 95% CIs
# ----------------------------------------------------------------------------

# (label, n, mean_score, m_lo, m_hi, pass, p_lo, p_hi)
tiers = [
    ("pre-comp\n(PB-Basic)",    231, 6.02, 5.71, 6.30, 0.86, 0.81, 0.90),
    ("comp-hard\n(PB-Adv+E397)",1507, 2.04, 1.88, 2.20, 0.29, 0.27, 0.31),
    ("research-easy",            115, 1.50, 0.99, 2.05, 0.23, 0.16, 0.30),
    ("research-medium",           57, 0.14, 0.00, 0.40, 0.02, 0.00, 0.05),
    ("research-hard",             55, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00),
    ("research-frontier",         27, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00),
]

fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
xs = np.arange(len(tiers))
labels = [t[0] for t in tiers]

# left: pass rate
passes = [t[5] for t in tiers]
plo = [t[5] - t[6] for t in tiers]
phi = [t[7] - t[5] for t in tiers]
axes[0].bar(xs, passes, color="#377eb8", alpha=0.85)
axes[0].errorbar(xs, passes, yerr=[plo, phi], fmt="none", color="black",
                 capsize=4, linewidth=1.0)
for i, (n, p) in enumerate(zip([t[1] for t in tiers], passes)):
    axes[0].text(i, p + 0.04, f"n={n}", ha="center", fontsize=8)
axes[0].set_xticks(xs)
axes[0].set_xticklabels(labels, fontsize=8, rotation=20, ha="right")
axes[0].set_ylim(0, 1.0)
axes[0].set_ylabel("v4-flash pass rate (≥6)")
axes[0].set_title("Pass rate by difficulty tier (95% bootstrap CI)")
axes[0].grid(True, axis="y", alpha=0.25, linestyle=":")
axes[0].set_axisbelow(True)

# right: mean score
means = [t[2] for t in tiers]
mlo = [t[2] - t[3] for t in tiers]
mhi = [t[4] - t[2] for t in tiers]
axes[1].bar(xs, means, color="#984ea3", alpha=0.85)
axes[1].errorbar(xs, means, yerr=[mlo, mhi], fmt="none", color="black",
                 capsize=4, linewidth=1.0)
axes[1].set_xticks(xs)
axes[1].set_xticklabels(labels, fontsize=8, rotation=20, ha="right")
axes[1].set_ylim(0, 7)
axes[1].set_ylabel("Mean v4-flash score (0-7)")
axes[1].set_title("Mean score by difficulty tier (95% bootstrap CI)")
axes[1].grid(True, axis="y", alpha=0.25, linestyle=":")
axes[1].set_axisbelow(True)

fig.tight_layout()
fig.savefig(PLOTS_DIR / "fig5_difficulty_gradient.png", dpi=180, bbox_inches="tight")
plt.close(fig)

# ----------------------------------------------------------------------------
# Plot 6: Architecture lift by tier (forest plot, seed_full - generate)
# ----------------------------------------------------------------------------

# (label, mean, lo, hi, n, p)
lifts = [
    ("seed_full–generate, all (default+max)",     0.315,  0.068, 0.570, 337, 0.013),
    ("    pooled • d=1 comp-hard",                0.325,  0.039, 0.627, 255, 0.032),
    ("    pooled • research-easy (d=2)",          1.000, -0.368, 2.421,  19, 0.322),
    ("    pooled • research-med+ (d≥3)",          0.043,  0.000, 0.130,  23, 1.000),
    ("seed_full–generate, default reasoning",     0.128, -0.182, 0.453, 203, 0.464),
    ("seed_full–generate, reasoning=max",         0.597,  0.231, 0.993, 134, 0.003),
    ("full–generate, all",                       -0.079, -0.272, 0.126, 533, 0.454),
    ("full–generate, R26 only (d≥2)",             0.060, -0.343, 0.493,  67, 1.000),
    ("seed_generate–generate, R26 only (d≥2)",   -0.243, -0.543,-0.029,  70, 0.030),
]

fig, ax = plt.subplots(figsize=(8.6, 4.8))
y = np.arange(len(lifts))
for i, (label, m, lo, hi, n, p) in enumerate(lifts):
    sig = (lo > 0 and hi > 0) or (lo < 0 and hi < 0)
    color = "#1a9850" if (sig and m > 0) else "#d73027" if (sig and m < 0) else "#737373"
    ax.errorbar(m, i, xerr=[[m - lo], [hi - m]], fmt="o", color=color,
                markersize=6, capsize=3, linewidth=1.4)
    ax.text(2.7, i, f"n={n}, p={p:.3f}", fontsize=8, va="center", color="#444")
ax.axvline(0, color="black", linewidth=0.8)
ax.set_yticks(y)
ax.set_yticklabels([e[0] for e in lifts], fontsize=9)
ax.invert_yaxis()
ax.set_xlim(-1.5, 4.0)
ax.set_xlabel("Δ mean v4-flash score (paired, 95% bootstrap CI)")
ax.set_title("Architecture lift by tier and reasoning regime (paired diffs, all v4-flash)")
ax.grid(True, axis="x", alpha=0.25, linestyle=":")
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(PLOTS_DIR / "fig6_lift_by_tier.png", dpi=180, bbox_inches="tight")
plt.close(fig)

print("Wrote 6 figures to", PLOTS_DIR)
for p in sorted(PLOTS_DIR.glob("*.png")):
    print(" -", p.name)
