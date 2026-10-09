"""The packaged program's entry point (public release Phase 10): the same as `python -m app`, plus a pause
before the window closes when a double-clicked start stops with a message, so the message can be read. A crash
counts: its traceback is printed and logged, then the same pause.

PyInstaller builds this file (tools/package/kickoff.spec, run by tools/package/build.py)."""

from __future__ import annotations

import logging
import os
import sys
import traceback

from app.cli import main, pause_before_closing


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
    code = run()
    if not os.environ.get("KICKOFF_NO_PAUSE"):  # Phase 16 wave 3: the tray starts the program in a hidden window
        pause_before_closing(code)
    sys.exit(code)
