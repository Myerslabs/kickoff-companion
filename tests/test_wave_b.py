"""The Prompts phase, wave B (owner 2026-10-13): the Pre-Game Program locked at kickoff (the file written once, the
housekeeping hook that writes it in the kickoff window, the route that reads it back), on this day from the facts
prompt's dates, the notes step of the one run waiting for its slot, and the facts carried by the program."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.maintenance import Maintenance
from app.services.anniversaries import on_this_day
from app.services.program_lock import LOCK_WINDOW, ProgramLock, lock_due, snapshot
from tests.conftest import CONFERENCE, TEAM
from tests.test_prompts_phase import SCHOOLS, facts_answer
from tests.test_season_notes import league  # noqa: F401 - routes the fake CFBD

NOW = datetime(2026, 10, 10, 19, 31, tzinfo=timezone.utc)

PROGRAM = {
    "game": {"gameId": 77, "kickoff": "2026-10-10T19:30:00.000Z", "homeIsUs": True, "completed": False, "usPoints": None},
    "us": {"school": TEAM, "abbreviation": "US", "mascot": "Us", "apRank": 5, "record": {"wins": 4}, "extra": "dropped"},
    "them": {"school": "Them U", "abbreviation": "THM"},
    "line": {"spread": -7.5, "formatted": "US -7.5", "overUnder": 55.5},
    "pregame": {"homeWinProbability": 0.7, "usWinProbability": 0.7, "spread": -7.5},
    "profile": {"us": [{"side": "offense", "label": "Points per game", "key": "ppg", "value": 35.8, "format": "1f", "higherIsBetter": True, "nationalRank": 4, "nationalOf": 136, "conferenceRank": 1}, {"key": 5}, "junk"], "them": "junk"},
    "leaders": [{"label": "Passing yards", "category": "passing", "stat": "YDS", "us": {"playerId": "1", "player": "A. Arm", "value": 1800}, "them": None}, "junk"],
    "edges": [{"label": "e"}] * 9,
    "notes": {"present": True, "author": "Test chat", "sections": ["long"]},
    "final": {"us": {"points": 31}},
}


def test_the_snapshot_keeps_the_expectations_and_nothing_that_moves():
    snap = snapshot(PROGRAM, NOW)
    assert snap["gameId"] == 77 and snap["lockedAt"] == "2026-10-10T19:31:00Z" and snap["homeIsUs"] is True
    assert snap["us"] == {"school": TEAM, "abbreviation": "US", "mascot": "Us", "apRank": 5, "record": {"wins": 4}} and snap["them"]["abbreviation"] == "THM"
    assert snap["line"]["formatted"] == "US -7.5" and snap["pregame"]["usWinProbability"] == 0.7
    assert [r["key"] for r in snap["profile"]["us"]] == ["ppg"] and snap["profile"]["them"] == [], "a bad row is dropped, junk is an empty list"
    assert snap["leaders"][0]["us"]["player"] == "A. Arm" and len(snap["edges"]) == 6
    assert snap["notes"] == {"present": True, "author": "Test chat"} and "final" not in snap
    assert snapshot("junk", NOW)["gameId"] is None


def test_the_lock_is_written_once_and_read_back(tmp_path: Path):
    lock = ProgramLock(tmp_path / "data", 2026)
    assert not lock.has(77) and lock.load(77) is None and lock.load("x") is None
    assert lock.save(77, snapshot(PROGRAM, NOW)) is True
    assert lock.has(77) and lock.load(77)["line"]["spread"] == -7.5
    assert lock.save(77, {"gameId": 77, "line": None}) is False, "the first lock wins"
    assert lock.load(77)["line"]["spread"] == -7.5
    lock.path(77).write_text("{broken", encoding="utf-8")
    assert lock.load(77) is None and lock.has(77)
    lock.path(78).parent.mkdir(parents=True, exist_ok=True)
    lock.path(78).write_text(json.dumps({"no": "gameId"}), encoding="utf-8")
    assert lock.load(78) is None


def test_the_lock_is_due_in_the_kickoff_window_only():
    kick = "2026-10-10T19:30:00.000Z"
    assert not lock_due(kick, False, NOW - timedelta(minutes=2))
    assert lock_due(kick, False, NOW)
    assert lock_due(kick, False, NOW + LOCK_WINDOW - timedelta(minutes=5))
    assert not lock_due(kick, False, NOW + LOCK_WINDOW + timedelta(minutes=5)), "a day later is the result, not the expectation"
    assert not lock_due(kick, True, NOW), "a final is never locked as an expectation"
    assert not lock_due(None, False, NOW) and not lock_due("soon", False, NOW)


def test_the_housekeeping_hook_locks_at_kickoff_through_the_app(client, league, app):  # noqa: F811
    program = client.get("/api/program/next").json()["data"]
    game_id = program["game"]["gameId"]
    assert program["game"]["locked"] is False and "facts" in program
    assert client.get(f"/api/program/{game_id}/locked").status_code == 404
    kickoff = datetime.fromisoformat(program["game"]["kickoff"].replace("Z", "+00:00"))
    hook = app.state.maintenance.lock_program
    assert client.portal.call(hook, kickoff - timedelta(minutes=1)) is False, "before kickoff: nothing"
    assert client.portal.call(hook, kickoff + timedelta(minutes=1)) is True
    assert client.portal.call(hook, kickoff + timedelta(minutes=2)) is False, "once"
    locked = client.get(f"/api/program/{game_id}/locked").json()["data"]
    assert locked["gameId"] == game_id and locked["us"]["school"] == TEAM and isinstance(locked["profile"]["us"], list) and locked["lockedAt"]
    assert client.get(f"/api/program/{game_id}").json()["data"]["game"]["locked"] is True
    assert client.get("/api/program/12/locked").status_code == 404 and client.get("/api/program/x/locked").status_code == 404


def test_the_maintenance_loop_calls_the_hook_and_survives_its_failure(tmp_path: Path):
    calls: list[datetime] = []

    async def hook(now: datetime) -> bool:
        calls.append(now)
        if len(calls) == 2:
            raise RuntimeError("down")
        return True

    m = Maintenance(data_dir=tmp_path / "data", backup_dir=tmp_path / "b", keep=3, window_open=lambda: False, backups_enabled=lambda: False, lock_program=hook, clock=lambda: NOW)
    asyncio.run(m.tick())
    asyncio.run(m.tick())
    asyncio.run(m.tick())
    assert len(calls) == 3, "every tick, and a failure never stops the loop"


# --- on this day ----------------------------------------------------------------------------------------------------


def test_on_this_day_picks_the_anniversaries():
    facts = {
        "A": {"dates": [{"date": "1930-10-13", "event": "The stadium opened"}, {"date": "1996", "event": "A title"}, {"date": "2026-10-13", "event": "today, not an anniversary"}, {"date": "1850-10-13", "event": "The first game"}, "junk", {"date": "1930-10-14", "event": "tomorrow"}]},
        "B": {"dates": "junk"},
        "C": {"dates": [{"date": "2001-10-13", "event": "  A win  "}]},
    }
    today = date(2026, 10, 13)
    events = on_this_day(facts, ["A", "B", "C", "A", None, "Z"], today)
    assert events == [
        {"school": "A", "event": "The first game", "date": "1850-10-13", "years": 176},
        {"school": "A", "event": "The stadium opened", "date": "1930-10-13", "years": 96},
        {"school": "C", "event": "A win", "date": "2001-10-13", "years": 25},
    ]
    assert on_this_day("junk", ["A"], today) == [] and on_this_day(facts, [], today) == []


def test_the_today_route_reads_the_facts(client, league, app):  # noqa: F811
    app.state.cfbd._clock = lambda: datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)
    assert client.get("/api/today").json()["data"] == {"date": "2026-10-13", "events": []}
    answer = facts_answer(schools=[TEAM], dates=[{"date": "1930-10-13", "event": "The stadium opened"}, {"date": "1950-01-01", "event": "Not today"}])
    assert client.post("/api/season-notes/save", json={"kind": "facts", "key": CONFERENCE, "text": answer}).status_code == 200
    data = client.get("/api/today").json()["data"]
    assert data["events"] == [{"school": TEAM, "event": "The stadium opened", "date": "1930-10-13", "years": 96}]
    team = client.get(f"/api/team/{TEAM}").json()["data"]
    assert team["facts"]["dates"][0]["event"] == "The stadium opened"
    program = client.get("/api/program/next").json()["data"]
    assert program["facts"]["us"]["school"] == TEAM and program["facts"]["us"]["founded"] == 1853


# --- the notes step waits for its slot ------------------------------------------------------------------------------


def test_the_notes_step_of_the_one_run_waits_for_two_hours_before_kickoff(client, league, app):  # noqa: F811
    program = client.get("/api/program/next").json()["data"]
    kickoff = datetime.fromisoformat(program["game"]["kickoff"].replace("Z", "+00:00"))
    step = next(s for s in app.state.prompt_runs.steps if s.kind == "notes")
    app.state.cfbd._clock = lambda: kickoff - timedelta(hours=3)
    assert client.portal.call(step.missing) is None, "three hours out: not yet"
    app.state.cfbd._clock = lambda: kickoff - timedelta(hours=1)
    assert client.portal.call(step.missing) == "this week's notes are not loaded", "inside the two hours: due"


def test_the_program_envelope_carries_the_facts_for_both_schools(client, league, app):  # noqa: F811
    client.post("/api/season-notes/save", json={"kind": "facts", "key": CONFERENCE, "text": facts_answer(schools=SCHOOLS[:3])})
    program = client.get("/api/program/next").json()["data"]
    facts: dict[str, Any] = program["facts"]
    assert set(facts) == {"us", "them"}
    for side in ("us", "them"):
        school = program[side]["school"]
        assert (facts[side] is None) == (school not in SCHOOLS[:3]) or facts[side] is None or facts[side]["founded"]
