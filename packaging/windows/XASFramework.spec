from pathlib import Path

root = Path(SPECPATH).parents[1]
datas = [
    (str(root / "frontend" / "dist"), "frontend/dist"),
    (str(root / "config" / "app.windows.yaml"), "config"),
    (str(root / "config" / "beamline_calibration.example.yaml"), "config"),
    (str(root / "xas_beamtime" / "profiles"), "xas_beamtime/profiles"),
    (str(root / "reference_library"), "reference_library"),
]

a = Analysis(
    [str(root / "packaging" / "windows" / "xas_launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "watchdog.observers.winapi"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="XASFramework", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name="XASFramework")
