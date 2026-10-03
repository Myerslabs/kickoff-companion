"""In-game analysis for the Live sheet's side sheets (Phase 12), all from released plays and
drives, so it follows the spoiler delay like everything else and costs no calls:

- Quarter splits per team: plays, yards, yards per play, success n of m, EPA per play (touchdown
  plays left out, since their EPA is mostly the score itself), 20+ yard plays, turnovers, third
  downs, and a few notes written from fixed thresholds (no model, no AI).
- Tendencies by situation per offense: standard downs, passing downs, third down by distance,
  the red zone; pass rate and success on runs and on passes. Run or pass comes from the feed's
  rushPass tag, else from the play type; standard or passing down from the feed's downType tag,
  else from the usual rule (2nd and 8 or more, 3rd or 4th and 5 or more is a passing down).
- Drive summary per team: drives, points, points per drive, three-and-outs, turnovers, scoring
  opportunities and points per opportunity; and per drive, success n of m and EPA.
- Fourth down: when the delayed state is 4th down, the conversion rate at which going for it
  breaks even with the better kick, from CFBD's expected points tables (verified 2026-09-26:
  /ppa/predicted rows are {yardLine, predictedPoints} with yardLine counted from the offense's
  own goal line and the 1st-and-10 table ending at 90; /metrics/fg/ep rows are {yardsToGoal,
  distance, expectedPoints} where expectedPoints is only 3 x the make chance, so the kick branch
  here adds the kickoff after a make and the opponent's field position after a miss)."""

from __future__ import annotations

import math
import re
from typing import Any

from app.live.events import is_scrimmage

TURNOVER_RESULTS = frozenset({"INT", "INT TD", "FUMBLE", "FUMBLE TD"})
DRIVE_POINTS = {"TD": 7, "FG": 3}  # when the feed sends no pointsGained; a touchdown counts the usual extra point
PERIOD_LABELS = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}
NOTE_MIN_PLAYS = 8  # a quarter needs this many snaps per team before a note compares it
NOTE_SUCCESS_GAP = 0.15
NOTE_YPP_GAP = 2.5

# Fourth down (all expected points are the offense's view)
TOUCHDOWN_POINTS = 6.95  # six plus a near-certain extra point
KICKOFF_START = 25  # the opponent's start after a score (touchback at the 25)
PUNT_NET = 40
PUNT_TOUCHBACK = 20
FG_SNAP_BACK = 17  # kick distance = yards to goal + 17
FG_MAX_DISTANCE = 60
MISS_SPOT_BACK = 7  # a miss: the opponent takes over at the spot of the kick, or its 20 if that is farther back


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _rate(made: int, of: int) -> float | None:
    return round(made / of, 4) if of else None


def rush_or_pass(play: dict[str, Any]) -> str | None:
    tag = play.get("rushPass")
    if isinstance(tag, str) and tag.lower() in ("rush", "pass"):
        return tag.lower()
    kind = str(play.get("playType") or "").lower()
    if "pass" in kind or "sack" in kind or "interception" in kind:
        return "pass"
    if "rush" in kind:
        return "rush"
    return None


def down_type(play: dict[str, Any]) -> str | None:
    tag = play.get("downType")
    if isinstance(tag, str) and tag.lower() in ("standard", "passing"):
        return tag.lower()
    down, distance = _int(play.get("down")), _int(play.get("distance"))
    if down is None or distance is None:
        return None
    return "passing" if (down == 2 and distance >= 8) or (down in (3, 4) and distance >= 5) else "standard"


def _epa(play: dict[str, Any]) -> float | None:
    """A play's EPA for averages: none on touchdown plays (their EPA is mostly the score)."""
    if "touchdown" in str(play.get("playType") or "").lower():
        return None
    return _num(play.get("ppa"))


