"""The season overview (S1 to S5, S10, and our team-page summary): one assembled answer
for GET /api/season/overview.

Every part comes through the CFBD client (cache, quota guard, breaker) and is parsed with the
Pydantic models, one record at a time. A part that fails is reported as failed and the rest of
the answer still goes out. Ranks are computed here from the all-FBS payloads so leader boards
never cost one call per team.

Calls on a cold cache: games (team), games (all, for points per game ranks), games/media,
records (conference), rankings, teams/fbs, stats/season (fbs), stats/season/advanced (fbs),
ratings sp, elo, fpi, and one games/teams per finished game of ours (cached for good).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import (
    AdvancedSeasonStat,
    CfbdModel,
    Game,
    GameMedia,
    GameTeamStats,
    PollWeek,
    Team,
    TeamElo,
    TeamFPI,
    TeamRecords,
    TeamSP,
    TeamStat,
)
from app.config import Settings
from app.services import context16, gamekeys
from app.services.depth2 import resume
from app.services.logos import logo_fields
from app.services.offday import last_season, road_ahead
from app.services.parts import Part, PartFetcher, assemble
from app.services.parts import iso as _iso
from app.services.playoff import playoff_block
from app.services.profiles import PROFILE_ROWS, advanced_rows, profiles_for
from app.services.ratings import fbs_set
from app.services.stats_extra import elo_table, fpi_tables, sp_tables

log = logging.getLogger("kickoff.season")

CONCURRENCY = 4
POLL_NAMES = {"AP Top 25": "AP", "Coaches Poll": "Coaches", "Playoff Committee Rankings": "CFP"}


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _split(value: Any) -> tuple[int | None, int | None]:
    """'7-15' -> (7, 15). Anything else -> (None, None)."""
    if isinstance(value, str) and "-" in value:
        a, b = value.split("-", 1)
        if a.strip().isdigit() and b.strip().isdigit():
            return int(a), int(b)
    return None, None


def _record(line: Any) -> dict[str, int | None] | None:
    if line is None:
        return None
    return {"games": line.games, "wins": line.wins, "losses": line.losses, "ties": line.ties}


def _win_pct(line: Any) -> float:
    if line is None or line.wins is None or line.losses is None:
        return -1.0
    games = line.wins + line.losses + (line.ties or 0)
    return (line.wins + 0.5 * (line.ties or 0)) / games if games else -1.0


# --- parts: see app/services/parts.py ------------------------------------------------------------


def standings_rows(records: list[TeamRecords], teams: dict[str, dict[str, Any]], ap: dict[str, int], conference: str | None, team: str | None) -> list[dict[str, Any]]:
    """One conference's standings: conference record first, then conference wins, then the overall record.
    Phase 17 #2: shared by the Season page (our conference) and every team page (that team's conference)."""
    rows = []
    for rec in records:
        if rec.conference and rec.conference != conference:
            continue
        meta = teams.get(rec.team, {})
        rows.append(
            {
                "team": rec.team,
                "abbreviation": meta.get("abbreviation"),
                "logo": meta.get("logo"),
                "logoDark": meta.get("logoDark"),
                "conference": _record(rec.conference_games),
                "overall": _record(rec.total),
                "apRank": ap.get(rec.team),
                "isUs": rec.team == team,
                "_conf_pct": _win_pct(rec.conference_games),
                "_conf_wins": (rec.conference_games.wins if rec.conference_games and rec.conference_games.wins is not None else -1),
                "_pct": _win_pct(rec.total),
            }
        )
    rows.sort(key=lambda r: (-r["_conf_pct"], -r["_conf_wins"], -r["_pct"], r["team"]))
    for index, row in enumerate(rows, start=1):
        row["place"] = index
        for key in ("_conf_pct", "_conf_wins", "_pct"):
            row.pop(key, None)
    return rows


@dataclass
class Overview:
    data: dict[str, Any]
    parts: dict[str, Part]
    fetched_at: str | None
    stale: bool
    source: str
    errors: list[dict[str, str]]
    all_failed: bool


