"""Integration regression evidence for CURRENT behavior, including known defects.

Passing these checks does not release the runtime for independent repeats.
Requires the separate runtime environment; all requests go to loopback.
"""
import unittest

from experiment.revision.runtime_probe import run_probe


class RuntimeProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_probe()

    def test_real_collector_resume_repeat_and_cache_bypass(self):
        cases = self.result['collector_cases']
        self.assertEqual([c['http_requests'] for c in cases], [1, 0, 0, 1, 1, 0])
        rows = self.result['collector_rows']
        self.assertEqual([r['repeat'] for r in rows], [0, 1, 2, 3])
        self.assertEqual(rows[0]['final_sql'], rows[1]['final_sql'])
        self.assertEqual(len({r['final_sql'] for r in rows}), 3)
        self.assertTrue(all(r['error'] is None and r['official_correct'] == 1 for r in rows))

    def test_unflushed_cache_defect_is_reproduced(self):
        cases = self.result['pending_cache']
        self.assertEqual([c['http_requests'] for c in cases], [1, 1, 0, 1])
        self.assertEqual(cases[0]['answer'], cases[2]['answer'])
        self.assertNotEqual(cases[1]['answer'], cases[3]['answer'])

    def test_logical_calls_do_not_count_samples_or_sdk_retry_requests(self):
        multi = self.result['multi_sample']
        self.assertEqual(multi['logical_trace_calls'], 1)
        self.assertEqual(multi['http_requests'], 3)
        self.assertEqual(len(set(multi['outputs'])), 3)
        retry = self.result['retry']
        self.assertEqual(retry, {'logical_trace_calls': 1, 'http_requests': 2, 'sdk_create_calls': 1,
                                 'statuses': [429, 200]})

    def test_returned_provider_usage_is_missing_from_collector_rows(self):
        ledger = self.result['provider_ledger']
        success = [r for r in ledger if r['status'] == 200]
        self.assertTrue(success)
        self.assertTrue(all(r['usage']['total_tokens'] == 18 for r in success))
        self.assertTrue(all('usage' not in r and 'total_tokens' not in r
                            and 'response_id' not in r for r in self.result['collector_rows']))
        self.assertTrue(all(r['path'] == '/v1/chat/completions' for r in ledger))

    def test_thinking_path_does_not_transmit_requested_temperature(self):
        request = self.result['thinking_request']
        self.assertNotIn('temperature', request)
        self.assertEqual(request['thinking'], {'type': 'enabled'})
        self.assertEqual(request['reasoning_effort'], 'high')

    def test_actual_project_judges_preserve_numeric_and_string_distinction(self):
        cases = self.result['judge_cases']
        self.assertEqual([(c['official'], c['legacy']) for c in cases],
                         [(1, 0), (0, 1), (1, 1), (0, 0)])


if __name__ == '__main__':
    unittest.main()
