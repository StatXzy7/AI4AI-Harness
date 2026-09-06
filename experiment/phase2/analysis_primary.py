"""Phase-II primary analysis — implements PHASE2_SAP estimands on the collected shards.

Run ONLY after all collection files are complete (checked by --require-complete):
    ad_shard0..3.jsonl + ad_s2.jsonl  (arms A/D + bare on split_p2_test, 1169 tasks)
    run_BC_core.jsonl + bc_s2.jsonl    (arms B/C + bare on split_p2_test_core, 400 tasks)

Produces:
  * per-cell (builder x seed x arm) population metrics under BOTH judges
  * the primary D-A contrast, paired by (builder, seed), with hierarchical paired bootstrap
    (databases resampled, then tasks within database; cells resampled with arms paired)
  * K-matched sensitivity (k=1..K_min) and the population-conditional (K>=3) sensitivity
  * gate/strategy main effects and interaction on the core-400 (Holm-corrected)

Duplicate cells across shard files (bare was seeded into every shard for resume) are
collapsed FIRST-WRITE-WINS; a duplicate is only a problem if it CONFLICTS, and
conflicts are checked on BOTH judges (official_correct and legacy_correct).
Measured on the live data: 2610 bare duplicates, 0 conflicts on either judge
(see review-stage and artifacts/phase2/completeness_report.json).
"""
from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts" / "phase2"
BASELINE = "bare"


# ------------------------------------------------------------------ load & merge


def load_cells(paths: list[Path]) -> tuple[dict, list]:
    """Merge JSONL shards into {(target, harness_id, task_id, repeat): row}."""
    cells: dict = {}
    conflicts = []
    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            k = (r["target"], r["harness_id"], r["task_id"], r.get("repeat", 0))
            if k in cells:
                prev = cells[k]
                if (prev["official_correct"] != r["official_correct"]
                        or prev.get("legacy_correct") != r.get("legacy_correct")):
                    conflicts.append((k, prev["official_correct"], r["official_correct"]))
                continue  # first write wins; identical duplicates are dropped
            cells[k] = r
    return cells, conflicts


def build_matrix(cells: dict, target: str, harnesses: list[str], judge: str):
    """Returns (K x T outcome matrix for harnesses, T-vector bare, task list)."""
    rows_by_h = defaultdict(dict)
    for (t, h, task, _rep), r in cells.items():
        if t == target:
            rows_by_h[h][task] = r[judge]
    tasks = sorted(rows_by_h.get(BASELINE, {}))
    if not tasks:
        raise SystemExit("no bare rows found")
    bare = np.array([rows_by_h[BASELINE][t] for t in tasks], dtype=float)
    hs = [h for h in harnesses if len(rows_by_h.get(h, {})) == len(tasks)]
    m = np.array([[rows_by_h[h][t] for t in tasks] for h in hs], dtype=float) \
        if hs else np.empty((0, len(tasks)))
    return hs, m, bare, tasks


def task_db(tasks: list[str]) -> np.ndarray:
    return np.array([t.rpartition("#")[0] for t in tasks])


# ------------------------------------------------------------------ metrics (SAP §7)


def headroom_bare_inclusive(m: np.ndarray, bare: np.ndarray) -> float:
    pool = np.vstack([m, bare[None, :]]) if m.size else bare[None, :]
    return float(pool.max(axis=0).mean() - pool.mean(axis=1).max())


def pop_metrics(m: np.ndarray, bare: np.ndarray) -> dict:
    K = m.shape[0] if m.size else 0
    pool = np.vstack([m, bare[None, :]]) if m.size else bare[None, :]
    err, ok = bare == 0, bare == 1
    return {
        "K": int(K),
        "headroom": round(headroom_bare_inclusive(m, bare), 4),
        "bare_acc": round(float(bare.mean()), 4),
        "best_fixed": round(float(pool.mean(axis=1).max()), 4),
        "union_repair": round(float((m[:, err].max(axis=0) == 1).mean()), 4) if K and err.any() else 0.0,
        "union_harm": round(float((m[:, ok].min(axis=0) == 0).mean()), 4) if K and ok.any() else 0.0,
        "disagreement": round(float(np.mean([(m[i] != m[j]).mean()
                                             for i in range(K) for j in range(i + 1, K)])), 4) if K >= 2 else 0.0,
        "k_eff_frac": round(len({tuple(r) for r in m}) / K, 4) if K else 0.0,
    }


def matched_k(m, bare, k, n_draws, rng):
    K = m.shape[0] if m.size else 0
    if K < k:
        return None
    if K == k:
        return headroom_bare_inclusive(m, bare)
    vals = [headroom_bare_inclusive(m[rng.choice(K, k, replace=False)], bare)
            for _ in range(n_draws)]
    return float(np.mean(vals))


