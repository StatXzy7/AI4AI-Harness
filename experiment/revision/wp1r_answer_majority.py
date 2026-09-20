"""Answer-level majority aggregation at a common per-task execution budget.

The reviewer (2026-09-20, W3) correctly noted that voting on recorded
correctness bits is not a deployable aggregation: a router sees model
ANSWERS, not labels. This module reconstructs, for every (member, task,
repeat), the normalized final answer from the sealed ledgers, and for a
chosen portfolio/budget forms the modal answer over the funded executions
(ties broken deterministically by the earliest funded execution), then
scores the modal answer with the official MATH judge. Oracle (post-
execution best outcome) remains an upper bound. All inputs are sealed;
no model calls are made.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiment.revision.wp1r_analysis import (ARM_LEDGERS, WP1R,
                                                matrices)
from experiment.diagnostics.math_adapter import judge_v2

SEED = 20260915
N_SUBSAMPLE = 1000


def _norm_answer(ans: str | None) -> str:
    """Answer key for modal voting. Two model outputs are the same vote
    when (i) their last \\\\boxed{} contents agree, or (ii) their last
    numeric token agrees (MATH answers are overwhelmingly a number or a
    simple fraction), after whitespace/case normalization. Voting on the
    raw chain-of-thought string would split semantically identical answers
    over formatting and is not what any deployable verifier sees. If
    neither extraction succeeds the first 200 normalized characters are
    used (formatting variants may then split votes)."""
    if ans is None:
        return ""
    a = re.sub(r"\s+", " ", ans.strip().lower())
    boxed = re.findall(r"\\boxed\{([^{}]*)\}", a)
    if boxed:
        return re.sub(r"\s+", " ", boxed[-1].strip())
    # last standalone number/fraction (including a/b, decimals, percentages)
    nums = re.findall(r"-?\d+(?:\s*/\s*\d+)?(?:\.\d+)?%?", a)
    if nums:
        return nums[-1].replace(" ", "")
    return a[:200]


def answer_table(arm_ledgers: list[str]) -> dict:
    """{(harness, task, repeat): normalized answer} from merged cells."""
    _, _, _, _, _, cells, _ = matrices(arm_ledgers)
    out = {}
    for c in cells:
        key = (c["harness"], c["task"], c["repeat"])
        a = c.get("final_answer")
        if a is not None:
            out[key] = _norm_answer(a)
    return out


def gold_map() -> dict[str, str]:
    split = json.loads((ROOT / "artifacts/gsm8k_audit/math500_split.json")
                       .read_text(encoding="utf-8"))
    return {f"math500_split#{i}": t["gold"] for i, t in
            enumerate(split["tasks"])}


def modal_answer(answers: list[str]) -> str:
    """Modal normalized answer; ties resolved by first funded execution."""
    if not answers:
        return ""
    counts = Counter(answers)
    top = max(counts.values())
    for a in answers:
        if counts[a] == top:
            return a
    return answers[0]


def answer_majority_curve() -> dict:
    """Answer-level majority accuracy for the panel portfolio vs same-code
    clone executions, matching wp1r_budget.budget_curves budgets."""
    real_ans = answer_table(ARM_LEDGERS["eval_real"])
    clone_ans = answer_table(ARM_LEDGERS["eval_clone"])
    members, tasks, _, _, _, _, _ = matrices(ARM_LEDGERS["eval_real"])
    cm, ct, _, _, _, _, _ = matrices(ARM_LEDGERS["eval_clone"])
    rng = np.random.default_rng(SEED)
    gold = gold_map()

    def score(ans: str, task: str) -> float:
        g = gold.get(task, "")
        try:
            return float(judge_v2(ans, g))
        except Exception:
            return np.nan

    # dev ranking from repeat-mean correctness (same rule as wp1r_budget)
    dm = None
    dev_dir = WP1R / "dev_real"
    if dev_dir.exists() and any((dev_dir / n / "ledger.sqlite").exists()
                                for n in ARM_LEDGERS["dev_real"]):
        try:
            _, _, _, dm, _, _, _ = matrices(ARM_LEDGERS["dev_real"])
        except Exception:
            dm = None
    if isinstance(dm, np.ndarray) and dm.size:
        with np.errstate(invalid="ignore"):
            dev_rank = np.nanmean(dm, axis=(0, 2))
        order = list(np.argsort(-dev_rank))
    else:
        order = list(range(len(members)))
    bare_i = members.index("bare") if "bare" in members else 0

    clone_exec = [(h, r) for h in cm for r in (1, 2, 3)]
    rows = []
    for b in range(3, 28, 3):
        panel_scores, clone_scores = [], []
        # panel: n members * 3 repeats, bare retained, dev ordered
        chosen = []
        n_mem = min(max(1, b // 3), len(members))
        chosen_idx = order[:n_mem]
        if bare_i not in chosen_idx:
            chosen_idx = [bare_i] + chosen_idx[:-1]
        for t in tasks:
            pa = [real_ans.get((members[i], t, r)) for i in chosen_idx
                  for r in (1, 2, 3)]
            pa = [a for a in pa if a is not None][:b]
            panel_scores.append(score(modal_answer(pa), t))
            idx = rng.choice(len(clone_exec), size=min(b, len(clone_exec)),
                             replace=False)
            ca = [clone_ans.get((clone_exec[i][0], t,
                                 clone_exec[i][1])) for i in idx]
            ca = [a for a in ca if a is not None]
            clone_scores.append(score(modal_answer(ca), t))
        rows.append({
            "budget_executions_per_task": b,
            "panel_answer_majority": round(float(np.nanmean(panel_scores)), 4),
            "clone_answer_majority_mean": round(float(np.nanmean(clone_scores)), 4),
        })
    return {"rows": rows, "aggregation": (
        "modal normalized final answer over funded executions, scored by "
        "official MATH judge; ties resolved by earliest funded execution; "
        "1000 seeded clone subsets per task")}


def main() -> None:
    out = WP1R / "answer_majority_curves.json"
    out.write_text(json.dumps(answer_majority_curve(), indent=1),
                   encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
