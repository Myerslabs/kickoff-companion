"""Phase 17 #2 in the fake browser: every W and L square on the cover opens its game (ours: the Archive when it
holds it, else the program; any other: the box score page), the conference record chip opens the standings (ours on
the Season page, another conference's on that team's page), the box score page draws both teams with damaged
fields as dashes, and a team page carries its conference's standings and opens there from the chip."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 300))}`);
  return t;
};
const proto = Object.getPrototypeOf(document.body);
proto.scrollIntoView = function () {};

async function mountView(factory, url, data, opts = {}) {
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route(url, () => envelope(clone(data)));
  const main = document.createElement("main");
  document.body.append(main);
  const view = factory(opts);
  view.mount(main);
  await settle();
  return { main, view };
}

scenarios.links = async () => {
  const { formGuide, formHref, standingsHref } = await import(moduleUrl("ui/cover.js"));
  assert.equal(formHref({ gameId: 5, archived: true }, true), "#archive=5");
  assert.equal(formHref({ gameId: "6" }, true), "#program=6");
  assert.equal(formHref({ gameId: 7 }, false), "#box=7");
  for (const bad of [{}, { gameId: null }, { gameId: "x1" }, { gameId: NaN }, null]) assert.equal(formHref(bad, false), null);
  const us = { school: "Us State", conference: "Big Pie" };
  assert.equal(standingsHref(us, us), "#season?band=standings");
  assert.equal(standingsHref({ school: "Same Conf", conference: "Big Pie" }, us), "#season?band=standings");
  assert.equal(standingsHref({ school: "Far Away U", conference: "Other" }, us), "#team=Far%20Away%20U?band=standings");
  assert.equal(standingsHref({}, us), null);
  const form = [{ gameId: 1, result: "W", points: 21, opponentPoints: 7, opponent: "A" }, { gameId: null, result: "L" }, { result: "Q" }, null];
  const linked = formGuide(form, { hrefFor: (g) => formHref(g, false) });
  document.body.append(linked);
  const links = linked.querySelectorAll("a");
  assert.equal(links.length, 1);
  assert.equal(links[0].getAttribute("href"), "#box=1");
  assert.equal(linked.querySelectorAll(".form-guide__game").length, 2, "the square without an id stays a plain square");
  clean("form", linked);
  const plain = formGuide(form);
  assert.equal(plain.querySelectorAll("a").length, 0, "no hrefFor: plain squares, as before");
};

const BOX = {
  season: 2026,
  game: { gameId: 900, week: 3, completed: true, neutralSite: false, conferenceGame: true, venue: "Pie Bowl", kickoff: "2026-09-20T19:00:00Z", isOurs: false },
  home: { school: "Home U", abbreviation: "HOM", points: 31, lineScores: [7, 10, 7, 7] },
  away: { school: "Away State", abbreviation: null, points: 24, lineScores: [7, null, "x", 10] },
  final: {
    available: true,
    home: { team: "Home U", totalYards: 410, netPassingYards: 250, rushingYards: 160, firstDowns: 22, thirdDown: { made: 5, of: 12 }, fourthDown: { made: 1, of: 1 }, turnovers: 1, penalties: { count: 6, yards: 50 }, possessionTime: "31:10" },
    away: { team: "Away State", totalYards: null, penalties: null, thirdDown: null },
    players: { home: { passing: [{ playerId: "1", name: "A Passer", stats: { "C/ATT": "20/30", YDS: 250, TD: 2, INT: 0, QBR: 70.1 } }, null] }, away: {} },
  },
  parts: { boxTeams: { status: "ok" }, boxPlayers: { status: "ok" } },
};

scenarios.page = async () => {
  installWindow();
  const { createBoxView } = await import(moduleUrl("views/box.js"));
  const { main } = await mountView(createBoxView, "/api/box/900", BOX, { gameId: "900" });
  const t = clean("box page", main);
  assert.ok(t.includes("Home U") && t.includes("Away State") && t.includes("Final"));
  const scores = main.querySelectorAll(".box-head__score").map(text);
  assert.deepEqual(scores, ["24", "31"], "the visitor first when neither team is ours");
  assert.ok(main.querySelector(".box-head__side--right").className.includes("won"));
  assert.ok(t.includes("A Passer"));
  assert.ok(t.includes("Conference game") && t.includes("Pie Bowl"));
};

scenarios.unplayed = async () => {
  installWindow();
  const { createBoxView } = await import(moduleUrl("views/box.js"));
  const data = { ...BOX, game: { ...BOX.game, completed: false }, home: { school: "Home U" }, away: { school: "Away State" }, final: { available: false, home: null, away: null, players: {} } };
  const { main } = await mountView(createBoxView, "/api/box/901", data, { gameId: "901" });
  const t = clean("unplayed", main);
  assert.ok(t.includes("Not played yet") && t.includes("The box score appears after the final."));
  const none = createBoxView({ gameId: "abc" });
  const host = document.createElement("main");
  none.mount(host);
  assert.ok(text(host).includes("No game was named"));
};

scenarios.standings = async () => {
  installWindow();
  const { createTeamView } = await import(moduleUrl("views/team.js"));
  const data = {
    season: 2026,
    team: { school: "Far Away U", abbreviation: "FAR" },
    profile: { rows: [] }, advanced: { rows: [] }, schedule: [], roster: [], coaches: [],
    standings: { conference: "Other", rows: [{ place: 1, team: "Far Away U", isUs: true, conference: { wins: 3, losses: 0 }, overall: { wins: 6, losses: 1 }, apRank: 12 }, { place: 2, team: "Next Door", isUs: false, conference: null, overall: { wins: "x" } }, null] },
    parts: { records: { status: "ok" } },
  };
  window.scrollY = 0;
  const { main } = await mountView(createTeamView, "/api/team/Far%20Away%20U", data, { school: "Far Away U", params: { band: "standings" } });
  await advance(10);
  const band = main.querySelector("#team-standings");
  assert.ok(band, "the standings band is on the Summary tab");
  const t = clean("standings", band);
  assert.ok(t.includes("Other standings") && t.includes("3-0") && t.includes("Next Door"));
  const independent = { ...data, standings: null };
  const { main: main2 } = await mountView(createTeamView, "/api/team/Lone", independent, { school: "Lone" });
  assert.equal(main2.querySelector("#team-standings"), null, "an independent has none");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["links", "page", "unplayed", "standings"])
def test_box_and_standings_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
