"""The full national lists (ENH-10). The owner, 2026-10-23: "menu - stats - passing should show the entire 136 passing list.
The leaders only shows the top 10"; asked whether he meant teams or players, "both, similar the the SP+"; "Passing is all
passers, but there should be a cutoff, we have minimum's for other parts"; and 2026-10-25, "When looking at a player
directly, by clicking on him, all his stats should be returned" (the player card, which reads every category).

GET /api/stats/{category}, category passing, rushing, receiving or defense, answers both views of one category:
    teams    every FBS team's season totals: its offense, and what its defense allowed, each value ranked nationally
    players  every FBS player at or over the stat grades' volume minimum per team game for his position group (a
             quarterback 14 passes a game, a running back 6 carries, a receiver 1.5 catches, a tight end 1, a defensive
             lineman 1.5 tackles, a linebacker 2.5, a defensive back 2; app/services/grades.py), each value ranked among them

Zero extra calls: the team totals are the stat profile's /stats/season answer (the Season page and the Pre-Game Program
ask for the same key), the player lines are the Leaders boards' and the grades' national pulls of /stats/player/season by
category, and the team list and the next opponent are the national lists' own keys. A team's games are its "games" total,
so a player's per-game volume uses his team's games, as the grades do (CFBD has no games played per player).

CFBD's names checked against the recorded 2026 answers (tests/fixtures/cfbd/stats_season_fbs.json and the player pulls):
a team's `interceptions` are the passes it threw that were picked off (they match its passers' INT), `passesIntercepted`
the passes its defense picked off (its defenders' INT); the Opponent forms are the same counts for its opponents.

    CATEGORIES                  the four lists: the team columns, the player columns, the minimum and the lead stat
    team_rows(stats, meta, cat) -> (offense rows, allowed rows), every value with its national rank
    player_rows(records, games, meta, cat) -> (rows, counts) the qualified players, ranked
    FullStatsService.listing(category) -> Assembled
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from app.cache import DataKind
from app.cfbd.models import PlayerStat, TeamStat
from app.services.grades import POSITION_GROUPS
from app.services.identity import conference_short
from app.services.parts import Assembled, Part, assemble, statuses
from app.services.players import lines_from
from app.services.profiles import tie_ranks

TeamTotals = dict[str, float]


@dataclass(frozen=True)
class Column:
    """One value of a list: its key in a row, its words, how to read it from the totals or a line, its format."""

    key: str
    label: str
    read: Callable[[dict[str, float], float | None], float | None]  # (totals or a player's stats, his team's games)
    format: str = "0f"
    higher: bool = True
    long: str | None = None
    size: str | None = None  # the smallest table size that shows it: None every size, "medium", "large" (the iPad shows medium)


def _get(name: str) -> Callable[[dict[str, float], float | None], float | None]:
    return lambda s, games: s.get(name)


def _ratio(top: str, bottom: str, scale: float = 1.0) -> Callable[[dict[str, float], float | None], float | None]:
    def read(s: dict[str, float], games: float | None) -> float | None:
        a, b = s.get(top), s.get(bottom)
        return a / b * scale if a is not None and b else None

    return read


def _per_game(name: str) -> Callable[[dict[str, float], float | None], float | None]:
    def read(s: dict[str, float], games: float | None) -> float | None:
        value = s.get(name)
        return value / games if value is not None and games else None

    return read


def _sum(*names: str) -> Callable[[dict[str, float], float | None], float | None]:
    def read(s: dict[str, float], games: float | None) -> float | None:
        values = [s.get(n) for n in names]
        return sum(v for v in values if v is not None) if any(v is not None for v in values) else None

    return read


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    player_categories: tuple[str, ...]  # the /stats/player/season pulls a player's line reads, the volume's first
    volume: tuple[str, str]  # (category, stat type) the minimum counts
    volume_words: str  # "passes a game"
    minimums: dict[str, float]  # position group -> the grades' minimum per team game; "*" for any other position
    player_columns: tuple[Column, ...]
    player_lead: str  # the column a player's Rk follows
    offense: tuple[Column, ...]  # the team's own totals
    allowed: tuple[Column, ...]  # what its defense allowed
    team_lead: str
    allowed_lead: str
    offense_title: str
    allowed_title: str
    joins: tuple[tuple[str, str], ...] = ()  # (category, stat type) taken from another pull into the line (defense: INT)


def _o(name: str) -> str:
    return f"{name}Opponent"


PASSING = Category(
    key="passing",
    label="Passing",
    player_categories=("passing",),
    volume=("passing", "ATT"),
    volume_words="passes a game",
    minimums={"*": 14.0},
    player_columns=(
        Column("cmp", "Cmp", _get("COMPLETIONS"), long="Completions", size="large"),
        Column("att", "Att", _get("ATT"), long="Attempts", size="large"),
        Column("pct", "Pct", _ratio("COMPLETIONS", "ATT"), "pct", long="Completion rate", size="medium"),
        Column("yds", "Yds", _get("YDS"), long="Passing yards"),
        Column("ypg", "Y/G", _per_game("YDS"), "1f", long="Passing yards a team game", size="medium"),  # owner 2026-11-15: a phone drops the per-game figure before a name is cut
        Column("ypa", "Y/A", _ratio("YDS", "ATT"), "1f", long="Yards an attempt", size="medium"),
        Column("td", "TD", _get("TD"), long="Touchdown passes"),
        Column("int", "INT", _get("INT"), higher=False, long="Interceptions thrown"),
    ),
    player_lead="yds",
    offense=(
        Column("cmp", "Cmp", _get("passCompletions"), long="Completions", size="large"),
        Column("att", "Att", _get("passAttempts"), long="Attempts", size="large"),
        Column("pct", "Pct", _ratio("passCompletions", "passAttempts"), "pct", long="Completion rate", size="medium"),
        Column("yds", "Yds", _get("netPassingYards"), long="Passing yards"),
        Column("ypg", "Y/G", _per_game("netPassingYards"), "1f", long="Passing yards a game"),
        Column("ypa", "Y/A", _ratio("netPassingYards", "passAttempts"), "1f", long="Yards an attempt", size="medium"),
        Column("td", "TD", _get("passingTDs"), long="Touchdown passes"),
        Column("int", "INT", _get("interceptions"), higher=False, long="Interceptions thrown"),
    ),
    allowed=(
        Column("cmp", "Cmp", _get(_o("passCompletions")), higher=False, long="Completions allowed", size="large"),
        Column("att", "Att", _get(_o("passAttempts")), higher=False, long="Attempts against", size="large"),
        Column("pct", "Pct", _ratio(_o("passCompletions"), _o("passAttempts")), "pct", higher=False, long="Completion rate allowed", size="medium"),
        Column("yds", "Yds", _get(_o("netPassingYards")), higher=False, long="Passing yards allowed"),
        Column("ypg", "Y/G", _per_game(_o("netPassingYards")), "1f", higher=False, long="Passing yards allowed a game"),
        Column("ypa", "Y/A", _ratio(_o("netPassingYards"), _o("passAttempts")), "1f", higher=False, long="Yards an attempt allowed", size="medium"),
        Column("td", "TD", _get(_o("passingTDs")), higher=False, long="Touchdown passes allowed"),
        Column("int", "INT", _get("passesIntercepted"), long="Interceptions made"),
    ),
    team_lead="ypg",
    allowed_lead="ypg",
    offense_title="Passing offense",
    allowed_title="Passing defense",
)

RUSHING = Category(
    key="rushing",
    label="Rushing",
    player_categories=("rushing",),
    volume=("rushing", "CAR"),
    volume_words="carries a game",
    minimums={"*": 6.0},
    player_columns=(
        Column("car", "Car", _get("CAR"), long="Carries"),
        Column("yds", "Yds", _get("YDS"), long="Rushing yards"),
        Column("ypg", "Y/G", _per_game("YDS"), "1f", long="Rushing yards a team game", size="medium"),
        Column("ypc", "Y/C", _ratio("YDS", "CAR"), "1f", long="Yards a carry", size="medium"),
        Column("td", "TD", _get("TD"), long="Rushing touchdowns"),
        Column("long", "Long", _get("LONG"), long="Longest run", size="large"),
    ),
    player_lead="yds",
    offense=(
        Column("att", "Att", _get("rushingAttempts"), long="Rushes", size="medium"),
        Column("yds", "Yds", _get("rushingYards"), long="Rushing yards"),
        Column("ypg", "Y/G", _per_game("rushingYards"), "1f", long="Rushing yards a game"),
        Column("ypc", "Y/C", _ratio("rushingYards", "rushingAttempts"), "1f", long="Yards a carry"),
        Column("td", "TD", _get("rushingTDs"), long="Rushing touchdowns"),
    ),
    allowed=(
        Column("att", "Att", _get(_o("rushingAttempts")), higher=False, long="Rushes against", size="medium"),
        Column("yds", "Yds", _get(_o("rushingYards")), higher=False, long="Rushing yards allowed"),
        Column("ypg", "Y/G", _per_game(_o("rushingYards")), "1f", higher=False, long="Rushing yards allowed a game"),
        Column("ypc", "Y/C", _ratio(_o("rushingYards"), _o("rushingAttempts")), "1f", higher=False, long="Yards a carry allowed"),
        Column("td", "TD", _get(_o("rushingTDs")), higher=False, long="Rushing touchdowns allowed"),
    ),
    team_lead="ypg",
    allowed_lead="ypg",
    offense_title="Rushing offense",
    allowed_title="Rushing defense",
)

RECEIVING = Category(
    key="receiving",
    label="Receiving",
    player_categories=("receiving",),
    volume=("receiving", "REC"),
    volume_words="catches a game",
    minimums={"TE": 1.0, "*": 1.5},
    player_columns=(
        Column("rec", "Rec", _get("REC"), long="Catches"),
        Column("yds", "Yds", _get("YDS"), long="Receiving yards"),
        Column("ypg", "Y/G", _per_game("YDS"), "1f", long="Receiving yards a team game", size="medium"),
        Column("ypr", "Y/R", _ratio("YDS", "REC"), "1f", long="Yards a catch", size="medium"),
        Column("td", "TD", _get("TD"), long="Receiving touchdowns"),
        Column("long", "Long", _get("LONG"), long="Longest catch", size="large"),
    ),
    player_lead="yds",
    offense=(
        Column("rec", "Rec", _get("passCompletions"), long="Catches", size="medium"),
        Column("yds", "Yds", _get("netPassingYards"), long="Receiving yards"),
        Column("ypg", "Y/G", _per_game("netPassingYards"), "1f", long="Receiving yards a game"),
        Column("ypr", "Y/R", _ratio("netPassingYards", "passCompletions"), "1f", long="Yards a catch"),
        Column("td", "TD", _get("passingTDs"), long="Receiving touchdowns"),
    ),
    allowed=(
        Column("rec", "Rec", _get(_o("passCompletions")), higher=False, long="Catches allowed", size="medium"),
        Column("yds", "Yds", _get(_o("netPassingYards")), higher=False, long="Receiving yards allowed"),
        Column("ypg", "Y/G", _per_game(_o("netPassingYards")), "1f", higher=False, long="Receiving yards allowed a game"),
        Column("ypr", "Y/R", _ratio(_o("netPassingYards"), _o("passCompletions")), "1f", higher=False, long="Yards a catch allowed"),
        Column("td", "TD", _get(_o("passingTDs")), higher=False, long="Receiving touchdowns allowed"),
    ),
    team_lead="ypg",
    allowed_lead="ypg",
    offense_title="Receiving offense",
    allowed_title="Receiving defense",
)

DEFENSE = Category(
    key="defense",
    label="Defense",
    player_categories=("defensive", "interceptions"),
    volume=("defensive", "TOT"),
    volume_words="tackles a game",
    minimums={"DL": 1.5, "LB": 2.5, "DB": 2.0, "*": 2.0},
    player_columns=(
        Column("tot", "Tkl", _get("TOT"), long="Tackles"),
        Column("tpg", "Tkl/G", _per_game("TOT"), "1f", long="Tackles a team game", size="medium"),
        Column("solo", "Solo", _get("SOLO"), long="Solo tackles", size="large"),
        Column("tfl", "TFL", _get("TFL"), "1f", long="Tackles for loss"),
        Column("sacks", "Sacks", _get("SACKS"), "1f", long="Sacks"),
        Column("hur", "Hur", _get("QB HUR"), long="Quarterback hurries", size="large"),
        Column("pd", "PD", _get("PD"), long="Passes defended", size="large"),
        Column("int", "INT", _get("INT"), long="Interceptions", size="medium"),
        Column("td", "TD", _get("TD"), long="Defensive touchdowns", size="large"),
    ),
    player_lead="tot",
    offense=(
        Column("sacks", "Sacks", _get("sacks"), long="Sacks", size="medium"),
        Column("spg", "Sacks/G", _per_game("sacks"), "1f", long="Sacks a game"),
        Column("tfl", "TFL", _get("tacklesForLoss"), long="Tackles for loss", size="medium"),
        Column("tflg", "TFL/G", _per_game("tacklesForLoss"), "1f", long="Tackles for loss a game"),
        Column("int", "INT", _get("passesIntercepted"), long="Interceptions", size="medium"),
        Column("fr", "FR", _get("fumblesRecovered"), long="Fumbles recovered", size="large"),
        Column("take", "Take", _sum("passesIntercepted", "fumblesRecovered"), long="Takeaways"),
        Column("ydsg", "Yds/G", _per_game(_o("totalYards")), "1f", higher=False, long="Yards allowed a game"),
    ),
    allowed=(
        Column("sacks", "Sacks", _get(_o("sacks")), higher=False, long="Sacks allowed", size="medium"),
        Column("spg", "Sacks/G", _per_game(_o("sacks")), "1f", higher=False, long="Sacks allowed a game"),
        Column("tfl", "TFL", _get(_o("tacklesForLoss")), higher=False, long="Tackles for loss allowed", size="medium"),
        Column("tflg", "TFL/G", _per_game(_o("tacklesForLoss")), "1f", higher=False, long="Tackles for loss allowed a game"),
        Column("int", "INT", _get("interceptions"), higher=False, long="Interceptions thrown", size="medium"),
        Column("fl", "FL", _get("fumblesLost"), higher=False, long="Fumbles lost", size="large"),
        Column("give", "Give", _sum("interceptions", "fumblesLost"), higher=False, long="Giveaways"),
        Column("ydsg", "Yds/G", _per_game("totalYards"), "1f", long="Yards a game"),
    ),
    team_lead="spg",
    allowed_lead="spg",
    offense_title="Defense: what it took",
    allowed_title="Offense: what it gave up",
    joins=(("interceptions", "INT"),),  # its TD and yards are the pick-sixes' own: the tackles' line keeps its TD
)

CATEGORIES: dict[str, Category] = {c.key: c for c in (PASSING, RUSHING, RECEIVING, DEFENSE)}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().rstrip("%"))
        except ValueError:
            return None
    else:
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def team_totals(records: Iterable[TeamStat], fbs: set[str] | None) -> dict[str, TeamTotals]:
    """team -> {stat name: value}, FBS teams only (every team when /teams/fbs failed); one bad record is skipped."""
    out: dict[str, TeamTotals] = {}
    for row in records:
        if not isinstance(row, TeamStat) or not row.team or not row.stat_name or (fbs is not None and row.team not in fbs):
            continue
        value = _number(row.stat_value)
        if value is not None:
            out.setdefault(row.team, {})[row.stat_name] = value
    return out


def _rounded(value: float | None, fmt: str) -> float | None:
    if value is None:
        return None
    if fmt == "pct":
        return round(value, 4)
    if fmt == "1f":
        return round(value, 1)
    return round(value, 2) if value != int(value) else float(int(value))


def _rank_rows(rows: list[dict[str, Any]], columns: tuple[Column, ...]) -> None:
    """Each value's national rank among the rows that have it (the one tie rule), in `<key>Rank`."""
    for col in columns:
        present = [r for r in rows if r.get(col.key) is not None]
        present.sort(key=lambda r: r[col.key], reverse=col.higher)
        for row, rank in zip(present, tie_ranks([r[col.key] for r in present]), strict=True):
            row[f"{col.key}Rank"] = rank


