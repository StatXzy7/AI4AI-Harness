"""Tests for continuation-ledger merging in wp1r_analysis (2026-09-19).

The 2026-09-17/18 stop-and-reconcile events split each arm's acquisition
across continuation ledgers.  merge_cells must (a) collapse migration
copies, (b) prefer completed observations over unknown_remote markers,
(c) retain the first completed execution when two completed records
disagree, and (d) report every category for the paper's deviation log.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import experiment.revision.wp1r_analysis as wpa


FAST = mock.patch.multiple(wpa, N_PERM=50, N_BOOT=50)


def Y_from(rows):
    """rows: dict repeat -> 2D list. Returns dict repeat -> np.array."""
    return {int(r): np.array(v, dtype=float) for r, v in rows.items()}


class A86Test(unittest.TestCase):
    def test_paired_difference_uses_task_intersection(self):
        # real complete on tasks {0,1}, clone complete on tasks {1,2}
        real = Y_from({
            1: [[1, 1, 0, 0], [1, 0, 1, 1]],          # bare, m1
            2: [[1, 1, 0, 0], [1, 0, 1, 1]],
            3: [[1, 1, 0, 0], [1, 0, 1, 1]],
        })
        real[2][0, 2] = np.nan                        # task 2 incomplete
        real[3][0, 0] = np.nan                        # task 0 incomplete
        clone = Y_from({
            1: [[1, 1, 1, 1], [1, 1, 0, 0]],          # clone-c1, clone-c2
            2: [[1, 1, 1, 1], [1, 1, 0, 0]],
            3: [[1, 1, 1, 1], [1, 1, 0, 0]],
        })
        clone[1][0, 0] = np.nan                       # task 0 incomplete
        clone[2][1, 3] = np.nan                       # task 3 incomplete
        with FAST:
            out = wpa.a86_test(real, ['bare', 'm1'],
                               clone, ['clone-c1', 'clone-c2'],
                               n_tasks_total=4)
        # real complete tasks: {1, 3}; clone complete tasks: {1, 2}
        self.assertEqual(out['n_tasks_real'], 2)
        self.assertEqual(out['n_tasks_clone'], 2)
        self.assertEqual(out['n_tasks_paired'], 1)

    def test_coverage_gate_forces_insufficient(self):
        # half of the real tasks incomplete -> exclusion 50% > 10%
        real = Y_from({
            1: [[1, 1, 1, 1], [0, 0, 0, 0]],
            2: [[1, 1, 1, 1], [0, 0, 0, 0]],
            3: [[1, 1, 1, 1], [0, 0, 0, 0]],
        })
        real[2][0, 2:] = np.nan
        real[3][0, 2:] = np.nan
        clone = Y_from({r: [[1, 1, 1, 1], [0, 0, 0, 0]] for r in (1, 2, 3)})
        with FAST:
            out = wpa.a86_test(real, ['bare', 'm1'],
                               clone, ['clone-c1', 'clone-c2'],
                               n_tasks_total=4)
        self.assertEqual(out['state'], 'INSUFFICIENT')
        self.assertIn('coverage gate', out['reason'])

    def test_imputation_sensitivity_reported(self):
        real = Y_from({
            1: [[1, 1], [0, 1]],
            2: [[1, 1], [0, 1]],
            3: [[1, 1], [0, 1]],
        })
        real[2][1, 0] = np.nan   # one missing repeat for m1 on task 0
        clone = Y_from({r: [[1, 1], [0, 0]] for r in (1, 2, 3)})
        with FAST:
            out = wpa.a86_test(real, ['bare', 'm1'],
                               clone, ['clone-c1', 'clone-c2'],
                               n_tasks_total=2)
        sens = out['sensitivity_imputed']
        self.assertIn('within-task', sens['rule'])
        # imputed real arm covers both tasks (m1's task-0 hole filled by mean)
        self.assertEqual(sens['n_tasks_paired'], 2)


class AccountingIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patcher = mock.patch.object(wpa, 'WP1R', self.root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_full_record_identity_dedup(self):
        c1 = cell(attempts=2, tokens=100)
        c1['worker_pid'] = 111
        copy = dict(c1)                       # migration copy: identical
        reexec = dict(c1, worker_pid=222)     # distinct execution
        make_ledger(self.root / 'eval_real', [c1])
        make_ledger(self.root / 'eval_real_cont', [copy, reexec])
        with mock.patch.dict(wpa.ARM_LEDGERS,
                             {'eval_real': ['eval_real', 'eval_real_cont']}):
            out = wpa.accounting(['eval_real'])
        arm = out['eval_real']
        self.assertEqual(arm['migration_copies_excluded'], 1)
        # copy collapsed, re-execution counted: 2 + 2 attempts
        self.assertEqual(arm['http_attempts'], 4)


class SelectorLeakageTest(unittest.TestCase):
    def test_fold_features_use_train_fold_only(self):
        import experiment.revision.wp2r_selector as sel
        members = ['bare', 'm1', 'm2']
        # 10 dev tasks; bare accuracy 6/10 so no train-fold mean equals it
        dev = np.array([[1] * 6 + [0] * 4,
                        [1] * 5 + [1] * 5,
                        [0] * 5 + [0] * 5], dtype=float)
        tasks = [f't{i}' for i in range(10)]
        captured = {}
        real_lr = None

        from sklearn.linear_model import LogisticRegression
        real_lr = LogisticRegression

        class SpyLR(real_lr):
            def fit(self, X, y):
                captured.setdefault('X', []).append(np.array(X))
                return super().fit(X, y)

        fake_feats = lambda tr, he: (np.zeros((len(tr), 2)),
                                     np.zeros((len(he), 2)))
        with mock.patch.object(sel, 'N_FOLDS', 5), \
             mock.patch.object(sel, 'question_features', fake_feats), \
             mock.patch('sklearn.linear_model.LogisticRegression', SpyLR):
            try:
                sel.fit_pi_z(dev, members, tasks, ['t0'])
            except Exception:
                pass  # feature/label shape issues are fine; we inspect X
        self.assertTrue(captured.get('X') is not None)
        # dev-acc feature columns (last 3) must equal train-fold means,
        # never the all-dev means [0.5, 1.0, 0.0]
        all_dev_means = dev.mean(axis=1)
        for X in captured['X']:
            feats = X[0, -3:]
            self.assertFalse(np.allclose(feats, all_dev_means),
                             'fold features leaked all-dev accuracies')


if __name__ == '__main__':
    unittest.main()


def make_ledger(folder: Path, cells, acquisition_id='acq-test',
                harnesses=None):
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / 'ledger.sqlite')
    conn.execute('CREATE TABLE manifest (id INTEGER PRIMARY KEY, value TEXT)')
    conn.execute('CREATE TABLE tasks (key TEXT PRIMARY KEY, result TEXT)')
    conn.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, value TEXT)')
    harness_ids = harnesses or sorted({c['harness'] for c in cells})
    manifest = {
        'acquisition_id': acquisition_id,
        'solver': {'model': 'M', 'base_url': 'u', 'max_tokens': 1},
        'cache_mode': 'off', 'temperature_semantics': 't', 'judge': 'j',
        'protocol': 'p', 'section': 'eval',
        'harnesses': [{'id': h, 'source_sha256_lf': 'h_' + h}
                      for h in harness_ids],
    }
    conn.execute('INSERT INTO manifest VALUES (1, ?)', (json.dumps(manifest),))
    for i, c in enumerate(cells):
        conn.execute('INSERT INTO tasks VALUES (?, ?)',
                     (f'k{i}', json.dumps(c)))
    conn.commit()
    conn.close()


def cell(h='bare', t='task1', r=1, oc=1, attempts=1, tokens=10):
    return {'harness': h, 'task': t, 'repeat': r, 'official_correct': oc,
            'accounting': {'http_attempts': attempts, 'logical_calls': 1,
                           'total_tokens': tokens}}


class MergeCellsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patcher = mock.patch.object(wpa, 'WP1R', self.root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_migration_copy_collapses(self):
        c = cell()
        make_ledger(self.root / 'a', [c])
        make_ledger(self.root / 'b', [dict(c)])
        merged, rep = wpa.merge_cells(['a', 'b'])
        self.assertEqual(len(merged), 1)
        self.assertEqual(rep['identical_copies'], 1)
        self.assertEqual(rep['rows_read'], 2)

    def test_completed_beats_unknown_either_order(self):
        done = cell(oc=1)
        unknown = cell(oc=None)
        make_ledger(self.root / 'a', [unknown])
        make_ledger(self.root / 'b', [done])
        merged, rep = wpa.merge_cells(['a', 'b'])
        self.assertEqual(merged[('bare', 'task1', 1)]['official_correct'], 1)
        self.assertEqual(rep['unknown_then_completed'], 1)
        # reverse order: earlier completed is retained
        make_ledger(self.root / 'c', [done])
        make_ledger(self.root / 'd', [unknown])
        merged, rep = wpa.merge_cells(['c', 'd'])
        self.assertEqual(merged[('bare', 'task1', 1)]['official_correct'], 1)
        self.assertEqual(rep['completed_beats_unknown'], 1)

    def test_both_completed_differ_keeps_earliest(self):
        first = cell(oc=0)
        second = cell(oc=1)
        make_ledger(self.root / 'a', [first])
        make_ledger(self.root / 'b', [second])
        merged, rep = wpa.merge_cells(['a', 'b'])
        self.assertEqual(merged[('bare', 'task1', 1)]['official_correct'], 0)
        self.assertEqual(len(rep['both_completed_differ']), 1)
        rec = rep['both_completed_differ'][0]
        self.assertEqual(rec['retained'], 0)
        self.assertEqual(rec['discarded'], 1)

    def test_matrices_merges_and_shapes(self):
        cells_a = [cell(h='bare', t='t1', r=1, oc=1),
                   cell(h='bare', t='t1', r=2, oc=0),
                   cell(h='mem', t='t1', r=1, oc=0)]
        cells_b = [cell(h='mem', t='t1', r=2, oc=1),
                   cell(h='mem', t='t1', r=3, oc=1)]
        make_ledger(self.root / 'a', cells_a, harnesses=['bare', 'mem'])
        make_ledger(self.root / 'b', cells_b, harnesses=['bare', 'mem'])
        members, tasks, repeats, by_rep, manifest, cells, dedup = \
            wpa.matrices(['a', 'b'])
        self.assertEqual(members, ['bare', 'mem'])
        self.assertEqual(repeats, [1, 2, 3])
        self.assertEqual(by_rep[1].tolist(), [[1.0], [0.0]])
        self.assertEqual(by_rep[2].tolist(), [[0.0], [1.0]])
        self.assertTrue(np.isnan(by_rep[3][0, 0]))
        self.assertEqual(by_rep[3][1, 0], 1.0)
        self.assertEqual(manifest['acquisition_id'], ['acq-test', 'acq-test'])

    def test_manifest_mismatch_raises(self):
        make_ledger(self.root / 'a', [cell()])
        make_ledger(self.root / 'b', [cell(t='t2')])
        # corrupt b's solver
        db = sqlite3.connect(self.root / 'b' / 'ledger.sqlite')
        m = json.loads(db.execute('SELECT value FROM manifest').fetchone()[0])
        m['solver']['model'] = 'OTHER'
        db.execute('UPDATE manifest SET value=?', (json.dumps(m),))
        db.commit()
        db.close()
        with self.assertRaises(ValueError):
            wpa.matrices(['a', 'b'])

    def test_accounting_dedups_copies_counts_distinct(self):
        c1 = cell(attempts=2, tokens=100)
        make_ledger(self.root / 'eval_real', [c1])
        # migration copy of c1 plus a distinct re-execution of the same key
        reexec = cell(attempts=1, tokens=50, oc=0)
        make_ledger(self.root / 'eval_real_cont', [dict(c1), reexec])
        make_ledger(self.root / 'eval_real_cont2', [])
        with mock.patch.dict(wpa.ARM_LEDGERS,
                             {'eval_real': ['eval_real', 'eval_real_cont',
                                            'eval_real_cont2']}):
            out = wpa.accounting(['eval_real'])
        arm = out['eval_real']
        self.assertEqual(arm['migration_copies_excluded'], 1)
        # distinct executions both count: 2 + 1 attempts, 100 + 50 tokens
        self.assertEqual(arm['http_attempts'], 3)
        self.assertEqual(arm['known_total_tokens'], 150)
        self.assertEqual(arm['ledger_row_attempts_upper_bound'], 5)


if __name__ == '__main__':
    unittest.main()
