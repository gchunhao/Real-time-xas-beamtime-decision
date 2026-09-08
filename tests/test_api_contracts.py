from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from xas_beamtime.config import AppConfig


class ApiContractTests(unittest.TestCase):
    def test_v02_resource_routes_exist(self) -> None:
        import xas_beamtime.api as api_module

        with tempfile.TemporaryDirectory() as directory:
            project = Path(__file__).parent.parent
            source = Path(directory) / "config" / "app.yaml"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("{}", encoding="utf-8")
            api_module.CONFIG_PATH = source
            original_loader = api_module.load_config
            api_module.load_config = lambda _: AppConfig(
                source,
                {
                    "storage": {"database": str(Path(directory) / "api.sqlite3")},
                    "references": {"root": str(project / "reference_library")},
                    "beamline": {"calibration_file": str(project / "config" / "beamline_calibration.example.yaml")},
                    "analysis": {"profile_id": "P_K_XANES_v1.2", "averaging_mode": "equal"},
                },
            )
            try:
                app = api_module.create_app()
            finally:
                api_module.load_config = original_loader
            paths = {route.path for route in app.routes}
            expected = {
                "/api/projects",
                "/api/projects/{project_id}",
                "/api/sessions",
                "/api/sessions/{session_id}",
                "/api/samples",
                "/api/samples/{sample_id}",
                "/api/samples/{sample_id}/scans",
                "/api/samples/{sample_id}/decisions",
                "/api/scans",
                "/api/scans/{scan_id}",
                "/api/scans/{scan_id}/spectrum",
                "/api/scans/{scan_id}/disposition",
                "/api/decisions",
                "/api/decisions/{decision_id}",
                "/api/review-queue",
                "/api/reviews",
                "/api/audit",
                "/api/scheduler/state",
                "/api/workflow",
                "/api/import/offline",
                "/api/import/demo",
            }
            self.assertTrue(expected.issubset(paths))
            app.state.beamtime.close()


if __name__ == "__main__":
    unittest.main()
