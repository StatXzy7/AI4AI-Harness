#!/usr/bin/env bash
# Phase-II seed-2 generation sweep — the ONLY generation entrypoint.
#
# Contract (per unified protocol):
#   * runs seed 2 ONLY; seeds 0/1 already exist and are never touched
#   * target JSON naming A_<builder>_s<seed>.json (matches monitor_gen/yield_table)
#   * --log is the flag generate.py actually defines (there is no --out)
#   * a target that already exists AND parses as valid JSON is skipped, never overwritten
#   * a target that exists but is corrupt (killed mid-write) is treated as absent and
#     regenerated into a temp file first
#   * generate.py writes to a .tmp.<pid> path; only on exit 0 is it renamed into place,
#     so a killed run can never leave a half-written final artifact (atomic publish)
#   * the runner function returns generate.py's exit code; the script exits non-zero if
#     any unit failed
#
# API key: read ONLY from the environment. Hardcoding one is a P0 incident.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PARATERA_API_KEY="${PARATERA_API_KEY:?set PARATERA_API_KEY in the environment (never hardcode it)}"
export PYTHONPATH="${REPO_ROOT}/external/TTHE:${PYTHONPATH:-}"
GEN_PY="${REPO_ROOT}/experiment/phase2/generate.py"
OUT_DIR="${REPO_ROOT}/artifacts/phase2/gen"
DRY_RUN="${DRY_RUN:-0}"
WORKERS=4
SEED=2
BUILDERS=(glm qwen deepseek kimi minimax ernie)
ARMS=(A B C D)

mkdir -p "$OUT_DIR"
cd "${REPO_ROOT}/external/TTHE"

valid_json() { python -c "import json,sys; json.load(open(sys.argv[1],encoding='utf-8'))" "$1" >/dev/null 2>&1; }

run_unit() {  # <arm> <builder>
    local arm="$1" builder="$2"
    local final="${OUT_DIR}/${arm}_${builder}_s${SEED}.json"
    local tmp="${OUT_DIR}/.tmp.${arm}_${builder}_s${SEED}.$$"

    if [[ -f "$final" ]] && valid_json "$final"; then
        echo "[skip] ${arm}/${builder}/s${SEED}: valid target exists"
        return 0
    fi
    if [[ -f "$final" ]]; then
        echo "[stale] ${arm}/${builder}/s${SEED}: corrupt partial file (killed run); regenerating"
    fi

    if [[ "$DRY_RUN" == "1" ]]; then
        echo "[dry ] would run: generate.py --builder ${builder} --arm ${arm} --seed ${SEED} -> ${final}"
        return 0
    fi

    echo "[run ] ${arm}/${builder}/s${SEED}"
    python "$GEN_PY" --builder "$builder" --arm "$arm" --seed "$SEED" \
        --k 8 --workers "$WORKERS" --log "$tmp"
    local rc=$?
    if [[ $rc -eq 0 ]] && valid_json "$tmp"; then
        mv -f "$tmp" "$final"   # atomic publish: rename is atomic on the same volume
        echo "[done] ${final}"
        return 0
    fi
    echo "[FAIL] ${arm}/${builder}/s${SEED} rc=${rc}; partial kept at ${tmp} for inspection" >&2
    return "$rc"
}

failures=0
for arm in "${ARMS[@]}"; do
    for builder in "${BUILDERS[@]}"; do
        run_unit "$arm" "$builder" || failures=$((failures+1))
    done
done

echo "=== seed-${SEED} sweep: $((24 - failures))/24 units OK, ${failures} failed ==="
exit "$failures"
