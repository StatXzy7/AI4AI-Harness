"""Offline paired-analysis checks; archived loopback data contain artificial usage."""

import json
from pathlib import Path
import tempfile
import unittest

from experiment.revision.common_pool_extraction_compare import (
    analyze,
    compare_message,
    sha,
)
from experiment.revision.generation_extraction_audit import ROOT, legacy_extractor


class ExtractionComparisonTests(unittest.TestCase):
    def test_nested_fence_and_missing_content_keep_denominators(self):
        legacy = legacy_extractor()
        row = compare_message('```python\nPROMPT = "Return ```sql only."\n```', legacy)
        self.assertFalse(row["legacy_syntax_valid"])
        self.assertTrue(row["new_syntax_valid"])
        self.assertFalse(row["legacy_truncated"])
        missing = compare_message(None, legacy)
        self.assertFalse(missing["legacy_syntax_valid"])
        self.assertFalse(missing["new_syntax_valid"])

    def test_complete_artificial_pool_retains_all_six_attempts(self):
        pool = (
            ROOT
            / "artifacts/revision_20260910/common_pool_generation/loopback/pool/pool.json"
        )
        result = analyze(pool, sha(pool.read_bytes()))
        self.assertEqual(result["n_attempts"], 6)
        self.assertEqual(sum(r["count"] for r in result["paired_counts"]), 6)
        self.assertEqual(len({r["task_key"] for r in result["rows"]}), 6)
        with self.assertRaisesRegex(ValueError, "externally pinned"):
            analyze(pool, "0" * 64)

    def test_incomplete_export_cannot_be_analyzed_as_complete(self):
        original = (
            ROOT / "artifacts/revision_20260910/common_pool_generation/loopback/pool"
        )
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "pool.json"
            data = json.loads((original / "pool.json").read_text(encoding="utf-8"))
            data["tasks"][0]["result"] = None
            p.write_text(json.dumps(data), encoding="utf-8")
            marker = json.loads(
                (original / "POOL_COMPLETE.json").read_text(encoding="utf-8")
            )
            marker["pool_sha256"] = sha(p.read_bytes())
            p.with_name("POOL_COMPLETE.json").write_text(
                json.dumps(marker), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "incomplete"):
                analyze(p, marker["pool_sha256"])


if __name__ == "__main__":
    unittest.main()
