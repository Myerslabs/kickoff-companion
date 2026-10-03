"""Our own event model and the normalizers that feed it.

Two sources produce the same events: the live endpoint during a game (a LiveGame document
with drives and plays) and the finished-game endpoints for replay (flat plays and drives).
Play and drive dictionaries use the shapes the design-system components already render
(see tools/make_sample_data.py), so the live sheet and the styleguide agree.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.cfbd.models import Drive, GamePlayerStats, GameTeamStats, LiveGame, LiveGameTeam, Play, ScoreboardGame

EXPLOSIVE_RUSH = 10
EXPLOSIVE_PASS = 20
# Play types that are not a snap on a scrimmage down: kicks, tries after a touchdown, timeouts,
# penalties with no play, and the period markers. Every type in the recorded live document is
# classified by tests/test_live_state_10a.py. The rarer words (start of, PAT, 1pt, uncategorized,
# placeholder) cover types that recording does not contain; they only narrow what counts as a snap.
NON_SCRIMMAGE = re.compile(r"kickoff|punt|field goal|timeout|penalty|end of|end period|start of|extra point|\bpat\b|two.point|2pt|1pt|kick|uncategorized|placeholder", re.IGNORECASE)
TURNOVER = re.compile(r"interception|fumble recovery \(opponent\)|fumble return", re.IGNORECASE)

# The drive bar's vocabulary (static/js/ui/drive-bar.js SCORES and TURNOVERS) for the live feed's
# words. The finished-game /drives endpoint already speaks it (TD, FG, PUNT, INT...), so a code
# maps to itself and anything unlisted is only trimmed and upper-cased.
DRIVE_RESULTS = {
    "touchdown": "TD",
    "field goal": "FG",
    "field goal good": "FG",
    "missed field goal": "MISSED FG",
    "field goal missed": "MISSED FG",
    "blocked field goal": "MISSED FG",
    "missed fg": "MISSED FG",  # short forms the recording lacks but the feed may send; each lands in a drive-bar set
    "fg missed": "MISSED FG",
    "blocked fg": "MISSED FG",
    "interception": "INT",
    "interception return touchdown": "INT TD",
    "interception touchdown": "INT TD",
    "interception td": "INT TD",
    "int td": "INT TD",
    "fumble": "FUMBLE",
    "fumble lost": "FUMBLE",
    "fumble return touchdown": "FUMBLE TD",
    "fumble touchdown": "FUMBLE TD",
    "fumble return td": "FUMBLE TD",
    "fumble td": "FUMBLE TD",
    "downs": "DOWNS",
    "turnover on downs": "DOWNS",
    "punt": "PUNT",
    "end of half": "END OF HALF",
    "end of game": "END OF GAME",
    "safety": "SAFETY",
}


@dataclass
class LiveEvent:
    """One thing that happened, with the server time it was first seen."""

    id: str  # stable across polls: play:<playId>, drive:<driveId>, status
    kind: str  # play, drive, status
    game_id: int
    received_at: datetime
    data: dict[str, Any]
    version: int = 1  # bumps when upstream corrects the same id
    seq: int | None = None  # assigned by the store, in receipt order

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "gameId": self.game_id,
            "receivedAt": self.received_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "version": self.version,
            "seq": self.seq,
            "data": self.data,
        }


# --- shared helpers ------------------------------------------------------------------------------


def clock_dict(value: Any) -> dict[str, int | None] | None:
    """'14:32' or {'minutes': 14, 'seconds': 32} -> {'minutes': 14, 'seconds': 32}; junk -> None."""
    if isinstance(value, dict):
        minutes, seconds = value.get("minutes"), value.get("seconds")
        if isinstance(minutes, int) and isinstance(seconds, int):
            return {"minutes": minutes, "seconds": seconds}
        return None
    if isinstance(value, str) and ":" in value:
        a, b = value.split(":", 1)
        if a.strip().isdigit() and b.strip().isdigit():
            return {"minutes": int(a), "seconds": int(b)}
    return None


def clock_seconds(value: Any) -> int | None:
    parsed = clock_dict(value)
    return parsed["minutes"] * 60 + parsed["seconds"] if parsed else None


def key_play_flags(play_type: str | None, text: str | None, yards_gained: int | None, scoring: bool | None, down: int | None) -> list[str]:
    """The badges of L7: touchdown, turnover, explosive, sack, fourth-down try, 15-yard flag."""
    flags: list[str] = []
    ptype = (play_type or "").lower()
    body = (text or "").lower()
    gained = yards_gained if isinstance(yards_gained, int) else 0
    if scoring and "touchdown" in ptype:
        flags.append("td")
    if "interception" in ptype or "fumble recovery (opponent)" in ptype or "fumble return" in ptype:
        flags.append("turnover")
    if "sack" in ptype:
        flags.append("sack")
    if "rush" in ptype and gained >= EXPLOSIVE_RUSH:
        flags.append("explosive")
    if ("pass" in ptype or "reception" in ptype) and gained >= EXPLOSIVE_PASS:
        flags.append("explosive")
    if down == 4 and not any(word in ptype for word in ("punt", "field goal", "kickoff", "timeout", "penalty")):
        flags.append("fourth")
    if "penalty" in ptype and ("15 yard" in body):
        flags.append("penalty")
    return flags


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def play_success(down: int | None, distance: int | None, yards_gained: int | None, play_type: str | None, scoring: bool | None) -> bool | None:
    """The local rule, used only where CFBD sends no flag (finished-game replays): 50% of the
    distance on first down, 70% on second, all of it after; a turnover fails and an offensive
    touchdown succeeds. None when not judged: not a scrimmage play, or no down and distance."""
    if not is_scrimmage(play_type):
        return None
    if not isinstance(down, int) or isinstance(down, bool) or down not in (1, 2, 3, 4) or not _number(distance) or not _number(yards_gained):
        return None
    if TURNOVER.search(play_type or ""):
        return False
    if scoring and "touchdown" in (play_type or "").lower():
        return True
    needed = {1: 0.5, 2: 0.7}.get(down, 1.0) * distance
    return yards_gained >= needed


def is_scrimmage(play_type: str | None) -> bool:
    """A snap on a scrimmage down: judged for success and counted in the box. A play with no type
    is neither, since nothing says whether it was a kick, a penalty, or a snap."""
    if not isinstance(play_type, str) or not play_type.strip():
        return False
    return not NON_SCRIMMAGE.search(play_type)


def drive_result(value: Any) -> str | None:
    """A drive's result as the drive bar's code (C3): the live feed's words mapped, anything
    else trimmed and upper-cased. None for a drive still running or a result that is not text."""
    if not isinstance(value, str):
        return None
    words = " ".join(value.split())
    if not words:
        return None
    return DRIVE_RESULTS.get(words.lower(), words.upper())


def drive_result_text(value: Any) -> str | None:
    """The source's own words for the result, kept for display next to the code."""
    return value if isinstance(value, str) and value.strip() else None


