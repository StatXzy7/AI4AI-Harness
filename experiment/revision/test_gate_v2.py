"""Development regression tests, not an independent gate calibration set."""
import unittest

from experiment.revision import gate_controls as controls
from experiment.revision.gate_v2 import Probe, STRATEGIES, SQL_A, evaluate, run_probe, scenarios


class GateV2Tests(unittest.TestCase):
    def test_all_eight_positive_control_contracts(self):
        self.assertEqual(set(controls.POSITIVE),set(STRATEGIES))
        for name,solve in controls.POSITIVE.items():
            with self.subTest(strategy=name):
                result=evaluate(solve,name)
                expected='review_required' if name in ('hint_guard','format_guard','two_view','error_classify') else 'pass'
                self.assertEqual(result['verdict'],expected,result)

    def test_eight_negative_variants_are_not_admitted(self):
        for name,solve in controls.NEGATIVE.items():
            with self.subTest(strategy=name):
                result=evaluate(solve,name)
                self.assertIn(result['verdict'],('fail','review_required'),result)

    def test_conditional_success_and_changed_error_are_separate_probes(self):
        probes=scenarios('repair')
        self.assertEqual(probes[0].responses[0],probes[1].responses[0])
        self.assertEqual(probes[1].responses,probes[2].responses)
        self.assertNotEqual(probes[1].error,probes[2].error)
        result=evaluate(controls.unconditional,'repair')
        self.assertEqual(result['verdict'],'fail')
        self.assertIn('unconditional_extra_generation',result['runs'][0]['reasons'])
        success=evaluate(controls.repair,'repair')['runs'][0]
        self.assertEqual(success['status'],'pass')
        self.assertEqual(sum(x['kind']=='llm' for x in success['trace']),1)

    def test_counterfactual_markers_are_not_fixed_to_default_salt(self):
        for name in ('repair','schema_link','decompose','error_classify'):
            with self.subTest(strategy=name):
                expected='review_required' if name=='error_classify' else 'pass'
                self.assertEqual(evaluate(controls.POSITIVE[name],name,'alternate_seed')['verdict'],expected)

    def test_uncertain_prompt_witness_is_review_not_no_mechanism(self):
        for name in ('hint_guard','format_guard'):
            result=evaluate(controls.passthrough,name)
            self.assertEqual(result['verdict'],'review_required')
        self.assertEqual(run_probe(controls.passthrough,Probe('plain','hint_guard',expected=SQL_A))['status'],'review_required')

    def test_adversarial_impostors_never_receive_automatic_pass(self):
        for name,(strategy,solve) in controls.ADVERSARIAL.items():
            with self.subTest(mutant=name):
                self.assertIn(evaluate(solve,strategy)['verdict'],('fail','review_required'))

    def test_execution_vote_counterfactual_holds_candidates_fixed(self):
        first,second,third=scenarios('vote3')[-3:]
        self.assertEqual(first.responses,second.responses)
        self.assertNotEqual(first.expected,second.expected)
        self.assertEqual(second.responses,third.responses)
        self.assertFalse(set([first.expected]+first.accepted)&set([second.expected]+second.accepted)&set([third.expected]+third.accepted))
        self.assertEqual(evaluate(controls.vote3,'vote3')['verdict'],'pass')

    def test_decomposition_counterfactual_keeps_plan_changes_opaque_answers(self):
        first,second=scenarios('decompose')
        self.assertEqual(first.steps,second.steps)
        self.assertEqual(first.responses,second.responses)
        self.assertNotEqual(first.answers,second.answers)

    def test_crash_invalid_output_and_unknown_contract_are_distinct(self):
        self.assertEqual(evaluate(controls.crash,'repair')['verdict'],'execution_failure')
        self.assertEqual(evaluate(controls.invalid,'repair')['verdict'],'execution_failure')
        with self.assertRaisesRegex(ValueError,'unknown explicit strategy'):
            evaluate(controls.repair,'auto_guess')


if __name__ == '__main__':
    unittest.main()
