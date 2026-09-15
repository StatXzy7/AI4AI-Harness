"""Unit tests for the diagnostics pipeline (offline, no model APIs)."""
from __future__ import annotations

import unittest

import numpy as np

from experiment.diagnostics import core, controls as ctl, challenges as chal
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
        pops = {}
        for r in range(3):
            p = self._pop(base)
            # independent execution noise per repeat: identical matrices are
            # refused by S3 (clone gate), as they should be
            p.Y[0] = (np.random.default_rng(100 + r).random(40) < 0.5).astype(float)
            p.Y[2] = (np.random.default_rng(200 + r).random(40) < 0.5).astype(float)
            pops[f"r{r}"] = p
        s3 = core.s3_stability(pops)
        self.assertEqual(s3["state"], core.SUPPORTED)
        self.assertTrue(any(p["state"] == core.SUPPORTED
                            for p in s3["stable_ranking"]["pairs"]))

    def test_s3_missing_kept_in_denominator(self):
        pops = {}
        for r in range(3):
            base = np.ones((3, 40)) * 0.5
            base[2, 0] = np.nan             # unknown cell: stays in denominator
            p = self._pop(base)
            p.Y[0] = 0.5
            p.Y[1] = 0.5
            # independent draw for member b per repeat: identical matrices are
            # refused by S3 (clone gate), as they should be
            p.Y[2] = (np.random.default_rng(400 + r).random(40) < 0.5).astype(float)
            p.Y[2, 0] = np.nan
            pops[f"r{r}"] = p
        s3 = core.s3_stability(pops)
        pair = next(p for p in s3["stable_ranking"]["pairs"]
                    if (p["h1"], p["h2"]) == ("a", "bare"))
        self.assertAlmostEqual(pair["mean_delta"], 0.0, places=6)

    def test_s3_identical_matrices_abstain(self):
        """Three byte-identical matrices: 'repeats' whose independence cannot
        be verified must abstain, not SUPPORT."""
        base = (np.random.default_rng(7).random((3, 40)) < 0.5).astype(float)
        base[1] = 1.0
        pops = {f"r{r}": self._pop(base) for r in range(3)}
        s3 = core.s3_stability(pops)
        self.assertEqual(s3["state"], core.INSUFFICIENT)
        self.assertIn("identical", s3["reason"])

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
        self.assertEqual(pkg["n_controls"], 24)
        self.assertEqual(len(pkg["blinded"]), 12)
        self.assertEqual(len(pkg["calibration"]), 12)

    def test_all_controls_match_expected(self):
        pkg = ctl.build_package()
        for c in pkg["controls"]:
            pop = ctl.get_control(c["cid"], c["instance"])
            got = _run_diagnostic(pop)
            for k in ("B", "C", "C_comp", "D", "E"):
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


