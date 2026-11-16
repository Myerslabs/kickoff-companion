"""The season rollover's switch (R2; owner 2026-11-15: "On its own, when 2027 is listed", "Restart as soon as due", "Also
wait for title game", "The book and its games"; once a day is plenty: "it will only happen once a year right?").

Once a day the housekeeping loop asks three things, the cheapest first: is our season closed out (every game final and its
Post-Game closed, the rail's Season book stop open), is the national title game final, and does CFBD list our next season's
schedule. The last two are one CFBD call each, made only once the season is closed out. When all three hold, the switch is
due and stays due (data/rollover.json) until it is made: it waits while something is writing (a Claude run, the weekly jobs,
a prompts run, a game window), then keeps the season in review as it stands (data/season/<year>/book/, so the Seasons list
reads it with no CFBD call), writes SEASON=<next> to .env and asks for the restart Update and Restart use. A step that fails
switches nothing: the To do says why on the host's devices and the next hourly housekeeping tries again.

    title_game_final(games, now) -> bool       the FBS postseason's title game is final
    RolloverStore(data_dir)                    data/rollover.json: checkedOn, due, waiting, error, switched [{from, to, at}]
    Rollover(...).tick(now) -> str             one decision: "checked today", a reason it waits, "waiting", "failed", "switched"
    switched_at(data_dir, season) -> datetime  when the app moved to this season (the schedule's catch-up), or None
    notice() / load_notice(data_dir, season, now)   what the envelope's meta.season says: the switch made, or the switch failing
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.cfbd.models import Game
from app.services.answers import atomic_write

log = logging.getLogger("kickoff.rollover")

STATE_FILE = "rollover.json"
NOTICE_DAYS = 14  # the To do says the app is on the new season for two weeks after the switch
TITLE_WORDS = "national championship"
UNNAMED_SETTLE = timedelta(days=3)  # no game named the title game: every game final and the last one three days old


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def title_game_final(games: list[Any], now: datetime) -> bool:
    """CFBD's FBS postseason games: the one its notes name the national championship, final; without one named, every game
    listed final and the last of them at least three days old in the new year (never True on an empty or partial list)."""
    post = [g for g in games if isinstance(g, Game) and str(g.season_type or "postseason") == "postseason"]
    if not post:
        return False
    named = [g for g in post if TITLE_WORDS in str(g.notes or "").lower()]
    if named:
        return all(g.completed is True for g in named)
    if not all(g.completed is True for g in post):
        return False
    kicks = [k for k in (_parse(g.start_date) for g in post) if k is not None]
    if not kicks:
        return False
    last = max(kicks)
    return last.month <= 2 and now - last >= UNNAMED_SETTLE


class RolloverStore:
    """data/rollover.json, the switch's memory. An unreadable file reads as empty (logged); the switch asks again."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / STATE_FILE

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = {}
        except (OSError, ValueError) as exc:
            log.warning("The rollover file could not be read (%s); it starts again", exc)
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        switched = [s for s in raw.get("switched") or [] if isinstance(s, dict) and isinstance(s.get("to"), int) and isinstance(s.get("from"), int)] if isinstance(raw.get("switched"), list) else []
        return {
            "checkedOn": raw.get("checkedOn") if isinstance(raw.get("checkedOn"), str) else None,
            "due": raw.get("due") if isinstance(raw.get("due"), int) and not isinstance(raw.get("due"), bool) else None,
            "waiting": raw.get("waiting") if isinstance(raw.get("waiting"), str) else None,
            "error": raw.get("error") if isinstance(raw.get("error"), str) else None,
            "switched": switched,
        }

    def save(self, state: dict[str, Any]) -> None:
        atomic_write(self.path, json.dumps(state, indent=2))


def switched_at(data_dir: Path, season: int) -> datetime | None:
    """When the app moved to `season` by the switch (the last such move), or None."""
    moves = [s for s in RolloverStore(data_dir).load()["switched"] if s.get("to") == season]
    return _parse(moves[-1].get("at")) if moves else None


_notice: dict[str, Any] | None = None


def notice() -> dict[str, Any] | None:
    """The envelope's meta.season: {"switched": {from, to, at}} for two weeks after the switch, {"failed": {to, error}}
    while a due switch fails, else None."""
    return _notice


