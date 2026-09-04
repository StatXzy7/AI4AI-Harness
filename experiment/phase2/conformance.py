"""Harness Behavioral Conformance Suite.

Judges whether a harness ACTUALLY EXECUTES the mechanism it claims, using synthetic scenarios
only. It never looks at task performance, so using it as a generation gate cannot leak outcome
supervision into harness selection.

Method: stub the frozen solver with a scripted responder and the database with a scripted
executor, run harness.solve() on a synthetic question, then assert on SQLHarness._trace, which
records every coder_llm (system/prompt/response) and execute_sql (sql/ok/error) step in order.

PAIRED COUNTERFACTUALS. A single scripted scenario is trivially gameable: if the expected answer
is always the second response, "call twice, return the second" passes without ever reading the
error; if the voting majority is always first, "return the first candidate" passes without
voting. Every mechanism is therefore probed with several variants whose correct answer DIFFERS,
and the harness must track that difference. Concretely:

    repair    v1 first call fails  -> must return the SECOND answer
              v2 same, different fix text  -> must return THAT fix (defeats hardcoding)
              v3 first call SUCCEEDS -> must return the FIRST answer
              v3 is what separates conditional repair from an unconditional second call.

    vote      v1 majority in positions 2,3   (defeats select-first)
              v2 majority is the other value (defeats hardcoding)
              v3 majority in positions 1,2   (defeats select-last)

    twostage  v1/v2 carry different stage-1 markers; the marker must reach a later prompt and
              the matching final answer must come back (defeats hardcoding either one).

Answers are compared with exact normalized equality, never substring containment, so returning
the expected SQL plus extra text does not pass.

The taxonomy the paper reports falls out of the repair probes:

    T1  mechanism described but never executed      -> no execute_sql step at all
    T2  executed, but feedback has no causal path   -> error never reaches a later prompt
    T3  feedback lands but the answer ignores it    -> counterfactual variants do not track
    PASS                                            -> all variants track

Usage:
    python experiment/phase2/conformance.py --harness p2_D_deepseek_s0_repair --scenario repair
    python experiment/phase2/conformance.py --all --out artifacts/phase2/conformance.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TTHE = ROOT / "external" / "TTHE"
sys.path.insert(0, str(TTHE))

ERR_TOKEN = "ERRTOKEN_7Q4"
LINK_A, LINK_B = "TABLE_PICK_9Z2", "TABLE_PICK_4W8"
BROKEN_SQL = "SELECT broken_col FROM t1;"
FIX_A = "SELECT id FROM t1;"
FIX_B = "SELECT name FROM t1;"


def norm(sql: str) -> str:
    """Exact-answer comparison must not be substring containment: a harness returning the
    expected SQL plus unrelated trailing text would otherwise pass."""
    return " ".join((sql or "").split()).rstrip(";").strip().lower()


# ----------------------------------------------------------------------------- stubs


class StubDB:
    """Minimal Database look-alike with a scripted executor."""

    db_id = "conformance"

    def __init__(self, fail_on: str | None = "broken_col"):
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
        # Rows must DEPEND ON THE SQL. A voting harness that selects by majority *execution
        # result* (which is the correct, objective way to vote) is untestable against a stub
        # that returns the same rows for every query -- it degenerates to picking the first
        # candidate and would be failed for a bug it does not have. Calibration: the
        # hand-written positive controls must pass, since they are known-good implementations.
        h = hashlib.md5(norm(sql).encode("utf-8")).hexdigest()[:6]
        return {"ok": True, "rows": [(int(h, 16) % 1000, f"row_{h}")], "error": None}


class ScriptedLLM:
    """Returns responses[i] for the i-th call, repeating the last once exhausted."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls: list[dict] = []

    def __call__(self, prompt, system="", temperature=0.0, n=1, seq=0):
        i = len(self.calls)
        self.calls.append({"prompt": prompt, "system": system, "n": n, "seq": seq})
        if n > 1:
            return [self.responses[min(i + j, len(self.responses) - 1)] for j in range(n)]
        return self.responses[min(i, len(self.responses) - 1)]


# ----------------------------------------------------------------------------- variants
# (variant_id, scripted responses, db fail_on, expected final answer, stage-1 marker or None)

