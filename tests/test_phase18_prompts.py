"""Phase 18.3: the one-paste season load and the readiness list."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.services import readiness, season_prompts
from app.services.notes import NotesFile
from tests.conftest import CONFERENCE, TEAM, fixture_payload
from tests.test_season_notes import SCHOOLS, league, preseason_answer  # noqa: F401 - the league fixture routes the fake CFBD

EVERY_SCHOOL = sorted(t["school"] for t in fixture_payload("teams_fbs"))


def season_answer(primaries=(TEAM,), schools=SCHOOLS, extra_coaches=(), extra_teams=()):
    teams = [{"school": p, "staff": [{"name": "Coach One", "role": "Head coach"}], "outlook": {"summary": "A good year ahead."}, "sources": [{"label": "Roster", "url": "https://example.invalid/r"}]} for p in primaries]
    teams += list(extra_teams)
    coaches = [{"school": s, "headCoach": f"Head {i}", "offensiveCoordinator": f"Off {i}", "defensiveCoordinator": f"Def {i}"} for i, s in enumerate(schools)] + list(extra_coaches)
    return "Here:\n```json\n" + json.dumps({"season": 2026, "author": "Test chat", "teams": teams, "coaches": coaches, "sources": [{"label": "Staffs", "url": "https://example.invalid/s"}]}) + "\n```"


def test_the_season_prompt_names_the_primaries_and_every_school(tmp_path):
    prompt = season_prompts.season_prompt(tmp_path, primaries=[TEAM], conferences={CONFERENCE: SCHOOLS}, season=2026)
    assert f"- {TEAM}" in prompt and f"{CONFERENCE}: " in prompt and SCHOOLS[0] in prompt and "{shape}" not in prompt and '"coaches"' in prompt
    assert season_prompts.template("season", tmp_path).check("no placeholders") is not None


def test_a_season_answer_splits_into_teams_and_conference_coaches():
    reading = season_prompts.read_season(season_answer(extra_coaches=[{"school": "Nowhere U", "headCoach": "X"}], extra_teams=[{"school": "Not Mine", "staff": [{"name": "A"}]}]), [TEAM], {CONFERENCE: SCHOOLS})
    assert reading.value is not None and list(reading.value["teams"]) == [TEAM]
    assert [r.school for r in reading.value["coaches"][CONFERENCE].teams] == SCHOOLS
    assert any("Not Mine" in w and "primary" in w for w in reading.warnings)
    assert reading.summary["coachTeams"] == len(SCHOOLS)


def test_a_partial_season_answer_still_saves_what_it_has_and_says_what_is_missing():
    reading = season_prompts.read_season(season_answer(schools=SCHOOLS[:2]), [TEAM, "Other Primary"], {CONFERENCE: SCHOOLS})
    assert reading.value is not None
    assert any("No preseason load for Other Primary" in w for w in reading.warnings) and any(f"Coaches for 2 of {len(SCHOOLS)}" in w for w in reading.warnings)


@pytest.mark.parametrize("junk", ["", "nothing", '{"other": 1}', json.dumps({"teams": [], "coaches": [], "season": 2026})])
def test_a_season_answer_with_nothing_usable_is_refused(junk):
    assert season_prompts.read_season(junk, [TEAM], {CONFERENCE: SCHOOLS}).value is None


def test_the_season_routes_save_everything_at_once(client, league):  # noqa: F811
    prompt = client.get("/api/season-notes/prompt", params={"kind": "season", "key": "all"}).json()["data"]["prompt"]
    assert TEAM in prompt and SCHOOLS[-1] in prompt
    saved = client.post("/api/season-notes/save", json={"kind": "season", "key": "all", "text": season_answer(schools=EVERY_SCHOOL)}).json()
    assert saved["data"]["saved"] is True
    status = client.get("/api/season-notes").json()["data"]
    assert status["preseason"][0]["savedAt"] and status["coachesSaved"] == len(EVERY_SCHOOL)
    page = client.get("/api/preseason").json()["data"]["teams"][0]
    assert page["preseason"]["outlook"]["summary"] == "A good year ahead." and page["coaches"]["headCoach"].startswith("Head ")
    assert client.post("/api/season-notes/save", json={"kind": "season", "key": "all", "text": "nope"}).status_code == 422


def status_with(**kw):
    base = {"season": 2026, "preseason": [{"school": TEAM, "savedAt": "2026-08-01T00:00:00Z"}], "coachesSaved": 136, "coachesOf": 136, "costsSaved": 136}
    return {**base, **kw}


def full_notes() -> NotesFile:
    return NotesFile.model_validate({"sections": [{"heading": "H", "paragraphs": ["p"]}], "availability": [{"name": "A"}], "lineups": {"us": {"slots": [{"slot": "QB", "players": [{"name": "A"}]}]}}, "broadcast": {"network": "ABC"}, "coaches": {"us": {"headCoach": "X"}}})


def test_nothing_is_missing_when_everything_is_loaded():
    result = readiness.readiness(status_with(), full_notes(), {"opponent": "Beta"}, date(2026, 10, 8))
    assert result == {"items": [], "ready": True}


def test_the_list_names_each_gap_with_a_link():
    result = readiness.readiness(status_with(preseason=[{"school": TEAM, "savedAt": None}], coachesSaved=100, costsSaved=0), None, {"opponent": "Beta"}, date(2026, 10, 8))
    ids = [i["id"] for i in result["items"]]
    assert ids == ["season", "costs", "notes"] and not result["ready"]
    season = result["items"][0]
    assert "preseason for" in season["detail"] and "100 of 136" in season["detail"] and season["href"] == "#preseason"
    assert result["items"][2]["href"] == "#program" and "Beta" in result["items"][2]["title"]


def test_half_written_notes_list_exactly_what_is_missing():
    notes = NotesFile.model_validate({"sections": [{"heading": "H", "paragraphs": ["p"]}], "availability": [{"name": "A"}]})
    detail = readiness.readiness(status_with(), notes, {"opponent": "Beta"})["items"][0]["detail"]
    assert detail == "Missing: both depth charts, the TV crew, the coaches."


def test_no_game_means_no_notes_item_and_bad_status_does_not_raise():
    assert readiness.readiness(status_with(), None, None)["ready"] is True
    assert readiness.readiness(None, None, None)["ready"] is True
    assert readiness.readiness({"preseason": ["junk", None], "coachesOf": "x"}, None, None)["ready"] is True


def test_the_readiness_route_answers_with_the_server_start(client, league):  # noqa: F811
    data = client.get("/api/readiness").json()["data"]
    assert data["serverStartedAt"].endswith("Z") and isinstance(data["items"], list)
    assert any(i["id"] == "season" for i in data["items"])  # nothing is loaded in a fresh test install
    client.post("/api/season-notes/save", json={"kind": "season", "key": "all", "text": season_answer(schools=EVERY_SCHOOL)})
    after = client.get("/api/readiness").json()["data"]
    assert not any(i["id"] == "season" for i in after["items"])