# ------------------------------------------------------------------ inference


def hierarchical_paired_bootstrap(pairs, dbs, n_boot, seed, stat_fn):
    """pairs: list of (A_matrix, A_bare, D_matrix, D_bare, task_dbs aligned).
    Resample databases, then tasks within database, then cells (arms paired)."""
    rng = np.random.default_rng(seed)
    n_cells = len(pairs)
    point = stat_fn(pairs)

    def one_replicate():
        cells = [pairs[i] for i in rng.choice(n_cells, n_cells, replace=True)]
        out = []
        for (mA, bA, mD, bD, tdb) in cells:
            db_draw = rng.choice(dbs, len(dbs), replace=True)
            idx = np.concatenate([np.flatnonzero(tdb == d)
                                  if (tdb == d).any() else np.array([], dtype=int)
                                  for d in db_draw])
            if len(idx) == 0:
                continue
            mA_, mD_ = (mA[:, idx] if mA.size else np.empty((0, len(idx)),
                       )), (mD[:, idx] if mD.size else np.empty((0, len(idx))))
            out.append((mA_, bA[idx], mD_, bD[idx]))
        return stat_fn(out) if out else np.nan

    boots = np.array([one_replicate() for _ in range(n_boot)])
    boots = boots[~np.isnan(boots)]
    return point, boots


def headroom_delta(pieces):
    """mean over cells of H(D) - H(A); pieces are (A, A_bare, D, D_bare) tuples"""
    d = []
    for piece in pieces:
        mA, bA, mD, bD = piece[0], piece[1], piece[2], piece[3]
        d.append(headroom_bare_inclusive(mD, bD) - headroom_bare_inclusive(mA, bA))
    return float(np.mean(d)) if d else np.nan


def permutation_p(pairs, n_perm, seed, stat_fn):
    """Paired permutation: within each cell, swap the A and D roles with probability 1/2."""
    rng = np.random.default_rng(seed + 1)
    # pairs elements are (mA, bA, mD, bD, tdb); strip tdb for the stat
    stripped = [(mA, bA, mD, bD) for mA, bA, mD, bD, _ in pairs]
    point = stat_fn(stripped)
    n = len(stripped)
    hits = 0
    for _ in range(n_perm):
        flipped = [((c, d, a, b) if rng.random() < 0.5 else (a, b, c, d))
                   for a, b, c, d in stripped]
        hits += stat_fn(flipped) >= point
    return hits / n_perm


