"""W1 addendum: oracle-headroom-captured normalization for the selection probe.

Same protocol as w1_selection.py (dev/test split by random database halves,
100 splits, per-cell pools of 25-29 p2 harnesses), recomputed here so the
full-pool oracle is available on the same splits. Reports, per selection
method (top-acc / div-only, k=8):
    captured = (oracle(selected k) - best_fixed) / (oracle(full pool) - best_fixed)
where best_fixed is the best single harness in the pool on the test half.
Paired cell-level bootstrap over the 18 cells for the div-vs-top-acc delta.
Exploratory post-hoc; appended to w1_headroom.json (separate from the frozen
w1_selection.json).
"""
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts" / "phase2"

split = json.loads((ROOT / "experiment/phase2/split_p2_test_core.json").read_text())
DBS = sorted(split["by_db"])
TASKS = {f"{d}#{i}" for d, idxs in split["by_db"].items() for i in idxs}

recs = {}
for pat in ("ad_*.jsonl", "bc_*.jsonl"):
    for p in sorted(P2.glob(pat)):
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            h, t = r.get("harness_id"), r.get("task_id")
            if (h and h.startswith("p2_") and t in TASKS
                    and r.get("repeat", 0) == 0):
                recs[(h, t)] = r.get("official_correct")

by_cell = defaultdict(list)
for h in {h for h, t in recs}:
    if all((h, t) in recs for t in TASKS):
        p = h.split("_")
        by_cell[(p[2], p[3])].append(h)
cells = {c: sorted(hs) for c, hs in by_cell.items() if len(hs) >= 8}

K = 8
N_SPLITS = 100
rng = random.Random(20260908)

def acc(h, tasks):
    return sum(recs[(h, t)] for t in tasks) / len(tasks)

def oracle(hs, tasks):
    return sum(any(recs[(h, t)] for h in hs) for t in tasks) / len(tasks)

def greedy_div(pool, k, dev):
    accs = {h: acc(h, dev) for h in pool}
    chosen = [max(pool, key=lambda h: (accs[h], h))]
    while len(chosen) < k:
        rest = [h for h in pool if h not in chosen]
        best = max(rest, key=lambda h: (oracle(chosen + [h], dev), h))
        chosen.append(best)
    return chosen

# per (method, cell): mean captured fraction over splits
rows = defaultdict(list)
for s_i in range(N_SPLITS):
    dbs = DBS[:]
    rng.shuffle(dbs)
    dev_dbs = set(dbs[: len(dbs) // 2])
    dev = {t for t in TASKS if t.split("#")[0] in dev_dbs}
    test = TASKS - dev
    for cell, pool in cells.items():
        accs_sorted = sorted(pool, key=lambda h: (-acc(h, dev), h))
        full_or = oracle(pool, test)
        best_fixed = max(acc(h, test) for h in pool)
        denom = full_or - best_fixed
        if denom <= 0:
            continue
        for name, S in [("top-acc", accs_sorted[:K]),
                        ("div-only", greedy_div(pool, K, dev))]:
            rows[(name, f"{cell[0]}/{cell[1]}")].append(
                (oracle(S, test) - best_fixed) / denom)

def cell_means(name):
    return [sum(v) / len(v) for v in (rows[(name, c)] for c in
            sorted({c for n, c in rows if n == name}))]

out = {"n_cells": len(cells), "n_splits": N_SPLITS, "k": K,
       "note": "exploratory addendum: captured = (oracle(selected)-best_fixed)/(oracle(full pool)-best_fixed)"}
for name in ("top-acc", "div-only"):
    m = cell_means(name)
    out[name] = {"mean_captured": round(sum(m) / len(m), 4),
                 "min_cell": round(min(m), 4), "max_cell": round(max(m), 4)}

# paired delta div - top-acc, bootstrap over cells
cells_all = sorted({c for n, c in rows})
deltas = {c: sum(rows[("div-only", c)]) / len(rows[("div-only", c)])
              - sum(rows[("top-acc", c)]) / len(rows[("top-acc", c)])
          for c in cells_all}
vals = list(deltas.values())
boot = random.Random(11)
stats = []
for _ in range(4000):
    s = [vals[boot.randrange(len(vals))] for _ in range(len(vals))]
    stats.append(sum(s) / len(s))
stats.sort()
out["delta_div_minus_topacc"] = {
    "mean_pp": round(sum(vals) / len(vals) * 100, 2),
    "ci95_pp": [round(stats[int(0.025 * len(stats))] * 100, 2),
                 round(stats[int(0.975 * len(stats))] * 100, 2)]}

(P2 / "w1_headroom.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
