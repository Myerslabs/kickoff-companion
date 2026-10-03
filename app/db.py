"""One SQLite file for everything that persists: the response cache, the quota ledger, and
later the live event store and the archive.

WAL mode, one connection guarded by a lock. Async code calls into it with asyncio.to_thread
so a slow disk never stalls the event loop.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("kickoff.db")

DB_FILE = "kickoff.db"


def database_path(data_dir: Path) -> Path:
    """The cache database in `data_dir`."""
    return data_dir / DB_FILE

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key         TEXT PRIMARY KEY,
    endpoint    TEXT NOT NULL,
    params      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    expires_at  TEXT,
    size_bytes  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS cache_endpoint ON cache(endpoint);

CREATE TABLE IF NOT EXISTS quota_calls (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    at        TEXT NOT NULL,
    month     TEXT NOT NULL,
    endpoint  TEXT NOT NULL,
    status    INTEGER,
    ok        INTEGER NOT NULL,
    live      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS quota_calls_month ON quota_calls(month, at);

CREATE TABLE IF NOT EXISTS quota_reconcile (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    at            TEXT NOT NULL,
    month         TEXT NOT NULL,
    remaining     INTEGER,
    budget        INTEGER,
    tier_level    INTEGER,
    tier_name     TEXT,
    raw           TEXT
);

-- Phase 14: publication schedules (app/cfbd/publish.py)
CREATE TABLE IF NOT EXISTS publications (
    key         TEXT PRIMARY KEY,
    endpoint    TEXT NOT NULL,
    params      TEXT NOT NULL,
    schedule    TEXT NOT NULL,
    hash        TEXT NOT NULL,
    changed_at  TEXT NOT NULL,
    checked_at  TEXT NOT NULL,
    asked_at    TEXT NOT NULL,
    checks      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS publication_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint  TEXT NOT NULL,
    key       TEXT NOT NULL,
    schedule  TEXT NOT NULL,
    slot      TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    checks    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS publication_log_endpoint ON publication_log(endpoint, changed_at);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""


class Database:
    """A lazily opened SQLite connection shared by every store in the app."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    @property
    def in_memory(self) -> bool:
        return str(self.path) == ":memory:"

    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                if not self.in_memory:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
                conn.row_factory = sqlite3.Row
                if not self.in_memory:
                    conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.executescript(SCHEMA)
                self._conn = conn
            return self._conn

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        with self._lock:
            yield conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        with self._lock:
            conn.execute("BEGIN")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    def size_bytes(self) -> int:
        if self.in_memory:
            return 0
        total = 0
        for suffix in ("", "-wal", "-shm"):
            candidate = self.path.with_name(self.path.name + suffix)
            try:
                total += candidate.stat().st_size
            except OSError:
                pass
        return total

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
