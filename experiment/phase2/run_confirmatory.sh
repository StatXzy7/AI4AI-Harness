#!/bin/bash
# Phase-II confirmatory evaluation pipeline.
# Runs collection → official re-scoring → primary table in one shot.
# Only executes when the frozen 18 paired (builder×seed) cells exist.

set -e
cd "$(dirname "$0")/../.."
export PYTHONPATH=external/TTHE:experiment

echo "[confirmatory] checking generation completeness"
paired=$(python experiment/phase2/yield_table.py 2>&1 | grep "paired.*cells" | awk '{print $NF}')
if [[ "$paired" -lt 18 ]]; then
  echo "[confirmatory] ABORT: only $paired/18 paired cells exist"
  echo "[confirmatory] wait for generation to complete all 6 builders × 3 seeds"
  exit 1
fi
echo "[confirmatory] $paired paired cells — proceeding"

# Build evaluation manifest (admits only populations with paired A/D)
echo "[confirmatory] building evaluation queue"
python experiment/phase2/queue_evaluation.py \
  --out artifacts/phase2/eval_manifest.json

manifest=$(cat artifacts/phase2/eval_manifest.json)
n_pops=$(echo "$manifest" | jq -r '.n_populations')
n_harnesses=$(echo "$manifest" | jq -r '.n_harnesses')
n_tasks=$(echo "$manifest" | jq -r '.n_tasks')
echo "[confirmatory] queue: $n_pops populations, $n_harnesses harnesses, $n_tasks tasks"

# Collection (dual-judged: legacy + official BIRD)
OUT=artifacts/phase2/outcomes_p2_test.parquet
if [[ -f "$OUT" ]]; then
  echo "[confirmatory] $OUT exists — skipping collection"
else
  echo "[confirmatory] running collection (this will take hours)"
  python experiment/phase2/collect.py \
    --manifest artifacts/phase2/eval_manifest.json \
    --target-model "GLM-5.3" \
    --out "$OUT" \
    --workers 16 \
    --no-cache
fi

# Official re-scoring (offline, zero API calls)
RESCORE=artifacts/phase2/rescore_p2_test.json
if [[ -f "$RESCORE" ]]; then
  echo "[confirmatory] $RESCORE exists — skipping re-score"
else
  echo "[confirmatory] re-scoring with official BIRD judge"
  python experiment/phase2/official_scorer.py rescore \
    --parquet "$OUT" \
    --out "$RESCORE" \
    --workers 16
fi

# Primary table
echo "[confirmatory] computing primary D−A contrast"
python experiment/phase2/outcome_table.py \
  --parquet "${OUT%.parquet}_official.parquet" \
  --out artifacts/phase2/table_primary.json

echo "[confirmatory] DONE — primary results in artifacts/phase2/table_primary.json"
cat artifacts/phase2/table_primary.json | jq '{
  n_paired_cells,
  primary_contrast,
  primary_metric,
  mean_delta_repair,
  mean_delta_headroom
}'
