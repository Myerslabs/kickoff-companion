"""The scoreboard ticker (L10): every FBS game, scores only, with poll ranks (owner direction 2026-09-23:
all of college football, not just our conference and the Top 25).

It always starts from the week's `/games` list (the schedule lifetime: 15 minutes on a Saturday,
six hours on other days). With a Tier 1 key it reads `/scoreboard` (15-second cache) only while a
game on that slate is in progress or the engine's game window is open (Phase 11: before this,
any open Live sheet billed a scoreboard call every minute on any day); a fresh answer while the
window is open is handed to the engine's recorder and its win probability. Otherwise, and on the
Free tier, the slate itself is shown, refreshed every five minutes only while a game on it is
about to start or in progress (the owner approved about 40 calls a Saturday, 2026-09-23). Our game always
follows the spoiler delay: while the app is watching the game its line comes from the engine's
released events, and when it is not, the entry shows no score at all until the final.

Public release Phase 5b: two modes, set on the setup page and in Settings. National (the default) shows
every FBS game; My teams (a Tier 2 key) keeps only the games of the primary and secondary teams
(app/services/teamset.py). Both read the same slate, so the mode costs no call; a slate with none of my
teams falls back to every game with a note. Every entry says whether it is one of my teams."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import CalendarWeek, Game, PollWeek, ScoreboardGame, Team
from app.config import Settings
from app.live.engine import LiveEngine
from app.services import gamekeys, plan, teamset
from app.services.parts import Assembled, Part, PartFetcher, assemble, calendar_slot, statuses

ACTIVE_BEFORE = timedelta(hours=1)  # a game counts as active from an hour before kickoff
ACTIVE_AFTER = timedelta(hours=5)  # until five hours after, unless it is marked complete
REFRESH = timedelta(minutes=5)  # the owner's approved cadence for a paid key
LEAN_REFRESH = timedelta(minutes=20)  # the Free profile (public release Phase 5a): a free key's 1,000 calls last the month
STATUS_ORDER = {"live": 0, "pre": 1, "final": 2}
AP_POLL = "AP Top 25"


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _clock_text(period: Any, clock: Any) -> str | None:
    if not isinstance(period, int):
        return None
    label = f"Q{period}" if period <= 4 else "OT" if period == 5 else f"{period - 4}OT"
    if isinstance(clock, dict) and isinstance(clock.get("minutes"), int) and isinstance(clock.get("seconds"), int):
        return f"{label} {clock['minutes']}:{clock['seconds']:02d}"
    if isinstance(clock, str) and clock:
        return f"{label} {clock}"
    return label


class TickerService:
    def __init__(self, client: CfbdClient, settings: Settings, engine: LiveEngine, prefs: Any = None) -> None:
        self.client = client
        self.settings = settings
        self.engine = engine
        self.prefs = prefs  # the settings store (tickerMode and the team picks); None in older tests
        self.fetcher = PartFetcher(client, 3)

    @property
    def year(self) -> int:
        return self.settings.season

    @property
    def team(self) -> str:
        return self.settings.team

    # --- the answer --------------------------------------------------------------------------------

    async def ticker(self, delay: float) -> Assembled:
        now = self.client._clock()
        results = await asyncio.gather(
            self.fetcher.fetch("schedule", "/games", {"year": self.year, "team": self.team}, Game, DataKind.SCHEDULE),
            self.fetcher.fetch("teams", "/teams/fbs", {"year": self.year}, Team, DataKind.TEAMS),
            self.fetcher.fetch("rankings", "/rankings", {"year": self.year}, PollWeek, DataKind.SCHEDULE),
            self.fetcher.fetch("calendar", "/calendar", {"year": self.year}, CalendarWeek, DataKind.REFERENCE),
        )
        parts: dict[str, Part] = {part.name: part for part in results}
        # The calendar's week when today is inside one (a bye Saturday shows its own slate, Phase 12;
        # bowl season, Phase 15); else our week.
        slot = calendar_slot(parts["calendar"].records, now) or self._week(parts["schedule"].records, now)
        week, season_type = slot if slot else (None, "regular")
        teams = {t.school: t for t in parts["teams"].records if t.school}
        ap = self._ap(parts["rankings"].records)
        games: list[dict[str, Any]] = []
        source = "none"
        if week is not None:
            params: dict[str, Any] = {"year": self.year, "week": week}
            if season_type == gamekeys.POSTSEASON:
                params["seasonType"] = gamekeys.POSTSEASON
            slate = await self.fetcher.fetch("slate", "/games", params, Game, DataKind.SCHEDULE)
            if self.client.capabilities.scoreboard and (self.engine.window_open(now) or (slate.ok and self._in_progress(slate.records, now))):
                part = await self.fetcher.fetch("scoreboard", "/scoreboard", {"classification": "fbs"}, ScoreboardGame, DataKind.SCOREBOARD)
                parts["scoreboard"] = part
                if part.fetched is not None and part.fetched.source == "live":
                    await self.engine.record_scoreboard(part.fetched.payload)  # kept with the game's recording while its window is open
                source = "scoreboard"
                games = [await self._from_scoreboard(g, teams, ap, delay, now) for g in part.records]
            else:
                if slate.ok and self._active(slate.records, now):
                    slate = await self.fetcher.fetch("slate", "/games", params, Game, DataKind.TICKER, max_age=LEAN_REFRESH if plan.lean(self.client) else REFRESH)
                parts["slate"] = slate
                source = "games"
                records = self._bowl_day(slate.records, now) if season_type == gamekeys.POSTSEASON else slate.records
                games = [await self._from_game(g, teams, ap, delay, now) for g in records]
        kept = [g for g in games if g is not None]
        kept.sort(key=lambda g: (STATUS_ORDER.get(g["status"], 3), g.get("kickoff") or ""))
        mode, asked, mode_note, mine = self._mode(parts["teams"].records)
        for g in kept:
            g["isMine"] = g["isUs"] or g["home"]["school"] in mine or g["away"]["school"] in mine
        if mode == "mine":
            ours = [g for g in kept if g["isMine"]]
            if ours or not kept:
                kept = ours
            else:
                mode, mode_note = "national", "None of your teams play on this slate, so the ticker shows every game."
        data = {
            "season": self.year,
            "week": week,
            "source": source,
            "delaySeconds": delay,
            "mode": mode,
            "modeAsked": asked,
            "refreshMinutes": int((LEAN_REFRESH if plan.lean(self.client) else REFRESH).total_seconds() // 60),  # the slate's cadence while games are on
            "modeNote": mode_note,
            "games": kept,
            "note": None if week is not None else "No week of ours to show yet.",
            "parts": statuses(parts, self.client._clock()),
        }
        return assemble(data, parts)

    # --- which week, which games -------------------------------------------------------------------

    def _mode(self, teams: list[Team]) -> tuple[str, str, str | None, frozenset[str]]:
        """(mode shown, mode asked for, a note, my teams). My teams needs a Tier 2 key; asked for without
        one, the ticker shows every game and says why."""
        prefs = getattr(self.prefs, "prefs", None)
        asked = getattr(prefs, "tickerMode", "national")
        asked = asked if asked in ("national", "mine") else "national"
        mine = teamset.current(self.settings, self.prefs, self.client, teams).mine()
        if asked == "mine" and not plan.allows_liked(self.client.capabilities):
            return "national", asked, "The My teams ticker needs a Tier 2 key, so it shows every game.", mine
        return asked, asked, None, mine

    def _week(self, games: list[Game], now: datetime) -> tuple[int, str] | None:
        """(week, seasonType) of our game today, else the next one, else the last one played."""
        today = now.astimezone(self.settings.tzinfo).date()
        dated = [(g, _utc(g.start_date)) for g in games if isinstance(g.week, int)]
        slot = lambda g: (g.week, g.season_type or "regular")  # noqa: E731
        todays = [g for g, k in dated if k is not None and k.astimezone(self.settings.tzinfo).date() == today]
        if todays:
            return slot(todays[0])
        upcoming = [(g, k) for g, k in dated if k is not None and k >= now]
        if upcoming:
            return slot(min(upcoming, key=lambda gk: gk[1])[0])
        played = [g for g, _ in dated if g.completed]
        return slot(max(played, key=gamekeys.order)) if played else None

    def _bowl_day(self, games: list[Game], now: datetime) -> list[Game]:
        """The postseason is one CFBD week of a month: the ticker carries the games of today, or of the
        next day that has any, not all 46 bowls."""
        tz = self.settings.tzinfo
        dated = [(g, k.astimezone(tz).date()) for g in games if (k := _utc(g.start_date)) is not None]
        today = now.astimezone(tz).date()
        days = sorted({d for _, d in dated if d >= today})
        if not days:
            days = sorted({d for _, d in dated})[-1:]
        return [g for g, d in dated if days and d == days[0]]

    def _ap(self, weeks: list[PollWeek]) -> dict[str, int]:
        pool = [w for w in weeks if isinstance(w.week, int)]
        if not pool:
            return {}
        latest = max(pool, key=gamekeys.poll_order)
        for poll in latest.polls:
            if poll.poll == AP_POLL:
                return {r.school: r.rank for r in poll.ranks if isinstance(r.rank, int)}
        return {}

    def _active(self, games: list[Game], now: datetime) -> bool:
        for g in games:
            kickoff = _utc(g.start_date)
            if kickoff is None or g.completed:
                continue
            if now - ACTIVE_AFTER <= kickoff <= now + ACTIVE_BEFORE:
                return True
        return False

    def _in_progress(self, games: list[Game], now: datetime) -> bool:
        """A game on the slate has kicked off and is not marked complete (at most five hours back,
        since the cached slate can be a few minutes behind the final)."""
        for g in games:
            kickoff = _utc(g.start_date)
            if kickoff is None or g.completed or g.start_time_tbd:
                continue
            if now - ACTIVE_AFTER <= kickoff <= now:
                return True
        return False

    def _keep(self, home: str | None, away: str | None, home_class: str | None, away_class: str | None, teams: dict[str, Team]) -> bool:
        """Every game with an FBS side: the /teams/fbs list decides, with the record's own classification as a hint."""
        if not home or not away:
            return False
        return home in teams or away in teams or "fbs" in (str(home_class or "").lower(), str(away_class or "").lower())

    # --- one entry -----------------------------------------------------------------------------------

    def _side(self, school: str, points: Any, teams: dict[str, Team], ap: dict[str, int]) -> dict[str, Any]:
        team = teams.get(school)
        abbr = (team.abbreviation if team and team.abbreviation else school[:4]).upper()
        return {"school": school, "abbr": abbr, "points": points if isinstance(points, int) and not isinstance(points, bool) else None, "rank": ap.get(school)}

    def _time_text(self, kickoff: datetime | None, tbd: Any) -> str:
        if tbd or kickoff is None:
            return "TBD"
        local = kickoff.astimezone(self.settings.tzinfo)
        return f"{local.hour % 12 or 12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"

    async def _ours(self, game_id: int, status: str, detail: str | None, home_pts: Any, away_pts: Any, delay: float) -> tuple[str, str | None, Any, Any]:
        """Our game's entry never runs ahead of the delayed live sheet."""
        engine = self.engine
        if engine.current_game_id == game_id and engine.mode in ("live", "replay"):
            state = await asyncio.to_thread(engine.state, delay, game_id)
            if state:
                s = state.get("status")
                kind = "final" if s == "final" else "pre" if s == "pre" else "live"
                text = "Final" if kind == "final" else _clock_text(state.get("period"), state.get("clock")) or ("In progress" if kind == "live" else detail)
                return kind, text, state.get("homeScore"), state.get("awayScore")
        if status == "live":
            return "live", "In progress", None, None
        return status, detail, home_pts, away_pts

    async def _from_game(self, g: Game, teams: dict[str, Team], ap: dict[str, int], delay: float, now: datetime) -> dict[str, Any] | None:
        if not self._keep(g.home_team, g.away_team, g.home_classification, g.away_classification, teams):
            return None
        kickoff = _utc(g.start_date)
        if g.completed:
            status, detail = "final", "Final"
        elif kickoff is not None and kickoff <= now:
            status, detail = "live", "In progress"
        else:
            status, detail = "pre", self._time_text(kickoff, g.start_time_tbd)
        is_us = self.team in (g.home_team, g.away_team)
        home_pts, away_pts = g.home_points, g.away_points
        if is_us:
            status, detail, home_pts, away_pts = await self._ours(g.id, status, detail, home_pts, away_pts, delay)
        return {
            "gameId": g.id,
            "status": status,
            "detail": detail,
            "kickoff": kickoff.isoformat() if kickoff else None,
            "startTimeTbd": bool(g.start_time_tbd),
            "isUs": is_us,
            "home": self._side(g.home_team or "", home_pts, teams, ap),
            "away": self._side(g.away_team or "", away_pts, teams, ap),
        }

    def _school(self, side: Any, teams: dict[str, Team]) -> str | None:
        """The scoreboard names teams with their mascot ("Michigan Wolverines", verified 2026-09-23). Resolve
        by team id first, then by the longest school name the display name starts with."""
        if side is None:
            return None
        team_id = getattr(side, "id", None)
        if isinstance(team_id, int):
            for team in teams.values():
                if team.id == team_id:
                    return team.school
        name = getattr(side, "name", None)
        if not isinstance(name, str) or not name:
            return None
        if name in teams:
            return name
        matches = [school for school in teams if name.startswith(school + " ")]
        return max(matches, key=len) if matches else name

    async def _from_scoreboard(self, g: ScoreboardGame, teams: dict[str, Team], ap: dict[str, int], delay: float, now: datetime) -> dict[str, Any] | None:
        home = self._school(g.home_team, teams)
        away = self._school(g.away_team, teams)
        if not self._keep(home, away, g.home_team.classification if g.home_team else None, g.away_team.classification if g.away_team else None, teams):
            return None
        kickoff = _utc(g.start_date)
        raw = str(g.status or "").lower()
        if raw in ("completed", "final"):
            status, detail = "final", "Final"
        elif raw == "in_progress":
            status, detail = "live", _clock_text(g.period, g.clock) or "In progress"
        else:
            status, detail = "pre", self._time_text(kickoff, g.start_time_tbd)
        is_us = self.team in (home, away)
        home_pts = g.home_team.points if g.home_team else None
        away_pts = g.away_team.points if g.away_team else None
        if is_us:
            status, detail, home_pts, away_pts = await self._ours(g.id, status, detail, home_pts, away_pts, delay)
        return {
            "gameId": g.id,
            "status": status,
            "detail": detail,
            "kickoff": kickoff.isoformat() if kickoff else None,
            "startTimeTbd": bool(g.start_time_tbd),
            "isUs": is_us,
            "home": self._side(home or "", home_pts, teams, ap),
            "away": self._side(away or "", away_pts, teams, ap),
        }
