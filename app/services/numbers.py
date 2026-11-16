"""The app's own numbers for every FBS team (FEAT-8, owner 2026-10-25: every team as deep as ours), from every play of every
final game this season: success rate by down and distance, explosive plays, havoc, and red-zone finishing, for each
offense and, from its opponents' snaps, each defense, with national ranks.

    game_counts(plays) -> {team: counts}        one game's counts for each offense, from CFBD's /plays rows
    NumbersStore(data_dir, season)              data/season/<year>/numbers.json: the counts of each game, kept for good
      .has(game_id), .put(game_id, week, home, away, counts), .games()
    season_table(store, fbs) -> {teams: [...], games}    every FBS team's season line with its national ranks
    team_line(table, school) -> dict | None

The rules, written once here:
- A snap is a scrimmage play (app/live/events.py is_scrimmage); its success is the local rule (50% of the distance on
  first down, 70% on second, all of it after; a turnover fails, an offensive touchdown succeeds).
- Down and distance: 1st down; 2nd and short (1 to 3), medium (4 to 7), long (8 or more); 3rd and 4th the same; and
  standard and passing downs (2nd and 8 or more, 3rd and 4th and 5 or more are passing downs).
- Explosive: a snap of 20 yards or more, the same line the In Game box uses.
- Havoc, on defense: a tackle for loss (a run that loses yards), a sack, or a takeaway, per snap the defense faced.
- Red zone: a drive with a snap inside the 20 is a trip; it is finished with a touchdown (seven points) or a field goal
  (three). CFBD's play types name each; nothing else counts.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.live.analysis import rush_or_pass
from app.live.events import TURNOVER, is_scrimmage, play_success
from app.services.answers import atomic_write

log = logging.getLogger("kickoff.numbers")

FORMAT = 1
EXPLOSIVE_YARDS = 20
RED_ZONE = 20
MIN_SNAPS = 100  # a team with fewer snaps in the season gets no national rank yet
TOUCHDOWN = re.compile(r"touchdown", re.IGNORECASE)
FIELD_GOAL_GOOD = re.compile(r"field goal good", re.IGNORECASE)
SACK = re.compile(r"\bsack\b", re.IGNORECASE)

BUCKETS = (  # key, label: the down-and-distance rows, in the order a table shows them
    ("first", "1st down"),
    ("second_short", "2nd and short (1-3)"),
    ("second_medium", "2nd and medium (4-7)"),
    ("second_long", "2nd and long (8+)"),
    ("third_short", "3rd/4th and short (1-3)"),
    ("third_medium", "3rd/4th and medium (4-7)"),
    ("third_long", "3rd/4th and long (8+)"),
    ("standard", "Standard downs"),
    ("passing", "Passing downs"),
)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _field(play: Any, name: str) -> Any:
    return play.get(name) if isinstance(play, dict) else getattr(play, name, None)


def _snake(play: Any, snake: str, camel: str) -> Any:
    value = _field(play, snake)
    return _field(play, camel) if value is None and isinstance(play, dict) else value


def buckets_of(down: int | None, distance: int | None) -> list[str]:
    if down not in (1, 2, 3, 4) or distance is None or distance < 0:
        return []
    found: list[str] = []
    if down == 1:
        found.append("first")
    else:
        size = "short" if distance <= 3 else "medium" if distance <= 7 else "long"
        found.append(f"{'second' if down == 2 else 'third'}_{size}")
    passing = (down == 2 and distance >= 8) or (down in (3, 4) and distance >= 5)
    found.append("passing" if passing else "standard")
    return found


def _empty() -> dict[str, Any]:
    return {"snaps": 0, "judged": 0, "success": 0, "explosive": 0, "rushes": 0, "passes": 0, "havoc": 0, "tfl": 0, "sacks": 0, "takeaways": 0,
            "rzTrips": 0, "rzTd": 0, "rzFg": 0, "by": {key: [0, 0] for key, _ in BUCKETS}}


def game_counts(plays: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """One game's counts for each offense. `havoc` and its parts are what the other side's defense did to that offense,
    so a defense's line is read from its opponents' counts. Plays may be Play models or CFBD's camelCase rows."""
    counts: dict[str, dict[str, Any]] = {}
    drives: dict[tuple[str, str], dict[str, bool]] = {}
    for play in plays:
        offense = _field(play, "offense")
        play_type = _snake(play, "play_type", "playType")
        if not isinstance(offense, str) or not offense or not isinstance(play_type, str):
            continue
        row = counts.setdefault(offense, _empty())
        drive_id = _snake(play, "drive_id", "driveId")
        ytg = _int(_snake(play, "yards_to_goal", "yardsToGoal"))
        drive = drives.setdefault((offense, str(drive_id)), {"trip": False, "td": False, "fg": False}) if drive_id is not None else None
        if drive is not None:
            if TOUCHDOWN.search(play_type) and not TURNOVER.search(play_type):
                drive["td"] = True
            if FIELD_GOAL_GOOD.search(play_type):
                drive["fg"] = True
        if not is_scrimmage(play_type):
            continue
        down, distance = _int(_field(play, "down")), _int(_field(play, "distance"))
        gained = _int(_snake(play, "yards_gained", "yardsGained"))
        scoring = _field(play, "scoring")
        row["snaps"] += 1
        if drive is not None and ytg is not None and 0 < ytg <= RED_ZONE:
            drive["trip"] = True
        kind = rush_or_pass({"playType": play_type})
        if kind == "rush":
            row["rushes"] += 1
        elif kind == "pass":
            row["passes"] += 1
        success = play_success(down, distance, gained, play_type, scoring if isinstance(scoring, bool) else None)
        if success is not None:
            row["judged"] += 1
            row["success"] += int(success)
            for key in buckets_of(down, distance):
                row["by"][key][1] += 1
                row["by"][key][0] += int(success)
        if gained is not None and gained >= EXPLOSIVE_YARDS:
            row["explosive"] += 1
        tfl = kind == "rush" and gained is not None and gained < 0
        sack = bool(SACK.search(play_type))
        takeaway = bool(TURNOVER.search(play_type))
        row["tfl"] += int(tfl)
        row["sacks"] += int(sack)
        row["takeaways"] += int(takeaway)
        row["havoc"] += int(tfl or sack or takeaway)
    for (offense, _drive), drive in drives.items():
        if drive["trip"]:
            row = counts[offense]
            row["rzTrips"] += 1
            row["rzTd"] += int(drive["td"])
            row["rzFg"] += int(drive["fg"] and not drive["td"])
    return {team: row for team, row in counts.items() if row["snaps"] > 0}


