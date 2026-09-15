"""Core diagnostic pipeline (S1-S5) per review-stage/DIAGNOSTIC_PLAN_20260915.md (FROZEN v1.3).

Scientific states are this project's own definitions (plan section 3), not ARIS-native
statuses: SUPPORTED / REFUTED_WITHIN_SCOPE / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE.

Offline only: no model API calls. All randomness is seeded; bootstrap units are tasks
(BIRD: (database, task) pairs resampled within database, matching replay.py's design).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SUPPORTED = "SUPPORTED"
REFUTED = "REFUTED_WITHIN_SCOPE"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
NOT_APPLICABLE = "NOT_APPLICABLE"

MIN_REPEATS = 3          # plan 3.C
MIN_REPEAT_TASKS = 30    # plan 3.C
ABSTAIN_EPS = 0.15       # plan 3.D (calibrated 0.05->0.15 during calibration; frozen for blinded)
LAMBDA_HARM = 1.0        # plan 3.E (frozen)
BUDGET_CALLS = 1         # plan 3.E (frozen: single-member selection)


@dataclass
class Population:
    """Members x task outcome matrix for one execution condition c.

    Y[i, j] in {0.0, 1.0}; NaN = missing (kept in the denominator, never imputed).
    members[0] is the bare reference when has_bare.
    """
    member_ids: list[str]
    source_hashes: list[str]
    tasks: list[str]
    Y: np.ndarray                     # (n_members, n_tasks), float with NaN
    condition: dict                   # execution condition c (all fields must match)
    has_bare: bool = True
    dev_task_ids: list[str] = field(default_factory=list)
    task_meta: dict = field(default_factory=dict)   # tid -> dict of pre-execution metadata
    calls: dict = field(default_factory=dict)       # (member_id, tid) -> logical calls
    # S1 inputs for synthetic controls (real adapters pass counters separately):
    judge_replay_mismatches: int = 0
    duplicate_keys: int = 0

    @property
    def n_gen(self) -> int:
        return len(self.member_ids) - (1 if self.has_bare else 0)

    def k_stats(self) -> dict:
        """Plan 2: K_raw / K_unique / unique outcome vectors, numerator and
        denominator on the SAME membership basis (both with and without bare)."""
        n = len(self.member_ids)
        seen_hashes, unique_members = set(), 0
        for h in self.source_hashes[1:] if self.has_bare else self.source_hashes:
            if h not in seen_hashes:
                seen_hashes.add(h)
                unique_members += 1
        vecs = {tuple(self.Y[i]) for i in range(n)}
        vecs_gen = {tuple(self.Y[i]) for i in range(n) if i > 0} if self.has_bare else vecs
        denom = self.n_gen if self.has_bare else n
        return {
            "K_raw": self.n_gen,
            "K_unique_source": unique_members,
            "unique_outcome_vectors_incl_bare": len(vecs),
            "unique_outcome_vectors_excl_bare": len(vecs_gen),
            "vectors_per_gen_incl_bare": round(len(vecs) / max(1, denom), 4),
            "vectors_per_gen_excl_bare": round(len(vecs_gen) / max(1, denom), 4),
        }


# ---------------------------------------------------------------- S1 integrity

def s1_integrity(manifest: dict, pop: Population, judge_replay_mismatches: int,
                 duplicate_keys: int, hash_conflicts: list[str]) -> dict:
    """Plan 3.A: manifest consistency, judge replay, identity uniqueness."""
    missing_cells = int(np.isnan(pop.Y).sum())
    missing_frac = missing_cells / pop.Y.size if pop.Y.size else 0.0
    checks = {
        "manifest_member_match": manifest["member_ids"] == pop.member_ids,
        "manifest_task_match": manifest["task_ids"] == pop.tasks,
        "judge_replay_consistent": judge_replay_mismatches == 0,
        "no_duplicate_keys": duplicate_keys == 0,
        "no_source_hash_conflict": not hash_conflicts,
        "missing_cells_le_1pct": missing_frac <= 0.01,
    }
    blocked = [k for k, ok in checks.items() if not ok]
    state = SUPPORTED if not blocked else REFUTED
    return {
        "state": state, "checks": checks, "blocked": blocked,
        "missing_cells": missing_cells, "missing_frac": round(missing_frac, 6),
        "duplicate_keys": duplicate_keys,
        "source_hash_conflicts": hash_conflicts,
        "judge_replay_mismatches": judge_replay_mismatches,
        "minimal_missing_evidence": [] if not blocked else
            [f"repair {k} then re-run" for k in blocked],
    }


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()



def _acc(v) -> float:
    """Denominator-preserving accuracy: unknown/missing cells stay in the
    denominator (counted as not-correct) per the frozen propagation rule;
    missing counts are reported separately, never silently dropped."""
    v = np.asarray(v, dtype=float)
    return float(np.nansum(v)) / len(v)


def _accs_rows(Y: np.ndarray) -> np.ndarray:
    return np.nansum(Y, axis=1) / Y.shape[1]


# ------------------------------------------------------------ S2 decomposition

def s2_decomposition(pop: Population, n_boot: int = 4000, seed: int = 20260915) -> dict:
    """Plan 3.B: oracle / best-fixed / dev-fixed / bare on ONE execution matrix.

    Paired task bootstrap (strata = unique task strata key when metadata provides
    a database/subject grouping, else plain task resample). CI > 0 -> SUPPORTED
    restricted to "this matrix has unused single-shot coverage".
    """
    Y = pop.Y
    n_t = Y.shape[1]
    oracle_per_task = np.nanmax(Y, axis=0)
    accs = {m: _acc(Y[i]) for i, m in enumerate(pop.member_ids)}
    best_fixed_m = max(accs, key=accs.get)
    best_fixed = float(accs[best_fixed_m])
    oracle = float(np.nansum(oracle_per_task) / n_t)
    headroom = oracle - best_fixed

    dev_fixed_m, dev_fixed = None, None
    if pop.dev_task_ids:
        dev_idx = [pop.tasks.index(t) for t in pop.dev_task_ids if t in pop.tasks]
        if dev_idx:
            dev_accs = {m: _acc(Y[i, dev_idx]) for i, m in enumerate(pop.member_ids)}
            dev_fixed_m = max(dev_accs, key=dev_accs.get)
            dev_fixed = float(dev_accs[dev_fixed_m])

    rng = np.random.default_rng(seed)
    strata = _strata(pop)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = _resample(strata, n_t, rng)
        # best-fixed must be re-selected per bootstrap draw (held-out principle)
        accs_b = {i: _acc(Y[i, idx]) for i in range(Y.shape[0])}
        boots[b] = (_acc(np.nanmax(Y[:, idx], axis=0)) - max(accs_b.values()))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    if lo > 0:
        state = SUPPORTED
    elif hi <= 1e-12:
        state = REFUTED      # CI excludes positive coverage (includes exact-zero headroom)
    else:
        state = INSUFFICIENT
    bare_acc = _acc(Y[0]) if pop.has_bare else None
    return {
        "state": state,
        "oracle_accuracy": round(oracle, 4),
        "best_fixed_member": best_fixed_m, "best_fixed_accuracy": round(best_fixed, 4),
        "dev_fixed_member": dev_fixed_m,
        "dev_fixed_accuracy": None if dev_fixed is None else round(dev_fixed, 4),
        "bare_accuracy": None if bare_acc is None else round(bare_acc, 4),
        "headroom": round(headroom, 4),
        "headroom_ci95": [round(lo, 4), round(hi, 4)],
        "residual_coverage_vs_bare": None if bare_acc is None else round(oracle - bare_acc, 4),
        "info_boundaries": ("oracle uses per-task outcomes of all members; best-fixed uses "
                            "outcome-averages over the same eval tasks; dev-fixed uses dev "
                            "data only; headroom is not a realizable gain (plan 2)"),
    }


def _strata(pop: Population) -> dict:
    groups: dict[str, list[int]] = {}
    for j, t in enumerate(pop.tasks):
        key = pop.task_meta.get(t, {}).get("stratum", "__all__")
        groups.setdefault(str(key), []).append(j)
    return groups


def _resample(strata: dict, n_t: int, rng) -> np.ndarray:
    parts = []
    for _, idxs in strata.items():
        idxs = np.asarray(idxs)
        parts.append(rng.choice(idxs, len(idxs), replace=True))
    return np.concatenate(parts)


# --------------------------------------------------------- S3 same-condition repeats

def s3_stability(pop_by_condition: dict[str, Population]) -> dict:
    """Plan 3.C: R >= MIN_REPEATS matched conditions covering >= MIN_REPEAT_TASKS tasks.

    pop_by_condition maps condition-key -> Population with identical membership and
    task set. Without matched repeats the state is INSUFFICIENT (an explicit
    abstention, not 'no difference').
    """
    conds = sorted(pop_by_condition)
    if len(conds) < MIN_REPEATS:
        return {
            "state": INSUFFICIENT,
            "reason": f"R={len(conds)} matched condition groups < {MIN_REPEATS}",
            "minimal_missing_evidence": [
                f"collect >= {MIN_REPEATS} same-condition repeats (all c fields equal) "
                f"over >= {MIN_REPEAT_TASKS} shared tasks"],
        }
    base = pop_by_condition[conds[0]]
    for c in conds[1:]:
        p = pop_by_condition[c]
        if p.member_ids != base.member_ids or p.tasks != base.tasks:
            return {"state": INSUFFICIENT, "reason": "membership/task set differs across conditions",
                    "minimal_missing_evidence": ["matched membership and tasks across repeats"]}
    Y = np.stack([pop_by_condition[c].Y for c in conds])       # (R, members, tasks)
    R, M, T = Y.shape
    if T < MIN_REPEAT_TASKS:
        return {"state": INSUFFICIENT,
                "reason": f"T={T} shared tasks < {MIN_REPEAT_TASKS}",
                "minimal_missing_evidence": [f">= {MIN_REPEAT_TASKS} shared tasks per repeat"]}
    rng = np.random.default_rng(20260915)
    pair_reports = []
    overall = INSUFFICIENT
    for h1 in range(M):
        for h2 in range(h1 + 1, M):
            deltas = [_acc(Y[r, h1] - 0) - _acc(Y[r, h2] - 0) for r in range(R)]
            boots = []
            for _ in range(2000):
                idx = rng.choice(T, T, replace=True)
                boots.append(np.nansum(Y[:, h1, idx], axis=1) / T - np.nansum(Y[:, h2, idx], axis=1) / T)
            lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)  # per-repeat CIs
            lo_all, hi_all = np.percentile(np.mean(boots, axis=1), [2.5, 97.5])
            signs = {int(np.sign(d)) for d in deltas}
            if lo_all > 0 and signs == {1}:
                st = SUPPORTED
            elif hi_all < 0 and signs == {-1}:
                st = REFUTED
            else:
                st = INSUFFICIENT
            pair_reports.append({"h1": base.member_ids[h1], "h2": base.member_ids[h2],
                                 "state": st, "mean_delta": round(float(np.mean(deltas)), 4),
                                 "ci95": [round(float(lo_all), 4), round(float(hi_all), 4)]})
            if st == SUPPORTED:
                overall = SUPPORTED
    if overall == INSUFFICIENT and any(p["state"] == REFUTED for p in pair_reports):
        overall = REFUTED
    return {
        "state": overall, "R": R, "shared_tasks": T,
        "estimand": "pairwise per-member-pair accuracy difference under matched conditions; "
                    "SUPPORTED only for a pair with CI excluding 0 and sign-consistent across repeats",
        "pairs": pair_reports,
        "note": ("pairing is across same-condition repeats; cross-time/provider batches are "
                 "non_exchangeable and excluded from this estimate"),
    }


# ------------------------------------------------------ S4 pre-execution selectability

def _softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _fit_member_probs(X_dev, Y_dev, X_ev, epochs=2000, lr=0.5):
    """Frozen policy core: per-member logistic P(Y_h=1 | features), fit on dev.

    Tie-free alternative to argmax labelling; returns predicted per-member
    correct probabilities on eval rows (n_ev, n_members).
    """
    n_m = Y_dev.shape[0]
    probs = np.zeros((X_ev.shape[0], n_m))
    for h in range(n_m):
        y = Y_dev[h]
        if np.all(np.isnan(y)):
            continue
        w = np.zeros(X_dev.shape[1])
        b0 = float(np.log(np.clip(np.nanmean(y), 1e-3, 0.999)) *
                   -np.log(1 - np.clip(np.nanmean(y), 1e-3, 0.999)))
        b0 = 0.0
        valid = ~np.isnan(y)
        for _ in range(epochs):
            p = _sigmoid(X_dev[valid] @ w + b0)
            g = (X_dev[valid].T @ (p - y[valid])) / max(1, valid.sum())
            w -= lr * g
            b0 -= lr * float(np.mean(p - y[valid]))
        probs[:, h] = _sigmoid(X_ev @ w + b0)
    return probs


def _feature_matrix(pop: Population, idxs: list[int]) -> np.ndarray:
    strata = sorted(_strata(pop))
    X = np.zeros((len(idxs), len(strata) + 1))
    for r, j in enumerate(idxs):
        key = str(pop.task_meta.get(pop.tasks[j], {}).get("stratum", "__all__"))
        X[r, strata.index(key) if key in strata else len(strata)] = 1.0
    return X


def _policy_choices(pop: Population, dev_idx: list[int], ev_idx: list[int]) -> np.ndarray:
    """Frozen pi_Z: argmax_h P_h(correct|Z(x)); abstain->bare when top-2 gap <
    ABSTAIN_EPS. (Calibration removed the dev-accuracy log prior: it swamped
    stratum-level signals and duplicated dev-fixed selection; frozen for blinded.)"""
    X_dev = _feature_matrix(pop, dev_idx)
    X_ev = _feature_matrix(pop, ev_idx)
    probs = _fit_member_probs(X_dev, pop.Y[:, dev_idx], X_ev)
    top2 = np.sort(probs, axis=1)[:, -2:]
    return np.where((top2[:, 1] - top2[:, 0]) < ABSTAIN_EPS, 0, np.argmax(probs, axis=1))


def s4_selectability(pop: Population, seed: int = 20260915) -> dict:
    """Plan 3.D: frozen pi_Z vs dev-fixed on held-out eval tasks.

    Features per task: one-hot task stratum (database/subject) + pre-execution
    metadata; member prior from dev accuracies is a bias term only. Training uses
    dev tasks exclusively. Abstain -> bare when top-2 posterior gap < ABSTAIN_EPS.
    """
    if not pop.dev_task_ids:
        return {"state": INSUFFICIENT,
                "reason": "no development split available for frozen policy training",
                "minimal_missing_evidence": ["a dev split disjoint from eval tasks"]}
    dev_idx = [pop.tasks.index(t) for t in pop.dev_task_ids if t in pop.tasks]
    ev_idx = [j for j, t in enumerate(pop.tasks) if t not in set(pop.dev_task_ids)]
    if not ev_idx:
        return {"state": INSUFFICIENT, "reason": "no held-out eval tasks"}

    strata = sorted(_strata(pop))
    def feats(idxs):
        return _feature_matrix(pop, idxs)

    # class prior from dev (member-level pre-execution info), applied as bias
    dev_acc = _accs_rows(pop.Y[:, dev_idx])

    choice = _policy_choices(pop, dev_idx, ev_idx)

    Y_ev = pop.Y[:, ev_idx]
    pi_acc = np.array([Y_ev[c, j] for j, c in enumerate(choice)])
    valid = ~np.isnan(pi_acc)
    pi_rate = float(np.nansum(pi_acc) / len(pi_acc))
    dev_fixed_idx = int(np.argmax(_accs_rows(pop.Y[:, dev_idx])))
    paired = pi_acc - Y_ev[dev_fixed_idx]
    n_valid = int(valid.sum())
    rng = np.random.default_rng(seed)
    # denominator-preserving: unknown cells count as 0, stay in the denominator
    boots = [float(np.nansum(rng.choice(paired, len(paired), replace=True))) / len(paired) for _ in range(4000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    if lo > 0:
        state = SUPPORTED
    elif hi < 0:
        state = REFUTED
    else:
        state = INSUFFICIENT
    return {
        "state": state,
        "policy": "frozen multinomial LR on task stratum one-hot + dev-accuracy prior; "
                  f"abstain->bare when top-2 gap < {ABSTAIN_EPS}",
        "eval_tasks": len(ev_idx), "abstain_rate": round(float((choice == 0).mean()), 4),
        "pi_Z_accuracy": round(pi_rate, 4),
        "dev_fixed_member": pop.member_ids[dev_fixed_idx],
        "dev_fixed_accuracy": round(_acc(Y_ev[dev_fixed_idx]), 4),
        "pi_Z_minus_devfixed_ci95": [round(lo, 4), round(hi, 4)],
        "leakage_boundary": "training used dev tasks only; eval tasks never entered fitting",
    }


# ------------------------------------------------------------------ S5 cost model

def s5_cost(pop: Population, s4: dict) -> dict:
    """Plan 3.E: P = pi_Z single-member (1 call/task) vs dev-fixed (1 call/task).

    Cost-matched by construction; oracle-routing (K calls) is a post-execution
    reference only. Net utility U = acc diff - LAMBDA_HARM * harm diff; harm =
    wrong while bare right. Missing call counts force INSUFFICIENT for claims
    beyond the matched-budget design.
    """
    if not pop.has_bare or s4.get("state") in (INSUFFICIENT,) and "dev split" in s4.get("reason", ""):
        return {"state": INSUFFICIENT, "reason": "pi_Z unavailable or no bare reference",
                "minimal_missing_evidence": ["trainable dev split"]}
    if not pop.calls:
        cost_evidence = "calls_missing"
    else:
        per_call = [v for v in pop.calls.values() if v is not None]
        cost_evidence = {"median_calls": float(np.median(per_call)) if per_call else None}
    # U is computed on the same eval tasks as S4 by re-running the frozen choice rule
    dev_idx = [pop.tasks.index(t) for t in pop.dev_task_ids if t in pop.tasks]
    ev_idx = [j for j, t in enumerate(pop.tasks) if t not in set(pop.dev_task_ids)]
    if not ev_idx:
        return {"state": INSUFFICIENT, "reason": "no held-out eval tasks"}
    choice = _policy_choices(pop, dev_idx, ev_idx)
    Y_ev = pop.Y[:, ev_idx]
    pi_acc = np.array([Y_ev[c, j] for j, c in enumerate(choice)])
    dev_fixed_idx = int(np.argmax(_accs_rows(pop.Y[:, dev_idx])))
    bare = Y_ev[0]
    harm_P = float(np.mean((pi_acc == 0) & (bare == 1)))
    harm_D = float(np.mean((Y_ev[dev_fixed_idx] == 0) & (bare == 1)))
    U = float(np.nansum(pi_acc) / len(pi_acc) - _acc(Y_ev[dev_fixed_idx]) - LAMBDA_HARM * (harm_P - harm_D))
    paired = (pi_acc - Y_ev[dev_fixed_idx]) - LAMBDA_HARM * (
        ((pi_acc == 0) & (bare == 1)).astype(float) - ((Y_ev[dev_fixed_idx] == 0) & (bare == 1)).astype(float))
    rng = np.random.default_rng(20260915)
    boots = [np.nansum(rng.choice(paired, len(paired), replace=True)) / len(paired) for _ in range(4000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    state = SUPPORTED if lo > 0 else (REFUTED if hi < 0 else INSUFFICIENT)
    return {
        "state": state, "policy": "pi_Z single member", "budget_calls_per_task": BUDGET_CALLS,
        "lambda_harm": LAMBDA_HARM, "comparator": "dev-fixed (same budget)",
        "U": round(U, 4), "U_ci95": [round(lo, 4), round(hi, 4)],
        "cost_evidence": cost_evidence,
        "note": ("real dollar/token costs are not recoverable from these archives; SUPPORT "
                 "is limited to the matched 1-call budget, not billable deployment"),
    }


def assemble_report(s1: dict, s2: dict, s3: dict, s4: dict, s5: dict) -> dict:
    return {
        "A_measurement_sufficiency": s1,
        "B_single_shot_coverage": s2,
        "C_stability": s3,
        "D_pre_execution_selectability": s4,
        "E_policy_utility": s5,
        "state_vocabulary": [SUPPORTED, REFUTED, INSUFFICIENT, NOT_APPLICABLE],
        "states_are_project_definitions": True,
    }
