from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parents[1]
scipy_array_api_hiddenimports = collect_submodules("scipy._external.array_api_compat")
webview_hiddenimports = collect_submodules("webview")
datas = [
    (str(root / "frontend" / "dist"), "frontend/dist"),
    (str(root / "config" / "app.windows.yaml"), "config"),
    (str(root / "config" / "beamline_calibration.example.yaml"), "config"),
    (str(root / "xas_beamtime" / "profiles"), "xas_beamtime/profiles"),
    (str(root / "reference_library"), "reference_library"),
    (str(root / "test_data" / "incoming"), "test_data/incoming"),
]

a = Analysis(
    [str(root / "packaging" / "windows" / "xas_launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "watchdog.observers.winapi",
    ] + scipy_array_api_hiddenimports + webview_hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="XASFramework", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name="XASFramework")
