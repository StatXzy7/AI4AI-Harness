#!/usr/bin/env bash
# One-shot status: counts only, no outcome data.
R="E:/projects/AI4AI-Harness"
s2=$(ls "$R"/artifacts/phase2/gen/[ABCD]_*_s2.json 2>/dev/null | wc -l)
ad=$(( $(wc -l < "$R"/artifacts/phase2/ad_shard0.jsonl 2>/dev/null || echo 0)
     + $(wc -l < "$R"/artifacts/phase2/ad_shard1.jsonl 2>/dev/null || echo 0)
     + $(wc -l < "$R"/artifacts/phase2/ad_shard2.jsonl 2>/dev/null || echo 0)
     + $(wc -l < "$R"/artifacts/phase2/ad_shard3.jsonl 2>/dev/null || echo 0)
     + $(wc -l < "$R"/artifacts/phase2/ad_s2.jsonl 2>/dev/null || echo 0) ))
bc=$(wc -l < "$R"/artifacts/phase2/run_BC_core.jsonl 2>/dev/null || echo 0)
echo "seed2=$s2/24  AD=$ad/145548  BC=$bc/83580"