# --- the store ---------------------------------------------------------------------------------------------------


class NumbersStore:
    def __init__(self, data_dir: Path, season: int) -> None:
        self.path = Path(data_dir) / "season" / str(season) / "numbers.json"
        self.season = season
        self._cache: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = {}
        except (OSError, ValueError) as exc:
            log.warning("The season's numbers could not be read (%s); starting over", exc)
            raw = {}
        games = raw.get("games") if isinstance(raw, dict) and raw.get("format") == FORMAT else None
        self._cache = {"format": FORMAT, "season": self.season, "games": games if isinstance(games, dict) else {}}
        return self._cache

    def has(self, game_id: int) -> bool:
        return str(game_id) in self._load()["games"]

    def games(self) -> dict[str, Any]:
        return dict(self._load()["games"])

    def put(self, game_id: int, week: int | None, home: str | None, away: str | None, counts: dict[str, Any]) -> None:
        data = self._load()
        data["games"][str(game_id)] = {"week": week, "home": home, "away": away, "teams": counts}

    def save(self) -> None:
        data = self._load()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(self.path, json.dumps(data, separators=(",", ":")) + "\n")
        except OSError as exc:
            log.warning("Could not keep the season's numbers: %s", exc)


# --- the season table --------------------------------------------------------------------------------------------


def _rate(made: int, of: int) -> float | None:
    return round(made / of, 4) if of else None


