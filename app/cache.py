"""The response cache: raw CFBD payloads in SQLite with a TTL per kind of data.

Rules from docs/02-ARCHITECTURE.md, "Cache policy":
- Every kind of data has a TTL. Finished-game data is permanent once it has settled: an empty
  answer is kept ten minutes while a just-played game settles (the client's settle_until, kickoff
  + 24 h) and six hours otherwise, and non-empty answers written while the game settles are kept
  an hour. Live plays are never cached.
- Stale-while-error: an expired entry is kept so it can be served, labelled stale with its
  age, when the upstream is down. Nothing is deleted just because it expired.
- Single-flight is the client's job (app/cfbd/client.py); this module is plain storage.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlencode

from app.db import Database


class DataKind(str, Enum):
    TEAMS = "teams"  # teams, logos, colors
    ROSTER = "roster"
    RECRUITING = "recruiting"
    REFERENCE = "reference"  # calendar, stat categories, play types
    HISTORY = "history"  # series history, past seasons
    SCHEDULE = "schedule"  # schedule, records, rankings
    SEASON_STATS = "season_stats"  # season team and player stats, ratings
    LINES = "lines"
    WEATHER = "weather"
    FINISHED_GAME = "finished_game"  # drives, plays, box scores of a final game
    SCOREBOARD = "scoreboard"
    TICKER = "ticker"  # the week's games while the ticker is active: five minutes, never scaled
    LIVE = "live"  # live plays: never cached
    INFO = "info"  # quota check: never cached


NO_CACHE = timedelta(0)
THURSDAY = 3
SATURDAY = 5
FINISHED_GAME_EMPTY_TTL = timedelta(minutes=10)  # a just-played game CFBD has not posted yet: ask again soon
FINISHED_GAME_EMPTY_LEAN_TTL = timedelta(hours=1)  # the same on the free profile (freeze wave F2): six asks a night, not 144
FINISHED_GAME_EMPTY_SETTLED_TTL = timedelta(hours=6)  # an older game CFBD never filled: a few asks a day, not 144
FINISHED_GAME_SETTLING_TTL = timedelta(hours=1)  # CFBD still corrects a game in the day after it
FINISHED_GAME_SETTLING_LEAN_TTL = timedelta(hours=6)  # the free profile takes CFBD's corrections a few times, not hourly


def ttl_for(kind: DataKind, local_now: datetime, *, game_day: bool = False) -> timedelta | None:
    """How long a payload of this kind stays fresh. None means permanent, NO_CACHE means never store."""
    weekday = local_now.weekday()
    weekend = weekday >= SATURDAY
    if kind in (DataKind.TEAMS, DataKind.ROSTER, DataKind.RECRUITING, DataKind.REFERENCE):
        return timedelta(days=7)
    if kind is DataKind.HISTORY:
        return timedelta(days=30)
    if kind is DataKind.SCHEDULE:  # our game on a Friday or a bowl weekday is game day too (Phase 12)
        # Phase 14: Thursday and Friday carry other teams' games (an hour); Sunday to Wednesday nothing
        # is played, only kickoff times get announced (twelve hours).
        if weekday == SATURDAY or game_day:
            return timedelta(minutes=15)
        return timedelta(hours=1) if weekday in (THURSDAY, THURSDAY + 1) else timedelta(hours=12)
    if kind is DataKind.SEASON_STATS:
        return timedelta(hours=1) if weekend or game_day else timedelta(hours=6)
    if kind in (DataKind.LINES, DataKind.WEATHER):
        return timedelta(minutes=30) if game_day else timedelta(hours=3)
    if kind is DataKind.FINISHED_GAME:
        return None  # the settled default; the client applies finished_game_ttl for empty and settling answers
    if kind is DataKind.SCOREBOARD:
        return timedelta(seconds=15)
    if kind is DataKind.TICKER:
        return timedelta(minutes=5)
    return NO_CACHE


def is_empty_payload(payload: Any) -> bool:
    """CFBD's 'nothing posted yet' answers: null, [], {} (and an empty string, to be safe)."""
    if payload is None:
        return True
    return isinstance(payload, (list, dict, str)) and len(payload) == 0


def finished_game_empty_ttl(now: datetime, settle_until: datetime | None, *, lean: bool = False) -> timedelta:
    """How long an empty finished-game answer is kept: ten minutes while the latest game settles (an hour on
    the free profile), six hours otherwise, so an old game CFBD never filled does not cost a call every ten minutes."""
    if settle_until is not None and now < settle_until:
        return FINISHED_GAME_EMPTY_LEAN_TTL if lean else FINISHED_GAME_EMPTY_TTL
    return FINISHED_GAME_EMPTY_SETTLED_TTL


def finished_game_ttl(payload: Any, now: datetime, settle_until: datetime | None, *, lean: bool = False) -> timedelta | None:
    """The lifetime of a finished-game answer; None means permanent.

    Empty answers are never permanent (see finished_game_empty_ttl). While `now` is before
    `settle_until` (UTC-aware, set by the live engine to kickoff + 24 h of the latest game) answers
    are kept an hour so corrections land (six hours on the free profile).
    """
    if is_empty_payload(payload):
        return finished_game_empty_ttl(now, settle_until, lean=lean)
    if settle_until is not None and now < settle_until:
        return FINISHED_GAME_SETTLING_LEAN_TTL if lean else FINISHED_GAME_SETTLING_TTL
    return None


