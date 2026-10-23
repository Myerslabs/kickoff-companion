"""Season with My Teams (the layout pass, board 9, owner 2026-10-22: "I want my teams, and season to combine. Have a
selection window at the top, start with the primary and allow to switch between teams similar to the pre-game-program
weeks"). The Season answer for any followed team, the window's team list, the old My Teams address, and the page in the
fake browser: the window, its arrows and chips, the bands side by side ending flush, the College Football Playoff band
only while the team picked is in the AP Top 25, and a free key's window."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services import myteams, teamset
from app.services.prefs import Prefs
from tests.conftest import FakeCfbd, fixture_payload
from tests.fakedom import needs_node, run_scenario
from tests.test_myteams import HOME, OPPONENT, SLATE_SCHOOL, TEAMS, tier
from tests.test_p16_season_js import FIXTURE
from tests.test_season import route_season


def route_followed(fake: FakeCfbd) -> None:
    """route_season, with the team's own games filtered the way CFBD filters them (the fake's week answer otherwise)."""
    route_season(fake)

    def games(request: httpx.Request) -> httpx.Response:
        team = request.url.params.get("team")
        if team == HOME:
            return httpx.Response(200, json=fixture_payload("games_team"))
        week = fixture_payload("games_week")
        if team:
            return httpx.Response(200, json=[g for g in week if team in (g.get("homeTeam"), g.get("awayTeam"))])
        return httpx.Response(200, json=week)

    fake.route("/games", handler=games)


def test_the_home_teams_season_carries_the_window(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_followed(fake_cfbd)
    tier(app, 2)
    app.state.prefs.update({"primaryTeams": [OPPONENT], "likedTeams": [SLATE_SCHOOL]})
    data = client.get("/api/season/overview").json()["data"]
    picker = data["picker"]
    assert [t["school"] for t in picker["teams"]] == [HOME, OPPONENT, SLATE_SCHOOL], "the home team, the other primaries, then the secondary ones"
    assert [t["role"] for t in picker["teams"]] == ["home", "primary", "secondary"]
    assert picker["picked"] == HOME and picker["home"] == HOME and picker["allowed"] is True and picker["note"] is None
    meta = {t.school: t for t in TEAMS}
    assert picker["teams"][1]["abbreviation"] == meta[OPPONENT].abbreviation and picker["teams"][1]["color"] == meta[OPPONENT].color
    assert data["team"]["conferenceShort"], "the page names the team's conference in short"
    assert len(data["trends"]["gameIds"]) == len(data["trends"]["weeks"]), "the trends' columns are matched to the schedule by game id"


def test_another_followed_team_gets_its_own_season(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_followed(fake_cfbd)
    tier(app, 2)
    app.state.prefs.update({"primaryTeams": [OPPONENT]})
    client.get("/api/season/overview")  # the home team's page first: the shared parts are cached
    game_day = app.state.cfbd.game_day
    before = len(fake_cfbd.requests)
    response = client.get(f"/api/season/overview?team={quote(OPPONENT)}")
    assert response.status_code == 200
    data = response.json()["data"]
    conference = meta_conference = next(t.conference for t in TEAMS if t.school == OPPONENT)
    assert data["team"]["school"] == OPPONENT and data["team"]["conference"] == meta_conference
    assert data["picker"]["picked"] == OPPONENT and [t["school"] for t in data["picker"]["teams"]] == [HOME, OPPONENT]
    assert all(OPPONENT in (row["opponent"]["school"], data["team"]["school"]) for row in data["schedule"])
    asked = [(r.url.path, dict(r.url.params)) for r in fake_cfbd.requests[before:]]
    assert ("/games", {"year": str(app.state.settings.season), "team": OPPONENT}) in asked, "its own schedule"
    assert any(path == "/records" and params.get("conference") == conference for path, params in asked), "its conference's standings"
    assert not any(path in ("/rankings", "/teams/fbs", "/ratings/sp", "/stats/season") for path, _ in asked), "the shared parts come from the cache"
    us = [row for row in data["standings"] if row.get("isUs")]
    assert [row["team"] for row in us] == [OPPONENT] or not data["standings"], "the standings mark the team picked"
    assert app.state.cfbd.game_day == game_day, "another team's game day never speeds up our refreshes"


def test_only_a_followed_team_opens(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_followed(fake_cfbd)
    tier(app, 2)
    app.state.prefs.update({"primaryTeams": [OPPONENT], "likedTeams": ["No Such School"]})
    stranger = client.get(f"/api/season/overview?team={quote(SLATE_SCHOOL)}")
    assert stranger.status_code == 404 and stranger.json()["errors"][0]["code"] == "not_followed"
    gone = client.get("/api/season/overview?team=No%20Such%20School")
    assert gone.status_code == 404 and gone.json()["errors"][0]["code"] == "unknown_team"
    assert client.get(f"/api/season/overview?team={quote(HOME)}").json()["data"]["picker"]["picked"] == HOME, "the home team by name is the plain page"
    assert client.get("/api/season/overview?team=%20").json()["data"]["picker"]["picked"] == HOME, "a blank name is the home team"
    tier(app, 0)
    free = client.get(f"/api/season/overview?team={quote(OPPONENT)}")
    assert free.status_code == 404, "a free key follows the home team alone"
    picker = client.get("/api/season/overview").json()["data"]["picker"]
    assert [t["school"] for t in picker["teams"]] == [HOME] and picker["allowed"] is False and "Tier 2" in picker["note"]


def test_the_picker_and_the_note_survive_junk():
    chosen = teamset.resolve(HOME, Prefs(primaryTeams=[OPPONENT, "Nowhere U"]), True, TEAMS)
    picker = myteams.season_picker(chosen, [*TEAMS, "junk", None], OPPONENT)  # type: ignore[list-item]
    assert picker["picked"] == OPPONENT and [t["school"] for t in picker["teams"]][:2] == [HOME, OPPONENT]
    alone = myteams.season_picker(teamset.resolve(HOME, Prefs(), True, TEAMS), [], HOME)
    assert alone["teams"][0]["abbreviation"] is None and alone["teams"][0]["known"] is True, "no team list: nothing known, nothing refused"
    assert myteams.set_note(teamset.resolve(HOME, Prefs(), True, TEAMS), 1).startswith("Only your home team")
    assert myteams.set_note(teamset.resolve(HOME, Prefs(primaryTeams=[OPPONENT]), False, TEAMS), 1).startswith("More primary teams"), "saved picks a free key leaves out"
    assert myteams.set_note(teamset.resolve(HOME, Prefs(primaryTeams=[OPPONENT]), True, TEAMS), 2) is None


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");
const PICKER = {
  teams: [
    { school: "Swampwater Tech", abbreviation: "SWT", color: "#00838f", altColor: "#f2b705", role: "home" },
    { school: "Diner Tech", abbreviation: "DINR", color: "#1c957a", role: "primary" },
    { school: "Cactus Gulch", abbreviation: null, color: "not a color", role: "secondary" },
    null, "junk", { school: "" },
  ],
  picked: "Swampwater Tech", home: "Swampwater Tech", allowed: true, note: null, plansUrl: "https://collegefootballdata.com/api-tiers",
};

async function draw(data, params) {
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/season/overview", () => envelope(data));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createSeasonView({ params });
  view.mount(main);
  await settle();
  return { main, view };
}

scenarios.window = async () => {
  installWindow();
  const data = clone(FIXTURE.season);
  data.picker = clone(PICKER);
  data.record.apRank = null; // unranked: too far out of the playoff picture
  const { main, view } = await draw(data, {});
  const pick = main.querySelector(".season-pick");
  assert.ok(pick, "the window on top");
  assert.ok(!RAW.test(text(pick)), text(pick));
  assert.equal(text(pick.querySelector(".season-pick__name")), "Swampwater Tech");
  assert.ok(text(pick).includes("Home team"));
  assert.ok(pick.querySelector(".season-pick__arrow--prev.season-pick__arrow--off"), "the home team has no team before it");
  const next = pick.querySelector("a.season-pick__arrow--next");
  assert.equal(next.getAttribute("href"), "#season?team=Diner%20Tech");
  assert.equal(next.getAttribute("aria-label"), "Next team: Diner Tech", "the arrow names the team it goes to");
  const chips = pick.querySelectorAll("a.season-pick__team");
  assert.deepEqual(chips.map((a) => a.getAttribute("href")), ["#season", "#season?team=Diner%20Tech", "#season?team=Cactus%20Gulch"], "one chip a team; junk rows dropped");
  assert.equal(chips[0].getAttribute("aria-current"), "page");
  assert.ok(chips[0].className.includes("is-on") && !chips[1].className.includes("is-on"));
  assert.equal(text(chips[2].querySelector("i")), "Cactus Gulch", "no abbreviation: the school");
  assert.equal(text(pick.querySelector(".season-pick__count")), "1 of 3");
  assert.equal(pick.querySelector(".season-pick__change").getAttribute("href"), "#profile=teams");
  const facts = pick.querySelectorAll(".season-pick__fact");
  assert.deepEqual(facts.map((f) => text(f.querySelector("small"))), ["AP", "SP+", "Elo", "FPI", "Last", "Next"]);
  assert.equal(text(facts[0].querySelector("b")), "Unranked");
  assert.ok(text(facts[4]).includes("L") && text(facts[4]).includes("GRID"), "the last game: its result and the opponent's abbreviation");
  assert.ok(text(facts[5]).includes("MISS"), "the next game's opponent");
  assert.equal(main.querySelector("#season-playoff"), null, "unranked: no playoff band");
  // the bands side by side, flush: Schedule | Standings 2:1, Polls | Ratings over Résumé 1:2
  const r21 = main.querySelector(".flush-row--21");
  assert.deepEqual(r21.children.map((c) => c.getAttribute("id")), ["season-schedule", "season-standings"]);
  const r12 = main.querySelector(".flush-row--12");
  assert.equal(r12.children[0].getAttribute("id"), "season-polls");
  assert.deepEqual(r12.children[1].children.map((c) => c.getAttribute("id")), ["season-ratings", "season-resume"]);
  assert.ok(r12.children[1].className.includes("flush-stack"));
  const order = [...main.querySelectorAll("section.band[id]")].map((s) => s.getAttribute("id"));
  assert.deepEqual(order, ["season-schedule", "season-standings", "season-polls", "season-ratings", "season-resume", "season-profile", "season-trends", "season-advanced", "season-road", "season-last"], "today's order");
  assert.equal(window.location.hash === "" || typeof window.location.hash === "string", true);
  view.unmount();
};

scenarios.other = async () => {
  installWindow();
  const data = clone(FIXTURE.season);
  data.team = { school: "Diner Tech", abbreviation: "DINR", conference: "Gravy Ten", conferenceShort: "G10", color: "#1c957a" };
  data.picker = { ...clone(PICKER), picked: "Diner Tech" };
  data.record.apRank = 3;
  const { main, view } = await draw(data, { team: "Diner Tech" });
  assert.ok(calls.some((u) => u === "/api/season/overview?team=Diner%20Tech"), calls.join(" "));
  const pick = main.querySelector(".season-pick");
  assert.equal(text(pick.querySelector(".season-pick__name")), "Diner Tech");
  assert.ok(text(pick).includes("Primary team") && text(pick).includes("Gravy Ten"));
  assert.equal(pick.querySelector("a.season-pick__arrow--prev").getAttribute("href"), "#season", "back to the home team's plain address");
  assert.equal(pick.querySelector("a.season-pick__arrow--next").getAttribute("href"), "#season?team=Cactus%20Gulch");
  assert.equal(text(pick.querySelector(".season-pick__count")), "2 of 3");
  assert.equal(text(pick.querySelectorAll(".season-pick__fact b")[0]), "No. 3");
  assert.ok(main.querySelector("#season-playoff"), "in the AP Top 25: the playoff band shows");
  assert.ok(text(main.querySelector("#season-standings")).includes("G10 standings"), "its own conference's name");
  view.unmount();
};

scenarios.free = async () => {
  installWindow();
  const data = clone(FIXTURE.season);
  data.picker = { teams: [clone(PICKER.teams[0])], picked: "Swampwater Tech", home: "Swampwater Tech", allowed: false, note: "Add more primary teams and secondary teams with a Tier 2 key.", plansUrl: "https://collegefootballdata.com/api-tiers" };
  const { main, view } = await draw(data, {});
  const pick = main.querySelector(".season-pick");
  assert.ok(pick.className.includes("season-pick--alone"));
  assert.equal(pick.querySelectorAll(".season-pick__arrow").length, 0, "no arrows: nowhere to step");
  assert.equal(pick.querySelectorAll(".season-pick__team").length, 0, "no chips");
  const note = pick.querySelector(".season-pick__note");
  assert.ok(text(note).includes("Tier 2 key"));
  const link = note.querySelector("a");
  assert.equal(link.getAttribute("href"), "https://collegefootballdata.com/api-tiers");
  assert.equal(link.getAttribute("target"), "_blank");
  view.unmount();
  data.picker.plansUrl = "javascript:alert(1)";
  const again = await draw(data, {});
  assert.equal(again.main.querySelectorAll(".season-pick__note a").length, 0, "a bad plans link is never drawn");
  again.view.unmount();
  // no picker at all (an older server): the team alone, no crash
  const bare = clone(FIXTURE.season);
  const third = await draw(bare, {});
  assert.equal(text(third.main.querySelector(".season-pick__name")), "Swampwater Tech");
  assert.ok(!RAW.test(text(third.main.querySelector(".season-pick"))));
  third.view.unmount();
};

scenarios.helpers = async () => {
  installWindow();
  const { seasonHref, pickOrder, inTopTwentyFive, trendGames } = await import(moduleUrl("views/season.js"));
  assert.equal(seasonHref("Swampwater Tech", "Swampwater Tech"), "#season");
  assert.equal(seasonHref("Okra Valley", "Swampwater Tech"), "#season?team=Okra%20Valley");
  assert.equal(seasonHref(null, "Swampwater Tech"), "#season");
  assert.equal(seasonHref("  ", "Swampwater Tech"), "#season");
  const order = pickOrder(PICKER, "Cactus Gulch");
  assert.equal(order.at, 2);
  assert.equal(order.prev.school, "Diner Tech");
  assert.equal(order.next, null);
  assert.deepEqual(pickOrder(null, "X"), { teams: [], at: -1, prev: null, next: null });
  assert.equal(pickOrder(PICKER, "Somebody Else").prev, null, "a team not on the list steps nowhere");
  assert.equal(inTopTwentyFive({ record: { apRank: 25 } }), true);
  assert.equal(inTopTwentyFive({ record: { apRank: 26 } }), false);
  assert.equal(inTopTwentyFive({ record: { apRank: "3" } }), false);
  assert.equal(inTopTwentyFive(null), false);
  assert.deepEqual(trendGames(null), []);
  assert.deepEqual(trendGames({ trends: { gameIds: [9], weeks: [4], opponents: ["Diner Tech"] }, schedule: [] }).map((g) => g.opponent.school), ["Diner Tech"], "an id the schedule lacks: the trends' own opponent");
};

scenarios.grid = async () => {
  installWindow();
  const { trendGrid } = await import(moduleUrl("ui/sparkline.js"));
  assert.equal(trendGrid({ games: [] }), null);
  assert.equal(trendGrid({ games: "junk" }), null);
  const games = [
    { week: 1, homeAway: "home", opponent: { school: "Rhubarb State", abbreviation: "RHUB", color: "#80671f" }, result: "W", usPoints: 59, themPoints: 13 },
    { week: 2, homeAway: "away", opponent: { school: "Silver Dollar", color: "#ffffff" }, result: "L", usPoints: 27, themPoints: 35 },
    { postseason: "Bowl", homeAway: "neutral", opponent: {}, result: null },
  ];
  const grid = trendGrid({ games, metrics: [{ key: "points", label: "Points scored", values: [59, null, 30] }, { label: "Third down", values: [0.5, 0.4], format: "pct" }, null] });
  document.body.append(grid);
  assert.ok(!RAW.test(text(grid)), text(grid));
  const heads = grid.querySelectorAll(".tgrid__game");
  assert.deepEqual(heads.map((h) => text(h.querySelector(".tgrid__chip"))), ["RHUB", "SD", "–"], "the abbreviation, else the school's initials, else a dash");
  assert.deepEqual(heads.map((h) => text(h.querySelector(".tgrid__when"))), ["wk 1 · vs", "wk 2 · at", "bowl · n"]);
  assert.deepEqual(heads.map((h) => text(h.querySelector(".tgrid__score"))), ["W 59-13", "L 27-35", "–"]);
  const rows = grid.querySelectorAll(".tgrid__row").slice(1);
  assert.equal(rows.length, 3, "a junk metric is a row of dashes, never a crash");
  assert.deepEqual(rows[0].querySelectorAll(".tgrid__val").map(text), ["59", "–", "30"]);
  assert.equal(rows[0].querySelectorAll(".tgrid__dot").length, 2, "no value, no dot");
  assert.equal(rows[0].querySelectorAll("polyline").length, 0, "a missing game breaks the line");
  assert.deepEqual(rows[1].querySelectorAll(".tgrid__val").map(text), ["50%", "40%", "–"]);
  assert.equal(rows[1].querySelectorAll("polyline").length, 1);
  assert.equal(text(rows[1].querySelector(".tgrid__avgtext")), "avg 45%");
  assert.equal(text(rows[2].querySelector(".tgrid__avgtext")), "no games yet");
  assert.ok(rows[0].querySelector(".tgrid__dot").className.includes("is-win"));
  assert.equal(grid.style["--tg-n"], "3");
};
"""

NAMES = ["window", "other", "free", "helpers", "grid"]


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("season_myteams") / "fixture.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return path


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_season_with_my_teams_in_a_fake_browser(tmp_path: Path, fixture_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario, str(fixture_path))


def test_the_menu_lists_one_season_entry_and_the_old_address_opens_it() -> None:
    root = Path(__file__).resolve().parents[1] / "static" / "js"
    tree = (root / "ui" / "menu-tree.js").read_text(encoding="utf-8")
    assert 'page: "myteams"' not in tree, "board 9: My Teams and the Season are one page"
    assert tree.count('page: "season" }') == 1
    app = (root / "app.js").read_text(encoding="utf-8")
    assert "myteams: (opts, arg, focus, params) => createSeasonView({ ...opts, params })" in app
    assert not (root / "views" / "myteams.js").exists()
