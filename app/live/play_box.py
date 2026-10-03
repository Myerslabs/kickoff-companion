"""Team box-score numbers worked out from the play-by-play (hotfix 2026-09-26, found at halftime
of the 2026-09-26 game). CFBD's /games/teams answer stays empty while a game is on (28 empty answers that
night), so the Team stats rows that read only the box score showed dashes all game: pass and rush
yards, completions and attempts, touchdowns by kind, first downs, fumbles lost, interceptions
thrown, sacks, tackles for loss and time of possession. These fill the same fields, in the box
score's own shapes, until the box score posts; the box score's numbers replace them field by field
(the Live sheet's mergedBox).

Rules, from the NCAA scoring the box score follows: a sack is a rush for the quarterback, never a
pass attempt; a pass attempt is a completion, an incompletion or an interception; a completion's
yards are passing yards; a play the officials wiped out ("NO PLAY") counts for nothing, except its
first down. First downs are the plays whose text says 1ST DOWN, a penalty's included (a NO PLAY
still moves the chains); on a penalty the first down goes to the team that was not penalized. On
that game (2026-09-26) that gave 26 and 23 against the official 27 and 25: the feed does not mark
every one. Time of possession is the drives' own durations plus the seconds between drives (a
kickoff or a punt return, up to two minutes) for the team that got the ball, each drive measured by its start and end clocks: 36:53 and 22:55
against the official 36:59 and 23:01, where the durations alone gave 36:27 and 22:37. Sacks and
tackles for loss are credited to the defense. Penalty yards are left to the box score."""

from __future__ import annotations

import re
from typing import Any

PASS_COMPLETE = ("pass reception", "passing touchdown", "pass completion")
PASS_INCOMPLETE = ("pass incompletion",)
INTERCEPTION = ("interception",)  # "Interception", "Pass Interception Return", "Interception Return Touchdown"
FUMBLE_LOST = ("fumble recovery (opponent)", "fumble return touchdown")


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _is(kind: str, names: tuple[str, ...]) -> bool:
    return any(name in kind for name in names)


