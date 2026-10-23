"""The menu one level at a time and the wide flyout (the layout pass, owner 2026-10-22, boards 2 to 4): the tree's helpers
(ui/menu-tree.js), the flyout with its "‹ the list", previous and next (ui/flyout.js), a Pre-Game Program table opened by
itself from the menu (views/panels.js), and Search finding the menu's screens (views/search.js)."""

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
  us: { school: "Swampwater Tech", abbreviation: "SWT" },
  them: { school: "Bluegrass Bottoms", abbreviation: "BLUE" },
  edges: [], parts: {}, notes: { present: false, availability: [] },
};

scenarios.tree = async () => {
  const { MENU, entriesOf, findPath, levelAt, allEntries, labelOf } = await import(moduleUrl("ui/menu-tree.js"));
  assert.deepEqual(findPath(MENU, (e) => e.flyout === "program:tape"), ["game", "tape"], "the tape under This week's game");
  assert.deepEqual(findPath(MENU, (e) => e.live === "drives"), ["game", "ingame", "ig-drives"], "In Game's panels one level down");
  assert.deepEqual(findPath(MENU, (e) => e.page === "live"), ["live"], "In Game is a tile of the opening level");
  assert.equal(findPath(MENU, () => false), null);
  assert.equal(levelAt(MENU, []).id, "", "the opening level");
  assert.equal(labelOf(levelAt(MENU, ["game", "ingame"]).label), "In Game's panels");
  assert.equal(levelAt(MENU, ["nope", "ingame"]).id, "", "a path that names nothing stays at the opening level");
  assert.equal(entriesOf(levelAt(MENU, ["game"]).items).length, 14, "headings and lower levels are not entries");
  const all = allEntries(MENU);
  const tape = all.find((x) => x.entry.id === "tape");
  assert.equal(tape.where, "This week's game › The matchup", "where an entry sits, for Search");
  assert.ok(all.every((x) => x.entry.page || x.entry.href || x.entry.flyout || x.entry.live), "every entry opens something: no dead ends");
  const ids = all.map((x) => x.entry.id);
  assert.equal(new Set(ids).size, ids.length, "no id twice");
  // every page the menu names is a page the router builds
  const pages = all.map((x) => x.entry.page).filter(Boolean).map((p) => p.split(/[=?]/)[0]);
  for (const p of pages) assert.ok(["newspaper", "program", "live", "board", "trivia", "season", "roster", "recruiting", "injuries", "review", "preseason", "archive", "myteams", "prompts", "top25", "leaders", "ratings", "glossary", "profile", "invite"].includes(p), p);
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
  const handle = openWide({ title: "Tale of the tape", subtitle: "SWT vs BLUE", back: { label: "This week's game", onClick: () => backs.push(1) }, steps: { items, index: 0, where: "This week's game", onStep: (id) => stepped.push(id) }, body: flyoutContent({ summary: "SWT better in 6 of 12", body: document.createElement("div") }) });
  const layer = document.body.querySelector(".sheet-layer");
  const aside = layer.querySelector(".side-sheet");
  assert.ok(aside.className.includes("side-sheet--wide"), "wide");
  assert.equal(text(layer.querySelector(".side-sheet__title")), "Tale of the tape");
  assert.equal(text(layer.querySelector(".side-sheet__subtitle")), "SWT vs BLUE", "the game it is about under the title");
  assert.equal(text(layer.querySelector(".flyout__summary")), "SWT better in 6 of 12");
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
  const b = band({ id: "program-tape", title: "Tale of the tape", foldable: true, summary: "SWT better in 6 of 12", body: () => document.createElement("p") });
  b.setAttribute("data-collapsed", "true");
  const lifted = liftBand(b);
  assert.equal(lifted.summary, "SWT better in 6 of 12");
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
  const tape = MENU.groups.find((g) => g.id === "game").items.find((i) => i.id === "tape");
  openFromMenu(tape, { path: findPath(MENU, (e) => e === tape), menu: MENU });
  await settle();
  await advance(50);
  const layer = document.body.querySelector(".sheet-layer");
  assert.equal(text(layer.querySelector(".side-sheet__title")), "Tale of the tape");
  assert.ok(text(layer.querySelector(".side-sheet__subtitle")).startsWith("SWT vs BLUE"), text(layer.querySelector(".side-sheet__subtitle")));
  assert.ok(gameLine().startsWith("SWT vs BLUE"));
  const lifted = layer.querySelector(".band--lifted");
  assert.ok(lifted, "the program's own band, lifted");
  clean("tape flyout", layer);
  assert.equal(text(layer.querySelector(".flyout-pager__count")), "1 of 14 in This week's game");
  layer.querySelector(".flyout-pager__next").click();
  await settle();
  await advance(50);
  assert.equal(text(layer.querySelector(".side-sheet__title")), "Leaders side by side", "next walks the matchup");
  assert.deepEqual(marks, ["leaders-pair"], "the menu's mark follows");
  assert.equal(text(layer.querySelector(".flyout-pager__count")), "2 of 14 in This week's game");
  clean("leaders flyout", layer);
  layer.querySelector(".flyout-back").click();
  assert.deepEqual(opened, [{ path: ["game"] }], "‹ This week's game reopens the menu on that list");
  // one of In Game's panels on In Game: asked for at once (views/live.js opens it)
  const asked = [];
  document.addEventListener("kickoff:live-panel", (e) => asked.push(e.detail));
  const drives = MENU.groups.find((g) => g.id === "game").items.find((i) => i.id === "ingame").items.find((i) => i.live === "drives");
  openFromMenu(drives, { path: findPath(MENU, (e) => e === drives), menu: MENU });
  assert.equal(asked.length, 1);
  assert.equal(asked[0].id, "drives");
  assert.equal(asked[0].steps.items.length, 12, "previous and next through In Game's twelve panels");
  assert.equal(asked[0].back.label, "In Game's panels");
  assert.equal(asked[0].entryOf("box"), "ig-box");
  // the radio tile opens the stations by themselves, with no list to walk
  const radio = MENU.tiles.find((t) => t.id === "radio");
  openFromMenu(radio, { path: ["radio"], menu: MENU });
  const radioLayer = [...document.body.querySelectorAll(".sheet-layer")].pop();
  assert.equal(text(radioLayer.querySelector(".side-sheet__title")), "Radio");
  assert.equal(radioLayer.querySelector(".flyout-pager"), null);
  assert.equal(openFromMenu(null), null);
};

scenarios.search = async () => {
  const { screenMatches } = await import(moduleUrl("views/search.js"));
  assert.deepEqual(screenMatches("tape").map((m) => m.entry.id), ["tape"]);
  assert.equal(screenMatches("SP+")[0].entry.id, "rating-sp", "a screen called by the words comes first");
  assert.ok(screenMatches("SP+").some((m) => m.entry.id === "ratings"), "then the ones that mention them");
  assert.ok(screenMatches("injury").some((m) => m.entry.page === "injuries"));
  assert.ok(screenMatches("in game drives").some((m) => m.entry.live === "drives"), "words from where it sits count too");
  assert.deepEqual(screenMatches("x"), [], "one letter matches nothing");
  assert.deepEqual(screenMatches(null), []);
  assert.ok(screenMatches("a").length === 0 && screenMatches("the").length <= 8, "at most eight");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["tree", "flyout", "panels", "search"])
def test_menu_and_flyout_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
