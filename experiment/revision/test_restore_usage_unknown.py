"""Tests for restore_usage_unknown: recover scored answers on cells whose
only defect is a missing provider-usage record (frozen preserve-answer
policy); genuine http_unknown failures must stay reconciled."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import experiment.revision.restore_usage_unknown as ruu


def make_arm(root: Path, arm: str, parent_rows, workers):
    """parent_rows: list of (key, result_json_or_None); workers: {key: result}."""
    folder = root / arm
    (folder / 'workers').mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / 'ledger.sqlite')
    conn.execute('CREATE TABLE manifest (id INTEGER PRIMARY KEY, value TEXT)')
    conn.execute('CREATE TABLE tasks (key TEXT PRIMARY KEY, result TEXT)')
    conn.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, value TEXT)')
    conn.execute('INSERT INTO manifest VALUES (1, "{}")')
    for key, result in parent_rows:
        conn.execute('INSERT INTO tasks VALUES (?,?)',
                     (key, json.dumps(result) if result else None))
    conn.commit()
    conn.close()
    for key, result, unknown in workers:
        wd = folder / 'workers' / key
        wd.mkdir(parents=True, exist_ok=True)
        wc = sqlite3.connect(wd / 'ledger.sqlite')
        wc.execute('CREATE TABLE tasks (key TEXT PRIMARY KEY, result TEXT)')
        wc.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, value TEXT)')
        wc.execute('INSERT INTO tasks VALUES (?,?)',
                   ('w0', json.dumps(result)))
        if unknown:
            wc.execute('INSERT INTO events VALUES (1,?)',
                       (json.dumps({'kind': 'http_unknown'}),))
        wc.commit()
        wc.close()


def failed_known():
    return {'outcome': 'failed_known', 'reconciled': True,
            'official_correct': None,
            'accounting': {'responses_missing_usage': 0,
                           'total_tokens': 0}}


def worker_result(oc, missing):
    return {'official_correct': oc, 'final_answer': 'ans',
            'accounting': {'responses_missing_usage': missing,
                           'total_tokens': None if missing else 100,
                           'logical_calls': 1, 'http_attempts': 1}}


class RestoreUsageUnknownTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patcher = mock.patch.object(ruu, 'WP1R', self.root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_restores_preserved_answer_with_unknown_cost(self):
        make_arm(self.root, 'dev_real_cont',
                 [('k1', failed_known())],
                 [('k1', worker_result(1, 1), False)])
        ruu.restore('dev_real_cont')
        conn = sqlite3.connect(str(self.root / 'dev_real_cont' / 'ledger.sqlite'))
        c = json.loads(conn.execute(
            "SELECT result FROM tasks WHERE key='k1'").fetchone()[0])
        conn.close()
        self.assertEqual(c['official_correct'], 1)
        self.assertEqual(c['outcome'], 'completed_usage_unknown')
        self.assertIsNone(c['accounting']['total_tokens'])
        self.assertNotIn('error', c)

    def test_does_not_restore_http_unknown(self):
        make_arm(self.root, 'dev_real_cont',
                 [('k2', failed_known())],
                 [('k2', worker_result(1, 1), True)])  # has http_unknown
        ruu.restore('dev_real_cont')
        conn = sqlite3.connect(str(self.root / 'dev_real_cont' / 'ledger.sqlite'))
        c = json.loads(conn.execute(
            "SELECT result FROM tasks WHERE key='k2'").fetchone()[0])
        conn.close()
        self.assertIsNone(c['official_correct'])
        self.assertEqual(c['outcome'], 'failed_known')

    def test_does_not_restore_known_cost_correct_cell(self):
        # worker closed with usage known and oc=0: not usage-unknown
        make_arm(self.root, 'dev_real_cont',
                 [('k3', failed_known())],
                 [('k3', worker_result(0, 0), False)])
        ruu.restore('dev_real_cont')
        conn = sqlite3.connect(str(self.root / 'dev_real_cont' / 'ledger.sqlite'))
        c = json.loads(conn.execute(
            "SELECT result FROM tasks WHERE key='k3'").fetchone()[0])
        conn.close()
        self.assertIsNone(c['official_correct'])


if __name__ == '__main__':
    unittest.main()
