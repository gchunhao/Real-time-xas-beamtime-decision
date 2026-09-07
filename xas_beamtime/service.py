from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .analysis import AnalysisEngine
from .calibration import BeamlineCalibration
from .completion import FileCompletionValidator
from .config import AppConfig
from .models import HumanFeedback, RuntimeLimits, Spectrum, canonical_scan_id
from .parser import ParseError, UniversalXASParser
from .references import ReferenceLibrary
from .registry import Profile, ProfileRegistry
from .storage import Storage
from .watcher import FolderWatcher


class BeamtimeService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.registry = ProfileRegistry()
        self.profile = self.registry.get(config.get("analysis.profile_id", "P_K_XANES_v1.2"))
        calibration = BeamlineCalibration.load(config.path("beamline.calibration_file", "./config/beamline_calibration.example.yaml"))
        self.parser = UniversalXASParser(calibration)
        self.analysis_engine = AnalysisEngine()
        self.storage = Storage(config.path("storage.database", "./runtime/xas_feedback.sqlite3"))
        self.references = ReferenceLibrary(config.path("references.root", "./reference_library"))
        self.limits = config.limits
        self.averaging_mode = config.get("analysis.averaging_mode", "equal")
        self.watch_folder = config.path("watch.folder", "./test_data/incoming")
        self.watcher: FolderWatcher | None = None
        self._lock = threading.RLock()
        self._scans: dict[str, dict[str, Spectrum]] = {}
        self._sample_db_ids: dict[str, str] = {}
        self._results: dict[str, list[Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._experiment_id: str | None = None

    def start(self) -> None:
        self.set_watch(self.watch_folder, self.limits, self.averaging_mode)

    def stop(self) -> None:
        if self.watcher:
            self.watcher.stop()
            self.watcher = None

    def set_watch(self, folder: str | Path, limits: RuntimeLimits, averaging_mode: str) -> None:
        with self._lock:
            if self.watcher:
                self.watcher.stop()
            self.watch_folder = Path(folder).resolve()
            self.limits = limits
            self.averaging_mode = averaging_mode
            self._experiment_id = self.storage.ensure_experiment(
                str(self.watch_folder),
                self.parser.calibration.beamline,
                {"limits": asdict(limits), "profile_id": self.profile.id, "mode": averaging_mode},
            )
            completion = FileCompletionValidator(
                stable_checks=int(self.config.get("watch.completion.stable_checks", 3)),
                stable_interval_seconds=float(self.config.get("watch.completion.stable_interval_seconds", 0.3)),
                minimum_bytes=int(self.config.get("watch.completion.minimum_bytes", 256)),
                require_final_newline=bool(self.config.get("watch.completion.require_final_newline", True)),
            )
            self.watcher = FolderWatcher(
                self.watch_folder,
                completion,
                self._on_complete,
                self.parser.extensions,
                recursive=bool(self.config.get("watch.recursive", False)),
                retry_seconds=float(self.config.get("watch.poll_seconds", 0.5)),
            )
            self.watcher.start(include_existing=True)
            self._event("watch_started", str(self.watch_folder))

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
            sample_key = spectrum.metadata.sample_id or path.stem
            scan_id = canonical_scan_id(spectrum.metadata)
            with self._lock:
                self._scans.setdefault(sample_key, {})[scan_id] = spectrum
                profile_version_id = self.storage.ensure_profile(matched)
                algorithm_version_id = self.storage.ensure_algorithm(
                    "xas_analysis", self.analysis_engine.algorithm_version, {"profile": matched.id}
                )
                if self._experiment_id is None:
                    raise RuntimeError("Experiment was not initialized")
                sample_db_id = self.storage.ensure_sample(self._experiment_id, spectrum, profile_version_id)
                self._sample_db_ids[sample_key] = sample_db_id
                self.storage.save_scan(sample_db_id, spectrum)
                results = self.analysis_engine.analyze_series(
                    self._scans[sample_key].values(), matched, self.limits, self.averaging_mode
                )
                self._results[sample_key] = results
                latest = results[-1]
                self.storage.save_analysis(sample_db_id, latest, profile_version_id, algorithm_version_id)
                self._event("scan_analyzed", path.name, sample_id=sample_key, recommendation=latest.recommendation.value)
        except Exception as exc:
            self._event("analysis_error", path.name, error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _fill_identity(spectrum: Spectrum, profile: Profile) -> None:
        identity = profile.data["identity"]
        spectrum.metadata.element = spectrum.metadata.element or str(identity["element"])
        spectrum.metadata.edge = spectrum.metadata.edge or str(identity["edge"])
        spectrum.metadata.scan_type = spectrum.metadata.scan_type or str(identity["scan_type"])

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
            self._results[sample_id] = results
            profile_version_id = self.storage.ensure_profile(self.profile)
            algorithm_version_id = self.storage.ensure_algorithm(
                "xas_analysis", self.analysis_engine.algorithm_version,
                {"profile": self.profile.id, "human_anchors": anchors or {}, "averaging_mode": averaging_mode},
            )
            self.storage.save_analysis(self._sample_db_ids[sample_id], latest, profile_version_id, algorithm_version_id)
            self._event("human_reanalysis", sample_id, averaging_mode=averaging_mode)
            return latest.to_dict()

    def save_review(self, payload: dict[str, Any]) -> str:
        feedback = HumanFeedback(
            analysis_id=payload["analysis_id"], sample_id=payload["sample_id"], profile_id=self.profile.id,
            rating=payload["rating"], override_recommendation=payload.get("override_recommendation"),
            averaging_mode=payload.get("averaging_mode", self.averaging_mode),
            included_scans=payload.get("included_scans", []), excluded_scans=payload.get("excluded_scans", []),
            glitch_decisions=payload.get("glitch_decisions", []),
            local_normalization_anchors=payload.get("local_normalization_anchors", {}),
            notes=payload.get("notes", ""),
            reviewer_role=payload.get("reviewer_role", "beamline_user"),
        )
        review_id = self.storage.save_review(feedback, payload.get("reviewer"))
        self._event("human_review_saved", feedback.sample_id, rating=feedback.rating)
        return review_id

    def state(self) -> dict[str, Any]:
        with self._lock:
            samples: list[dict[str, Any]] = []
            for sample_id, scans in self._scans.items():
                results = self._results.get(sample_id, [])
                ordered_scans = sorted(scans.values(), key=lambda s: s.metadata.scan_number or 0)
                samples.append({
                    "sample_id": sample_id,
                    "scan_count": len(scans),
                    "scans": [
                        {
                            "id": canonical_scan_id(scan.metadata),
                            "label": f"Scan {scan.metadata.scan_number or index + 1}",
                            "metadata": asdict(scan.metadata),
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
                })
            return {
                "framework_version": "0.2.0",
                "mode": "Real-time decision support",
                "acquisition_control_enabled": False,
                "watching": self.watcher is not None,
                "watch_folder": str(self.watch_folder),
                "limits": asdict(self.limits),
                "averaging_mode": self.averaging_mode,
                "profiles": self.registry.list(),
                "samples": samples,
                "events": list(reversed(self._events[-20:])),
                "database_counts": self.storage.table_counts(),
            }
