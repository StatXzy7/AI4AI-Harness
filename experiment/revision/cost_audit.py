"""Describe logged logical-call costs and missing token accounting, canonically."""
import json

import numpy as np

from experiment.revision.replay import P2, ROOT, digest, load_sources, membership, task_ids


def summarize(group, mem, arm, tasks):
    cells, records = [], []
    for (builder, seed, a), hs in sorted(mem.items()):
        if a != arm:
            continue
        rows = [group["GLM-5.3-Flash", h, t, 0, False] for h in hs for t in tasks]
        for row in rows:
            for key in ("n_llm_calls", "n_execs", "latency_ms"):
                value = row[key]
                if not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
                    raise ValueError(f"invalid recorded cost: {builder}/{seed}/{key}")
        records.extend(rows)
        cell = {"builder": builder, "seed": seed, "K_candidate": len(hs), "n_rows": len(rows),
                "logical_solver_calls_per_task_population": sum(r["n_llm_calls"] for r in rows)/len(tasks)}
        for key in ("n_llm_calls", "n_execs", "latency_ms", "official_correct"):
            cell["mean_per_candidate_" + key] = float(np.mean([r[key] for r in rows])) if rows else None
        cell["multicall_fraction"] = float(np.mean([r["n_llm_calls"] > 1 for r in rows])) if rows else None
        cells.append(cell)
    return {"n_cells": len(cells), "n_rows": len(records),
            "n_harnesses": sum(c["K_candidate"] for c in cells),
            "total_logged_solver_calls": sum(r["n_llm_calls"] for r in records),
            "logical_solver_calls_per_task_population_cell_mean": float(np.mean([
                c["logical_solver_calls_per_task_population"] for c in cells])),
            "row_weighted_multicall_fraction": float(np.mean([r["n_llm_calls"] > 1 for r in records])) if records else None,
            "row_weighted_mean_solver_calls": float(np.mean([r["n_llm_calls"] for r in records])) if records else None,
            "rows_with_token_usage_field": sum(any(k in r for k in (
                "usage", "prompt_tokens", "completion_tokens", "input_tokens", "output_tokens", "total_tokens")) for r in records),
            "per_cell": cells}


def main():
    groups, inventory, _ = load_sources({"AD": P2 / "primary_input_manifest.json",
                                         "BC": P2 / "bc_input_manifest.json"})
    mem, generation, _ = membership()
    split = ROOT / "experiment/phase2/split_p2_test_core.json"
    tasks = task_ids(split)
    report = {"version": "cost-audit-20260910-v1", "n_tasks": len(tasks),
              "scope": "core400 candidates, bare excluded; logical trace counts are not provider-billed API requests",
              "token_cost_status": "no token usage fields in inspected canonical rows; no token/dollar estimate imputed",
              "arms": {a: summarize(groups["AD" if a in "AD" else "BC"], mem, a, tasks) for a in "ABCD"},
              "inputs": inventory + generation + [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)}
                  for p in (split, ROOT / "experiment/revision/cost_audit.py", ROOT / "experiment/revision/replay.py")]}
    (ROOT / "artifacts/revision_20260910/cost_audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print({a: {k: v for k, v in d.items() if k != "per_cell"} for a, d in report["arms"].items()})


if __name__ == "__main__":
    main()
