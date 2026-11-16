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
  // New (beta) holds a new screen until the owner places it: ENH-11's strengths and weaknesses (2026-10-28), then the bands
  // every band its own flyout and page brought (2026-10-28): the program's other tables, the Newspaper's, our team page's
  // ... he placed every one of them (2026-10-28), and New keeps them too while he tests them ("I still want things I am
  // testing to be there"): copies with their own ids, opening the same screens
  const fresh = MENU.groups[7].items;
  assert.ok(MENU.groups[7].beta === true && fresh.every((i) => (i.flyout || i.page) && !i.items), "New holds only screens that open, each on one tap");
  assert.deepEqual(fresh.map((i) => i.id), ["new:program:program-matchup", "new:program:program-matchup-last", "new:program:program-week", "new:program:program-talent", "new:program:program-schools", "new:program:program-trip", "new:program:program-scout", "new:program:program-recap", "new:program:program-box", "new:program:program-blame", "new:newspaper-bands", "new:season", "new:top25", "new:conference"]); // the Imperialism Map went under National (owner 2026-11-15) // the Circle of Blame's row went into My Team (wave 3, 2026-11-01) // the Season stop's box and Our land (Wave 4); the Post-Game stop's boxes (the line, Wave 3); FEAT-16 (2026-10-30); the margins under the poll path (ENH-19 chart 3); Getting there (ENH-15); the Imperialism Map (FEAT-17); the Circle of Blame (FEAT-18)
  assert.ok(fresh.every((i) => String(i.id).startsWith("new:")), "every screen in New is a copy of one placed elsewhere: the last unplaced one, the Imperialism Map (FEAT-17), went under National (owner 2026-11-15), as FEAT-18's went into My Team (wave 3, 2026-11-01)");
  assert.equal(MENU.groups[2].items.at(-1).page, "imperialism", "the Imperialism Map: the last row of National, one row that opens the page (ENH-46, 2026-11-10: its bands are on the page)");
  assert.equal(fresh[0].flyout, "program:matchup", "a band he is testing opens wide: New's row is the only row a band has (ENH-46)");
  assert.equal(fresh.find((i) => i.id === "new:newspaper-bands").page, "newspaper", "a page's copy opens the same page");
  const game = MENU.groups[1].items;
  assert.deepEqual(game.map((i) => i.label), ["Pre-Game Program", "In Game", "Post-Game Program"], "This week's game is its three pages (ENH-46, owner 2026-11-10: no menu item for a thing on a page; a band opens from its own head)");
  const teams = MENU.groups[0].items.filter((i) => !("heading" in i)).map((i) => i.id);
  assert.deepEqual(teams.slice(0, 2), ["newspaper-bands", "season"], "the Newspaper first in My Teams, then My Team (the Season page with the team page's list folded in, 2026-11-01)");
  // no list one level down any more, so nothing to split past fourteen rows
  assert.ok(MENU.groups.every((g) => g.items.every((i) => !i.items)), "every row opens something by itself");
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
  assert.equal(nationalHref("rating:sp", { scope: "mine", team: "Texas State" }), "#national=rating%3Asp?team=Texas%20State&scope=mine");
  assert.equal(nationalRoute(parseRoute("#national=rating%3Asp?scope=opponents")).scope, "opponents");
  assert.equal(nationalRoute(parseRoute("#national=rating%3Asp?scope=bogus")).scope, "national");
  assert.equal(listTitle({ label: "SP+ overall", scope: "opponents", us: { team: "Florida" } }), "SP+ overall, Florida and its opponents");
  assert.equal(listTitle({ label: "SP+ overall", scope: "mine" }), "SP+ overall, my teams");
  const data = {
    metric: "rating:sp", family: "rating", key: "sp", label: "SP+ overall", format: "1f", higherIsBetter: true, season: 2026, year: 2026, years: [2026],
    scope: "mine", scopes: ["national", "conference", "opponents", "mine"], unit: "team", population: "My teams, ranked nationally (FBS teams)", rankSource: "cfbd", of: 136,
    rows: [{ rank: 3, team: "Florida", conference: "SEC", value: 20.1, isUs: true }, { rank: 40, team: "Houston", conference: null, value: null }, null],
    beyond: [], us: { team: "Florida", rank: 3, value: 20.1, of: 136 }, focus: null, parts: {},
  };
  const picked = [];
  const body = nationalListBody({ data, errors: [], meta: { source: "live", stale: false } }, { onScope: (s) => picked.push(s) });
  document.body.append(body);
  const seg = body.querySelector(".nat-seg");
  assert.equal(text(seg), "All FBSSECOpponentsMy teams");
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
    { school: "Texas State", search: [{ label: "Search the web", url: "https://www.google.com/search?q=x" }, { label: "Bad", url: "javascript:alert(1)" }, { label: "Plain", url: "http://x" }], requestUrl: "https://github.com/Myerslabs/kickoff-companion/issues/new?template=radio-station.yml" },
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
  assert.ok(t.includes("Texas State: no station in the app yet."));
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
