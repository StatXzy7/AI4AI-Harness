"""Unit tests for the calibrated C-comp v3 statistics (post 2026-09-19 review).

The four invariants the external review demanded, as executable tests:

  T1  Pure sampling noise (all true q identical) must NEVER yield a
      SUPPORTED complementarity state -- the v2 plug-in did (8.83 pp CI
      excluding zero at q=0.9, M=9, T=400, R=3).
  T2  Global dominance (bare 0.5 / other members 0.9 everywhere; H=0) must
      never yield SUPPORTED, because a member better on every task gives
      no task-conditional complementarity (the old vs-bare A8.6 did
      reject here).
  T3  Genuine crossover interaction must yield SUPPORTED when R is large
      enough for a noisy discovery probe to recover the mapping (positive
      control / power sanity).
  T4  The legacy plug-in H_hat is retained but flagged descriptive-only;
      it never determines the v3 state.
"""
from __future__ import annotations

import unittest

import numpy as np

from experiment.diagnostics import calibration_sim as sim
from experiment.diagnostics.ccomp_v3 import (
    _batch_crossfit_gain, _batch_permuted, _complete_cols, ccomp_v3,
    crossfit_gain)
from experiment.diagnostics.core import INSUFFICIENT, SUPPORTED

N_PERM = 400
N_BOOT = 400
TASK_IDS = [f"t{i}" for i in range(400)]


def _equal_tensor(seed, q=0.9, M=9, T=400, R=3):
    rng = np.random.default_rng(seed)
    return (rng.random((R, M, T)) < q).astype(float)


class TestReviewerCounterexamples(unittest.TestCase):
    def test_w1_equal_ability_no_support(self):
        """Reviewer W1, exact reported setting: q=0.9, M=9, T=400, R=3.
        The legacy plug-in prints 8.83 pp SUPPORTED; v3 must not."""
        Y = _equal_tensor(20260915)
        # descriptive plug-in reproduces the reviewer's false positive ...
        r = ccomp_v3(Y, Y, TASK_IDS, n_perm=N_PERM, n_boot=N_BOOT)
        self.assertIsNotNone(r["H_plugin_descriptive"])
        self.assertGreater(r["H_plugin_descriptive"], 0.07)
        # ... but the calibrated decision abstains
        from experiment.diagnostics.core import INSUFFICIENT
        self.assertEqual(r["state"], INSUFFICIENT)
        self.assertIn("upward biased", r["descriptive_warning"])

    def test_w1_fpr_over_repeated_null_draws(self):
        """Monte-Carlo size at the equal-ability boundary (reviewer Q1):
        SUPPORTED rate must be at the nominal floor over many draws."""
        sup = 0
        n = 20
        for b in range(n):
            rng = np.random.default_rng(4242 + b)
            Y = (rng.random((3, 9, 400)) < 0.9).astype(float)
            C = (rng.random((3, 9, 400)) < 0.9).astype(float)
            r = ccomp_v3(Y, C, TASK_IDS, n_perm=200, n_boot=200)
            sup += int(r["state"] == "SUPPORTED")
        self.assertLessEqual(sup / n, 0.10)

    def test_w2_global_dominance_no_support(self):
        """Reviewer W2: bare q=0.5, all 8 others q=0.9 on every task.
        A vs-bare statistic shows ~20 pp; H_stable = 0; v3 must abstain."""
        rng = np.random.default_rng(7)
        Q = np.full((9, 400), 0.9)
        Q[0] = 0.5
        Y = np.stack([(rng.random((9, 400)) < Q).astype(float)
                      for _ in range(3)])
        C = np.stack([(rng.random((9, 400)) < 0.5).astype(float)
                      for _ in range(3)])   # same-code bare clone
        r = ccomp_v3(Y, C, TASK_IDS, n_perm=N_PERM, n_boot=N_BOOT)
        from experiment.diagnostics.core import INSUFFICIENT
        self.assertEqual(r["state"], INSUFFICIENT)
        self.assertLess(r["G"], 0)          # frozen selector loses to fixed

    def test_w2_dominance_fpr_over_draws(self):
        sup = 0
        n = 20
        for b in range(n):
            rng = np.random.default_rng(5050 + b)
            Q = np.full((9, 400), 0.9)
            Q[0] = 0.5
            Y = np.stack([(rng.random((9, 400)) < Q).astype(float)
                          for _ in range(3)])
            C = np.stack([(rng.random((9, 400)) < 0.5).astype(float)
                          for _ in range(3)])
            r = ccomp_v3(Y, C, TASK_IDS, n_perm=200, n_boot=200)
            sup += int(r["state"] == "SUPPORTED")
        self.assertEqual(sup, 0)

    def test_w3_crossover_positive_control(self):
        """Strong two-stratum specialization with enough repeats must be
        recognized (power sanity check)."""
        d = sim.dgp_crossover(seed=5, M=9, T=400, R=20, gamma=1.5,
                              k_types=2, base_q=0.8)
        C = sim.draw_clone_arm(d.Q, d.task_types, 20, 6)
        r = ccomp_v3(d.Y, C, TASK_IDS, n_perm=300, n_boot=400)
        from experiment.diagnostics.core import SUPPORTED
        self.assertEqual(r["state"], SUPPORTED)
        self.assertGreater(r["paired_difference"]["D_real_minus_clone"], 0.03)

    def test_without_clone_arm_never_supports(self):
        """Real-arm G alone has only the descriptive interval; a size
        claim needs the same-code reference."""
        d = sim.dgp_crossover(seed=5, M=9, T=400, R=20, gamma=1.5,
                              k_types=2, base_q=0.8)
        r = ccomp_v3(d.Y, None, TASK_IDS, n_perm=200, n_boot=200)
        from experiment.diagnostics.core import INSUFFICIENT
        self.assertEqual(r["state"], INSUFFICIENT)
        self.assertIsNone(r["p_D_clone_randomization"])
        self.assertIn("clone", r["reason"])