class TestS3Invariants(unittest.TestCase):
    """Invariants the S3 stability estimands MUST satisfy (external review
    2026-09-15): permutation invariance, dominance != complementarity, and
    refusal of condition-mixed / cloned / identity-broken repeats."""

    @staticmethod
    def _review_case(member_order):
        """The reviewer's counterexample population: bare ~ Bernoulli(0.5)
        independently per repeat, a right on the first 20 tasks, b right
        everywhere - 40 tasks, 3 repeats. Only the MEMBER LIST ORDER varies;
        the id->data mapping is fixed."""
        data = {
            "bare": (np.random.default_rng(900).random(40) < 0.5).astype(float),
            "a":    np.concatenate([np.ones(20), np.zeros(20)]),
            "b":    np.ones(40),
        }
        pops = {}
        for r in range(3):
            rows = []
            for m in member_order:
                row = data[m].copy()
                if m == "bare":
                    row = (np.random.default_rng(900 + r).random(40) < 0.5).astype(float)
                rows.append(row)
            pops[f"r{r}"] = ctl.Population(
                member_ids=list(member_order),
                source_hashes=[f"h_{m}" for m in member_order],
                tasks=ctl._task_ids(40), Y=np.vstack(rows),
                condition={"c": "synthetic"}, has_bare=True,
                dev_task_ids=[], task_meta={}, calls={})
        return pops

    def test_s3_population_conclusion_is_permutation_invariant(self):
        s_ab = core.s3_stability(self._review_case(["bare", "a", "b"]))
        s_ba = core.s3_stability(self._review_case(["bare", "b", "a"]))
        # the pre-fix code returned REFUTED for one order and SUPPORTED for the
        # other; the population-level conclusion must not depend on ordering
        self.assertEqual(s_ab["state"], s_ba["state"])
        self.assertEqual(s_ab["stable_complementarity"]["state"],
                         s_ba["stable_complementarity"]["state"])
        self.assertEqual(s_ab["state"], core.SUPPORTED)   # stable ranking exists
        # pair reports must be identical as a set (same named pairs, same states)
        pairs_a = {(p["h1"], p["h2"], p["state"]) for p in s_ab["stable_ranking"]["pairs"]}
        pairs_b = {(p["h1"], p["h2"], p["state"]) for p in s_ba["stable_ranking"]["pairs"]}
        self.assertEqual(pairs_a, pairs_b)

    def test_s3_dominance_is_not_complementarity(self):
        """b dominates on every task: stable ranking SUPPORTED, but H_stable = 0
        -> complementarity REFUTED. A global-dominance reading of a ranking
        result must be impossible."""
        s3 = core.s3_stability(self._review_case(["bare", "a", "b"]))
        self.assertEqual(s3["state"], core.SUPPORTED)
        self.assertEqual(s3["stable_complementarity"]["state"], core.REFUTED)
        self.assertEqual(s3["stable_complementarity"]["H_stable"], 0.0)

    def test_s3_crossover_complementarity_detected(self):
        """Equal mean accuracy with opposite per-stratum skill: no stable mean
        difference (ranking INSUFFICIENT) but real complementarity SUPPORTED."""
        pops = ctl.get_control("C10", 1)
        s3 = core.s3_stability(pops)
        self.assertEqual(s3["state"], core.INSUFFICIENT)
        self.assertEqual(s3["stable_complementarity"]["state"], core.SUPPORTED)
        self.assertGreater(s3["stable_complementarity"]["H_stable"], 0)

    def test_s3_refuses_condition_mixed_repeats(self):
        s3 = core.s3_stability(ctl.get_control("C11", 1))
        self.assertEqual(s3["state"], core.INSUFFICIENT)
        self.assertIn("condition", s3["reason"])

    def test_s3_refuses_cloned_repeats(self):
        s3 = core.s3_stability(ctl.get_control("C12", 1))
        self.assertEqual(s3["state"], core.INSUFFICIENT)
        self.assertIn("identical", s3["reason"])

    def test_s3_refuses_changed_source_identity(self):
        """A member whose source hash changes across 'repeats' cannot form a
        matched-repeat set (changed code masquerading as repeats)."""
        pops = ctl.get_control("C9", 1)
        pops["r2"].source_hashes[2] = "hCHANGED"
        s3 = core.s3_stability(pops)
        self.assertEqual(s3["state"], core.INSUFFICIENT)
        self.assertIn("identity", s3["reason"].lower() + s3["reason"])

    def test_s3_missing_sensitivity_bounds_reported(self):
        s3 = core.s3_stability(ctl.get_control("C9", 1))
        for p in s3["stable_ranking"]["pairs"]:
            self.assertIn("missing_sensitivity_bounds", p)
            lo, hi = p["missing_sensitivity_bounds"]
            self.assertLessEqual(lo, p["mean_delta"] + 1e-9)

    def test_s3_condition_compare_is_type_safe(self):
        """{timeout: 60} and {timeout: '60'} are DIFFERENT execution conditions
        (canonical typed JSON comparison, not str())."""
        pops = ctl.get_control("C9", 1)
        pops["r2"].condition = {"c": "synthetic", "timeout": "60"}   # str, not int
        s3 = core.s3_stability(pops)
        self.assertEqual(s3["state"], core.INSUFFICIENT)
        self.assertIn("condition", s3["reason"])

    def test_s3_condition_null_vs_missing_key_differ(self):
        """An absent key and an explicit null are DIFFERENT conditions
        (recheck2 blocker #3): the whole typed condition object is compared."""
        pops = ctl.get_control("C9", 1)
        pops["r2"].condition = {"c": "synthetic", "timeout": None}
        s3 = core.s3_stability(pops)
        self.assertEqual(s3["state"], core.INSUFFICIENT)
        pops2 = ctl.get_control("C9", 1)
        pops2["r2"].condition = {}                     # both keys absent
        s3b = core.s3_stability(pops2)
        self.assertEqual(s3b["state"], core.INSUFFICIENT)

    def test_s3_comp_abstains_on_unidentified_expectation(self):
        """A (member, task) cell with NO valid repeat across all repeats leaves
        the per-task expectation unknown; C-comp must abstain, never report
        H_stable from a 0-imputation."""
        pops = ctl.get_control("C9", 1)
        for r in pops.values():
            r.Y[2, 7] = np.nan          # 'dom' has no valid repeat on task 7
        s3 = core.s3_stability(pops)
        comp = s3["stable_complementarity"]
        self.assertEqual(comp["state"], core.INSUFFICIENT)
        self.assertIsNone(comp["H_stable"])
        self.assertIn("unidentified", comp["reason"])


