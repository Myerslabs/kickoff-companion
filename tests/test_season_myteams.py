"""Season with My Teams (the layout pass, board 9, owner 2026-10-22: "I want my teams, and season to combine. Have a
selection window at the top, start with the primary and allow to switch between teams similar to the pre-game-program
weeks"). The Season answer for any followed team, the window's team list, the old My Teams address, and the page in the
fake browser: the window, its arrows and chips, the bands side by side ending flush, the College Football Playoff band
only while the team picked is in the AP Top 25, and a free key's window."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
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
    assert [(t["school"], t["role"]) for t in picker["teams"]] == [(HOME, "home")], "batch 3 (2026-11-19): one team; an older file's picks are read by nothing"
    assert picker["picked"] == HOME and picker["home"] == HOME and picker["allowed"] is True and picker["note"] is None
    meta = {t.school: t for t in TEAMS}
    assert picker["teams"][0]["abbreviation"] == meta[HOME].abbreviation and picker["teams"][0]["color"] == meta[HOME].color
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


def test_any_fbs_team_opens_and_a_made_up_name_does_not(app, client: TestClient, fake_cfbd: FakeCfbd):
    """FEAT-5 (owner 2026-10-25): every team the way the home team is seen; a team nobody follows comes last in the picker."""
    route_followed(fake_cfbd)
    tier(app, 2)
    app.state.prefs.update({"primaryTeams": [OPPONENT], "likedTeams": ["No Such School"]})
    stranger = client.get(f"/api/season/overview?team={quote(SLATE_SCHOOL)}")
    assert stranger.status_code == 200, stranger.text[:300]
    picker = stranger.json()["data"]["picker"]
    assert picker["picked"] == SLATE_SCHOOL and picker["teams"][-1]["school"] == SLATE_SCHOOL and picker["teams"][-1]["role"] == "viewing"
    assert [t["role"] for t in picker["teams"]].count("viewing") == 1
    gone = client.get("/api/season/overview?team=No%20Such%20School")
    assert gone.status_code == 404 and gone.json()["errors"][0]["code"] == "unknown_team"
    assert client.get(f"/api/season/overview?team={quote(HOME)}").json()["data"]["picker"]["picked"] == HOME, "the home team by name is the plain page"
    assert client.get("/api/season/overview?team=%20").json()["data"]["picker"]["picked"] == HOME, "a blank name is the home team"
    tier(app, 0)
    free = client.get(f"/api/season/overview?team={quote(OPPONENT)}")
    assert free.status_code == 200, "FEAT-5: any team's page still opens when someone asks for it, on any key"
    picker = client.get("/api/season/overview").json()["data"]["picker"]
    assert [t["school"] for t in picker["teams"]] == [HOME] and picker["note"] is None, "2.1, one team on every plan: nothing to add, no Tier 2 note"


def test_the_picker_is_our_team_and_the_one_changed_to():
    """Batch 3 (owner 2026-11-19: "Let's just have one team listed, and a change team for the switch"): our team, then the
    team this device changed to; no note, whatever an older settings file still holds."""
    picker = myteams.season_picker(teamset.resolve(HOME, Prefs(), True, TEAMS), [*TEAMS, "junk", None], OPPONENT)  # type: ignore[list-item]
    assert [(t["school"], t["role"]) for t in picker["teams"]] == [(HOME, "home"), (OPPONENT, "viewing")]
    assert picker["picked"] == OPPONENT and picker["note"] is None
    alone = myteams.season_picker(teamset.resolve(HOME, Prefs(), True, TEAMS), [], HOME)
    assert len(alone["teams"]) == 1 and alone["teams"][0]["abbreviation"] is None and alone["teams"][0]["known"] is True, "no team list: nothing known, nothing refused"


def test_the_team_set_is_the_home_team_alone(settings):
    """An older settings file's extra primaries and secondary teams are read by nothing."""
    old = SimpleNamespace(prefs=Prefs(primaryTeams=[OPPONENT], likedTeams=["Houston"], likedConferences=["SEC"], likedStates=["TX"]))
    chosen = teamset.current(settings, old, None, TEAMS)
    assert chosen.primaries == (settings.team,) and chosen.secondary == () and chosen.mine() == frozenset({settings.team})


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");
const PICKER = {
  teams: [
    { school: "Florida", abbreviation: "FLA", color: "#00838f", altColor: "#f2b705", role: "home" },
    { school: "Texas State", abbreviation: "TXST", color: "#1c957a", role: "primary" },
    { school: "Houston", abbreviation: null, color: "not a color", role: "secondary" },
    null, "junk", { school: "" },
  ],
  picked: "Florida", home: "Florida", allowed: true, note: null, plansUrl: "https://collegefootballdata.com/api-tiers",
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
  assert.ok(pick.querySelector("section.cover.cover--one"), "the cover on one team (2026-11-07) is the window");
  assert.equal(text(pick.querySelector(".cover__name")), "Florida");
  // batch 3 (owner 2026-11-19): one team listed, and Change team for the switch; no arrows, chips, count or role word
  assert.equal(pick.getAttribute("aria-label"), "Your team");
  assert.equal(pick.querySelectorAll(".season-pick__arrow").length, 0, "no team arrows");
  assert.equal(pick.querySelectorAll(".season-pick__team").length, 0, "no team chips, even from an older answer that lists more");
  assert.equal(pick.querySelector(".season-pick__count"), null);
  assert.ok(!text(pick).includes("Home team") && !text(pick).includes("Primary") && !text(pick).includes("Secondary"));
  const change = pick.querySelector("button.season-pick__change");
  assert.ok(change && text(change) === "Change team", "Change team opens the switch sheet");
  // the cover on one team (2026-11-07): the facts are the cover's chips, the last and the next game its middle
  const chipWords = pick.querySelectorAll(".cover-chip").map(text);
  assert.ok(chipWords.some((w) => w.startsWith("SP+ #")) && chipWords.some((w) => w.startsWith("Elo #")) && chipWords.some((w) => w.startsWith("FPI #")), chipWords.join(" | "));
  assert.equal(pick.querySelector(".poll-badge"), null, "unranked: no AP badge");
  // owner 2026-11-20: "remove the vanderbuilt part and just show the gators logo at the top for my team": our team alone,
  // centered, no next-game card, countdown or Last line (the Pre-Game Program has the next game)
  assert.ok(pick.querySelector(".cover.cover--alone"), "the cover on our team alone");
  assert.equal(pick.querySelector(".cover__center--one"), null);
  assert.equal(pick.querySelector('[data-k="pick:last"]'), null);
  assert.equal(pick.querySelector('[data-k="pick:next"]'), null);
  assert.ok(!text(pick).includes("to kickoff"), "no countdown");
  assert.equal(main.querySelector("#season-playoff"), null, "unranked: no playoff band");
  // one column (owner 2026-11-01): no flush rows, every band a child of the page in the order of board 9
  assert.equal(main.querySelector(".flush-row"), null);
  const page = main.querySelector(".page.season");
  assert.equal(page.dataset.cols, "1");
  const order = [...main.querySelectorAll("section.band[id]")].map((s) => s.getAttribute("id"));
  assert.deepEqual(order, ["season-schedule", "season-standings", "season-ratings", "season-resume", "season-profile", "season-trends", "season-road", "season-last", "season-numbers", "season-land", "season-injuries", "team-recruiting", "season-tendencies", "season-trip", "season-race", "roster-breakdown", "roster-costs", "roster-table", "roster-stars", "roster-impact", "recruiting-class", "recruiting-where", "team-staff", "team-playvalue", "team-facts", "season-stars", "season-lineup"], "today's order: the season's bands (the polls left for the Newspaper), then the bands that joined My Team in the inventory's order (wave 3, 2026-11-01; here each late band's host holds its band at its id, loaded or not)");
  const wrapped = order.filter((id) => { const n = main.querySelector(`#${id}`); return n.parentNode !== page && n.parentNode.parentNode !== page; });
  assert.deepEqual(wrapped, [], "every band a child of the page, or of its own host on the page (one column, 2026-11-01)");
  assert.equal(window.location.hash === "" || typeof window.location.hash === "string", true);
  view.unmount();
};

