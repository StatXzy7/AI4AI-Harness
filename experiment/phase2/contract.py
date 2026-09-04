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
S_FAIL = ([BROKEN_SQL, FIX_A, FIX_A, FIX_A], "broken_col")
S_OK = ([FIX_B, FIX_A, FIX_A, FIX_A], None)
S_CARRY = ([f"stage one says {LINK_A}", FIX_A, FIX_A, FIX_A], None)

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
        # the ONLY difference between the probes is the first execution outcome, so any
        # downstream difference must be caused by it. An unconditional second call produces
        # identical structure in both and fails here.
        differs = (f["n_llm"] != k["n_llm"]) or (norm(f["final"]) != norm(k["final"]))
        res.append(("branches_on_execution", bool(differs and f["err_fed_back"]),
                    f"fail-trace {f['n_llm']}calls/{norm(f['final'])[:24]!r} vs "
                    f"ok-trace {k['n_llm']}calls/{norm(k['final'])[:24]!r}, "
                    f"error_fed_back={f['err_fed_back']}"))

    if contract.get("carries_data_forward"):
        res.append(("carries_data_forward", c["marker_fed_back"],
                    "stage-1 marker reached a later prompt" if c["marker_fed_back"]
                    else "stage-1 output never reached a later prompt"))

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


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True)
    ap.add_argument("--contract", required=True, help="JSON string or path")
    a = ap.parse_args()
    raw = Path(a.contract).read_text(encoding="utf-8") if Path(a.contract).exists() else a.contract
    print(json.dumps(verify(a.harness, json.loads(raw)), indent=2))
