from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import AnalysisResult, HumanFeedback, ScanMetadata, Spectrum, canonical_scan_id, utc_now
from .registry import Profile


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS experiment (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, watch_folder TEXT NOT NULL,
  beamline TEXT, started_at TEXT NOT NULL, ended_at TEXT, settings_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_version (
  id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, version TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE, frozen INTEGER NOT NULL, snapshot_yaml TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS algorithm_version (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
  source_revision TEXT, parameters_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(name, version, parameters_json)
);
CREATE TABLE IF NOT EXISTS sample (
  id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiment(id),
  sample_key TEXT NOT NULL, element TEXT, edge TEXT, scan_type TEXT,
  profile_version_id TEXT REFERENCES profile_version(id), created_at TEXT NOT NULL,
  UNIQUE(experiment_id, sample_key)
);
CREATE TABLE IF NOT EXISTS scan (
  id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES sample(id), source_path TEXT NOT NULL,
  scan_number INTEGER, duration_seconds REAL, started_at TEXT, beamline TEXT,
  parser_name TEXT NOT NULL, parser_version TEXT NOT NULL, metadata_json TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, included INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
  UNIQUE(sample_id, source_path)
);
CREATE TABLE IF NOT EXISTS cumulative_average (
  id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES sample(id), scan_count INTEGER NOT NULL,
  averaging_mode TEXT NOT NULL, included_scan_ids_json TEXT NOT NULL,
  energy_json TEXT NOT NULL, raw_average_json TEXT NOT NULL, normalized_average_json TEXT NOT NULL,
  normalization_mode TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
  id TEXT PRIMARY KEY, cumulative_average_id TEXT NOT NULL REFERENCES cumulative_average(id),
  q_hf REAL, q_pre REAL, q_post REAL, a_spike REAL, e0 REAL, white_line_scale REAL,
  route TEXT, usable_protected_region INTEGER NOT NULL, diagnostics_json TEXT NOT NULL,
  uncertainty_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decision (
  id TEXT PRIMARY KEY, cumulative_average_id TEXT NOT NULL REFERENCES cumulative_average(id),
  profile_version_id TEXT NOT NULL REFERENCES profile_version(id),
  algorithm_version_id TEXT NOT NULL REFERENCES algorithm_version(id),
  automatic_recommendation TEXT NOT NULL, automatic_reason TEXT NOT NULL,
  predicted_n_quant INTEGER, n_quant INTEGER, marginal_gain REAL,
  total_measured_seconds REAL NOT NULL, remaining_scan_budget INTEGER,
  remaining_time_seconds REAL, state_key TEXT NOT NULL,
  human_decision TEXT, manually_overridden INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifact_flag (
  id TEXT PRIMARY KEY, cumulative_average_id TEXT NOT NULL REFERENCES cumulative_average(id),
  scan_id TEXT, energy REAL NOT NULL, magnitude REAL NOT NULL, region TEXT NOT NULL,
  protected INTEGER NOT NULL, automatically_masked INTEGER NOT NULL,
  human_status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS human_review (
  id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES decision(id),
  rating TEXT NOT NULL, override_recommendation TEXT, averaging_mode TEXT NOT NULL,
  included_scans_json TEXT NOT NULL, excluded_scans_json TEXT NOT NULL,
  glitch_decisions_json TEXT NOT NULL, local_normalization_anchors_json TEXT NOT NULL,
  notes TEXT NOT NULL, reviewer TEXT, reviewer_role TEXT NOT NULL DEFAULT 'beamline_user',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scan_sample ON scan(sample_id, scan_number);
CREATE INDEX IF NOT EXISTS ix_average_sample ON cumulative_average(sample_id, scan_count);
CREATE INDEX IF NOT EXISTS ix_decision_average ON decision(cumulative_average_id);
CREATE INDEX IF NOT EXISTS ix_review_decision ON human_review(decision_id);
"""


class Storage:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.executescript(SCHEMA)
            columns = {row[1] for row in self._connection.execute("PRAGMA table_info(metrics)")}
            if "uncertainty_json" not in columns:
                self._connection.execute("ALTER TABLE metrics ADD COLUMN uncertainty_json TEXT NOT NULL DEFAULT '{}'")
            review_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(human_review)")}
            if "reviewer_role" not in review_columns:
                self._connection.execute(
                    "ALTER TABLE human_review ADD COLUMN reviewer_role TEXT NOT NULL DEFAULT 'beamline_user'"
                )
            decision_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(decision)")}
            if "scientist_decision" in decision_columns and "human_decision" not in decision_columns:
                self._connection.execute("ALTER TABLE decision RENAME COLUMN scientist_decision TO human_decision")
            artifact_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(artifact_flag)")}
            if "scientist_status" in artifact_columns and "human_status" not in artifact_columns:
                self._connection.execute("ALTER TABLE artifact_flag RENAME COLUMN scientist_status TO human_status")

    def _one(self, sql: str, parameters: tuple[Any, ...]) -> sqlite3.Row | None:
        return self._connection.execute(sql, parameters).fetchone()

    def ensure_experiment(self, watch_folder: str, beamline: str | None, settings: dict[str, Any]) -> str:
        with self._lock, self._connection:
            row = self._one("SELECT id FROM experiment WHERE watch_folder=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1", (watch_folder,))
            if row:
                return str(row["id"])
            experiment_id = str(uuid.uuid4())
            self._connection.execute(
                "INSERT INTO experiment VALUES (?,?,?,?,?,?,?)",
                (experiment_id, f"Beamtime {Path(watch_folder).name}", watch_folder, beamline, utc_now(), None, json.dumps(settings)),
            )
            return experiment_id

    def ensure_profile(self, profile: Profile) -> str:
        content = profile.source.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self._lock, self._connection:
            row = self._one("SELECT id FROM profile_version WHERE sha256=?", (digest,))
            if row:
                return str(row["id"])
            identifier = str(uuid.uuid4())
            self._connection.execute(
                "INSERT INTO profile_version VALUES (?,?,?,?,?,?,?)",
                (identifier, profile.id, str(profile.data.get("version")), digest, int(profile.data.get("status") == "frozen"), content, utc_now()),
            )
            return identifier

    def ensure_algorithm(self, name: str, version: str, parameters: dict[str, Any]) -> str:
        encoded = json.dumps(parameters, sort_keys=True)
        with self._lock, self._connection:
            row = self._one("SELECT id FROM algorithm_version WHERE name=? AND version=? AND parameters_json=?", (name, version, encoded))
            if row:
                return str(row["id"])
            identifier = str(uuid.uuid4())
            self._connection.execute(
                "INSERT INTO algorithm_version VALUES (?,?,?,?,?,?)",
                (identifier, name, version, None, encoded, utc_now()),
            )
            return identifier

    def ensure_sample(self, experiment_id: str, spectrum: Spectrum, profile_version_id: str) -> str:
        metadata = spectrum.metadata
        sample_key = metadata.sample_id or Path(metadata.source_path).stem
        with self._lock, self._connection:
            row = self._one("SELECT id FROM sample WHERE experiment_id=? AND sample_key=?", (experiment_id, sample_key))
            if row:
                return str(row["id"])
            identifier = str(uuid.uuid4())
            self._connection.execute(
                "INSERT INTO sample VALUES (?,?,?,?,?,?,?,?)",
                (identifier, experiment_id, sample_key, metadata.element, metadata.edge, metadata.scan_type, profile_version_id, utc_now()),
            )
            return identifier

    def save_scan(self, sample_id: str, spectrum: Spectrum) -> str:
        scan_id = canonical_scan_id(spectrum.metadata)
        payload = json.dumps(asdict(spectrum.metadata), sort_keys=True)
        digest = hashlib.sha256(spectrum.energy.tobytes() + spectrum.mu.tobytes()).hexdigest()
        with self._lock, self._connection:
            row = self._one("SELECT id FROM scan WHERE sample_id=? AND source_path=?", (sample_id, spectrum.metadata.source_path))
            if row:
                return str(row["id"])
            self._connection.execute(
                "INSERT INTO scan VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    scan_id, sample_id, spectrum.metadata.source_path, spectrum.metadata.scan_number,
                    spectrum.metadata.duration_seconds, spectrum.metadata.started_at, spectrum.metadata.beamline,
                    spectrum.metadata.parser_name, spectrum.metadata.parser_version, payload, digest, 1, utc_now(),
                ),
            )
            return scan_id

    def save_analysis(self, sample_id: str, result: AnalysisResult, profile_version_id: str, algorithm_version_id: str) -> str:
        average_id = result.analysis_id
        decision_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO cumulative_average VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    average_id, sample_id, result.scan_count, result.averaging_mode, json.dumps(result.scan_ids),
                    json.dumps(result.energy.tolist()), json.dumps(result.raw_average.tolist()),
                    json.dumps(result.normalized_average.tolist()), result.metrics.normalization_mode, result.created_at,
                ),
            )
            self._connection.execute(
                """INSERT INTO metrics
                (id,cumulative_average_id,q_hf,q_pre,q_post,a_spike,e0,white_line_scale,route,
                 usable_protected_region,diagnostics_json,uncertainty_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), average_id, result.metrics.q_hf, result.metrics.q_pre, result.metrics.q_post,
                    result.metrics.a_spike, result.metrics.e0, result.metrics.white_line_scale, result.metrics.route,
                    int(result.metrics.usable_protected_region), json.dumps(result.metrics.diagnostics),
                    json.dumps(result.uncertainty), result.created_at,
                ),
            )
            state_key = "quantitative_candidate" if result.metrics.route else (
                "qualitative_only" if result.recommendation.value == "QL ONLY" else "collecting"
            )
            self._connection.execute(
                "INSERT INTO decision VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    decision_id, average_id, profile_version_id, algorithm_version_id,
                    result.recommendation.value, result.recommendation_reason, result.predicted_n_quant,
                    result.n_quant, result.marginal_gain, result.total_measured_seconds,
                    result.remaining_scan_budget, result.remaining_time_seconds, state_key,
                    None, 0, result.created_at,
                ),
            )
            for anomaly in result.anomalies:
                self._connection.execute(
                    "INSERT INTO artifact_flag VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()), average_id, None, anomaly.energy, anomaly.magnitude, anomaly.region,
                        int(anomaly.protected), int(anomaly.automatically_masked), anomaly.status, result.created_at,
                    ),
                )
        return decision_id

    def save_review(self, feedback: HumanFeedback, reviewer: str | None = None) -> str:
        with self._lock, self._connection:
            row = self._one(
                "SELECT d.id FROM decision d WHERE d.cumulative_average_id=? ORDER BY d.created_at DESC LIMIT 1",
                (feedback.analysis_id,),
            )
            if row is None:
                raise KeyError(f"No decision for analysis {feedback.analysis_id}")
            decision_id = str(row["id"])
            review_id = str(uuid.uuid4())
            self._connection.execute(
                """INSERT INTO human_review
                (id,decision_id,rating,override_recommendation,averaging_mode,included_scans_json,
                 excluded_scans_json,glitch_decisions_json,local_normalization_anchors_json,notes,
                 reviewer,reviewer_role,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    review_id, decision_id, feedback.rating, feedback.override_recommendation,
                    feedback.averaging_mode, json.dumps(feedback.included_scans), json.dumps(feedback.excluded_scans),
                    json.dumps(feedback.glitch_decisions), json.dumps(feedback.local_normalization_anchors),
                    feedback.notes, reviewer, feedback.reviewer_role, feedback.created_at,
                ),
            )
            self._connection.execute(
                "UPDATE decision SET human_decision=?, manually_overridden=? WHERE id=?",
                (feedback.override_recommendation or feedback.rating, int(feedback.override_recommendation is not None), decision_id),
            )
            for choice in feedback.glitch_decisions:
                if "id" in choice:
                    self._connection.execute(
                        "UPDATE artifact_flag SET human_status=? WHERE id=?",
                        (choice.get("status", "unreviewed"), choice["id"]),
                    )
            return review_id

    def table_counts(self) -> dict[str, int]:
        tables = ["experiment", "sample", "scan", "cumulative_average", "metrics", "decision", "artifact_flag", "human_review", "profile_version", "algorithm_version"]
        with self._lock:
            return {table: int(self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}

    def recent_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        sql = """
        SELECT hr.*, d.automatic_recommendation, d.automatic_reason, ca.scan_count,
               s.sample_key, pv.profile_id, pv.version AS profile_version
        FROM human_review hr
        JOIN decision d ON d.id=hr.decision_id
        JOIN cumulative_average ca ON ca.id=d.cumulative_average_id
        JOIN sample s ON s.id=ca.sample_id
        JOIN profile_version pv ON pv.id=d.profile_version_id
        ORDER BY hr.created_at DESC LIMIT ?
        """
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, (limit,)).fetchall()]
