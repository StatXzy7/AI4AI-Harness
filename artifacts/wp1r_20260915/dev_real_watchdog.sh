#!/bin/bash
# dev_real watchdog: reconcile+relaunch on stop until 2700 cells done.
cd /e/projects/AI4AI-Harness || exit 1
KEY=$(grep '^PARATERA_API_KEY=' experiment/.env_tthe | cut -d= -f2)
export PARATERA_API_KEY="$KEY"
EXP=2700
for i in $(seq 1 2000); do
  ts=$(date -u +%FT%TZ)
  reserved=$(python -c "import json;print(json.load(open('artifacts/wp1r_20260915/global_budget.json'))['reserved'])" 2>/dev/null)
  if [ -n "$reserved" ] && [ "$reserved" -ge 58000 ]; then
    echo "$ts budget guard: reserved=$reserved, not relaunching" >> artifacts/wp1r_20260915/dev_real_watchdog.log
    break
  fi
  running=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*configs/dev_real.json*' } | Measure-Object).Count" 2>/dev/null)
  done_cells=$(python - <<'PYEOF'
import sqlite3, os
p = 'artifacts/wp1r_20260915/dev_real/ledger.sqlite'
if not os.path.exists(p):
    print(0); raise SystemExit
conn = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
done = conn.execute("SELECT COUNT(*) FROM tasks WHERE result IS NOT NULL").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
# complete when every scheduled task has a result AND no new tasks can appear:
# the parent exits by itself when the schedule is exhausted; use total==done
# only as a liveness signal here.
print(done)
PYEOF
)
  if [ "$done_cells" -ge "$EXP" ]; then
    echo "$ts dev_real complete ($done_cells cells)" >> artifacts/wp1r_20260915/dev_real_watchdog.log
    break
  fi
  if [ "$running" = "0" ]; then
    echo "$ts dev_real not running at $done_cells/$EXP cells; reconcile+relaunch" >> artifacts/wp1r_20260915/dev_real_watchdog.log
    python -m experiment.revision.reconcile_cell --arm dev_real >> artifacts/wp1r_20260915/dev_real_watchdog.log 2>&1
    nohup python -m experiment.revision.fresh_collect_math \
      --config "artifacts/wp1r_20260915/configs/dev_real.json" \
      >> "artifacts/wp1r_20260915/dev_real_parent.log" 2>&1 &
  fi
  sleep 600
done
echo "$(date -u +%FT%TZ) dev_real watchdog exiting" >> artifacts/wp1r_20260915/dev_real_watchdog.log
