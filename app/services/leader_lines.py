"""Leaders side by side, the whole line (Phase 17 #17, owner 2026-10-07: "show overall stats, to include secondary
stats, but also conference stats"; answers: both conference ranks and conference-game stats).

For each leader on the Game program: every stat of the category in a fixed reading order, a national rank and a
conference rank on each counting stat (from the national pulls the Leaders page caches; the conference rank is
among FBS players whose team is in that conference, so no conference pull is needed), and the same line counted
over conference games only (from each conference game's /games/players box, cached for good).

    LINE_STATS[category]                       the stats shown, in order
    RankIndex(national_lines, conference_of)   ranks for any (category, stat) on demand
    leader_detail(line, index)                 {"stats": [{stat, value, national, conference}]}
    game_totals(boxes)                         {(player id, category): {stat: total}} over the given box parts
"""

from __future__ import annotations

from typing import Any

from app.services.players import BOARDS, Line
from app.services.profiles import tie_ranks

LINE_STATS: dict[str, list[str]] = {
    "passing": ["YDS", "TD", "INT", "COMPLETIONS", "ATT", "PCT", "YPA"],
    "rushing": ["YDS", "TD", "CAR", "YPC", "LONG"],
    "receiving": ["YDS", "TD", "REC", "YPR", "LONG"],
    "defensive": ["TOT", "SOLO", "TFL", "SACKS", "QB HUR", "PD"],
}
# Counting stats get rank chips; a rate (PCT, YPA, YPC, YPR) needs a volume floor to rank fairly and an
# interception thrown is not a thing to lead in, so neither gets one.
RANKED = frozenset({"YDS", "TD", "COMPLETIONS", "ATT", "CAR", "REC", "TOT", "SOLO", "TFL", "SACKS", "QB HUR", "PD"})
# The national lists the chips open (final pass, tables-9): a stat has one when the Leaders page keeps a board for it.
BOARD_IDS = frozenset(board.id for board in BOARDS)
# /games/players names some stats differently from the season lines; each box key -> the season key.
BOX_KEYS = {"AVG": None, "QBR": None}


def _number(value: Any) -> float | None:
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


class RankIndex:
    """National and conference ranks for any (category, stat), built once each on first use. The conference of
    a player is his team's conference from /teams/fbs (conference_of: school -> conference)."""

    def __init__(self, national: dict[str, dict[tuple[str, str], Line]], conference_of: dict[str, str]) -> None:
        self.national = national
        self.conference_of = conference_of
        self._built: dict[tuple[str, str], tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int, str]]]] = {}

    def _build(self, category: str, stat: str) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int, str]]]:
        key = (category, stat)
        if key in self._built:
            return self._built[key]
        rows = [(line, line.stats.get(stat)) for line in self.national.get(category, {}).values()]
        valued = sorted(((line, float(v)) for line, v in rows if isinstance(v, float) and v > 0), key=lambda pair: -pair[1])
        nat_ranks = tie_ranks([v for _, v in valued])
        national = {line.player_id: (rank, len(valued)) for (line, _), rank in zip(valued, nat_ranks, strict=True)}
        groups: dict[str, list[tuple[Line, float]]] = {}
        for line, value in valued:
            conf = self.conference_of.get(line.team or "")
            if conf:
                groups.setdefault(conf, []).append((line, value))
        conference: dict[str, tuple[int, int, str]] = {}
        for conf, members in groups.items():
            for (line, _), rank in zip(members, tie_ranks([v for _, v in members]), strict=True):
                conference[line.player_id] = (rank, len(members), conf)
        self._built[key] = (national, conference)
        return self._built[key]

    def ranks(self, category: str, stat: str, player_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if stat not in RANKED:
            return None, None
        national, conference = self._build(category, stat)
        nat = national.get(player_id)
        conf = conference.get(player_id)
        return ({"rank": nat[0], "of": nat[1]} if nat else None), ({"rank": conf[0], "of": conf[1], "conference": conf[2]} if conf else None)


def leader_detail(line: Line | None, category: str, index: RankIndex) -> dict[str, Any] | None:
    """The whole line of one leader: each stat of the category that he has, in order, with its ranks."""
    if line is None:
        return None
    stats = []
    for stat in LINE_STATS.get(category, []):
        value = line.stats.get(stat)
        if not isinstance(value, float):
            continue
        national, conference = index.ranks(category, stat, line.player_id)
        metric = f"board:{category}:{stat}" if f"{category}:{stat}" in BOARD_IDS else None
        stats.append({"stat": stat, "value": value, "national": national, "conference": conference, "metric": metric})
    return {"stats": stats}


def game_totals(boxes: list[Any]) -> dict[tuple[str, str], dict[str, float]]:
    """Season-style totals over the given games' /games/players records, per (player id, category): counting stats
    summed, completions and attempts split out of C/ATT, the long the longest, and the rates worked out again
    (PCT, YPA, YPC, YPR) from the sums. A game counts once even when two answers hold it."""
    totals: dict[tuple[str, str], dict[str, float]] = {}
    seen: set[int] = set()
    for game in boxes:
        game_id = getattr(game, "id", None)
        if game_id is None or game_id in seen:
            continue
        seen.add(game_id)
        for side in getattr(game, "teams", None) or []:
            for category in getattr(side, "categories", None) or []:
                name = getattr(category, "name", None)
                if name not in LINE_STATS:
                    continue
                for stat_type in getattr(category, "types", None) or []:
                    stat = getattr(stat_type, "name", None)
                    if not isinstance(stat, str) or stat in BOX_KEYS:
                        continue
                    for athlete in getattr(stat_type, "athletes", None) or []:
                        pid = getattr(athlete, "id", None)
                        if not pid:
                            continue
                        row = totals.setdefault((str(pid), name), {})
                        raw = getattr(athlete, "stat", None)
                        if stat == "C/ATT":
                            parts = str(raw).split("/") if raw is not None else []
                            made, tried = (_number(parts[0]), _number(parts[1])) if len(parts) == 2 else (None, None)
                            if made is not None and tried is not None:
                                row["COMPLETIONS"] = row.get("COMPLETIONS", 0.0) + made
                                row["ATT"] = row.get("ATT", 0.0) + tried
                            continue
                        value = _number(raw)
                        if value is None:
                            continue
                        row[stat] = max(row.get(stat, value), value) if stat == "LONG" else row.get(stat, 0.0) + value
    for (_, category), row in totals.items():
        yards = row.get("YDS")
        rate = {"passing": ("YPA", "ATT"), "rushing": ("YPC", "CAR"), "receiving": ("YPR", "REC")}.get(category)
        if rate and yards is not None and row.get(rate[1]):
            row[rate[0]] = round(yards / row[rate[1]], 1)
        if category == "passing" and row.get("ATT"):
            row["PCT"] = round(row.get("COMPLETIONS", 0.0) / row["ATT"], 3)
    return totals
