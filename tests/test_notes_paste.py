"""Public release Phase 6: notes by copy and paste. The prompt names the game and the team and carries the
notes shape inline; an edited prompt is kept in data/notes/PROMPT.md and an old file-writing one is ignored.
A pasted answer is read leniently (fences, chatter, trailing commas, wrong-typed fields, bad rows), a wrong
game number only warns, preview saves nothing, save replaces the game's notes, and the Game program then
shows them. No CFBD call beyond the schedule the program already caches; no AI is called."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services import notes_paste
from app.services.notes import load_notes
from tests.conftest import FakeCfbd, fixture_payload

NEXT_GAME = 526001015  # Diner Tech at Swampwater Tech, the next game on 2026-09-23
NOW = datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)

GOOD = {
    "gameId": NEXT_GAME,
    "author": "A chat",
    "sources": [{"label": "Beat report", "url": "https://example.invalid/beat"}],
    "schemes": {"offense": "Spread, 11 personnel", "defense": "4-2-5, quarters"},
    "sections": [{"heading": "Coaching matchup", "paragraphs": ["Two coaches."]}, {"heading": "Key matchups", "paragraphs": ["Lines."]}],
    "availability": [{"name": "Player One", "position": "WR", "status": "Out", "note": "knee"}],
    "visitors": {"home": [{"name": "Recruit One", "stars": 4}], "away": []},
    "lineups": {"us": {"team": "Swampwater Tech", "slots": [{"unit": "Offense", "slot": "QB", "players": [{"name": "Starter", "number": 12}]}]}},
}


@pytest.fixture
def notes_app(app, client: TestClient, fake_cfbd: FakeCfbd):
    fake_cfbd.route("/games", handler=lambda r: httpx.Response(200, json=fixture_payload("games_team")))
    client.portal.call(app.state.live.stop_background)
    app.state.cfbd._clock = lambda: NOW
    return app


# --- reading an answer --------------------------------------------------------------------------------


def test_an_answer_wrapped_in_chatter_and_a_code_fence_is_read():
    text = "Sure! Here are the notes.\n\n```json\n" + json.dumps(GOOD, indent=2) + "\n```\n\nLet me know if you want more."
    reading = notes_paste.read_answer(text, NEXT_GAME, now=NOW)
    assert reading.notes is not None and reading.error is None and reading.warnings == []
    s = reading.summary
    assert s["sections"] == ["Coaching matchup", "Key matchups"] and s["availability"] == 1 and s["visitors"] == {"home": 1, "away": 0}
    assert s["lineups"] == {"us": 1, "them": 0} and s["sources"] == 1 and s["author"] == "A chat"


def test_bare_json_with_trailing_commas_and_a_second_object_is_read():
    text = 'Example of a row: {"name": "x"}\n' + json.dumps(GOOD).replace("]}", "],}", 1).replace('"knee"}', '"knee",}')
    reading = notes_paste.read_answer(text, NEXT_GAME, now=NOW)
    assert reading.notes is not None, reading.error
    assert reading.summary["sections"] == ["Coaching matchup", "Key matchups"]  # the notes object wins over the stray one


def test_a_wrong_game_number_warns_and_the_notes_go_on_this_game():
    reading = notes_paste.read_answer(json.dumps({**GOOD, "gameId": 12345}), NEXT_GAME, now=NOW)
    assert reading.notes is not None and reading.notes.gameId == NEXT_GAME
    assert any("game 12345" in w for w in reading.warnings)


def test_missing_author_and_time_are_filled_and_sources_are_checked():
    bare = {k: v for k, v in GOOD.items() if k not in ("author", "sources")}
    reading = notes_paste.read_answer(json.dumps(bare), NEXT_GAME, now=NOW)
    assert reading.notes.author == notes_paste.PASTED_AUTHOR and reading.notes.writtenAt == "2026-09-23T16:00:00Z"
    assert any("No sources" in w for w in reading.warnings)
    linkless = notes_paste.read_answer(json.dumps({**GOOD, "sources": [{"label": "A paper"}]}), NEXT_GAME)
    assert any("no link" in w for w in linkless.warnings)


def test_wrong_types_and_bad_rows_are_left_out_not_fatal():
    junk = {**GOOD, "author": 5, "sections": "not a list", "availability": [1, None, {"name": "Ok", "status": "Out"}, {"status": "Out"}], "visitors": {"home": "nobody"}, "lineups": [], "writtenAt": {"when": "now"}}
    reading = notes_paste.read_answer(json.dumps(junk), NEXT_GAME, now=NOW)
    assert reading.notes is not None, reading.error
    assert reading.summary["availability"] == 1 and reading.notes.visitors is None and reading.notes.lineups is None and reading.notes.sections == []
    joined = " ".join(reading.warnings)
    assert '"author" could not be read' in joined and '"sections" could not be read' in joined and '"writtenAt" could not be read' in joined
    assert "rows or blocks could not be read" in joined
    assert reading.notes.author == notes_paste.PASTED_AUTHOR


@pytest.mark.parametrize("text, words", [
    ("", "Paste"),
    ("   ", "Paste"),
    (None, "Paste"),
    ("I could not find anything this week, sorry.", "No JSON object"),
    ('{"weather": "sunny", "score": [1, 2]}', "not notes"),
    ('{"gameId": 526001015, "sections": [], "availability": []}', "no notes in it"),
    ('[{"sections": []}]', "no notes in it"),  # a list around the object: the object is read, and it is empty
    ("{" * 50, "No JSON object"),
    ("x" * (notes_paste.MAX_PASTE + 1), "far shorter"),
], ids=["empty", "blank", "none", "words", "other-json", "empty-notes", "in-a-list", "braces", "too-long"])
def test_an_answer_with_nothing_usable_is_refused_with_a_reason(text, words):
    reading = notes_paste.read_answer(text, NEXT_GAME)
    assert reading.notes is None and words in (reading.error or ""), reading.error
    assert reading.as_dict()["ok"] is False


# --- the prompt ------------------------------------------------------------------------------------------


def test_placeholders_fill_by_name_and_stray_braces_stay():
    assert notes_paste.fill("{team} plays {opponent}; keep {this} and {{that}}", {"team": "A", "opponent": "B"}) == "A plays B; keep {this} and {{that}}"


def test_the_prompt_names_the_game_and_carries_the_shape(tmp_path: Path):
    class Who:
        school, name, conference = "Swampwater Tech", "Mudpuppies", "Biscuit Belt"

    game = {"gameId": NEXT_GAME, "home": "Swampwater Tech", "away": "Diner Tech", "kickoff": "2026-09-26T19:30:00Z"}
    from zoneinfo import ZoneInfo

    prompt = notes_paste.build_prompt(tmp_path, Who(), game, 2026, ZoneInfo("America/New_York"))
    assert "kickoff Saturday, September 26, 3:30 PM EDT" in prompt
    assert notes_paste.kickoff_text(None) == "time to be announced" and notes_paste.kickoff_text("soon") == "soon"
    assert "Diner Tech at Swampwater Tech" in prompt and str(NEXT_GAME) in prompt and "Biscuit Belt availability report" in prompt
    assert "The opponent is Diner Tech" in prompt and "```json" in prompt and "{shape}" not in prompt and "{team}" not in prompt
    shape = json.loads(notes_paste.shape_example("Swampwater Tech", "Diner Tech", "Biscuit Belt"))
    assert set(shape) >= {"gameId", "sections", "availability", "visitors", "lineups", "schemes", "sources"}
    reading = notes_paste.read_answer(json.dumps(shape), NEXT_GAME)  # the example itself reads cleanly
    assert reading.notes is not None and reading.warnings == []


def test_an_edited_prompt_is_used_and_an_old_file_writing_one_is_ignored(tmp_path: Path):
    notes_paste.write_template(tmp_path, "Notes for {game_id}, {team}. Shape: {shape} {unknown}")
    template, custom = notes_paste.read_template(tmp_path)
    assert custom and template.startswith("Notes for {game_id}")
    prompt = notes_paste.build_prompt(tmp_path, None, {"gameId": 7, "home": "A", "away": "B"}, 2026)
    assert prompt.startswith("Notes for 7, our team.") and "{unknown}" in prompt
    notes_paste.prompt_path(tmp_path).write_text("Write the file {notes_path} like {example_path}", encoding="utf-8")
    assert notes_paste.read_template(tmp_path) == (notes_paste.DEFAULT_PROMPT, False)
    notes_paste.write_template(tmp_path, None)
    assert not notes_paste.prompt_path(tmp_path).exists() and notes_paste.read_template(tmp_path)[1] is False
    notes_paste.write_template(tmp_path, None)  # removing twice is fine


# --- the API ---------------------------------------------------------------------------------------------


def test_copy_check_and_save_from_any_device(notes_app, client: TestClient, fake_cfbd: FakeCfbd):
    prompt = client.get("/api/notes/prompt").json()["data"]
    assert prompt["gameId"] == NEXT_GAME and "Swampwater Tech" in prompt["prompt"] and str(NEXT_GAME) in prompt["prompt"] and prompt["custom"] is False
    assert client.get("/api/notes/prompt?gameId=12345").status_code == 404
    data_dir = notes_app.state.settings.data_dir
    pasted = "Here you go:\n```json\n" + json.dumps({**GOOD, "gameId": 99}) + "\n```"
    preview = client.post("/api/notes/preview", json={"gameId": NEXT_GAME, "text": pasted}).json()["data"]
    assert preview["ok"] and any("game 99" in w for w in preview["warnings"])
    assert load_notes(data_dir, NEXT_GAME) == (None, None)  # a preview saves nothing
    saved = client.post("/api/notes/save", json={"gameId": NEXT_GAME, "text": pasted})
    assert saved.status_code == 200 and saved.json()["data"]["saved"] is True
    notes, error = load_notes(data_dir, NEXT_GAME)
    assert error is None and notes.gameId == NEXT_GAME and [s.heading for s in notes.sections] == ["Coaching matchup", "Key matchups"]
    calls = len(fake_cfbd.requests)
    again = client.post("/api/notes/save", json={"gameId": NEXT_GAME, "text": json.dumps({**GOOD, "sections": [{"heading": "Replaced", "paragraphs": []}]})})
    assert again.status_code == 200 and [s.heading for s in load_notes(data_dir, NEXT_GAME)[0].sections] == ["Replaced"]  # replaced, no confirm
    assert len(fake_cfbd.requests) == calls  # the schedule was cached; pasting costs nothing


def test_an_unusable_paste_is_refused_and_nothing_is_written(notes_app, client: TestClient):
    refused = client.post("/api/notes/save", json={"gameId": NEXT_GAME, "text": "Sorry, I can't browse."})
    assert refused.status_code == 422 and refused.json()["errors"][0]["code"] == "notes_unreadable"
    assert load_notes(notes_app.state.settings.data_dir, NEXT_GAME) == (None, None)
    assert client.post("/api/notes/save", json={"gameId": 12345, "text": json.dumps(GOOD)}).status_code == 404
    assert client.post("/api/notes/save", json={"gameId": 0, "text": "{}"}).status_code == 422
    assert client.post("/api/notes/save", json={"gameId": NEXT_GAME, "text": "x" * (notes_paste.MAX_PASTE + 1)}).status_code == 422


def test_the_prompt_template_is_read_edited_and_reset(notes_app, client: TestClient):
    first = client.get("/api/notes/template").json()["data"]
    assert first["custom"] is False and first["template"] == notes_paste.DEFAULT_PROMPT and "shape" in first["placeholders"]
    edited = client.put("/api/notes/template", json={"template": "Short notes for {game_id}: {team}.\r\n{shape}"}).json()["data"]
    assert edited["custom"] is True and edited["template"] == "Short notes for {game_id}: {team}.\n{shape}"
    assert client.get("/api/notes/prompt").json()["data"]["prompt"].startswith(f"Short notes for {NEXT_GAME}: Swampwater Tech.")
    missing = client.put("/api/notes/template", json={"template": "No game here"})
    assert missing.status_code == 422 and "{game_id}" in missing.json()["errors"][0]["message"]
    assert client.put("/api/notes/template", json={"template": "   "}).status_code == 422
    assert client.put("/api/notes/template", json={"template": notes_paste.DEFAULT_PROMPT}).json()["data"]["custom"] is False  # the default text is no edit
    client.put("/api/notes/template", json={"template": "Again {game_id}"})
    reset = client.delete("/api/notes/template").json()["data"]
    assert reset["custom"] is False and not notes_paste.prompt_path(notes_app.state.settings.data_dir).exists()


def test_saved_notes_show_on_the_game_program(notes_app, client: TestClient, fake_cfbd: FakeCfbd):
    from tests.test_program import route_program

    route_program(fake_cfbd)
    before = client.get(f"/api/program/{NEXT_GAME}").json()["data"]["notes"]
    assert before["present"] is False
    client.post("/api/notes/save", json={"gameId": NEXT_GAME, "text": json.dumps(GOOD)})
    after = client.get(f"/api/program/{NEXT_GAME}").json()["data"]["notes"]
    assert after["present"] is True and after["author"] == "A chat" and after["schemes"]["offense"] == "Spread, 11 personnel"
