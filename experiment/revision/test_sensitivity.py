"""Behavioral invariants for exact K matching and separately identified reruns."""
import itertools
import unittest

import numpy as np

from experiment.revision.cost_audit import summarize
from experiment.revision.verify import merge_expectations

from experiment.revision.sensitivity import (
    exact_subsets, kmatched, repeat_analysis, repeat_rows, shared_bootstrap,
    subset_metrics, weighted_metrics,
)


class SensitivityTests(unittest.TestCase):
    def test_shared_dependency_cannot_silently_replace_primary_provenance(self):
        primary = {"replay.py": "old"}
        sensitivity = {"replay.py": "new", "sensitivity.py": "current"}
        with self.assertRaisesRegex(SystemExit, "CONFLICTING provenance: replay.py"):
            merge_expectations(primary, sensitivity)
        self.assertEqual(merge_expectations(primary, primary), primary)

    def test_cost_keeps_zero_candidate_cells_and_distinguishes_denominators(self):
        tasks = ["db#0", "db#1"]
        mem = {("builder", 0, "A"): [], ("builder", 1, "A"): ["h0", "h1"]}
        rows = {("GLM-5.3-Flash", h, t, 0, False): {
            "n_llm_calls": calls, "n_execs": 0, "latency_ms": 5., "official_correct": 0}
            for h, values in (("h0", [2, 4]), ("h1", [1, 1])) for t, calls in zip(tasks, values)}
        result = summarize(rows, mem, "A", tasks)
        self.assertEqual(result["n_cells"], 2)
        self.assertIsNone(result["per_cell"][0]["mean_per_candidate_n_llm_calls"])
        self.assertEqual(result["per_cell"][0]["logical_solver_calls_per_task_population"], 0.)
        self.assertEqual(result["logical_solver_calls_per_task_population_cell_mean"], 2.)
        self.assertEqual(result["total_logged_solver_calls"], 8)
        self.assertEqual(result["row_weighted_multicall_fraction"], .5)
        self.assertEqual(result["rows_with_token_usage_field"], 0)
        rows["GLM-5.3-Flash", "h0", "db#0", 0, False]["latency_ms"] = float("nan")
        with self.assertRaisesRegex(ValueError, "invalid recorded cost"):
            summarize(rows, mem, "A", tasks)

    def test_kmatched_pipeline_with_asymmetric_counts_and_zero_candidates(self):
        tasks = ["db#0", "db#1"]
        vectors = {"bare": [1, 0], "b0": [0, 1], "b1": [0, 1],
                   "c0": [1, 0], "d0": [0, 1], "d1": [1, 0]}
        rows = {("GLM-5.3-Flash", h, t, 0, False): {"official_correct": v}
                for h, values in vectors.items() for t, v in zip(tasks, values)}
        mem = {("builder", 0, a): hs for a, hs in
               (("A", []), ("B", ["b0", "b1"]), ("C", ["c0"]), ("D", ["d0", "d1"]))}
        result = kmatched({"AD": rows, "BC": rows}, mem, tasks, 100, 42)
        self.assertEqual(result["n_cells"], 1)
        self.assertEqual(result["per_cell"][0]["k_candidate_AB"], 0)
        self.assertEqual(result["per_cell"][0]["k_candidate_CD"], 1)
        np.testing.assert_allclose(np.array(result["point"])[:, 2], [0., .25, .125])

    def test_repeat_pipeline_retains_singleton_and_never_substitutes_bare(self):
        tasks = ["db#0", "db#1"]
        mem = {("builder", 0, "A"): ["a0"], ("builder", 0, "D"): ["d0", "d1"],
               ("builder", 1, "A"): ["a2", "a3"], ("builder", 1, "D"): ["d2", "d3"]}
        names = [h for hs in mem.values() for h in hs]
        def records(cacheoff, group):
            rows = {}
            for h in names:
                if group == "two" and not h.startswith("d"):
                    continue
                values = [0, 1] if h == "d0" and group != "one" else [1, 0]
                for t, v in zip(tasks, values):
                    rows["GLM-5.3-Flash", h, t, 0, cacheoff] = {
                        "official_correct": v, "code_hash": h}
            return rows
        result = repeat_analysis({"AD": records(False, "original")},
                                 {"r2_pass1": records(True, "one"),
                                  "r2_pass2_D": records(True, "two")}, mem, tasks, 100, 42)
        self.assertEqual(result["n_cells"], 2)
        self.assertEqual(result["legacy_eligible_scope_diagnostic"]["n_cells"], 1)
        np.testing.assert_allclose(result["point"][:3], [.25, 0., -.25])
        self.assertEqual(result["micro_verdict_flips"]["flips"], 2)
        self.assertEqual(result["micro_D_repeat_flips"]["flips"], 2)
        self.assertIn("EXCLUDES bare", result["baseline"])

    def test_subsets_always_keep_bare_and_match_literal_enumeration(self):
        pool = np.array([[1., 0., 0., 0.], [0., 1., 0., 0.],
                         [0., 0., 1., 0.], [0., 0., 0., 1.]])
        weights = np.array([.1, .2, .3, .4])
        for k in range(4):
            prepared = exact_subsets(pool, k)
            self.assertTrue(np.all(prepared[1][:, 0] == 0))
            self.assertTrue(np.all(np.sum(prepared[1] == 0, axis=1) == 1))
            expected = np.mean([weighted_metrics(pool[[0, *c]], weights)
                                for c in itertools.combinations(range(1, 4), k)], axis=0)
            np.testing.assert_allclose(subset_metrics(prepared, weights), expected, atol=1e-15)

    def test_empty_candidate_comparison_stays_bare_only(self):
        pool = np.array([[1., 0.], [0., 1.]])
        result = subset_metrics(exact_subsets(pool, 0), np.array([.5, .5]))
        np.testing.assert_array_equal(result, [.5, .5, 0.])

    def test_best_fixed_reselected_on_each_task_draw(self):
        pool = np.array([[1., 0.], [0., 1.]])
        prepared = exact_subsets(pool, 1)
        self.assertEqual(subset_metrics(prepared, np.array([.5, .5]))[2], .5)
        self.assertEqual(subset_metrics(prepared, np.array([1., 0.]))[2], 0.)

    def test_shared_weight_draw_and_fixed_builder_sampling(self):
        keys = [(b, s) for b in ("a", "b") for s in range(3)]
        def paired_null(weights):
            self.assertAlmostEqual(float(weights.sum()), 1.)
            # Identical arms cancel on every common draw; different task/cell
            # samplings would generally violate this invariant.
            pool = np.array([[1., 0., 1.], [0., 1., 0.]])
            h = weighted_metrics(pool, weights)[2]
            return np.array([[h - h, float(b == "b")] for b, _ in keys])
        point, ci = shared_bootstrap(keys, np.array(["d1", "d1", "d2"]), paired_null, 100, 42)
        np.testing.assert_array_equal(point[:, 0], 0.)
        np.testing.assert_array_equal(ci[:, 0], 0.)
        np.testing.assert_array_equal(ci[:, 1], .5)

    def test_repeat_group_identity_and_hash_coverage_checks(self):
        key = ("GLM-5.3-Flash", "h", "db#0", 0, True)
        original = {(*key[:4], False): {"code_hash": "same"}}
        first = {key: {"official_correct": 1, "code_hash": "same"}}
        second = {key: {"official_correct": 0, "code_hash": "same"}}
        groups = {"one": first, "two": second}
        self.assertEqual(repeat_rows(original, groups, "one", ["h"], ["db#0"])["h"][0], 1.)
        self.assertEqual(repeat_rows(original, groups, "two", ["h"], ["db#0"])["h"][0], 0.)
        second[key]["code_hash"] = "changed"
        with self.assertRaisesRegex(ValueError, "source changed"):
            repeat_rows(original, groups, "two", ["h"], ["db#0"])
        with self.assertRaisesRegex(ValueError, "coverage"):
            repeat_rows(original, groups, "one", ["h"], ["db#0", "db#1"])


if __name__ == "__main__":
    unittest.main()
