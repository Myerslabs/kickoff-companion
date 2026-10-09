"""Phase 17 Part 3a: the season prompts. The shared answer reader, the preseason and coaches answers (lenient: a bad row
dropped, a stranger left out, warnings never refusals), the files they save into (a batch replaces only its own
teams), ages from birthdates, the routes, the Claude Code queue with a fake tool, and where the data shows: the
Game program's coaches when the notes name none, the team page's staff and ages, the roster's ages."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.services import season_prompts
from app.services.answers import keys_score, read_json
from app.services.season_notes import CoachesBatch, PreseasonTeam, SeasonNotes, age_on, name_key
from tests.conftest import CONFERENCE, TEAM, fixture_payload

SCHOOLS = sorted(t["school"] for t in fixture_payload("teams_fbs") if t["conference"] == CONFERENCE)
ROSTER = fixture_payload("roster")
PLAYER = ROSTER[0]
PLAYER_NAME = f"{PLAYER['firstName']} {PLAYER['lastName']}"


def coaches_answer(schools=SCHOOLS[:3], extra=()):
    teams = [{"school": s, "headCoach": f"Head {i}", "offensiveCoordinator": f"Off {i}", "defensiveCoordinator": f"Def {i}"} for i, s in enumerate(schools)]
    teams += list(extra)
    return "Here you go:\n```json\n" + json.dumps({"conference": CONFERENCE, "season": 2026, "author": "Test chat", "teams": teams, "sources": [{"label": "Staff list", "url": "https://example.invalid/staff"}]}) + "\n```\nDone."


def preseason_answer(school=TEAM, **team):
    body = {"school": school, "staff": [{"name": "Coach One", "role": "Head coach"}, {"role": "no name"}],
            "birthdates": [{"name": PLAYER_NAME + " Jr.", "number": PLAYER.get("jersey"), "born": "2005-11-03"}, {"name": "Bad Date", "born": "next year"}, {"name": "Too Old", "born": "1960-01-01"}],
            "departures": [{"name": "Gone Guy", "kind": "NFL draft", "detail": "Round 3"}], "outlook": {"summary": "A good year ahead.", "predictions": [{"title": "Preseason poll", "detail": "No. 20"}]},
            "injuries": [{"name": "Hurt Guy", "status": "Out for the season"}], "programFacts": [{"title": "A tradition"}], "sources": [{"label": "Roster", "url": "https://example.invalid/roster"}], **team}
    return "```json\n" + json.dumps({"season": 2026, "author": "Test chat", "teams": [body]}) + ",\n```"  # a trailing comma is forgiven


# --- the reader and the models --------------------------------------------------------------------------------


def test_the_shared_reader_finds_validates_and_forgives():
    parsed = read_json(coaches_answer(), CoachesBatch, keys_score(("teams",)), max_chars=100, what="x", keys_text="teams")
    assert parsed.value is None and "characters" in parsed.error, "too long for its limit"
    for junk, says in [("", "Paste"), ("no json here", "No JSON"), ('{"other": 1}', "none of")]:
        assert says in season_prompts.read_coaches(junk, CONFERENCE, SCHOOLS).error


def test_names_and_ages():
    assert name_key("D'Andre Smith-Jones Jr.") == "dandre smith jones" and name_key("José Núñez III") == "jose nunez" and name_key(5) is None
    assert age_on(date(2005, 11, 3), date(2026, 11, 2)) == 20 and age_on(date(2005, 11, 3), date(2026, 11, 3)) == 21


def test_a_preseason_answer_keeps_good_rows_and_warns():
    reading = season_prompts.read_preseason(preseason_answer(), TEAM)
    team = reading.value
    assert isinstance(team, PreseasonTeam) and [m.name for m in team.staff] == ["Coach One"]
    assert [b.name for b in team.birthdates] == [PLAYER_NAME + " Jr."], "a bad date and an impossible year are dropped"
    assert any("could not be read" in w for w in reading.warnings)
    other = season_prompts.read_preseason(preseason_answer(school="Someone Else"), TEAM)
    assert other.value is not None and any("Saving puts it on" in w for w in other.warnings)
    empty = season_prompts.read_preseason("```json\n" + json.dumps({"teams": [{"school": TEAM}]}) + "\n```", TEAM)
    assert empty.value is None and "nothing in it" in empty.error


def test_a_coaches_answer_leaves_strangers_out():
    reading = season_prompts.read_coaches(coaches_answer(extra=[{"school": "Not In This League"}, {"headCoach": "No school"}]), CONFERENCE, SCHOOLS)
    assert reading.value is not None and reading.summary["teams"] == 3
    assert any("Not in the" in w for w in reading.warnings) and any("No staff for" in w for w in reading.warnings)
    assert season_prompts.read_coaches(coaches_answer(schools=[], extra=[{"school": "Nowhere U"}]), CONFERENCE, SCHOOLS).value is None


def test_the_files_merge_by_batch_and_survive_damage(tmp_path):
    notes = SeasonNotes(tmp_path, 2026)
    batch = season_prompts.read_coaches(coaches_answer(), CONFERENCE, SCHOOLS).value
    kept = notes.save_coaches(batch, CONFERENCE, SCHOOLS)
    assert kept["kept"] == SCHOOLS[:3] and len(kept["missing"]) == len(SCHOOLS) - 3
    again = season_prompts.read_coaches(coaches_answer(schools=SCHOOLS[3:5]), CONFERENCE, SCHOOLS).value
    notes.save_coaches(again, CONFERENCE, SCHOOLS)
    assert len(notes.coaches()["teams"]) == 5, "a batch replaces only its own teams"
    assert notes.coaches_for(SCHOOLS[0])["offensiveCoordinator"] == "Off 0"
    notes.save_preseason(season_prompts.read_preseason(preseason_answer(), TEAM).value, TEAM, "Test chat")
    assert notes.age(TEAM, PLAYER_NAME, date(2026, 10, 8)) == (20, "2005-11-03")
    assert notes.age(TEAM, "Nobody Here", date(2026, 10, 8)) == (None, None)
    status = notes.status([TEAM, "Other Primary"], {CONFERENCE: SCHOOLS}, date(2026, 8, 15))
    assert status["preseason"][0]["counts"]["birthdates"] == 1 and status["preseason"][1]["savedAt"] is None
    assert status["coachesSaved"] == 5 and status["remind"] is True
    assert notes.status([TEAM], {}, date(2026, 8, 15))["remind"] is False, "everything loaded: no reminder"
    notes.coaches_path.write_text("{broken", encoding="utf-8")
    notes.preseason_path.write_text(json.dumps({"teams": {TEAM: {"school": 5}, "Fine": {"school": "Fine"}}}), encoding="utf-8")
    assert notes.coaches()["teams"] == {} and list(SeasonNotes(tmp_path, 2026).preseason()) == ["Fine"]


def test_templates_fill_check_and_reset(tmp_path):
    t = season_prompts.template("coaches", tmp_path)
    prompt = season_prompts.coaches_prompt(tmp_path, conference=CONFERENCE, schools=SCHOOLS[:2], season=2026)
    assert CONFERENCE in prompt and f"- {SCHOOLS[0]}" in prompt and "{shape}" not in prompt
    assert t.check("no placeholder") and t.check("") and t.check("{schools} ok") is None
    t.write("Custom {schools} {conference}")
    assert t.read() == ("Custom {schools} {conference}", True)
    t.write(None)
    assert t.read()[1] is False
    with pytest.raises(ValueError):
        season_prompts.template("nope", tmp_path)


# --- the routes and where the data shows ----------------------------------------------------------------------


@pytest.fixture
def league(fake_cfbd):
    from tests.test_program import route_program

    route_program(fake_cfbd)
    return fake_cfbd


def test_the_routes(client, league, app):
    status = client.get("/api/season-notes").json()["data"]
    assert [r["school"] for r in status["preseason"]] == [TEAM]
    assert any(b["conference"] == CONFERENCE and b["schools"] == len(SCHOOLS) for b in status["coaches"])
    prompt = client.get("/api/season-notes/prompt", params={"kind": "preseason", "key": TEAM}).json()["data"]["prompt"]
    assert TEAM in prompt and "birthdates" in prompt
    assert client.get("/api/season-notes/prompt", params={"kind": "preseason", "key": "Not Mine"}).status_code == 404
    assert client.get("/api/season-notes/prompt", params={"kind": "coaches", "key": "No Such Conference"}).status_code == 404
    bad = client.post("/api/season-notes/save", json={"kind": "coaches", "key": CONFERENCE, "text": "nothing"})
    assert bad.status_code == 422
    saved = client.post("/api/season-notes/save", json={"kind": "coaches", "key": CONFERENCE, "text": coaches_answer(schools=SCHOOLS)}).json()
    assert saved["data"]["saved"] is True
    assert client.post("/api/season-notes/save", json={"kind": "preseason", "key": TEAM, "text": preseason_answer()}).json()["data"]["saved"] is True
    page = client.get("/api/preseason").json()["data"]
    ours = page["teams"][0]
    assert ours["school"] == TEAM and ours["preseason"]["outlook"]["summary"] == "A good year ahead." and ours["coaches"]["headCoach"]
    template = client.put("/api/season-notes/template", params={"kind": "coaches"}, json={"template": "Custom {schools} {conference} {season} {shape}"}).json()["data"]
    assert template["custom"] is True
    assert client.put("/api/season-notes/template", params={"kind": "coaches"}, json={"template": "no batch tie"}).status_code == 422
    assert client.delete("/api/season-notes/template", params={"kind": "coaches"}).json()["data"]["custom"] is False
    assert client.get("/api/season-notes/template", params={"kind": "nope"}).status_code == 404


def test_coaches_ages_and_staff_show_where_they_belong(client, league, app):
    app.state.cfbd._clock = lambda: datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)
    client.post("/api/season-notes/save", json={"kind": "coaches", "key": CONFERENCE, "text": coaches_answer(schools=SCHOOLS)})
    client.post("/api/season-notes/save", json={"kind": "preseason", "key": TEAM, "text": preseason_answer()})
    program = client.get("/api/program/next").json()["data"]
    us = program["notes"]["coaches"]["us"]
    assert us["headCoach"].startswith("Head ") and us["offensiveCoordinator"].startswith("Off "), "filled from the season load"
    team = client.get(f"/api/team/{TEAM}").json()["data"]
    assert team["staff"]["offensiveCoordinator"].startswith("Off ") and team["staff"]["full"][0]["name"] == "Coach One"
    aged = next(r for r in team["roster"] if r["name"] == PLAYER_NAME)
    assert aged["age"] == 20 and aged["born"] == "2005-11-03"
    roster = client.get("/api/roster").json()["data"]
    hit = next(r for r in roster["players"] if r.get("playerId") == str(PLAYER["id"]))
    assert hit["age"] == 20 and hit["born"] == "2005-11-03"
    others = [r for r in roster["players"] if r.get("playerId") != str(PLAYER["id"])]
    assert others and all(r["age"] is None for r in others), "no birthdate, no age"


def test_claude_code_runs_a_batch_queue(client, league, app, tmp_path: Path):
    answer = coaches_answer(schools=SCHOOLS[:2]).replace("\n", " ")
    if sys.platform.startswith("win"):
        tool = tmp_path / "fake-claude.cmd"
        tool.write_text(f"@echo off\r\necho {answer.replace('`', '')}\r\n", encoding="utf-8")
    else:
        tool = tmp_path / "fake-claude"
        tool.write_text(f"#!/bin/sh\necho '{answer}'\n", encoding="utf-8")
        os.chmod(tool, 0o755)
    app.state.settings.claude_command = str(tool)
    started = client.post("/api/season-notes/run", json={"kind": "coaches", "keys": [CONFERENCE]}).json()
    assert started["errors"] == [] and started["data"]["of"] == 1
    for _ in range(100):
        status = client.get("/api/season-notes/run").json()["data"]
        if not status["running"]:
            break
        time.sleep(0.1)
    batch = status["batches"][0]
    assert batch["state"] == "saved", batch
    assert app.state.season_notes.coaches_for(SCHOOLS[0])["headCoach"] == "Head 0"
    app.state.settings.claude_command = str(tmp_path / "missing-tool")
    refused = client.post("/api/season-notes/run", json={"kind": "coaches"}).json()
    assert refused["errors"] and "not found" in refused["errors"][0]["message"]

