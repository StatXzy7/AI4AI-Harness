"""Unit tests for the diagnostics pipeline (offline, no model APIs)."""
from __future__ import annotations

import unittest

import numpy as np

from experiment.diagnostics import core, controls as ctl
from experiment.diagnostics.math_adapter import judge_v2
from experiment.diagnostics.cli import _m0_metrics, _m1_metrics, _run_diagnostic


class TestJudgeV2(unittest.TestCase):
    def test_endpoint_sensitivity(self):
        # closed vs open bracket predictions on identical values must differ
        self.assertEqual(judge_v2("[0,1]", "(0,1)"), 0)
        self.assertEqual(judge_v2("(0,1)", "(0,1)"), 1)
        self.assertEqual(judge_v2("(0,1]", "(0,1)"), 0)
        self.assertEqual(judge_v2("[3,\\infty)", "3<=x"), 0)

    def test_agreement_with_v1_on_plain_answers(self):
        self.assertEqual(judge_v2("The answer is \\boxed{42}.", "42"), 1)
        self.assertEqual(judge_v2("\\boxed{\\frac{1}{2}}", "0.5"), 1)  # numeric path
        self.assertEqual(judge_v2("no answer here", "7"), 0)


class TestCore(unittest.TestCase):
    def _pop(self, Y, **kw):
        return ctl._pop(Y, kw.get("members", ["bare", "a", "b"]),
                        ctl._task_ids(Y.shape[1]), ctl._task_ids(20)[:20])

    def test_decomposition_identical_members_refutes(self):
        Y = np.tile([[1], [1], [1]], (1, 30)).astype(float)
        Y = np.hstack([np.tile([1., 1., 1.], (30, 1)).T, np.zeros((3, 5))])
        pop = self._pop(Y)
        s2 = core.s2_decomposition(pop)
        self.assertEqual(s2["state"], core.REFUTED)   # exact-zero headroom CI

    def test_decomposition_detects_coverage(self):
        rng = np.random.default_rng(3)
        Y = (rng.random((3, 120)) < 0.5).astype(float)
        s2 = core.s2_decomposition(self._pop(Y))
        self.assertEqual(s2["state"], core.SUPPORTED)

    def test_s3_abstains_without_repeats(self):
        pop = self._pop((np.random.default_rng(1).random((3, 60)) < 0.6).astype(float))
        s3 = core.s3_stability({"single": pop})
        self.assertEqual(s3["state"], core.INSUFFICIENT)

    def test_s3_supported_with_matched_repeats(self):
        rng = np.random.default_rng(5)
        base = (rng.random((3, 40)) < 0.5).astype(float)
        base[1] = 1.0                       # member a always right -> stable
        pops = {f"r{r}": self._pop(base) for r in range(3)}
        s3 = core.s3_stability(pops)
        self.assertEqual(s3["state"], core.SUPPORTED)
        self.assertTrue(any(p["state"] == core.SUPPORTED for p in s3["pairs"]))

    def test_s3_missing_kept_in_denominator(self):
        base = np.ones((3, 40)) * 0.5
        base[2, 0] = np.nan                 # unknown cell: stays in denominator
        pops = {f"r{r}": self._pop(base) for r in range(3)}
        s3 = core.s3_stability(pops)
        a0 = s3["pairs"][0]["mean_delta"]   # bare vs member a: equal rates -> 0
        self.assertEqual(a0, 0.0)

    def test_s4_positive_control_supported(self):
        pop = ctl.get_control("C4", 1)
        s4 = core.s4_selectability(pop)
        self.assertEqual(s4["state"], core.SUPPORTED)

    def test_s5_harm_reduces_utility(self):
        pop = ctl.get_control("C6", 1)
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertEqual(s5["state"], core.REFUTED)
        self.assertEqual(s5["budget_calls_per_task"], 1)
        self.assertEqual(s5["lambda_harm"], 1.0)

    def test_k_stats_same_denominator(self):
        pop = ctl.get_control("C4", 1)
        ks = pop.k_stats()
        self.assertIn("vectors_per_gen_incl_bare", ks)
        self.assertIn("vectors_per_gen_excl_bare", ks)
        self.assertEqual(ks["K_raw"], pop.n_gen)


class TestControls(unittest.TestCase):
    def test_package_frozen_shape(self):
        pkg = ctl.build_package()
        self.assertEqual(pkg["n_controls"], 16)
        self.assertEqual(len(pkg["blinded"]), 8)
        self.assertEqual(len(pkg["calibration"]), 8)

    def test_all_controls_match_expected(self):
        pkg = ctl.build_package()
        for c in pkg["controls"]:
            pop = ctl.get_control(c["cid"], c["instance"])
            got = _run_diagnostic(pop)
            for k in ("B", "C", "D", "E"):
                self.assertEqual(got[k], c["expected"][k],
                                 f"{c['cid']}#{c['instance']} {k}: "
                                 f"{c['expected'][k]} != {got[k]}")

    def test_stable_seeds(self):
        p1 = ctl.get_control("C4", 1)
        p2 = ctl.get_control("C4", 1)
        self.assertTrue(np.array_equal(p1.Y, p2.Y))


class TestMetricsComparison(unittest.TestCase):
    def test_m1_reports_integrity_m0_does_not(self):
        pop = ctl.get_control("C4", 1)
        m0 = _m0_metrics(pop)
        m1 = _m1_metrics(pop)
        self.assertNotIn("integrity", m0)
        self.assertIn("integrity", m1)
        self.assertIn("headroom", m1)


if __name__ == "__main__":
    unittest.main()
