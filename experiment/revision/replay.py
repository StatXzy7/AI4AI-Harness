"""API-free post-review reanalysis of the archived, ORIGINAL gate experiment.

This is not a repaired-gate experiment or a prospectively frozen analysis.
Run from the repository root: python -m experiment.revision.replay
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts/phase2"
TARGET = "GLM-5.3-Flash"
EXCLUDED = {"p2_A_glm_s1_g0", "p2_A_glm_s1_g4"}  # historical D15
ARMS = "ABCD"
CONTRASTS = np.array([[-1., 0., 0., 1.],
                      [-.5, .5, -.5, .5],
                      [-.5, -.5, .5, .5],
                      [1., -1., -1., 1.]])


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_sources(manifest_paths):
    """Manifest order, then line order, first write wins; never mix repeats/cache.

    Each group retains its own baseline until the analysis explicitly chooses the
    AD baseline for all arms. Every retained row carries its source file and line.
    """
    groups, inventory, audit = {}, [], {}
    for group, manifest_path in manifest_paths.items():
        rows, counts, identities = {}, Counter(), {}
        inventory.append({"path": manifest_path.relative_to(ROOT).as_posix(),
                          "sha256": digest(manifest_path)})
        for entry in read_json(manifest_path)["files"]:
            path = manifest_path.parent / entry["file"]
            sha = digest(path)
            if path.stat().st_size != entry["bytes"] or not sha.startswith(entry["sha256_16"]):
                raise ValueError(f"frozen input mismatch: {path.name}")
            inventory.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha})
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                r = json.loads(line)  # malformed input is an error, not an exclusion
                required = ("target", "harness_id", "task_id", "repeat", "no_cache",
                            "code_hash", "official_correct", "legacy_correct")
                if any(k not in r for k in required):
                    raise ValueError(f"missing provenance fields: {path.name}:{line_no}")
                for judge in ("official_correct", "legacy_correct"):
                    if r[judge] not in (0, 1):
                        raise ValueError(f"nonbinary {judge}: {path.name}:{line_no}")
                identity = (r["target"], r["harness_id"])
                previous_hash = identities.setdefault(identity, r["code_hash"])
                if previous_hash != r["code_hash"]:
                    raise ValueError(f"source hash changed: {identity}")
                key = tuple(r[k] for k in ("target", "harness_id", "task_id", "repeat", "no_cache"))
                counts["rows"] += 1
                if key in rows:
                    counts["duplicates"] += 1
                    if any(rows[key][j] != r[j] for j in ("official_correct", "legacy_correct")):
                        counts["verdict_conflicts"] += 1
                    continue
                rows[key] = {**r, "source_file": path.relative_to(ROOT).as_posix(),
                             "source_line": line_no}
        groups[group] = rows
        audit[group] = dict(counts)
    return groups, inventory, audit


def task_ids(path):
    return sorted(f"{db}#{i}" for db, indices in read_json(path)["by_db"].items() for i in indices)


def membership():
    mem, files, generation = {}, [], []
    for path in sorted((P2 / "gen").glob("[ABCD]_*_s[012].json")):
        d = read_json(path)
        key = (d["builder"], d["seed"], d["arm"])
        if key in mem:
            raise ValueError(f"duplicate generation unit: {key}")
        mem[key] = [r["harness"] for r in d["results"]
                    if r["admitted"] and r["harness"] not in EXCLUDED]
        files.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)})
        generation.append({"builder": d["builder"], "seed": d["seed"], "arm": d["arm"],
                           "slots": d["n_slots"], "attempt_cap": d["raw_attempts_per_slot"],
                           "actual_raw_attempts": d["raw_total"],
                           "K_candidate": len(mem[key]),
                           "prompt_rejections": sum(
                               a.get("neutral_valid", False) and
                               a.get("mechanism_detail", {}).get("verdict") == "NO_MECHANISM_declared"
                               for r in d["results"] for a in r["attempts"]
                               if isinstance(a.get("mechanism_detail", {}), dict))})
    builders = sorted({b for b, _, _ in mem})
    expected = set(itertools.product(builders, range(3), ARMS))
    if len(builders) != 6 or set(mem) != expected:
        raise ValueError("expected complete 6 builders x 3 seeds x 4 arms")
    return mem, files, generation


def vector(rows, harness, tasks):
    # All historical primary measurements are repeat 0 with response caching on.
    return np.array([rows[(TARGET, harness, t, 0, False)]["official_correct"]
                     for t in tasks], dtype=float)


def make_pools(groups, mem, tasks, arms):
    """Fixed task set, complete membership, one AD baseline reused in every arm."""
    bare = vector(groups["AD"], "bare", tasks)
    keys = sorted({(b, s) for b, s, _ in mem})
    pools = []
    for b, s in keys:
        cell = []
        for arm in arms:
            names = mem[b, s, arm]
            rows = groups["AD" if arm in "AD" else "BC"]
            cell.append(np.vstack([bare] + [vector(rows, h, tasks) for h in names]))
        pools.append(cell)
    return keys, pools


def metrics(pool):
    oracle = float(pool.max(axis=0).mean())
    best = float(pool.mean(axis=1).max())
    return {"K_candidate": len(pool) - 1, "K_total": len(pool),
            "bare_accuracy": float(pool[0].mean()),
            "mean_member_accuracy": float(pool.mean()), "best_fixed": best,
            "oracle_accuracy": oracle, "headroom": oracle - best}


def sample_tasks(dbs, rng):
    """Shared draw across every cell/arm; repeated DB copies get independent draws."""
    unique = np.unique(dbs)
    groups = {d: np.flatnonzero(dbs == d) for d in unique}
    return np.concatenate([rng.choice(groups[d], len(groups[d]), replace=True)
                           for d in rng.choice(unique, len(unique), replace=True)])


def sample_cells(keys, rng):
    """Keep all six fixed builders; resample their three generation seeds within builder."""
    builders = sorted({b for b, _ in keys})
    indices = [np.array([i for i, (bb, _) in enumerate(keys) if bb == b]) for b in builders]
    return np.concatenate([rng.choice(ii, len(ii), replace=True) for ii in indices])


def headrooms(pools, idx):
    return np.array([[metrics(p[:, idx])["headroom"] for p in cell] for cell in pools])


def bootstrap(pools, keys, dbs, weights, n_boot, seed):
    rng = np.random.default_rng(seed)
    point_cells = headrooms(pools, np.arange(len(dbs))) @ weights.T
    boots = np.empty((n_boot, len(weights)))
    for i in range(n_boot):
        idx = sample_tasks(dbs, rng)
        cell_idx = sample_cells(keys, rng)
        boots[i] = (headrooms(pools, idx) @ weights.T)[cell_idx].mean(axis=0)
    return point_cells, np.percentile(boots, [2.5, 97.5], axis=0).T


def sign_p(contrasts, one_sided=False):
    """Exact cell-level sign test under sign-symmetry, conditional on observed tasks.

    This is a sign-flip test of mean contrasts, not a binomial sign-count test,
    and is not a randomization-based causal test of the implemented gate.
    """
    contrasts = np.asarray(contrasts)
    signs = np.array(list(itertools.product((-1., 1.), repeat=len(contrasts))))
    null = signs @ contrasts / len(contrasts)
    observed = contrasts.mean(axis=0)
    hits = null >= observed - 1e-12 if one_sided else np.abs(null) >= np.abs(observed) - 1e-12
    return hits.mean(axis=0)


def holm(pvalues):
    p = np.asarray(pvalues)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    adjusted[order] = np.minimum(1., np.maximum.accumulate(p[order] * np.arange(len(p), 0, -1)))
    return adjusted


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "artifacts/revision_20260910")
    args = ap.parse_args()
    if args.n_boot < 100:
        ap.error("use at least 100 bootstrap replicates; final report uses 10000")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    groups, inventory, audit = load_sources({"AD": P2 / "primary_input_manifest.json",
                                            "BC": P2 / "bc_input_manifest.json"})
    mem, gen_files, generation = membership()
    inventory.extend(gen_files)
    result = {"analysis_version": "revision-20260910-v1", "status": "post-review corrected reanalysis",
              "gate_version": "original Phase-II gate, unchanged",
              "baseline_policy": "AD first-write-wins bare reused for all arms on identical tasks",
              "record_policy": "first-write-wins in frozen manifest order, then line order",
              "inference": "fixed six builders; seeds resampled within builder; shared database then within-database task resampling; no new execution repeats",
              "sign_test_scope": "exact cell sign-flip reference under sign-symmetry; conditional on observed tasks; not causal randomization inference",
              "n_boot": args.n_boot, "seed": args.seed, "input_audit": audit,
              "generation": generation}
    for name, split, arms, weights in (
        ("primary", "split_p2_test.json", "AD", np.array([[-1., 1.]])),
        ("core", "split_p2_test_core.json", ARMS, CONTRASTS)):
        split_path = ROOT / "experiment/phase2" / split
        tasks = task_ids(split_path)
        inventory.append({"path": split_path.relative_to(ROOT).as_posix(), "sha256": digest(split_path)})
        keys, pools = make_pools(groups, mem, tasks, arms)
        dbs = np.array([t.rpartition("#")[0] for t in tasks])
        deltas, cis = bootstrap(pools, keys, dbs, weights, args.n_boot, args.seed)
        pvalues = sign_p(deltas, one_sided=name == "primary")
        arm_metrics = {a: [metrics(cell[i]) for cell in pools] for i, a in enumerate(arms)}
        result[name] = {"n_tasks": len(tasks), "n_databases": len(set(dbs)), "n_cells": len(keys),
                        "contrast_order": ["D-A"] if name == "primary" else ["D-A", "gate", "strategy", "interaction"],
                        "point": deltas.mean(axis=0).tolist(), "ci95_unadjusted": cis.tolist(),
                        "p_signflip": pvalues.tolist(),
                        "arm_means": {a: {k: float(np.mean([m[k] for m in mm])) for k in mm[0]}
                                      for a, mm in arm_metrics.items()},
                        "per_cell": [{"builder": b, "seed": s, "contrasts": deltas[i].tolist(),
                                      "arms": {a: arm_metrics[a][i] for a in arms}}
                                     for i, (b, s) in enumerate(keys)]}
        if name == "core":
            result[name]["holm_secondaries"] = holm(pvalues[1:]).tolist()
            result[name]["AD_vs_BC_bare_conflicts"] = int(np.sum(
                vector(groups["AD"], "bare", tasks) != vector(groups["BC"], "bare", tasks)))
        print(f"{name}: {len(tasks)} tasks, {len(keys)} cells; contrasts={result[name]['point']}", flush=True)
    inventory.extend({"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)}
                     for p in sorted((ROOT / "experiment/revision").glob("*.py")))
    result["inputs"] = inventory
    path = args.out_dir / "corrected_analysis.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    # A compact canonical row index permits source-level reconstruction without copying SQL.
    index = args.out_dir / "canonical_rows.jsonl"
    with index.open("w", encoding="utf-8", newline="\n") as f:
        for group, rows in groups.items():
            for r in rows.values():
                keep = ("target", "harness_id", "code_hash", "task_id", "repeat", "no_cache",
                        "official_correct", "legacy_correct", "source_file", "source_line")
                f.write(json.dumps({"collection": group, **{k: r[k] for k in keep}}) + "\n")
    print(path)


if __name__ == "__main__":
    main()
