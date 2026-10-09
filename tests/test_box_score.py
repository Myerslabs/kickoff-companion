"""Phase 17 #2: every W and L square on a cover opens that game. Ours open the archive or the program; any other
game opens the box score page (/api/box/{id}): the header from the season's game list, the team and player box
from /games/teams and /games/players once it is final, cached for good. A team page carries its conference's
standings, which the conference record chip opens."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import fixture_payload
from tests.test_program import LAST_GAME, route_program

OTHER_GAME = 526000065  # the opponent's week 1 game, no team of ours in it


@pytest.fixture(autouse=True)
def league(fake_cfbd):
    route_program(fake_cfbd)

    def games(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("games_team"))
        if params.get("team"):
            return httpx.Response(200, json=fixture_payload("games_opponent"))
        return httpx.Response(200, json=fixture_payload("games_week") + fixture_payload("games_team") + fixture_payload("games_opponent"))

    fake_cfbd.route("/games", handler=games)


def test_our_game_has_both_sides_and_player_lines(client):
    body = client.get(f"/api/box/{LAST_GAME}").json()
    data = body["data"]
    assert data["game"]["gameId"] == LAST_GAME and data["game"]["isOurs"] is True and data["game"]["completed"] is True
    assert data["final"]["available"] is True
    sides = [data["final"]["home"], data["final"]["away"]]
    assert all(isinstance(s, dict) and s["team"] for s in sides)
    assert data["final"]["players"]["home"] or data["final"]["players"]["away"]
    assert data["home"]["school"] and data["away"]["school"] and "logo" in data["home"]


def test_another_teams_game_has_its_header_and_says_when_the_box_is_missing(client):
    data = client.get(f"/api/box/{OTHER_GAME}").json()["data"]
    assert data["game"]["isOurs"] is False and data["home"]["school"] and data["away"]["school"]
    assert isinstance(data["home"]["points"], int)
    assert data["final"]["available"] is False, "the recorded week holds another game's box, which is not shown"


@pytest.mark.parametrize("bad", ["abc", "1" * 13, "999999999"])
def test_a_bad_id_is_404(client, bad):
    assert client.get(f"/api/box/{bad}").status_code == 404


def test_a_team_page_has_its_conference_standings(client):
    data = client.get("/api/team/Diner%20Tech").json()["data"]
    standings = data["standings"]
    assert standings["conference"] and standings["rows"]
    assert [r["place"] for r in standings["rows"]] == list(range(1, len(standings["rows"]) + 1))
    assert [r["team"] for r in standings["rows"] if r["isUs"]] == ["Diner Tech"], "the page's team is marked"
