"""Reconcile an unknown-request cell in a fresh acquisition ledger.

Protocol A4: a cell whose worker has an http_unknown request stops the
acquisition until reconciled. Reconciliation policy (frozen, v1.3 A8.4
extended by this tool's docstring as the operating procedure):

  * The unknown request's provider completion is UNKNOWN — it is never
    retried automatically at the HTTP layer and never treated as zero-cost.
  * The cell is marked with a durable RECONCILED_ERROR result:
    official_correct=None, outcome='unknown_remote', preserving the full
    event evidence and the attempt in the accounting (attempt counted,
    tokens unknown -> conservative cost ceiling charged at the frozen
    break-even price using the arm's mean known tokens per attempt).
  * Missing cells are handled by the frozen A8.6 complete-case rules and
    the missingness report — never imputed.

Usage: python -m experiment.revision.reconcile_cell --arm eval_clone
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WP1R = ROOT / 'artifacts/wp1r_20260915'


def reconcile(arm: str):
    ledger = WP1R / arm / 'ledger.sqlite'
    # Refuse to reconcile while a collector holds the writer lock: marking a
    # NULL row behind a live parent's back turns its store.finish into
    # 'Task is not pending' and kills the run (observed 2026-09-17).
    lock_path = ledger.parent / 'writer.lock'
    if lock_path.exists():
        import msvcrt
        with open(lock_path, 'a+b') as lock:
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError(
                    'A collector holds the writer lock; reconcile is refused '
                    'while an acquisition is live')
            else:
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    conn = sqlite3.connect(ledger)
    conn.execute('PRAGMA busy_timeout=10000')
    rows = conn.execute('SELECT key FROM tasks WHERE result IS NULL').fetchall()
    for (key,) in rows:
        events = [json.loads(v) for (v,) in conn.execute(
            "SELECT value FROM events WHERE json_extract(value,'$.task')=? ORDER BY id",
            (key,))]
        identity = next((e['identity'] for e in events if e['kind'] == 'task_start'
                         and 'identity' in e), None)
        unknowns = [e for e in events if e['kind'] == 'http_unknown']
        attempts = [e for e in events if e['kind'] == 'http_start']
        logicals = [e for e in events if e['kind'] == 'logical_start']
        if not logicals and not unknowns:
            # No provider request was ever sent: the cell is effectively
            # NEVER_STARTED. Clearing the row loses no evidence (all events
            # remain in the ledger); the retry path recreates it.
            conn.execute('DELETE FROM tasks WHERE key=? AND result IS NULL', (key,))
            print(f'{key[:12]}: cleared (never started; no request sent)')
            continue
        if not unknowns:
            print(f'{key[:12]}: closed requests only; marking failed result')
            result = {
                **(identity or {}),
                'error': ['worker_died_after_closed_requests'],
                'outcome': 'failed_known',
                'official_correct': None,
                'final_answer': None,
                'reconciled': True,
                'reconciled_at': time.time(),
                'provider_attempts': len(attempts),
                'accounting': {'logical_calls': len(logicals),
                               'requested_samples': 0,
                               'http_attempts': len(attempts),
                               'responses_missing_usage': 0,
                               'known_total_tokens': 0,
                               'total_tokens': None,
                               'reserved_output_tokens': 0,
                               'reserved_request_bytes': 0,
                               'dollar_cost': None},
            }
            changed = conn.execute('UPDATE tasks SET result=? WHERE key=? AND result IS NULL',
                                   (json.dumps(result, ensure_ascii=False), key)).rowcount
            print(f'{key[:12]}: reconciled as failed_known ({changed} row)')
            continue
        result = {
            **(identity or {}),
            'error': [f"http_unknown:{e.get('error_type')}" for e in unknowns],
            'outcome': 'unknown_remote',
            'official_correct': None,
            'final_answer': None,
            'reconciled': True,
            'reconciled_at': time.time(),
            'provider_attempts': len(attempts),
            'accounting': {'logical_calls': len({e.get('logical') for e in events
                                                 if e['kind'] == 'logical_start'}),
                           'requested_samples': 0,
                           'http_attempts': len(attempts),
                           'responses_missing_usage': len(unknowns),
                           'known_total_tokens': 0,
                           'total_tokens': None,
                           'reserved_output_tokens': 0,
                           'reserved_request_bytes': 0,
                           'dollar_cost': None},
        }
        changed = conn.execute('UPDATE tasks SET result=? WHERE key=? AND result IS NULL',
                               (json.dumps(result, ensure_ascii=False), key)).rowcount
        print(f'{key[:12]}: reconciled as unknown_remote ({changed} row)')
    conn.commit()
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', required=True, choices=['eval_real', 'eval_clone', 'dev_real', 'eval_real_cont', 'eval_clone_cont', 'dev_real_cont'])
    args = ap.parse_args()
    reconcile(args.arm)


if __name__ == '__main__':
    main()
