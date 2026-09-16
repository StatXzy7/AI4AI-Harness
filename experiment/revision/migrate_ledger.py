"""Migrate a fresh-acquisition ledger into a continuation RunStore.

Rationale (protocol A9-resume, 2026-09-16): the run manifest binds the
protocol file, the collector source, and the config at launch. Forward
amendments (protocol A9, runtime fixes) make byte-identical resume impossible
while the shared state ceiling must rise (45k -> 60k). The audited path:

  * create a NEW RunStore whose manifest is the CURRENT frozen config
    (protocol incl. A9, current source hashes, 60000 attempts);
  * copy every completed cell (result + full event evidence) from the old
    ledger, remapping cell keys to the new run id;
  * record a migration event binding the source ledger SHA256 and counts;
  * resume collection: only unfinished cells execute; finished cells are
    treated as done exactly as if they had run in this ledger.

Nothing is fabricated: results and events are copied verbatim; the old
ledger remains untouched as frozen evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiment.revision.fresh_runtime import RunStore, digest  # noqa: E402


def file_sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def migrate(old_ledger: Path, new_config_path: str, new_output: str):
    cfg = json.loads(Path(new_config_path).read_text(encoding='utf-8'))
    cfg = {**cfg, 'output': new_output}
    from experiment.revision.fresh_collect_math import prepare
    manifest, tasks = prepare(cfg)
    # Replicate exactly what collect() adds to the manifest before opening
    # the RunStore, so the stored identity matches the resuming collector.
    from experiment.revision.interleaved_collect import schedule
    rows = schedule(manifest['repeats'], manifest['harnesses'], tasks,
                    cfg['schedule_salt'])
    shard_index = cfg.get('shard_index', 0)
    shards = cfg.get('shards', 1)
    rows = [row for i, row in enumerate(rows) if i % shards == shard_index]
    manifest['schedule_sha256'] = digest(rows)
    manifest['shard'] = {'index': shard_index, 'count': shards}
    old = sqlite3.connect(f'file:{old_ledger}?mode=ro', uri=True)
    old_run_id = json.loads(old.execute('SELECT value FROM manifest WHERE id=1')
                            .fetchone()[0]).get('acquisition_id')
    migrated = skipped = 0
    with RunStore(Path(new_output), manifest) as store:
        # every completed cell in the old ledger
        rows = old.execute('SELECT key, result FROM tasks WHERE result IS NOT NULL').fetchall()
        # map old key -> identity via task_start events
        idents = {}
        for (v,) in old.execute("SELECT value FROM events WHERE json_extract(value,'$.kind')='task_start'"):
            e = json.loads(v)
            idents[e['task']] = e.get('identity')
        for key, result in rows:
            identity = idents.get(key)
            if identity is None:
                skipped += 1
                continue
            new_key = digest({'run': store.run_id, 'cell': identity})
            exists = store.db.execute('SELECT result FROM tasks WHERE key=?',
                                      (new_key,)).fetchone()
            if exists is not None:
                continue
            store.db.execute('INSERT INTO tasks VALUES (?,?)', (new_key, result))
            # copy events of this cell, remapping the task field
            for (v,) in old.execute(
                    "SELECT value FROM events WHERE json_extract(value,'$.task')=? ORDER BY id",
                    (key,)):
                e = json.loads(v)
                e.pop('id', None)
                e['task'] = new_key
                e['migrated_from'] = key
                store.event(e.pop('kind'), **e)
            migrated += 1
        store.event('ledger_migration',
                    source_ledger=str(old_ledger),
                    source_ledger_sha256=file_sha(old_ledger),
                    source_acquisition_id=old_run_id,
                    migrated_cells=migrated, skipped_cells=skipped,
                    migrated_at=time.time())
    print(f'migrated {migrated} cells, skipped {skipped} (no identity)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='old_ledger', required=True)
    ap.add_argument('--config', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    migrate(Path(args.old_ledger), args.config, args.output)


if __name__ == '__main__':
    main()
