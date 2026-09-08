"""GSM8K audit generation: mirror of phase2/generate.py for the math domain.

Mini-audit design (frozen 2026-09-08, exploratory replication probe):
  * Builders: the 6 Phase-II builders, 1 seed (s0), arm A protocol (free,
    neutral validity only) -- 8 slots each -> up to 48 harnesses.
  * The question is whether the Phase-I collapse phenomenon (code diversity
    without outcome diversity) appears in a second domain under the SIMPLE
    protocol. No factorial, no gate -- this is a replication probe.
  * Neutral validity: parse, import, correct interface, non-empty answer on
    dev questions (first 150 of the frozen split). Mechanism-blind.

Smoke acceptance uses DEV tasks ONLY (first 150); evaluation uses the last
150. See artifacts/gsm8k_audit/task_split.json.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
RAW_ATTEMPTS = 3
TEMPERATURE = 0.7
K_SLOTS = 8

AGENTS_DIR = ROOT / "experiment" / "gsm8k" / "agents"
AGENTS_DIR.mkdir(parents=True, exist_ok=True)
(AGENTS_DIR / "__init__.py").write_text("", encoding="utf-8")

SPLIT = json.loads((ROOT / "artifacts" / "gsm8k_audit" / "task_split.json").read_text())
DEV = SPLIT["tasks"][:150]

SKELETON = """The harness is a Python class:
```python
from ..harness_base import MathHarness

class {cls}(MathHarness):
    def solve(self, question: str) -> str:
        # self.llm(prompt, system="", temperature=0.0, n=1)  -- the frozen solver
        ...
        return final_answer_string
```

Domain notes: the solver answers grade-school math word problems. Its raw
replies typically end with a line like "#### 42" or "The answer is 42".
There is NO code executor in this domain: the only signals available inside
solve() are the question and the solver's own text output. Return the final
answer as a string containing the number (e.g. "42").
"""

PROMPT_FREE = """You are designing an executable HARNESS that wraps a FROZEN weak solver for
grade-school math word problems (GSM8K).

{skeleton}
Your task: invent an improvement over a single greedy generation call, and
implement it. You choose what the improvement is -- no mechanism is
prescribed. Make it a real change to the control flow, not only a longer
prompt.

