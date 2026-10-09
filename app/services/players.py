"""Leaders (S6 to S9), the roster page, recruiting (R1 to R3), and player cards (X1).

Every source comes through the CFBD client and app/services/parts.py. Leader boards are built
from bulk pulls (one per category for all of D1, filtered to FBS here) and ranked locally, so a
board never costs one call per team. Calls on a cold cache: teams, schedule, team player stats,
conference player stats, seven category pulls, and the opponent's stats when the opponent is
outside the conference. The roster page adds the roster and five recruiting classes; a player
card adds the prior rosters and one player box score per finished game of the player's own team
(cached for good). An opponent's finished games come from the league-wide schedule answer the
Season view and the program already cache, so an opponent card asks for no schedule of its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.cache import DataKind
from app.cfbd.client import CfbdClient
from app.cfbd.models import (  # Phase 10
    Game,
    GamePlayerStats,
    KickerPAAR,
    PlayerGamePpa,
    PlayerSeasonPpa,
    PlayerStat,
    PlayerTransfer,
    PlayerUsage,
    PlayerWeightedEPA,
    Recruit,
    RosterPlayer,
    Team,
    TeamRecruitingRanking,
)
from app.config import Settings
from app.services import context16, gamekeys
from app.services.classes import class_fields, class_label
from app.services.depth2 import class_rank, player_boards, portal_index, shared_ranks, transfer_for
from app.services.logos import logo_fields
from app.services.national_extra import PageRanks, page_fetches, recruit_metric  # Phase 16 NV: the extra-call lists' keys and ranks
from app.services.notes import load_notes
from app.services.parts import Assembled, Part, PartFetcher, assemble, statuses
from app.services.profiles import tie_ranks
from app.services.season_notes import SeasonNotes
from app.services.stats_extra import blue_chip, ppa_game_rows, ppa_season_rows, recruit_block, usage_rows  # Phase 10

log = logging.getLogger("kickoff.players")
PPA_MIN_PLAYS = 50  # a season PPA average means little under this many plays (the national board)
PPA_MIN_PLAYS_TEAM = 10
# CFBD's threshold filters the national pull. This local floor only backs it up, and sits under 50
# because a count derived from a three-place average can read up to 5% low (47 for a 50-play player).
PPA_MIN_PLAYS_NATIONAL_CHECK = 45

CATEGORIES = ("passing", "rushing", "receiving", "defensive", "interceptions", "kicking", "punting")
TEAM_TOP = 5
SCOPE_TOP = 10


@dataclass(frozen=True)
class Board:
    category: str
    stat: str
    label: str
    format: str = "0f"
    min_stat: tuple[str, float] | None = None  # e.g. ("NO", 5): at least five punts before an average counts

    @property
    def id(self) -> str:
        return f"{self.category}:{self.stat}"


BOARDS: list[Board] = [
    Board("passing", "YDS", "Passing yards"),
    Board("rushing", "YDS", "Rushing yards"),
    Board("receiving", "YDS", "Receiving yards"),
    Board("defensive", "TOT", "Tackles"),
    Board("defensive", "SACKS", "Sacks", "1f"),
    Board("interceptions", "INT", "Interceptions"),
    Board("kicking", "FGM", "Field goals made"),
    Board("punting", "YPP", "Punting average", "1f", ("NO", 5)),
]

# Which board leads the offense and the defense impact lists, in order.
IMPACT_OFFENSE = ["passing:YDS", "rushing:YDS", "receiving:YDS"]
IMPACT_DEFENSE = ["defensive:TOT", "defensive:SACKS", "interceptions:INT"]


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


def _scalar(value: Any) -> float | str | None:
    number = _num(value)
    if number is not None:
        return number
    return value if isinstance(value, str) and value.strip() else None


def history_classes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Name each History row's class (Phase 17, #19). CFBD's older rosters carry the player's current class
    (its 2024 roster lists a 2024 freshman as a junior), so a past season counts back one class a year from
    the latest season the player appears in. Below freshman (a redshirt year the data cannot show) or with
    no class to count from, the row's class is None and the card shows a dash."""
    anchor = next((r for r in reversed(rows) if isinstance(r.get("classYear"), int) and 1 <= r["classYear"] <= 5), None)
    out = []
    for row in rows:
        level = anchor["classYear"] - (anchor["year"] - row["year"]) if anchor is not None else None
        out.append({**row, "classYear": class_label(level) if level is not None else None})
    return out


def _height_text(inches: float | None) -> str | None:
    if inches is None or inches <= 0:
        return None
    whole = int(inches)
    return f"{whole // 12}-{whole % 12}"


def _record_text(game: Game, team: str) -> tuple[str | None, str | None]:
    """(opponent, 'W 44-39') for one finished game from the team's point of view."""
    home_is_us = game.home_team == team
    opponent = game.away_team if home_is_us else game.home_team
    us = game.home_points if home_is_us else game.away_points
    them = game.away_points if home_is_us else game.home_points
    if us is None or them is None:
        return opponent, None
    letter = "W" if us > them else "L" if us < them else "T"
    return opponent, f"{letter} {us}-{them}"


# --- stat lines ------------------------------------------------------------------------------


