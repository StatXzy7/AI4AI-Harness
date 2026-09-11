"""Exposed-control regressions for v3 repairs, not independent calibration."""
import json
import unittest

from experiment.revision import gate_controls, gate_v2, gate_v3
from experiment.revision import independent_gate_controls as exposed


def decomposition(order=(0, 1), ambiguous=False):
    def solve(io, question):
        plan = json.loads(io.llm(question))
        partials = []
        for index in order:
            target = json.dumps(plan) if ambiguous else plan[index]
            answer = io.llm('Current subquestion: ' + target + '\nPrior: ' + json.dumps(partials))
            partials.append({'step': plan[index], 'answer': answer})
        return io.llm('Assemble SQL from: ' + json.dumps(partials))
    return solve


class GateV3Tests(unittest.TestCase):
    def test_eight_development_positives_and_negative_variants(self):
        semantic = {'hint_guard', 'format_guard', 'two_view', 'error_classify'}
        for strategy, solve in gate_controls.POSITIVE.items():
            expected = 'review_required' if strategy in semantic else 'pass'
            self.assertEqual(gate_v3.evaluate(solve, strategy)['verdict'], expected, strategy)
        negative = list(gate_controls.NEGATIVE.items()) + list(gate_controls.ADVERSARIAL.values())
        for strategy, solve in negative:
            self.assertIn(gate_v3.evaluate(solve, strategy)['verdict'], ('fail', 'review_required'))

    def test_three_frozen_false_rejections_have_expected_transition(self):
        for solve, strategy, after in [
            (exposed.case_021, 'decompose', 'pass'),
            (exposed.case_025, 'error_classify', 'review_required'),
            (exposed.case_026, 'error_classify', 'review_required'),
        ]:
            with self.subTest(case=solve.__name__):
                self.assertEqual(gate_v2.evaluate(solve, strategy)['verdict'], 'fail')
                result = gate_v3.evaluate(solve, strategy)
                self.assertEqual(result['verdict'], after, result)

    def test_prior_context_does_not_repeat_the_first_payload(self):
        result = gate_v3.evaluate(decomposition(), 'decompose', 'context-check')
        self.assertEqual(result['verdict'], 'pass', result)
        for run in result['runs']:
            calls = [c for c in run['trace'] if c['kind'] == 'llm']
            self.assertNotEqual(calls[1]['response'], calls[2]['response'])
            self.assertEqual([c['decomposition_step'] for c in calls[1:3]], [0, 1])

    def test_reversed_and_repeated_steps_fail(self):
        for order in [(1, 0), (0, 0)]:
            result = gate_v3.evaluate(decomposition(order), 'decompose')
            self.assertEqual(result['verdict'], 'fail', result)
            self.assertTrue(any('ordered_subquestions_not_answered' in r['reasons'] for r in result['runs']))

    def test_ambiguous_target_is_retained_for_review(self):
        result = gate_v3.evaluate(decomposition(ambiguous=True), 'decompose')
        self.assertEqual(result['verdict'], 'review_required', result)
        for run in result['runs']:
            self.assertIn('decomposition_request_attribution_ambiguous', run['reasons'])
            self.assertNotIn('counterfactual_output_mismatch', run['reasons'])

    def test_ambiguity_does_not_erase_missing_subquestion_calls(self):
        result = gate_v3.evaluate(exposed.case_023, 'decompose')
        self.assertEqual(result['verdict'], 'fail', result)

    def test_discarded_and_fabricated_answers_still_fail(self):
        for solve in [exposed.case_024, gate_controls.fabricated_parts]:
            result = gate_v3.evaluate(solve, 'decompose')
            self.assertEqual(result['verdict'], 'fail', result)

    def test_classification_impostors_never_automatically_pass(self):
        for solve in [exposed.case_027, exposed.case_028, gate_controls.all_classes,
                      gate_controls.punctuation_classes, gate_controls.shared_two_actions]:
            self.assertIn(gate_v3.evaluate(solve, 'error_classify')['verdict'], ('fail', 'review_required'))

    def test_classification_independent_structural_failures_stay_hard(self):
        for solve, reason in [
            (gate_controls.passthrough, 'initial_sql_not_executed'),
            (gate_controls.batch_repair, 'extra_batched_samples'),
            (gate_controls.read_discard, 'execution_feedback_not_carried_forward'),
        ]:
            result = gate_v3.evaluate(solve, 'error_classify')
            self.assertEqual(result['verdict'], 'fail', solve.__name__)
            self.assertTrue(any(r['status'] == 'fail' and reason in r['reasons'] for r in result['runs']), result)

    def test_unrelated_exposed_strategies_have_identical_runs(self):
        for case in exposed.CASES:
            if case['strategy'] in ('decompose', 'error_classify'):
                continue
            old = gate_v2.evaluate(case['solve'], case['strategy'], 'same-comparison-salt')
            new = gate_v3.evaluate(case['solve'], case['strategy'], 'same-comparison-salt')
            self.assertEqual(old['runs'], new['runs'], case['case_id'])
            self.assertEqual(old['verdict'], new['verdict'], case['case_id'])


if __name__ == '__main__':
    unittest.main()
