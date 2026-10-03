"""Phase 16 stream BX, after the final: the win probability series on game time (GX-02), the biggest
swings (GX-09) and the postgame recap (UX-07). Pure functions over what the app already holds: the
post-game /metrics/wp series (wp_series rows), the archived final (data/archive/<id>.json), CFBD's
advanced box score and play value, and our schedule. No calls.

What the recorded /metrics/wp answer carries (tests/fixtures/cfbd/metrics_wp.json, 165 points):
playNumber, homeWinProbability, homeScore, awayScore, down, distance, yardLine, homeBall and
playText, but no period and no clock. The clock is the "(MM:SS)" that opens a play's text, and the
quarter ends are points of their own ("End of 1st quarter."), so the quarter is counted from those.
A series whose derived game time runs backwards is left without it rather than drawn wrong.

A point's probability is taken with the score after its play but the down, distance and field
position before it (the recorded touchdown point already shows the new score; an interception
shows on the next point). So the change between two points is credited to the later point's play
when the score changed there, and to the earlier point's play otherwise; a play's swing is the sum
of the changes credited to it (a touchdown's score and the kickoff that follows)."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.cfbd.models import Game
from app.services import gamekeys

CLOCK_AT_START = re.compile(r"^\s*\((\d{1,2}):(\d{2})\)")
QUARTER_END = re.compile(r"^\s*end of (?:the )?(1st|2nd|3rd|4th|first|second|third|fourth) quarter", re.IGNORECASE)
GAME_END = re.compile(r"^\s*(?:game ended|end of game|final)\b", re.IGNORECASE)
QUARTERS = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3, "4th": 4, "fourth": 4}
QUARTER_SECONDS = 900
BACKWARDS_TOLERANCE = 10  # seconds a derived game clock may step back before the series loses game time
SWING_LIMIT = 5
RECAP_WINDOW = timedelta(hours=36)

# (key, label, reader over one team's archived box, scale of a telling gap, higher is better, format)
KEY_STATS: list[tuple[str, str, Any, float, bool, str]] = [
    ("successRate", "Success rate", lambda b: b.get("successRate"), 0.10, True, "pct"),
    ("turnovers", "Turnovers", lambda b: b.get("turnovers"), 1.0, False, "0f"),
    ("explosive", "Explosive plays (20+ yards)", lambda b: (b.get("explosive") or {}).get("twenty") if isinstance(b.get("explosive"), dict) else None, 3.0, True, "0f"),
    ("yardsPerPlay", "Yards per play", lambda b: b.get("yardsPerPlay"), 1.5, True, "1f"),
    ("thirdDown", "Third-down rate", lambda b: _rate(b.get("thirdDown")), 0.20, True, "pct"),
    ("rushingYards", "Rushing yards", lambda b: b.get("rushingYards"), 80.0, True, "0f"),
    ("netPassingYards", "Passing yards", lambda b: b.get("netPassingYards"), 80.0, True, "0f"),
    ("firstDowns", "First downs", lambda b: b.get("firstDowns"), 6.0, True, "0f"),
]


def num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _rate(split: Any) -> float | None:
    if not isinstance(split, dict):
        return None
    made, of = whole(split.get("made")), whole(split.get("of"))
    return made / of if made is not None and of else None


def _wp(point: Any) -> float | None:
    value = num(point.get("homeWp")) if isinstance(point, dict) else None
    return value if value is not None and 0.0 <= value <= 1.0 else None


def _points(series: Any) -> list[dict[str, Any]]:
    """The usable points of a series (dicts with a probability in [0, 1]), in the order given."""
    return [p for p in series if _wp(p) is not None] if isinstance(series, list) else []


def _score(point: dict[str, Any]) -> tuple[int | None, int | None]:
    return whole(point.get("homeScore")), whole(point.get("awayScore"))


# --- GX-02 game time ----------------------------------------------------------------------------------


def text_clock(value: Any) -> dict[str, int] | None:
    """{minutes, seconds} from the "(MM:SS)" that opens a play's text, or None."""
    match = CLOCK_AT_START.match(value) if isinstance(value, str) else None
    if match is None:
        return None
    minutes, seconds = int(match.group(1)), int(match.group(2))
    return {"minutes": minutes, "seconds": seconds} if minutes <= 15 and seconds < 60 and minutes * 60 + seconds <= QUARTER_SECONDS else None


