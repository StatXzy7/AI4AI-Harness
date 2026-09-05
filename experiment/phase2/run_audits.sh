#!/usr/bin/env bash
# Robustness audits R2 + R3 (PHASE2_PROTOCOL.md section 6) -- cache-off studies.
# Run AFTER the main collection completes (API contention), NOT before.
#
# R2: arms A and D replicated CACHE-OFF on split_p2_test_core.
#     Measures how much apparent agreement/diversity is the shared cache
#     (common random numbers) vs structural.
# R3: bare and the D arm, 3 independent repeats CACHE-OFF on the core.
#     Outcome flip rate + repair stability across repeats.
#
# Cost: ~125k rows cache-off (all fresh calls). At ~2 rows/s ≈ 17h.
set -eu
REPO="E:/projects/AI4AI-Harness"
export PARATERA_API_KEY="${PARATERA_API_KEY:?set PARATERA_API_KEY}"
export PYTHONPATH="$REPO/external/TTHE"

cd "$REPO/external/TTHE"
mkdir -p "$REPO/artifacts/phase2/audits"

# ---- manifests -----------------------------------------------------------
python - "$REPO" <<'PY'
import json, sys
from pathlib import Path
REPO = Path(sys.argv[1])
GEN = REPO / "artifacts" / "phase2" / "gen"
def names(arm, seeds=(0, 1, 2)):
    out = []
    for f in sorted(GEN.glob(f"{arm}_*_s[012].json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out += [r["harness"] for r in d["results"] if r["admitted"]]
    return out
A, D = names("A"), names("D")
(REPO / "artifacts/phase2/audits/manifest_R2_A.json").write_text(json.dumps(
    {"purpose": "R2: arm A cache-off on core", "n": len(A), "harnesses": A}))
(REPO / "artifacts/phase2/audits/manifest_R2_R3_D.json").write_text(json.dumps(
    {"purpose": "R2+R3: arm D cache-off x3 repeats on core", "n": len(D),
     "harnesses": D}))
print(f"A: {len(A)} harnesses, D: {len(D)} harnesses")
PY

# ---- R3 first: bare + D x 3 repeats (D repeats also serve R2's D arm) ----
for rep in 0 1 2; do
  OUT="$REPO/artifacts/phase2/audits/r3_rep${rep}.jsonl"
  if python -c "import json,sys;sys.exit(0 if __import__('pathlib').Path('$OUT').exists() else 1)" 2>/dev/null; then
    echo "[audit] rep $rep exists, skip"; continue
  fi
  H=$(python -c "
import json
d=json.load(open('$REPO/artifacts/phase2/audits/manifest_R2_R3_D.json'))
print(','.join(['bare']+d['harnesses']))")
  echo "[audit] R3 repeat $rep: bare + D arm, cache-off, core-400"
  python "$REPO/experiment/phase2/collect.py" \
    --split split_p2_test_core --harnesses "$H" --target GLM-5.3-Flash \
    --workers 32 --repeat "$rep" --no-cache --out "$OUT"
done

# ---- R2: arm A cache-off, single pass ----
OUT="$REPO/artifacts/phase2/audits/r2_A.jsonl"
if [ ! -f "$OUT" ]; then
  H=$(python -c "
import json
d=json.load(open('$REPO/artifacts/phase2/audits/manifest_R2_A.json'))
print(','.join(['bare']+d['harnesses']))")
  echo "[audit] R2: arm A, cache-off, core-400"
  python "$REPO/experiment/phase2/collect.py" \
    --split split_p2_test_core --harnesses "$H" --target GLM-5.3-Flash \
    --workers 32 --no-cache --out "$OUT"
fi

echo "=== audits R2+R3 complete ==="
