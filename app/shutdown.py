"""The server is shutting down: a flag the open event streams read, so they end on their own
before uvicorn's graceful timeout cancels them (Phase 11: Ctrl+C with a Live sheet open used to
log a CancelledError traceback from the stream's disconnect listener).

The server calls begin() first thing in its shutdown; each stream's wake-up callback runs so a
stream waiting on its queue sees the flag at once. Plain module state: there is one server per
process, and create_app() calls reset() so a test's app never starts out shutting down."""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger("kickoff.shutdown")

_stopping = False
_wakers: list[Callable[[], None]] = []


def stopping() -> bool:
    return _stopping


def on_begin(waker: Callable[[], None]) -> None:
    """Run `waker` when the shutdown begins (it must not block and must not raise)."""
    _wakers.append(waker)


def begin() -> None:
    global _stopping
    if _stopping:
        return
    _stopping = True
    for waker in list(_wakers):
        try:
            waker()
        except Exception:  # noqa: BLE001 - one bad waker must not stop the shutdown; logged with its traceback
            log.exception("A shutdown wake-up callback failed")


def reset() -> None:
    global _stopping
    _stopping = False
    _wakers.clear()
