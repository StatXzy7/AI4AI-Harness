"""Phase-II harness generation: the 2x2 factorial plus a builder-discovery arm.

    Factor S  strategy forcing   S=1 a named mechanism is assigned; S=0 the builder invents one
    Factor G  conformance gate   G=1 must pass phase2/conformance.py; G=0 import+smoke only

        A  S=0 G=0   free, ungated          (closest to the Phase-I "old protocol")
        B  S=0 G=1   free, gated
        C  S=1 G=0   forced, ungated
        D  S=1 G=1   forced, gated           (closest to the Phase-I "strategy-forced" protocol)
        E  builder-discovered spec, gated on the builder's OWN declaration

Arm E exists to answer the sharpest objection to Phase-I: that the behavioural diversity in
arm D was injected by the authors' choice of six mechanisms rather than produced by the
builder. In E no mechanism vocabulary is supplied -- the builder emits a structured spec
first, then implements it, and the gate checks the implementation against that self-declared
spec.

For the free arms the builder must still emit a machine-readable `# MECHANISM: <class>` line,
because a gate cannot check a mechanism that was never declared. That declaration is the
ONLY vocabulary the free arms receive, and the gate is run against whatever the builder
declared -- not against what we hoped it would build.

Smoke acceptance uses D_build questions from split_p2_dev ONLY. No arm ever sees a
split_p2_test item.
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
RETRIES = 3

# assigned mechanisms for the strategy-forced arms (C, D). Identical wording to Phase-I so the
# arms remain comparable across phases.
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

PROMPT_SPEC = """You are designing an executable HARNESS that wraps a FROZEN weak solver for Text-to-SQL.

STEP 1. Emit a mechanism specification as a JSON object in a ```json fence, with these keys:
    "name":        short identifier for your mechanism
    "stages":      ordered list of stage descriptions
    "feedback":    what observable signal (if any) flows from a later stage back to an earlier one
    "selection":   how the final answer is chosen among candidates, or null
    "stop":        the stopping condition

Design the mechanism yourself. Do not copy a textbook technique unless you judge it best.

STEP 2. Then emit the COMPLETE Python file implementing EXACTLY that specification, in a
```python fence.

