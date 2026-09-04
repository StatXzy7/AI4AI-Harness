"""Harness Behavioral Conformance Suite.

Judges whether a harness ACTUALLY EXECUTES the mechanism it claims, using synthetic scenarios
only. It never looks at task performance, so using it as a generation gate cannot leak outcome
supervision into harness selection -- the objection that sinks a naive "keep harnesses that score
well" gate.

Method: stub the frozen solver with a scripted responder and the database with a scripted
executor, run harness.solve() on a synthetic question, then assert on SQLHarness._trace, which
records every coder_llm (system/prompt/response) and execute_sql (sql/ok/error) step in order.

The taxonomy the paper reports falls out of three probes on the repair scenario:

    T1  mechanism described but never executed      -> no execute_sql step at all
    T2  executed, but feedback has no causal path   -> error never reaches a later prompt
    T3  real multi-turn loop, implementation broken -> feedback lands but final answer ignores it
    PASS                                            -> all three hold

Usage:
    python experiment/phase2/conformance.py --harness c2_b2dexp_repair --scenario repair
    python experiment/phase2/conformance.py --all --out artifacts/phase2/conformance.json
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TTHE = ROOT / "external" / "TTHE"
sys.path.insert(0, str(TTHE))

ERR_TOKEN = "ERRTOKEN_7Q4"
LINK_TOKEN = "TABLE_PICK_9Z2"
BROKEN_SQL = "SELECT broken_col FROM t1;"
FIXED_SQL = "SELECT id FROM t1;"

# ----------------------------------------------------------------------------- stubs


class StubDB:
    """Minimal Database look-alike with a scripted executor."""

    db_id = "conformance"

    def __init__(self, fail_on: str = "broken_col"):
        self.fail_on = fail_on
        self.schema = {
            "tables": [
                {"name": "t1", "columns": [{"name": "id", "type": "INTEGER", "pk": True},
                                           {"name": "name", "type": "TEXT", "pk": False}]},
                {"name": "t2", "columns": [{"name": "t1_id", "type": "INTEGER", "pk": False},
                                           {"name": "val", "type": "REAL", "pk": False}]},
            ],
            "foreign_keys": [{"from_table": "t2", "from_col": "t1_id", "to_table": "t1", "to_col": "id"}],
        }

    def schema_text(self):
        lines = [f"Table {t['name']}({', '.join(c['name'] for c in t['columns'])})"
                 for t in self.schema["tables"]]
        lines += [f"FK {fk['from_table']}.{fk['from_col']} -> {fk['to_table']}.{fk['to_col']}"
                  for fk in self.schema["foreign_keys"]]
        return "\n".join(lines)

    def join_graph_text(self):
        return "t2-t1"

    def text_columns(self):
        return [("t1", "name")]

    def sample_values(self, table, col, k=3):
        return ["alpha", "beta"][:k]

    def execute(self, sql, timeout=30.0, limit=20000):
        if self.fail_on and self.fail_on in (sql or ""):
            return {"ok": False, "rows": [], "error": f"no such column: {self.fail_on} [{ERR_TOKEN}]"}
        return {"ok": True, "rows": [(1, "alpha")], "error": None}


class ScriptedLLM:
    """Returns responses[i] for the i-th call, repeating the last one once exhausted."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls: list[dict] = []

    def __call__(self, prompt, system="", temperature=0.0, n=1, seq=0):
        i = len(self.calls)
        self.calls.append({"prompt": prompt, "system": system, "temperature": temperature,
                           "n": n, "seq": seq})
        pick = self.responses[min(i, len(self.responses) - 1)]
        if n > 1:
            # a voting harness asking for n samples in one call gets n scripted answers
            return [self.responses[min(i + j, len(self.responses) - 1)] for j in range(n)]
        return pick


# ----------------------------------------------------------------------------- scenarios

SCENARIOS = {
    # first answer is broken and will fail to execute; every later answer is the fix
    "repair": {"responses": [BROKEN_SQL, FIXED_SQL, FIXED_SQL, FIXED_SQL, FIXED_SQL],
               "fail_on": "broken_col"},
    # two identical answers and one different -> majority is FIXED_SQL
    "vote": {"responses": [FIXED_SQL, FIXED_SQL, "SELECT name FROM t1;", FIXED_SQL],
             "fail_on": None},
    # two-sample compare/arbitrate (two_view): needs >=2 samples, not 3
    "vote2": {"responses": [FIXED_SQL, FIXED_SQL, FIXED_SQL, FIXED_SQL],
              "fail_on": None},
    # first answer is an intermediate artifact carrying a marker that must reach a later prompt
    "twostage": {"responses": [f"Relevant tables: {LINK_TOKEN} t1", FIXED_SQL, FIXED_SQL, FIXED_SQL],
                 "fail_on": None},
    # single-shot baselines declare no mechanism -- nothing to conform to
    "plain": {"responses": [FIXED_SQL, FIXED_SQL], "fail_on": None},
}


def run_scenario(harness_name: str, scenario: str) -> dict:
    """Import the harness, run it against the scripted stubs, return probe results."""
    import importlib

    from text_to_sql import bridge

    spec = SCENARIOS[scenario]
    db = StubDB(fail_on=spec["fail_on"])
    llm = ScriptedLLM(spec["responses"])

    real_solver = bridge.solver_llm
    bridge.solver_llm = llm
    try:
        mod = importlib.import_module(f"text_to_sql.agents.{harness_name}")
        importlib.reload(mod)
        cls = next(v for k, v in vars(mod).items()
                   if isinstance(v, type) and k not in ("SQLHarness",) and issubclass_safe(v))
        h = cls(db)
        final_sql = h.solve("How many rows are in t1?")
        trace = list(h._trace)
        error = None
    except Exception:
        final_sql, trace, error = "", [], traceback.format_exc(limit=6)
    finally:
        bridge.solver_llm = real_solver

    return probe(scenario, final_sql or "", trace, llm.calls, error)


