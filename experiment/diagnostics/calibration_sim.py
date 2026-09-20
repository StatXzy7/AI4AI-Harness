"""Known-truth simulation DGPs for statistical calibration of the
stable-complementarity diagnostics.

Every DGP returns a binary outcome tensor Y with shape (R, M, T) drawn
from a fully specified member x task probability matrix Q[M, T], plus a
ground-truth record:

  H_stable = mean_t max_m Q[m,t] - max_m mean_t Q[m,t]
  null_family in {"equal_ability", "dominance", "crossover"}
  notes     human-readable generating mechanism

A *clone-arm* draw for the same tasks uses the SAME task difficulties but
sets every slot's probability to the bare/reference profile (optionally
including slot-level fixed effects to stress exchangeability).

The DGPs deliberately cover every null and alternative the 2026-09-19
external review asked the calibration to distinguish:
  D1 equal-ability iid noise       (all q identical; H = 0)
  D2 task-difficulty heterogeneity (common a_t, members tied; H = 0)
  D3 global dominance              (one member best everywhere; H = 0)
  D3b global dominance vs weak bare (0.5/0.9 reviewer counterexample 2)
  D4 genuine crossover interaction (specialization across task types; H > 0)
  D5 correlated executions          (shared latent execution quality)
Missingness is applied separately by apply_missingness (MCAR or
difficulty-related MNAR) so each mechanism is reusable under both.

Everything here is offline, numpy-only, and deterministic given a seed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DGPResult:
    Y: np.ndarray                 # (R, M, T) Bernoulli draws
    Q: np.ndarray                 # (M, T) generating probabilities
    H_true: float                 # target parameter on the generating Q
    null_family: str
    task_types: np.ndarray        # (T,) integer latent type labels
    description: str


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


def _task_difficulties(rng: np.random.Generator, T: int,
                       lo: float = 0.55, hi: float = 0.99,
                       k_types: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Beta-ish task difficulties via sigmoid of a normal, spread over [lo,hi]."""
    z = rng.normal(0.0, 1.0, size=T)
    a = lo + (hi - lo) * _sigmoid(1.4 * z)
    types = rng.integers(0, k_types, size=T) if k_types > 1 else np.zeros(T, int)
    return a, types


def _draw(Q: np.ndarray, R: int, rng: np.random.Generator,
          exec_rho: float = 0.0) -> np.ndarray:
    """Draw R repeats. exec_rho>0 induces within-repeat shared latent
    execution quality (e.g. server-side sampling correlation): a repeat-
    level normal shift applied jointly to all members on each task."""
    M, T = Q.shape
    if exec_rho <= 0.0:
        return (rng.random((R, M, T)) < Q[None, :, :]).astype(float)
    # Gaussian latent copula-style correlation: per (repeat, task) shared
    # shift u, per-cell noise e, corr(u_shock, total_shock) tuned loosely.
    Y = np.empty((R, M, T))
    for r in range(R):
        u = rng.normal(0.0, exec_rho, size=(1, T))
        e = rng.normal(0.0, 1.0, size=(M, T))
        z = np.log(np.clip(Q, 1e-6, 1 - 1e-6) /
                   (1 - np.clip(Q, 1e-6, 1 - 1e-6)))
        p = _sigmoid(z + u + 0.0)  # shared shift moves all members together
        Y[r] = (rng.random((M, T)) < p).astype(float)
    return Y


# --------------------------------------------------------------------- D1/D2

def dgp_equal_ability(seed: int, M: int = 9, T: int = 400, R: int = 3,
                      q: float = 0.9, heterogeneity: bool = False,
                      exec_rho: float = 0.0) -> DGPResult:
    """All members share one per-task success probability.

    heterogeneity=False: constant q (reviewer counterexample 1; q=0.9).
    heterogeneity=True:  common latent task difficulty a_t (still identical
                         across members), so the bootstrap must not mistake
                         difficulty variance for member-task interaction.
    H_stable = 0 by construction.
    """
    rng = np.random.default_rng(seed)
    if heterogeneity:
        a, types = _task_difficulties(rng, T)
    else:
        a, types = np.full(T, q), np.zeros(T, int)
    Q = np.tile(a[None, :], (M, 1))
    Y = _draw(Q, R, rng, exec_rho)
    return DGPResult(Y=Y, Q=Q, H_true=0.0, null_family="equal_ability",
                     task_types=types,
                     description=("iid equal-ability q=%.2f" % q
                                  if not heterogeneity else
                                  "equal-ability with shared task difficulty"))


# ------------------------------------------------------------------------ D3

