"""The packaged program's entry point (public release Phase 10): the same as `python -m app`, plus a pause
before the window closes when a double-clicked start stops with a message, so the message can be read.

PyInstaller builds this file (tools/package/kickoff.spec, run by tools/package/build.py)."""

from __future__ import annotations

import sys

from app.cli import main, pause_before_closing

if __name__ == "__main__":
    code = main()
    pause_before_closing(code)
    sys.exit(code)
