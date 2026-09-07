from __future__ import annotations

import argparse
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


APP_NAME = "XAS Framework"
_stdio_log = None


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def user_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / APP_NAME


def prepare_user_files() -> Path:
    root = user_root()
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "runtime").mkdir(parents=True, exist_ok=True)
    (root / "reference_library").mkdir(parents=True, exist_ok=True)
    (root / "test_data" / "incoming").mkdir(parents=True, exist_ok=True)
    source = bundle_root()
    copies = {
        source / "config" / "app.windows.yaml": root / "config" / "app.yaml",
        source / "config" / "beamline_calibration.example.yaml": root / "config" / "beamline_calibration.example.yaml",
        source / "reference_library" / "references.example.yaml": root / "reference_library" / "references.example.yaml",
        source / "reference_library" / "README.md": root / "reference_library" / "README.md",
    }
    for src, dst in copies.items():
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
    os.environ["XAS_CONFIG"] = str(root / "config" / "app.yaml")
    return root


def ensure_stdio(root: Path) -> None:
    """Give windowed PyInstaller builds streams for Uvicorn logging."""
    global _stdio_log
    if sys.stdout is not None and sys.stderr is not None:
        return
    _stdio_log = (root / "runtime" / "launcher.log").open(
        "a", encoding="utf-8", buffering=1
    )
    if sys.stdout is None:
        sys.stdout = _stdio_log
    if sys.stderr is None:
        sys.stderr = _stdio_log


def wait_until_ready(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Local service did not become ready: {url}")


def available_port(host: str, preferred: int = 8765) -> int:
    for port in range(preferred, preferred + 10):
        with socket.socket() as candidate:
            try:
                candidate.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("No local port is available for XAS Framework.")


def run(smoke_test: bool = False) -> int:
    root = prepare_user_files()
    ensure_stdio(root)
    from xas_beamtime.api import app
    import uvicorn

    host = "127.0.0.1"
    port = available_port(host)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    if smoke_test:
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        wait_until_ready(f"http://{host}:{port}/api/workflow")
        with urllib.request.urlopen(f"http://{host}:{port}/api/scheduler/state") as response:
            if b'"acquisition_control_enabled":false' not in response.read():
                raise RuntimeError("Safety smoke check failed")
        server.should_exit = True
        thread.join(5)
        return 0
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    server.run()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    raise SystemExit(run(parser.parse_args().smoke_test))