def elapsed(period: int | None, clock: dict[str, int] | None) -> int | None:
    """Seconds of regulation played at (period, clock left); None in overtime (untimed) or without either."""
    if period is None or clock is None or not 1 <= period <= 4:
        return None
    return (period - 1) * QUARTER_SECONDS + QUARTER_SECONDS - (clock["minutes"] * 60 + clock["seconds"])


def attach_game_time(series: Any) -> bool:
    """Adds period, clock and elapsedSeconds to every point in place (None where unknown) and says
    whether the series has game time. A point without a clock (a no-play penalty, a quarter end)
    keeps the last known time; a quarter end moves to the next quarter; a series whose time would run
    backwards gets None throughout."""
    points = [p for p in series if isinstance(p, dict)] if isinstance(series, list) else []
    period = 1
    last: int | None = None
    overtime = False  # a play after the 4th quarter's end
    times: list[tuple[int | None, dict[str, int] | None, int | None]] = []
    for point in points:
        words = point.get("text") if isinstance(point.get("text"), str) else ""
        end = QUARTER_END.match(words)
        if end is not None:
            quarter = QUARTERS[end.group(1).lower()]
            times.append((quarter, {"minutes": 0, "seconds": 0}, quarter * QUARTER_SECONDS))
            last = quarter * QUARTER_SECONDS
            period = quarter + 1
            continue
        if GAME_END.match(words):
            times.append((period, None, None) if overtime else (4, {"minutes": 0, "seconds": 0}, 4 * QUARTER_SECONDS))
            continue
        if period > 4:  # overtime is untimed: its plays keep their period and no game time
            overtime = True
            times.append((period, None, None))
            continue
        clock = text_clock(words)
        seconds = elapsed(period, clock) if clock is not None else last
        times.append((period, clock, seconds))
        if seconds is not None:
            last = seconds
    known = [t[2] for t in times if t[2] is not None]
    ok = bool(known) and all(b >= a - BACKWARDS_TOLERANCE for a, b in zip(known, known[1:], strict=False))
    for point, (p, c, s) in zip(points, times, strict=True):
        point["period"] = p if ok else None
        point["clock"] = c if ok else None
        point["elapsedSeconds"] = s if ok else None
    return ok


# --- GX-09 biggest swings -------------------------------------------------------------------------------


def _marker(point: dict[str, Any]) -> bool:
    words = point.get("text") if isinstance(point.get("text"), str) else ""
    return bool(QUARTER_END.match(words) or GAME_END.match(words))


def play_swings(series: Any, home_is_us: bool) -> list[dict[str, Any]]:
    """Every play's swing in our chance, in play order (see the module note on credit)."""
    points = _points(series)
    credited: dict[int, list[int]] = {}
    for i in range(1, len(points)):
        target = i if _score(points[i]) != _score(points[i - 1]) else i - 1
        if _marker(points[target]):
            continue  # a quarter's or the game's end is not a play: the change it shows is the next snap's situation
        credited.setdefault(target, []).append(i)
    rows = []
    for index, ends in sorted(credited.items()):
        start, end = ends[0] - 1, ends[-1]
        home_before, home_after = _wp(points[start]), _wp(points[end])
        play, after = points[index], points[end]
        home_score, away_score = _score(after)
        us_before = home_before if home_is_us else 1 - home_before
        us_after = home_after if home_is_us else 1 - home_after
        clock = play.get("clock") if isinstance(play.get("clock"), dict) else text_clock(play.get("text"))
        rows.append({
            "play": whole(play.get("play")),
            "text": play.get("text") if isinstance(play.get("text"), str) else None,
            "period": whole(play.get("period")),
            "clock": clock,
            "elapsedSeconds": whole(play.get("elapsedSeconds")),
            "homeScore": home_score,
            "awayScore": away_score,
            "usScore": home_score if home_is_us else away_score,
            "themScore": away_score if home_is_us else home_score,
            "homeWpBefore": round(home_before, 4),
            "homeWpAfter": round(home_after, 4),
            "usWpBefore": round(us_before, 4),
            "usWpAfter": round(us_after, 4),
            "change": round(us_after - us_before, 4),
        })
    return rows


