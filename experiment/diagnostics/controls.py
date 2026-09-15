"""Synthetic control package for diagnostics validation (plan section 5, FROZEN).

8 classes x 2 independent instances = 16 controls. Expected A-E states are frozen
below and hashed into the control manifest BEFORE any blinded run. Calibration =
instance #1 of each class; blinded = instance #2 of each class (+ auditor
challenges supplied externally). Reference conclusions come from the analytic
generating mechanism, never from the diagnostic program under test.
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
        tasks=tasks, Y=np.asarray(Y, dtype=float),
        condition=condition or {"c": "synthetic"}, has_bare=has_bare,
        dev_task_ids=dev_ids, task_meta=meta or {}, calls=calls or {})


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


# ---- frozen package ---------------------------------------------------------

# Expected states, frozen from the generating mechanisms (NOT from running the
# diagnostics). S1/A for clean controls = SUPPORTED; C = INSUFFICIENT everywhere
# (single-shot synthetic data has no matched repeats).
_CLEAN_A = SUPPORTED
_CLEAN_C = INSUFFICIENT
CLASSES = [
    ("C1", "identical outputs, different code",
     lambda s: gen_C1_common_output(s),
     {"A": _CLEAN_A, "B": REFUTED, "C": _CLEAN_C, "D": INSUFFICIENT, "E": INSUFFICIENT}),
    ("C2", "random one-shot gap, no pre-execution signal",
     lambda s: gen_C2_random_gap_no_signal(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "D": INSUFFICIENT, "E": SUPPORTED}),
    ("C3", "single dominant member, strata-varying gap",
     lambda s: gen_C3_single_dominant(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "D": REFUTED, "E": INSUFFICIENT}),
    ("C4", "stable complementarity identified by visible stratum (POSITIVE control)",
     lambda s: gen_C4_real_complementarity(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "D": SUPPORTED, "E": SUPPORTED}),
    ("C5", "real complementarity, Z cannot identify it (abstention control)",
     lambda s: gen_C5_complementarity_unidentifiable(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "D": REFUTED, "E": INSUFFICIENT}),
    ("C6", "dev/eval drift flips Z signal; no coverage, net utility negative",
     lambda s: gen_C6_cost_kills_gain(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "D": REFUTED, "E": REFUTED}),
    ("C7", "headroom driven by best-fixed drop; bare remains best",
     lambda s: gen_C7_headroom_from_bestfixed_drop(s),
     {"A": _CLEAN_A, "B": SUPPORTED, "C": _CLEAN_C, "D": INSUFFICIENT, "E": INSUFFICIENT}),
    ("C8", "integrity violations caught by S1",
     None,   # per-instance generator mode set below
     {"A": REFUTED, "B": SUPPORTED, "C": _CLEAN_C, "D": INSUFFICIENT, "E": INSUFFICIENT}),
]
C8_MODES = ["missing_member", "corrupt_judge"]


def build_package() -> dict:
    """Freeze all 16 controls + expected states; return manifest dict."""
    controls = []
    for cid, desc, gen, expected in CLASSES:
        for instance in (1, 2):
            if cid == "C8":
                mode = C8_MODES[instance - 1]
                pop = gen_C8_integrity_violation(1000 + instance, mode)
                exp = expected
                d = f"{desc} [{mode}]"
            else:
                pop = gen(stable_seed(cid, instance))
                exp = expected
                d = desc
            controls.append({
                "cid": cid, "cls": desc, "instance": instance,
                "instance_phase": "calibration" if instance == 1 else "blinded",
                "description": d,
                "expected": exp,
                "n_members": len(pop.member_ids), "n_tasks": len(pop.tasks),
            })
    manifest = {
        "package": "diagnostics control package v1 (frozen pre-run)",
        "n_classes": len(CLASSES), "n_controls": len(controls),
        "calibration": [c["cid"] + f"#{c['instance']}" for c in controls if c["instance_phase"] == "calibration"],
        "blinded": [c["cid"] + f"#{c['instance']}" for c in controls if c["instance_phase"] == "blinded"],
        "controls": controls,
        "notes": "expected states derive from the analytic generating mechanisms; "
                 "C2/C6/C7 D/E expectations assume the frozen 1-call policy; auditor "
                 "challenges are appended to the blinded set with their own frozen states.",
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return manifest


def get_control(cid: str, instance: int) -> Population:
    for c, _, gen, _ in [(x[0], x[1], x[2], x[3]) for x in CLASSES]:
        if c == cid:
            if cid == "C8":
                return gen_C8_integrity_violation(stable_seed(cid, instance),
                                                  C8_MODES[instance - 1])
            return gen(stable_seed(cid, instance))
    raise KeyError(cid)
