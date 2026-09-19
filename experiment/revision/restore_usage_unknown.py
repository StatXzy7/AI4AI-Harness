"""Restore preserved answers for usage-unknown cells (frozen policy).

PROVIDER_LAUNCH_GUARDS.md: on a successful response whose usage is missing,
the parent preserves the answer and stops without retrying.  The generic
reconcile path conservatively marked such cells failed_known (oc=None);
this tool recovers the worker's scored answer when the worker ledger
shows fully closed requests (no http_unknown), records
outcome=completed_usage_unknown with the worker's accounting, and leaves
total_tokens unknown for E4.  Idempotent. Refuses to run while a live
collector holds the writer lock (same guard as reconcile_cell).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WP1R = ROOT / 'artifacts' / 'wp1r_20260915'


def restore(arm: str):
    folder = WP1R / arm
    lock = folder / 'writer.lock'
    if lock.exists():
        import msvcrt
        with open(lock, 'a+b') as fh:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError(
                    'A collector holds the writer lock; restore is refused '
                    'while an acquisition is live')
            else:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    conn = sqlite3.connect(folder / 'ledger.sqlite')
    conn.execute('PRAGMA busy_timeout=10000')
    rows = conn.execute(
        "SELECT key,result FROM tasks "
        "WHERE json_extract(result,'$.outcome')='failed_known'").fetchall()
    restored = 0
    for key, res in rows:
        wl = folder / 'workers' / key / 'ledger.sqlite'
        if not wl.exists():
            continue
        wd = sqlite3.connect(f'file:{wl}?mode=ro', uri=True)
        # closed-request safety: no http_unknown events in this worker
        unknown = wd.execute(
            "SELECT COUNT(*) FROM events "
            "WHERE json_extract(value,'$.kind')='http_unknown'").fetchone()[0]
        wr = wd.execute(
            'SELECT result FROM tasks WHERE result IS NOT NULL').fetchone()
        wd.close()
        if unknown or not wr:
            continue
        child = json.loads(wr[0])
        if child.get('official_correct') is None:
            continue
        acc = child.get('accounting', {})
        if acc.get('responses_missing_usage', 0) == 0 \
                and acc.get('total_tokens') is not None:
            continue   # not a usage-unknown cell; leave as-is
        merged = {
            **json.loads(res),
            'official_correct': child['official_correct'],
            'final_answer': child.get('final_answer'),
            'n_llm_calls': child.get('n_llm_calls'),
            'answer_seconds': child.get('answer_seconds'),
            'trace': child.get('trace'),
            'worker_pid': child.get('worker_pid'),
            'accounting': acc,
            'outcome': 'completed_usage_unknown',
            'usage_unknown_restored': True,
        }
        merged.pop('error', None)
        conn.execute('UPDATE tasks SET result=? WHERE key=?',
                     (json.dumps(merged, ensure_ascii=False), key))
        conn.execute(
            'INSERT INTO events (value) VALUES (?)',
            (json.dumps({'kind': 'usage_unknown_answer_restored',
                         'task': key,
                         'official_correct': child['official_correct'],
                         'total_tokens_known': False}),))
        restored += 1
    conn.commit()
    conn.close()
    print(f'{arm}: restored {restored} preserved answer(s)')


if __name__ == '__main__':
    for a in sys.argv[1:]:
        restore(a)
