"""Claude Code's answers build on the ones before (owner 2026-10-30: "make the full notes run see this week's notes and merge
its answer, and make the season loads keep what a new answer leaves empty"): the shared rule (keep_filled, join_sources),
the notes run's prompt and save, a pasted whole answer, and the four season loads (coaches, facts, costs, preseason)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import notes_paste
from app.services.answers import filled, join_sources, keep_filled
from app.services.notes import NotesFile, load_notes
from app.services.season_notes import CoachesBatch, CostsBatch, FactsBatch, PreseasonTeam, SeasonNotes
from tests.test_notes_paste import GOOD, NEXT_GAME, notes_app  # noqa: F401 - the fixture is used by name

# --- the rule ---------------------------------------------------------------------------------------------------


def test_filled_and_keep_filled():
    assert not any(filled(v) for v in (None, "", "  ", [], {}, [None, ""], {"a": None, "b": []}))
    assert all(filled(v) for v in ("x", 0, False, [1], {"a": "x"}, [{"a": ["y"]}]))
    old = {"a": "old", "b": ["x"], "c": {"d": "keep", "e": "old"}, "f": "only old"}
    new = {"a": "new", "b": [], "c": {"e": "new", "g": ""}, "h": "only new"}
    assert keep_filled(new, old) == {"a": "new", "b": ["x"], "c": {"d": "keep", "e": "new", "g": ""}, "f": "only old", "h": "only new"}
    assert keep_filled({"b": ["y"]}, {"b": ["x", "z"]}) == {"b": ["y"]}, "a filled list is the new answer's whole list"
    assert keep_filled(None, "old") == "old" and keep_filled("new", None) == "new" and keep_filled({"a": 1}, "junk") == {"a": 1}


def test_join_sources():
    got = join_sources([{"label": "A", "url": "https://a"}, {"label": "B"}], [{"label": "A again", "url": "https://A"}, "junk", {"label": "C", "url": "https://c"}], None, limit=3)
    assert [s["label"] for s in got] == ["A", "B", "C"], "the newest first, each page once"


# --- the notes ----------------------------------------------------------------------------------------------------

WEEK = {
    "gameId": 7, "author": "Monday run", "writtenAt": "2026-10-26T15:00:00Z",
    "sources": [{"label": "Depth chart", "url": "https://example.invalid/chart"}],
    "schemes": {"offense": "Spread", "defense": "3-3-5", "opponent": {"offense": "Pro style", "defense": "4-3"}},
    "availability": [{"name": "Hurt Guy", "status": "Out"}], "availabilitySource": "SEC report", "availabilityUpdatedAt": "2026-10-29T20:00:00Z",
    "visitors": {"home": [{"name": "Big Recruit", "stars": 5}], "away": []},
    "lineups": {"us": {"team": "Florida", "slots": [{"slot": "QB", "players": [{"name": "Our QB"}]}]}, "them": {"team": "Georgia", "slots": [{"slot": "QB", "players": [{"name": "Their QB"}]}]}},
}


def test_a_whole_answer_builds_on_the_weeks_notes(tmp_path: Path):
    notes_paste.save_notes(tmp_path, 7, NotesFile.model_validate(WEEK))
    answer = NotesFile.model_validate({
        "gameId": 7, "author": "Game-day run", "writtenAt": "2026-10-31T17:30:00Z", "sources": [{"label": "Preview", "url": "https://example.invalid/preview"}],
        "sections": [{"heading": "Coaching matchup", "paragraphs": ["New."]}],
        "visitors": {"home": [], "away": []},
        "lineups": {"us": {"team": "Florida", "slots": [{"slot": "QB", "players": [{"name": "New QB"}]}]}},
        "schemes": {"offense": "Spread, 11 personnel"},
    })
    assert notes_paste.merge_notes(tmp_path, 7, answer) is True
    notes, error = load_notes(tmp_path, 7)
    assert error is None
    assert [s.heading for s in notes.sections] == ["Coaching matchup"], "what the answer fills is new"
    assert notes.visitors.home[0].name == "Big Recruit", "Friday's visitors stay when the answer has none"
    assert notes.lineups.us.slots[0].players[0].name == "New QB" and notes.lineups.them.slots[0].players[0].name == "Their QB", "one team's chart never wipes the other's"
    assert notes.schemes.offense == "Spread, 11 personnel" and notes.schemes.opponent.defense == "4-3"
    assert notes.availability[0].name == "Hurt Guy" and notes.availabilityUpdatedAt == "2026-10-29T20:00:00Z", "the report and its time stay together"
    assert notes.author == "Game-day run" and [s.label for s in notes.sources] == ["Preview", "Depth chart"]
    assert notes_paste.merge_notes(tmp_path, 7, answer) is False, "the same answer again changes nothing"


def test_a_new_injury_report_brings_its_time(tmp_path: Path):
    notes_paste.save_notes(tmp_path, 7, NotesFile.model_validate(WEEK))
    answer = NotesFile.model_validate({"gameId": 7, "writtenAt": "2026-10-31T17:30:00Z", "availability": [{"name": "New Hurt", "status": "Questionable"}]})
    notes_paste.merge_notes(tmp_path, 7, answer)
    notes, _error = load_notes(tmp_path, 7)
    assert [r.name for r in notes.availability] == ["New Hurt"] and notes.availabilityUpdatedAt == "2026-10-31T17:30:00Z" and notes.availabilitySource == "SEC report"


def test_no_notes_yet_or_a_damaged_file_takes_the_answer_whole(tmp_path: Path):
    answer = NotesFile.model_validate({**WEEK, "author": "First"})
    assert notes_paste.merge_notes(tmp_path, 7, answer) is True and load_notes(tmp_path, 7)[0].author == "First"
    notes_paste.notes_path(tmp_path, 8).parent.mkdir(parents=True, exist_ok=True)
    notes_paste.notes_path(tmp_path, 8).write_text("{broken", encoding="utf-8")
    assert notes_paste.merge_notes(tmp_path, 8, answer) is True and load_notes(tmp_path, 8)[0].author == "First", "a broken file never blocks game-day notes"


def test_the_full_prompt_carries_the_weeks_notes(tmp_path: Path):
    assert notes_paste.so_far_text(tmp_path, 7) == "", "no notes yet: nothing to build on"
    notes_paste.save_notes(tmp_path, 7, NotesFile.model_validate({"gameId": 7, "author": "x"}))
    assert notes_paste.so_far_text(tmp_path, 7) == "", "notes with nothing in them: nothing to build on"
    notes_paste.save_notes(tmp_path, 7, NotesFile.model_validate(WEEK))
    text = notes_paste.so_far_text(tmp_path, 7)
    assert "This game's notes so far" in text and "Big Recruit" in text and "Their QB" in text and "leave a part out rather than send it emptier" in text
    assert "example.invalid/chart" not in text, "the sources stay out of the prompt"
    prompt = notes_paste.build_prompt(tmp_path, None, {"gameId": 7, "home": "Georgia", "away": "Florida"}, 2026)
    assert "This game's notes so far" in prompt and "Big Recruit" in prompt


def test_a_pasted_whole_answer_builds_on_the_notes(notes_app, client: TestClient):  # noqa: F811 - the fixture
    data_dir = notes_app.state.settings.data_dir
    assert client.post("/api/notes/save", json={"gameId": NEXT_GAME, "text": json.dumps(GOOD)}).json()["data"]["saved"] is True
    later = {**GOOD, "sections": [{"heading": "Game day", "paragraphs": ["x"]}], "visitors": {"home": [], "away": []}}
    later.pop("lineups")
    saved = client.post("/api/notes/save", json={"gameId": NEXT_GAME, "text": json.dumps(later)}).json()["data"]
    assert saved["saved"] is True and saved["changed"] is True
    notes, _error = load_notes(data_dir, NEXT_GAME)
    assert [s.heading for s in notes.sections] == ["Game day"] and notes.visitors.home[0].name == "Recruit One" and notes.lineups.us.slots[0].players[0].name == "Starter"


# --- the season loads ---------------------------------------------------------------------------------------------


@pytest.fixture
def season_notes(tmp_path: Path) -> SeasonNotes:
    return SeasonNotes(tmp_path, 2026)


def test_a_preseason_load_keeps_what_the_new_answer_leaves_out(season_notes: SeasonNotes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first = PreseasonTeam.model_validate({"school": "Florida", "outlook": {"summary": "Old.", "stars": [{"name": "Star One", "honor": "Watch list"}], "predictedRecord": {"overall": "7-5"}}, "injuries": [{"name": "Hurt"}], "sources": [{"label": "A", "url": "https://a"}]})
    season_notes.save_preseason(first, "Florida", "first")
    second = PreseasonTeam.model_validate({"school": "Florida", "outlook": {"summary": "New.", "stars": []}, "staff": [{"name": "Coach", "role": "Head coach"}], "sources": [{"label": "B", "url": "https://b"}]})
    season_notes.save_preseason(second, "Florida", "second")
    got = season_notes.preseason_for("Florida")
    assert got.outlook.summary == "New." and got.outlook.stars[0].name == "Star One" and got.outlook.predictedRecord.overall == "7-5"
    assert got.injuries[0].name == "Hurt" and got.staff[0].name == "Coach" and [s.label for s in got.sources] == ["B", "A"]
    # a first load of its own builds on the shipped one
    shipped = tmp_path / "preseason-shipped.json"
    shipped.write_text(json.dumps({"season": 2026, "checkedAt": "2026-10-22", "teams": {"Georgia": {"school": "Georgia", "outlook": {"stars": [{"name": "Shipped Star"}], "summary": "Shipped."}}}}), encoding="utf-8")
    monkeypatch.setattr("app.services.season_notes.SHIPPED_PRESEASON", shipped)
    season_notes.save_preseason(PreseasonTeam.model_validate({"school": "Georgia", "outlook": {"summary": "Own."}}), "Georgia", "own")
    georgia = season_notes.preseason_for("Georgia")
    assert georgia.outlook.summary == "Own." and georgia.outlook.stars[0].name == "Shipped Star"


def test_coaches_facts_and_costs_keep_what_is_left_out(season_notes: SeasonNotes):
    season_notes.save_coaches(CoachesBatch.model_validate({"teams": [{"school": "Florida", "headCoach": "Head One", "offensiveCoordinator": "OC One", "defensiveCoordinator": "DC One"}]}), "SEC", ["Florida"])
    season_notes.save_coaches(CoachesBatch.model_validate({"teams": [{"school": "Florida", "headCoach": "Head One", "defensiveCoordinator": "DC Two"}]}), "SEC", ["Florida"])
    row = season_notes.coaches_for("Florida")
    assert row["offensiveCoordinator"] == "OC One" and row["defensiveCoordinator"] == "DC Two"
    season_notes.save_facts(FactsBatch.model_validate({"teams": [{"school": "Florida", "nationalTitles": 3, "traditions": ["Gator Chomp"], "stadiumNickname": "The Swamp"}]}), "SEC", ["Florida"])
    season_notes.save_facts(FactsBatch.model_validate({"teams": [{"school": "Florida", "traditions": [], "stadiumNickname": "The Swamp"}]}), "SEC", ["Florida"])
    facts = season_notes.facts_for("Florida")
    assert facts["traditions"] == ["Gator Chomp"] and facts["stadiumNickname"] == "The Swamp"
    season_notes.save_costs(CostsBatch.model_validate({"teams": [{"school": "Florida", "totalUsd": 20500000, "note": "Reported."}]}), "SEC", ["Florida"], ["Florida"])
    season_notes.save_costs(CostsBatch.model_validate({"teams": [{"school": "Florida", "note": "Newer report."}]}), "SEC", ["Florida"], ["Florida"])
    costs = season_notes.costs_for("Florida")
    assert costs["totalUsd"] == 20500000 and costs["note"] == "Newer report."
