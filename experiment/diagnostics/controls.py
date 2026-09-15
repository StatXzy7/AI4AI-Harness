"""Synthetic control package for diagnostics validation (plan section 5, FROZEN).

v1 (frozen 2026-09-15): 8 classes x 2 independent instances = 16 controls.
v2 (same day, per external review): adds repeat-based classes C9-C12 that
exercise the S3 matched-repeat paths and the ranking-vs-complementarity
distinction that v1 (all single-shot) could not cover:
  C9  one member dominant on every task, with repeats -> stable ranking
      difference SUPPORTED but stable complementarity REFUTED (H_stable = 0);
      a dominance reading of a ranking result is the trap under test.
  C10 equal overall accuracy, opposite per-stratum skill, with repeats ->
      ranking INSUFFICIENT (no stable mean difference) but complementarity
      SUPPORTED; the mirror-image trap: average differences miss interaction.
  C11 three purported repeats where one carries a different execution
      condition -> S3 must refuse the merge (INSUFFICIENT), never SUPPORT.
  C12 three exactly identical matrices (deterministic members) -> repeated
      executions are unverifiable; S3 must abstain, never SUPPORT.

Expected A-E states are frozen below and hashed into the control manifest
BEFORE any blinded run, derived from the generating mechanisms, never from
running the diagnostics. Calibration = instance #1 of each class; blinded =
instance #2 of each class (+ auditor challenges re-executed from the frozen
spec). Reference conclusions come from the analytic generating mechanism.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np

from experiment.diagnostics.core import (INSUFFICIENT, NOT_APPLICABLE, REFUTED,
                                         SUPPORTED, Population)


@dataclass
class Control:
    cid: str
    cls: str
    instance: int
    expected: dict          # {"B": state, "D": state, ...}
    description: str
    population: Population


def _pop(Y, member_ids, tasks, dev_ids, meta=None, condition=None, has_bare=True,
         calls=None):
    return Population(
        member_ids=member_ids,
        source_hashes=[f"h{i}" for i in range(len(member_ids))],
        tasks=tasks, Y=np.array(Y, dtype=float, copy=True),
        condition=condition or {"c": "synthetic"}, has_bare=has_bare,
        dev_task_ids=dev_ids, task_meta=meta or {}, calls=calls or {},
        budget_by_construction=True)


def _task_ids(n, prefix="t"):
    return [f"{prefix}{i}" for i in range(n)]


def stable_seed(cid: str, instance: int) -> int:
    """Process-independent seed (str hash() is salted per interpreter)."""
    return int(hashlib.sha256(f"{cid}#{instance}".encode()).hexdigest()[:8], 16)


# ---- generators -------------------------------------------------------------
# Each returns a Population whose ground-truth properties follow from the
# generating mechanism (stated in the description), not from the diagnostics.

def gen_C1_common_output(seed):          # different code, identical outputs
    """Two generated members always copy bare's correctness exactly -> no
    additional coverage; D/E pre-execution selection cannot beat dev-fixed."""
    rng = np.random.default_rng(seed)
    n_dev, n_ev = 60, 120
    p = 0.6
    Y = (rng.random((4, n_dev + n_ev)) < p).astype(float)
    member_ids = ["bare", "clone_a", "clone_b", "clone_c"]
    Y[1:] = Y[0]                      # identical outcome vectors by construction
    return _pop(Y, member_ids, _task_ids(n_dev + n_ev),
                _task_ids(n_dev)[:n_dev], meta={}, has_bare=True)


def gen_C2_random_gap_no_signal(seed):   # one-shot oracle gap, no stable signal
    """Members are i.i.d. Bernoulli per task -> single-shot oracle gap exists but
    no member is predictable better than another; D must not find pre-execution
    signal (expected D: REFUTED or INSUFFICIENT, E: REFUTED/INSUFFICIENT)."""
    rng = np.random.default_rng(seed)
    n_dev, n_ev = 60, 150
    Y = (rng.random((5, n_dev + n_ev)) < 0.55).astype(float)
    return _pop(Y, ["bare", "m1", "m2", "m3", "m4"], _task_ids(n_dev + n_ev),
                _task_ids(n_dev)[:n_dev], meta={})


def gen_C3_single_dominant(seed):        # one member dominates on all tasks
    """m1 has strictly higher per-task correct probability on every task -> the
    single-shot gap changes across task strata but ONE member always wins;
    no cross-member complementarity exists (B SUPPORTED; D may select m1)."""
    rng = np.random.default_rng(seed)
    n_dev, n_ev = 60, 160
    p = 0.55 + 0.25 * (rng.random(n_dev + n_ev) > 0.5)   # strata-varying difficulty
    Y = np.empty((4, n_dev + n_ev))
    Y[0] = rng.random(n_dev + n_ev) < (p - 0.15)
    Y[1] = rng.random(n_dev + n_ev) < p                  # dominant
    Y[2] = rng.random(n_dev + n_ev) < (p - 0.20)
    Y[3] = rng.random(n_dev + n_ev) < (p - 0.10)
    meta = {t: {"stratum": "hi" if i >= n_dev else "lo"} for i, t in enumerate(_task_ids(n_dev + n_ev))}
    return _pop(Y, ["bare", "dom", "weak1", "weak2"], _task_ids(n_dev + n_ev),
                _task_ids(n_dev)[:n_dev], meta=meta)


def gen_C4_real_complementarity(seed):   # stable cross advantage, Z identifies it
    """Stratum A: member m_sql wins; stratum B: member m_text wins; both stable
    in probability. Task stratum is visible pre-execution -> D SUPPORTED and
    E SUPPORTED (1-call policy beats dev-fixed net of harm)."""
    rng = np.random.default_rng(seed)
    n_dev, n_ev = 80, 200
    n = n_dev + n_ev
    stratum = np.array(["A"] * n)
    stratum[::2] = "B"
    Y = np.empty((4, n))
    Y[0] = rng.random(n) < 0.5
    Y[1] = (rng.random(n) < np.where(stratum == "A", 0.85, 0.35)).astype(float)
    Y[2] = (rng.random(n) < np.where(stratum == "A", 0.35, 0.85)).astype(float)
    Y[3] = rng.random(n) < 0.5
    meta = {t: {"stratum": stratum[i]} for i, t in enumerate(_task_ids(n))}
    return _pop(Y, ["bare", "m_sql", "m_text", "m_flat"], _task_ids(n),
                _task_ids(n)[:n_dev], meta=meta)


def gen_C5_complementarity_unidentifiable(seed):  # hidden strata, Z insufficient
    """Same mechanism as C4 but the informative stratum is HIDDEN from Z (random
    permutation of the label column) -> real complementarity exists but
    pre-execution info cannot identify it: D/E INSUFFICIENT (abstention)."""
    rng = np.random.default_rng(seed)
    n_dev, n_ev = 80, 200
    n = n_dev + n_ev
    stratum = np.array(["A"] * n)
    stratum[::2] = "B"
    Y = np.empty((4, n))
    Y[0] = rng.random(n) < 0.5
    Y[1] = (rng.random(n) < np.where(stratum == "A", 0.85, 0.35)).astype(float)
    Y[2] = (rng.random(n) < np.where(stratum == "A", 0.35, 0.85)).astype(float)
    Y[3] = rng.random(n) < 0.5
    # Z carries NO task-level structure at all (worst-case info condition)
    return _pop(Y, ["bare", "m1", "m2", "m3"], _task_ids(n),
                _task_ids(n)[:n_dev], meta={})


def gen_C6_cost_kills_gain(seed):        # dev signal flips on eval; net utility negative
    """Stratum A members look excellent on dev (m_risky 0.9) but the mechanism
    FLIPS on eval (m_risky 0.1 on A) - realistic distribution drift. The frozen
    policy is lured: D REFUTED (pi worse than dev-fixed) and E REFUTED (net
    utility negative under lambda=1), while naive dev metrics looked fine."""
    rng = np.random.default_rng(seed)
    n_dev, n_ev = 100, 500
    n = n_dev + n_ev
    stratum = np.array(["A"] * n)
    stratum[::2] = "B"
    p_risky_A = np.where(np.arange(n) < n_dev, 0.9, 0.1)   # drift: dev 0.9 -> eval 0.1
    Y = np.vstack([
        (rng.random(n) < 0.5).astype(float),                        # bare
        (rng.random(n) < np.where(stratum == "A", p_risky_A, 0.0)).astype(float),
        (rng.random(n) < 0.55).astype(float),                       # m_steady
    ])
    meta = {t: {"stratum": stratum[i]} for i, t in enumerate(_task_ids(n))}
    return _pop(Y, ["bare", "m_risky", "m_steady"], _task_ids(n),
                _task_ids(n)[:n_dev], meta=meta)


def gen_C7_headroom_from_bestfixed_drop(seed):  # headroom inflated by weak members
    """bare is strong, all generated members weak-but-diverse -> headroom is
    positive ONLY because best-fixed fell below bare; a naive reading 'positive
    headroom => deploy a member' is the trap under test (B SUPPORTED but bare is
    best; D/E must NOT support deploying a generated member)."""
    rng = np.random.default_rng(seed)
    n_dev, n_ev = 60, 160
    n = n_dev + n_ev
    Y = np.empty((4, n))
    Y[0] = (rng.random(n) < 0.80).astype(float)      # bare strong
    Y[1] = (rng.random(n) < 0.55).astype(float)
    Y[2] = (rng.random(n) < 0.60).astype(float)
    Y[3] = (rng.random(n) < 0.58).astype(float)
    return _pop(Y, ["bare", "w1", "w2", "w3"], _task_ids(n), _task_ids(n)[:n_dev], meta={})


def gen_C8_integrity_violation(seed, mode):      # corrupted inputs (S1 must catch)
    """One mechanism, two violation modes: missing member cells, corrupted judge
    (verdict flips on 10% of cells, surfaced as judge-replay mismatches). S1/A
    must REFUTE while naive metrics look healthy."""
    rng = np.random.default_rng(seed)
    n = 120
    Y = (rng.random((3, n)) < 0.6).astype(float)
    member_ids = ["bare", "a", "b"]
    replays, dups = 0, 0
    if mode == "missing_member":
        Y[2, :30] = np.nan
    elif mode == "corrupt_judge":
        flip = rng.random((3, n)) < 0.10
        Y = np.where(flip, 1 - Y, Y)
        replays = int(flip.sum())
    pop = _pop(Y, member_ids, _task_ids(Y.shape[1]), _task_ids(24)[:24])
    pop.judge_replay_mismatches = replays
    pop.duplicate_keys = dups
    return pop


# ---- repeat-based generators (v2): S3 paths + ranking-vs-complementarity ----

def _repeat_pop(Y, member_ids, tasks, condition, repeat_index, seed,
                dev_ids=None):
    """One same-condition repeat with independent execution noise from `seed`."""
    rng = np.random.default_rng(seed + 1000 * repeat_index)
    Yr = np.array(Y, dtype=float, copy=True)
    noise = np.isnan(Yr) | (Yr < 0)          # cells marked -1 are stochastic
    if noise.any():
        Yr[noise] = (rng.random(int(noise.sum())) < 0.5).astype(float)
    return Population(
        member_ids=member_ids,
        source_hashes=[f"h{i}" for i in range(len(member_ids))],
        tasks=tasks, Y=Yr, condition=dict(condition), has_bare=True,
        dev_task_ids=dev_ids or [], task_meta={},
        calls={}, calls_status="not_provided",
        budget_by_construction=True)


_STOCH = -1.0   # sentinel: cell is stochastic Bernoulli(0.5), drawn per repeat


def gen_C9_global_dominance(seed):       # ranking != complementarity
    """dom is deterministically correct on EVERY task, a only on 30-44, bare is
    stochastic Bernoulli(0.5) per repeat. dom is expectation-best everywhere ->
    H_stable = 0 (complementarity REFUTED) even though the ranking difference
    dom-a is perfectly stable (SUPPORTED) and naive pair scanning 'finds' it.
    """
    n, n_dev = 60, 20
    tasks = _task_ids(n)
    Y = np.full((3, n), _STOCH)
    Y[0, :] = _STOCH                       # bare: stochastic per repeat
    Y[1, 30:45] = 1.0                      # a: correct on tasks 30-44 only
    Y[1, :] = np.where(Y[1] == _STOCH, 0.0, Y[1])
    Y[2, :] = 1.0                          # dom: always correct
    return {f"r{r}": _repeat_pop(Y, ["bare", "a", "dom"], tasks,
                                 {"c": "synthetic", "timeout": 60}, r, seed,
                                 dev_ids=tasks[:n_dev])
            for r in range(3)}


def gen_C10_crossover_complementarity(seed):   # equal means, real interaction
    """m_sql deterministically correct on the 30 A tasks, m_text on the 30 B
    tasks, bare stochastic. Mean accuracies are equal (0.5 vs 0.5) so no stable
    MEAN difference exists (ranking INSUFFICIENT), yet per-task expectation
    crosses: H_stable = 0.5 (complementarity SUPPORTED) and the visible stratum
    makes it selectable (D/E SUPPORTED). The dev split covers BOTH strata
    (10 A + 10 B tasks) - a single-stratum dev split could not learn routing."""
    n = 60
    tasks = _task_ids(n)
    Y = np.full((3, n), _STOCH)
    Y[0, :] = _STOCH                       # bare stochastic
    Y[1, 0:30] = 1.0                       # m_sql on A tasks
    Y[1, 30:] = 0.0
    Y[2, 0:30] = 0.0
    Y[2, 30:] = 1.0                        # m_text on B tasks
    meta = {t: {"stratum": "A" if i < 30 else "B"} for i, t in enumerate(tasks)}
    dev_ids = tasks[0:10] + tasks[30:40]   # both strata represented in dev
    pops = {}
    for r in range(3):
        p = _repeat_pop(Y, ["bare", "m_sql", "m_text"], tasks,
                        {"c": "synthetic", "timeout": 60}, r, seed,
                        dev_ids=dev_ids)
        p.task_meta = meta
        pops[f"r{r}"] = p
    return pops


def gen_C11_condition_mixing(seed):      # one 'repeat' under a different condition
    """Three matrices where the third was produced under timeout=61, not 60.
    These are different execution conditions, not matched repeats: S3 must
    refuse the merge and abstain, regardless of how clean the matrices look."""
    n, n_dev = 60, 20
    tasks = _task_ids(n)
    Y = np.zeros((3, n))
    Y[0, 0:24] = 1.0                       # bare
    Y[1, 0:36] = 1.0                       # a
    Y[2, 18:48] = 1.0                      # b (crossover with a)
    Y[2, 0:18] = 0.0
    pops = {}
    for r in range(3):
        cond = {"c": "synthetic", "timeout": 61 if r == 2 else 60}
        pops[f"r{r}"] = Population(
            member_ids=["bare", "a", "b"],
            source_hashes=[f"h{i}" for i in range(3)],
            tasks=tasks, Y=np.array(Y, dtype=float, copy=True),
            condition=cond, has_bare=True, dev_task_ids=tasks[:n_dev],
            task_meta={}, calls={}, calls_status="not_provided",
            budget_by_construction=True)
    return pops


def gen_C12_cloned_repeats(seed):        # identical matrices = unverifiable repeats
    """Three byte-identical matrices (deterministic members). Independent
    executions cannot be verified; S3 must abstain even though every other
    signal (integrity, coverage) looks healthy."""
    n, n_dev = 60, 20
    tasks = _task_ids(n)
    Y = np.zeros((3, n))
    Y[0, 48:60] = 1.0                      # bare correct on 48-59
    Y[1, 18:48] = 1.0                      # a on 18-47
    Y[2, 0:36] = 1.0                       # dom on 0-35
    pops = {}
    for r in range(3):
        pops[f"r{r}"] = Population(
            member_ids=["bare", "a", "dom"],
            source_hashes=[f"h{i}" for i in range(3)],
            tasks=tasks, Y=np.array(Y, dtype=float, copy=True),
            condition={"c": "synthetic", "timeout": 60}, has_bare=True,
            dev_task_ids=tasks[:n_dev], task_meta={}, calls={},
            calls_status="not_provided", budget_by_construction=True)
    return pops


REPEAT_CLASSES = {
    "C9": gen_C9_global_dominance,
    "C10": gen_C10_crossover_complementarity,
    "C11": gen_C11_condition_mixing,
    "C12": gen_C12_cloned_repeats,
}


# ---- frozen package ---------------------------------------------------------

# Expected states, frozen from the generating mechanisms (NOT from running the
# diagnostics). S1/A for clean controls = SUPPORTED; C = INSUFFICIENT everywhere
# in v1 classes (single-shot synthetic data has no matched repeats), likewise
# C_comp (the complementarity estimand needs repeats by definition).
_CLEAN_A = SUPPORTED
_CLEAN_C = INSUFFICIENT
CLASSES = [
    ("C1", "identical outputs, different code",
     lambda s: gen_C1_common_output(s),
     {"A": _CLEAN_A, "B": REFUTED, "C": _CLEAN_C, "C_comp": _CLEAN_C,
      "D": INSUFFICIENT, "E": INSUFFICIENT}),
    ("C2", "random one-shot gap, no pre-execution signal",
     lambda s: gen_C2_random_gap_no_signal(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "C_comp": _CLEAN_C,
      "D": INSUFFICIENT, "E": SUPPORTED}),
    ("C3", "single dominant member, strata-varying gap",
     lambda s: gen_C3_single_dominant(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "C_comp": _CLEAN_C,
      "D": REFUTED, "E": INSUFFICIENT}),
    ("C4", "stable complementarity identified by visible stratum (POSITIVE control)",
     lambda s: gen_C4_real_complementarity(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "C_comp": _CLEAN_C,
      "D": SUPPORTED, "E": SUPPORTED}),
    ("C5", "real complementarity, Z cannot identify it (abstention control)",
     lambda s: gen_C5_complementarity_unidentifiable(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "C_comp": _CLEAN_C,
      "D": REFUTED, "E": INSUFFICIENT}),
    ("C6", "dev/eval drift flips Z signal; no coverage, net utility negative",
     lambda s: gen_C6_cost_kills_gain(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "C_comp": _CLEAN_C,
      "D": REFUTED, "E": REFUTED}),
    ("C7", "headroom driven by best-fixed drop; bare remains best",
     lambda s: gen_C7_headroom_from_bestfixed_drop(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "C_comp": _CLEAN_C,
      "D": INSUFFICIENT, "E": INSUFFICIENT}),
    ("C8", "integrity violations caught by S1",
     None,   # per-instance generator mode set below
     {"A": REFUTED, "B": SUPPORTED, "C": _CLEAN_C, "C_comp": _CLEAN_C,
      "D": INSUFFICIENT, "E": INSUFFICIENT}),
    # ---- v2 repeat-based classes (S3 paths) ----
    ("C9", "global dominance with repeats: stable ranking SUPPORTED, "
           "complementarity REFUTED (H_stable = 0)",
     lambda s: gen_C9_global_dominance(s),
     {"A": _CLEAN_A, "B": REFUTED, "C": SUPPORTED, "C_comp": REFUTED,
      "D": INSUFFICIENT, "E": INSUFFICIENT}),
    ("C10", "crossover interaction with repeats: equal means (ranking "
            "INSUFFICIENT) but real complementarity SUPPORTED",
     lambda s: gen_C10_crossover_complementarity(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": INSUFFICIENT, "C_comp": SUPPORTED,
      "D": SUPPORTED, "E": SUPPORTED}),
    ("C11", "condition-mixing trap: one 'repeat' under a different timeout",
     lambda s: gen_C11_condition_mixing(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": INSUFFICIENT, "C_comp": INSUFFICIENT,
      "D": INSUFFICIENT, "E": INSUFFICIENT}),
    ("C12", "cloned-repeats trap: identical matrices, independence unverifiable",
     lambda s: gen_C12_cloned_repeats(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": INSUFFICIENT, "C_comp": INSUFFICIENT,
      "D": INSUFFICIENT, "E": INSUFFICIENT}),
]
C8_MODES = ["missing_member", "corrupt_judge"]


def build_package() -> dict:
    """Freeze all controls + expected states; return manifest dict."""
    controls = []
    for cid, desc, gen, expected in CLASSES:
        for instance in (1, 2):
            if cid == "C8":
                mode = C8_MODES[instance - 1]
                pop = gen_C8_integrity_violation(1000 + instance, mode)
                d = f"{desc} [{mode}]"
                repeats = 1
            elif cid in REPEAT_CLASSES:
                pops = REPEAT_CLASSES[cid](stable_seed(cid, instance))
                pop = pops[sorted(pops)[0]]
                d = desc
                repeats = len(pops)
            else:
                pop = gen(stable_seed(cid, instance))
                d = desc
                repeats = 1
            controls.append({
                "cid": cid, "cls": desc, "instance": instance,
                "instance_phase": "calibration" if instance == 1 else "blinded",
                "description": d,
                "expected": expected,
                "n_members": len(pop.member_ids), "n_tasks": len(pop.tasks),
                "n_repeats": repeats,
            })
    manifest = {
        "package": "diagnostics control package v2 (v1 frozen 16 + C9-C12 "
                   "repeat-based classes per the 2026-09-15 external review)",
        "n_classes": len(CLASSES), "n_controls": len(controls),
        "calibration": [c["cid"] + f"#{c['instance']}" for c in controls if c["instance_phase"] == "calibration"],
        "blinded": [c["cid"] + f"#{c['instance']}" for c in controls if c["instance_phase"] == "blinded"],
        "controls": controls,
        "notes": "expected states derive from the analytic generating mechanisms; "
                 "C2/C6/C7 D/E expectations assume the frozen 1-call policy; "
                 "auditor challenges are re-executed from the frozen spec in the "
                 "blinded phase with spec+code hash binding. v1 classes keep "
                 "their frozen expectations unchanged.",
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return manifest


def get_control(cid: str, instance: int):
    """Return a Population (single-shot classes) or {repeat_key: Population}
    (repeat-based classes C9-C12) for the given control instance."""
    if cid in REPEAT_CLASSES:
        return REPEAT_CLASSES[cid](stable_seed(cid, instance))
    for c, _, gen, _ in [(x[0], x[1], x[2], x[3]) for x in CLASSES]:
        if c == cid:
            if cid == "C8":
                return gen_C8_integrity_violation(stable_seed(cid, instance),
                                                  C8_MODES[instance - 1])
            return gen(stable_seed(cid, instance))
    raise KeyError(cid)
