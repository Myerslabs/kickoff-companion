"""Public release Phase 5b in the fake browser (tests/fakedom.py): the menu's My teams group with one tap to
each primary team, the opponents and My teams switches on a ranked list (their URLs and titles), the My teams
page over a damaged payload (no undefined, null or NaN; dashes for missing games), and the radio help block
(only https links, the request button)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import STATIC_JS, needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};

scenarios.menu = async () => {
  const { MENU, menuWith } = await import(moduleUrl("ui/shell.js"));
  const plain = menuWith();
  assert.deepEqual(plain.map((g) => g.group), ["Views", "My teams", "More"]);
  assert.deepEqual(plain[1].items.map((i) => i.id), ["myteams"], "without extra primaries: the page only");
  const full = menuWith(["Diner Tech", "", null, 7, "Lake Effect", "A", "B", "C"]);
  const items = full[1].items;
  assert.equal(items.length, 5, "the page plus four primaries at most");
  assert.equal(items[1].label, "Diner Tech");
  assert.equal(items[1].hash, "team=Diner%20Tech");
  assert.equal(MENU.length, 2, "the base menu is not changed");
};

scenarios.scopes = async () => {
  installWindow();
  const { nationalApiUrl, listTitle, nationalListBody } = await import(moduleUrl("ui/national-sheet.js"));
  const { nationalHref, nationalRoute, parseRoute } = await import(moduleUrl("ui/national-link.js"));
  assert.equal(nationalApiUrl({ metric: "rating:sp", scope: "opponents" }), "/api/national/rating%3Asp?scope=opponents");
  assert.equal(nationalApiUrl({ metric: "rating:sp", scope: "mine" }), "/api/national/rating%3Asp?scope=mine");
  assert.equal(nationalApiUrl({ metric: "rating:sp", scope: "everything" }), "/api/national/rating%3Asp");
  assert.equal(nationalHref("rating:sp", { scope: "mine", team: "Diner Tech" }), "#national=rating%3Asp?team=Diner%20Tech&scope=mine");
  assert.equal(nationalRoute(parseRoute("#national=rating%3Asp?scope=opponents")).scope, "opponents");
  assert.equal(nationalRoute(parseRoute("#national=rating%3Asp?scope=bogus")).scope, "national");
  assert.equal(listTitle({ label: "SP+ overall", scope: "opponents", us: { team: "Swampwater Tech" } }), "SP+ overall, Swampwater Tech and its opponents");
  assert.equal(listTitle({ label: "SP+ overall", scope: "mine" }), "SP+ overall, my teams");
  const data = {
    metric: "rating:sp", family: "rating", key: "sp", label: "SP+ overall", format: "1f", higherIsBetter: true, season: 2026, year: 2026, years: [2026],
    scope: "mine", scopes: ["national", "conference", "opponents", "mine"], unit: "team", population: "My teams, ranked nationally (FBS teams)", rankSource: "cfbd", of: 136,
    rows: [{ rank: 3, team: "Swampwater Tech", conference: "Biscuit Belt", value: 20.1, isUs: true }, { rank: 40, team: "Cactus Gulch", conference: null, value: null }, null],
    beyond: [], us: { team: "Swampwater Tech", rank: 3, value: 20.1, of: 136 }, focus: null, parts: {},
  };
  const picked = [];
  const body = nationalListBody({ data, errors: [], meta: { source: "live", stale: false } }, { onScope: (s) => picked.push(s) });
  document.body.append(body);
  const seg = body.querySelector(".nat-seg");
  assert.equal(text(seg), "All FBSBiscuit BeltOpponentsMy teams");
  const pressed = seg.querySelectorAll("button").filter((b) => b.getAttribute("aria-pressed") === "true");
  assert.equal(text(pressed[0]), "My teams");
  seg.querySelectorAll("button")[2].click();
  assert.deepEqual(picked, ["opponents"]);
  clean("mine list", body);
  const free = nationalListBody({ data: { ...data, scope: "national", scopes: ["national", "opponents"] }, errors: [], meta: {} }, { onScope: () => {} });
  assert.equal(text(free.querySelector(".nat-seg")), "All FBSOpponents", "a free key: no My teams switch");
};

scenarios.myteams = async () => {
  installWindow();
  const { createMyTeamsView, lastText, nextText, shapeRows } = await import(moduleUrl("views/myteams.js"));
  assert.equal(lastText({ opponent: "Diner Tech", homeAway: "away", result: "W", usPoints: 31, themPoints: 14 }), "W 31-14 at Diner Tech");
  assert.equal(lastText({ opponent: "Diner Tech", homeAway: "home" }), "vs Diner Tech");
  assert.equal(lastText(null), "–");
  assert.equal(nextText({ opponent: null }), "–");
  assert.ok(nextText({ opponent: "Lake Effect", homeAway: "neutral", date: "2026-10-10T19:30:00Z" }).startsWith("vs Lake Effect, "));
  assert.equal(shapeRows([null, "junk", { school: "" }, { school: "X", why: [null, "Gravy Ten"], sp: { rank: "1" } }]).length, 1);
  route("/api/myteams", () => envelope({
    season: 2026, pollWeek: 5, plansUrl: "javascript:alert(1)",
    teamSet: { home: "Swampwater Tech", primaries: ["Swampwater Tech", "Diner Tech"], extraPrimaries: ["Diner Tech"], secondary: ["Cactus Gulch"], allowed: true, locked: {} },
    rows: [
      { school: "Swampwater Tech", role: "home", why: ["Home team"], record: { wins: 3, losses: 1, ties: 0 }, conferenceRecord: { wins: 1, losses: 0 }, apRank: 12, sp: { value: 20.1, rank: 3, of: 136 }, elo: { value: null, rank: null, of: null }, fpi: {}, last: { opponent: "Silver Dollar", homeAway: "away", result: "W", usPoints: 30, themPoints: 3 }, next: { opponent: "Diner Tech", homeAway: "home", date: "2026-10-10T19:30:00Z" } },
      { school: "Diner Tech", role: "primary", why: ["Primary team"], record: null, apRank: null, sp: null, elo: "junk", fpi: { rank: NaN }, last: null, next: null },
      { school: "Cactus Gulch", role: "secondary", why: ["Liked school", "Gravy Ten"], record: { wins: "two" }, sp: { rank: 50, of: 136 } },
      null, "junk",
    ],
    note: null, parts: { teams: { status: "ok" }, records: { status: "ok" }, rankings: { status: "ok" } },
  }));
  const host = document.createElement("main");
  document.body.append(host);
  const view = createMyTeamsView({ onStatus: () => {} });
  view.mount(host);
  await advance(50);
  const all = clean("my teams", host);
  assert.ok(all.includes("Home team") && all.includes("Primary") && all.includes("Secondary"), all.slice(0, 300));
  assert.ok(all.includes("2 primary, 1 secondary"), "the summary counts each kind");
  assert.ok(all.includes("W 30-3 at Silver Dollar"));
  assert.ok(all.includes("Liked school, Gravy Ten"), "why a secondary team is on the list");
  const links = host.querySelectorAll("a.rank-chip--link").map((a) => a.getAttribute("href"));
  assert.ok(links.includes("#national=rating%3Asp?team=Swampwater%20Tech&scope=mine"), links.join(" "));
  assert.equal(host.querySelectorAll("a").filter((a) => String(a.getAttribute("href")).startsWith("javascript:")).length, 0, "a bad plans link is never drawn");
  view.unmount();
};

scenarios.radioHelp = async () => {
  const { cleanHelp, radioHelpBlock } = await import(moduleUrl("radio.js"));
  const help = cleanHelp([
    { school: "Diner Tech", search: [{ label: "Search the web", url: "https://www.google.com/search?q=x" }, { label: "Bad", url: "javascript:alert(1)" }, { label: "Plain", url: "http://x" }], requestUrl: "https://github.com/Myerslabs/kickoff-companion/issues/new?template=radio-station.yml" },
    { school: "", search: [] },
    { school: "No Links", search: "junk", requestUrl: "ftp://x" },
    null,
  ]);
  assert.equal(help.length, 2);
  assert.equal(help[0].search.length, 1, "only https search links survive");
  assert.equal(help[1].requestUrl, null);
  assert.equal(radioHelpBlock([]), null, "nothing to help with: no block");
  const block = radioHelpBlock(help);
  document.body.append(block);
  const t = clean("radio help", block);
  assert.ok(t.includes("Diner Tech: no station in the app yet."));
  const request = block.querySelectorAll("a").find((a) => text(a) === "Request your team's radio");
  assert.ok(request && request.getAttribute("target") === "_blank" && request.getAttribute("rel") === "noopener");
  assert.ok(block.querySelector('a[href="#settings"]'), "it points at Settings to add a station");
};
"""

NAMES = ["menu", "scopes", "myteams", "radioHelp"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_phase5b_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_app_registers_the_my_teams_view_and_warms_the_primaries() -> None:
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    assert 'myteams: (opts) => createMyTeamsView(opts)' in app
    assert "menuWith(prefsMeta()?.teamSet?.extraPrimaries)" in app
    assert '"/api/myteams/warm", { method: "POST" }' in app
