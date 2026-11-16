"""Restart the server (public release Phase 5a; a fresh process since BUG-22). Finishing setup in the browser, switching
the team in Settings, or an update from GitHub (FEAT-13) changes .env or the code; a restart rebuilds the app from them
without a new window or a new port.

How: a route calls request(). The server notices on its next tick (app/serving.py), shuts down the usual graceful way,
and run_server() returns RESTART. Then app/cli.py either serves anew in the same process, or, when a launcher waits
to start it again (the tray icon and start.ps1's window set KICKOFF_RELAUNCH=1), exits with RELAUNCH so the launcher
starts a fresh process. Only a fresh process loads changed Python code: the same process keeps the modules it already
imported, so a restart after `git pull` used to bring in the new pages but not the server's new code (BUG-22). The
launcher also runs `uv sync` first when an update changed the packages (data/update-sync.json), which the running
server cannot do itself because Windows locks the files it has loaded.

Plain module state: one server per process, and create_app() calls reset() so a fresh app never starts out restarting."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

log = logging.getLogger("kickoff.restart")

RESTART = 5  # run_server's return value when a restart was asked for
RELAUNCH = 8  # the process exit code that asks the launcher to start the server again (tools/tray.ps1, start.ps1)
LAUNCHER_ENV = "KICKOFF_RELAUNCH"

_reason: str | None = None


def request(reason: str) -> None:
    global _reason
    if _reason is None:
        log.info("Restart requested: %s", reason)
    _reason = reason


def requested() -> str | None:
    """Why a restart was asked for, or None."""
    return _reason


def reset() -> None:
    global _reason
    _reason = None


def relaunch_available(environ: Mapping[str, str] | None = None) -> bool:
    """True when a launcher starts the server again after it exits with RELAUNCH."""
    return (os.environ if environ is None else environ).get(LAUNCHER_ENV) == "1"