class _Tally:
    __slots__ = ("plays", "yards", "judged", "successes", "epa_sum", "epa_n", "explosive", "turnovers", "third_made", "third_of")

    def __init__(self) -> None:
        self.plays = self.yards = self.judged = self.successes = self.epa_n = self.explosive = self.turnovers = self.third_made = self.third_of = 0
        self.epa_sum = 0.0

    def add(self, play: dict[str, Any]) -> None:
        gained = _int(play.get("yardsGained")) or 0
        self.plays += 1
        self.yards += gained
        success = play.get("success")
        if isinstance(success, bool):
            self.judged += 1
            self.successes += success
        epa = _epa(play)
        if epa is not None:
            self.epa_sum += epa
            self.epa_n += 1
        if gained >= 20:
            self.explosive += 1
        flags = play.get("flags") if isinstance(play.get("flags"), list) else []
        if "turnover" in flags:
            self.turnovers += 1
        if play.get("down") == 3:
            self.third_of += 1
            distance = _int(play.get("distance"))
            if play.get("scoring") or (distance is not None and gained >= distance):
                self.third_made += 1

    def out(self) -> dict[str, Any]:
        return {
            "plays": self.plays,
            "yards": self.yards,
            "yardsPerPlay": round(self.yards / self.plays, 2) if self.plays else None,
            "success": {"made": self.successes, "of": self.judged},
            "successRate": _rate(self.successes, self.judged),
            "epaPerPlay": round(self.epa_sum / self.epa_n, 3) if self.epa_n else None,
            "explosive": self.explosive,
            "turnovers": self.turnovers,
            "thirdDown": {"made": self.third_made, "of": self.third_of},
        }


def _period_key(period: Any) -> str | None:
    value = _int(period)
    if value is None or value < 1:
        return None
    return PERIOD_LABELS.get(value, "OT")


def quarter_splits(plays: list[dict[str, Any]], teams: tuple[str | None, str | None]) -> dict[str, Any]:
    """{"periods": ["Q1", ...], "teams": {team: {"Q1": {...}, ..., "Game": {...}}}, "notes": [...]}"""
    sides = [t for t in teams if t]
    tallies: dict[str, dict[str, _Tally]] = {t: {} for t in sides}
    periods: list[str] = []
    for play in plays:
        offense = play.get("offense")
        key = _period_key(play.get("period"))
        if offense not in tallies or key is None or not is_scrimmage(play.get("playType")):
            continue
        if key not in periods:
            periods.append(key)
        tallies[offense].setdefault(key, _Tally()).add(play)
        tallies[offense].setdefault("Game", _Tally()).add(play)
    order = [p for p in ("Q1", "Q2", "Q3", "Q4", "OT") if p in periods]
    out = {team: {key: tally.out() for key, tally in by.items()} for team, by in tallies.items()}
    return {"periods": order, "teams": out, "notes": _notes(out, order, sides)}


def _notes(splits: dict[str, dict[str, Any]], periods: list[str], sides: list[str]) -> list[str]:
    """A few plain lines from fixed thresholds: a big success-rate or yards-per-play gap in a
    quarter, and a team whose success rate moved a lot from its first half to its second."""
    if len(sides) != 2:
        return []
    a, b = sides
    notes: list[str] = []
    for period in periods:
        sa, sb = splits.get(a, {}).get(period), splits.get(b, {}).get(period)
        if not sa or not sb or sa["plays"] < NOTE_MIN_PLAYS or sb["plays"] < NOTE_MIN_PLAYS:
            continue
        ra, rb = sa["successRate"], sb["successRate"]
        if ra is not None and rb is not None and abs(ra - rb) >= NOTE_SUCCESS_GAP:
            lead, trail = (a, b) if ra > rb else (b, a)
            hi, lo = max(ra, rb), min(ra, rb)
            notes.append(f"{period}: {lead} success {round(hi * 100)}% to {trail} {round(lo * 100)}%.")
            continue
        ya, yb = sa["yardsPerPlay"], sb["yardsPerPlay"]
        if ya is not None and yb is not None and abs(ya - yb) >= NOTE_YPP_GAP:
            lead, trail = (a, b) if ya > yb else (b, a)
            notes.append(f"{period}: {lead} {max(ya, yb):.1f} yards a play to {trail} {min(ya, yb):.1f}.")
    for team in sides:
        halves = []
        for pair in (("Q1", "Q2"), ("Q3", "Q4")):
            made = sum(splits.get(team, {}).get(p, {}).get("success", {}).get("made", 0) for p in pair)
            of = sum(splits.get(team, {}).get(p, {}).get("success", {}).get("of", 0) for p in pair)
            halves.append((made, of))
        (m1, o1), (m2, o2) = halves
        if o1 >= 2 * NOTE_MIN_PLAYS and o2 >= NOTE_MIN_PLAYS:
            r1, r2 = m1 / o1, m2 / o2
            if abs(r2 - r1) >= NOTE_SUCCESS_GAP:
                notes.append(f"{team} success rate {'up' if r2 > r1 else 'down'} from {round(r1 * 100)}% in the first half to {round(r2 * 100)}% since.")
    return notes[:5]


