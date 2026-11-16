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

KEY = re.compile(r"^(?:week-(\d{1,2})|postseason)(-sunday)?$")  # Wave 6 (owner 2026-11-15): a game's Sunday paper is "<week>-sunday"
POSTSEASON = "postseason"
OFFSEASON_KEY = re.compile(r"^offseason-\d{4}-\d{2}-\d{2}$")  # rollover R3: the off-season paper of the week turning that Monday


def offseason_key(turn: Any) -> str:
    """'offseason-2027-01-11': the off-season paper that turned over on that Monday (never kept as an edition)."""
    return f"offseason-{turn.date().isoformat()}"


def is_offseason(key: Any) -> bool:
    return isinstance(key, str) and bool(OFFSEASON_KEY.match(key))
SUNDAY = "-sunday"
FORMAT = 1


def key_for(week: Any, season_type: Any, sunday: bool = False) -> str | None:
    """The file name of a week's edition: 'week-7', 'postseason' (bowl season is one CFBD week), their Sunday papers
    'week-7-sunday' and 'postseason-sunday', or None."""
    tail = SUNDAY if sunday else ""
    if str(season_type or "regular") == POSTSEASON:
        return POSTSEASON + tail
    if isinstance(week, int) and not isinstance(week, bool) and 0 <= week <= 99:
        return f"week-{week}{tail}"
    return None


def is_sunday(key: Any) -> bool:
    return isinstance(key, str) and bool(KEY.match(key)) and key.endswith(SUNDAY)


def week_key(key: Any) -> str | None:
    """A Sunday paper's week paper ('week-7-sunday' -> 'week-7'); a week paper's own key; None for anything else."""
    return key.removesuffix(SUNDAY) if isinstance(key, str) and KEY.match(key) else None


def label_for(key: str) -> str:
    """'Week 7', 'Week 7 · Sunday paper', 'Bowl season' or 'Bowl season · Sunday paper'."""
    match = KEY.match(key or "")
    if not match:
        return "This week"
    name = "Bowl season" if key.startswith(POSTSEASON) else f"Week {int(match.group(1))}"
    return f"{name} · Sunday paper" if match.group(2) else name


def order_of(key: str) -> tuple[int, int, int]:
    """Where an edition falls in the season: regular weeks in order, each week's Sunday paper after it, then bowl season."""
    match = KEY.match(key)
    if not match:
        return (2, 0, 0)
    sunday = 1 if match.group(2) else 0
    return (1, 0, sunday) if key.startswith(POSTSEASON) else (0, int(match.group(1)), sunday)


def _content(edition: dict[str, Any]) -> str:
    """What decides whether an edition changed: everything but the time it was saved."""
    return json.dumps({k: v for k, v in edition.items() if k != "savedAt"}, sort_keys=True, default=str)


class Editions:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.season = season
        self.dir = Path(data_dir) / "season" / str(season) / "paper"
        self._read: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}  # freeze wave F7: each file decoded once per change (by mtime and size)
        self._written: dict[str, tuple[str, dict[str, Any]]] = {}  # what was last saved, by its content, so an unchanged edition is never read back and compared

    def _path(self, key: str) -> Path | None:
        return self.dir / f"{key}.json" if isinstance(key, str) and KEY.match(key) else None

    def load(self, key: Any) -> dict[str, Any] | None:
        path = self._path(key) if isinstance(key, str) else None
        if path is None:
            return None
        try:
            stat = path.stat()
        except OSError:
            self._read.pop(key, None)
            return None
        stamp = (stat.st_mtime_ns, stat.st_size)
        kept = self._read.get(key)
        if kept is not None and kept[0] == stamp:
            return kept[1]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("The paper's edition %s could not be read: %s", key, exc)
            return None
        if not isinstance(data, dict) or data.get("key") != key:
            log.warning("The paper's edition %s is not an edition; it is ignored", key)
            return None
        self._read[key] = (stamp, data)
        return data

    def save(self, edition: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
        """Write the edition when it changed. A frozen edition on disk is never written over: the saved one comes back
        (force is the one write that freezes it)."""
        key = edition.get("key") if isinstance(edition, dict) else None
        path = self._path(key) if isinstance(key, str) else None
        if path is None:
            return edition
        content = _content({**edition, "format": FORMAT, "season": self.season})
        written = self._written.get(key)
        if written is not None and written[0] == content and not force:
            return written[1]  # the same edition this process saved last: nothing to read back or compare
        old = self.load(key)
        if old is not None and old.get("frozen") is True and not force:
            return old
        if old is not None and _content(old) == content:
            self._written[key] = (content, old)
            return old
        out = {**edition, "format": FORMAT, "season": self.season, "savedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            atomic_write(path, json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.error("The paper's edition %s could not be saved: %s", key, exc)
            return edition
        self._written[key] = (content, out)
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
