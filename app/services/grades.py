"""Stat grades (public release Phase 7): our own 0 to 100 grade for every FBS player CFBD has season stats for,
in place of PFF's film grades (which may not be published in a public app).

How a grade is made, per position group:
1. Volume first. A player needs a group's minimum per team game (a quarterback 14 passes a game, a running
   back 6 carries, a receiver 1.5 catches, a tight end 1, a lineman or linebacker 1.5 to 2.5 tackles, a
   defensive back 2, a kicker one field goal try every two games, a punter 2 punts). Below it he shows "not
   enough plays" with what he has and what he needs. CFBD has no games played per player, so the team's
   games stand in, which reads low for a player who missed games.
2. Each component (yards per attempt, touchdown rate, play value from CFBD's PPA, and so on) becomes a
   percentile among the group's qualified FBS players: 100 is the best, 50 the middle.
3. The grade is the weighted average of the components the player has (at least half the weight must be
   there), rounded. Its label: 90 Elite, 75 Very good, 60 Good, 40 Average, 25 Below average, else Struggling.

Quarterbacks, running backs, kickers and punters are graded on efficiency and production. Receivers, tight
ends and defenders are graded on production only: CFBD has no targets or snaps for them. Offensive linemen
and long snappers have no individual stats and get no grade. Everything here is pure: no fetching, so the
service, the tests and the national lists read the same numbers."""

from __future__ import annotations

import bisect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.cfbd.models import Game, KickerPAAR, PlayerSeasonPpa, PlayerStat, PlayerWeightedEPA
from app.services.players import lines_from
from app.services.stats_extra import ppa_plays

POSITION_GROUPS = {
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
    "OL": "OL", "OT": "OL", "OG": "OL", "C": "OL", "IOL": "OL",
    "DL": "DL", "DE": "DL", "DT": "DL", "NT": "DL", "EDGE": "DL",
    "LB": "LB", "OLB": "LB", "ILB": "LB", "MLB": "LB",
    "DB": "DB", "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB",
    "PK": "PK", "K": "PK", "P": "P", "LS": "LS",
}
GROUP_NAMES = {
    "QB": "quarterbacks", "RB": "running backs", "WR": "wide receivers", "TE": "tight ends", "DL": "defensive linemen",
    "LB": "linebackers", "DB": "defensive backs", "PK": "kickers", "P": "punters", "OL": "offensive linemen", "LS": "long snappers",
}
GRADED = ("QB", "RB", "WR", "TE", "DL", "LB", "DB", "PK", "P")
UNGRADED = {
    "OL": "Offensive linemen have no individual stats in CFBD's data, so they get no stat grade.",
    "LS": "Long snappers have no individual stats in CFBD's data, so they get no stat grade.",
}
LABELS = ((90, "Elite"), (75, "Very good"), (60, "Good"), (40, "Average"), (25, "Below average"), (0, "Struggling"))
MIN_WEIGHT_SHARE = 0.5


def label_for(grade: int | None) -> str | None:
    if grade is None:
        return None
    return next(name for floor, name in LABELS if grade >= floor)


@dataclass
class Player:
    """Everything one player's grade reads."""

    player_id: str
    name: str | None
    team: str | None
    conference: str | None
    position: str | None
    games: int
    stats: dict[str, dict[str, float]] = field(default_factory=dict)  # category -> stat type -> value
    ppa: dict[str, float | None] | None = None  # average PPA: all, pass, rush
    ppa_plays: int | None = None
    wepa_pass: float | None = None
    wepa_rush: float | None = None
    paar: float | None = None

    def stat(self, category: str, key: str) -> float | None:
        value = self.stats.get(category, {}).get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def per_game(self, category: str, key: str) -> float | None:
        value = self.stat(category, key)
        return value / self.games if value is not None and self.games > 0 else None

    def rate(self, category: str, top: str, bottom: str) -> float | None:
        a, b = self.stat(category, top), self.stat(category, bottom)
        return a / b if a is not None and b else None


@dataclass(frozen=True)
class Component:
    key: str
    label: str
    weight: float
    read: Callable[[Player], float | None]
    format: str = "1f"
    higher: bool = True


@dataclass(frozen=True)
class Spec:
    group: str
    basis: str  # "efficiency" or "production"
    volume_label: str
    volume: Callable[[Player], float | None]  # per team game
    needed: float
    components: tuple[Component, ...]


