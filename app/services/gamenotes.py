"""Your own notes while a game is on (Phase 19, owner's idea: "your own in-game notes into the archive"). Jot a line during
the game, with the quarter, clock and score stamped on it, and read them back later in the Archive next to the plays. They
are the owner's words, kept as plain JSON in data/gamenotes/<game_id>.json and part of the nightly backup.

    GameNotes(data_dir)
      .list(game_id) -> [note]            oldest first
      .add(game_id, text, context)        -> the note ({id, at, text, period, clock, score}); text trimmed, 1 to 1,000 characters
      .delete(game_id, note_id) -> bool
      .count(game_id) -> int

Nothing is invented: a context field that is missing or the wrong type is left out of the note. At most 300 notes a game.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.gamenotes")

MAX_TEXT = 1000
MAX_NOTES = 300


class NoteError(ValueError):
    """A note that cannot be saved; the message is safe to show."""


def _clean(context: Any) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    out: dict[str, Any] = {}
    period = context.get("period")
    if isinstance(period, int) and not isinstance(period, bool) and 1 <= period <= 12:
        out["period"] = period
    clock = context.get("clock")
    if isinstance(clock, str) and 0 < len(clock.strip()) <= 12:
        out["clock"] = clock.strip()
    score = context.get("score")
    if isinstance(score, str) and 0 < len(score.strip()) <= 40:
        out["score"] = score.strip()
    return out


class GameNotes:
    def __init__(self, data_dir: Path) -> None:
        self.folder = Path(data_dir) / "gamenotes"

    def _path(self, game_id: int) -> Path:
        return self.folder / f"{int(game_id)}.json"

    def list(self, game_id: int) -> list[dict[str, Any]]:
        try:
            raw = json.loads(self._path(game_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        rows = raw.get("notes") if isinstance(raw, dict) else None
        return [r for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str) and isinstance(r.get("text"), str)] if isinstance(rows, list) else []

    def count(self, game_id: int) -> int:
        return len(self.list(game_id))

    def _write(self, game_id: int, rows: list[dict[str, Any]]) -> None:
        try:
            atomic_write(self._path(game_id), json.dumps({"gameId": int(game_id), "notes": rows}, indent=1, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise NoteError(f"The note could not be saved: {exc.strerror or exc}.") from None

    def add(self, game_id: int, text: Any, context: Any = None, now: datetime | None = None) -> dict[str, Any]:
        body = text.strip() if isinstance(text, str) else ""
        if not body:
            raise NoteError("Write something first.")
        if len(body) > MAX_TEXT:
            raise NoteError(f"A note is at most {MAX_TEXT:,} characters.")
        rows = self.list(game_id)
        if len(rows) >= MAX_NOTES:
            raise NoteError(f"This game already has {MAX_NOTES} notes.")
        note = {"id": secrets.token_hex(4), "at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds").replace("+00:00", "Z"), "text": body, **_clean(context)}
        self._write(game_id, [*rows, note])
        log.info("Game note added for %s (%d now)", game_id, len(rows) + 1)
        return note

    def delete(self, game_id: int, note_id: str) -> bool:
        rows = self.list(game_id)
        kept = [r for r in rows if r["id"] != note_id]
        if len(kept) == len(rows):
            return False
        self._write(game_id, kept)
        return True
