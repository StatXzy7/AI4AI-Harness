#!/usr/bin/env bash
# Watches seed-2 generation and primary collection; appends seed-2 A/D harnesses to the
# collection queue when they land. NO metric computation happens here.
set -u
REPO="E:/projects/AI4AI-Harness"
GEN="$REPO/artifacts/phase2/gen"
RUN="$REPO/artifacts/phase2/run_primary_AD.jsonl"
LOG="$REPO/artifacts/phase2/watchdog.log"

log(){ echo "[$(date +'%H:%M:%S')] $*" >> "$LOG"; }

while true; do
    s2=$(ls "$GEN"/[ABCD]_*_s2.json 2>/dev/null | wc -l)
    rows=$(wc -l < "$RUN" 2>/dev/null || echo 0)
    log "seed2=$s2/24 collection_rows=$rows"
    if [[ $s2 -ge 24 ]]; then
        log "seed-2 generation COMPLETE (24/24)"
        break
    fi
    sleep 300
done

# append seed-2 A/D harnesses to the collection
python - <<'PY' >> "$LOG" 2>&1
import json
from pathlib import Path
GEN = Path("E:/projects/AI4AI-Harness/artifacts/phase2/gen")
new = []
for f in sorted(GEN.glob("[AD]_*_s2.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    new += [r["harness"] for r in d["results"] if r["admitted"]]
Path("E:/projects/AI4AI-Harness/artifacts/phase2/manifest_AD_s2.json").write_text(
    json.dumps({"n_harnesses": len(new), "harnesses": new}, indent=1))
print(f"seed-2 A/D harnesses to collect: {len(new)}")
print(",".join(new))
PY
log "watchdog exiting; run the seed-2 append manually per the printed harness list"
