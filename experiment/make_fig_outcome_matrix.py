"""Figure: outcome disagreement matrix (harness x task heatmap), collapsed vs repaired populations.

Left panel: A6 old-proposer population (collapsed) — columns nearly identical.
Right panel: D8 strategy-forced population (repaired) — visibly varied.
Items ordered by bare correctness (bare errors last) so repair columns are visible.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
df1 = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_eval151_matrix.parquet")
df3 = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_eval151_matrix_round3.parquet")
df = pd.concat([df1, df3], ignore_index=True).drop_duplicates(subset=["task_id", "harness_id"])
wide = df.pivot_table(index="task_id", columns="harness_id", values="harness_correct")
bare = wide["bare"]

POPS = {
    "A6 old-proposer (collapsed)": ["cand_bird_g1_b1r0_g1", "cand_bird_g1_b1r1_g0", "cand_bird_g1_b1r1_g1",
                                    "cand_bird_g1_b2r0_g1", "cand_bird_pop1_b0r0_g0", "cand_bird_pop1_b0r0_g1"],
    "D8 strategy-forced (repaired)": ["c2_b2dexp_two_view", "c2_b2dexp_format_guard", "c2_b2dexp_decompose",
                                      "c2_b2dexp_error_classify", "c2_b2dexp_repair", "c2_b2dexp_vote3",
                                      "c2_b2dexp_schema_link", "c2_b2dexp_hint_guard"],
}
order = wide.index[np.argsort(-bare.values)]  # bare-correct first, errors last

fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
for ax, (label, members) in zip(axes, POPS.items()):
    mat = wide[members].reindex(order).T.values
    ax.imshow(mat, aspect="auto", cmap="Greens", vmin=0, vmax=1, interpolation="none")
    ax.set_title(label, fontsize=10)
    ax.set_xlabel(f"tasks (bare errors at right); mean disagreement "
                  f"{np.mean([np.mean(wide[a] != wide[b]) for a in members for b in members if a < b]):.1%}",
                  fontsize=8)
    ax.set_yticks(range(len(members)))
    ax.set_yticklabels([m.replace('cand_bird_', '').replace('c2_b2dexp_', '') for m in members], fontsize=7)
    ax.set_xticks([])
fig.suptitle("Outcome matrices: syntactically distinct harnesses, behavioral difference on show (1=correct)", fontsize=11)
fig.tight_layout()
fig.savefig(ROOT / "artifacts" / "day2" / "fig_outcome_matrix.png", dpi=200)
print("wrote fig_outcome_matrix.png")
