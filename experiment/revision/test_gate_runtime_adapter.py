"""Local trusted-runtime adapter checks; requires the archived/restored TTHE sources."""
import sys
import unittest

from experiment.revision.gate_runtime_adapter import candidate
from experiment.revision.gate_v2 import evaluate
from experiment.revision.replay import ROOT


class GateRuntimeTests(unittest.TestCase):
    def test_real_harness_base_and_trusted_positive_negative_controls(self):
        previous=sys.modules.get('text_to_sql.bridge')
        cases=[('hpc_repair','repair','pass'),('hpc_vote3','vote3','pass'),
               ('neg_uncond_twocall','repair','fail'),('neg_selectfirst','vote3','fail'),
               ('bare','format_guard','review_required')]
        for name,strategy,expected in cases:
            with self.subTest(control=name):
                with candidate(ROOT/f'external/TTHE/text_to_sql/agents/{name}.py') as solve:
                    result=evaluate(solve,strategy)
                    self.assertEqual(result['verdict'],expected,result)
                self.assertFalse(any(n.startswith('_gate_probe_') for n in sys.modules))
        self.assertIs(sys.modules.get('text_to_sql.bridge'),previous)

    def test_adapter_cleanup_after_caller_exception(self):
        with self.assertRaisesRegex(RuntimeError,'test cleanup'):
            with candidate(ROOT/'external/TTHE/text_to_sql/agents/hpc_repair.py'):
                raise RuntimeError('test cleanup')
        self.assertFalse(any(n.startswith('_gate_probe_') for n in sys.modules))


if __name__ == '__main__':
    unittest.main()