def feed_success(success: Any, play_type: str | None) -> bool | None:
    """C3: CFBD's per-play success flag, only on scrimmage plays and only when it is a boolean."""
    return success if isinstance(success, bool) and is_scrimmage(play_type) else None


# --- finished game (replay) ---------------------------------------------------------------------------


def play_from_finished(play: Play, home: str | None, away: str | None) -> dict[str, Any]:
    offense = play.offense
    defense = play.defense
    home_score = play.offense_score if offense == home else play.defense_score
    away_score = play.offense_score if offense == away else play.defense_score
    flags = key_play_flags(play.play_type, play.play_text, play.yards_gained, play.scoring, play.down)
    return {
        "id": play.id,
        "driveId": play.drive_id,
        "driveNumber": play.drive_number,
        "playNumber": play.play_number,
        "period": play.period,
        "clock": clock_dict(play.clock.model_dump() if play.clock else None),
        "offense": offense,
        "defense": defense,
        "down": play.down,
        "distance": play.distance,
        "yardsToGoal": play.yards_to_goal,
        "yardsGained": play.yards_gained,
        "playType": play.play_type,
        "text": play.play_text,
        "scoring": bool(play.scoring),
        "ppa": play.ppa,
        "offenseScore": play.offense_score,
        "defenseScore": play.defense_score,
        "homeScore": home_score,
        "awayScore": away_score,
        "wallclock": play.wallclock,
        "flags": flags,
        "success": play_success(play.down, play.distance, play.yards_gained, play.play_type, play.scoring),
    }


