from __future__ import annotations

import tempfile
import unittest
import shutil
from contextlib import closing
from pathlib import Path

from xas_beamtime.config import AppConfig
from xas_beamtime.models import ScanDisposition
from xas_beamtime.models import RuntimeLimits
from xas_beamtime.service import BeamtimeService


class ServicePipelineTests(unittest.TestCase):
    def _service(self, directory: str, profile_id: str = "P_K_XANES_v1.2") -> BeamtimeService:
        project = Path(__file__).parent.parent
        source = Path(directory) / "config" / "app.yaml"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("{}", encoding="utf-8")
        config = AppConfig(
            source,
            {
                "analysis": {"profile_id": profile_id, "averaging_mode": "equal"},
                "storage": {"database": str(Path(directory) / "runtime.sqlite3")},
                "references": {"root": str(project / "reference_library")},
                "beamline": {"calibration_file": str(project / "config" / "beamline_calibration.example.yaml")},
                "limits": {"maximum_scans": 8, "maximum_time_seconds": 900},
                "project": {"name": "Test Project"},
            },
        )
        service = BeamtimeService(config)
        service._experiment_id = service.storage.ensure_experiment(str(Path(directory) / "watch"), None, {})
        service._project_id, service._session_id = service.storage.ensure_project_session(
            str(Path(directory) / "watch"), None, {}, service._experiment_id, project_name="Test Project"
        )
        return service

    def test_scan_disposition_drives_review_queue_and_usable_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory, closing(self._service(directory)) as service:
            scan_path = Path(__file__).parent.parent / "test_data" / "incoming" / "apatite_scan-001.dat"
            service._on_complete(scan_path)
            scans = service.scans("apatite")
            self.assertEqual(len(scans), 1)
            scan_id = scans[0]["id"]
            self.assertEqual(scans[0]["disposition"], "USABLE")

            payload = service.set_scan_disposition(scan_id, ScanDisposition.PENDING_REVIEW, "manual check")
            latest = payload["latest_decision"]
            self.assertEqual(latest["recommendation"], "REVIEW_REQUIRED")
            self.assertEqual(latest["usable_scan_count"], 0)
            self.assertEqual(latest["physical_scan_count"], 1)
            self.assertIn("apatite", service.scheduler.held_samples)
            queue = service.storage.review_queue("PENDING")
            self.assertEqual(len(queue), 1)
            self.assertEqual(queue[0]["logical_sample_key"], "apatite")

            payload = service.set_scan_disposition(scan_id, ScanDisposition.USABLE, "reviewed usable")
            self.assertNotEqual(payload["latest_decision"]["recommendation"], "REVIEW_REQUIRED")
            self.assertNotIn("apatite", service.scheduler.held_samples)
            self.assertEqual(service.storage.review_queue("PENDING"), [])
            self.assertEqual(len(service.storage.review_queue("SUPERSEDED")), 1)

    def test_reviewer_override_resolves_review_queue_but_quality_rating_alone_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory, closing(self._service(directory)) as service:
            scan_path = Path(__file__).parent.parent / "test_data" / "incoming" / "apatite_scan-001.dat"
            service._on_complete(scan_path)
            scan_id = service.scans("apatite")[0]["id"]
            result = service.set_scan_disposition(scan_id, ScanDisposition.PENDING_REVIEW, "manual check")
            analysis_id = result["latest_decision"]["analysis_id"]

            service.save_review(
                {
                    "analysis_id": analysis_id,
                    "sample_id": "apatite",
                    "rating": "QL-ready",
                    "averaging_mode": "equal",
                    "included_scans": [],
                    "excluded_scans": [],
                    "reviewer_role": "User",
                    "reviewer_level": 1,
                    "review_context": "LIVE",
                }
            )
            self.assertEqual(len(service.storage.review_queue("PENDING")), 1)
            decision = service.storage.decision_for_analysis(analysis_id)
            self.assertEqual(decision["adjudication_status"], "QUALITY_RATING_ONLY")

            service.save_review(
                {
                    "analysis_id": analysis_id,
                    "sample_id": "apatite",
                    "rating": "QL-ready",
                    "override_recommendation": "CONTINUE",
                    "averaging_mode": "equal",
                    "included_scans": [],
                    "excluded_scans": [],
                    "reviewer_role": "Beamline Scientist",
                    "reviewer_level": 2,
                    "review_context": "LIVE",
                }
            )
            self.assertEqual(service.storage.review_queue("PENDING"), [])
            self.assertEqual(len(service.storage.review_queue("RESOLVED")), 1)
            self.assertNotIn("apatite", service.scheduler.held_samples)

    def test_project_session_sample_resources_are_populated(self) -> None:
        with tempfile.TemporaryDirectory() as directory, closing(self._service(directory)) as service:
            scan_path = Path(__file__).parent.parent / "test_data" / "incoming" / "apatite_scan-001.dat"
            service._on_complete(scan_path)
            self.assertEqual(len(service.projects()), 1)
            self.assertEqual(len(service.sessions()), 1)
            samples = service.samples(service._session_id)
            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0]["logical_sample_key"], "apatite")
            self.assertEqual(samples[0]["physical_scan_count"], 1)

    def test_workflow_projection_is_read_only_simulation_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory, closing(self._service(directory)) as service:
            scan_path = Path(__file__).parent.parent / "test_data" / "incoming" / "apatite_scan-001.dat"
            service._on_complete(scan_path)
            before = service.storage.table_counts()
            projection = service.workflow_projection()
            after = service.storage.table_counts()

            self.assertTrue(projection["simulation_only"])
            self.assertFalse(projection["scheduler"]["acquisition_control_enabled"])
            self.assertEqual(projection["queue_counts"]["all"], 1)
            self.assertEqual(
                [stage["key"] for stage in projection["stages"]],
                ["detected", "parsed", "qc", "adp", "decision", "scheduler"],
            )
            self.assertEqual(before, after)

    def test_offline_import_processes_folder_without_starting_watcher(self) -> None:
        with tempfile.TemporaryDirectory() as directory, closing(self._service(directory)) as service:
            source = Path(__file__).parent.parent / "test_data" / "incoming"
            import_root = Path(directory) / "offline-data"
            import_root.mkdir()
            for name in ("apatite_scan-001.dat", "apatite_scan-002.dat"):
                shutil.copy2(source / name, import_root / name)

            report = service.import_offline(
                [import_root], RuntimeLimits(maximum_scans=8, maximum_time_seconds=900), "equal"
            )

            self.assertEqual(report["discovered_files"], 2)
            self.assertEqual(report["imported_files"], 2)
            self.assertEqual(report["failed_files"], 0)
            self.assertEqual(service.state()["mode"], "OFFLINE")
            self.assertFalse(service.state()["watching"])
            self.assertEqual(service.state()["watch_folder"], str(import_root.resolve()))
            self.assertEqual(service.state()["samples"][0]["physical_scan_count"], 2)

    def test_v13_offline_import_exposes_single_scan_arrays_on_one_grid(self) -> None:
        with tempfile.TemporaryDirectory() as directory, closing(
            self._service(directory, "P_K_XANES_v1.3")
        ) as service:
            source = Path(__file__).parent.parent / "test_data" / "incoming"
            report = service.import_offline(
                [source], RuntimeLimits(maximum_scans=8, maximum_time_seconds=900), "equal"
            )

            self.assertEqual(report["imported_files"], 6)
            state = service.state()
            self.assertEqual(state["samples"][0]["latest"]["profile_id"], "P_K_XANES_v1.3")
            self.assertEqual(len(service.storage.review_queue("PENDING")), 1)
            self.assertEqual(len(service.storage.review_queue("SUPERSEDED")), 5)
            for scan in state["samples"][0]["scans"]:
                self.assertEqual(len(scan["energy"]), len(scan["raw"]))
                self.assertEqual(len(scan["energy"]), len(scan["normalized"]))
                spectrum = service.scan_spectrum(scan["id"])
                self.assertEqual(len(spectrum["energy"]), len(spectrum["raw"]))
                self.assertEqual(len(spectrum["energy"]), len(spectrum["normalized"]))
            sample_id = service.samples()[0]["id"]
            persisted = service.sample_spectrum(sample_id)
            self.assertEqual(len(persisted["energy"]), len(persisted["raw"]))
            self.assertEqual(len(persisted["energy"]), len(persisted["normalized"]))
            service._scans.clear()
            self.assertEqual(service.sample_spectrum(sample_id), persisted)


if __name__ == "__main__":
    unittest.main()
