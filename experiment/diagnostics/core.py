"""Core diagnostic pipeline (S1-S5) per review-stage/DIAGNOSTIC_PLAN_20260915.md (FROZEN v1.3).

Scientific states are this project's own definitions (plan section 3), not ARIS-native
statuses: SUPPORTED / REFUTED_WITHIN_SCOPE / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE.

Offline only: no model API calls. All randomness is seeded; bootstrap units are tasks
(BIRD: (database, task) pairs resampled within database, matching replay.py's design).
"""
from __future__ import annotations

import hashlib
import json
import warnings
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
    # provenance of the calls dict: "per_record" (read from archive rows),
    # "aggregate_only" (archive reports totals the adapter did not read row-wise),
    # "absent_in_archive_rows", "not_provided" (caller supplied no evidence either way)
    calls_status: str = "not_provided"
    # True ONLY for synthetic designs where the 1-call budget is part of the
    # generating mechanism (cost-matched by construction), never for archives:
    # this is the frozen plan's design-by-construction exception; archives must
    # verify call counts to leave INSUFFICIENT_EVIDENCE
    budget_by_construction: bool = False
    # S1 inputs for synthetic controls (real adapters pass counters separately):
    judge_replay_mismatches: int = 0
    duplicate_keys: int = 0
    # Optional execution provenance for identity gate 3: when two repeats
    # have byte-identical outcome matrices, independence is accepted ONLY if
    # both carry independent, distinct execution identifiers. Absent provenance,
    # identical matrices force an abstention as before (never auto-passed).
    repeat_provenance: dict = field(default_factory=dict)

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

# Judge-replay evidence must state whether the replay was actually executed;
# "not executed" must never be rendered as "check passed".
JUDGE_REPLAY_EXECUTED = "executed"
JUDGE_REPLAY_NOT_EXECUTED = "not_executed"
JUDGE_REPLAY_INFEASIBLE = "infeasible"


def _normalize_judge_replay(judge_replay) -> dict:
    """Accept a status dict or a bare mismatch count (count => executed)."""
    if isinstance(judge_replay, dict):
        status = judge_replay.get("status", JUDGE_REPLAY_EXECUTED)
        mism = judge_replay.get("mismatches")
        return {"status": status, "mismatches": mism}
    return {"status": JUDGE_REPLAY_EXECUTED, "mismatches": int(judge_replay)}


def s1_integrity(manifest: dict, pop: Population, judge_replay,
                 duplicate_keys: int, hash_conflicts: list[str]) -> dict:
    """Plan 3.A (v2): manifest consistency, judge replay (with execution state),
    identity uniqueness.

    Check values: True = passed, False = violated (blocks), None = could not be
    run (forces INSUFFICIENT_EVIDENCE, never SUPPORTED).
    """
    jr = _normalize_judge_replay(judge_replay)
    if jr["status"] == JUDGE_REPLAY_EXECUTED:
        judge_check = int(jr["mismatches"] or 0) == 0
    else:
        judge_check = None          # not run: cannot claim consistency
    missing_cells = int(np.isnan(pop.Y).sum())
    missing_frac = missing_cells / pop.Y.size if pop.Y.size else 0.0
    checks = {
        "manifest_member_match": manifest["member_ids"] == pop.member_ids,
        "manifest_task_match": manifest["task_ids"] == pop.tasks,
        "judge_replay_consistent": judge_check,
        "no_duplicate_keys": duplicate_keys == 0,
        "no_source_hash_conflict": not hash_conflicts,
        "missing_cells_le_1pct": missing_frac <= 0.01,
    }
    blocked = [k for k, ok in checks.items() if ok is False]
    not_run = [k for k, ok in checks.items() if ok is None]
    if blocked:
        state = REFUTED
    elif not_run:
        state = INSUFFICIENT        # verification missing != verification passed
    else:
        state = SUPPORTED
    return {
        "state": state, "checks": checks, "blocked": blocked, "not_run": not_run,
        "judge_replay_status": jr["status"],
        "judge_replay_mismatches": jr["mismatches"],
        "missing_cells": missing_cells, "missing_frac": round(missing_frac, 6),
        "duplicate_keys": duplicate_keys,
        "source_hash_conflicts": hash_conflicts,
        "minimal_missing_evidence":
            ([f"repair {k} then re-run" for k in blocked] +
             [f"execute or bind evidence for {k}" for k in not_run]),
    }


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()



