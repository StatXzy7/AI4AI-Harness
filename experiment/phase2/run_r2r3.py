"""R2/R3 robustness audits (frozen in PHASE2_SAP).

R2: arms A and D replicated CACHE-OFF on the core-400 — quantifies how much apparent
agreement/diversity is the shared response cache (common random numbers) vs structural.
R3: three independent cache-off repeats of bare — outcome flip rate under API
nondeterminism at temperature 0.

Cost is bounded: cache-off means every call is fresh, but the core-400 × a
representative subset of harnesses keeps it affordable. The audit does NOT enter the
confirmatory analysis; it quantifies the noise floor under the effect sizes (-0.30 pp
K-matched) we are interpreting.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts" / "phase2"

# Representative subset: for R2, 2 harnesses per arm per seed would be ideal but
# costly. Frozen plan says "arms A and D on the core". Take the first 2 admitted
# harnesses per cell for A and D — deterministic selection, documented.
GEN = P2 / "gen"
EXCLUDED = {"p2_A_glm_s1_g0", "p2_A_glm_s1_g4"}

sel = []
for f in sorted(GEN.glob("A_*_s[012].json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    admitted = [r["harness"] for r in d["results"]
                if r["admitted"] and r["harness"] not in EXCLUDED][:2]
    sel.extend(admitted)
for f in sorted(GEN.glob("D_*_s[012].json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    admitted = [r["harness"] for r in d["results"] if r["admitted"]][:2]
    sel.extend(admitted)

Path(ROOT / "artifacts/phase2/r2_harnesses.txt").write_text(",".join(sel))
print(f"R2: {len(sel)} harnesses (2 per A/D cell) + bare, cache-off, core-400")

# R3: bare x 3 repeats
for rep in range(3):
    out = ROOT / f"artifacts/phase2/r3_rep{rep}.jsonl"
    if out.exists():
        print(f"R3 rep{rep} exists, skip")
        continue
    cmd = [
        "python", str(ROOT / "experiment/phase2/collect.py"),
        "--split", "split_p2_test_core",
        "--harnesses", "bare",
        "--target", "GLM-5.3-Flash",
        "--workers", "24", "--repeat", str(rep), "--no-cache",
        "--out", str(out),
    ]
    print(f"R3 rep{rep}: launching")
    subprocess.Popen(cmd, cwd=ROOT / "external" / "TTHE",
                     env={**__import__("os").environ,
                          "PARATERA_API_KEY": [l for l in open(ROOT / "experiment/.env_tthe")][0].split("=", 1)[1].strip()})
