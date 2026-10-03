"""Restart the server in place (public release Phase 5a). Finishing setup in the browser, or switching
the team in Settings, changes .env, which every service reads when the app is built; a restart rebuilds
the app from the new .env without a new window, a new process or a new port.

How: a route calls request(). The server notices on its next tick (app/serving.py), shuts down the
usual graceful way, and run_server() returns RESTART; app/cli.py then reads the settings again and
serves anew in the same process. Plain module state: one server per process, and create_app() calls
reset() so a fresh app never starts out restarting."""

from __future__ import annotations

import logging

log = logging.getLogger("kickoff.restart")

RESTART = 5  # run_server's return value when a restart was asked for

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
