"""Hero + taxonomy figures from Day-1 data (independent of eval151 matrix).

Fig 1 (hero): syntactic vs behavioral diversity. Left: pairwise code-similarity heatmap
(Levenshtein-ratio on normalized source) among the 13 AI candidates; Right: the same
pairs' outcome-agreement heatmap. Code is diverse (low similarity), outcomes are nearly
identical (high agreement) — the paper's one-figure story.

Fig 2 (taxonomy): per-harness trace profile (LLM calls / executions per task) showing
T1 pure-prompt variants (1 call, 0 exec), T2 react (multi call but byte-identical SQL),
T3 buggy multi-turn.

Output: artifacts/day2/fig_hero.png, fig_taxonomy.png (+ .pdf), fig_hero_data.json
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "external" / "TTHE" / "text_to_sql" / "agents"
OUT = ROOT / "artifacts" / "day2"
OUT.mkdir(parents=True, exist_ok=True)

CANDS = ["cand_bird_g1_b0r0_g0", "cand_bird_g1_b0r0_g1", "cand_bird_g1_b0r1_g0",
         "cand_bird_g1_b0r1_g1", "cand_bird_g1_b1r0_g0", "cand_bird_g1_b1r0_g1",
         "cand_bird_g1_b1r1_g0", "cand_bird_g1_b1r1_g1", "cand_bird_g1_b2r0_g0",
         "cand_bird_g1_b2r0_g1", "cand_bird_pop1_b0r0_g0", "cand_bird_pop1_b0r0_g1"]
LABELS = [c.replace("cand_bird_", "") for c in CANDS]

df = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_bird_matrix.parquet")
wide = df.pivot_table(index="task_id", columns="harness_id", values="harness_correct")

# ---- code similarity (normalized: strip comments/blank lines/whitespace) ----
def norm_src(name: str) -> str:
    src = (AGENTS / f"{name}.py").read_text(encoding="utf-8", errors="ignore")
    lines = [ln.split("#")[0].strip() for ln in src.splitlines()]
    return "\n".join(ln for ln in lines if ln)

n = len(CANDS)
code_sim = np.zeros((n, n))
out_agree = np.zeros((n, n))
for i, a in enumerate(CANDS):
    for j, b in enumerate(CANDS):
        if i == j:
            code_sim[i, j] = out_agree[i, j] = 1.0
            continue
        code_sim[i, j] = difflib.SequenceMatcher(None, norm_src(a), norm_src(b)).ratio()
        out_agree[i, j] = float(np.mean(wide[a] == wide[b]))

# ---- figure 1: hero ----
fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
for ax, mat, title in ((axes[0], code_sim, "Code similarity (syntactic)"),
                       (axes[1], out_agree, "Outcome agreement (behavioral)")):
    im = ax.imshow(mat, vmin=0.0, vmax=1.0, cmap="viridis")
    ax.set_xticks(range(n), LABELS, rotation=90, fontsize=6)
    ax.set_yticks(range(n), LABELS, fontsize=6)
    ax.set_title(title, fontsize=11)
mean_off_code = float(code_sim[np.triu_indices(n, 1)].mean())
mean_off_out = float(out_agree[np.triu_indices(n, 1)].mean())
n_ident = int(sum(1 for i in range(n) for j in range(i + 1, n) if out_agree[i, j] == 1.0))
axes[0].set_xlabel(f"mean off-diagonal = {mean_off_code:.2f}", fontsize=9)
axes[1].set_xlabel(f"mean off-diagonal = {mean_off_out:.2f}   ({n_ident}/{n*(n-1)//2} pairs = 1.00)", fontsize=9)
fig.colorbar(im, ax=axes, shrink=0.75, pad=0.015)
fig.suptitle("AI-generated harnesses: syntactically diverse, behaviorally collapsed",
             fontsize=12, y=0.99)
fig.tight_layout()
fig.savefig(OUT / "fig_hero.png", dpi=200, bbox_inches="tight")
fig.savefig(OUT / "fig_hero.pdf", bbox_inches="tight")
plt.close(fig)

# ---- figure 2: taxonomy (trace profile) ----
audit = pd.read_json(ROOT / "artifacts" / "day1" / "trace_audit.jsonl", lines=True)
audit["task_db"] = audit["task"].str.split("#").str[0]
classes = [("bare", "bare (H0)"), ("react", "react [T2]"),
           ("cand_bird_g1_b0r0_g1", "pure prompt variant [T1]"),
           ("cand_bird_g1_b1r1_g1", "multi-turn candidate [T3]")]
fig, ax = plt.subplots(figsize=(7.5, 4.2))
w = 0.2
xs = np.arange(audit["task_db"].nunique() if audit["task"].nunique() > 12 else audit["task"].nunique())
tasks = sorted(audit["task"].unique())[:10]
for k, (h, label) in enumerate(classes):
    sub = audit[audit["harness"] == h].set_index("task").reindex(tasks)
    ax.bar(np.arange(len(tasks)) + (k - 1.5) * w, sub["n_llm_calls"].fillna(0), w,
           label=label, alpha=0.9 if h != "react" else 0.55)
ax.set_xticks(np.arange(len(tasks)), [t.split("#")[1] for t in tasks], fontsize=8)
ax.set_xlabel("card_games task id (10 audited)", fontsize=9)
ax.set_ylabel("# LLM calls per task", fontsize=9)
ax.axhline(1.0, color="grey", lw=0.8, ls="--")
ax.text(len(tasks) - 0.5, 1.05, "bare path = 1 call", ha="right", fontsize=8, color="grey")
ax.set_title("Execution-trace taxonomy: T1 same path as bare, T2 feedback that cannot change\n"
             "the answer (10/10 byte-identical final SQL), T3 buggy multi-turn", fontsize=10)
ax.legend(fontsize=8, ncol=2)
fig.tight_layout()
fig.savefig(OUT / "fig_taxonomy.png", dpi=200, bbox_inches="tight")
fig.savefig(OUT / "fig_taxonomy.pdf", bbox_inches="tight")
plt.close(fig)

(OUT / "fig_hero_data.json").write_text(json.dumps({
    "labels": LABELS, "code_sim_mean_offdiag": mean_off_code,
    "out_agree_mean_offdiag": mean_off_out,
    "n_identical_behavior_pairs": int(sum(1 for i in range(n) for j in range(i + 1, n)
                                          if out_agree[i, j] == 1.0)),
    "n_pairs": n * (n - 1) // 2}, indent=2))
print(f"[figs] hero: code_sim={mean_off_code:.2f} out_agree={mean_off_out:.2f} "
      f"identical_pairs={n_ident}/{n*(n-1)//2}")
print(f"[figs] wrote {OUT/'fig_hero.png'} and {OUT/'fig_taxonomy.png'}")
