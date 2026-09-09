"""Judge validation against REAL gold values (from the frozen MATH-500 split) and
REAL model outputs (from the completed bare run). No heredoc backslash mangling:
this file is written directly, and test inputs come from JSON files."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiment" / "gsm8k"))
from collect import is_correct, _norm_latex, extract_answer  # noqa: E402

split = json.loads((ROOT / "artifacts" / "gsm8k_audit" / "math500_split.json").read_text())
gold = {f"math500_split#{100 + i}": t["gold"] for i, t in enumerate(split["tasks"][100:])}

# 1. cross-field validation: pred == gold must ALWAYS be judged correct (self-consistency)
n_bad = 0
for tid, g in gold.items():
    if not is_correct(f"#### {g}", g):
        n_bad += 1
        if n_bad <= 5:
            print(f"SELF-INCONSISTENT: {g!r} vs itself -> {_norm_latex(g)!r}")
print(f"self-consistency: {len(gold) - n_bad}/{len(gold)} golds judge correct against themselves")

# 2. re-score the completed bare run
rows = [json.loads(l) for l in
        (ROOT / "artifacts" / "gsm8k_audit" / "run_bare_math500.jsonl").read_text(encoding="utf-8").splitlines()]
acc = sum(is_correct(r["final_answer"] or "", gold[r["task_id"]]) for r in rows) / len(rows)
print(f"re-scored bare acc = {acc:.4f} (initial judge: 0.835)")

# 3. remaining wrong answers: real errors vs residual judge misses
wrong = [r for r in rows if not is_correct(r["final_answer"] or "", gold[r["task_id"]])]
print(f"\n{len(wrong)} judged wrong; sample for manual inspection:")
for r in wrong[:12]:
    p = extract_answer(r["final_answer"] or "")
    print(f"  pred={p!r:30s} gold={gold[r['task_id']]!r:30s} tail={r['final_answer'][-50:]!r}")
