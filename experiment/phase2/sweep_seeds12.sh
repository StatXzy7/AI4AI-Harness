#!/bin/bash
# Phase-II seeds 1 and 2 sweep
export PARATERA_API_KEY="${PARATERA_API_KEY:?Error: PARATERA_API_KEY environment variable not set}"
export PYTHONPATH="$PWD/external/TTHE:$PYTHONPATH"

SCRIPT="experiment/phase2/generate.py"
WORKERS=4

# Ensure output directory exists (absolute path to stay inside repo)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${REPO_ROOT}/artifacts/phase2/gen"
mkdir -p "$OUT_DIR"

BUILDERS=(glm qwen deepseek kimi minimax ernie)
ARMS=(A B C D)

run_job() {
    local builder=$1
    local arm=$2
    local seed=$3
    local logfile="${OUT_DIR}/p2_${arm}_${builder}_s${seed}.log"
    local outfile="${OUT_DIR}/p2_${arm}_${builder}_s${seed}.json"
    
    echo "[$(date +'%H:%M:%S')] Starting ${arm}/${builder}/seed${seed}"
    python "$SCRIPT" \
        --builder "$builder" \
        --arm "$arm" \
        --seed "$seed" \
        --out "$outfile" \
        > "$logfile" 2>&1
    
    if [ $? -eq 0 ]; then
        echo "[$(date +'%H:%M:%S')] ✓ ${arm}/${builder}/seed${seed} complete"
    else
        echo "[$(date +'%H:%M:%S')] ✗ ${arm}/${builder}/seed${seed} FAILED (see $logfile)"
    fi
}

export -f run_job
export SCRIPT OUT_DIR PARATERA_API_KEY PYTHONPATH

# Seeds 1 and 2
for seed in 1 2; do
    echo "=== Starting seed $seed sweep ==="
    for builder in "${BUILDERS[@]}"; do
        for arm in "${ARMS[@]}"; do
            echo "$builder $arm $seed"
        done
    done | parallel -j "$WORKERS" --colsep ' ' run_job {1} {2} {3}
done

echo "=== Seeds 1 and 2 complete ==="