def _nanmean(arr, axis):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(arr, axis=axis)


def _acc(v) -> float:
    """Recorded success rate: unknown/missing cells stay in the denominator and
    count as not-correct (conservative, per the frozen propagation rule).

    This is a *recorded*-outcome rate, NOT a hypothesis-free estimate of the
    rate over unknown true correctness. Missing counts and pair-level
    imputation bounds (see _missing_bounds_delta) are reported alongside every
    comparison so missingness can never silently create or destroy a
    difference."""
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

def _missing_bounds_delta(y1: np.ndarray, y2: np.ndarray) -> tuple[float, float]:
    """Worst/best-case pair delta under every imputation of unknown cells.

    Observed delta counts missing as not-correct (denominator-preserving). These
    bounds report how much the *unknown* cells alone could move the delta, so a
    difference is never read as identified when missingness could flip it.
    """
    t = len(y1)
    lo = hi = 0.0
    for a, b in zip(y1, y2):
        a_vals = [0.0, 1.0] if np.isnan(a) else [float(a)]
        b_vals = [0.0, 1.0] if np.isnan(b) else [float(b)]
        diffs = [a - b for a in a_vals for b in b_vals]
        lo += min(diffs)
        hi += max(diffs)
    return lo / t, hi / t


def _canonical_pairs(member_ids: list[str]) -> list[tuple[int, int, str, str]]:
    """Directional pairs keyed by member ID order, NOT list position.

    Reversing or permuting the member list must not flip a pair's direction:
    h1 is always the lexicographically smaller member id, so the delta
    acc(h1)-acc(h2) is a property of the named pair, not of the input ordering.
    """
    order = sorted(range(len(member_ids)), key=lambda i: member_ids[i])
    pairs = []
    for x in range(len(order)):
        for y in range(x + 1, len(order)):
            i, j = order[x], order[y]
            pairs.append((i, j, member_ids[i], member_ids[j]))
    return pairs


