"""P4 on the schedule (owner 2026-10-25): the game week's other runs (Monday's depth charts, the Wednesday and Thursday
availability reports, Friday's visitors, the scouting report, the paper, the trivia), the morning after our game (what
decided it, then the weekly review), and the weekly data check, each before the notes' last run; and the review's
findings: what the notes said against what the box shows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.claude_schedule import ClaudeSchedule, Ledger, after_slots, week_slots, weekly_slots
from app.services.notes import NotesFile
from app.writing_setup import review_findings

ET = ZoneInfo("America/New_York")
SATURDAY = datetime(2026, 10, 24, 19, 30, tzinfo=ET)
THURSDAY = datetime(2026, 10, 22, 19, 30, tzinfo=ET)


def test_a_saturday_game_week_has_every_run_in_order_before_the_notes_last_run():
    slots = week_slots(401, SATURDAY, ET, week=8)
    assert [s.key for s in slots] == ["parts-mon:401", "scout:401", "parts-wed:401", "numbers:week-8", "paper:week-8", "picks:week-8", "parts-thu:401", "parts-fri:401", "trivia:401"]  # Wave 6: By the numbers Thursday morning
    mon = slots[0]
    assert mon.at == datetime(2026, 10, 19, 10, 0, tzinfo=ET) and mon.mode == "parts:lineups,schemes,coaches,broadcast" and mon.kind == "parts"
    assert slots[2].mode == "parts:availability" and slots[7].mode == "parts:visitors"
    assert slots[1].writing_key == "401" and slots[4].writing_key == "week-8" and slots[4].kind == "paper"
    assert slots[3].kind == "numbers" and slots[3].writing_key == "week-8" and slots[3].at == datetime(2026, 10, 22, 10, 0, tzinfo=ET)
    last = SATURDAY.astimezone(timezone.utc) - timedelta(hours=2)
    assert all(s.at < last and s.until <= SATURDAY.astimezone(timezone.utc) for s in slots)
    assert all(s.until <= last for s in slots if s.kind == "parts"), "a part never runs after the notes' last run"


def test_a_thursday_game_keeps_only_what_comes_before_its_kickoff_and_no_week_no_paper():
    keys = [s.key for s in week_slots(402, THURSDAY, ET, week=None)]
    assert keys == ["parts-mon:402", "scout:402", "parts-wed:402"], keys


def test_the_morning_after_and_the_weekly_check():
    recap, review = after_slots(401, SATURDAY)
    kick = SATURDAY.astimezone(timezone.utc)
    assert recap.at == kick + timedelta(hours=14) and review.at == kick + timedelta(hours=15) and review.until == kick + timedelta(days=4)
    assert recap.writing_key == review.writing_key == "401"
    this, nxt = weekly_slots(datetime(2026, 10, 25, 12, tzinfo=timezone.utc), ET)
    assert this.key == "datacheck:2026-10-20" and nxt.key == "datacheck:2026-10-27" and this.at == datetime(2026, 10, 20, 10, tzinfo=ET)


def test_the_schedule_runs_the_new_kinds_only_when_writing_is_on(tmp_path):
    started: list = []

    async def current():
        return {"gameId": 401, "home": "Florida", "away": "Texas", "kickoff": SATURDAY.astimezone(timezone.utc), "week": 8}

    async def last():
        return {"gameId": 400, "kickoff": (SATURDAY - timedelta(days=7)).astimezone(timezone.utc)}

    async def current_data(slot):
        return False

    async def start(slot, game):
        started.append(slot.key)
        return {"running": True}

    def make(writing: bool, now: datetime) -> ClaudeSchedule:
        return ClaudeSchedule(ledger=Ledger(tmp_path / f"l-{writing}-{now.day}.json"), enabled=lambda: True, command_found=lambda: True, current_game=current, last_game=last,
                              writing=writing, season=lambda: 2026, tz=ET, data_is_current=current_data, start=start, poll=lambda slot: {"running": False, "ok": True}, clock=lambda: now)

    tuesday = datetime(2026, 10, 20, 11, 0, tzinfo=ET).astimezone(timezone.utc)
    assert asyncio.run(make(False, tuesday).tick()) == "nothing due", "off: as before P4"
    schedule = make(True, datetime(2026, 10, 18, 12, 0, tzinfo=ET).astimezone(timezone.utc))  # the Sunday after game 400
    assert asyncio.run(schedule.tick()) == "started recap:400"
    upcoming = [s.key for s in schedule.upcoming(None, datetime(2026, 10, 18, 12, 0, tzinfo=ET).astimezone(timezone.utc), {"gameId": 400, "kickoff": (SATURDAY - timedelta(days=7)).astimezone(timezone.utc)})]
    assert "review:400" in upcoming and "datacheck:2026-10-20" in upcoming


def test_the_review_finds_what_the_notes_got_wrong():
    notes = NotesFile.model_validate({
        "availability": [
            {"team": "Florida", "name": "Avery Passer", "status": "Out"},
            {"team": "Florida", "name": "Ben Runner Jr.", "status": "Questionable"},
            {"team": "Texas", "name": "Cal Catcher", "status": "Doubtful"},
            {"team": "Nowhere", "name": "X", "status": "Out"},
        ],
        "lineups": {"us": {"slots": [{"slot": "QB", "players": [{"name": "Dee Thrower"}]}, {"slot": "LT", "players": [{"name": "Big Blocker"}]}, {"slot": "RB", "players": [{"name": "Ben Runner Jr."}]}]},
                    "them": {"slots": [{"slot": "WR", "players": [{"name": "Cal Catcher"}]}]}},
        "sections": [{"heading": "Coaching", "paragraphs": ["x"]}],
    })
    players = {
        "Florida": {"passing": [{"name": "Avery Passer", "stats": {"YDS": 200}}], "rushing": [{"name": "Other Back"}]},
        "Texas": {"receiving": [{"name": "Cal Catcher"}], "defensive": "junk"},
    }
    found = review_findings(notes, players, "Florida", "Texas")
    assert found["listedOutButPlayed"] == [{"team": "Florida", "name": "Avery Passer", "status": "Out"}, {"team": "Texas", "name": "Cal Catcher", "status": "Doubtful"}]
    assert found["questionableDidNotPlay"] == [{"team": "Florida", "name": "Ben Runner Jr."}]
    assert {(r["slot"], r["name"]) for r in found["starterWithNoLine"]} == {("QB", "Dee Thrower"), ("RB", "Ben Runner Jr.")}, "linemen have no line to look for"
    assert "visitors" in found["emptyParts"] and "sections" not in found["emptyParts"] and "lineups" not in found["emptyParts"]
    nothing = review_findings(None, {}, "Florida", "Texas")
    assert "sections" in nothing["emptyParts"] and nothing["listedOutButPlayed"] == []
    assert review_findings(notes, {}, "Florida", "Texas")["listedOutButPlayed"] == [], "no box yet: nothing judged"
