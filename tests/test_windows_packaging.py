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
        windows_config = (root / "config" / "app.windows.yaml").read_text(encoding="utf-8")
        self.assertIn('--smoke-test', launcher)
        self.assertIn('"acquisition_control_enabled":false', launcher)
        self.assertIn('available_port(host)', launcher)
        self.assertIn('windows-latest', workflow)
        self.assertIn('XAS_Framework_v0.2_Setup.exe', workflow)
        self.assertIn('profile_id: P_K_XANES_v1.3', windows_config)

    def test_scipy_runtime_modules_and_native_failures_are_guarded(self) -> None:
        root = Path(__file__).parent.parent
        spec = (root / "packaging" / "windows" / "XASFramework.spec").read_text(encoding="utf-8")
        launcher = (root / "packaging" / "windows" / "xas_launcher.py").read_text(encoding="utf-8")
        build_script = (root / "packaging" / "windows" / "build_installer.ps1").read_text(encoding="utf-8")
        build_requirements = (root / "packaging" / "windows" / "requirements-build.txt").read_text(encoding="utf-8")

        self.assertIn('collect_submodules("scipy._external.array_api_compat")', spec)
        self.assertIn('ensure_stdio(root)', launcher)
        self.assertIn('runtime" / "launcher.log', launcher)
        self.assertIn('Start-Process', build_script)
        self.assertIn('-Wait -PassThru', build_script)
        self.assertIn('$Smoke.ExitCode', build_script)
        self.assertIn('scipy==1.18.1', build_requirements)
        self.assertIn('pywebview==6.2.1', build_requirements)
        self.assertIn('collect_submodules("webview")', spec)
        self.assertIn('"test_data/incoming"', spec)
        self.assertIn('webview.create_window', launcher)
        self.assertIn('create_file_dialog', launcher)
        self.assertIn('demo_source', launcher)
        self.assertIn('profile_id: P_K_XANES_v1.3', launcher)
        self.assertNotIn('webbrowser.open', launcher)


if __name__ == "__main__":
    unittest.main()
