#!/bin/bash
# Phase-II generation: parallel execution across builders and arms
export PARATERA_API_KEY="${PARATERA_API_KEY:?Error: PARATERA_API_KEY environment variable not set}"
export PYTHONPATH="$PWD/external/TTHE:$PYTHONPATH"

SCRIPT="experiment/phase2/generate.py"
WORKERS=4
SEED=0

# Ensure output directory exists
mkdir -p artifacts/phase2/gen

# All 24 combinations (6 builders × 4 arms)
BUILDERS=(glm qwen deepseek kimi minimax ernie)
ARMS=(A B C D)

run_job() {
    local builder=$1
    local arm=$2
    local logfile="artifacts/phase2/gen/p2_${arm}_${builder}_s${SEED}.log"
    
    echo "[$(date +'%H:%M:%S')] Starting ${arm}/${builder}/seed${SEED}"
    python "$SCRIPT" \
        --builder "$builder" \
        --arm "$arm" \
        --seed "$SEED" \
        --out "artifacts/phase2/gen/p2_${arm}_${builder}_s${SEED}.json" \
        > "$logfile" 2>&1
    
    if [ $? -eq 0 ]; then
        echo "[$(date +'%H:%M:%S')] ✓ ${arm}/${builder}/seed${SEED} complete"
    else
        echo "[$(date +'%H:%M:%S')] ✗ ${arm}/${builder}/seed${SEED} FAILED (see $logfile)"
    fi
}

export -f run_job
export SCRIPT SEED PARATERA_API_KEY PYTHONPATH

# Run in parallel
for builder in "${BUILDERS[@]}"; do
    for arm in "${ARMS[@]}"; do
        echo "$builder $arm"
    done
done | parallel -j "$WORKERS" --colsep ' ' run_job {1} {2}

echo "=== All jobs submitted ==="
