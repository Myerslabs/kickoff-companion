"""Claude Code signed out (owner 2026-11-15, after his reports of 2026-11-11 and 2026-11-14: every Claude run failed with
"the tool exited with code 1" while Claude Code's own sign-in on the server computer had expired; his pick, "Yes, fix it
first").

Claude Code says why before it stops: into the run's log with `--output-format text` ("Failed to authenticate: OAuth
session expired and could not be refreshed", the words in logs/writing-*.log from 2026-11-10 to 2026-11-14), or as the
JSON result's text. A failed run's output is read here. A sign-in failure becomes SIGNED_OUT, the run's error in plain
words, and is remembered until a run gets through, so every answer of the server can say so (`meta.claudeSignedOut` in
app/api/envelope.py; the To do and the Data status card on the host's devices). Only a failed run's output is read: an
answer that merely mentions a sign-in never counts. The memory is this process's: a restart starts signed in, and the
next failed run says otherwise.

    SIGNED_OUT                 the words a run's error takes
    is_sign_in_failure(text)   the output names a sign-in failure (its last TAIL characters)
    failed(text)               a failed run's output: SIGNED_OUT, remembered, when it is a sign-in failure; else None
    from_log(path)             failed() on a run's log file; None when the file cannot be read
    succeeded()                a run got through: Claude Code is signed in
    signed_out_since()         the ISO time of the first sign-in failure since the last run that got through, or None
    reset()                    for the tests
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("kickoff.claude")

SIGNED_OUT = "Claude Code is signed out on the server computer (its sign-in expired). On that computer, open a terminal, run claude and type /login, then run this again."
TAIL = 4000  # a sign-in failure is the last thing Claude Code prints; a long answer's middle is never read

# Claude Code's own words when it cannot sign in: the OAuth session of 2026-11-10 to 2026-11-14, an expired token, a bad
# or missing API key, the API's authentication_error. Matched case-insensitively.
_SIGN_IN = re.compile(
    r"failed to authenticate|oauth (?:session|token) (?:has )?expired|invalid api key|please run /login|not logged in|authentication_error",
    re.IGNORECASE,
)

_since: datetime | None = None


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_sign_in_failure(text: object) -> bool:
    return isinstance(text, str) and bool(_SIGN_IN.search(text[-TAIL:]))


def failed(text: object) -> str | None:
    """A failed run's output. SIGNED_OUT when it names a sign-in failure, remembered until a run gets through; else None."""
    global _since
    if not is_sign_in_failure(text):
        return None
    if _since is None:
        _since = datetime.now(timezone.utc)
        line = next((ln.strip() for ln in reversed(str(text)[-TAIL:].splitlines()) if _SIGN_IN.search(ln)), "")
        log.warning("Claude Code is signed out on this computer: %s", line[:200])
    return SIGNED_OUT


def from_log(path: Path) -> str | None:
    """failed() on a run's log file (its tail). None when the file cannot be read, so the caller keeps its own words."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("The run's log %s could not be read for its reason: %s", path, exc)
        return None
    return failed(text)


def succeeded() -> None:
    """A run got through, so Claude Code is signed in."""
    global _since
    if _since is not None:
        log.info("Claude Code is signed in again (signed out since %s)", _iso(_since))
    _since = None


def signed_out_since() -> str | None:
    return _iso(_since) if _since is not None else None


def reset() -> None:
    global _since
    _since = None