def _clock(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


MAX_GAP_SECONDS = 120  # between drives: a kickoff or a return, not a halftime


def _subsequence(abbr: str, name: str) -> bool:
    """"MICH" in "Michigan", "OSU" in "Ohio State", "TENN" in "Tennessee": the letters in order."""
    letters = iter(name.lower().replace(" ", ""))
    return bool(abbr) and all(ch in letters for ch in abbr.lower())


def first_down_team(text: str, offense: str, teams: list[str]) -> str:
    """Who a 1ST DOWN belongs to: the offense, or on a penalty the team that was not penalized."""
    upper = text.upper()
    match = re.search(r"PENALTY\s+([A-Z][A-Z&.]*)", upper)
    if match is None or upper.find("1ST DOWN") < match.start() or len(teams) != 2:
        return offense
    hits = [t for t in teams if _subsequence(match.group(1).rstrip("."), t)]
    if len(hits) != 1:
        return offense
    return teams[1] if hits[0] == teams[0] else teams[0]


def _game_second(period: Any, clock: Any) -> int | None:
    """Seconds since kickoff at a period and a {minutes, seconds} clock (overtime has no clock: None)."""
    if not isinstance(period, int) or isinstance(period, bool) or not 1 <= period <= 4 or not isinstance(clock, dict):
        return None
    minutes, seconds = clock.get("minutes"), clock.get("seconds")
    if not isinstance(minutes, int) or not isinstance(seconds, int):
        return None
    return (period - 1) * 900 + 900 - (minutes * 60 + seconds)


def play_box(plays: list[dict[str, Any]], drives: list[dict[str, Any]], teams: tuple[str | None, str | None]) -> dict[str, dict[str, Any]]:
    """{team: {netPassingYards, rushingYards, firstDowns, possessionTime, raw: {...}}} for the two teams."""
    sides = [t for t in teams if t]
    t = {s: {"comp": 0, "att": 0, "pass_yds": 0, "pass_td": 0, "rush": 0, "rush_yds": 0, "rush_td": 0, "firsts": 0, "ints": 0, "fumbles": 0, "sacks": 0, "tfl": 0} for s in sides}
    for play in plays:
        if not isinstance(play, dict):
            continue
        offense, defense = play.get("offense"), play.get("defense")
        if offense not in t:
            continue
        text = play.get("text") if isinstance(play.get("text"), str) else ""
        if "1ST DOWN" in text.upper():
            gainer = first_down_team(text, offense, sides)
            if gainer in t:
                t[gainer]["firsts"] += 1
        if "NO PLAY" in text.upper():
            continue
        kind = str(play.get("playType") or "").lower()
        if "fumble" in kind:
            # A fumble play is typed by its recovery ("Fumble Recovery (Own)"); what the snap was is
            # in the text. 2026-09-26: a run and a sack typed so were missed, leaving 2 carries and 7 yards out.
            lower = text.lower()
            kind = f"{kind} sack" if " sacked " in lower else f"{kind} rush" if " rush " in lower else kind
        gained = _int(play.get("yardsGained")) or 0
        o = t[offense]
        d = t.get(defense) if defense in t and defense != offense else None
        if _is(kind, PASS_COMPLETE):
            o["comp"] += 1
            o["att"] += 1
            o["pass_yds"] += gained
            o["pass_td"] += "touchdown" in kind
        elif _is(kind, PASS_INCOMPLETE):
            o["att"] += 1
        elif _is(kind, INTERCEPTION):
            o["att"] += 1
            o["ints"] += 1
        elif "sack" in kind:
            o["rush"] += 1
            o["rush_yds"] += gained
            if d is not None:
                d["sacks"] += 1
                d["tfl"] += 1
        elif "rush" in kind:
            o["rush"] += 1
            o["rush_yds"] += gained
            o["rush_td"] += "touchdown" in kind
            if gained < 0 and d is not None:
                d["tfl"] += 1
        if _is(kind, FUMBLE_LOST):
            o["fumbles"] += 1
    held = {s: 0 for s in sides}
    timed = {s: False for s in sides}
    previous_end: int | None = None
    ordered = sorted((d for d in drives if isinstance(d, dict)), key=lambda d: _int(d.get("number")) or 0)
    for drive in ordered:
        start = _game_second(drive.get("period"), drive.get("startClock"))
        end = _game_second(drive.get("endPeriod"), drive.get("endClock"))
        seconds = end - start if start is not None and end is not None and end >= start else _int(drive.get("elapsedSeconds"))
        if end is None and start is not None and seconds is not None and seconds >= 0:
            end = start + seconds  # a drive without its end clock (older stored events)
        if drive.get("offense") in held and seconds is not None and seconds >= 0:
            held[drive["offense"]] += seconds
            timed[drive["offense"]] = True
            if start is not None and previous_end is not None and 0 < start - previous_end <= MAX_GAP_SECONDS:
                held[drive["offense"]] += start - previous_end  # the kickoff or return that gave it the ball
        previous_end = end
    out: dict[str, dict[str, Any]] = {}
    for side, c in t.items():
        out[side] = {
            "netPassingYards": c["pass_yds"],
            "rushingYards": c["rush_yds"],
            "firstDowns": c["firsts"],
            "possessionTime": _clock(held[side]) if timed[side] else None,
            "raw": {
                "completionAttempts": f"{c['comp']}-{c['att']}",
                "yardsPerPass": round(c["pass_yds"] / c["att"], 1) if c["att"] else None,
                "passingTDs": c["pass_td"],
                "rushingAttempts": c["rush"],
                "yardsPerRushAttempt": round(c["rush_yds"] / c["rush"], 1) if c["rush"] else None,
                "rushingTDs": c["rush_td"],
                "passesIntercepted": c["ints"],
                "fumblesLost": c["fumbles"],
                "sacks": c["sacks"],
                "tacklesForLoss": c["tfl"],
                "source": "plays",
            },
        }
    return out