scenarios.other = async () => {
  installWindow();
  const data = clone(FIXTURE.season);
  data.team = { school: "Texas State", abbreviation: "TXST", conference: "Big Ten", conferenceShort: "B1G", color: "#1c957a" };
  data.picker = { ...clone(PICKER), teams: [clone(PICKER.teams[0]), { school: "Texas State", abbreviation: "TXST", color: "#1c957a", role: "viewing" }], picked: "Texas State" };
  data.record.apRank = 3;
  // opened by name with no switch (a flyout's Full page): not ours, but not changed on this device either
  const { setViewing, _resetViewing } = await import(moduleUrl("viewing.js"));
  _resetViewing();
  const named = await draw(clone(data), { team: "Texas State" });
  const namedText = text(named.main.querySelector(".season-pick"));
  assert.ok(namedText.includes("Not your team") && !namedText.includes("Changed on this device"), namedText);
  named.view.unmount();
  // the device switched to that team: it says so
  setViewing({ school: "Texas State" });
  const { main, view } = await draw(data, { team: "Texas State" });
  assert.ok(calls.some((u) => u === "/api/season/overview?team=Texas%20State"), calls.join(" "));
  const pick = main.querySelector(".season-pick");
  assert.equal(text(pick.querySelector(".cover__name")), "Texas State");
  assert.ok(text(pick).includes("Changed on this device") && text(pick).includes("Big Ten"), text(pick));
  assert.equal(pick.querySelectorAll(".season-pick__arrow").length, 0, "no arrows: Back to our team is the top bar's");
  assert.ok(text(pick.querySelector(".poll-badge")).includes("3"), "the AP badge on the cover");
  assert.equal(pick.querySelector(".rail"), null, "another team's page carries no rail");
  assert.ok(main.querySelector("#season-playoff"), "in the AP Top 25: the playoff band shows");
  assert.ok(text(main.querySelector("#season-standings")).includes("B1G standings"), "its own conference's name");
  view.unmount();
  _resetViewing();
};

