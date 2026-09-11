"""Canonical K-matched and repeat reanalysis; no new model calls.

python -m experiment.revision.sensitivity --n-boot 10000
The original archived analyses are never overwritten.
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np

from experiment.revision.replay import (
    P2, ROOT, TARGET, digest, load_sources, make_pools, membership, read_json,
    sample_cells, sample_tasks,
)

OUT = ROOT / "artifacts/revision_20260910"


def exact_subsets(pool, k):
    """All k-candidate subsets; bare (row zero) is retained in every subset."""
    if not 0 <= k < len(pool):
        raise ValueError("k must be between zero and the available candidate count")
    indices = np.array([(0, *c) for c in itertools.combinations(range(1, len(pool)), k)])
    # The expected union is linear in task weights; best-fixed must be reselected
    # within every subset for each bootstrap draw.
    union = pool[indices].max(axis=1).mean(axis=0)
    return pool, indices, union


def subset_metrics(prepared, weights):
    pool, indices, union = prepared
    oracle = float(union @ weights)
    best = float((pool @ weights)[indices].max(axis=1).mean())
    return np.array([oracle, best, oracle - best])


def weighted_metrics(pool, weights):
    """Pool need not contain bare; the caller explicitly defines its membership."""
    if len(pool) == 0:
        raise ValueError("empty measurement pool")
    oracle = float(pool.max(axis=0) @ weights)
    best = float((pool @ weights).max())
    return np.array([oracle, best, oracle - best])


def shared_bootstrap(keys, dbs, cell_stat, n_boot, seed):
    """Same DB/task/within-builder seed scheme as the corrected primary analysis."""
    rng = np.random.default_rng(seed)
    n = len(dbs)
    per_cell = cell_stat(np.full(n, 1 / n))
    boots = np.empty((n_boot, *per_cell.shape[1:]))
    for i in range(n_boot):
        idx = sample_tasks(dbs, rng)
        weights = np.bincount(idx, minlength=n) / len(idx)
        cell_idx = sample_cells(keys, rng)
        boots[i] = cell_stat(weights)[cell_idx].mean(axis=0)
    return per_cell, np.percentile(boots, [2.5, 97.5], axis=0)


def kmatched(groups, mem, tasks, n_boot, seed):
    keys, pools = make_pools(groups, mem, tasks, "ABCD")
    prepared, ks = [], []
    for cell in pools:
        matches, counts = [], []
        for lo, hi in ((0, 1), (2, 3)):
            k = min(len(cell[lo]), len(cell[hi])) - 1
            matches.append((exact_subsets(cell[lo], k), exact_subsets(cell[hi], k)))
            counts.append(k)
        prepared.append(matches)
        ks.append(counts)

    def cell_stat(weights):
        values = []
        for matches in prepared:
            ba, dc = [subset_metrics(hi, weights) - subset_metrics(lo, weights)
                      for lo, hi in matches]
            values.append([ba, dc, (ba + dc) / 2])
        return np.array(values)

    dbs = np.array([t.rpartition("#")[0] for t in tasks])
    points, ci = shared_bootstrap(keys, dbs, cell_stat, n_boot, seed)
    return {"status": "post-review fixed-K sensitivity; not a causal mediation estimate",
            "n_cells": len(keys), "n_tasks": len(tasks),
            "baseline": "shared AD bare retained; K_candidate excludes bare",
            "matching": "min candidate K separately for A/B and C/D; exact uniform subset enumeration on both sides",
            "contrast_order": ["B-A", "D-C", "gate_mean"],
            "metric_order": ["oracle_accuracy", "best_fixed", "headroom"],
            "point": points.mean(axis=0).tolist(), "ci95_unadjusted": ci.tolist(),
            "per_cell": [{"builder": b, "seed": s, "k_candidate_AB": ks[i][0],
                          "k_candidate_CD": ks[i][1], "contrasts": points[i].tolist()}
                         for i, (b, s) in enumerate(keys)]}


def repeat_rows(canonical, repeats, group, names, tasks, repeat=0):
    """Strictly align a named acquisition group, with hashes checked against original."""
    rows = repeats[group]
    expected = {(TARGET, h, t, repeat, True) for h in names for t in tasks}
    if set(rows) != expected:
        raise ValueError(f"{group}: unexpected repeat coverage; missing={len(expected-set(rows))}, extra={len(set(rows)-expected)}")
    values = {}
    for h in names:
        records = [rows[TARGET, h, t, repeat, True] for t in tasks]
        for t, row in zip(tasks, records):
            if row["code_hash"] != canonical[TARGET, h, t, 0, False]["code_hash"]:
                raise ValueError(f"source changed across execution groups: {group}/{h}")
        values[h] = np.array([r["official_correct"] for r in records], dtype=float)
    return values


def repeat_analysis(groups, repeats, mem, tasks, n_boot, seed):
    keys = sorted({(b, s) for b, s, _ in mem})
    selected = {(b, s, a): mem[b, s, a][:2] for b, s in keys for a in "AD"}
    names = [h for hs in selected.values() for h in hs]
    d_names = [h for (b, s, a), hs in selected.items() if a == "D" for h in hs]
    cached = {h: np.array([groups["AD"][TARGET, h, t, 0, False]["official_correct"]
                           for t in tasks], dtype=float) for h in names}
    off = repeat_rows(groups["AD"], repeats, "r2_pass1", names, tasks)
    off_d = repeat_rows(groups["AD"], repeats, "r2_pass2_D", d_names, tasks)
    arrays = []
    for b, s in keys:
        cell = []
        for a in "AD":
            hs = selected[b, s, a]
            if not hs:
                raise ValueError("R2 acquired no member for this arm/cell; no baseline substitution allowed")
            cell.append((np.array([cached[h] for h in hs]), np.array([off[h] for h in hs])))
        d_repeat = np.array([off_d[h] for h in selected[b, s, "D"]])
        arrays.append((cell, d_repeat))

    def cell_stat(weights):
        values = []
        for cell, d_repeat in arrays:
            (a0, a1), (d0, d1) = cell
            cached_delta = weighted_metrics(d0, weights)[2] - weighted_metrics(a0, weights)[2]
            off_delta = weighted_metrics(d1, weights)[2] - weighted_metrics(a1, weights)[2]
            values.append([cached_delta, off_delta, off_delta - cached_delta,
                           float((a0 != a1).mean(axis=0) @ weights),
                           float((d0 != d1).mean(axis=0) @ weights),
                           float((d1 != d_repeat).mean(axis=0) @ weights)])
        return np.array(values)

    dbs = np.array([t.rpartition("#")[0] for t in tasks])
    points, ci = shared_bootstrap(keys, dbs, cell_stat, n_boot, seed)
    flips = sum(int(np.sum(cached[h] != off[h])) for h in names)
    d_flips = sum(int(np.sum(off[h] != off_d[h])) for h in d_names)
    eligible = [i for i, (b, s) in enumerate(keys)
                if min(len(selected[b, s, a]) for a in "AD") >= 2]
    return {"status": "archived execution variability; not a balanced clone control or causal cache intervention",
            "acquisition_identity": "r2_pass1 and r2_pass2_D remain separate despite identical stored repeat=0",
            "n_cells": len(keys), "n_tasks": len(tasks), "n_harnesses": len(names),
            "baseline": "no bare acquired in R2; subset headroom explicitly EXCLUDES bare in both conditions",
            "population": "first two callable admitted candidates per arm/cell; singleton headroom zero; no K-based cell exclusion",
            "inference": "shared DB/task/seed resampling, conditional on the observed acquisition groups; no future-execution variance identified",
            "metric_order": ["D-A_cached_headroom", "D-A_cacheoff_headroom", "change_in_D-A",
                             "A_flip_rate_cell_mean", "D_flip_rate_cell_mean", "D_repeat_flip_rate_cell_mean"],
            "point": points.mean(axis=0).tolist(), "ci95_unadjusted": ci.tolist(),
            "micro_verdict_flips": {"n": len(names)*len(tasks), "flips": flips,
                                    "rate": flips/(len(names)*len(tasks))},
            "micro_D_repeat_flips": {"n": len(d_names)*len(tasks), "flips": d_flips,
                                      "rate": d_flips/(len(d_names)*len(tasks))},
            "legacy_eligible_scope_diagnostic": {
                "n_cells": len(eligible),
                "rule": "both A and D have at least two acquired members; shown only to reconcile the old report",
                "point": points[eligible].mean(axis=0).tolist()},
            "per_cell": [{"builder": b, "seed": s, "A_members": selected[b, s, "A"],
                          "D_members": selected[b, s, "D"], "metrics": points[i].tolist()}
                         for i, (b, s) in enumerate(keys)]}


def main():
    import json

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--out-name", default="sensitivity.json")
    args = ap.parse_args()
    if args.n_boot < 100:
        ap.error("at least 100 replicates required (10000 for paper)")
    # Both analyses consume the same original canonical sources and admitted membership.
    groups, inventory, audit = load_sources({"AD": P2 / "primary_input_manifest.json",
                                            "BC": P2 / "bc_input_manifest.json"})
    repeat_paths = {name: OUT / "inputs" / f"{name}.json" for name in ("r2_pass1", "r2_pass2_D")}
    repeats, repeat_inventory, repeat_audit = load_sources(repeat_paths)
    mem, gen_inventory, _ = membership()
    split = ROOT / "experiment/phase2/split_p2_test_core.json"
    tasks = sorted(f"{d}#{i}" for d, ii in read_json(split)["by_db"].items() for i in ii)
    result = {"analysis_version": "sensitivity-20260910-v1", "n_boot": args.n_boot,
              "seed": args.seed, "canonical_source_audit": audit, "repeat_source_audit": repeat_audit}
    result["kmatched"] = kmatched(groups, mem, tasks, args.n_boot, args.seed)
    print("K-matched gate headroom:", result["kmatched"]["point"][2][2], flush=True)
    result["r2"] = repeat_analysis(groups, repeats, mem, tasks, args.n_boot, args.seed)
    print("R2 contrasts:", result["r2"]["point"][:3], flush=True)
    result["inputs"] = inventory + repeat_inventory + gen_inventory + [
        {"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in
        (split, ROOT / "experiment/revision/replay.py", ROOT / "experiment/revision/sensitivity.py")]
    (OUT / args.out_name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