SITUATIONS = [
    ("standard", "Standard downs"),
    ("passing", "Passing downs"),
    ("third_short", "3rd and 1 to 3"),
    ("third_medium", "3rd and 4 to 6"),
    ("third_long", "3rd and 7 or more"),
    ("red_zone", "Red zone"),
]


def _situations(play: dict[str, Any]) -> list[str]:
    found: list[str] = []
    kind = down_type(play)
    if kind:
        found.append(kind)
    if play.get("down") == 3:
        distance = _int(play.get("distance"))
        if distance is not None:
            found.append("third_short" if distance <= 3 else "third_medium" if distance <= 6 else "third_long")
    ytg = _int(play.get("yardsToGoal"))
    if ytg is not None and 0 < ytg <= 20:
        found.append("red_zone")
    return found


def tendencies(plays: list[dict[str, Any]], teams: tuple[str | None, str | None]) -> dict[str, list[dict[str, Any]]]:
    """{team: [{key, label, plays, passRate, runSuccess {made, of}, passSuccess {made, of}}]} per offense."""
    sides = [t for t in teams if t]
    counts = {t: {key: {"plays": 0, "passes": 0, "run_m": 0, "run_n": 0, "pass_m": 0, "pass_n": 0} for key, _ in SITUATIONS} for t in sides}
    for play in plays:
        offense = play.get("offense")
        if offense not in counts or not is_scrimmage(play.get("playType")):
            continue
        kind = rush_or_pass(play)
        if kind is None:
            continue
        success = play.get("success")
        for key in _situations(play):
            row = counts[offense][key]
            row["plays"] += 1
            if kind == "pass":
                row["passes"] += 1
            if isinstance(success, bool):
                prefix = "pass" if kind == "pass" else "run"
                row[f"{prefix}_n"] += 1
                row[f"{prefix}_m"] += success
    return {
        team: [
            {
                "key": key,
                "label": label,
                "plays": c["plays"],
                "passRate": _rate(c["passes"], c["plays"]),
                "runSuccess": {"made": c["run_m"], "of": c["run_n"]},
                "passSuccess": {"made": c["pass_m"], "of": c["pass_n"]},
            }
            for key, label in SITUATIONS
            for c in (counts[team][key],)
        ]
        for team in sides
    }


def _drive_points(drive: dict[str, Any]) -> int:
    gained = _int(drive.get("pointsGained"))
    if gained is not None and gained >= 0:
        return gained
    return DRIVE_POINTS.get(str(drive.get("result") or ""), 0)


def _opportunity(drive: dict[str, Any], drive_plays: list[dict[str, Any]]) -> bool:
    """CFBD's scoringOpportunity flag when the feed sends it; else a first down at the opponent's 40 or closer."""
    flag = drive.get("scoringOpportunity")
    if isinstance(flag, bool):
        return flag
    return any(p.get("down") == 1 and (_int(p.get("yardsToGoal")) or 100) <= 40 and p.get("offense") == drive.get("offense") for p in drive_plays)


def drive_summary(drives: list[dict[str, Any]], plays_by_drive: dict[str, list[dict[str, Any]]], teams: tuple[str | None, str | None]) -> dict[str, Any]:
    """Per team: drives, points, pointsPerDrive, threeAndOuts, turnovers, opportunities, pointsPerOpportunity.
    Also sets successCounts and epaPerPlay on each drive dict it is given (a copy made by the caller)."""
    sides = [t for t in teams if t]
    out = {t: {"drives": 0, "points": 0, "threeAndOuts": 0, "turnovers": 0, "opportunities": 0, "opportunityPoints": 0} for t in sides}
    for drive in drives:
        drive_plays = plays_by_drive.get(str(drive.get("id")), [])
        offense = drive.get("offense")
        snaps = [p for p in drive_plays if is_scrimmage(p.get("playType")) and p.get("offense") in (offense, None)]
        judged = [p for p in snaps if isinstance(p.get("success"), bool)]
        epas = [e for e in (_epa(p) for p in snaps) if e is not None]
        drive["successCounts"] = {"made": sum(1 for p in judged if p["success"]), "of": len(judged)}
        drive["epaPerPlay"] = round(sum(epas) / len(epas), 3) if epas else None
        if offense not in out or not drive.get("result"):
            continue  # a drive still going does not count yet
        row = out[offense]
        points = _drive_points(drive)
        row["drives"] += 1
        row["points"] += points
        if drive.get("result") == "PUNT" and len(snaps) <= 3:
            row["threeAndOuts"] += 1
        if drive.get("result") in TURNOVER_RESULTS:
            row["turnovers"] += 1
        if _opportunity(drive, drive_plays):
            row["opportunities"] += 1
            row["opportunityPoints"] += points
    for row in out.values():
        row["pointsPerDrive"] = round(row["points"] / row["drives"], 2) if row["drives"] else None
        row["pointsPerOpportunity"] = round(row["opportunityPoints"] / row["opportunities"], 2) if row["opportunities"] else None
    return out


