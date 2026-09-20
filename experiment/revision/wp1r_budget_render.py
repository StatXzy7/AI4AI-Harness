"""Render artifacts/wp1r_20260915/budget_curves.json into a compact
common-budget ORACLE comparison table (majority aggregation is not shown:
answer formats are incompatible across arms, see sec_wp1r)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "artifacts/wp1r_20260915/budget_curves.json"
OUT = ROOT / "paper/latex/revision_budget_table.tex"

SHOW_B = (3, 9, 15, 27)


def main() -> None:
    r = json.loads(SRC.read_text(encoding="utf-8"))
    rows = {x["budget_executions_per_task"]: x for x in r["budget_rows"]}
    lines = [
        r"\begin{tabular}{@{}rcc@{}}",
        r"\toprule",
        r"budget $b$ & panel oracle & same-code oracle \\",
        r"(exec./task) & (\%) & (\%) \\",
        r"\midrule",
    ]
    for b in SHOW_B:
        x = rows[b]
        lines.append(
            f"{b} & {100*x['panel_oracle']:.2f} & "
            f"{100*x['clone_oracle_mean']:.2f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
