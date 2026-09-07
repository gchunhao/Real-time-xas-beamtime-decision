from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xas_beamtime.desktop import available_port, prepare_user_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DesktopBootstrapTests(unittest.TestCase):
    def test_user_configuration_is_initialized_outside_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            user_root = Path(temporary) / "user-data"
            with (
                patch("xas_beamtime.desktop.bundle_root", return_value=PROJECT_ROOT),
                patch("xas_beamtime.desktop.user_data_root", return_value=user_root),
            ):
                config_path = prepare_user_config()
                self.assertEqual(config_path, user_root / "config" / "app.yaml")
                self.assertTrue(config_path.is_file())
                self.assertTrue((user_root / "config" / "beamline_calibration.yaml").is_file())
                self.assertTrue((user_root / "reference_library").is_dir())
                self.assertTrue((user_root / "incoming").is_dir())

    def test_desktop_selects_an_available_local_port(self) -> None:
        selected = available_port()
        self.assertGreaterEqual(selected, 8765)
        self.assertLess(selected, 8775)


if __name__ == "__main__":
    unittest.main()
