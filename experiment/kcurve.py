"""K-controlled oracle-headroom and union-repair curves (external review Q3/P1).

For each population, subsample K harnesses (all combinations up to C(K_pop, K), random
sample above), compute oracle headroom and union repair on the eval151 outcome matrix.
Answers: does headroom grow with K (population-size effect), and do behavior-aware
populations dominate at matched K?

Output: artifacts/day2/kcurve.json + artifacts/day2/fig_kcurve.png
"""
import itertools
import json
import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
random.seed(1234)
N_SUBSAMPLES = 60

df1 = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_eval151_matrix.parquet")
df3 = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_eval151_matrix_round3.parquet")
df = pd.concat([df1, df3], ignore_index=True).drop_duplicates(subset=["task_id", "harness_id"])
wide = df.pivot_table(index="task_id", columns="harness_id", values="harness_correct")
bare = wide["bare"]
bare_errors = set(bare.index[bare == 0])

POPS = {
    "A6 old-proposer": ["cand_bird_g1_b1r0_g1", "cand_bird_g1_b1r1_g0", "cand_bird_g1_b1r1_g1",
                        "cand_bird_g1_b2r0_g1", "cand_bird_pop1_b0r0_g0", "cand_bird_pop1_b0r0_g1"],
    "C8 strategy-forced (Qwen)": ["c2_b2qwen_schema_link", "c2_b2qwen_hint_guard", "c2_b2qwen_two_view",
                                  "c2_b2qwen_format_guard", "c2_b2qwen_decompose", "c2_b2qwen_error_classify",
                                  "c2_b2qwen_repair"],
    "D8 strategy-forced (DeepSeek)": ["c2_b2dexp_two_view", "c2_b2dexp_format_guard", "c2_b2dexp_decompose",
                                      "c2_b2dexp_error_classify", "c2_b2dexp_repair", "c2_b2dexp_vote3",
                                      "c2_b2dexp_schema_link", "c2_b2dexp_hint_guard"],
    "Human control (4)": ["hpc_schema", "hpc_hint", "hpc_repair", "hpc_vote3"],
}


def metrics(members):
    sub = wide[members]
    oracle = pd.concat([sub.max(axis=1), bare], axis=1).max(axis=1)
    head = 100 * (float(oracle.mean()) - float(sub.mean().max()))
    fixed = sum(1 for t in bare_errors if (sub.loc[t, members] == 1).any())
    return head, fixed / len(bare_errors)


out = {}
for label, members in POPS.items():
    K = len(members)
    curve = {}
    for k in range(2, K + 1):
        combos = list(itertools.combinations(members, k))
        if len(combos) > N_SUBSAMPLES:
            combos = [random.sample(members, k) for _ in range(N_SUBSAMPLES)]
        hs, rs = [], []
        for c in combos:
            h, r = metrics(list(c))
            hs.append(h)
            rs.append(r)
        curve[k] = {"headroom_pp_mean": round(float(np.mean(hs)), 2),
                    "headroom_pp_ci95": [round(float(np.percentile(hs, 2.5)), 2),
                                         round(float(np.percentile(hs, 97.5)), 2)],
                    "union_repair_mean": round(float(np.mean(rs)), 4),
                    "n_subsamples": len(combos)}
    out[label] = {"K": K, "curve": curve}
    print(f"[{label}] " + "  ".join(f"K={k}:{v['headroom_pp_mean']}pp" for k, v in curve.items()))

(ROOT / "artifacts" / "day2" / "kcurve.json").write_text(json.dumps(out, indent=1))

fig, ax = plt.subplots(figsize=(7, 4.4))
colors = {"A6 old-proposer": "#c44", "C8 strategy-forced (Qwen)": "#48c",
          "D8 strategy-forced (DeepSeek)": "#161", "Human control (4)": "#888"}
for label, d in out.items():
    ks = sorted(d["curve"])
    ys = [d["curve"][k]["headroom_pp_mean"] for k in ks]
    lo = [d["curve"][k]["headroom_pp_ci95"][0] for k in ks]
    hi = [d["curve"][k]["headroom_pp_ci95"][1] for k in ks]
    ax.plot(ks, ys, "o-", label=label, color=colors[label])
    ax.fill_between(ks, lo, hi, alpha=0.12, color=colors[label])
ax.axhline(5.0, color="k", ls="--", lw=0.8)
ax.text(2.05, 5.15, "pre-specified 5pp line", fontsize=8, color="k")
ax.set_xlabel("population size K (random subsamples, 95% band)", fontsize=9)
ax.set_ylabel("oracle headroom vs best fixed (pp)", fontsize=9)
ax.set_title("Headroom vs population size: not a size effect at matched K", fontsize=11)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(ROOT / "artifacts" / "day2" / "fig_kcurve.png", dpi=200)
print("[write] kcurve.json + fig_kcurve.png")
