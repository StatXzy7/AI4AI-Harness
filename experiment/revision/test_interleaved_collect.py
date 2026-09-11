"""Offline ordering and real isolated-worker tests against a loopback provider."""

from collections import Counter
import itertools
import json
import os
import subprocess
import sys
import unittest

from experiment.revision.fresh_collect import ROOT
from experiment.revision.interleaved_collect import schedule
from experiment.revision.test_isolated_collect import fixture, provider


class InterleavedTests(unittest.TestCase):
    def test_complete_task_blocks_and_order_independence(self):
        tasks = [{"id": f"t{i}"} for i in range(4)]
        members = [{"id": f"h{i}"} for i in range(3)]
        rows = schedule([0, 1], members, tasks, "fixed")
        self.assertEqual(rows, schedule([0, 1], members[::-1], tasks[::-1], "fixed"))
        self.assertEqual(
            Counter((r["repeat"], r["task"], r["harness"]) for r in rows),
            Counter(
                itertools.product(
                    [0, 1], [t["id"] for t in tasks], [h["id"] for h in members]
                )
            ),
        )
        for offset in range(0, len(rows), 3):
            group = rows[offset : offset + 3]
            self.assertEqual(len({(r["repeat"], r["task"]) for r in group}), 1)
            self.assertEqual({r["harness"] for r in group}, {"h0", "h1", "h2"})
        with self.assertRaises(ValueError):
            schedule([0], members, tasks, "")

    def invoke(self, path):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "experiment.revision.interleaved_collect",
                "--config",
                str(path),
            ],
            cwd=ROOT,
            env={**os.environ, "ISOLATED_FIXTURE_KEY": "dummy-local"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )

    def configure(self, folder, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["schedule_salt"] = "offline-interleaving"
        source = "external/TTHE/text_to_sql/agents/bare.py"
        data["harnesses"] = [
            dict(id="bare", source=source),
            dict(id="clone", source=source),
        ]
        dev = json.loads((folder / "dev.json").read_text(encoding="utf-8"))
        dev.append({**dev[0], "question": "Count the entries again."})
        (folder / "dev.json").write_text(json.dumps(dev), encoding="utf-8")
        (folder / "split.json").write_text(
            json.dumps({"by_db": {"fixture": [0, 1]}}), encoding="utf-8"
        )
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_actual_workers_follow_schedule_and_complete_all_cells(self):
        with provider() as (url, calls), fixture(url, harness="bare") as (folder, path):
            self.configure(folder, path)
            result = self.invoke(path)
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(
                (folder / "output/snapshot.json").read_text(encoding="utf-8")
            )
            starts = [
                e["identity"]
                for e in snapshot["events"]
                if e["kind"] == "task_start" and "worker_event" not in e
            ]
            # Parent ledger also imports worker task_start events; distinguish parent starts by the absence of worker_event.
            self.assertEqual(starts, snapshot["manifest"]["schedule"])
            self.assertEqual(len(snapshot["tasks"]), 8)
            self.assertEqual(len(calls), 8)
            self.assertTrue(
                all(
                    t["result"]["accounting"]["total_tokens"] == 5
                    for t in snapshot["tasks"]
                )
            )
            exits = [e for e in snapshot["events"] if e["kind"] == "worker_exited"]
            self.assertTrue(
                all(e["after_cleanup"]["active_processes"] == 0 for e in exits)
            )

    def test_missing_usage_stops_before_next_scheduled_cell(self):
        with provider(missing_usage=True) as (url, calls), fixture(
            url, harness="bare"
        ) as (folder, path):
            self.configure(folder, path)
            result = self.invoke(path)
            self.assertNotEqual(result.returncode, 0)
            snapshot = json.loads(
                (folder / "output/snapshot.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(snapshot["tasks"]), 1)
            self.assertIsNone(snapshot["tasks"][0]["result"])


if __name__ == "__main__":
    unittest.main()