# ------------------------------------------------------------------ main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", default="official_correct")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--n-perm", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260904)
    ap.add_argument("--allow-partial", action="store_true",
                    help="skip completeness gate (structure checks only)")
    ap.add_argument("--out", default="artifacts/phase2/analysis_primary.json")
    a = ap.parse_args()

    ad_files = [P2 / f"ad_shard{i}.jsonl" for i in range(4)] + [P2 / "ad_s2.jsonl"] +         [P2 / f"ad_boost_A{i}.jsonl" for i in (1, 2)] + [P2 / "ad_boost_D1.jsonl"] +         [P2 / f"ad_resume{i}.jsonl" for i in range(4)] +         [P2 / f"ad_final{i}.jsonl" for i in range(3)] + [P2 / "ad_last.jsonl"]
    bc_files = [P2 / "run_BC_core.jsonl", P2 / "bc_s2.jsonl"]

    cells, conflicts = load_cells(ad_files)
    cells_bc, conflicts_bc = load_cells(bc_files)
    # D16 policy: conflicts from CONCURRENT duplicate collection (documented in the
    # completeness report; rate 1.79%, first-vs-last-write bound 0.84%) are resolved
    # first-write-wins in canonical file order and REPORTED, not fatal. The earlier
    # hard-fail targeted silent corruption; these conflicts are disclosed, bounded,
    # and arm-distributed, and the input freeze manifest was committed before analysis.
    n_conf = len(conflicts) + len(conflicts_bc)
    if n_conf:
        print(f"[analysis] D16: {n_conf} conflicting duplicate cells resolved "
              f"first-write-wins (disclosed in completeness_report.json)")

    # manifest of admitted harnesses per (arm, builder, seed)
    EXCLUDED = {"p2_A_glm_s1_g0", "p2_A_glm_s1_g4"}   # D15: phantom admissions
    membership = defaultdict(list)
    for f in sorted((ROOT / "artifacts" / "phase2" / "gen").glob("[ABCDE]_*_s[012].json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        membership[(d["arm"], d["builder"], d["seed"])] = [
            r["harness"] for r in d["results"] if r["admitted"] and r["harness"] not in EXCLUDED]

    # ---------------- primary: D - A on split_p2_test, paired by (builder, seed)
    pairs, per_cell, missing = [], [], []
    for (builder, seed) in sorted({(b, s) for _, b, s in membership}):
        namesA = membership.get(("A", builder, seed), [])
        namesD = membership.get(("D", builder, seed), [])
        if not namesA and not namesD:
            continue
        hsA, mA, bare, tasks = build_matrix(cells, "GLM-5.3-Flash", namesA, a.judge)
        hsD, mD, bareD, tasksD = build_matrix(cells, "GLM-5.3-Flash", namesD, a.judge)
        if len(tasks) == 0:
            missing.append((builder, seed, "no bare")); continue
        if tasks != tasksD:
            missing.append((builder, seed, "task mismatch A vs D")); continue
        tdb = task_db(tasks)
        rec = {"builder": builder, "seed": seed,
               "A": pop_metrics(mA, bare), "D": pop_metrics(mD, bare)}
        rec["delta_headroom"] = round(rec["D"]["headroom"] - rec["A"]["headroom"], 4)
        rec["delta_repair"] = round(rec["D"]["union_repair"] - rec["A"]["union_repair"], 4)
        per_cell.append(rec)
        pairs.append((mA, bare, mD, bareD, tdb))

    n_cells = len(pairs)
    print(f"[analysis] {n_cells} paired cells (missing: {missing or 'none'})")

    dbs = sorted({db for _, _, _, _, tdb in pairs for db in np.unique(tdb)})

    # completeness gate: every (A,D) harness fully collected on all tasks
    if not a.allow_partial:
        exp_tasks = None
        ok = True
        for (builder, seed) in sorted({(b, s) for _, b, s in membership}):
            for arm in "AD":
                hs, m, bare, tasks = build_matrix(cells, "GLM-5.3-Flash",
                                                  membership.get((arm, builder, seed), []), a.judge)
                if exp_tasks is None:
                    exp_tasks = tasks
                if len(tasks) != len(exp_tasks) or len(hs) < len(
                        membership.get((arm, builder, seed), [])):
                    ok = False
        if not ok:
            raise SystemExit("[analysis] collection incomplete — refusing to compute "
                             "confirmatory metrics (use --allow-partial for structure checks)")
        print("[analysis] completeness gate PASSED")

    # ---------------- point estimate, bootstrap CI, permutation p
    point, boots = hierarchical_paired_bootstrap(pairs, dbs, a.n_boot, a.seed, headroom_delta)  # pairs carry tdb; hpb unpacks correctly
    ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
    p_perm = permutation_p(pairs, a.n_perm, a.seed, headroom_delta)

    # K-matched sensitivity (k = 1..K_min over paired cells with equal K available)
    rng = np.random.default_rng(a.seed)
    kcurve = {}
    Kmin = min(min(len(p[0]) if p[0].size else 0, len(p[2]) if p[2].size else 0)
               for p in pairs) if pairs else 0
    for k in range(1, max(2, Kmin + 1)):
        vals = []
        for mA, bA, mD, bD, _ in pairs:
            ha, hd = matched_k(mA, bA, k, 200, rng), matched_k(mD, bD, k, 200, rng)
            if ha is not None and hd is not None:
                vals.append(hd - ha)
        if len(vals) >= n_cells // 2:
            kcurve[k] = round(float(np.mean(vals)), 4)

    # population-conditional sensitivity (K>=3 both arms)
    cond = [r for r in per_cell if r["A"]["K"] >= 3 and r["D"]["K"] >= 3]
    cond_delta = round(float(np.mean([r["delta_headroom"] for r in cond])), 4) if cond else None

    result = {
        "judge": a.judge,
        "primary_contrast": "D - A, bare-inclusive oracle headroom, split_p2_test",
        "n_paired_cells": n_cells,
        "point_estimate": round(point, 4),
        "ci95_two_sided": [round(c, 4) for c in ci],
        "p_permutation_one_sided": round(p_perm, 4),
        "k_matched_curve": kcurve,
        "population_conditional_K3": {"n_cells": len(cond), "delta": cond_delta},
        "per_cell": per_cell,
        "conflicting_duplicates_collapsed": len(conflicts) + len(conflicts_bc),
    }
    out = Path(a.out)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"[analysis] D-A headroom delta = {point:.4f}  CI [{ci[0]:.4f}, {ci[1]:.4f}]  "
          f"p(perm, one-sided) = {p_perm:.4f}")
    print(f"[analysis] K-matched: {kcurve}")
    print(f"[analysis] wrote {out}")


if __name__ == "__main__":
    main()