def _notice_from(state: dict[str, Any], season: int, now: datetime) -> dict[str, Any] | None:
    if state.get("error") and isinstance(state.get("due"), int):
        return {"failed": {"to": state["due"], "error": state["error"]}}
    moves = [s for s in state.get("switched") or [] if s.get("to") == season]
    if moves:
        at = _parse(moves[-1].get("at"))
        if at is not None and now - at <= timedelta(days=NOTICE_DAYS):
            return {"switched": {"from": moves[-1]["from"], "to": season, "at": moves[-1].get("at")}}
    return None


def load_notice(data_dir: Path, season: int, now: datetime | None = None) -> dict[str, Any] | None:
    global _notice
    _notice = _notice_from(RolloverStore(data_dir).load(), season, now or datetime.now(timezone.utc))
    return _notice


def reset_notice() -> None:
    global _notice
    _notice = None


class Rollover:
    def __init__(
        self,
        *,
        data_dir: Path,
        season: int,
        tz: Any,
        closed_out: Callable[[], Awaitable[bool]],
        title_final: Callable[[], Awaitable[bool | None]],
        next_listed: Callable[[int], Awaitable[bool | None]],
        busy: Callable[[], str | None],
        keep_book: Callable[[int], Awaitable[None]],
        set_season: Callable[[int], None],
        restart: Callable[[str], None],
    ) -> None:
        self.store = RolloverStore(data_dir)
        self.data_dir = Path(data_dir)
        self.season = season
        self.tz = tz
        self.closed_out = closed_out
        self.title_final = title_final
        self.next_listed = next_listed
        self.busy = busy
        self.keep_book = keep_book
        self.set_season = set_season
        self.restart = restart

    def status(self) -> dict[str, Any]:
        state = self.store.load()
        return {"season": self.season, "next": self.season + 1, **state}

    async def tick(self, now: datetime) -> str:
        state = self.store.load()
        if state["due"] == self.season + 1:
            return await self._switch(state, now)
        today = now.astimezone(self.tz).date().isoformat()
        if state["checkedOn"] == today:
            return "checked today"
        state["checkedOn"] = today
        reason = await self._check()
        state["waiting"] = reason
        if reason is not None:
            state["due"] = None
            self.store.save(state)
            log.info("The season stays on %s: %s", self.season, reason)
            return reason
        state["due"] = self.season + 1
        self.store.save(state)
        log.info("The switch to %s is due: our season is closed out, the title game is final and CFBD lists %s", self.season + 1, self.season + 1)
        return await self._switch(state, now)

    async def _check(self) -> str | None:
        nxt = self.season + 1
        if not await self.closed_out():
            return f"Our {self.season} season is not closed out yet."
        final = await self.title_final()
        if final is None:
            return "The national title game could not be read from CFBD; the app asks again tomorrow."
        if not final:
            return "The national title game is still to be played."
        listed = await self.next_listed(nxt)
        if listed is None:
            return f"CFBD's {nxt} schedule could not be read; the app asks again tomorrow."
        if not listed:
            return f"CFBD does not list our {nxt} schedule yet."
        return None

    async def _switch(self, state: dict[str, Any], now: datetime) -> str:
        global _notice
        nxt = self.season + 1
        why = self.busy()
        if why:
            state["waiting"] = f"The switch to {nxt} waits: {why}."
            self.store.save(state)
            log.info("%s", state["waiting"])
            return "waiting"
        try:
            await self.keep_book(self.season)
            self.set_season(nxt)
        except Exception as exc:  # noqa: BLE001 - nothing switches; the To do says why and the next hour tries again
            reason = str(exc).strip() or exc.__class__.__name__
            state["error"] = f"The switch to {nxt} could not be made: {reason.rstrip('.')}. The app tries again within the hour."
            self.store.save(state)
            _notice = _notice_from(state, self.season, now)
            log.exception("The switch to %s failed", nxt)
            return "failed"
        state.update(due=None, error=None, waiting=None)
        state["switched"] = [*state["switched"], {"from": self.season, "to": nxt, "at": _iso(now)}]
        self.store.save(state)
        _notice = None
        log.info("The season moved to %s; the server restarts", nxt)
        self.restart(f"The season moved to {nxt}")
        return "switched"
