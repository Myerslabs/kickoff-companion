"""Phase 19: the coaches prompt and the roster costs prompt each cover every conference in one paste (Settings cards)."""

from __future__ import annotations

import json

from app.services import season_all
from tests.conftest import CONFERENCE, TEAM, fixture_payload
from tests.test_season_notes import league  # noqa: F401 - routes the fake CFBD

EVERY = sorted(t["school"] for t in fixture_payload("teams_fbs"))
BY_CONFERENCE: dict[str, list[str]] = {}
for _t in fixture_payload("teams_fbs"):
    BY_CONFERENCE.setdefault(_t["conference"], []).append(_t["school"])


def coaches_answer(schools=EVERY, extra=()):
    teams = [{"school": s, "headCoach": f"Head {i}", "offensiveCoordinator": f"Off {i}", "defensiveCoordinator": f"Def {i}"} for i, s in enumerate(schools)]
    return "```json\n" + json.dumps({"season": 2026, "author": "Test chat", "teams": [*teams, *extra], "sources": [{"label": "Staffs", "url": "https://example.invalid/s"}]}) + "\n```"


def costs_answer(schools=EVERY):
    teams = [{"school": s, "totalUsd": 1_000_000 + i, "note": "rumored", "sources": [{"label": "Report", "url": "https://example.invalid/c"}]} for i, s in enumerate(schools)]
    return "```json\n" + json.dumps({"season": 2026, "author": "Test chat", "teams": teams}) + "\n```"


def test_the_prompts_list_every_conference(tmp_path):
    prompt = season_all.coaches_all_prompt(tmp_path, conferences=BY_CONFERENCE, season=2026)
    assert "every FBS conference" in prompt and f"{CONFERENCE}: " in prompt and EVERY[0] in prompt and "{shape}" not in prompt
    costs = season_all.costs_all_prompt(tmp_path, conferences=BY_CONFERENCE, detailed=[TEAM], season=2026)
    assert f"- {TEAM}" in costs and "every FBS conference" in costs


def test_a_coaches_answer_is_split_by_conference_and_strangers_left_out():
    reading = season_all.read_coaches_all(coaches_answer(extra=[{"school": "Nowhere U", "headCoach": "X"}]), BY_CONFERENCE)
    assert reading.value is not None and set(reading.value) == set(BY_CONFERENCE)
    assert sum(len(b.teams) for b in reading.value.values()) == len(EVERY)
    assert any("Nowhere U" in w for w in reading.warnings)
    partial = season_all.read_coaches_all(coaches_answer(schools=EVERY[:3]), BY_CONFERENCE)
    assert any("3 of" in w for w in partial.warnings)
    assert season_all.read_coaches_all(coaches_answer(schools=[], extra=[{"school": "Nowhere U", "headCoach": "X"}]), BY_CONFERENCE).value is None
    assert season_all.read_coaches_all("nothing", BY_CONFERENCE).value is None


def test_a_costs_answer_is_split_by_conference():
    reading = season_all.read_costs_all(costs_answer(), BY_CONFERENCE)
    assert reading.value is not None and reading.summary["totals"] == len(EVERY)
    assert season_all.read_costs_all(json.dumps({"teams": [{"school": "Nowhere U"}]}), BY_CONFERENCE).value is None


def test_the_routes_save_every_conference_at_once(client, league):  # noqa: F811
    for kind, answer in (("coaches", coaches_answer()), ("costs", costs_answer())):
        prompt = client.get("/api/season-notes/prompt", params={"kind": kind, "key": "all"})
        assert prompt.status_code == 200 and "every FBS conference" in prompt.json()["data"]["prompt"]
        saved = client.post("/api/season-notes/save", json={"kind": kind, "key": "all", "text": answer})
        assert saved.status_code == 200 and saved.json()["data"]["saved"] is True
    status = client.get("/api/season-notes").json()["data"]
    assert status["coachesSaved"] == len(EVERY) and status["costsSaved"] == len(EVERY)
    assert client.post("/api/season-notes/save", json={"kind": "coaches", "key": "all", "text": "nope"}).status_code == 422
