"""builder_generate3.py — Faithful, reproducible multi-builder harness generation.

Provenance note (2026-09-03): the c2_b2glm / c2_b2qwen / c2_b2dexp populations of
09-01 were produced in-session and predate this script; the committed builder_generate2.py
is a stale draft (undefined `prompt` in gen_one, hardcoded GLM) and must not be cited as
the generation tool. This script is the tool of record from 2026-09-03 onward; every
attempt (success or failure) is logged to the run JSON.

Acceptance (per candidate): code fence extracted -> file written -> import/instantiate
against BOTH databases -> smoke solve on ONE builder-visible question (D_build only,
never D_eval) returning non-empty SQL. Retries: 3 per strategy (max_tokens 16384).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

TTHE_ROOT = Path(__file__).resolve().parent.parent / "external" / "TTHE"
sys.path.insert(0, str(TTHE_ROOT))

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

PROMPT = """You are designing an executable HARNESS that wraps a FROZEN weak solver for Text-to-SQL.

The harness is a Python class:
```python
from ..harness_base import SQLHarness
from .. import bridge

class {cls}(SQLHarness):
    def solve(self, question: str) -> str:
        # self.schema: str, self.llm(prompt, system="", temperature=0.0, n=1)
        # self.execute(sql) -> {{"ok": bool, "rows": [...]}}, bridge.extract_sql(text) -> str
        ...
        return final_sql_string
```

STRATEGY (implement it faithfully, in the control flow — not only in the prompt): {strategy}

Write the COMPLETE Python file. First line: a one-sentence docstring describing the mechanism.
Class name MUST be exactly {cls}.
"""

BUILDERS = {
    "glm":   "GLM-5.3-Flash",
    "qwen":  "Qwen3.8-Flash",
    "dsexp": "DeepSeek-V4-Flash-Vision-Exp",
}
BASE_URL = "https://llmapi.paratera.com/v1"
MAX_TOKENS = 16384
RETRIES = 3


def accept(fname: str, code: str) -> tuple[bool, str]:
    """Write file, then import + smoke on one D_build question. Returns (ok, detail)."""
    from text_to_sql import bridge
    from text_to_sql.evolve import AGENTS_DIR, load_harness
    (AGENTS_DIR / f"{fname}.py").write_text(code, encoding="utf-8")
    try:
        for db_id in ("card_games", "formula_1"):
            load_harness(fname, bridge.get_db(db_id))
        h = load_harness(fname, bridge.get_db("card_games"))
        build_id = json.loads((Path(__file__).parent / "split_eval151.json").read_text())["build_ids"][0]
        q = bridge.eval_questions("card_games")[build_id]
        sql = h.solve(q.question)
        if not sql.strip():
            return False, "smoke solve returned empty sql"
        return True, f"smoke ok ({len(sql)} chars)"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e!s:.160}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--builder", required=True, choices=BUILDERS)
    ap.add_argument("--strategies", required=True, help="comma-separated from: " + ",".join(STRATEGIES))
    ap.add_argument("--run-name", required=True, help="e.g. b2qwen -> files c2_b2qwen_<strategy>.py")
    ap.add_argument("--log", required=True, help="output JSON path for per-attempt provenance")
    args = ap.parse_args()

    from openai import OpenAI
    import os
    key = os.environ.get("PARATERA_API_KEY") or os.environ.get("PARATERA_API_KEY_ZIYANG", "")
    client = OpenAI(base_url=BASE_URL, api_key=key)
    model = BUILDERS[args.builder]

    split = json.loads((Path(__file__).parent / "split_eval151.json").read_text())
    build_id = split["build_ids"][0]
    from text_to_sql import bridge
    q_build = bridge.eval_questions("card_games")[build_id].question  # D_build only

    log = {"run": args.run_name, "builder": args.builder, "model": model,
           "max_tokens": MAX_TOKENS, "retries": RETRIES, "attempts": [], "accepted": []}
    for sname in args.strategies.split(","):
        sname = sname.strip()
        fname = f"c2_{args.run_name}_{sname}"
        cls = "C" + fname.replace("_", " ").title().replace(" ", "")
        prompt = PROMPT.format(cls=cls, strategy=STRATEGIES[sname])
        sysm = f"You are a harness designer. Output a complete Python file defining class {cls} exactly."
        ok = False
        for attempt in range(1, RETRIES + 1):
            t0 = time.time()
            try:
                resp = client.chat.completions.create(
                    model=model, temperature=0.7, n=1, max_tokens=MAX_TOKENS,
                    messages=[{"role": "system", "content": sysm},
                              {"role": "user", "content": prompt}])
                text = resp.choices[0].message.content or ""
                finish = getattr(resp.choices[0], "finish_reason", None)
                m = re.search(r"```python\s*(.*?)```", text, re.S)
                truncated = False
                if not m:
                    # long generations may hit max_tokens and lose the closing fence:
                    # take everything after the opening fence, let acceptance decide
                    m2 = re.search(r"```python\s*(.*)", text, re.S)
                    if m2 and m2.group(1).strip():
                        code = m2.group(1).strip()
                        truncated = True
                    else:
                        log["attempts"].append({"strategy": sname, "attempt": attempt, "stage": "extract",
                                                "ok": False, "detail": f"no python fence (finish={finish})",
                                                "secs": round(time.time() - t0, 1)})
                        continue
                else:
                    code = m.group(1).strip()
                ok, detail = accept(fname, code)
                log["attempts"].append({"strategy": sname, "attempt": attempt, "stage": "accept",
                                        "ok": ok, "detail": detail, "chars": len(code),
                                        "truncated": truncated, "finish": finish,
                                        "secs": round(time.time() - t0, 1)})
                if ok:
                    break
            except Exception as e:  # noqa: BLE001
                log["attempts"].append({"strategy": sname, "attempt": attempt, "stage": "api",
                                        "ok": False, "detail": repr(e)[:200], "secs": round(time.time() - t0, 1)})
        if ok:
            log["accepted"].append(fname)
        print(f"[{sname}] {'ok' if ok else 'FAIL after %d attempts' % RETRIES}", flush=True)

    Path(args.log).write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(json.dumps({"accepted": log["accepted"]}, indent=1))


if __name__ == "__main__":
    main()