def _ppa(key: str) -> Callable[[Player], float | None]:
    def read(p: Player) -> float | None:
        value = (p.ppa or {}).get(key)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return read


SPECS: dict[str, Spec] = {
    "QB": Spec("QB", "efficiency", "passes a game", lambda p: p.per_game("passing", "ATT"), 14.0, (
        Component("ypa", "Yards per attempt", 0.2, lambda p: p.rate("passing", "YDS", "ATT")),
        Component("pct", "Completion rate", 0.1, lambda p: p.rate("passing", "COMPLETIONS", "ATT"), "pct"),
        Component("tdRate", "Touchdown rate", 0.15, lambda p: p.rate("passing", "TD", "ATT"), "pct"),
        Component("intRate", "Interception rate", 0.15, lambda p: p.rate("passing", "INT", "ATT"), "pct", higher=False),
        Component("ppaPass", "Play value per pass (PPA)", 0.25, _ppa("pass"), "2f"),
        Component("wepaPass", "Opponent-adjusted passing value", 0.1, lambda p: p.wepa_pass, "2f"),
        Component("rushYdsG", "Rushing yards a game", 0.05, lambda p: p.per_game("rushing", "YDS")),
    )),
    "RB": Spec("RB", "efficiency", "carries a game", lambda p: p.per_game("rushing", "CAR"), 6.0, (
        Component("ypc", "Yards per carry", 0.25, lambda p: p.rate("rushing", "YDS", "CAR")),
        Component("rushYdsG", "Rushing yards a game", 0.25, lambda p: p.per_game("rushing", "YDS")),
        Component("rushTdG", "Rushing touchdowns a game", 0.1, lambda p: p.per_game("rushing", "TD"), "2f"),
        Component("ppaRush", "Play value per rush (PPA)", 0.2, _ppa("rush"), "2f"),
        Component("wepaRush", "Opponent-adjusted rushing value", 0.1, lambda p: p.wepa_rush, "2f"),
        Component("recYdsG", "Receiving yards a game", 0.1, lambda p: p.per_game("receiving", "YDS")),
    )),
    "WR": Spec("WR", "production", "catches a game", lambda p: p.per_game("receiving", "REC"), 1.5, (
        Component("recYdsG", "Receiving yards a game", 0.4, lambda p: p.per_game("receiving", "YDS")),
        Component("ypr", "Yards per catch", 0.2, lambda p: p.rate("receiving", "YDS", "REC")),
        Component("recG", "Catches a game", 0.2, lambda p: p.per_game("receiving", "REC")),
        Component("recTdG", "Receiving touchdowns a game", 0.2, lambda p: p.per_game("receiving", "TD"), "2f"),
    )),
    "TE": Spec("TE", "production", "catches a game", lambda p: p.per_game("receiving", "REC"), 1.0, (
        Component("recYdsG", "Receiving yards a game", 0.4, lambda p: p.per_game("receiving", "YDS")),
        Component("ypr", "Yards per catch", 0.2, lambda p: p.rate("receiving", "YDS", "REC")),
        Component("recG", "Catches a game", 0.2, lambda p: p.per_game("receiving", "REC")),
        Component("recTdG", "Receiving touchdowns a game", 0.2, lambda p: p.per_game("receiving", "TD"), "2f"),
    )),
    "DL": Spec("DL", "production", "tackles a game", lambda p: p.per_game("defensive", "TOT"), 1.5, (
        Component("tflG", "Tackles for loss a game", 0.3, lambda p: p.per_game("defensive", "TFL"), "2f"),
        Component("sacksG", "Sacks a game", 0.3, lambda p: p.per_game("defensive", "SACKS"), "2f"),
        Component("hurriesG", "Quarterback hurries a game", 0.2, lambda p: p.per_game("defensive", "QB HUR"), "2f"),
        Component("tacklesG", "Tackles a game", 0.2, lambda p: p.per_game("defensive", "TOT")),
    )),
    "LB": Spec("LB", "production", "tackles a game", lambda p: p.per_game("defensive", "TOT"), 2.5, (
        Component("tacklesG", "Tackles a game", 0.35, lambda p: p.per_game("defensive", "TOT")),
        Component("tflG", "Tackles for loss a game", 0.25, lambda p: p.per_game("defensive", "TFL"), "2f"),
        Component("sacksG", "Sacks a game", 0.15, lambda p: p.per_game("defensive", "SACKS"), "2f"),
        Component("pdG", "Passes defended a game", 0.1, lambda p: p.per_game("defensive", "PD"), "2f"),
        Component("intG", "Interceptions a game", 0.15, lambda p: p.per_game("interceptions", "INT") or 0.0, "2f"),
    )),
    "DB": Spec("DB", "production", "tackles a game", lambda p: p.per_game("defensive", "TOT"), 2.0, (
        Component("pdG", "Passes defended a game", 0.3, lambda p: p.per_game("defensive", "PD"), "2f"),
        Component("intG", "Interceptions a game", 0.3, lambda p: p.per_game("interceptions", "INT") or 0.0, "2f"),
        Component("tacklesG", "Tackles a game", 0.3, lambda p: p.per_game("defensive", "TOT")),
        Component("tflG", "Tackles for loss a game", 0.1, lambda p: p.per_game("defensive", "TFL"), "2f"),
    )),
    "PK": Spec("PK", "efficiency", "field goal tries a game", lambda p: p.per_game("kicking", "FGA"), 0.5, (
        Component("fgPct", "Field goal rate", 0.45, lambda p: p.rate("kicking", "FGM", "FGA"), "pct"),
        Component("fgmG", "Field goals a game", 0.15, lambda p: p.per_game("kicking", "FGM"), "2f"),
        Component("long", "Longest field goal", 0.1, lambda p: p.stat("kicking", "LONG"), "0f"),
        Component("xpPct", "Extra point rate", 0.1, lambda p: p.rate("kicking", "XPM", "XPA"), "pct"),
        Component("paar", "Points added above replacement", 0.2, lambda p: p.paar, "2f"),
    )),
    "P": Spec("P", "efficiency", "punts a game", lambda p: p.per_game("punting", "NO"), 2.0, (
        Component("ypp", "Yards per punt", 0.6, lambda p: p.rate("punting", "YDS", "NO")),
        Component("in20", "Punts inside the 20, per punt", 0.25, lambda p: p.rate("punting", "In 20", "NO"), "pct"),
        Component("tb", "Touchbacks per punt", 0.15, lambda p: p.rate("punting", "TB", "NO"), "pct", higher=False),
    )),
}