# --- fourth down --------------------------------------------------------------------------------------


def ep_table(rows: Any) -> dict[int, float]:
    """{yardLine: predictedPoints} from parsed /ppa/predicted records (objects with yard_line, predicted_points)."""
    table: dict[int, float] = {}
    for row in rows or []:
        line, points = _int(getattr(row, "yard_line", None)), _num(getattr(row, "predicted_points", None))
        if line is not None and points is not None and 1 <= line <= 99:
            table[line] = points
    return table


def fg_table(rows: Any) -> dict[int, float]:
    """{yardsToGoal: make chance} from parsed /metrics/fg/ep records (expectedPoints / 3)."""
    table: dict[int, float] = {}
    for row in rows or []:
        ytg, points = _int(getattr(row, "yards_to_goal", None)), _num(getattr(row, "expected_points", None))
        if ytg is not None and points is not None and ytg >= 0 and 0 <= points <= 3:
            table[ytg] = points / 3
    return table


def _lookup(table: dict[int, float], line: int) -> float | None:
    if not table:
        return None
    if line in table:
        return table[line]
    nearest = min(table, key=lambda k: abs(k - line))
    return table[nearest] if abs(nearest - line) <= 10 else None


def fourth_down(down: Any, distance: Any, yards_to_goal: Any, first_down: dict[int, float], fg: dict[int, float]) -> dict[str, Any] | None:
    """The go-or-kick numbers for a 4th down, or None when it is not one or a table is missing.
    {breakEven, go {success, fail}, fieldGoal {distance, makeChance, ep} | None, punt {ep} | None, best}."""
    down, distance, ytg = _int(down), _int(distance), _int(yards_to_goal)
    if down != 4 or distance is None or ytg is None or distance < 1 or not 1 <= ytg <= 99 or not first_down:
        return None
    line = 100 - ytg  # the offense's yard line from its own goal

    def theirs(their_line: int) -> float | None:
        value = _lookup(first_down, min(90, max(1, their_line)))
        return -value if value is not None else None

    after_score = theirs(KICKOFF_START)
    if after_score is None:
        return None
    if distance >= ytg:
        success = TOUCHDOWN_POINTS + after_score
    else:
        value = _lookup(first_down, min(90, line + distance))
        if value is None:
            return None
        success = value
    fail = theirs(100 - line)
    if fail is None:
        return None
    field_goal = None
    kick_distance = ytg + FG_SNAP_BACK
    make = _lookup(fg, ytg) if kick_distance <= FG_MAX_DISTANCE else None
    if make is not None:
        miss = theirs(max(PUNT_TOUCHBACK, 100 - (line - MISS_SPOT_BACK)))
        if miss is not None:
            field_goal = {"distance": kick_distance, "makeChance": round(make, 3), "ep": round(make * (3 + after_score) + (1 - make) * miss, 2)}
    punt = None
    if line + PUNT_NET < 100:
        punt_ep = theirs(100 - (line + PUNT_NET))
    else:
        punt_ep = theirs(PUNT_TOUCHBACK)
    if punt_ep is not None and ytg > 35:  # nobody punts from the opponent's 35 or closer
        punt = {"ep": round(punt_ep, 2)}
    kicks = [k for k in (field_goal, punt) if k is not None]
    if not kicks or success <= fail:
        return None
    best_kick = max(kicks, key=lambda k: k["ep"])
    even = (best_kick["ep"] - fail) / (success - fail)
    return {
        "down": 4,
        "distance": distance,
        "yardsToGoal": ytg,
        "breakEven": round(min(1.0, max(0.0, even)), 3),
        "go": {"success": round(success, 2), "fail": round(fail, 2)},
        "fieldGoal": field_goal,
        "punt": punt,
        "best": "fieldGoal" if best_kick is field_goal else "punt",
    }


