"""Candidate statistics for the stable-complementarity calibration study.

All functions are offline, numpy-only, deterministic given a seed.  The
outcome tensor convention throughout is Y with shape (R, M, T) containing
0/1 with NaN for missing cells.

Three families are provided so the simulation study can compare them on
identical known-truth draws:

  plugin_h_stable            LEGACY descriptive plug-in (the 2026-09-19
                             review showed it prints false SUPPORT under
                             iid equal-ability noise); kept ONLY as a
                             labeled descriptive quantity and as the
                             demonstrated-broken comparator.

  frozen_selection_gain      Cross-fitted discovery/validation test of a
                             frozen per-task selector against the best
                             FIXED member (both frozen on discovery data):
                               G = mean_x [Y_v(h*(x), x) - Y_v(h_fix, x)]
                             which is EXACTLY ZERO in expectation under
                             global dominance (a dominant member is always
                             the frozen pick) and has mean ~ selection noise
                             under equal-ability iid.

  clone_calibrated_gain      Difference of real-arm G and same-code clone
                             arm G on matched tasks, with a paired task
                             bootstrap CI and an empirical-null permutation
                             p-value over clone-slot identity permutations.
                             This subtracts the finite-(R,T) selection-noise
                             component that remains after cross-fitting.

Decision states mirror the diagnostic vocabulary:
SUPPORTED / REFUTED_WITHIN_SCOPE / INSUFFICIENT_EVIDENCE.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SUPPORTED = "SUPPORTED"
REFUTED = "REFUTED_WITHIN_SCOPE"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

DELTA_EQ = 0.01     # 1.0 pp practical margin (frozen 2026-09-15)
ALPHA = 0.05


@dataclass(frozen=True)
class StatResult:
    state: str
    estimate: float
    ci95: tuple[float, float] | None
    n_tasks: int
    detail: dict


# ------------------------------------------------------------ LEGACY plug-in

def plugin_h_stable(Y: np.ndarray, n_boot: int = 1000,
                    seed: int = 20260915) -> StatResult:
    """Legacy H plug-in on repeat-averaged q. DESCRIPTIVE ONLY.

    Retained to quantify the bias the 2026-09-19 review identified:
    maximizing noisy per-task estimates is upward biased and the task
    bootstrap does not remove selection noise already inside the max.
    """
    R, M, T = Y.shape
    with np.errstate(invalid="ignore"):
        Q = np.nanmean(Y, axis=0)
    if np.isnan(Q).any():
        return StatResult(INSUFFICIENT, float("nan"), None, 0,
                          {"reason": "unidentified (member,task) expectation"})
    per_task_max = Q.max(axis=0)
    best = int(np.argmax(Q.mean(axis=1)))
    H = float(per_task_max.mean() - Q[best].mean())
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.choice(T, T, replace=True)
        boots[b] = per_task_max[idx].mean() - Q[best, idx].mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    state = SUPPORTED if lo > 0 else (REFUTED if hi <= 1e-12 else INSUFFICIENT)
    return StatResult(state, H, (float(lo), float(hi)), T,
                      {"estimand": "legacy plug-in H (descriptive only)",
                       "best_fixed": int(best)})


# ----------------------------------------------- frozen-selection gain (G)

def _complete_cols(Y: np.ndarray, reps: list[int]) -> np.ndarray:
    """Columns observed in every member/repeat of the given repeats."""
    R, M, T = Y.shape
    ok = np.ones(T, dtype=bool)
    for r in reps:
        ok &= ~np.isnan(Y[r]).any(axis=0)
    return np.nonzero(ok)[0]


def frozen_gain_one_split(Y: np.ndarray, discovery_rep: int,
                          validation_reps: list[int], cols: np.ndarray,
                          rng: np.random.Generator,
                          n_boot: int = 1000) -> dict:
    """One discovery/validation split.

    Both the per-task mapping h*(x) and the single best fixed member h_fix
    are frozen on the discovery repeat; scoring uses only validation
    repeats. Per-task gain vector (paired with fixed) is bootstrapped over
    tasks for the conditional CI.
    """
    scores = Y[discovery_rep][:, cols]
    h_star = np.argmax(scores, axis=0)            # ties -> smallest id
    h_fix = int(np.argmax(scores.mean(axis=1)))
    v = np.mean([Y[r][:, cols] for r in validation_reps], axis=0)  # (M,t)
    g = v[h_star, np.arange(len(cols))] - v[h_fix, np.arange(len(cols))]
    n = len(cols)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        boots[b] = g[idx].mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"G": float(g.mean()), "ci": (float(lo), float(hi)),
            "g": g, "h_fix": h_fix,
            "n_distinct_selection": int(len(set(h_star.tolist())))}


def frozen_selection_gain(Y: np.ndarray, n_boot: int = 1000,
                          seed: int = 20260915,
                          delta: float = DELTA_EQ) -> StatResult:
    """Frozen discovery(r1) -> validation(r2,r3) selector gain vs best fixed.

    SUPPORTED: CI lower bound > delta (gain beyond practical margin).
    REFUTED:   CI upper bound <= 0.
    INSUFFICIENT otherwise.
    """
    reps = list(range(Y.shape[0]))
    if len(reps) < 2:
        return StatResult(INSUFFICIENT, float("nan"), None, 0,
                          {"reason": "need >= 2 repeats"})
    cols = _complete_cols(Y, reps)
    if len(cols) < 30:
        return StatResult(INSUFFICIENT, float("nan"), None, len(cols),
                          {"reason": "fewer than 30 complete tasks"})
    rng = np.random.default_rng(seed)
    split = frozen_gain_one_split(Y, reps[0], reps[1:], cols, rng, n_boot)
    lo, hi = split["ci"]
    state = SUPPORTED if lo > delta else (REFUTED if hi <= 0 else INSUFFICIENT)
    return StatResult(state, split["G"], split["ci"], len(cols),
                      {"h_fix": split["h_fix"],
                       "n_distinct_selection": split["n_distinct_selection"],
                       "estimand": "frozen selection gain vs best fixed "
                                   "(discovery r1, validation r2-r3)"})


def crossfit_selection_gain(Y: np.ndarray, n_boot: int = 1000,
                            seed: int = 20260915,
                            delta: float = DELTA_EQ) -> StatResult:
    """R-fold cross-fit over repeats plus task averaging.

    For each discovery repeat d, freeze h*_d(x) and h_fix_d on d and score
    on the other repeats; per-task gains are averaged over the R discovery
    folds (each task therefore contributes R conditionally-valid validation
    comparisons). Complete-case across ALL folds. Bootstrap over tasks of
    the averaged per-task gain.
    """
    R, M, T = Y.shape
    reps = list(range(R))
    cols = _complete_cols(Y, reps)
    if len(cols) < 30:
        return StatResult(INSUFFICIENT, float("nan"), None, len(cols),
                          {"reason": "fewer than 30 complete tasks"})
    fold_g = np.zeros(len(cols))
    detail_folds = []
    for d in reps:
        v_reps = [r for r in reps if r != d]
        scores = Y[d][:, cols]
        h_star = np.argmax(scores, axis=0)
        h_fix = int(np.argmax(scores.mean(axis=1)))
        v = np.mean([Y[r][:, cols] for r in v_reps], axis=0)
        fold_g += (v[h_star, np.arange(len(cols))]
                   - v[h_fix, np.arange(len(cols))]) / R
        detail_folds.append(h_fix)
    rng = np.random.default_rng(seed)
    n = len(cols)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        boots[b] = fold_g[idx].mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    state = SUPPORTED if lo > delta else (REFUTED if hi <= 0 else INSUFFICIENT)
    return StatResult(state, float(fold_g.mean()), (float(lo), float(hi)),
                      n, {"fold_best_fixed": detail_folds,
                          "estimand": "repeat-cross-fitted selection gain "
                                      "vs best fixed"})


# -------------------------------------------------- clone-calibrated gain

def _gain_vector(Y: np.ndarray, discovery_rep: int,
                 validation_reps: list[int], cols: np.ndarray) -> np.ndarray:
    scores = Y[discovery_rep][:, cols]
    h_star = np.argmax(scores, axis=0)
    h_fix = int(np.argmax(scores.mean(axis=1)))
    v = np.mean([Y[r][:, cols] for r in validation_reps], axis=0)
    return v[h_star, np.arange(len(cols))] - v[h_fix, np.arange(len(cols))]


def _permuted_gain(Y: np.ndarray, cols: np.ndarray, rng: np.random.Generator,
                   discovery_rep: int, validation_reps: list[int]) -> float:
    """Apply an independent member-identity permutation per task, jointly
    across repeats (same-code exchangeability null), and return G."""
    M = Y.shape[1]
    Yp = Y[:, :, cols]
    perms = np.stack([rng.permutation(M) for _ in cols], axis=1)  # (M,t)
    Yp = np.take_along_axis(Yp, np.broadcast_to(perms[None, :, :], Yp.shape),
                            axis=1)
    scores = Yp[discovery_rep]
    h_star = np.argmax(scores, axis=0)
    h_fix = int(np.argmax(scores.mean(axis=1)))
    v = np.mean([Yp[r] for r in validation_reps], axis=0)
    g = v[h_star, np.arange(len(cols))] - v[h_fix, np.arange(len(cols))]
    return float(g.mean())


def clone_calibrated_gain(real_Y: np.ndarray, clone_Y: np.ndarray,
                          n_boot: int = 2000, n_perm: int = 4000,
                          seed: int = 20260915,
                          delta: float = DELTA_EQ) -> StatResult:
    """Real-arm frozen-G minus clone-arm frozen-G on identical task columns.

    Both arms must share the task order (simulations draw them jointly).
    Uncertainty:
      * paired task bootstrap CI of D = mean(g_real - g_clone);
      * empirical-null one-sided p = P_perm(G_clone >= G_real - delta)
        under joint cross-repeat member-identity permutations within tasks.
    SUPPORTED requires the coverage gate, p < alpha, and CI lower > 0;
    an equivalence-style REFUTED requires CI upper <= delta.
    """
    reps = list(range(real_Y.shape[0]))
    cols_r = _complete_cols(real_Y, reps)
    cols_c = _complete_cols(clone_Y, reps)
    cols = np.intersect1d(cols_r, cols_c)
    T = real_Y.shape[2]
    excluded = 1 - len(cols) / T
    if len(cols) < 30:
        return StatResult(INSUFFICIENT, float("nan"), None, len(cols),
                          {"reason": "fewer than 30 paired complete tasks"})
    g_r = _gain_vector(real_Y, reps[0], reps[1:], cols)
    g_c = _gain_vector(clone_Y, reps[0], reps[1:], cols)
    diff = g_r - g_c
    D = float(diff.mean())
    rng = np.random.default_rng(seed)
    n = len(cols)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        boots[b] = diff[idx].mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    G_real = float(g_r.mean())
    null = np.empty(n_perm)
    for b in range(n_perm):
        null[b] = _permuted_gain(clone_Y, cols, rng, reps[0], reps[1:])
    p = (1 + int(np.sum(null >= G_real - delta))) / (n_perm + 1)
    coverage_ok = excluded <= 0.10
    if not coverage_ok:
        state = INSUFFICIENT
    elif p < ALPHA and lo > 0 and G_real > delta:
        state = SUPPORTED
    elif hi <= delta:
        state = REFUTED
    else:
        state = INSUFFICIENT
    return StatResult(state, D, (float(lo), float(hi)), n,
                      {"G_real": G_real, "G_clone": float(g_c.mean()),
                       "p_empnull": float(p),
                       "excluded_frac": float(excluded),
                       "estimand": "clone-calibrated frozen selection gain"})


STATISTICS = {
    "plugin_descriptive": plugin_h_stable,
    "frozen_gain": frozen_selection_gain,
    "crossfit_gain": crossfit_selection_gain,
}
