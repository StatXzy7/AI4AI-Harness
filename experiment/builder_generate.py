"""Direct Builder: generate a diverse executable-harness population via one API call each.

Bypasses TTHE's agentic claude-CLI proposer (too slow/unreliable on Windows+paratera).
Each candidate is a complete SQLHarness subclass implementing one named strategy, written
by GLM-5.3-Flash, audited (frozen-solver + label-free) and import-checked before saving.

D_A discipline: the Builder prompt shows only the harness interface + strategy description
+ a few DEV questions WITH their schemas but WITHOUT gold SQL.

Usage (from TTHE root):  PYTHONPATH=. python ../../experiment/builder_generate.py --n 8
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
import time
from pathlib import Path

TTHE_ROOT = Path(__file__).resolve().parent.parent / "external" / "TTHE"
sys.path.insert(0, str(TTHE_ROOT))

from openai import OpenAI  # noqa: E402

AGENTS = TTHE_ROOT / "text_to_sql" / "agents"
KEY_LINE = None
for line in (Path(__file__).resolve().parent.parent / "experiment" / ".env_tthe").read_text().splitlines():
    if line.startswith("PARATERA_API_KEY="):
        KEY_LINE = line.split("=", 1)[1].strip()
CLIENT = OpenAI(base_url="https://llmapi.paratera.com/v1", api_key=KEY_LINE, timeout=300)
MODEL = "GLM-5.3-Flash"

STRATEGIES = [
    ("schema_link", "Careful schema linking: first identify the tables/columns mentioned in the "
     "question and restate them, then write the SQL against the linked subset. Single LLM call."),
    ("decompose", "Stepwise decomposition: break the question into ordered sub-questions, answer "
     "each with a small LLM call, then assemble the final SQL. Multiple LLM calls allowed."),
    ("selfverify", "Generate, then self-verify: after writing the SQL, call self.execute(sql); if it "
     "errors or returns an empty result, diagnose and rewrite up to 2 times."),
    ("vote3", "Self-consistency voting: ask the LLM for 3 independent SQL attempts (n=3, temperature "
     "0.7), execute all that parse, and return the result that executes successfully (majority on "
     "execution key if ties)."),
    ("repair_loop", "Repair loop: write SQL, execute; on error, feed the exact SQLite error message "
     "back to the LLM for a corrected query; up to 3 repair rounds."),
    ("constraint_guard", "Constraint enforcement: before writing SQL, list explicit constraints "
     "(GROUP BY needs, JOIN keys, filters, ordering) as a checklist, then write SQL that satisfies "
     "each checklist item; mention the checklist in the prompt."),
    ("hint_first", "Evidence-first: BIRD questions embed a 'Hint:' line with external knowledge. "
     "Extract and restate the hint's constraints in the prompt as hard requirements before writing SQL."),
    ("conservative", "Conservative simple-SQL bias: prefer the simplest SQL that could answer the "
     "question (avoid unnecessary JOINs/subqueries); ask the LLM to output the minimal query and a "
     "one-line justification, return the query."),
]

PROMPT_TMPL = """You are designing an executable HARNESS that wraps a FROZEN weak LLM coder for BIRD Text-to-SQL (SQLite).

The harness is a Python class:

```python
from ..harness_base import SQLHarness
from .. import bridge

class {cls_name}(SQLHarness):
    def solve(self, question: str) -> str:
        # available: self.schema (str), self.llm(prompt, system="", temperature=0.0, n=1) -> str|list[str]
        #            self.execute(sql) -> {{"ok": bool, "rows": [...], ...}}, bridge.extract_sql(text) -> str
        ...
        return final_sql_string
```

Rules:
- The frozen solver is ONLY reachable via self.llm(...). No new network clients, no imports of requests/openai.
- Never read gold answers. Only question text and execution results.
- solve() MUST return a single SQL string (no markdown fences).
- Python only; standard library imports allowed (re, json, collections).