@dataclass
class Line:
    player_id: str
    player: str | None
    position: str | None
    team: str | None
    conference: str | None
    category: str
    stats: dict[str, float | str]


def lines_from(records: list[PlayerStat]) -> dict[tuple[str, str], Line]:
    """(playerId, category) -> one line with every stat type, from the flat CFBD rows."""
    lines: dict[tuple[str, str], Line] = {}
    for row in records:
        if not row.category or not row.stat_type:
            continue
        key = (row.player_id, row.category)
        line = lines.get(key)
        if line is None:
            line = Line(row.player_id, row.player, row.position, row.team, row.conference, row.category, {})
            lines[key] = line
        value = _scalar(row.stat)
        if value is not None:
            line.stats[row.stat_type] = value
    return lines


def board_entries(lines: dict[tuple[str, str], Line], board: Board) -> list[Line]:
    """Every line for the board's category with a numeric value, best first."""
    out = []
    for (_, category), line in lines.items():
        if category != board.category:
            continue
        value = line.stats.get(board.stat)
        if not isinstance(value, float):
            continue
        if board.min_stat is not None:
            gate = line.stats.get(board.min_stat[0])
            if not isinstance(gate, float) or gate < board.min_stat[1]:
                continue
        out.append(line)
    out.sort(key=lambda line: (-float(line.stats[board.stat]), line.player or ""))
    return out


def rank_map(entries: list[Line], board: Board) -> dict[str, int]:
    """playerId -> rank, ties sharing a rank (the one tie rule, profiles.tie_ranks)."""
    ranks = tie_ranks([float(line.stats[board.stat]) for line in entries])
    return {line.player_id: rank for line, rank in zip(entries, ranks, strict=True)}


def fbs_lines(records: list[PlayerStat], fbs: set[str] | None) -> dict[tuple[str, str], Line]:
    """One national category pull as lines, FBS players only (every player when /teams/fbs failed)."""
    return lines_from([r for r in records if fbs is None or r.team in fbs])


def national_board(board: Board, national: dict[tuple[str, str], Line], conference: dict[tuple[str, str], Line]) -> tuple[list[Line], dict[str, int], list[Line], dict[str, int]]:
    """(national entries, national ranks, conference entries, conference ranks) for one board: the
    Leaders chips and the national list (Phase 16) read these same numbers."""
    nat_entries = board_entries(national, board)
    conf_entries = board_entries(conference, board)
    return nat_entries, rank_map(nat_entries, board), conf_entries, rank_map(conf_entries, board)


def ppa_national(records: list[PlayerSeasonPpa], teams: dict[str, dict[str, Any]], fbs: set[str] | None, conference: str) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]], dict[str, int]]:
    """The play value board's national list (50 plays or more by CFBD's threshold, checked at 45
    here) and the conference's, best first with ties by name, ranked with the one tie rule."""
    national = [r for r in ppa_season_rows(records, None, PPA_MIN_PLAYS_NATIONAL_CHECK) if r["all"] is not None and (fbs is None or r["team"] in fbs)]
    national.sort(key=lambda r: (-r["all"], r["name"] or ""))
    conf = [r for r in national if teams.get(r["team"] or "", {}).get("conference") == conference]
    return national, shared_ranks(national, "all"), conf, shared_ranks(conf, "all")


