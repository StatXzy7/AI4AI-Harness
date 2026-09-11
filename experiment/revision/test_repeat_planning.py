"""Behavioral tests for simulation estimands, repeat separation and clone identity."""
import unittest

import numpy as np

from experiment.revision.repeat_planning import (
    SCENARIOS, build_populations, cross_repeat, fitted_policy_score,
    generate_execution, marginal_probabilities, stable_headroom, tied_max_weights,
)


class RepeatPlanningTests(unittest.TestCase):
    def test_probability_headroom_differs_from_single_run_and_mixed_baseline(self):
        p=np.array([[.5,.5],[.5,.5]])
        self.assertEqual(stable_headroom(p),0.)
        self.assertEqual(stable_headroom(np.array([[1.,0.],[0.,1.]])),.5)
        # A clone-only pool is zero; adding a distinct bare can preserve complementarity.
        mixed=np.array([[1.,0.],[0.,1.],[0.,1.]])
        self.assertEqual(stable_headroom(mixed),.5)

    def test_validation_does_not_train_its_own_directional_policy(self):
        train=np.array([[[[[1.,0.],[0.,1.]]]]])
        validation=1-train
        result=fitted_policy_score(train,validation)[0,0]
        np.testing.assert_allclose(result,[-.5,0.,.5])
        changed=fitted_policy_score(train,train)[0,0]
        np.testing.assert_allclose(changed,[.5,1.,.5])
        # Selected members are determined by train; swapping heldout outcomes changes score, not choice.
        np.testing.assert_allclose(tied_max_weights(train.mean(axis=2),2),[[[[1.,0.],[0.,1.]]]])

    def test_two_half_averaging_and_invalid_repeat_count(self):
        data=np.array([[[[[1.,0.],[0.,1.]],[[0.,1.],[1.,0.]]]]])
        truth=np.full(data.shape,.5)
        observed,oracle=cross_repeat(data,truth)
        np.testing.assert_allclose(observed[0,0],[-.5,0.,.5])
        np.testing.assert_allclose(oracle[0,0],[0.,.5,.5])
        with self.assertRaises(ValueError):
            cross_repeat(data[:,:,:1],truth[:,:,:1])

    def test_clone_probabilities_and_code_identity_and_fully_coupled_cache(self):
        rng=np.random.default_rng(7)
        p,codes=build_populations(rng,12,2,SCENARIOS['task_interaction'],.64,.22,n_dev=20)
        np.testing.assert_allclose(p[:,1,0],p[:,1,1])
        np.testing.assert_allclose(p[:,1,1],p[:,1,2])
        np.testing.assert_allclose(p[:,0,0],p[:,2,0])
        np.testing.assert_allclose(p[:,2,1],p[:,2,2])
        x,_=generate_execution(rng,p,codes,4,0.,1.)
        np.testing.assert_array_equal(x[0,0,:,0],x[1,0,:,0])
        for c in range(2):
            for g in range(3):
                for h in range(3):
                    expected=np.broadcast_to(x[c,0,0,codes[c,g,h]],x[c,g,:,h].shape)
                    np.testing.assert_array_equal(x[c,g,:,h],expected)

    def test_marginal_probabilities_and_uniform_ties(self):
        p=np.array([.01,.5,.99])
        np.testing.assert_array_equal(marginal_probabilities(p,0),p)
        marginal=marginal_probabilities(p,1.2)
        self.assertAlmostEqual(marginal[1],.5)
        self.assertAlmostEqual(marginal[0]+marginal[2],1.)
        np.testing.assert_array_equal(tied_max_weights(np.array([[1.,1.,0.]]),1),[[.5,.5,0.]])


if __name__=='__main__':
    unittest.main()