class TestS1ExecutionState(unittest.TestCase):
    """A check that was not run must never be rendered as passed."""

    def _pop(self):
        return ctl.get_control("C4", 1)

    def test_not_executed_judge_replay_blocks_supported(self):
        pop = self._pop()
        manifest = {"member_ids": pop.member_ids, "task_ids": pop.tasks}
        s1 = core.s1_integrity(
            manifest, pop,
            {"status": core.JUDGE_REPLAY_NOT_EXECUTED, "mismatches": None},
            0, [])
        self.assertIsNone(s1["checks"]["judge_replay_consistent"])
        self.assertEqual(s1["state"], core.INSUFFICIENT)
        self.assertIn("judge_replay_consistent", s1["not_run"])

    def test_executed_zero_mismatch_supports(self):
        pop = self._pop()
        manifest = {"member_ids": pop.member_ids, "task_ids": pop.tasks}
        s1 = core.s1_integrity(manifest, pop,
                               {"status": core.JUDGE_REPLAY_EXECUTED,
                                "mismatches": 0}, 0, [])
        self.assertEqual(s1["state"], core.SUPPORTED)

    def test_bare_count_means_executed(self):
        """Backward compat: a plain mismatch count is treated as executed."""
        pop = self._pop()
        manifest = {"member_ids": pop.member_ids, "task_ids": pop.tasks}
        s1 = core.s1_integrity(manifest, pop, 3, 0, [])
        self.assertEqual(s1["judge_replay_status"], core.JUDGE_REPLAY_EXECUTED)
        self.assertEqual(s1["state"], core.REFUTED)


class TestS5BudgetGate(unittest.TestCase):
    """Frozen E contract: without verifiable call-budget evidence, E is
    INSUFFICIENT regardless of the utility interval (recheck blocker #1)."""

    def test_archive_without_calls_cannot_support(self):
        pop = ctl.get_control("C4", 1)
        pop.budget_by_construction = False      # strip the design exception
        pop.calls = {}
        pop.calls_status = "not_provided"
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertEqual(s5["state"], core.INSUFFICIENT)
        self.assertFalse(s5["budget_verified"])

    def test_construction_budget_allows_support(self):
        pop = ctl.get_control("C4", 1)          # budget_by_construction=True
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertEqual(s5["state"], core.SUPPORTED)
        self.assertTrue(s5["budget_verified"])

    def test_per_record_calls_verify_budget(self):
        pop = ctl.get_control("C4", 1)
        pop.budget_by_construction = False
        pop.calls = {(m, t): 1 for m in pop.member_ids for t in pop.tasks}
        pop.calls_status = "per_record"
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertEqual(s5["state"], core.SUPPORTED)

    def test_aggregate_only_does_not_verify(self):
        """An aggregate total is not per-task verification (recheck2 blocker #2)."""
        pop = ctl.get_control("C4", 1)
        pop.budget_by_construction = False
        pop.calls = {}
        pop.calls_status = "aggregate_only"
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertEqual(s5["state"], core.INSUFFICIENT)
        self.assertIn("aggregate", s5["budget_basis"])

    def test_partial_records_do_not_verify(self):
        pop = ctl.get_control("C4", 1)
        pop.budget_by_construction = False
        all_pairs = [(m, t) for m in pop.member_ids for t in pop.tasks]
        pop.calls = {p: 1 for p in all_pairs[:-5]}      # 5 cells missing
        pop.calls_status = "per_record"
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertEqual(s5["state"], core.INSUFFICIENT)
        self.assertEqual(s5["budget_basis"], "per_record_incomplete")

    def test_over_budget_records_do_not_verify(self):
        pop = ctl.get_control("C4", 1)
        pop.budget_by_construction = False
        pop.calls = {(m, t): 3 for m in pop.member_ids for t in pop.tasks}
        pop.calls_status = "per_record"
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertEqual(s5["state"], core.INSUFFICIENT)
        self.assertIn("over_budget", s5["budget_basis"])

    def test_nan_call_records_do_not_verify(self):
        """NaN is not a verified call count (recheck3 blocker)."""
        pop = ctl.get_control("C4", 1)
        pop.budget_by_construction = False
        calls = {(m, t): 1 for m in pop.member_ids for t in pop.tasks}
        calls[(pop.member_ids[1], pop.tasks[0])] = float("nan")
        pop.calls = calls
        pop.calls_status = "per_record"
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertEqual(s5["state"], core.INSUFFICIENT)
        self.assertIn("malformed", s5["budget_basis"])


