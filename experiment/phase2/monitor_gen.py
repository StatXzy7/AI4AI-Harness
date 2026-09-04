#!/usr/bin/env python3
"""Monitor Phase-II generation progress."""
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "artifacts" / "phase2" / "gen"

while True:
    logs = list(GEN.glob("[ABCD]_*_s[012].json"))
    by_seed = {0: 0, 1: 0, 2: 0}
    for f in logs:
        parts = f.stem.split("_")
        seed = int(parts[-1][1:])
        by_seed[seed] += 1

    total = len(logs)
    target = 6 * 4 * 3  # 6 builders × 4 arms × 3 seeds

    print(f"\r[gen] {total}/{target} logs | seed 0: {by_seed[0]}/24 | "
          f"seed 1: {by_seed[1]}/24 | seed 2: {by_seed[2]}/24", end="", flush=True)

    if total >= target:
        print("\n[gen] COMPLETE — all 72 runs finished")
        break

    time.sleep(30)
