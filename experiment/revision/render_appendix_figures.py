"""Redraw three appendix figures from frozen data, without running analyses.

This rendering-only entry point adapts the archived Phase-I scatter and
Phase-II design/result plots. It never writes manuscript text or source data.
Pass the nature-figure QA scripts directory to enable the required alignment
gate. All numerical inputs come from archived records or published annotations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "paper" / "figures"
LATEX_FIGURES = ROOT / "paper" / "latex" / "figures"
BLUE = "#476B88"
LIGHT_BLUE = "#EDF3F7"
GRAY = "#50565C"
ORANGE = "#A76B2D"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans"],
        "font.size": 8.5,
        "axes.titlesize": 9,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.7,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
        "savefig.facecolor": "white",
    })


def save_figure(fig, stem: str, qa_dir: Path, require_matplotlib_panel_alignment) -> dict:
    fig.canvas.draw()
    alignment = require_matplotlib_panel_alignment(
        fig,
        json_out=qa_dir / f"{stem}.alignment.json",
        overlay_svg=qa_dir / f"{stem}.alignment.svg",
        tolerance_pt=1.5,
        gutter_tolerance_pt=1.5,
        strict=True,
    )
    fig.savefig(FIGURES / f"{stem}.pdf")
    fig.savefig(FIGURES / f"{stem}.svg")
    fig.savefig(FIGURES / f"{stem}.png", dpi=600)
    files = {}
    for extension in ("pdf", "svg", "png"):
        target = FIGURES / f"{stem}.{extension}"
        shutil.copyfile(target, LATEX_FIGURES / target.name)
        files[target.name] = digest(target)
    plt.close(fig)
    return {"alignment_verdict": alignment.get("verdict"), "files": files}


def box(ax, x, y, width, height, text, *, fill=LIGHT_BLUE,
        edge=BLUE, fontsize=8.2, bold=False):
    patch = FancyBboxPatch(
        (x, y), width, height, boxstyle="round,pad=0.012,rounding_size=0.018",
        facecolor=fill, edgecolor=edge, linewidth=0.8,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, text,
            ha="center", va="center", fontsize=fontsize,
            fontweight="bold" if bold else "normal", linespacing=1.3)


def make_design():
    fig, axes = plt.subplots(1, 3, figsize=(6.8, 4.7))
    fig.subplots_adjust(left=0.025, right=0.975, bottom=0.035,
                        top=0.91, wspace=0.12)
    for label, title, ax in zip(
        "abc", ("Data and exposure", "Four-arm comparison", "Admission scope"), axes
    ):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.set_title(f"{label}  {title}", loc="left", fontweight="bold", pad=9)

    left, middle, right = axes
    box(left, 0.025, 0.79, 0.95, 0.18,
        "Hand-written controls\n151 items\nDevelopment overlap disclosed")
    box(left, 0.025, 0.55, 0.95, 0.19,
        "Admission development\n2 databases; 365 questions\ncard_games + formula_1")
    box(left, 0.025, 0.31, 0.95, 0.19,
        "Admission evaluation\n9 databases; 1,169 questions\n18-item smoke-test exception",
        fill="#F9F3E9", edge=ORANGE)
    box(left, 0.025, 0.065, 0.95, 0.19,
        "Shared core: 400 questions\nDrawn before outcomes\nSubset of the 1,169")

    middle.text(0.5, 0.93, "Ungated               Gated", ha="center", fontsize=8.1)
    box(middle, 0.035, 0.66, 0.40, 0.21, "II-A\nFree\nUngated")
    box(middle, 0.565, 0.66, 0.40, 0.21, "II-B\nFree\nGated")
    box(middle, 0.035, 0.37, 0.40, 0.21, "II-C\nForced\nUngated")
    box(middle, 0.565, 0.37, 0.40, 0.21, "II-D\nForced\nGated")
    middle.text(0.5, 0.255, "Primary contrast: D − A", ha="center", fontweight="bold")
    middle.text(0.5, 0.155, "6 builders × 3 seeds = 18 cells\nAll cells enter, including K = 0",
                ha="center", va="center", linespacing=1.5, fontsize=8.2)
    middle.text(0.5, 0.035, "Attempt cap: 3\nStop at first admission", ha="center",
                va="center", linespacing=1.4, fontsize=8.2)

    box(right, 0.025, 0.76, 0.95, 0.21,
        "All four arms\nNeutral validity\nParse / import / nonempty SQL")
    box(right, 0.025, 0.44, 0.95, 0.24,
        "Gated arms B and D\nStructural screening\n+ mechanism conformance",
        fill="#F9F3E9", edge=ORANGE)
    right.annotate("", xy=(0.5, 0.695), xytext=(0.5, 0.745),
                   arrowprops={"arrowstyle": "->", "color": GRAY, "lw": 0.8})
    box(right, 0.025, 0.035, 0.95, 0.27,
        "II-E: development only\nOpen mechanism\nSelf-specified contract\nExcluded from four-arm comparison",
        fill="#F4F4F4", edge="#777777", fontsize=8.0)
    return fig


def make_results(data: dict):
    primary, core = data["primary"], data["core"]
    cells = sorted(primary["per_cell"], key=lambda row: row["contrasts"][0])
    if len(cells) != 18 or set(core["arm_means"]) != set("ABCD"):
        raise ValueError("Expected the frozen 18-cell, four-arm result")
    values = np.array([row["contrasts"][0] for row in cells]) * 100
    lower, upper = np.array(primary["ci95_unadjusted"][0]) * 100
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 4.25),
                             gridspec_kw={"width_ratios": [1.3, 1]})
    fig.subplots_adjust(left=0.135, right=0.975, bottom=0.18,
                        top=0.89, wspace=0.56)
    names = {"glm": "GLM", "deepseek": "DeepSeek", "minimax": "MiniMax",
             "qwen": "Qwen", "ernie": "ERNIE", "kimi": "Kimi"}
    axes[0].barh(range(len(cells)), values, height=0.68, color=BLUE, zorder=2)
    axes[0].set_yticks(range(len(cells)),
                      [f"{names[row['builder']]}/s{row['seed']}" for row in cells])
    axes[0].axvspan(lower, upper, color="#C9D9E6", alpha=0.65, zorder=1)
    axes[0].axvline(0, color=GRAY, linewidth=0.7, zorder=3)
    axes[0].set_xlabel("D − A headroom (pp)")
    axes[0].set_title("a  Paired cell contrasts", loc="left", fontweight="bold", pad=12)
    axes[0].text(0.5, -0.17, "Shading: pooled unadjusted 95% CI", transform=axes[0].transAxes,
                 ha="center", va="top", fontsize=8.0)
    axes[1].bar(list("ABCD"),
                [core["arm_means"][arm]["headroom"] * 100 for arm in "ABCD"],
                color=BLUE, width=0.62)
    axes[1].set_ylim(0, 10)
    axes[1].set_ylabel("Mean headroom (pp)")
    axes[1].set_xlabel("Admission arm")
    axes[1].set_title("b  Shared core of 400 tasks", loc="left", fontweight="bold", pad=12)
    axes[1].text(0.5, -0.17, "Same single-call baseline in all arms", transform=axes[1].transAxes,
                 ha="center", va="top", fontsize=8.0)
    return fig


def make_phenomenon(pairs: list[dict]):
    if len(pairs) != 91:
        raise ValueError("Expected all 91 archived discovery pairs")
    x_values = [row["code_sim"] for row in pairs]
    y_values = [row["disagreement"] for row in pairs]
    fig, ax = plt.subplots(figsize=(5.8, 3.75))
    fig.subplots_adjust(left=0.14, right=0.98, bottom=0.23, top=0.82)
    ax.scatter(x_values, y_values, s=32, alpha=0.80, edgecolor=BLUE,
               linewidth=0.5, facecolor="#93B1C8", zorder=3)
    ax.set_xlim(min(x_values) - 0.015, max(x_values) + 0.015)
    ax.set_ylim(-0.009, 0.145)
    ax.set_xlabel("Source-code similarity (token-sequence ratio)")
    ax.set_ylabel("Correctness disagreement")
    ax.grid(axis="y", alpha=0.18, linewidth=0.6, zorder=0)
    ax.set_title("Source similarity and observed correctness", loc="left",
                 fontweight="bold", pad=26)
    ax.text(0, 1.065, "14 harnesses × 60 tasks; all 91 pairs", transform=ax.transAxes,
            ha="left", va="bottom", fontsize=8.5)
    # These are frozen published annotations, not newly computed statistics.
    fig.text(0.14, 0.073, "Spearman ρ = −0.010; mean disagreement = 3.3%", fontsize=8.5)
    fig.text(0.14, 0.026, "36/91 pairs have identical correctness on all 60 tasks", fontsize=8.5)
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-scripts", type=Path, required=True)
    parser.add_argument("--qa-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.qa_scripts.resolve()))
    from audit_panel_alignment import require_matplotlib_panel_alignment

    args.qa_dir.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    LATEX_FIGURES.mkdir(parents=True, exist_ok=True)
    analysis_path = ROOT / "artifacts/revision_20260910/corrected_analysis.json"
    pairs_path = ROOT / "artifacts/phase2/fig1_phenomenon_data.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    pairs = json.loads(pairs_path.read_text(encoding="utf-8"))
    if analysis["analysis_version"] != "revision-20260910-v1" or analysis["n_boot"] != 10000:
        raise ValueError("Expected the final frozen 10000-replicate analysis")
    inputs = {path.relative_to(ROOT).as_posix(): digest(path)
              for path in (analysis_path, pairs_path)}
    configure()
    results = {}
    for stem, figure in (
        ("fig_design_revision", make_design()),
        ("fig_results_revision", make_results(analysis)),
        ("fig_phenomenon", make_phenomenon(pairs)),
    ):
        results[stem] = save_figure(figure, stem, args.qa_dir,
                                    require_matplotlib_panel_alignment)
    if any(digest(ROOT / name) != value for name, value in inputs.items()):
        raise RuntimeError("A frozen input changed during rendering")
    manifest = {
        "backend": "python/matplotlib", "operation": "rendering only",
        "inputs_sha256": inputs,
        "source_sha256": digest(Path(__file__)),
        "input_rows": {"discovery_pairs": len(pairs), "primary_cells": 18},
        "excluded_rows": 0,
        "annotation_policy": "Published discovery annotations retained; no statistics recomputed",
        "figures": results,
    }
    (args.qa_dir / "figure_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