def _add(total: dict[str, Any], row: dict[str, Any]) -> None:
    for key, value in row.items():
        if key == "by":
            for bucket, (made, of) in value.items():
                if bucket in total["by"] and isinstance(made, int) and isinstance(of, int):
                    total["by"][bucket][0] += made
                    total["by"][bucket][1] += of
        elif isinstance(value, int) and key in total:
            total[key] += value


def _line(counts: dict[str, Any]) -> dict[str, Any]:
    snaps = counts["snaps"]
    trips = counts["rzTrips"]
    return {
        "snaps": snaps,
        "successRate": _rate(counts["success"], counts["judged"]),
        "explosiveRate": _rate(counts["explosive"], snaps),
        "explosive": counts["explosive"],
        "havocRate": _rate(counts["havoc"], snaps),
        "havoc": {"tfl": counts["tfl"], "sacks": counts["sacks"], "takeaways": counts["takeaways"]},
        "passRate": _rate(counts["passes"], counts["passes"] + counts["rushes"]),
        "redZone": {"trips": trips, "touchdowns": counts["rzTd"], "fieldGoals": counts["rzFg"], "tdRate": _rate(counts["rzTd"], trips),
                    "pointsPerTrip": round((7 * counts["rzTd"] + 3 * counts["rzFg"]) / trips, 2) if trips else None},
        "downs": [{"key": key, "label": label, "made": counts["by"][key][0], "of": counts["by"][key][1], "rate": _rate(*counts["by"][key])} for key, label in BUCKETS],
    }


RANKED = (  # (side, metric, higher is better)
    ("offense", "successRate", True), ("offense", "explosiveRate", True), ("offense", "havocRate", False), ("offense", "redZone.tdRate", True), ("offense", "redZone.pointsPerTrip", True),
    ("defense", "successRate", False), ("defense", "explosiveRate", False), ("defense", "havocRate", True), ("defense", "redZone.tdRate", False), ("defense", "redZone.pointsPerTrip", False),
)


def _get(line: dict[str, Any], path: str) -> Any:
    value: Any = line
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def season_table(games: dict[str, Any], fbs: set[str] | None = None) -> dict[str, Any]:
    """Every team's season line, offense and defense (what its opponents' offenses did against it), with national ranks
    among the FBS teams with MIN_SNAPS or more on that side. A defense's havoc is the havoc its opponents' offenses
    suffered in games against it."""
    offense: dict[str, dict[str, Any]] = {}
    defense: dict[str, dict[str, Any]] = {}
    played: dict[str, int] = {}
    for game in games.values():
        teams = game.get("teams") if isinstance(game, dict) else None
        if not isinstance(teams, dict):
            continue
        sides = [s for s in (game.get("home"), game.get("away")) if isinstance(s, str) and s]
        for team, row in teams.items():
            if not isinstance(row, dict):
                continue
            _add(offense.setdefault(team, _empty()), row)
            played[team] = played.get(team, 0) + 1
            opponent = next((s for s in sides if s != team), None)
            if opponent:
                _add(defense.setdefault(opponent, _empty()), row)
    schools = sorted(set(offense) | set(defense))
    if fbs:
        schools = [s for s in schools if s in fbs]
    rows = []
    for school in schools:
        rows.append({"school": school, "games": played.get(school, 0), "offense": _line(offense.get(school, _empty())), "defense": _line(defense.get(school, _empty()))})
    of: dict[str, int] = {}
    for row in rows:
        row["offense"]["ranks"], row["defense"]["ranks"] = {}, {}
    for side, metric, higher in RANKED:
        eligible = [r for r in rows if r[side]["snaps"] >= MIN_SNAPS and _get(r[side], metric) is not None]
        eligible.sort(key=lambda r: _get(r[side], metric), reverse=higher)
        rank, last = 0, None
        for i, row in enumerate(eligible, 1):
            value = _get(row[side], metric)
            if value != last:
                rank, last = i, value  # a tie shares the better rank
            row[side]["ranks"][metric] = rank
        of[f"{side}.{metric}"] = len(eligible)
    return {"teams": rows, "games": len(games), "rankOf": of}


def team_line(table: dict[str, Any], school: str) -> dict[str, Any] | None:
    return next((r for r in table.get("teams", []) if r.get("school") == school), None)
