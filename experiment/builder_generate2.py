"""
builder_generate2.py — Multi-builder gated free-form harness generation.

Runs on any OpenAI-compatible endpoint. Builders see D_build examples only.
Outputs TTHE-style HarnessBase subclasses saved to TTHE agents dir.
"""
import argparse, hashlib, json, os, re, sys, time
from pathlib import Path

TTHE_ROOT = Path(__file__).resolve().parent.parent / "external" / "TTHE"
sys.path.insert(0, str(TTHE_ROOT))

BUILDERS = {
    "glm":   ("https://llmapi.paratera.com/v1", os.environ.get("PARATERA_API_KEY", ""), "GLM-5.3-Flash"),
    "qwen":  ("https://llmapi.paratera.com/v1", os.environ.get("PARATERA_API_KEY_ZIYANG", ""), "Qwen3.8-Flash"),
    "dsexp": ("https://llmapi.paratera.com/v1", os.environ.get("PARATERA_API_KEY_ZIYANG", ""), "DeepSeek-V4-Flash-Vision-Exp"),
}

STRATEGIES = [
    ("repair", "Generate SQL, then EXECUTE it via self.execute(); if execution fails, feed the exact SQLite error back and regenerate up to 2 times."),
    ("vote3", "Ask the solver for 3 independent SQL attempts (n=3, temperature=0.7), execute all that parse, return the majority result."),
    ("schema_link", "First identify the tables/columns mentioned in the question, then write the SQL against the linked subset."),
    ("hint_guard", "Parse the 'Hint:' line from the question and restate its constraints as hard requirements before writing SQL."),
    ("decompose", "Break the question into ordered sub-questions, answer each with a small LLM call, then assemble the final SQL."),
    ("format_guard", "Emphasize output format and schema fidelity; require the final answer inside a ```sql fence with no extra text."),
]

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

STRATEGY (implement it faithfully): {strategy}

Write the COMPLETE Python file. First line: a one-sentence docstring describing the mechanism.
Class name MUST be exactly {cls}.
"""


def gen_one(cls, strategy):
    from openai import OpenAI
    import os
    client = OpenAI(base_url=BUILDERS["glm"][0], api_key=os.environ.get("PARATERA_API_KEY", ""))
    sysm = f"You are a harness designer. Output a complete Python file defining class {cls} exactly."
    resp = client.chat.completions.create(model="GLM-5.3-Flash", temperature=0.7, n=1,
                                          messages=[{"role": "system", "content": sysm},
                                                    {"role": "user", "content": prompt}])
    return resp.choices[0].message.content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", default="b2")
    args = ap.parse_args()
    from openai import OpenAI
    client = OpenAI(base_url=BUILDERS["glm"][0], api_key=os.environ.get("PARATERA_API_KEY", ""))
    outdir = TTHE_ROOT / "text_to_sql" / "agents"
    for k, (sname, sdesc) in enumerate(STRATEGIES):
        fname = f"c2_{args.run_name}_{sname}"
        cls = "C" + fname.replace("_", " ").title().replace(" ", "")
        prompt = PROMPT.format(cls=cls, strategy=sdesc)
        t0 = time.time()
        try:
            text = gen_one(cls, sdesc)
        except Exception as e:
            print(f"[fail] {sname}: {e}")
            continue
        m = re.search(r"```python\s*(.*?)```", text, re.S)
        if not m:
            print(f"[parse-fail] {sname}: no python fence")
            continue
        code = m.group(1).strip()
        code = code.replace(f"class {cls}", f"class {cls}")  # normalize
        (outdir / f"{fname}.py").write_text(code, encoding="utf-8")
        print(f"[ok] {fname} ({time.time()-t0:.0f}s, {len(code)} chars)")
    print(json.dumps({"run": args.run_name, "outdir": str(outdir)}, indent=2))


if __name__ == "__main__":
    main()