def _ordered(rows: list[dict[str, Any]], lead: str, name: str) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (r.get(f"{lead}Rank") is None, r.get(f"{lead}Rank") or 0, str(r.get(name) or "")))


def team_rows(totals: dict[str, TeamTotals], meta: dict[str, dict[str, Any]], cat: Category) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(offense rows, allowed rows): one row per FBS team with every column's value and national rank, by the lead stat."""

    def build(columns: tuple[Column, ...], lead: str) -> list[dict[str, Any]]:
        rows = []
        for team, stats in totals.items():
            games = stats.get("games")
            row: dict[str, Any] = {"team": team, "games": int(games) if games else None, **_team_fields(team, meta)}
            for col in columns:
                row[col.key] = _rounded(col.read(stats, games), col.format)
            rows.append(row)
        _rank_rows(rows, columns)
        return _ordered(rows, lead, "team")

    return build(cat.offense, cat.team_lead), build(cat.allowed, cat.allowed_lead)


def _team_fields(team: str | None, meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    info = meta.get(team or "", {})
    conference = info.get("conference")
    return {"abbreviation": info.get("abbreviation"), "conference": conference, "conferenceShort": conference_short(conference), "logo": info.get("logo"), "logoDark": info.get("logoDark")}


def minimum_for(cat: Category, position: str | None) -> float:
    group = POSITION_GROUPS.get((position or "").strip().upper())
    return cat.minimums.get(group or "", cat.minimums["*"])


def player_rows(pulls: dict[str, list[PlayerStat]], games: dict[str, float], meta: dict[str, dict[str, Any]], cat: Category) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The qualified FBS players of one category, every column valued and ranked among them, by the lead stat; counts of
    who had the category's stat at all and who met the minimum. A stat from another pull (defense's interceptions) joins
    his line by id; a player whose team has no games yet cannot qualify."""
    vol_category, vol_stat = cat.volume
    lines: dict[str, dict[str, Any]] = {}
    for (player_id, _), line in lines_from(pulls.get(vol_category, [])).items():
        if meta and line.team not in meta:
            continue  # FBS players only (every player when /teams/fbs failed)
        lines[player_id] = {"line": line, "stats": {k: v for k, v in line.stats.items() if isinstance(v, float)}}
    for category, stat in cat.joins:
        for (player_id, _), line in lines_from(pulls.get(category, [])).items():
            value = line.stats.get(stat)
            if player_id in lines and isinstance(value, float):
                lines[player_id]["stats"][stat] = value
    rows: list[dict[str, Any]] = []
    with_stat = 0
    for player_id, entry in lines.items():
        line, stats = entry["line"], entry["stats"]
        if vol_stat not in stats:
            continue
        with_stat += 1
        team_games = games.get(line.team or "")
        if not team_games or stats[vol_stat] / team_games < minimum_for(cat, line.position):
            continue
        row: dict[str, Any] = {"playerId": player_id, "player": line.player, "position": line.position, "team": line.team, "headshotUrl": f"/media/headshot/{player_id}", **_team_fields(line.team, meta)}
        if not row["conference"] and line.conference:
            row["conference"], row["conferenceShort"] = line.conference, conference_short(line.conference)
        for col in cat.player_columns:
            row[col.key] = _rounded(col.read(stats, team_games), col.format)
        rows.append(row)
    _rank_rows(rows, cat.player_columns)
    return _ordered(rows, cat.player_lead, "player"), {"withStat": with_stat, "qualified": len(rows)}


def columns_of(columns: tuple[Column, ...]) -> list[dict[str, Any]]:
    return [{"key": c.key, "label": c.label, "long": c.long or c.label, "format": c.format, "higherIsBetter": c.higher, "size": c.size} for c in columns]


def minimum_words(cat: Category) -> str:
    """"14 passes a game for every position" / "1.5 catches a game (a tight end 1)"."""
    default = cat.minimums["*"]
    others = [(group, value) for group, value in cat.minimums.items() if group != "*" and value != default]
    names = {"QB": "a quarterback", "RB": "a running back", "WR": "a receiver", "TE": "a tight end", "DL": "a defensive lineman", "LB": "a linebacker", "DB": "a defensive back"}
    head = f"{default:g} {cat.volume_words}"
    return f"{head} ({', '.join(f'{names.get(g, g)} {v:g}' for g, v in others)})" if others else head


class FullStatsService:
    """Serves the lists through the national lists' fetchers, so every answer is one the app already keeps."""

    def __init__(self, national: Any) -> None:
        self.national = national

    async def listing(self, key: str) -> Assembled | None:
        cat = CATEGORIES.get(key)
        if cat is None:
            return None
        n = self.national
        season = n.season
        fetches = [
            n._teams(),
            n._schedule(),
            n.season_fetcher.fetch("stats", "/stats/season", {"year": season, "classification": "fbs"}, TeamStat, DataKind.SEASON_STATS),
            *(n.players_fetcher.fetch(f"national_{c}", "/stats/player/season", {"year": season, "category": c}, PlayerStat, DataKind.SEASON_STATS) for c in cat.player_categories),
        ]
        parts: dict[str, Part] = {part.name: part for part in await asyncio.gather(*fetches)}
        meta = n._team_meta(parts["teams"])
        totals = team_totals(parts["stats"].records, set(meta) or None)
        games = {team: stats["games"] for team, stats in totals.items() if stats.get("games")}
        offense, allowed = team_rows(totals, meta, cat)
        pulls = {c: parts[f"national_{c}"].records for c in cat.player_categories}
        players, counts = player_rows(pulls, games, meta, cat)
        us, next_team = n.settings.team, n._next_opponent(parts["schedule"])
        for row in (*offense, *allowed, *players):
            row["isUs"] = row.get("team") == us
            row["isNext"] = bool(next_team) and row.get("team") == next_team
        data = {
            "category": cat.key,
            "label": cat.label,
            "season": season,
            "team": us,
            "next": next_team,
            "teams": {
                "offense": {"title": cat.offense_title, "lead": cat.team_lead, "columns": columns_of(cat.offense), "rows": offense},
                "allowed": {"title": cat.allowed_title, "lead": cat.allowed_lead, "columns": columns_of(cat.allowed), "rows": allowed},
                "count": len(offense),
            },
            "players": {
                "lead": cat.player_lead,
                "columns": columns_of(cat.player_columns),
                "rows": players,
                "minimum": {"words": minimum_words(cat), "stat": cat.volume[1], "byGroup": dict(cat.minimums)},
                **counts,
            },
            "categories": [{"key": c.key, "label": c.label} for c in CATEGORIES.values()],
            "parts": statuses(parts, n.client._clock()),
        }
        return assemble(data, parts)
