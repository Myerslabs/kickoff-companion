"""The live state a browser renders, derived from released events only. Applied in receipt
order so a correction replaces the earlier version of the same play or drive. Situational
figures (L4) and the last-play success (L13) are computed here so every panel agrees.

Success is CFBD's own data (owner decision 2026-09-23, contract C3): a team's rate is the live
feed's successRate for that team, and a play's verdict is CFBD's per-play flag on scrimmage
plays. A replay of a finished game has no feed block, so its team rate is None; its plays carry
the local rule from events.play_success. Drive results arrive as the drive bar's codes and are
re-coded here too, so events stored by any earlier version read the same way."""

from __future__ import annotations

import math
import re
from typing import Any

from app.live.analysis import drive_summary, fourth_down, quarter_splits, shot_chart, tendencies
from app.live.events import LiveEvent, drive_result, drive_result_text, is_scrimmage
from app.live.play_box import _subsequence, play_box
from app.live.play_leaders import play_player_lines

RED_ZONE_YARDS = 20
RED_ZONE_SCORES = frozenset({"TD", "FG", "RUSHING TD", "PASSING TD"})  # offensive scores; the last two are drive-bar synonyms of TD


def _empty_box(team: str | None) -> dict[str, Any]:
    return {
        "team": team,
        "plays": 0,
        "totalYards": 0,
        "yardsPerPlay": None,
        "thirdDown": {"made": 0, "of": 0},
        "fourthDown": {"made": 0, "of": 0},
        "redZone": {"scores": 0, "trips": 0},
        "turnovers": 0,
        "penalties": {"count": 0, "yards": None},
        "sacks": 0,
        "explosive": {"twenty": 0, "forty": 0},
        "successCounts": None,  # C3: the rate is CFBD's, so there is no local count behind it
        "successRate": None,
        "points": None,
        "drives": 0,
    }


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _share(value: Any) -> float | None:
    """A rate from the feed as a number between 0 and 1; text, booleans, NaN, and anything out of
    range are None, so the sheet shows a dash rather than a wrong percentage."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if 0 <= value <= 1 else None


def _feed_rate(block: Any, counted_plays: int) -> float | None:
    """A team's success rate from its feed block, only once that team has run a play. The feed's own
    play count decides when it is a number; otherwise the box's count does. A block that says 0
    plays, as a live document may before the first snap, gives None, so the sheet shows a dash
    rather than 0.0%."""
    if not isinstance(block, dict):
        return None
    feed_plays = block.get("plays")
    if isinstance(feed_plays, (int, float)) and not isinstance(feed_plays, bool) and math.isfinite(feed_plays):
        played = feed_plays > 0
    else:
        played = counted_plays > 0
    return _share(block.get("successRate")) if played else None


def _play_key(play: dict[str, Any]) -> tuple[int, int, int]:
    """Game order: period, then the clock running down, then the feed's sequence number."""
    clock = play.get("clock")
    left = (_int(clock.get("minutes")) or 0) * 60 + (_int(clock.get("seconds")) or 0) if isinstance(clock, dict) else 0
    return (_int(play.get("period")) or 0, -left, _int(play.get("playNumber")) or 0)


def _judged(play: dict[str, Any]) -> dict[str, Any]:
    """The play with success only as a boolean and only on a scrimmage play (C3)."""
    success = play.get("success")
    clean = success if isinstance(success, bool) and is_scrimmage(play.get("playType")) else None
    return play if clean is success else {**play, "success": clean}


def _coded(drive: dict[str, Any]) -> dict[str, Any]:
    """The drive with its result as the drive bar's code and the source's words beside it."""
    raw = drive.get("result")
    text = drive.get("resultText")
    return {**drive, "result": drive_result(raw), "resultText": text if isinstance(text, str) and text.strip() else drive_result_text(raw)}


def _inside_twenty(yards_to_goal: Any) -> bool:
    value = _int(yards_to_goal)
    return value is not None and 0 <= value <= RED_ZONE_YARDS


def _red_zone_trip(drive: dict[str, Any], drive_plays: list[dict[str, Any]]) -> bool:
    """C3: the drive's offense ran a scrimmage play at the opponent's 20 or closer. A drive with no
    plays in the log yet falls back to where it ended. Drives the clock ended do not count."""
    if str(drive.get("result") or "").startswith("END OF"):  # END OF HALF, END OF GAME
        return False
    offense = drive.get("offense")
    if drive_plays:
        return any(is_scrimmage(p.get("playType")) and p.get("offense") in (offense, None) and _inside_twenty(p.get("yardsToGoal")) for p in drive_plays)
    return _inside_twenty(drive.get("endYardsToGoal"))


def _has_lines(categories: Any) -> bool:
    return isinstance(categories, dict) and any(isinstance(rows, list) and rows for rows in categories.values())


