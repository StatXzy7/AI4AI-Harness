"""Small offline checks for the 2026-09-15 insight revision.

This file deliberately contains no provider calls.  It verifies the two
interpretive counterexamples, the two-action conditional-value identity, and
records a compact inventory of the frozen Phase-II inputs.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "revision_20260915" / "insight_analysis"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def counterexamples() -> dict:
    # A: changing magnitudes without changing the best action gives C_Z = 0.
    q_a = {"h0": (0.90, 0.60), "h1": (0.80, 0.20)}
    fixed_a = max(sum(v) / 2 for v in q_a.values())
    oracle_a = sum(max(q_a[h][z] for h in q_a) for z in range(2)) / 2
    # B: independent execution has positive residual coverage but h0 is the
    # best pre-execution single action.
    p0, p1 = 0.8, 0.7
    residual_b = (1 - p0) * p1
    reverse_b = p0 * (1 - p1)
    oracle_b = 1 - (1 - p0) * (1 - p1)
    return {
        "counterexample_A": {
            "status": "constructed, not measured",
            "q_h_by_task": q_a,
            "best_fixed": fixed_a,
            "oracle": oracle_a,
            "C_Z": oracle_a - fixed_a,
            "interpretation": "h0 is best on every task; heterogeneity does not create routing value",
        },
        "counterexample_B": {
            "status": "constructed, not measured",
            "p_h": {"h0": p0, "h1": p1},
            "residual_coverage_h1_over_h0": residual_b,
            "reverse_disagreement": reverse_b,
            "ex_post_oracle": oracle_b,
            "best_fixed": p0,
            "C_Z": 0.0,
            "cost_note": "two executions cost more than one; oracle is ex-post",
        },
    }


def identity_check() -> dict:
    # Exhaustive finite checks over bounded rational-looking values plus a
    # deterministic grid make the algebra executable without simulation.
    grid = [0.0, 0.2, 0.5, 0.8, 1.0]
    checked = 0
    max_abs = 0.0
    for q0 in grid:
        for q1 in grid:
            for r0 in grid:
                for r1 in grid:
                    vals0 = [q0, r0]
                    vals1 = [q1, r1]
                    lhs = sum(max(a, b) for a, b in zip(vals0, vals1)) / 2 - max(sum(vals0) / 2, sum(vals1) / 2)
                    d = [b - a for a, b in zip(vals0, vals1)]
                    rhs = (sum(abs(x) for x in d) / 2 - abs(sum(d) / 2)) / 2
                    max_abs = max(max_abs, abs(lhs - rhs))
                    checked += 1
    assert max_abs < 1e-12
    return {
        "checked_grid_cases": checked,
        "max_absolute_error": max_abs,
        "identity": "E[max(q0,q1)]-max(E[q0],E[q1])=(E|d|-|Ed|)/2",
        "scope": "two actions, common resource/cost scale, Z excludes post-answer information",
    }


def file_inventory() -> dict:
    manifests = [ROOT / "artifacts" / "phase2" / "primary_input_manifest.json",
                 ROOT / "artifacts" / "phase2" / "bc_input_manifest.json"]
    files = []
    for manifest in manifests:
        obj = json.loads(manifest.read_text(encoding="utf-8"))
        for item in obj["files"]:
            p = ROOT / "artifacts" / "phase2" / item["file"]
            rows = 0
            keys: set[tuple] = set()
            conflicts: set[tuple] = set()
            values: dict[tuple, int] = {}
            repeats, cache, targets, providers = set(), set(), set(), set()
            costs = Counter()
            if p.exists():
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rows += 1
                    key = (r.get("harness_id"), r.get("task_id"), r.get("repeat", 0))
                    val = r.get("official_correct")
                    if key in values and values[key] != val:
                        conflicts.add(key)
                    values.setdefault(key, val)
                    keys.add(key)
                    repeats.add(r.get("repeat", 0)); cache.add(bool(r.get("no_cache", False)))
                    targets.add(r.get("target")); providers.add(r.get("provider") or r.get("model"))
                    for field in ("latency_ms", "n_llm_calls", "n_execs", "cost", "prompt_tokens", "completion_tokens"):
                        if field in r and r[field] is not None:
                            costs[field] += 1
            files.append({
                "manifest": manifest.name,
                "file": item["file"],
                "sha256_16_manifest": item["sha256_16"],
                "sha256_16_observed": sha256(p)[:16] if p.exists() else None,
                "bytes_manifest": item["bytes"],
                "bytes_observed": p.stat().st_size if p.exists() else None,
                "rows_parsed": rows,
                "unique_harness_task_repeat": len(keys),
                "conflicting_duplicate_keys": len(conflicts),
                "repeats": sorted(repeats),
                "cache_modes": sorted(cache),
                "targets": sorted(x for x in targets if x),
                "provider_or_model_fields": sorted(x for x in providers if x),
                "non_null_cost_fields": dict(costs),
            })
    return {
        "files": files,
        "primary_and_bc_manifest_files": len(files),
        "manifest_hash_match_all": all(x["sha256_16_manifest"] == x["sha256_16_observed"] for x in files),
        "interpretation": "input inventory only; duplicate resolution remains the canonical first-write rule in completeness_report.json",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {
        "version": "insight-analysis-20260915-v1",
        "counterexamples": counterexamples(),
        "identity_check": identity_check(),
        "input_inventory": file_inventory(),
        "existing_w1": {
            "artifact": "artifacts/phase2/w1_selection.json",
            "status": "post-hoc exploratory; dev/test split by database halves; not a frozen selector",
            "relationship": "div-only is the existing greedy oracle-coverage baseline; no new algorithm is introduced",
        },
    }
    (OUT / "insight_analysis.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (OUT / "input_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["manifest", "file", "sha256_16_manifest", "sha256_16_observed", "bytes_manifest", "bytes_observed", "rows_parsed", "unique_harness_task_repeat", "conflicting_duplicate_keys", "repeats", "cache_modes", "targets", "provider_or_model_fields", "non_null_cost_fields"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in result["input_inventory"]["files"]:
            w.writerow({k: json.dumps(row[k], ensure_ascii=False) if isinstance(row[k], (list, dict)) else row[k] for k in fields})
    print(json.dumps({"out": str(OUT), "identity": result["identity_check"], "manifest_hash_match_all": result["input_inventory"]["manifest_hash_match_all"]}, indent=2))


if __name__ == "__main__":
    main()
