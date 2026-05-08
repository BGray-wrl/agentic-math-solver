from __future__ import annotations

import csv
import math
import os
from collections import defaultdict
from pathlib import Path

PLOT_DIR = Path(__file__).resolve().parent
ROOT = PLOT_DIR.parents[1]
GALLERY_DIR = PLOT_DIR / "candidate_gallery"
GALLERY_DIR.mkdir(parents=True, exist_ok=True)
(PLOT_DIR / ".mplconfig").mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(PLOT_DIR / ".mplconfig"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PALETTE = {
    "blue": "#4477AA",
    "cyan": "#66CCEE",
    "green": "#228833",
    "yellow": "#CCBB44",
    "red": "#EE6677",
    "purple": "#AA3377",
    "grey": "#777777",
    "black": "#222222",
}

MODEL_LABELS = {
    "deepseek-v4-flash": "DS-v4-flash",
    "deepseek-v4-pro": "DS-v4-pro",
    "gemini-3-flash-preview": "Gemini-3-flash",
    "gemma-4-31b-it": "Gemma-4-31B",
    "gpt-oss-120b": "GPT-OSS-120B",
    "qwen3.6-35b-a3b": "Qwen3.6-35B",
    "gpt-5.4-nano": "GPT-5.4-nano",
    "gemini-3.1-pro-preview": "Gemini-3.1-pro",
    "kimi-k2.6": "Kimi-k2.6",
    "qwen3.6-max-preview": "Qwen3.6-max",
    "gpt-5.4": "GPT-5.4",
}

MODE_LABELS = {
    "generate": "pass@3",
    "seed_generate": "seeded",
    "full": "G-V-R",
    "seed_full": "seeded G-V-R",
}

JUDGES = [
    ("v4flash_score", "v4flash_pass", "v4-flash"),
    ("v4pro_score", None, "v4-pro"),
    ("gemini_score", None, "Gemini"),
]


def read_csv(rel_path: str) -> list[dict[str, str]]:
    with (ROOT / rel_path).open(newline="") as f:
        return list(csv.DictReader(f))


def fnum(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def truthy_pass(row: dict[str, str], score_col: str, pass_col: str | None = None) -> bool | None:
    if pass_col and row.get(pass_col) in ("True", "False"):
        return row[pass_col] == "True"
    score = fnum(row.get(score_col))
    if score is None:
        return None
    return score >= 6


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(GALLERY_DIR / name, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "grid.linewidth": 0.5,
            "grid.alpha": 0.28,
            "figure.dpi": 120,
        }
    )


def plot_judge_flip_deltas() -> None:
    rows = [
        r
        for r in read_csv("results/architecture_20260506/trials.csv")
        if r["source_experiment"] == "phase1" and r["mode"] in ("generate", "full")
    ]
    models = [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "gemini-3-flash-preview",
        "gemma-4-31b-it",
        "gpt-oss-120b",
        "qwen3.6-35b-a3b",
    ]
    mat = np.full((len(JUDGES), len(models)), np.nan)
    for j, (score_col, _, _) in enumerate(JUDGES):
        for i, model in enumerate(models):
            gen = [fnum(r[score_col]) for r in rows if r["model_short"] == model and r["mode"] == "generate"]
            full = [fnum(r[score_col]) for r in rows if r["model_short"] == model and r["mode"] == "full"]
            gen = [v for v in gen if v is not None]
            full = [v for v in full if v is not None]
            if gen and full:
                mat[j, i] = mean(full) - mean(gen)

    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    im = ax.imshow(mat, cmap="RdBu_r", vmin=-1.0, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(models)), [MODEL_LABELS[m] for m in models], rotation=30, ha="right")
    ax.set_yticks(range(len(JUDGES)), [j[2] for j in JUDGES])
    ax.set_title("Pipeline lift flips sign under the lenient judge")
    for y in range(mat.shape[0]):
        for x in range(mat.shape[1]):
            v = mat[y, x]
            ax.text(x, y, f"{v:+.2f}", ha="center", va="center", fontsize=8, color="white" if abs(v) > 0.55 else "#222")
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Mean score delta: G-V-R minus pass@3")
    save(fig, "candidate_01_judge_flip_deltas.png")


