"""National lists (Phase 16, feature N1, the zero-call part): every team or player behind a rank chip,
ranked exactly as the chip is, from answers the pages already cache.

GET /api/national/{metric}?team=&year=&scope=national|conference&conf= answers one list. The metric
key names the family and the stat (the METRICS registry below): profile:<key>, advanced:<key>,
adjusted:<key>, rating:<key>, board:<board id>, poll:<AP|Coaches|CFP>, class:<year>. Every page row
with a national list carries its key (`metric`, or usMetric and themMetric on two-team rows), so the
front end never guesses one.

Zero extra calls. Each family asks for the byte-identical (endpoint, params, DataKind) its source
page asks for, through that page's own fetcher (so a big answer is parsed once), and ranks with the
same code: Profiles.ranked for the stat profile, rank_teams for the advanced and adjusted stats, the
rating tables for SP+, Elo, FPI, talent, CORE, SRS and strength of schedule, national_board and
ppa_national for the player boards. A list the chip's page loaded is a cache hit; on a cold cache
it costs what that page would, through the quota guard. `team` only highlights a row and never
changes a fetch; `year` is this season or last season only (the profile family), so no year can
cost a call nobody else makes.

The extra-call families (recruit:<year>, returning:<key>, bluechip:ratio; stream NV) live in
national_extra.py: resolve() asks it for their registry entries and FAMILIES holds their builders.
They cost calls the first time (no page loads those answers), through the same fetcher and guard.

Every list also marks the next opponent (isNext, and `next`), from our schedule the Season
page already caches (stream NV).

Public release Phase 5b adds two scopes to every list: `opponents` (the home team and every team on its
schedule) and `mine` (the primary and secondary teams, a Tier 2 key; app/services/teamset.py). Both are
the national list cut down, so every rank stays the national rank and neither costs a call."""

from __future__ import annotations

import asyncio
import dataclasses
import re
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import (
    AdjustedTeamMetrics,
    AdvancedSeasonStat,
    Game,
    KickerPAAR,
    PlayerSeasonPpa,
    PlayerStat,
    PlayerWeightedEPA,
    PollWeek,
    Team,
    TeamCoreRating,
    TeamElo,
    TeamFPI,
    TeamRecruitingRanking,
    TeamSP,
    TeamSRS,
    TeamStat,
    TeamTalent,
)
from app.config import Settings
from app.services import gamekeys, national_extra, plan, teamset
from app.services.depth2 import ADJUSTED_BOARDS, ADJUSTED_KEYS, adjusted_board_rows, adjusted_rows, adjusted_source_rows, core_tables, shared_ranks, sos_table, srs_table
from app.services.depth2 import num as finite
from app.services.logos import logo_fields
from app.services.parts import Assembled, Part, PartFetcher, assemble, statuses
from app.services.players import BOARDS, PPA_MIN_PLAYS, Board, Line, fbs_lines, lines_from, national_board, ppa_national
from app.services.profiles import ADVANCED_ROWS, PROFILE_ROWS, advanced_key, advanced_values, profiles_for, rank_teams, ranked_list
from app.services.stats_extra import elo_table, fpi_tables, sp_tables, talent_table

METRIC_PATTERN = re.compile(r"^[a-z]+:[A-Za-z0-9_:]+$")
MAX_METRIC = 60
MAX_TEAM = 80
MAX_CONFERENCE = 60
PLAYER_CUT = 100  # owner answer 2 (2026-09-28): the top 100, then every one of ours below the cut
SCOPES = ("national", "conference")
TEAM_SET_SCOPES = ("opponents", "mine")  # public release Phase 5b: the national list cut to a set of teams
POLLS = {"AP": "AP Top 25", "Coaches": "Coaches Poll", "CFP": "Playoff Committee Rankings"}
POLL_LABELS = {"AP": "AP Top 25", "Coaches": "Coaches Poll", "CFP": "College Football Playoff rankings"}


@dataclass(frozen=True)
class Metric:
    """One national list: what it ranks and how its rows read."""

    key: str
    family: str
    id: str
    label: str
    format: str
    higher: bool
    unit: str = "team"  # "team" | "player"
    side: str | None = None
    group: str | None = None
    scopes: tuple[str, ...] = SCOPES
    population: str = "FBS teams"
    rank_source: str = "local"  # "local" (the tie rule here) | "cfbd" (CFBD's own ranking)
    value_label: str | None = None
    last_season: bool = False  # the profile family also answers ?year=<season - 1>


