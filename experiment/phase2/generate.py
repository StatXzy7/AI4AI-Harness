"""Phase-II harness generation: the 2x2 factorial, plus a pre-specified open-mechanism arm.

    Factor S  strategy forcing   S=1 a named mechanism is assigned; S=0 the builder invents one
    Factor G  conformance gate   G=1 must pass the frozen conformance suite; G=0 neutral validity only

        A  S=0 G=0   free, ungated       C  S=1 G=0   forced, ungated
        B  S=0 G=1   free, gated         D  S=1 G=1   forced, gated

        E            open mechanism discovery + self-specified behavioural contract.
                     Pre-specified SECONDARY arm; deliberately NOT a fifth factorial cell,
                     because it answers a different question and must not contaminate the
                     A-D causal design.

EQUAL RAW GENERATION BUDGET. Every slot in every arm gets exactly R raw builder attempts,
with identical model, temperature and token cap. Arms differ ONLY in which of those raw
candidates is admitted:

    ungated  first candidate passing NEUTRAL VALIDITY  (parse, import, interface, produces
             non-empty SQL on a dev question) -- a check that cannot see any mechanism
    gated    first candidate passing neutral validity AND the frozen conformance suite

Without this, the gated arms would silently receive three generation attempts against the
ungated arms' one, and any improvement would be confounded with rejection sampling and extra
compute rather than attributable to the gate.

SLOT FAILURE IS FINAL. If no raw candidate in a slot is admitted, the slot stays empty and
the population is smaller. Generation is never topped up to reach K, because that would
restore the budget asymmetry through the back door. Populations are compared at matched K.

All raw candidates are retained, so generation reliability -- P(neutral valid) and
P(conformance pass) -- is reported separately from the quality of the admitted population.

Smoke acceptance uses split_p2_dev questions ONLY. No arm ever sees a split_p2_test item.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TTHE = ROOT / "external" / "TTHE"
sys.path.insert(0, str(TTHE))
sys.path.insert(0, str(ROOT / "experiment"))

BUILDERS = {
    "glm": "GLM-5.3",
    "qwen": "Qwen3.8-Max",
    "deepseek": "DeepSeek-V4-Pro",
    "kimi": "Kimi-K3",
    "minimax": "MiniMax-M3",
    "ernie": "ERNIE-5.0-Thinking-Preview",
}
BASE_URL = "https://llmapi.paratera.com/v1"
MAX_TOKENS = 16384
RAW_ATTEMPTS = 3          # identical for every arm -- see module docstring
TEMPERATURE = 0.7

STRATEGIES = {
    "repair": "Generate SQL, then EXECUTE it via self.execute(); if execution fails, feed the exact SQLite error back and regenerate up to 2 times.",
    "vote3": "Ask the solver for 3 independent SQL attempts (n=3, temperature=0.7), execute all that parse, return the majority result.",
    "schema_link": "First identify the tables/columns mentioned in the question, then write the SQL against the linked subset.",
    "hint_guard": "Parse the 'Hint:' line from the question and restate its constraints as hard requirements before writing SQL.",
    "two_view": "Write the SQL from two independent formulations (e.g. join-based and subquery-based), execute both, and return the result that is non-empty or, if both are, the first.",
    "decompose": "Break the question into ordered sub-questions, answer each with a small LLM call, then assemble the final SQL.",
    "error_classify": "Generate SQL, execute it; classify the failure (syntax / schema / semantics) and apply a strategy-specific fix for each class, up to 2 rounds.",
    "format_guard": "Emphasize output format and schema fidelity; require the final answer inside a ```sql fence with no extra text.",
}

SKELETON = """The harness is a Python class:
```python
from ..harness_base import SQLHarness
from .. import bridge

class {cls}(SQLHarness):
    def solve(self, question: str) -> str:
        # self.schema: str, self.llm(prompt, system="", temperature=0.0, n=1)
        # self.execute(sql) -> {{"ok": bool, "rows": [...], "error": str}}
        # bridge.extract_sql(text) -> str
        ...
        return final_sql_string
```
"""

# Arms A/B only. This four-way label is the minimum needed to run a gate at all, and is the
# ONLY vocabulary the free arms receive.
DECLARE = """Declare the mechanism you implemented by putting EXACTLY ONE of these lines as the
second line of the file, immediately after the docstring:

    # MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
    # MECHANISM: vote        -- you draw multiple samples and select among them
    # MECHANISM: twostage    -- an earlier LLM stage produces an artifact a later stage consumes
    # MECHANISM: plain       -- a single generation call, no control-flow mechanism