def plot_pass_confusion() -> None:
    rows = [
        r
        for r in read_csv("results/architecture_20260506/trials.csv")
        if r["v4flash_score"] and r["v4pro_score"] and r["gemini_score"]
    ]
    comparisons = [
        ("v4flash_score", "v4-flash", "Gemini"),
        ("v4pro_score", "v4-pro", "Gemini"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 3.0))
    for ax, (strict_col, strict_label, loose_label) in zip(axes, comparisons):
        counts = np.zeros((2, 2), dtype=int)
        for r in rows:
            strict = fnum(r[strict_col]) >= 6
            loose = fnum(r["gemini_score"]) >= 6
            counts[int(strict), int(loose)] += 1
        pct = counts / counts.sum()
        im = ax.imshow(pct, cmap="Blues", vmin=0, vmax=max(0.7, pct.max()))
        ax.set_xticks([0, 1], [f"{loose_label}\nfail", f"{loose_label}\npass"])
        ax.set_yticks([0, 1], [f"{strict_label}\nfail", f"{strict_label}\npass"])
        ax.set_title(f"{strict_label} vs Gemini")
        for y in range(2):
            for x in range(2):
                ax.text(x, y, f"{counts[y, x]}\n{100*pct[y, x]:.1f}%", ha="center", va="center", fontsize=9)
    fig.suptitle("Gemini lenience is mostly one-sided at the pass threshold", y=1.03, fontsize=10)
    save(fig, "candidate_02_pass_confusion_matrices.png")


def plot_score_distribution_modes() -> None:
    rows = [
        r
        for r in read_csv("results/architecture_20260506/trials.csv")
        if r["source_experiment"] == "phase1" and r["v4flash_score"] and r["mode"] in ("generate", "seed_generate", "full")
    ]
    modes = ["generate", "seed_generate", "full"]
    data = [[float(r["v4flash_score"]) for r in rows if r["mode"] == mode] for mode in modes]
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    parts = ax.violinplot(data, showmeans=True, showextrema=False, widths=0.78)
    for i, body in enumerate(parts["bodies"]):
        body.set_facecolor([PALETTE["blue"], PALETTE["green"], PALETTE["purple"]][i])
        body.set_edgecolor("none")
        body.set_alpha(0.55)
    parts["cmeans"].set_color(PALETTE["black"])
    parts["cmeans"].set_linewidth(1.2)
    rng = np.random.default_rng(7)
    for i, vals in enumerate(data, start=1):
        jitter = rng.uniform(-0.08, 0.08, size=len(vals))
        ax.scatter(np.full(len(vals), i) + jitter, vals, s=7, color="#222222", alpha=0.10, linewidths=0)
    ax.set_xticks(range(1, 4), [MODE_LABELS[m] for m in modes])
    ax.set_ylabel("v4-flash score (0-7)")
    ax.set_title("The clean Phase 1 architectures have nearly identical score distributions")
    ax.set_ylim(-0.25, 7.25)
    ax.grid(axis="y")
    save(fig, "candidate_03_phase1_score_distributions.png")