VARIANTS: dict[str, list[tuple]] = {
    "repair": [
        ("fail_fixA",   [BROKEN_SQL, FIX_A, FIX_A, FIX_A], "broken_col", FIX_A, None),
        ("fail_fixB",   [BROKEN_SQL, FIX_B, FIX_B, FIX_B], "broken_col", FIX_B, None),
        ("first_is_ok", [FIX_B, FIX_A, FIX_A, FIX_A],      None,         FIX_B, None),
    ],
    "vote": [
        ("maj_late_B",  [FIX_A, FIX_B, FIX_B, FIX_B], None, FIX_B, None),
        ("maj_late_A",  [FIX_B, FIX_A, FIX_A, FIX_A], None, FIX_A, None),
        ("maj_early_A", [FIX_A, FIX_A, FIX_B, FIX_A], None, FIX_A, None),
    ],
    # two-sample arbitration cannot be probed as sharply as 3-way voting; disclosed as WEAK
    "vote2": [
        ("both_A", [FIX_A, FIX_A, FIX_A], None, FIX_A, None),
        ("both_B", [FIX_B, FIX_B, FIX_B], None, FIX_B, None),
    ],
    "twostage": [
        ("marker_A", [f"Relevant tables: {LINK_A} t1", FIX_A, FIX_A, FIX_A], None, FIX_A, LINK_A),
        ("marker_B", [f"Relevant tables: {LINK_B} t1", FIX_B, FIX_B, FIX_B], None, FIX_B, LINK_B),
    ],
    "plain": [
        ("single", [FIX_A, FIX_A], None, FIX_A, None),
    ],
}

WEAK_SCENARIOS = {"vote2", "plain"}


def issubclass_safe(v) -> bool:
    from text_to_sql.harness_base import SQLHarness

    try:
        return issubclass(v, SQLHarness) and v is not SQLHarness
    except Exception:
        return False


def run_variant(harness_name: str, responses, fail_on, question="How many rows are in t1?") -> dict:
    """Run one scripted variant; return the trace and the final answer."""
    import importlib

    from text_to_sql import bridge

    llm = ScriptedLLM(responses)
    real = bridge.solver_llm
    bridge.solver_llm = llm
    try:
        mod = importlib.import_module(f"text_to_sql.agents.{harness_name}")
        importlib.reload(mod)
        cls = next(v for k, v in vars(mod).items() if isinstance(v, type) and issubclass_safe(v))
        h = cls(StubDB(fail_on=fail_on))
        final = h.solve(question) or ""
        return {"final": final, "trace": list(h._trace), "error": None}
    except Exception:
        return {"final": "", "trace": [], "error": traceback.format_exc(limit=6)}
    finally:
        bridge.solver_llm = real


