"""Phase-II evaluation queue builder.

Reads generation logs, emits a collection manifest for the confirmatory matrix.
Enforces: (1) only admitted harnesses, (2) every (builder,seed) cell has both A and D
present or both absent (paired design), (3) frozen split_p2_test only.

Usage:
    python experiment/phase2/queue_evaluation.py --out artifacts/phase2/eval_manifest.json
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "artifacts" / "phase2" / "gen"
SPLITS = ROOT / "experiment" / "phase2" / "splits"


def load_populations():
    """Returns {(arm, builder, seed): [harness_ids]}."""
    pops = collections.defaultdict(list)
    for f in sorted(GEN.glob("[ABCDE]_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "K_admitted" not in d or d["K_admitted"] == 0:
            continue
        for r in d["results"]:
            if r["admitted"]:
                pops[(d["arm"], d["builder"], d["seed"])].append(r["harness"])
    return dict(pops)


def build_manifest(pops: dict, split_name: str = "split_p2_test.json") -> dict:
    split = json.loads((SPLITS / split_name).read_text(encoding="utf-8"))
    tasks = split["by_db"]
    n_tasks = sum(len(v) for v in tasks.values())

    # Enforce pairing: both A and D present or both absent
    cells = {(b, s) for (arm, b, s) in pops if arm in ("A", "D")}
    paired = {(b, s) for (b, s) in cells
              if ("A", b, s) in pops and ("D", b, s) in pops}

    manifest = {"split": split_name, "n_tasks": n_tasks, "tasks": tasks, "populations": []}

    # All arms, but only paired builders/seeds for A and D
    for (arm, builder, seed), harnesses in sorted(pops.items()):
        if arm in ("A", "D") and (builder, seed) not in paired:
            continue
        manifest["populations"].append({
            "arm": arm, "builder": builder, "seed": seed,
            "K": len(harnesses), "harness_ids": harnesses
        })

    manifest["n_paired_cells"] = len(paired)
    manifest["n_populations"] = len(manifest["populations"])
    manifest["n_harnesses"] = sum(len(p["harness_ids"]) for p in manifest["populations"])
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    pops = load_populations()
    manifest = build_manifest(pops)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[queue] {manifest['n_populations']} populations, {manifest['n_harnesses']} harnesses")
    print(f"[queue] {manifest['n_paired_cells']} paired (builder×seed) cells with A and D")
    print(f"[queue] {manifest['n_tasks']} tasks from {manifest['split']}")
    print(f"[queue] wrote {a.out}")


if __name__ == "__main__":
    main()
