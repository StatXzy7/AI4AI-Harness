"""Versioned interleaved scheduling with the unchanged isolated-v2 worker lifecycle.

No new scientific run is implied. All members run within each task/repeat block;
SHA256 ordering is fixed by an explicit salt, not by observed correctness.
"""

import argparse
import json
from pathlib import Path
import sqlite3

from experiment.revision import isolated_collect as legacy
from experiment.revision.fresh_collect import file_hash, validate_inputs
from experiment.revision.fresh_runtime import RunStore, digest
from experiment.revision.isolated_collect import (
    import_events,
    read_ledger,
    require_launch_identity,
    run_worker,
)


def schedule(repeats, harnesses, tasks, salt):
    if not isinstance(salt, str) or not salt.strip():
        raise ValueError("Explicit nonempty schedule salt required")
    rows = []
    for repeat in repeats:
        ordered_tasks = sorted(
            tasks, key=lambda t: (digest([salt, "task", repeat, t["id"]]), t["id"])
        )
        for task in ordered_tasks:
            members = sorted(
                harnesses,
                key=lambda h: (
                    digest([salt, "member", repeat, task["id"], h["id"]]),
                    h["id"],
                ),
            )
            rows.extend(
                dict(repeat=repeat, harness=h["id"], task=task["id"]) for h in members
            )
    return rows


def prepare(config):
    manifest, tasks = legacy.prepare(config)
    rows = schedule(
        manifest["repeats"], manifest["harnesses"], tasks, config["schedule_salt"]
    )
    manifest.update(
        version="interleaved-isolated-v1",
        task_order="repeat-task-member-sha256-v1",
        schedule_salt=config["schedule_salt"],
        schedule=rows,
        schedule_sha256=digest(rows),
    )
    manifest["source_sha256"][str(Path(__file__).resolve())] = file_hash(Path(__file__))
    return manifest, tasks


def collect(config):
    require_launch_identity(config)
    manifest, tasks = prepare(config)
    output = Path(config["output"]).resolve()
    with RunStore(output, manifest) as store:
        by_task = {t["id"]: t for t in tasks}
        by_harness = {h["id"]: h for h in manifest["harnesses"]}
        for cell in manifest["schedule"]:
            task = by_task[cell["task"]]
            harness = by_harness[cell["harness"]]
            key, needed = store.begin(cell)
            if not needed:
                continue
            folder = output / "workers" / key
            folder.mkdir(parents=True, exist_ok=False)
            request = {
                "manifest": manifest,
                "cell": cell,
                "task": task,
                "harness": harness,
                "folder": str(folder),
                "dataset_root": str(Path(config["dataset_root"]).resolve()),
            }
            request_path = folder / "request.json"
            request_path.write_text(
                json.dumps(request, ensure_ascii=False), encoding="utf-8"
            )
            process = run_worker(request_path, folder, manifest["worker_wall_seconds"])
            store.event("worker_exited", task=key, **process)
            try:
                child = read_ledger(folder)
            except sqlite3.DatabaseError as exc:
                store.event(
                    "ledger_read_error",
                    task=key,
                    error_type=type(exc).__name__,
                    request_accounting="unknown",
                )
                child = None
            if child:
                import_events(store, key, child)
            success = (
                process["reason"] == "exited"
                and process["exit_code"] == 0
                and child
                and len(child["tasks"]) == 1
                and child["tasks"][0]["result"] is not None
            )
            if not success:
                store.event(
                    "acquisition_stopped",
                    task=key,
                    reason="worker_or_requests_unresolved",
                )
                (output / "snapshot.json").write_text(
                    json.dumps(store.snapshot(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                raise RuntimeError(
                    "Worker stopped; preserve answer and unknown requests, do not retry automatically"
                )
            child_result = child["tasks"][0]["result"]
            accounting = child_result.get("accounting", {})
            if (
                accounting.get("responses_missing_usage") != 0
                or accounting.get("total_tokens") is None
            ):
                store.event(
                    "acquisition_stopped",
                    task=key,
                    reason="response_usage_unknown",
                    answer_preserved=True,
                    worker_result=child_result,
                )
                (output / "snapshot.json").write_text(
                    json.dumps(store.snapshot(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                raise RuntimeError(
                    "Response usage unknown; preserve answer and pending cell, do not retry automatically"
                )
            store.finish(key, {**child_result, "worker_pid": process["pid"]})
        validate_inputs(
            store, {**manifest["source_sha256"], **manifest["database_sha256"]}
        )
        store.event(
            "run_verified",
            cells=len(tasks) * len(manifest["harnesses"]) * len(manifest["repeats"]),
        )
        result = store.snapshot()
        (output / "snapshot.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = collect(json.loads(args.config.read_text(encoding="utf-8")))
    print(f"Verified {len(result['tasks'])} interleaved isolated cells")