Declare what you ACTUALLY built. The declaration is checked against the execution trace.
"""

PROMPT_FORCED = """You are designing an executable HARNESS that wraps a FROZEN weak solver for Text-to-SQL.

{skeleton}
STRATEGY (implement it faithfully, in the control flow -- not only in the prompt): {strategy}

Write the COMPLETE Python file. First line: a one-sentence docstring describing the mechanism.
Class name MUST be exactly {cls}.
"""

PROMPT_FREE = """You are designing an executable HARNESS that wraps a FROZEN weak solver for Text-to-SQL.

{skeleton}
Your task: invent an improvement over a single greedy generation call, and implement it. You
choose what the improvement is -- no mechanism is prescribed. Make it a real change to the
control flow, not only a longer prompt.

{declare}
Write the COMPLETE Python file. First line: a one-sentence docstring describing the mechanism.
Class name MUST be exactly {cls}.
"""

# Arm E. No mechanism is named anywhere in this prompt -- not repair, voting, schema linking,
# critique or decomposition. The builder receives only instrumentation primitives, which are
# unavoidable in any trace-based verification, and must state its own contract in them.
PROMPT_OPEN = """You are designing an executable HARNESS that wraps a FROZEN weak solver for Text-to-SQL.

{skeleton}
Design a harness that changes the target model's solving procedure in a way you judge useful.
The design is entirely yours.

STEP 1 -- BEHAVIOURAL CONTRACT. State what observable execution behaviour makes your harness
different from a baseline that calls the model once and returns the answer. Emit a JSON object
in a ```json fence using ONLY these keys (omit any that do not apply):

    "name"                              short identifier you choose
    "min_llm_calls"        int          at least this many generation calls
    "min_executions"       int          at least this many SQL executions
    "min_distinct_samples" int          at least this many sampled candidate answers
    "branches_on_execution"      bool   your control flow depends on WHETHER a query executed cleanly
    "carries_data_forward"       bool   output of an earlier step appears in a later step's prompt
    "final_from_last_generation" bool   you return the most recent generation
    "final_invariant_to_sample_order" bool  your returned answer is unchanged if the candidate
                                            answers are permuted, but changes if the set of
                                            candidate answers changes

Two rules your contract must satisfy, both checked automatically:
  * It must be VIOLATED by the one-call baseline. A contract that baseline already satisfies
    describes nothing.
  * Any behaviour you claim is verified by flipping the relevant condition and re-running you.
    Claiming "branches_on_execution" when you always make the same calls regardless will fail.

STEP 2 -- IMPLEMENTATION. Emit the COMPLETE Python file in a ```python fence, implementing
EXACTLY the contract you declared. Class name MUST be exactly {cls}.
"""


def extract_block(text: str, lang: str) -> tuple[str, bool]:
    m = re.search(rf"```{lang}\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip(), False
    m2 = re.search(rf"```{lang}\s*(.*)", text, re.S)   # truncated: lost the closing fence
    if m2 and m2.group(1).strip():
        return m2.group(1).strip(), True
    return "", False


def declared_mechanism(code: str) -> str | None:
    m = re.search(r"^#\s*MECHANISM:\s*(\w+)", code, re.M)
    return m.group(1).lower() if m else None


def neutral_valid(fname: str, code: str) -> tuple[bool, str]:
    """Mechanism-blind validity: parse, import against both dev databases, correct interface,
    and a non-empty SQL string on one dev question. Deliberately cannot see any mechanism, so
    it is the same admission bar for gated and ungated arms."""
    from text_to_sql import bridge
    from text_to_sql.evolve import AGENTS_DIR, load_harness

    (AGENTS_DIR / f"{fname}.py").write_text(code, encoding="utf-8")
    try:
        for db_id in ("card_games", "formula_1"):
            load_harness(fname, bridge.get_db(db_id))
        h = load_harness(fname, bridge.get_db("card_games"))
        dev = json.loads((ROOT / "experiment" / "phase2" / "split_p2_dev.json").read_text())
        qi = dev["by_db"]["card_games"][0]
        sql = h.solve(bridge.eval_questions("card_games")[qi].question)
        if not (sql or "").strip():
            return False, "empty sql on dev question"
        return True, f"neutral-valid ({len(sql)} chars)"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e!s:.150}"


def mechanism_pass(fname: str, code: str, arm: str, strategy: str | None,
                   contract: dict | None) -> tuple[bool, dict]:
    """The frozen gate. Arms B/D check the declared-or-assigned mechanism; arm E checks the
    builder's own contract."""
    from phase2.conformance import run_scenario, scenario_for

    if arm == "E":
        from phase2.contract import verify

        if not contract:
            return False, {"reason": "no contract emitted"}
        r = verify(fname, contract)
        return r["verdict"] == "PASS", {"verdict": r["verdict"], "reason": r["reason"],
                                        "checks": r.get("checks", [])}

    if strategy is not None:
        scenario = scenario_for(strategy)
    else:
        decl = declared_mechanism(code)
        if decl not in ("repair", "vote", "twostage", "plain"):
            return False, {"reason": f"no valid MECHANISM declaration (got {decl!r})"}
        scenario = decl
    r = run_scenario(fname, scenario)
    return r["verdict"] == "PASS", {"verdict": r["verdict"], "scenario": scenario}


