"""Packet blinding and immutable-input checks without evaluating reference controls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from experiment.revision.common_pool import file_hash
from experiment.revision.independent_gate_v4_measure import ROOT, review_runs, validate, validate_dependencies


class MeasurementTests(unittest.TestCase):
    def test_dependencies_reject_omission_and_instrument_conflict(self):
        instrument_path = 'artifacts/revision_20260910/gate_v4_regression/instrument_freeze.json'
        instrument = json.loads((ROOT / instrument_path).read_text(encoding='utf-8'))
        bindings = dict(instrument['bindings'])
        names = ['experiment/revision/independent_gate_v4_measure.py',
                 'experiment/phase2/generate.py',
                 'experiment/revision/code_responses.py', 'experiment/revision/fresh_runtime.py',
                 'review-stage/GATE_V4_CALIBRATION_PROTOCOL.md', instrument_path]
        bindings.update({name: file_hash(ROOT / name) for name in names})
        # Only dependency validation is exercised; these placeholders are never measured.
        freeze = dict(bindings=bindings, instrument_freeze_path=instrument_path,
                      source_path=names[0], inventory_path=names[0],
                      author_reference_path=names[0], source_review_path=names[0])
        validate_dependencies(freeze)
        missing = deepcopy(freeze)
        del missing['bindings']['experiment/revision/common_pool.py']
        with self.assertRaisesRegex(ValueError, 'not bound'):
            validate_dependencies(missing)
        conflict = deepcopy(freeze)
        conflict['bindings']['experiment/revision/gate_v4.py'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            validate_dependencies(conflict)

    def test_typed_packet_preserves_observations_without_derived_decisions(self):
        result = dict(structural_verdict='review_required', runs=[dict(
            case=dict(name='parts_0', final='EXPECTED', category_reply='EXPECTED_CLASS'),
            status='review_required', interface_issues=['derived issue'],
            final='ACTUAL', error=None, trace=[dict(kind='llm', prompt='actual request', system='',
              n=1, response='actual answer', response_role='assembly_sql', target_step=1,
              decomposition_ambiguous=False), dict(kind='execute', sql='actual SQL', ok=False,
              rows=[], error='actual SQLite error', error_type='OperationalError')])])
        before = deepcopy(result)
        exported = review_runs(result, 'decompose', 'test')
        self.assertEqual(exported[0]['trace'][0], dict(kind='llm', prompt='actual request', system='', n=1, response='actual answer'))
        self.assertEqual(exported[0]['trace'][1], result['runs'][0]['trace'][1])
        self.assertEqual(exported[0]['final'], 'ACTUAL')
        self.assertNotIn('EXPECTED', json.dumps(exported))
        self.assertNotIn('derived issue', json.dumps(exported))
        self.assertEqual(result, before)

    def test_changed_input_leaves_durable_invalid_marker(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as temporary:
            folder = Path(temporary)
            source = folder/'source.txt'
            source.write_text('original', encoding='utf-8')
            freeze = dict(bindings={source.relative_to(ROOT).as_posix(): file_hash(source)})
            output = folder/'measurement'
            output.mkdir()
            validate(freeze, output)
            source.write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'frozen input changed'):
                validate(freeze, output)
            self.assertTrue((output/'INVALID.json').is_file())
            source.write_text('original', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'marked invalid'):
                validate(freeze, output)


if __name__ == '__main__':
    unittest.main()