def biggest_swings(series: Any, home_is_us: bool, limit: int = SWING_LIMIT) -> list[dict[str, Any]]:
    """The `limit` plays with the largest absolute swing, largest first, each with its rank."""
    rows = sorted(play_swings(series, home_is_us), key=lambda r: (-abs(r["change"]), r["play"] if r["play"] is not None else 10**9))
    return [{"rank": i + 1, **row} for i, row in enumerate(rows[:limit]) if row["change"] != 0]


def enrich_win_probability(block: Any, home_is_us: bool) -> None:
    """A winProbability block (analytics or archive) gains gameTime and swings; its points gain
    period, clock and elapsedSeconds. Harmless on an empty or malformed block."""
    if not isinstance(block, dict):
        return
    series = block.get("series")
    block["gameTime"] = attach_game_time(series) if isinstance(series, list) else False
    block["swings"] = biggest_swings(series, home_is_us) if isinstance(series, list) else []


# --- UX-07 postgame recap ---------------------------------------------------------------------------------


def _record_after(schedule: list[Game], game_id: int, team: str, result: str | None) -> dict[str, int] | None:
    ordered = sorted((g for g in schedule if isinstance(g, Game)), key=gamekeys.order)
    this = next((g for g in ordered if g.id == game_id), None)
    if this is None or result is None:
        return None
    wins = losses = ties = 0
    for g in ordered:
        if g.id == game_id:
            break
        home = g.home_team == team
        ours, theirs = (g.home_points, g.away_points) if home else (g.away_points, g.home_points)
        if not g.completed or whole(ours) is None or whole(theirs) is None:
            continue
        wins += ours > theirs
        losses += ours < theirs
        ties += ours == theirs
    wins += result == "W"
    losses += result == "L"
    ties += result == "T"
    return {"wins": wins, "losses": losses, "ties": ties}


def _next_game(schedule: list[Game], game_id: int, team: str) -> dict[str, Any] | None:
    ordered = sorted((g for g in schedule if isinstance(g, Game)), key=gamekeys.order)
    index = next((i for i, g in enumerate(ordered) if g.id == game_id), None)
    if index is None:
        return None
    g = next((g for g in ordered[index + 1:] if team in (g.home_team, g.away_team)), None)
    if g is None:
        return None
    home = g.home_team == team
    return {"gameId": g.id, "week": whole(g.week), "postseason": gamekeys.label(g), "date": g.start_date, "startTimeTbd": bool(g.start_time_tbd), "opponent": g.away_team if home else g.home_team, "homeAway": "neutral" if g.neutral_site else ("home" if home else "away")}


def player_of_game(advanced: Any, ppa: Any, team: str, opponent: str | None = None) -> dict[str, Any] | None:
    """The highest play value: CFBD's total PPA for the game from the advanced box score (players of
    the two teams only, so a box score of another game never names one), else the best PPA per play
    among the graded players of either side."""
    players = advanced.get("players") if isinstance(advanced, dict) else None
    sides = {team, opponent} - {None}
    best = None
    for p in players if isinstance(players, list) else []:
        value = num(p.get("totalPpa")) if isinstance(p, dict) else None
        if value is not None and isinstance(p.get("player"), str) and p.get("team") in sides and (best is None or value > best[0]):
            best = (value, p)
    if best is not None:
        p = best[1]
        return {"name": p["player"], "team": p.get("team") if isinstance(p.get("team"), str) else None, "position": p.get("position") if isinstance(p.get("position"), str) else None, "isUs": p.get("team") == team, "value": round(best[0], 1), "basis": "total play value (PPA)"}
    sides = ppa.get("players") if isinstance(ppa, dict) else None
    for side in ("us", "them"):
        for p in (sides.get(side) if isinstance(sides, dict) and isinstance(sides.get(side), list) else []):
            value = num(p.get("all")) if isinstance(p, dict) else None
            if value is not None and isinstance(p.get("name"), str) and (best is None or value > best[0]):
                best = (value, {**p, "_side": side})
    if best is None:
        return None
    p = best[1]
    return {"name": p["name"], "team": None, "position": p.get("position") if isinstance(p.get("position"), str) else None, "isUs": p["_side"] == "us", "value": round(best[0], 2), "basis": "play value per play (PPA)"}


