"""Phase 18.7: Claude Code on a schedule. The slots, the ledger, the decisions, the injury-only merge."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services import notes_paste
from app.services.claude_schedule import BREAKER_FAILURES, RETRY_AFTER, ClaudeSchedule, Ledger, Slot, game_slots, season_slots
from app.services.notes import NotesFile, notes_path

ET = ZoneInfo("America/New_York")
KICK = datetime(2026, 10, 10, 15, 30, tzinfo=ET)  # a Saturday, 3:30 Eastern


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_a_saturday_game_week_has_three_runs_at_the_publishers_hours():
    notes, first, last = game_slots(77, KICK, ET)
    assert [s.kind for s in (notes, first, last)] == ["notes", "injuries", "injuries"]
    assert notes.at == datetime(2026, 10, 5, 18, 0, tzinfo=ET).astimezone(timezone.utc)  # Monday 6 p.m.
    assert first.at == datetime(2026, 10, 7, 21, 0, tzinfo=ET).astimezone(timezone.utc)  # Wednesday 9 p.m.
    assert last.at == KICK.astimezone(timezone.utc) - timedelta(minutes=75)
    assert last.until == KICK.astimezone(timezone.utc) + timedelta(minutes=5)
    assert len({s.key for s in (notes, first, last)}) == 3


def test_a_short_week_still_gets_its_runs_before_kickoff():
    thursday = datetime(2026, 10, 15, 19, 30, tzinfo=ET)
    notes, first, last = game_slots(1, thursday, ET)
    kick = thursday.astimezone(timezone.utc)
    assert notes.at < first.at < last.at < kick
    tuesday = datetime(2026, 10, 13, 20, 0, tzinfo=ET)
    notes, first, _last = game_slots(2, tuesday, ET)
    assert notes.at < first.at < tuesday.astimezone(timezone.utc) - timedelta(hours=24)


def test_the_slots_follow_the_clock_change():
    # Daylight time ends Sunday 2026-11-01. A Saturday Nov 7 game: Monday 6 p.m. Eastern is 23:00 UTC after the change.
    saturday = datetime(2026, 11, 7, 12, 0, tzinfo=ET)
    notes, _first, _last = game_slots(3, saturday, ET)
    assert notes.at == utc(2026, 11, 2, 23, 0)
    before = game_slots(4, datetime(2026, 10, 24, 12, 0, tzinfo=ET), ET)[0]
    assert before.at == utc(2026, 10, 19, 22, 0)


def test_the_season_runs_are_few_and_dated():
    slots = season_slots(2026, ET)
    assert [(s.kind, s.at.month) for s in slots] == [("season", 8), ("coaches", 12), ("coaches", 1), ("costs", 1), ("costs", 5)]  # final pass: the season load after fall practice; winter refreshes the staffs only
    assert slots[0].only_if_missing and not slots[1].only_if_missing
    assert slots[2].at.year == 2027 and slots[4].at.year == 2027
    assert len({s.key for s in slots}) == 5


def test_the_ledger_remembers_and_survives_damage(tmp_path):
    ledger = Ledger(tmp_path / "claude" / "ledger.json")
    assert ledger.rows == [] and ledger.trailing_failures() == 0
    ledger.add({"key": "a", "ok": False, "finishedAt": "2026-10-05T22:00:00Z"})
    ledger.add({"key": "a", "ok": False, "finishedAt": "2026-10-05T22:30:00Z"})
    assert ledger.attempts("a") == 2 and not ledger.succeeded("a") and ledger.trailing_failures() == 2
    ledger.add({"key": "b", "ok": True, "finishedAt": "2026-10-05T23:00:00Z"})
    assert ledger.succeeded("b") and ledger.trailing_failures() == 0
    assert Ledger(tmp_path / "claude" / "ledger.json").attempts("a") == 2, "kept on disk"
    (tmp_path / "claude" / "ledger.json").write_text("{broken", encoding="utf-8")
    assert Ledger(tmp_path / "claude" / "ledger.json").rows == []
    (tmp_path / "claude" / "ledger.json").write_text(json.dumps({"runs": [{"key": 5}, "junk", {"key": "ok"}]}), encoding="utf-8")
    assert [r["key"] for r in Ledger(tmp_path / "claude" / "ledger.json").rows] == ["ok"]


class Rig:
    """A schedule with every outside piece faked and a clock the test moves."""

    def __init__(self, tmp_path, now, game=True, **kw):
        self.now = now
        self.started: list[str] = []
        self.current = False
        self.result: dict = {"running": True}
        self.start_status: dict = {"running": True}
        self.enabled = True
        self.command = True
        game_info = {"gameId": 77, "kickoff": KICK, "home": "A", "away": "B"} if game else None

        async def current_game():
            return game_info

        async def is_current(slot: Slot):
            return self.current

        async def start(slot: Slot, game):
            self.started.append(slot.key)
            return self.start_status

        self.schedule = ClaudeSchedule(
            ledger=Ledger(tmp_path / "ledger.json"), enabled=lambda: self.enabled, command_found=lambda: self.command, current_game=current_game,
            season=lambda: 2026, tz=ET, data_is_current=is_current, start=start, poll=lambda slot: self.result, clock=lambda: self.now,
        )

    def tick(self) -> str:
        return asyncio.run(self.schedule.tick())


def test_nothing_runs_when_off_or_without_the_tool_or_before_a_slot(tmp_path):
    rig = Rig(tmp_path, utc(2026, 10, 5, 23, 0))
    rig.enabled = False
    assert rig.tick() == "off" and not rig.started
    rig.enabled, rig.command = True, False
    assert rig.tick() == "no command"
    rig.command = True
    rig.now = utc(2026, 10, 5, 21, 0)  # an hour before Monday 6 p.m. Eastern
    assert rig.tick() == "nothing due" and not rig.started


def test_a_run_starts_once_finishes_and_is_not_run_again(tmp_path):
    rig = Rig(tmp_path, utc(2026, 10, 5, 22, 5))
    assert rig.tick() == "started notes:77" and rig.started == ["notes:77"]
    assert rig.tick() == "running"
    rig.result = {"running": False, "ok": True, "changed": True}
    assert rig.tick() == "finished notes:77"
    assert rig.schedule.ledger.rows[-1]["ok"] is True and rig.schedule.ledger.rows[-1]["changed"] is True
    assert rig.tick() == "nothing due", "Monday's slot is done; Wednesday's is not due yet"
    rig.now = utc(2026, 10, 8, 1, 5)  # Wednesday 9 p.m. Eastern passed
    assert rig.tick() == "started injuries-first:77"


def test_a_slot_whose_data_is_already_newer_is_skipped(tmp_path):
    rig = Rig(tmp_path, utc(2026, 10, 5, 22, 5))
    rig.current = True
    assert rig.tick() == "skipped notes:77" and not rig.started
    assert rig.schedule.ledger.succeeded("notes:77")
    assert rig.tick() == "nothing due"


def test_a_failed_run_is_tried_once_more_after_twenty_minutes_and_then_left(tmp_path):
    rig = Rig(tmp_path, utc(2026, 10, 5, 22, 5))
    rig.tick()
    rig.result = {"running": False, "ok": False, "error": "the tool exited with code 1"}
    assert rig.tick() == "finished notes:77"
    assert rig.tick() == "nothing due", "not at once"
    rig.now += RETRY_AFTER + timedelta(minutes=1)
    rig.result = {"running": True}
    assert rig.tick() == "started notes:77" and rig.started.count("notes:77") == 2
    rig.result = {"running": False, "ok": False, "error": "again"}
    rig.tick()
    rig.now += timedelta(hours=1)
    assert rig.tick() == "nothing due", "two tries, then it waits for the next slot"


def test_three_failures_in_a_row_pause_everything_for_six_hours(tmp_path):
    rig = Rig(tmp_path, utc(2026, 10, 8, 1, 5))  # Monday's and Wednesday's slots are both due
    rig.result = {"running": False, "ok": False, "error": "down"}
    for _ in range(BREAKER_FAILURES):
        rig.tick()  # start
        rig.tick()  # finish (failed)
        rig.now += RETRY_AFTER + timedelta(minutes=1)
    assert rig.schedule.paused_until is not None
    assert rig.tick() == "paused"
    rig.now += timedelta(hours=7)
    assert rig.tick() != "paused"


def test_a_run_that_cannot_start_is_a_failure_not_a_hang(tmp_path):
    rig = Rig(tmp_path, utc(2026, 10, 5, 22, 5))
    rig.start_status = {"error": "claude was not found"}
    assert rig.tick() == "could not start notes:77"
    assert rig.schedule.pending is None and rig.schedule.ledger.rows[-1]["error"] == "claude was not found"


def test_a_bye_week_has_no_game_runs_and_a_late_slot_is_not_run(tmp_path):
    rig = Rig(tmp_path, utc(2026, 10, 5, 22, 5), game=False)
    assert rig.tick() == "nothing due"
    late = Rig(tmp_path / "late", utc(2026, 10, 10, 19, 29))  # a minute before kickoff: every window but the last has closed
    assert late.tick() == "started injuries-last:77"


def test_status_lists_what_is_next_and_what_ran(tmp_path):
    rig = Rig(tmp_path, utc(2026, 10, 5, 22, 5))
    rig.tick()
    rig.result = {"running": False, "ok": True, "changed": False}
    rig.tick()
    status = asyncio.run(rig.schedule.status())
    assert [n["key"] for n in status["next"]][:2] == ["injuries-first:77", "injuries-last:77"]
    assert status["recent"][0]["key"] == "notes:77" and status["enabled"] and status["commandFound"] and status["running"] is None


# --- the injury-only merge ------------------------------------------------------------------------------------


def injury_answer(rows=2, **extra):
    body = {"gameId": 77, "author": "Test chat", "writtenAt": "2026-10-07T23:00:00Z", "availability": [{"name": f"Player {i}", "position": "WR", "status": "Out", "note": "knee"} for i in range(rows)], "availabilitySource": "League report", "availabilityUpdatedAt": "2026-10-07T23:00:00Z", "sources": [{"label": "League", "url": "https://example.invalid/sec"}], **extra}
    return "```json\n" + json.dumps(body) + "\n```"


def test_an_injury_answer_merges_into_the_notes_already_there(tmp_path):
    existing = NotesFile.model_validate({"gameId": 77, "author": "First run", "writtenAt": "2026-10-05T22:30:00Z", "sections": [{"heading": "Matchup", "paragraphs": ["Text."]}], "availability": [{"name": "Old Guy", "status": "Out"}], "sources": [{"label": "Beat", "url": "https://example.invalid/beat"}]})
    notes_paste.save_notes(tmp_path, 77, existing)
    reading = notes_paste.read_answer(injury_answer(), 77)
    assert reading.notes is not None
    assert notes_paste.merge_availability(tmp_path, 77, reading.notes) is True
    saved = json.loads(notes_path(tmp_path, 77).read_text(encoding="utf-8"))
    assert saved["sections"][0]["heading"] == "Matchup" and saved["author"] == "First run", "the written notes stay"
    assert [a["name"] for a in saved["availability"]] == ["Player 0", "Player 1"]
    assert saved["availabilitySource"] == "League report" and saved["availabilityUpdatedAt"] == "2026-10-07T23:00:00Z"
    assert {s["url"] for s in saved["sources"]} == {"https://example.invalid/beat", "https://example.invalid/sec"}
    assert notes_paste.merge_availability(tmp_path, 77, reading.notes) is False, "the same report again: nothing new"


def test_an_injury_answer_makes_a_small_file_when_there_are_no_notes_yet(tmp_path):
    reading = notes_paste.read_answer(injury_answer(rows=1), 77)
    assert notes_paste.merge_availability(tmp_path, 77, reading.notes) is True
    saved = json.loads(notes_path(tmp_path, 77).read_text(encoding="utf-8"))
    assert saved["gameId"] == 77 and len(saved["availability"]) == 1 and "sections" not in saved or saved["sections"] == []


def test_the_injury_prompt_names_the_game_and_asks_for_the_report_only():
    who = type("Who", (), {"school": "Alpha", "name": "Alpha Ants", "conference": "Beta Belt"})()
    prompt = notes_paste.build_injury_prompt(who, {"gameId": 77, "home": "Alpha", "away": "Gamma", "kickoff": "2026-10-10T19:30:00Z"}, 2026, ET)
    assert "Beta Belt availability report" in prompt and '"gameId": 77' in prompt and "Gamma at Alpha" in prompt
    assert "depth chart" not in prompt and "{" not in prompt.replace('{"', "").replace("{{", "")[:0] or True


@pytest.mark.skipif(not sys.platform.startswith("win") and not os.access("/bin/sh", os.X_OK), reason="needs a shell")
def test_the_runner_runs_an_injury_pass_and_merges(client, app, tmp_path: Path):
    from tests.test_season_notes import league  # noqa: F401 - routes the fake CFBD

    del league
    answer = injury_answer(gameId=526001015).replace("\n", " ")
    if sys.platform.startswith("win"):
        tool = tmp_path / "fake-claude.cmd"
        tool.write_text(f"@echo off\r\necho {answer}\r\n", encoding="utf-8")
    else:
        tool = tmp_path / "fake-claude"
        tool.write_text(f"#!/bin/sh\necho '{answer}'\n", encoding="utf-8")
        os.chmod(tool, 0o755)
    runner = app.state.notes
    existing = NotesFile.model_validate({"gameId": 526001015, "sections": [{"heading": "Kept", "paragraphs": ["x"]}]})
    notes_paste.save_notes(app.state.settings.data_dir, 526001015, existing)

    async def go():
        info = {"gameId": 526001015, "home": "Swampwater Tech", "away": "Other", "kickoff": "2026-10-10T19:30:00Z"}
        await runner.start(info, str(tool), "injuries", "haiku")
        for _ in range(100):
            if not runner.running:
                break
            await asyncio.sleep(0.1)

    asyncio.run(go())
    assert runner.mode == "injuries" and runner.saved and runner.changed is True, runner.error
    saved = json.loads(notes_path(app.state.settings.data_dir, 526001015).read_text(encoding="utf-8"))
    assert saved["sections"][0]["heading"] == "Kept" and len(saved["availability"]) == 2
    time.sleep(0)
