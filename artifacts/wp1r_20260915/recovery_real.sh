#!/bin/bash
# Recovery loop for eval_real_cont: reconcile -> relaunch -> verify progress.
# Exits when the arm seals (10800 cells with results + SEALED.json) or on
# repeated failures. Budget guard: stop relaunching at 44,500 reserved.
cd /e/projects/AI4AI-Harness || exit 1
EXPECTED=10800
for i in $(seq 1 400); do
  ts=$(date -u +%FT%TZ)
  reserved=$(python -c "import json;print(json.load(open('artifacts/wp1r_20260915/global_budget.json'))['reserved'])" 2>/dev/null)
  if [ -n "$reserved" ] && [ "$reserved" -ge 44500 ]; then
    echo "$ts budget guard hit ($reserved); stopping" >> artifacts/wp1r_20260915/recovery.log
    break
  fi
  # seal check
  if [ -f artifacts/wp1r_20260915/eval_real_cont/SEALED.json ]; then
    echo "$ts eval_real_cont SEALED" >> artifacts/wp1r_20260915/recovery.log
    break
  fi
  running=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*eval_real_cont.json*' } | Measure-Object).Count" 2>/dev/null)
  done_cells=$(python - <<PYEOF
import sqlite3
conn = sqlite3.connect('file:artifacts/wp1r_20260915/eval_real_cont/ledger.sqlite?mode=ro', uri=True)
print(conn.execute("SELECT COUNT(*) FROM tasks WHERE result IS NOT NULL").fetchone()[0])
PYEOF
)
  if [ "$done_cells" -ge "$EXPECTED" ]; then
    echo "$ts eval_real_cont all cells done ($done_cells); run seal" >> artifacts/wp1r_20260915/recovery.log
    python -m experiment.revision.fresh_collect_math --config artifacts/wp1r_20260915/configs/eval_real_cont.json >> artifacts/wp1r_20260915/eval_real_cont_parent.log 2>&1
    continue
  fi
  if [ "$running" = "0" ]; then
    echo "$ts arm down at $done_cells/$EXPECTED; reconcile+relaunch" >> artifacts/wp1r_20260915/recovery.log
    rm -rf artifacts/wp1r_20260915/eval_real_cont/workers/*.orphan 2>/dev/null; python -m experiment.revision.reconcile_cell --arm eval_real_cont >> artifacts/wp1r_20260915/recovery.log 2>&1|| true
    export PARATERA_API_KEY=$(grep '^PARATERA_API_KEY=' experiment/.env_tthe | cut -d= -f2)
    nohup python -m experiment.revision.fresh_collect_math \
      --config artifacts/wp1r_20260915/configs/eval_real_cont.json \
      >> artifacts/wp1r_20260915/eval_real_cont_parent.log 2>&1 &
  fi
  sleep 600
done
echo "$(date -u +%FT%TZ) recovery loop exiting" >> artifacts/wp1r_20260915/recovery.log
