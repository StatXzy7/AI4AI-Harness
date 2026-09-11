"""Checks that candidate inference reselects and keeps repeat identities separate."""
import unittest

import numpy as np

from experiment.revision.repeat_inference import (
    SCENARIOS, bootstrap_scores, interval_calibration, resampling_weights, simulated_panel,
)
from experiment.revision.repeat_planning import cross_repeat


class RepeatInferenceTests(unittest.TestCase):
    def test_identity_draw_matches_original_cross_repeat(self):
        rng = np.random.default_rng(77)
        y = rng.integers(0, 2, (4, 3, 4, 3, 12)).astype(float)
        task = np.full((1, 12), 1/12)
        repeat = np.array([[[.5, .5, 0, 0], [0, 0, .5, .5]]])
        observed, _ = cross_repeat(y, y)
        self.assertAlmostEqual(bootstrap_scores(y, task, repeat)[0],
                               np.mean(observed[:, 0, 0]-observed[:, 2, 0]))

    def test_bootstrap_matches_explicit_reselected_duplicate_records(self):
        rng = np.random.default_rng(89)
        y = rng.integers(0, 2, (4, 3, 4, 3, 12)).astype(float)
        task, repeat = resampling_weights(rng, np.repeat([0, 1, 2], 4), 4, 7)
        actual = bootstrap_scores(y, task, repeat)
        for b in range(7):
            tasks = np.repeat(np.arange(12), np.rint(task[b]*12).astype(int))
            repeats = np.concatenate([np.repeat(np.arange(4), np.rint(repeat[b,s]*2).astype(int)) for s in range(2)])
            panel = y[:, :, repeats][:, :, :, :, tasks]
            observed, _ = cross_repeat(panel, panel)
            self.assertAlmostEqual(actual[b], np.mean(observed[:, 0, 0]-observed[:, 2, 0]))

    def test_repeat_support_disjoint_and_database_sampling_differs_from_iid(self):
        ids = np.repeat(np.arange(9), 20)
        task, repeat = resampling_weights(np.random.default_rng(7), ids, 8, 100)
        np.testing.assert_allclose(task.sum(axis=1), 1)
        np.testing.assert_allclose(repeat.sum(axis=2), 1)
        self.assertFalse(repeat[:, 0, 4:].any())
        self.assertFalse(repeat[:, 1, :4].any())
        db_mass = task.reshape(100, 9, 20).sum(axis=2)*9
        np.testing.assert_allclose(db_mass, np.rint(db_mass))
        with self.assertRaises(ValueError):
            resampling_weights(np.random.default_rng(1), ids, 3, 10)

    def test_null_fresh_target_zero_even_with_database_shocks_and_cache(self):
        for scenario in ['database_null', 'cache_null']:
            y, ids, observed, target = simulated_panel(np.random.default_rng(3), 9, 20, 4,
                                                       SCENARIOS[scenario], .22, [0,1,2,1])
            self.assertEqual(y.shape, (4,3,4,3,180))
            self.assertEqual(len(np.unique(ids)), 9)
            self.assertAlmostEqual(target, 0)
            self.assertTrue(np.isfinite(observed))

    def test_reference_uncertainty_bounds_coverage(self):
        summary = interval_calibration(np.array([0., .1, .2]), np.array([[-.1,.1],[0,.1],[.2,.3]]), .05, .02)
        self.assertLessEqual(summary['coverage_reference_band_lower'], summary['coverage'])
        self.assertGreaterEqual(summary['coverage_reference_band_upper'], summary['coverage'])
        self.assertAlmostEqual(summary['mean_width'], .4/3)


if __name__ == '__main__':
    unittest.main()
