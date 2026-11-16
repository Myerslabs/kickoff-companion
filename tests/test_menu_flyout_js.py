"""The menu one level at a time and the wide flyout (the layout pass, owner 2026-10-22, boards 2 to 4): the tree's helpers
(ui/menu-tree.js), the flyout with its "‹ the list", previous and next (ui/flyout.js), a table opened by itself
(views/panels.js), and Search finding the screens (views/search.js).

ENH-46 (owner 2026-11-10: "I want anything that is just a menu item to it's page to be removed. Anything thats on the page
still needs it whole page, and a way to look at it directly if the user wants, however I dont think we need a menu item for
things on that page"): the menu lists pages, a band opens by itself from the button in its own head (ui/band-open.js) and
from Search, and New, his testing list, is the one list that keeps a row for a band."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|NaN|null)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};
const PROGRAM = {
  game: { gameId: 526001015, kickoff: "2026-10-24T23:00:00Z", homeIsUs: true, completed: false },
  us: { school: "Florida", abbreviation: "FLA" },
  them: { school: "Texas", abbreviation: "TEX" },
  edges: [], parts: {}, notes: { present: false, availability: [] },
};
const lastLayer = () => [...document.body.querySelectorAll(".sheet-layer")].pop();

scenarios.tree = async () => {
  const { MENU, entriesOf, findPath, levelAt, allEntries, labelOf } = await import(moduleUrl("ui/menu-tree.js"));
  // ENH-46: a page's row opens the page, with no list of its bands in between
  assert.deepEqual(findPath(MENU, (e) => e.page === "preseason"), ["teams", "preseason"], "the Preseason Magazine is one row of My Teams");
  assert.deepEqual(findPath(MENU, (e) => e.page === "stats=passing"), ["stats", "lead-passing"], "a full list is one row");
  assert.deepEqual(findPath(MENU, (e) => e.page === "live"), ["live"], "In Game is a tile of the opening level");
  assert.deepEqual(findPath(MENU, (e) => e.flyout === "program:matchup"), ["new", "new:program:program-matchup"], "a band's only row is New's, the testing list");
  assert.equal(findPath(MENU, (e) => e.live === "drives"), null, "In Game's panels are In Game's own row of buttons, not the menu's");
  assert.equal(findPath(MENU, () => false), null);
  assert.equal(levelAt(MENU, []).id, "", "the opening level");
  assert.equal(labelOf(levelAt(MENU, ["game"]).label), "This week's game");
  assert.equal(levelAt(MENU, ["nope", "game"]).id, "", "a path that names nothing stays at the opening level");
  // the board's After column: 44 rows where there were 280
  const groups = ["teams", "game", "national", "stats", "advanced", "knowledge", "profile", "new"];
  assert.deepEqual(groups.map((id) => entriesOf(levelAt(MENU, [id]).items).length), [10, 3, 4, 5, 1, 2, 4, 14], "each group's rows"); // 1.40.5: the Imperialism Map left New for National; 1.46.0: Seasons in My Teams
  assert.deepEqual(MENU.groups.map((g) => g.id), groups);
  for (const group of MENU.groups) assert.ok(group.items.every((item) => !Array.isArray(item.items)), `${group.id}: no list one level down, a page's bands are on the page`);
  const all = allEntries(MENU);
  assert.equal(all.length, 6 + 43, "the six tiles and the groups' rows"); // 1.46.0: Seasons; three rows left New
  const placedRows = all.filter((x) => !x.entry.id.startsWith("new:"));
  assert.deepEqual(placedRows.filter((x) => x.entry.flyout || x.entry.live).map((x) => x.entry.id), ["radio"], "outside New only the Radio opens wide: no row for a thing on a page");
  // the rows that went: the lists of bands, the six rows that opened one band of a page, the Profile's sections
  for (const gone of ["matchup", "week", "ingame", "afterfinal", "program:program-matchup", "ig-drives", "season:season-schedule", "poll-ap", "poll-coaches", "rating-sp", "rating-elo", "lead-usage", "lead-ppa", "profile-gameday", "profile-radio", "profile-feedback", "season:page", "preseason:page"]) {
    assert.ok(!all.some((x) => x.entry.id === gone), `${gone} is no row of the menu any more`);
  }
  assert.deepEqual(entriesOf(levelAt(MENU, ["game"]).items).map((e) => [labelOf(e.label), e.page]), [["Pre-Game Program", "program"], ["In Game", "live"], ["Post-Game Program", "postgame"]], "This week's game: the three pages");
  assert.deepEqual(entriesOf(levelAt(MENU, ["profile"]).items).map((e) => e.id), ["profile", "invite", "connect", "status"], "the Profile page has the sections as tiles");
  assert.equal(all.find((x) => x.entry.id === "top25").where, "National", "where an entry sits, for Search");
  // New: a band under test keeps a row there, a page under test is copied there; the Imperialism Map went under National
  // (owner 2026-11-15)
  const fresh = entriesOf(levelAt(MENU, ["new"]).items);
  assert.equal(fresh.filter((e) => e.flyout).length, 10, "the ten bands he is testing");
  assert.deepEqual(fresh.filter((e) => e.page).map((e) => e.id), ["new:newspaper-bands", "new:season", "new:top25", "new:conference"]);
  assert.deepEqual(entriesOf(levelAt(MENU, ["national"]).items).map((e) => e.page), ["top25", "national=class:current", "conference", "imperialism"], "National: the Top 25, recruiting, the conferences, the Imperialism Map");
  assert.equal(all.find((x) => x.entry.id === "imperialism").where, "National", "Search says where it sits");
  assert.equal(fresh.find((e) => e.id === "new:season").page, "season", "a copy opens the same page");
  assert.ok(all.every((x) => x.entry.page || x.entry.href || x.entry.flyout || x.entry.live), "every entry opens something: no dead ends");
  const ids = all.map((x) => x.entry.id);
  assert.equal(new Set(ids).size, ids.length, "no id twice");
  // every page the menu names is a page the router builds
  const pages = all.map((x) => x.entry.page).filter(Boolean).map((p) => p.split(/[=?]/)[0]);
  for (const p of pages) assert.ok(["newspaper", "program", "postgame", "live", "board", "trivia", "season", "roster", "recruiting", "injuries", "review", "seasons", "preseason", "archive", "prompts", "top25", "imperialism", "leaders", "ratings", "glossary", "profile", "invite", "stats", "national", "conference"].includes(p), p);
};

scenarios.flyout = async () => {
  installWindow();
  const { openWide, pagerFor, liftBand, flyoutContent } = await import(moduleUrl("ui/flyout.js"));
  const { band } = await import(moduleUrl("ui/states.js"));
  assert.equal(pagerFor(null), null, "no list, no foot");
  assert.equal(pagerFor({ items: [{ id: "a", label: "A" }], index: 0 }), null, "one table, no foot");
  const items = [{ id: "a", label: "Tale of the tape" }, { id: "b", label: "Leaders side by side" }, { id: "c", label: "Lineups" }];
  const stepped = [];
  const backs = [];
  const handle = openWide({ title: "Tale of the tape", subtitle: "FLA vs TEX", back: { label: "This week's game", onClick: () => backs.push(1) }, steps: { items, index: 0, where: "This week's game", onStep: (id) => stepped.push(id) }, body: flyoutContent({ summary: "FLA better in 6 of 12", body: document.createElement("div") }) });
  const layer = document.body.querySelector(".sheet-layer");
  const aside = layer.querySelector(".side-sheet");
  assert.ok(aside.className.includes("side-sheet--wide"), "wide");
  assert.equal(text(layer.querySelector(".side-sheet__title")), "Tale of the tape");
  assert.equal(text(layer.querySelector(".side-sheet__subtitle")), "FLA vs TEX", "the game it is about under the title");
  assert.equal(text(layer.querySelector(".flyout__summary")), "FLA better in 6 of 12");
  const head = layer.querySelector(".side-sheet__head");
  assert.ok(head.childNodes[0].className.includes("side-sheet__lead") && head.childNodes[head.childNodes.length - 1].className.includes("side-sheet__close"), "‹ the list at the left, × at the right (board 4)");
  const pager = layer.querySelector(".flyout-pager");
  assert.ok(layer.querySelector(".flyout-pager__prev").hasAttribute("disabled"), "nothing before the first");
  assert.equal(text(layer.querySelector(".flyout-pager__count")), "1 of 3 in This week's game");
  assert.ok(text(layer.querySelector(".flyout-pager__next")).includes("Leaders side by side"));
  layer.querySelector(".flyout-pager__next").click();
  assert.deepEqual(stepped, ["b"]);
  handle.setTitle("Leaders side by side");
  handle.setSteps({ items, index: 1, where: "This week's game", onStep: (id) => stepped.push(id) });
  assert.equal(text(layer.querySelector(".flyout-pager__count")), "2 of 3 in This week's game", "the foot moves along");
  assert.ok(text(layer.querySelector(".flyout-pager__prev")).includes("Tale of the tape"));
  assert.ok(pager !== layer.querySelector(".flyout-pager"), "a new foot");
  handle.setSubtitle("");
  assert.ok(layer.querySelector(".side-sheet__subtitle").hasAttribute("hidden"));
  layer.querySelector(".flyout-back").click();
  assert.deepEqual(backs, [1], "‹ the list reopens the menu there ...");
  assert.equal(document.body.querySelector(".sheet-layer[open] .side-sheet--wide"), null, "... and the flyout closes");
  // a band shown alone: its head goes, its summary rises, it is never folded, it keeps no id
  const b = band({ id: "program-tape", title: "Tale of the tape", foldable: true, summary: "FLA better in 6 of 12", body: () => document.createElement("p") });
  b.setAttribute("data-collapsed", "true");
  const lifted = liftBand(b);
  assert.equal(lifted.summary, "FLA better in 6 of 12");
  assert.ok(lifted.node.className.includes("band--lifted") && lifted.node.getAttribute("data-collapsed") === "false" && !lifted.node.getAttribute("id"));
  assert.deepEqual(liftBand(null).summary, null, "a missing band lifts nothing");
};

scenarios.panels = async () => {
  installWindow();
  window.location.hash = "#live";
  route("/api/program/next", () => envelope(PROGRAM));
  route("/api/newspaper", () => envelope({ news: [] }));
  route("/api/program/526001015/leaders", () => envelope({ categories: [] }));
  const { MENU, findPath } = await import(moduleUrl("ui/menu-tree.js"));
  const { openFromMenu, gameLine } = await import(moduleUrl("views/panels.js"));
  const marks = [];
  const opened = [];
  document.addEventListener("kickoff:menu-mark", (e) => marks.push(e.detail.mark));
  document.addEventListener("kickoff:menu-open", (e) => opened.push(e.detail));
  // New's row of a band he is testing: the one kind of band row the menu still has
  const tape = MENU.groups.find((g) => g.id === "new").items.find((i) => i.id === "new:program:program-matchup");
  openFromMenu(tape, { path: findPath(MENU, (e) => e === tape), menu: MENU });
  await settle();
  await advance(50);
  const layer = document.body.querySelector(".sheet-layer");
  assert.equal(text(layer.querySelector(".side-sheet__title")), "The matchup");
  assert.ok(text(layer.querySelector(".side-sheet__subtitle")).startsWith("FLA vs TEX"), text(layer.querySelector(".side-sheet__subtitle")));
  assert.ok(gameLine().startsWith("FLA vs TEX"));
  const lifted = layer.querySelector(".band--lifted");
  assert.ok(lifted, "the program's own band, lifted");
  clean("tape flyout", layer);
  assert.equal(text(layer.querySelector(".flyout-pager__count")), "1 of 10 in New", "previous and next walk the bands under test");
  assert.equal(layer.querySelector(".flyout-own").getAttribute("href"), "#band=program:program-matchup", "Own page in the head (owner 2026-10-28)");
  layer.querySelector(".flyout-pager__next").click();
  await settle();
  await advance(50);
  assert.equal(text(layer.querySelector(".side-sheet__title")), "The matchup · Last season", "next walks the list: the box's other views follow it");
  assert.deepEqual(marks, ["new:program:program-matchup-last"], "the menu's mark follows");
  assert.equal(text(layer.querySelector(".flyout-pager__count")), "2 of 10 in New");
  assert.equal(layer.querySelector(".flyout-own").getAttribute("href"), "#band=program:program-matchup-last?view=last", "Own page follows: the box opened on that view");
  clean("strengths flyout", layer);
  layer.querySelector(".flyout-back").click();
  assert.deepEqual(opened, [{ path: ["new"] }], "‹ New reopens the menu on that list");
  // the radio tile opens the stations by themselves, with no list to walk
  const radio = MENU.tiles.find((t) => t.id === "radio");
  openFromMenu(radio, { path: ["radio"], menu: MENU });
  const radioLayer = lastLayer();
  assert.equal(text(radioLayer.querySelector(".side-sheet__title")), "Radio");
  assert.equal(radioLayer.querySelector(".flyout-pager"), null);
  assert.equal(openFromMenu(null), null);
  assert.equal(openFromMenu(MENU.groups[0].items[1], { path: ["teams", "newspaper-bands"], menu: MENU }), null, "a page's row opens no flyout");
};

// ENH-46: a band opened by itself where it sits, from its own head or from Search (views/panels.js openBand)
scenarios.openBand = async () => {
  installWindow();
  window.location.hash = "#program=526001015";
  route("/api/program/526001015", () => envelope(PROGRAM));
  route("/api/newspaper", () => envelope({ news: [] }));
  route("/api/program/526001015/leaders", () => envelope({ categories: [] }));
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  const { openBand } = await import(moduleUrl("views/panels.js"));
  const marks = [];
  document.addEventListener("kickoff:menu-mark", (e) => marks.push(e.detail.mark));
  const entry = (id) => cat.bandEntry("program", cat.findBand("program", id));
  const steps = ["program-matchup", "program-week", "program-talent"].map(entry);
  openBand(steps[0], { steps, where: "Pre-Game Program", route: "program=526001015" });
  await settle();
  await advance(50);
  const layer = lastLayer();
  assert.equal(text(layer.querySelector(".side-sheet__title")), "The matchup");
  assert.ok(text(layer.querySelector(".side-sheet__subtitle")).startsWith("FLA vs TEX"), "the game on screen");
  assert.equal(layer.querySelector(".flyout-back"), null, "no list to go back to: the band was opened from its page");
  assert.equal(text(layer.querySelector(".flyout-pager__count")), "1 of 3 in Pre-Game Program", "previous and next walk the bands the page shows");
  assert.equal(layer.querySelector(".flyout-own").getAttribute("href"), "#band=program=526001015:program-matchup", "Own page keeps the page on screen");
  layer.querySelector(".flyout-pager__next").click();
  await settle();
  await advance(50);
  assert.equal(text(layer.querySelector(".side-sheet__title")), "Margin by week");
  assert.equal(layer.querySelector(".flyout-own").getAttribute("href"), "#band=program=526001015:program-week");
  assert.deepEqual(marks, [], "no row of the menu to mark");
  clean("the band from its page", layer);
  // a band whose entry is missing from the steps still opens, first
  openBand(entry("program-tendencies"), { steps: [steps[0]], where: "Pre-Game Program" });
  await settle();
  assert.equal(text(lastLayer().querySelector(".flyout-pager__count")), "1 of 2 in Pre-Game Program");
  assert.equal(lastLayer().querySelector(".flyout-own").getAttribute("href"), "#band=program=526001015:program-tendencies", "no address given: the program on screen, as the program's own tables");
  // a band of another team's page: that team's page is mounted, its own page keeps the team, the head says whose it is
  const schedule = cat.bandEntry("season", cat.findBand("season", "season-schedule"));
  openBand(schedule, { steps: [schedule], where: "My Team", route: "team=Georgia" });
  await settle();
  assert.equal(lastLayer().querySelector(".flyout-own").getAttribute("href"), "#band=team=Georgia:season-schedule");
  assert.equal(text(lastLayer().querySelector(".side-sheet__subtitle")), "Georgia");
  assert.equal(lastLayer().querySelector(".flyout-pager"), null, "one band, no foot");
  // one of In Game's panels, from Search: asked for over In Game, with no list of the menu behind it
  window.location.hash = "#live";
  const asked = [];
  document.addEventListener("kickoff:live-panel", (e) => asked.push(e.detail));
  const drives = cat.pageList("live").find((e) => e.live === "drives");
  openBand(drives, { steps: cat.pageList("live"), where: "In Game" });
  assert.equal(asked.length, 1);
  assert.equal(asked[0].id, "drives");
  assert.equal(asked[0].steps.items.length, 11, "previous and next through In Game's nine panels and the stage's two");
  assert.equal(asked[0].steps.where, "In Game");
  assert.equal(asked[0].back, null);
  assert.equal(asked[0].entryOf("box"), null, "no row of the menu to mark");
  assert.equal(openBand(null), null);
  assert.equal(openBand({ id: "x", page: "season" }), null, "a page is not a band");
};

// ENH-46: the button in a band's own head (ui/band-open.js)
scenarios.bandButton = async () => {
  installWindow();
  const { band } = await import(moduleUrl("ui/states.js"));
  const { bandsOnPage, markBands, watchBands } = await import(moduleUrl("ui/band-open.js"));
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  assert.equal(cat.catalogOf("#season"), "season");
  assert.equal(cat.catalogOf("team=Georgia"), "season", "a team's page is My Team's page of that team");
  assert.equal(cat.catalogOf("#postgame=401?tab=x"), "program", "the Post-Game stop draws the program's bands");
  assert.equal(cat.catalogOf("stats=rushing?view=teams"), "stats-rushing");
  assert.equal(cat.catalogOf("blame"), "season");
  assert.equal(cat.catalogOf("picks"), "top25");
  for (const none of ["", null, "glossary", "band=season:season-schedule", "constructor", "profile=radio", "sea son"]) assert.equal(cat.catalogOf(none), null, String(none));
  const body = () => document.createElement("p");
  const root = document.createElement("div");
  const inner = band({ id: "season-ratings", title: "Ratings", body });
  const box = band({ id: "season-numbers", title: "The numbers", body: () => inner });
  root.append(
    band({ id: "season-schedule", title: "Schedule", foldable: true, tools: document.createElement("span"), body }),
    band({ id: "not-in-the-catalog", title: "Something else", body }),
    box,
    band({ id: "season-road", title: "Road ahead", bare: true, body }),
    band({ id: "season-standings", title: "Standings", collapsible: false, body }),
  );
  document.body.append(root);
  const ids = (route) => bandsOnPage(root, route).map((item) => item.band.id);
  assert.deepEqual(ids("season"), ["season-schedule", "season-numbers", "season-standings"], "the catalog's bands the page draws, in the page's order: not a band inside a band, not one without a head, not one the catalog does not name");
  assert.deepEqual(ids("#team=Georgia"), ["season-schedule", "season-numbers", "season-standings"]);
  for (const none of ["live", "glossary", "band=season:season-schedule", "roster", ""]) assert.deepEqual(ids(none), [], none);
  const taps = [];
  assert.equal(markBands(root, "season", (node) => taps.push(node.getAttribute("id"))), 3);
  const buttons = () => [...root.querySelectorAll(".band__open")];
  assert.equal(buttons().length, 3, "one button a band");
  const first = root.querySelector("#season-schedule");
  const head = first.querySelector(".band__head");
  const kids = [...head.children].map((n) => n.className.split(" ").find((c) => c.startsWith("band__")));
  assert.deepEqual(kids, ["band__title", "band__tools", "band__open", "band__toggle"], "after the band's tools, before the fold button");
  assert.equal(head.querySelector(".band__open").getAttribute("aria-label"), "Open Schedule by itself");
  assert.equal(root.querySelector("#season-standings .band__open").getAttribute("data-band"), "season-standings");
  assert.equal(inner.querySelector(".band__open"), null, "a band inside a band has none");
  assert.equal(markBands(root, "season", () => {}), 3);
  assert.equal(buttons().length, 3, "a second pass adds nothing");
  assert.ok(buttons()[0] === head.querySelector(".band__open"), "and replaces nothing");
  const folded = first.getAttribute("data-collapsed");
  head.querySelector(".band__open").click();
  assert.deepEqual(taps, ["season-schedule"]);
  assert.equal(first.getAttribute("data-collapsed"), folded, "the tap does not fold the band");
  assert.equal(markBands(root, "glossary", () => {}), 0);
  assert.equal(buttons().length, 0, "a page the catalog does not list keeps no button");
  // the watch: the page on screen decides, and a tap hands over the band, the page's bands and the address
  let address = "#team=Georgia";
  const got = [];
  const stop = watchBands(root, { route: () => address, onOpen: (entry, ctx) => got.push({ entry, ctx }) });
  assert.equal(buttons().length, 3, "marked at once");
  root.querySelector("#season-standings .band__open").click();
  assert.equal(got.length, 1);
  assert.equal(got[0].entry.id, "season:season-standings");
  assert.equal(got[0].entry.flyout, "band:season:season-standings");
  assert.deepEqual(got[0].ctx.steps.map((e) => e.id), ["season:season-schedule", "season:season-numbers", "season:season-standings"]);
  assert.equal(got[0].ctx.where, "Georgia", "another team's page is that team's: the flyout's foot says whose bands it walks");
  assert.equal(got[0].ctx.route, "team=Georgia", "the page on screen, so the band is that team's");
  address = "#season";
  root.querySelector("#season-schedule .band__open").click();
  assert.equal(got[1].ctx.where, "My Team", "our own page by its name");
  assert.equal(got[1].ctx.route, "season");
  address = "#team=Georgia";
  root.append(band({ id: "season-resume", title: "Résumé", body }));
  document.dispatchEvent(new CustomEvent("kickoff:rendered", { detail: {} }));
  await settle();
  assert.equal(buttons().length, 4, "a band the page draws later gets its button");
  stop();
  address = "#glossary";
  document.dispatchEvent(new CustomEvent("kickoff:rendered", { detail: {} }));
  await settle();
  assert.equal(buttons().length, 4, "stopped: nothing more is touched");
  assert.equal(typeof watchBands(null), "function");
};

scenarios.search = async () => {
  const { screenMatches } = await import(moduleUrl("views/search.js"));
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  // ENH-46: the bands are found from the catalog, each with its page's name
  const tendencies = screenMatches("tendencies");
  const ids = tendencies.map((m) => m.entry.id);
  assert.ok(ids.includes("program:program-tendencies") && ids.includes("season:season-tendencies"), `the program's Tendencies and My Team's: ${ids.join(", ")}`);
  assert.deepEqual(tendencies.find((m) => m.entry.id === "season:season-tendencies").where, "My Team", "the band's page under its name");
  assert.equal(tendencies.find((m) => m.entry.id === "season:season-tendencies").page, "season", "an item with a page is a band of the catalog");
  assert.equal(screenMatches("SP+")[0].entry.label, "SP+", "a screen called by the words comes first");
  assert.ok(screenMatches("SP+").some((m) => m.entry.id === "ratings" && !m.page), "then the ones that mention them: the Ratings page's row");
  assert.ok(screenMatches("leaders").some((m) => m.entry.id === "leaders" && m.entry.page === "leaders"), "a page is found by its name");
  assert.ok(screenMatches("injury").some((m) => m.entry.page === "injuries"));
  assert.ok(screenMatches("in game drives").some((m) => m.entry.live === "drives" && m.page === "live"), "words from where it sits count too");
  assert.ok(screenMatches("roster costs").some((m) => m.entry.flyout === "band:preseason:roster-costs"), "the Preseason Magazine's band, with no row in the menu");
  // every band of every page can be found: the menu no longer lists them
  const bands = cat.allBands();
  assert.equal(bands.length, Object.keys(cat.BAND_PAGES).reduce((n, page) => n + cat.bandsOf(page).length, 0));
  assert.ok(bands.every((b) => b.where && (b.entry.flyout || b.entry.live) && cat.BAND_PAGES[b.page]), "each opens wide and names its page");
  assert.deepEqual(screenMatches("x"), [], "one letter matches nothing");
  assert.deepEqual(screenMatches(null), []);
  assert.ok(screenMatches("a").length === 0 && screenMatches("the").length <= 8, "at most eight");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["tree", "flyout", "panels", "openBand", "bandButton", "search"])
def test_menu_and_flyout_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