def _player_stats(box_teams: Any, plays: list[dict[str, Any]], sides: tuple[str | None, str | None], rosters: Any = None) -> dict[str, Any]:
    """Player lines per team: the box score's once it has any for that team, else the lines worked
    out from the play-by-play (Phase 11: the box endpoints stay empty while a game is on)."""
    box = box_teams if isinstance(box_teams, dict) else {}
    derived = play_player_lines(plays, rosters if isinstance(rosters, dict) else None) if any(not _has_lines(box.get(t)) for t in sides if t) else {}
    teams: dict[str, Any] = {}
    source: dict[str, str] = {}
    for team in {*box.keys(), *derived.keys()}:
        if _has_lines(box.get(team)):
            teams[team], source[team] = box[team], "box"
        elif _has_lines(derived.get(team)):
            teams[team], source[team] = derived[team], "plays"
    return {"playerStats": teams or None, "playerStatsSource": source}


def _live_wp(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """CFBD's in-game win probability as released so far: the readings in game order and the newest."""
    if not points:
        return None
    ordered = sorted(points, key=lambda p: (p["period"] or 0, -((_int((p["clock"] or {}).get("minutes")) or 0) * 60 + (_int((p["clock"] or {}).get("seconds")) or 0))))
    return {"source": "CFBD scoreboard", "homeWp": points[-1]["homeWp"], "series": ordered}



_PENALTY_TEAM = re.compile(r"PENALTY\s+([A-Z][A-Z&.]*)")


def _penalized_team(text: Any, boxes: dict[str, Any]) -> str | None:
    """The team a PENALTY in the play text names ("PENALTY AUB Pass Interference ..."), as the box key, or None
    when the text names neither team clearly (then the flag is not counted: a wrong count is worse than none)."""
    if not isinstance(text, str):
        return None
    match = _PENALTY_TEAM.search(text.upper())
    if match is None:
        return None
    token = match.group(1).rstrip(".")
    hits = [name for name in boxes if name and _subsequence(token, name)]
    return hits[0] if len(hits) == 1 else None

def derive_state(events: list[LiveEvent], *, game_id: int, home: str | None, away: str | None, mode: str = "live", rosters: Any = None, ep_tables: Any = None) -> dict[str, Any]:
    """Fold the events into plays, drives, a status line, and per-team situational stats.
    `rosters` (app.live.play_leaders.Rosters) names the players in lines taken from the play-by-play.
    `ep_tables` ({"firstDown": {yardLine: points}, "fieldGoal": {yardsToGoal: make chance}}) gives
    the fourth-down break-even when the released status is a 4th down."""
    plays: dict[str, dict[str, Any]] = {}
    drives: dict[str, dict[str, Any]] = {}
    status: dict[str, Any] | None = None
    box_event: dict[str, Any] | None = None
    players_event: dict[str, Any] | None = None
    order: list[str] = []
    wp_points: dict[str, dict[str, Any]] = {}  # in-game win probability readings, in receipt order
    for event in events:
        if not isinstance(event.data, dict):
            continue
        if event.kind == "play":
            if event.id not in plays:
                order.append(event.id)
            plays[event.id] = _judged(event.data)
        elif event.kind == "drive":
            drives[event.id] = _coded(event.data)
        elif event.kind == "status":
            status = event.data
        elif event.kind == "box":
            box_event = event.data
        elif event.kind == "players":
            players_event = event.data
        elif event.kind == "wp":
            wp = _share(event.data.get("homeWp"))
            if wp is not None:
                wp_points.pop(event.id, None)  # a correction moves to where it was received
                wp_points[event.id] = {"homeWp": wp, "period": _int(event.data.get("period")), "clock": event.data.get("clock") if isinstance(event.data.get("clock"), dict) else None}

    ordered_plays = sorted((plays[i] for i in order), key=_play_key)
    last = ordered_plays[-1] if ordered_plays else None

    home_score = status.get("homeScore") if status else None
    away_score = status.get("awayScore") if status else None
    if last is not None:
        if home_score is None and last.get("homeScore") is not None:
            home_score = last.get("homeScore")
        if away_score is None and last.get("awayScore") is not None:
            away_score = last.get("awayScore")

    boxes = {name: _empty_box(name) for name in (home, away) if name}
    plays_by_drive: dict[str, list[dict[str, Any]]] = {}
    for play in ordered_plays:
        if play.get("driveId") is not None:
            plays_by_drive.setdefault(str(play["driveId"]), []).append(play)
        offense, defense = play.get("offense"), play.get("defense")
        box = boxes.get(offense) if offense in boxes else None
        ptype = play.get("playType") if isinstance(play.get("playType"), str) else ""
        gained = _int(play.get("yardsGained")) or 0
        distance = _int(play.get("distance"))
        flags = play.get("flags") if isinstance(play.get("flags"), list) else []
        if box is not None and is_scrimmage(ptype):
            box["plays"] += 1
            box["totalYards"] += gained
            if play.get("down") == 3:
                box["thirdDown"]["of"] += 1
                if play.get("scoring") or (distance is not None and gained >= distance):
                    box["thirdDown"]["made"] += 1
            if play.get("down") == 4:
                box["fourthDown"]["of"] += 1
                if play.get("scoring") or (distance is not None and gained >= distance):
                    box["fourthDown"]["made"] += 1
            if "turnover" in flags:
                box["turnovers"] += 1
            if gained >= 20:
                box["explosive"]["twenty"] += 1
            if gained >= 40:
                box["explosive"]["forty"] += 1
        if "penalty" in ptype.lower():
            flagged = _penalized_team(play.get("text"), boxes)  # final pass: the flagged team, not the team with the ball
            if flagged is not None:
                boxes[flagged]["penalties"]["count"] += 1
        if "sack" in flags and defense in boxes:
            boxes[defense]["sacks"] += 1
    feed = (status or {}).get("teams")
    for name, box in boxes.items():
        box["yardsPerPlay"] = round(box["totalYards"] / box["plays"], 2) if box["plays"] else None
        block = feed.get(name) if isinstance(feed, dict) else None
        box["successRate"] = _feed_rate(block, box["plays"])
        box["points"] = home_score if name == home else away_score
    drive_list = sorted(drives.values(), key=lambda d: (_int(d.get("number")) or 0, str(d.get("id") or "")))
    for drive in drive_list:
        team = drive.get("offense")
        if team not in boxes:
            continue
        boxes[team]["drives"] += 1
        if _red_zone_trip(drive, plays_by_drive.get(str(drive.get("id")), [])):
            boxes[team]["redZone"]["trips"] += 1
            if drive.get("result") in RED_ZONE_SCORES:
                boxes[team]["redZone"]["scores"] += 1
    # The box score's own fields from the play-by-play, until CFBD posts the box score (hotfix 2026-09-26).
    for name, extra in play_box(ordered_plays, drive_list, (home, away)).items():
        if name in boxes:
            boxes[name].update(extra)
    current_drive = next((d for d in reversed(drive_list) if d.get("current") or not d.get("result")), drive_list[-1] if drive_list else None)
    drive_list = [dict(d) for d in drive_list]  # drive_summary adds per-drive success and EPA to these copies
    sides = (home, away)
    summary = drive_summary(drive_list, plays_by_drive, sides)
    tables = ep_tables if isinstance(ep_tables, dict) else {}
    fourth = fourth_down((status or {}).get("down"), (status or {}).get("distance"), (status or {}).get("yardsToGoal"), tables.get("firstDown") or {}, tables.get("fieldGoal") or {}) if (status or {}).get("status", "in_progress") == "in_progress" else None

    newest_first = list(reversed(ordered_plays))
    last_judged = next((p for p in newest_first if isinstance(p.get("success"), bool)), None)
    return {
        "gameId": game_id,
        "mode": mode,
        "status": (status or {}).get("status", "in_progress" if ordered_plays else "pre"),
        "home": home,
        "away": away,
        "homeScore": home_score,
        "awayScore": away_score,
        "period": (status or {}).get("period", last.get("period") if last else None),
        "clock": (status or {}).get("clock", last.get("clock") if last else None),
        "possession": (status or {}).get("possession", last.get("offense") if last else None),
        "down": (status or {}).get("down"),
        "distance": (status or {}).get("distance"),
        "yardsToGoal": (status or {}).get("yardsToGoal"),
        "homeLineScores": (status or {}).get("homeLineScores"),
        "awayLineScores": (status or {}).get("awayLineScores"),
        "boxScore": (box_event or {}).get("sides"),
        "feedStats": feed,  # the live feed's own efficiency block per team (Tier 2, verified 2026-09-23)
        **_player_stats((players_event or {}).get("teams"), ordered_plays, (home, away), rosters),
        "liveWinProbability": _live_wp(list(wp_points.values())),
        "plays": newest_first,
        "drives": drive_list,
        "splits": quarter_splits(ordered_plays, sides),
        "tendencies": tendencies(ordered_plays, sides),
        "shotChart": shot_chart(ordered_plays, sides),  # public release Phase 7b: pass zones and run lanes, released plays only
        "driveSummary": summary,
        "fourthDown": fourth,
        "currentDriveId": current_drive.get("id") if current_drive else None,
        "box": boxes,
        "lastPlay": last_judged,
        "counts": {"plays": len(ordered_plays), "drives": len(drive_list), "events": len(events)},
        "lastSeq": max((e.seq or 0 for e in events), default=0),
    }