# --- shot chart (public release Phase 7b) ------------------------------------------------------------------
# Every pass in the play-by-play names its zone ("pass complete short left", "pass incomplete deep middle") and
# every run its direction ("rush right", "rush left end", "rush up the middle"); checked against the recorded
# live documents of 2026-10-03. A pass with no zone (a sack, a scramble, a throwaway) or a run with no direction
# counts in "unzoned" so the totals still add up.

PASS_ZONES = tuple(f"{depth}-{side}" for depth in ("deep", "short") for side in ("left", "middle", "right"))
RUN_LANES = ("left", "middle", "right")
_PASS_ZONE = re.compile(r"\b(short|deep)\s+(left|middle|right)\b", re.IGNORECASE)
_RUN_LANE = re.compile(r"\brush(?:es)?\s+(?:up\s+the\s+)?(left|middle|right)\b", re.IGNORECASE)
_COMPLETE = re.compile(r"\bpass\s+complete\b", re.IGNORECASE)
_SACK = re.compile(r"\bsack", re.IGNORECASE)


def _cell() -> dict[str, Any]:
    return {"attempts": 0, "completions": 0, "yards": 0, "success": {"made": 0, "of": 0}}


def _add(cell: dict[str, Any], play: dict[str, Any], completed: bool) -> None:
    cell["attempts"] += 1
    if completed:
        cell["completions"] += 1
    gained = play.get("yardsGained")
    if isinstance(gained, (int, float)) and not isinstance(gained, bool) and gained == gained:
        cell["yards"] += int(gained)
    success = play.get("success")
    if isinstance(success, bool):
        cell["success"]["of"] += 1
        cell["success"]["made"] += int(success)


def _finish(cell: dict[str, Any]) -> dict[str, Any]:
    made, of = cell["success"]["made"], cell["success"]["of"]
    attempts = cell["attempts"]
    return {**cell, "successRate": round(made / of, 3) if of else None, "completionRate": round(cell["completions"] / attempts, 3) if attempts else None,
            "yardsPerAttempt": round(cell["yards"] / attempts, 1) if attempts else None}


def shot_chart(plays: list[dict[str, Any]], teams: tuple[str | None, str | None]) -> dict[str, dict[str, Any]]:
    """{team: {passes: {zone: cell}, runs: {lane: cell}, unzoned: {passes, runs}, sacks}} for each offense, from
    the released plays. A cell: attempts, completions (passes), yards, success {made, of}, successRate,
    completionRate, yardsPerAttempt."""
    sides = [t for t in teams if t]
    raw = {t: {"passes": {z: _cell() for z in PASS_ZONES}, "runs": {lane: _cell() for lane in RUN_LANES}, "unzoned": {"passes": 0, "runs": 0}, "sacks": 0} for t in sides}
    for play in plays:
        offense = play.get("offense")
        if offense not in raw or not is_scrimmage(play.get("playType")):
            continue
        kind = rush_or_pass(play)
        words = str(play.get("text") or "")
        if kind == "pass":
            if _SACK.search(str(play.get("playType") or "")) or _SACK.search(words):
                raw[offense]["sacks"] += 1
                continue
            zone = _PASS_ZONE.search(words)
            if zone is None:
                raw[offense]["unzoned"]["passes"] += 1
                continue
            completed = bool(_COMPLETE.search(words))
            _add(raw[offense]["passes"][f"{zone.group(1).lower()}-{zone.group(2).lower()}"], play, completed)
        elif kind == "rush":
            lane = _RUN_LANE.search(words)
            if lane is None:
                raw[offense]["unzoned"]["runs"] += 1
                continue
            _add(raw[offense]["runs"][lane.group(1).lower()], play, False)
    return {
        team: {
            "passes": {z: _finish(c) for z, c in data["passes"].items()},
            "runs": {lane: _finish(c) for lane, c in data["runs"].items()},
            "unzoned": data["unzoned"],
            "sacks": data["sacks"],
        }
        for team, data in raw.items()
    }
