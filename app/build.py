"""The build the server is serving, so an open tablet can tell when it runs old code (Phase 12).

build_id() is a short hash of this process's start and every static file's path, size and
modification time. It changes on a server restart and whenever a file under static/ changes on
disk (the running server serves static files straight from disk, so a merged fix reaches a
reloaded page without a restart). It is recomputed at most every STAMP_SECONDS; walking the static
folder costs about a millisecond. Every API envelope and the stream's hello carry it; app.js
remembers the first one it sees and offers a reload when it changes."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time

from app.config import STATIC_DIR

log = logging.getLogger("kickoff.build")

STAMP_SECONDS = 30.0
STARTED = f"{os.getpid()}-{time.time_ns()}"

_lock = threading.Lock()
_cached: tuple[float, str] | None = None


def _static_stamp() -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    try:
        for root, dirs, files in os.walk(STATIC_DIR):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue  # a file replaced mid-walk: the next stamp sees the new one
                digest.update(f"{os.path.relpath(path, STATIC_DIR)}|{stat.st_size}|{stat.st_mtime_ns};".encode())
    except OSError as exc:
        log.warning("Could not read the static folder for the build id: %s", exc)
    return digest.hexdigest()


def build_id() -> str:
    global _cached
    now = time.monotonic()
    with _lock:
        if _cached is not None and now - _cached[0] < STAMP_SECONDS:
            return _cached[1]
    value = hashlib.sha1(f"{STARTED}|{_static_stamp()}".encode(), usedforsecurity=False).hexdigest()[:12]
    with _lock:
        _cached = (now, value)
    return value


def reset() -> None:
    """Forget the cached id (tests that change files under static/)."""
    global _cached
    with _lock:
        _cached = None