# (id, label, format, higher is better, population, rank source)
RATINGS: list[tuple[str, str, str, bool, str, str]] = [
    ("sp", "SP+ overall", "1f", True, "FBS teams", "cfbd"),
    ("spOffense", "SP+ offense", "1f", True, "FBS teams", "cfbd"),
    ("spDefense", "SP+ defense", "1f", False, "FBS teams", "cfbd"),
    ("spSpecial", "SP+ special teams", "2f", True, "FBS teams", "local"),
    ("sosPlayed", "Strength of schedule played (average SP+ of opponents)", "1f", True, "FBS teams that have played an SP+ rated opponent", "local"),
    ("elo", "Elo", "0f", True, "FBS teams", "local"),
    ("fpi", "FPI", "1f", True, "FBS teams", "cfbd"),
    ("fpiSos", "FPI strength of schedule", "rank", True, "FBS teams (ESPN's FPI résumé rank)", "cfbd"),
    ("fpiSor", "FPI strength of record", "rank", True, "FBS teams (ESPN's FPI résumé rank)", "cfbd"),
    ("talent", "Talent composite", "2f", True, "FBS teams", "local"),
    ("core", "CORE rating", "2f", True, "FBS teams", "local"),
    ("coreOffense", "CORE offense", "2f", True, "FBS teams", "local"),
    ("coreDefense", "CORE defense", "2f", False, "FBS teams", "local"),
    ("srs", "SRS", "1f", True, "Division I teams (CFBD's SRS ranking)", "cfbd"),
]
VALUELESS = {"fpiSos", "fpiSor"}  # CFBD sends the rank only


def _registry() -> dict[str, Metric]:
    out: dict[str, Metric] = {}
    for side, label, key, higher, fmt in PROFILE_ROWS:
        out[f"profile:{key}"] = Metric(f"profile:{key}", "profile", key, label, fmt, higher, side=side, last_season=True)
    for side, label, attr, higher, fmt, group in ADVANCED_ROWS:
        key = advanced_key(side, attr)
        out[f"advanced:{key}"] = Metric(f"advanced:{key}", "advanced", key, label, fmt, higher, side=side, group=group)
    for key, label, _read, higher, fmt in ADJUSTED_KEYS:
        out[f"adjusted:{key}"] = Metric(f"adjusted:{key}", "adjusted", key, label, fmt, higher)
    for key, label, fmt, higher, population, source in RATINGS:
        scopes = SCOPES
        out[f"rating:{key}"] = Metric(f"rating:{key}", "rating", key, label, fmt, higher, scopes=scopes, population=population, rank_source=source)
    for board in BOARDS:
        population = "FBS punters with 5 or more punts" if board.min_stat else "FBS players"
        out[f"board:{board.id}"] = Metric(f"board:{board.id}", "board", board.id, board.label, board.format, True, unit="player", population=population)
    out["board:ppa:all"] = Metric("board:ppa:all", "board", "ppa:all", "Play value, PPA per play", "+2f", True, unit="player", population=f"FBS players with {PPA_MIN_PLAYS} or more plays")
    for board_id, label, _stat, fmt, _detail, _note in ADJUSTED_BOARDS:
        out[f"board:{board_id}"] = Metric(f"board:{board_id}", "board", board_id, label, fmt, True, unit="player", population="FBS players")
    for short in POLLS:
        out[f"poll:{short}"] = Metric(f"poll:{short}", "poll", short, POLL_LABELS[short], "0f", True, scopes=("national",), population=f"The {POLL_LABELS[short]}", rank_source="cfbd", value_label="Points")
    return out


METRICS: dict[str, Metric] = _registry()


def class_metric(year: int) -> Metric:
    return Metric(f"class:{year}", "class", str(year), f"{year} recruiting class", "2f", True, scopes=("national",), population="Division I classes (247Sports composite)", rank_source="cfbd", value_label="Points")


def resolve(metric: Any, season: int) -> Metric | None:
    """The metric for a key, or None for anything malformed or unknown (checked before any fetch)."""
    if not isinstance(metric, str) or len(metric) > MAX_METRIC or not METRIC_PATTERN.match(metric):
        return None
    if metric in METRICS:
        return METRICS[metric]
    family, _, rest = metric.partition(":")
    if family == "class" and rest.isdigit() and int(rest) in (season, season + 1):  # the Recruiting page's two classes
        return class_metric(int(rest))
    extra = national_extra.spec(metric, season)  # stream NV: the extra-call lists
    return Metric(**extra) if extra else None


