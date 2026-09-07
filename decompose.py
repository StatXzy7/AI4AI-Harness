import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, 'experiment')
from collections import defaultdict
from phase2.metrics import headroom, population_metrics
from phase2.analysis_primary import build_matrix, load_cells

ROOT = Path('.')
P2 = ROOT / 'artifacts' / 'phase2'
AD_FILES = [P2 / f"ad_shard{i}.jsonl" for i in range(4)] + [P2 / "ad_s2.jsonl"] + [
    P2 / f"ad_boost_A{i}.jsonl" for i in (1, 2)] + [P2 / "ad_boost_D1.jsonl"] + [
    P2 / f"ad_resume{i}.jsonl" for i in range(4)] + [
    P2 / f"ad_final{i}.jsonl" for i in range(3)] + [P2 / "ad_last.jsonl"]
BC_FILES = [P2 / f for f in [
    "run_BC_core.jsonl", "bc_s2.jsonl", "bc_boost1.jsonl", "bc_boost2.jsonl",
    "bc_final.jsonl", "bc_last.jsonl", "bc_rem0.jsonl", "bc_rem1.jsonl", "bc_rem2.jsonl"]]

cells, _ = load_cells(AD_FILES)
cells_bc, _ = load_cells(BC_FILES)
core = json.loads((ROOT / 'experiment/phase2/split_p2_test_core.json').read_text())
core_tasks = sorted({f"{d}#{i}" for d, idxs in core["by_db"].items() for i in idxs})

GEN = P2 / 'gen'
EXCLUDED = {"p2_A_glm_s1_g0", "p2_A_glm_s1_g4"}
mem = defaultdict(list)
for f in sorted(GEN.glob("[ABCD]_*_s[012].json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    for r in d["results"]:
        if r["admitted"] and r["harness"] not in EXCLUDED:
            mem[(d["arm"], d["builder"], d["seed"])].append(r["harness"])

M = {}
for (arm, builder, seed), hs in mem.items():
    src = cells if arm in ("A", "D") else cells_bc
    names = hs + ["bare"]
    present, m, bare, _ = build_matrix(src, "GLM-5.3-Flash", names, "official_correct")
    if bare is None or not present:
        continue
    M[(arm, builder, seed)] = (m, np.array(bare, dtype=float))

cells_q = sorted({(b, s) for (a, b, s) in M if a == "A"} & {(b, s) for (a, b, s) in M if a == "D"})
cells_q = [(b, s) for (b, s) in cells_q if all((a, b, s) in M for a in "ABCD")]

# KILLER 2: headroom decomposition per arm — is the gate making individuals
# stronger but populations less complementary, or actually worse overall?
print("=== HEADROOM DECOMPOSITION (18 quad cells, core-400, official judge) ===")
print(f"{'arm':>4s} {'K':>5s} {'bare':>6s} {'meanH':>7s} {'bestfix':>8s} {'oracle':>7s} {'H':>7s}")
out = {}
for arm in "ABCD":
    Ks, bares, meanaccs, bestfix, oracle, H = [], [], [], [], [], []
    for (b, s) in cells_q:
        m, bare = M[(arm, b, s)]
        pool = np.vstack([m, bare[None, :]])
        Ks.append(m.shape[0])
        bares.append(bare.mean())
        meanaccs.append(m.mean())
        bestfix.append(pool.mean(axis=1).max())
        oracle.append(pool.max(axis=0).mean())
        H.append(headroom(m, bare))
    row = {"K": round(float(np.mean(Ks)), 1), "bare_acc": round(float(np.mean(bares)), 4),
           "mean_harness_acc": round(float(np.mean(meanaccs)), 4),
           "best_fixed": round(float(np.mean(bestfix)), 4),
           "oracle_acc": round(float(np.mean(oracle)), 4),
           "headroom": round(float(np.mean(H)), 4)}
    out[arm] = row
    print(f"{arm:>4s} {row['K']:>5.1f} {row['bare_acc']:>6.3f} {row['mean_harness_acc']:>7.3f} "
          f"{row['best_fixed']:>8.3f} {row['oracle_acc']:>7.3f} {row['headroom']:>7.3f}")
json.dump(out, open('artifacts/phase2/headroom_decomposition.json', 'w'), indent=1)
print("saved -> artifacts/phase2/headroom_decomposition.json")

# KILLER 3: raw + Holm-adjusted p-values for the three factorial contrasts
print("\n=== HOLM-ADJUSTED INFERENCE ===")
fact = json.loads((P2 / 'analysis_factorial.json').read_text(encoding='utf-8'))
rng = np.random.default_rng(20260907)
per = fact["per_cell"]
b_a = np.array([c["B-A"] for c in per])
d_c = np.array([c["D-C"] for c in per])
c_a = np.array([c["C-A"] for c in per])
d_b = np.array([c["D-A"] - c["C-A"] + c["B-A"] - c["A"] - (c["D-A"] - c["B"]) if False else 0 for c in per])
# D-B directly:
d_b = np.array([c["H"]["D"] - c["H"]["B"] for c in per])

contrasts = {
    "gate_main": (b_a + d_c) / 2,
    "strategy_main": (c_a + d_b) / 2,
    "interaction": d_c - b_a,
}
# permutation p-values (sign-flip within cell, two-sided) + Holm
def perm_p(x, n=10000):
    obs = np.mean(x)
    hits = 0
    for _ in range(n):
        flips = rng.random(len(x)) < 0.5
        stat = np.mean(np.where(flips, -x, x))
        if abs(stat) >= abs(obs):
            hits += 1
    return hits / n

raw = {k: perm_p(v) for k, v in contrasts.items()}
# Holm correction
order = sorted(raw, key=raw.get)
m_tests = len(order)
holm = {}
running = 0.0
for i, k in enumerate(order):
    adj = min(1.0, (m_tests - i) * raw[k])
    adj = max(adj, running)
    holm[k] = round(adj, 4)
    running = adj
print(f"{'contrast':16s} {'effect':>8s} {'raw p':>8s} {'Holm p':>8s}")
for k in order:
    print(f"{k:16s} {np.mean(contrasts[k])*100:+7.2f}pp {raw[k]:>8.4f} {holm[k]:>8.4f}")
json.dump({"raw_p": {k: round(v,4) for k,v in raw.items()}, "holm_p": holm},
          open('artifacts/phase2/holm_pvalues.json','w'), indent=1)
print("saved -> artifacts/phase2/holm_pvalues.json")