class TestS4CrossValidation(unittest.TestCase):
    """Plan 3.D conformance: the frozen policy is a 5-fold-CV fit on dev
    (recheck blocker #2)."""

    def test_cv_direction_matches_reference_implementation(self):
        """The fold models must be TRAINED ON THE OTHER n_folds-1 FOLDS and
        averaged (recheck2 blocker #1). Compare against an explicit reference
        implementation with the same fold assignment."""
        import numpy as np
        rng = np.random.default_rng(0)
        n_dev, n_ev, n_feat = 30, 20, 2
        X_dev = rng.normal(size=(n_dev, n_feat))
        X_ev = rng.normal(size=(n_ev, n_feat))
        w_true = np.array([1.5, -1.0])
        y_dev = (rng.random(n_dev) < core._sigmoid(X_dev @ w_true)).astype(float)
        got = core._fit_member_probs(X_dev, y_dev[None, :], X_ev)

        # reference: replicate the fold assignment (pattern-stratified global
        # round-robin, same seed) and train each fold model on the OTHER folds
        fold_rng = np.random.default_rng(20260915)
        fold_order = fold_rng.permutation(n_dev)
        groups = {}
        keys = [groups.setdefault(tuple(X_dev[i]), len(groups)) for i in range(n_dev)]
        order = sorted(range(n_dev), key=lambda i: (keys[i], fold_order[i]))
        fold_of = np.zeros(n_dev, dtype=int)
        for pos, i in enumerate(order):
            fold_of[i] = pos % 5
        preds = []
        for f in range(5):
            tr = fold_of != f
            w = np.zeros(n_feat); b0 = 0.0
            X_tr, y_tr = X_dev[tr], y_dev[tr]
            for _ in range(2000):
                p = core._sigmoid(X_tr @ w + b0)
                g = (X_tr.T @ (p - y_tr)) / len(y_tr)
                w -= 0.5 * g
                b0 -= 0.5 * float(np.mean(p - y_tr))
            preds.append(core._sigmoid(X_ev @ w + b0))
        ref = np.mean(preds, axis=0)
        np.testing.assert_allclose(got[:, 0], ref, atol=1e-8)

    def test_s4_positive_control_still_supported(self):
        pop = ctl.get_control("C4", 1)
        s4 = core.s4_selectability(pop)
        self.assertIn("5-fold CV", s4["policy"])
        self.assertEqual(s4["state"], core.SUPPORTED)


class TestChallengeExecution(unittest.TestCase):
    """Challenges must be re-executable from the frozen spec, spec-faithfully."""

    def test_spec_sha_matches_recorded(self):
        sha_file = chal.SPEC_PATH.with_suffix(".sha256")
        self.assertEqual(chal.spec_sha256(),
                         sha_file.read_text(encoding="utf-8").strip().split()[0])

    def test_ch1_spec_faithful_outcomes(self):
        r = chal.execute_challenges(lambda p: {"A": "SUPPORTED", "B": "x",
                                               "C": "x", "D": "x", "E": "x"})
        # only checks the runner wiring; state expectations checked in controls
        self.assertIn("CH1", r["challenges"])
        self.assertIn("code_sha256", r)

    def test_ch1_analytic_values(self):
        pop = chal.build_ch1()
        s2 = core.s2_decomposition(pop)
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        self.assertAlmostEqual(s2["oracle_accuracy"], 0.9, places=2)
        self.assertAlmostEqual(s2["best_fixed_accuracy"], 0.515, places=3)
        self.assertEqual(s2["state"], core.SUPPORTED)
        self.assertEqual(s4["state"], core.SUPPORTED)
        self.assertEqual(s5["state"], core.SUPPORTED)

    def test_ch2_analytic_values_match_spec_reference(self):
        pop = chal.build_ch2()
        s2 = core.s2_decomposition(pop)
        s4 = core.s4_selectability(pop)
        s5 = core.s5_cost(pop, s4)
        # spec-forced: oracle 1.0, best-fixed 0.79, pi 0.80, dev-fixed 0.70
        self.assertAlmostEqual(s2["oracle_accuracy"], 1.0, places=6)
        self.assertAlmostEqual(s2["best_fixed_accuracy"], 0.79, places=3)
        self.assertEqual(s2["state"], core.SUPPORTED)
        self.assertEqual(s4["state"], core.SUPPORTED)
        self.assertEqual(s5["state"], core.REFUTED)
        self.assertLess(s5["U"], 0)


if __name__ == "__main__":
    unittest.main()
