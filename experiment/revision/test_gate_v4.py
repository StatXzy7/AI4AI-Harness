"""Integrated measurement tests; no provider calls or independent calibration."""
import unittest

from experiment.revision import gate_v3, gate_v4


class GateV4Tests(unittest.TestCase):
    def test_unassigned_profile_never_executes_or_rejects(self):
        def forbidden(*_):
            raise AssertionError('unassigned profile executed')
        result = gate_v4.evaluate(forbidden, 'schema_link')
        self.assertEqual(result['structural_verdict'], 'review_required')
        self.assertEqual(result['runs'], [])
        self.assertEqual(result['admission'], 'not_evaluated')

    def test_old_single_call_contract_still_requires_review(self):
        def plain(io, question):
            return io.llm(question + '\n' + gate_v3.SCHEMA)
        result = gate_v4.evaluate(plain, 'format_guard')
        self.assertEqual(result['structural_verdict'], 'review_required')
        self.assertTrue(all('explicit_sql_only_fence_requirement_not_observed' in r['reasons'] for r in result['runs']))

    def test_category_reply_occurs_only_after_failure_and_before_sql(self):
        def classify(io, question):
            sql = io.llm(question + '\n' + io.schema)
            executed = io.execute(sql)
            if executed['ok']:
                return sql
            category = io.llm('Classify: ' + executed['error'])
            fixed = io.llm('Repair ' + category + ': ' + executed['error'])
            io.execute(fixed)
            return fixed
        result = gate_v4.evaluate(classify, 'error_classify', profile='llm_classifier')
        self.assertEqual(len(result['runs']), 9)
        for r in result['runs']:
            self.assertIsNone(r['error'])
            roles = [x['response_role'] for x in r['trace'] if x['kind'] == 'llm']
            expected = ['initial_sql'] if r['case']['name'] in ('success', 'executable_other_column') else ['initial_sql', 'classification', 'repair_sql']
            self.assertEqual(roles, expected)
        overflow = next(r for r in result['runs'] if r['case']['name'] == 'sqlite_numeric_overflow')
        self.assertIn('integer overflow', overflow['trace'][1]['error'])
        invalid = next(r for r in result['runs'] if r['case']['name'] == 'category_invalid')
        self.assertTrue(invalid['case']['diagnostic_only'])
        self.assertEqual(invalid['trace'][2]['response'], 'unrecognized category')

    def test_context_preservation_is_not_automatic_schema_rejection(self):
        def link(io, question):
            linked = io.llm(question)
            return io.llm('Use only this linked subset: ' + linked + '\n' + gate_v3.SCHEMA)
        result = gate_v4.evaluate(link, 'schema_link', profile='tables_columns_json')
        self.assertEqual(result['structural_verdict'], 'review_required')
        self.assertEqual(len(result['runs']), 3)
        self.assertTrue(all(r['admission'] == 'not_evaluated' for r in result['runs']))


if __name__ == '__main__':
    unittest.main()
