"""Tests for inferential identification mistakes, not only array arithmetic."""
import unittest

import numpy as np

from experiment.revision.stable_witness import (
    contrast_bounds, counterexamples, freeze_choices, hoeffding_bands,
    policy_witness, stable_bounds, validation_differences,
)
from experiment.revision.repeat_planning import stable_headroom


class StableWitnessTests(unittest.TestCase):
    def test_selected_fixed_positive_gain_does_not_imply_stable_headroom(self):
        trap = counterexamples()['discovery_fixed_trap']
        self.assertAlmostEqual(trap['apparent_advantage'], .225)
        self.assertAlmostEqual(trap['stable_headroom'], 0)
        self.assertAlmostEqual(trap['all_fixed_witness'], -.375)

    def test_difference_of_witnesses_can_have_wrong_sign(self):
        trap = counterexamples()['difference_of_lower_bounds_trap']
        self.assertAlmostEqual(trap['invalid_witness_difference'], .4)
        self.assertAlmostEqual(trap['true_stable_difference'], -.4)

    def test_policy_fixed_before_validation_and_all_comparators_retained(self):
        train = np.array([[1.,0.],[0.,1.]])[None,None,None]
        policy, _ = freeze_choices(train)
        validation = 1-train
        np.testing.assert_allclose(validation_differences(policy,validation),[[[[-.5,-.5]]]])
        np.testing.assert_allclose(validation_differences(policy,train),[[[[.5,.5]]]])
        np.testing.assert_array_equal(policy[0,0],np.eye(2))

    def test_bands_contain_true_headroom_and_contrast_for_valid_probability_bands(self):
        rng = np.random.default_rng(55)
        for _ in range(100):
            p = rng.random((4,3,3,20))
            lo = np.maximum(0.,p-rng.random(p.shape)*.2)
            hi = np.minimum(1.,p+rng.random(p.shape)*.2)
            bounds = stable_bounds(lo,hi)
            truth = stable_headroom(p)
            self.assertTrue((bounds[...,0] <= truth+1e-12).all())
            self.assertTrue((truth <= bounds[...,1]+1e-12).all())
            contrast = contrast_bounds(bounds)
            delta = (truth[:,0]-truth[:,2]).mean()
            self.assertLessEqual(contrast[0],delta+1e-12)
            self.assertGreaterEqual(contrast[1],delta-1e-12)
            policy = rng.random(p.shape)
            policy /= policy.sum(axis=-2,keepdims=True)
            self.assertTrue((policy_witness(p,policy) <= truth+1e-12).all())

    def test_exact_bands_and_single_member(self):
        p = np.array([[1.,0.],[0.,1.]])
        np.testing.assert_allclose(stable_bounds(p,p),[.5,.5])
        np.testing.assert_array_equal(stable_bounds(np.zeros((1,4)),np.ones((1,4))),[0.,0.])
        np.testing.assert_allclose(stable_bounds(np.zeros((3,4)),np.ones((3,4))),[0.,2/3])

    def test_validation_band_count_and_invalid_inputs(self):
        y = np.zeros((4,3,8,3,180))
        lo,hi,radius = hoeffding_bands(y)
        self.assertAlmostEqual(radius,np.sqrt(np.log(2*6480/.05)/16))
        self.assertEqual(lo.shape,(4,3,3,180))
        self.assertTrue((hi >= lo).all())
        with self.assertRaises(ValueError):
            hoeffding_bands(y+.2)
        with self.assertRaises(ValueError):
            stable_bounds(np.ones((3,4)),np.zeros((3,4)))


if __name__ == '__main__':
    unittest.main()
