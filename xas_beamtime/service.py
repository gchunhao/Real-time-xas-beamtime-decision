from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .analysis import AnalysisEngine
from .calibration import BeamlineCalibration
from .completion import FileCompletionValidator
from .config import AppConfig
from .decision import DecisionEngine, DecisionOutcome
from .disposition import ScanDispositionPolicy
from .models import (
    AnalysisContext,
    AnalysisResult,
    HumanFeedback,
    ReviewContext,
    RuntimeLimits,
    ScanDisposition,
    ScientificDecision,
    Spectrum,
    canonical_scan_id,
    utc_now,
)
from .parser import ParseError, UniversalXASParser
from .references import ReferenceLibrary
from .registry import Profile, ProfileRegistry
from .scheduler import SchedulerSimulationAdapter
from .storage import Storage


class BeamtimeService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.registry = ProfileRegistry()
        self.profile = self.registry.get(config.get("analysis.profile_id", "P_K_XANES_v1.2"))
        calibration = BeamlineCalibration.load(
            config.path("beamline.calibration_file", "./config/beamline_calibration.example.yaml")
        )
        self.parser = UniversalXASParser(calibration)
        self.analysis_engine = AnalysisEngine()
        self.disposition_policy = ScanDispositionPolicy()
        self.storage = Storage(config.path("storage.database", "./runtime/xas_feedback.sqlite3"))
        self.references = ReferenceLibrary(config.path("references.root", "./reference_library"))
        self.scheduler = SchedulerSimulationAdapter()
        self.limits = config.limits
        self.averaging_mode = config.get("analysis.averaging_mode", "equal")
        self.watch_folder = config.path("watch.folder", "./test_data/incoming")
        self.watcher: Any | None = None
        self._lock = threading.RLock()
        self._scans: dict[str, dict[str, Spectrum]] = {}
        self._sample_db_ids: dict[str, str] = {}
        self._results: dict[str, list[AnalysisResult]] = {}
        self._review_results: dict[str, list[AnalysisResult]] = {}
        self._events: list[dict[str, Any]] = []
        self._experiment_id: str | None = None
        self._project_id: str | None = None
        self._session_id: str | None = None

    def start(self) -> None:
        self.set_watch(self.watch_folder, self.limits, self.averaging_mode)

    def stop(self) -> None:
        if self.watcher:
            self.watcher.stop()
            self.watcher = None

    def close(self) -> None:
        self.stop()
        self.storage.close()

    def set_watch(self, folder: str | Path, limits: RuntimeLimits, averaging_mode: str) -> None:
        with self._lock:
            if self.watcher:
                self.watcher.stop()
            self.watch_folder = Path(folder).resolve()
            self.limits = limits
            self.averaging_mode = averaging_mode
            settings = {"limits": asdict(limits), "profile_id": self.profile.id, "mode": averaging_mode}
            self._experiment_id = self.storage.ensure_experiment(
                str(self.watch_folder), self.parser.calibration.beamline, settings
            )
            self._project_id, self._session_id = self.storage.ensure_project_session(
                str(self.watch_folder),
                self.parser.calibration.beamline,
                settings,
                self._experiment_id,
                project_name=str(self.config.get("project.name", "XAS Project")),
                session_name=self.config.get("session.name"),
            )
            completion = FileCompletionValidator(
                stable_checks=int(self.config.get("watch.completion.stable_checks", 3)),
                stable_interval_seconds=float(self.config.get("watch.completion.stable_interval_seconds", 0.3)),
                minimum_bytes=int(self.config.get("watch.completion.minimum_bytes", 256)),
                require_final_newline=bool(self.config.get("watch.completion.require_final_newline", True)),
            )
            try:
                from .watcher import FolderWatcher
            except ModuleNotFoundError as exc:
                if exc.name == "watchdog":
                    raise RuntimeError(
                        "Folder watching requires the 'watchdog' package. Install project requirements before live mode."
                    ) from exc
                raise
            self.watcher = FolderWatcher(
                self.watch_folder,
                completion,
                self._on_complete,
                self.parser.extensions,
                recursive=bool(self.config.get("watch.recursive", False)),
                retry_seconds=float(self.config.get("watch.poll_seconds", 0.5)),
            )
            self.watcher.start(include_existing=True)
            self._event("watch_started", str(self.watch_folder), project_id=self._project_id, session_id=self._session_id)

    def _event(self, kind: str, message: str, **details: Any) -> None:
        from .models import utc_now

        self._events.append({"time": utc_now(), "kind": kind, "message": message, **details})
        self._events = self._events[-100:]

    def _on_complete(self, path: Path) -> None:
        try:
            spectrum = self.parser.parse(path)
            self._fill_identity(spectrum, self.profile)
            matched = self.registry.match(spectrum.metadata.element, spectrum.metadata.edge, spectrum.metadata.scan_type)
            if matched is None:
                raise ParseError(
                    f"No profile for {spectrum.metadata.element}_{spectrum.metadata.edge}_{spectrum.metadata.scan_type}"
                )
            self._prepare_logical_identity(spectrum, path)
            sample_key = spectrum.metadata.logical_sample_key or spectrum.metadata.sample_id or path.stem
            scan_id = canonical_scan_id(spectrum.metadata)

            with self._lock:
                self._scans.setdefault(sample_key, {})[scan_id] = spectrum
                profile_version_id = self.storage.ensure_profile(matched)
                if self._experiment_id is None:
                    raise RuntimeError("Experiment was not initialized")
                sample_db_id = self.storage.ensure_sample(
                    self._experiment_id, spectrum, profile_version_id, session_id=self._session_id
                )
                self._sample_db_ids[sample_key] = sample_db_id
                self.storage.save_scan(sample_db_id, spectrum)

                assessment = self.disposition_policy.assess_new_scan(spectrum)
                if assessment.disposition is not ScanDisposition.USABLE:
                    self.storage.set_scan_disposition(scan_id, assessment.disposition, assessment.reason)
                    self.storage.save_audit_event(
                        "SCAN_DISPOSITION_AUTO",
                        sample_id=sample_db_id,
                        scan_id=scan_id,
                        payload={
                            "disposition": assessment.disposition.value,
                            "reason": assessment.reason,
                            "reason_code": assessment.reason_code,
                        },
                    )

                latest = self._recompute_production(sample_key, matched, trigger_scan_id=scan_id)
                self._event(
                    "scan_analyzed",
                    path.name,
                    sample_id=sample_key,
                    scan_id=scan_id,
                    disposition=self.storage.get_scan_record(scan_id)["disposition"],
                    scientific_decision=latest.recommendation.value,
                    sample_action=latest.sample_action.value,
                    scheduler_action=latest.scheduler_action.value,
                    effective_scheduler_action=latest.effective_scheduler_action.value,
                )
        except Exception as exc:
            self._event("analysis_error", path.name, error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _fill_identity(spectrum: Spectrum, profile: Profile) -> None:
        identity = profile.data["identity"]
        spectrum.metadata.element = spectrum.metadata.element or str(identity["element"])
        spectrum.metadata.edge = spectrum.metadata.edge or str(identity["edge"])
        spectrum.metadata.scan_type = spectrum.metadata.scan_type or str(identity["scan_type"])

    @staticmethod
    def _prepare_logical_identity(spectrum: Spectrum, path: Path) -> None:
        sample_key = spectrum.metadata.logical_sample_key or spectrum.metadata.sample_id or path.stem
        spectrum.metadata.logical_sample_key = sample_key
        spectrum.metadata.base_sample_name = spectrum.metadata.base_sample_name or spectrum.metadata.sample_id or sample_key
        spectrum.metadata.grouping_method = spectrum.metadata.grouping_method or (
            "metadata_sample_id" if spectrum.metadata.sample_id else "filename_fallback"
        )
        spectrum.metadata.grouping_confidence = (
            spectrum.metadata.grouping_confidence
            if spectrum.metadata.grouping_confidence is not None
            else (1.0 if spectrum.metadata.sample_id else 0.5)
        )
        spectrum.metadata.requires_grouping_confirmation = bool(
            spectrum.metadata.requires_grouping_confirmation or spectrum.metadata.grouping_confidence < 0.75
        )

    @staticmethod
    def _apply_outcome(result: AnalysisResult, outcome: DecisionOutcome) -> None:
        result.recommendation = outcome.recommendation
        result.recommendation_reason = outcome.reason
        result.predicted_n_quant = outcome.predicted_n_quant
        result.remaining_scan_budget = outcome.remaining_scan_budget
        result.remaining_time_seconds = outcome.remaining_time_seconds
        result.sample_action = outcome.sample_action
        result.scheduler_action = outcome.scheduler_action
        result.auto_execution_eligibility = outcome.auto_execution_eligibility
        result.resource_constraint = outcome.resource_constraint
        result.effective_scheduler_action = outcome.effective_scheduler_action
        result.decision_reason_codes = outcome.reason_codes
        result.suggested_reviewer_action = outcome.suggested_reviewer_action
        result.decision_confidence = outcome.confidence
        result.uncertainty.update(
            {"alpha_global": outcome.alpha_global, "alpha_recent": outcome.alpha_recent, "alpha_pred": outcome.alpha_pred}
        )

    def _stamp_calibration_provenance(self, result: AnalysisResult) -> None:
        calibration = self.parser.calibration
        raw = calibration.raw or {}
        calibration_file = self.config.path(
            "beamline.calibration_file",
            "./config/beamline_calibration.example.yaml",
        )
        result.provenance.update(
            {
                "beamline": calibration.beamline,
                "energy_calibration_configured": calibration.beamline is not None,
                "energy_calibration_applied": bool(
                    abs(float(calibration.energy_offset_ev)) > 1e-12
                    or abs(float(calibration.energy_scale) - 1.0) > 1e-12
                ),
                "energy_offset_ev": float(calibration.energy_offset_ev),
                "energy_scale": float(calibration.energy_scale),
                "calibration_file": str(calibration_file),
                "calibration_schema_version": raw.get("schema_version"),
                "calibration_standard": raw.get("calibration_standard"),
                "calibration_timestamp": raw.get("calibration_timestamp"),
                "calibration_notes": raw.get("notes"),
            }
        )

    def _recompute_production(
        self, sample_key: str, profile: Profile | None = None, trigger_scan_id: str | None = None
    ) -> AnalysisResult:
        profile = profile or self.profile
        scans = self._scans.get(sample_key)
        if not scans:
            raise KeyError(sample_key)
        sample_db_id = self._sample_db_ids[sample_key]
        disposition_map = self.storage.scan_dispositions(sample_db_id)
        ordered = sorted(
            scans.values(),
            key=lambda s: (s.metadata.scan_number is None, s.metadata.scan_number or 0, s.metadata.source_path),
        )
        usable = [s for s in ordered if disposition_map.get(canonical_scan_id(s.metadata)) is ScanDisposition.USABLE]
        blocking = [
            (canonical_scan_id(s.metadata), disposition_map.get(canonical_scan_id(s.metadata)))
            for s in ordered
            if self.disposition_policy.blocks_automatic_sample_decision(
                disposition_map.get(canonical_scan_id(s.metadata), ScanDisposition.USABLE)
            )
        ]

        if usable:
            results = self.analysis_engine.analyze_series(usable, profile, self.limits, self.averaging_mode)
            latest = results[-1]
        else:
            diagnostic = scans.get(trigger_scan_id) if trigger_scan_id else None
            diagnostic = diagnostic or ordered[-1]
            results = self.analysis_engine.analyze_series([diagnostic], profile, self.limits, self.averaging_mode)
            latest = results[-1]
            latest.provenance["diagnostic_only_nonusable_scan"] = True

        for result in results:
            result.physical_scan_count = len(ordered)
            result.usable_scan_count = len(usable)
            result.analysis_context = AnalysisContext.PRODUCTION
            self._stamp_calibration_provenance(result)

        reason_codes: list[str] = []
        if blocking:
            for scan_id, disposition in blocking:
                reason_codes.append(f"SCAN_{disposition.value}:{scan_id}")
            outcome = DecisionEngine(profile).review_required(
                "Automatic sample decision blocked by unresolved scan disposition",
                ["UNRESOLVED_SCAN_DISPOSITION", *reason_codes],
                suggested_reviewer_action="MANUAL_ASSESSMENT",
            )
            self._apply_outcome(latest, outcome)
        elif not usable:
            outcome = DecisionEngine(profile).review_required(
                "No scan is currently eligible for the production usable-scan series",
                ["NO_USABLE_SCANS"],
                suggested_reviewer_action="MANUAL_ASSESSMENT",
            )
            self._apply_outcome(latest, outcome)

        profile_version_id = self.storage.ensure_profile(profile)
        algorithm_version_id = self.storage.ensure_algorithm(
            "xas_analysis", self.analysis_engine.algorithm_version, {"profile": profile.id, "context": "PRODUCTION"}
        )
        self._results[sample_key] = results
        self.storage.save_analysis(sample_db_id, latest, profile_version_id, algorithm_version_id)
        execution = self.scheduler.apply(latest)
        self.storage.save_audit_event(
            "SIMULATED_EXECUTION", sample_id=sample_db_id, analysis_id=latest.analysis_id, payload=execution.to_dict()
        )
        return latest

    def set_scan_disposition(
        self,
        scan_id: str,
        disposition: ScanDisposition,
        reason: str | None = None,
        replacement_for_scan_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            record = self.storage.get_scan_record(scan_id)
            if record is None:
                raise KeyError(scan_id)
            self.storage.set_scan_disposition(scan_id, disposition, reason, replacement_for_scan_id)
            self.storage.save_audit_event(
                "SCAN_DISPOSITION_CHANGED",
                sample_id=str(record["sample_id"]),
                scan_id=scan_id,
                payload={
                    "disposition": disposition.value,
                    "reason": reason,
                    "replacement_for_scan_id": replacement_for_scan_id,
                },
            )
            sample_key = str(record["logical_sample_key"] or record["sample_key"])
            latest = self._recompute_production(sample_key, trigger_scan_id=scan_id)
            return {"scan": self.storage.get_scan_record(scan_id), "latest_decision": latest.to_dict(include_arrays=False)}

    def reanalyze(
        self,
        sample_id: str,
        averaging_mode: str,
        included_scan_ids: set[str] | None,
        anchors: dict[str, list[float]] | None,
    ) -> dict[str, Any]:
        with self._lock:
            scans = self._scans.get(sample_id)
            if not scans:
                raise KeyError(sample_id)
            results = self.analysis_engine.analyze_series(
                scans.values(), self.profile, self.limits, averaging_mode, included_scan_ids, anchors
            )
            latest = results[-1]
            latest.analysis_context = AnalysisContext.REVIEW
            latest.physical_scan_count = len(scans)
            latest.usable_scan_count = len(results[-1].scan_ids)
            for result in results:
                self._stamp_calibration_provenance(result)
            self._review_results[sample_id] = results
            profile_version_id = self.storage.ensure_profile(self.profile)
            algorithm_version_id = self.storage.ensure_algorithm(
                "xas_analysis",
                self.analysis_engine.algorithm_version,
                {"profile": self.profile.id, "human_anchors": anchors or {}, "averaging_mode": averaging_mode, "context": "REVIEW"},
            )
            self.storage.save_analysis(self._sample_db_ids[sample_id], latest, profile_version_id, algorithm_version_id)
            self._event("human_reanalysis", sample_id, averaging_mode=averaging_mode, production_state_unchanged=True)
            payload = latest.to_dict()
            payload["production_state_unchanged"] = True
            return payload

    def save_review(self, payload: dict[str, Any]) -> str:
        override = payload.get("override_recommendation")
        if override is not None:
            ScientificDecision(override)
        feedback = HumanFeedback(
            analysis_id=payload["analysis_id"],
            sample_id=payload["sample_id"],
            profile_id=self.profile.id,
            rating=payload["rating"],
            override_recommendation=override,
            averaging_mode=payload.get("averaging_mode", self.averaging_mode),
            included_scans=payload.get("included_scans", []),
            excluded_scans=payload.get("excluded_scans", []),
            glitch_decisions=payload.get("glitch_decisions", []),
            local_normalization_anchors=payload.get("local_normalization_anchors", {}),
            notes=payload.get("notes", ""),
            reviewer_role=payload.get("reviewer_role", "User"),
            reviewer_level=int(payload.get("reviewer_level", 0)),
            review_context=ReviewContext(payload.get("review_context", "LIVE")),
        )
        review_id = self.storage.save_review(feedback, payload.get("reviewer"))
        decision = self.storage.decision_for_analysis(feedback.analysis_id)
        if decision:
            self.scheduler.resolve_review(feedback.sample_id, decision.get("adjudicated_reviewer_decision"))
        self._event(
            "human_review_saved",
            feedback.sample_id,
            rating=feedback.rating,
            override_recommendation=override,
            review_context=feedback.review_context.value,
        )
        return review_id

    def state(self) -> dict[str, Any]:
        with self._lock:
            samples: list[dict[str, Any]] = []
            for sample_id, scans in self._scans.items():
                results = self._results.get(sample_id, [])
                ordered_scans = sorted(scans.values(), key=lambda s: s.metadata.scan_number or 0)
                db_sample_id = self._sample_db_ids.get(sample_id)
                dispositions = self.storage.scan_dispositions(db_sample_id) if db_sample_id else {}
                samples.append(
                    {
                        "sample_id": sample_id,
                        "physical_scan_count": len(scans),
                        "usable_scan_count": sum(1 for d in dispositions.values() if d is ScanDisposition.USABLE),
                        "scan_count": len(scans),
                        "scans": [
                            {
                                "id": canonical_scan_id(scan.metadata),
                                "label": f"Scan {scan.metadata.scan_number or index + 1}",
                                "metadata": asdict(scan.metadata),
                                "disposition": dispositions.get(
                                    canonical_scan_id(scan.metadata), ScanDisposition.USABLE
                                ).value,
                                "energy": scan.energy.tolist(),
                                "raw": scan.mu.tolist(),
                                "normalized": self.analysis_engine.analyze_series(
                                    [scan], self.profile, self.limits, "equal"
                                )[0].normalized_average.tolist(),
                            }
                            for index, scan in enumerate(ordered_scans)
                        ],
                        "history": [result.to_dict(include_arrays=False) for result in results],
                        "averages": [result.to_dict() for result in results],
                        "latest": results[-1].to_dict() if results else None,
                    }
                )
            return {
                "framework_version": "0.2.0",
                "mode": "Real-time decision support",
                "acquisition_control_enabled": False,
                "scheduler_mode": "SIMULATION",
                "scheduler": self.scheduler.state(),
                "watching": self.watcher is not None,
                "watch_folder": str(self.watch_folder),
                "project_id": self._project_id,
                "session_id": self._session_id,
                "limits": asdict(self.limits),
                "averaging_mode": self.averaging_mode,
                "profiles": self.registry.list(),
                "samples": samples,
                "review_queue_count": len(self.storage.review_queue("PENDING", 1000)),
                "events": list(reversed(self._events[-20:])),
                "database_counts": self.storage.table_counts(),
            }

    def workflow_projection(self) -> dict[str, Any]:
        """Return a read-only operator projection for the v0.2 workspace.

        This projection intentionally derives presentation state from persisted
        resources and the simulation scheduler. It does not participate in QC,
        prediction, or scientific decision making.
        """
        samples = self.storage.list_samples(self._session_id)
        decisions = self.storage.list_decisions(limit=1000)
        pending = self.storage.review_queue("PENDING", 1000)
        pending_sample_ids = {item["sample_id"] for item in pending}
        latest_by_sample: dict[str, dict[str, Any]] = {}
        for decision in decisions:
            latest_by_sample.setdefault(str(decision["sample_id"]), decision)

        current_key = next(reversed(self._scans), None) if self._scans else None
        current_db_id = self._sample_db_ids.get(current_key) if current_key else None
        queue: list[dict[str, Any]] = []
        for sample in samples:
            sample_id = str(sample["id"])
            latest = latest_by_sample.get(sample_id)
            scientific = latest.get("scientific_decision") if latest else None
            if sample_id in pending_sample_ids:
                status = "REVIEW"
            elif sample_id == current_db_id and self.watcher is not None and scientific in {None, "CONTINUE", "REACQUIRE"}:
                status = "RUNNING"
            elif latest:
                status = "COMPLETED"
            else:
                status = "QUEUED"
            queue.append(
                {
                    "sample_id": sample_id,
                    "logical_sample_key": sample.get("logical_sample_key") or sample.get("sample_key"),
                    "element": sample.get("element"),
                    "edge": sample.get("edge"),
                    "scan_type": sample.get("scan_type"),
                    "status": status,
                    "automatic_decision": scientific,
                    "sample_action": latest.get("sample_action") if latest else None,
                    "scheduler_action": latest.get("effective_scheduler_action") if latest else None,
                    "physical_scan_count": int(sample.get("physical_scan_count") or 0),
                    "usable_scan_count": int(sample.get("usable_scan_count") or 0),
                    "updated_at": latest.get("created_at") if latest else sample.get("created_at"),
                }
            )

        current = next((item for item in queue if item["sample_id"] == current_db_id), queue[0] if queue else None)
        has_result = bool(current and current.get("automatic_decision"))
        stages = [
            {"key": "detected", "label": "New Scan Detected", "state": "complete" if has_result else "waiting"},
            {"key": "parsed", "label": "Parse & Process", "state": "complete" if has_result else "waiting"},
            {"key": "qc", "label": "QC Analysis", "state": "complete" if has_result else "waiting"},
            {"key": "adp", "label": "ADP Shadow", "state": "complete" if has_result else "waiting"},
            {"key": "decision", "label": "Automated Decision", "state": "active" if has_result else "waiting"},
            {"key": "scheduler", "label": "Scheduler Action", "state": "simulated" if has_result else "waiting"},
        ]
        return {
            "generated_at": utc_now(),
            "run_status": "AUTO RUNNING" if self.watcher is not None else "PAUSED",
            "simulation_only": True,
            "current_sample_id": current["sample_id"] if current else None,
            "current_sample_key": current["logical_sample_key"] if current else None,
            "queue": queue,
            "queue_counts": {
                "all": len(queue),
                "running": sum(item["status"] == "RUNNING" for item in queue),
                "queued": sum(item["status"] == "QUEUED" for item in queue),
                "review": sum(item["status"] == "REVIEW" for item in queue),
                "completed": sum(item["status"] == "COMPLETED" for item in queue),
            },
            "review_queue_count": len(pending),
            "stages": stages,
            "sample_action": current.get("sample_action") if current else None,
            "scheduler_action": current.get("scheduler_action") if current else None,
            "scheduler": self.scheduler.state(),
        }

    def projects(self) -> list[dict[str, Any]]:
        return self.storage.list_projects()

    def sessions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        return self.storage.list_sessions(project_id)

    def samples(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self.storage.list_samples(session_id)

    def sample(self, sample_id: str) -> dict[str, Any]:
        row = self.storage.get_sample(sample_id)
        if row is None:
            raise KeyError(sample_id)
        row["latest_decision"] = next(iter(self.storage.list_decisions(sample_id, limit=1)), None)
        row["review_queue"] = [item for item in self.storage.review_queue(None, 1000) if item["sample_id"] == row["id"]]
        return row

    def scans(self, sample_id: str | None = None) -> list[dict[str, Any]]:
        return self.storage.list_scans(sample_id)

    def scan(self, scan_id: str) -> dict[str, Any]:
        row = self.storage.get_scan_record(scan_id)
        if row is None:
            raise KeyError(scan_id)
        return row

    def scan_spectrum(self, scan_id: str) -> dict[str, Any]:
        for sample_scans in self._scans.values():
            if scan_id in sample_scans:
                scan = sample_scans[scan_id]
                normalized = self.analysis_engine.analyze_series([scan], self.profile, self.limits, "equal")[0]
                return {
                    "scan_id": scan_id,
                    "energy": scan.energy.tolist(),
                    "raw": scan.mu.tolist(),
                    "normalized": normalized.normalized_average.tolist(),
                }
        raise KeyError(scan_id)
