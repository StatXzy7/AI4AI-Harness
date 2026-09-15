"""Spec-faithful executors for the pre-committed auditor challenges (CH1, CH2).

The challenge contracts live in review-stage/astra_20260915/challenge_spec.json
(SHA256 recorded in challenge_spec.sha256). Both challenges are fully
deterministic generating rules, so they can be RE-EXECUTED under the current
diagnostics code instead of replaying a stored result file.

History note (recorded per the 2026-09-15 external review): the archived
astra_challenges_result.json was produced by an earlier, unverified challenge
implementation whose stored numbers contradict the spec they claim to execute
(e.g. CH2 best_fixed_accuracy = 0.94, unreachable under the spec's generating
rule, which forces 0.79). Re-execution from the spec under hash-bound current
code supersedes that file; the historical file is retained for provenance and
can only be used as a labeled historical replay (cli.verify-challenges).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from experiment.diagnostics.core import Population

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "review-stage/astra_20260915/challenge_spec.json"


def spec_sha256() -> str:
    return hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest()


def code_binding() -> dict:
    """Hash every diagnostics module that determines challenge outcomes, so a
    stored or transmitted result can be bound to the code that produced it."""
    import experiment.diagnostics.core as core
    import experiment.diagnostics.challenges as ch
    out = {}
    for mod in (core, ch):
        out[mod.__name__] = hashlib.sha256(
            Path(mod.__file__).read_bytes()).hexdigest()
    return out


def _pop_from_rules(Y: np.ndarray, member_ids: list[str], meta: dict,
                    dev_ids: list[str], n_total: int) -> Population:
    return Population(
        member_ids=member_ids,
        source_hashes=[f"challenge:{m}" for m in member_ids],
        tasks=[f"ch_task{i}" for i in range(n_total)],
        Y=np.asarray(Y, dtype=float),
        condition={"target": "deterministic_rule", "repeat": 0, "no_cache": False,
                   "judge": "challenge_spec"},
        has_bare=True, dev_task_ids=dev_ids, task_meta=meta, calls={},
        calls_status="not_provided")


def build_ch1() -> Population:
    """Three-way visible complementarity under severe stratum-prevalence shift.

    Spec: 4 members (bare, mA, mB, mC); 1200 tasks = 600 dev (A=480, B=90,
    C=30) then 600 eval (A=60, B=270, C=270). Per stratum, task ordinal r
    (contiguous across dev then eval; all dev counts are multiples of 10, so
    per-split or global ordinals coincide): bare Y=1 iff r%10<5; the stratum's
    winner (mA/mB/mC) Y=1 iff r%10<9; the other members Y=1 iff r%10<2.
    """
    dev_counts = {"A": 480, "B": 90, "C": 30}
    ev_counts = {"A": 60, "B": 270, "C": 270}
    strata = (["A"] * dev_counts["A"] + ["B"] * dev_counts["B"] + ["C"] * dev_counts["C"]
              + ["A"] * ev_counts["A"] + ["B"] * ev_counts["B"] + ["C"] * ev_counts["C"])
    n = len(strata)
    winners = {"A": 1, "B": 2, "C": 3}      # column index of the stratum winner
    Y = np.zeros((4, n))
    ordinal = {s: 0 for s in "ABC"}
    for j, s in enumerate(strata):
        r = ordinal[s]
        ordinal[s] += 1
        Y[0, j] = 1.0 if r % 10 < 5 else 0.0
        for m in (1, 2, 3):
            Y[m, j] = (1.0 if r % 10 < 9 else 0.0) if m == winners[s] else \
                      (1.0 if r % 10 < 2 else 0.0)
    meta = {f"ch_task{j}": {"stratum": s} for j, s in enumerate(strata)}
    dev_ids = [f"ch_task{j}" for j in range(600)]
    return _pop_from_rules(Y, ["bare", "mA", "mB", "mC"], meta, dev_ids, n)


def build_ch2() -> Population:
    """Stable visible routing with bare-correlated errors that reverse
    cost-sensitive utility.

    Spec: 3 members (bare, mA, mB); 2000 tasks = 1000 dev (800 A then 200 B)
    then 1000 eval (500 A then 500 B). A tasks: (bare, mA, mB) = (0, 1, 0).
    B tasks, first 60%: (0, 0, 1); last 40%: (1, 1, 0). The within-B subcase is
    NOT exposed as metadata.
    """
    dev = [("A", (0, 1, 0))] * 800 + [("B", (0, 0, 1))] * 120 + [("B", (1, 1, 0))] * 80
    ev = [("A", (0, 1, 0))] * 500 + [("B", (0, 0, 1))] * 300 + [("B", (1, 1, 0))] * 200
    seq = dev + ev
    n = len(seq)
    Y = np.array([rule for _, rule in seq], dtype=float).T       # (3, n)
    meta = {f"ch_task{j}": {"stratum": s} for j, (s, _) in enumerate(seq)}
    dev_ids = [f"ch_task{j}" for j in range(1000)]
    return _pop_from_rules(Y, ["bare", "mA", "mB"], meta, dev_ids, n)


BUILDERS = {"CH1": build_ch1, "CH2": build_ch2}


def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def execute_challenges(cls_runner) -> dict:
    """Run every challenge in the frozen spec with the CURRENT code.

    cls_runner: callable Population -> {"A":..., "B":..., "C":..., "D":..., "E":...}
    Returns a result dict bound to the spec hash and the diagnostics code hashes.
    """
    spec = load_spec()
    result = {
        "challenge_spec_sha256": spec_sha256(),
        "code_sha256": code_binding(),
        "execution": "re-executed from the frozen spec under the current "
                     "diagnostics code (supersedes historical replay)",
        "challenges": {},
    }
    for c in spec["challenges"]:
        cid = c["id"]
        pop = BUILDERS[cid]()
        got = cls_runner(pop)
        expected = dict(c["expected"])
        expected.setdefault("A", "SUPPORTED")
        result["challenges"][cid] = {
            "description": c["description"],
            "expected": expected,
            "got": {k: got[k] for k in expected},
            "match": {k: got[k] == expected[k] for k in expected},
            "generating_rule": c["generating_rule"],
        }
        if cid == "CH2":
            result["challenges"][cid]["analytic_reference"] = (
                "spec-forced values: oracle 1.0; best-fixed (mA, full matrix) "
                "0.79; dev-fixed (mA on eval) 0.70; pi_Z (A->mA, B->mB) 0.80; "
                "harm_P 0.20, harm_D 0.00, U -0.10 -> E REFUTED")
    return result
