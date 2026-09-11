"""Fault tests for evidence packaging; never execute the independent controls."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiment.revision import independent_gate_v3_measure as runner


class IndependentMeasurementTests(unittest.TestCase):
    def test_missing_freeze_binding_rejected_before_control_import(self):
        with tempfile.TemporaryDirectory(prefix='gate_freeze_test_') as temporary:
            folder = Path(temporary)
            (folder / 'measurement_freeze.json').write_text(json.dumps({'bindings': {}}), encoding='utf-8')
            with patch.object(runner, 'OUT', folder), patch.object(runner.importlib, 'import_module') as loader:
                with self.assertRaisesRegex(ValueError, 'Incomplete'):
                    runner.main()
                loader.assert_not_called()

    def test_failure_retained_unknown_trace_kept_and_packaging_never_reruns(self):
        def stub(_io, _question):
            return 'SELECT 1'
        controls = [{'case_id': f'test-{i}', 'strategy': strategy, 'solve': stub}
                    for i, strategy in enumerate(s for s in runner.STRATEGIES for _ in range(4))]
        roster = [{**{k: c[k] for k in ('case_id', 'strategy')}, 'callable_name': 'stub'} for c in controls]
        calls = []
        def fake_evaluate(_solve, strategy, salt):
            calls.append(strategy)
            if len(calls) == 2:
                raise RuntimeError('injected evaluator failure')
            return {'strategy': strategy, 'verdict': 'pass', 'runs': [
                {'probe': 'additional_check', 'trace': [
                    {'kind': 'llm', 'prompt': 'Synthetic request', 'system': '', 'n': 1,
                     'temperature': 0.0, 'response': 'SELECT 1', 'decomposition_step': 0,
                     'decomposition_candidates': [0], 'decomposition_ambiguous': False},
                    {'kind': 'execute', 'sql': 'SELECT 1'}],
                 'final': 'SELECT 1', 'error': None},
                {'probe': 'cross_class_action', 'trace': [], 'final': None, 'error': None,
                 'status': 'review_required', 'reasons': ['same_action_template_across_error_classes']}]}
        with tempfile.TemporaryDirectory(prefix='gate_package_test_') as temporary:
            folder = Path(temporary)
            # Keep mocks isolated from the still-blinded newly authored controls.
            for name in runner.REQUIRED:
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('synthetic fixture source', encoding='utf-8')
            freeze = {'bindings': {name: runner.sha(folder / name) for name in runner.REQUIRED},
                      'salt': runner.SALT, 'planned_cases': 32,
                      'strategy_counts': {s: 4 for s in runner.STRATEGIES},
                      'semantic_strategies': list(runner.SEMANTIC), 'case_roster': roster}
            (folder / 'measurement_freeze.json').write_text(json.dumps(freeze), encoding='utf-8')
            with patch.object(runner, 'ROOT', folder), patch.object(runner, 'OUT', folder), patch.object(runner.importlib, 'import_module', return_value=SimpleNamespace(CASES=controls)), patch.object(runner, 'evaluate', side_effect=fake_evaluate), patch.object(runner, 'scenarios', return_value=[]), patch.object(runner.sys, 'argv', ['test']):
                runner.main()
                results = json.loads((folder / 'results.json').read_text(encoding='utf-8'))
                self.assertEqual(len(results['cases']), 32)
                self.assertEqual(results['cases'][1]['verdict'], 'execution_failure')
                self.assertEqual(results['cases'][1]['measurement_error']['type'], 'RuntimeError')
                packet = json.loads((folder / 'review_packet.json').read_text(encoding='utf-8'))
                self.assertEqual(packet['cases'][0]['runs'][0]['probe'], 'additional_check')
                self.assertIsNone(packet['cases'][0]['runs'][0]['question'])
                self.assertEqual(len(results['cases'][0]['runs']), 2)
                self.assertEqual(results['cases'][0]['runs'][1]['probe'], 'cross_class_action')
                self.assertEqual(len(packet['cases'][0]['runs']), 1)
                raw_event = results['cases'][0]['runs'][0]['trace'][0]
                neutral_event = packet['cases'][0]['runs'][0]['trace'][0]
                hidden = {'decomposition_step', 'decomposition_candidates', 'decomposition_ambiguous'}
                self.assertTrue(hidden.issubset(raw_event))
                self.assertEqual(neutral_event, {k: v for k, v in raw_event.items() if k not in hidden})
                self.assertEqual(sum(c['review_mode'] == 'semantic' for c in packet['cases']), 20)
                packet_hash = runner.sha(folder / 'review_packet.json')
                # Simulate an interrupted publication, preserving measured results.
                (folder / 'COMPLETE.json').unlink()
                (folder / 'review_packet.json').unlink()
                (folder / 'review_packet.json.interrupted.tmp').write_text('{', encoding='utf-8')
                (folder / 'COMPLETE.json.interrupted.tmp').write_text('{', encoding='utf-8')
                result_hash = runner.sha(folder / 'results.json')
                with patch.object(runner.sys, 'argv', ['test', '--package-only']):
                    runner.main()
                self.assertEqual(len(calls), 32)
                self.assertEqual(runner.sha(folder / 'results.json'), result_hash)
                self.assertEqual(runner.sha(folder / 'review_packet.json'), packet_hash)
                self.assertTrue((folder / 'review_packet.json.interrupted.tmp').exists())
                self.assertTrue((folder / 'COMPLETE.json.interrupted.tmp').exists())
                complete = json.loads((folder / 'COMPLETE.json').read_text(encoding='utf-8'))
                self.assertEqual(complete['results_sha256'], result_hash)
                self.assertEqual(complete['review_packet_sha256'], runner.sha(folder / 'review_packet.json'))


if __name__ == '__main__':
    unittest.main()
