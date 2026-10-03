"""The box score's fields from the play-by-play while CFBD's box score is empty (hotfix
2026-09-26): pass and rush splits, first downs, turnovers by kind, sacks and tackles for loss for
the defense, time of possession; the box score still wins once it posts."""

from __future__ import annotations

from datetime import datetime, timezone

from app.cfbd.models import LiveGame, parse_one
from app.live.events import LiveEvent, events_from_live
from app.live.play_box import first_down_team, play_box
from app.live.state import derive_state
from tests.conftest import fixture_payload

SEEN = datetime(2026, 9, 26, 21, 0, tzinfo=timezone.utc)


def play(offense: str, kind: str, gained: int, text: str = "") -> dict:
    return {"offense": offense, "defense": "B" if offense == "A" else "A", "playType": kind, "yardsGained": gained, "text": text}


def test_play_box_counts_by_the_ncaa_rules():
    plays = [
        play("A", "Pass Reception", 12, "#1 X pass complete to #2 Y for 12 yards, 1ST DOWN"),
        play("A", "Passing Touchdown", 30, "#1 X pass complete to #3 Z for 30 yards TOUCHDOWN"),
        play("A", "Pass Incompletion", 0),
        play("A", "Interception", 0),
        play("A", "Sack", -7),
        play("A", "Rush", 5),
        play("A", "Rush", -2),
        play("A", "Rushing Touchdown", 3, "#4 R rush for 3 yards TOUCHDOWN"),
        play("A", "Fumble Recovery (Opponent)", 1),
        play("A", "Rush", 40, "#4 R rush for 40 yards PENALTY B Holding 10 yards. NO PLAY"),
        play("A", "Penalty", 15, "PENALTY B Pass Interference 15 yards, 1ST DOWN"),
        play("C", "Rush", 9),
        None,
        {"offense": "A", "playType": None, "yardsGained": "x", "text": None},
    ]
    drives = [{"offense": "A", "elapsedSeconds": 150}, {"offense": "A", "elapsedSeconds": 95}, {"offense": "B", "elapsedSeconds": None}, "junk"]
    out = play_box(plays, drives, ("A", "B"))  # type: ignore[arg-type]
    a, b = out["A"], out["B"]
    assert a["netPassingYards"] == 42 and a["rushingYards"] == -1 and a["firstDowns"] == 2 and a["possessionTime"] == "4:05"
    assert a["raw"] == {"completionAttempts": "2-4", "yardsPerPass": 10.5, "passingTDs": 1, "rushingAttempts": 4, "yardsPerRushAttempt": -0.2, "rushingTDs": 1, "passesIntercepted": 1, "fumblesLost": 1, "sacks": 0, "tacklesForLoss": 0, "source": "plays"}
    assert b["raw"]["sacks"] == 1 and b["raw"]["tacklesForLoss"] == 2 and b["possessionTime"] is None
    assert b["raw"]["completionAttempts"] == "0-0" and b["raw"]["yardsPerPass"] is None
    assert play_box([], [], (None, None)) == {}


def test_the_recorded_game_fills_every_team_stats_row():
    game = parse_one(LiveGame, fixture_payload("live_plays"), context="t")
    assert game is not None
    state = derive_state(events_from_live(game, SEEN), game_id=game.id, home="Silver Dollar", away="Swampwater Tech")
    for team in ("Silver Dollar", "Swampwater Tech"):
        box = state["box"][team]
        assert box["netPassingYards"] + box["rushingYards"] >= box["totalYards"] - 20  # the same snaps, give or take odd plays
        comp, att = (int(x) for x in box["raw"]["completionAttempts"].split("-"))
        assert 0 < comp <= att and box["firstDowns"] > 10 and box["possessionTime"]
        for key in ("yardsPerPass", "passingTDs", "rushingAttempts", "yardsPerRushAttempt", "rushingTDs", "passesIntercepted", "fumblesLost", "sacks", "tacklesForLoss"):
            assert box["raw"][key] is not None, key


