"""Scientific invariants for the post-review replay (no API or benchmark needed)."""
import unittest
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

from experiment.revision.replay import (
    ROOT, bootstrap, holm, load_sources, make_pools, metrics, sample_cells, sample_tasks, sign_p,
)


class ReplayTests(unittest.TestCase):
    def test_canonical_duplicates_provenance_and_manifest_tampering(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / "rows.jsonl"
            r = {"target": "target", "harness_id": "bare", "task_id": "db#0",
                 "repeat": 0, "no_cache": False, "code_hash": "hash",
                 "official_correct": 1, "legacy_correct": 1}
            other = {**r, "official_correct": 0}
            repeat = {**other, "repeat": 1}
            cacheoff = {**other, "no_cache": True}
            path.write_text("\n".join(json.dumps(x) for x in (r, other, repeat, cacheoff)), encoding="utf-8")
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"files": [{"file": path.name,
                "bytes": path.stat().st_size,
                "sha256_16": hashlib.sha256(path.read_bytes()).hexdigest()[:16]}]}), encoding="utf-8")
            groups, _, audit = load_sources({"group": manifest})
            self.assertEqual(len(groups["group"]), 3)
            kept = groups["group"]["target", "bare", "db#0", 0, False]
            self.assertEqual(kept["official_correct"], 1)
            self.assertEqual(kept["source_line"], 1)
            self.assertEqual(audit["group"]["verdict_conflicts"], 1)
            path.write_text("modified", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frozen input mismatch"):
                load_sources({"group": manifest})

    def test_zero_candidates_and_one_candidate(self):
        bare = np.array([[1., 0., 0., 1.]])
        self.assertEqual(metrics(bare)["headroom"], 0)
        self.assertEqual(metrics(bare)["K_candidate"], 0)
        self.assertEqual(metrics(bare)["K_total"], 1)
        self.assertEqual(metrics(np.vstack([bare, 1 - bare]))["headroom"], .5)

    def test_nonmonotonic_headroom(self):
        pool = np.array([[1., 0.], [0., 1.]])
        self.assertEqual(metrics(pool)["headroom"], .5)
        self.assertEqual(metrics(np.vstack([pool, [1., 1.]]))["headroom"], 0)

    def test_decomposition(self):
        for pool in (np.array([[1., 0., 1.]]), np.array([[1., 0., 0.], [0., 1., 0.]])):
            m = metrics(pool)
            self.assertAlmostEqual(m["headroom"], m["oracle_accuracy"] - m["best_fixed"])

    def test_shared_draw_preserves_identical_arm_null(self):
        pool = np.array([[1., 0., 1., 0.], [0., 1., 1., 0.]])
        keys = [(b, s) for b in ("a", "b") for s in range(3)]
        pairs = [[pool.copy(), pool.copy()] for _ in keys]
        points, ci = bootstrap(pairs, keys, np.array(["d1", "d1", "d2", "d2"]),
                               np.array([[-1., 1.]]), 100, 42)
        np.testing.assert_array_equal(points, 0)
        np.testing.assert_array_equal(ci, 0)

    def test_tasks_are_resampled_within_database(self):
        # One DB isolates the within-DB stage: it must not always return all tasks.
        rng = np.random.default_rng(42)
        draws = [sample_tasks(np.array(["db"] * 8), rng) for _ in range(20)]
        self.assertTrue(any(len(set(d)) < 8 for d in draws))
        self.assertTrue(all(len(d) == 8 for d in draws))

    def test_fixed_builders_never_dropped_or_reweighted(self):
        keys = [(b, s) for b in ("a", "b", "c") for s in range(3)]
        rng = np.random.default_rng(42)
        for _ in range(30):
            idx = sample_cells(keys, rng)
            self.assertEqual([sum(keys[i][0] == b for i in idx) for b in ("a", "b", "c")], [3, 3, 3])

    def test_holm_and_exact_signflip(self):
        np.testing.assert_allclose(holm([.02, .01, .2]), [.04, .03, .2])
        self.assertEqual(float(sign_p(np.array([[1.], [1.]]))[0]), .5)
        self.assertEqual(float(sign_p(np.array([[1.], [1.]]), one_sided=True)[0]), .25)
        self.assertEqual(float(sign_p(np.zeros((3, 1)))[0]), 1.)

    def test_shared_bare_and_missing_member_is_error(self):
        tasks = ["db#0", "db#1"]
        def rows(h, vv):
            return {("GLM-5.3-Flash", h, t, 0, False): {"official_correct": v}
                    for t, v in zip(tasks, vv)}
        groups = {"AD": rows("bare", [1, 0]), "BC": rows("bare", [0, 0])}
        mem = {("b", 0, a): [] for a in "ABCD"}
        _, pools = make_pools(groups, mem, tasks, "ABCD")
        for pool in pools[0]:
            np.testing.assert_array_equal(pool[0], [1, 0])
        mem["b", 0, "A"] = ["missing"]
        with self.assertRaises(KeyError):
            make_pools(groups, mem, tasks, "ABCD")


if __name__ == "__main__":
    unittest.main()
