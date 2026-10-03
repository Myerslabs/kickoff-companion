"""Logging: a rotating file in logs/ plus the console.

- INFO for lifecycle, WARNING for skipped records and stale serves, ERROR for failures.
- The API key is redacted from every formatted line, including tracebacks.
- uvicorn's loggers propagate to the root logger so everything lands in one file.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import Settings

LOG_FILE_NAME = "app.log"
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
REDACTED = "[redacted]"

_state: dict[str, Any] = {"configured": False, "file": None, "level": None}


class RedactingFormatter(logging.Formatter):
    """Formats records normally, then blanks any secret that slipped into the text."""

    def __init__(self, fmt: str, datefmt: str, secrets: Iterable[str]):
        super().__init__(fmt, datefmt)
        self._secrets = [secret for secret in secrets if secret and len(secret) >= 8]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        return text


QUIET_ACCESS = ("/static/", "/media/", "/favicon")


class QuietAccessFilter(logging.Filter):
    """Drops access lines for page files and headshots (about half the log on a game night);
    API, stream and page requests stay. Errors on any path still show through uvicorn.error."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        args = record.args if isinstance(record.args, tuple) else ()
        path = str(args[2]) if len(args) >= 3 else record.getMessage()
        status = args[4] if len(args) >= 5 else None
        if isinstance(status, int) and status >= 400:
            return True
        return not any(marker in path for marker in QUIET_ACCESS)


class DroppedConnectionFilter(logging.Filter):
    """Windows' event loop logs a device that hangs up (the tablet sleeping, WinError 10054) as an
    ERROR with a traceback. That is not a fault of the app, and it hid real errors in the log on the
    game night of 2026-09-26, so it becomes one INFO line."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "asyncio" and record.exc_info and isinstance(record.exc_info[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            record.levelno, record.levelname = logging.INFO, "INFO"
            record.msg, record.args = "A device dropped its connection (%s)", (record.exc_info[1].__class__.__name__,)
            record.exc_info, record.exc_text = None, None
        return True


def configure_logging(settings: Settings, *, to_file: bool = True) -> Path | None:
    """Install the console handler and, when to_file is set, the rotating file handler.

    Calling it again with the same file and level is a no-op. Different settings
    replace the previous handlers. Returns the log file path, or None when not writing a file.
    """
    log_file = (settings.log_dir / LOG_FILE_NAME) if to_file else None
    if _state["configured"] and _state["file"] == log_file and _state["level"] == settings.log_level:
        return log_file

    shutdown_logging()
    formatter = RedactingFormatter(LOG_FORMAT, DATE_FORMAT, secrets=[settings.cfbd_api_key.get_secret_value()])
    root = logging.getLogger()
    root.setLevel(settings.log_level)

    quiet = QuietAccessFilter()
    dropped = DroppedConnectionFilter()
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.addFilter(quiet)
    console.addFilter(dropped)
    console._kickoff_handler = True  # type: ignore[attr-defined]
    root.addHandler(console)

    if log_file is not None:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(quiet)
        file_handler.addFilter(dropped)
        file_handler._kickoff_handler = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
    # kickoff.cfbd logs every CFBD call with its timing and size; httpx's own line repeated it.
    logging.getLogger("httpx").setLevel(logging.DEBUG if settings.log_level == "DEBUG" else logging.WARNING)

    _state.update(configured=True, file=log_file, level=settings.log_level)
    return log_file


def shutdown_logging() -> None:
    """Remove and close the handlers this module installed. Leaves other handlers alone."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_kickoff_handler", False):
            root.removeHandler(handler)
            handler.close()
    _state.update(configured=False, file=None, level=None)


def current_log_file() -> Path | None:
    return _state["file"]
