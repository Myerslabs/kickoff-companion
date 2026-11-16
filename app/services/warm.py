"""The nightly warm (ENH-27, owner 2026-10-25: "use all the calls we can as opposed to limiting the calls"). Once a day after
WARM_HOUR, while no game window is open, the server loads its teams' pages ahead of the readers: the home team, the other
primary and the secondary teams, this season's opponents and the latest AP Top 25, each one's Season page, Roster and
Recruiting. Every call is paced (app/cfbd/client.py paced_calls): the warm spends the month's target and stops when the
day's share is used, never touching the reserve that pages someone opens and live games keep.

After the warm, the sweep (FEAT-8): every final game this season with an FBS side, oldest first, gets its box score and
advanced box cached for good (so any game's box opens at once) and its plays read once, without keeping them, for the
app's own numbers (app/services/numbers.py), kept in data/season/<year>/numbers.json. A game is swept once it is
SETTLE_HOURS old, so CFBD's corrections are in.

    NightlyWarm(data_dir, client, season, players, program, team_set, tz)
      due(now) -> bool          after WARM_HOUR, not yet today
      await run(now) -> dict    {day, teams, warmed, cards, calls, stoppedBy, swept}; kept in data/warm.json (cards: batch 1)
      await sweep(now) -> dict  {games, swept, calls, stoppedBy}
      status() -> dict          the last run, for /api/settings housekeeping
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient, CfbdError, paced_calls
from app.cfbd.quota import QuotaBlocked
from app.services import gamekeys, plan
from app.services.answers import atomic_write
from app.services.numbers import NumbersStore, game_counts
from app.services.playoff import latest_poll
from app.services.rankedweek import AP_NAME

log = logging.getLogger("kickoff.warm")

WARM_HOUR = 3  # local; the backup follows at four
SETTLE_HOURS = 30  # a game is swept once CFBD has had a day to correct it
SAVE_EVERY = 10


class NightlyWarm:
    def __init__(self, data_dir: Path, client: CfbdClient, season: Any, players: Any, program: Any, team_set: Callable[[], list[str]]) -> None:
        self.path = Path(data_dir) / "warm.json"
        self.client = client
        self.season = season
        self.players = players
        self.program = program
        self.team_set = team_set  # the home team first, then the other primary and the secondary teams
        self.numbers = NumbersStore(data_dir, client.settings.season)
        self.running = False

    def _stored(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def status(self) -> dict[str, Any]:
        return {**self._stored(), "running": self.running}

    def due(self, now: datetime) -> bool:
        if self._lean():
            return False  # the Free profile never loads ahead of the readers (public release Phase 5a's no-prewarm rule)
        return now.hour >= WARM_HOUR and self._stored().get("day") != now.date().isoformat() and not self.running

    def _lean(self) -> bool:
        try:
            return plan.lean(self.client)
        except Exception:  # noqa: BLE001 - a client without a quota (a test double) runs the full profile
            log.debug("The nightly warm could not read the plan; it runs the full profile", exc_info=True)
            return False

    async def teams(self) -> list[str]:
        """The warm's order: our teams, then this season's opponents, then the AP Top 25, each once."""
        order: list[str] = list(self.team_set())
        try:
            parts = await self.program._core()
            home = order[0] if order else self.program.team
            for game in parts["schedule"].records:
                other = game.away_team if game.home_team == home else game.home_team
                if isinstance(other, str) and other:
                    order.append(other)
            fbs = {t.school for t in parts["teams"].records if isinstance(t.school, str)}
            _week, ranks = latest_poll(parts["rankings"].records, AP_NAME)
            order.extend(r.school for r in ranks)
        except Exception:  # noqa: BLE001 - a missing part only shortens the list; logged
            log.exception("The nightly warm could not read the schedule and the poll")
            fbs = set()
        seen: list[str] = []
        for school in order:
            if school and school not in seen and (not fbs or school in fbs):
                seen.append(school)
        return seen

    async def card_teams(self) -> list[str]:
        """Batch 1: whose player cards the warm loads: ours, then the next opponent's (none when the schedule cannot be read)."""
        out = [self.program.team]
        try:
            schedule = (await self.program._core())["schedule"]
            _game, opponent = self.players._next_game(schedule.records) if schedule.ok else (None, None)
        except Exception:  # noqa: BLE001 - ours alone then; logged
            log.exception("The nightly warm could not find the next opponent for the player cards")
            opponent = None
        if isinstance(opponent, str) and opponent and opponent not in out:
            out.append(opponent)
        return out

    async def run(self, now: datetime) -> dict[str, Any]:
        self.running = True
        try:
            teams = await self.teams()
            before = self.client.quota.status(self.client._clock()).ledger_calls_this_month
            warmed, stopped = 0, None
            carded: list[str] = []
            home = self.program.team
            with paced_calls():
                for school in teams:
                    if self.client.live_window:
                        stopped = "a game window opened"
                        break
                    if not self.client.quota.status(self.client._clock()).paced_open:
                        stopped = "the day's share of the month's target"
                        break
                    try:
                        await self.season.overview(None if school == home else school)
                        players = await self.players.scoped(school)
                        if players is not None:
                            await players.roster()
                            await players.recruiting()
                        warmed += 1
                    except Exception:  # noqa: BLE001 - one team's trouble never stops the rest; logged
                        log.exception("The nightly warm could not load %s", school)
                # batch 1 (owner 2026-11-15, "Fetch overnight"): every player card of our team and the next opponent, each
                # finished game's box and play value one call a game, so a card opens at once (a few dozen calls the first
                # night, then a couple a game; the cache keeps a finished game's box for good)
                for school in await self.card_teams() if stopped is None else []:
                    if self.client.live_window:
                        stopped = "a game window opened"
                        break
                    if not self.client.quota.status(self.client._clock()).paced_open:
                        stopped = "the day's share of the month's target"
                        break
                    try:
                        await self.players.card_parts(school)
                        carded.append(school)
                    except Exception:  # noqa: BLE001 - the cards only wait as before; logged
                        log.exception("The nightly warm could not load %s's player cards", school)
            calls = self.client.quota.status(self.client._clock()).ledger_calls_this_month - before
            record = {"day": now.date().isoformat(), "at": now.isoformat(timespec="minutes"), "teams": len(teams), "warmed": warmed, "cards": carded, "calls": max(calls, 0), "stoppedBy": stopped}
            try:
                atomic_write(self.path, json.dumps(record, indent=1) + "\n")
            except OSError as exc:
                log.warning("Could not keep the nightly warm's record: %s", exc)
            log.info("Nightly warm: %d of %d teams, %d calls%s", warmed, len(teams), record["calls"], f", stopped by {stopped}" if stopped else "")
            if stopped is None:
                record["sweep"] = await self.sweep(now)
                try:
                    atomic_write(self.path, json.dumps(record, indent=1) + "\n")
                except OSError as exc:
                    log.warning("Could not keep the nightly warm's record: %s", exc)
            return record
        finally:
            self.running = False

    async def sweep(self, now: datetime) -> dict[str, Any]:
        """FEAT-8: every settled final game with an FBS side, oldest first, until the day's share runs out."""
        parts = await self.program._core()
        fbs = {t.school for t in parts["teams"].records if isinstance(t.school, str)}
        year = self.program.year
        cutoff = now.astimezone(timezone.utc) - timedelta(hours=SETTLE_HOURS)

        def settled(game: Any) -> bool:
            try:
                kickoff = datetime.fromisoformat(str(game.start_date).replace("Z", "+00:00"))
            except ValueError:
                return False
            return kickoff.tzinfo is not None and kickoff <= cutoff

        games = sorted((g for g in parts["games"].records if g.completed and isinstance(g.id, int) and (g.home_team in fbs or g.away_team in fbs) and settled(g)), key=gamekeys.order)
        todo = [g for g in games if not self.numbers.has(g.id)]
        before = self.client.quota.status(self.client._clock()).ledger_calls_this_month
        swept, stopped = 0, None
        with paced_calls():
            for game in todo:
                if self.client.live_window:
                    stopped = "a game window opened"
                    break
                if not self.client.quota.status(self.client._clock()).paced_open:
                    stopped = "the day's share of the month's target"
                    break
                side = game.home_team if game.home_team in fbs else game.away_team
                try:
                    await self.program.box(game.id)  # the team and player box, cached for good
                    await self.client.get("/game/box/advanced", {"id": game.id}, kind=DataKind.FINISHED_GAME)
                    fetched = await self.client.get("/plays", gamekeys.week_params(game, year, side), kind=DataKind.FINISHED_GAME, use_cache=False)
                except QuotaBlocked:
                    stopped = "the day's share of the month's target"
                    break
                except CfbdError as exc:
                    log.info("The sweep skipped game %s: %s", game.id, exc)
                    continue
                rows = [r for r in (fetched.payload if isinstance(fetched.payload, list) else []) if isinstance(r, dict) and r.get("gameId") == game.id]
                if not rows:
                    continue  # nothing posted yet: asked again next night
                self.numbers.put(game.id, game.week, game.home_team, game.away_team, game_counts(rows))
                swept += 1
                if swept % SAVE_EVERY == 0:
                    await asyncio.to_thread(self.numbers.save)
        if swept:
            await asyncio.to_thread(self.numbers.save)
        calls = self.client.quota.status(self.client._clock()).ledger_calls_this_month - before
        log.info("The sweep: %d of %d games left, %d calls%s", swept, len(todo), max(calls, 0), f", stopped by {stopped}" if stopped else "")
        return {"games": len(games), "left": len(todo) - swept, "swept": swept, "calls": max(calls, 0), "stoppedBy": stopped}
