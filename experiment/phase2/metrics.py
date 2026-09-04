"""Phase-II metrics and inference, implementing PHASE2_SAP.md v1.2.

Headroom is BARE-INCLUSIVE:

    H(P) = Acc( x -> max_{H in P u {H0}} Y(x,H) ) - max_{H in P u {H0}} Acc(H)

so it is total: K=0 gives exactly 0 (only bare remains), and K=1 is a genuine bare-vs-harness
conditional-routing problem rather than a degenerate 0. This is what lets every builder x seed
cell enter the primary contrast regardless of how many harnesses were admitted -- excluding
low-K cells would condition on a post-treatment outcome and silently change the estimand to
"conditional on having generated k valid harnesses".

Inference is a hierarchical paired bootstrap: databases resampled with replacement, then tasks
within each drawn database, and (builder, seed) cells resampled with arms kept PAIRED. Tasks are
not i.i.d. (they share a schema within a database) and the intervention is applied to cells, not
tasks, so a flat task bootstrap is wrong in both directions.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "bare"


# ----------------------------------------------------------------- population metrics


def _mat(df: pd.DataFrame, harnesses: list[str], judge: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (K x T outcome matrix for `harnesses`, T-vector for bare) aligned on task_id."""
    piv = df.pivot_table(index="harness_id", columns="task_id", values=judge)
    tasks = sorted(piv.columns)
    bare = piv.loc[BASELINE, tasks].to_numpy(dtype=float) if BASELINE in piv.index else None
    if bare is None:
        raise ValueError("baseline 'bare' missing from matrix")
    present = [h for h in harnesses if h in piv.index]
    m = piv.loc[present, tasks].to_numpy(dtype=float) if present else np.empty((0, len(tasks)))
    return m, bare


def headroom(m: np.ndarray, bare: np.ndarray) -> float:
    """Bare-inclusive oracle headroom. K=0 -> 0.0 by construction."""
    pool = np.vstack([m, bare[None, :]]) if m.size else bare[None, :]
    oracle = pool.max(axis=0).mean()
    best_fixed = pool.mean(axis=1).max()
    return float(oracle - best_fixed)


def population_metrics(m: np.ndarray, bare: np.ndarray) -> dict:
    K, T = m.shape if m.size else (0, len(bare))
    pool = np.vstack([m, bare[None, :]]) if m.size else bare[None, :]
    out = {
        "K": int(K),
        "headroom": headroom(m, bare),
        "bare_acc": float(bare.mean()),
        "best_fixed_acc": float(pool.mean(axis=1).max()),
        "oracle_acc": float(pool.max(axis=0).mean()),
    }
    err = bare == 0
    ok = bare == 1
    out["union_repair"] = float((m[:, err].max(axis=0) == 1).mean()) if K and err.any() else 0.0
    out["union_harm"] = float((m[:, ok].min(axis=0) == 0).mean()) if K and ok.any() else 0.0
    if K >= 2:
        d = [float((m[i] != m[j]).mean()) for i in range(K) for j in range(i + 1, K)]
        out["pairwise_disagreement"] = float(np.mean(d))
    else:
        out["pairwise_disagreement"] = 0.0
    out["K_eff_frac"] = float(len({tuple(r) for r in m}) / K) if K else 0.0
    return out


def matched_k_headroom(m: np.ndarray, bare: np.ndarray, k: int, n_draws: int, rng) -> float | None:
    """Mean headroom over random size-k subsets. None when the population is too small."""
    K = m.shape[0] if m.size else 0
    if K < k:
        return None
    if K == k:
        return headroom(m, bare)
    vals = [headroom(m[rng.choice(K, k, replace=False)], bare) for _ in range(n_draws)]
    return float(np.mean(vals))


# ----------------------------------------------------------------- inference


