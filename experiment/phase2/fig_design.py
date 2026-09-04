"""Study-design diagram: contamination isolation + 2x2 factorial + three-layer gate.

Draws from PHASE2_PROTOCOL.md only; contains no outcome data."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp

fig, ax = plt.subplots(figsize=(9.5, 4.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 52); ax.axis("off")

def box(x, y, w, h, text, fc="#eef3fb", ec="#3a6ea5", fs=8.0, lw=1.2, bold=False):
    ax.add_patch(mp.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.35",
                 fc=fc, ec=ec, lw=lw))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", linespacing=1.35)

# ---- left panel: data isolation
ax.text(14, 50, "Data isolation", fontsize=10, fontweight="bold", ha="center")
box(2, 36, 24, 9, "Phase-I discovery set\n(card_games + formula_1,\n365 q, contaminated)", fc="#fdeeee", ec="#b5545a")
box(2, 22, 24, 9, "9 never-opened DBs\n1169 q — frozen\nconfirmatory test", fc="#eef8ee", ec="#4a8f5c", bold=True)
box(2, 8, 24, 9, "400-item core\n(stratified, drawn\npre-outcome)", fc="#eef8ee", ec="#4a8f5c")
ax.annotate("", xy=(14, 31), xytext=(14, 36), arrowprops=dict(arrowstyle="-", ls=":", color="#999"))

# ---- middle panel: 2x2 factorial
ax.text(58, 50, "Generation protocol (equal raw budget R=3/slot)", fontsize=10, fontweight="bold", ha="center")
box(42, 34, 13, 9, "A\nfree\nungated", fs=8)
box(62, 34, 13, 9, "B\nfree\ngated", fs=8)
box(42, 21, 13, 9, "C\nforced\nungated", fs=8)
box(62, 21, 13, 9, "D\nforced\ngated\n(PRIMARY)", fs=8, bold=True, ec="#b8860b", fc="#fdf6e3")
ax.text(40.5, 39.5, "S=0", fontsize=8, color="#555")
ax.text(40.5, 26.5, "S=1", fontsize=8, color="#555")
ax.text(48.5, 44.5, "G=0", fontsize=8, color="#555")
ax.text(68.5, 44.5, "G=1", fontsize=8, color="#555")
box(82, 21, 16, 22, "E\nopen-mechanism\n(self-specified\ncontract, gated)", fs=7.5, fc="#f4eefb", ec="#7a4a9e")

# ---- right panel: three-layer gate
ax.text(90, 50, "Admission", fontsize=10, fontweight="bold", ha="center")
box(84, 36, 14, 8, "neutral validity\n(parse/import/SQL)", fs=7)
box(84, 25, 14, 8, "conformance\n(counterfactual\nprobes)", fs=7)
box(84, 14, 14, 8, "non-vacuity\n(vs. bare)", fs=7)
for y0, y1 in ((36, 33), (25, 22)):
    ax.annotate("", xy=(91, y1), xytext=(91, y0), arrowprops=dict(arrowstyle="->", color="#666"))
ax.annotate("", xy=(21, 21), xytext=(29, 21),
            arrowprops=dict(arrowstyle="->", color="#888", connectionstyle="arc3,rad=0.15"))

fig.suptitle("Phase-II confirmatory design: database-level isolation, 2×2 factorial + open-mechanism arm, three-layer admission",
             fontsize=10.5, y=0.99)
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig("../../paper/figures/fig_design.pdf", bbox_inches="tight")
plt.savefig("../../paper/figures/fig_design.png", dpi=180, bbox_inches="tight")
print("wrote paper/figures/fig_design.pdf/.png")
