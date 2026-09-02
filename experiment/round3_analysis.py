"""Matched-strategy + completed-grid population analysis (round-3, post strategy completion).

Populations (eval151, bare as H0):
  C6/D6   : original six-strategy populations (pre-registered admission; unchanged)
  C8/D8   : completed eight-strategy grids for Qwen / DeepSeek builders (post-hoc, labeled)
  B3      : GLM logged re-run, the 3 strategies it accepted (post-hoc)
  MATCHED : builder comparison restricted to strategies both builders produced
            (C8 vs D8 share all 8; B3 shares 3 with both)

Reads both matrices and writes artifacts/day2/eval151_round3_analysis.json
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
H0 = "bare"

df1 = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_eval151_matrix.parquet")
df3 = pd.read_parquet(ROOT / "artifacts" / "outcomes" / "tthe_eval151_matrix_round3.parquet")
df = pd.concat([df1, df3], ignore_index=True)
df = df.drop_duplicates(subset=["task_id", "harness_id"], keep="first")
wide = df.pivot_table(index="task_id", columns="harness_id", values="harness_correct")
bare = wide[H0]

POPS = {
    "C6_qwen_original": ["c2_b2qwen_schema_link", "c2_b2qwen_hint_guard", "c2_b2qwen_two_view",
                         "c2_b2qwen_format_guard", "c2_b2qwen_decompose", "c2_b2qwen_error_classify"],
    "D6_dsexp_original": ["c2_b2dexp_two_view", "c2_b2dexp_format_guard", "c2_b2dexp_decompose",
                          "c2_b2dexp_error_classify", "c2_b2dexp_repair", "c2_b2dexp_vote3"],
    "C8_qwen_completed": ["c2_b2qwen_schema_link", "c2_b2qwen_hint_guard", "c2_b2qwen_two_view",
                          "c2_b2qwen_format_guard", "c2_b2qwen_decompose", "c2_b2qwen_error_classify",
                          "c2_b2qwen_repair"],
    "D8_dsexp_completed": ["c2_b2dexp_two_view", "c2_b2dexp_format_guard", "c2_b2dexp_decompose",
                           "c2_b2dexp_error_classify", "c2_b2dexp_repair", "c2_b2dexp_vote3",
                           "c2_b2dexp_schema_link", "c2_b2dexp_hint_guard"],
    "B3_glm_logged": ["c2_b3glm_repair", "c2_b3glm_vote3", "c2_b3glm_two_view"],
    "MATCHED_C7_D7": ["c2_b2qwen_schema_link", "c2_b2qwen_hint_guard", "c2_b2qwen_two_view",
                      "c2_b2qwen_format_guard", "c2_b2qwen_decompose", "c2_b2qwen_error_classify",
                      "c2_b2qwen_repair"],
    "MATCHED_D7": ["c2_b2dexp_two_view", "c2_b2dexp_format_guard", "c2_b2dexp_decompose",
                   "c2_b2dexp_error_classify", "c2_b2dexp_repair", "c2_b2dexp_vote3",
                   "c2_b2dexp_schema_link", "c2_b2dexp_hint_guard"],
}


def stats(members: list[str]) -> dict:
    sub = wide[members]
    dis = [float(np.mean(sub[a] != sub[b])) for a, b in itertools.combinations(members, 2)]
    bare_errors = set(bare.index[bare == 0])
    fixsets = {h: set(sub.index[(sub[h] == 1) & (bare.reindex(sub.index) == 0)]) for h in members}
    union = set().union(*fixsets.values()) & bare_errors if fixsets else set()
    seen, distinct = [], 0
    for h, s in fixsets.items():
        if s and frozenset(s) not in seen:
            seen.append(frozenset(s)); distinct += 1
    per = sub.mean()
    oracle = pd.concat([sub.max(axis=1), bare], axis=1).max(axis=1)
    return {
        "n_harnesses": len(members),
        "pairwise_disagreement_mean": round(float(np.mean(dis)), 4) if dis else 0.0,
        "union_repair_rate": round(len(union) / len(bare_errors), 4) if bare_errors else 0.0,
        "union_repair_items": len(union),
        "bare_errors": len(bare_errors),
        "best_fixed_acc": round(float(per.max()), 4),
        "best_fixed_id": str(per.idxmax()),
        "oracle_headroom_vs_best_fixed_pp": round(100 * (float(oracle.mean()) - float(per.max())), 2),
        "n_distinct_nonempty_fixsets": distinct,
        "fixset_sizes": {h: len(s) for h, s in fixsets.items()},
    }


out = {"note": "C8/D8/B3 are post-hoc completed-grid populations (label as secondary analysis); "
               "C6/D6 carry the pre-registered admission decisions.",
       "populations": {}}
for label, members in POPS.items():
    missing = [m for m in members if m not in wide.columns]
    out["populations"][label] = {"error": f"missing: {missing}"} if missing else stats(members)
    s = out["populations"][label]
    if "error" not in s:
        print(f"[{label}] disagree={s['pairwise_disagreement_mean']:.3f} "
              f"repair={s['union_repair_rate']:.3f} headroom={s['oracle_headroom_vs_best_fixed_pp']:.2f}pp "
              f"distinct_fixsets={s['n_distinct_nonempty_fixsets']}")

# builder axis on matched strategies: per-strategy accuracy qwen vs dsexp vs glm
strat_map = {
    "repair": ("c2_b2qwen_repair", "c2_b2dexp_repair", "c2_b3glm_repair"),
    "vote3": ("c2_b2qwen_vote3", "c2_b2dexp_vote3", "c2_b3glm_vote3"),
    "schema_link": ("c2_b2qwen_schema_link", "c2_b2dexp_schema_link", None),
    "hint_guard": ("c2_b2qwen_hint_guard", "c2_b2dexp_hint_guard", None),
    "two_view": ("c2_b2qwen_two_view", "c2_b2dexp_two_view", "c2_b3glm_two_view"),
    "decompose": ("c2_b2qwen_decompose", "c2_b2dexp_decompose", None),
    "error_classify": ("c2_b2qwen_error_classify", "c2_b2dexp_error_classify", None),
    "format_guard": ("c2_b2qwen_format_guard", "c2_b2dexp_format_guard", None),
}
out["per_strategy_acc"] = {}
for strat, (q, d, g) in strat_map.items():
    row = {}
    for tag, hid in (("qwen", q), ("dsexp", d), ("glm", g)):
        row[tag] = round(float(wide[hid].mean()), 4) if hid and hid in wide.columns else None
    out["per_strategy_acc"][strat] = row
print("[per-strategy]", json.dumps(out["per_strategy_acc"], indent=1))

(ROOT / "artifacts" / "day2" / "eval151_round3_analysis.json").write_text(json.dumps(out, indent=1))
print("[write] artifacts/day2/eval151_round3_analysis.json")
