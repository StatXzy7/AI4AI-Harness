"""Tests of delivered types, observed execution order and retained contracts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment.revision import gate_v3 as gate
from experiment.revision.classification_profiles import ClassificationIO, run_profile
from experiment.revision import classification_profile_report as report


class ClassificationProfileTests(unittest.TestCase):
    def setUp(self):
        self.success, *self.failures = gate.scenarios('error_classify', 'roles-test')

    def test_category_delivery_follows_failed_execution_not_prompt_words(self):
        for probe in self.failures:
            io = ClassificationIO(probe, 'classify_then_repair')
            initial = io.llm('Classify syntax schema semantics')
            io.execute(initial)
            self.assertEqual(io.llm('an arbitrary request'), probe.error_class)
            self.assertEqual(io.llm(probe.error), probe.expected)
            self.assertEqual([event['response_role'] for event in io.trace if event['kind'] == 'llm'],
                             ['initial_sql', 'classification', 'repair_sql'])
            self.assertEqual(io.trace[2]['response'], probe.error_class)
            self.assertEqual(io.trace[2]['state_before'], 'after_failure')

    def test_direct_profile_never_delivers_category(self):
        probe = self.failures[0]
        io = ClassificationIO(probe, 'direct_repair')
        io.execute(io.llm('initial'))
        self.assertEqual(io.llm('Classify syntax schema semantics ' + probe.error), probe.expected)
        self.assertEqual(io.trace[-1]['response_role'], 'repair_sql')

    def test_success_does_not_inject_category_or_allow_extra_generation(self):
        def extra(io, question):
            sql = io.llm(question)
            io.execute(sql)
            return io.llm('Classify this')
        result = run_profile(extra, self.success, 'classify_then_repair')
        self.assertIn('unconditional_extra_generation', result['structural_failures'])
        self.assertTrue(result['interface_issues'])
        self.assertNotIn('classification', [e.get('response_role') for e in result['trace']])

    def test_missing_execution_and_batched_samples_remain_structural_failures(self):
        def missing(io, question):
            io.llm(question)
            return io.llm('classify')
        self.assertIn('initial_sql_not_executed',
                      run_profile(missing, self.failures[0], 'classify_then_repair')['structural_failures'])
        def batch(io, question):
            sql = io.llm(question, n=2)[0]
            result = io.execute(sql)
            return io.llm(result['error'])
        self.assertIn('extra_batched_samples',
                      run_profile(batch, self.failures[0], 'direct_repair')['structural_failures'])

    def test_missing_feedback_is_not_hidden_by_correct_category(self):
        def no_feedback(io, question):
            io.execute(io.llm(question))
            io.llm('a category please')
            return io.llm('repair without feedback')
        result = run_profile(no_feedback, self.failures[0], 'classify_then_repair')
        self.assertIn('execution_feedback_not_carried_forward', result['structural_failures'])

    def test_invalid_and_ambiguous_replies_are_delivered_verbatim(self):
        for reply in ('UNRECOGNIZED_CATEGORY', 'syntax or schema'):
            io = ClassificationIO(self.failures[0], 'classify_then_repair', reply)
            io.execute(io.llm('initial'))
            self.assertEqual(io.llm('category'), reply)
            self.assertEqual(io.trace[-1]['response'], reply)

    def test_category_consumption_is_never_automatic_admission(self):
        def consumer(io, question):
            sql = io.llm(question)
            result = io.execute(sql)
            if result['ok']:
                return sql
            category = io.llm(result['error'])
            return io.llm(category + result['error'])
        for probe in [self.success, *self.failures]:
            result = run_profile(consumer, probe, 'classify_then_repair')
            self.assertEqual(result['status'], 'review_required')
            self.assertEqual(result['structural_failures'], [])
            self.assertIsNone(result['error'])


class ProfileSelectionTests(unittest.TestCase):
    def role_map(self, out, roles):
        (out / 'PROTOCOL.md').write_text('test protocol', encoding='utf-8')
        report.write_new(out / 'role_map.json', dict(
            source_sha256=report.digest(report.SOURCE),
            protocol_sha256=report.digest(out / 'PROTOCOL.md'),
            cases=[dict(case_id=case_id, role=role)
                   for case_id, role in zip(report.EXPECTED_CASES, roles)]))

    def test_source_role_is_primary_even_if_diagnostic_looks_better(self):
        with tempfile.TemporaryDirectory(dir=report.ROOT / 'artifacts') as directory:
            out = Path(directory)
            self.role_map(out, ['classify_then_repair', 'direct_repair', 'ambiguous', 'classify_then_repair'])
            def mock_run(solve, probe, profile, reply):
                self.assertTrue((out / 'measurement_freeze.json').exists())
                return dict(profile=profile, final='better' if profile == 'direct_repair' else 'worse')
            with patch.object(report, 'OUT', out), patch.object(report, 'run_profile', side_effect=mock_run) as run:
                result = report.collect()
                self.assertEqual(run.call_count, 84)
                for case, expected in zip(result['cases'], ['classify_then_repair', 'direct_repair', None, 'classify_then_repair']):
                    primary = [p for p in case['profiles'] if p['use'] == 'primary']
                    self.assertEqual([p['profile'] for p in primary], [expected] if expected else [])
                    self.assertEqual(case['status'], 'review_required')
                with self.assertRaises(FileExistsError):
                    report.collect()
                self.assertEqual(run.call_count, 84)

    def test_changed_protocol_prevents_any_measurement(self):
        with tempfile.TemporaryDirectory(dir=report.ROOT / 'artifacts') as directory:
            out = Path(directory)
            self.role_map(out, ['direct_repair'] * 4)
            (out / 'PROTOCOL.md').write_text('changed protocol', encoding='utf-8')
            with patch.object(report, 'OUT', out), patch.object(report, 'run_profile') as run:
                with self.assertRaisesRegex(ValueError, 'protocol hash mismatch'):
                    report.collect()
                run.assert_not_called()
                self.assertFalse((out / 'measurement_freeze.json').exists())

    def test_changed_input_during_collection_preserves_results_without_complete(self):
        with tempfile.TemporaryDirectory(dir=report.ROOT / 'artifacts') as directory:
            out = Path(directory)
            self.role_map(out, ['direct_repair'] * 4)
            before = (out / 'PROTOCOL.md').read_bytes()
            def mock_run(*args):
                (out / 'PROTOCOL.md').write_text('changed during collection', encoding='utf-8')
                return dict(trace=[])
            with patch.object(report, 'OUT', out), patch.object(report, 'run_profile', side_effect=mock_run):
                with self.assertRaisesRegex(RuntimeError, 'bound input changed'):
                    report.collect()
                self.assertTrue((out / 'results.json').exists())
                self.assertFalse((out / 'COMPLETE.json').exists())
                (out / 'PROTOCOL.md').write_bytes(before)
                with self.assertRaisesRegex(RuntimeError, 'collection was invalidated'):
                    report.complete_saved()
                self.assertFalse((out / 'COMPLETE.json').exists())

    def test_completion_recovery_does_not_rerun_profiles(self):
        with tempfile.TemporaryDirectory(dir=report.ROOT / 'artifacts') as directory:
            out = Path(directory)
            self.role_map(out, ['direct_repair'] * 4)
            original_write = report.write_new
            def interrupted_write(path, value):
                if path.name == 'COMPLETE.json':
                    raise OSError('simulated interruption after complete results')
                original_write(path, value)
            with patch.object(report, 'OUT', out), patch.object(report, 'run_profile', return_value={}) as run:
                with patch.object(report, 'write_new', side_effect=interrupted_write):
                    with self.assertRaises(OSError):
                        report.collect()
                before = (out / 'results.json').read_bytes()
                count = run.call_count
                report.complete_saved()
                report.complete_saved()
                self.assertEqual(run.call_count, count)
                self.assertEqual((out / 'results.json').read_bytes(), before)
                self.assertTrue((out / 'COMPLETE.json').exists())


if __name__ == '__main__':
    unittest.main()
