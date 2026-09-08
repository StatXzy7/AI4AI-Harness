"""R2 analysis: how much of the Phase-II agreement/diversity is the shared response
cache vs structural (frozen in run_r2r3.py: arms A and D, 2 admitted harnesses per
cell, cache-off single pass on the core-400).

Reports:
  1. Verdict flip rate — same harness, cached confirmatory run vs cache-off replica.
  2. Disagreement structure — mean pairwise disagreement between different harnesses
     of the same arm, computed under cached outcomes and under cache-off outcomes,
     against the same-harness cross-run flip rate as the noise reference.
  3. Subset headroom stability — per (builder x seed) cell, headroom of the 2-harness
     R2 subset (oracle minus best-fixed, no bare), cached vs cache-off.
  4. Subset D-A contrast — per-cell D-A subset headroom difference, cached vs
     cache-off, and the mean difference (does the arm-level picture move?).
"""
import itertools
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts" / "phase2"

AD_FILES = ["ad_shard0.jsonl", "ad_shard1.jsonl", "ad_shard2.jsonl", "ad_shard3.jsonl",
            "ad_s2.jsonl", "ad_boost_A1.jsonl", "ad_boost_A2.jsonl", "ad_boost_D1.jsonl"]

split = json.loads((ROOT / "experiment/phase2/split_p2_test_core.json").read_text())
core_tasks = {f"{d}#{i}" for d, idxs in split["by_db"].items() for i in idxs}


def verdicts(cells, harnesses):
    """(harness, task) -> official_correct for the given harness set, core tasks only."""
    out = {}
    for r in cells:
        h, t = r["harness_id"], r["task_id"]
        if h in harnesses and t in core_tasks:
            out[(h, t)] = r.get("official_correct")
    return out


orig_cells = []
for p in sorted(P2.glob("ad_*.jsonl")):          # every cached confirmatory file
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip():
            try:
                orig_cells.append(json.loads(line))
            except Exception:
                pass

# Pass 1: the original collector covered all 70 selected harnesses (A then D).
r2_cells = [json.loads(l) for l in (P2 / "r2_cacheoff.jsonl").read_text(
    encoding="utf-8", errors="ignore").splitlines() if l.strip()]
# Pass 2: the parallel D-arm collector re-ran all 36 D harnesses independently --
# two independent cache-off passes over D, usable as a D-arm repeat-stability check.
r2d_cells = [json.loads(l) for l in (P2 / "r2_cacheoff_D.jsonl").read_text(
    encoding="utf-8", errors="ignore").splitlines() if l.strip()]

sel = (P2 / "r2_harnesses.txt").read_text().strip().split(",")
by_arm = defaultdict(list)
for h in sel:
    by_arm[h.split("_")[1]].append(h)          # p2_<ARM>_<builder>_s<k>_<slot>

cache_off = verdicts(r2_cells, set(sel))
cached = verdicts(orig_cells, set(sel))

# ---- 1. flip rate ---------------------------------------------------------
n_cmp = n_flip = 0
per_h = defaultdict(lambda: [0, 0])
for (h, t), v in cache_off.items():
    vo = cached.get((h, t))
    if vo is None:
        continue
    per_h[h][0] += 1
    per_h[h][1] += (v != vo)
    n_cmp += 1
    n_flip += (v != vo)

# ---- 2. disagreement structure -------------------------------------------
def mean_pairwise(vmap, hs):
    """Mean disagreement rate over harness pairs of the same arm, common tasks."""
    ds = []
    for h1, h2 in itertools.combinations(hs, 2):
        common = [t for t in core_tasks
                  if (h1, t) in vmap and (h2, t) in vmap]
        if len(common) < 100:
            continue
        ds.append(sum(vmap[(h1, t)] != vmap[(h2, t)] for t in common) / len(common))
    return (sum(ds) / len(ds), len(ds)) if ds else (None, 0)

struct = {}
for arm in sorted(by_arm):
    hs = [h for h in by_arm[arm] if per_h[h][0] == 400]   # completed harnesses only
    d_cached, np_c = mean_pairwise(cached, hs)
    d_off, np_o = mean_pairwise(cache_off, hs)
    struct[arm] = {"harnesses_complete": len(hs),
                   "pairwise_disagree_cached": round(d_cached, 4) if d_cached else None,
                   "pairwise_disagree_cacheoff": round(d_off, 4) if d_off else None,
                   "n_pairs": np_c}

# ---- 3. subset headroom stability ----------------------------------------
def cell_of(h):
    parts = h.split("_")            # p2, arm, builder, s<k>, slot
    return (parts[2], parts[3])

def subset_headroom(vmap, cell, arm):
    hs = [h for h in by_arm[arm] if cell_of(h) == cell
          and sum(1 for t in core_tasks if (h, t) in vmap) == 400]
    if len(hs) < 2:
        return None
    accs = {h: sum(vmap[(h, t)] for t in core_tasks) / 400 for h in hs}
    oracle = sum(any(vmap[(h, t)] for h in hs) for t in core_tasks) / 400
    return oracle - max(accs.values())

# ---- 4. D-arm repeat stability: two independent cache-off passes ------------
pass2 = verdicts(r2d_cells, set(sel))
n_rep = n_rep_flip = 0
per_h_rep = defaultdict(lambda: [0, 0])
for (h, t), v in pass2.items():
    v1 = cache_off.get((h, t))
    if v1 is None:
        continue
    per_h_rep[h][0] += 1
    per_h_rep[h][1] += (v != v1)
    n_rep += 1
    n_rep_flip += (v != v1)

cells = sorted({cell_of(h) for h in sel})
hr_rows = []
for cell in cells:
    row = {"cell": f"{cell[0]}/{cell[1]}"}
    for arm in ("A", "D"):
        hc = subset_headroom(cached, cell, arm)
        ho = subset_headroom(cache_off, cell, arm)
        row[f"hr_{arm}_cached"], row[f"hr_{arm}_cacheoff"] = hc, ho
    if all(v is not None for k, v in row.items() if k != "cell"):
        row["dA_cached"] = round(row["hr_D_cached"] - row["hr_A_cached"], 4)
        row["dA_cacheoff"] = round(row["hr_D_cacheoff"] - row["hr_A_cacheoff"], 4)
    hr_rows.append({k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in row.items()})

summary = {
    "cells_compared": n_cmp,
    "flips": n_flip,
    "flip_rate": round(n_flip / max(1, n_cmp), 4),
    "per_harness": {h: {"n": n, "flips": f, "rate": round(f / max(1, n), 4)}
                    for h, (n, f) in sorted(per_h.items())},
    "structure": struct,
    "d_repeat": {"cells_compared": n_rep, "flips": n_rep_flip,
                 "flip_rate": round(n_rep_flip / max(1, n_rep), 4),
                 "per_harness": {h: {"n": n, "flips": f, "rate": round(f / max(1, n), 4)}
                                 for h, (n, f) in sorted(per_h_rep.items())}},
    "subset_headroom": hr_rows,
}
out = P2 / "r2_analysis.json"
out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "per_harness"}, indent=1))
print(f"\nper-harness flip rates:")
for h, r in summary["per_harness"].items():
    print(f"  {h:35s} {r['n']:4d} cells  {r['flips']:3d} flips  {r['rate']:.2%}")
print(f"\n-> {out}")