def issubclass_safe(v) -> bool:
    from text_to_sql.harness_base import SQLHarness

    try:
        return issubclass(v, SQLHarness) and v is not SQLHarness
    except Exception:
        return False


def probe(scenario: str, final_sql: str, trace: list, calls: list, error: str | None) -> dict:
    llm_steps = [s for s in trace if s["step"] == "coder_llm"]
    exec_steps = [s for s in trace if s["step"] == "execute_sql"]
    # every sample counts: n>1 in one call is still n behavioural samples
    n_samples = sum(len(s["response"]) if isinstance(s["response"], list) else 1 for s in llm_steps)

    r: dict = {
        "scenario": scenario,
        "crashed": bool(error),
        "error": error,
        "n_llm_calls": len(llm_steps),
        "n_samples": n_samples,
        "n_execs": len(exec_steps),
        "final_sql": final_sql[:200],
    }

    # a harness that will not even import is a generation failure, not a mechanism failure
    if error and not llm_steps:
        r["verdict"] = "INVALID_uncallable"
        return r

    if scenario == "plain":
        # single-shot baseline: declares no mechanism, so there is nothing to conform to
        r["verdict"] = "NO_MECHANISM_declared"
        r["single_shot"] = len(llm_steps) <= 1
        return r

    if scenario == "repair":
        failed = [i for i, s in enumerate(trace) if s["step"] == "execute_sql" and not s["ok"]]
        first_fail = failed[0] if failed else None
        fed_back = first_fail is not None and any(
            s["step"] == "coder_llm" and ERR_TOKEN in str(s["prompt"])
            for s in trace[first_fail + 1:]
        )
        r["executed"] = len(exec_steps) > 0
        r["observed_failure"] = first_fail is not None
        r["feedback_in_later_prompt"] = fed_back
        r["regenerated"] = len(llm_steps) >= 2
        r["final_is_repaired"] = FIXED_SQL.rstrip(";").lower() in final_sql.rstrip(";").lower()
        if not r["executed"]:
            r["verdict"] = "T1_not_executed"
        elif not fed_back:
            r["verdict"] = "T2_feedback_no_causal_path"
        elif not r["final_is_repaired"]:
            r["verdict"] = "T3_broken_implementation"
        else:
            r["verdict"] = "PASS"

    elif scenario in ("vote", "vote2"):
        need = 3 if scenario == "vote" else 2
        r["sampled_enough"] = n_samples >= need
        r["final_is_majority"] = FIXED_SQL.rstrip(";").lower() in final_sql.rstrip(";").lower()
        if not r["sampled_enough"]:
            r["verdict"] = "T1_insufficient_samples"
        elif not r["final_is_majority"]:
            r["verdict"] = "T3_selection_broken"
        else:
            r["verdict"] = "PASS"

    else:  # twostage: schema-link / decompose / classify -- stage 1 must reach stage 2
        carried = any(s["step"] == "coder_llm" and LINK_TOKEN in str(s["prompt"]) for s in trace)
        r["multi_stage"] = len(llm_steps) >= 2
        r["stage1_reaches_stage2"] = carried
        if len(llm_steps) < 2:
            r["verdict"] = "T1_single_stage"
        elif not carried:
            r["verdict"] = "T2_stage1_output_discarded"
        else:
            r["verdict"] = "PASS"

    return r


# ----------------------------------------------------------------------------- strategy routing

# Ordered rules: first match wins. Order matters -- a "schema_repair" harness claims a repair
# loop, which is the stronger and checkable claim, so the repair rule must precede the schema one.
SCENARIO_RULES: list[tuple[tuple[str, ...], str]] = [
    (("plain", "bare"), "plain"),
    (("repair", "error_classify"), "repair"),
    (("two_view",), "vote2"),
    (("vote",), "vote"),
    (("schema", "link"), "twostage"),
    (("hint", "format", "guard", "decompose", "classify"), "twostage"),
]


def scenario_for(name: str) -> str:
    for keys, sc in SCENARIO_RULES:
        if any(k in name for k in keys):
            return sc
    return "repair"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness")
    ap.add_argument("--scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    agents_dir = TTHE / "text_to_sql" / "agents"
    if a.all:
        names = sorted(p.stem for p in agents_dir.glob("*.py") if p.stem != "__init__")
    else:
        names = [a.harness]

    results = {}
    for n in names:
        sc = a.scenario or scenario_for(n)
        results[n] = run_scenario(n, sc)
        v = results[n]["verdict"]
        print(f"  {n:34s} [{sc:9s}] {v:32s} calls={results[n]['n_llm_calls']} execs={results[n]['n_execs']}")

    if a.out:
        p = Path(a.out)
        p = p if p.is_absolute() else ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(results, indent=2), encoding="utf-8")
        from collections import Counter

        c = Counter(r["verdict"] for r in results.values())
        print(f"\n[conformance] {len(results)} harnesses -> {dict(c)}")
        print(f"[conformance] wrote {p}")


if __name__ == "__main__":
    main()
