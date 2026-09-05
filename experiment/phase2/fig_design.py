"""Figure 2 (study design): Phase-II confirmatory design diagram.

v2 fixes from the Codex review:
  * no text overlap (arm II-E box moved to its own panel row; admission
    boxes re-laid-out below the factorial grid)
  * the 365-question development set is labelled as the PHASE-II development
    pool (card_games + formula_1); Phase-I's own evaluation (151 items) is
    labelled as such -- the two phases' datasets are different things
Contains no outcome data; draws only from the frozen protocol.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp

fig, ax = plt.subplots(figsize=(9.5, 5.4))
ax.set_xlim(0, 100); ax.set_ylim(0, 56); ax.axis("off")

def box(x, y, w, h, text, fc="#eef3fb", ec="#3a6ea5", fs=8.0, lw=1.2, bold=False):
    ax.add_patch(mp.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.35",
                 fc=fc, ec=ec, lw=lw))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", linespacing=1.3)

# ---- left panel: data isolation (both phases)
ax.text(15, 54, "Data isolation", fontsize=10, fontweight="bold", ha="center")
box(2, 41, 26, 9, "Phase-I discovery eval\n151 q (overlaps dev use;\ndisclosed)", fc="#fdeeee", ec="#b5545a")
box(2, 29, 26, 9, "Phase-II development pool\n(card_games + formula_1,\n365 q — builders only)", fc="#fdf6e3", ec="#b8860b")
box(2, 16, 26, 10, "Phase-II confirmatory test\n9 never-opened DBs\n1,169 q — frozen", fc="#eef8ee", ec="#4a8f5c", bold=True)
box(2, 4, 26, 9, "Stratified core 400\n(drawn pre-outcome,\nsubset of the 1,169)", fc="#eef8ee", ec="#4a8f5c")

# ---- middle panel: 2x2 factorial
ax.text(58, 54, "Generation protocol (equal raw budget R=3/slot)", fontsize=10, fontweight="bold", ha="center")
box(42, 38, 14, 10, "II-A\nfree\nungated", fs=8)
box(62, 38, 14, 10, "II-B\nfree\ngated", fs=8)
box(42, 24, 14, 10, "II-C\nforced\nungated", fs=8)
box(62, 24, 14, 10, "II-D\nforced\ngated\n(PRIMARY)", fs=8, bold=True, ec="#b8860b", fc="#fdf6e3")
ax.text(40.2, 44, "S=0", fontsize=8, color="#555")
ax.text(40.2, 30, "S=1", fontsize=8, color="#555")
ax.text(47.5, 49, "G=0", fontsize=8, color="#555")
ax.text(67.5, 49, "G=1", fontsize=8, color="#555")
box(80, 24, 18, 24, "II-E (secondary)\nopen mechanism:\nself-specified\ncontract,\ngated on own\ndeclaration", fs=7.5, fc="#f4eefb", ec="#7a4a9e")
ax.text(69, 12.5, "6 builders $\\times$ 3 seeds = 18 paired cells (all enter, incl. K=0)",
        fontsize=8, color="#333", ha="center")

# ---- bottom panel: three-layer admission (full width, no overlap)
ax.text(50, 14.5, "Three-layer admission (gated arms)", fontsize=10, fontweight="bold", ha="center")
box(22, 2.5, 17, 8, "1. neutral validity\n(parse / import /\nreturns SQL)", fs=7)
box(41.5, 2.5, 17, 8, "2. counterfactual\nconformance\n(trace probes)", fs=7)
box(61, 2.5, 17, 8, "3. non-vacuity\n(must be violated\nby bare) — arm E", fs=7)
for x0, x1 in ((39, 41.5), (58.5, 61)):
    ax.annotate("", xy=(x1, 6.5), xytext=(x0, 6.5), arrowprops=dict(arrowstyle="->", color="#666"))
ax.annotate("", xy=(30.5, 16), xytext=(15, 29),
            arrowprops=dict(arrowstyle="->", color="#888", connectionstyle="arc3,rad=0.2"))

fig.suptitle("Phase-II confirmatory design: database-level isolation, 2×2 factorial + open-mechanism arm, three-layer admission",
             fontsize=10.5, y=0.99)
plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig("../../paper/figures/fig_design.pdf", bbox_inches="tight")
plt.savefig("../../paper/figures/fig_design.png", dpi=180, bbox_inches="tight")
print("wrote paper/figures/fig_design.pdf/.png (v2: no overlap, phase labels corrected)")
