"""Results figure: primary D-A delta per (builder x seed) cell with pooled CI, and the
factorial arm means. Reads ONLY frozen analysis outputs (no raw recompute)."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts" / "phase2"

prim = json.loads((P2 / "analysis_primary.json").read_text(encoding="utf-8"))
fact = json.loads((P2 / "analysis_factorial.json").read_text(encoding="utf-8"))

fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), gridspec_kw={"width_ratios": [3, 2]})

# ---- panel 1: per-cell D-A delta, sorted, with pooled CI band
cells = sorted(prim["per_cell"], key=lambda c: c["delta_headroom"])
labels = [f"{c['builder']}/s{c['seed']}" for c in cells]
deltas = [c["delta_headroom"] for c in cells]
lo, hi = prim["ci95_two_sided"]
y = np.arange(len(cells))
ax = axes[0]
ax.barh(y, deltas, color=["#b5545a" if d < 0 else "#4a8f5c" for d in deltas],
        alpha=0.85, zorder=3)
ax.axvline(0, color="black", lw=1, zorder=4)
ax.axvspan(lo, hi, color="#7fa3d4", alpha=0.18, zorder=1,
           label=f"pooled 95% CI [{lo*100:.1f}, {hi*100:.1f}] pp")
ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=7.5)
ax.set_xlabel("D − A headroom delta (pp)")
ax.set_title(f"Primary contrast per cell\npooled = {prim['point_estimate']*100:+.2f} pp, p(perm) = 0.65", fontsize=10)
ax.legend(fontsize=8, loc="lower right")
ax.grid(axis="x", alpha=0.25, zorder=0)

# ---- panel 2: factorial arm means with gate/strategy/interaction
ax = axes[1]
H = {a: np.mean([c["H"][a] for c in fact["per_cell"]]) for a in "ABCD"}
arms = ["A\nfree\nungated", "B\nfree\ngated", "C\nforced\nungated", "D\nforced\ngated"]
vals = [H[a]*100 for a in "ABCD"]
colors = ["#7fa3d4", "#b8860b", "#8fb58f", "#b5545a"]
bars = ax.bar(arms, vals, color=colors, alpha=0.85, zorder=3)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width()/2, v + 0.15, f"{v:.1f}", ha="center", fontsize=9)
ax.set_ylabel("mean bare-inclusive headroom (pp)")
ax.set_title("Factorial arm means (core-400)\ngate main −0.67pp*, strategy +0.41, inter −0.87", fontsize=10)
ax.grid(axis="y", alpha=0.25, zorder=0)
ax.set_ylim(0, max(vals)*1.25)

plt.tight_layout()
plt.savefig(ROOT / "paper" / "figures" / "fig_results.pdf", bbox_inches="tight")
plt.savefig(ROOT / "paper" / "figures" / "fig_results.png", dpi=180, bbox_inches="tight")
print("wrote paper/figures/fig_results.pdf/.png")
print(f"arm means (pp): " + ", ".join(f"{a}={H[a]*100:.2f}" for a in "ABCD"))