def drive_from_finished(drive: Drive) -> dict[str, Any]:
    return {
        "id": drive.id,
        "number": drive.drive_number,
        "offense": drive.offense,
        "defense": drive.defense,
        "startYardsToGoal": drive.start_yards_to_goal,
        "endYardsToGoal": drive.end_yards_to_goal,
        "plays": drive.plays,
        "yards": drive.yards,
        "result": drive_result(drive.drive_result),
        "resultText": drive_result_text(drive.drive_result),
        "scoring": bool(drive.scoring),
        "period": drive.start_period,
        "startClock": drive.start_time.model_dump() if drive.start_time else None,
        "elapsedSeconds": clock_seconds(drive.elapsed.model_dump() if drive.elapsed else None),
        "startScore": [drive.start_offense_score, drive.start_defense_score],
        "endScore": [drive.end_offense_score, drive.end_defense_score],
    }


def status_from_scores(game_id: int, home: str | None, away: str | None, home_score: int | None, away_score: int | None, period: int | None, clock: dict[str, int | None] | None, possession: str | None, down: int | None, distance: int | None, yards_to_goal: int | None, status: str, home_line_scores: list | None = None, away_line_scores: list | None = None) -> dict[str, Any]:
    return {
        "homeLineScores": home_line_scores,
        "awayLineScores": away_line_scores,
        "gameId": game_id,
        "status": status,  # pre, in_progress, final
        "home": home,
        "away": away,
        "homeScore": home_score,
        "awayScore": away_score,
        "period": period,
        "clock": clock,
        "possession": possession,
        "down": down,
        "distance": distance,
        "yardsToGoal": yards_to_goal,
    }


# --- live endpoint ----------------------------------------------------------------------------------


def _live_status(value: str | None) -> str:
    v = (value or "").lower()
    if "final" in v or "complete" in v or v == "completed":
        return "final"
    if v in ("", "scheduled", "pre", "pregame", "not started"):
        return "pre"
    return "in_progress"


def events_from_live(game: LiveGame, received_at: datetime) -> list[LiveEvent]:
    """Every play, drive, and the status from one live document. Order: drives, plays, status."""
    teams = {t.home_away: t for t in game.teams if t.home_away}
    home = teams.get("home").team if teams.get("home") else None
    away = teams.get("away").team if teams.get("away") else None
    home_points = teams.get("home").points if teams.get("home") else None
    away_points = teams.get("away").points if teams.get("away") else None
    events: list[LiveEvent] = []
    play_number = 0
    last_scores: tuple[int | None, int | None] = (None, None)
    for index, drive in enumerate(game.drives, start=1):
        drive_data = {
            "id": drive.id,
            "number": index,
            "offense": drive.offense,
            "defense": drive.defense,
            "startYardsToGoal": drive.start_yards_to_goal,
            "endYardsToGoal": drive.end_yards_to_goal,
            "plays": drive.play_count if drive.play_count is not None else len(drive.plays),
            "yards": drive.yards,
            "result": drive_result(drive.result),
            "resultText": drive_result_text(drive.result),
            "scoring": bool(drive.points_gained),
            "scoringOpportunity": drive.scoring_opportunity,
            "pointsGained": drive.points_gained,
            "period": drive.start_period,
            "startClock": clock_dict(drive.start_clock),
            "endPeriod": drive.end_period,
            "endClock": clock_dict(drive.end_clock),
            "elapsedSeconds": clock_seconds(drive.duration),
            "startScore": None,
            "endScore": None,
            "current": False,
        }
        events.append(LiveEvent(f"drive:{drive.id}", "drive", game.id, received_at, drive_data))
        for play in drive.plays:
            play_number += 1
            offense = play.team or drive.offense
            defense = drive.defense if offense == drive.offense else drive.offense
            flags = key_play_flags(play.play_type, play.play_text, play.yards_gained, bool(play.home_score is not None and (play.home_score, play.away_score) != last_scores and "touchdown" in (play.play_type or "").lower()), play.down)
            scoring = "touchdown" in (play.play_type or "").lower() or "field goal good" in (play.play_type or "").lower()
            if play.home_score is not None:
                last_scores = (play.home_score, play.away_score)
            offense_is_home = offense == home
            events.append(
                LiveEvent(
                    f"play:{play.id}",
                    "play",
                    game.id,
                    received_at,
                    {
                        "id": play.id,
                        "driveId": drive.id,
                        "driveNumber": index,
                        "playNumber": play_number,
                        "period": play.period,
                        "clock": clock_dict(play.clock),
                        "offense": offense,
                        "defense": defense,
                        "down": play.down,
                        "distance": play.distance,
                        "yardsToGoal": play.yards_to_goal,
                        "yardsGained": play.yards_gained,
                        "playType": play.play_type,
                        "text": play.play_text,
                        "scoring": scoring,
                        "ppa": play.epa,
                        "offenseScore": play.home_score if offense_is_home else play.away_score,
                        "defenseScore": play.away_score if offense_is_home else play.home_score,
                        "homeScore": play.home_score,
                        "awayScore": play.away_score,
                        "wallclock": play.wall_clock,
                        "flags": flags,
                        "success": feed_success(play.success, play.play_type),  # CFBD's own flag (C3); no local fallback on the live feed
                        "garbageTime": play.garbage_time,
                        "rushPass": play.rush_pass,  # the feed's own tags (Phase 12 tendencies)
                        "downType": play.down_type,
                    },
                )
            )
    status = status_from_scores(game.id, home, away, home_points, away_points, game.period, clock_dict(game.clock), game.possession, game.down, game.distance, game.yards_to_goal, _live_status(game.status), teams.get("home").line_scores if teams.get("home") else None, teams.get("away").line_scores if teams.get("away") else None)
    status["teams"] = {t.team: feed_efficiency(t) for t in game.teams if t.team}  # the feed's own per-team block, verified on Tier 2 2026-09-23
    events.append(LiveEvent("status", "status", game.id, received_at, status))
    return events