class TestGainMechanics(unittest.TestCase):
    def test_g_zero_under_exact_dominance(self):
        """Deterministic dominance: dom always right -> the frozen pick is
        the dominant member, so G = 0 exactly (no noise)."""
        T = 200
        Y = np.zeros((3, 3, T))
        Y[:, 2, :] = 1.0
        g, _, folds = crossfit_gain(Y)
        self.assertAlmostEqual(g, 0.0, places=10)
        self.assertTrue(all(f["best_fixed"] == 2 for f in folds))

    def test_g_positive_under_deterministic_crossover(self):
        """Deterministic crossover with enough discovery repeats: the frozen
        per-task mapping recovers the right member and gains over fixed."""
        T = 300
        Y = np.zeros((5, 2, T))
        Y[:, 0, :T // 2] = 1.0
        Y[:, 1, T // 2:] = 1.0
        g, _, _ = crossfit_gain(Y)
        self.assertGreater(g, 0.4)

    def test_permutation_breaks_identity_transfer(self):
        """Independent per-repeat permutations must destroy the observed
        crossover mapping: mean permuted G near 0, not above observed."""
        d = sim.dgp_crossover(seed=9, M=9, T=400, R=20, gamma=1.5,
                              k_types=2, base_q=0.8)
        cols = _complete_cols(d.Y)
        g0, _, _ = crossfit_gain(d.Y, cols)
        rng = np.random.default_rng(0)
        null = _batch_crossfit_gain(
            _batch_permuted(d.Y, cols, 200, rng))
        self.assertGreater(g0, np.quantile(null, 0.99))
        self.assertLess(abs(null.mean()), 0.01)

    def test_batch_matches_single_path(self):
        rng = np.random.default_rng(11)
        Y = (rng.random((3, 5, 40)) < 0.8).astype(float)
        cols = _complete_cols(Y)
        # deterministic (no-jitter) single path matches the jitter=False batch
        single, _, _ = crossfit_gain(Y)
        batch = _batch_crossfit_gain(Y[None], jitter=False)[0]
        self.assertAlmostEqual(single, float(batch), places=10)

    def test_missing_cells_gate(self):
        """More than the coverage threshold excluded -> INSUFFICIENT with
        G still reported on complete tasks; no state SUPPORTED."""
        rng = np.random.default_rng(3)
        Y = (rng.random((3, 9, 400)) < 0.9).astype(float)
        C = (rng.random((3, 9, 400)) < 0.9).astype(float)
        Y[:, :, :80] = np.nan         # 20% incomplete
        r = ccomp_v3(Y, C, TASK_IDS, n_perm=200, n_boot=200)
        from experiment.diagnostics.core import INSUFFICIENT
        self.assertEqual(r["state"], INSUFFICIENT)
        self.assertFalse(r["coverage_ok"])
        self.assertEqual(r["n_complete_tasks"], 320)

    def test_extremal_bounds_bracket_observed(self):
        rng = np.random.default_rng(4)
        Y = (rng.random((3, 4, 60)) < 0.7).astype(float)
        Y[:, 0, 0] = np.nan
        from experiment.diagnostics.ccomp_v3 import extremal_bounds
        lo, hi = extremal_bounds(Y)
        self.assertLessEqual(lo, hi)
        self.assertTrue(-1.0 <= lo <= 1.0 and -1.0 <= hi <= 1.0)

    def test_clone_coverage_gate_blocks_degenerate_intersection(self):
        """A clone arm with 1/40 complete tasks must never drive SUPPORT
        even if that single paired difference is large (reviewer edge
        case): clone-arm and paired-intersection coverage gates."""
        rng = np.random.default_rng(0)
        Y = np.zeros((3, 2, 40))
        Y[:, 0, :20] = 1
        Y[:, 1, 20:] = 1
        C = np.full_like(Y, np.nan)
        C[:, :, 0] = 1
        r = ccomp_v3(Y, C, member_ids=["b", "m"],
                     task_ids=[f"t{i}" for i in range(40)],
                     n_perm=400, n_boot=400, n_tie=1)
        self.assertEqual(r["state"], INSUFFICIENT)
        self.assertIn("clone-arm coverage", r["reason"])

    def test_extremal_bounds_bracket_all_fill_gains(self):
        """The reported fill-extremes must contain G under both all-0 and
        all-1 filling of the missing observations (the tight fill
        directions), re-running the full cross-fit each time."""
        from experiment.diagnostics.ccomp_v3 import extremal_bounds
        rng = np.random.default_rng(4)
        Y = (rng.random((3, 9, 200)) < 0.9).astype(float)
        for i in [10, 50, 100, 150]:
            Y[:, i % 9, i] = np.nan
        lo, hi = extremal_bounds(Y)
        for fill in (0.0, 1.0):
            Z = Y.copy()
            Z[np.isnan(Z)] = fill
            from experiment.diagnostics.ccomp_v3 import crossfit_gain
            g, _, _ = crossfit_gain(Z, tie_rng=np.random.default_rng(20260915))
            self.assertLessEqual(lo - 1e-9, g)
            self.assertLessEqual(g, hi + 1e-9)

    def test_output_invariant_to_member_order(self):
        """Permuting member order in BOTH arms consistently must leave the
        state unchanged and the (10-draw tie-averaged) estimate the same up
        to Monte Carlo tolerance: label symmetry holds in expectation, so a
        single tie realization is not required to match exactly (Codex
        non-blocking ask)."""
        rng = np.random.default_rng(20260920)
        Q = np.full((9, 200), 0.9)
        for t in range(200):
            Q[t % 3, t] = 0.97
        Y = np.stack([(rng.random((9, 200)) < Q).astype(float)
                      for _ in range(3)])
        C = (rng.random((3, 9, 200)) < 0.9).astype(float)
        tids = [f"t{i}" for i in range(200)]
        G1, G2, D1, D2, st1, st2 = [], [], [], [], [], []
        for seed0 in (11, 23, 37, 51, 68):
            r1 = ccomp_v3(Y, C, task_ids=tids, n_perm=400, n_boot=400,
                          n_tie=10, seed=seed0)
            perm = [3, 0, 8, 1, 7, 2, 6, 4, 5]
            r2 = ccomp_v3(Y[:, perm, :], C[:, perm, :], task_ids=tids,
                          n_perm=400, n_boot=400, n_tie=10, seed=seed0)
            G1.append(r1["G"]); G2.append(r2["G"])
            D1.append(r1["paired_difference"]["D_real_minus_clone"])
            D2.append(r2["paired_difference"]["D_real_minus_clone"])
            st1.append(r1["state"]); st2.append(r2["state"])
        self.assertEqual(set(st1), set(st2))
        self.assertLess(abs(np.mean(G1) - np.mean(G2)), 0.005)
        self.assertLess(abs(np.mean(D1) - np.mean(D2)), 0.008)


if __name__ == "__main__":
    unittest.main()
