from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH).parent
package_datas = collect_data_files("xas_beamtime")

a = Analysis(
    [str(project_root / "packaging" / "desktop_entry.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=package_datas + [
        (str(project_root / "frontend" / "dist"), "frontend/dist"),
        (str(project_root / "config"), "config"),
        (str(project_root / "reference_library"), "reference_library"),
    ],
    hiddenimports=["tkinter", "tkinter.filedialog"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="XASBeamtimeDecision",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="XASBeamtimeDecision",
)
