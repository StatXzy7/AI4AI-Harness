"""Arm E: self-specified behavioural contracts over a generic trace DSL.

Arms C/D hand the builder a mechanism from the authors' vocabulary (repair, vote,
schema-link, ...). The obvious objection is then that any behavioural diversity in D was
INJECTED by that vocabulary rather than discovered by the builder. Arm E removes the
vocabulary and keeps only instrumentation primitives, which are unavoidable: an LLM call, an
execution, an ordering, a data dependency, a branch. No mechanism name is ever supplied.

The builder emits two artifacts: an implementation, and a CONTRACT stating what observable
execution behaviour distinguishes it from the bare baseline. The gate then checks

    declared contract  ==  observed trace behaviour

which is a different question from the one arms C/D ask. C/D verify fidelity to an
author-specified mechanism; E verifies that the builder honoured its OWN declaration.

Two admission conditions stop the contract from being gamed:

  NON-VACUITY              the contract must be violated by the bare harness. Enforced by
                           literally running it against bare.py -- a contract bare satisfies
                           describes nothing. This is the C(H) != C(H_0) condition.

  COUNTERFACTUAL           a contract claiming to branch on an execution outcome must
  DISCRIMINABILITY         actually produce different traces when that outcome is flipped.
                           Without this, "always call the model twice" impersonates
                           conditional repair.

Contract keys (the ENTIRE vocabulary the builder receives):

    min_llm_calls               int   at least this many generation calls
    min_executions              int   at least this many SQL executions
    min_distinct_samples        int   at least this many sampled candidates
    branches_on_execution       bool  control flow depends on whether execution succeeded
    carries_data_forward        bool  an earlier stage's output reaches a later stage's prompt
    final_from_last_generation  bool  the returned answer is the most recent generation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so `phase2` resolves standalone

from phase2.conformance import (BROKEN_SQL, ERR_TOKEN, FIX_A, FIX_B, LINK_A, TTHE,
                                norm, run_variant)

CONTRACT_KEYS = {
    "min_llm_calls": int,
    "min_executions": int,
    "min_distinct_samples": int,
    "branches_on_execution": bool,
    "carries_data_forward": bool,
    "final_from_last_generation": bool,
    "final_invariant_to_sample_order": bool,
}

# Paired probes. S_FAIL and S_OK differ ONLY in whether the first query executes cleanly,
# which is what makes a branch-on-execution claim falsifiable.
# TRUE counterfactual: byte-identical scripted responses, differing ONLY in whether the DB
# fails the first query. The earlier pair also changed the first response text, so a harness
# that merely returns its first answer showed a "difference" and appeared to branch -- bare
# itself passed. Holding the script fixed makes execution outcome the only varying cause.
S_FAIL = ([BROKEN_SQL, FIX_A, FIX_A, FIX_A], "broken_col")
S_OK = ([BROKEN_SQL, FIX_A, FIX_A, FIX_A], None)
S_CARRY = ([f"stage one says {LINK_A}", FIX_A, FIX_A, FIX_A], None)
# Carry probe under FAILURE. A conditional repair harness only carries data forward when
# something failed, so testing carry only in a success world makes the property unfalsifiable
# for exactly the mechanisms most likely to assert it. The marker rides on the failing query so
# a harness that echoes the previous SQL, or the error, propagates it.
S_CARRY_FAIL = ([f"SELECT broken_col FROM t1 -- {LINK_A}", FIX_A, FIX_A, FIX_A], "broken_col")
# Filter probe: the MAJORITY of candidates fails to execute. A harness whose control flow
# depends on execution outcome discards them and returns the survivor; one that ignores
# execution returns the failing majority. This detects execution-dependent selection, which
# S_FAIL/S_OK cannot see when both paths happen to converge on the same answer.
S_FILTER = ([BROKEN_SQL, BROKEN_SQL, FIX_A, FIX_A], "broken_col")

# Selection probes. Q1 and Q2 are PERMUTATIONS of the same sample multiset; Q3 changes the
# multiset. A harness that selects by content is invariant to the first and sensitive to the
# second. A harness that returns a fixed position (first or last) fails the invariance leg --
# which is how a "draw 3 samples then return candidates[0]" impostor is caught without the
# contract vocabulary ever naming voting, majority or consensus.
Q1 = [FIX_A, FIX_B, FIX_B]
Q2 = [FIX_B, FIX_B, FIX_A]
Q3 = [FIX_B, FIX_A, FIX_A]


def valid_contract(c: dict) -> tuple[bool, str]:
    if not isinstance(c, dict):
        return False, "contract is not an object"
    unknown = set(c) - set(CONTRACT_KEYS) - {"name"}
    if unknown:
        return False, f"unknown contract keys: {sorted(unknown)}"
    for k, t in CONTRACT_KEYS.items():
        if k in c and not isinstance(c[k], t):
            return False, f"{k} must be {t.__name__}"
    return True, "ok"


def observe(harness: str) -> dict:
    """Run the three probes once and reduce each trace to the observables the DSL talks about."""
    out = {}
    for tag, (resp, fail_on) in (("fail", S_FAIL), ("ok", S_OK), ("carry", S_CARRY),
                                 ("carry_fail", S_CARRY_FAIL), ("filter", S_FILTER),
                                 ("q1", (Q1, None)), ("q2", (Q2, None)), ("q3", (Q3, None))):
        r = run_variant(harness, resp, fail_on)
        llm = [s for s in r["trace"] if s["step"] == "coder_llm"]
        ex = [s for s in r["trace"] if s["step"] == "execute_sql"]
        last = llm[-1]["response"] if llm else ""
        last = last[0] if isinstance(last, list) else last
        out[tag] = {
            "crashed": bool(r["error"]),
            "n_llm": len(llm),
            "n_exec": len(ex),
            "n_samples": sum(len(s["response"]) if isinstance(s["response"], list) else 1
                             for s in llm),
            "final": r["final"],
            "final_is_last_generation": norm(r["final"]) == norm(last),
            "err_fed_back": any(ERR_TOKEN in str(s["prompt"]) for s in llm),
            "marker_fed_back": any(LINK_A in str(s["prompt"]) for s in llm),
        }
    return out


def check(contract: dict, obs: dict) -> list[tuple[str, bool, str]]:
    """Each declared property becomes one pass/fail check against the observed traces."""
    f, k, c = obs["fail"], obs["ok"], obs["carry"]
    res: list[tuple[str, bool, str]] = []

    if any(v["crashed"] for v in obs.values()):
        return [("callable", False, "harness crashed on a probe scenario")]

    if "min_llm_calls" in contract:
        n = contract["min_llm_calls"]
        ok = min(f["n_llm"], k["n_llm"]) >= n
        res.append(("min_llm_calls", ok, f"declared >={n}, observed {f['n_llm']}/{k['n_llm']}"))
    if "min_executions" in contract:
        n = contract["min_executions"]
        ok = min(f["n_exec"], k["n_exec"]) >= n
        res.append(("min_executions", ok, f"declared >={n}, observed {f['n_exec']}/{k['n_exec']}"))
    if "min_distinct_samples" in contract:
        n = contract["min_distinct_samples"]
        ok = f["n_samples"] >= n
        res.append(("min_distinct_samples", ok, f"declared >={n}, observed {f['n_samples']}"))

    if contract.get("branches_on_execution"):
        # The ONLY difference between these probes is the first execution outcome, so any
        # downstream difference must be caused by it. An unconditional second call produces
        # identical structure in both and fails here.
        #
        # Deliberately NOT conjoined with "the error text reached a later prompt". The DSL text
        # shown to the builder defines this property as control flow depending on WHETHER a
        # query executed cleanly; propagating the error STRING is a different property, and the
        # DSL already expresses that separately as carries_data_forward. Requiring both would
        # grade a stricter property than the one the builder was asked to assert, and would fail
        # a legitimate "if it failed, fall back to a different candidate" branch.
        differs = (f["n_llm"] != k["n_llm"]) or (norm(f["final"]) != norm(k["final"]))
        # Second, independent route: the majority of candidates fails to execute. Returning the
        # survivor rather than the failing majority is itself proof that control flow consulted
        # the execution outcome. Needed because S_FAIL/S_OK are blind to execution-dependent
        # FILTERING whenever both paths converge on the same answer.
        flt = obs["filter"]
        filtered = norm(flt["final"]) not in (norm(BROKEN_SQL), "")
        res.append(("branches_on_execution", bool(differs or filtered),
                    f"fail/ok {f['n_llm']}calls/{norm(f['final'])[:18]!r} vs "
                    f"{k['n_llm']}calls/{norm(k['final'])[:18]!r} (differs={differs}); "
                    f"failing-majority probe -> {norm(flt['final'])[:18]!r} (filtered={filtered})"))

    if contract.get("carries_data_forward"):
        cf = obs["carry_fail"]
        carried = c["marker_fed_back"] or cf["marker_fed_back"]
        res.append(("carries_data_forward", carried,
                    f"marker reached a later prompt (success-world={c['marker_fed_back']}, "
                    f"failure-world={cf['marker_fed_back']})"))

    if contract.get("final_invariant_to_sample_order"):
        q1, q2, q3 = obs["q1"], obs["q2"], obs["q3"]
        invariant = norm(q1["final"]) == norm(q2["final"])       # permutation of same samples
        sensitive = norm(q1["final"]) != norm(q3["final"])       # different sample multiset
        res.append(("final_invariant_to_sample_order", invariant and sensitive,
                    f"permuted->{norm(q1['final'])[:18]!r}/{norm(q2['final'])[:18]!r} "
                    f"(invariant={invariant}), changed->{norm(q3['final'])[:18]!r} "
                    f"(sensitive={sensitive})"))

    if contract.get("final_from_last_generation"):
        ok = f["final_is_last_generation"] and k["final_is_last_generation"]
        res.append(("final_from_last_generation", ok, ""))

    return res


def non_vacuous(contract: dict) -> tuple[bool, str]:
    """A contract the BARE baseline already satisfies describes no mechanism at all."""
    checks = check(contract, observe("bare"))
    if not checks:
        return False, "contract declares no observable property"
    failed = [name for name, ok, _ in checks if not ok]
    if not failed:
        return False, "bare harness satisfies the entire contract (vacuous)"
    return True, f"bare violates {failed}"


def verify(harness: str, contract: dict) -> dict:
    ok_schema, why = valid_contract(contract)
    if not ok_schema:
        return {"verdict": "E_INVALID_CONTRACT", "reason": why, "checks": []}

    ok_vac, why_vac = non_vacuous(contract)
    if not ok_vac:
        return {"verdict": "E_VACUOUS_CONTRACT", "reason": why_vac, "checks": []}

    checks = check(contract, observe(harness))
    failed = [name for name, ok, _ in checks if not ok]
    return {
        "verdict": "PASS" if not failed else "E_CONTRACT_VIOLATED",
        "reason": why_vac if not failed else f"violated {failed}",
        "checks": [{"property": n, "ok": o, "detail": d} for n, o, d in checks],
    }


# --------------------------------------------------------------------- calibration invariant
# Encoded as an executable test rather than a habit. Three classes of bug have already been
# caught here, in BOTH directions -- probes too strict (a known-good harness rejected) and
# probes too lenient (bare spuriously satisfying a property because the paired scenarios
# differed in more than one respect). `--calibrate` must pass before any arm-E generation runs.
POSITIVE = [
    ("hpc_repair", {"name": "x", "min_llm_calls": 1, "min_executions": 1,
                    "branches_on_execution": True, "carries_data_forward": True}),
    ("hpc_vote3", {"name": "x", "min_distinct_samples": 3, "branches_on_execution": True}),
    ("hpc_schema", {"name": "x", "min_llm_calls": 2, "carries_data_forward": True}),
]
NEGATIVE = [
    ("neg_uncond_twocall", {"name": "x", "min_llm_calls": 1, "min_executions": 1,
                            "branches_on_execution": True}),
    ("neg_selectfirst", {"name": "x", "min_distinct_samples": 3,
                         "final_invariant_to_sample_order": True}),
]
DISCRIMINATING = ["branches_on_execution", "carries_data_forward",
                  "final_invariant_to_sample_order"]


def calibrate(verbose: bool = True) -> bool:
    ok_all = True
    rows = []
    for h, c in POSITIVE:
        v = verify(h, c)["verdict"]
        ok = v == "PASS"
        rows.append((ok, f"known-good {h}", v, "PASS"))
        ok_all &= ok
    for h, c in NEGATIVE:
        v = verify(h, c)["verdict"]
        ok = v == "E_CONTRACT_VIOLATED"
        rows.append((ok, f"impostor {h}", v, "E_CONTRACT_VIOLATED"))
        ok_all &= ok
    v = verify("hpc_repair", {"name": "vac", "min_llm_calls": 1})["verdict"]
    ok = v == "E_VACUOUS_CONTRACT"
    rows.append((ok, "vacuous contract", v, "E_VACUOUS_CONTRACT"))
    ok_all &= ok
    # every conditional/content property must be VIOLATED by bare, or it does not discriminate
    for prop in DISCRIMINATING:
        nv, _ = non_vacuous({"name": "b", prop: True})
        rows.append((nv, f"bare violates {prop}", str(nv), "True"))
        ok_all &= nv
    if verbose:
        for ok, what, got, exp in rows:
            print(f"  {'ok  ' if ok else 'MISS'} {what:44s} {got:22s} exp {exp}")
        print(f"[calibrate] {'OK' if ok_all else 'FAILED'} ({sum(r[0] for r in rows)}/{len(rows)})")
    return ok_all


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--harness")
    ap.add_argument("--contract", help="JSON string or path")
    ap.add_argument("--calibrate", action="store_true",
                    help="run the calibration invariant and exit nonzero on failure")
    a = ap.parse_args()
    if a.calibrate:
        raise SystemExit(0 if calibrate() else 1)
    raw = Path(a.contract).read_text(encoding="utf-8") if Path(a.contract).exists() else a.contract
    print(json.dumps(verify(a.harness, json.loads(raw)), indent=2))
