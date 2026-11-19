"""Another game on one device (batch 3, owner 2026-11-16: "Stays on host's game, each client can view another game").

The live engine follows one game for every screen: ours, or the one the host picked (FEAT-1). A device may watch any other
game of the day on its own In Game. Such a game is polled here, alongside, only while a device asks for it:
`GET /api/live/state?game=<id>` is both the read and the heartbeat. A poll is due every SIDE_POLL_SECONDS (the host's game
keeps the engine's own pace), runs in the background through the client's quota guard as a plain call (never the room's
live lane), and its plays go into the engine's event store under the game's own id, so the state is the same fold
(`derive_state`) and the spoiler delay holds. A game nobody asked for in IDLE_SECONDS is let go; at most MAX_SIDE_GAMES at
once (a fourth is told which are on). A final game is never polled again (its stored plays answer), nor one LATE past
kickoff, and one with no plays QUIET after kickoff (or with no kickoff time) says so and stops.

    SideGames.state(game_id, delay, team)   the state for a device, or a short answer saying why there is none yet
    SideGames.close()                        shutdown: cancels the polls under way
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdError
from app.cfbd.models import LiveGame, parse_one
from app.cfbd.quota import QuotaBlocked
from app.live.events import events_from_live
from app.live.state import derive_state

log = logging.getLogger("kickoff.live.side")

SIDE_POLL_SECONDS = 30
IDLE_SECONDS = 120
MAX_SIDE_GAMES = 3
FIRST_WAIT_SECONDS = 4.0  # a device's first ask waits this long for the game's first poll
EARLY = timedelta(minutes=30)  # a game is watchable from half an hour before kickoff
LATE = timedelta(hours=8)  # and until eight hours after it (a long game, overtime, the final's last plays)
QUIET = timedelta(minutes=90)  # past kickoff (or with no kickoff time) and still no plays: postponed, say so and stop
UNAVAILABLE = "Watching another game here needs live play-by-play, which comes with a Tier 2 CFBD key. After the final, its box score is on its program."
SIDE_POLL_TIMEOUT = 25.0  # one side poll, the client's own retries included, never runs past this


class SideGames:
    def __init__(self, engine: Any, program: Any, *, clock=None) -> None:
        self.engine = engine
        self.program = program
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._asked: dict[int, float] = {}  # game id -> the last time a device asked (monotonic)
        self._polled: dict[int, float] = {}  # game id -> the last poll's start (monotonic)
        self._teams: dict[int, tuple[str | None, str | None]] = {}  # game id -> (home, away)
        self._errors: dict[int, str] = {}
        self._tasks: dict[int, asyncio.Task[Any]] = {}
        self._quiet_since: dict[int, datetime] = {}  # game id -> the first ask after kickoff that found no plays stored
        self._closed = False
        self.polls = 0

    def watching(self) -> list[int]:
        now = time.monotonic()
        for gid in [g for g, at in self._asked.items() if now - at > IDLE_SECONDS]:
            self._forget(gid)
            log.info("Side game %s let go: no device asked for it in %d s", gid, IDLE_SECONDS)
        return sorted(self._asked)

    def _forget(self, game_id: int) -> None:
        """A game let go (nobody asked) or done (final, late, no plays): its bookkeeping goes; a poll under way finishes."""
        self._asked.pop(game_id, None)
        self._polled.pop(game_id, None)
        self._errors.pop(game_id, None)
        self._teams.pop(game_id, None)
        task = self._tasks.get(game_id)
        if task is not None and task.done():
            self._tasks.pop(game_id, None)

    async def close(self) -> None:
        """Shutdown, beside the engine's stop: cancel the polls under way and wait for them, so none outlives the client."""
        self._closed = True
        tasks = [t for t in self._tasks.values() if not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._asked.clear()
        self._polled.clear()

    async def _game(self, game_id: int) -> Any:
        parts = await self.program._core()
        return next((g for g in parts["games"].records if g.id == game_id), None)

    def _stored(self, game_id: int, cutoff: datetime) -> tuple[int, bool, list[Any]]:
        """Off the event loop: how many events the store holds for the game, whether the feed has said final, and the ones
        released at `cutoff`."""
        store = self.engine.store
        count = store.count(game_id)
        if not count:
            return 0, False, []
        status = store.latest(game_id, "status") or {}
        return count, status.get("status") == "final", store.released(game_id, cutoff)

    def _build(self, events: list[Any], game_id: int, home: str | None, away: str | None, cutoff: datetime) -> dict[str, Any]:
        """Off the event loop: the state's fold, as the engine builds its own."""
        built = derive_state(events, game_id=game_id, home=home, away=away, mode="live", rosters=None, ep_tables=getattr(self.engine, "_ep_tables", None))
        built["pending"] = self.engine.store.pending_after(game_id, cutoff, built.get("lastSeq") or 0)
        return built

    async def state(self, game_id: int, delay_seconds: float, team: str | None = None) -> dict[str, Any]:
        game = await self._game(game_id)
        if game is None:
            return {"gameId": game_id, "status": "unknown", "side": True, "reason": "No FBS game with that id this season."}
        home, away = game.home_team, game.away_team
        side = team if team in (home, away) else home
        base = {"gameId": game_id, "home": home, "away": away, "team": side, "side": True, "kickoff": game.start_date}
        now = self._clock()
        kickoff = _when(game.start_date)
        if not self.engine.client.capabilities.live_plays and not (kickoff is not None and now > kickoff + LATE):
            # Kickoff Companion 2.1: a key without live play-by-play says so from the start, not "plays come before kickoff"
            return {**base, "status": "unavailable", "reason": UNAVAILABLE}
        if kickoff is not None and now < kickoff - EARLY:
            return {**base, "status": "pregame", "reason": "The game has not started; plays come from half an hour before kickoff."}
        cutoff = self.engine.cutoff(delay_seconds)
        stored, final, events = await asyncio.to_thread(self._stored, game_id, cutoff)
        late = kickoff is not None and now > kickoff + LATE
        if late and not stored:
            return {**base, "status": "over", "reason": "The game is over; its box score is on its program."}
        if final or late:
            # the review (2026-11-19): a finished game is never polled again; its stored plays answer every ask
            self._forget(game_id)
            self._quiet_since.pop(game_id, None)
            if not events:
                return {**base, "status": "waiting", "reason": "The plays are on their way at this screen's delay.", "error": None}
            return await self._answer(events, game_id, home, away, side, delay_seconds, cutoff)
        if not self.engine.client.capabilities.live_plays:
            return {**base, "status": "unavailable", "reason": UNAVAILABLE}
        if stored:
            self._quiet_since.pop(game_id, None)
        elif kickoff is None or now >= kickoff:
            # the review (2026-11-19): a game with no kickoff time, or put off past it, is not polled forever
            since = self._quiet_since.setdefault(game_id, now)
            if now - since > QUIET:
                why = self._errors.get(game_id)
                self._forget(game_id)
                more = f" The last try: {why}" if why else ""
                return {**base, "status": "noplays", "reason": f"No plays have come for this game in an hour and a half; it may be postponed.{more}"}
        on = self.watching()
        if game_id not in on and len(on) >= MAX_SIDE_GAMES:
            return {**base, "status": "full", "watching": on, "reason": f"{MAX_SIDE_GAMES} other games are being watched on this network already; pick one of those or try again in a few minutes."}
        self._asked[game_id] = time.monotonic()
        self._teams[game_id] = (home, away)
        self._maybe_poll(game_id)
        task = self._tasks.get(game_id)
        if not events and task is not None and not task.done():
            # the review (owner 2026-11-19): a live game picked on a device read "Pregame" until the next ask, 12 s on; the
            # first answer waits a moment for the first poll, never longer than FIRST_WAIT_SECONDS
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=FIRST_WAIT_SECONDS)
            except (TimeoutError, Exception):  # noqa: BLE001 - the poll keeps going and says its own errors
                pass
            cutoff = self.engine.cutoff(delay_seconds)
            _, _, events = await asyncio.to_thread(self._stored, game_id, cutoff)
        if not events:
            return {**base, "status": "waiting", "reason": self._errors.get(game_id) or "The first plays are on their way.", "error": self._errors.get(game_id)}
        return await self._answer(events, game_id, home, away, side, delay_seconds, cutoff)

    async def _answer(self, events: list[Any], game_id: int, home: str | None, away: str | None, side: str | None, delay_seconds: float, cutoff: datetime) -> dict[str, Any]:
        built = await asyncio.to_thread(self._build, events, game_id, home, away, cutoff)
        built.update({"delaySeconds": delay_seconds, "team": side, "side": True, "home": built.get("home") or home, "away": built.get("away") or away})
        if self._errors.get(game_id):
            built["sideError"] = self._errors[game_id]
        return built

    def _maybe_poll(self, game_id: int) -> None:
        if self._closed:
            return
        task = self._tasks.get(game_id)
        if task is not None and not task.done():
            return
        last = self._polled.get(game_id)
        if last is not None and time.monotonic() - last < SIDE_POLL_SECONDS:
            return
        self._polled[game_id] = time.monotonic()
        self._tasks[game_id] = asyncio.create_task(self._poll(game_id), name=f"side-game-{game_id}")

    async def _poll(self, game_id: int) -> None:
        """One /live/plays call for a side game; its events go into the shared store (never the engine's own counters or
        streams, which are the host's game's).

        The review (2026-11-19): a side game is optional, so it is a plain call (live=False), never the room's: the quota
        guard holds it back in RESTRICTED mode, keeping the reserve for the room's game, and its failures count on the
        general breaker, never the live lane the engine's poll answers to. Inside a live window it takes its turn behind
        the room's poll (the client's ENH-3 gate). It is not paced: a device asked for it, like a page someone opens."""
        self.polls += 1
        try:
            fetched = await asyncio.wait_for(
                self.engine.client.get("/live/plays", {"gameId": game_id}, kind=DataKind.LIVE, live=False, use_cache=False),
                timeout=SIDE_POLL_TIMEOUT,
            )
        except (QuotaBlocked, CfbdError) as exc:
            self._errors[game_id] = f"The live feed did not answer ({exc.__class__.__name__}); trying again."
            log.warning("Side game %s: the live poll failed: %s", game_id, exc)
            return
        except TimeoutError:
            self._errors[game_id] = f"The live feed did not answer in {SIDE_POLL_TIMEOUT:.0f} s; trying again."
            log.warning("Side game %s: the live poll timed out after %.0f s", game_id, SIDE_POLL_TIMEOUT)
            return
        except Exception:  # noqa: BLE001 - a side game never takes the server down; logged with its traceback
            self._errors[game_id] = "The live feed could not be read; trying again."
            log.exception("Side game %s: the live poll broke", game_id)
            return
        game = parse_one(LiveGame, fetched.payload, context="live/plays")
        if game is None or game.id != game_id:
            self._errors[game_id] = "The live feed has no plays for this game yet."
            return
        events = events_from_live(game, self._clock())
        try:
            await asyncio.to_thread(self.engine.store.append, events)
        except Exception as exc:  # noqa: BLE001 - logged; the next poll carries the same plays again
            self._errors[game_id] = "The plays could not be stored; trying again."
            log.exception("Side game %s: could not store the plays: %s", game_id, exc)
            return
        self._errors.pop(game_id, None)


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
