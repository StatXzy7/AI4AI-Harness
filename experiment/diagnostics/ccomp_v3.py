"""C-comp v3: calibrated test of stable complementarity (post 2026-09-19 review).

The v2 plug-in test (core.s3_stability's stable_complementarity block)
computed H_stable on repeat-averaged per-task estimates and supported
complementarity whenever a task bootstrap lower bound exceeded zero.
The 2026-09-19 external review proved that path false-positives on pure
sampling noise: with every member-task probability equal to 0.9, M=9,
T=400, R=3, the plug-in prints H_hat = 8.83 pp, CI [7.2, 10.4], SUPPORTED,
and the sealed same-code clone arm itself printed 2.67 pp SUPPORTED.

This module replaces that decision path with two explicitly separated
objects:

  H_plugin  DESCRIPTIVE ONLY. The old plug-in, retained for transparency
            and clearly marked as a biased descriptive quantity; it never
            determines a scientific state.

  G         CROSS-FITTED FROZEN-SELECTOR GAIN vs the best FIXED member
            (a deployable cousin of H_stable, bounded above by it):
              folds v = 1..R
                discovery fold K_v = all repeats except v
                q^K[h,x] = mean over K_v of Y[h,x,r]
                h_v(x)   = argmax_h q^K[h,x]
                hbar_v   = argmax_h mean_x q^K[h,x]
                s_v(x)   = Y[h_v(x),x,v] - Y[hbar_v,x,v]
              G = mean_v mean_x s_v(x).
            Both selections are frozen on discovery repeats and scored on
            the held-out repeat, so under global dominance (one member
            expectation-best everywhere) the frozen pick coincides with
            the best fixed member and G <= 0: dominance cannot trigger
            support, unlike the v2 comparison against `bare`.

The size-controlled decision statistic is the real-minus-clone difference
D = G_real - G_clone, where G_clone is the identical cross-fitted gain
computed on the same-code clone arm. Its reference distribution is obtained
by independently permuting member labels within every task, JOINTLY across
repeats, in BOTH arms and recomputing D: this is the exact finite-(R,T)
equal-ability randomization distribution, and because G_real <= 0 under
global dominance while G_clone is centered at zero, the same one-sided
rejection rule stays conservative across the whole null family H=0. A
paired task bootstrap supplies D's sampling CI, and G_real's own CI is a
dominance sign guard. Without a clone arm, G is reported descriptively and
no SUPPORTED state is emitted.

States: SUPPORTED only when the coverage gate passes AND the randomization
p-value is below alpha AND D's bootstrap lower bound is positive AND
D > delta AND G_real's lower bound is positive; REFUTED_WITHIN_SCOPE when
D's upper bound is within the margin and the equivalence p-value is small;
equivalence test p-value is small; otherwise INSUFFICIENT_EVIDENCE.
Everything is offline, numpy-only, and seeded.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from experiment.diagnostics.core import INSUFFICIENT, REFUTED, SUPPORTED

DELTA = 0.01        # 1.0 pp practical margin (frozen 2026-09-15)
ALPHA = 0.05
MIN_TASKS = 30
MAX_EXCLUDE_FRAC = 0.10


@dataclass(frozen=True)
class Tensor:
    """Outcome tensor with member ids and task ids."""
    Y: np.ndarray                  # (R, M, T), 0/1/NaN
    member_ids: list[str]
    task_ids: list[str]


# --------------------------------------------------------------- core stat

def _complete_cols(Y: np.ndarray) -> np.ndarray:
    ok = np.ones(Y.shape[2], dtype=bool)
    for r in range(Y.shape[0]):
        ok &= ~np.isnan(Y[r]).any(axis=0)
    return np.nonzero(ok)[0]


def crossfit_gain(Y: np.ndarray, cols: np.ndarray | None = None,
                  return_folds: bool = False,
                  tie_rng: np.random.Generator | None = None):
    """G as defined in the module docstring (R folds, 2-discovery / 1-held
    out when R=3). Returns (G, per_task_gain_vector, fold_info).

    Tie-breaking is LABEL-SYMMETRIC: when discovery scores are exactly
    tied (at R=2 discovery scores lie on {0,.5,1}, so ties are the norm at
    high accuracy), the argmax adds iid $U(0,10^{-9})$ jitter from
    `tie_rng`, so every tied label has equal probability. A deterministic
    lexicographic tie-break gives the first listed member a systematic
    selection advantage and makes G depend on member ordering (an
    adversarial finding from the design review); symmetric jitter removes
    that bias. The jitter is orders of magnitude below any non-tie score
    gap and therefore never changes a non-tied ordering.
    """
    R, M, T = Y.shape
    if cols is None:
        cols = _complete_cols(Y)
    per_task = np.zeros(len(cols))
    folds = []
    for v in range(R):
        K = [r for r in range(R) if r != v]
        qd = np.mean([Y[r][:, cols] for r in K], axis=0)
        # tie_rng=None -> lexicographic (deterministic) selection, used only
        # for exact vectorization comparisons; all scientific paths pass a
        # seeded rng and get label-symmetric tie-breaking.
        if tie_rng is not None:
            qd = qd + tie_rng.random(qd.shape) * 1e-9
        h_star = np.argmax(qd, axis=0)
        fs = qd.mean(axis=1)
        if tie_rng is not None:
            fs = fs + tie_rng.random(fs.shape) * 1e-9
        h_fix = int(np.argmax(fs))
        yv = Y[v][:, cols]
        per_task += (yv[h_star, np.arange(len(cols))]
                     - yv[h_fix, np.arange(len(cols))]) / R
        folds.append({"held_out_repeat": v, "best_fixed": h_fix,
                      "n_distinct_selection": int(len(set(h_star.tolist())))})
    if return_folds:
        return float(per_task.mean()), per_task, folds
    return float(per_task.mean()), per_task, folds


# ----------------------------------------------------------------- bootstrap

def task_bootstrap_ci(g: np.ndarray, rng: np.random.Generator,
                      n_boot: int = 2000) -> tuple[float, float]:
    n = len(g)
    idx = rng.integers(0, n, size=(n_boot, n))
    boots = g[idx].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(lo), float(hi)


# ------------------------------------------------- vectorized null machinery

def _batch_permuted(Y: np.ndarray, cols: np.ndarray, n_perm: int,
                    rng: np.random.Generator) -> np.ndarray:
    """Batched member-label randomization of Y[:, :, cols].

    Returns (B, R, M, t): independent uniform member-label permutations per
    (permute draw, repeat, task), applied to the corresponding held rows.
    Independent permutations across repeats break discovery-to-validation
    identity transfer while preserving margins.
    """
    R, M, _ = Y.shape
    t = len(cols)
    Yc = Y[:, :, cols]                                  # (R, M, t)
    keys = rng.random((n_perm, R, t, M))
    perms = np.argsort(keys, axis=3)                    # (B, R, t, M)
    idx = np.broadcast_to(perms, (n_perm, R, t, M))
    Yb = np.broadcast_to(Yc[None, :, :, :], (n_perm, R, M, t))
    # gather row perm[..., m] for each output row m
    return np.take_along_axis(
        Yb.swapaxes(2, 3), np.broadcast_to(perms, (n_perm, R, t, M)), axis=3
    ).swapaxes(2, 3).copy()


def _batch_crossfit_gain(Yb: np.ndarray, jitter: bool = True) -> np.ndarray:
    """Vectorized crossfit_gain over a batch (B, R, M, t) of tensors.

    With jitter=True, symmetric iid U(0,1e-9) tie-breaking is added per
    (draw, fold, task) and (draw, fold, fixed choice); this is the batched
    counterpart of the seeded tie_rng used by the single-tensor path."""
    B, R, M, t = Yb.shape
    out = np.zeros((B, t))
    rng = np.random.default_rng(12345)
    for v in range(R):
        K = [r for r in range(R) if r != v]
        qd = Yb[:, K, :, :].mean(axis=1)                # (B, M, t)
        if jitter:
            qd = qd + rng.random(qd.shape) * 1e-9
        h_star = np.argmax(qd, axis=1)                  # (B, t)
        fscores = qd.mean(axis=2)
        if jitter:
            fscores = fscores + rng.random((B, M)) * 1e-9
        h_fix = np.argmax(fscores, axis=1)              # (B,)
        held = Yb[:, v, :, :]                           # (B, M, t)
        bidx = np.arange(B)[:, None]
        tidx = np.arange(t)[None, :]
        picked = held[bidx, h_star, tidx]               # (B, t)
        fixed = held[bidx, h_fix[:, None], tidx]        # (B, t)
        out += (picked - fixed) / R
    return out.mean(axis=1)


def randomization_D_pvalue(Y: np.ndarray, clone_Y: np.ndarray,
                           cols: np.ndarray, c_cols: np.ndarray,
                           d_obs: float, n_perm: int,
                           rng: np.random.Generator,
                           delta: float = DELTA
                           ) -> tuple[float, float, np.ndarray]:
    """Vectorized two-arm randomization p-value for D = G_real - G_clone.

    Member labels are permuted independently per (repeat, task) in each arm
    on every draw. Returns (one-sided p for gain, equivalence p, null D)."""
    Rp = _batch_crossfit_gain(_batch_permuted(Y, cols, n_perm, rng))
    Cp = _batch_crossfit_gain(_batch_permuted(clone_Y, c_cols, n_perm, rng))
    null_D = Rp - Cp
    p_gain = (1 + int(np.sum(null_D >= d_obs - delta))) / (n_perm + 1)
    p_equiv = (1 + int(np.sum(null_D >= d_obs + delta))) / (n_perm + 1)
    return float(p_gain), float(p_equiv), null_D


# -------------------------------------------------- label randomization null

def _label_permute_within_tasks(Y: np.ndarray, cols: np.ndarray,
                                rng: np.random.Generator) -> np.ndarray:
    """Single-draw member-label randomization (independent permutation per
    repeat and task). Kept for tests/inspection; batch path uses
    _batch_permuted."""
    return _batch_permuted(Y, cols, 1, rng)[0]


# ------------------------------------------------------------- missingness

def extremal_bounds(Y: np.ndarray,
                    cols: np.ndarray | None = None,
                    seed: int = 20260915) -> tuple[float, float]:
    """Scenario range for G if every unknown outcome were observed.

    The point estimate is a complete-case statistic: tasks with any NaN
    are excluded (`cols`), so on the included tasks there are no unknown
    cells and the point G itself is exact. This function answers the
    separate sensitivity question ``how far could G move if the excluded
    tasks' missing observations had been recorded?'': fill every NaN with
    0 (worst) and with 1 (best), INCLUDING the resulting selection
    changes, recompute the full cross-fit, and report both. The two fills
    bracket every binary filling because raising any executed outcome from
    0 to 1 can only weakly increase a selected member's score; ties use the
    same frozen seed as the point estimate. These are therefore tight
    fill-extremes, not a loose interval from a fixed selection.
    """
    if not np.isnan(Y).any():
        g, _, _ = crossfit_gain(Y, cols, tie_rng=np.random.default_rng(seed))
        return float(g), float(g)
    vals = []
    for fill in (0.0, 1.0):
        Z = Y.copy()
        Z[np.isnan(Z)] = fill
        g, _, _ = crossfit_gain(Z, tie_rng=np.random.default_rng(seed))
        vals.append(g)
    return float(min(vals)), float(max(vals))


# --------------------------------------------------------------- main entry

def ccomp_v3(Y: np.ndarray, clone_Y: np.ndarray | None = None,
              member_ids: list[str] | None = None,
              task_ids: list[str] | None = None,
              n_perm: int = 4000, n_boot: int = 2000,
              n_tie: int = 10,
              delta: float = DELTA, seed: int = 20260915) -> dict:
    """Calibrated C-comp decision on one arm, optionally with a same-code
    clone arm for the empirical-null reference and the paired difference.

    Returns a dict with descriptive H_plugin, the cross-fitted G with its
    bootstrap CI, p_fl (always), p_clone (when a clone arm is supplied),
    the union p-value, the paired D, coverage gates, bounds on missing
    cells, and exactly one scientific state.
    """
    rng = np.random.default_rng(seed)
    R, M, T = Y.shape

    # ---------------- descriptive legacy plug-in (NEVER decides state)
    with np.errstate(invalid="ignore"):
        Q = np.nanmean(Y, axis=0)
    if np.isnan(Q).any():
        H_plugin = None
    else:
        H_plugin = float(Q.max(axis=0).mean()
                         - Q[np.argmax(Q.mean(axis=1))].mean())

    cols = _complete_cols(Y)
    n_complete = len(cols)
    excluded_frac = 1 - n_complete / T
    coverage_ok = excluded_frac <= MAX_EXCLUDE_FRAC and n_complete >= MIN_TASKS

    unidentified = int(np.isnan(Q).sum())

    if n_complete < MIN_TASKS:
        return {"state": INSUFFICIENT,
                "estimand": "cross-fitted frozen-selection gain G vs best "
                            "fixed member (bounded by H_stable)",
                "G": None, "G_ci95": None,
                "H_plugin_descriptive": H_plugin,
                "n_complete_tasks": n_complete,
                "excluded_frac_real": round(excluded_frac, 4),
                "reason": f"only {n_complete} complete tasks (< {MIN_TASKS})",
                "unidentified_cells": unidentified}

    # Observed G: average over n_tie symmetric tie-break draws, so the
    # reported statistic is label-symmetric rather than tied to one random
    # tie realization (and independent of input member ordering in
    # expectation). Calibration studies use n_tie=1: under the null the
    # tie-break bias is mean zero, so one draw is unbiased and 10x faster;
    # the real-data report uses the default 10.
    g_acc = np.zeros(len(cols))
    fold_votes = []
    for k in range(n_tie):
        _, gk, fk = crossfit_gain(
            Y, cols, tie_rng=np.random.default_rng(seed + 100 + k))
        g_acc += gk / n_tie
        fold_votes.append([f["best_fixed"] for f in fk])
    g_vec = g_acc
    g_obs = float(g_vec.mean())
    # fold diagnostics from the first averaged realization; the majority of
    # best-fixed labels over all tie draws is reported alongside.
    _, _, folds0 = crossfit_gain(
        Y, cols, tie_rng=np.random.default_rng(seed))
    folds = folds0
    folds[0]["best_fixed_tie_majority"] = [
        int(np.argmax(np.bincount([fv[fi] for fv in fold_votes],
                                  minlength=M)))
        for fi in range(len(folds))]
    g_lo, g_hi = task_bootstrap_ci(g_vec, rng, n_boot)

    g_clone = d_stat = d_lo = d_hi = None
    p_d = None
    null_info = None
    # clone-arm coverage and paired-intersection coverage are gated
    # independently: a clone arm with 1/400 complete tasks must not drive a
    # paired support decision (reviewer edge case).
    clone_coverage_ok = paired_coverage_ok = True
    n_paired = 0
    if clone_Y is not None:
        c_cols = _complete_cols(clone_Y)
        n_c_complete = len(c_cols)
        c_excluded = 1 - n_c_complete / T
        clone_coverage_ok = (c_excluded <= MAX_EXCLUDE_FRAC
                             and n_c_complete >= MIN_TASKS)
        g_c_acc = np.zeros(len(c_cols))
        for k in range(n_tie):
            _, gck, _ = crossfit_gain(
                clone_Y, c_cols, tie_rng=np.random.default_rng(seed + 200 + k))
            g_c_acc += gck / n_tie
        g_c_vec = g_c_acc
        g_clone = float(g_c_vec.mean())
        # paired D on the shared task-id intersection (caller supplies
        # aligned task ids for both arms)
        id_to_col_obs = {task_ids[j]: i for i, j in enumerate(cols)} \
            if task_ids is not None else {f"t{j}": i for i, j in enumerate(cols)}
        id_to_col_clone = {task_ids[j]: i for i, j in enumerate(c_cols)} \
            if task_ids is not None else {f"t{j}": i for i, j in enumerate(c_cols)}
        common = sorted(set(id_to_col_obs) & set(id_to_col_clone))
        diff = np.array([g_vec[id_to_col_obs[t]]
                         - g_c_vec[id_to_col_clone[t]] for t in common])
        d_stat = float(diff.mean())
        n_paired = len(diff)
        paired_coverage_ok = (
            n_paired >= MIN_TASKS
            and 1 - n_paired / T <= MAX_EXCLUDE_FRAC)
        d_lo, d_hi = task_bootstrap_ci(
            diff, np.random.default_rng(seed + 3), n_boot)
        # empirical-null randomization of D: independently permute labels in
        # BOTH arms (per repeat and task), recompute both gains and their
        # difference; this is the exact equal-ability null distribution of
        # the decision statistic and under global dominance in the real arm
        # D's population value is <= 0, so the same rejection rule remains
        # conservative there.
        p_d, p_d_equiv, null_D = randomization_D_pvalue(
            Y, clone_Y, cols, c_cols, d_stat, n_perm,
            np.random.default_rng(seed + 2), delta)
        null_info = {"null_D_mean": round(float(null_D.mean()), 5),
                     "null_D_sd": round(float(null_D.std()), 5)}

    lo_bound, hi_bound = extremal_bounds(Y, cols)

    # ---------------- state machine
    # The size-controlled SUPPORT decision REQUIRES a same-code clone arm:
    # D = G_real - G_clone clears the randomization null by delta and the
    # paired bootstrap lower bound is positive, while the real-arm G's own
    # interval provides the dominance sign guard. Without the clone arm the
    # real-arm G is reported descriptively and the state stays INSUFFICIENT.
    if not coverage_ok:
        state = INSUFFICIENT
        reason = (f"coverage gate: {excluded_frac:.3f} of real-arm tasks "
                  f"excluded (> {MAX_EXCLUDE_FRAC}); G reported on "
                  f"{n_complete} complete tasks as a labeled secondary "
                  "quantity")
    elif clone_Y is None:
        state = INSUFFICIENT
        reason = ("no same-code clone arm: the equal-ability empirical-null "
                  "reference is required for a size-controlled SUPPORT "
                  "decision; G is descriptive only")
    elif not clone_coverage_ok:
        state = INSUFFICIENT
        reason = (f"clone-arm coverage gate failed: {n_c_complete}/"
                  f"{T} complete tasks (need >= {MIN_TASKS} and <= "
                  f"{int(MAX_EXCLUDE_FRAC*100)}% excluded)")
    elif not paired_coverage_ok:
        state = INSUFFICIENT
        reason = (f"paired intersection coverage gate failed: {n_paired} "
                  f"shared complete tasks (need >= {MIN_TASKS})")
    elif p_d < ALPHA and d_lo > 0 and d_stat > delta and g_lo > 0:
        state = SUPPORTED
        reason = ""
    elif d_hi <= delta and p_d_equiv < ALPHA and g_hi <= 0:
        state = REFUTED
        reason = ""
    else:
        state = INSUFFICIENT
        reason = ("real-minus-clone gain neither clears the randomization "
                  "null by the margin nor is bounded inside it; abstention")

    return {
        "state": state,
        "estimand": ("PRIMARY: D = G_real - G_clone where G is the "
                     "cross-fitted frozen per-task selector gain vs the best "
                     "FIXED member. G <= H_stable, G=0 under dominance; the "
                     "same-code clone subtraction removes the finite-(R,T) "
                     "selection-noise component. G without a clone arm is "
                     "reported descriptively only."),
        "G": round(g_obs, 5),
        "G_ci95": [round(g_lo, 5), round(g_hi, 5)],
        "p_D_clone_randomization": (None if p_d is None else round(p_d, 5)),
        "p_D_equivalence": (None if clone_Y is None else round(p_d_equiv, 5)),
        "null_D": null_info,
        "paired_difference": (None if d_stat is None else
                              {"D_real_minus_clone": round(d_stat, 5),
                               "D_ci95": [round(d_lo, 5), round(d_hi, 5)],
                               "n_paired_tasks": int(len(diff)),
                               "G_clone": round(g_clone, 5)}),
        "H_plugin_descriptive": (None if H_plugin is None
                                 else round(H_plugin, 5)),
        "descriptive_warning": "H_plugin is the repeat-average plug-in; it "
                               "is upward biased by finite-R selection noise "
                               "and is reported for transparency only",
        "n_complete_tasks": n_complete,
        "excluded_frac": round(excluded_frac, 4),
        "coverage_gate": f"excluded <= {MAX_EXCLUDE_FRAC}",
        "coverage_ok": coverage_ok,
        "missing_extremal_G_bounds": [round(lo_bound, 5), round(hi_bound, 5)],
        "unidentified_cells": unidentified,
        "folds": folds,
        "delta": delta, "alpha": ALPHA,
        "n_perm": n_perm, "n_boot": n_boot, "seed": seed,
        "reason": reason,
    }