def group_of(position: str | None, stats: dict[str, dict[str, float]]) -> str | None:
    """The grading group: the listed position, else the category the player's volume is in."""
    if isinstance(position, str) and position.strip().upper() in POSITION_GROUPS:
        return POSITION_GROUPS[position.strip().upper()]
    for category, group in (("passing", "QB"), ("kicking", "PK"), ("punting", "P"), ("rushing", "RB"), ("receiving", "WR")):
        if stats.get(category):
            return group
    return None


def team_games(games: Iterable[Game]) -> dict[str, int]:
    """Completed games per team this season (regular season and postseason)."""
    out: dict[str, int] = {}
    for g in games:
        if not isinstance(g, Game) or not g.completed:
            continue
        for team in (g.home_team, g.away_team):
            if team:
                out[team] = out.get(team, 0) + 1
    return out


def _percentiles(values: dict[str, float], higher: bool) -> dict[str, float]:
    """Mid-rank percentile, 0 to 100, best = highest; one value alone is the middle."""
    ordered = sorted(values.values())
    n = len(ordered)
    out: dict[str, float] = {}
    if n == 0:
        return out


    for pid, value in values.items():
        below = bisect.bisect_left(ordered, value)
        equal = bisect.bisect_right(ordered, value) - below
        share = (below + 0.5 * equal) / n
        out[pid] = round(100 * (share if higher else 1 - share), 1)
    return out


def _tie_ranks(rows: list[dict[str, Any]]) -> None:
    previous, rank = None, 0
    for index, row in enumerate(rows, start=1):
        if row["grade"] != previous:
            rank, previous = index, row["grade"]
        row["rank"] = rank