class PlayerService:
    def __init__(self, client: CfbdClient, settings: Settings) -> None:
        self.season_notes = SeasonNotes(settings.data_dir, settings.season)  # Phase 17 #38: ages
        self.client = client
        self.settings = settings
        self.fetcher = PartFetcher(client, 4)

    # --- fetch helpers ------------------------------------------------------------------------

    @property
    def year(self) -> int:
        return self.settings.season

    @property
    def team(self) -> str:
        return self.settings.team

    async def _teams(self) -> Part:
        return await self.fetcher.fetch("teams", "/teams/fbs", {"year": self.year}, Team, DataKind.TEAMS)

    async def _schedule(self) -> Part:
        return await self.fetcher.fetch("schedule", "/games", {"year": self.year, "team": self.team}, Game, DataKind.SCHEDULE)

    async def _league_games(self) -> Part:
        # The same endpoint and parameters as season.py and program.py, so one cache entry serves all three.
        return await self.fetcher.fetch("games", "/games", {"year": self.year}, Game, DataKind.SCHEDULE)

    async def _roster(self, team: str, year: int, name: str) -> Part:
        return await self.fetcher.fetch(name, "/roster", {"team": team, "year": year}, RosterPlayer, DataKind.ROSTER)

    async def _recruits(self, year: int) -> Part:
        return await self.fetcher.fetch(f"recruits_{year}", "/recruiting/players", {"year": year, "team": self.team}, Recruit, DataKind.RECRUITING)

    async def _player_stats(self, name: str, params: dict[str, Any]) -> Part:
        return await self.fetcher.fetch(name, "/stats/player/season", {"year": self.year, **params}, PlayerStat, DataKind.SEASON_STATS)

    async def _box(self, game: Game, team: str) -> Part:
        return await self.fetcher.fetch(f"box_{team}_{gamekeys.tag(game)}", "/games/players", gamekeys.box_params(game, self.year, team), GamePlayerStats, DataKind.FINISHED_GAME)

    def _team_lookup(self, teams: list[Team]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for t in teams:
            if not t.school:
                continue
            out[t.school] = {"school": t.school, "abbreviation": t.abbreviation, "conference": t.conference, **logo_fields(t.id, t.logos), "color": t.color}  # Phase 16: local logo URLs
        return out

    def _next_game(self, games: list[Game]) -> tuple[Game | None, str | None]:
        upcoming = sorted((g for g in games if not g.completed and g.week is not None), key=gamekeys.order)
        if not upcoming:
            return None, None
        game = upcoming[0]
        return game, (game.away_team if game.home_team == self.team else game.home_team)

    @staticmethod
    def _completed(games: list[Game], team: str) -> list[Game]:
        """One team's finished games, week order, each game once, from its own schedule or from the
        league-wide list."""
        seen: set[int] = set()
        out: list[Game] = []
        for g in games:
            if not g.completed or g.week is None or team not in (g.home_team, g.away_team) or g.id in seen:
                continue
            seen.add(g.id)
            out.append(g)
        return sorted(out, key=gamekeys.order)

    # --- leaders --------------------------------------------------------------------------------

    async def leaders(self) -> Assembled:
        import asyncio

        teams_part, schedule_part, team_part, conf_part = await asyncio.gather(
            self._teams(), self._schedule(), self._player_stats("team", {"team": self.team}), self._player_stats("conference", {"conference": self.settings.conference})
        )
        category_parts = await asyncio.gather(*(self._player_stats(f"national_{c}", {"category": c}) for c in CATEGORIES))
        parts: dict[str, Part] = {"teams": teams_part, "schedule": schedule_part, "team": team_part, "conference": conf_part}
        for part in category_parts:
            parts[part.name] = part

        teams = self._team_lookup(teams_part.records)
        _, opponent = self._next_game(schedule_part.records)
        opponent_conf = teams.get(opponent or "", {}).get("conference")
        in_conference = opponent is not None and opponent_conf == self.settings.conference
        opponent_lines: dict[tuple[str, str], Line] = {}
        if opponent and not in_conference:
            opp_part = await self._player_stats("opponent", {"team": opponent})
            parts["opponent"] = opp_part
            opponent_lines = lines_from(opp_part.records)

        fbs = set(teams) if teams else None
        team_lines = lines_from(team_part.records)
        conf_lines = lines_from(conf_part.records)
        if opponent and in_conference:
            opponent_lines = {k: v for k, v in conf_lines.items() if v.team == opponent}
        national_lines = {c: fbs_lines(parts[f"national_{c}"].records, fbs) for c in CATEGORIES}

        boards = []
        for board in BOARDS:
            nat_entries, nat_rank, conf_entries, conf_rank = national_board(board, national_lines.get(board.category, {}), conf_lines)
            team_entries = board_entries(team_lines, board)[:TEAM_TOP]
            opp_entries = board_entries(opponent_lines, board)[:TEAM_TOP]
            entry = lambda line, **extra: self._entry(line, board, teams, conf_rank, nat_rank, len(conf_entries), len(nat_entries), **extra)  # noqa: E731, B023 - used within this pass of the loop
            boards.append(
                {
                    "id": board.id,
                    "metric": f"board:{board.id}",  # Phase 16: the full national list behind the chips
                    "category": board.category,
                    "stat": board.stat,
                    "label": board.label,
                    "format": board.format,
                    "minimum": {"stat": board.min_stat[0], "value": board.min_stat[1]} if board.min_stat else None,
                    "team": [entry(line) for line in team_entries],
                    "opponent": [entry(line) for line in opp_entries],
                    "conference": [entry(line, rank=conf_rank.get(line.player_id)) for line in conf_entries[:SCOPE_TOP]],
                    "national": [entry(line, rank=nat_rank.get(line.player_id)) for line in nat_entries[:SCOPE_TOP]],
                    "conferenceOf": len(conf_entries) or None,
                    "nationalOf": len(nat_entries) or None,
                    "usBest": {
                        "conferenceRank": min((conf_rank[ln.player_id] for ln in team_entries if ln.player_id in conf_rank), default=None),
                        "nationalRank": min((nat_rank[ln.player_id] for ln in team_entries if ln.player_id in nat_rank), default=None),
                    },
                }
            )
        extra_boards = await self._extra_boards(parts, teams, opponent, fbs)
        data = {
            "season": self.year,
            "team": {**teams.get(self.team, {}), "school": self.team},
            "opponent": {**teams.get(opponent or "", {}), "school": opponent, "inConference": in_conference} if opponent else None,
            "boards": boards,
            "extraBoards": extra_boards,
            "parts": statuses(parts, self.client._clock()),
        }
        return assemble(data, parts)

    async def _extra_boards(self, parts: dict[str, Part], teams: dict[str, dict[str, Any]], opponent: str | None, fbs: set[str] | None) -> list[dict[str, Any]]:
        """Play value (PPA per play) with team, opponent, conference and national scopes, and usage share
        for the two teams. The national pull is one all-FBS call with a play threshold."""
        import asyncio

        fetches = [
            self.fetcher.fetch("ppaSeason", "/ppa/players/season", {"year": self.year, "team": self.team}, PlayerSeasonPpa, DataKind.SEASON_STATS),
            self.fetcher.fetch("ppaSeasonAll", "/ppa/players/season", {"year": self.year, "threshold": PPA_MIN_PLAYS}, PlayerSeasonPpa, DataKind.SEASON_STATS),
            self.fetcher.fetch("usage", "/player/usage", {"year": self.year, "team": self.team}, PlayerUsage, DataKind.SEASON_STATS),
        ]
        fetches += [  # Phase 13: opponent-adjusted passing and rushing EPA and kicker PAAR, one national call each
            self.fetcher.fetch("wepaPassing", "/wepa/players/passing", {"year": self.year}, PlayerWeightedEPA, DataKind.SEASON_STATS),
            self.fetcher.fetch("wepaRushing", "/wepa/players/rushing", {"year": self.year}, PlayerWeightedEPA, DataKind.SEASON_STATS),
            self.fetcher.fetch("paar", "/wepa/players/kicking", {"year": self.year}, KickerPAAR, DataKind.SEASON_STATS),
        ]
        if opponent:
            fetches += [
                self.fetcher.fetch("ppaSeasonOpponent", "/ppa/players/season", {"year": self.year, "team": opponent}, PlayerSeasonPpa, DataKind.SEASON_STATS),
                self.fetcher.fetch("usageOpponent", "/player/usage", {"year": self.year, "team": opponent}, PlayerUsage, DataKind.SEASON_STATS),
            ]
        for part in await asyncio.gather(*fetches):
            parts[part.name] = part

        def entry(row: dict[str, Any], value_key: str, rank: int | None = None, conf: int | None = None, nat: int | None = None, conf_of: int = 0, nat_of: int = 0) -> dict[str, Any]:
            meta = teams.get(row["team"] or "", {})
            detail = {k: row.get(k) for k in ("plays", "pass", "rush")} if value_key == "all" else {k: row.get(k) for k in ("pass", "rush", "thirdDown")}
            return {"playerId": row["playerId"], "player": row["name"], "position": row["position"], "team": row["team"], "teamAbbr": meta.get("abbreviation"), "logo": meta.get("logo"), "logoDark": meta.get("logoDark"), "metric": "board:ppa:all" if value_key == "all" else None, "isUs": row["team"] == self.team, "value": row.get(value_key), "detail": detail, "rank": rank, "conferenceRank": conf, "conferenceOf": conf_of or None, "nationalRank": nat, "nationalOf": nat_of or None, "headshotUrl": f"/media/headshot/{row['playerId']}"}

        # Phase 16: ties share a rank here too (they used to count 1, 2, 3), like every other chip
        national, nat_rank, conference, conf_rank = ppa_national(parts["ppaSeasonAll"].records, teams, fbs, self.settings.conference)
        team_rows = [r for r in ppa_season_rows(parts["ppaSeason"].records, self.team, PPA_MIN_PLAYS_TEAM) if r["all"] is not None][:TEAM_TOP]
        opp_rows = [r for r in ppa_season_rows(parts["ppaSeasonOpponent"].records, opponent, PPA_MIN_PLAYS_TEAM) if r["all"] is not None][:TEAM_TOP] if opponent and "ppaSeasonOpponent" in parts else []
        ppa_board = {
            "id": "ppa:all",
            "metric": "board:ppa:all",
            "category": "ppa",
            "stat": "PPA/play",
            "label": "Play value, PPA per play",
            "format": "+2f",
            "minimum": {"stat": "plays", "value": PPA_MIN_PLAYS_TEAM},
            "detailColumns": [{"key": "plays", "label": "Plays", "format": "0f"}, {"key": "pass", "label": "Pass", "format": "+2f"}, {"key": "rush", "label": "Rush", "format": "+2f"}],
            "team": [entry(r, "all", conf=conf_rank.get(r["playerId"]), nat=nat_rank.get(r["playerId"]), conf_of=len(conference), nat_of=len(national)) for r in team_rows],
            "opponent": [entry(r, "all", conf=conf_rank.get(r["playerId"]), nat=nat_rank.get(r["playerId"]), conf_of=len(conference), nat_of=len(national)) for r in opp_rows],
            "conference": [entry(r, "all", rank=conf_rank[r["playerId"]], conf_of=len(conference), nat_of=len(national)) for r in conference[:SCOPE_TOP]],
            "national": [entry(r, "all", rank=nat_rank[r["playerId"]], conf_of=len(conference), nat_of=len(national)) for r in national[:SCOPE_TOP]],
            "conferenceOf": len(conference) or None,
            "nationalOf": len(national) or None,
            "usBest": {"conferenceRank": min((conf_rank[r["playerId"]] for r in team_rows if r["playerId"] in conf_rank), default=None), "nationalRank": min((nat_rank[r["playerId"]] for r in team_rows if r["playerId"] in nat_rank), default=None)},
            "note": f"Season average of predicted points added per play, at least {PPA_MIN_PLAYS} plays for the conference and national lists.",
        }
        usage_team = [r for r in usage_rows(parts["usage"].records, self.team) if r["overall"] is not None][:TEAM_TOP]
        usage_opp = [r for r in usage_rows(parts["usageOpponent"].records, opponent) if r["overall"] is not None][:TEAM_TOP] if opponent and "usageOpponent" in parts else []
        usage_board = {
            "id": "usage:overall",
            "metric": None,  # team and opponent only: no national list, so its chips stay plain
            "category": "usage",
            "stat": "Usage",
            "label": "Usage, share of the team's plays",
            "format": "pct",
            "minimum": None,
            "detailColumns": [{"key": "pass", "label": "Pass", "format": "pct"}, {"key": "rush", "label": "Rush", "format": "pct"}, {"key": "thirdDown", "label": "3rd down", "format": "pct"}],
            "team": [entry(r, "overall") for r in usage_team],
            "opponent": [entry(r, "overall") for r in usage_opp],
            "conference": [],
            "national": [],
            "conferenceOf": None,
            "nationalOf": None,
            "usBest": {"conferenceRank": None, "nationalRank": None},
            "note": "Share of the team's offensive plays a player was involved in. Team and opponent only.",
        }
        adjusted = player_boards(parts["wepaPassing"].records, parts["wepaRushing"].records, parts["paar"].records, team=self.team, opponent=opponent, conference=self.settings.conference, fbs=fbs, top=SCOPE_TOP, team_top=TEAM_TOP)
        for board in adjusted:
            for scope in ("team", "opponent", "conference", "national"):
                for entry_row in board[scope]:
                    meta = teams.get(entry_row.get("team") or "", {})
                    entry_row["teamAbbr"] = meta.get("abbreviation")
                    entry_row["logo"] = meta.get("logo")
                    entry_row["logoDark"] = meta.get("logoDark")
        return [ppa_board, usage_board, *adjusted]

    def _entry(self, line: Line, board: Board, teams: dict[str, dict[str, Any]], conf_rank: dict[str, int], nat_rank: dict[str, int], conf_of: int, nat_of: int, rank: int | None = None) -> dict[str, Any]:
        meta = teams.get(line.team or "", {})
        return {
            "playerId": line.player_id,
            "player": line.player,
            "position": line.position,
            "team": line.team,
            "teamAbbr": meta.get("abbreviation"),
            "logo": meta.get("logo"),
            "logoDark": meta.get("logoDark"),
            "metric": f"board:{board.id}",
            "isUs": line.team == self.team,
            "value": line.stats.get(board.stat),
            "detail": {k: v for k, v in line.stats.items() if k != board.stat},
            "rank": rank,
            "conferenceRank": conf_rank.get(line.player_id),
            "conferenceOf": conf_of or None,
            "nationalRank": nat_rank.get(line.player_id),
            "nationalOf": nat_of or None,
            "headshotUrl": f"/media/headshot/{line.player_id}",
        }

    # --- roster ----------------------------------------------------------------------------------

    def _recruit_lookup(self, parts: dict[str, Part]) -> dict[str, Recruit]:
        out: dict[str, Recruit] = {}
        for name, part in parts.items():
            if name.startswith("recruits_"):
                for recruit in part.records:
                    out[recruit.id] = recruit
        return out

    def _player_row(self, player: RosterPlayer, recruits: dict[str, Recruit]) -> dict[str, Any]:
        recruit = next((recruits[r] for r in (player.recruit_ids or []) if r in recruits), None)
        return {
            "playerId": player.id,
            "number": player.jersey,
            "name": " ".join(part for part in (player.first_name, player.last_name) if part) or None,
            "firstName": player.first_name,
            "lastName": player.last_name,
            "team": player.team,
            "position": player.position,
            **class_fields(player.year, recruit.year if recruit else None, self.year),
            "height": player.height,
            "heightText": _height_text(player.height),
            "weight": player.weight,
            "hometown": ", ".join(part for part in (player.home_city, player.home_state) if part) or None,
            "highSchool": recruit.school if recruit else None,
            "stars": recruit.stars if recruit else None,
            "rating": recruit.rating if recruit else None,
            "recruitRank": recruit.ranking if recruit else None,
            "recruitClass": recruit.year if recruit else None,
            "recruitMetric": recruit_metric(recruit.year, self.year) if recruit and isinstance(recruit.ranking, int) else None,  # Phase 16 NV: the class's recruit list
            "headshotUrl": f"/media/headshot/{player.id}",
            **self._age(player.team, player.first_name, player.last_name),
        }

    def _age(self, team: str | None, first: str | None, last: str | None) -> dict[str, Any]:
        """Phase 17 #38: the age from the preseason load's birthdates (CFBD has none); nothing when unknown."""
        name = " ".join(part for part in (first, last) if part)
        age, born = self.season_notes.age(team, name, self.client._clock().astimezone(self.settings.tzinfo).date())
        return {"age": age, "born": born} if age is not None else {"age": None}

    async def roster(self) -> Assembled:
        import asyncio

        roster_part, teams_part, team_part, ppa_part, usage_part, *recruit_parts = await asyncio.gather(
            self._roster(self.team, self.year, "roster"),
            self._teams(),
            self._player_stats("team", {"team": self.team}),
            self.fetcher.fetch("ppaSeason", "/ppa/players/season", {"year": self.year, "team": self.team}, PlayerSeasonPpa, DataKind.SEASON_STATS),
            self.fetcher.fetch("usage", "/player/usage", {"year": self.year, "team": self.team}, PlayerUsage, DataKind.SEASON_STATS),
            *(self._recruits(y) for y in range(self.year - 4, self.year + 1)),
            *page_fetches(self.fetcher, self.year, returning=False),  # Phase 16 NV: the blue-chip rank, the list's own keys
        )
        portal_part = await self.fetcher.fetch("portal", "/player/portal", {"year": self.year}, PlayerTransfer, DataKind.SEASON_STATS)
        parts: dict[str, Part] = {"roster": roster_part, "teams": teams_part, "team": team_part, "ppaSeason": ppa_part, "usage": usage_part, "portal": portal_part}
        for part in recruit_parts:  # the team's classes, then the nationwide classes behind the blue-chip rank
            parts[part.name] = part
        recruits = self._recruit_lookup(parts)
        players = [self._player_row(p, recruits) for p in roster_part.records]
        ppa_by_id = {r["playerId"]: r for r in ppa_season_rows(ppa_part.records, self.team)}
        usage_by_id = {r["playerId"]: r for r in usage_rows(usage_part.records, self.team)}
        transfers = portal_index(portal_part.records, self.team)
        for p in players:
            p["isUs"] = True  # Phase 16 (LRP-07): the roster is ours, so a card opened from it is never "them"
            p["transfer"] = transfer_for(transfers, p["firstName"], p["lastName"])  # Phase 13: where a transfer came from
            p["ppaPerPlay"] = (ppa_by_id.get(p["playerId"]) or {}).get("all")
            p["ppaPlays"] = (ppa_by_id.get(p["playerId"]) or {}).get("plays")
            p["usageShare"] = (usage_by_id.get(p["playerId"]) or {}).get("overall")
        classes = {y: parts[f"recruits_{y}"].records for y in range(self.year - 3, self.year + 1) if f"recruits_{y}" in parts}
        players.sort(key=lambda p: (p["number"] is None, p["number"] or 0, p["name"] or ""))

        counts = {str(n): 0 for n in (5, 4, 3, 2, 1)}
        rated = [p["stars"] for p in players if isinstance(p["stars"], int) and 1 <= p["stars"] <= 5]
        for stars in rated:
            counts[str(stars)] += 1
        teams = self._team_lookup(teams_part.records)
        by_id = {p["playerId"]: p for p in players}
        data = {
            "season": self.year,
            "team": {**teams.get(self.team, {}), "school": self.team},
            "players": players,
            "costs": self.season_notes.costs_for(self.team),  # Phase 17 Part 3b: rumored roster costs
            "starCounts": counts,
            "average": round(sum(rated) / len(rated), 2) if rated else None,
            "rated": len(rated),
            "blueChip": PageRanks(parts, self.year, {t.school for t in teams_part.records if t.school} or None).bluechip_block(blue_chip(classes), self.team),  # Phase 16 NV
            "impact": self._impact(lines_from(team_part.records), by_id),
            "parts": statuses(parts, self.client._clock()),
        }
        return assemble(data, parts)

    def _impact(self, lines: dict[tuple[str, str], Line], roster: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Top three on each side of the ball: the leader of each board in order, no player twice."""
        boards = {b.id: b for b in BOARDS}
        out: dict[str, list[dict[str, Any]]] = {"offense": [], "defense": []}
        for side, ids in (("offense", IMPACT_OFFENSE), ("defense", IMPACT_DEFENSE)):
            taken: set[str] = set()
            for board_id in ids:
                board = boards[board_id]
                for line in board_entries(lines, board):
                    if line.player_id in taken:
                        continue
                    taken.add(line.player_id)
                    entry = roster.get(line.player_id, {})
                    chips = [f"{self._fmt(line.stats.get(board.stat), board.format)} {board.label.lower()}"]
                    for k, v in line.stats.items():
                        if k == board.stat or len(chips) >= 4 or (isinstance(v, float) and v == 0):
                            continue  # zeros say nothing on a card; the board stat leads
                        if k.upper() == "PCT" and isinstance(v, float):
                            chips.append(f"{v * 100:.0f}% completions" if v <= 1 else f"{v:.0f}% completions")
                        else:
                            chips.append(f"{self._fmt(v, '1f' if isinstance(v, float) and not v.is_integer() else '0f')} {k}")
                    out[side].append({"playerId": line.player_id, "name": line.player or entry.get("name"), "position": line.position or entry.get("position"), "number": entry.get("number"), "classYear": entry.get("classYear"), "headshotUrl": f"/media/headshot/{line.player_id}", "board": board.id, "chips": chips, "isUs": True})
                    break
                if len(out[side]) >= 3:
                    break
        return out

    @staticmethod
    def _fmt(value: Any, fmt: str) -> str:
        if isinstance(value, float):
            return f"{value:.1f}" if fmt == "1f" else f"{value:.0f}"
        return str(value) if value is not None else "–"

    # --- recruiting -------------------------------------------------------------------------------

    async def recruiting(self) -> Assembled:
        import asyncio

        current, following, schedule_part, rank_now, rank_next = await asyncio.gather(
            self._recruits(self.year),
            self._recruits(self.year + 1),
            self._schedule(),
            self.fetcher.fetch("classRank", "/recruiting/teams", {"year": self.year}, TeamRecruitingRanking, DataKind.RECRUITING),
            self.fetcher.fetch("classRankNext", "/recruiting/teams", {"year": self.year + 1}, TeamRecruitingRanking, DataKind.RECRUITING),
        )
        parts = {current.name: current, following.name: following, "schedule": schedule_part, "classRank": rank_now, "classRankNext": rank_next}
        classes = [self._class_block(self.year, current), self._class_block(self.year + 1, following)]
        classes[0]["classRank"] = class_rank(rank_now.records, self.team, self.year)  # Phase 13: the 247 team ranking
        classes[1]["classRank"] = class_rank(rank_next.records, self.team, self.year + 1)
        next_game, opponent = self._next_game(schedule_part.records)
        notes, error = load_notes(self.settings.data_dir, next_game.id if next_game else None)
        visitors = notes.visitors if notes else None
        data = {
            "season": self.year,
            "classes": classes,
            "visitors": {
                "gameId": next_game.id if next_game else None,
                "opponent": opponent,
                "date": next_game.start_date if next_game else None,  # Phase 16 (LRP-05): the summary shows the kickoff date, never the id
                "startTimeTbd": bool(next_game.start_time_tbd) if next_game else None,
                "home": [v.model_dump() for v in visitors.home] if visitors else [],
                "away": [v.model_dump() for v in visitors.away] if visitors else [],
                "source": visitors.source if visitors else None,
                "sourceUrl": visitors.sourceUrl if visitors else None,
                "updatedAt": visitors.updatedAt if visitors else None,
                "error": error,
                "note": None if visitors else (error or "No visitors list for this game yet. The pre-game task writes one on Friday, or add it to the notes file by hand."),
            },
            "parts": statuses(parts, self.client._clock()),
        }
        await context16.recruiting_extras(self.client, data, parts, team=self.team, year=self.year)  # Phase 16 BX: where they're from
        return assemble(data, parts)

    def _class_block(self, year: int, part: Part) -> dict[str, Any]:
        commits = []
        counts = {str(n): 0 for n in (5, 4, 3, 2, 1)}
        for r in part.records:
            if r.committed_to and r.committed_to != self.team:
                continue
            if isinstance(r.stars, int) and 1 <= r.stars <= 5:
                counts[str(r.stars)] += 1
            commits.append(
                {
                    "recruitId": r.id,
                    "athleteId": r.athlete_id,
                    "name": r.name,
                    "position": r.position,
                    "stars": r.stars,
                    "rating": r.rating,
                    "nationalRank": r.ranking,
                    "metric": recruit_metric(year, self.year) if isinstance(r.ranking, int) else None,  # Phase 16 NV: the class's recruit list
                    "highSchool": r.school,
                    "hometown": ", ".join(part for part in (r.city, r.state_province) if part) or None,
                    "heightText": _height_text(r.height),
                    "weight": r.weight,
                    "recruitType": r.recruit_type,
                }
            )
        commits.sort(key=lambda c: (c["nationalRank"] is None, c["nationalRank"] or 0, c["name"] or ""))
        rated = [c["stars"] for c in commits if isinstance(c["stars"], int)]
        return {"year": year, "count": len(commits), "commits": commits, "starCounts": counts, "average": round(sum(rated) / len(rated), 2) if rated else None, "partName": part.name}

    # --- player card ---------------------------------------------------------------------------------

    async def player(self, player_id: str, team_hint: str | None = None) -> Assembled | None:
        """Our players, the next opponent's, or (Phase 15, from search) a player of any FBS team
        named by `team_hint`, which costs that team's roster, stats and box scores the first time."""
        import asyncio

        roster_part, schedule_part, teams_part = await asyncio.gather(self._roster(self.team, self.year, "roster"), self._schedule(), self._teams())
        parts: dict[str, Part] = {"roster": roster_part, "schedule": schedule_part, "teams": teams_part}
        found = next((p for p in roster_part.records if p.id == player_id), None)
        team = self.team
        if found is None:
            _, opponent = self._next_game(schedule_part.records)
            fbs = {t.school for t in teams_part.records if t.school}
            if team_hint and team_hint != self.team and team_hint in fbs:
                opponent = team_hint
            if not opponent:
                if schedule_part.ok:
                    return None
                return assemble({"playerId": player_id, "parts": statuses(parts, self.client._clock())}, parts)  # the schedule failed: say so, not 404
            opp_roster = await self._roster(opponent, self.year, "opponentRoster")
            parts["opponentRoster"] = opp_roster
            found = next((p for p in opp_roster.records if p.id == player_id), None)
            if found is None:
                if opp_roster.ok:
                    return None
                return assemble({"playerId": player_id, "parts": statuses(parts, self.client._clock())}, parts)
            team = opponent
        is_us = team == self.team

        if is_us:
            completed = self._completed(schedule_part.records, team)
        else:
            # The opponent's own games, never ours: the league-wide answer holds every team's schedule.
            games_part = await self._league_games()
            parts["games"] = games_part
            completed = self._completed(games_part.records, team)
        stats_params = {"team": team}
        gather = [self._player_stats("stats", stats_params), *(self._box(g, team) for g in completed)]
        gather += [
            self.fetcher.fetch("ppaSeason", "/ppa/players/season", {"year": self.year, "team": team}, PlayerSeasonPpa, DataKind.SEASON_STATS),
            self.fetcher.fetch("usage", "/player/usage", {"year": self.year, "team": team}, PlayerUsage, DataKind.SEASON_STATS),
            *(self.fetcher.fetch(f"ppaGames_{gamekeys.tag(g)}", "/ppa/players/games", gamekeys.week_params(g, self.year, team), PlayerGamePpa, DataKind.SEASON_STATS) for g in completed if g.week is not None),
        ]
        if is_us:
            gather += [self._recruits(y) for y in range(self.year - 4, self.year + 1)]
            gather += [self._roster(self.team, y, f"roster_{y}") for y in range(self.year - 4, self.year)]
        else:
            gather += [self.fetcher.fetch(f"recruits_{y}", "/recruiting/players", {"year": y, "team": team}, Recruit, DataKind.RECRUITING) for y in range(self.year - 3, self.year + 1)]
        results = await asyncio.gather(*gather)
        for part in results:
            parts[part.name] = part

        recruits = self._recruit_lookup(parts)
        row = self._player_row(found, recruits)
        row["recruit"] = recruit_block(next((recruits[r] for r in (found.recruit_ids or []) if r in recruits), None))
        if row["recruit"] is not None:  # Phase 16 NV: the class's recruit list behind the rank
            row["recruit"]["metric"] = recruit_metric(row["recruit"]["year"], self.year) if row["recruit"]["nationalRank"] is not None else None
        portal_part = await self.fetcher.fetch("portal", "/player/portal", {"year": self.year}, PlayerTransfer, DataKind.SEASON_STATS)
        parts["portal"] = portal_part
        row["transfer"] = transfer_for(portal_index(portal_part.records, team), found.first_name, found.last_name)
        teams = self._team_lookup(teams_part.records)
        row["team"] = team
        row["teamAbbr"] = teams.get(team, {}).get("abbreviation")
        row["logo"] = teams.get(team, {}).get("logo")
        row["logoDark"] = teams.get(team, {}).get("logoDark")
        row["isUs"] = is_us

        lines = lines_from(parts["stats"].records)
        seasons = [
            {"year": self.year, "category": category, "stats": line.stats}
            for (pid, category), line in lines.items()
            if pid == player_id
        ]
        seasons.sort(key=lambda s: CATEGORIES.index(s["category"]) if s["category"] in CATEGORIES else 99)

        game_log = []
        missing_weeks = []
        for game in completed:
            part = parts.get(f"box_{team}_{gamekeys.tag(game)}")
            if part is None or not part.ok:
                missing_weeks.append(game.week)
                continue
            box = next((b for b in part.records if b.id == game.id), None)
            side = next((s for s in (box.teams if box else []) if s.team == team), None)
            entries = []
            for category in (side.categories if side else []):
                stats: dict[str, Any] = {}
                for stat_type in category.types:
                    for athlete in stat_type.athletes:
                        if athlete.id == player_id:
                            stats[stat_type.name] = _scalar(athlete.stat)
                if stats:
                    entries.append({"category": category.name, "stats": stats})
            opponent_name, result = _record_text(game, team)
            game_log.append({"gameId": game.id, "week": game.week, "postseason": gamekeys.label(game), "date": game.start_date, "opponent": opponent_name, "homeAway": "home" if game.home_team == team else "away", "result": result, "lines": entries})

        history = []
        for year in range(self.year - 4, self.year + 1):
            part = parts.get("roster" if year == self.year else f"roster_{year}")
            if part is None:
                continue
            hit = next((p for p in part.records if p.id == player_id), None)
            if hit is not None:
                history.append({"year": year, "team": hit.team or team, "classYear": hit.year, "position": hit.position, "number": hit.jersey})
        history = history_classes(history)

        ppa_rows = ppa_season_rows(parts["ppaSeason"].records, team) if "ppaSeason" in parts else []
        mine = next((r for r in ppa_rows if r["playerId"] == player_id), None)
        by_week = [
            (g.week, gamekeys.only_opponent(parts[f"ppaGames_{gamekeys.tag(g)}"].records, g, gamekeys.opponent_of(g, team)))
            for g in completed
            if g.week is not None and f"ppaGames_{gamekeys.tag(g)}" in parts
        ]
        ppa = {"season": mine, "teamRank": next((i + 1 for i, r in enumerate(ppa_rows) if r["playerId"] == player_id), None), "teamOf": len(ppa_rows) or None, "games": ppa_game_rows(by_week, player_id)}
        usage_all = usage_rows(parts["usage"].records, team) if "usage" in parts else []
        usage = next((r for r in usage_all if r["playerId"] == player_id), None)
        data = {"player": row, "seasons": seasons, "gameLog": game_log, "missingWeeks": missing_weeks, "history": history, "ppa": ppa, "usage": usage, "parts": statuses(parts, self.client._clock())}
        return assemble(data, parts)
