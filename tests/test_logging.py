"""Rotating file logging with the API key redacted from every line."""

from __future__ import annotations

import logging
import logging.handlers

from app.logging_setup import BACKUP_COUNT, MAX_BYTES, REDACTED, configure_logging, shutdown_logging
from tests.conftest import TEST_KEY


def _file_handler() -> logging.handlers.RotatingFileHandler:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            return handler
    raise AssertionError("no rotating file handler installed")


def test_log_file_is_created_and_rotates(settings):
    log_file = configure_logging(settings)
    try:
        assert log_file is not None
        logging.getLogger("kickoff.test").info("hello from the test")
        assert log_file.exists()
        assert "hello from the test" in log_file.read_text(encoding="utf-8")
        handler = _file_handler()
        assert handler.maxBytes == MAX_BYTES == 5 * 1024 * 1024
        assert handler.backupCount == BACKUP_COUNT == 5
    finally:
        shutdown_logging()


def test_key_is_redacted_from_messages_and_tracebacks(settings):
    log_file = configure_logging(settings)
    try:
        logger = logging.getLogger("kickoff.test")
        logger.warning("key is %s here", TEST_KEY)
        try:
            raise RuntimeError(f"upstream said {TEST_KEY}")
        except RuntimeError:
            logger.exception("call failed")
        content = log_file.read_text(encoding="utf-8")
        assert TEST_KEY not in content
        assert content.count(REDACTED) >= 2
        assert "RuntimeError" in content
    finally:
        shutdown_logging()


def test_reconfigure_is_idempotent(settings):
    try:
        configure_logging(settings)
        count = len(logging.getLogger().handlers)
        configure_logging(settings)
        assert len(logging.getLogger().handlers) == count
    finally:
        shutdown_logging()


def test_console_only_mode_writes_no_file(settings):
    try:
        assert configure_logging(settings, to_file=False) is None
        logging.getLogger("kickoff.test").info("console only")
        assert not (settings.log_dir / "app.log").exists()
    finally:
        shutdown_logging()


def test_uvicorn_loggers_propagate(settings):
    try:
        configure_logging(settings)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            assert logging.getLogger(name).propagate is True
            assert logging.getLogger(name).handlers == []
    finally:
        shutdown_logging()
