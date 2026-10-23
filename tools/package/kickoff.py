"""The packaged program's entry point (public release Phase 10): the same as `python -m app`, plus a pause
before the window closes when a double-clicked start stops with a message, so the message can be read. A crash
counts: its traceback is printed and logged, then the same pause.

The tray on by default (owner 2026-10-23): on Windows a plain double-click hands the program to the tray icon (the
bundled tools\tray.ps1, which starts it again hidden) and the console closes, unless Tray mode is off in Settings.

PyInstaller builds this file (tools/package/kickoff.spec, run by tools/package/build.py)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.cli import main, pause_before_closing
from app.paths import ROOTS, Roots
from app.services.prefs import PrefsStore, tray_wanted


def tray_handoff(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] = os.environ,
    roots: Roots = ROOTS,
    system: str = "windows" if sys.platform == "win32" else sys.platform,
    popen: Callable[..., Any] = subprocess.Popen,
) -> bool:
    """Start the tray icon in this program's place and say True, or say False and let the program start in its window: not
    on Windows, Tray mode off, started by the tray itself (KICKOFF_NO_PAUSE), started with options (--check, --login, the
    demo...), or the tray script missing. A tray that will not start leaves the window, never nothing."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args or environ.get("KICKOFF_NO_PAUSE") or roots.program is None:
        return False
    tray = roots.bundle / "tools" / "tray.ps1"
    if not tray.is_file() or not tray_wanted(PrefsStore(roots.install / "data").prefs.trayMode, system):
        return False
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(tray), "-Program", str(roots.program), "-Root", str(roots.install)]
    try:
        popen(command, cwd=str(roots.install) if Path(roots.install).is_dir() else None, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except OSError as exc:
        print(f"The tray icon did not start ({exc}); starting in this window instead.", file=sys.stderr)
        return False
    return True


def run() -> int:
    """main(), with an uncaught error turned into exit code 1 so the pause still comes."""
    try:
        return main()
    except SystemExit as exc:  # argparse (a bad option, --help) or sys.exit with a message
        if exc.code is None or isinstance(exc.code, int):
            return exc.code or 0
        print(exc.code, file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc()
        logging.getLogger("app").critical("The program stopped on an unexpected error", exc_info=True)
        return 1


if __name__ == "__main__":
    if tray_handoff():
        sys.exit(0)  # the tray icon runs the program from here on
    code = run()
    if not os.environ.get("KICKOFF_NO_PAUSE"):  # Phase 16 wave 3: the tray starts the program in a hidden window
        pause_before_closing(code)
    sys.exit(code)
