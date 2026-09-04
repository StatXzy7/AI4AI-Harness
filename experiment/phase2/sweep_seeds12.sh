#!/bin/bash
set -e
export PARATERA_API_KEY=sk-8YAaA4ry1ToVzXRdq331OA
export PYTHONPATH=external/TTHE:experiment
cd external/TTHE
for seed in 1 2; do
  for builder in glm qwen deepseek kimi minimax ernie; do
    for arm in A B C D; do
      log="../../artifacts/phase2/gen/${arm}_${builder}_s${seed}.json"
      if [[ -f "$log" ]]; then echo "[skip] $log exists"; continue; fi
      echo "[gen] arm=$arm builder=$builder seed=$seed"
      timeout 3600 python ../../experiment/phase2/generate.py \
        --builder "$builder" --arm "$arm" --seed "$seed" --k 8 --workers 4 \
        --log "$log" 2>&1 | tail -4
    done
  done
done
