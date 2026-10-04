# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the packaged program (public release Phase 10). tools/package/build.py runs it after writing
# the staging files it bundles into tools/package/out/: the demo league's source hash (app/demo/upstream.py reads it
# when the generator sources are not on disk), the program's icon and, on Windows, the version resource.
#
# One folder, a console program, no UPX and no one-file build: both trip antivirus heuristics, and a one-file
# build unpacks itself on every start.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

HERE = Path(SPECPATH).resolve()  # noqa: F821 - SPECPATH is set by PyInstaller
ROOT = HERE.parents[1]
OUT = HERE / "out"
WINDOWS = sys.platform.startswith("win")

datas = [
    (str(ROOT / "static"), "static"),  # the whole front end, fonts and icons included
    (str(ROOT / ".env.example"), "."),  # the template the setup page writes .env from
    (str(ROOT / "app" / "radio_stations.json"), "app"),  # read beside app/services/stations.py's parent
    (str(OUT / "demo-sources.sha1"), "app/demo"),  # the league cache's key, since no .py file ships
]
datas += collect_data_files("tzdata")  # the time zones, with no system database to lean on

a = Analysis(
    [str(HERE / "kickoff.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["app.main"],  # uvicorn imports the app factory by its dotted name
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = OUT / "kickoff.ico"
version_file = OUT / "version_info.txt"
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KickoffCompanion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon) if WINDOWS and icon.is_file() else None,
    version=str(version_file) if WINDOWS and version_file.is_file() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KickoffCompanion",
)