STRATEGY to implement (follow it faithfully, this exact behavior): {strategy}

Question style examples (NO answers given):
{examples}

Write the COMPLETE Python file now. First line must be a one-sentence docstring describing the harness.
The class name MUST be exactly {cls_name}.
"""


def gen_one(idx: int, strategy_name: str, strategy: str, examples: str) -> tuple[str, str] | None:
    cls_name = f"CandH{idx:02d}{strategy_name.title().replace('_', '')}"
    prompt = PROMPT_TMPL.format(cls_name=cls_name, strategy=strategy, examples=examples)
    r = CLIENT.chat.completions.create(model=MODEL, temperature=0.6, max_tokens=8192,
                                       messages=[{"role": "user", "content": prompt}])
    text = r.choices[0].message.content or ""
    m = re.search(r"```python\s*(.*?)```", text, re.S)
    code = m.group(1) if m else text
    return cls_name, code


def audit_and_load(cls_name: str, code: str, fname: str) -> bool:
    p = AGENTS / f"{fname}.py"
    p.write_text(code, encoding="utf-8")
    # 1) TTHE's own static audit (frozen-solver + label-free rules), if importable
    try:
        sys.path.insert(0, str(TTHE_ROOT))
        import audit_harness  # noqa: E402
        rules = audit_harness.audit_file(p)
        bad = [r for r in rules if getattr(r, "rule", None) != "PARSE" and
               (getattr(r, "violation", None) or getattr(r, "ok", True) is False)]
        if bad:
            print(f"  [audit-fail] {fname}: {[(getattr(r,'rule',None), str(getattr(r,'detail',''))[:60]) for r in bad][:2]}")
            p.unlink(missing_ok=True)
            return False
    except Exception as e:
        print(f"  [audit-skip] {fname}: {repr(e)[:80]}")
    # 2) import check: module loads and exposes the class
    try:
        mod = importlib.import_module(f"text_to_sql.agents.{fname}")
        importlib.reload(mod)
        if not any(isinstance(o, type) and o.__name__ == cls_name for o in vars(mod).values()):
            raise ValueError(f"class {cls_name} not found")
    except Exception as e:
        print(f"  [reject] {fname}: {repr(e)[:120]}")
        p.unlink(missing_ok=True)
        return False
    return True


def main() -> None:
    sys.path.insert(0, str(TTHE_ROOT / "text_to_sql"))  # so audit helper paths resolve

    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-strategy", type=int, default=1)
    ap.add_argument("--run-name", default="builder1")
    args = ap.parse_args()

    dev = json.loads((TTHE_ROOT.parent / "data" / "bird" / "dev_20240627" / "dev.json")
                     .read_text(encoding="utf-8"))
    cg = [e for e in dev if e["db_id"] == "card_games"][:3]
    examples = "\n\n".join(f"Q{i+1}: {e['question']}\nHint: {e.get('evidence','')}"
                           for i, e in enumerate(cg))

    made = []
    idx = 0
    for sname, sdesc in STRATEGIES:
        for k in range(args.n_per_strategy):
            fname = f"cand_{args.run_name}_{sname}{'' if k == 0 else f'_{k}'}"
            if (AGENTS / f"{fname}.py").exists():
                print(f"[skip exists] {fname}")
                continue
            t0 = time.time()
            try:
                cls_name, code = gen_one(idx, sname, sdesc, examples)
            except Exception as e:
                print(f"  [api-fail] {sname}: {repr(e)[:120]}")
                continue
            ok = audit_and_load(cls_name, code, fname)
            print(f"[{'ok' if ok else 'REJ'}] {fname} ({time.time()-t0:.0f}s)")
            if ok:
                made.append(fname)
            idx += 1

    reg = {"run": args.run_name, "generated": made,
           "hashes": {f: hashlib.sha256((AGENTS / f'{f}.py').read_bytes()).hexdigest()[:12] for f in made}}
    print(json.dumps(reg, indent=2))


if __name__ == "__main__":
    main()
