"""Phase 17 Part 3b: rumored roster costs. The answer reader (lenient, strangers left out), the file (a total for
every team, position and player detail kept only for the primary teams), the routes, and where the figures show:
the Roster page, team pages and the Game program's talent table."""

from __future__ import annotations

import json

from app.services import season_prompts
from app.services.season_notes import SeasonNotes
from tests.conftest import CONFERENCE, TEAM, fixture_payload

SCHOOLS = sorted(t["school"] for t in fixture_payload("teams_fbs") if t["conference"] == CONFERENCE)
OTHER = next(s for s in SCHOOLS if s != TEAM)


def costs_answer(teams=None, extra=()):
    teams = teams if teams is not None else [
        {"school": TEAM, "totalUsd": 20500000, "note": "rumored", "asOf": "2026-08-01", "positions": [{"group": "Quarterbacks", "amountUsd": 4000000}, {"amountUsd": 5}], "players": [{"name": "Star Passer", "position": "QB", "amountUsd": 2500000}]},
        {"school": OTHER, "totalUsd": 15000000, "positions": [{"group": "Receivers", "amountUsd": 1}], "players": [{"name": "Not Primary", "amountUsd": 9}]},
        {"school": SCHOOLS[-1]},
    ]
    return "```json\n" + json.dumps({"conference": CONFERENCE, "author": "Test chat", "teams": teams + list(extra), "sources": [{"label": "Report", "url": "https://example.invalid/r"}]}) + "\n```"


def test_reading_a_costs_answer():
    reading = season_prompts.read_costs(costs_answer(extra=[{"school": "Somewhere Else", "totalUsd": 1}]), CONFERENCE, SCHOOLS)
    assert reading.value is not None and reading.summary["teams"] == 3 and reading.summary["totals"] == 2
    assert any("Not in the" in w for w in reading.warnings) and any("could not be read" in w for w in reading.warnings)
    assert season_prompts.read_costs(costs_answer(teams=[{"school": "Nowhere U"}]), CONFERENCE, SCHOOLS).value is None
    none = season_prompts.read_costs(costs_answer(teams=[{"school": TEAM}]), CONFERENCE, SCHOOLS)
    assert none.value is not None and any("No team total" in w for w in none.warnings)


def test_detail_is_kept_only_for_primary_teams(tmp_path):
    notes = SeasonNotes(tmp_path, 2026)
    batch = season_prompts.read_costs(costs_answer(), CONFERENCE, SCHOOLS).value
    notes.save_costs(batch, CONFERENCE, SCHOOLS, [TEAM])
    ours = notes.costs_for(TEAM)
    assert ours["totalUsd"] == 20500000 and [p["group"] for p in ours["positions"]] == ["Quarterbacks"] and ours["players"][0]["name"] == "Star Passer"
    theirs = notes.costs_for(OTHER)
    assert theirs["totalUsd"] == 15000000 and theirs.get("positions", []) == [] and theirs.get("players", []) == [], "a shallow search's detail on others is not kept"
    assert notes.costs_for(SCHOOLS[-1])["sources"][0]["label"] == "Report", "the batch's sources stand in"
    status = notes.status([TEAM], {CONFERENCE: SCHOOLS}, __import__("datetime").date(2026, 10, 8))
    assert status["costsSaved"] == 3 and status["costs"][0]["savedAt"]
    notes.costs_path.write_text(json.dumps({"teams": {TEAM: {"school": 5}, OTHER: {"school": OTHER, "totalUsd": 1}}}), encoding="utf-8")
    assert list(notes.costs()["teams"]) == [OTHER], "a damaged team is left out"


def test_routes_and_where_the_figures_show(client, fake_cfbd):
    from tests.test_program import route_program

    route_program(fake_cfbd)
    prompt = client.get("/api/season-notes/prompt", params={"kind": "costs", "key": CONFERENCE}).json()["data"]["prompt"]
    assert "rumored" in prompt and f"- {TEAM}" in prompt.split("For these schools only")[1], "our team is asked in detail"
    saved = client.post("/api/season-notes/save", json={"kind": "costs", "key": CONFERENCE, "text": costs_answer()}).json()
    assert saved["data"]["saved"] is True
    assert client.get("/api/season-notes").json()["data"]["costsSaved"] == 3
    assert client.get("/api/roster").json()["data"]["costs"]["totalUsd"] == 20500000
    assert client.get(f"/api/team/{OTHER}").json()["data"]["costs"]["totalUsd"] == 15000000
    program = client.get("/api/program/next").json()["data"]
    assert program["recruiting"]["us"]["costs"]["totalUsd"] == 20500000
    assert client.get("/api/preseason").json()["data"]["teams"][0]["costs"]["totalUsd"] == 20500000
    template = client.get("/api/season-notes/template", params={"kind": "costs"}).json()["data"]
    assert "{detailed}" in template["template"]
