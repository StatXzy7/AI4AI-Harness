#!/bin/bash
set -e
export PARATERA_API_KEY=sk-8YAaA4ry1ToVzXRdq331OA
export PYTHONPATH=external/TTHE:experiment
cd external/TTHE
todo=$(mktemp)
for seed in 1 2; do
  for builder in glm qwen deepseek kimi minimax ernie; do
    for arm in A B C D; do
      log="../../artifacts/phase2/gen/${arm}_${builder}_s${seed}.json"
      [[ -f "$log" ]] || echo "$arm $builder $seed $log" >> "$todo"
    done
  done
done
total=$(wc -l < "$todo")
echo "[parallel_gen] $total runs queued"
cat "$todo" | xargs -n4 -P4 bash -c '
  arm=$1 builder=$2 seed=$3 log=$4
  echo "[start] $arm/$builder/s$seed"
  timeout 3600 python ../../experiment/phase2/generate.py \
    --builder "$builder" --arm "$arm" --seed "$seed" --k 8 --workers 4 --log "$log" \
    >/dev/null 2>&1 && echo "[done] $log" || echo "[fail] $log"
' _
rm -f "$todo"
