"""Canonical W3 membership, denominator and fingerprint behavior checks."""
import unittest

from experiment.revision.fingerprint import candidate_records, norm_sql, pair_summary, rerun_summary, spearman
from experiment.revision.replay import TARGET


class FingerprintTests(unittest.TestCase):
    def test_repeat_channel_denominators_and_source_hash(self):
        tasks = ['db#0', 'db#1', 'db#2']
        original = [dict(final_sql=sql, official_correct=0, n_llm_calls=1, code_hash='same')
                    for sql in ('select 1', '', 'select 1')]
        repeated = [dict(final_sql=sql, official_correct=v, n_llm_calls=calls, code_hash='same')
                    for sql, v, calls in [('select 2', 1, 2), ('select 1', 0, 1), ('select 1', 0, 1)]]
        groups = {'AD': {(TARGET, 'h', t, 0, False): r for t,r in zip(tasks, original)}}
        repeats = {'r2_pass1': {(TARGET, 'h', t, 0, True): r for t,r in zip(tasks, repeated)}}
        records = {('h', t): r for t,r in zip(tasks, original)}
        mem = {('builder', 0, 'A'): ['h']}
        result = rerun_summary(groups, repeats, mem, tasks, records)
        self.assertEqual(result['channels']['sql'], dict(n=2, changed=1, rate=.5))
        self.assertEqual(result['channels']['calls'], dict(n=3, changed=1, rate=1/3))
        self.assertEqual(result['channels']['verdict'], dict(n=3, changed=1, rate=1/3))
        self.assertAlmostEqual(result['mean_jaccard_when_sql_changed'], 1/3)
        repeated[0]['code_hash'] = 'different'
        with self.assertRaisesRegex(ValueError, 'source changed'):
            rerun_summary(groups, repeats, mem, tasks, records)
        repeated[0]['code_hash'] = 'same'
        repeated[0]['n_llm_calls'] = -1
        with self.assertRaisesRegex(ValueError, 'invalid repeated call count'):
            rerun_summary(groups, repeats, mem, tasks, records)

    def test_legacy_normalization_is_lossy_not_semantic_equivalence(self):
        self.assertEqual(norm_sql("SELECT 'a;b'"), norm_sql("SELECT 'ab'"))
        self.assertNotEqual(norm_sql("SELECT 'Eur'"), norm_sql("SELECT 'EUR'"))
        self.assertEqual(norm_sql(None), ('', frozenset()))
        with self.assertRaises(ValueError):
            norm_sql(5)

    def test_spearman_ties_and_undefined(self):
        self.assertAlmostEqual(spearman([1, 1, 2], [5, 5, 7]), 1.)
        self.assertAlmostEqual(spearman([1, 2, 3], [3, 2, 1]), -1.)
        self.assertIsNone(spearman([1, 1], [1, 2]))
        self.assertIsNone(spearman([], []))

    def test_membership_and_pair_denominators_use_complete_canonical_rows(self):
        def row(sql, v):
            return dict(final_sql=sql, official_correct=v, n_llm_calls=1, n_execs=1)
        groups = {'AD': {(TARGET, 'hA', 'db#0', 0, False): row("SELECT 'a;b'", 1),
                         (TARGET, 'hA', 'db#1', 0, False): row(None, 0)},
                  'BC': {(TARGET, 'hB', 'db#0', 0, False): row("SELECT 'ab'", 0),
                         (TARGET, 'hB', 'db#1', 0, False): row(None, 0)}}
        mem = {('builder', 0, 'A'): ['hA'], ('builder', 0, 'B'): ['hB']}
        tasks = ['db#0', 'db#1']
        records, cells, arms = candidate_records(groups, mem, tasks)
        out = pair_summary(records, cells, arms, tasks)
        self.assertEqual(out['n_pairs'], 1)
        self.assertEqual(out['identical_normalized_sql'], dict(n=1, verdict_disagreements=1, rate=1.))
        self.assertEqual(out['pairs'][0]['outcome_disagreements'], 1)
        self.assertEqual(out['pairs'][0]['n_nonempty_sql_verdict_agree'], 0)
        self.assertEqual(out['all_pairs_correlation']['n_eligible'], 0)
        self.assertEqual(out['all_channels_identical_pairs'], 0)
        del groups['BC'][TARGET, 'hB', 'db#1', 0, False]
        with self.assertRaises(KeyError):
            candidate_records(groups, mem, tasks)


if __name__ == '__main__':
    unittest.main()
