"""Post-freeze Wave 1 (2026-10-25): a roster whose classes cannot be believed. CFBD's 2026 roster of the owner's team lists all 117 players
as year 1, so the Roster breakdown called every player a freshman. Nearly one class across a full roster is not believed: each
player's class comes from his recruiting class, else last season's roster, else it is unknown, and the page says so."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.services.classes import INFERRED_NOTE, degenerate, inferred_year
from tests.conftest import FakeCfbd, fixture_payload
from tests.test_players import route_players


def test_nearly_one_class_across_a_full_roster_is_not_believed():
    assert degenerate([1] * 117)
    assert degenerate([1] * 108 + [2] * 9), "nine in ten in one class"
    assert not degenerate([1] * 100 + [2] * 17)
    assert not degenerate([1, 2, 3, 4] * 30), "a real roster"
    assert not degenerate([1] * 30), "too few players to judge"
    assert not degenerate([None, "x", True, 0] * 40), "nothing usable is no verdict"


def test_the_inferred_class_comes_from_the_recruiting_class_then_last_season():
    assert inferred_year(None, 2023, 2026) == 4, "the class of 2023 is in its fourth season"
    assert inferred_year(None, 2026, 2026) == 1
    assert inferred_year(None, 2021, 2026) == 6, "beyond four: a senior with a redshirt (class_fields)"
    assert inferred_year(3, 2023, 2026) == 4, "the recruiting class wins over the roster"
    assert inferred_year(3, None, 2026) == 3, "CFBD's older rosters carry the current class"
    assert inferred_year(None, 2027, 2026) is None, "a future class is no evidence"
    assert inferred_year(None, None, 2026) is None and inferred_year("x", True, None) is None


def _one_class(fake: FakeCfbd) -> None:
    """Florida's 2026 roster with every player listed as year 1, the rest of the league as recorded."""
    flat = [{**row, "year": 1} for row in fixture_payload("roster")]

    def roster(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") == "Florida" and params.get("year") == "2026":
            return httpx.Response(200, json=flat)
        if params.get("team") != "Florida":
            return httpx.Response(200, json=fixture_payload("roster_opponent"))
        return httpx.Response(200, json=fixture_payload(f"roster_{params.get('year')}"))

    fake.route("/roster", handler=roster)


def test_the_roster_page_infers_the_classes_and_says_so(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    _one_class(fake_cfbd)
    data = client.get("/api/roster").json()["data"]
    assert data["classesInferred"] == INFERRED_NOTE
    assert fake_cfbd.count("/roster") == 2, "one more call: last season's roster"
    classes = {p["classYear"] for p in data["players"]}
    assert len(classes - {None}) >= 3, f"not every player a freshman any more: {classes}"
    recruited = {r["id"]: r["year"] for y in (2023, 2024, 2025) for r in fixture_payload(f"recruiting_players_{y}") if isinstance(r, dict)}
    label = {1: "FR", 2: "SO", 3: "JR", 4: "SR"}
    checked = 0
    for player in data["players"]:
        row = next(r for r in fixture_payload("roster") if r["id"] == player["playerId"])
        year = next((recruited[i] for i in row.get("recruitIds") or [] if i in recruited), None)
        if year is not None:
            assert player["classYear"] == label[min(2026 - year + 1, 4)], (player["name"], year, player["classYear"])
            checked += 1
    assert checked >= 10, "the recruiting classes decide most of them"


def test_a_believable_roster_costs_no_extra_call(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    data = client.get("/api/roster").json()["data"]
    assert data["classesInferred"] is None and fake_cfbd.count("/roster") == 1


def test_the_team_page_infers_them_too(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    _one_class(fake_cfbd)
    body = client.get("/api/team/Florida").json()
    data = body["data"]
    assert data["classesInferred"] == INFERRED_NOTE
    assert len({p["classYear"] for p in data["roster"]} - {None}) >= 3