def key_stats(box: Any, us: str, them: str | None, limit: int = 3) -> list[dict[str, Any]]:
    """The team stats with the largest gaps between the sides, each gap measured against a telling
    margin for that stat (a 10-point success-rate gap weighs like one turnover or three explosive plays)."""
    mine = box.get(us) if isinstance(box, dict) and isinstance(box.get(us), dict) else None
    theirs = box.get(them) if isinstance(box, dict) and them and isinstance(box.get(them), dict) else None
    if mine is None or theirs is None:
        return []
    rows = []
    for key, label, read, scale, higher, fmt in KEY_STATS:
        a, b = num(read(mine)), num(read(theirs))
        if a is None or b is None or a == b:
            continue
        better = a > b if higher else a < b
        rows.append({"key": key, "label": label, "format": fmt, "higherIsBetter": higher, "us": round(a, 3), "them": round(b, 3), "edge": "us" if better else "them", "weight": round(abs(a - b) / scale, 3)})
    rows.sort(key=lambda r: -r["weight"])
    return rows[:limit]


def recap(raw: Any, series: Any, *, team: str, schedule: list[Game], advanced: Any = None, ppa: Any = None) -> dict[str, Any] | None:
    """The recap card of an archived final, or None when the file is not a usable final."""
    if not isinstance(raw, dict) or not isinstance(raw.get("state"), dict) or whole(raw.get("gameId")) is None:
        return None
    state = raw["state"]
    if raw.get("partial") or str(state.get("status") or "").lower() != "final":
        return None
    home, away = raw.get("home"), raw.get("away")
    if team not in (home, away):
        return None
    home_is_us = home == team
    opponent = away if home_is_us else home
    home_score, away_score = whole(state.get("homeScore")), whole(state.get("awayScore"))
    us_score = home_score if home_is_us else away_score
    them_score = away_score if home_is_us else home_score
    result = None if us_score is None or them_score is None else "W" if us_score > them_score else "L" if us_score < them_score else "T"
    game_id = raw["gameId"]
    attach_game_time(series)  # idempotent: a series straight from the file or the cache gets its quarters and clocks
    swings = biggest_swings(series, home_is_us, 1)
    turning = swings[0] if swings else None
    return {
        "gameId": game_id,
        "opponent": opponent if isinstance(opponent, str) else None,
        "homeIsUs": home_is_us,
        "kickoff": raw.get("kickoff") if isinstance(raw.get("kickoff"), str) else None,
        "savedAt": raw.get("savedAt") if isinstance(raw.get("savedAt"), str) else None,
        "final": {"usScore": us_score, "themScore": them_score, "homeScore": home_score, "awayScore": away_score, "result": result},
        "record": _record_after(schedule, game_id, team, result),
        "turningPoint": {k: turning[k] for k in ("play", "text", "period", "clock", "usScore", "themScore", "usWpBefore", "usWpAfter", "change")} if turning else None,
        "playerOfGame": player_of_game(advanced, ppa, team, opponent if isinstance(opponent, str) else None),
        "keyStats": key_stats(state.get("box"), team, opponent if isinstance(opponent, str) else None),
        "next": _next_game(schedule, game_id, team),
    }


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def recent(raw: Any, now: datetime, window: timedelta = RECAP_WINDOW) -> bool:
    """Whether an archived final is recent enough for the Newspaper: saved (or, failing that, kicked
    off) no more than `window` before now."""
    if not isinstance(raw, dict):
        return False
    at = parse_time(raw.get("savedAt")) or parse_time(raw.get("kickoff"))
    return at is not None and timedelta(0) <= now - at <= window
