"""The event store: every live event appended in receipt order with the server time it arrived.
Dedupe and corrections live here: an event whose id and data were already stored is dropped,
one whose data changed is appended again with a higher version, so a later reader sees the
correction in order. The delay buffer is a query: released(cutoff) returns events received on
or before the cutoff, so a 45-second delay is `now - 45 s` and nothing newer can leak."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from app.db import Database
from app.live.events import LiveEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_log (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id      INTEGER NOT NULL,
    event_id     TEXT NOT NULL,
    kind         TEXT NOT NULL,
    version      INTEGER NOT NULL,
    received_at  TEXT NOT NULL,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS live_log_game ON live_log(game_id, seq);
CREATE INDEX IF NOT EXISTS live_log_event ON live_log(game_id, event_id, version);
"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


class EventStore:
    """Freeze wave F7: a game's events are kept in memory once read (append-only, in seq order), so each client's
    look at what the delay has released is a walk of a list, not a read of every row from seq 0 per event per client."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._events: dict[int, list[LiveEvent]] = {}
        self._lock = threading.RLock()
        with self.db.read() as conn:
            conn.executescript(SCHEMA)  # executescript commits on its own, so no explicit transaction here

    def _loaded(self, game_id: int) -> list[LiveEvent]:
        """The game's events, oldest first, read from the log the first time they are asked for."""
        with self._lock:
            kept = self._events.get(game_id)
            if kept is not None:
                return kept
        with self.db.read() as conn:
            rows = conn.execute("SELECT seq, event_id, kind, version, received_at, payload FROM live_log WHERE game_id = ? ORDER BY seq", (game_id,)).fetchall()
        events = [LiveEvent(r["event_id"], r["kind"], game_id, _parse(r["received_at"]), json.loads(r["payload"]), int(r["version"]), int(r["seq"])) for r in rows]
        with self._lock:
            return self._events.setdefault(game_id, events)

    def append(self, events: list[LiveEvent]) -> list[LiveEvent]:
        """Store what is new or changed. Returns the stored events with seq and version set."""
        stored: list[LiveEvent] = []
        with self.db.transaction() as conn:
            for event in events:
                row = conn.execute(
                    "SELECT version, payload FROM live_log WHERE game_id = ? AND event_id = ? ORDER BY version DESC LIMIT 1",
                    (event.game_id, event.id),
                ).fetchone()
                payload = json.dumps(event.data, sort_keys=True, separators=(",", ":"))
                if row is not None:
                    if row["payload"] == payload:
                        continue  # the same thing again: not an event
                    event.version = int(row["version"]) + 1  # upstream corrected it
                else:
                    event.version = 1
                cursor = conn.execute(
                    "INSERT INTO live_log (game_id, event_id, kind, version, received_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
                    (event.game_id, event.id, event.kind, event.version, _iso(event.received_at), payload),
                )
                event.seq = int(cursor.lastrowid)
                stored.append(event)
        with self._lock:
            for event in stored:
                kept = self._events.get(event.game_id)
                if kept is not None:
                    kept.append(event)
        return stored

    def released(self, game_id: int, cutoff: datetime, after_seq: int = 0, limit: int | None = None) -> list[LiveEvent]:
        """Events received at or before `cutoff`, after `after_seq`, oldest first."""
        events = self._loaded(game_id)
        with self._lock:
            out = [e for e in events if (e.seq or 0) > after_seq and e.received_at <= cutoff]
        return out[:limit] if limit else out

    def latest_seq(self, game_id: int) -> int:
        events = self._loaded(game_id)
        with self._lock:
            return int(events[-1].seq or 0) if events else 0

    def latest(self, game_id: int, event_id: str) -> dict[str, Any] | None:
        """The newest stored data of one event id (the status line, say), whatever its receipt time.
        None when nothing is stored or the stored payload is not an object."""
        events = self._loaded(game_id)
        with self._lock:
            found = next((e for e in reversed(events) if e.id == event_id), None)
        if found is None:
            return None
        return found.data if isinstance(found.data, dict) else None

    def pending_after(self, game_id: int, cutoff: datetime, after_seq: int) -> bool:
        """True when events exist beyond `after_seq` that the delay has not released yet."""
        events = self._loaded(game_id)
        with self._lock:
            return any((e.seq or 0) > after_seq and e.received_at > cutoff for e in events)

    def count(self, game_id: int) -> int:
        return len(self._loaded(game_id))

    def count_kind(self, game_id: int, kind: str) -> int:
        """How many events of one kind (play, drive, status, box, players) are stored for a game, corrections included."""
        events = self._loaded(game_id)
        with self._lock:
            return sum(1 for e in events if e.kind == kind)

    def games(self) -> list[int]:
        with self.db.read() as conn:
            rows = conn.execute("SELECT DISTINCT game_id FROM live_log ORDER BY game_id").fetchall()
        return [int(r["game_id"]) for r in rows]

    def clear(self, game_id: int) -> int:
        with self._lock:
            self._events.pop(game_id, None)
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM live_log WHERE game_id = ?", (game_id,))
        return int(cursor.rowcount)