def run_scenario(harness_name: str, scenario: str) -> dict:
    # A harness whose source is byte-identical to the baseline did not implement a mechanism
    # badly -- generation produced nothing at all. Calling that "T1: mechanism described but
    # never executed" overstates the taxonomy, because no mechanism was ever described.
    src = TTHE / "text_to_sql" / "agents" / f"{harness_name}.py"
    bare = TTHE / "text_to_sql" / "agents" / "bare.py"
    try:
        if harness_name != "bare" and src.read_bytes() == bare.read_bytes():
            return {"scenario": scenario, "verdict": "COPY_OF_BASELINE", "variants": [],
                    "n_llm_calls": 1, "n_execs": 0, "weak_probe": False}
    except Exception:
        pass

    variants = VARIANTS[scenario]
    runs = []
    for vid, resp, fail_on, expected, marker in variants:
        r = run_variant(harness_name, resp, fail_on)
        llm_steps = [s for s in r["trace"] if s["step"] == "coder_llm"]
        exec_steps = [s for s in r["trace"] if s["step"] == "execute_sql"]
        n_samples = sum(len(s["response"]) if isinstance(s["response"], list) else 1
                        for s in llm_steps)
        failed = [i for i, s in enumerate(r["trace"])
                  if s["step"] == "execute_sql" and not s.get("ok")]
        fed_back = bool(failed) and any(
            s["step"] == "coder_llm" and ERR_TOKEN in str(s["prompt"])
            for s in r["trace"][failed[0] + 1:])
        runs.append({
            "variant": vid,
            "crashed": bool(r["error"]),
            "error": r["error"],
            "n_llm_calls": len(llm_steps),
            "n_samples": n_samples,
            "n_execs": len(exec_steps),
            "executed": bool(exec_steps),
            "observed_failure": bool(failed),
            "feedback_in_later_prompt": fed_back,
            "marker_carried": (marker is None) or any(
                s["step"] == "coder_llm" and marker in str(s["prompt"]) for s in r["trace"]),
            "tracks_expected": norm(r["final"]) == norm(expected),
            "final": r["final"][:160],
        })

    out = {"scenario": scenario, "weak_probe": scenario in WEAK_SCENARIOS, "variants": runs,
           "n_llm_calls": runs[0]["n_llm_calls"], "n_execs": runs[0]["n_execs"]}

    if any(v["crashed"] for v in runs) and not any(v["n_llm_calls"] for v in runs):
        out["verdict"] = "INVALID_uncallable"
        out["error"] = next(v["error"] for v in runs if v["crashed"])
        return out

    tracks_all = all(v["tracks_expected"] for v in runs)

    if scenario == "plain":
        out["verdict"] = "NO_MECHANISM_declared"
    elif scenario == "repair":
        if not any(v["executed"] for v in runs):
            out["verdict"] = "T1_not_executed"
        elif not runs[0]["feedback_in_later_prompt"]:
            out["verdict"] = "T2_feedback_no_causal_path"
        elif not tracks_all:
            # names the counterfactual that broke it, so the failure is auditable
            bad = [v["variant"] for v in runs if not v["tracks_expected"]]
            out["verdict"] = "T3_ignores_feedback" if "first_is_ok" in bad else "T3_broken_implementation"
            out["failed_variants"] = bad
        else:
            out["verdict"] = "PASS"
    elif scenario in ("vote", "vote2"):
        need = 3 if scenario == "vote" else 2
        if runs[0]["n_samples"] < need:
            out["verdict"] = "T1_insufficient_samples"
        elif not tracks_all:
            out["verdict"] = "T3_selection_broken"
            out["failed_variants"] = [v["variant"] for v in runs if not v["tracks_expected"]]
        else:
            out["verdict"] = "PASS"
    else:  # twostage
        if runs[0]["n_llm_calls"] < 2:
            out["verdict"] = "T1_single_stage"
        elif not all(v["marker_carried"] for v in runs):
            out["verdict"] = "T2_stage1_output_discarded"
        elif not tracks_all:
            out["verdict"] = "T3_broken_implementation"
            out["failed_variants"] = [v["variant"] for v in runs if not v["tracks_expected"]]
        else:
            out["verdict"] = "PASS"
    return out


# ----------------------------------------------------------------------------- routing
# Explicit per-strategy contracts. Inferring a contract from a filename is how a legitimate
# single-call prompt transformation gets rejected as T1; these are declared, not guessed.
STRATEGY_CONTRACT = {
    "repair": "repair", "error_classify": "repair",
    "vote3": "vote", "two_view": "vote2",
    "schema_link": "twostage", "decompose": "twostage",
    # hint_guard and format_guard are PROMPT-LEVEL by construction: their frozen strategy text
    # permits a single call that rewrites the prompt. Holding them to a control-flow contract
    # would manufacture failures, so their declared contract is 'plain'.
    "hint_guard": "plain", "format_guard": "plain",
}

SCENARIO_RULES: list[tuple[tuple[str, ...], str]] = [
    (("plain", "bare"), "plain"),
    (("repair", "error_classify"), "repair"),
    (("two_view",), "vote2"),
    (("vote",), "vote"),
    (("hint", "format"), "plain"),
    (("schema", "link", "decompose"), "twostage"),
]


def scenario_for(name: str) -> str:
    if name in STRATEGY_CONTRACT:
        return STRATEGY_CONTRACT[name]
    for keys, sc in SCENARIO_RULES:
        if any(k in name for k in keys):
            return sc
    return "repair"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness")
    ap.add_argument("--scenario", choices=sorted(VARIANTS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pattern", default="", help="only harnesses whose name contains this")
    ap.add_argument("--out")
    a = ap.parse_args()

    agents_dir = TTHE / "text_to_sql" / "agents"
    if a.all:
        names = sorted(p.stem for p in agents_dir.glob("*.py") if p.stem != "__init__")
        if a.pattern:
            names = [n for n in names if a.pattern in n]
    else:
        names = [a.harness]

    results = {}
    for n in names:
        sc = a.scenario or scenario_for(n)
        results[n] = run_scenario(n, sc)
        r = results[n]
        flag = " (weak)" if r.get("weak_probe") else ""
        print(f"  {n:38s} [{sc:8s}] {r['verdict']:30s} calls={r['n_llm_calls']} execs={r['n_execs']}{flag}")

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
