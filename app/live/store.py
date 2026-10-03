"""The event store: every live event appended in receipt order with the server time it arrived.
Dedupe and corrections live here: an event whose id and data were already stored is dropped,
one whose data changed is appended again with a higher version, so a later reader sees the
correction in order. The delay buffer is a query: released(cutoff) returns events received on
or before the cutoff, so a 45-second delay is `now - 45 s` and nothing newer can leak."""

from __future__ import annotations

import json
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
    def __init__(self, db: Database) -> None:
        self.db = db
        with self.db.read() as conn:
            conn.executescript(SCHEMA)  # executescript commits on its own, so no explicit transaction here

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
        return stored

    def released(self, game_id: int, cutoff: datetime, after_seq: int = 0, limit: int | None = None) -> list[LiveEvent]:
        """Events received at or before `cutoff`, after `after_seq`, oldest first."""
        sql = "SELECT seq, event_id, kind, version, received_at, payload FROM live_log WHERE game_id = ? AND seq > ? AND received_at <= ? ORDER BY seq"
        params: tuple[Any, ...] = (game_id, after_seq, _iso(cutoff))
        if limit:
            sql += " LIMIT ?"
            params = (*params, limit)
        with self.db.read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [LiveEvent(r["event_id"], r["kind"], game_id, _parse(r["received_at"]), json.loads(r["payload"]), int(r["version"]), int(r["seq"])) for r in rows]

    def latest_seq(self, game_id: int) -> int:
        with self.db.read() as conn:
            row = conn.execute("SELECT MAX(seq) AS s FROM live_log WHERE game_id = ?", (game_id,)).fetchone()
        return int(row["s"] or 0) if row else 0

    def latest(self, game_id: int, event_id: str) -> dict[str, Any] | None:
        """The newest stored data of one event id (the status line, say), whatever its receipt time.
        None when nothing is stored or the stored payload is not an object."""
        with self.db.read() as conn:
            row = conn.execute("SELECT payload FROM live_log WHERE game_id = ? AND event_id = ? ORDER BY seq DESC LIMIT 1", (game_id, event_id)).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row["payload"])
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def pending_after(self, game_id: int, cutoff: datetime, after_seq: int) -> bool:
        """True when events exist beyond `after_seq` that the delay has not released yet."""
        with self.db.read() as conn:
            row = conn.execute("SELECT 1 FROM live_log WHERE game_id = ? AND seq > ? AND received_at > ? LIMIT 1", (game_id, after_seq, _iso(cutoff))).fetchone()
        return row is not None

    def count(self, game_id: int) -> int:
        with self.db.read() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM live_log WHERE game_id = ?", (game_id,)).fetchone()
        return int(row["n"]) if row else 0

    def count_kind(self, game_id: int, kind: str) -> int:
        """How many events of one kind (play, drive, status, box, players) are stored for a game, corrections included."""
        with self.db.read() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM live_log WHERE game_id = ? AND kind = ?", (game_id, kind)).fetchone()
        return int(row["n"]) if row else 0

    def games(self) -> list[int]:
        with self.db.read() as conn:
            rows = conn.execute("SELECT DISTINCT game_id FROM live_log ORDER BY game_id").fetchall()
        return [int(r["game_id"]) for r in rows]

    def clear(self, game_id: int) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM live_log WHERE game_id = ?", (game_id,))
        return int(cursor.rowcount)
