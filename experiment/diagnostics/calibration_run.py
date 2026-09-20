"""Run the known-truth calibration grid for the stable-complementarity
statistics. Offline, numpy-only; writes JSON + CSV.

For each DGP x (M, T, R) cell it draws n_reps independent datasets (each
with a matched same-code clone arm), runs every candidate statistic, and
records:

  * false-positive rate under a null family  (P(SUPPORTED))
  * power under an alternative                (P(SUPPORTED))
  * CI coverage of zero (nulls) and of the
    cross-fitted conditional target (alternatives)
  * abstain rate (P(INSUFFICIENT))
  * mean estimate

Usage:
  python -m experiment.diagnostics.calibration_run --smoke   # fast check
  python -m experiment.diagnostics.calibration_run           # frozen grid
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np

from experiment.diagnostics import calibration_sim as sim
from experiment.diagnostics.ccomp_v3 import ccomp_v3
from experiment.diagnostics.calibration_stats import (
    INSUFFICIENT, SUPPORTED, crossfit_selection_gain, frozen_selection_gain,
    plugin_h_stable)

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = ROOT / "artifacts" / "diagnostics" / "calibration_v3"

NULL_FAMILIES = {"equal_ability", "dominance"}

# Focused paper grid: the actual acquisition design (9,400,3) with high
# replication, plus single-axis sweeps for asymptotics and missingness.
# Each tuple: (M, T, R, missing_name, frac, mech, n_reps)
def paper_cells(n_reps_core: int = 300, n_reps_sweep: int = 150):
    cells = [(9, 400, 3, "complete", 0.0, "mcar", n_reps_core)]
    for R in (5, 10, 20):
        cells.append((9, 400, R, "complete", 0.0, "mcar", n_reps_sweep))
    for M in (3, 20):
        cells.append((M, 400, 3, "complete", 0.0, "mcar", n_reps_sweep))
    for T in (100, 1000):
        cells.append((9, T, 3, "complete", 0.0, "mcar", n_reps_sweep))
    cells.append((9, 400, 3, "mcar5", 0.05, "mcar", n_reps_sweep))
    cells.append((9, 400, 3, "mnar_hard3", 0.03, "mnar_hard", n_reps_sweep))
    return cells


SCENARIOS = [
    ("equal_const", "equal_ability"),
    ("equal_hetero", "equal_ability"),
    ("dominance_clean", "dominance"),
    ("dominance_reviewer", "dominance"),
    ("dominance_hetero", "dominance"),
    ("cross_mid", "crossover"),
    ("cross_strong", "crossover"),
    ("cross_vstrong", "crossover"),
    ("two_specialist", "crossover"),
    ("cross_weak", "crossover"),
]
MISSING = [("complete", 0.0, "mcar"), ("mcar5", 0.05, "mcar"),
           ("mnar_hard3", 0.03, "mnar_hard")]


def _v3_fast(Y, clone, n_perm=300, n_boot=300, delta=0.01):
    """Vectorized v3 decision for Monte Carlo calibration, IDENTICAL in
    decision logic to ccomp_v3 (n_tie=1) — same task alignment, the same
    G_real sign guard uses the G bootstrap lower bound (not the D bound),
    the same coverage gate, and the same null/equivalence p-values. It
    differs only in vectorizing the permutation draw and reports the
    actually used complete-task count rather than a hard-coded value."""
    from experiment.diagnostics.ccomp_v3 import (
        _batch_crossfit_gain, _batch_permuted, _complete_cols, crossfit_gain,
        task_bootstrap_ci)
    rng = np.random.default_rng(20260927)
    R, M, T = Y.shape
    cols = _complete_cols(Y)
    c_cols = _complete_cols(clone)
    n_complete = len(cols)
    excluded = 1 - n_complete / T
    g_obs, g_vec, _ = crossfit_gain(Y, cols, tie_rng=np.random.default_rng(3))
    _, g_c, _ = crossfit_gain(clone, c_cols, tie_rng=np.random.default_rng(4))
    g_lo, g_hi = task_bootstrap_ci(
        g_vec, np.random.default_rng(5), n_boot)
    # paired D on the SAME task ids (columns already index identical tasks
    # because both tensors are drawn on the same ordered task list)
    common = np.intersect1d(cols, c_cols)
    pos_r = {j: i for i, j in enumerate(cols)}
    pos_c = {j: i for i, j in enumerate(c_cols)}
    diff = np.array([g_vec[pos_r[t]] - g_c[pos_c[t]] for t in common])
    D = float(diff.mean())
    d_lo, d_hi = task_bootstrap_ci(
        diff, np.random.default_rng(6), n_boot)
    Rp = _batch_crossfit_gain(_batch_permuted(Y, cols, n_perm, rng))
    Cp = _batch_crossfit_gain(_batch_permuted(clone, c_cols, n_perm, rng))
    null_D = Rp - Cp
    p = (1 + int(np.sum(null_D >= D - delta))) / (n_perm + 1)
    coverage_ok = excluded <= 0.10 and n_complete >= 30
    if not coverage_ok:
        state = INSUFFICIENT
    elif p < 0.05 and d_lo > 0 and D > delta and g_lo > 0:
        state = SUPPORTED
    else:
        state = INSUFFICIENT
    return state, D, g_obs, n_complete, g_lo, d_lo, d_hi


def _run_stat(name, fn, Y, clone):
    t0 = time.time()
    out = {}
    if fn is not None:
        try:
            res = fn(Y)
            out = dict(state=res.state, est=res.estimate,
                       lo=res.ci95[0] if res.ci95 else None,
                       hi=res.ci95[1] if res.ci95 else None,
                       n=res.n_tasks, ok=True, ms=round(1000 * (time.time() - t0)))
        except Exception as exc:  # a crash is a calibration failure, not a skip
            out = dict(state="ERROR", est=None, lo=None, hi=None, n=0,
                       ok=False, error=repr(exc),
                       ms=round(1000 * (time.time() - t0)))
    if name == "clone_calibrated_v3":
        try:
            state, D, G_real, n_used, g_lo, d_lo, d_hi = _v3_fast(Y, clone)
            out = dict(state=state, est=D, lo=d_lo, hi=d_hi, n=n_used,
                       ok=True, G_real=G_real,
                       ms=round(1000 * (time.time() - t0)))
        except Exception as exc:
            out = dict(state="ERROR", est=None, lo=None, hi=None, n=0,
                       ok=False, error=repr(exc),
                       ms=round(1000 * (time.time() - t0)))
    return out


def run_cell(scenario: str, family: str, M: int, T: int, R: int,
             miss_name: str, miss_frac: float, miss_mech: str,
             n_reps: int, n_workers: int = 8) -> dict:
    spec = sim.REGISTRY[scenario]
    jobs = [(scenario, spec["kwargs"], M, T, R, miss_frac, miss_mech, b,
             hash_grid(scenario, M, T, R, miss_name)) for b in range(n_reps)]
    if n_workers and n_workers > 1:
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        with ctx.Pool(min(n_workers, n_reps), maxtasksperchild=20) as pool:
            records = pool.map(_one_dataset, jobs, chunksize=4)
    else:
        records = [_one_dataset(j) for j in jobs]
    return summarize(scenario, family, records)


def _one_dataset(job):
    scenario, kwargs, M, T, R, miss_frac, miss_mech, b, grid_seed = job
    seed = 20260915 + b * 7919 + grid_seed
    d = sim.REGISTRY[scenario]["fn"](seed=seed, M=M, T=T, R=R, **kwargs)
    Y = d.Y
    clone = sim.draw_clone_arm(d.Q, d.task_types, R, seed + 1)
    if miss_frac > 0:
        Y = sim.apply_missingness(Y, seed + 2, miss_frac, miss_mech, d.Q)
        clone = sim.apply_missingness(clone, seed + 3, miss_frac, "mcar")
    row = {"rep": b, "H_true": d.H_true}
    for name, fn in [("plugin_descriptive", plugin_h_stable),
                     ("frozen_gain", frozen_selection_gain),
                     ("crossfit_gain",
                      lambda z: crossfit_selection_gain(z, n_boot=500)),
                     ("clone_calibrated_v3", None)]:
        row[name] = _run_stat(name, fn, Y, clone)
    return row


def hash_grid(*parts) -> int:
    import hashlib
    return int(hashlib.sha256("|".join(map(str, parts)).encode())
               .hexdigest()[:8], 16)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(float((c - h) / d), 4), round(float((c + h) / d), 4))


def summarize(scenario: str, family: str, records: list[dict]) -> dict:
    stats = ["plugin_descriptive", "frozen_gain", "crossfit_gain",
             "clone_calibrated_v3"]
    out = {"scenario": scenario, "family": family,
           "n_reps": len(records), "statistics": {}}
    H_true = float(np.mean([r["H_true"] for r in records]))
    is_null = family in ("equal_ability", "dominance")
    n = len(records)
    for s in stats:
        rows = [r[s] for r in records]
        k_sup = sum(r["state"] == SUPPORTED for r in rows)
        k_ref = sum(r["state"] == "REFUTED" for r in rows)
        k_abst = sum(r["state"] == INSUFFICIENT for r in rows)
        k_err = sum(r["state"] == "ERROR" for r in rows)
        ests = [r["est"] for r in rows if r["est"] is not None
                and np.isfinite(r["est"])]
        if is_null or s == "plugin_descriptive":
            cover = np.mean([(r["lo"] is not None and r["lo"] <= H_true
                              <= r["hi"]) for r in rows])
        else:
            cover = None
        sup = k_sup / n
        out["statistics"][s] = {
            "support_rate": round(float(sup), 4),
            "support_wilson95": list(wilson(k_sup, n)),
            "refuted_rate": round(k_ref / n, 4),
            "abstain_rate": round(k_abst / n, 4),
            "error_rate": round(k_err / n, 4),
            "ci_coverage": (round(float(cover), 4) if cover is not None
                            else None),
            "mean_est": round(float(np.mean(ests)), 5) if ests else None,
            "is_false_positive": bool(is_null),
            "label": ("FPR" if is_null else "power"),
        }
    out["H_true_mean"] = H_true
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="one small fast configuration per scenario")
    ap.add_argument("--n-reps", type=int, default=400)
    args = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    if args.smoke:
        cells = [(9, 200, 3, "complete", 0.0, "mcar", 60)]
    else:
        cells = paper_cells(args.n_reps)
    results = []
    t_start = time.time()
    for scenario, family in SCENARIOS:
        for (M, T, R, miss_name, frac, mech, n_reps) in cells:
            r = run_cell(scenario, family, M, T, R, miss_name,
                         frac, mech, n_reps)
            r.update(M=M, T=T, R=R, missing=miss_name)
            results.append(r)
            print(f"{scenario:18s} M={M:2d} T={T:4d} R={R} "
                  f"{miss_name:10s} n={n_reps:3d} H={r['H_true_mean']:.3f} "
                  f"plugin={r['statistics']['plugin_descriptive']['support_rate']:.2f} "
                  f"frozen={r['statistics']['frozen_gain']['support_rate']:.2f} "
                  f"crossfit={r['statistics']['crossfit_gain']['support_rate']:.2f} "
                  f"v3={r['statistics']['clone_calibrated_v3']['support_rate']:.2f}",
                  flush=True)
    meta = {"elapsed_s": round(time.time() - t_start, 1),
            "cells": [list(c[:6]) + [c[6]] for c in cells],
            "scenarios": [s[0] for s in SCENARIOS]}
    (OUTDIR / "calibration_results.json").write_text(
        json.dumps({"meta": meta, "results": results}, indent=1),
        encoding="utf-8")
    # flat CSV
    with (OUTDIR / "calibration_results.csv").open("w", newline="",
                                                   encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "family", "M", "T", "R", "missing",
                    "statistic", "support_rate", "refuted_rate",
                    "abstain_rate", "ci_coverage", "mean_est", "H_true",
                    "label"])
        for r in results:
            family = ("null" if r["scenario"].startswith(("equal", "dominance"))
                      else "alternative")
            for s, v in r["statistics"].items():
                w.writerow([r["scenario"], family, r["M"], r["T"], r["R"],
                            r["missing"], s, v["support_rate"],
                            v["refuted_rate"], v["abstain_rate"],
                            v["ci_coverage"], v["mean_est"],
                            r["H_true_mean"], v["label"]])
    print(f"wrote {OUTDIR}")


if __name__ == "__main__":
    main()
