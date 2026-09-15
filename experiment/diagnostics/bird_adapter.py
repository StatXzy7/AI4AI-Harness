"""BIRD (phase2) archive adapter: thin wrapper over the canonical replay loader.

Reuses experiment.revision.replay (manifest-verified, duplicate-aware) instead of
reimplementing loading. Produces per-(builder, seed) x arm Populations. All
historical primary rows are repeat 0 / cache on -> S3 abstains by the frozen rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiment.revision import replay as rp  # noqa: E402
from experiment.diagnostics.core import Population  # noqa: E402


def load_bird() -> dict:
    """Return {cell_key: {arm: Population}} plus shared task/bare info."""
    manifests = {
        "AD": ROOT / "artifacts/phase2/primary_input_manifest.json",
        "BC": ROOT / "artifacts/phase2/bc_input_manifest.json",
    }
    groups, _inventory, audit = rp.load_sources(manifests)
    mem, _files, generation = rp.membership()
    # BC collections cover the stratified 400-task CORE subsample; AD covers the
    # full 1169-task test split. Use the core intersection so every arm's rows
    # exist; AD-bare rows outside the core are simply not selected.
    split_path = ROOT / "experiment/phase2" / "split_p2_test_core.json"
    tasks = rp.task_ids(split_path)
    # restrict to tasks present in BOTH collections (bare source = AD)
    def has_all(rows, hs):
        return all((rp.TARGET, h, t, 0, False) in rows for t in tasks for h in hs)
    ad_rows = groups["AD"]
    tasks = [t for t in tasks if (rp.TARGET, "bare", t, 0, False) in ad_rows]
    dbs = {}
    for tk in tasks:
        db = tk.split("#")[0]
        dbs[tk] = {"stratum": db}
    bare_vec = rp.vector(groups["AD"], "bare", tasks)
    out = {}
    for (builder, seed) in sorted({(b, s) for b, s, _ in mem}):
        for arm in "ABCD":
            names = mem[(builder, seed, arm)]
            rows = groups["AD" if arm in "AD" else "BC"]
            members = ["bare"] + names
            Y = np.vstack([bare_vec] + [rp.vector(rows, h, tasks) for h in names])
            hashes = []
            for h in members:
                hs = {r["code_hash"] for (tg, hh, *_), r in rows.items() if hh == h}
                hashes.append(sorted(hs)[0] if len(hs) == 1 else "CONFLICT:" + ",".join(sorted(hs)))
            out[(builder, seed, arm)] = Population(
                member_ids=members, source_hashes=hashes, tasks=tasks, Y=Y,
                condition={"target": rp.TARGET, "repeat": 0, "no_cache": False},
                has_bare=True, dev_task_ids=[], task_meta=dbs, calls={})
    return {"cells": out, "tasks": tasks, "audit": audit, "generation": generation}