def dgp_global_dominance(seed: int, M: int = 9, T: int = 400, R: int = 3,
                         gap: float = 0.4, base_q: float = 0.5,
                         heterogeneous: bool = True,
                         member_spread: bool = True,
                         dominant_index: int = 1,
                         exec_rho: float = 0.0) -> DGPResult:
    """One fixed member is expectation-best on EVERY task (H_stable = 0),
    while other members may be much better/worse than the reference.

    Defaults instantiate reviewer counterexample 2: the reference member
    (index 0) has q=0.5 on all tasks, the other 8 members q=0.9, so any
    vs-bare discovery statistic shows a large gain despite zero
    complementarity. dominant_index moves the dominant profile to another
    slot (index 0 = the clean zero-G null where tie-breaking favors the
    dominant member).

    heterogeneous: add shared task-difficulty variation around the levels.
    member_spread: give non-dominant members small fixed offsets, all still
                   strictly below the dominant member.
    """
    rng = np.random.default_rng(seed)
    a, types = _task_difficulties(rng, T) if heterogeneous else \
        (np.full(T, 0.775), np.zeros(T, int))
    # center the difficulty swing so mean(base)=base_q and mean(dom)=base_q+gap
    a = a - a.mean()
    Q = np.empty((M, T))
    weak_levels = np.full(M, base_q)
    for m in range(M):
        offset = 0.0 if not member_spread else (m - M / 2) * 0.01
        weak_levels[m] = base_q + offset
    for m in range(M):
        Q[m] = np.clip(weak_levels[m] + a, 0.02, 0.98)
    Q[dominant_index] = np.clip(base_q + gap + a, 0.02, 0.99)
    # guarantee strict dominance of the dominant member
    for m in range(M):
        if m != dominant_index:
            Q[m] = np.minimum(Q[m], Q[dominant_index] - 0.02)
    Y = _draw(Q, R, rng, exec_rho)
    H = float(Q.max(axis=0).mean() - Q.mean(axis=1).max())
    return DGPResult(Y=Y, Q=Q, H_true=H, null_family="dominance",
                     task_types=types,
                     description=("global dominance: member %d=%.2f vs base=%.2f"
                                  % (dominant_index, base_q + gap, base_q)))


# ------------------------------------------------------------------------ D4

def dgp_crossover(seed: int, M: int = 9, T: int = 400, R: int = 3,
                  gamma: float = 0.12, base_q: float = 0.88,
                  k_types: int = 3, specialization: float = 1.0,
                  noise_members: int = 0,
                  exec_rho: float = 0.0) -> DGPResult:
    """Genuine task x member interaction: each member is specialized for one
    latent task type, so the per-task argmax crosses members across tasks
    and H_stable > 0.

    Q[m,t] = sigmoid(logit(base + a_t) + gamma * s[m,type(t)])
    Specialization profiles sum to zero within a type, and each type has a
    distinct best member. `noise_members` members get a flat (non-specialized)
    profile near base_q to mimic panel members that carry no interaction.
    """
    rng = np.random.default_rng(seed)
    a, types = _task_difficulties(rng, T, lo=0.6, hi=0.98, k_types=k_types)
    a = a - a.mean()
    # specialization score matrix S[M, k_types]: cyclic assignment, each
    # type has a distinct winner; rows for noise members are flat zero.
    S = np.zeros((M, k_types))
    n_active = M - noise_members
    for m in range(n_active):
        for k in range(k_types):
            # triangular wave: member m peaks at type m mod k_types
            d = abs(((m - k) % max(1, n_active)))
            S[m, k] = specialization * (1.0 if d == 0 else -0.6 / max(1, d))
    z = np.log(np.clip(base_q + a[:, None], 1e-6, 1 - 1e-6) /
               (1 - np.clip(base_q + a[:, None], 1e-6, 1 - 1e-6)))
    Q = _sigmoid(z.T + gamma * S[:, types]).clip(0.02, 0.99)
    Y = _draw(Q, R, rng, exec_rho)
    H = float(Q.max(axis=0).mean() - Q.mean(axis=1).max())
    return DGPResult(Y=Y, Q=Q, H_true=H, null_family="crossover",
                     task_types=types,
                     description=f"crossover gamma={gamma}, k={k_types}, "
                                 f"H={H:.3f}")