@dataclass
class Request:
    """A validated list request."""

    metric: Metric
    year: int
    scope: str
    conference: str | None  # asked for; resolved against the data for a conference list
    team: str | None


def validate(metric: Any, *, team: Any, year: Any, scope: Any, conf: Any, season: int) -> Request | str:
    """A Request, or the reason for a 404. Nothing here fetches."""
    found = resolve(metric, season)
    if found is None:
        return "No national list with that name."
    if team is not None and (not isinstance(team, str) or len(team.strip()) > MAX_TEAM):
        return "That team name is too long."
    name = team.strip() if isinstance(team, str) and team.strip() else None
    if year in (None, ""):
        asked = season
    elif isinstance(year, str) and year.strip().isdigit():
        asked = int(year.strip())
    else:
        return "The year must be this season or last season."
    allowed = {season, season - 1} if found.last_season else {season}
    if asked not in allowed:
        return f"This list covers {' and '.join(str(y) for y in sorted(allowed, reverse=True))} only."
    chosen = (scope.strip() if isinstance(scope, str) and scope.strip() else "national")
    if chosen not in found.scopes and chosen not in TEAM_SET_SCOPES:
        return f"This list has no {chosen} scope."
    if conf is not None and (not isinstance(conf, str) or len(conf.strip()) > MAX_CONFERENCE):
        return "That conference name is too long."
    return Request(found, asked, chosen, conf.strip() if isinstance(conf, str) and conf.strip() else None, name)


# --- rows --------------------------------------------------------------------------------------------------------


@dataclass
class Ranked:
    """What a family builder hands back: the list in scope order plus the facts around it."""

    rows: list[dict[str, Any]]  # rank, tied, value, and identity; team or player
    of: int
    unranked: int | None
    conference: str | None  # the conference a conference list covers
    known: bool  # the population loaded, so an unknown conference is a 404 rather than an outage
    rank_source: str | None = None
    note: str | None = None
    conferences: set[str] | None = None  # conferences seen in the population, beside /teams/fbs's