EFFICIENCY_FIELDS = (
    ("successRate", "success_rate"),
    ("standardDownSuccessRate", "standard_down_success_rate"),
    ("passingDownSuccessRate", "passing_down_success_rate"),
    ("epaPerPlay", "epa_per_play"),
    ("epaPerPass", "epa_per_pass"),
    ("epaPerRush", "epa_per_rush"),
    ("totalEpa", "total_epa"),
    ("explosiveness", "explosiveness"),
    ("pointsPerOpportunity", "points_per_opportunity"),
    ("scoringOpportunities", "scoring_opportunities"),
    ("lineYardsPerRush", "line_yards_per_rush"),
    ("averageStartYardLine", "average_start_yard_line"),
    ("plays", "plays"),
    ("drives", "drives"),
    ("deserveToWin", "deserve_to_win"),
)


def feed_efficiency(team: LiveGameTeam) -> dict[str, float | int | None]:
    """The numbers the live document carries per team, camelCased for the browser; None where absent."""
    out: dict[str, float | int | None] = {}
    for key, attr in EFFICIENCY_FIELDS:
        value = getattr(team, attr, None)
        out[key] = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return out


def events_from_finished(game_id: int, plays: list[Play], drives: list[Drive], home: str | None, away: str | None) -> list[tuple[LiveEvent, str | None]]:
    """Plays and drives of a finished game in game order, each with its wall clock for replay pacing.
    The received_at is a placeholder the replay engine overwrites as it emits."""
    placeholder = datetime.fromtimestamp(0, tz=__import__("datetime").timezone.utc)
    ordered = sorted(plays, key=lambda p: (p.period or 0, -(clock_seconds(p.clock.model_dump() if p.clock else None) or 0), p.play_number or 0))
    drive_by_id = {d.id: d for d in drives}
    seen_drives: set[str] = set()
    out: list[tuple[LiveEvent, str | None]] = []
    for play in ordered:
        if play.drive_id and play.drive_id not in seen_drives and play.drive_id in drive_by_id:
            seen_drives.add(play.drive_id)
            data = drive_from_finished(drive_by_id[play.drive_id])
            data["current"] = True
            out.append((LiveEvent(f"drive:{play.drive_id}", "drive", game_id, placeholder, data), play.wallclock))
        out.append((LiveEvent(f"play:{play.id}", "play", game_id, placeholder, play_from_finished(play, home, away)), play.wallclock))
    return out