def dgp_two_specialist(seed: int, M: int = 9, T: int = 400, R: int = 3,
                       base_q: float = 0.6, gap: float = 0.35
                       ) -> "DGPResult":
    """CLEAN two-specialist crossover power DGP.

    Two members are strong specialists on two disjoint task halves
    (base+gap); the remaining M-2 members are at base everywhere.
    H_stable = gap/2 and the frozen selector can recover it once discovery
    repeats separate a specialist from the base crowd --- unlike the cyclic
    multi-specialist dgp_crossover, where same-type specialists compete and
    dilute the selectable gain. This is the positive-control power curve."""
    rng = np.random.default_rng(seed)
    _, types = _task_difficulties(rng, T, k_types=2)
    Q = np.full((M, T), base_q)
    Q[0, :T // 2] = min(0.99, base_q + gap)
    Q[1, T // 2:] = min(0.99, base_q + gap)
    H = float(Q.max(0).mean() - Q.mean(1).max())
    Y = _draw(Q, R, rng)
    return DGPResult(Y=Y, Q=Q, H_true=H, null_family="crossover",
                     task_types=np.array(types),
                     description=f"two strong specialists +/- {gap} over base {base_q}")


def dgp_partial_crossover(seed: int, M: int = 9, T: int = 400, R: int = 3,
                          frac_cross: float = 0.25, gap: float = 0.10,
                          base_q: float = 0.9) -> DGPResult:
    """Small-H alternative: a globally best member except on a fraction of
    tasks where another member wins. Used to map power near the 1 pp margin."""
    rng = np.random.default_rng(seed)
    a, _ = _task_difficulties(rng, T)
    a = a - a.mean()
    Q = np.broadcast_to(base_q + a, (M, T)).copy()
    cross_idx = rng.choice(T, size=int(frac_cross * T), replace=False)
    Q[0, cross_idx] = np.clip(base_q + a[cross_idx] - gap, 0.02, 0.99)
    Q[1, cross_idx] = np.clip(base_q + a[cross_idx] + gap, 0.02, 0.99)
    # member 1 best elsewhere
    Q[1, :] = np.maximum(Q[1, :], Q[0, :] + 0.02)
    Q[1, cross_idx] = Q[0, cross_idx] - 0.04
    Y = _draw(Q, R, rng)
    H = float(Q.max(axis=0).mean() - Q.mean(axis=1).max())
    return DGPResult(Y=Y, Q=Q, H_true=H, null_family="crossover",
                     task_types=np.isin(np.arange(T), cross_idx).astype(int),
                     description=f"partial crossover frac={frac_cross}, H={H:.3f}")


# ------------------------------------------------------------- clone-arm draw

def draw_clone_arm(Q_real: np.ndarray, task_types: np.ndarray, R: int,
                   seed: int, base_member: int = 0,
                   slot_effect_sd: float = 0.0,
                   exec_rho: float = 0.0) -> np.ndarray:
    """Same-code clone slots for the same tasks.

    All slots share the reference member's probability profile. Nonzero
    slot_effect_sd adds fixed slot-level offsets (a stress test of the
    exchangeability assumption; default 0 = exact same code)."""
    rng = np.random.default_rng(seed)
    M = Q_real.shape[0]
    base = Q_real[base_member]
    Qc = np.tile(base[None, :], (M, 1))
    if slot_effect_sd > 0:
        offsets = rng.normal(0.0, slot_effect_sd, size=(M, 1))
        Qc = np.clip(Qc + offsets, 0.02, 0.99)
    return _draw(Qc, R, rng, exec_rho)


# -------------------------------------------------------------- missingness

def apply_missingness(Y: np.ndarray, seed: int, frac: float,
                      mechanism: str = "mcar",
                      Q: np.ndarray | None = None) -> np.ndarray:
    """Return a copy of Y with NaN cells.

    mechanism='mcar': cells removed uniformly at random.
    mechanism='mnar_hard': removal probability is higher for hard tasks
        (low Q) and concentrated on specified members, mimicking provider
        timeouts on long/hard items; informative, never ignorable.
    """
    rng = np.random.default_rng(seed)
    out = Y.copy()
    R, M, T = out.shape
    if mechanism == "mcar":
        mask = rng.random((R, M, T)) < frac
        out[mask] = np.nan
    elif mechanism == "mnar_hard":
        if Q is None:
            raise ValueError("mnar_hard requires Q")
        # harder tasks (low max Q) are more likely to be missing, plus a
        # member-specific vulnerability
        hard = 1.0 - Q.max(axis=0)
        p = np.clip(3.0 * frac * (0.3 + hard / max(hard.max(), 1e-9)), 0, 0.9)
        for m in range(M):
            pm = p * (2.0 if m >= M - 2 else 0.6)
            u = rng.random((R, T))
            out[:, m, :][u < pm[None, :]] = np.nan
    else:
        raise ValueError(f"unknown missingness mechanism {mechanism}")
    return out


REGISTRY = {
    "equal_const": dict(fn=dgp_equal_ability, kwargs=dict(q=0.9)),
    "equal_hetero": dict(fn=dgp_equal_ability,
                         kwargs=dict(q=0.9, heterogeneity=True)),
    "dominance_reviewer": dict(fn=dgp_global_dominance,
                               kwargs=dict(base_q=0.5, gap=0.4,
                                           heterogeneous=False, member_spread=False,
                                           dominant_index=1)),
    "dominance_clean": dict(fn=dgp_global_dominance,
                            kwargs=dict(base_q=0.75, gap=0.12,
                                        heterogeneous=True, member_spread=False,
                                        dominant_index=0)),
    "dominance_hetero": dict(fn=dgp_global_dominance,
                             kwargs=dict(base_q=0.8, gap=0.1,
                                         dominant_index=1)),
    "cross_strong": dict(fn=dgp_crossover, kwargs=dict(gamma=0.25)),
    "cross_vstrong": dict(fn=dgp_crossover,
                          kwargs=dict(gamma=0.6, k_types=2, base_q=0.8)),
    "cross_mid": dict(fn=dgp_crossover, kwargs=dict(gamma=0.12)),
    "cross_weak": dict(fn=dgp_partial_crossover,
                       kwargs=dict(frac_cross=0.2, gap=0.12)),
    "two_specialist": dict(fn=dgp_two_specialist,
                           kwargs=dict(base_q=0.6, gap=0.35)),
}
