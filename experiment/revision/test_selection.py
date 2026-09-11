"""Selection must use dev only; shared bare and score decomposition are explicit."""
import random
import unittest

import numpy as np

from experiment.revision.replay import TARGET
from experiment.revision.selection import analyze, evaluate, selections


class SelectionTests(unittest.TestCase):
    def test_selection_is_unaffected_by_heldout_labels(self):
        pool = np.array([[1, 1, 0, 0], [0, 0, 1, 1], [1, 0, 0, 1]], dtype=float)
        other = pool.copy()
        other[:, 2:] = 1-other[:, 2:]
        self.assertEqual(selections(pool, 2, [0, 1], random.Random(1), 5),
                         selections(other, 2, [0, 1], random.Random(1), 5))
        with self.assertRaises(ValueError):
            selections(pool, 4, [0, 1], random.Random(1), 5)

    def test_dev_fixed_is_not_test_best_and_bare_is_retained(self):
        pool = np.array([[1,1,0,0], [0,0,1,0]], dtype=float)
        bare = np.array([0,0,0,1], dtype=float)
        candidate = evaluate(pool, [[0,1]], [0,1], [2,3])
        augmented = evaluate(pool, [[0,1]], [0,1], [2,3], bare)
        np.testing.assert_allclose(candidate, [.5,.5,0,0])
        np.testing.assert_allclose(augmented, [1,.5,.5,0])
        tied = np.array([[1,0,1,1], [1,0,0,0]], dtype=float)
        np.testing.assert_array_equal(evaluate(tied, [[0,1]], [0,1], [2,3]),
                                      evaluate(tied, [[1,0]], [0,1], [2,3]))

    def test_pipeline_replays_membership_and_all_methods_without_ci(self):
        tasks = ['db0#0','db1#0','db2#0','db3#0']
        names = [f'p2_A_demo_s0_g{i}' for i in range(8)]
        rows = {(TARGET,h,t,0,False): dict(final_sql='select 1', official_correct=int(i % 2 == j % 2),
                n_llm_calls=1,n_execs=1) for i,h in enumerate(names) for j,t in enumerate(tasks)}
        rows.update({(TARGET,'bare',t,0,False): dict(official_correct=1) for t in tasks})
        result = analyze({'AD': rows}, {('builder',0,'A'): names}, tasks, n_splits=2, n_random=5)
        self.assertEqual(len(result['summary']),14)
        for row in result['summary'].values():
            for scope in ('candidate_only','bare_inclusive'):
                o,b,h,f = row[scope]
                self.assertAlmostEqual(o-b,h)
                self.assertLessEqual(f,b)
            self.assertEqual(row['bare_inclusive'][:3],[1.,1.,0.])


if __name__ == '__main__':
    unittest.main()
