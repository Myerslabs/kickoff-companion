"""Post-freeze Wave 1 (owner 2026-10-25): one part of the game's notes loaded on its own. "Recruits on hand sends you to
Program notes. Every empty or partly filled section gets its own Claude button saying what is missing." The prompt asks for
that part alone, the answer is merged into the notes there and never replaces them, the To do names only the parts that can
be had yet (the injury report two days out, the depth charts from the game week), and its Run says what it starts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import notes_paste, readiness
from app.services.notes import NotesFile, notes_path

GAME = {"gameId": 41, "home": "Swampwater Tech", "away": "Diner Tech", "kickoff": "2026-10-31T23:00:00Z"}


class Who:
    school = "Swampwater Tech"
    name = "Mudpuppies"
    conference = "Biscuit Belt"


def test_a_part_prompt_asks_for_that_part_alone():
    prompt = notes_paste.build_parts_prompt(Who(), GAME, 2026, ["visitors"])
    assert "This asks only for the recruits on hand" in prompt and "game id is 41" in prompt
    assert '"visitors"' in prompt and '"lineups"' not in prompt and '"availability"' not in prompt and '"sections"' not in prompt
    assert "1. \"visitors\"" in prompt and "2. \"sources\"" in prompt and "never invent a player" in prompt
    two = notes_paste.build_parts_prompt(Who(), GAME, 2026, ["lineups", "availability", "bogus"])
    assert "the injury report and both depth charts" in two, "in the notes' own order, unknown names dropped"
    assert "{team}" not in two and "{opponent}" not in two and "Diner Tech" in two


def test_parts_are_read_from_a_list_or_a_comma_list():
    assert notes_paste.parse_parts("lineups, visitors,BOGUS") == ["visitors", "lineups"]
    assert notes_paste.parse_parts(["availability", 7, None]) == ["availability"]
    assert notes_paste.parse_parts(None) == [] and notes_paste.parse_parts(12) == []


def _write(tmp_path: Path, payload: dict) -> None:
    path = notes_path(tmp_path, 41)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read(tmp_path: Path) -> dict:
    return json.loads(notes_path(tmp_path, 41).read_text(encoding="utf-8"))


def test_a_part_is_merged_and_the_rest_kept(tmp_path: Path):
    _write(tmp_path, {"gameId": 41, "author": "First run", "sections": [{"heading": "Coaching", "paragraphs": ["Kept."]}], "availability": [{"team": "Swampwater Tech", "name": "A Back", "status": "Out"}], "sources": [{"label": "Old", "url": "https://a.example/one"}]})
    update = NotesFile.model_validate({"visitors": {"home": [{"name": "Big Recruit", "stars": 5}], "source": "A site"}, "availability": [], "sources": [{"label": "Old", "url": "https://a.example/one"}, {"label": "New", "url": "https://b.example/two"}]})
    assert notes_paste.merge_parts(tmp_path, 41, update, ["visitors"]) is True
    saved = _read(tmp_path)
    assert saved["visitors"]["home"][0]["name"] == "Big Recruit"
    assert saved["sections"][0]["paragraphs"] == ["Kept."] and saved["author"] == "First run", "the written notes stay"
    assert saved["availability"][0]["name"] == "A Back", "a part not asked for stays, even when the answer carried it empty"
    assert [s["url"] for s in saved["sources"]] == ["https://a.example/one", "https://b.example/two"], "sources added once"
    assert notes_paste.merge_parts(tmp_path, 41, update, ["visitors"]) is False, "the same answer again changes nothing"


def test_an_empty_answer_never_wipes_a_part(tmp_path: Path):
    _write(tmp_path, {"gameId": 41, "lineups": {"us": {"slots": [{"slot": "QB", "players": [{"name": "Kept Starter"}]}]}}})
    assert notes_paste.merge_parts(tmp_path, 41, NotesFile.model_validate({"lineups": {"us": {"slots": []}}}), ["lineups"]) is False
    assert _read(tmp_path)["lineups"]["us"]["slots"][0]["players"][0]["name"] == "Kept Starter"


def test_a_part_makes_a_small_file_when_there_is_none_and_refuses_a_broken_one(tmp_path: Path):
    update = NotesFile.model_validate({"author": "Claude", "broadcast": {"network": "ABC", "playByPlay": "A Voice"}})
    assert notes_paste.merge_parts(tmp_path, 41, update, ["broadcast"]) is True
    assert _read(tmp_path)["broadcast"]["playByPlay"] == "A Voice" and _read(tmp_path)["gameId"] == 41
    notes_path(tmp_path, 41).write_text("{ broken", encoding="utf-8")
    with pytest.raises(notes_paste.NotesUnreadable):
        notes_paste.merge_parts(tmp_path, 41, update, ["broadcast"])
    assert notes_path(tmp_path, 41).read_text(encoding="utf-8") == "{ broken", "never replaced by a partial update"


def test_a_part_is_due_only_once_it_is_published():
    kickoff = "2026-10-31T23:00:00Z"
    monday = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    friday = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    assert readiness.part_due("availability", kickoff, monday) == (False, "2026-10-29T23:00:00Z")
    assert readiness.part_due("availability", kickoff, friday)[0] is True
    assert readiness.part_due("lineups", kickoff, monday)[0] is True and readiness.part_due("broadcast", kickoff, monday)[0] is True
    assert readiness.part_due("coaches", kickoff, monday) == (True, None), "the coaches can be had any time"
    assert readiness.part_due("availability", None, monday) == (True, None), "an unknown kickoff is no reason to wait"
    assert readiness.notes_due(kickoff, monday)["availability"] == {"due": False, "from": "2026-10-29T23:00:00Z"}


def test_the_to_do_names_what_can_be_had_and_says_what_its_run_starts():
    status = {"season": 2026, "preseason": [], "coachesSaved": 136, "coachesOf": 136, "costsSaved": 136, "factsSaved": 136}
    notes = NotesFile.model_validate({"sections": [{"heading": "H", "paragraphs": ["p"]}], "coaches": {"us": {"headCoach": "X"}}})
    game = {"gameId": 41, "opponent": "Diner Tech", "kickoff": "2026-10-31T23:00:00Z"}
    monday = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    result = readiness.readiness(status, notes, game, monday, command_found=True)
    item = result["items"][0]
    assert item["detail"].startswith("Missing: both depth charts and the TV crew.") and "Later: the injury report from" in item["detail"]
    assert item["run"] == {"kind": "notes", "gameId": 41, "parts": ["lineups", "broadcast"]} and item["canRun"] is True
    early = readiness.readiness(status, notes, game, datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert early["items"] == [] and early["ready"], "eleven days out only the injury report, the charts and the crew are missing: nothing to nag about yet"
    whole = readiness.readiness(status, None, game, monday)["items"][0]
    assert whole["run"]["parts"] is None and whole["detail"].startswith("Not loaded:") and whole["canRun"] is False
    loads = readiness.readiness({**status, "costsSaved": 18}, NotesFile.model_validate({}), None, monday, command_found=True)["items"]
    assert loads[0]["id"] == "costs" and loads[0]["run"] == {"kind": "prompts"}
