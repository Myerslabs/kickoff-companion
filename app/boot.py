"""When this start began (post-freeze Wave 1, owner 2026-10-25: log the time to the first data, numbers for the startup-wait
test). The clock starts when the process imports the app, or again at an in-place restart (app/serving.py run_server), so
"ready after 9.4 s" in the log and in /api/health counts the whole wait a viewer sees, Python's own start aside.

    mark()        start the clock again (an in-place restart)
    seconds()     seconds since the clock started, to a tenth
"""

from __future__ import annotations

import time

_started = time.monotonic()


def mark() -> None:
    global _started
    _started = time.monotonic()


def seconds() -> float:
    return round(time.monotonic() - _started, 1)
