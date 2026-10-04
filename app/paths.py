r"""Where the program's files live (public release Phase 10: the packaged program).

Two roots. The bundle holds what ships with the program and is only read: `static/`, `.env.example`,
`app/radio_stations.json`. The install holds what this install writes: `.env`, `data/`, `logs/`.

Run from a checkout (`python -m app`) both are the project folder, as they always were. Run as the
packaged program (PyInstaller sets `sys.frozen` and unpacks the bundle into `sys._MEIPASS`, the
`_internal` folder beside the program), the bundle is that folder and the install is the user's own
app-data folder, so a new version of the program can replace the old folder and lose nothing:

    Windows   %LOCALAPPDATA%\Kickoff Companion
    macOS     ~/Library/Application Support/Kickoff Companion
    Linux     $XDG_DATA_HOME/kickoff-companion, else ~/.local/share/kickoff-companion

A file named `portable` beside the program keeps everything beside it instead (a USB stick, a game
folder). `DATA_DIR` and `LOG_DIR` in `.env` still move those two wherever they say.

`ROOTS` is resolved once at import from the running interpreter; `Roots.resolve()` takes every
input as an argument so tests can stand anywhere."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_FOLDER = Path(__file__).resolve().parent.parent  # the checkout this module lives in
PORTABLE_MARKER = "portable"  # a file by this name beside the program: files stay beside the program
APP_FOLDER_TITLE = "Kickoff Companion"  # the app-data folder on Windows and macOS
APP_FOLDER_SLUG = "kickoff-companion"  # and on Linux


def is_frozen(module: Any = sys) -> bool:
    """True when running as the packaged program (PyInstaller)."""
    return bool(getattr(module, "frozen", False)) and hasattr(module, "_MEIPASS")


def app_data_dir(system: str = sys.platform, environ: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    """The user's app-data folder for this app on `system`."""
    home = Path(home) if home is not None else Path.home()
    if system.startswith("win"):
        base = environ.get("LOCALAPPDATA", "").strip()
        return (Path(base) if base else home / "AppData" / "Local") / APP_FOLDER_TITLE
    if system == "darwin":
        return home / "Library" / "Application Support" / APP_FOLDER_TITLE
    base = environ.get("XDG_DATA_HOME", "").strip()
    return (Path(base) if base else home / ".local" / "share") / APP_FOLDER_SLUG


@dataclass(frozen=True)
class Roots:
    bundle: Path  # read only: static/, .env.example, app/radio_stations.json
    install: Path  # written: .env, data/, logs/
    program: Path | None  # the packaged program itself, None from a checkout
    portable: bool  # the packaged program keeps its files beside itself

    @property
    def packaged(self) -> bool:
        return self.program is not None

    @classmethod
    def resolve(
        cls,
        *,
        frozen: bool | None = None,
        bundle: str | Path | None = None,
        executable: str | Path | None = None,
        system: str = sys.platform,
        environ: Mapping[str, str] = os.environ,
        home: Path | None = None,
    ) -> Roots:
        """The roots for this run. Every argument defaults to the running interpreter's facts."""
        if frozen is None:
            frozen = is_frozen()
        if not frozen:
            return cls(bundle=PROJECT_FOLDER, install=PROJECT_FOLDER, program=None, portable=False)
        bundle_dir = Path(bundle if bundle is not None else getattr(sys, "_MEIPASS", PROJECT_FOLDER)).resolve()
        program = Path(executable if executable is not None else sys.executable).resolve()
        if (program.parent / PORTABLE_MARKER).exists():
            return cls(bundle=bundle_dir, install=program.parent, program=program, portable=True)
        return cls(bundle=bundle_dir, install=app_data_dir(system, environ, home), program=program, portable=False)

    def describe(self) -> dict[str, Any]:
        """For /api/health and /api/settings: where this install keeps its files."""
        return {
            "packaged": self.packaged,
            "portable": self.portable,
            "program": str(self.program) if self.program else None,
            "install": str(self.install),
            "bundle": str(self.bundle),
        }


ROOTS = Roots.resolve()
