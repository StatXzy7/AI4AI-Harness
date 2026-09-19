#!/bin/bash
# dev_real continuation watchdog: reconcile+relaunch on stop until 2700.
cd /e/projects/AI4AI-Harness || exit 1
KEY=$(grep '^PARATERA_API_KEY=' experiment/.env_tthe | cut -d= -f2)
export PARATERA_API_KEY="$KEY"
EXP=2700
for i in $(seq 1 2000); do
  ts=$(date -u +%FT%TZ)
  reserved=$(python -c "import json;print(json.load(open('artifacts/wp1r_20260915/global_budget.json'))['reserved'])" 2>/dev/null)
  if [ -n "$reserved" ] && [ "$reserved" -ge 58000 ]; then
    echo "$ts budget guard: reserved=$reserved" >> artifacts/wp1r_20260915/dev_cont_watchdog.log
    break
  fi
  running=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*configs/dev_real_cont2.json*' -and \$_.CommandLine -notlike '*--worker*' } | Measure-Object).Count" 2>/dev/null)
  done_cells=$(python - <<'PYEOF'
import sqlite3, os, json
def cells(p):
    if not os.path.exists(p): return set()
    c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
    rows = c.execute('SELECT result FROM tasks WHERE result IS NOT NULL').fetchall()
    c.close()
    return {(json.loads(v)['harness'], json.loads(v)['task'],
             json.loads(v)['repeat']) for (v,) in rows}
names = ['dev_real','dev_real_cont','dev_real_cont2']
u = set()
for n in names:
    u |= cells(f'artifacts/wp1r_20260915/{n}/ledger.sqlite')
print(len(u))
PYEOF
)
  if [ "$done_cells" -ge "$EXP" ]; then
    echo "$ts dev_real merged complete ($done_cells)" >> artifacts/wp1r_20260915/dev_cont_watchdog.log
    break
  fi
  if [ "$running" = "0" ]; then
    echo "$ts dev_real_cont2 not running at $done_cells/$EXP; reconcile+restore+relaunch" >> artifacts/wp1r_20260915/dev_cont_watchdog.log
    # reconcile first (never-started / http_unknown), then recover answers
    # preserved on closed requests whose only defect is missing usage.
    python -m experiment.revision.reconcile_cell --arm dev_real_cont2 >> artifacts/wp1r_20260915/dev_cont_watchdog.log 2>&1
    python -m experiment.revision.restore_usage_unknown dev_real_cont2 >> artifacts/wp1r_20260915/dev_cont_watchdog.log 2>&1
    nohup python -m experiment.revision.fresh_collect_math \
      --config "artifacts/wp1r_20260915/configs/dev_real_cont2.json" \
      >> "artifacts/wp1r_20260915/dev_real_cont2_parent.log" 2>&1 &
  fi
  sleep 120
done
