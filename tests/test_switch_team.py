"""Switch teams (batch 3, owner 2026-11-16: "I want to be able to have all the features of our current my team, but it just
doesnt save"). A device switched to another team asks for that team's own next program; ours stays ours, a school not in
FBS is refused, and nothing is written for the other team. The page side (static/js/viewing.js, ui/team-switch.js) is
checked by the Node page tests on GitHub."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from tests.fakedom import needs_node, run_scenario
from tests.test_any_team import OTHER, lclient  # noqa: F401 - the league client fixture

ROOT = Path(__file__).resolve().parents[1]


def test_a_switched_device_gets_that_teams_own_next_program(lclient: TestClient):  # noqa: F811
    theirs = lclient.get(f"/api/program/next?team={quote(OTHER)}")
    assert theirs.status_code == 200, theirs.text[:300]
    data = theirs.json()["data"]
    assert data["us"]["school"] == OTHER and data["ours"] is False
    season = lclient.get(f"/api/season/overview?team={quote(OTHER)}").json()["data"]
    upcoming = [g for g in season["schedule"] if isinstance(g.get("gameId"), int) and not g.get("completed")]
    assert upcoming and data["game"]["gameId"] == upcoming[0]["gameId"], "its own next game, not ours"


def test_our_own_name_or_none_is_our_next_program(lclient: TestClient):  # noqa: F811
    ours = lclient.get("/api/program/next").json()["data"]
    named = lclient.get("/api/program/next?team=Florida").json()["data"]
    blank = lclient.get("/api/program/next?team=%20").json()["data"]
    assert ours["us"]["school"] == named["us"]["school"] == blank["us"]["school"] == "Florida"
    assert ours["game"]["gameId"] == named["game"]["gameId"] == blank["game"]["gameId"]


def test_a_school_not_in_fbs_is_refused(lclient: TestClient):  # noqa: F811
    refused = lclient.get("/api/program/next?team=No%20Such%20School")
    assert refused.status_code == 404 and refused.json()["errors"][0]["code"] == "unknown_team"
    assert "No Such School" in refused.json()["errors"][0]["message"]
    assert lclient.get("/api/program/next?team=" + "x" * 81).status_code == 422, "a name past 80 characters is refused"


def test_a_refused_switch_says_why(lclient: TestClient, monkeypatch):  # noqa: F811
    """Review 2026-11-19: a real team with no game ahead, and CFBD's team list unavailable, are not "no such team"."""
    service = lclient.app.state.program

    async def nothing(team):
        return None

    monkeypatch.setattr(service, "team_next", nothing)
    no_game = lclient.get(f"/api/program/next?team={quote(OTHER)}")
    assert no_game.status_code == 404 and no_game.json()["errors"][0]["code"] == "no_game"
    assert OTHER in no_game.json()["errors"][0]["message"] and "No FBS team" not in no_game.json()["errors"][0]["message"]
    unknown = lclient.get("/api/program/next?team=No%20Such%20School")
    assert unknown.status_code == 404 and unknown.json()["errors"][0]["code"] == "unknown_team"

    async def no_list(team):
        return None

    monkeypatch.setattr(service, "team_known", no_list)
    down = lclient.get(f"/api/program/next?team={quote(OTHER)}")
    assert down.status_code == 503 and down.json()["errors"][0]["code"] == "teams_unavailable"


def test_switching_writes_nothing_for_the_other_team(lclient: TestClient, settings):  # noqa: F811
    before = {p for p in Path(settings.data_dir).rglob("*") if p.is_file()}
    lclient.get(f"/api/program/next?team={quote(OTHER)}")
    lclient.get(f"/api/season/overview?team={quote(OTHER)}")
    after = {p for p in Path(settings.data_dir).rglob("*") if p.is_file()}
    written = sorted(str(p.relative_to(settings.data_dir)) for p in after - before)
    assert not [w for w in written if "lock" in w or "notes" in w or "book" in w], written


def test_the_switch_is_one_device_only_and_never_reaches_the_server():
    viewing = (ROOT / "static/js/viewing.js").read_text(encoding="utf-8")
    switch = (ROOT / "static/js/ui/team-switch.js").read_text(encoding="utf-8")
    assert "sessionStorage" in viewing and "localStorage" not in viewing, "this visit only"
    assert "fetch(" not in viewing and "method:" not in switch and "POST" not in switch, "nothing goes to the server"


VIEW_ROUTE = r"""
scenarios.viewRoute = async () => {
  await useTeam();
  const { setViewing, viewRoute, _resetViewing } = await import(moduleUrl("viewing.js"));
  _resetViewing();
  const bare = (id, arg = null, params = {}) => ({ id, arg, params });
  assert.deepEqual(viewRoute(bare("program")), bare("program"), "ours: nothing added");
  setViewing({ school: "Alabama" });
  assert.equal(viewRoute(bare("program")).params.team, "Alabama", "the bare Program follows the switch");
  assert.equal(viewRoute(bare("postgame")).params.team, "Alabama", "the bare Post-Game follows the switch");
  assert.equal(viewRoute(bare("season")).params.team, "Alabama");
  // review 2026-11-19: a game by id (the Archive, the Newspaper, Seasons, Last/Next) is a game of ours, seen from our side
  for (const id of ["program", "postgame"]) {
    const route = bare(id, "401856699");
    assert.equal(viewRoute(route), route, `#${id}=<game id> stays ours`);
  }
  const named = bare("season", null, { team: "Florida" });
  assert.equal(viewRoute(named), named, "a page that names its team keeps it");
  assert.equal(viewRoute(bare("archive")).params.team, undefined, "our own pages stay ours");
  _resetViewing();
};
"""


@needs_node
def test_a_game_by_id_stays_ours_on_a_switched_device(tmp_path: Path):
    run_scenario(tmp_path, VIEW_ROUTE, "viewRoute")
