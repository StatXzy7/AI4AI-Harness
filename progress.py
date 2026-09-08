import json
from pathlib import Path

P2 = Path("artifacts/phase2")
ad_files = ["ad_shard0.jsonl","ad_shard1.jsonl","ad_shard2.jsonl","ad_shard3.jsonl","ad_s2.jsonl",
            "ad_boost_A1.jsonl","ad_boost_A2.jsonl","ad_boost_D1.jsonl"]
bc_files = ["run_BC_core.jsonl","bc_boost1.jsonl","bc_boost2.jsonl","bc_s2.jsonl"]

def load(files):
    done = set()
    for f in files:
        p = P2/f
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            done.add((r["target"], r["harness_id"], r["task_id"]))
    return done

split = json.loads(Path("experiment/phase2/split_p2_test.json").read_text())
tasks = {f"{d}#{i}" for d, idxs in split["by_db"].items() for i in idxs}
core = json.loads(Path("experiment/phase2/split_p2_test_core.json").read_text())
core_tasks = {f"{d}#{i}" for d, idxs in core["by_db"].items() for i in idxs}
GEN = Path("artifacts/phase2/gen")

def admitted(arm):
    out = []
    for f in sorted(GEN.glob(f"{arm}_*_s[012].json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out += [r["harness"] for r in d["results"] if r["admitted"]]
    return out

A, D, B, C = admitted("A"), admitted("D"), admitted("B"), admitted("C")
ad_done, bc_done = load(ad_files), load(bc_files)

incomplete_ad, incomplete_bc = [], []
for h in A + D:
    have = sum(1 for t in tasks if ("GLM-5.3-Flash", h, t) in ad_done)
    if have < len(tasks):
        incomplete_ad.append((h, len(tasks)-have))
for h in B + C:
    have = sum(1 for t in core_tasks if ("GLM-5.3-Flash", h, t) in bc_done)
    if have < len(core_tasks):
        incomplete_bc.append((h, len(core_tasks)-have))
# A/D restricted to core also needed for factorial
for h in A + D:
    have = sum(1 for t in core_tasks if ("GLM-5.3-Flash", h, t) in ad_done)
    if have < len(core_tasks):
        incomplete_bc.append((f"ADcore/{h}", len(core_tasks)-have))

bare = sum(1 for t in tasks if ("GLM-5.3-Flash", "bare", t) in ad_done)
print(f"AD: {len(ad_done)} unique cells | bare {bare}/1169")
print(f"AD incomplete: {len(incomplete_ad)} harnesses, {sum(x[1] for x in incomplete_ad)} cells missing")
print(f"BC(+ADcore) incomplete: {len(incomplete_bc)} entries, {sum(x[1] for x in incomplete_bc)} cells missing")
print("top AD missing:", incomplete_ad[:5])
print("top BC missing:", incomplete_bc[:5])