@dataclass
class GradeTable:
    """Every graded or gradable FBS player by id, and each group's qualified players, best first."""

    by_id: dict[str, dict[str, Any]]
    groups: dict[str, list[dict[str, Any]]]

    def get(self, player_id: Any) -> dict[str, Any] | None:
        return self.by_id.get(str(player_id)) if player_id is not None else None

    def for_position(self, position: str | None) -> dict[str, Any]:
        """The answer for a player CFBD has no season stats for: an ungraded group's reason, or none yet."""
        group = POSITION_GROUPS.get((position or "").strip().upper())
        if group in UNGRADED:
            return {"grade": None, "group": group, "groupName": GROUP_NAMES[group], "reason": UNGRADED[group], "basis": None}
        return {"grade": None, "group": group, "groupName": GROUP_NAMES.get(group or ""), "reason": "No stats this season yet.", "basis": SPECS[group].basis if group in SPECS else None}

    def counts(self) -> dict[str, int]:
        return {g: len(rows) for g, rows in self.groups.items()}


def build(stats: dict[str, list[PlayerStat]], games: list[Game], fbs: set[str] | None, ppa: list[PlayerSeasonPpa] | None = None,
          wepa_pass: list[PlayerWeightedEPA] | None = None, wepa_rush: list[PlayerWeightedEPA] | None = None,
          paar: list[KickerPAAR] | None = None) -> GradeTable:
    """Grade every FBS player in the national category pulls. `stats` maps a category to its rows."""
    played = team_games(games)
    players: dict[str, Player] = {}
    for category, records in stats.items():
        for line in lines_from([r for r in records if fbs is None or r.team in fbs]).values():
            p = players.get(line.player_id)
            if p is None:
                p = players[line.player_id] = Player(line.player_id, line.player, line.team, line.conference, line.position, max(1, played.get(line.team or "", 0)))
            elif not p.position and line.position:
                p.position = line.position
            p.stats[category] = {k: float(v) for k, v in line.stats.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    for row in ppa or []:
        p = players.get(row.id)
        if p is not None and isinstance(row.average_ppa, dict):
            p.ppa = {k: row.average_ppa.get(k) for k in ("all", "pass", "rush")}
            p.ppa_plays = ppa_plays(row)
    for rows, attr in ((wepa_pass or [], "wepa_pass"), (wepa_rush or [], "wepa_rush")):
        for row in rows:
            p = players.get(row.athlete_id)
            if p is not None and isinstance(row.wepa, (int, float)):
                setattr(p, attr, float(row.wepa))
    for row in paar or []:
        p = players.get(row.athlete_id)
        if p is not None and isinstance(row.paar, (int, float)):
            p.paar = float(row.paar)

    by_id: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = {g: [] for g in GRADED}
    members: dict[str, list[Player]] = {g: [] for g in GRADED}
    for p in players.values():
        group = group_of(p.position, p.stats)
        base = {"playerId": p.player_id, "name": p.name, "team": p.team, "conference": p.conference, "position": p.position, "group": group,
                "groupName": GROUP_NAMES.get(group or ""), "grade": None, "label": None, "rank": None, "of": None, "basis": None, "components": [],
                "volume": None, "reason": None, "games": p.games}
        if group in UNGRADED or group is None:
            base["reason"] = UNGRADED.get(group or "", "No position to compare this player with.")
            by_id[p.player_id] = base
            continue
        spec = SPECS[group]
        volume = spec.volume(p)
        base["basis"] = spec.basis
        base["volume"] = {"label": spec.volume_label, "perGame": round(volume, 1) if volume is not None else None, "needed": spec.needed}
        if volume is None or volume < spec.needed:
            have = f"{volume:.1f}" if volume is not None else "no"
            base["reason"] = f"Not enough plays to grade: {have} {spec.volume_label}, {spec.needed:g} needed."
            by_id[p.player_id] = base
            continue
        by_id[p.player_id] = base
        members[group].append(p)

    for group, spec in SPECS.items():
        peers = members[group]
        values_by_component: dict[str, dict[str, float]] = {}
        for comp in spec.components:
            values: dict[str, float] = {}
            for p in peers:
                try:
                    value = comp.read(p)
                except (TypeError, ZeroDivisionError):
                    value = None
                if value is not None and value == value and abs(value) != float("inf"):  # NaN and infinities never rank
                    values[p.player_id] = value
            values_by_component[comp.key] = values
        pctls = {comp.key: _percentiles(values_by_component[comp.key], comp.higher) for comp in spec.components}
        total = sum(c.weight for c in spec.components)
        for p in peers:
            row = by_id[p.player_id]
            parts, have = [], 0.0
            score = 0.0
            for comp in spec.components:
                value = values_by_component[comp.key].get(p.player_id)
                pctl = pctls[comp.key].get(p.player_id)
                parts.append({"key": comp.key, "label": comp.label, "value": round(value, 4) if value is not None else None, "format": comp.format, "percentile": pctl, "weight": comp.weight})
                if pctl is not None:
                    score += comp.weight * pctl
                    have += comp.weight
            row["components"] = parts
            if have < MIN_WEIGHT_SHARE * total:
                row["reason"] = "Not enough stats to grade."
                continue
            row["grade"] = max(0, min(100, round(score / have)))
            row["label"] = label_for(row["grade"])
            groups[group].append(row)
        rows = sorted(groups[group], key=lambda r: (-r["grade"], r["name"] or "", r["playerId"]))
        _tie_ranks(rows)
        for row in rows:
            row["of"] = len(rows)
        groups[group] = rows
    return GradeTable(by_id, groups)


def public(row: dict[str, Any] | None, *, components: bool = True) -> dict[str, Any] | None:
    """A grade as the API sends it (components only where asked)."""
    if row is None:
        return None
    out = {k: row.get(k) for k in ("playerId", "name", "team", "position", "group", "groupName", "grade", "label", "rank", "of", "basis", "reason", "volume")}
    if components:
        out["components"] = row.get("components") or []
    return out


# --- the service: the national lists through the Leaders page's own keys ---------------------------------


class GradeService:
    """Loads the national player pulls through the players service's fetcher, with the byte-identical keys the
    Leaders page uses, so grades cost no call once Leaders has loaded (about 12 on a cold cache, cached for
    the season-stats lifetime). The table is rebuilt only when one of its parts changes."""

    def __init__(self, client: Any, settings: Any, fetcher: Any) -> None:
        self.client = client
        self.settings = settings
        self.fetcher = fetcher
        self._memo: tuple[tuple[Any, ...], GradeTable] | None = None

    @property
    def year(self) -> int:
        return self.settings.season

    async def parts(self) -> dict[str, Any]:
        import asyncio

        from app.cache import DataKind
        from app.cfbd.models import Team
        from app.services.players import CATEGORIES, PPA_MIN_PLAYS

        f, year = self.fetcher, self.year
        fetches = [f.fetch(f"national_{c}", "/stats/player/season", {"year": year, "category": c}, PlayerStat, DataKind.SEASON_STATS) for c in CATEGORIES]
        fetches += [
            f.fetch("teams", "/teams/fbs", {"year": year}, Team, DataKind.TEAMS),
            f.fetch("games", "/games", {"year": year}, Game, DataKind.SCHEDULE),
            f.fetch("ppaSeasonAll", "/ppa/players/season", {"year": year, "threshold": PPA_MIN_PLAYS}, PlayerSeasonPpa, DataKind.SEASON_STATS),
            f.fetch("wepaPassing", "/wepa/players/passing", {"year": year}, PlayerWeightedEPA, DataKind.SEASON_STATS),
            f.fetch("wepaRushing", "/wepa/players/rushing", {"year": year}, PlayerWeightedEPA, DataKind.SEASON_STATS),
            f.fetch("paar", "/wepa/players/kicking", {"year": year}, KickerPAAR, DataKind.SEASON_STATS),
        ]
        return {part.name: part for part in await asyncio.gather(*fetches)}

    async def table(self) -> tuple[GradeTable, dict[str, Any]]:
        from app.services.players import CATEGORIES

        parts = await self.parts()
        key = tuple((name, part.fetched.fetched_at if part.fetched else None, len(part.records)) for name, part in sorted(parts.items()))
        if self._memo is not None and self._memo[0] == key:
            return self._memo[1], parts
        fbs = {t.school for t in parts["teams"].records if getattr(t, "school", None)} or None
        table = build(
            {c: parts[f"national_{c}"].records for c in CATEGORIES}, parts["games"].records, fbs, parts["ppaSeasonAll"].records,
            parts["wepaPassing"].records, parts["wepaRushing"].records, parts["paar"].records,
        )
        self._memo = (key, table)
        return table, parts
