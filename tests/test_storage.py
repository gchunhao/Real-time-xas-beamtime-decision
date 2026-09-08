from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from xas_beamtime.analysis import AnalysisEngine
from xas_beamtime.models import HumanFeedback, ReviewContext, RuntimeLimits
from xas_beamtime.parser import UniversalXASParser
from xas_beamtime.registry import ProfileRegistry
from xas_beamtime.storage import Storage


class StorageTests(unittest.TestCase):
    def test_required_entities_and_v02_columns_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            storage = Storage(path)
            connection = sqlite3.connect(path)
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {
                "schema_version", "project", "session", "experiment", "sample", "scan",
                "cumulative_average", "metrics", "decision", "artifact_flag", "human_review",
                "profile_version", "algorithm_version", "audit_event", "review_queue",
            }
            self.assertTrue(required.issubset(names))
            self.assertEqual(set(storage.table_counts()), required)

            review_columns = {row[1] for row in connection.execute("PRAGMA table_info(human_review)")}
            decision_columns = {row[1] for row in connection.execute("PRAGMA table_info(decision)")}
            scan_columns = {row[1] for row in connection.execute("PRAGMA table_info(scan)")}
            sample_columns = {row[1] for row in connection.execute("PRAGMA table_info(sample)")}
            average_columns = {row[1] for row in connection.execute("PRAGMA table_info(cumulative_average)")}

            self.assertTrue({"reviewer_role", "reviewer_level", "review_context"}.issubset(review_columns))
            self.assertTrue({
                "scientific_decision", "resource_constraint", "sample_action", "scheduler_action",
                "effective_scheduler_action", "auto_execution_eligibility", "reason_codes_json",
                "decision_policy_version", "adjudicated_reviewer_decision", "adjudication_status",
            }.issubset(decision_columns))
            self.assertTrue({"disposition", "disposition_reason", "replacement_for_scan_id", "replaced_by_scan_id"}.issubset(scan_columns))
            self.assertTrue({"logical_sample_key", "spot_id", "grouping_confidence", "grouping_method", "session_id", "archived_at", "archived_reason"}.issubset(sample_columns))
            self.assertTrue({"analysis_context", "physical_scan_count", "usable_scan_count"}.issubset(average_columns))
            connection.close()
            storage.close()

    def test_schema_migrates_existing_v01_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript("""
            CREATE TABLE metrics (id TEXT PRIMARY KEY, cumulative_average_id TEXT, q_hf REAL, q_pre REAL, q_post REAL,
              a_spike REAL, e0 REAL, white_line_scale REAL, route TEXT, usable_protected_region INTEGER,
              diagnostics_json TEXT, created_at TEXT);
            CREATE TABLE human_review (id TEXT PRIMARY KEY, decision_id TEXT, rating TEXT, override_recommendation TEXT,
              averaging_mode TEXT, included_scans_json TEXT, excluded_scans_json TEXT, glitch_decisions_json TEXT,
              local_normalization_anchors_json TEXT, notes TEXT, reviewer TEXT, reviewer_role TEXT, created_at TEXT);
            CREATE TABLE decision (id TEXT PRIMARY KEY, cumulative_average_id TEXT, profile_version_id TEXT,
              algorithm_version_id TEXT, automatic_recommendation TEXT, automatic_reason TEXT, predicted_n_quant INTEGER,
              n_quant INTEGER, marginal_gain REAL, total_measured_seconds REAL, remaining_scan_budget INTEGER,
              remaining_time_seconds REAL, state_key TEXT, human_decision TEXT, manually_overridden INTEGER, created_at TEXT);
            CREATE TABLE artifact_flag (id TEXT PRIMARY KEY, cumulative_average_id TEXT, scan_id TEXT, energy REAL,
              magnitude REAL, region TEXT, protected INTEGER, automatically_masked INTEGER, human_status TEXT, created_at TEXT);
            CREATE TABLE experiment (id TEXT PRIMARY KEY, name TEXT, watch_folder TEXT, beamline TEXT, started_at TEXT, ended_at TEXT, settings_json TEXT);
            CREATE TABLE profile_version (id TEXT PRIMARY KEY, profile_id TEXT, version TEXT, sha256 TEXT UNIQUE, frozen INTEGER, snapshot_yaml TEXT, created_at TEXT);
            CREATE TABLE algorithm_version (id TEXT PRIMARY KEY, name TEXT, version TEXT, source_revision TEXT, parameters_json TEXT, created_at TEXT);
            CREATE TABLE sample (id TEXT PRIMARY KEY, experiment_id TEXT, sample_key TEXT, element TEXT, edge TEXT, scan_type TEXT, profile_version_id TEXT, created_at TEXT);
            CREATE TABLE scan (id TEXT PRIMARY KEY, sample_id TEXT, source_path TEXT, scan_number INTEGER, duration_seconds REAL,
              started_at TEXT, beamline TEXT, parser_name TEXT, parser_version TEXT, metadata_json TEXT, source_sha256 TEXT,
              included INTEGER, created_at TEXT);
            CREATE TABLE cumulative_average (id TEXT PRIMARY KEY, sample_id TEXT, scan_count INTEGER, averaging_mode TEXT,
              included_scan_ids_json TEXT, energy_json TEXT, raw_average_json TEXT, normalized_average_json TEXT,
              normalization_mode TEXT, created_at TEXT);
            """)
            connection.close()
            storage = Storage(path)
            migrated = sqlite3.connect(path)
            self.assertIn("scientific_decision", {row[1] for row in migrated.execute("PRAGMA table_info(decision)")})
            self.assertIn("disposition", {row[1] for row in migrated.execute("PRAGMA table_info(scan)")})
            self.assertIn("analysis_context", {row[1] for row in migrated.execute("PRAGMA table_info(cumulative_average)")})
            self.assertIn("session_id", {row[1] for row in migrated.execute("PRAGMA table_info(sample)")})
            self.assertIn("archived_at", {row[1] for row in migrated.execute("PRAGMA table_info(sample)")})
            migrated_names = {row[0] for row in migrated.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"project", "session", "review_queue", "schema_version"}.issubset(migrated_names))
            migrated.close()
            storage.close()

    def test_reviewer_hierarchy_and_same_level_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviews.sqlite3"
            storage = Storage(path)
            profile = ProfileRegistry().get("P_K_XANES_v1.2")
            scan = UniversalXASParser().parse(Path(__file__).parent.parent / "test_data" / "incoming" / "apatite_scan-001.dat")
            scan.metadata.logical_sample_key = scan.metadata.sample_id
            result = AnalysisEngine().analyze_series([scan], profile, RuntimeLimits(8, 900))[0]
            experiment_id = storage.ensure_experiment(str(Path(directory) / "watch"), None, {})
            profile_version_id = storage.ensure_profile(profile)
            algorithm_version_id = storage.ensure_algorithm("xas_analysis", "test", {})
            sample_id = storage.ensure_sample(experiment_id, scan, profile_version_id)
            storage.save_scan(sample_id, scan)
            storage.save_analysis(sample_id, result, profile_version_id, algorithm_version_id)

            base = dict(
                analysis_id=result.analysis_id, sample_id=result.sample_id, profile_id=profile.id, rating="QL-ready",
                averaging_mode="equal", included_scans=result.scan_ids, excluded_scans=[], glitch_decisions=[],
                local_normalization_anchors={}, review_context=ReviewContext.LIVE,
            )
            storage.save_review(HumanFeedback(**base, override_recommendation="CONTINUE", reviewer_role="User", reviewer_level=1))
            storage.save_review(HumanFeedback(**base, override_recommendation="STOP", reviewer_role="Beamline Scientist", reviewer_level=2))
            connection = sqlite3.connect(path)
            row = connection.execute("SELECT adjudicated_reviewer_decision, adjudication_status FROM decision").fetchone()
            self.assertEqual(row[0], "STOP")
            self.assertEqual(row[1], "ADJUDICATED_BY_HIGHEST_LEVEL")

            storage.save_review(HumanFeedback(**base, override_recommendation="CONTINUE", reviewer_role="PI", reviewer_level=2))
            row = connection.execute("SELECT adjudicated_reviewer_decision, adjudication_status FROM decision").fetchone()
            self.assertIsNone(row[0])
            self.assertEqual(row[1], "UNRESOLVED_SAME_LEVEL_CONFLICT")
            connection.close()
            storage.close()


if __name__ == "__main__":
    unittest.main()
