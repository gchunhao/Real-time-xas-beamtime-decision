from __future__ import annotations

import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path


APP_FOLDER = "XAS Beamtime Decision"


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def user_data_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_FOLDER


def prepare_user_config() -> Path:
    source = bundle_root()
    target = user_data_root()
    (target / "config").mkdir(parents=True, exist_ok=True)
    (target / "incoming").mkdir(exist_ok=True)
    (target / "runtime").mkdir(exist_ok=True)

    config_path = target / "config" / "app.yaml"
    if not config_path.exists():
        shutil.copy2(source / "config" / "desktop.yaml", config_path)

    calibration_path = target / "config" / "beamline_calibration.yaml"
    if not calibration_path.exists():
        shutil.copy2(source / "config" / "beamline_calibration.example.yaml", calibration_path)

    references = target / "reference_library"
    if not references.exists():
        shutil.copytree(source / "reference_library", references)
    return config_path


def available_port(preferred: int = 8765) -> int:
    for port in range(preferred, preferred + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            try:
                candidate.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No local port is available for the XAS application.")


def main() -> None:
    config_path = prepare_user_config()
    os.environ["XAS_CONFIG"] = str(config_path)
    port = available_port()
    import uvicorn
    from .api import app
    import webview

    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, name="xas-local-server", daemon=True)
    server_thread.start()
    for _ in range(80):
        try:
            urllib.request.urlopen(f"{url}/api/state", timeout=.3).close()
            break
        except OSError:
            time.sleep(.1)

    webview.create_window(
        "XAS Decision Workbench",
        url,
        width=1500,
        height=920,
        min_size=(1050, 700),
    )
    webview.start()
    server.should_exit = True
    server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