Write the COMPLETE Python file. First line: a one-sentence docstring
describing the mechanism. Class name MUST be exactly {cls}.
"""


def extract_block(text: str, lang: str) -> tuple[str, bool]:
    m = re.search(rf"```{lang}\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip(), False
    m2 = re.search(rf"```{lang}\s*(.*)", text, re.S)
    if m2 and m2.group(1).strip():
        return m2.group(1).strip(), True
    return "", False


def load_harness(fname: str):
    """Import agents/<fname>.py as a module of THIS package and instantiate its
    MathHarness subclass. Agents use `from ..harness_base import MathHarness`,
    so they must be imported as gsm8k.agents.<name>, not top-level agents.<name>."""
    import gsm8k                                   # this package
    mod = importlib.import_module(f"gsm8k.agents.{fname}")
    importlib.reload(mod)
    for obj in vars(mod).values():
        if (isinstance(obj, type) and obj.__name__ != "MathHarness"
                and obj.__module__ == mod.__name__
                and "MathHarness" in [c.__name__ for c in obj.__mro__]):
            return obj()
    raise ValueError(f"no MathHarness subclass in agents/{fname}.py")


def neutral_valid(fname: str, code: str) -> tuple[bool, str]:
    """Mechanism-blind validity: parse, import, interface, non-empty answers on
    two dev questions."""
    (AGENTS_DIR / f"{fname}.py").write_text(code, encoding="utf-8")
    try:
        h = load_harness(fname)
        for ex in DEV[:2]:
            ans = h.solve(ex["question"]) or ""
            if not ans.strip():
                return False, "empty answer on dev question"
        return True, "neutral-valid"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e!s:.150}"


def run_slot(client, model, fname, cls, seed, raw_dir) -> dict:
    prompt = PROMPT_FREE.format(skeleton=SKELETON.format(cls=cls), cls=cls)
    sysm = f"You are a harness designer. Output a complete Python file defining class {cls} exactly."
    attempts, admitted = [], None

    for i in range(RAW_ATTEMPTS):
        t0 = time.time()
        rec = {"attempt": i, "neutral_valid": False}
        try:
            resp = client.chat.completions.create(
                model=model, temperature=TEMPERATURE, n=1, max_tokens=MAX_TOKENS,
                seed=seed * 100 + i,
                messages=[{"role": "system", "content": sysm},
                          {"role": "user", "content": prompt}])
            text = resp.choices[0].message.content or ""
            code, truncated = extract_block(text, "python")
            rec["truncated"] = truncated
            if not code:
                rec["reason"] = "no python fence"
                attempts.append({**rec, "secs": round(time.time() - t0, 1)})
                continue
            (raw_dir / f"{fname}_raw{i}.py").write_text(code, encoding="utf-8")

            ok_n, why_n = neutral_valid(fname, code)
            rec["neutral_valid"], rec["neutral_detail"] = ok_n, why_n
            attempts.append({**rec, "secs": round(time.time() - t0, 1)})
            if ok_n and admitted is None:
                admitted = {"attempt": i, "code": code}
                break
        except Exception as e:  # noqa: BLE001
            attempts.append({**rec, "reason": repr(e)[:180], "secs": round(time.time() - t0, 1)})

    if admitted:
        (AGENTS_DIR / f"{fname}.py").write_text(admitted["code"], encoding="utf-8")
    else:
        (AGENTS_DIR / f"{fname}.py").unlink(missing_ok=True)

    return {"harness": fname, "seed": seed, "admitted": admitted is not None,
            "admitted_attempt": admitted["attempt"] if admitted else None,
            "n_raw": len(attempts),
            "n_neutral_valid": sum(1 for a in attempts if a["neutral_valid"]),
            "attempts": attempts}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--builder", required=True, choices=sorted(BUILDERS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--k", type=int, default=K_SLOTS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()

    from openai import OpenAI

    client = OpenAI(base_url=BASE_URL, api_key=os.environ["PARATERA_API_KEY"],
                    timeout=900, max_retries=0)
    model = BUILDERS[a.builder]

    raw_dir = ROOT / "artifacts" / "gsm8k_audit" / "raw" / f"{a.builder}_s{a.seed}"
    raw_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for slot in range(a.k):
        fname = f"gsm_{a.builder}_s{a.seed}_g{slot}"
        cls = "Gsm" + fname.replace("_", " ").title().replace(" ", "")
        jobs.append((fname, cls))

    print(f"[gen] builder={a.builder}({model}) slots={len(jobs)} raw_budget={RAW_ATTEMPTS}/slot")

    results = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(run_slot, client, model, f, c, a.seed, raw_dir)
                for f, c in jobs]
        for fut in futs:
            r = fut.result()
            results.append(r)
            why = r["attempts"][-1].get("reason") or r["attempts"][-1].get("neutral_detail") or ""
            print(f"  {r['harness']:30s} {'ADMIT' if r['admitted'] else 'empty':6s} "
                  f"nv={r['n_neutral_valid']}/{r['n_raw']} {str(why)[:40]}", flush=True)

    K = sum(r["admitted"] for r in results)
    tot_raw = sum(r["n_raw"] for r in results)
    summary = {"builder": a.builder, "model": model, "seed": a.seed,
               "raw_attempts_per_slot": RAW_ATTEMPTS,
               "n_slots": len(results), "K_admitted": K, "raw_total": tot_raw,
               "R_artifact": round(sum(r["n_neutral_valid"] for r in results) / max(1, tot_raw), 4),
               "results": results}
    out = Path(a.log)
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"[gen] K={K}/{len(results)} admitted | R_artifact={summary['R_artifact']} -> {out}")


if __name__ == "__main__":
    main()