def hierarchical_paired_bootstrap(cells: list[dict], arm_a: str, arm_b: str, judge: str,
                                  n_boot: int = 10000, seed: int = 20260904) -> dict:
    """Paired arm_b - arm_a difference in headroom.

    Each `cell` is {'builder','seed','dbs':{db: {'arm': (m, bare)}}}. One replicate resamples
    databases, then tasks within database, then cells -- arms stay paired inside a cell.
    """
    rng = np.random.default_rng(seed)
    dbs = sorted({db for c in cells for db in c["dbs"]})
    n_cells = len(cells)

    def stat(cell_idx, db_list, task_idx) -> float:
        diffs = []
        for ci in cell_idx:
            c = cells[ci]
            ma, ba, mb, bb = [], [], [], []
            for db in db_list:
                if db not in c["dbs"]:
                    continue
                ti = task_idx[db]
                a_m, a_bare = c["dbs"][db].get(arm_a, (np.empty((0, 0)), None))
                b_m, b_bare = c["dbs"][db].get(arm_b, (np.empty((0, 0)), None))
                if a_bare is None or b_bare is None:
                    continue
                ma.append(a_m[:, ti] if a_m.size else np.empty((0, len(ti))))
                ba.append(a_bare[ti])
                mb.append(b_m[:, ti] if b_m.size else np.empty((0, len(ti))))
                bb.append(b_bare[ti])
            if not ba:
                continue
            A = (np.hstack(ma) if ma[0].size or any(x.size for x in ma) else np.empty((0, 0)),
                 np.hstack(ba))
            B = (np.hstack(mb) if mb[0].size or any(x.size for x in mb) else np.empty((0, 0)),
                 np.hstack(bb))
            diffs.append(headroom(*B) - headroom(*A))
        return float(np.mean(diffs)) if diffs else np.nan

    full_tasks = {}
    for db in dbs:
        n = next((c["dbs"][db][arm_a][1].shape[0] for c in cells
                  if db in c["dbs"] and arm_a in c["dbs"][db]), 0)
        full_tasks[db] = np.arange(n)
    point = stat(list(range(n_cells)), dbs, full_tasks)

    boot = []
    for _ in range(n_boot):
        db_draw = list(rng.choice(dbs, len(dbs), replace=True))
        ti = {db: rng.choice(len(full_tasks[db]), len(full_tasks[db]), replace=True)
              for db in set(db_draw) if len(full_tasks[db])}
        ci = rng.choice(n_cells, n_cells, replace=True)
        v = stat(ci, db_draw, ti)
        if not np.isnan(v):
            boot.append(v)
    boot = np.array(boot)

    # paired permutation: swap arm labels within a cell
    perm = []
    for _ in range(n_boot):
        flip = rng.random(n_cells) < 0.5
        d = []
        for ci in range(n_cells):
            c = cells[ci]
            a, b = (arm_b, arm_a) if flip[ci] else (arm_a, arm_b)
            try:
                ma, ba = _merge(c, a, dbs)
                mb, bb = _merge(c, b, dbs)
            except KeyError:
                continue
            d.append(headroom(mb, bb) - headroom(ma, ba))
        if d:
            perm.append(float(np.mean(d)))
    perm = np.array(perm)

    return {
        "contrast": f"{arm_b} - {arm_a}", "judge": judge, "n_cells": n_cells,
        "point": point,
        "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        "p_perm_one_sided": float((perm >= point).mean()) if len(perm) else float("nan"),
        "n_boot": len(boot),
    }


def _merge(cell, arm, dbs):
    ms, bs = [], []
    for db in dbs:
        if db in cell["dbs"] and arm in cell["dbs"][db]:
            m, b = cell["dbs"][db][arm]
            ms.append(m if m.size else np.empty((0, len(b))))
            bs.append(b)
    if not bs:
        raise KeyError(arm)
    widths = [x.shape[0] for x in ms]
    K = widths[0] if widths else 0
    if any(w != K for w in widths):
        K = min(widths)
        ms = [x[:K] for x in ms]
    return (np.hstack(ms) if K else np.empty((0, 0))), np.hstack(bs)


def load_cells(jsonl: Path, gen_dir: Path, judge: str, arms: tuple[str, ...]) -> list[dict]:
    """Assemble per-(builder, seed) cells from a collector JSONL plus the generation logs."""
    df = pd.read_json(jsonl, lines=True)
    membership: dict[tuple, list[str]] = {}
    for f in sorted(gen_dir.glob("[ABCDE]_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("arm") not in arms:
            continue
        membership[(d["builder"], d["seed"], d["arm"])] = [
            r["harness"] for r in d["results"] if r["admitted"]]

    cells = []
    for (builder, seed) in sorted({(b, s) for b, s, _ in membership}):
        cell = {"builder": builder, "seed": seed, "dbs": {}}
        for db, sub in df.groupby("db_id"):
            for arm in arms:
                names = membership.get((builder, seed, arm))
                if names is None:
                    continue
                try:
                    cell["dbs"].setdefault(db, {})[arm] = _mat(sub, names, judge)
                except ValueError:
                    pass
        if cell["dbs"]:
            cells.append(cell)
    return cells


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--gen-dir", default="artifacts/phase2/gen")
    ap.add_argument("--judge", default="official_correct")
    ap.add_argument("--arm-a", default="A")
    ap.add_argument("--arm-b", default="D")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--out")
    a = ap.parse_args()

    cells = load_cells(ROOT / a.jsonl, ROOT / a.gen_dir, a.judge, (a.arm_a, a.arm_b))
    print(f"[metrics] {len(cells)} builder x seed cells")
    for c in cells:
        for arm in (a.arm_a, a.arm_b):
            m, bare = _merge(c, arm, sorted(c["dbs"]))
            pm = population_metrics(m, bare)
            print(f"  {c['builder']}/s{c['seed']}/{arm}: K={pm['K']} "
                  f"headroom={pm['headroom']:.4f} repair={pm['union_repair']:.3f} "
                  f"harm={pm['union_harm']:.3f} disagree={pm['pairwise_disagreement']:.3f}")
    res = hierarchical_paired_bootstrap(cells, a.arm_a, a.arm_b, a.judge, a.n_boot)
    print(json.dumps(res, indent=2))
    if a.out:
        p = ROOT / a.out
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, indent=2), encoding="utf-8")
