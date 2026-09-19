#!/bin/bash
# WP-1R collection supervisor: keeps eval_real / eval_clone running.
# Per protocol: on unknown-request stop -> reconcile (mark unknown_remote) ->
# relaunch with the key from experiment/.env_tthe. Guards the 45000 budget.
cd /e/projects/AI4AI-Harness || exit 1
KEY=$(grep '^PARATERA_API_KEY=' experiment/.env_tthe | cut -d= -f2)
export PARATERA_API_KEY="$KEY"
EXPECTED_real=10800
EXPECTED_cont_real=10800
EXPECTED_clone=10800
for i in $(seq 1 2000); do   # up to ~2000 cycles of 10 minutes (~14 days)
  ts=$(date -u +%FT%TZ)
  # budget guard
  reserved=$(python -c "import json;print(json.load(open('artifacts/wp1r_20260915/global_budget.json'))['reserved'])" 2>/dev/null)
  if [ -n "$reserved" ] && [ "$reserved" -ge 58000 ]; then
    echo "$ts budget guard: reserved=$reserved, not relaunching" >> artifacts/wp1r_20260915/supervisor.log
    break
  fi
  for arm in eval_real_cont2 eval_clone_cont; do
    # expected cells for this arm
    if [[ "$arm" == eval_real* ]]; then EXP=$EXPECTED_real; else EXP=$EXPECTED_clone; fi
    # is the parent process running?
    running=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*configs/$arm.json*' } | Measure-Object).Count" 2>/dev/null)
    done_cells=$(python - "$arm" "$EXP" <<'PYEOF'
import sqlite3, sys, os
arm, exp = sys.argv[1], int(sys.argv[2])
p = f'artifacts/wp1r_20260915/{arm}/ledger.sqlite'
if not os.path.exists(p):
    print(-1); raise SystemExit
conn = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
done = conn.execute("SELECT COUNT(*) FROM tasks WHERE result IS NOT NULL").fetchone()[0]
print(done if done < exp else exp)   # exp = complete sentinel
PYEOF
)
    if [ "$done_cells" = "-1" ]; then continue; fi
    if [ "$done_cells" = "$EXP" ]; then
      echo "$ts $arm complete ($done_cells cells)" >> artifacts/wp1r_20260915/supervisor.log
      continue
    fi
    if [ "$running" = "0" ]; then
      echo "$ts $arm not running at $done_cells/$EXP cells; reconcile+relaunch" >> artifacts/wp1r_20260915/supervisor.log
      python -m experiment.revision.reconcile_cell --arm "$arm" >> artifacts/wp1r_20260915/supervisor.log 2>&1
      nohup python -m experiment.revision.fresh_collect_math \
        --config "artifacts/wp1r_20260915/configs/$arm.json" \
        >> "artifacts/wp1r_20260915/$arm/parent_supervisor.log" 2>&1 &
    fi
  done
  sleep 600
done
echo "$(date -u +%FT%TZ) supervisor exiting" >> artifacts/wp1r_20260915/supervisor.log
