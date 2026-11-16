"""When this start began (post-freeze Wave 1, owner 2026-10-25: log the time to the first data, numbers for the startup-wait
test). The clock starts when the process imports the app, or again at an in-place restart (app/serving.py run_server), so
"ready after 9.4 s" in the log and in /api/health counts the whole wait a viewer sees, Python's own start aside.

BUG-17, ENH-18 (owner 2026-10-27, "Open the browser only after the first data", a cap of 30 s): the start says READY and
opens the browser once the opening pages have their data, never while it is still held back.

    mark()             start the clock again (an in-place restart); the opening pages are not ready again
    generation()       counts the starts of this process, so a wait from the start before a restart steps aside
    seconds()          seconds since the clock started, to a tenth
    pages_ready()      the opening pages have their data (main.py _startup_warm), or there are none to warm (setup mode)
    wait_pages(t)      wait up to t seconds for that; True when it came
    opened(browser)    the start said READY (app/serving.py when_ready), and opened the browser or not
    open_seconds()     seconds from the start to READY, None before it
    browser_opened()   whether this start opened the browser
"""

from __future__ import annotations

import threading
import time

_started = time.monotonic()
_pages = threading.Event()
_open_seconds: float | None = None
_browser = False
_generation = 0


def mark() -> None:
    global _started, _open_seconds, _browser, _generation
    _started = time.monotonic()
    _generation += 1
    _pages.clear()
    _open_seconds = None
    _browser = False


def generation() -> int:
    return _generation


def seconds() -> float:
    return round(time.monotonic() - _started, 1)


def pages_ready() -> None:
    _pages.set()


def wait_pages(timeout: float) -> bool:
    return _pages.wait(timeout)


def opened(*, browser: bool) -> float:
    global _open_seconds, _browser
    _open_seconds = seconds()
    _browser = browser
    return _open_seconds


def open_seconds() -> float | None:
    return _open_seconds


def browser_opened() -> bool:
    return _browser