scenarios.free = async () => {
  installWindow();
  const data = clone(FIXTURE.season);
  data.picker = { teams: [clone(PICKER.teams[0])], picked: "Florida", home: "Florida", allowed: false, note: "Add more primary teams and secondary teams with a Tier 2 key.", plansUrl: "javascript:alert(1)" };
  const { main, view } = await draw(data, {});
  const pick = main.querySelector(".season-pick");
  assert.equal(pick.querySelectorAll(".season-pick__arrow").length, 0, "no arrows: nowhere to step");
  assert.equal(pick.querySelectorAll(".season-pick__team").length, 0, "no chips");
  assert.equal(pick.querySelector(".season-pick__note"), null, "an older answer's note about more teams is never drawn");
  assert.equal(pick.querySelectorAll("a").filter((a) => /^javascript:/i.test(a.getAttribute("href") || "")).length, 0, "no script link from an older answer");
  view.unmount();
  // no picker at all (an older server): the team alone, no crash
  const bare = clone(FIXTURE.season);
  const third = await draw(bare, {});
  assert.equal(text(third.main.querySelector(".cover__name")), "Florida");
  assert.ok(!RAW.test(text(third.main.querySelector(".season-pick"))));
  third.view.unmount();
};

scenarios.helpers = async () => {
  installWindow();
  const { seasonHref, pickOrder, inTopTwentyFive, trendGames } = await import(moduleUrl("views/season.js"));
  assert.equal(seasonHref("Florida", "Florida"), "#season");
  assert.equal(seasonHref("Georgia", "Florida"), "#season?team=Georgia");
  assert.equal(seasonHref(null, "Florida"), "#season");
  assert.equal(seasonHref("  ", "Florida"), "#season");
  const order = pickOrder(PICKER, "Houston");
  assert.equal(order.at, 2);
  assert.equal(order.prev.school, "Texas State");
  assert.equal(order.next, null);
  assert.deepEqual(pickOrder(null, "X"), { teams: [], at: -1, prev: null, next: null });
  assert.equal(pickOrder(PICKER, "Somebody Else").prev, null, "a team not on the list steps nowhere");
  assert.equal(inTopTwentyFive({ record: { apRank: 25 } }), true);
  assert.equal(inTopTwentyFive({ record: { apRank: 26 } }), false);
  assert.equal(inTopTwentyFive({ record: { apRank: "3" } }), false);
  assert.equal(inTopTwentyFive(null), false);
  assert.deepEqual(trendGames(null), []);
  assert.deepEqual(trendGames({ trends: { gameIds: [9], weeks: [4], opponents: ["Texas State"] }, schedule: [] }).map((g) => g.opponent.school), ["Texas State"], "an id the schedule lacks: the trends' own opponent");
};

scenarios.grid = async () => {
  installWindow();
  const { trendGrid } = await import(moduleUrl("ui/sparkline.js"));
  assert.equal(trendGrid({ games: [] }), null);
  assert.equal(trendGrid({ games: "junk" }), null);
  const games = [
    { week: 1, homeAway: "home", opponent: { school: "Akron", abbreviation: "AKR", color: "#80671f" }, result: "W", usPoints: 59, themPoints: 13 },
    { week: 2, homeAway: "away", opponent: { school: "Fresno State", color: "#ffffff" }, result: "L", usPoints: 27, themPoints: 35 },
    { postseason: "Bowl", homeAway: "neutral", opponent: {}, result: null },
  ];
  const grid = trendGrid({ games, metrics: [{ key: "points", label: "Points scored", values: [59, null, 30] }, { label: "Third down", values: [0.5, 0.4], format: "pct" }, null] });
  document.body.append(grid);
  assert.ok(!RAW.test(text(grid)), text(grid));
  const heads = grid.querySelectorAll(".tgrid__game");
  assert.deepEqual(heads.map((h) => text(h.querySelector(".tgrid__chip"))), ["AKR", "FS", "–"], "the abbreviation, else the school's initials, else a dash");
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
    catalog = (root / "ui" / "band-catalog.js").read_text(encoding="utf-8")  # the page's name and address are the catalog's
    assert tree.count('pageRow("season"') == 1 and 'pageList("season")' not in tree, "My Team (owner 2026-11-01): one row; ENH-46 (2026-11-10): it opens the page, the team page's bands on it"
    assert 'label: "My Team"' in catalog
    assert '"team-bands"' not in tree and 'pageList("team")' not in tree, "the team page's own row and list are gone"
    assert catalog.count('route: "season"') == 1
    app = (root / "app.js").read_text(encoding="utf-8")
    assert "myteams: (opts, arg, focus, params) => createSeasonView({ ...opts, params })" in app
    assert not (root / "views" / "myteams.js").exists()