# --- box score and player stats (polled every few minutes inside the window) ----------------------


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


def _split(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, str) and "-" in value:
        a, b = value.split("-", 1)
        if a.strip().isdigit() and b.strip().isdigit():
            return int(a), int(b)
    return None, None


def box_events(game_id: int, teams: list[GameTeamStats], players: list[GamePlayerStats], received_at: datetime) -> list[LiveEvent]:
    """A 'box' event (team stats per side, the styleguide's box shape) and a 'players' event
    (category tables per side) from the two box-score payloads. Missing payloads make no event."""
    out: list[LiveEvent] = []
    box = next((b for b in teams if b.id == game_id), None)
    if box is not None:
        sides: dict[str, Any] = {}
        for side in box.teams:
            stats = {s.category: s.stat for s in side.stats}
            third, fourth, pens = _split(stats.get("thirdDownEff")), _split(stats.get("fourthDownEff")), _split(stats.get("totalPenaltiesYards"))
            sides[side.team or ""] = {
                "team": side.team,
                "homeAway": side.home_away,
                "points": side.points,
                "totalYards": _num(stats.get("totalYards")),
                "netPassingYards": _num(stats.get("netPassingYards")),
                "rushingYards": _num(stats.get("rushingYards")),
                "firstDowns": _num(stats.get("firstDowns")),
                "thirdDown": {"made": third[0], "of": third[1]},
                "fourthDown": {"made": fourth[0], "of": fourth[1]},
                "turnovers": _num(stats.get("turnovers")),
                "penalties": {"count": pens[0], "yards": pens[1]},
                "possessionTime": stats.get("possessionTime"),
                "raw": {k: (v if isinstance(v, str) else _num(v)) for k, v in stats.items()},
            }
        out.append(LiveEvent("box", "box", game_id, received_at, {"sides": sides}))
    pbox = next((b for b in players if b.id == game_id), None)
    if pbox is not None:
        teams_out: dict[str, Any] = {}
        for side in pbox.teams:
            categories: dict[str, list[dict[str, Any]]] = {}
            for category in side.categories:
                rows: dict[str, dict[str, Any]] = {}
                for stat_type in category.types:
                    for athlete in stat_type.athletes:
                        row = rows.setdefault(athlete.id, {"playerId": athlete.id, "name": athlete.name, "stats": {}})
                        value = athlete.stat
                        row["stats"][stat_type.name] = _num(value) if _num(value) is not None and "/" not in str(value) else value
                categories[category.name] = list(rows.values())
            teams_out[side.team or ""] = categories
        out.append(LiveEvent("players", "players", game_id, received_at, {"teams": teams_out}))
    return out


# --- in-game win probability (L8, Phase 11) ------------------------------------------------------


def _probability(value: Any) -> float | None:
    number = _num(value)
    return number if number is not None and math.isfinite(number) and 0.0 <= number <= 1.0 else None


def wp_event(game: ScoreboardGame, received_at: datetime) -> LiveEvent | None:
    """One reading of CFBD's in-game win probability from its /scoreboard entry for the game
    (homeTeam.winProbability and awayTeam.winProbability, verified on the Texas at Tennessee
    recording 2026-09-26). Keyed by period and clock, so the same moment read twice is one event
    and a changed number is a correction. None before kickoff, after the final, or without a
    usable number."""
    if str(game.status or "").lower() != "in_progress":
        return None
    home = _probability(game.home_team.win_probability) if game.home_team else None
    away = _probability(game.away_team.win_probability) if game.away_team else None
    if home is None and away is not None:
        home = 1.0 - away
    if home is None:
        return None
    period = game.period if isinstance(game.period, int) and not isinstance(game.period, bool) else None
    clock = clock_dict(game.clock)
    key = f"wp:{period if period is not None else '-'}:{clock_seconds(game.clock) if clock else '-'}"
    data = {
        "homeWp": round(home, 4),
        "period": period,
        "clock": clock,
        "homeScore": game.home_team.points if game.home_team else None,
        "awayScore": game.away_team.points if game.away_team else None,
    }
    return LiveEvent(key, "wp", game.id, received_at, data)
