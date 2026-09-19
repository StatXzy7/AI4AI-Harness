#!/bin/bash
# Recovery loop for dev_real_cont: reconcile -> relaunch -> verify progress.
cd /e/projects/AI4AI-Harness || exit 1
EXPECTED=2700
for i in $(seq 1 600); do
  ts=$(date -u +%FT%TZ)
  reserved=$(python -c "import json;print(json.load(open('artifacts/wp1r_20260915/global_budget.json'))['reserved'])" 2>/dev/null)
  if [ -n "$reserved" ] && [ "$reserved" -ge 58000 ]; then
    echo "$ts budget guard hit ($reserved); stopping" >> artifacts/wp1r_20260915/recovery_dev.log
    break
  fi
  if [ -f artifacts/wp1r_20260915/dev_real_cont/SEALED.json ]; then
    echo "$ts dev_real_cont SEALED" >> artifacts/wp1r_20260915/recovery_dev.log
    break
  fi
  running=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*dev_real_cont.json*' } | Measure-Object).Count" 2>/dev/null)
  done_cells=$(python - <<PYEOF
import sqlite3
conn = sqlite3.connect('file:artifacts/wp1r_20260915/dev_real_cont/ledger.sqlite?mode=ro', uri=True)
print(conn.execute("SELECT COUNT(*) FROM tasks WHERE result IS NOT NULL").fetchone()[0])
PYEOF
)
  if [ "$done_cells" -ge "$EXPECTED" ]; then
    echo "$ts dev_real_cont all cells done ($done_cells); final seal pass" >> artifacts/wp1r_20260915/recovery_dev.log
    export PARATERA_API_KEY=$(grep '^PARATERA_API_KEY=' experiment/.env_tthe | cut -d= -f2)
    python -m experiment.revision.fresh_collect_math --config artifacts/wp1r_20260915/configs/dev_real_cont.json >> artifacts/wp1r_20260915/dev_real_cont_parent.log 2>&1 || true
    python -m experiment.revision.reconcile_cell --arm dev_real_cont >> artifacts/wp1r_20260915/recovery_dev.log 2>&1 || true
    python -m experiment.revision.fresh_collect_math --config artifacts/wp1r_20260915/configs/dev_real_cont.json >> artifacts/wp1r_20260915/dev_real_cont_parent.log 2>&1 || true
    continue
  fi
  if [ "$running" = "0" ]; then
    echo "$ts arm down at $done_cells/$EXPECTED; reconcile+relaunch" >> artifacts/wp1r_20260915/recovery_dev.log
    python -m experiment.revision.reconcile_cell --arm dev_real_cont >> artifacts/wp1r_20260915/recovery_dev.log 2>&1
    export PARATERA_API_KEY=$(grep '^PARATERA_API_KEY=' experiment/.env_tthe | cut -d= -f2)
    nohup python -m experiment.revision.fresh_collect_math \
      --config artifacts/wp1r_20260915/configs/dev_real_cont.json \
      >> artifacts/wp1r_20260915/dev_real_cont_parent.log 2>&1 &
  fi
  sleep 600
done
echo "$(date -u +%FT%TZ) dev recovery loop exiting" >> artifacts/wp1r_20260915/recovery_dev.log