def test_the_box_score_still_arrives_separately():
    """The derived fields live in state.box; the box score stays in state.boxScore, and the Live sheet lets it win."""
    events = [LiveEvent("play:1", "play", 1, SEEN, {"id": "1", "period": 1, "offense": "A", "defense": "B", "playType": "Rush", "yardsGained": 4, "text": "rush"})]
    box = LiveEvent("box", "box", 1, SEEN, {"sides": {"A": {"rushingYards": 99}}})
    state = derive_state([*events, box], game_id=1, home="A", away="B")
    assert state["box"]["A"]["rushingYards"] == 4 and state["boxScore"]["A"]["rushingYards"] == 99


def test_fumble_plays_count_as_the_snap_they_were():
    """Diner Tech 2026-09-26: a run and a sack typed "Fumble Recovery (Own)" were missed (2 carries, 7 yards)."""
    plays = [
        play("A", "Fumble Recovery (Own)", -4, "#26 J.Lindsey rush middle for 4 yards loss to the OLE31 fumbled by #26 J.Lindsey recovered by OLE"),
        play("A", "Fumble Recovery (Own)", -3, "#6 T.Webb sacked for loss of 3 yards to the FLA43, fumble by #6 T.Webb recovered by OLE"),
        play("A", "Fumble Recovery (Opponent)", 2, "#4 R rush for 2 yards fumbled recovered by B"),
        play("A", "Fumble Recovery (Own)", 0, "Aborted snap, fumble recovered by A"),
    ]
    a, b = play_box(plays, [], ("A", "B"))["A"], play_box(plays, [], ("A", "B"))["B"]
    assert a["rushingYards"] == -5 and a["raw"]["rushingAttempts"] == 3 and a["raw"]["fumblesLost"] == 1
    assert b["raw"]["sacks"] == 1 and b["raw"]["tacklesForLoss"] == 2


def test_a_penalty_first_down_goes_to_the_team_not_penalized():
    teams = ["Swampwater Tech", "Diner Tech"]
    assert first_down_team("#1 X rush for 12 yards, 1ST DOWN", "Swampwater Tech", teams) == "Swampwater Tech"
    assert first_down_team("PENALTY DINR Pass Interference 15 yards, 1ST DOWN. NO PLAY", "Diner Tech", teams) == "Swampwater Tech"
    assert first_down_team("PENALTY SWT Roughing The Passer 15 yards, 1ST DOWN", "Swampwater Tech", teams) == "Diner Tech"
    assert first_down_team("#1 X rush for 12 yards, 1ST DOWN, PENALTY DINR Holding declined", "Swampwater Tech", teams) == "Swampwater Tech"  # the first down came first
    assert first_down_team("PENALTY ZZZ Holding 10 yards, 1ST DOWN", "Swampwater Tech", teams) == "Swampwater Tech"  # unknown team: the offense
    assert first_down_team("PENALTY DINR Holding, 1ST DOWN", "Swampwater Tech", ["Swampwater Tech"]) == "Swampwater Tech"


def test_possession_adds_the_seconds_between_drives_to_the_team_that_got_the_ball():
    drives = [
        {"number": 1, "offense": "A", "period": 1, "startClock": {"minutes": 14, "seconds": 52}, "endPeriod": 1, "endClock": {"minutes": 10, "seconds": 53}, "elapsedSeconds": 230},
        {"number": 2, "offense": "B", "period": 1, "startClock": {"minutes": 10, "seconds": 45}, "endPeriod": 1, "endClock": {"minutes": 9, "seconds": 16}, "elapsedSeconds": 90},
        {"number": 3, "offense": "A", "period": 3, "startClock": {"minutes": 14, "seconds": 56}, "endPeriod": None, "endClock": None, "elapsedSeconds": 60},  # after halftime: no gap credited
        {"number": 4, "offense": "B", "period": 5, "startClock": None, "elapsedSeconds": None},  # overtime has no clock
    ]
    out = play_box([], drives, ("A", "B"))
    assert out["A"]["possessionTime"] == "4:59"  # 3:59 + 1:00
    assert out["B"]["possessionTime"] == "1:37"  # 1:29 + the 8 s kickoff