def plot_scaling_frontier() -> None:
    rows = [r for r in read_csv("results/scaling_20260506/summary.csv") if r["mean_pass_at_n_v4flash"]]
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    wanted = [
        ("scaling_v4flash", "deepseek-v4-flash", "default", "DS-v4-flash", PALETTE["blue"], "D"),
        ("scaling_reasoning", "gemma-4-31b-it", "max", "Gemma max", PALETTE["green"], "s"),
        ("scaling_reasoning", "gpt-oss-120b", "max", "GPT-OSS max", PALETTE["purple"], "^"),
        ("scaling", "gemma-4-31b-it", "default", "Gemma default", PALETTE["yellow"], "o"),
        ("scaling", "gpt-oss-120b", "default", "GPT-OSS default", PALETTE["grey"], "v"),
    ]
    for source, model, reasoning, label, color, marker in wanted:
        pts = [
            (int(r["n"]), float(r["mean_pass_at_n_v4flash"]))
            for r in rows
            if r["source_experiment"] == source and r["model_short"] == model and r["reasoning"] == reasoning
        ]
        pts.sort()
        if not pts:
            continue
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker=marker, color=color, linewidth=1.8, label=label)

    arch = read_csv("results/architecture_20260506/summary.csv")
    refs = [
        ("deepseek-v4-flash", "default", "seed_full", PALETTE["blue"], "DS seed_full"),
        ("gemma-4-31b-it", "max", "seed_full", PALETTE["green"], "Gemma max seed_full"),
        ("gpt-oss-120b", "max", "seed_full", PALETTE["purple"], "GPT-OSS max seed_full"),
    ]
    for model, reasoning, mode, color, label in refs:
        vals = [
            float(r["mean_score_v4flash"])
            for r in arch
            if r["model_short"] == model and r["reasoning"] == reasoning and r["mode"] == mode and r["mean_score_v4flash"]
        ]
        if vals:
            y = mean(vals)
            ax.scatter([9], [y], s=155, marker="*", color=color, edgecolor=PALETTE["black"], linewidth=0.7, zorder=4)
            ax.text(9.25, y, label, color=color, fontsize=8, va="center")

    ax.set_xlim(0.5, 12.0)
    ax.set_ylim(0, 5.1)
    ax.set_xticks([1, 3, 5, 7, 9])
    ax.set_xlabel("Approximate generation budget k")
    ax.set_ylabel("Mean v4-flash score")
    ax.set_title("Pure sampling is a hard baseline for seeded pipelines")
    ax.grid(True)
    ax.legend(frameon=False, ncols=2, loc="upper left")
    save(fig, "candidate_04_sampling_frontier_vs_seed_full.png")


def plot_marginal_passn_gains() -> None:
    rows = [r for r in read_csv("results/scaling_20260506/summary.csv") if r["pass_rate_v4flash"]]
    series = defaultdict(dict)
    for r in rows:
        key = (r["source_experiment"], r["model_short"], r["reasoning"])
        series[key][int(r["n"])] = 100 * float(r["pass_rate_v4flash"])
    wanted = [
        (("scaling_v4flash", "deepseek-v4-flash", "default"), "DS-v4-flash"),
        (("scaling_reasoning", "gemma-4-31b-it", "max"), "Gemma max"),
        (("scaling_reasoning", "gpt-oss-120b", "max"), "GPT-OSS max"),
        (("scaling", "gemma-4-31b-it", "default"), "Gemma default"),
        (("scaling", "gpt-oss-120b", "default"), "GPT-OSS default"),
    ]
    intervals = [(1, 3), (3, 5), (5, 7)]
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    x = np.arange(len(wanted))
    width = 0.22
    colors = [PALETTE["blue"], PALETTE["green"], PALETTE["purple"]]
    for idx, (lo, hi) in enumerate(intervals):
        gains = []
        for key, _ in wanted:
            vals = series.get(key, {})
            gains.append(vals.get(hi, 0) - vals.get(lo, 0))
        ax.bar(x + (idx - 1) * width, gains, width, color=colors[idx], label=f"k={lo}->{hi}")
    ax.axhline(0, color="#222", linewidth=0.7)
    ax.set_xticks(x, [label for _, label in wanted], rotation=25, ha="right")
    ax.set_ylabel("Marginal pass-rate gain (pp)")
    ax.set_title("Sampling gains persist beyond k=3")
    ax.grid(axis="y")
    ax.legend(frameon=False, ncols=3)
    save(fig, "candidate_05_marginal_passn_gains.png")


