from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    AnalysisResult,
    HumanFeedback,
    ScanDisposition,
    Spectrum,
    canonical_scan_id,
    utc_now,
)
from .registry import Profile


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id), legacy_experiment_id TEXT,
  name TEXT NOT NULL, watch_folder TEXT NOT NULL, beamline TEXT, started_at TEXT NOT NULL,
  ended_at TEXT, settings_json TEXT NOT NULL
);
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
  logical_sample_key TEXT, base_sample_name TEXT, spot_id TEXT,
  grouping_confidence REAL, grouping_method TEXT, requires_grouping_confirmation INTEGER NOT NULL DEFAULT 0,
  UNIQUE(experiment_id, sample_key)
);
CREATE TABLE IF NOT EXISTS scan (
  id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES sample(id), source_path TEXT NOT NULL,
  scan_number INTEGER, duration_seconds REAL, started_at TEXT, beamline TEXT,
  parser_name TEXT NOT NULL, parser_version TEXT NOT NULL, metadata_json TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, included INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
  disposition TEXT NOT NULL DEFAULT 'USABLE', disposition_reason TEXT,
  replacement_for_scan_id TEXT, replaced_by_scan_id TEXT,
  UNIQUE(sample_id, source_path)
);
CREATE TABLE IF NOT EXISTS cumulative_average (
  id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES sample(id), scan_count INTEGER NOT NULL,
  averaging_mode TEXT NOT NULL, included_scan_ids_json TEXT NOT NULL,
  energy_json TEXT NOT NULL, raw_average_json TEXT NOT NULL, normalized_average_json TEXT NOT NULL,
  normalization_mode TEXT NOT NULL, created_at TEXT NOT NULL,
  analysis_context TEXT NOT NULL DEFAULT 'PRODUCTION',
  physical_scan_count INTEGER, usable_scan_count INTEGER
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
  created_at TEXT NOT NULL,
  scientific_decision TEXT, resource_constraint TEXT, sample_action TEXT,
  scheduler_action TEXT, effective_scheduler_action TEXT,
  auto_execution_eligibility TEXT, reason_codes_json TEXT NOT NULL DEFAULT '[]',
  suggested_reviewer_action TEXT, decision_confidence TEXT,
  decision_policy_version TEXT, adjudicated_reviewer_decision TEXT,
  adjudication_status TEXT NOT NULL DEFAULT 'NO_REVIEW'
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
  notes TEXT NOT NULL, reviewer TEXT, reviewer_role TEXT NOT NULL DEFAULT 'User',
  created_at TEXT NOT NULL, reviewer_level INTEGER NOT NULL DEFAULT 0,
  review_context TEXT NOT NULL DEFAULT 'LIVE'
);
CREATE TABLE IF NOT EXISTS audit_event (
  id TEXT PRIMARY KEY, event_type TEXT NOT NULL, sample_id TEXT, scan_id TEXT,
  analysis_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_queue (
  id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES sample(id), analysis_id TEXT NOT NULL,
  decision_id TEXT, status TEXT NOT NULL, reason_codes_json TEXT NOT NULL,
  suggested_reviewer_action TEXT, enqueued_at TEXT NOT NULL, resolved_at TEXT,
  resolved_by_review_id TEXT, resolution_note TEXT, UNIQUE(sample_id, analysis_id)
);
CREATE INDEX IF NOT EXISTS ix_scan_sample ON scan(sample_id, scan_number);
CREATE INDEX IF NOT EXISTS ix_average_sample ON cumulative_average(sample_id, scan_count);
CREATE INDEX IF NOT EXISTS ix_decision_average ON decision(cumulative_average_id);
CREATE INDEX IF NOT EXISTS ix_review_decision ON human_review(decision_id);
CREATE INDEX IF NOT EXISTS ix_audit_sample ON audit_event(sample_id, created_at);
CREATE INDEX IF NOT EXISTS ix_review_queue_status ON review_queue(status, enqueued_at);
CREATE INDEX IF NOT EXISTS ix_session_project ON session(project_id, started_at);
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
            self._migrate_v02()

    def close(self) -> None:
        """Release the SQLite handle deterministically (required on Windows)."""
        with self._lock:
            self._connection.close()

    def _columns(self, table: str) -> set[str]:
        return {row[1] for row in self._connection.execute(f"PRAGMA table_info({table})")}

    def _add_column(self, table: str, definition: str) -> None:
        name = definition.split()[0]
        if name not in self._columns(table):
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def _migrate_v02(self) -> None:
        self._add_column("metrics", "uncertainty_json TEXT NOT NULL DEFAULT '{}'")
        self._add_column("human_review", "reviewer_role TEXT NOT NULL DEFAULT 'User'")
        self._add_column("human_review", "reviewer_level INTEGER NOT NULL DEFAULT 0")
        self._add_column("human_review", "review_context TEXT NOT NULL DEFAULT 'LIVE'")
        self._add_column("sample", "logical_sample_key TEXT")
        self._add_column("sample", "base_sample_name TEXT")
        self._add_column("sample", "spot_id TEXT")
        self._add_column("sample", "grouping_confidence REAL")
        self._add_column("sample", "grouping_method TEXT")
        self._add_column("sample", "requires_grouping_confirmation INTEGER NOT NULL DEFAULT 0")
        self._add_column("sample", "session_id TEXT")
        self._add_column("scan", "disposition TEXT NOT NULL DEFAULT 'USABLE'")
        self._add_column("scan", "disposition_reason TEXT")
        self._add_column("scan", "replacement_for_scan_id TEXT")
        self._add_column("scan", "replaced_by_scan_id TEXT")
        self._add_column("cumulative_average", "analysis_context TEXT NOT NULL DEFAULT 'PRODUCTION'")
        self._add_column("cumulative_average", "physical_scan_count INTEGER")
        self._add_column("cumulative_average", "usable_scan_count INTEGER")
        decision_columns = self._columns("decision")
        if "scientist_decision" in decision_columns and "human_decision" not in decision_columns:
            self._connection.execute("ALTER TABLE decision RENAME COLUMN scientist_decision TO human_decision")
        for definition in (
            "scientific_decision TEXT", "resource_constraint TEXT", "sample_action TEXT",
            "scheduler_action TEXT", "effective_scheduler_action TEXT",
            "auto_execution_eligibility TEXT", "reason_codes_json TEXT NOT NULL DEFAULT '[]'",
            "suggested_reviewer_action TEXT", "decision_confidence TEXT",
            "decision_policy_version TEXT", "adjudicated_reviewer_decision TEXT",
            "adjudication_status TEXT NOT NULL DEFAULT 'NO_REVIEW'",
        ):
            self._add_column("decision", definition)
        artifact_columns = self._columns("artifact_flag")
        if "scientist_status" in artifact_columns and "human_status" not in artifact_columns:
            self._connection.execute("ALTER TABLE artifact_flag RENAME COLUMN scientist_status TO human_status")
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS audit_event (
              id TEXT PRIMARY KEY, event_type TEXT NOT NULL, sample_id TEXT, scan_id TEXT,
              analysis_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            )"""
        )
        self._connection.execute("CREATE INDEX IF NOT EXISTS ix_audit_sample ON audit_event(sample_id, created_at)")
        self._connection.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS project (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS session (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, legacy_experiment_id TEXT, name TEXT NOT NULL,
          watch_folder TEXT NOT NULL, beamline TEXT, started_at TEXT NOT NULL, ended_at TEXT, settings_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS review_queue (
          id TEXT PRIMARY KEY, sample_id TEXT NOT NULL, analysis_id TEXT NOT NULL, decision_id TEXT,
          status TEXT NOT NULL, reason_codes_json TEXT NOT NULL, suggested_reviewer_action TEXT,
          enqueued_at TEXT NOT NULL, resolved_at TEXT, resolved_by_review_id TEXT, resolution_note TEXT,
          UNIQUE(sample_id, analysis_id)
        );
        CREATE INDEX IF NOT EXISTS ix_review_queue_status ON review_queue(status, enqueued_at);
        CREATE INDEX IF NOT EXISTS ix_session_project ON session(project_id, started_at);
        """)
        self._connection.execute("INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?,?)", (2, utc_now()))

    def _one(self, sql: str, parameters: tuple[Any, ...]) -> sqlite3.Row | None:
        return self._connection.execute(sql, parameters).fetchone()

    def ensure_experiment(self, watch_folder: str, beamline: str | None, settings: dict[str, Any]) -> str:
        with self._lock, self._connection:
            row = self._one(
                "SELECT id FROM experiment WHERE watch_folder=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (watch_folder,),
            )
            if row:
                return str(row["id"])
            experiment_id = str(uuid.uuid4())
            self._connection.execute(
                "INSERT INTO experiment VALUES (?,?,?,?,?,?,?)",
                (experiment_id, f"Beamtime {Path(watch_folder).name}", watch_folder, beamline, utc_now(), None, json.dumps(settings)),
            )
            return experiment_id


    def ensure_project_session(
        self,
        watch_folder: str,
        beamline: str | None,
        settings: dict[str, Any],
        legacy_experiment_id: str,
        project_name: str = "XAS Project",
        session_name: str | None = None,
    ) -> tuple[str, str]:
        session_name = session_name or f"Session {Path(watch_folder).name}"
        with self._lock, self._connection:
            project_row = self._one("SELECT id FROM project WHERE name=? ORDER BY created_at LIMIT 1", (project_name,))
            if project_row:
                project_id = str(project_row["id"])
            else:
                project_id = str(uuid.uuid4())
                self._connection.execute(
                    "INSERT INTO project(id,name,metadata_json,created_at) VALUES (?,?,?,?)",
                    (project_id, project_name, json.dumps({}), utc_now()),
                )
            session_row = self._one(
                "SELECT id FROM session WHERE legacy_experiment_id=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (legacy_experiment_id,),
            )
            if session_row:
                return project_id, str(session_row["id"])
            session_id = str(uuid.uuid4())
            self._connection.execute(
                """INSERT INTO session
                (id,project_id,legacy_experiment_id,name,watch_folder,beamline,started_at,ended_at,settings_json)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (session_id, project_id, legacy_experiment_id, session_name, watch_folder, beamline, utc_now(), None, json.dumps(settings)),
            )
            return project_id, session_id

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
            row = self._one(
                "SELECT id FROM algorithm_version WHERE name=? AND version=? AND parameters_json=?",
                (name, version, encoded),
            )
            if row:
                return str(row["id"])
            identifier = str(uuid.uuid4())
            self._connection.execute(
                "INSERT INTO algorithm_version VALUES (?,?,?,?,?,?)",
                (identifier, name, version, None, encoded, utc_now()),
            )
            return identifier

    def ensure_sample(self, experiment_id: str, spectrum: Spectrum, profile_version_id: str, session_id: str | None = None) -> str:
        metadata = spectrum.metadata
        sample_key = metadata.logical_sample_key or metadata.sample_id or Path(metadata.source_path).stem
        with self._lock, self._connection:
            row = self._one("SELECT id FROM sample WHERE experiment_id=? AND sample_key=?", (experiment_id, sample_key))
            if row:
                return str(row["id"])
            identifier = str(uuid.uuid4())
            self._connection.execute(
                """INSERT INTO sample
                (id,experiment_id,sample_key,element,edge,scan_type,profile_version_id,created_at,
                 logical_sample_key,base_sample_name,spot_id,grouping_confidence,grouping_method,
                 requires_grouping_confirmation,session_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier, experiment_id, sample_key, metadata.element, metadata.edge, metadata.scan_type,
                    profile_version_id, utc_now(), metadata.logical_sample_key or sample_key,
                    metadata.base_sample_name or metadata.sample_id or sample_key, metadata.spot_id,
                    metadata.grouping_confidence, metadata.grouping_method,
                    int(metadata.requires_grouping_confirmation), session_id,
                ),
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
                """INSERT INTO scan
                (id,sample_id,source_path,scan_number,duration_seconds,started_at,beamline,parser_name,
                 parser_version,metadata_json,source_sha256,included,created_at,disposition)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    scan_id, sample_id, spectrum.metadata.source_path, spectrum.metadata.scan_number,
                    spectrum.metadata.duration_seconds, spectrum.metadata.started_at, spectrum.metadata.beamline,
                    spectrum.metadata.parser_name, spectrum.metadata.parser_version, payload, digest, 1, utc_now(),
                    ScanDisposition.USABLE.value,
                ),
            )
            return scan_id

    def set_scan_disposition(
        self,
        scan_id: str,
        disposition: ScanDisposition,
        reason: str | None = None,
        replacement_for_scan_id: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE scan SET disposition=?, disposition_reason=?, replacement_for_scan_id=? WHERE id=?",
                (disposition.value, reason, replacement_for_scan_id, scan_id),
            )
            if replacement_for_scan_id:
                self._connection.execute("UPDATE scan SET replaced_by_scan_id=? WHERE id=?", (scan_id, replacement_for_scan_id))

    def scan_dispositions(self, sample_id: str) -> dict[str, ScanDisposition]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, disposition FROM scan WHERE sample_id=? ORDER BY scan_number, created_at", (sample_id,)
            ).fetchall()
            return {str(row["id"]): ScanDisposition(str(row["disposition"])) for row in rows}

    def get_scan_record(self, scan_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._one(
                """SELECT sc.*, s.sample_key, s.logical_sample_key, s.session_id
                   FROM scan sc JOIN sample s ON s.id=sc.sample_id WHERE sc.id=?""",
                (scan_id,),
            )
            return dict(row) if row else None

    def save_analysis(self, sample_id: str, result: AnalysisResult, profile_version_id: str, algorithm_version_id: str) -> str:
        average_id = result.analysis_id
        decision_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO cumulative_average
                (id,sample_id,scan_count,averaging_mode,included_scan_ids_json,energy_json,raw_average_json,
                 normalized_average_json,normalization_mode,created_at,analysis_context,physical_scan_count,usable_scan_count)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    average_id, sample_id, result.scan_count, result.averaging_mode, json.dumps(result.scan_ids),
                    json.dumps(result.energy.tolist()), json.dumps(result.raw_average.tolist()),
                    json.dumps(result.normalized_average.tolist()), result.metrics.normalization_mode,
                    result.created_at, result.analysis_context.value, result.physical_scan_count, result.usable_scan_count,
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
            state_key = result.recommendation.value.lower()
            self._connection.execute(
                """INSERT INTO decision
                (id,cumulative_average_id,profile_version_id,algorithm_version_id,automatic_recommendation,
                 automatic_reason,predicted_n_quant,n_quant,marginal_gain,total_measured_seconds,
                 remaining_scan_budget,remaining_time_seconds,state_key,human_decision,manually_overridden,
                 created_at,scientific_decision,resource_constraint,sample_action,scheduler_action,
                 effective_scheduler_action,auto_execution_eligibility,reason_codes_json,
                 suggested_reviewer_action,decision_confidence,decision_policy_version,
                 adjudicated_reviewer_decision,adjudication_status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    decision_id, average_id, profile_version_id, algorithm_version_id,
                    result.recommendation.value, result.recommendation_reason, result.predicted_n_quant,
                    result.n_quant, result.marginal_gain, result.total_measured_seconds,
                    result.remaining_scan_budget, result.remaining_time_seconds, state_key, None, 0,
                    result.created_at, result.recommendation.value, result.resource_constraint.value,
                    result.sample_action.value, result.scheduler_action.value,
                    result.effective_scheduler_action.value, result.auto_execution_eligibility.value,
                    json.dumps(result.decision_reason_codes), result.suggested_reviewer_action,
                    result.decision_confidence, result.decision_policy_version, None, "NO_REVIEW",
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
            self._save_audit_event_locked(
                "AUTOMATED_DECISION", sample_id=sample_id, analysis_id=average_id,
                payload={
                    "scientific_decision": result.recommendation.value,
                    "sample_action": result.sample_action.value,
                    "scheduler_action": result.scheduler_action.value,
                    "effective_scheduler_action": result.effective_scheduler_action.value,
                    "resource_constraint": result.resource_constraint.value,
                    "auto_execution_eligibility": result.auto_execution_eligibility.value,
                },
            )
            if result.analysis_context.value == "PRODUCTION" and result.recommendation.value == "REVIEW_REQUIRED":
                self._supersede_pending_reviews_locked(
                    sample_id, "SUPERSEDED_BY_NEW_AUTOMATED_DECISION"
                )
                self._enqueue_review_locked(
                    sample_id, average_id, decision_id, result.decision_reason_codes,
                    result.suggested_reviewer_action,
                )
            elif result.analysis_context.value == "PRODUCTION":
                self._supersede_pending_reviews_locked(sample_id, "SUPERSEDED_BY_NEW_AUTOMATED_DECISION")
        return decision_id

    def _enqueue_review_locked(
        self, sample_id: str, analysis_id: str, decision_id: str, reason_codes: list[str], suggested_action: str | None
    ) -> str:
        existing = self._one("SELECT id FROM review_queue WHERE sample_id=? AND analysis_id=?", (sample_id, analysis_id))
        if existing:
            return str(existing["id"])
        queue_id = str(uuid.uuid4())
        self._connection.execute(
            """INSERT INTO review_queue
            (id,sample_id,analysis_id,decision_id,status,reason_codes_json,suggested_reviewer_action,enqueued_at,
             resolved_at,resolved_by_review_id,resolution_note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (queue_id, sample_id, analysis_id, decision_id, "PENDING", json.dumps(reason_codes),
             suggested_action, utc_now(), None, None, None),
        )
        self._save_audit_event_locked(
            "REVIEW_QUEUED", sample_id=sample_id, analysis_id=analysis_id,
            payload={"queue_id": queue_id, "reason_codes": reason_codes, "suggested_reviewer_action": suggested_action},
        )
        return queue_id

    def _supersede_pending_reviews_locked(self, sample_id: str, note: str) -> None:
        pending = self._connection.execute(
            "SELECT id, analysis_id FROM review_queue WHERE sample_id=? AND status='PENDING'", (sample_id,)
        ).fetchall()
        for row in pending:
            self._connection.execute(
                "UPDATE review_queue SET status='SUPERSEDED', resolved_at=?, resolution_note=? WHERE id=?",
                (utc_now(), note, row["id"]),
            )
            self._save_audit_event_locked(
                "REVIEW_QUEUE_SUPERSEDED", sample_id=sample_id, analysis_id=str(row["analysis_id"]),
                payload={"queue_id": str(row["id"]), "reason": note},
            )

    def _resolve_review_queue_locked(self, decision_id: str, review_id: str, adjudicated: str | None) -> None:
        if adjudicated not in {"CONTINUE", "STOP", "REACQUIRE"}:
            return
        rows = self._connection.execute(
            "SELECT id, sample_id, analysis_id FROM review_queue WHERE decision_id=? AND status='PENDING'", (decision_id,)
        ).fetchall()
        for row in rows:
            self._connection.execute(
                """UPDATE review_queue SET status='RESOLVED', resolved_at=?, resolved_by_review_id=?, resolution_note=?
                   WHERE id=?""",
                (utc_now(), review_id, f"Reviewer adjudicated {adjudicated}", row["id"]),
            )
            self._save_audit_event_locked(
                "REVIEW_RESOLVED", sample_id=str(row["sample_id"]), analysis_id=str(row["analysis_id"]),
                payload={"queue_id": str(row["id"]), "review_id": review_id, "adjudicated": adjudicated},
            )

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
            proposed = feedback.override_recommendation
            self._connection.execute(
                """INSERT INTO human_review
                (id,decision_id,rating,override_recommendation,averaging_mode,included_scans_json,
                 excluded_scans_json,glitch_decisions_json,local_normalization_anchors_json,notes,
                 reviewer,reviewer_role,created_at,reviewer_level,review_context)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    review_id, decision_id, feedback.rating, feedback.override_recommendation,
                    feedback.averaging_mode, json.dumps(feedback.included_scans), json.dumps(feedback.excluded_scans),
                    json.dumps(feedback.glitch_decisions), json.dumps(feedback.local_normalization_anchors),
                    feedback.notes, reviewer, feedback.reviewer_role, feedback.created_at,
                    feedback.reviewer_level, feedback.review_context.value,
                ),
            )
            reviews = self._connection.execute(
                "SELECT reviewer_level, override_recommendation AS proposed FROM human_review WHERE decision_id=? AND override_recommendation IS NOT NULL",
                (decision_id,),
            ).fetchall()
            if not reviews:
                adjudicated = None
                status = "QUALITY_RATING_ONLY"
            else:
                max_level = max(int(r["reviewer_level"]) for r in reviews)
                top = {str(r["proposed"]) for r in reviews if int(r["reviewer_level"]) == max_level}
                if len(top) == 1:
                    adjudicated = next(iter(top))
                    status = "ADJUDICATED_BY_HIGHEST_LEVEL"
                else:
                    adjudicated = None
                    status = "UNRESOLVED_SAME_LEVEL_CONFLICT"
            self._connection.execute(
                """UPDATE decision
                   SET human_decision=?, adjudicated_reviewer_decision=?, adjudication_status=?, manually_overridden=?
                   WHERE id=?""",
                (adjudicated, adjudicated, status, int(adjudicated is not None and feedback.override_recommendation is not None), decision_id),
            )
            for choice in feedback.glitch_decisions:
                if "id" in choice:
                    self._connection.execute(
                        "UPDATE artifact_flag SET human_status=? WHERE id=?",
                        (choice.get("status", "unreviewed"), choice["id"]),
                    )
            self._save_audit_event_locked(
                "REVIEWER_DECISION", sample_id=feedback.sample_id, analysis_id=feedback.analysis_id,
                payload={
                    "review_id": review_id, "reviewer_role": feedback.reviewer_role,
                    "reviewer_level": feedback.reviewer_level, "review_context": feedback.review_context.value,
                    "quality_rating": feedback.rating, "proposed": proposed,
                    "adjudicated": adjudicated, "adjudication_status": status,
                },
            )
            self._resolve_review_queue_locked(decision_id, review_id, adjudicated)
            return review_id

    def save_audit_event(
        self,
        event_type: str,
        sample_id: str | None = None,
        scan_id: str | None = None,
        analysis_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        with self._lock, self._connection:
            return self._save_audit_event_locked(event_type, sample_id, scan_id, analysis_id, payload or {})

    def _save_audit_event_locked(
        self,
        event_type: str,
        sample_id: str | None = None,
        scan_id: str | None = None,
        analysis_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        identifier = str(uuid.uuid4())
        self._connection.execute(
            "INSERT INTO audit_event VALUES (?,?,?,?,?,?,?)",
            (identifier, event_type, sample_id, scan_id, analysis_id, json.dumps(payload or {}, sort_keys=True), utc_now()),
        )
        return identifier

    def decision_for_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._one(
                """SELECT d.*, ca.sample_id, ca.scan_count, ca.physical_scan_count, ca.usable_scan_count, ca.analysis_context
                   FROM decision d JOIN cumulative_average ca ON ca.id=d.cumulative_average_id
                   WHERE d.cumulative_average_id=? ORDER BY d.created_at DESC LIMIT 1""",
                (analysis_id,),
            )
            return dict(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT p.*, COUNT(DISTINCT se.id) AS session_count
                   FROM project p LEFT JOIN session se ON se.project_id=p.id
                   GROUP BY p.id ORDER BY p.created_at DESC"""
            ).fetchall()
            return [dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._one("SELECT * FROM project WHERE id=?", (project_id,))
            return dict(row) if row else None

    def list_sessions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT se.*, p.name AS project_name, COUNT(DISTINCT s.id) AS sample_count
                 FROM session se JOIN project p ON p.id=se.project_id
                 LEFT JOIN sample s ON s.session_id=se.id"""
        params: tuple[Any, ...] = ()
        if project_id:
            sql += " WHERE se.project_id=?"
            params = (project_id,)
        sql += " GROUP BY se.id ORDER BY se.started_at DESC"
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, params).fetchall()]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._one(
                "SELECT se.*, p.name AS project_name FROM session se JOIN project p ON p.id=se.project_id WHERE se.id=?",
                (session_id,),
            )
            return dict(row) if row else None

    def list_samples(self, session_id: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT s.*, COUNT(DISTINCT sc.id) AS physical_scan_count,
                 SUM(CASE WHEN sc.disposition='USABLE' THEN 1 ELSE 0 END) AS usable_scan_count
                 FROM sample s LEFT JOIN scan sc ON sc.sample_id=s.id"""
        params: tuple[Any, ...] = ()
        if session_id:
            sql += " WHERE s.session_id=?"
            params = (session_id,)
        sql += " GROUP BY s.id ORDER BY s.created_at DESC"
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, params).fetchall()]

    def get_sample(self, sample_id_or_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._one(
                """SELECT s.*, COUNT(DISTINCT sc.id) AS physical_scan_count,
                   SUM(CASE WHEN sc.disposition='USABLE' THEN 1 ELSE 0 END) AS usable_scan_count
                   FROM sample s LEFT JOIN scan sc ON sc.sample_id=s.id
                   WHERE s.id=? OR s.sample_key=? OR s.logical_sample_key=? GROUP BY s.id LIMIT 1""",
                (sample_id_or_key, sample_id_or_key, sample_id_or_key),
            )
            return dict(row) if row else None

    def list_scans(self, sample_id: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT sc.*, s.sample_key, s.logical_sample_key FROM scan sc
                 JOIN sample s ON s.id=sc.sample_id"""
        params: tuple[Any, ...] = ()
        if sample_id:
            sql += " WHERE sc.sample_id=? OR s.sample_key=? OR s.logical_sample_key=?"
            params = (sample_id, sample_id, sample_id)
        sql += " ORDER BY sc.created_at DESC"
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, params).fetchall()]

    def list_decisions(self, sample_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = """SELECT d.*, ca.sample_id, ca.scan_count, ca.physical_scan_count, ca.usable_scan_count, ca.analysis_context,
                 s.sample_key, s.logical_sample_key
                 FROM decision d JOIN cumulative_average ca ON ca.id=d.cumulative_average_id
                 JOIN sample s ON s.id=ca.sample_id"""
        params: list[Any] = []
        if sample_id:
            sql += " WHERE ca.sample_id=? OR s.sample_key=? OR s.logical_sample_key=?"
            params.extend([sample_id, sample_id, sample_id])
        sql += " ORDER BY d.created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, tuple(params)).fetchall()]

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._one(
                """SELECT d.*, ca.sample_id, ca.scan_count, ca.physical_scan_count, ca.usable_scan_count, ca.analysis_context,
                   s.sample_key, s.logical_sample_key
                   FROM decision d JOIN cumulative_average ca ON ca.id=d.cumulative_average_id
                   JOIN sample s ON s.id=ca.sample_id WHERE d.id=?""",
                (decision_id,),
            )
            return dict(row) if row else None

    def review_queue(self, status: str | None = "PENDING", limit: int = 100) -> list[dict[str, Any]]:
        sql = """SELECT rq.*, s.sample_key, s.logical_sample_key, d.scientific_decision,
                 d.automatic_reason, d.decision_confidence
                 FROM review_queue rq JOIN sample s ON s.id=rq.sample_id
                 LEFT JOIN decision d ON d.id=rq.decision_id"""
        params: list[Any] = []
        if status:
            sql += " WHERE rq.status=?"
            params.append(status)
        sql += " ORDER BY rq.enqueued_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, tuple(params)).fetchall()]

    def table_counts(self) -> dict[str, int]:
        tables = [
            "schema_version", "project", "session", "experiment", "sample", "scan",
            "cumulative_average", "metrics", "decision", "artifact_flag", "human_review",
            "profile_version", "algorithm_version", "audit_event", "review_queue",
        ]
        with self._lock:
            return {table: int(self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}

    def recent_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        sql = """
        SELECT hr.*, d.automatic_recommendation, d.automatic_reason, d.scientific_decision,
               d.adjudicated_reviewer_decision, d.adjudication_status, ca.scan_count,
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

    def recent_audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM audit_event ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
