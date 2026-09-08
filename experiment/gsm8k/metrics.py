"""GSM8K audit metrics: the same population statistics as the SQL phases.

  * pairwise disagreement, K_eff (unique outcome vectors)
  * oracle headroom over best fixed, union repair/harm over bare
  * bare baseline included as a population member (same convention as SQL)
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "artifacts" / "gsm8k_audit"


def load(path: Path):
    verdicts, answers = {}, {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        verdicts[(r["harness_id"], r["task_id"])] = r["official_correct"]
        answers[(r["harness_id"], r["task_id"])] = r.get("final_answer") or ""
    return verdicts, answers


def main() -> None:
    files = sorted(P.glob("run_*.jsonl"))
    if not files:
        sys.exit(f"no run_*.jsonl under {P}")
    verdicts, answers = {}, {}
    for f in files:
        v, a = load(f)
        verdicts.update(v)
        answers.update(a)

    tasks = sorted({t for h, t in verdicts})
    harnesses = sorted({h for h, t in verdicts})
    per_h = {h: [verdicts[(h, t)] for t in tasks] for h in harnesses}
    vecs = {tuple(per_h[h]) for h in harnesses}

    accs = {h: sum(v) / len(v) for h, v in per_h.items()}
    gen = [h for h in harnesses if h != "bare"]
    oracle = sum(max(per_h[h][i] for h in harnesses) for i in range(len(tasks))) / len(tasks)
    best_fixed = max(accs.values())

    dis = []
    for h1, h2 in itertools.combinations(gen, 2):
        d = sum(a != b for a, b in zip(per_h[h1], per_h[h2])) / len(tasks)
        dis.append((h1, h2, d))
    dis.sort(key=lambda x: -x[2])

    # union repair/harm over bare
    bare_v = per_h.get("bare")
    rep = harm = None
    if bare_v:
        any_gen = [max(per_h[h][i] for h in gen) for i in range(len(tasks))]
        n_bare_wrong = sum(1 for v in bare_v if not v)
        rep = sum(1 for b, g in zip(bare_v, any_gen) if not b and g) / n_bare_wrong if n_bare_wrong else None
        n_bare_right = sum(1 for v in bare_v if v)
        harm = sum(1 for b, g in zip(bare_v, any_gen) if b and not g) / n_bare_right if n_bare_right else None

    out = {
        "n_harnesses": len(harnesses), "n_generated": len(gen),
        "n_tasks": len(tasks),
        "unique_outcome_vectors": len(vecs),
        "K_eff_fraction": round(len(vecs) / max(1, len(gen)), 4),
        "mean_pairwise_disagreement": round(sum(d for _, _, d in dis) / max(1, len(dis)), 4),
        "max_pairwise_disagreement": round(dis[0][2], 4) if dis else None,
        "frac_pairs_outcome_identical": round(
            sum(1 for _, _, d in dis if d == 0) / max(1, len(dis)), 4),
        "oracle_acc": round(oracle, 4),
        "best_fixed_acc": round(best_fixed, 4),
        "best_fixed_harness": max(accs, key=accs.get),
        "oracle_headroom_pp": round((oracle - best_fixed) * 100, 2),
        "bare_acc": round(accs["bare"], 4) if "bare" in accs else None,
        "union_repair": round(rep, 4) if rep is not None else None,
        "union_harm": round(harm, 4) if harm is not None else None,
        "per_harness_acc": {h: round(a, 4) for h, a in sorted(accs.items(), key=lambda kv: -kv[1])},
    }
    (P / "metrics.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "per_harness_acc"}, indent=1))
    print("\ntop-5 disagreeing pairs:")
    for h1, h2, d in dis[:5]:
        print(f"  {d:.3f}  {h1} vs {h2}")
    print(f"-> {P / 'metrics.json'}")


if __name__ == "__main__":
    main()
