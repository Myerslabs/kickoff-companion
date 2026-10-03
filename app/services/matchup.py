"""UX-12: the matchup sheet for any two FBS teams (GET /api/matchup?away=&home=), built only from the
all-FBS answers the Season overview and the program already cache: /teams/fbs, /stats/season,
/stats/season/advanced, /ratings/sp, /talent, /rankings, /records and /games, each asked with the
same endpoint, parameters and kind as there, so a warm cache answers every one. It never touches
the per-school calls of the team page (games, media, roster, coaches, series, recruiting, usage,
play value).

Names are checked against /teams/fbs before anything else is asked for: an unknown team costs no
further part at all."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import AdvancedSeasonStat, Game, PollWeek, Team, TeamRecords, TeamSP, TeamStat, TeamTalent
from app.config import Settings
from app.services import gamekeys
from app.services.context16 import POLL_NAMES, _r, elo_path, form_for, form_table, num, whole
from app.services.logos import logo_fields
from app.services.parts import Assembled, Part, PartFetcher, assemble, statuses
from app.services.profiles import PROFILE_ROWS, Profiles, advanced_rows

log = logging.getLogger("kickoff.matchup")

NAME_LIMIT = 60
SLATE_WINDOW = timedelta(days=7)  # a game between the two within a week of now is "on this week's slate"
ADVANCED_GROUP = "Overall"  # the sheet keeps CFBD's headline efficiency rows; the program shows the rest


class UnknownTeam(LookupError):
    """A name that is not an FBS team this season (or two names for one team)."""


def _record(line: Any) -> dict[str, int | None] | None:
    if line is None:
        return None
    return {"games": whole(line.games), "wins": whole(line.wins), "losses": whole(line.losses), "ties": whole(line.ties)}


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def slate_game(games: list[Game], away: str, home: str, now: datetime) -> dict[str, Any] | None:
    """The game between the two teams closest to now, if it kicks off within a week either side of now."""
    best: tuple[float, Game] | None = None
    for g in games:
        if not isinstance(g, Game) or {g.home_team, g.away_team} != {away, home}:
            continue
        kickoff = _when(g.start_date)
        if kickoff is None:
            continue
        gap = abs((kickoff - now).total_seconds())
        if gap <= SLATE_WINDOW.total_seconds() and (best is None or gap < best[0]):
            best = (gap, g)
    if best is None:
        return None
    g = best[1]
    kickoff = _when(g.start_date)
    status = "final" if g.completed else ("underway" if kickoff is not None and kickoff <= now else "scheduled")
    return {
        "gameId": g.id, "week": whole(g.week), "postseason": gamekeys.label(g), "kickoff": g.start_date, "startTimeTbd": bool(g.start_time_tbd),
        "homeTeam": g.home_team, "awayTeam": g.away_team, "homePoints": whole(g.home_points), "awayPoints": whole(g.away_points),
        "neutralSite": bool(g.neutral_site), "venue": g.venue, "completed": bool(g.completed), "status": status,
    }


def latest_ranks(weeks: list[PollWeek]) -> tuple[dict[str, dict[str, int]], int | None]:
    pool = [w for w in weeks if isinstance(w, PollWeek) and whole(w.week) is not None]
    if not pool:
        return {}, None
    latest = max(pool, key=gamekeys.poll_order)
    out: dict[str, dict[str, int]] = {}
    for poll in latest.polls:
        short = POLL_NAMES.get(poll.poll)
        if short:
            out[short] = {r.school: r.rank for r in poll.ranks if whole(r.rank) is not None}
    return out, latest.week


def talent_ranks(records: list[TeamTalent]) -> dict[str, dict[str, Any]]:
    values = {r.team: v for r in records if isinstance(r, TeamTalent) and r.team and (v := num(r.talent)) is not None}
    ordered = sorted(values.items(), key=lambda item: -item[1])
    out: dict[str, dict[str, Any]] = {}
    last_value, last_rank = None, 0
    for index, (team, value) in enumerate(ordered, start=1):
        if value != last_value:
            last_rank, last_value = index, value
        out[team] = {"talent": round(value, 2), "rank": last_rank, "of": len(ordered)}
    return out


def two_team_rows(profiles: Profiles, advanced: list[AdvancedSeasonStat], away: str, home: str) -> list[dict[str, Any]]:
    """One row per stat with both teams' value and national rank: the per-game profile, then CFBD's
    headline efficiency rows."""
    rows = []
    for spec in PROFILE_ROWS:
        a, h = profiles.row(away, *spec), profiles.row(home, *spec)
        rows.append({"group": "Per game", "side": spec[0], "label": spec[1], "key": spec[2], "metric": f"profile:{spec[2]}", "format": spec[4], "higherIsBetter": spec[3], "of": a.get("nationalOf") or h.get("nationalOf"),
                     "away": {"value": a.get("value"), "rank": a.get("nationalRank")}, "home": {"value": h.get("value"), "rank": h.get("nationalRank")}})
    away_adv = {r["key"]: r for r in advanced_rows(advanced, away)}
    for h in advanced_rows(advanced, home):
        if h.get("group") != ADVANCED_GROUP:
            continue
        a = away_adv.get(h["key"], {})
        rows.append({"group": "Efficiency", "side": h["side"], "label": h["label"], "key": h["key"], "metric": h.get("metric") or f"advanced:{h['key']}", "format": h["format"], "higherIsBetter": h["higherIsBetter"], "of": h.get("nationalOf"),
                     "away": {"value": a.get("value"), "rank": a.get("nationalRank")}, "home": {"value": h.get("value"), "rank": h.get("nationalRank")}})
    return rows


class MatchupService:
    def __init__(self, client: CfbdClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.fetcher = PartFetcher(client, 4)

    @property
    def year(self) -> int:
        return self.settings.season

    def _f(self, name: str, endpoint: str, params: dict[str, Any], model: Any, kind: DataKind) -> Any:
        return self.fetcher.fetch(name, endpoint, params, model, kind)

    @staticmethod
    def resolve(teams: list[Team], name: str) -> str | None:
        """The FBS school for a name: exact first, then ignoring case."""
        schools = [t.school for t in teams if isinstance(t, Team) and t.school]
        if name in schools:
            return name
        folded = name.casefold()
        return next((s for s in schools if s.casefold() == folded), None)

    async def matchup(self, away: str, home: str) -> Assembled:
        """Raises UnknownTeam for a name that is not an FBS team this season, after asking for the
        teams list alone. A teams list that cannot be had comes back as an all-failed answer."""
        teams_part = await self._f("teams", "/teams/fbs", {"year": self.year}, Team, DataKind.TEAMS)
        now = self.client._clock()
        if not teams_part.ok:
            return assemble({"parts": statuses({"teams": teams_part}, now)}, {"teams": teams_part})
        away_name, home_name = self.resolve(teams_part.records, away), self.resolve(teams_part.records, home)
        if away_name is None or home_name is None:
            raise UnknownTeam(f"No FBS team called {away if away_name is None else home}.")
        if away_name == home_name:
            raise UnknownTeam("Pick two different teams.")

        fetched = await asyncio.gather(
            self._f("stats", "/stats/season", {"year": self.year, "classification": "fbs"}, TeamStat, DataKind.SEASON_STATS),
            self._f("advanced", "/stats/season/advanced", {"year": self.year, "classification": "fbs"}, AdvancedSeasonStat, DataKind.SEASON_STATS),
            self._f("sp", "/ratings/sp", {"year": self.year}, TeamSP, DataKind.SEASON_STATS),
            self._f("talent", "/talent", {"year": self.year}, TeamTalent, DataKind.SEASON_STATS),
            self._f("rankings", "/rankings", {"year": self.year}, PollWeek, DataKind.SCHEDULE),
            self._f("records", "/records", {"year": self.year}, TeamRecords, DataKind.SCHEDULE),
            self._f("games", "/games", {"year": self.year}, Game, DataKind.SCHEDULE),
        )
        parts: dict[str, Part] = {"teams": teams_part, **{part.name: part for part in fetched}}
        now = self.client._clock()
        profiles = Profiles(parts["stats"].records, parts["games"].records, self.settings.conference)
        ranks, poll_week = latest_ranks(parts["rankings"].records)
        records = {r.team: r for r in parts["records"].records if isinstance(r, TeamRecords)}
        sp = {r.team: r for r in parts["sp"].records if isinstance(r, TeamSP) and r.team}
        talent = talent_ranks(parts["talent"].records)
        form = form_table(parts["games"].records)
        meta = {t.school: t for t in teams_part.records if isinstance(t, Team) and t.school}

        def block(school: str) -> dict[str, Any]:
            t, rec, rating = meta.get(school), records.get(school), sp.get(school)
            return {
                "school": school, "abbreviation": t.abbreviation if t else None, "mascot": t.mascot if t else None, "conference": t.conference if t else None,
                "color": t.color if t else None, "altColor": t.alternate_color if t else None, **(logo_fields(t.id, t.logos) if t else {"logo": None, "logoDark": None}),  # NV: our own logo route, never the CDN
                "isUs": school == self.settings.team,
                "record": _record(rec.total) if rec else None, "conferenceRecord": _record(rec.conference_games) if rec else None,
                "apRank": ranks.get("AP", {}).get(school), "coachesRank": ranks.get("Coaches", {}).get(school), "cfpRank": ranks.get("CFP", {}).get(school),
                "sp": {"rating": _r(rating.rating, 1), "rank": whole(rating.ranking),
                       "offense": {"rating": _r(rating.offense.rating, 1) if rating.offense else None, "rank": whole(rating.offense.ranking) if rating.offense else None},
                       "defense": {"rating": _r(rating.defense.rating, 1) if rating.defense else None, "rank": whole(rating.defense.ranking) if rating.defense else None}} if rating else None,
                "talent": talent.get(school),
                "games": profiles.games_for(school),
                "form": form_for(form, school),
                "eloPath": elo_path(parts["games"].records, school),
            }

        data = {
            "season": self.year,
            "away": block(away_name),
            "home": block(home_name),
            "rows": two_team_rows(profiles, parts["advanced"].records, away_name, home_name),
            "game": slate_game(parts["games"].records, away_name, home_name, now),
            "pollWeek": poll_week,
            "parts": statuses(parts, now),
        }
        return assemble(data, parts)