def plot_cost_accuracy_pareto() -> None:
    rows = [
        r
        for r in read_csv("results/answerbench_calibration_20260506/summary.csv")
        if r["accuracy"] and r["cost_per_run_usd"] and int(r["n_valid"]) >= 43
    ]
    extra = [
        r
        for r in read_csv("results/expensive_models_calibration_20260506/summary.csv")
        if r["accuracy"] and r["cost_per_run_usd"]
    ]
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    for r in rows + extra:
        x = float(r["cost_per_run_usd"])
        y = 100 * float(r["accuracy"])
        is_extra = r in extra
        color = PALETTE["red"] if is_extra else PALETTE["blue"]
        marker = "D" if is_extra else "o"
        ax.scatter(x, y, s=56, color=color, marker=marker, alpha=0.85, edgecolor="white", linewidth=0.6)
        label = MODEL_LABELS.get(r["model"], r["model"])
        config = r["model_config"].replace("_effective_synthesized", "")
        ax.text(x * 1.08, y, f"{label}\n{config}", fontsize=7, va="center")
    ax.set_xscale("log")
    ax.set_xlim(0.0008, 0.5)
    ax.set_ylim(45, 103)
    ax.set_xlabel("Cost per AnswerBench run, log scale ($)")
    ax.set_ylabel("AnswerBench accuracy (%)")
    ax.set_title("Generator calibration: capability-cost Pareto view")
    ax.grid(True, which="both")
    save(fig, "candidate_06_answerbench_cost_accuracy_pareto.png")


def plot_judge_calibration_pareto() -> None:
    rows = [
        r
        for r in read_csv("results/gradingbench_calibration_20260506/summary.csv")
        if r["pass_agree_at_6"] and r["mean_cost_per_call"] and int(r["n_valid"]) >= 175
    ]
    fig, ax = plt.subplots(figsize=(6.8, 4.1))
    for r in rows:
        x = float(r["mean_cost_per_call"])
        y = 100 * float(r["pass_agree_at_6"])
        size = 55 + 170 * max(float(r["f1_at_6"]), 0)
        color = PALETTE["green"] if r["judge_id"] == "deepseek-v4-flash" else PALETTE["blue"]
        if "gemini" in r["judge_id"]:
            color = PALETTE["red"]
        elif "gpt-oss" in r["judge_id"] or "gemma" in r["judge_id"]:
            color = PALETTE["grey"]
        ax.scatter(x, y, s=size, color=color, alpha=0.78, edgecolor="white", linewidth=0.6)
        ax.text(x * 1.07, y, f"{MODEL_LABELS.get(r['judge_id'], r['judge_id'])}\n{r['reasoning_config']}", fontsize=7, va="center")
    ax.set_xscale("log")
    ax.set_xlim(0.0005, 0.06)
    ax.set_ylim(62, 91)
    ax.set_xlabel("Mean cost per judge call, log scale ($)")
    ax.set_ylabel("Pass/fail agreement with human labels (%)")
    ax.set_title("Judge choice is a cost-calibration tradeoff")
    ax.grid(True, which="both")
    save(fig, "candidate_07_judge_calibration_pareto.png")


def short_model(model_id: str) -> str:
    if "gemma" in model_id:
        return "Gemma"
    if "gpt-oss" in model_id:
        return "GPT-OSS"
    if "deepseek-v4-pro" in model_id:
        return "DS-pro"
    if "deepseek-v4-flash" in model_id:
        return "DS-flash"
    return model_id.split("/")[-1]


