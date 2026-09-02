"""SQL Harness IR: structured spec -> deterministic compile -> HarnessBase subclass.

The spec is a dict (from Builder or human) with typed knobs:
    context:   {schema_link: none|llm_select, hint_guard: bool}
    generate:  {candidates: int>=1, temperature: float}
    execution: {execute_each: bool}
    repair:    {on_error: bool, max_rounds: int}
    selection: {type: first_ok|majority_rows|llm_judge}

The compiler emits deterministic Python — the Builder can only choose/parameterize
modules, so claimed mechanisms are in the control flow BY CONSTRUCTION.

Usage: PYTHONPATH=. python ../../experiment/harness_ir.py --spec spec.yaml --out-name c3_x
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TTHE_ROOT = Path(__file__).resolve().parent.parent / "external" / "TTHE"

TEMPLATE = '''"""IR-compiled harness: {doc} (spec: {spec_name})"""
from ..harness_base import SQLHarness
from .. import bridge
{extra_imports}

SYS = ("You are an expert Text-to-SQL system for SQLite. Output exactly one SQLite query "
       "inside a ```sql block. No commentary.")

SYS_LINK = ("You are a schema-linking expert. Given a SQLite schema and a question, list ONLY "
            "the tables and columns needed, plus join keys. Be terse.")


class {cls}(SQLHarness):
    def solve(self, question: str) -> str:
{body}
'''

BODY_CTX_SCHEMA = '''        base_prompt = f"Database schema:\\n{self.schema}\\n\\nQuestion: {question}\\n\\nWrite the SQLite query."
        link = bridge.extract_sql.__self__ if False else None  # placeholder'''

BODY = {
"ctx_plain": '''        prompt = f"Database schema:\\n{self.schema}\\n\\nQuestion: {question}\\n\\nWrite the SQLite query."''',
"ctx_link": '''        link = self.llm(f"SQLite schema:\\n{self.schema}\\n\\nQuestion: {question}\\n\\n"
                        f"List ONLY the tables/columns/join keys needed. Be terse.",
                        system=SYS_LINK, temperature=0.0)
        prompt = (f"Linked schema (authoritative):\\n{link}\\n\\nFull schema:\\n{self.schema}\\n\\n"
                  f"Question: {question}\\n\\nWrite the SQLite query.")''',
"ctx_hint": '''        base, _, hint = question.partition("Hint:")
        hint = hint.strip()
        extra = (f"\\n\\nHint (external knowledge, treat as binding constraints):\\n{hint}") if hint else ""
        prompt = f"Database schema:\\n{self.schema}\\n\\nQuestion: {base.strip()}{extra}\\n\\nWrite the SQLite query."''',
"ctx_link_hint": '''        base, _, hint = question.partition("Hint:")
        hint = hint.strip()
        extra = (f"\\n\\nHint (external knowledge, treat as binding constraints):\\n{hint}") if hint else ""
        link = self.llm(f"SQLite schema:\\n{self.schema}\\n\\nQuestion: {base.strip()}{extra}\\n\\n"
                        f"List ONLY the tables/columns/join keys needed. Be terse.",
                        system=SYS_LINK, temperature=0.0)
        prompt = (f"Linked schema (authoritative):\\n{link}\\n\\nFull schema:\\n{self.schema}\\n\\n"
                  f"Question: {base.strip()}{extra}\\n\\nWrite the SQLite query.")''',
}

GEN = '''        outs = self.llm(prompt, system=SYS, temperature={temp}, n={k})
        outs = outs if isinstance(outs, list) else [outs]
        cands = [bridge.extract_sql(o) for o in outs]
        cands = [c for c in cands if c and c.strip()] or [""]'''

GEN1 = '''        out = self.llm(prompt, system=SYS, temperature={temp}, n=1)
        cands = [bridge.extract_sql(out) if isinstance(out, str) else bridge.extract_sql(out[0])]
        cands = [c for c in cands if c and c.strip()] or [""]'''

EXEC_REPAIR = '''        best, err = None, None
        for rnd in range({rounds}):
            round_cands = cands if rnd == 0 else [best]
            for c in round_cands:
                r = self.execute(c)
                if r.get("ok"):
                    return c
                err = str(r.get("error") or r)[:400]
                best = c
            if err is not None and {repair}:
                fix = self.llm(f"Database schema:\\n{{self.schema}}\\n\\nQuestion: {{question}}\\n\\n"
                               f"Your query:\\n{{best}}\\n\\nSQLite error:\\n{{err}}\\n\\n"
                               f"Write a corrected query.", system=SYS, temperature=0.0)
                best = bridge.extract_sql(fix) or best
                cands = [best]
        return cands[0] if cands else (best or "")'''

NOEXEC = '''        return cands[0]'''

SELECT_MAJ = '''        # selection: majority on executed result keys (candidates pre-filtered to successful executions)
        from collections import Counter
        ok = [(c, self.execute(c)) for c in cands]
        ok = [(c, r) for c, r in ok if r.get("ok")]
        if ok:
            keys = [bridge.result_key(r["rows"], True) for _, r in ok]
            top = Counter(keys).most_common(1)[0][0]
            for c, r in ok:
                if bridge.result_key(r["rows"], True) == top:
                    return c
        return cands[0]'''


def compile_spec(spec: dict, cls: str, doc: str, spec_name: str) -> str:
    ctx = spec.get("context", {})
    gen = spec.get("generate", {})
    exe = spec.get("execution", {})
    rep = spec.get("repair", {})
    sel = spec.get("selection", {})

    if ctx.get("schema_link") == "llm_select" and ctx.get("hint_guard"):
        ctxk = "ctx_link_hint"
    elif ctx.get("schema_link") == "llm_select":
        ctxk = "ctx_link"
    elif ctx.get("hint_guard"):
        ctxk = "ctx_hint"
    else:
        ctxk = "ctx_plain"

    k = int(gen.get("candidates", 1))
    temp = float(gen.get("temperature", 0.0))
    gk = "GEN" if k > 1 else "GEN1"
    body = [BODY[ctxk], GEN.format(temp=temp, k=k) if k > 1 else GEN1.format(temp=temp)]

    if exe.get("execute_each") or rep.get("on_error") or sel.get("type") == "majority_rows":
        body.append(EXEC_REPAIR.format(rounds=max(1, int(rep.get("max_rounds", 1))),
                                       repair="True" if rep.get("on_error") else "False"))
    elif sel.get("type") == "majority_rows":
        body.append(SELECT_MAJ)
    else:
        body.append(NOEXEC)
    return TEMPLATE.format(cls=cls, doc=doc, spec_name=spec_name,
                           extra_imports="", body="\n".join("    " + ln if ln else ln for blk in body for ln in blk.split("\n")))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="JSON spec file")
    ap.add_argument("--out-name", required=True)
    a = ap.parse_args()
    spec = json.loads((Path(__file__).resolve().parent.parent / "experiment" / a.spec).read_text())
    cls = "C" + a.out_name.replace("_", " ").title().replace(" ", "")
    code = compile_spec(spec, cls, spec.get("doc", "IR-compiled"), a.out_name)
    compile(code, a.out_name, "exec")
    p = TTHE_ROOT / "text_to_sql" / "agents" / f"{a.out_name}.py"
    p.write_text(code, encoding="utf-8")
    print(f"[compiled] {p} (class {cls})")


if __name__ == "__main__":
    main()
