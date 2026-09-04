"""Phase-II outcome table — the primary analysis.

Computes the SAP estimands (union repair, oracle headroom, disagreement, K_eff) per
population and reports the primary D−A contrast paired by (builder, seed). Dual-scored
under both the legacy judge and the official BIRD judge.

Usage:
    python experiment/phase2/outcome_table.py \
        --parquet artifacts/phase2/outcomes_p2_test.parquet \
        --out artifacts/phase2/table_primary.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_matrix(parquet: Path):
    """Returns df with columns [task_id, harness_id, harness_correct, official_correct]."""
    import pandas as pd
    df = pd.read_parquet(parquet)
    if "official_correct" not in df.columns:
        raise SystemExit(f"{parquet.name} lacks official_correct — run official_scorer first")
    return df


def outcome_vec(df, harness_id: str, judge: str) -> list[int]:
    col = "official_correct" if judge == "official" else "harness_correct"
    return df[df["harness_id"] == harness_id].sort_values("task_id")[col].tolist()


def metrics(df, population: dict, bare_id: str, judge: str) -> dict:
    """Compute SAP metrics for one population under one judge."""
    tasks = sorted(df["task_id"].unique())
    n = len(tasks)
    H_ids = population["harness_ids"]
    K = len(H_ids)

    # Outcome matrix: tasks × (bare + population)
    Y = {}
    Y[bare_id] = outcome_vec(df, bare_id, judge)
    for h in H_ids:
        Y[h] = outcome_vec(df, h, judge)

    # Bare errors
    bare_errors = {i for i, y in enumerate(Y[bare_id]) if y == 0}
    n_bare_err = len(bare_errors)

    # Union repair / harm
    repaired = set()
    harmed = set()
    for h in H_ids:
        for i in range(n):
            if Y[bare_id][i] == 0 and Y[h][i] == 1:
                repaired.add(i)
            if Y[bare_id][i] == 1 and Y[h][i] == 0:
                harmed.add(i)

    union_repair = len(repaired) / n_bare_err if n_bare_err else 0.0
    union_harm = len(harmed) / (n - n_bare_err) if n > n_bare_err else 0.0

    # Pairwise disagreement
    pairs = []
    for i, h1 in enumerate(H_ids):
        for h2 in H_ids[i+1:]:
            disagree = sum(Y[h1][t] != Y[h2][t] for t in range(n))
            pairs.append(disagree / n)
    mean_disagreement = sum(pairs) / len(pairs) if pairs else 0.0

    # K_eff
    unique_vecs = len({tuple(Y[h]) for h in H_ids})
    k_eff = unique_vecs / K if K else 0.0

    # Oracle headroom (bare-inclusive)
    oracle_correct = [max([Y[bare_id][i]] + [Y[h][i] for h in H_ids]) for i in range(n)]
    best_fixed = max([sum(Y[bare_id])] + [sum(Y[h]) for h in H_ids])
    acc_oracle = sum(oracle_correct) / n
    acc_best = best_fixed / n
    headroom = acc_oracle - acc_best

    return {
        "judge": judge,
        "n_tasks": n, "K": K, "n_bare_errors": n_bare_err,
        "union_repair": round(union_repair, 4),
        "union_harm": round(union_harm, 4),
        "mean_disagreement": round(mean_disagreement, 4),
        "k_eff": round(k_eff, 4),
        "acc_oracle": round(acc_oracle, 4),
        "acc_best_fixed": round(acc_best, 4),
        "oracle_headroom": round(headroom, 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    df = load_matrix(Path(a.parquet))
    manifest_path = Path(a.out).parent / "eval_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"run queue_evaluation.py first to produce {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Identify bare
    bare_candidates = [h for h in df["harness_id"].unique() if "bare" in h.lower()]
    if len(bare_candidates) != 1:
        raise SystemExit(f"expected exactly one bare harness, found {bare_candidates}")
    bare_id = bare_candidates[0]

    results = []
    for pop in manifest["populations"]:
        for judge in ["legacy", "official"]:
            m = metrics(df, pop, bare_id, judge)
            results.append({
                "arm": pop["arm"], "builder": pop["builder"], "seed": pop["seed"],
                **m
            })

    # Primary contrast: D − A, paired by (builder, seed)
    by_cell = collections.defaultdict(dict)
    for r in results:
        if r["arm"] in ("A", "D") and r["judge"] == "official":
            by_cell[(r["builder"], r["seed"])][r["arm"]] = r

    paired = []
    for (builder, seed), arms in sorted(by_cell.items()):
        if "A" in arms and "D" in arms:
            delta_repair = arms["D"]["union_repair"] - arms["A"]["union_repair"]
            delta_headroom = arms["D"]["oracle_headroom"] - arms["A"]["oracle_headroom"]
            paired.append({
                "builder": builder, "seed": seed,
                "A_repair": arms["A"]["union_repair"],
                "D_repair": arms["D"]["union_repair"],
                "delta_repair": round(delta_repair, 4),
                "A_headroom": arms["A"]["oracle_headroom"],
                "D_headroom": arms["D"]["oracle_headroom"],
                "delta_headroom": round(delta_headroom, 4),
            })

    mean_delta_repair = sum(p["delta_repair"] for p in paired) / len(paired) if paired else 0.0
    mean_delta_headroom = sum(p["delta_headroom"] for p in paired) / len(paired) if paired else 0.0

    output = {
        "n_populations": len(manifest["populations"]),
        "n_tasks": manifest["n_tasks"],
        "n_paired_cells": len(paired),
        "primary_contrast": "D − A (forced+gated minus free+ungated)",
        "primary_metric": "union_repair (official judge)",
        "mean_delta_repair": round(mean_delta_repair, 4),
        "mean_delta_headroom": round(mean_delta_headroom, 4),
        "per_population": results,
        "paired_deltas": paired,
    }

    Path(a.out).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"[table] {len(results)} population×judge rows")
    print(f"[table] {len(paired)} paired (builder×seed) cells")
    print(f"[table] primary D−A: repair Δ={mean_delta_repair:.4f}, headroom Δ={mean_delta_headroom:.4f}")
    print(f"[table] wrote {a.out}")


if __name__ == "__main__":
    main()