def s3_stability(pop_by_condition: dict[str, Population],
                 clone_by_condition: dict[str, Population] | None = None,
                 clone_n_perm: int = 4000) -> dict:
    """Plan 3.C (v2): matched same-condition repeats, two separated estimands.

    Estimand 1 (stable ranking): for a member pair, the same-condition accuracy
    difference with task-level bootstrap CI, sign-consistent across repeats.
    Population state SUPPORTED iff some canonical pair shows a stable
    difference in either direction. Permutation invariance is structural:
    pair direction is fixed by member ID, never by list position.

    Estimand 2 (stable complementarity / task-harness interaction):
    H_stable = E_x max_h q_h(x) - max_h E_x q_h(x), where q_h(x) is member h's
    expected correctness on task x estimated across repeats. H_stable = 0 iff
    one fixed member is expectation-best on every task (global dominance), so
    a stable ranking difference CANNOT substitute for complementarity.

    Identity gates (v2): repeats with differing `condition` fields, differing
    per-member `source_hashes`, or exactly duplicated outcome matrices are
    refused as matched repeats (explicit INSUFFICIENT, with the offending
    fields listed) - mixing conditions or cloned matrices can never produce a
    SUPPORTED/REFUTED stability claim.
    """
    conds = sorted(pop_by_condition)
    abstain = lambda reason, extra=None: {
        "state": INSUFFICIENT, "reason": reason,
        "minimal_missing_evidence": [extra] if extra else []}
    if len(conds) < MIN_REPEATS:
        return abstain(
            f"R={len(conds)} matched condition groups < {MIN_REPEATS}",
            f"collect >= {MIN_REPEATS} same-condition repeats (all c fields equal) "
            f"over >= {MIN_REPEAT_TASKS} shared tasks")
    base = pop_by_condition[conds[0]]
    for c in conds[1:]:
        p = pop_by_condition[c]
        if p.member_ids != base.member_ids or p.tasks != base.tasks:
            return abstain("membership/task set differs across conditions",
                           "matched membership and tasks across repeats")
    # --- identity gate 1: execution condition must be identical across repeats
    # Canonical TYPED comparison of the whole condition object (including key
    # presence vs explicit null): 60 != "60", {} != {"timeout": null}
    cond_canonical = {json.dumps(pop_by_condition[c].condition, sort_keys=True)
                      for c in conds}
    cond_mismatch = {}
    if len(cond_canonical) > 1:
        present = sorted({k for c in conds for k in pop_by_condition[c].condition})
        for f in present + [None]:
            vals = {json.dumps(pop_by_condition[c].condition.get(f), sort_keys=True)
                    for c in conds}
            if len(vals) > 1:
                cond_mismatch[str(f)] = sorted(vals)
        if not cond_mismatch:
            cond_mismatch["<whole_object>"] = sorted(cond_canonical)
    if cond_mismatch:
        return abstain(
            "execution condition fields differ across purported repeats; "
            "these are different conditions, not matched repeats",
            "collect repeats under one identical execution condition")
    # --- identity gate 2: member source identity must be constant across repeats
    identity_conflicts = []
    for i, m in enumerate(base.member_ids):
        hashes = {pop_by_condition[c].source_hashes[i] for c in conds}
        if len(hashes) > 1:
            identity_conflicts.append({"member": m, "hashes": sorted(hashes)})
    if identity_conflicts:
        return abstain(
            "member source identity differs across repeats (changed code "
            "masquerading as same-condition repeats)",
            "re-collect repeats under frozen member source code")
    # --- identity gate 3: duplicated matrices require independent provenance.
    # Byte-identical outcome matrices alone are never sufficient evidence of
    # independent executions, but near-deterministic members can legitimately
    # reproduce identical correctness: equality therefore triggers PROVENANCE
    # VERIFICATION rather than an automatic rejection of the data. Identical
    # matrices pass only when both repeats carry distinct, explicitly
    # independent execution identifiers; otherwise S3 abstains.
    identical_pairs = []
    for a in range(len(conds)):
        for b in range(a + 1, len(conds)):
            Pa, Pb = pop_by_condition[conds[a]], pop_by_condition[conds[b]]
            if Pa.Y.shape == Pb.Y.shape and np.array_equal(Pa.Y, Pb.Y,
                                                           equal_nan=True):
                prov_a = Pa.repeat_provenance.get(conds[a])
                prov_b = Pb.repeat_provenance.get(conds[b])
                independent = bool(
                    prov_a and prov_b
                    and prov_a.get("independent_execution") is True
                    and prov_b.get("independent_execution") is True
                    and prov_a.get("execution_id")
                    != prov_b.get("execution_id"))
                if not independent:
                    identical_pairs.append([conds[a], conds[b]])
    if identical_pairs:
        return abstain(
            "repeats contain exactly identical outcome matrices and "
            "independent-execution provenance is absent or not distinct; "
            "independence of executions cannot be verified",
            "bind distinct request/execution identifiers "
            "(repeat_provenance.independent_execution) or re-run repeats "
            "as separate executions")
    Y = np.stack([pop_by_condition[c].Y for c in conds])       # (R, members, tasks)
    R, M, T = Y.shape
    if T < MIN_REPEAT_TASKS:
        return abstain(f"T={T} shared tasks < {MIN_REPEAT_TASKS}",
                       f">= {MIN_REPEAT_TASKS} shared tasks per repeat")
    rng = np.random.default_rng(20260915)
    n_boot_rank = 2000
    # Shared task-resample index across ALL pairs: the max-T adjustment needs
    # the joint (over pairs) distribution from the same bootstrap draw, not
    # independent per-pair draws.
    boot_idx = rng.choice(T, size=(n_boot_rank, T), replace=True)
    pairs = _canonical_pairs(base.member_ids)
    # observed per-repeat deltas and bootstrap mean-delta matrix per pair
    obs_deltas = []
    boot_means = []
    for i, j, _, _ in pairs:
        deltas = np.array([_acc(Y[r, i]) - _acc(Y[r, j]) for r in range(R)])
        # per-draw per-repeat paired differences on shared task resamples,
        # averaged over the R repeats -> (n_boot,)
        diffs = ((np.nansum(Y[:, i, :][:, boot_idx], axis=2)
                  - np.nansum(Y[:, j, :][:, boot_idx], axis=2)) / T)
        bi = diffs.mean(axis=0)
        obs_deltas.append(deltas)
        boot_means.append(bi)
    boot_means = np.array(boot_means)                  # (n_pairs, n_boot)
    se = boot_means.std(axis=1, ddof=1)
    se = np.where(se < 1e-12, 1e-12, se)
    t_mat = (boot_means - boot_means.mean(axis=1, keepdims=True)) / se[:, None]
    max_t = np.max(np.abs(t_mat), axis=0)              # joint over pairs/draw
    crit = float(np.percentile(max_t, 95))             # max-T 95% critical value

    pair_reports = []
    stable_diff_exists = False
    decisive_nonconsistent = False
    for k, (i, j, id1, id2) in enumerate(pairs):
        deltas = obs_deltas[k]
        mean_d = float(deltas.mean())
        # marginal (unadjusted) interval for continuity
        lo_m, hi_m = np.percentile(boot_means[k], [2.5, 97.5])
        # simultaneous max-T interval (family-wise 95% over all pairs)
        lo_all, hi_all = mean_d - crit * se[k], mean_d + crit * se[k]
        signs = {int(np.sign(d)) for d in deltas}
        if lo_all > 0 and signs == {1}:
            st = SUPPORTED
        elif hi_all < 0 and signs == {-1}:
            st = REFUTED        # stable difference, direction opposite canonical
        else:
            st = INSUFFICIENT
            if hi_all < 0 or lo_all > 0:
                decisive_nonconsistent = True
        if st in (SUPPORTED, REFUTED):
            stable_diff_exists = True
        mlo, mhi = _missing_bounds_delta(_nanmean(Y[:, i, :], 0),
                                         _nanmean(Y[:, j, :], 0))
        pair_reports.append({
            "h1": id1, "h2": id2, "state": st,
            "mean_delta": round(mean_d, 4),
            "ci95_marginal": [round(float(lo_m), 4), round(float(hi_m), 4)],
            "ci95_maxT_simultaneous": [round(float(lo_all), 4),
                                       round(float(hi_all), 4)],
            "multiplicity": "max-T simultaneous 95% interval over all "
                            f"{len(pairs)} canonical pairs (shared task "
                            "bootstrap draws)",
            "missing_sensitivity_bounds": [round(mlo, 4), round(mhi, 4)],
            "direction_note": "h1/h2 fixed by member id order; independent of "
                              "input member ordering"})
    if stable_diff_exists:
        rank_state = SUPPORTED
    elif decisive_nonconsistent:
        rank_state = REFUTED
    else:
        rank_state = INSUFFICIENT
    rank_state_note = ("population state means AT LEAST ONE canonical member "
                       "pair shows a multiplicity-adjusted stable difference "
                       "(max-T family-wise 95%); it is not a claim that the "
                       "whole ranking is stable")

    # --- Estimand 2: stable complementarity
    # The repeat-averaged plug-in H_hat is retained as a DESCRIPTIVE quantity
    # ONLY: maximizing noisy per-task estimates is upward biased by finite-R
    # selection noise, and a task bootstrap of the post-selection statistic
    # cannot remove that bias (2026-09-19 external review, counterexample:
    # all q=0.9, M=9, T=400, R=3 -> H_hat=8.83pp SUPPORTED under the old rule).
    # A scientific SUPPORTED state requires the clone-calibrated cross-fitted
    # test (ccomp_v3); without it S3 can REFUTE only in the degenerate
    # structural case H_hat = 0 exactly on every bootstrap draw (a member
    # deterministically best on every observed task), otherwise it abstains.
    with np.errstate(invalid="ignore"):
        Q = _nanmean(Y, axis=0)                     # (members, tasks) q estimates
    unidentified = np.isnan(Q)                      # cells with NO valid repeat
    unidentified_cells = [(base.member_ids[i], base.tasks[j])
                          for i, j in zip(*np.nonzero(unidentified))]
    # descriptive plug-in on observed cells (unknown cells count as 0 here;
    # this is display-only and never decides state)
    q_filled = np.where(np.isnan(Q), 0.0, Q)
    per_task_max = q_filled.max(axis=0)
    best_fixed_idx = int(np.argmax(q_filled.mean(axis=1)))
    h_plugin = float(per_task_max.mean() - q_filled[best_fixed_idx].mean())
    boots_h = []
    rng_h = np.random.default_rng(20260915)
    for _ in range(2000):
        idx = rng_h.choice(T, T, replace=True)
        boots_h.append(per_task_max[idx].mean() - q_filled[best_fixed_idx, idx].mean())
    lo_h, hi_h = float(np.min(boots_h)), float(np.max(boots_h))
    exact_zero = bool(not unidentified.any() and hi_h <= 1e-12)

    calibrated = None
    if not exact_zero and clone_by_condition is not None:
        # The calibrated test runs on complete-case tasks with its own
        # coverage gate; partially observed data therefore yields an explicit
        # INSUFFICIENT there rather than being dropped silently.
        try:
            from experiment.diagnostics.ccomp_v3 import ccomp_v3
            conds_c = sorted(clone_by_condition)
            Yc = np.stack([clone_by_condition[c].Y for c in conds_c])
            calibrated = ccomp_v3(
                Y, Yc, member_ids=base.member_ids, task_ids=base.tasks,
                n_perm=clone_n_perm, n_boot=2000)
        except Exception as exc:   # calibration failure is an abstention, never a support
            calibrated = {"state": INSUFFICIENT,
                          "reason": f"clone calibration failed: {exc!r}"}

    if exact_zero:
        comp_state = REFUTED         # structural zero is the strongest possible
        comp_reason = ("descriptive plug-in H_hat is exactly 0 on every "
                       "bootstrap draw: a member is best on every observed "
                       "task; clone calibration cannot resurrect interaction")
    elif calibrated is not None:
        comp_state = calibrated["state"]
        comp_reason = calibrated.get("reason", "")
        # Fully-unidentified (member, task) cells are not removable by the
        # complete-case coverage gate alone: even one such cell means an
        # expectation is unobserved, and SUPPORTED under informative
        # missingness would require extremal bounds that agree. Conservatively
        # downgrade to INSUFFICIENT (the bound analysis is reported alongside).
        if unidentified.any() and comp_state == SUPPORTED:
            comp_state = INSUFFICIENT
            comp_reason = (f"{len(unidentified_cells)} (member, task) cells "
                           "have no valid repeat; extremal bounds were not "
                           "both positive, so support is downgraded to "
                           "abstention under potential informative missingness")
    else:
        comp_state = INSUFFICIENT
        comp_reason = ("plug-in H_hat is a biased descriptive quantity under "
                       "finite R; a SUPPORTED state requires the clone-"
                       "calibrated cross-fitted test (no clone arm supplied)")
    return {
        "state": rank_state,
        "R": R, "shared_tasks": T,
        "condition_canonical_form": sorted(cond_canonical),
        "identity_checks": {"condition_mismatch": {}, "identity_conflicts": [],
                            "identical_repeat_pairs": []},
        "stable_ranking_note": rank_state_note,
        "estimand": {
            "stable_ranking": "pairwise same-condition accuracy difference (canonical "
                              "member-id direction); SUPPORTED iff some pair is stable "
                              "in either direction after max-T multiplicity adjustment; "
                              "permutation invariant by construction",
            "stable_complementarity": "H_stable = E_x max_h q_h(x) - max_h E_x q_h(x); "
                                      "zero iff one member is expectation-best on all "
                                      "tasks; ranking differences do not imply this. "
                                      "Scientific state requires clone-calibrated ccomp_v3.",
        },
        "stable_ranking": {"state": rank_state, "pairs": pair_reports},
        "stable_complementarity": {
            "state": comp_state,
            "descriptive_plugin": {
                "H_hat": round(h_plugin, 4),
                "H_bootstrap_range": [round(lo_h, 4), round(hi_h, 4)],
                "expectation_best_member": base.member_ids[best_fixed_idx],
                "n_unidentified_cells": int(unidentified.sum()),
                "warning": "DESCRIPTIVE ONLY: upward biased by finite-R "
                           "per-task argmax selection noise; unknown cells "
                           "counted as 0 here; never a scientific state by "
                           "itself (2026-09-19 review)"},
            "unidentified_cells": unidentified_cells[:20],
            "clone_calibrated": calibrated,
            "reason": comp_reason},
        "note": ("pairing is across same-condition repeats; cross-time/provider batches "
                 "are non_exchangeable and excluded from this estimate"),
    }


