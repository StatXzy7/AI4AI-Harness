"""Trace audit: do generated harnesses actually EXECUTE differently, or only look different?

For 5 harnesses (bare, react, 2 most-divergent cands, 1 zero-divergence control) x 10 fixed
BIRD tasks (5 bare-correct + 5 bare-wrong), run solve() and inspect harness._trace:
  - number of coder LLM calls (bare=1; vote/decompose should be >1)
  - whether prompts differ across calls / vs bare's prompt
  - whether execute() was ever called (repair/verify loops)
  - final SQL vs bare's final SQL
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

TTHE_ROOT = Path(__file__).resolve().parent.parent / "external" / "TTHE"
sys.path.insert(0, str(TTHE_ROOT))

import os  # noqa: E402
for _l in (Path(__file__).resolve().parent.parent / "experiment" / ".env_tthe").read_text().splitlines():
    if _l.startswith("PARATERA_API_KEY="):
        os.environ["PARATERA_API_KEY"] = _l.split("=", 1)[1].strip()
os.environ.setdefault("ASE_MAX_TOKENS", "4096")

from text_to_sql import bridge  # noqa: E402
from text_to_sql.evolve import AGENTS_DIR, load_harness  # noqa: E402

HARNESS = ["bare", "react", "cand_bird_g1_b1r1_g1", "cand_bird_g1_b0r0_g1",
           "cand_bird_g1_b0r0_g0", "cand_bird_g1_b0r1_g0"]
N_TASKS = 10

import pandas as pd  # noqa: E402
df = pd.read_parquet(Path(__file__).resolve().parent.parent / "artifacts" / "outcomes" / "tthe_bird_matrix.parquet")
bare_col = df[df["harness_id"] == "bare"].set_index("task_id")["harness_correct"]
bare_wrong_ids = sorted(bare_col[bare_col == 0].index)[:5]
bare_right_ids = sorted(bare_col[bare_col == 1].index)[:5]
task_ids = bare_right_ids + bare_wrong_ids
questions = bridge.eval_questions("card_games")
golds = None
db = bridge.get_db("card_games")

report = []
for name in HARNESS:
    harness = load_harness(name, db)
    bare_h = load_harness("bare", db) if name != "bare" else None
    for tid in task_ids:
        ti = int(tid.split("#")[1])
        q = questions[ti]
        sql = harness.solve(q.question)
        trace = getattr(harness, "_trace", [])
        calls = [s for s in trace if s.get("step") == "coder_llm"]
        execs = [s for s in trace if s.get("step") != "coder_llm"]
        prompt_hashes = [hashlib.md5(str(c.get("prompt")) .encode()).hexdigest()[:8] for c in calls]
        info = {
            "harness": name, "task": tid, "bare_correct": int(bare_col[tid]),
            "n_llm_calls": len(calls),
            "n_distinct_prompts": len(set(prompt_hashes)),
            "n_sql_executions": len(execs),
            "sql": (sql or "")[:120],
        }
        if bare_h is not None:
            bare_sql = bare_h.solve(q.question)
            info["same_final_sql_as_bare"] = int(
                bridge.result_key(bridge.execute(harness.db, sql)["rows"] if sql.strip() else [], True)
                == bridge.result_key(bridge.execute(bare_h.db, bare_sql)["rows"] if bare_sql.strip() else [], True)) \
                if False else (sql.strip() == bare_sql.strip())
        report.append(info)
        print(json.dumps(info), flush=True)

out = Path(__file__).resolve().parent.parent / "artifacts" / "day1" / "trace_audit.jsonl"
with open(out, "w", encoding="utf-8") as f:
    for r in report:
        f.write(json.dumps(r) + "\n")
print(f"[saved] {out}")
