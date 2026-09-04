#!/usr/bin/env bash
# Phase-II generation sweep. Arms A-D are frozen (PHASE2_SAP.md); arm E is run separately
# because its admission rule is still under discussion.
#
# Every run gets the SAME raw budget (R=3 per slot), so arms differ only in admission.
# Runs are sequential per builder to stay inside provider rate limits, parallel across builders.
set -u
cd "$(dirname "$0")/../../external/TTHE" || exit 1
export PARATERA_API_KEY="${PARATERA_API_KEY:?set PARATERA_API_KEY}"
export PYTHONPATH=".:E:/projects/AI4AI-Harness/experiment"

GEN=E:/projects/AI4AI-Harness/experiment/phase2/generate.py
LOGDIR=E:/projects/AI4AI-Harness/artifacts/phase2/gen
mkdir -p "$LOGDIR"

BUILDERS="${BUILDERS:-deepseek qwen glm}"
ARMS="${ARMS:-A B C D}"
SEEDS="${SEEDS:-0 1 2}"

run_builder() {
  local b=$1
  for seed in $SEEDS; do
    for arm in $ARMS; do
      local log="$LOGDIR/${arm}_${b}_s${seed}.json"
      if [ -f "$log" ]; then echo "[skip] $arm/$b/s$seed already done"; continue; fi
      echo "[run ] $arm/$b/s$seed"
      timeout 3600 python "$GEN" --builder "$b" --arm "$arm" --seed "$seed" \
        --k 8 --workers 4 --log "$log" >> "$LOGDIR/${b}.log" 2>&1 \
        || echo "[FAIL] $arm/$b/s$seed (see $LOGDIR/${b}.log)"
    done
  done
  echo "[done] builder $b"
}

for b in $BUILDERS; do run_builder "$b" & done
wait
echo "=== sweep complete ==="
for f in "$LOGDIR"/*.json; do
  python - "$f" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
try:
    d = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    sys.exit()
if "K_admitted" not in d:
    sys.exit()
print(f"  {d['arm']}/{d['builder']}/s{d['seed']}: K={d['K_admitted']}/{d['n_slots']} "
      f"nv={d['p_neutral_valid']} mech={d['p_mechanism_pass']}")
PY
done
