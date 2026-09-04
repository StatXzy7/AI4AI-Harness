#!/usr/bin/env bash
# One-shot status: counts only, no outcome data.
R="E:/projects/AI4AI-Harness"
s2=$(ls "$R"/artifacts/phase2/gen/[ABCD]_*_s2.json 2>/dev/null | wc -l)
ad=$(wc -l < "$R"/artifacts/phase2/run_primary_AD.jsonl 2>/dev/null || echo 0)
bc=$(wc -l < "$R"/artifacts/phase2/run_BC_core.jsonl 2>/dev/null || echo 0)
procs=$(ps -ef 2>/dev/null | grep -c "[c]ollect.py\|[g]enerate.py\|[g]en_seed2")
eta=$(python -c "print(round((139080-$ad)/600,1))" 2>/dev/null || echo "?")
echo "seed2_units=$s2/24  AD_rows=$ad/139080  BC_rows=$bc/56420  procs=$procs  AD_eta_h=$eta"