def _round(value: Any, digits: int = 4) -> float | None:
    return round(value, digits) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _team_rows(listing: list[tuple[str, Any, int, bool]], conference_of: Callable[[str], str | None], digits: int = 4, national: dict[str, int] | None = None, extra: Callable[[str], dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = []
    for team, value, rank, tied in listing:
        row = {"rank": rank, "tied": tied, "team": team, "conference": conference_of(team), "value": _round(value, digits)}
        if national is not None:
            row["nationalRank"] = national.get(team)
        if extra is not None:
            row.update(extra(team))
        rows.append(row)
    return rows


def _tied(rows: list[dict[str, Any]]) -> None:
    counts = Counter(r["rank"] for r in rows if r.get("rank") is not None)
    for r in rows:
        r["tied"] = counts.get(r.get("rank"), 0) > 1


def _conference_values(values: dict[str, Any], conference_of: Callable[[str], str | None], conference: str) -> dict[str, Any]:
    return {t: v for t, v in values.items() if conference_of(t) == conference}


# --- the service -------------------------------------------------------------------------------------------------


Builder = Callable[["NationalService", Request, dict[str, Part], dict[str, dict[str, Any]]], Awaitable[Ranked]]


class NationalService:
    """Serves the lists through the fetchers of the pages whose chips open them (the season,
    players and ratings services), so every answer is parsed once and every key is shared."""

    def __init__(self, client: CfbdClient, settings: Settings, season_fetcher: PartFetcher, players_fetcher: PartFetcher, ratings_fetcher: PartFetcher, prefs: Any = None) -> None:
        self.client = client
        self.settings = settings
        self.prefs = prefs  # the settings store, for the My teams scope (Phase 5b); None in older tests
        self.season_fetcher = season_fetcher
        self.players_fetcher = players_fetcher
        self.ratings_fetcher = ratings_fetcher

    @property
    def season(self) -> int:
        return self.settings.season

    # --- fetches: each the byte-identical (endpoint, params, kind) of its source page ----------------------------

    def _teams(self) -> Awaitable[Part]:
        return self.season_fetcher.fetch("teams", "/teams/fbs", {"year": self.season}, Team, DataKind.TEAMS)

    def _schedule(self) -> Awaitable[Part]:
        """Our schedule, the Season page's key: the next opponent is marked in every list (NV)."""
        return self.season_fetcher.fetch("schedule", "/games", {"year": self.season, "team": self.settings.team}, Game, DataKind.SCHEDULE)

    def _next_opponent(self, part: Part) -> str | None:
        upcoming = sorted((g for g in part.records if isinstance(g, Game) and not g.completed and g.week is not None), key=gamekeys.order)
        return gamekeys.opponent_of(upcoming[0], self.settings.team) if upcoming else None

    async def _gather(self, *fetches: Awaitable[Part]) -> dict[str, Part]:
        return {part.name: part for part in await asyncio.gather(*fetches)}

    # --- entry --------------------------------------------------------------------------------------------------------

    async def listing(self, req: Request) -> Assembled | str:
        """The list, or a 404 reason when the conference asked for is not in a list that loaded."""
        builder = FAMILIES[req.metric.family]
        if req.scope == "mine" and not plan.allows_liked(self.client.capabilities):
            return "The My teams list needs a Tier 2 key."
        teams_part, schedule_part = await asyncio.gather(self._teams(), self._schedule())
        parts: dict[str, Part] = {"teams": teams_part, "schedule": schedule_part}
        meta = self._team_meta(teams_part)
        keep: set[str] | None = None
        if req.scope in TEAM_SET_SCOPES:  # the national list, cut down after ranking
            keep = self._scope_teams(req.scope, teams_part, schedule_part)
            ranked = await builder(self, dataclasses.replace(req, scope="national"), parts, meta)
        else:
            ranked = await builder(self, req, parts, meta)
        if req.scope == "conference" and ranked.known and ranked.conference is not None:
            seen = {v["conference"] for v in meta.values() if v.get("conference")} | (ranked.conferences or set())
            if ranked.conference not in seen:
                return f"No team in this list plays in the {ranked.conference}."
        return assemble(self._data(req, ranked, parts, meta, self._next_opponent(schedule_part), keep), parts)

    def _scope_teams(self, scope: str, teams_part: Part, schedule_part: Part) -> set[str]:
        """The teams an opponents or My teams list keeps. The home team is in both, so it can be compared."""
        home = self.settings.team
        if scope == "opponents":
            return {home, *teamset.opponents(schedule_part.records, home)}
        return set(teamset.current(self.settings, self.prefs, self.client, teams_part.records).mine())

    @staticmethod
    def _team_meta(part: Part) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for t in part.records:
            if t.school:
                out[t.school] = {"abbreviation": t.abbreviation, "conference": t.conference, **logo_fields(t.id, t.logos)}
        return out

    def _scope_conference(self, req: Request, own: Callable[[str], str | None]) -> str | None:
        """The conference of a conference list: the one asked for, else the highlighted team's,
        else the configured one (the Season page's conference chips)."""
        if req.scope != "conference":
            return None
        if req.conference:
            return req.conference
        if req.team and own(req.team):
            return own(req.team)
        return self.settings.conference

    def _data(self, req: Request, ranked: Ranked, parts: dict[str, Part], meta: dict[str, dict[str, Any]], next_team: str | None = None, keep: set[str] | None = None) -> dict[str, Any]:
        m = req.metric
        us_team, focus = self.settings.team, req.team
        for row in ranked.rows:
            team = row.get("team") or ""
            info = meta.get(team, {})
            row.setdefault("abbreviation", info.get("abbreviation"))
            row["logo"], row["logoDark"] = info.get("logo"), info.get("logoDark")
            if not row.get("conference"):
                row["conference"] = info.get("conference")
            row["isUs"] = team == us_team
            row["isFocus"] = bool(focus) and team == focus
            row["isNext"] = bool(next_team) and team == next_team
        rows, beyond, cut = (ranked.rows if keep is None else [r for r in ranked.rows if r.get("team") in keep]), [], None
        if m.unit == "player" and len(rows) > PLAYER_CUT:
            cut = PLAYER_CUT
            beyond = [r for r in rows[PLAYER_CUT:] if r["isUs"] or r["isFocus"]]
            rows = rows[:PLAYER_CUT]
        everyone = ranked.rows
        mine = next((r for r in everyone if r["isUs"]), None)
        us = {"team": us_team, "rank": mine["rank"] if mine else None, "value": mine["value"] if mine else None, "of": ranked.of or None}
        if m.unit == "player":
            us.update({"playerId": mine.get("playerId") if mine else None, "player": mine.get("player") if mine else None})
        focus_row = next((r for r in everyone if r["isFocus"]), None) if focus else None
        focus_block = {"team": focus, "rank": focus_row["rank"] if focus_row else None, "value": focus_row["value"] if focus_row else None} if focus else None
        if focus and m.unit == "player" and focus_row:
            focus_block.update({"playerId": focus_row.get("playerId"), "player": focus_row.get("player")})
        noun = "players" if m.unit == "player" else "teams"
        if req.scope == "opponents":
            population = f"{us_team} and its opponents, ranked nationally"
        elif req.scope == "mine":
            population = f"My teams, ranked nationally ({m.population})"
        elif req.scope == "national":
            population = m.population
        else:
            population = f"{ranked.conference} {noun}"
        scopes = [*m.scopes, "opponents", *(["mine"] if plan.allows_liked(self.client.capabilities) else [])]
        return {
            "metric": m.key,
            "family": m.family,
            "key": m.id,
            "label": m.label,
            "side": m.side,
            "group": m.group,
            "format": m.format,
            "higherIsBetter": m.higher,
            "valueLabel": m.value_label or m.label,
            "valueless": m.id in VALUELESS and m.family == "rating",
            "season": self.season,
            "year": req.year,
            "years": [self.season, self.season - 1] if m.last_season else [self.season],
            "scope": req.scope,
            "scopes": scopes,
            "scopeTeams": len(keep) if keep is not None else None,
            "conference": ranked.conference,
            "unit": m.unit,
            "population": population,
            "rankSource": ranked.rank_source or m.rank_source,
            "tiesShare": True,
            "of": ranked.of or None,
            "unranked": ranked.unranked,
            "rows": rows,
            "beyond": beyond,
            "cut": cut,
            "shown": len(rows) + len(beyond),
            "us": us,
            "focus": focus_block,
            "next": next_team,
            "note": ranked.note,
            "parts": statuses(parts, self.client._clock()),
        }

    # --- families -----------------------------------------------------------------------------------------------------

    async def _profile(self, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
        year, last = req.year, req.year == self.season - 1
        f = self.season_fetcher
        if last:  # season.py and program.py ask for last season as HISTORY (kept 30 days)
            got = await self._gather(
                f.fetch("lastStats", "/stats/season", {"year": year, "classification": "fbs"}, TeamStat, DataKind.HISTORY),
                f.fetch("lastGames", "/games", {"year": year}, Game, DataKind.HISTORY),
            )
            stats, league, own = got["lastStats"], got["lastGames"], None
        else:
            got = await self._gather(
                f.fetch("stats", "/stats/season", {"year": year, "classification": "fbs"}, TeamStat, DataKind.SEASON_STATS),
                f.fetch("games", "/games", {"year": year}, Game, DataKind.SCHEDULE),
                f.fetch("schedule", "/games", {"year": year, "team": self.settings.team}, Game, DataKind.SCHEDULE),
            )
            stats, league, own = got["stats"], got["games"], got["schedule"]
        parts.update(got)
        m = req.metric
        profiles = profiles_for(stats.records, league.records, own.records if own else [], self.settings.conference, self.settings.team)

        def conference_of(team: str) -> str | None:
            return profiles.conference_of.get(team) or meta.get(team, {}).get("conference")

        conference = self._scope_conference(req, conference_of)
        national = profiles.ranked(m.id, m.higher, "national")
        listing = profiles.ranked(m.id, m.higher, req.scope, conference) if conference else national
        nat_ranks = {team: rank for team, _, rank, _ in national}
        rows = _team_rows(listing, conference_of, 3, nat_ranks if conference else None)
        population = [t for t in profiles.teams() if conference is None or conference_of(t) == conference]
        note = None
        if m.id in ("ppg", "opp_ppg") and not profiles.points_ranked:
            note = "Points need every FBS game of the season; that answer did not load, so this list is empty."
        return Ranked(rows, len(listing), max(0, len(population) - len(listing)), conference, stats.ok, note=note, conferences=set(profiles.conference_of.values()))

    async def _advanced(self, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
        got = await self._gather(self.season_fetcher.fetch("advanced", "/stats/season/advanced", {"year": self.season, "classification": "fbs"}, AdvancedSeasonStat, DataKind.SEASON_STATS))
        parts.update(got)
        records = got["advanced"].records
        spec = next(s for s in ADVANCED_ROWS if advanced_key(s[0], s[2]) == req.metric.id)
        values = advanced_values(records, spec[0], spec[2])
        own = {r.team: r.conference for r in records if isinstance(r.conference, str) and r.conference}

        def conference_of(team: str) -> str | None:
            return own.get(team) or meta.get(team, {}).get("conference")

        conference = self._scope_conference(req, conference_of)
        nat_ranks, _ = rank_teams(values, req.metric.higher)
        scoped = _conference_values(values, conference_of, conference) if conference else values
        listing = ranked_list(scoped, req.metric.higher, None if conference else nat_ranks)
        rows = _team_rows(listing, conference_of, 4, nat_ranks if conference else None)
        population = {r.team for r in records if conference is None or conference_of(r.team) == conference}
        return Ranked(rows, len(listing), max(0, len(population) - len(listing)), conference, got["advanced"].ok, conferences=set(own.values()))

    async def _adjusted(self, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
        got = await self._gather(self.ratings_fetcher.fetch("adjusted", "/wepa/team/season", {"year": self.season}, AdjustedTeamMetrics, DataKind.SEASON_STATS))
        parts.update(got)
        records = got["adjusted"].records
        table = adjusted_rows(records)
        key = req.metric.id
        values = {t: v[key]["value"] for t, v in table.items() if v.get(key, {}).get("rank") is not None}
        nat_ranks = {t: v[key]["rank"] for t, v in table.items() if v.get(key, {}).get("rank") is not None}
        own = {r.team: r.conference for r in records if isinstance(r.conference, str) and r.conference}

        def conference_of(team: str) -> str | None:
            return own.get(team) or meta.get(team, {}).get("conference")

        conference = self._scope_conference(req, conference_of)
        if conference:
            scoped = _conference_values(values, conference_of, conference)
            # the rank within the conference comes from the unrounded values, as adjusted_rows ranks
            raw = {t: v for t, v in _raw_adjusted(records, key).items() if t in scoped}
            listing = [(t, values[t], rank, tied) for t, _v, rank, tied in ranked_list(raw, req.metric.higher)]
        else:
            listing = ranked_list(values, req.metric.higher, nat_ranks)
        rows = _team_rows(listing, conference_of, 4, nat_ranks if conference else None)
        population = {t for t in table if conference is None or conference_of(t) == conference}
        return Ranked(rows, len(listing), max(0, len(population) - len(listing)), conference, got["adjusted"].ok, conferences=set(own.values()))

    async def _rating(self, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
        key = req.metric.id
        f = self.ratings_fetcher
        year = self.season
        fbs = {t for t in meta} or None
        if key.startswith("sp"):
            got = await self._gather(f.fetch("sp", "/ratings/sp", {"year": year}, TeamSP, DataKind.SEASON_STATS))
            table = sp_tables(got["sp"].records, fbs)[key]
        elif key == "sosPlayed":
            got = await self._gather(f.fetch("sp", "/ratings/sp", {"year": year}, TeamSP, DataKind.SEASON_STATS), f.fetch("games", "/games", {"year": year}, Game, DataKind.SCHEDULE))
            table = sos_table(got["games"].records, got["sp"].records, fbs)
        elif key == "elo":
            got = await self._gather(f.fetch("elo", "/ratings/elo", {"year": year}, TeamElo, DataKind.SEASON_STATS))
            table = elo_table(got["elo"].records, fbs)
        elif key.startswith("fpi"):
            got = await self._gather(f.fetch("fpi", "/ratings/fpi", {"year": year}, TeamFPI, DataKind.SEASON_STATS))
            table = fpi_tables(got["fpi"].records, fbs)[key]
        elif key == "talent":
            got = await self._gather(f.fetch("talent", "/talent", {"year": year}, TeamTalent, DataKind.SEASON_STATS))
            table = talent_table(got["talent"].records, fbs)
        elif key.startswith("core"):
            got = await self._gather(f.fetch("core", "/ratings/core", {"year": year}, TeamCoreRating, DataKind.SEASON_STATS))
            table = core_tables(got["core"].records, fbs)[key]
        else:  # srs
            got = await self._gather(f.fetch("srs", "/ratings/srs", {"year": year}, TeamSRS, DataKind.SEASON_STATS))
            table = srs_table(got["srs"].records)
        parts.update(got)
        source = next(iter(got.values()))

        def conference_of(team: str) -> str | None:
            return table.conference.get(team) or meta.get(team, {}).get("conference")

        conference = self._scope_conference(req, conference_of)
        rank_source = table.source
        if conference:
            ranked_teams = {t for t in table.ranks if conference_of(t) == conference}
            if key in VALUELESS:  # CFBD's rank only: the conference list keeps its order
                listing = [(t, None, rank, tied) for t, _v, rank, tied in ranked_list({t: table.ranks[t] for t in ranked_teams}, False)]
            else:
                listing = ranked_list({t: table.values[t] for t in ranked_teams if table.values.get(t) is not None}, table.higher)
            rank_source = "local"
        else:
            listing = table.listing()
        rows = _team_rows(listing, conference_of, 2 if key == "talent" else 4, table.ranks if conference else None)
        population = {t for t in table.values if conference is None or conference_of(t) == conference}
        return Ranked(rows, len(listing), max(0, len(population) - len(listing)), conference, source.ok, rank_source, conferences=set(table.conference.values()))

    async def _poll(self, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
        got = await self._gather(self.season_fetcher.fetch("rankings", "/rankings", {"year": self.season}, PollWeek, DataKind.SCHEDULE))
        parts.update(got)
        name = POLLS[req.metric.id]
        best = None
        for week in got["rankings"].records:  # the latest week that has this poll (the committee ranks from November)
            poll = next((p for p in week.polls if p.poll == name), None)
            if poll is not None and isinstance(week.week, int) and (best is None or gamekeys.poll_order(week) > gamekeys.poll_order(best[0])):
                best = (week, poll)
        rows: list[dict[str, Any]] = []
        note = None
        if best is None:
            note = "The committee has not ranked anyone yet this season." if req.metric.id == "CFP" else "This poll has not been published yet this season."
        else:
            week, poll = best
            for entry in sorted((r for r in poll.ranks if isinstance(r.rank, int)), key=lambda r: (r.rank, r.school)):
                rows.append({"rank": entry.rank, "team": entry.school, "conference": entry.conference, "value": entry.points, "firstPlaceVotes": entry.first_place_votes, "week": week.week, "seasonType": week.season_type or "regular"})
            _tied(rows)
            note = f"Week {week.week} ({'final' if (week.season_type or 'regular') != 'regular' else 'regular season'})."
        return Ranked(rows, len(rows), None, None, got["rankings"].ok, note=note)

    async def _class(self, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
        year = int(req.metric.id)
        got = await self._gather(self.players_fetcher.fetch("classRank" if year == self.season else "classRankNext", "/recruiting/teams", {"year": year}, TeamRecruitingRanking, DataKind.RECRUITING))
        parts.update(got)
        records = next(iter(got.values())).records
        rows = [{"rank": r.rank, "team": r.team, "conference": None, "value": _round(r.points, 2)} for r in records if isinstance(r.rank, int) and not isinstance(r.rank, bool)]
        rows.sort(key=lambda r: (r["rank"], r["team"]))
        _tied(rows)
        # class_rank's "of" counts every class in CFBD's answer (Division I, FCS included), so the chip reads the same
        return Ranked(rows, len(records), len(records) - len(rows), None, next(iter(got.values())).ok)

    async def _board(self, req: Request, parts: dict[str, Part], meta: dict[str, dict[str, Any]]) -> Ranked:
        board_id = req.metric.id
        fbs = {t for t in meta} or None

        def conference_of_team(team: str | None) -> str | None:
            return meta.get(team or "", {}).get("conference")

        conference = self._scope_conference(req, conference_of_team)
        if board_id == "ppa:all":
            got = await self._gather(self.players_fetcher.fetch("ppaSeasonAll", "/ppa/players/season", {"year": self.season, "threshold": PPA_MIN_PLAYS}, PlayerSeasonPpa, DataKind.SEASON_STATS))
            parts.update(got)
            national, nat_rank, conf_rows, conf_rank = ppa_national(got["ppaSeasonAll"].records, meta, fbs, conference or self.settings.conference)
            chosen, ranks = (conf_rows, conf_rank) if conference else (national, nat_rank)
            rows = [_ppa_row(r, ranks, nat_rank if conference else None) for r in chosen]
            known = got["ppaSeasonAll"].ok
        elif board_id in {b[0] for b in ADJUSTED_BOARDS}:
            got = await self._gather(
                self.players_fetcher.fetch("wepaPassing", "/wepa/players/passing", {"year": self.season}, PlayerWeightedEPA, DataKind.SEASON_STATS)
                if board_id == "wepa:passing"
                else self.players_fetcher.fetch("wepaRushing", "/wepa/players/rushing", {"year": self.season}, PlayerWeightedEPA, DataKind.SEASON_STATS)
                if board_id == "wepa:rushing"
                else self.players_fetcher.fetch("paar", "/wepa/players/kicking", {"year": self.season}, KickerPAAR, DataKind.SEASON_STATS)
            )
            parts.update(got)
            part = next(iter(got.values()))
            passing = part.records if board_id == "wepa:passing" else []
            rushing = part.records if board_id == "wepa:rushing" else []
            kicking = part.records if board_id == "paar:kicking" else []
            national = adjusted_board_rows(adjusted_source_rows(board_id, passing, rushing, kicking), fbs)
            nat_rank = shared_ranks(national)
            chosen = [r for r in national if r.get("conference") == conference] if conference else national  # the record's conference, as the Leaders conference chips
            ranks = shared_ranks(chosen) if conference else nat_rank
            rows = [_adjusted_player_row(r, ranks, nat_rank if conference else None, conference_of_team) for r in chosen]
            known = part.ok
        else:
            board = next(b for b in BOARDS if b.id == board_id)
            fetches = [self.players_fetcher.fetch(f"national_{board.category}", "/stats/player/season", {"year": self.season, "category": board.category}, PlayerStat, DataKind.SEASON_STATS)]
            use_pull = conference == self.settings.conference  # the Leaders page's conference pull ranks the conference chips
            if use_pull:
                fetches.append(self.players_fetcher.fetch("conference", "/stats/player/season", {"year": self.season, "conference": self.settings.conference}, PlayerStat, DataKind.SEASON_STATS))
            got = await self._gather(*fetches)
            parts.update(got)
            lines = fbs_lines(got[f"national_{board.category}"].records, fbs)
            if use_pull:
                conf_lines = lines_from(got["conference"].records)
            elif conference:
                conf_lines = {k: v for k, v in lines.items() if (v.conference or conference_of_team(v.team)) == conference}
            else:
                conf_lines = {}
            nat_entries, nat_rank, conf_entries, conf_rank = national_board(board, lines, conf_lines)
            chosen_lines, ranks = (conf_entries, conf_rank) if conference else (nat_entries, nat_rank)
            rows = [_line_row(line, board, ranks, nat_rank if conference else None, conference_of_team) for line in chosen_lines]
            known = got[f"national_{board.category}"].ok and (not use_pull or got["conference"].ok)
        _tied(rows)
        return Ranked(rows, len(rows), None, conference, known)


def _raw_adjusted(records: list[AdjustedTeamMetrics], key: str) -> dict[str, float]:
    """The unrounded values adjusted_rows ranks (finite numbers only), for a conference re-rank."""
    read = next(spec[2] for spec in ADJUSTED_KEYS if spec[0] == key)
    out: dict[str, float] = {}
    for m in records:
        try:
            value = finite(read(m))
        except AttributeError:
            value = None
        if value is not None:
            out[m.team] = value
    return out


def _player(player_id: Any, name: Any, position: Any, team: Any, conference: Any, value: Any, detail: dict[str, Any], rank: int | None, national: int | None) -> dict[str, Any]:
    row = {"rank": rank, "playerId": player_id, "player": name, "position": position, "team": team, "conference": conference, "value": _round(value), "detail": detail, "headshotUrl": f"/media/headshot/{player_id}"}
    if national is not None:
        row["nationalRank"] = national
    return row


def _line_row(line: Line, board: Board, ranks: dict[str, int], national: dict[str, int] | None, conference_of: Callable[[str | None], str | None]) -> dict[str, Any]:
    detail = {k: v for k, v in line.stats.items() if k != board.stat}
    return _player(line.player_id, line.player, line.position, line.team, line.conference or conference_of(line.team), line.stats.get(board.stat), detail, ranks.get(line.player_id), national.get(line.player_id) if national is not None else None)


def _ppa_row(r: dict[str, Any], ranks: dict[str, int], national: dict[str, int] | None) -> dict[str, Any]:
    return _player(r["playerId"], r["name"], r["position"], r["team"], None, r["all"], {k: r.get(k) for k in ("plays", "pass", "rush")}, ranks.get(r["playerId"]), national.get(r["playerId"]) if national is not None else None)


def _adjusted_player_row(r: dict[str, Any], ranks: dict[str, int], national: dict[str, int] | None, conference_of: Callable[[str | None], str | None]) -> dict[str, Any]:
    return _player(r["playerId"], r["player"], r["position"], r["team"], r.get("conference") or conference_of(r.get("team")), r["value"], dict(r.get("detail") or {}), ranks.get(r["playerId"]), national.get(r["playerId"]) if national is not None else None)


# The family builders. The extra-call families (recruit, returning, bluechip) come from national_extra
# with their own registry entries and weekly or monthly cache kinds (stream NV).
FAMILIES: dict[str, Builder] = {
    "profile": NationalService._profile,
    "advanced": NationalService._advanced,
    "adjusted": NationalService._adjusted,
    "rating": NationalService._rating,
    "board": NationalService._board,
    "poll": NationalService._poll,
    "class": NationalService._class,
    **national_extra.FAMILIES,
}
