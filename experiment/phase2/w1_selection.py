"""W1 exploratory probe: does diversity-aware POPULATION selection on a dev split
transfer to held-out headroom? (Post-hoc on the archived confirmatory cells;
exploratory -- the confirmatory set was already used for the primary analysis.)

Per (builder x seed) cell, pool = all p2 harnesses of that cell (25-29, arms mixed).
Task split: random half of the 9 databases -> dev, complement -> held-out
(R=100 splits). Selection on dev only, evaluation on held-out only.

Methods (all select k harnesses from the cell pool):
  top-acc   : k highest dev accuracies
  random    : uniform random k (averaged over draws)
  div-only  : greedy max dev oracle coverage (diversity only)
  acc+lam*div : greedy max dev [mean-acc + lam * oracle-acc], lam in {0.25,0.5,1,2}

Reported: held-out oracle acc, best-fixed acc, headroom (oracle - best-fixed);
paired deltas vs top-acc with a cell-level bootstrap CI.
"""
import itertools
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts" / "phase2"

split = json.loads((ROOT / "experiment/phase2/split_p2_test_core.json").read_text())
DBS = sorted(split["by_db"])
TASKS = {f"{d}#{i}" for d, idxs in split["by_db"].items() for i in idxs}

# ---------------------------------------------------------------- outcome vectors
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
print(f"cells used: {len(cells)}  (pool sizes "
      f"{min(map(len, cells.values()))}-{max(map(len, cells.values()))})")

KS = (4, 8)
LAMS = (0.25, 0.5, 1.0, 2.0)
N_SPLITS = 100
N_RANDOM = 200
rng = random.Random(20260908)

def acc(h, tasks):
    return sum(recs[(h, t)] for t in tasks) / len(tasks)

def oracle(hs, tasks):
    return sum(any(recs[(h, t)] for h in hs) for t in tasks) / len(tasks)

def greedy_score(pool, k, dev, lam, score):
    """Greedy selection maximizing score(S); score uses dev only."""
    accs = {h: acc(h, dev) for h in pool}
    chosen = [max(pool, key=lambda h: (accs[h], h))]
    while len(chosen) < k:
        rest = [h for h in pool if h not in chosen]
        if not rest:
            break
        best = max(rest, key=lambda h: (score(chosen + [h], accs, dev), h))
        chosen.append(best)
    return chosen

def combined_score(lam):
    def sc(S, accs, dev):
        return sum(accs[h] for h in S) / len(S) + lam * oracle(S, dev)
    return sc

def div_score(S, accs, dev):          # diversity only
    return oracle(S, dev)

def heldout_eval(S, test):
    accs = [acc(h, test) for h in S]
    return {"oracle": oracle(S, test), "best": max(accs),
            "headroom": oracle(S, test) - max(accs)}

# ---------------------------------------------------------------- run
results = defaultdict(list)            # (method, k) -> list of per-cell-split dicts
for s_i in range(N_SPLITS):
    dbs = DBS[:]
    rng.shuffle(dbs)
    dev_dbs = set(dbs[: len(dbs) // 2])
    dev = {t for t in TASKS if t.split("#")[0] in dev_dbs}
    test = TASKS - dev
    for cell, pool in cells.items():
        # baselines and methods
        accs_sorted = sorted(pool, key=lambda h: (-acc(h, dev), h))
        for k in KS:
            for name, S in [
                ("top-acc", accs_sorted[:k]),
                ("div-only", greedy_score(pool, k, dev, None, div_score)),
            ] + [(f"acc+{lam}div", greedy_score(pool, k, dev, lam,
                                                 combined_score(lam)))
                 for lam in LAMS]:
                results[(name, k)].append({"cell": f"{cell[0]}/{cell[1]}",
                                           **heldout_eval(S, test)})
            rnd = [heldout_eval(rng.sample(pool, k), test)
                   for _ in range(N_RANDOM)]
            results[("random", k)].append({
                "cell": f"{cell[0]}/{cell[1]}",
                "oracle": sum(r["oracle"] for r in rnd) / N_RANDOM,
                "best": sum(r["best"] for r in rnd) / N_RANDOM,
                "headroom": sum(r["headroom"] for r in rnd) / N_RANDOM,
            })

# ---------------------------------------------------------------- aggregate
def agg(name, k, key):
    vals = [r[key] for r in results[(name, k)]]
    return sum(vals) / len(vals)

summary = {"n_cells": len(cells), "n_splits": N_SPLITS,
           "note": "exploratory post-hoc probe; dev/test split by database halves",
           "methods": {}}
for k in KS:
    for name in ["top-acc", "random", "div-only"] + [f"acc+{lam}div" for lam in LAMS]:
        summary["methods"][f"{name}|k={k}"] = {
            "heldout_oracle": round(agg(name, k, "oracle"), 4),
            "heldout_best": round(agg(name, k, "best"), 4),
            "heldout_headroom": round(agg(name, k, "headroom"), 4),
        }

# paired deltas vs a baseline, aggregated per cell first (splits within a cell are
# correlated), bootstrap over the 18 cells
def per_cell_deltas(name, k, base_name, key="headroom"):
    base_rows = defaultdict(list)
    for r in results[(base_name, k)]:
        base_rows[r["cell"]].append(r[key])
    rows = defaultdict(list)
    for r in results[(name, k)]:
        rows[r["cell"]].append(r[key])
    cells_all = sorted(rows)
    return {c: sum(r2 - r1 for r2, r1 in zip(rows[c], base_rows[c]))
                 / len(rows[c]) for c in cells_all}

boot = random.Random(7)
def delta_ci(name, k, base_name="top-acc"):
    d = per_cell_deltas(name, k, base_name)
    vals = list(d.values())
    stats = []
    for _ in range(4000):
        s = [vals[boot.randrange(len(vals))] for _ in range(len(vals))]
        stats.append(sum(s) / len(s))
    stats.sort()
    return {"mean_pp": round(sum(vals) / len(vals) * 100, 2),
            "ci95_pp": [round(stats[int(0.025 * len(stats))] * 100, 2),
                        round(stats[int(0.975 * len(stats))] * 100, 2)]}

for k in KS:
    for name in ["random", "div-only"] + [f"acc+{lam}div" for lam in LAMS]:
        summary["methods"][f"{name}|k={k}"]["delta_vs_topacc"] = delta_ci(name, k)
    summary["methods"][f"div-only|k={k}"]["delta_vs_random"] = delta_ci("div-only", k, "random")

(P2 / "w1_selection.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print(json.dumps(summary["methods"], indent=1))
print(f"-> {P2 / 'w1_selection.json'}")
