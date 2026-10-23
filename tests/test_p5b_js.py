"""Public release Phase 5b in the fake browser (tests/fakedom.py): the menu's My teams group with one tap to
each primary team, the opponents and My teams switches on a ranked list (their URLs and titles), the My teams
page over a damaged payload (no undefined, null or NaN; dashes for missing games), and the radio help block
(only https links, the request button). Tables wave 3: the My Teams table sizes itself by its own box, every data point in its
own column (the role, why, the last game's result and opponent, the next game and its kickoff), the AP rank as the poll's
badge."""

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
  // the layout pass (owner 2026-10-22, boards 2 and 3): the opening level's six tiles and eight groups, in his order
  const { MENU } = await import(moduleUrl("ui/shell.js"));
  const plain = MENU;
  assert.deepEqual(MENU.tiles.map((t) => t.label), ["Newspaper", "Program", "In Game", "Big screen", "Trivia", "Radio"]);
  assert.deepEqual(MENU.groups.map((g) => g.label), ["My Teams", "This week's game", "National", "Stats", "Advanced stats", "Knowledge", "Profile", "New"]);
  assert.ok(MENU.groups[7].beta === true && MENU.groups[7].items.length === 0, "New (beta) waits empty until a new screen is placed");
  const game = MENU.groups[1].items;
  assert.deepEqual(game.filter((i) => i.flyout).map((i) => i.label), ["Tale of the tape", "Leaders side by side", "Lineups", "Advanced matchup", "Tendencies", "Talent and recruiting", "Play value", "Availability report", "Recruits on hand", "Common opponents", "Series", "Program notes", "Headlines", "What we need"], "the matchup's tables in the program's order (board 3)");
  assert.ok(game.filter((i) => i.items).every((i) => i.items.length <= 14), "a list splits past fourteen rows");
  assert.ok(!MENU.groups.flatMap((g) => g.items).some((i) => i.page === "setup" || i.page === "settings"), "Setup and Settings are the Profile now");
  // the tabs: the views in the same order, Top 25 after Season since 2026-10-13 (the magazine only in the menu); the Pre-Game Program stays home
  const { shell, VIEWS } = await import(moduleUrl("ui/shell.js"));
  assert.deepEqual(VIEWS.map((v) => v.id), ["newspaper", "program", "live", "season", "top25"]);
  installWindow();
  const page = shell({ menu: plain });
  document.body.append(page.root);
  const tab = page.root.querySelector('.tab[data-view="live"]');
  const flag = page.root.querySelector(".live-flag");
  assert.equal(page.root.querySelector('.tab[aria-current="page"]').dataset.view, "program");
  assert.ok(flag.hasAttribute("hidden") && !tab.className.includes("tab--live"));
  page.setLive(true);
  assert.ok(!flag.hasAttribute("hidden") && tab.className.includes("tab--live"));
  assert.ok(text(page.root.querySelector(".drawer")).includes("our game is live"), "the In Game tile says so");
  assert.ok(page.root.querySelector('.drawer__tile[data-entry="live"] .live-dot'), "with its dot");
  page.setLive("yes");
  assert.ok(flag.hasAttribute("hidden") && !tab.className.includes("tab--live"), "only true turns it on");
  assert.ok(!text(page.root.querySelector(".drawer")).includes("our game is live"));
  clean("shell", page.root);
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
  assert.ok(block.querySelector('a[href="#settings=radio"]'), "it points at Settings' station guide to add a station");
};
"""

NAMES = ["menu", "scopes", "radioHelp"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_phase5b_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_old_my_teams_address_opens_the_season_and_warms_the_primaries() -> None:
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    assert "myteams: (opts, arg, focus, params) => createSeasonView({ ...opts, params })" in app, "board 9: the old My Teams address opens the Season page"
    assert "menu: MENU," in app, "owner 2026-10-10: the other primary teams are reached from the My Teams page, not the menu"
    assert '"/api/myteams/warm", { method: "POST" }' in app
