from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path

PLOT_DIR = Path(__file__).resolve().parent
ROOT = PLOT_DIR.parents[1]
PLOT_DIR.mkdir(parents=True, exist_ok=True)
(PLOT_DIR / ".mplconfig").mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(PLOT_DIR / ".mplconfig"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_csv(rel_path: str) -> list[dict[str, str]]:
    with (ROOT / rel_path).open(newline="") as f:
        return list(csv.DictReader(f))


def fnum(value: str) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(PLOT_DIR / name, dpi=220)
    plt.close(fig)


def plot_judge_calibration() -> None:
    rows = read_csv("results/gradingbench_calibration_20260506/summary.csv")
    keep = [
        "gpt-5.4-nano",
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "gemini-3.1-pro",
        "gpt-oss-120b",
    ]
    filtered = []
    for row in rows:
        if row["judge_id"] in keep and row["reasoning_config"] in ("default", "xhigh"):
            if row["judge_id"] == "gpt-oss-120b" and row["reasoning_config"] != "xhigh":
                continue
            filtered.append(row)
    filtered.sort(key=lambda r: float(r["pass_agree_at_6"]), reverse=True)

    labels = [
        f"{r['judge_id'].replace('deepseek-', 'ds-')}\n{r['reasoning_config']}"
        for r in filtered
    ]
    agree = [100 * float(r["pass_agree_at_6"]) for r in filtered]
    cost = [float(r["mean_cost_per_call"]) for r in filtered]

    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    colors = ["#3b7ea1", "#2f9c67", "#7a6fba", "#d08a2d", "#9a5f5f"]
    ax.bar(labels, agree, color=colors[: len(labels)], width=0.68)
    ax.set_ylim(80, 91)
    ax.set_ylabel("Pass/fail agreement with humans (%)")
    ax.set_title("Judge calibration on IMO-GradingBench")
    ax.grid(axis="y", alpha=0.25)
    for i, (a, c) in enumerate(zip(agree, cost)):
        ax.text(i, a + 0.15, f"{a:.1f}%\n${c:.4f}", ha="center", va="bottom", fontsize=8)
    save(fig, "fig1_judge_calibration.png")


def plot_architecture_modes() -> None:
    rows = read_csv("results/architecture_20260506/trials.csv")
    modes = ["generate", "seed_generate", "full", "seed_full"]
    labels = ["pass@3", "seeded", "G-V-R", "seeded G-V-R"]

    def pass_rate(row_filter):
        rates = []
        for mode in modes:
            rs = [
                r
                for r in rows
                if r["mode"] == mode and r["v4flash_score"] and row_filter(r)
            ]
            rates.append(100 * sum(r["v4flash_pass"] == "True" for r in rs) / len(rs) if rs else None)
        return rates

    phase1 = pass_rate(lambda r: r["source_experiment"] == "phase1")
    all_rows = pass_rate(lambda r: True)

    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    x = range(len(modes))
    width = 0.34
    ax.bar([i - width / 2 for i in x], [v or 0 for v in phase1], width, label="Clean Phase 1", color="#4c78a8")
    ax.bar([i + width / 2 for i in x], [v or 0 for v in all_rows], width, label="All architecture rows", color="#f58518")
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("Pass rate under v4-flash judge (%)")
    ax.set_title("Architecture modes: clean comparison vs all rows")
    ax.set_ylim(0, 42)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    for i, v in enumerate(phase1):
        if v is not None:
            ax.text(i - width / 2, v + 0.6, f"{v:.1f}", ha="center", fontsize=8)
    for i, v in enumerate(all_rows):
        if v is not None:
            ax.text(i + width / 2, v + 0.6, f"{v:.1f}", ha="center", fontsize=8)
        else:
            ax.text(i - width / 2, 1.5, "not run", ha="center", fontsize=8, rotation=90)
    save(fig, "fig2_architecture_modes.png")


def plot_scaling() -> None:
    rows = read_csv("results/scaling_20260506/summary.csv")
    series = defaultdict(list)
    for r in rows:
        key = (r["source_experiment"], r["model_short"], r["reasoning"])
        if r["pass_rate_v4flash"]:
            series[key].append((int(r["n"]), 100 * float(r["pass_rate_v4flash"])))

    wanted = [
        ("scaling_reasoning", "gemma-4-31b-it", "max", "Gemma max"),
        ("scaling_reasoning", "gpt-oss-120b", "max", "GPT-OSS max"),
        ("scaling_v4flash", "deepseek-v4-flash", "default", "DeepSeek V4 Flash"),
        ("scaling", "gemma-4-31b-it", "default", "Gemma default"),
        ("scaling", "gpt-oss-120b", "default", "GPT-OSS default"),
    ]
    colors = ["#2f9c67", "#7a6fba", "#3b7ea1", "#c44e52", "#8c8c8c"]
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    for color, (source, model, reasoning, label) in zip(colors, wanted):
        pts = sorted(series.get((source, model, reasoning), []))
        if not pts:
            continue
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", linewidth=2, label=label, color=color)
    ax.set_xticks([1, 3, 5, 7])
    ax.set_ylim(0, 70)
    ax.set_xlabel("n samples")
    ax.set_ylabel("Expected pass@n rate (%)")
    ax.set_title("Pass@n scaling continues through n=7")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, ncols=2, fontsize=8)
    save(fig, "fig3_passn_scaling.png")


def plot_difficulty() -> None:
    rows = [r for r in read_csv("results/architecture_20260506/trials.csv") if r["v4flash_score"]]
    order = [
        (0, "Pre-\ncompetition"),
        (1, "Competition\nhard"),
        (2, "Research\neasy"),
        (3, "Research\nmedium"),
        (4, "Research\nhard"),
        (5, "Research\nfrontier"),
    ]
    rates = []
    counts = []
    means = []
    for difficulty, _ in order:
        rs = [r for r in rows if int(r["difficulty"]) == difficulty]
        counts.append(len(rs))
        rates.append(100 * sum(r["v4flash_pass"] == "True" for r in rs) / len(rs))
        means.append(sum(float(r["v4flash_score"]) for r in rs) / len(rs))

    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    bars = ax.bar([label for _, label in order], rates, color=["#2f9c67", "#4c78a8", "#f58518", "#b279a2", "#c44e52", "#6b6b6b"])
    ax.set_ylim(0, 92)
    ax.set_ylabel("Pass rate under v4-flash judge (%)")
    ax.set_title("Performance drops sharply with difficulty")
    ax.grid(axis="y", alpha=0.25)
    for bar, rate, mean, count in zip(bars, rates, means, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, rate + 1.0, f"{rate:.1f}%\nn={count}\nmean {mean:.2f}", ha="center", va="bottom", fontsize=8)
    save(fig, "fig4_difficulty_gradient.png")


def main() -> None:
    plot_judge_calibration()
    plot_architecture_modes()
    plot_scaling()
    plot_difficulty()


if __name__ == "__main__":
    main()
