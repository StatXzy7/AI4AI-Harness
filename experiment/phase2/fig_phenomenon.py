"""Figure 1 (phenomenon): syntactic similarity vs behavioral disagreement.

Phase-I day-1 population only (14 harnesses x 60 tasks, GLM-5.3-Flash target) —
DISCOVERY data, unsealed; contains no Phase-II confirmatory outcome.

Each point is a harness pair (h_i, h_j):
    x = pairwise source-code similarity (difflib SequenceMatcher on token streams)
    y = pairwise outcome disagreement (fraction of tasks where correctness differs)

The paper's title claim is the shape of this cloud: code similarity carries almost
no information about outcome disagreement — pairs at ~0.1 code similarity are just
as behaviorally identical as pairs at ~0.5.
"""
import difflib
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "external" / "TTHE" / "text_to_sql" / "agents"

df = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_bird_matrix.parquet")
piv = df.pivot_table(index="harness_id", columns="task_id", values="harness_correct")

def tokenize(name):
    src = (AGENTS / f"{name}.py").read_text(encoding="utf-8")
    # token stream: identifiers, keywords, strings -> code structure, not formatting
    import re
    return re.findall(r"[A-Za-z_][A-Za-z_0-9]*|==|!=|<=|>=|[0-9]+", src)

toks = {h: tokenize(h) for h in piv.index}

xs, ys, pairs = [], [], []
for a, b in combinations(piv.index, 2):
    sim = difflib.SequenceMatcher(None, toks[a], toks[b], autojunk=True).ratio()
    dis = float((piv.loc[a] != piv.loc[b]).mean())
    xs.append(sim); ys.append(dis); pairs.append((a, b, sim, dis))

xs, ys = np.array(xs), np.array(ys)
from scipy import stats
rho, rho_p = stats.spearmanr(xs, ys)
r, r_p = stats.pearsonr(xs, ys)

fig, ax = plt.subplots(figsize=(6.2, 4.4))
ax.scatter(xs, ys, s=42, alpha=0.75, edgecolor="#33517a", linewidth=0.6,
           facecolor="#7fa3d4", zorder=3)
n_identical = int((ys == 0).sum())
ax.axhline(ys.mean(), color="#b5545a", lw=1.2, ls="--", zorder=2)
ax.annotate(f"mean disagreement {ys.mean():.1%}", xy=(0.98, ys.mean()),
            xycoords=("axes fraction", "data"), va="bottom", ha="right",
            fontsize=9, color="#b5545a")
ax.annotate(f"{n_identical}/{len(ys)} pairs identical on all 60 tasks",
            xy=(0.02, 0.05), xycoords="axes fraction", fontsize=9, color="#444")
ax.set_xlabel("pairwise source-code similarity (token-sequence ratio)")
ax.set_ylabel("pairwise outcome disagreement")
ax.set_title(f"Syntactically diverse, behaviorally collapsed\n"
             f"(day-1 population, 14 harnesses x 60 tasks; "
             f"Spearman $\\rho$ = {rho:.2f}, $p$ = {rho_p:.2f})", fontsize=10.5)
ax.grid(alpha=0.25, zorder=1)
plt.tight_layout()
plt.savefig(ROOT / "paper" / "figures" / "fig_phenomenon.pdf", bbox_inches="tight")
plt.savefig(ROOT / "paper" / "figures" / "fig_phenomenon.png", dpi=180, bbox_inches="tight")

print(f"{len(xs)} pairs | mean code sim {xs.mean():.3f} | mean disagreement {ys.mean():.3f}")
print(f"identical-outcome pairs: {n_identical}/{len(ys)}")
print(f"Spearman rho={rho:.3f} (p={rho_p:.3f})  Pearson r={r:.3f} (p={r_p:.3f})")
out = [{"a": a, "b": b, "code_sim": round(s, 4), "disagreement": round(d, 4)}
       for a, b, s, d in pairs]
import json
(ROOT / "artifacts" / "phase2" / "fig1_phenomenon_data.json").write_text(
    json.dumps(out, indent=1))
print("wrote paper/figures/fig_phenomenon.pdf + png, raw pairs archived")