def plot_role_swap_matrix() -> None:
    rows = [
        r
        for r in read_csv("results/roleswap_20260506/summary.csv")
        if r["subclass"] == "oss_gemma_8cell" and r["reasoning"] == "max" and r["mean_score_v4flash"]
    ]
    cells = defaultdict(list)
    for r in rows:
        gen = short_model(r["generator_model"])
        ver = short_model(r["verifier_model"])
        rev = short_model(r["reviser_model"])
        cells[(gen, ver, rev)].append(float(r["mean_score_v4flash"]))
    labels = []
    vals = []
    for (gen, ver, rev), scores in sorted(cells.items(), key=lambda kv: mean(kv[1]), reverse=True):
        labels.append(f"G:{gen}  V:{ver}  R:{rev}")
        vals.append(mean(scores))
    labels = labels[:10]
    vals = vals[:10]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    y = np.arange(len(vals))
    colors = [PALETTE["green"] if "V:GPT-OSS" in label else PALETTE["grey"] for label in labels]
    ax.barh(y, vals, color=colors)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 4.3)
    ax.set_xlabel("Mean v4-flash score")
    ax.set_title("Role-swap candidates show large cell-to-cell variation")
    ax.grid(axis="x")
    for yi, v in zip(y, vals):
        ax.text(v + 0.05, yi, f"{v:.2f}", va="center", fontsize=8)
    save(fig, "candidate_08_role_swap_top_cells.png")


def plot_research_problem_judge_gap() -> None:
    rows = [
        r
        for r in read_csv("results/architecture_20260506/trials.csv")
        if r["is_26_research"] == "True" and r["v4flash_score"] and r["v4pro_score"] and r["gemini_score"]
    ]
    problems = sorted({r["problem_id"] for r in rows})
    data = []
    for p in problems:
        rs = [r for r in rows if r["problem_id"] == p]
        v4f = sum(float(r["v4flash_score"]) >= 6 for r in rs)
        v4p = sum(float(r["v4pro_score"]) >= 6 for r in rs)
        gem = sum(float(r["gemini_score"]) >= 6 for r in rs)
        diff = gem - max(v4f, v4p)
        data.append((diff, p, v4f, v4p, gem, len(rs)))
    data.sort(reverse=True)
    labels = [d[1].replace("-official", "").replace("first-proof", "FP").replace("erdos", "E") for d in data]
    x = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(7.4, 3.7))
    width = 0.25
    ax.bar(x - width, [d[2] for d in data], width, label="v4-flash", color=PALETTE["blue"])
    ax.bar(x, [d[3] for d in data], width, label="v4-pro", color=PALETTE["green"])
    ax.bar(x + width, [d[4] for d in data], width, label="Gemini", color=PALETTE["red"])
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_ylabel("Pass judgments")
    ax.set_title("Research-problem solve counts expose where lenient judging matters")
    ax.grid(axis="y")
    ax.legend(frameon=False, ncols=3)
    save(fig, "candidate_09_research_problem_judge_gap.png")


