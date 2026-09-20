"""WP-1R budget analysis under a COMMON per-task execution budget (W3).

The external review (2026-09-19) correctly distinguishes three controls
that the manuscript previously conflated under "equal budget":

  1. equal-SLOT / equal-repeat: 9 members/slots x 3 repeats in each arm
     (what was collected);
  2. common per-task execution budget: both strategies may spend the same
     number b of model executions per task (this module);
  3. realized-cost matching: calls/tokens actually spent (unequal: the
     multi-call panel spent 54.5 calls/task and 3.7x the tokens).

This module computes #2 from the sealed ledgers (no model calls): at each
budget b = 3, 6, ..., 27 executions per task it compares

  * panel strategy:  b executions drawn from the generated-harness panel
     (dev-ranked members, three eval repeats each; bare is retained in the
     portfolio because it is the dev-best fixed member);
  * same-code strategy: b of the 27 bare-code clone executions
     (subsampled repeatedly to average over choice of executions),

under two post-execution aggregators that bracket what is achievable:
  * ORACLE coverage  max over executed outcomes (upper bound, not
                     deployable; requires an ex-post verifier),
  * MAJORITY vote    self-consistency aggregation (deployable without any
                     per-task correctness signal).

All numbers come from the sealed WP-1R ledgers via wp1r_analysis.matrices.
Deterministic, offline, seeded.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiment.revision.wp1r_analysis import ARM_LEDGERS, matrices, merge_cells  # noqa: E402

WP1R = ROOT / "artifacts/wp1r_20260915"
SEED = 20260915
N_SUBSAMPLE = 1000


def _oracle_acc(P: np.ndarray) -> float:
    return float(np.nanmean(np.nanmax(P, axis=0)))


def _majority_acc(P: np.ndarray) -> float:
    denom = np.sum(~np.isnan(P), axis=0)
    votes = np.nansum(P, axis=0)
    pred = (votes > denom / 2).astype(float)
    pred[denom == 0] = np.nan
    return float(np.nanmean(pred))


def _per_task_spend(arm: str) -> dict:
    cells, _ = merge_cells(ARM_LEDGERS[arm])
    calls: dict[str, int] = {}
    tokens: dict[str, int] = {}
    for (h, t, r), c in cells.items():
        acc = c.get("accounting", {})
        calls[t] = calls.get(t, 0) + (acc.get("logical_calls", 0) or 0)
        v = acc.get("total_tokens")
        if isinstance(v, int):
            tokens[t] = tokens.get(t, 0) + v
    cs = np.array(list(calls.values()), dtype=float)
    ts = np.array(list(tokens.values()), dtype=float)
    return {
        "tasks": len(cs),
        "calls_per_task_mean": round(float(cs.mean()), 2),
        "calls_per_task_median": float(np.median(cs)),
        "calls_per_task_minmax": [int(cs.min()), int(cs.max())],
        "tokens_per_task_mean": round(float(ts.mean()), 0),
        "tokens_per_task_median": float(np.median(ts)),
        "tokens_total": int(ts.sum()),
    }


def budget_curves(n_subsample: int = N_SUBSAMPLE) -> dict:
    members, _, _, Ym, _, _, _ = matrices(ARM_LEDGERS["eval_real"])
    _, _, _, Yd, _, _, _ = matrices(ARM_LEDGERS["dev_real"])
    _, _, _, Ycm, _, _, _ = matrices(ARM_LEDGERS["eval_clone"])
    Yr = np.stack([Ym[r] for r in sorted(Ym)])
    Ydev = np.stack([Yd[r] for r in sorted(Yd)])
    Yc = np.stack([Ycm[r] for r in sorted(Ycm)])
    M = Yr.shape[1]
    bare_i = members.index("bare")
    dev_acc = np.nanmean(Ydev, axis=(0, 2))
    dev_order = list(np.argsort(-dev_acc))

    clone_pool = np.stack([Yc[r, i] for i in range(M) for r in range(3)])
    n_clone = clone_pool.shape[0]
    rng = np.random.default_rng(SEED)

    rows = []
    for n_mem in range(1, M + 1):
        chosen = list(dev_order[:n_mem])
        if bare_i not in chosen:
            chosen[-1] = bare_i          # keep the dev-best fixed member
        chosen = sorted(chosen, key=lambda i: -dev_acc[i])
        P = np.stack([Yr[r, i] for i in chosen for r in range(3)])
        b = P.shape[0]
        co, cm = [], []
        for _ in range(n_subsample):
            idx = rng.choice(n_clone, size=b, replace=False)
            co.append(_oracle_acc(clone_pool[idx]))
            cm.append(_majority_acc(clone_pool[idx]))
        rows.append({
            "budget_executions_per_task": b,
            "n_panel_members": len(chosen),
            "panel_members": [members[i] for i in chosen],
            "panel_oracle": round(_oracle_acc(P), 4),
            "panel_majority": round(_majority_acc(P), 4),
            "clone_oracle_mean": round(float(np.mean(co)), 4),
            "clone_oracle_ci95": [round(float(np.percentile(co, 2.5)), 4),
                                  round(float(np.percentile(co, 97.5)), 4)],
            "clone_majority_mean": round(float(np.mean(cm)), 4),
            "clone_majority_ci95": [round(float(np.percentile(cm, 2.5)), 4),
                                    round(float(np.percentile(cm, 97.5)), 4)],
            "oracle_gap_panel_minus_clone_pp":
                round(100 * (_oracle_acc(P) - float(np.mean(co))), 2),
            "majority_gap_panel_minus_clone_pp":
                round(100 * (_majority_acc(P) - float(np.mean(cm))), 2),
        })
    return {
        "estimand": "common per-task execution budget b (model executions); "
                    "panel vs same-code clone, oracle and majority aggregation",
        "portfolio_rule": "dev-ranked members, three eval repeats each, "
                          "bare retained (dev-best fixed member)",
        "seed": SEED, "n_subsample": n_subsample,
        "realized_spend": {a: _per_task_spend(a)
                           for a in ("eval_real", "eval_clone", "dev_real")},
        "budget_rows": rows,
    }


def main() -> None:
    report = budget_curves()
    out = WP1R / "budget_curves.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(f"wrote {out}")
    print(f"{'b':>3} {'panelORC':>9} {'cloneORC':>9} {'panelMAJ':>9} "
          f"{'cloneMAJ':>9} {'gapORC':>7} {'gapMAJ':>7}")
    for r in report["budget_rows"]:
        print(f"{r['budget_executions_per_task']:>3} "
              f"{r['panel_oracle']*100:>8.2f}% {r['clone_oracle_mean']*100:>8.2f}% "
              f"{r['panel_majority']*100:>8.2f}% {r['clone_majority_mean']*100:>8.2f}% "
              f"{r['oracle_gap_panel_minus_clone_pp']:>6.2f} "
              f"{r['majority_gap_panel_minus_clone_pp']:>6.2f}")


if __name__ == "__main__":
    main()
