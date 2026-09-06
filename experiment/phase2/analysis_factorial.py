"""Factorial secondary analysis: gate / strategy main effects + interaction.

Confirmatory secondaries per PHASE2_SAP.md section 4, Holm-corrected, tested after the
primary (which returned no clear improvement: D-A -0.0016 [-0.0090, +0.0082]).

All four arms (II-A free/ungated, II-B free/gated, II-C forced/ungated, II-D
forced/gated) evaluated on the SAME core-400 items, bare-inclusive headroom, official
judge, paired by (builder x seed):

    gate main effect      = [(B-A) + (D-C)] / 2
    strategy main effect = [(C-A) + (D-B)] / 2
    interaction          = (D-C) - (B-A)

The interaction is the key mechanism question after the primary's null result: if the
gate and strategy forcing SUBSTITUTE for each other (negative interaction), the combined
protocol's null delta is explained — each component delivers what the other already
provides.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts" / "phase2"
GEN = P2 / "gen"
TARGET = "GLM-5.3-Flash"
EXCLUDED = {"p2_A_glm_s1_g0", "p2_A_glm_s1_g4"}   # D15

AD_FILES = [P2 / f"ad_shard{i}.jsonl" for i in range(4)] + [P2 / "ad_s2.jsonl"] + \
    [P2 / f"ad_boost_A{i}.jsonl" for i in (1, 2)] + [P2 / "ad_boost_D1.jsonl"] + \
    [P2 / f"ad_resume{i}.jsonl" for i in range(4)] + \
    [P2 / f"ad_final{i}.jsonl" for i in range(3)] + [P2 / "ad_last.jsonl"]
BC_FILES = [P2 / f for f in
            ["run_BC_core.jsonl", "bc_s2.jsonl", "bc_boost1.jsonl", "bc_boost2.jsonl",
             "bc_final.jsonl", "bc_last.jsonl", "bc_rem0.jsonl", "bc_rem1.jsonl", "bc_rem2.jsonl"]]


def load(files):
    cells = {}
    conflicts = 0
    for p in files:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            k = (r["target"], r["harness_id"], r["task_id"])
            if k in cells:
                if cells[k]["official_correct"] != r["official_correct"]:
                    conflicts += 1
                continue  # D16: first-write-wins in canonical file order
            cells[k] = r
    return cells, conflicts


def headroom(m, bare):
    pool = np.vstack([m, bare[None, :]]) if m.size else bare[None, :]
    return float(pool.max(axis=0).mean() - pool.mean(axis=1).max())


def build(df_cells, names, tasks):
    piv_rows = defaultdict(dict)
    want = set(names) | {"bare"}   # bare must be pivoted even when not in `names`
    for (t, h, task), r in df_cells.items():
        if t == TARGET and h in want and task in tasks:
            piv_rows[h][task] = r["official_correct"]
    bare = [piv_rows["bare"][t] for t in tasks] if "bare" in piv_rows else None
    present = [h for h in names if h in piv_rows and len(piv_rows[h]) == len(tasks)]
    m = np.array([[piv_rows[h][t] for t in tasks] for h in present], dtype=float) \
        if present else np.empty((0, len(tasks)))
    return present, m, bare


def membership():
    mem = defaultdict(list)
    for f in sorted(GEN.glob("[ABCD]_*_s[012].json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for r in d["results"]:
            if r["admitted"] and r["harness"] not in EXCLUDED:
                mem[(d["arm"], d["builder"], d["seed"])].append(r["harness"])
    return mem


def main():
    core = json.loads((ROOT / "experiment/phase2/split_p2_test_core.json").read_text())
    core_tasks = sorted({f"{d}#{i}" for d, idxs in core["by_db"].items() for i in idxs})

    ad_cells, ad_conf = load(AD_FILES)
    bc_cells, bc_conf = load(BC_FILES)
    mem = membership()

    # headroom per (arm, cell) on the SAME core items
    H = {}
    for (arm, builder, seed), hs in mem.items():
        if arm in ("A", "D"):
            present, m, bare = build(ad_cells, hs, core_tasks)
        else:
            present, m, bare = build(bc_cells, hs, core_tasks)
        if bare is None or not present:
            H[(arm, builder, seed)] = None
            continue
        H[(arm, builder, seed)] = headroom(m, np.array(bare, dtype=float))

    # paired cells with all four arms
    cells = sorted({(b, s) for (a, b, s) in mem})
    quad = []
    for (b, s) in cells:
        vals = {a: H.get((a, b, s)) for a in "ABCD"}
        if all(v is not None for v in vals.values()):
            quad.append(((b, s), vals))
    print(f"[factorial] {len(quad)} cells with all four arms on core-400")

    # paired contrasts per cell
    d_a = [v["D"] - v["A"] for _, v in quad]
    b_a = [v["B"] - v["A"] for _, v in quad]
    d_c = [v["D"] - v["C"] for _, v in quad]
    c_a = [v["C"] - v["A"] for _, v in quad]
    d_b = [v["D"] - v["B"] for _, v in quad]

    def ci(x, n=10000, seed=20260904):
        rng = np.random.default_rng(seed)
        x = np.array(x)
        boots = [rng.choice(x, len(x), replace=True).mean() for _ in range(n)]
        return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))

    gate_main = float(np.mean(b_a) / 2 + np.mean(d_c) / 2)
    strat_main = float(np.mean(c_a) / 2 + np.mean(d_b) / 2)
    inter = float(np.mean(d_c) - np.mean(b_a))

    out = {
        "n_cells": len(quad),
        "per_cell": [
            {"builder": b, "seed": s,
             "H": {a: round(v[a], 4) for a in "ABCD"},
             "D-A": round(v["D"] - v["A"], 4), "B-A": round(v["B"] - v["A"], 4),
             "D-C": round(v["D"] - v["C"], 4), "C-A": round(v["C"] - v["A"], 4)}
            for (b, s), v in quad],
        "gate_main_effect": round(gate_main, 4),
        "gate_main_ci95": [round(x, 4) for x in ci((np.array(b_a) + np.array(d_c)) / 2)],
        "strategy_main_effect": round(strat_main, 4),
        "strategy_main_ci95": [round(x, 4) for x in ci((np.array(c_a) + np.array(d_b)) / 2)],
        "interaction_DminusC_minus_BminusA": round(inter, 4),
        "interaction_ci95": [round(x, 4) for x in ci(np.array(d_c) - np.array(b_a))],
        "conflicts_resolved": ad_conf + bc_conf,
    }
    (P2 / "analysis_factorial.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(f"[factorial] gate main effect      : {gate_main:+.4f}  CI {out['gate_main_ci95']}")
    print(f"[factorial] strategy main effect  : {strat_main:+.4f}  CI {out['strategy_main_ci95']}")
    print(f"[factorial] interaction (D-C)-(B-A): {inter:+.4f}  CI {out['interaction_ci95']}")
    print(f"[factorial] wrote artifacts/phase2/analysis_factorial.json")


if __name__ == "__main__":
    main()