class SeasonService:
    def __init__(self, client: CfbdClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.fetcher = PartFetcher(client, CONCURRENCY)

    async def _part(self, name: str, endpoint: str, params: dict[str, Any], model: type[CfbdModel], kind: DataKind) -> Part:
        return await self.fetcher.fetch(name, endpoint, params, model, kind)

    async def overview(self) -> Overview:
        year, team, conference = self.settings.season, self.settings.team, self.settings.conference
        now = self.client._clock()

        first = await asyncio.gather(
            self._part("schedule", "/games", {"year": year, "team": team}, Game, DataKind.SCHEDULE),
            self._part("games", "/games", {"year": year}, Game, DataKind.SCHEDULE),
            self._part("media", "/games/media", {"year": year, "team": team}, GameMedia, DataKind.SCHEDULE),
            self._part("records", "/records", {"year": year, "conference": conference}, TeamRecords, DataKind.SCHEDULE),
            self._part("rankings", "/rankings", {"year": year}, PollWeek, DataKind.SCHEDULE),
            self._part("teams", "/teams/fbs", {"year": year}, Team, DataKind.TEAMS),
            self._part("stats", "/stats/season", {"year": year, "classification": "fbs"}, TeamStat, DataKind.SEASON_STATS),
            self._part("advanced", "/stats/season/advanced", {"year": year, "classification": "fbs"}, AdvancedSeasonStat, DataKind.SEASON_STATS),
            self._part("sp", "/ratings/sp", {"year": year}, TeamSP, DataKind.SEASON_STATS),
            self._part("elo", "/ratings/elo", {"year": year}, TeamElo, DataKind.SEASON_STATS),
            self._part("fpi", "/ratings/fpi", {"year": year}, TeamFPI, DataKind.SEASON_STATS),
            # Phase 15: last season beside this one; a finished season is kept 30 days
            self._part("lastStats", "/stats/season", {"year": year - 1, "classification": "fbs"}, TeamStat, DataKind.HISTORY),
            self._part("lastGames", "/games", {"year": year - 1}, Game, DataKind.HISTORY),
        )
        parts: dict[str, Part] = {part.name: part for part in first}

        completed = sorted(
            (g for g in parts["schedule"].records if g.completed and g.week is not None),
            key=gamekeys.order,
        )
        boxes = await asyncio.gather(
            *(self._part(f"box_{gamekeys.tag(g)}", "/games/teams", gamekeys.box_params(g, year, team), GameTeamStats, DataKind.FINISHED_GAME) for g in completed)
        )
        for part in boxes:
            parts[part.name] = part

        self._set_game_day(parts["schedule"].records, now)
        data = self._assemble(parts, completed, boxes, now)
        context16.season_extras(data, parts, team)  # Phase 16 BX: form, rank paths, season strip
        return self._wrap(data, parts, now)

    def _set_game_day(self, games: list[Game], now: datetime) -> None:
        """Tell the client whether today is our game day so lines and weather refresh faster."""
        today = now.astimezone(self.settings.tzinfo).date()
        game_day = False
        for game in games:
            local = self._local(game.start_date)
            if local is not None and local.date() == today:
                game_day = True
        self.client.game_day = game_day

    def _local(self, iso: str | None) -> datetime | None:
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(self.settings.tzinfo)
        except ValueError:
            return None

    # --- assembling ----------------------------------------------------------------------

    def _assemble(self, parts: dict[str, Part], completed: list[Game], boxes: list[Part], now: datetime) -> dict[str, Any]:
        team = self.settings.team
        teams = self._team_lookup(parts["teams"].records)
        fbs = fbs_set(parts["teams"].records)
        polls, poll_ranks = self._polls(parts["rankings"].records, teams)
        records = {r.team: r for r in parts["records"].records}
        schedule, next_game = self._schedule(parts["schedule"].records, parts["media"].records, teams, poll_ranks)
        profile, opponent_profile = self._profile(parts["stats"].records, parts["games"].records, parts["schedule"].records, next_game)
        last_profiles = profiles_for(parts["lastStats"].records, parts["lastGames"].records, [], self.settings.conference, team) if parts["lastStats"].records else None
        return {
            "season": self.settings.season,
            "team": {**teams.get(team, {"school": team}), "school": team},
            "record": self._record_block(records.get(team), poll_ranks, parts["sp"].records),
            "schedule": schedule,
            "nextGameId": next_game.id if next_game else None,
            "opponent": opponent_profile,
            "standings": self._standings(parts["records"].records, teams, poll_ranks),
            "polls": polls,
            "profile": profile,
            "advanced": self._advanced(parts["advanced"].records),
            "ratings": self._ratings(parts["sp"].records, parts["elo"].records, parts["fpi"].records, fbs),
            "trends": self._trends(completed, boxes),
            "resume": resume(parts["schedule"].records, parts["games"].records, team, parts["sp"].records, parts["rankings"].records),  # Phase 13
            "playoff": playoff_block(parts["rankings"].records, parts["games"].records, team, teams),  # Phase 15
            "lastSeason": {"year": self.settings.season - 1, "rows": last_season(profile["rows"], last_profiles, team, self.settings.season)},  # Phase 15
            "roadAhead": road_ahead(parts["schedule"].records, parts["games"].records, team, parts["sp"].records, poll_ranks.get("AP", {}), fbs),  # Phase 15
            "parts": {name: part.status(now) for name, part in parts.items() if not name.startswith("box_")}
            | {"trends": self._trend_status(boxes, now)},
        }

    def _team_lookup(self, teams: list[Team]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for t in teams:
            if not t.school:
                continue
            out[t.school] = {
                "school": t.school,
                "abbreviation": t.abbreviation,
                "mascot": t.mascot,
                "conference": t.conference,
                "color": t.color,
                "altColor": t.alternate_color,
                **logo_fields(t.id, t.logos),  # Phase 16: our own /media/logo URLs, never the CDN's
            }
        return out

    def _polls(self, weeks: list[PollWeek], teams: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
        """The latest recorded poll week. Returns the poll blocks and {poll short name: {school: rank}}."""
        pool = [w for w in weeks if isinstance(w.week, int)]
        if not pool:
            return [], {}
        latest = max(pool, key=gamekeys.poll_order)  # Phase 15: the final poll after the bowls counts
        blocks: list[dict[str, Any]] = []
        lookup: dict[str, dict[str, int]] = {}
        for poll in latest.polls:
            short = POLL_NAMES.get(poll.poll)
            if short is None:
                continue
            ranks = []
            by_school: dict[str, int] = {}
            for entry in sorted(poll.ranks, key=lambda r: r.rank if r.rank is not None else 999):
                if entry.rank is None:
                    continue
                by_school[entry.school] = entry.rank
                meta = teams.get(entry.school, {})
                ranks.append(
                    {
                        "rank": entry.rank,
                        "school": entry.school,
                        "abbreviation": meta.get("abbreviation"),
                        "logo": meta.get("logo"),
                        "logoDark": meta.get("logoDark"),
                        "conference": entry.conference or meta.get("conference"),
                        "points": entry.points,
                        "firstPlaceVotes": entry.first_place_votes,
                        "isUs": entry.school == self.settings.team,
                    }
                )
            lookup[short] = by_school
            blocks.append({"poll": short, "metric": f"poll:{short}", "name": poll.poll, "week": latest.week, "ranks": ranks, "usRank": by_school.get(self.settings.team)})
        order = {"AP": 0, "Coaches": 1, "CFP": 2}
        blocks.sort(key=lambda b: order.get(b["poll"], 9))
        return blocks, lookup

    def _record_block(self, rec: TeamRecords | None, poll_ranks: dict[str, dict[str, int]], sp: list[TeamSP]) -> dict[str, Any]:
        team = self.settings.team
        sp_row = next((r for r in sp if r.team == team), None)
        return {
            "overall": _record(rec.total) if rec else None,
            "conference": _record(rec.conference_games) if rec else None,
            "home": _record(rec.home_games) if rec else None,
            "away": _record(rec.away_games) if rec else None,
            "expectedWins": rec.expected_wins if rec else None,
            "apRank": poll_ranks.get("AP", {}).get(team),
            "coachesRank": poll_ranks.get("Coaches", {}).get(team),
            "cfpRank": poll_ranks.get("CFP", {}).get(team),
            "spRank": sp_row.ranking if sp_row else None,
            "spMetric": "rating:sp",  # Phase 16: the record line's SP+ opens its national list
        }

    def _schedule(self, games: list[Game], media: list[GameMedia], teams: dict[str, dict[str, Any]], poll_ranks: dict[str, dict[str, int]]) -> tuple[list[dict[str, Any]], Game | None]:
        team = self.settings.team
        tv = {m.id: m.outlet for m in media if (m.media_type or "").lower() == "tv" and m.outlet}
        ap = poll_ranks.get("AP", {})
        rows: list[dict[str, Any]] = []
        next_game: Game | None = None
        for game in sorted(games, key=gamekeys.order):
            home_is_us = game.home_team == team
            opponent = game.away_team if home_is_us else game.home_team
            us_points = game.home_points if home_is_us else game.away_points
            them_points = game.away_points if home_is_us else game.home_points
            result = None
            if game.completed and us_points is not None and them_points is not None:
                result = "W" if us_points > them_points else "L" if us_points < them_points else "T"
            if not game.completed and next_game is None:
                next_game = game
            rows.append(
                {
                    "gameId": game.id,
                    "week": game.week,
                    "postseason": gamekeys.label(game),  # Phase 15: the bowl or playoff game's name
                    "playoffRound": gamekeys.playoff_round(game),
                    "date": game.start_date,
                    "startTimeTbd": bool(game.start_time_tbd),
                    "opponent": {**teams.get(opponent or "", {"school": opponent}), "school": opponent, "apRank": ap.get(opponent or "")},
                    "homeAway": "neutral" if game.neutral_site else ("home" if home_is_us else "away"),
                    "venue": game.venue,
                    "completed": bool(game.completed),
                    "result": result,
                    "usPoints": us_points,
                    "themPoints": them_points,
                    "tv": tv.get(game.id),
                    "conferenceGame": game.conference_game,
                    "usLineScores": game.home_line_scores if home_is_us else game.away_line_scores,
                    "themLineScores": game.away_line_scores if home_is_us else game.home_line_scores,
                }
            )
        return rows, next_game

    def _standings(self, records: list[TeamRecords], teams: dict[str, dict[str, Any]], poll_ranks: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        return standings_rows(records, teams, poll_ranks.get("AP", {}), self.settings.conference, self.settings.team)

    # --- the stat profile ---------------------------------------------------------------

    def _profile(self, stats: list[TeamStat], all_games: list[Game], team_games: list[Game], next_game: Game | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
        team = self.settings.team
        profiles = profiles_for(stats, all_games, team_games, self.settings.conference, team)
        profile = {"rows": profiles.rows(team), "games": profiles.games_for(team), "conference": self.settings.conference}
        opponent_profile = None
        if next_game is not None:
            opp = next_game.away_team if next_game.home_team == team else next_game.home_team
            if opp:
                opponent_profile = {"school": opp, "values": {key: (round(v, 3) if (v := profiles.value(opp, key)) is not None else None) for _, _, key, _, _ in PROFILE_ROWS}}
        return profile, opponent_profile

    def _advanced(self, records: list[AdvancedSeasonStat]) -> dict[str, Any]:
        return {"rows": advanced_rows(records, self.settings.team)}

    def _ratings(self, sp: list[TeamSP], elo: list[TeamElo], fpi: list[TeamFPI], fbs: set[str] | None = None) -> dict[str, Any]:
        """Our SP+, Elo and FPI with ranks from the rating tables the Ratings page and the
        national lists read (Phase 16): the same numbers, each "of" its own population, and the
        nationalAverages pseudo-team no longer counted (SP+ of 138, not 139)."""
        team = self.settings.team
        out: dict[str, Any] = {"sp": None, "elo": None, "fpi": None}
        sps = sp_tables(sp, fbs)
        sp_row = next((r for r in sp if r.team == team), None)
        if sp_row is not None:

            def unit(key: str) -> dict[str, Any]:
                return {"rating": sps[key].value(team), "rank": sps[key].rank(team), "of": sps[key].of or None, "metric": f"rating:{key}"}

            out["sp"] = {
                "rating": sp_row.rating,
                "rank": sps["sp"].rank(team),
                "of": sps["sp"].of or None,
                "metric": "rating:sp",
                "offense": unit("spOffense"),
                "defense": unit("spDefense"),
                "special": unit("spSpecial"),
                "sos": sp_row.sos,
            }
        elo_ranked = elo_table(elo, fbs)
        elo_row = next((r for r in elo if r.team == team), None)
        if elo_row is not None and elo_ranked.rank(team) is not None:
            out["elo"] = {"rating": elo_row.elo, "rank": elo_ranked.rank(team), "of": elo_ranked.of or None, "metric": "rating:elo"}
        fpis = fpi_tables(fpi, fbs)
        fpi_row = next((r for r in fpi if r.team == team), None)
        if fpi_row is not None and fpis["fpi"].value(team) is not None:
            out["fpi"] = {
                "rating": fpi_row.fpi,
                "rank": fpis["fpi"].rank(team),
                "of": fpis["fpi"].of or None,
                "metric": "rating:fpi",
                "strengthOfScheduleRank": fpis["fpiSos"].rank(team),
                "strengthOfScheduleOf": fpis["fpiSos"].of or None,
                "strengthOfScheduleMetric": "rating:fpiSos",
                "strengthOfRecordRank": fpis["fpiSor"].rank(team),
                "strengthOfRecordOf": fpis["fpiSor"].of or None,
                "strengthOfRecordMetric": "rating:fpiSor",
            }
        return out

    # --- trends ---------------------------------------------------------------------------

    def _trends(self, completed: list[Game], boxes: list[Part]) -> dict[str, Any]:
        team = self.settings.team
        by_week = {part.name: part for part in boxes}
        weeks: list[int] = []
        opponents: list[str | None] = []
        points: list[float | None] = []
        allowed: list[float | None] = []
        ypp: list[float | None] = []
        margin: list[float | None] = []
        third: list[float | None] = []
        for game in completed:
            home_is_us = game.home_team == team
            weeks.append(game.week or 0)
            opponents.append(game.away_team if home_is_us else game.home_team)
            points.append(float(game.home_points if home_is_us else game.away_points) if (game.home_points is not None and game.away_points is not None) else None)
            allowed.append(float(game.away_points if home_is_us else game.home_points) if (game.home_points is not None and game.away_points is not None) else None)
            part = by_week.get(f"box_{gamekeys.tag(game)}")
            box = next((b for b in (part.records if part else []) if b.id == game.id), None)
            us = next((side for side in (box.teams if box else []) if side.team == team), None)
            them = next((side for side in (box.teams if box else []) if side.team != team), None)
            u = {s.category: s.stat for s in (us.stats if us else [])}
            t = {s.category: s.stat for s in (them.stats if them else [])}
            comp, att = _split(u.get("completionAttempts"))
            plays = (_num(u.get("rushingAttempts")) or 0) + (att or 0)
            ypp.append(round(_num(u.get("totalYards")) / plays, 2) if _num(u.get("totalYards")) is not None and plays else None)
            our_to, their_to = _num(u.get("turnovers")), _num(t.get("turnovers"))
            margin.append(their_to - our_to if our_to is not None and their_to is not None else None)
            made, of = _split(u.get("thirdDownEff"))
            third.append(round(made / of, 3) if made is not None and of else None)
        return {"weeks": weeks, "opponents": opponents, "points": points, "pointsAllowed": allowed, "yardsPerPlay": ypp, "turnoverMargin": margin, "thirdDown": third}

    def _trend_status(self, boxes: list[Part], now: datetime) -> dict[str, Any]:
        if not boxes:
            return {"status": "ok", "fetchedAt": None, "ageSeconds": None, "error": None, "skipped": 0, "missingWeeks": []}
        missing = [part.name.removeprefix("box_") for part in boxes if not part.ok]
        stale = any(part.ok and part.fetched.stale for part in boxes)
        oldest = min((part.fetched.fetched_at for part in boxes if part.ok), default=None)
        status = "error" if len(missing) == len(boxes) else "stale" if stale else "ok"
        return {
            "status": status,
            "fetchedAt": _iso(oldest),
            "ageSeconds": round((now - oldest).total_seconds()) if oldest else None,
            "error": next((part.error for part in boxes if part.error), None),
            "skipped": sum(part.skipped for part in boxes),
            "missingWeeks": missing,
        }

    # --- envelope pieces --------------------------------------------------------------------

    def _wrap(self, data: dict[str, Any], parts: dict[str, Part], now: datetime) -> Overview:
        built = assemble(data, parts)
        return Overview(data=built.data, parts=parts, fetched_at=built.fetched_at, stale=built.stale, source=built.source, errors=built.errors, all_failed=built.all_failed)
