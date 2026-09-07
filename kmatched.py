import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, 'experiment')
from collections import defaultdict
from phase2.metrics import headroom
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
        M[(arm, builder, seed)] = None
        continue
    M[(arm, builder, seed)] = (m, np.array(bare, dtype=float))

cells_q = sorted({(b, s) for (a, b, s) in M if M.get((a, b, s)) is not None and a == "A"} &
                {(b, s) for (a, b, s) in M if M.get((a, b, s)) is not None and a == "D"})
cells_q = [(b, s) for (b, s) in cells_q if all(M.get((a, b, s)) is not None for a in "ABCD")]
print(f"quad cells: {len(cells_q)}")

rng = np.random.default_rng(20260907)
N_DRAWS = 200


def k_matched_H(m, bare, k):
    K = m.shape[0]
    if K < k:
        return None
    if K == k:
        return headroom(m, bare)
    vals = [headroom(m[rng.choice(K, k, replace=False)], bare) for _ in range(N_DRAWS)]
    return float(np.mean(vals))


b_a_km, d_c_km = [], []
per_cell_km = []
for (b, s) in cells_q:
    A = M[("A", b, s)]
    B = M[("B", b, s)]
    C = M[("C", b, s)]
    D = M[("D", b, s)]
    k1 = min(B[0].shape[0], A[0].shape[0])
    hA, hB = k_matched_H(A[0], A[1], k1), k_matched_H(B[0], B[1], k1)
    if hA is not None and hB is not None:
        b_a_km.append(hB - hA)
    k2 = min(D[0].shape[0], C[0].shape[0])
    hC, hD = k_matched_H(C[0], C[1], k2), k_matched_H(D[0], D[1], k2)
    if hC is not None and hD is not None:
        d_c_km.append(hD - hC)
    per_cell_km.append({"builder": b, "seed": s, "k_BvA": k1, "k_DvC": k2,
                       "BA_km": round(hB - hA, 4) if hA is not None and hB is not None else None,
                       "DC_km": round(hD - hC, 4) if hC is not None and hD is not None else None})

n_min = min(len(b_a_km), len(d_c_km))
combined = [(b_a_km[i] + d_c_km[i]) / 2 for i in range(n_min)]
gate_km = float(np.mean(combined))
bs = [rng.choice(combined, n_min, replace=True).mean() for _ in range(10000)]
lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))

print("\n=== K-MATCHED GATE MAIN EFFECT ===")
print(f"B-A (K-matched): {np.mean(b_a_km):+.4f} (n={len(b_a_km)})")
print(f"D-C (K-matched): {np.mean(d_c_km):+.4f} (n={len(d_c_km)})")
print(f"gate main K-matched: {gate_km:+.4f}  CI [{lo:+.4f}, {hi:+.4f}]")
print("original unmatched: -0.0067 [-0.0117, -0.0013]")

json.dump({"gate_main_km": round(gate_km, 4), "ci95": [round(lo, 4), round(hi, 4)],
           "b_a_km": round(float(np.mean(b_a_km)), 4),
           "d_c_km": round(float(np.mean(d_c_km)), 4),
           "n": n_min, "per_cell": per_cell_km},
          open('artifacts/phase2/kmatched_gate.json', 'w'), indent=1)
print("saved -> artifacts/phase2/kmatched_gate.json")
