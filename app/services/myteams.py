"""My teams (public release Phase 5b): one list of every primary and secondary team with its record, its
national ranks and its last and next game, and the warm-up that loads the primary teams' pages as soon as a
device connects.

The page reads only answers other pages already cache: the season's FBS games, the FBS teams, the records
and the polls (the Game program's shared parts), and SP+, Elo and FPI (the Ratings page's keys). So a team
more or less on the list costs nothing, and a free key, whose set is the home team alone, pays for no more
than the Ratings page would.

Warm-up: with a Tier 2 key, POST /api/myteams/warm loads the team page of primaries #2 to #5 in the
background (ProgramService.team_page, through the quota guard), at most once every WARM_EVERY, so a
tablet waking up never waits on them. A free key warms nothing."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import Game, TeamElo, TeamFPI, TeamSP
from app.config import Settings
from app.services import gamekeys, plan, teamset
from app.services.parts import Assembled, Part, PartFetcher, assemble, statuses
from app.services.program import ProgramService
from app.services.ratings import fbs_set
from app.services.stats_extra import elo_table, fpi_tables, sp_tables

log = logging.getLogger("kickoff.myteams")

WARM_EVERY = timedelta(minutes=10)
ROLE_ORDER = {teamset.HOME: 0, teamset.PRIMARY: 1, teamset.SECONDARY: 2}


def _utc_text(game: Game) -> str | None:
    return game.start_date if isinstance(game.start_date, str) and game.start_date else None


def _result(game: Game, school: str) -> dict[str, Any]:
    home = game.home_team == school
    us, them = (game.home_points, game.away_points) if home else (game.away_points, game.home_points)
    outcome = None
    if isinstance(us, int) and isinstance(them, int):
        outcome = "W" if us > them else "L" if us < them else "T"
    return {
        "gameId": game.id,
        "opponent": gamekeys.opponent_of(game, school),
        "homeAway": "neutral" if game.neutral_site else ("home" if home else "away"),
        "date": _utc_text(game),
        "startTimeTbd": bool(game.start_time_tbd),
        "result": outcome,
        "usPoints": us if isinstance(us, int) else None,
        "themPoints": them if isinstance(them, int) else None,
    }


def last_and_next(games: list[Game], school: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """A team's latest finished game and its next one, from the season's games (the Game program's part)."""
    own = sorted((g for g in games if isinstance(g, Game) and school in (g.home_team, g.away_team) and g.week is not None), key=gamekeys.order)
    done = [g for g in own if g.completed]
    ahead = [g for g in own if not g.completed]
    return (_result(done[-1], school) if done else None), (_result(ahead[0], school) if ahead else None)


def _rating(table: Any, school: str) -> dict[str, Any]:
    return {"value": table.value(school), "rank": table.rank(school), "of": table.of or None}


class MyTeamsService:
    def __init__(self, client: CfbdClient, settings: Settings, prefs: Any, program: ProgramService, ratings_fetcher: PartFetcher) -> None:
        self.client = client
        self.settings = settings
        self.prefs = prefs
        self.program = program
        self.ratings_fetcher = ratings_fetcher
        self._warmed_at: datetime | None = None
        self._warming: asyncio.Task[None] | None = None

    @property
    def year(self) -> int:
        return self.settings.season

    async def page(self) -> Assembled:
        parts = await self.program._core()
        f = self.ratings_fetcher
        rated = await asyncio.gather(
            f.fetch("sp", "/ratings/sp", {"year": self.year}, TeamSP, DataKind.SEASON_STATS),
            f.fetch("elo", "/ratings/elo", {"year": self.year}, TeamElo, DataKind.SEASON_STATS),
            f.fetch("fpi", "/ratings/fpi", {"year": self.year}, TeamFPI, DataKind.SEASON_STATS),
        )
        for part in rated:
            parts[part.name] = part
        return assemble(self.table(parts), parts)

    def table(self, parts: dict[str, Part]) -> dict[str, Any]:
        """The page's data from its parts; no fetching here."""
        team_records = parts["teams"].records
        chosen = teamset.current(self.settings, self.prefs, self.client, team_records)
        teams = self.program._teams(parts["teams"])
        records = {r.team: r for r in parts["records"].records}
        ranks, poll_week = self.program._poll_ranks(parts["rankings"])
        fbs = fbs_set(team_records)
        sp = sp_tables(parts["sp"].records, fbs)["sp"]
        elo = elo_table(parts["elo"].records, fbs)
        fpi = fpi_tables(parts["fpi"].records, fbs)["fpi"]
        rows = []
        for school in [*chosen.primaries, *chosen.secondary]:
            last, upcoming = last_and_next(parts["games"].records, school)
            block = self.program._team_block(school, teams, records, ranks)
            rows.append({
                **block,
                "role": chosen.role(school),
                "why": list(chosen.why.get(school, ())),
                "known": school in teams or not parts["teams"].ok,  # a saved name CFBD no longer lists
                "sp": _rating(sp, school),
                "elo": _rating(elo, school),
                "fpi": _rating(fpi, school),
                "last": last,
                "next": upcoming,
            })
        rows.sort(key=lambda r: (ROLE_ORDER.get(r["role"] or "", 3), r["apRank"] if isinstance(r.get("apRank"), int) else 99, (r.get("school") or "").lower()))
        note = None
        if not chosen.allowed:
            note = "More primary teams and secondary teams show with a Tier 2 key. Your saved picks come back when the key has it." if chosen.locked else "Add more primary teams and secondary teams with a Tier 2 key."
        elif len(rows) == 1:
            note = "Only your home team so far. Add primary and secondary teams on the setup page."
        return {
            "season": self.year,
            "pollWeek": poll_week,
            "teamSet": chosen.as_dict(),
            "rows": rows,
            "note": note,
            "plansUrl": plan.PLANS_URL,
            "parts": statuses(parts, self.client._clock()),
        }

    # --- warm-up -------------------------------------------------------------------------------------

    def warm(self) -> dict[str, Any]:
        """Start loading the primary teams' pages in the background. Answers at once with what it does."""
        chosen = teamset.current(self.settings, self.prefs, self.client)
        schools = list(chosen.extra)
        if not chosen.allowed:
            return {"warming": [], "reason": "free_key"}
        if not schools:
            return {"warming": [], "reason": "no_primaries"}
        if self._warming is not None and not self._warming.done():
            return {"warming": schools, "reason": "already_running"}
        now = self.client._clock()
        if self._warmed_at is not None and now - self._warmed_at < WARM_EVERY:
            return {"warming": [], "reason": "recent"}
        self._warmed_at = now
        self._warming = asyncio.create_task(self._warm(schools))
        return {"warming": schools, "reason": None}

    async def _warm(self, schools: list[str]) -> None:
        for school in schools:
            try:
                result = await self.program.team_page(school)
            except Exception:  # one team's failure must not stop the others; it is logged in full
                log.exception("Warming the team page of %s failed", school)
                continue
            if result is None:
                log.warning("Primary team %s is not in CFBD's FBS list; its page was not warmed", school)
        log.info("Warmed the team pages of %s", ", ".join(schools))

    async def close(self) -> None:
        task = self._warming
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