def build_prompt(arm, cls, strategy):
    sk = SKELETON.format(cls=cls)
    if arm == "E":
        return PROMPT_OPEN.format(skeleton=sk, cls=cls)
    if strategy is not None:
        return PROMPT_FORCED.format(skeleton=sk, strategy=STRATEGIES[strategy], cls=cls)
    return PROMPT_FREE.format(skeleton=sk, declare=DECLARE, cls=cls)


def run_slot(client, model, fname, cls, arm, strategy, seed, gate, raw_dir) -> dict:
    """Generate RAW_ATTEMPTS candidates, keep them all, admit the first that clears this arm's bar."""
    prompt = build_prompt(arm, cls, strategy)
    sysm = f"You are a harness designer. Output a complete Python file defining class {cls} exactly."
    attempts, admitted = [], None

    for i in range(RAW_ATTEMPTS):
        t0 = time.time()
        rec = {"attempt": i, "neutral_valid": False, "mechanism_pass": False}
        try:
            resp = client.chat.completions.create(
                model=model, temperature=TEMPERATURE, n=1, max_tokens=MAX_TOKENS,
                seed=seed * 100 + i,
                messages=[{"role": "system", "content": sysm}, {"role": "user", "content": prompt}])
            text = resp.choices[0].message.content or ""
            code, truncated = extract_block(text, "python")
            rec["truncated"] = truncated
            if not code:
                rec["reason"] = "no python fence"
                attempts.append({**rec, "secs": round(time.time() - t0, 1)})
                continue
            (raw_dir / f"{fname}_raw{i}.py").write_text(code, encoding="utf-8")

            contract = None
            if arm == "E":
                cj, _ = extract_block(text, "json")
                if cj:
                    try:
                        contract = json.loads(cj)
                    except Exception:
                        rec["reason"] = "contract is not valid JSON"
                    (raw_dir / f"{fname}_raw{i}.contract.json").write_text(cj, encoding="utf-8")
                rec["contract"] = contract

            ok_n, why_n = neutral_valid(fname, code)
            rec["neutral_valid"], rec["neutral_detail"] = ok_n, why_n
            if ok_n and gate:
                ok_m, det = mechanism_pass(fname, code, arm, strategy, contract)
                rec["mechanism_pass"], rec["mechanism_detail"] = ok_m, det
            elif ok_n:
                rec["mechanism_pass"] = None      # not evaluated: ungated arm

            admit = ok_n and (rec["mechanism_pass"] is True or not gate)
            attempts.append({**rec, "secs": round(time.time() - t0, 1)})
            if admit and admitted is None:
                admitted = {"attempt": i, "code": code, "contract": contract}
                break                              # first admissible candidate wins
        except Exception as e:  # noqa: BLE001
            attempts.append({**rec, "reason": repr(e)[:180], "secs": round(time.time() - t0, 1)})

    from text_to_sql.evolve import AGENTS_DIR

    if admitted:
        (AGENTS_DIR / f"{fname}.py").write_text(admitted["code"], encoding="utf-8")
    else:
        (AGENTS_DIR / f"{fname}.py").unlink(missing_ok=True)   # slot failure is final

    return {"harness": fname, "arm": arm, "strategy": strategy, "seed": seed,
            "admitted": admitted is not None,
            "admitted_attempt": admitted["attempt"] if admitted else None,
            "contract": admitted["contract"] if admitted else None,
            "n_raw": len(attempts),
            "n_neutral_valid": sum(1 for a in attempts if a["neutral_valid"]),
            "n_mechanism_pass": sum(1 for a in attempts if a["mechanism_pass"] is True),
            "attempts": attempts}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--builder", required=True, choices=sorted(BUILDERS))
    ap.add_argument("--arm", required=True, choices=list("ABCDE"))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--k", type=int, default=8, help="slots for the free/open arms")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()

    from openai import OpenAI

    client = OpenAI(base_url=BASE_URL, api_key=os.environ["PARATERA_API_KEY"],
                    timeout=900, max_retries=0)
    model = BUILDERS[a.builder]
    gate = a.arm in ("B", "D", "E")
    forced = a.arm in ("C", "D")

    raw_dir = ROOT / "artifacts" / "phase2" / "raw" / f"{a.arm}_{a.builder}_s{a.seed}"
    raw_dir.mkdir(parents=True, exist_ok=True)

    slots = list(STRATEGIES) if forced else [f"g{i}" for i in range(a.k)]
    jobs = []
    for slot in slots:
        fname = f"p2_{a.arm}_{a.builder}_s{a.seed}_{slot}"
        cls = "P2" + fname.replace("_", " ").title().replace(" ", "")
        jobs.append((fname, cls, slot if forced else None))

    print(f"[gen] builder={a.builder}({model}) arm={a.arm} seed={a.seed} gate={gate} "
          f"forced={forced} slots={len(jobs)} raw_budget={RAW_ATTEMPTS}/slot")

    results = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(run_slot, client, model, f, c, a.arm, s, a.seed, gate, raw_dir)
                for f, c, s in jobs]
        for fut in futs:
            r = fut.result()
            results.append(r)
            last = r["attempts"][-1] if r["attempts"] else {}
            why = (last.get("mechanism_detail") or {}).get("verdict") or last.get("reason") or ""
            print(f"  {r['harness']:40s} {'ADMIT' if r['admitted'] else 'empty':6s} "
                  f"nv={r['n_neutral_valid']}/{r['n_raw']} mech={r['n_mechanism_pass']} {str(why)[:40]}",
                  flush=True)

    K = sum(r["admitted"] for r in results)
    tot_raw = sum(r["n_raw"] for r in results)
    summary = {
        "builder": a.builder, "model": model, "arm": a.arm, "seed": a.seed,
        "gate": gate, "forced": forced, "raw_attempts_per_slot": RAW_ATTEMPTS,
        "n_slots": len(results), "K_admitted": K,
        "raw_total": tot_raw,
        "p_neutral_valid": round(sum(r["n_neutral_valid"] for r in results) / max(1, tot_raw), 4),
        "p_mechanism_pass": round(sum(r["n_mechanism_pass"] for r in results) / max(1, tot_raw), 4),
        "results": results,
    }
    out = Path(a.log)
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"[gen] K={K}/{len(results)} admitted | P(neutral valid)={summary['p_neutral_valid']} "
          f"P(mechanism pass)={summary['p_mechanism_pass']} -> {out}")


if __name__ == "__main__":
    main()
