from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from xas_beamtime.storage import Storage


class StorageTests(unittest.TestCase):
    def test_required_entities_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            storage = Storage(path)
            names = {row[0] for row in sqlite3.connect(path).execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {
                "experiment", "sample", "scan", "cumulative_average", "metrics", "decision",
                "artifact_flag", "human_review", "profile_version", "algorithm_version",
            }
            self.assertTrue(required.issubset(names))
            self.assertEqual(set(storage.table_counts()), required)
            review_columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(human_review)")}
            decision_columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(decision)")}
            self.assertIn("reviewer_role", review_columns)
            self.assertIn("human_decision", decision_columns)


if __name__ == "__main__":
    unittest.main()
