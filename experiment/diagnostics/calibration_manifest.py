#!/usr/bin/env python3
"""Write a machine-readable manifest for the v3 calibration run.

Captures command line, git HEAD, code hashes, seed/replication counts, and
the calibration_results.json hash, so the paper table's provenance is
auditable without re-running the grid.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/diagnostics/calibration_v3"
CODE = [
    "experiment/diagnostics/calibration_sim.py",
    "experiment/diagnostics/calibration_stats.py",
    "experiment/diagnostics/calibration_run.py",
    "experiment/diagnostics/ccomp_v3.py",
    "experiment/diagnostics/core.py",
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(args: str) -> str:
    try:
        return subprocess.run(["git"] + args.split(), cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unavailable"


def main() -> None:
    results = json.loads((ART / "calibration_results.json").read_text("utf-8"))
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "python -m experiment.diagnostics.calibration_run --n-reps 300",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_head": git("rev-parse HEAD"),
        "git_status_dirty": bool(git("status --porcelain")),
        "code_sha256": {c: sha256(ROOT / c) for c in CODE},
        "results_sha256": sha256(ART / "calibration_results.json"),
        "n_results": len(results["results"]),
        "grid": results["meta"],
    }
    out = ART / "calibration_manifest.json"
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