def canonical_params(params: dict[str, Any] | None) -> dict[str, str]:
    """Parameters as strings, sorted, with None values dropped and booleans lower-cased."""
    out: dict[str, str] = {}
    for key in sorted(params or {}):
        value = (params or {})[key]
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        out[str(key)] = str(value)
    return out


def cache_key(endpoint: str, params: dict[str, Any] | None) -> str:
    query = urlencode(canonical_params(params))
    return f"{endpoint}?{query}" if query else endpoint


@dataclass(frozen=True)
class CacheEntry:
    key: str
    endpoint: str
    params: dict[str, str]
    payload: Any
    fetched_at: datetime
    expires_at: datetime | None
    size_bytes: int

    def is_fresh(self, now: datetime) -> bool:
        return self.expires_at is None or self.expires_at > now

    def age_seconds(self, now: datetime) -> float:
        return max((now - self.fetched_at).total_seconds(), 0.0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


MEMORY_BUDGET = 96 * 1024 * 1024  # freeze wave F7: the payloads read lately stay decoded (every page read decoded multi-MB JSON from SQLite: the program 90 decodes, 46 ms)


class Cache:
    """The SQLite cache with the entries read lately kept decoded in memory (this process is the only writer, so a put,
    delete or clear is the only way an entry changes; the least recently used leave when the budget is spent)."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._mem: OrderedDict[str, CacheEntry] = OrderedDict()
        self._mem_bytes = 0
        self._lock = threading.Lock()

    def _remember(self, entry: CacheEntry) -> None:
        with self._lock:
            old = self._mem.pop(entry.key, None)
            if old is not None:
                self._mem_bytes -= old.size_bytes
            self._mem[entry.key] = entry
            self._mem_bytes += entry.size_bytes
            while self._mem_bytes > MEMORY_BUDGET and self._mem:
                _key, gone = self._mem.popitem(last=False)
                self._mem_bytes -= gone.size_bytes

    def _forget(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._mem.clear()
                self._mem_bytes = 0
                return
            gone = self._mem.pop(key, None)
            if gone is not None:
                self._mem_bytes -= gone.size_bytes

    def memory_stats(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._mem), "bytes": self._mem_bytes}

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            kept = self._mem.get(key)
            if kept is not None:
                self._mem.move_to_end(key)
                return kept
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload"])
            params = json.loads(row["params"])
            fetched_at = _parse(row["fetched_at"])
        except (ValueError, TypeError):
            return None
        if fetched_at is None:
            return None
        entry = CacheEntry(
            key=row["key"],
            endpoint=row["endpoint"],
            params=params if isinstance(params, dict) else {},
            payload=payload,
            fetched_at=fetched_at,
            expires_at=_parse(row["expires_at"]),
            size_bytes=int(row["size_bytes"] or 0),
        )
        self._remember(entry)
        return entry

    def put(
        self,
        key: str,
        endpoint: str,
        params: dict[str, Any] | None,
        payload: Any,
        *,
        fetched_at: datetime,
        ttl: timedelta | None,
    ) -> CacheEntry:
        """Store a payload. ttl None keeps it forever. NO_CACHE stores nothing."""
        canonical = canonical_params(params)
        body = json.dumps(payload, separators=(",", ":"))
        expires_at = None if ttl is None else fetched_at + ttl
        entry = CacheEntry(
            key=key,
            endpoint=endpoint,
            params=canonical,
            payload=payload,
            fetched_at=fetched_at,
            expires_at=expires_at,
            size_bytes=len(body.encode("utf-8")),
        )
        if ttl == NO_CACHE:
            return entry
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, endpoint, params, payload, fetched_at, expires_at, size_bytes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    endpoint,
                    json.dumps(canonical, separators=(",", ":")),
                    body,
                    _iso(fetched_at),
                    _iso(expires_at) if expires_at else None,
                    entry.size_bytes,
                ),
            )
        self._remember(entry)
        return entry

    def delete(self, key: str) -> None:
        self._forget(key)
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))

    def clear(self) -> int:
        self._forget()
        with self.db.transaction() as conn:
            return conn.execute("DELETE FROM cache").rowcount

    def stats(self, now: datetime) -> dict[str, Any]:
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS entries, COALESCE(SUM(size_bytes), 0) AS size_bytes,"
                " MIN(fetched_at) AS oldest, MAX(fetched_at) AS newest FROM cache"
            ).fetchone()
            fresh = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE expires_at IS NULL OR expires_at > ?", (_iso(now),)
            ).fetchone()[0]
        return {
            "entries": int(row["entries"]),
            "fresh": int(fresh),
            "size_bytes": int(row["size_bytes"]),
            "oldest": row["oldest"],
            "newest": row["newest"],
            "db_bytes": self.db.size_bytes(),
        }
