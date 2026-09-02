"""Pre-registered comparison table for harness populations (PROBLEM_FREEZE v7 / EXPERIMENT_PLAN §2).

For each population (subset of harnesses in an outcome matrix), computes:
  - pairwise outcome disagreement (mean over pairs)
  - union repair rate over bare errors
  - oracle headroom vs best fixed (pp)
  - number of harnesses with non-empty, pairwise-distinct fix sets
  - admission against the pre-registered thresholds:
      union_repair >= --min-repair (default 0.15), headroom >= --min-headroom-pp (default 5),
      distinct fix sets >= --min-fixsets (default 3)

Usage:
  python experiment/compare_populations.py \
      --matrix artifacts/outcomes/tthe_eval151_matrix.parquet \
      --spec artifacts/day2/populations_eval151.json \
      --out artifacts/day2/eval151_comparison.json
Spec format: {"<population label>": ["harness_id", ...], ...}  (bare must be included)
With --spec omitted, every non-bare harness is one single-harness "population".
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
H0 = "bare"


def pop_stats(wide: pd.DataFrame, bare: pd.Series, members: list[str]) -> dict:
    sub = wide[members]
    dis = [float(np.mean(sub[a] != sub[b])) for a, b in itertools.combinations(members, 2)]
    bare_errors = set(bare.index[bare == 0])
    fixsets = {}
    for h in members:
        repaired = set(sub.index[(sub[h] == 1) & (bare.reindex(sub.index) == 0)])
        fixsets[h] = repaired
    union_repair_items = set().union(*fixsets.values()) & bare_errors if fixsets else set()
    nonempty = {h: s for h, s in fixsets.items() if s}
    distinct = 0
    seen: list[frozenset] = []
    for h, s in nonempty.items():
        fs = frozenset(s)
        if fs not in seen:
            seen.append(fs)
            distinct += 1
    per_acc = sub.mean()
    best_fixed = float(per_acc.max())
    oracle_any = pd.concat([sub.max(axis=1), bare], axis=1).max(axis=1)
    return {
        "n_harnesses": len(members),
        "pairwise_disagreement_mean": float(np.mean(dis)) if dis else 0.0,
        "pairwise_disagreement_max": float(np.max(dis)) if dis else 0.0,
        "n_zero_disagreement_pairs": int(sum(1 for d in dis if d == 0.0)),
        "n_pairs": len(dis),
        "bare_acc": float(bare.mean()),
        "best_fixed_acc": best_fixed,
        "best_fixed_id": str(per_acc.idxmax()),
        "oracle_any_acc": float(oracle_any.mean()),
        "oracle_headroom_vs_best_fixed_pp": 100 * (float(oracle_any.mean()) - best_fixed),
        "bare_errors": len(bare_errors),
        "union_repair_rate": float(len(union_repair_items) / len(bare_errors)) if bare_errors else 0.0,
        "union_repair_items": len(union_repair_items),
        "n_harnesses_with_fixes": len(nonempty),
        "n_distinct_nonempty_fixsets": distinct,
        "per_harness_acc": {k: round(float(v), 4) for k, v in per_acc.items()},
    }


def admit(s: dict, min_repair: float, min_head_pp: float, min_fixsets: int) -> bool:
    return (s["union_repair_rate"] >= min_repair
            and s["oracle_headroom_vs_best_fixed_pp"] >= min_head_pp
            and s["n_distinct_nonempty_fixsets"] >= min_fixsets)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-repair", type=float, default=0.15)
    ap.add_argument("--min-headroom-pp", type=float, default=5.0)
    ap.add_argument("--min-fixsets", type=int, default=3)
    args = ap.parse_args()

    df = pd.read_parquet(ROOT / args.matrix)
    wide = df.pivot_table(index="task_id", columns="harness_id", values="harness_correct")
    bare = wide[H0]
    if args.spec:
        spec = json.loads((ROOT / args.spec).read_text())
    else:
        spec = {h: [h] for h in wide.columns if h != H0}

    out = {"matrix": args.matrix, "n_tasks": int(wide.shape[0]),
           "thresholds": {"min_repair": args.min_repair,
                          "min_headroom_pp": args.min_headroom_pp,
                          "min_distinct_fixsets": args.min_fixsets},
           "populations": {}}
    for label, members in spec.items():
        missing = [m for m in members if m not in wide.columns]
        if missing:
            out["populations"][label] = {"error": f"missing harnesses: {missing}"}
            continue
        s = pop_stats(wide, bare, members)
        s["admitted"] = admit(s, args.min_repair, args.min_headroom_pp, args.min_fixsets)
        out["populations"][label] = s
        print(f"[{label}] disagree={s['pairwise_disagreement_mean']:.3f} "
              f"union_repair={s['union_repair_rate']:.3f} "
              f"headroom={s['oracle_headroom_vs_best_fixed_pp']:.2f}pp "
              f"distinct_fixsets={s['n_distinct_nonempty_fixsets']} "
              f"admitted={s['admitted']}")

    if args.out:
        path = ROOT / args.out
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2))
        print(f"[write] {path}")


if __name__ == "__main__":
    main()