def plot_difficulty_score_heatmap() -> None:
    rows = [
        r
        for r in read_csv("results/architecture_20260506/trials.csv")
        if r["v4flash_score"] and r["mode"] in ("generate", "seed_generate", "full", "seed_full")
    ]
    difficulties = [
        (0, "pre-comp"),
        (1, "comp-hard"),
        (2, "research-easy"),
        (3, "research-med"),
        (4, "research-hard"),
        (5, "research-frontier"),
    ]
    modes = ["generate", "seed_generate", "full", "seed_full"]
    mat = np.full((len(difficulties), len(modes)), np.nan)
    for i, (difficulty, _) in enumerate(difficulties):
        for j, mode in enumerate(modes):
            vals = [
                float(r["v4flash_score"])
                for r in rows
                if int(r["difficulty"]) == difficulty and r["mode"] == mode
            ]
            if vals:
                mat[i, j] = mean(vals)
    fig, ax = plt.subplots(figsize=(6.6, 3.7))
    im = ax.imshow(mat, cmap="YlGnBu", vmin=0, vmax=7, aspect="auto")
    ax.set_xticks(range(len(modes)), [MODE_LABELS[m] for m in modes], rotation=20, ha="right")
    ax.set_yticks(range(len(difficulties)), [d[1] for d in difficulties])
    ax.set_title("Difficulty dominates architecture choice")
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            if not math.isnan(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=8)
            else:
                ax.text(j, i, "-", ha="center", va="center", fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
    cbar.set_label("Mean v4-flash score")
    save(fig, "candidate_10_difficulty_mode_heatmap.png")


def write_readme() -> None:
    entries = [
        ("candidate_01_judge_flip_deltas.png", "Heatmap of G-V-R minus pass@3 by model and judge; highlights the judge-dependent sign flip."),
        ("candidate_02_pass_confusion_matrices.png", "Pass/fail confusion matrices for strict judges versus Gemini; shows one-sided Gemini lenience."),
        ("candidate_03_phase1_score_distributions.png", "Phase 1 score distributions by architecture under the canonical judge; visual support for near-null architecture effects."),
        ("candidate_04_sampling_frontier_vs_seed_full.png", "Pass@k mean-score frontier with seed_full stars at k=9 equivalent; direct baseline comparison."),
        ("candidate_05_marginal_passn_gains.png", "Incremental pass-rate gains from k=1->3, 3->5, and 5->7; shows scaling still has slope."),
        ("candidate_06_answerbench_cost_accuracy_pareto.png", "AnswerBench capability versus cost, including the small expensive-model calibration bucket."),
        ("candidate_07_judge_calibration_pareto.png", "GradingBench judge agreement versus cost; supports the canonical judge choice."),
        ("candidate_08_role_swap_top_cells.png", "Top role-swap cells at reasoning=max; compact view of model-role variation."),
        ("candidate_09_research_problem_judge_gap.png", "Research-problem pass counts by judge; localizes where lenient judging changes the story."),
        ("candidate_10_difficulty_mode_heatmap.png", "Mean score by difficulty and architecture; compact visual of the difficulty gradient."),
    ]
    text = [
        "# Candidate Figure Gallery",
        "",
        "These are exploratory, NeurIPS-style candidate visuals generated from the local result buckets.",
        "They are intended as a menu; pick a small handful rather than including all of them.",
        "",
    ]
    for filename, description in entries:
        text.append(f"- `{filename}`: {description}")
    text.append("")
    text.append("Regenerate with `.venv/bin/python codex_draft_and_work/plots/make_candidate_gallery.py` from the repository root.")
    text.append("A thumbnail overview is available as `contact_sheet.png`.")
    (GALLERY_DIR / "README.md").write_text("\n".join(text) + "\n")


def write_contact_sheet() -> None:
    paths = sorted(GALLERY_DIR.glob("candidate_*.png"))
    thumbs = []
    for path in paths:
        image = plt.imread(path)
        thumbs.append((path, image))

    fig, axes = plt.subplots(5, 2, figsize=(11.0, 14.5))
    for ax, (path, image) in zip(axes.flat, thumbs):
        ax.imshow(image)
        ax.set_title(path.name.replace(".png", ""), fontsize=9)
        ax.axis("off")
    for ax in axes.flat[len(thumbs) :]:
        ax.axis("off")
    fig.suptitle("Candidate figure gallery contact sheet", fontsize=12, y=0.995)
    fig.tight_layout()
    fig.savefig(GALLERY_DIR / "contact_sheet.png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    apply_style()
    plot_judge_flip_deltas()
    plot_pass_confusion()
    plot_score_distribution_modes()
    plot_scaling_frontier()
    plot_marginal_passn_gains()
    plot_cost_accuracy_pareto()
    plot_judge_calibration_pareto()
    plot_role_swap_matrix()
    plot_research_problem_judge_gap()
    plot_difficulty_score_heatmap()
    write_contact_sheet()
    write_readme()
    print(f"Wrote candidate gallery to {GALLERY_DIR}")
    for path in sorted(GALLERY_DIR.glob("candidate_*.png")):
        print(f" - {path.name}")


if __name__ == "__main__":
    main()
