from __future__ import annotations

import unittest
from pathlib import Path


class WindowsPackagingTests(unittest.TestCase):
    def test_installer_creates_desktop_shortcut_and_uses_bundled_app(self) -> None:
        root = Path(__file__).parent.parent
        installer = (root / "packaging" / "windows" / "XAS_Framework_v0.2.iss").read_text(encoding="utf-8")
        self.assertIn('OutputBaseFilename=XAS_Framework_v0.2_Setup', installer)
        self.assertIn('Name: "desktopicon"', installer)
        self.assertIn('{autodesktop}\\XAS Framework', installer)
        self.assertIn('build\\dist\\XASFramework\\*', installer)

    def test_packaged_configuration_remains_simulation_only(self) -> None:
        root = Path(__file__).parent.parent
        launcher = (root / "packaging" / "windows" / "xas_launcher.py").read_text(encoding="utf-8")
        workflow = (root / ".github" / "workflows" / "windows-installer.yml").read_text(encoding="utf-8")
        self.assertIn('--smoke-test', launcher)
        self.assertIn('"acquisition_control_enabled":false', launcher)
        self.assertIn('available_port(host)', launcher)
        self.assertIn('windows-latest', workflow)
        self.assertIn('XAS_Framework_v0.2_Setup.exe', workflow)


if __name__ == "__main__":
    unittest.main()