{skeleton}
{declare}
Class name MUST be exactly {cls}.
"""


def extract_code(text: str) -> tuple[str, bool]:
    m = re.search(r"```python\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip(), False
    m2 = re.search(r"```python\s*(.*)", text, re.S)  # truncated: lost the closing fence
    if m2 and m2.group(1).strip():
        return m2.group(1).strip(), True
    return "", False


def declared_mechanism(code: str) -> str | None:
    m = re.search(r"^#\s*MECHANISM:\s*(\w+)", code, re.M)
    return m.group(1).lower() if m else None


def accept(fname: str, code: str, gate: bool, forced_strategy: str | None) -> tuple[bool, dict]:
    """Write the file, then: import against both dev databases -> smoke solve on a D_build
    question -> (if gated) mechanism conformance. Returns (ok, detail)."""
    from text_to_sql import bridge
    from text_to_sql.evolve import AGENTS_DIR, load_harness

    (AGENTS_DIR / f"{fname}.py").write_text(code, encoding="utf-8")
    detail: dict = {"chars": len(code)}
    try:
        for db_id in ("card_games", "formula_1"):
            load_harness(fname, bridge.get_db(db_id))
        h = load_harness(fname, bridge.get_db("card_games"))
        dev = json.loads((ROOT / "experiment" / "phase2" / "split_p2_dev.json").read_text())
        qi = dev["by_db"]["card_games"][0]          # D_build only, never a test item
        sql = h.solve(bridge.eval_questions("card_games")[qi].question)
        if not sql.strip():
            return False, {**detail, "stage": "smoke", "reason": "empty sql"}
    except Exception as e:  # noqa: BLE001
        return False, {**detail, "stage": "import_or_smoke", "reason": f"{type(e).__name__}: {e!s:.160}"}

    if not gate:
        return True, {**detail, "stage": "smoke", "reason": "ungated: import+smoke passed"}

    from phase2.conformance import run_scenario, scenario_for

    decl = declared_mechanism(code)
    if forced_strategy is not None:
        scenario = scenario_for(forced_strategy)
    elif decl in ("repair", "vote", "twostage", "plain"):
        scenario = decl
    else:
        return False, {**detail, "stage": "gate", "reason": f"no valid MECHANISM declaration (got {decl!r})"}

    res = run_scenario(fname, scenario)
    detail.update({"stage": "gate", "declared": decl, "scenario": scenario, "verdict": res["verdict"]})
    # 'plain' is a legitimate declaration but contributes no mechanism, so it cannot pass a
    # mechanism gate -- an arm whose builders all declare 'plain' has genuinely produced nothing.
    return res["verdict"] == "PASS", detail


def generate_one(client, model, fname, cls, arm, strategy, seed, gate) -> dict:
    if arm == "E":
        prompt = PROMPT_SPEC.format(skeleton=SKELETON.format(cls=cls), declare=DECLARE, cls=cls)
    elif strategy is not None:
        prompt = PROMPT_FORCED.format(skeleton=SKELETON.format(cls=cls),
                                      strategy=STRATEGIES[strategy], cls=cls)
    else:
        prompt = PROMPT_FREE.format(skeleton=SKELETON.format(cls=cls), declare=DECLARE, cls=cls)

    sysm = f"You are a harness designer. Output a complete Python file defining class {cls} exactly."
    attempts = []
    for attempt in range(1, RETRIES + 1):
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0.7, n=1, max_tokens=MAX_TOKENS, seed=seed,
                messages=[{"role": "system", "content": sysm}, {"role": "user", "content": prompt}])
            text = resp.choices[0].message.content or ""
            code, truncated = extract_code(text)
            if not code:
                attempts.append({"attempt": attempt, "stage": "extract", "ok": False,
                                 "reason": "no python fence", "secs": round(time.time() - t0, 1)})
                continue
            spec = None
            if arm == "E":
                ms = re.search(r"```json\s*(.*?)```", text, re.S)
                if ms:
                    try:
                        spec = json.loads(ms.group(1))
                    except Exception:
                        spec = {"raw": ms.group(1)[:500]}
            ok, detail = accept(fname, code, gate, strategy)
            attempts.append({"attempt": attempt, "ok": ok, "truncated": truncated,
                             "spec": spec, **detail, "secs": round(time.time() - t0, 1)})
            if ok:
                return {"harness": fname, "arm": arm, "strategy": strategy, "seed": seed,
                        "accepted": True, "attempts": attempts}
        except Exception as e:  # noqa: BLE001
            attempts.append({"attempt": attempt, "stage": "api", "ok": False,
                             "reason": repr(e)[:200], "secs": round(time.time() - t0, 1)})
    return {"harness": fname, "arm": arm, "strategy": strategy, "seed": seed,
            "accepted": False, "attempts": attempts}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--builder", required=True, choices=sorted(BUILDERS))
    ap.add_argument("--arm", required=True, choices=list("ABCDE"))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--k", type=int, default=8, help="population size for the free/discovery arms")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()

    from openai import OpenAI

    client = OpenAI(base_url=BASE_URL, api_key=os.environ["PARATERA_API_KEY"], timeout=900, max_retries=0)
    model = BUILDERS[a.builder]
    gate = a.arm in ("B", "D", "E")
    forced = a.arm in ("C", "D")

    jobs = []
    slots = list(STRATEGIES) if forced else [f"g{i}" for i in range(a.k)]
    for slot in slots:
        fname = f"p2_{a.arm}_{a.builder}_s{a.seed}_{slot}"
        cls = "P2" + fname.replace("_", " ").title().replace(" ", "")
        jobs.append((fname, cls, slot if forced else None))

    print(f"[gen] builder={a.builder}({model}) arm={a.arm} seed={a.seed} "
          f"gate={gate} forced={forced} k={len(jobs)}")

    results = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(generate_one, client, model, f, c, a.arm, s, a.seed, gate)
                for f, c, s in jobs]
        for fut in futs:
            r = fut.result()
            results.append(r)
            last = r["attempts"][-1] if r["attempts"] else {}
            print(f"  {r['harness']:38s} {'ACCEPT' if r['accepted'] else 'reject':7s} "
                  f"{last.get('verdict') or last.get('reason', '')[:52]}", flush=True)

    n_ok = sum(r["accepted"] for r in results)
    out = Path(a.log)
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"builder": a.builder, "model": model, "arm": a.arm,
                               "seed": a.seed, "gate": gate, "forced": forced,
                               "accepted": n_ok, "n": len(results), "results": results},
                              indent=1), encoding="utf-8")
    print(f"[gen] accepted {n_ok}/{len(results)} -> {out}")


if __name__ == "__main__":
    main()
