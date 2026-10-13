"""The newspaper's weekly editions, kept for the season (queue item 12: the weekly keepsake, owner 2026-10-11).

Each week's paper is saved as the week goes: this week's headlines with their links, every AP-ranked game's matchup with
its score and headline, and the teams off that week. Once the week is over and its games are final the edition is
frozen and never written again, so a final's headline stays as it was first printed. The masthead's arrows page through
the editions; an earlier one is read from its file (the cached season data only, never the live scores).

  data/season/<year>/paper/<key>.json     key: "week-7" for a regular week, "postseason" for bowl season

  Editions(data_dir, season)
    key_for(week, season_type)   "week-7" | "postseason" | None
    load(key)                    the saved edition, or None (no file, a bad key, an unreadable file)
    save(edition, force=False)   writes it when its content changed; never over a frozen edition; returns what is on disk
    frozen_headlines(key)        {gameId: headline} of the finals the saved edition printed
    keys()                       [{key, week, seasonType, label, opponent, homeAway, frozen, weekEnd}] in the season's order

The nightly backup already copies data/season (app/maintenance.py), so the keepsake is backed up with the season notes.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.editions")

KEY = re.compile(r"^(?:week-(\d{1,2})|postseason)$")
POSTSEASON = "postseason"
FORMAT = 1


def key_for(week: Any, season_type: Any) -> str | None:
    """The file name of a week's edition: 'week-7', 'postseason' (bowl season is one CFBD week), or None."""
    if str(season_type or "regular") == POSTSEASON:
        return POSTSEASON
    if isinstance(week, int) and not isinstance(week, bool) and 0 <= week <= 99:
        return f"week-{week}"
    return None


def label_for(key: str) -> str:
    """'Week 7' or 'Bowl season'."""
    match = KEY.match(key or "")
    if not match:
        return "This week"
    return "Bowl season" if key == POSTSEASON else f"Week {int(match.group(1))}"


def order_of(key: str) -> tuple[int, int]:
    """Where an edition falls in the season: regular weeks in order, then bowl season."""
    match = KEY.match(key)
    if not match:
        return (2, 0)
    return (1, 0) if key == POSTSEASON else (0, int(match.group(1)))


def _content(edition: dict[str, Any]) -> str:
    """What decides whether an edition changed: everything but the time it was saved."""
    return json.dumps({k: v for k, v in edition.items() if k != "savedAt"}, sort_keys=True, default=str)


class Editions:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.season = season
        self.dir = Path(data_dir) / "season" / str(season) / "paper"

    def _path(self, key: str) -> Path | None:
        return self.dir / f"{key}.json" if isinstance(key, str) and KEY.match(key) else None

    def load(self, key: Any) -> dict[str, Any] | None:
        path = self._path(key) if isinstance(key, str) else None
        if path is None or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("The paper's edition %s could not be read: %s", key, exc)
            return None
        if not isinstance(data, dict) or data.get("key") != key:
            log.warning("The paper's edition %s is not an edition; it is ignored", key)
            return None
        return data

    def save(self, edition: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
        """Write the edition when it changed. A frozen edition on disk is never written over: the saved one comes back
        (force is the one write that freezes it)."""
        key = edition.get("key") if isinstance(edition, dict) else None
        path = self._path(key) if isinstance(key, str) else None
        if path is None:
            return edition
        old = self.load(key)
        if old is not None and old.get("frozen") is True and not force:
            return old
        if old is not None and _content(old) == _content({**edition, "format": FORMAT, "season": self.season}):
            return old
        out = {**edition, "format": FORMAT, "season": self.season, "savedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            atomic_write(path, json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.error("The paper's edition %s could not be saved: %s", key, exc)
            return edition
        return out

    def frozen_headlines(self, key: Any) -> dict[int, dict[str, Any]]:
        """The headline each final of the saved edition was printed with, by game id (a final's line never changes)."""
        saved = self.load(key)
        out: dict[int, dict[str, Any]] = {}
        for game in (saved or {}).get("matchups") or []:
            if not isinstance(game, dict) or game.get("status") != "final":
                continue
            gid, line = game.get("gameId"), game.get("headline")
            if isinstance(gid, int) and isinstance(line, dict) and isinstance(line.get("text"), str) and line["text"].strip():
                out[gid] = line
        return out

    def keys(self) -> list[dict[str, Any]]:
        """Every saved edition in the season's order (regular weeks, then bowl season)."""
        if not self.dir.is_dir():
            return []
        out = []
        for path in self.dir.glob("*.json"):
            key = path.stem
            if not KEY.match(key):
                continue
            saved = self.load(key)
            if saved is None:
                continue
            out.append({
                "key": key,
                "week": saved.get("week") if isinstance(saved.get("week"), int) else None,
                "seasonType": saved.get("seasonType") if isinstance(saved.get("seasonType"), str) else "regular",
                "label": label_for(key),
                "opponent": saved.get("opponent") if isinstance(saved.get("opponent"), str) else None,
                "homeAway": saved.get("homeAway") if isinstance(saved.get("homeAway"), str) else None,
                "frozen": saved.get("frozen") is True,
                "weekEnd": saved.get("weekEnd") if isinstance(saved.get("weekEnd"), str) else None,
            })
        out.sort(key=lambda e: order_of(e["key"]))
        return out
