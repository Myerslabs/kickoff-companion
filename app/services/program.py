"""The game program (P1 to P10), the Newspaper (N1 to N4), and the team page for any opponent
(T1). Assembled from parts through the CFBD client, the feed store, the NWS client, and the
per-game notes file. Every part can fail alone; the rest of the page still goes out.

Calls on a cold cache for the next program: schedule, media, lines, pregame win probability,
teams, records (conference and all), rankings, season stats, advanced stats, team and
conference player stats, the series, venues, the opponent's schedule, and, for a past game,
its two box scores. The newspaper adds the week's games, lines, win probability, and media.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import (
    AdjustedTeamMetrics,
    AdvancedSeasonStat,
    BettingGame,
    CalendarWeek,
    Coach,
    Game,
    GameMedia,
    GamePlayerStats,
    GameTeamStats,
    GameWeather,
    Matchup,
    PassingPlay,
    PlayerGamePpa,
    PlayerSeasonPpa,
    PlayerStat,
    PlayerTransfer,
    PlayerUsage,
    PollWeek,
    PregameWinProbability,
    Recruit,
    ReturningProduction,
    RosterPlayer,
    RushingPlay,
    Team,
    TeamGamePpa,
    TeamRecords,
    TeamSP,
    TeamStat,
    TeamTalent,
    Venue,
)
from app.config import Settings
from app.feeds import FeedStore, SeasonArchive, merge_headlines
from app.services import context16, gamekeys
from app.services.analytics import player_rows, season_average, team_game_rows
from app.services.classes import class_fields
from app.services.depth2 import adjusted_matchup, advanced_box, portal_index, tendencies, transfer_for
from app.services.leader_lines import RankIndex, game_totals, leader_detail
from app.services.lineup_stats import attach_lineup_stats
from app.services.logos import logo_fields
from app.services.national_extra import PageRanks, page_fetches  # Phase 16 NV: the extra-call lists' keys and ranks
from app.services.notes import load_notes
from app.services.offday import common_opponents
from app.services.paper import paper_weeks
from app.services.parts import Assembled, Part, PartFetcher, assemble, calendar_slot, statuses
from app.services.players import BOARDS, CATEGORIES, board_entries, fbs_lines, lines_from
from app.services.profiles import PROFILE_ROWS, advanced_rows, profiles_for
from app.services.ratings import fbs_set
from app.services.season import standings_rows
from app.services.season_notes import SeasonNotes
from app.services.stats_extra import RankTable, blue_chip, ppa_season_rows, recruit_sides, returning_block, sp_tables, star_counts, talent_lookup, usage_rows
from app.weather import NwsClient

log = logging.getLogger("kickoff.program")

POLL_NAMES = {"AP Top 25": "AP", "Coaches Poll": "Coaches", "Playoff Committee Rankings": "CFP"}
SATURDAY = 5
SIDE_BY_SIDE = [("passing", "YDS", "Passing yards"), ("rushing", "YDS", "Rushing yards"), ("receiving", "YDS", "Receiving yards"), ("defensive", "TOT", "Tackles"), ("defensive", "SACKS", "Sacks")]


def _record(line: Any) -> dict[str, int | None] | None:
    if line is None:
        return None
    return {"games": line.games, "wins": line.wins, "losses": line.losses, "ties": line.ties}


def _scalar(value: Any) -> float | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value.strip() or None
    return None


def compass(degrees: Any) -> str | None:
    """Wind direction in degrees (CFBD) to a 16-point compass label; anything else stays None."""
    if isinstance(degrees, bool) or not isinstance(degrees, (int, float)):
        return None
    points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return points[int((float(degrees) % 360) / 22.5 + 0.5) % 16]


def _split(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, str) and "-" in value:
        a, b = value.split("-", 1)
        if a.strip().isdigit() and b.strip().isdigit():
            return int(a), int(b)
    return None, None



def box_sides(teams_part: Part | None, players_part: Part | None, game: Game) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, list[dict[str, Any]]]]]:
    """One game's team box ({school: totals}) and player lines ({school: {category: rows}}) from the
    /games/teams and /games/players answers (a week-keyed answer can hold other games; only this one is read)."""
    box = next((b for b in (teams_part.records if teams_part else []) if b.id == game.id), None)
    sides: dict[str, dict[str, Any]] = {}
    for side in (box.teams if box else []):
        stats = {s.category: s.stat for s in side.stats}
        third, fourth, pens = _split(stats.get("thirdDownEff")), _split(stats.get("fourthDownEff")), _split(stats.get("totalPenaltiesYards"))
        comp = stats.get("completionAttempts")
        sides[side.team or ""] = {
            "team": side.team, "points": side.points,
            "totalYards": _scalar(stats.get("totalYards")), "netPassingYards": _scalar(stats.get("netPassingYards")), "rushingYards": _scalar(stats.get("rushingYards")),
            "firstDowns": _scalar(stats.get("firstDowns")), "thirdDown": {"made": third[0], "of": third[1]}, "fourthDown": {"made": fourth[0], "of": fourth[1]},
            "turnovers": _scalar(stats.get("turnovers")), "penalties": {"count": pens[0], "yards": pens[1]}, "possessionTime": stats.get("possessionTime"),
            "raw": {k: (v if isinstance(v, str) else _scalar(v)) for k, v in stats.items()}, "completionAttempts": comp,
        }
    players: dict[str, dict[str, list[dict[str, Any]]]] = {}
    pbox = next((b for b in (players_part.records if players_part else []) if b.id == game.id), None)
    for side in (pbox.teams if pbox else []):
        categories: dict[str, list[dict[str, Any]]] = {}
        for category in side.categories:
            rows: dict[str, dict[str, Any]] = {}
            for stat_type in category.types:
                for athlete in stat_type.athletes:
                    row = rows.setdefault(athlete.id, {"playerId": athlete.id, "name": athlete.name, "stats": {}})
                    row["stats"][stat_type.name] = _scalar(athlete.stat)
            categories[category.name] = list(rows.values())
        players[side.team or ""] = categories
    return sides, players

class ProgramService:
    def __init__(self, client: CfbdClient, settings: Settings, feeds: FeedStore, weather: NwsClient) -> None:
        self.client = client
        self.settings = settings
        self.feeds = feeds
        self.weather = weather
        self.fetcher = PartFetcher(client, 4)
        self.archive = SeasonArchive(settings.data_dir)  # Phase 17 #26: every headline this season
        self.season_notes = SeasonNotes(settings.data_dir, settings.season)  # Phase 17 Part 3a: coaches, staffs, ages

    @property
    def year(self) -> int:
        return self.settings.season

    @property
    def team(self) -> str:
        return self.settings.team

    # --- fetch helpers -------------------------------------------------------------------------

    def _f(self, name: str, endpoint: str, params: dict[str, Any], model: Any, kind: DataKind) -> Any:
        return self.fetcher.fetch(name, endpoint, params, model, kind)

    async def _core(self) -> dict[str, Part]:
        """The parts every program and the newspaper share."""
        results = await asyncio.gather(
            self._f("schedule", "/games", {"year": self.year, "team": self.team}, Game, DataKind.SCHEDULE),
            self._f("games", "/games", {"year": self.year}, Game, DataKind.SCHEDULE),
            self._f("teams", "/teams/fbs", {"year": self.year}, Team, DataKind.TEAMS),
            self._f("records", "/records", {"year": self.year}, TeamRecords, DataKind.SCHEDULE),
            self._f("rankings", "/rankings", {"year": self.year}, PollWeek, DataKind.SCHEDULE),
            self._f("stats", "/stats/season", {"year": self.year, "classification": "fbs"}, TeamStat, DataKind.SEASON_STATS),
        )
        return {part.name: part for part in results}

    # --- shared lookups -------------------------------------------------------------------------

    def _teams(self, part: Part) -> dict[str, dict[str, Any]]:
        return self._teams_from(part.records)

    def _teams_from(self, records: list[Any]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for t in records:
            if not t.school:
                continue
            out[t.school] = {"school": t.school, "abbreviation": t.abbreviation, "mascot": t.mascot, "conference": t.conference, "color": t.color, "altColor": t.alternate_color, **logo_fields(t.id, t.logos)}  # Phase 16: local logo URLs
        return out

    @staticmethod
    def _location(part: Part, school: str) -> dict[str, Any] | None:
        """Where a team plays, from /teams/fbs (location is an object the spec leaves open: its home
        venue's name, city, state, capacity and more). None when there is no city or state to show."""
        team = next((t for t in part.records if t.school == school), None)
        raw = team.location if team is not None and isinstance(team.location, dict) else None
        if not raw:
            return None

        def word(key: str) -> str | None:
            value = raw.get(key)
            return value.strip() if isinstance(value, str) and value.strip() else None

        capacity = raw.get("capacity")
        out = {"city": word("city"), "state": word("state"), "venue": word("name"), "capacity": capacity if isinstance(capacity, int) and not isinstance(capacity, bool) and capacity > 0 else None}
        return out if out["city"] or out["state"] else None

    def _poll_ranks(self, part: Part) -> tuple[dict[str, dict[str, int]], int | None]:
        pool = [w for w in part.records if isinstance(w.week, int)]
        if not pool:
            return {}, None
        latest = max(pool, key=gamekeys.poll_order)  # Phase 15: the postseason's final poll is the latest
        out: dict[str, dict[str, int]] = {}
        for poll in latest.polls:
            short = POLL_NAMES.get(poll.poll)
            if short:
                out[short] = {r.school: r.rank for r in poll.ranks if r.rank is not None}
        return out, latest.week

    @staticmethod
    def _team_standings(parts: dict[str, Part], teams: dict[str, dict[str, Any]], ranks: dict[str, dict[str, int]], school: str) -> dict[str, Any] | None:
        """The standings of the team's own conference from /records (every team, already fetched). None for an
        independent or a team /records doesn't list."""
        rec = next((r for r in parts["records"].records if r.team == school), None)
        conference = rec.conference if rec is not None else None
        if not conference or conference.strip().lower() in ("fbs independents", "independent", "independents"):
            return None
        return {"conference": conference, "rows": standings_rows(parts["records"].records, teams, ranks.get("AP", {}), conference, school)}

    def _team_block(self, name: str | None, teams: dict[str, dict[str, Any]], records: dict[str, TeamRecords], ranks: dict[str, dict[str, int]]) -> dict[str, Any]:
        rec = records.get(name or "")
        return {
            **teams.get(name or "", {}),
            "school": name,
            "record": _record(rec.total) if rec else None,
            "conferenceRecord": _record(rec.conference_games) if rec else None,
            "apRank": ranks.get("AP", {}).get(name or ""),
            "coachesRank": ranks.get("Coaches", {}).get(name or ""),
            "cfpRank": ranks.get("CFP", {}).get(name or ""),
        }

    def _local(self, iso: str | None) -> datetime | None:
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(self.settings.tzinfo)
        except ValueError:
            return None

    def _pick_game(self, games: list[Game], game_id: int | None) -> Game | None:
        ordered = sorted((g for g in games if g.week is not None), key=gamekeys.order)
        if game_id is not None:
            return next((g for g in ordered if g.id == game_id), None)
        upcoming = [g for g in ordered if not g.completed]
        return upcoming[0] if upcoming else (ordered[-1] if ordered else None)

    # --- the program (P1 to P10) ------------------------------------------------------------------

    async def program(self, game_id: int | None = None) -> Assembled | None:
        parts = await self._core()
        game = self._pick_game(parts["schedule"].records, game_id)
        if game is None:
            if game_id is not None and parts["schedule"].ok:
                return None  # a real miss: the id is not on our schedule
            # No schedule at all (CFBD down, the quota, the breaker): the answer carries the part's error, never a 404
            data = {"season": self.year, "gameId": game_id, "game": None, "picker": [], "parts": statuses(parts, self.client._clock())}
            return assemble(data, parts)
        home_is_us = game.home_team == self.team
        opponent = game.away_team if home_is_us else game.home_team

        # Each team's latest finished game (a bowl counts, Phase 15) for the players' play value.
        us_last = max((g for g in parts["schedule"].records if g.completed and isinstance(g.week, int)), key=gamekeys.order, default=None)
        them_last = max((g for g in parts["games"].records if g.completed and isinstance(g.week, int) and opponent in (g.home_team, g.away_team)), key=gamekeys.order, default=None) if opponent else None
        us_week = us_last.week if us_last else None
        them_week = them_last.week if them_last else None
        extra = await asyncio.gather(
            self._f("media", "/games/media", {"year": self.year, "team": self.team}, GameMedia, DataKind.SCHEDULE),
            self._f("lines", "/lines", {"year": self.year, "team": self.team}, BettingGame, DataKind.LINES),
            self._f("pregame", "/metrics/wp/pregame", gamekeys.week_params(game, self.year, self.team), PregameWinProbability, DataKind.SEASON_STATS),
            self._f("advanced", "/stats/season/advanced", {"year": self.year, "classification": "fbs"}, AdvancedSeasonStat, DataKind.SEASON_STATS),
            self._f("playersTeam", "/stats/player/season", {"year": self.year, "team": self.team}, PlayerStat, DataKind.SEASON_STATS),
            self._f("playersOpponent", "/stats/player/season", {"year": self.year, "team": opponent}, PlayerStat, DataKind.SEASON_STATS),
            self._f("series", "/teams/matchup", {"team1": self.team, "team2": opponent}, Matchup, DataKind.HISTORY),
            self._f("venues", "/venues", {}, Venue, DataKind.TEAMS),
            self._f("sp", "/ratings/sp", {"year": self.year}, TeamSP, DataKind.SEASON_STATS),
            self._f("ppaUs", "/ppa/games", gamekeys.season_params(self.year, self.team, parts["schedule"].records), TeamGamePpa, DataKind.SEASON_STATS),
            *([self._f("ppaThem", "/ppa/games", gamekeys.season_params(self.year, opponent, parts["schedule"].records), TeamGamePpa, DataKind.SEASON_STATS)] if opponent else []),
            *([self._f("ppaPlayersUs", "/ppa/players/games", gamekeys.week_params(us_last, self.year, self.team), PlayerGamePpa, DataKind.SEASON_STATS)] if us_last is not None else []),
            *([self._f("ppaPlayersThem", "/ppa/players/games", gamekeys.week_params(them_last, self.year, opponent), PlayerGamePpa, DataKind.SEASON_STATS)] if opponent and them_last is not None else []),
            *([self._f("boxTeams", "/games/teams", gamekeys.box_params(game, self.year, self.team), GameTeamStats, DataKind.FINISHED_GAME), self._f("boxPlayers", "/games/players", gamekeys.box_params(game, self.year, self.team), GamePlayerStats, DataKind.FINISHED_GAME)] if game.completed else []),
            *self._recruiting_fetches(self.team, "us"),
            *(self._recruiting_fetches(opponent, "them") if opponent else []),
            *page_fetches(self.fetcher, self.year),  # Phase 16 NV: blue-chip and returning ranks, the lists' own keys
            self._f("talent", "/talent", {"year": self.year}, TeamTalent, DataKind.SEASON_STATS),
            *([self._f("cfbdWeather", "/games/weather", gamekeys.week_params(game, self.year, self.team), GameWeather, DataKind.WEATHER)] if self.client.capabilities.weather else []),
            # Phase 13: the opponent's season of runs and passes, opponent-adjusted team metrics, and a finished game's advanced box
            *([self._f("oppRushes", "/rushing/plays", {"year": self.year, "team": opponent}, RushingPlay, DataKind.SEASON_STATS), self._f("oppPasses", "/passing/plays", {"year": self.year, "team": opponent}, PassingPlay, DataKind.SEASON_STATS)] if opponent else []),
            self._f("adjusted", "/wepa/team/season", {"year": self.year}, AdjustedTeamMetrics, DataKind.SEASON_STATS),
            *([self._f("advancedBox", "/game/box/advanced", {"id": game.id}, None, DataKind.FINISHED_GAME)] if game.completed else []),
            # Phase 15: how both teams played last season (a finished season is kept 30 days)
            self._f("lastStats", "/stats/season", {"year": self.year - 1, "classification": "fbs"}, TeamStat, DataKind.HISTORY),
            self._f("lastGames", "/games", {"year": self.year - 1}, Game, DataKind.HISTORY),
        )
        for part in extra:
            parts[part.name] = part

        teams = self._teams(parts["teams"])
        records = {r.team: r for r in parts["records"].records}
        ranks, poll_week = self._poll_ranks(parts["rankings"])
        # Phase 16: the one factory, so the program ranks the same games as the Season page and the lists
        profiles = profiles_for(parts["stats"].records, parts["games"].records, parts["schedule"].records, self.settings.conference, self.team)
        kickoff_local = self._local(game.start_date)
        tv = next((m.outlet for m in parts["media"].records if m.id == game.id and (m.media_type or "").lower() == "tv"), None)
        book = next((b for b in parts["lines"].records if b.id == game.id), None)
        line = (book.lines[0] if book and book.lines else None)
        pregame = next((p for p in parts["pregame"].records if p.game_id == game.id), None)
        venue = next((v for v in parts["venues"].records if v.id == game.venue_id), None) if game.venue_id else None
        weather = await self._weather(game, venue, parts, kickoff_local)
        notes, notes_error = load_notes(self.settings.data_dir, game.id)
        sp_ranked = sp_tables(parts["sp"].records, fbs_set(parts["teams"].records))["sp"]

        us_lines, opp_lines = lines_from(parts["playersTeam"].records), lines_from(parts["playersOpponent"].records)
        side_by_side = []
        for category, stat, label in SIDE_BY_SIDE:
            board = next(b for b in BOARDS if b.category == category and b.stat == stat)
            us_top = board_entries(us_lines, board)[:1]
            them_top = board_entries(opp_lines, board)[:1]
            side_by_side.append({
                "label": label,
                "category": category,  # Phase 17 #17: matches the whole lines from /api/program/<id>/leaders
                "stat": stat,
                "format": board.format,
                "us": {"playerId": us_top[0].player_id, "player": us_top[0].player, "position": us_top[0].position, "value": us_top[0].stats.get(stat), "headshotUrl": f"/media/headshot/{us_top[0].player_id}"} if us_top else None,
                "them": {"playerId": them_top[0].player_id, "player": them_top[0].player, "position": them_top[0].position, "value": them_top[0].stats.get(stat), "headshotUrl": f"/media/headshot/{them_top[0].player_id}"} if them_top else None,
            })

        series = self._series(parts["series"].records, opponent)
        picker = self._picker(parts["schedule"].records, teams, ranks)
        final = self._final_box(parts, game, opponent) if game.completed else None
        now = self.client._clock()
        data = {
            "season": self.year,
            "game": {
                "gameId": game.id,
                "week": game.week,
                "postseason": gamekeys.label(game),
                "playoffRound": gamekeys.playoff_round(game),
                "kickoff": game.start_date,
                "kickoffLocal": kickoff_local.isoformat() if kickoff_local else None,
                "startTimeTbd": bool(game.start_time_tbd),
                "completed": bool(game.completed),
                "homeIsUs": home_is_us,
                "neutralSite": bool(game.neutral_site),
                "conferenceGame": game.conference_game,
                "venue": game.venue,
                "venueDetail": {"name": venue.name, "city": venue.city, "state": venue.state, "capacity": venue.capacity, "grass": venue.grass, "dome": venue.dome, "timezone": venue.timezone} if venue else None,
                "tv": tv,
                "usPoints": game.home_points if home_is_us else game.away_points,
                "themPoints": game.away_points if home_is_us else game.home_points,
                "usLineScores": game.home_line_scores if home_is_us else game.away_line_scores,
                "themLineScores": game.away_line_scores if home_is_us else game.home_line_scores,
                "excitement": game.excitement_index,
                "attendance": game.attendance,
            },
            "us": {**self._team_block(self.team, teams, records, ranks), "sp": self._sp_block(sp_ranked, self.team)},
            "them": {**self._team_block(opponent, teams, records, ranks), "sp": self._sp_block(sp_ranked, opponent)},
            "pollWeek": poll_week,
            "line": {"spread": line.spread, "formatted": line.formatted_spread, "spreadOpen": line.spread_open, "overUnder": line.over_under, "overUnderOpen": line.over_under_open} if line else None,  # no provider, no moneylines: the owner shows the line, not the book
            "pregame": {"homeWinProbability": pregame.home_win_probability, "usWinProbability": (pregame.home_win_probability if home_is_us else (1 - pregame.home_win_probability if pregame.home_win_probability is not None else None)), "spread": pregame.spread} if pregame else None,
            "weather": weather,
            "profile": {"us": profiles.rows(self.team), "them": profiles.rows(opponent or ""), "games": {"us": profiles.games_for(self.team), "them": profiles.games_for(opponent or "")}},
            "edges": profiles.edges(self.team, opponent or "") if opponent else [],
            "advanced": {"us": advanced_rows(parts["advanced"].records, self.team), "them": advanced_rows(parts["advanced"].records, opponent or "")},
            "adjusted": adjusted_matchup(parts["adjusted"].records, self.team, opponent),
            "tendencies": tendencies(parts["oppRushes"].records, parts["oppPasses"].records, opponent) if opponent and "oppRushes" in parts else None,
            "advancedBox": advanced_box(parts["advancedBox"].fetched.payload if parts["advancedBox"].fetched else None) if "advancedBox" in parts else None,
            "leaders": side_by_side,
            "series": series,
            "notes": self._with_season_coaches(self._notes_block(notes, notes_error, us_lines, opp_lines), opponent),
            "final": final,
            "ppa": self._ppa_block(parts, opponent, us_week, them_week, us_last, them_last),
            "commonOpponents": common_opponents(parts["games"].records, self.team, opponent),  # Phase 15
            "lastSeason": self._last_season(parts, opponent),  # Phase 15
            "recruiting": {"us": self._team_recruiting(parts, self.team, "us"), "them": self._team_recruiting(parts, opponent, "them") if opponent else None},
            "picker": picker,
            "parts": statuses(parts, now),
        }
        context16.program_extras(data, parts, team=self.team, opponent=opponent, venue=venue)  # Phase 16 BX: form, Elo paths, venue facts, radar, throw and run tables
        return assemble(data, parts)

    def _conference_of(self, stats: list[TeamStat], teams: dict[str, dict[str, Any]], school: str) -> str:
        """The conference a team's stat profile ranks in: its /stats/season conference (the one
        Profiles groups by), else /teams/fbs, else the configured one."""
        found = next((r.conference for r in stats if r.team == school and isinstance(r.conference, str) and r.conference), None)
        return found or teams.get(school, {}).get("conference") or self.settings.conference

    @staticmethod
    def _sp_block(table: RankTable, school: str | None) -> dict[str, Any] | None:
        """A team's SP+ rating and rank from the rating table (Phase 16: with its count and list)."""
        if not school or table.value(school) is None:
            return None
        return {"rating": table.value(school), "rank": table.rank(school), "of": table.of or None, "metric": "rating:sp"}

    def _last_season(self, parts: dict[str, Part], opponent: str | None) -> dict[str, Any]:
        """Both teams' stat profile last season, each value with its national rank. Phase 16: each
        row names its national list, and metricYear says the chips open last season's."""
        stats, games = parts.get("lastStats"), parts.get("lastGames")
        if stats is None or not stats.records:
            return {"year": self.year - 1, "rows": []}
        profiles = profiles_for(stats.records, games.records if games else [], [], self.settings.conference, self.team)
        rows = []
        for spec in PROFILE_ROWS:
            us = profiles.row(self.team, *spec)
            them = profiles.row(opponent, *spec) if opponent else {}
            rows.append({"side": spec[0], "label": spec[1], "key": spec[2], "metric": f"profile:{spec[2]}", "metricYear": self.year - 1, "format": spec[4], "higherIsBetter": spec[3], "us": {"value": us.get("value"), "rank": us.get("nationalRank"), "of": us.get("nationalOf")}, "them": {"value": them.get("value"), "rank": them.get("nationalRank"), "of": them.get("nationalOf")}})
        return {"year": self.year - 1, "rows": rows}

    def _ppa_block(self, parts: dict[str, Part], opponent: str | None, us_week: int | None, them_week: int | None, us_last: Game | None = None, them_last: Game | None = None) -> dict[str, Any]:
        """L9 on the program: PPA per play by game and for the season, plus each team's players from its latest game.
        A postseason latest game's answer covers every postseason game of the team: cut to that game's opponent."""
        us_games = team_game_rows(parts["ppaUs"].records, self.team) if "ppaUs" in parts else []
        them_games = team_game_rows(parts["ppaThem"].records, opponent) if opponent and "ppaThem" in parts else []
        us_rows = gamekeys.only_opponent(parts["ppaPlayersUs"].records, us_last, gamekeys.opponent_of(us_last, self.team)) if "ppaPlayersUs" in parts and us_last else []
        them_rows = gamekeys.only_opponent(parts["ppaPlayersThem"].records, them_last, gamekeys.opponent_of(them_last, opponent)) if opponent and "ppaPlayersThem" in parts and them_last else []
        players_us = player_rows(us_rows, self.team)
        players_them = player_rows(them_rows, opponent)
        return {
            "available": bool(us_games or them_games),
            "season": {"us": season_average(us_games), "them": season_average(them_games)},
            "games": {"us": us_games, "them": them_games},
            "players": {"us": players_us, "them": players_them, "usWeek": us_week, "themWeek": them_week},
            "seasonLeaders": {"us": ppa_season_rows(parts["ppaSeason_us"].records, self.team, 10)[:8] if "ppaSeason_us" in parts else [], "them": ppa_season_rows(parts["ppaSeason_them"].records, opponent, 10)[:8] if opponent and "ppaSeason_them" in parts else []},
            "usage": {"us": usage_rows(parts["usage_us"].records, self.team)[:8] if "usage_us" in parts else [], "them": usage_rows(parts["usage_them"].records, opponent)[:8] if opponent and "usage_them" in parts else []},
        }

    def _recruiting_fetches(self, school: str, prefix: str) -> list[Any]:
        """The parts behind the blue-chip ratio, returning production, season PPA and usage of one team."""
        return [
            *(self._f(f"recruits_{prefix}_{y}", "/recruiting/players", {"year": y, "team": school}, Recruit, DataKind.RECRUITING) for y in range(self.year - 3, self.year + 1)),
            self._f(f"returning_{prefix}", "/player/returning", {"year": self.year, "team": school}, ReturningProduction, DataKind.SEASON_STATS),
            self._f(f"ppaSeason_{prefix}", "/ppa/players/season", {"year": self.year, "team": school}, PlayerSeasonPpa, DataKind.SEASON_STATS),
            self._f(f"usage_{prefix}", "/player/usage", {"year": self.year, "team": school}, PlayerUsage, DataKind.SEASON_STATS),
        ]

    def _team_recruiting(self, parts: dict[str, Part], school: str | None, prefix: str) -> dict[str, Any] | None:
        if not school:
            return None
        classes = {y: parts[f"recruits_{prefix}_{y}"].records for y in range(self.year - 3, self.year + 1) if f"recruits_{prefix}_{y}" in parts}
        # Phase 16: the rating table's FBS population, the same "of" as the Ratings page and the list
        fbs = fbs_set(parts["teams"].records) if "teams" in parts else None
        talent = talent_lookup(parts["talent"].records, fbs) if "talent" in parts else {}
        extra = PageRanks(parts, self.year, fbs)  # Phase 16 NV: the same tables as the bluechip:ratio and returning:<key> lists
        return {
            "school": school,
            "blueChip": extra.bluechip_block(blue_chip(classes), school) if classes else None,
            "stars": star_counts(classes) if classes else None,  # Phase 17 #36: the same signees by stars
            "sides": recruit_sides(classes) if classes else None,  # Phase 17 #24: offense and defense apart
            "costs": self._cost_total(school),  # Phase 17 Part 3b: the rumored roster total, for the two-team table
            "talent": talent.get(school),
            "talentOf": len(talent) or None,
            "returning": extra.returning_block(returning_block(parts[f"returning_{prefix}"].records, school), school) if f"returning_{prefix}" in parts else None,
        }

    async def _weather(self, game: Game, venue: Venue | None, parts: dict[str, Part], kickoff_local: datetime | None) -> dict[str, Any]:
        cfbd = parts.get("cfbdWeather")
        if cfbd is not None and cfbd.ok:
            row = next((w for w in cfbd.records if w.id == game.id), None)
            if row is not None:
                # verified 2026-09-23 on Tier 2: windDirection is degrees, weatherCondition can be null
                return {"available": True, "source": "CFBD", "tempF": row.temperature, "windMph": row.wind_speed, "windDir": compass(row.wind_direction), "sky": row.weather_condition, "precipChance": None, "precipitation": row.precipitation, "humidity": row.humidity, "dome": row.game_indoors, "stale": cfbd.fetched.stale, "error": cfbd.fetched.error, "fetchedAt": cfbd.status(self.client._clock())["fetchedAt"]}
        if venue is None or venue.latitude is None or venue.longitude is None:
            return {"available": False, "source": "National Weather Service", "error": "No venue coordinates for this game yet." if game.venue_id else "No venue on the schedule yet.", "stale": False}
        if kickoff_local is None:
            return {"available": False, "source": "National Weather Service", "error": "No kickoff time yet.", "stale": False}
        days_out = (kickoff_local.date() - self.client._clock().astimezone(self.settings.tzinfo).date()).days
        if days_out > 6:
            return {"available": False, "source": "National Weather Service", "error": f"The forecast reaches seven days out; this game is {days_out} days away.", "stale": False, "dome": venue.dome}
        if days_out < 0:
            return {"available": False, "source": "National Weather Service", "error": "Game day has passed; no forecast to show.", "stale": False, "dome": venue.dome}
        try:
            forecast = await self.weather.forecast(venue.latitude, venue.longitude, kickoff_local.date())
        except Exception as exc:  # noqa: BLE001 - the program must not die on weather; it is logged
            log.exception("Weather lookup failed")
            return {"available": False, "source": "National Weather Service", "error": f"unexpected error: {exc.__class__.__name__}", "stale": False}
        result = forecast.as_dict(kickoff_local)
        result["dome"] = venue.dome
        return result

    def _series(self, records: list[Matchup], opponent: str | None) -> dict[str, Any] | None:
        matchup = records[0] if records else None
        if matchup is None:
            return None
        games = sorted(matchup.games or [], key=lambda g: (g.season or 0, g.week or 0), reverse=True)
        streak_team, streak = None, 0
        for g in games:
            if not g.winner:
                break
            if streak_team is None:
                streak_team, streak = g.winner, 1
            elif g.winner == streak_team:
                streak += 1
            else:
                break
        return {
            "team1": matchup.team1, "team2": matchup.team2, "team1Wins": matchup.team1_wins, "team2Wins": matchup.team2_wins, "ties": matchup.ties,
            "usWins": matchup.team1_wins if matchup.team1 == self.team else matchup.team2_wins,
            "themWins": matchup.team2_wins if matchup.team1 == self.team else matchup.team1_wins,
            "streak": {"team": streak_team, "games": streak} if streak_team else None,
            "lastTen": [{"season": g.season, "week": g.week, "date": g.date, "homeTeam": g.home_team, "awayTeam": g.away_team, "homeScore": g.home_score, "awayScore": g.away_score, "winner": g.winner, "venue": g.venue, "neutralSite": g.neutral_site} for g in games[:10]],
        }

    def _picker(self, games: list[Game], teams: dict[str, dict[str, Any]], ranks: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        out = []
        for g in sorted((g for g in games if g.week is not None), key=gamekeys.order):
            home_is_us = g.home_team == self.team
            opponent = g.away_team if home_is_us else g.home_team
            us, them = (g.home_points, g.away_points) if home_is_us else (g.away_points, g.home_points)
            result = None
            if g.completed and us is not None and them is not None:
                result = "W" if us > them else "L" if us < them else "T"
            out.append({"gameId": g.id, "week": g.week, "postseason": gamekeys.label(g), "date": g.start_date, "startTimeTbd": bool(g.start_time_tbd), "opponent": {**teams.get(opponent or "", {}), "school": opponent, "apRank": ranks.get("AP", {}).get(opponent or "")}, "homeAway": "neutral" if g.neutral_site else ("home" if home_is_us else "away"), "completed": bool(g.completed), "result": result, "usPoints": us, "themPoints": them, "venue": g.venue})
        return out

    def _notes_block(self, notes: Any, error: str | None, us_lines: dict | None = None, opp_lines: dict | None = None) -> dict[str, Any]:
        if notes is None:
            return {"present": False, "error": error, "sections": [], "availability": [], "schemes": None, "lineups": None, "broadcast": None, "coaches": None, "sources": [], "author": None, "writtenAt": None}
        return {
            "present": True,
            "error": None,
            "author": notes.author,
            "writtenAt": notes.writtenAt,
            "sources": [s.model_dump() for s in notes.sources],
            "sections": [s.model_dump() for s in notes.sections],
            "availability": [a.model_dump() for a in notes.availability],
            "availabilitySource": notes.availabilitySource,
            "availabilityUpdatedAt": notes.availabilityUpdatedAt,
            "schemes": notes.schemes.model_dump() if notes.schemes else None,
            "lineups": attach_lineup_stats(notes.lineups.model_dump(), us_lines or {}, opp_lines or {}) if notes.lineups else None,  # 2026-10-02: both depth charts, starters first, season chips
            "broadcast": notes.broadcast.model_dump() if notes.broadcast else None,  # public release Phase 7b: the TV crew
            "coaches": notes.coaches.model_dump() if notes.coaches else None,  # and both coaching staffs, from the notes
        }

    def _cost_total(self, school: str | None) -> dict[str, Any] | None:
        row = self.season_notes.costs_for(school)
        if not row or row.get("totalUsd") is None:
            return None
        return {"totalUsd": row.get("totalUsd"), "note": row.get("note"), "asOf": row.get("asOf"), "savedAt": row.get("savedAt")}

    def _staff(self, school: str) -> dict[str, Any] | None:
        coaches = self.season_notes.coaches_for(school)
        pre = self.season_notes.preseason_for(school)
        full = [m.model_dump(exclude_none=True) for m in pre.staff] if pre else []
        if not coaches and not full:
            return None
        return {
            "headCoach": (coaches or {}).get("headCoach"),
            "offensiveCoordinator": (coaches or {}).get("offensiveCoordinator"),
            "defensiveCoordinator": (coaches or {}).get("defensiveCoordinator"),
            "savedAt": (coaches or {}).get("savedAt"),
            "full": full,
        }

    def _with_season_coaches(self, block: dict[str, Any], opponent: str | None) -> dict[str, Any]:
        """Phase 17 Part 3a: each side's head coach and coordinators from the season's coaches batch where the game's
        own notes name none (the notes are newer, so a name they give always stands)."""
        coaches = block.get("coaches") if isinstance(block.get("coaches"), dict) else {}
        filled = False
        out = dict(coaches)
        for side, school in (("us", self.team), ("them", opponent)):
            season = self.season_notes.coaches_for(school)
            if not season:
                continue
            have = dict(out.get(side) or {})
            for key in ("headCoach", "offensiveCoordinator", "defensiveCoordinator"):
                if not have.get(key) and season.get(key):
                    have[key] = season[key]
                    filled = True
            have.setdefault("team", school)
            out[side] = have
        if filled:
            out.setdefault("source", "The season's coaches load")
            return {**block, "coaches": out}
        return block

    def _final_box(self, parts: dict[str, Part], game: Game, opponent: str | None) -> dict[str, Any]:
        sides, players = box_sides(parts.get("boxTeams"), parts.get("boxPlayers"), game)
        return {"us": sides.get(self.team), "them": sides.get(opponent or ""), "players": {"us": players.get(self.team, {}), "them": players.get(opponent or "", {})}, "available": bool(sides)}

    async def fbs_teams(self) -> list[Team]:
        """CFBD's FBS teams this season (cached), for the season prompts' conferences and primary teams."""
        return [t for t in (await self._core())["teams"].records if isinstance(t, Team)]

    async def team_meta(self) -> dict[str, dict[str, Any]]:
        """Every FBS team's school, mascot and conference from /teams/fbs (cached), for the Wikipedia lookups."""
        return self._teams((await self._core())["teams"])

    # --- Phase 17 #17: the leaders side by side, the whole line --------------------------------------

    async def leaders(self, game_id: int | None) -> Assembled | None:
        """The program's leaders with each one's whole line: every stat of the category with national and
        conference ranks (from the national pulls the Leaders page caches), and the line over conference games
        only (each conference game's /games/players box, cached for good: ours share the program's keys, so a
        week costs the opponent's new games at most). Loaded by the band on its own, so the program stays fast."""
        parts = await self._core()
        game = self._pick_game(parts["schedule"].records, game_id)
        if game is None:
            if parts["schedule"].ok:
                return None
            return assemble({"gameId": game_id, "game": None, "parts": statuses(parts, self.client._clock())}, parts)
        opponent = game.away_team if game.home_team == self.team else game.home_team
        teams = self._teams(parts["teams"])
        conference_of = {school: meta["conference"] for school, meta in teams.items() if isinstance(meta.get("conference"), str) and meta["conference"]}

        def conference_games(team: str | None, pool: list[Game]) -> list[Game]:
            if not team:
                return []
            seen: set[int] = set()
            out = []
            for g in sorted(pool, key=gamekeys.order):
                if g.id in seen or not g.completed or g.conference_game is not True or team not in (g.home_team, g.away_team) or g.week is None:
                    continue
                seen.add(g.id)
                out.append(g)
            return out

        ours = conference_games(self.team, parts["schedule"].records)
        theirs = conference_games(opponent, parts["games"].records)
        fetches = [
            self._f("playersTeam", "/stats/player/season", {"year": self.year, "team": self.team}, PlayerStat, DataKind.SEASON_STATS),
            *([self._f("playersOpponent", "/stats/player/season", {"year": self.year, "team": opponent}, PlayerStat, DataKind.SEASON_STATS)] if opponent else []),
            *(self._f(f"national_{c}", "/stats/player/season", {"year": self.year, "category": c}, PlayerStat, DataKind.SEASON_STATS) for c in CATEGORIES if c in ("passing", "rushing", "receiving", "defensive")),
            *(self._f(f"confBox_us_{g.id}", "/games/players", gamekeys.box_params(g, self.year, self.team), GamePlayerStats, DataKind.FINISHED_GAME) for g in ours),
            *(self._f(f"confBox_them_{g.id}", "/games/players", gamekeys.box_params(g, self.year, opponent), GamePlayerStats, DataKind.FINISHED_GAME) for g in theirs if opponent),
        ]
        for part in await asyncio.gather(*fetches):
            parts[part.name] = part
        fbs = fbs_set(parts["teams"].records)
        national = {c: fbs_lines(parts[f"national_{c}"].records, fbs) for c in ("passing", "rushing", "receiving", "defensive") if f"national_{c}" in parts}
        index = RankIndex(national, conference_of)
        boxes = lambda side, games: [b for g in games for b in (parts[f"confBox_{side}_{g.id}"].records if f"confBox_{side}_{g.id}" in parts else []) if b.id == g.id]  # noqa: E731 - read twice below
        conf_us = game_totals(boxes("us", ours))
        conf_them = game_totals(boxes("them", theirs))
        us_lines = lines_from(parts["playersTeam"].records)
        opp_lines = lines_from(parts["playersOpponent"].records) if "playersOpponent" in parts else {}

        def side(lines: dict[tuple[str, str], Any], board: Any, conf: dict[tuple[str, str], dict[str, float]]) -> dict[str, Any] | None:
            top = board_entries(lines, board)[:1]
            if not top:
                return None
            line = top[0]
            in_conf = conf.get((line.player_id, board.category))
            return {
                "playerId": line.player_id,
                "player": line.player,
                "position": line.position,
                "value": line.stats.get(board.stat),
                "headshotUrl": f"/media/headshot/{line.player_id}",
                "detail": leader_detail(line, board.category, index),
                "conferenceGames": {"stats": in_conf} if in_conf else None,
            }

        categories = []
        for category, stat, label in SIDE_BY_SIDE:
            board = next(b for b in BOARDS if b.category == category and b.stat == stat)
            categories.append({"label": label, "category": category, "stat": stat, "format": board.format, "us": side(us_lines, board, conf_us), "them": side(opp_lines, board, conf_them)})
        data = {
            "gameId": game.id,
            "categories": categories,
            "conferenceGames": {
                "us": {"games": len(ours), "conference": conference_of.get(self.team)},
                "them": {"games": len(theirs), "conference": conference_of.get(opponent or "")},
            },
            "parts": statuses(parts, self.client._clock()),
        }
        return assemble(data, parts)

    # --- Phase 17 #2: the box score of any game this season ----------------------------------------

    async def box(self, game_id: int) -> Assembled | None:
        """Any game of this season by id: the header from the season's game list (already cached), and once it
        is final the team and player box from /games/teams and /games/players, cached for good (a final box
        does not change). Our own games use the program's cache keys. None when the id is not a game this season."""
        parts = await self._core()
        game = next((g for g in [*parts["games"].records, *parts["schedule"].records] if g.id == game_id), None)
        if game is None:
            if parts["games"].ok:
                return None
            return assemble({"gameId": game_id, "game": None, "parts": statuses(parts, self.client._clock())}, parts)
        home, away = game.home_team or "", game.away_team or ""
        if game.completed and home:
            keyed = self.team if self.team in (home, away) else home  # our games share the program's cache keys
            boxes = await asyncio.gather(
                self._f("boxTeams", "/games/teams", gamekeys.box_params(game, self.year, keyed), GameTeamStats, DataKind.FINISHED_GAME),
                self._f("boxPlayers", "/games/players", gamekeys.box_params(game, self.year, keyed), GamePlayerStats, DataKind.FINISHED_GAME),
            )
            for part in boxes:
                parts[part.name] = part
        teams = self._teams(parts["teams"])
        records = {r.team: r for r in parts["records"].records}
        ranks, _ = self._poll_ranks(parts["rankings"])
        sides, players = box_sides(parts.get("boxTeams"), parts.get("boxPlayers"), game)
        kickoff_local = self._local(game.start_date)
        data = {
            "season": self.year,
            "game": {
                "gameId": game.id,
                "week": game.week,
                "postseason": gamekeys.label(game),
                "kickoff": game.start_date,
                "kickoffLocal": kickoff_local.isoformat() if kickoff_local else None,
                "completed": bool(game.completed),
                "neutralSite": bool(game.neutral_site),
                "conferenceGame": game.conference_game,
                "venue": game.venue,
                "isOurs": self.team in (home, away),
            },
            "home": {**self._team_block(home or None, teams, records, ranks), "points": game.home_points, "lineScores": game.home_line_scores},
            "away": {**self._team_block(away or None, teams, records, ranks), "points": game.away_points, "lineScores": game.away_line_scores},
            "final": {"home": sides.get(home), "away": sides.get(away), "players": {"home": players.get(home, {}), "away": players.get(away, {})}, "available": bool(sides)},
            "parts": statuses(parts, self.client._clock()),
        }
        return assemble(data, parts)

    # --- the newspaper (N1 to N4) -------------------------------------------------------------------

    async def newspaper(self) -> Assembled:
        parts = await self._core()
        now_local = self.client._clock().astimezone(self.settings.tzinfo)
        today = now_local.date()
        games = parts["schedule"].records
        todays = [g for g in games if (local := self._local(g.start_date)) is not None and local.date() == today]
        game = todays[0] if todays else None
        next_game = self._pick_game(games, None)
        game_day = game is not None
        # Phase 12: a Saturday in the regular season we do not play (a bye) still gets the slate, from CFBD's
        # calendar week. (Phase 17 #32: the app always opens on the Game program, so the paper no longer says
        # whether it opens here.)
        slate_week = game.week if game_day else None
        slate_type = (game.season_type or "regular") if game_day else "regular"
        bye = False
        # Phase 15: in bowl season (December and January) any day with games gets the slate; the
        # postseason is one CFBD week. Other weekdays ask for nothing, as before.
        if not game_day and (now_local.weekday() == SATURDAY or now_local.month in (12, 1)):
            calendar = await self._f("calendar", "/calendar", {"year": self.year}, CalendarWeek, DataKind.REFERENCE)
            parts["calendar"] = calendar
            slot = calendar_slot(calendar.records, self.client._clock())
            if slot is not None and slot[1] == gamekeys.POSTSEASON:
                slate_week, slate_type = slot
            elif slot is not None and now_local.weekday() == SATURDAY:
                slate_week, slate_type = slot
                bye = True

        slate: list[dict[str, Any]] = []
        if slate_week is not None:
            week_params: dict[str, Any] = {"year": self.year, "week": slate_week}
            if slate_type == gamekeys.POSTSEASON:
                week_params["seasonType"] = gamekeys.POSTSEASON
            week_parts = await asyncio.gather(
                self._f("weekGames", "/games", week_params, Game, DataKind.SCHEDULE),
                self._f("weekLines", "/lines", week_params, BettingGame, DataKind.LINES),
                self._f("weekPregame", "/metrics/wp/pregame", week_params, PregameWinProbability, DataKind.SEASON_STATS),
                self._f("weekMedia", "/games/media", week_params, GameMedia, DataKind.SCHEDULE),
            )
            for part in week_parts:
                parts[part.name] = part
            slate = self._slate(parts, today, self._opponents(games, next_game), postseason=slate_type == gamekeys.POSTSEASON)

        feed_results = await self.feeds.all()
        now = self.client._clock()
        # Phase 17 #26: the season's headlines by game week, with a topic and the players each names. The rosters
        # are ours and the next opponent's (both kept a week, as on the program); a failed one only names fewer.
        roster_parts = [await self._f("roster", "/roster", {"team": self.team, "year": self.year}, RosterPlayer, DataKind.ROSTER)]
        next_opponent = (next_game.away_team if next_game.home_team == self.team else next_game.home_team) if next_game else None
        if next_opponent:
            roster_parts.append(await self._f("opponentRoster", "/roster", {"team": next_opponent, "year": self.year}, RosterPlayer, DataKind.ROSTER))
        for part in roster_parts:
            parts[part.name] = part
        rosters = [(self.team, parts["roster"].records)] + ([(next_opponent, parts["opponentRoster"].records)] if "opponentRoster" in parts else [])
        weeks = paper_weeks(self.archive.add(self.year, feed_results), games, self.team, tz=self.settings.tzinfo, rosters=rosters)
        data = {
            "season": self.year,
            "today": today.isoformat(),
            "gameDay": game_day,
            "slateDay": slate_week is not None,
            "byeWeek": bye,
            "slateWeek": slate_week,
            "kickoff": game.start_date if game else None,
            "gameId": game.id if game else None,
            "nextGame": {"gameId": next_game.id, "date": next_game.start_date, "opponent": next_game.away_team if next_game.home_team == self.team else next_game.home_team} if next_game else None,
            "slate": slate,
            "slateNote": None if slate_week is not None else "The slate shows on Saturdays in the season. Headlines are here every day.",
            "news": merge_headlines(feed_results),
            "weeks": weeks,
            "feeds": {r.feed.id: {"name": r.feed.name, **r.status(now)} for r in feed_results},
            "parts": statuses(parts, now),
        }
        context16.newspaper_extras(data, parts)  # Phase 16 BX: form on the game cards
        return assemble(data, parts)

    def _opponents(self, games: list[Game], next_game: Game | None) -> dict[str, str]:
        """{school: "next" | "future"} for our opponents still to play, so their games today are
        pinned on the slate whatever their rank or conference."""
        out: dict[str, str] = {}
        now = self.client._clock()
        for g in games:
            kickoff = self._local(g.start_date)
            if g.completed or kickoff is None or kickoff < now:
                continue
            opponent = g.away_team if g.home_team == self.team else g.home_team
            if opponent:
                out.setdefault(opponent, "future")
        if next_game is not None:
            opponent = next_game.away_team if next_game.home_team == self.team else next_game.home_team
            if opponent:
                out[opponent] = "next"
        return out

    def _slate(self, parts: dict[str, Part], today: Any, opponents: dict[str, str] | None = None, *, postseason: bool = False) -> list[dict[str, Any]]:
        teams = self._teams(parts["teams"])
        records = {r.team: r for r in parts["records"].records}
        ranks, _ = self._poll_ranks(parts["rankings"])
        ap = ranks.get("AP", {})
        lines = {b.id: b for b in parts["weekLines"].records}
        wp = {p.game_id: p for p in parts["weekPregame"].records}
        media = {m.id: m.outlet for m in parts["weekMedia"].records if (m.media_type or "").lower() == "tv" and m.outlet}
        # Final pass (N2): points and yards a game with their national ranks for both teams, and the biggest edge of the
        # matchup, from the same profiles every page ranks with (no extra call: the stats are already in the core parts)
        profiles = profiles_for(parts["stats"].records, parts["games"].records, parts["schedule"].records, self.settings.conference, self.team) if parts["stats"].ok else None
        card_specs = [spec for spec in PROFILE_ROWS if spec[2] in ("ppg", "ypg")]

        def card_rows(team: str | None) -> list[dict[str, Any]] | None:
            if profiles is None or not team:
                return None
            rows = []
            for spec in card_specs:
                row = profiles.row(team, *spec)
                if row.get("value") is None:
                    continue
                rows.append({"key": spec[2], "label": spec[1], "value": row.get("value"), "format": spec[4], "rank": row.get("nationalRank"), "of": row.get("nationalOf"), "metric": f"profile:{spec[2]}"})
            return rows or None

        def biggest_edge(home: str | None, away: str | None) -> dict[str, Any] | None:
            if profiles is None or not home or not away:
                return None
            try:
                edges = profiles.edges(home, away)  # "us" is the home team here
            except Exception:  # noqa: BLE001 - a slate card never fails the paper over one pairing; logged by the caller
                log.exception("No edge for %s at %s", away, home)
                return None
            if not edges:
                return None
            top = edges[0]
            unit = str(top.get("label") or "").split(":")[0].strip()
            return {"stat": unit, "side": top.get("side"), "edge": top.get("edge"), "homeRank": top.get("usRank"), "awayRank": top.get("themRank")}

        out = []
        for g in parts["weekGames"].records:
            local = self._local(g.start_date)
            if local is None or local.date() != today or not g.home_team or not g.away_team:
                continue
            watch = next((opponents[t] for t in (g.home_team, g.away_team) if opponents and t in opponents and t != self.team), None)
            # A bowl day carries every bowl (a handful); a regular Saturday only the Top 25 and the conference.
            if not postseason and watch is None and not (g.home_team in ap or g.away_team in ap or self.settings.conference in (g.home_conference, g.away_conference)):
                continue
            book = lines.get(g.id)
            line = book.lines[0] if book and book.lines else None
            out.append({
                "gameId": g.id, "week": g.week, "bowl": gamekeys.label(g), "playoffRound": gamekeys.playoff_round(g), "kickoff": g.start_date, "startTimeTbd": bool(g.start_time_tbd), "tv": media.get(g.id), "venue": g.venue, "neutralSite": bool(g.neutral_site), "conferenceGame": g.conference_game,
                "home": self._team_block(g.home_team, teams, records, ranks), "away": self._team_block(g.away_team, teams, records, ranks),
                "isUs": self.team in (g.home_team, g.away_team), "completed": bool(g.completed), "homePoints": g.home_points, "awayPoints": g.away_points,
                "line": {"spread": line.spread, "formatted": line.formatted_spread, "overUnder": line.over_under} if line else None,
                "homeWinProbability": wp[g.id].home_win_probability if g.id in wp else None,
                "watch": None if self.team in (g.home_team, g.away_team) else watch,  # "next": our next opponent plays; "future": a later one
                "stats": {"home": card_rows(g.home_team), "away": card_rows(g.away_team)},  # N2 (final pass)
                "edge": biggest_edge(g.home_team, g.away_team),
            })
        out.sort(key=lambda s: (not s["isUs"], {"next": 0, "future": 1}.get(s.get("watch") or "", 2), s.get("kickoff") or ""))
        return out

    # --- the team page (T1) ---------------------------------------------------------------------------

    async def team_page(self, school: str) -> Assembled | None:
        parts = await self._core()
        teams = self._teams(parts["teams"])
        if school not in teams and parts["teams"].ok:
            return None
        extra = await asyncio.gather(
            self._f("teamGames", "/games", {"year": self.year, "team": school}, Game, DataKind.SCHEDULE),
            self._f("teamMedia", "/games/media", {"year": self.year, "team": school}, GameMedia, DataKind.SCHEDULE),
            self._f("teamRoster", "/roster", {"team": school, "year": self.year}, RosterPlayer, DataKind.ROSTER),
            self._f("coaches", "/coaches", {"team": school, "year": self.year}, Coach, DataKind.TEAMS),
            self._f("advanced", "/stats/season/advanced", {"year": self.year, "classification": "fbs"}, AdvancedSeasonStat, DataKind.SEASON_STATS),
            self._f("sp", "/ratings/sp", {"year": self.year}, TeamSP, DataKind.SEASON_STATS),
            *([self._f("series", "/teams/matchup", {"team1": self.team, "team2": school}, Matchup, DataKind.HISTORY)] if school != self.team else []),
            *self._recruiting_fetches(school, "team"),
            *page_fetches(self.fetcher, self.year),  # Phase 16 NV: blue-chip and returning ranks, the lists' own keys
            self._f("talent", "/talent", {"year": self.year}, TeamTalent, DataKind.SEASON_STATS),
            self._f("portal", "/player/portal", {"year": self.year}, PlayerTransfer, DataKind.SEASON_STATS),  # Phase 13: where transfers came from
        )
        for part in extra:
            parts[part.name] = part
        records = {r.team: r for r in parts["records"].records}
        ranks, poll_week = self._poll_ranks(parts["rankings"])
        # Phase 16 (G3-01 d): a team page ranks inside the team's own conference (its /stats/season
        # conference, as Profiles groups teams), so a Big 12 team's "Conf" column is the Big 12's
        conference = self._conference_of(parts["stats"].records, teams, school)
        profiles = profiles_for(parts["stats"].records, parts["games"].records, parts["schedule"].records, conference, self.team)  # the same games as every page
        tv = {m.id: m.outlet for m in parts["teamMedia"].records if (m.media_type or "").lower() == "tv" and m.outlet}
        schedule = []
        for g in sorted((g for g in parts["teamGames"].records if g.week is not None), key=gamekeys.order):
            home = g.home_team == school
            opponent = g.away_team if home else g.home_team
            us, them = (g.home_points, g.away_points) if home else (g.away_points, g.home_points)
            result = None
            if g.completed and us is not None and them is not None:
                result = "W" if us > them else "L" if us < them else "T"
            schedule.append({"gameId": g.id, "week": g.week, "postseason": gamekeys.label(g), "date": g.start_date, "startTimeTbd": bool(g.start_time_tbd), "opponent": {**teams.get(opponent or "", {}), "school": opponent, "apRank": ranks.get("AP", {}).get(opponent or "")}, "homeAway": "neutral" if g.neutral_site else ("home" if home else "away"), "completed": bool(g.completed), "result": result, "usPoints": us, "themPoints": them, "tv": tv.get(g.id), "venue": g.venue})
        roster = []
        transfers = portal_index(parts["portal"].records, school) if "portal" in parts else {}
        today = self.client._clock().astimezone(self.settings.tzinfo).date()
        for p in parts["teamRoster"].records:
            age, born = self.season_notes.age(school, " ".join(x for x in (p.first_name, p.last_name) if x), today)  # Phase 17 #38
            roster.append({"age": age, "born": born, "transfer": transfer_for(transfers, p.first_name, p.last_name), "isUs": school == self.team, "playerId": p.id, "number": p.jersey, "name": " ".join(x for x in (p.first_name, p.last_name) if x) or None, "position": p.position, **class_fields(p.year, None, self.year), "heightText": f"{int(p.height) // 12}-{int(p.height) % 12}" if p.height else None, "weight": p.weight, "hometown": ", ".join(x for x in (p.home_city, p.home_state) if x) or None, "headshotUrl": f"/media/headshot/{p.id}"})
        roster.sort(key=lambda r: (r["number"] is None, r["number"] or 0, r["name"] or ""))
        coaches = []
        for c in parts["coaches"].records:
            season = next((s for s in c.seasons if s.year == self.year and s.school == school), None) or (c.seasons[0] if c.seasons else None)
            coaches.append({"name": " ".join(x for x in (c.first_name, c.last_name) if x) or None, "hireDate": c.hire_date, "wins": season.wins if season else None, "losses": season.losses if season else None, "ties": season.ties if season else None, "year": season.year if season else None, "srs": season.srs if season else None, "spOverall": season.sp_overall if season else None})
        sp_ranked = sp_tables(parts["sp"].records, fbs_set(parts["teams"].records))["sp"]
        data = {
            "season": self.year,
            "team": {**self._team_block(school, teams, records, ranks), "sp": self._sp_block(sp_ranked, school), "isUs": school == self.team},
            "location": self._location(parts["teams"], school),
            "pollWeek": poll_week,
            "profile": {"rows": profiles.rows(school), "games": profiles.games_for(school), "conference": conference},
            "advanced": {"rows": advanced_rows(parts["advanced"].records, school)},
            "schedule": schedule,
            "roster": roster,
            "coaches": coaches,
            "standings": self._team_standings(parts, teams, ranks, school),
            "staff": self._staff(school),  # Phase 17 Part 3a: coordinators for every team, the full staff for primaries
            "costs": self.season_notes.costs_for(school),  # Phase 17 Part 3b: rumored roster costs  # Phase 17 #2: the conference record chip opens these
            "series": self._series(parts["series"].records, school) if "series" in parts else None,
            "recruiting": self._team_recruiting(parts, school, "team"),
            "playValue": {"players": ppa_season_rows(parts["ppaSeason_team"].records, school, 10)[:10] if "ppaSeason_team" in parts else [], "usage": usage_rows(parts["usage_team"].records, school)[:10] if "usage_team" in parts else []},
            "parts": statuses(parts, self.client._clock()),
        }
        context16.team_extras(data, parts, school)  # Phase 16 BX: form and the Elo path
        return assemble(data, parts)

