"""Behavioral checks for joint W1 perturbation, never CI calibration."""
import random
import unittest

import numpy as np

from experiment.revision.selection import METHODS, evaluate, selections
from experiment.revision.replay import ROOT
from experiment.revision.selection_weights import (
    empty_side_probability, positive_weights, weighted_choices, weighted_evaluate,
)


class SelectionWeightTests(unittest.TestCase):
    def test_archived_mixed_objective_float_tie_regression(self):
        # Minimal outcome-matrix extraction, no questions or provider data.
        with np.load(ROOT/'artifacts/revision_20260910/selection_weight_tie_fixture.npz') as fixture:
            pool, dev = fixture['pool'], fixture['dev']
        w = np.zeros((3, pool.shape[1]))
        w[:, dev] = 1
        reference = selections(pool, 8, dev, random.Random(0), 1)['acc+0.25div'][0]
        self.assertEqual(reference, [14, 7, 12, 13, 6, 24, 9, 4])
        np.testing.assert_array_equal(weighted_choices(pool, w, 8, 'acc+0.25div'),
                                      np.broadcast_to(reference, (3, 8)))

    def test_empty_side_exact_small_case(self):
        result = empty_side_probability([{'dev_databases': ['a'], 'heldout_databases': ['b', 'c']}])
        self.assertEqual(result['bad_sequences'], 9)
        self.assertEqual(result['all_sequences'], 27)

    def test_weights_are_positive_reproducible_and_group_normalized(self):
        dbs = ['a', 'a', 'b', 'b', 'b']
        first = positive_weights(dbs, 11, 7)
        np.testing.assert_array_equal(first, positive_weights(dbs, 11, 7))
        self.assertTrue((first > 0).all())
        # Same seed and generation order expose the exact database multipliers.
        rng = np.random.default_rng(7)
        for idx in ([0, 1], [2, 3, 4]):
            group = rng.exponential(size=(11, 1))
            rng.exponential(size=(11, len(idx)))
            np.testing.assert_allclose(first[:, idx].sum(axis=1), group[:, 0]*len(idx))

    def test_choices_ignore_heldout_and_agree_with_scalar_weighted_objective(self):
        rng = np.random.default_rng(12)
        pool = rng.integers(0, 2, (10, 9)).astype(float)
        weights = rng.exponential(size=(6, 9))
        weights[:, 5:] = 0
        other = pool.copy()
        other[:, 5:] = 1-other[:, 5:]
        for method in [METHODS[0], *METHODS[2:]]:
            got = weighted_choices(pool, weights, 4, method)
            np.testing.assert_array_equal(got, weighted_choices(other, weights, 4, method))
            for row, w in enumerate(weights):
                acc = np.average(pool, weights=w, axis=1)
                if method == 'top-acc':
                    expected = sorted(range(len(pool)), key=lambda i: (-acc[i], i))[:4]
                else:
                    expected = [max(range(len(pool)), key=lambda i: (acc[i], i))]
                    lam = None if method == 'div-only' else float(method[4:-3])
                    while len(expected) < 4:
                        def score(i):
                            ids = expected+[i]
                            oracle = np.average(pool[ids].max(axis=0), weights=w)
                            return (oracle if lam is None else acc[ids].mean()+lam*oracle, i)
                        expected.append(max((i for i in range(len(pool)) if i not in expected), key=score))
                np.testing.assert_array_equal(got[row], expected)

    def test_uniform_choices_and_metrics_match_canonical(self):
        rng = np.random.default_rng(31)
        pool = rng.integers(0, 2, (12, 12)).astype(float)
        bare = rng.integers(0, 2, 12).astype(float)
        dev, test = np.arange(6), np.arange(6, 12)
        dw = np.array([[1.]*6+[0.]*6])
        tw = 1-dw
        for k in (4, 8):
            ref = selections(pool, k, dev, random.Random(5), 7)
            for method in METHODS:
                if method == 'random':
                    choices = np.array([ref[method]])
                else:
                    choices = weighted_choices(pool, dw, k, method)[:, None, :]
                    np.testing.assert_array_equal(choices[0], ref[method])
                for baseline in (None, bare):
                    np.testing.assert_allclose(weighted_evaluate(pool, choices, dw, tw, baseline)[0],
                                               evaluate(pool, ref[method], dev, test, baseline))

    def test_reselection_and_bare_dev_ties(self):
        pool = np.array([[1., 0, 1, 0], [0., 1, 0, 1]])
        weights = np.array([[3., 1, 0, 0], [1., 3, 0, 0]])
        choices = weighted_choices(pool, weights, 1, 'top-acc')
        np.testing.assert_array_equal(choices, [[0], [1]])
        with_bare = weighted_evaluate(pool, choices[:, None, :], weights,
                                     np.array([[0., 0, 1, 3], [0., 0, 1, 3]]), np.ones(4))
        np.testing.assert_allclose(with_bare, [[1, 1, 0, 1], [1, 1, 0, 1]])
        with self.assertRaises(ValueError):
            weighted_choices(pool, np.zeros((1, 4)), 1, 'top-acc')
        with self.assertRaises(ValueError):
            weighted_evaluate(pool, np.array([[[0]]]), np.ones((1, 4)), np.zeros((1, 4)))

    def test_shared_random_coverage_matches_direct_weighted_evaluation(self):
        rng = np.random.default_rng(6)
        pool = rng.integers(0, 2, (9, 17)).astype(float)
        bare = rng.integers(0, 2, 17).astype(float)
        weights = rng.exponential(size=(5, 17))
        dw, tw = weights.copy(), weights.copy()
        dw[:, 8:] = 0
        tw[:, :8] = 0
        subsets = np.array([[1, 4, 7], [0, 3, 2], [6, 8, 5]])
        choices = np.broadcast_to(subsets, (5, 3, 3))
        for baseline in (None, bare):
            got = weighted_evaluate(pool, choices, dw, tw, baseline)
            for row in range(5):
                results = []
                for subset in subsets:
                    values = pool[np.sort(subset)]
                    if baseline is not None:
                        values = np.vstack([baseline, values])
                    da = np.average(values, weights=dw[row], axis=1)
                    ta = np.average(values, weights=tw[row], axis=1)
                    oracle = np.average(values.max(axis=0), weights=tw[row])
                    results.append([oracle, ta.max(), oracle-ta.max(), ta[da.argmax()]])
                np.testing.assert_allclose(got[row], np.mean(results, axis=0), atol=1e-12)


if __name__ == '__main__':
    unittest.main()
