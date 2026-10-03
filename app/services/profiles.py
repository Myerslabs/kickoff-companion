"""Team stat profiles with ranks, shared by the season overview, the program, and the team
page: per-game and per-play figures derived from the all-FBS season stats plus points from the
finished games, ranked nationally and inside the conference with ties sharing a rank."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from app.cfbd.models import AdvancedSeasonStat, Game, TeamStat

# side, label, key, higher is better, display format
PROFILE_ROWS: list[tuple[str, str, str, bool, str]] = [
    ("offense", "Points per game", "ppg", True, "1f"),
    ("offense", "Yards per game", "ypg", True, "0f"),
    ("offense", "Yards per play", "ypp", True, "1f"),
    ("offense", "Pass yards per game", "pass_ypg", True, "0f"),
    ("offense", "Pass yards per attempt", "pass_ypa", True, "1f"),
    ("offense", "Completion rate", "comp_pct", True, "pct"),
    ("offense", "Rush yards per game", "rush_ypg", True, "0f"),
    ("offense", "Rush yards per carry", "rush_ypc", True, "1f"),
    ("offense", "Third down", "third", True, "pct"),
    ("offense", "Fourth down", "fourth", True, "pct"),
    ("offense", "First downs per game", "fd_pg", True, "1f"),
    ("offense", "Sacks allowed per game", "sacks_allowed_pg", False, "1f"),
    ("offense", "Turnovers lost per game", "to_lost_pg", False, "1f"),
    ("offense", "Penalty yards per game", "pen_ypg", False, "0f"),
    ("defense", "Opp points per game", "opp_ppg", False, "1f"),
    ("defense", "Opp yards per game", "ypg_d", False, "0f"),
    ("defense", "Opp yards per play", "ypp_d", False, "1f"),
    ("defense", "Opp pass yards per game", "pass_ypg_d", False, "0f"),
    ("defense", "Opp pass yards per attempt", "pass_ypa_d", False, "1f"),
    ("defense", "Opp rush yards per game", "rush_ypg_d", False, "0f"),
    ("defense", "Opp rush yards per carry", "rush_ypc_d", False, "1f"),
    ("defense", "Opp third down", "third_d", False, "pct"),
    ("defense", "Sacks per game", "sacks_pg", True, "1f"),
    ("defense", "Tackles for loss per game", "tfl_pg", True, "1f"),
    ("defense", "Takeaways per game", "takeaways_pg", True, "1f"),
    ("both", "Turnover margin", "to_margin", True, "+0f"),
]

# (side, label, attribute path, higher is better, format, group). Phase 13 shows everything CFBD
# sends in /stats/season/advanced, grouped; before it only the first six rows were shown.
ADVANCED_ROWS: list[tuple[str, str, str, bool, str, str]] = [
    ("offense", "Success rate", "success_rate", True, "pct", "Overall"),
    ("offense", "Explosiveness", "explosiveness", True, "2f", "Overall"),
    ("offense", "PPA per play", "ppa", True, "2f", "Overall"),
    ("defense", "Success rate allowed", "success_rate", False, "pct", "Overall"),
    ("defense", "Explosiveness allowed", "explosiveness", False, "2f", "Overall"),
    ("defense", "PPA allowed per play", "ppa", False, "2f", "Overall"),
    ("offense", "Success on standard downs", "standard_downs.success_rate", True, "pct", "Downs"),
    ("offense", "Success on passing downs", "passing_downs.success_rate", True, "pct", "Downs"),
    ("offense", "PPA on passing downs", "passing_downs.ppa", True, "2f", "Downs"),
    ("defense", "Success allowed, standard downs", "standard_downs.success_rate", False, "pct", "Downs"),
    ("defense", "Success allowed, passing downs", "passing_downs.success_rate", False, "pct", "Downs"),
    ("offense", "Run rate", "rushing_plays.rate", True, "pct", "Run and pass"),
    ("offense", "PPA per rush", "rushing_plays.ppa", True, "2f", "Run and pass"),
    ("offense", "PPA per pass", "passing_plays.ppa", True, "2f", "Run and pass"),
    ("defense", "PPA allowed per rush", "rushing_plays.ppa", False, "2f", "Run and pass"),
    ("defense", "PPA allowed per pass", "passing_plays.ppa", False, "2f", "Run and pass"),
    ("offense", "Line yards per rush", "line_yards", True, "2f", "Line play"),
    ("offense", "Stuff rate", "stuff_rate", False, "pct", "Line play"),
    ("offense", "Power success", "power_success", True, "pct", "Line play"),
    ("offense", "Second-level yards", "second_level_yards", True, "2f", "Line play"),
    ("offense", "Open-field yards", "open_field_yards", True, "2f", "Line play"),
    ("defense", "Line yards allowed", "line_yards", False, "2f", "Line play"),
    ("defense", "Stuff rate (defense)", "stuff_rate", True, "pct", "Line play"),
    ("defense", "Power success allowed", "power_success", False, "pct", "Line play"),
    ("defense", "Havoc rate", "havoc.total", True, "pct", "Havoc"),
    ("defense", "Havoc, front seven", "havoc.front_seven", True, "pct", "Havoc"),
    ("defense", "Havoc, secondary", "havoc.db", True, "pct", "Havoc"),
    ("offense", "Havoc allowed", "havoc.total", False, "pct", "Havoc"),
    ("offense", "Points per scoring chance", "points_per_opportunity", True, "2f", "Finishing drives"),
    ("defense", "Points per chance allowed", "points_per_opportunity", False, "2f", "Finishing drives"),
    ("offense", "Average start, yards to goal", "field_position.average_start", False, "1f", "Field position"),  # CFBD counts from the goal line: 68 is the own 32
    ("defense", "Opponents' average start, yards to goal", "field_position.average_start", True, "1f", "Field position"),
]


def _path(unit: Any, path: str) -> Any:
    for attr in path.split("."):
        unit = getattr(unit, attr, None) if unit is not None else None
    return unit


# Offense key vs the defensive key it meets, for the edges table (P3).
EDGE_PAIRS: list[tuple[str, str, str]] = [
    ("ypp", "ypp_d", "Yards per play"),
    ("ppg", "opp_ppg", "Scoring"),
    ("rush_ypg", "rush_ypg_d", "Rushing"),
    ("pass_ypg", "pass_ypg_d", "Passing"),
    ("third", "third_d", "Third down"),
    ("to_lost_pg", "takeaways_pg", "Ball security"),
]


def num(value: Any) -> float | None:
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


def div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def tie_ranks(ordered_values: list[float]) -> list[int]:
    """The one tie rule (Phase 16): values already best first; equal values share a rank and the
    next rank skips (1, 2, 2, 4). Every chip and every national list ranks with this."""
    ranks: list[int] = []
    last_value: float | None = None
    last_rank = 0
    for index, value in enumerate(ordered_values, start=1):
        if value != last_value:
            last_rank = index
            last_value = value
        ranks.append(last_rank)
    return ranks


def rank_teams(values: dict[str, float], higher_is_better: bool) -> tuple[dict[str, int], int]:
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=higher_is_better)
    ranks = tie_ranks([value for _, value in ordered])
    return {team: rank for (team, _), rank in zip(ordered, ranks, strict=True)}, len(ordered)


def ranked_list(values: dict[str, float], higher_is_better: bool, ranks: dict[str, int] | None = None) -> list[tuple[str, float, int, bool]]:
    """[(team, value, rank, tied)] in list order: rank, then name (Phase 16, the national lists).
    `ranks` passes a rank someone else set (CFBD's own); otherwise the tie rule ranks the values."""
    if ranks is None:
        ranks, _ = rank_teams(values, higher_is_better)
    rows = [(team, value, ranks[team]) for team, value in values.items() if ranks.get(team) is not None]
    counts: dict[int, int] = defaultdict(int)
    for _, _, rank in rows:
        counts[rank] += 1
    rows.sort(key=lambda r: (r[2], r[0]))
    return [(team, value, rank, counts[rank] > 1) for team, value, rank in rows]


def derive(stats: dict[str, float], points: dict[str, float] | None) -> dict[str, float | None]:
    g = stats.get("games") or (points or {}).get("games") or 0
    if not g:
        return {}

    def s(name: str) -> float | None:
        return stats.get(name)

    def per_game(name: str) -> float | None:
        value = s(name)
        return value / g if value is not None else None

    pass_att, rush_att = s("passAttempts"), s("rushingAttempts")
    pass_att_d, rush_att_d = s("passAttemptsOpponent"), s("rushingAttemptsOpponent")
    has_turnovers = any(s(name) is not None for name in ("passesIntercepted", "fumblesLost", "interceptions", "fumblesRecovered"))
    lost = ((s("passesIntercepted") or 0) + (s("fumblesLost") or 0)) if has_turnovers else None
    taken = ((s("interceptions") or 0) + (s("fumblesRecovered") or 0)) if has_turnovers else None
    plays = (pass_att or 0) + (rush_att or 0)
    plays_d = (pass_att_d or 0) + (rush_att_d or 0)
    return {
        "ppg": div((points or {}).get("for"), (points or {}).get("games")),
        "opp_ppg": div((points or {}).get("against"), (points or {}).get("games")),
        "ypg": per_game("totalYards"),
        "ypp": div(s("totalYards"), plays),
        "pass_ypg": per_game("netPassingYards"),
        "pass_ypa": div(s("netPassingYards"), pass_att),
        "comp_pct": div(s("passCompletions"), pass_att),
        "rush_ypg": per_game("rushingYards"),
        "rush_ypc": div(s("rushingYards"), rush_att),
        "third": div(s("thirdDownConversions"), s("thirdDowns")),
        "fourth": div(s("fourthDownConversions"), s("fourthDowns")),
        "fd_pg": per_game("firstDowns"),
        "sacks_allowed_pg": per_game("sacksOpponent"),
        "to_lost_pg": lost / g if lost is not None else None,
        "pen_ypg": per_game("penaltyYards"),
        "ypg_d": per_game("totalYardsOpponent"),
        "ypp_d": div(s("totalYardsOpponent"), plays_d),
        "pass_ypg_d": per_game("netPassingYardsOpponent"),
        "pass_ypa_d": div(s("netPassingYardsOpponent"), pass_att_d),
        "rush_ypg_d": per_game("rushingYardsOpponent"),
        "rush_ypc_d": div(s("rushingYardsOpponent"), rush_att_d),
        "third_d": div(s("thirdDownConversionsOpponent"), s("thirdDownsOpponent")),
        "sacks_pg": per_game("sacks"),
        "tfl_pg": per_game("tacklesForLoss"),
        "takeaways_pg": taken / g if taken is not None else None,
        "to_margin": taken - lost if taken is not None and lost is not None else None,
    }


def points_table(games: list[Game]) -> dict[str, dict[str, float]]:
    """Points for and against per team from every finished game in the list, by game id."""
    out: dict[str, dict[str, float]] = defaultdict(lambda: {"for": 0.0, "against": 0.0, "games": 0.0})
    seen: set[int] = set()
    for game in games:
        if not game.completed or game.id in seen or game.home_points is None or game.away_points is None:
            continue
        seen.add(game.id)
        for side, opp_points, own_points in ((game.home_team, game.away_points, game.home_points), (game.away_team, game.home_points, game.away_points)):
            if side:
                out[side]["for"] += own_points
                out[side]["against"] += opp_points
                out[side]["games"] += 1
    return out


class Profiles:
    """Derived figures for every team in the stats payload, with rank lookups on demand."""

    def __init__(self, stats: list[TeamStat], games: list[Game], conference: str, points_ranked: bool = True, team: str | None = None) -> None:
        by_team: dict[str, dict[str, float]] = defaultdict(dict)
        self.conference_of: dict[str, str] = {}
        for row in stats:
            value = num(row.stat_value)
            if value is None:
                continue
            by_team[row.team][row.stat_name] = value
            if row.conference:
                self.conference_of[row.team] = row.conference
        self.points = points_table(games)
        self.derived: dict[str, dict[str, float | None]] = {name: derive(values, self.points.get(name)) for name, values in by_team.items()}
        # Only the configured team gets a points-only profile when the stats payload lacks it:
        # anyone else (FCS opponents in the all-games list) would pollute every rank with blanks.
        if team and team not in self.derived and self.points.get(team, {}).get("games"):
            self.derived[team] = derive({"games": self.points[team]["games"]}, self.points[team])
        self.conference = conference
        self.rankable = len(by_team) > 1
        self.points_ranked = points_ranked and bool(self.points)
        self._cache: dict[tuple[str, bool, str | None], tuple[dict[str, float], dict[str, int], int, dict[str, int], int]] = {}

    def games_for(self, team: str) -> int:
        return int(self.points.get(team, {}).get("games") or 0)

    def value(self, team: str, key: str) -> float | None:
        return self.derived.get(team, {}).get(key)

    def teams(self) -> list[str]:
        """Every team with a profile (a national list counts those without a value as unranked)."""
        return list(self.derived)

    def _ranks(self, key: str, higher: bool, conference: str | None = None) -> tuple[dict[str, float], dict[str, int], int, dict[str, int], int]:
        """(national values, national ranks, of, conference ranks, of) for one key. The conference
        defaults to the one these profiles were built for (the team page passes the team's own)."""
        conference = conference or self.conference
        cached = self._cache.get((key, higher, conference))
        if cached:
            return cached
        national = {t: v[key] for t, v in self.derived.items() if v.get(key) is not None} if self.rankable else {}
        if key in ("ppg", "opp_ppg") and not self.points_ranked:
            national = {}
        nat_rank, nat_of = rank_teams(national, higher)
        conf = {t: v for t, v in national.items() if self.conference_of.get(t) == conference}
        conf_rank, conf_of = rank_teams(conf, higher)
        result = (national, nat_rank, nat_of, conf_rank, conf_of)
        self._cache[(key, higher, conference)] = result
        return result

    def ranked(self, key: str, higher: bool, scope: str = "national", conference: str | None = None) -> list[tuple[str, float, int, bool]]:
        """The national list behind the chips (Phase 16): [(team, value, rank, tied)], the same
        numbers row() reads from the same cache, in rank then name order."""
        national, nat_rank, _, conf_rank, _ = self._ranks(key, higher, conference)
        if scope == "conference":
            conference = conference or self.conference
            values = {t: v for t, v in national.items() if self.conference_of.get(t) == conference}
            return ranked_list(values, higher, conf_rank)
        return ranked_list(national, higher, nat_rank)

    def row(self, team: str, side: str, label: str, key: str, higher: bool, fmt: str) -> dict[str, Any]:
        _, nat_rank, nat_of, conf_rank, conf_of = self._ranks(key, higher)
        value = self.value(team, key)
        return {
            "side": side,
            "label": label,
            "key": key,
            "metric": f"profile:{key}",  # Phase 16: the national list this row's chips open
            "value": round(value, 3) if value is not None else None,
            "format": fmt,
            "higherIsBetter": higher,
            "nationalRank": nat_rank.get(team),
            "nationalOf": nat_of or None,
            "conferenceRank": conf_rank.get(team),
            "conferenceOf": conf_of or None,
        }

    def rows(self, team: str) -> list[dict[str, Any]]:
        return [self.row(team, *spec) for spec in PROFILE_ROWS]

    def edges(self, us: str, them: str) -> list[dict[str, Any]]:
        """Unit versus unit by national rank (P3): positive edge favours our unit. Phase 16
        (audit L-02, P-11): each row names the stat behind each side's rank. On an offense row
        Our rank is our offense stat and the opponent's its defense stat; on a defense row it
        is the other way round."""
        out: list[dict[str, Any]] = []
        for off_key, def_key, label in EDGE_PAIRS:
            off_spec = next(spec for spec in PROFILE_ROWS if spec[2] == off_key)
            def_spec = next(spec for spec in PROFILE_ROWS if spec[2] == def_key)
            us_off, them_def = self.row(us, *off_spec), self.row(them, *def_spec)
            them_off, us_def = self.row(them, *off_spec), self.row(us, *def_spec)
            if us_off["nationalRank"] and them_def["nationalRank"]:
                out.append({
                    "label": f"{label}: {us} offense vs {them} defense", "side": "offense",
                    "usRank": us_off["nationalRank"], "themRank": them_def["nationalRank"], "of": us_off["nationalOf"], "themOf": them_def["nationalOf"],
                    "edge": them_def["nationalRank"] - us_off["nationalRank"], "usValue": us_off["value"], "themValue": them_def["value"],
                    "format": off_spec[4], "usFormat": off_spec[4], "themFormat": def_spec[4],
                    "usKey": off_key, "themKey": def_key, "usMetric": f"profile:{off_key}", "themMetric": f"profile:{def_key}",
                })
            if them_off["nationalRank"] and us_def["nationalRank"]:
                out.append({
                    "label": f"{label}: {them} offense vs {us} defense", "side": "defense",
                    "usRank": us_def["nationalRank"], "themRank": them_off["nationalRank"], "of": us_def["nationalOf"], "themOf": them_off["nationalOf"],
                    "edge": them_off["nationalRank"] - us_def["nationalRank"], "usValue": us_def["value"], "themValue": them_off["value"],
                    "format": def_spec[4], "usFormat": def_spec[4], "themFormat": off_spec[4],
                    "usKey": def_key, "themKey": off_key, "usMetric": f"profile:{def_key}", "themMetric": f"profile:{off_key}",
                })
        out.sort(key=lambda e: -abs(e["edge"]))
        return out


def profiles_for(stats: list[TeamStat], league_games: list[Game], team_games: list[Game], conference: str, team: str | None) -> Profiles:
    """The one way to build profiles (Phase 16), so the Season page, the program, the team page and
    the national lists rank the same games: the league-wide finished games plus the team's own
    schedule (deduplicated by game id), points ranked only when the league-wide answer loaded."""
    return Profiles(stats, list(league_games) + list(team_games), conference, points_ranked=bool(league_games), team=team)


def advanced_values(records: list[AdvancedSeasonStat], side: str, attr: str) -> dict[str, float]:
    """{team: value} for one advanced measure: finite numbers only (no bool, NaN or Infinity)."""
    values: dict[str, float] = {}
    for r in records:
        value = _path(getattr(r, side, None), attr)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            values[r.team] = float(value)
    return values


def advanced_key(side: str, attr: str) -> str:
    return f"{side}_{attr.replace('.', '_')}"


def advanced_rows(records: list[AdvancedSeasonStat], team: str) -> list[dict[str, Any]]:
    rows = []
    mine = next((r for r in records if r.team == team), None)
    for side, label, attr, higher, fmt, group in ADVANCED_ROWS:
        values = advanced_values(records, side, attr)
        ranks, of = rank_teams(values, higher)
        value = _path(getattr(mine, side, None), attr) if mine is not None else None
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        key = advanced_key(side, attr)
        rows.append({"side": side, "label": label, "key": key, "metric": f"advanced:{key}", "group": group, "value": round(value, 3) if ok else None, "format": fmt, "higherIsBetter": higher, "nationalRank": ranks.get(team) if ok else None, "nationalOf": of or None})
    return rows