# ------------------------------------------------------ S4 pre-execution selectability

def _softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _fit_member_probs(X_dev, Y_dev, X_ev, epochs=2000, lr=0.5, n_folds=5):
    """Frozen policy core: per-member logistic P(Y_h=1 | features), trained by
    stratified n_folds cross-validation ON THE DEV SPLIT (plan 3.D): each fold
    model is TRAINED ON THE OTHER n_folds-1 FOLDS (fold_of != f) and predicts
    the eval rows; the eval prediction is the average over fold models.
    Folds are balanced over feature patterns (strata). Eval rows never enter
    fitting. Folds whose complement has no valid labels are skipped.
    """
    n_m, n_dev = Y_dev.shape[0], Y_dev.shape[1]
    probs = np.zeros((X_ev.shape[0], n_m))
    fold_rng = np.random.default_rng(20260915)
    fold_order = fold_rng.permutation(n_dev)
    # Stratified fold assignment: order rows by feature pattern (random
    # tiebreak inside a pattern), then round-robin over that order. Repeated
    # patterns (one-hot strata) spread evenly across folds; unique patterns
    # still yield balanced folds.
    groups: dict[tuple, int] = {}
    keys = [groups.setdefault(tuple(X_dev[i]), len(groups)) for i in range(n_dev)]
    order = sorted(range(n_dev), key=lambda i: (keys[i], fold_order[i]))
    fold_of = np.zeros(n_dev, dtype=int)
    for pos, i in enumerate(order):
        fold_of[i] = pos % n_folds

    def _fit_one(X_tr, y_tr):
        w = np.zeros(X_tr.shape[1])
        b0 = 0.0
        for _ in range(epochs):
            p = _sigmoid(X_tr @ w + b0)
            g = (X_tr.T @ (p - y_tr)) / max(1, len(y_tr))
            w -= lr * g
            b0 -= lr * float(np.mean(p - y_tr))
        return w, b0

    for h in range(n_m):
        y = Y_dev[h]
        if np.all(np.isnan(y)):
            continue
        valid = ~np.isnan(y)
        fold_preds, fold_count = [], 0
        for f in range(n_folds):
            tr = valid & (fold_of != f)      # train on the OTHER folds
            if not tr.any():
                continue
            w, b0 = _fit_one(X_dev[tr], y[tr])
            fold_preds.append(_sigmoid(X_ev @ w + b0))
            fold_count += 1
        if fold_count:
            probs[:, h] = np.mean(fold_preds, axis=0)
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
    ABSTAIN_EPS. Features per plan 3.D: task stratum one-hot PLUS the dev-set
    member accuracy vector (constant across tasks, one column per member).
    (Calibration removed the dev-accuracy log prior: it swamped stratum-level
    signals and duplicated dev-fixed selection; frozen for blinded.)"""
    X_dev = _feature_matrix(pop, dev_idx)
    X_ev = _feature_matrix(pop, ev_idx)
    dev_accs = _accs_rows(pop.Y[:, dev_idx])            # plan 3.D feature vector
    X_dev = np.hstack([X_dev, np.tile(dev_accs, (X_dev.shape[0], 1))])
    X_ev = np.hstack([X_ev, np.tile(dev_accs, (X_ev.shape[0], 1))])
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

    if not ev_idx:
        return {"state": INSUFFICIENT, "reason": "no held-out eval tasks"}

    choice = _policy_choices(pop, dev_idx, ev_idx)

    Y_ev = pop.Y[:, ev_idx]
    pi_acc = np.array([Y_ev[c, j] for j, c in enumerate(choice)])
    valid = ~np.isnan(pi_acc)
    pi_rate = float(np.nansum(pi_acc) / len(pi_acc))
    dev_fixed_idx = int(np.argmax(_accs_rows(pop.Y[:, dev_idx])))
    paired = pi_acc - Y_ev[dev_fixed_idx]
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
        "policy": "frozen multinomial LR on task stratum one-hot, 5-fold CV on dev "
                  "(fold-model average); "
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

    Budget gate (frozen contract): E may leave INSUFFICIENT_EVIDENCE only when
    the per-task call budget is verifiable - per-record call evidence in the
    population, or the design-by-construction exception for synthetic controls
    (Population.budget_by_construction). Otherwise E is INSUFFICIENT regardless
    of the utility interval, and this is never rendered as 'no effect'.
    """
    if not pop.has_bare or s4.get("state") in (INSUFFICIENT,) and "dev split" in s4.get("reason", ""):
        return {"state": INSUFFICIENT, "reason": "pi_Z unavailable or no bare reference",
                "minimal_missing_evidence": ["trainable dev split"]}
    # Budget verification (frozen contract, strict): per-record call evidence
    # must cover every member x task cell with finite, non-negative numeric
    # values <= BUDGET_CALLS (NaN/inf/negative/non-numeric are not verified
    # counts). An aggregate total, partial records, or malformed records do
    # NOT verify the budget; only the design-by-construction exception does.
    expected_cells = {(m, t) for m in pop.member_ids for t in pop.tasks}
    malformed = [v for v in pop.calls.values()
                 if v is None or not isinstance(v, (int, float)) or isinstance(v, bool)
                 or not np.isfinite(v) or v < 0]
    over_budget = [v for v in pop.calls.values()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)
                   and np.isfinite(v) and v > BUDGET_CALLS]
    recorded = {k for k, v in pop.calls.items()
                if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)
                                      or (np.isfinite(v) and 0 <= v <= BUDGET_CALLS))}
    if pop.budget_by_construction:
        budget_verified = True
        budget_basis = "design_by_construction (synthetic 1-call policy)"
    elif malformed:
        budget_verified = False
        budget_basis = f"malformed_call_records(n={len(malformed)})"
    elif pop.calls_status != "per_record":
        budget_verified = False
        budget_basis = f"calls_status={pop.calls_status} (not per-record evidence)"
    elif over_budget:
        budget_verified = False
        budget_basis = f"over_budget_records(max={max(over_budget)})"
    elif recorded != expected_cells:
        budget_verified = False
        budget_basis = "per_record_incomplete"
    else:
        budget_verified = True
        budget_basis = "complete per-record evidence, finite and within budget"
    if not pop.calls:
        # Distinguish "no evidence supplied by this adapter/caller" from
        # "the archive contains no call records" - never conflate the two.
        cost_evidence = {"status": pop.calls_status if pop.calls_status != "not_provided"
                         else "calls_not_provided",
                         "note": "absence of a populated calls dict is NOT evidence "
                                 "that the archive lacks call records"}
    else:
        # aggregate only VALID counts: malformed values (str, NaN, inf,
        # negative, bool, None) are excluded here and already force the
        # budget gate to INSUFFICIENT above - they must never crash this
        # summary statistic (recheck4 blocker)
        per_call = [v for v in pop.calls.values()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                    and np.isfinite(v) and v >= 0]
        cost_evidence = {"status": pop.calls_status if pop.calls_status != "not_provided"
                         else "per_record",
                         "median_calls": float(np.median(per_call)) if per_call else None}
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
    interval_state = SUPPORTED if lo > 0 else (REFUTED if hi < 0 else INSUFFICIENT)
    if not budget_verified:
        state = INSUFFICIENT
        budget_note = ("utility interval computed, but the per-task call budget "
                       "could not be verified for this population; the frozen E "
                       "contract forces INSUFFICIENT_EVIDENCE (an abstention, "
                       "not a claim of no effect)")
    else:
        state = interval_state
        budget_note = ""
    return {
        "state": state, "policy": "pi_Z single member", "budget_calls_per_task": BUDGET_CALLS,
        "lambda_harm": LAMBDA_HARM, "comparator": "dev-fixed (same budget)",
        "U": round(U, 4), "U_ci95": [round(lo, 4), round(hi, 4)],
        "budget_verified": budget_verified,
        "budget_basis": budget_basis,
        "cost_evidence": cost_evidence,
        "note": ("real dollar/token costs are not recoverable from these archives; SUPPORT "
                 "is limited to the matched 1-call budget, not billable deployment"
                 + ("; " + budget_note if budget_note else "")),
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
