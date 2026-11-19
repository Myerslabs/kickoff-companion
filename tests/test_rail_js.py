"""The rail. Since batch 4 (owner 2026-11-19): three stops in view, the one on screen in the middle, on a track that slides
("when i go left, another one is added and left is now center"; "only show 3, not 4"; "Animated would be great"); the Season
stop reads My Team and a "Now" tag sits under the stop that leads now; the Preseason Magazine and the season book are the
walk's two ends all season. Since 2026-11-15 a ‹ and a › at the row's ends step one stop at a time both ways through the
walk; from a page not on the walk they start at My Team."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const week = (n, opponent, homeAway, kickoff, result, pre, post) => ({
  kind: "week", week: n, seasonType: "regular", gameId: n, opponent, homeAway, date: kickoff, result,
  stops: {
    pre: { kind: "pre", key: `pre:${n}`, state: pre, date: kickoff.slice(0, 10) + "T06:00-04:00", href: pre === "missing" ? null : result ? `#program=${n}?tab=pre` : `#program=${n}`, label: "Pre-Game Program" },
    game: { kind: "game", key: `game:${n}`, state: result ? "done" : "to_come", date: kickoff, href: result ? `#archive=${n}` : null, label: "The game", ...(result ? { result } : {}) },
    post: { kind: "post", key: `post:${n}`, state: post, date: kickoff.slice(0, 10) + "T09:00-04:00", href: result ? `#postgame=${n}` : null, label: "Post-Game Program" },
  },
});

const LINE = {
  now: "2026-10-29T12:00-04:00",
  current: { kind: "pre", gameId: 9, week: 9, href: "#program=9", label: "Pre-Game Program", detail: "Week 9 · vs Georgia" },
  items: [
    { kind: "preseason", state: "saved", href: "#preseason", label: "Preseason Magazine", date: "2026-08-22T19:00-04:00" },
    week(1, "Florida Atlantic", "home", "2026-09-05T19:00-04:00", { usPoints: 66, themPoints: 21, won: true }, "missing", "saved"),
    week(7, "Texas", "away", "2026-10-17T19:30-04:00", { usPoints: 27, themPoints: 24, won: true }, "saved", "saved"),
    { kind: "bye", week: 8, date: "2026-10-24T19:30-04:00", label: "Bye" },
    { kind: "now", date: "2026-10-29T12:00-04:00", href: "#season", label: "My Team now", state: "now" },
    week(9, "Georgia", "neutral", "2026-10-31T15:30-04:00", null, "live", "to_come"),
    week(10, "Oklahoma", "home", "2026-11-07T12:00-05:00", null, "open", "to_come"),
    week(11, "Kentucky", "away", "2026-11-14T18:15-05:00", null, "open", "to_come"),
    { kind: "book", state: "to_come", href: null, label: "Season book", date: null },
  ],
};

const hrefs = (root) => root.querySelectorAll(".rail__chip").map((c) => c.getAttribute("href"));
const inView = (root) => root.querySelectorAll(".rail__chip").filter((c) => c.getAttribute("aria-hidden") !== "true").map((c) => c.getAttribute("href"));
const lit = (root) => root.querySelectorAll(".rail__chip--lit").map((c) => c.getAttribute("href"));
const nowAt = (root) => root.querySelectorAll(".rail__slot--now").map((s) => s.querySelector(".rail__chip").getAttribute("href"));
const chipAt = (root, href) => root.querySelectorAll(".rail__chip").find((c) => c.getAttribute("href") === href);
const stepHref = (root, which) => {
  const a = root.querySelector(`a.rail__step--${which}`);
  return a ? a.getAttribute("href") : null;
};
const stepLabel = (root, which) => root.querySelector(`a.rail__step--${which}`)?.getAttribute("aria-label") || null;
const WALK = ["#preseason", "#postgame=1", "#program=7?tab=pre", "#postgame=7", "#season", "#program=9", "#program=10", "#program=11", "#review"];

scenarios.row = async () => {
  const { rail } = await import(moduleUrl("ui/rail.js"));
  const root = rail({ line: LINE, viewing: { kind: "pre", gameId: 9 } });
  document.body.append(root);
  assert.deepEqual(hrefs(root), WALK, "every stop on the track, the book last");
  assert.deepEqual(inView(root), ["#season", "#program=9", "#program=10"], "three in view, the stop on screen in the middle");
  assert.deepEqual(lit(root), ["#program=9"], "the Pre-Game on screen wears the ring");
  assert.equal(root.querySelector(".rail__chip--lit").getAttribute("aria-current"), "page");
  const out = root.querySelectorAll(".rail__chip").filter((c) => c.getAttribute("aria-hidden") === "true");
  assert.ok(out.length === 6 && out.every((c) => c.getAttribute("tabindex") === "-1"), "the stops out of view take no tab");
  assert.deepEqual(nowAt(root), ["#program=9"], "Now under the stop that leads now (the line's current)");
  assert.ok(root.querySelector(".rail__slot--now .rail__now").textContent.includes("Now"));
  const t = root.textContent;
  assert.ok(!t.includes("Bye") && !t.includes("Oct"), "no byes, no dates: " + t);
  const post = chipAt(root, "#postgame=7");
  assert.ok(post.textContent.includes("Post-Game") && post.textContent.includes("Wk 7 · at Texas") && post.textContent.includes("W 27-24"), post.textContent);
  assert.ok(post.querySelector(".rail__result--won"));
  const pre = root.querySelector(".rail__chip--lit");
  assert.ok(pre.textContent.includes("Pre-Game") && pre.textContent.includes("Wk 9 · Georgia · Sat 3:30"), pre.textContent);
  const team = root.querySelector(".rail__chip--season");
  assert.ok(team.querySelector(".rail__mark--diamond") && team.textContent === "My Team", "My Team alone, the Now word moved under the current stop: " + team.textContent);
  const book = root.querySelector(".rail__chip--book");
  assert.ok(book.textContent.includes("Season book") && book.textContent.includes("so far"), book.textContent);
  // the arrows sit at the row's ends, outside the row
  const kids = Array.from(root.children);
  assert.ok(kids[0].classList.contains("rail__step--prev") && kids[kids.length - 1].classList.contains("rail__step--next"), "‹ first, › last");
  assert.equal(root.querySelector(".rail__row .rail__step"), null, "no arrow inside the row");
  assert.equal(stepHref(root, "prev"), "#season", "back from the next game's Pre-Game: My Team");
  assert.equal(stepLabel(root, "prev"), "Back to My Team");
  assert.equal(stepHref(root, "next"), "#program=10");
  assert.equal(stepLabel(root, "next"), "Forward to Pre-Game Program · Wk 10 · Oklahoma");
  console.log("ok row");
};

scenarios.slide = async () => {
  const { rail, _resetSlide } = await import(moduleUrl("ui/rail.js"));
  _resetSlide();
  const track = (root) => root.querySelector(".rail__track");
  const first = rail({ line: LINE, viewing: { kind: "pre", gameId: 9 } });
  assert.equal(track(first).style["--n"], "9");
  assert.equal(track(first).style["--at"], "4", "the first rail drawn sits still, the center's left neighbor first");
  assert.ok(!track(first).classList.contains("rail__track--still"));
  document.body.append(first);
  await advance(40); // on the page: where it stands is remembered
  // the page drawn after ‹: the track starts where the last one stood, then slides one stop once it is on the page
  first.remove();
  const back = rail({ line: LINE, viewing: { kind: "season" } });
  assert.equal(track(back).style["--at"], "4", "drawn where the last rail stood");
  assert.ok(track(back).classList.contains("rail__track--still"), "no transition for the start position");
  document.body.append(back);
  await advance(80); // the fake clock owns every timer
  assert.equal(track(back).style["--at"], "3", "then slid: My Team in the middle");
  assert.ok(!track(back).classList.contains("rail__track--still"));
  // a copy drawn and thrown away (the finished game's Pre-Game builds its cover twice) never moves where the rail stood
  const thrown = rail({ line: LINE, viewing: { kind: "pre", gameId: 10 } });
  await advance(1000);
  assert.ok(!thrown.isConnected);
  back.remove();
  const ahead = rail({ line: LINE, viewing: { kind: "pre", gameId: 9 } });
  assert.equal(track(ahead).style["--at"], "3", "it starts from My Team, the rail that was on the page, not the thrown copy");
  document.body.append(ahead);
  await advance(80);
  assert.equal(track(ahead).style["--at"], "4");
  // the Preseason in the middle: the slot on its left is empty, so it still sits in the center
  _resetSlide();
  const magazine = rail({ line: LINE, viewing: { kind: "preseason" } });
  assert.equal(track(magazine).style["--at"], "-1");
  assert.deepEqual(inView(magazine), ["#preseason", "#postgame=1"]);
  // the slots out of view are hidden from a screen reader, the Now tag with them
  const nine = rail({ line: LINE, viewing: { kind: "post", gameId: 1 } });
  const nowSlot = nine.querySelector(".rail__slot--now");
  assert.equal(nowSlot.getAttribute("aria-hidden"), "true", "Now under a stop out of view is not read out of context");
  console.log("ok slide");
};

scenarios.stepping = async () => {
  const { rail, walk, steps } = await import(moduleUrl("ui/rail.js"));
  // the walk: no byes; week 1's Pre-Game was never kept (missing), so its Post-Game follows the Preseason; the book last
  assert.deepEqual(walk(LINE).map((s) => s.href), WALK);
  const around = (viewing) => {
    const root = rail({ line: LINE, viewing });
    return [stepHref(root, "prev"), stepHref(root, "next")];
  };
  assert.deepEqual(around({ kind: "season" }), ["#postgame=7", "#program=9"]);
  assert.deepEqual(around({ kind: "post", gameId: 7 }), ["#program=7?tab=pre", "#season"]);
  assert.equal(stepLabel(rail({ line: LINE, viewing: { kind: "post", gameId: 7 } }), "prev"), "Back to Pre-Game Program · Wk 7 · at Texas");
  assert.deepEqual(around({ kind: "pre", gameId: 7 }), ["#postgame=1", "#postgame=7"], "the Pre-Game as it stood steps back past the bye to the game before");
  assert.deepEqual(around({ kind: "post", gameId: 1 }), ["#preseason", "#program=7?tab=pre"]);
  assert.equal(stepLabel(rail({ line: LINE, viewing: { kind: "post", gameId: 1 } }), "prev"), "Back to Preseason Magazine");
  const magazine = rail({ line: LINE, viewing: { kind: "preseason" } });
  assert.equal(stepHref(magazine, "prev"), null, "the Preseason: nothing before it");
  assert.ok(magazine.querySelector(".rail__step--prev.rail__step--off"), "an end with nowhere to go is drawn dim, so the row never jumps");
  assert.equal(stepHref(magazine, "next"), "#postgame=1");
  const ten = rail({ line: LINE, viewing: { kind: "pre", gameId: 10 } });
  assert.deepEqual(lit(ten), ["#program=10"], "a game ahead previewed: its chip, lit");
  assert.deepEqual([stepHref(ten, "prev"), stepHref(ten, "next")], ["#program=9", "#program=11"]);
  const eleven = rail({ line: LINE, viewing: { kind: "pre", gameId: 11 } });
  assert.deepEqual([stepHref(eleven, "prev"), stepHref(eleven, "next")], ["#program=10", "#review"], "after the last game: the season book");
  assert.equal(stepLabel(eleven, "next"), "Forward to Season book, the season so far");
  const book = rail({ line: LINE, viewing: { kind: "book" } });
  assert.deepEqual(lit(book), ["#review"]);
  assert.deepEqual(inView(book), ["#program=11", "#review"]);
  assert.deepEqual([stepHref(book, "prev"), stepHref(book, "next")], ["#program=11", null], "the book is the far end");
  assert.ok(book.querySelector(".rail__step--next.rail__step--off"));
  // a page not on the walk starts at My Team: no viewing, a stop the line does not open (week 1's Pre-Game), a game it does not know
  for (const viewing of [null, undefined, {}, { kind: "pre", gameId: 1 }, { kind: "post", gameId: 99 }, { kind: "pre" }, "x"]) {
    assert.deepEqual(around(viewing), ["#postgame=7", "#program=9"], `from My Team: ${JSON.stringify(viewing)}`);
    assert.deepEqual(steps(LINE, viewing), { prev: walk(LINE)[3], next: walk(LINE)[5] });
    assert.deepEqual(lit(rail({ line: LINE, viewing })), [], "nothing lit for a page not on the walk");
  }
  console.log("ok stepping");
};

scenarios.pastWeeks = async () => {
  const { rail } = await import(moduleUrl("ui/rail.js"));
  const oldPost = rail({ line: LINE, viewing: { kind: "post", gameId: 1 } });
  assert.deepEqual(inView(oldPost), ["#preseason", "#postgame=1", "#program=7?tab=pre"]);
  assert.deepEqual(lit(oldPost), ["#postgame=1"]);
  assert.deepEqual(nowAt(oldPost), ["#program=9"], "Now stays under this week's Pre-Game while an old week is on screen");
  const oldPre = rail({ line: LINE, viewing: { kind: "pre", gameId: 7 } });
  assert.deepEqual(inView(oldPre), ["#postgame=1", "#program=7?tab=pre", "#postgame=7"]);
  assert.deepEqual(lit(oldPre), ["#program=7?tab=pre"], "the Pre-Game as it stood at kickoff, lit");
  assert.ok(oldPre.querySelector(".rail__chip--lit").textContent.includes("W 27-24"), "a played game's Pre-Game shows the result, not a kickoff time");
  assert.deepEqual(lit(rail({ line: LINE, viewing: { kind: "season" } })), ["#season"]);
  assert.deepEqual(lit(rail({ line: LINE, viewing: { kind: "preseason" } })), ["#preseason"]);
  console.log("ok pastWeeks");
};

scenarios.ends = async () => {
  const { rail, walk } = await import(moduleUrl("ui/rail.js"));
  // before the first game: no Post-Game yet; Now under the Magazine when it leads
  const august = { current: { kind: "preseason" }, items: [LINE.items[0], { kind: "now", href: "#season" }, week(1, "Florida Atlantic", "home", "2026-09-05T19:00-04:00", null, "open", "to_come"), LINE.items[LINE.items.length - 1]] };
  const start = rail({ line: august, viewing: { kind: "season" } });
  assert.deepEqual(inView(start), ["#preseason", "#season", "#program=1"]);
  assert.deepEqual(nowAt(start), ["#preseason"]);
  assert.deepEqual([stepHref(start, "prev"), stepHref(start, "next")], ["#preseason", "#program=1"]);
  // the season over: the book closes the walk, final
  const december = { current: { kind: "book" }, items: [...LINE.items.filter((i) => (i.kind !== "week" || i.result) && i.kind !== "book"), { kind: "book", state: "open", href: "#review", label: "Season book", date: null }] };
  const over = rail({ line: december, viewing: { kind: "season" } });
  assert.deepEqual(hrefs(over), ["#preseason", "#postgame=1", "#program=7?tab=pre", "#postgame=7", "#season", "#review"]);
  assert.deepEqual([stepHref(over, "prev"), stepHref(over, "next")], ["#postgame=7", "#review"]);
  assert.deepEqual(nowAt(over), ["#review"], "Now under the book once it leads");
  assert.ok(over.querySelector(".rail__chip--book").textContent.includes("final"));
  // a line with no now marker: My Team after the last game played, before the Pre-Games to come, the book still last
  const unmarked = { items: LINE.items.filter((i) => i.kind !== "now") };
  assert.deepEqual(walk(unmarked).map((s) => s.href), WALK);
  // no current on the line: no Now tag, never a crash
  assert.deepEqual(nowAt(rail({ line: { items: LINE.items }, viewing: { kind: "season" } })), []);
  console.log("ok ends");
};

scenarios.quiet = async () => {
  const { rail } = await import(moduleUrl("ui/rail.js"));
  const root = rail({ line: null, viewing: { kind: "pre", gameId: 9 } });
  assert.ok(root.classList.contains("rail--quiet") && root.textContent.includes("loading"));
  assert.equal(root.querySelectorAll(".rail__step").length, 0, "no arrows before the line comes");
  const broken = rail({ line: { current: "x", items: [null, "x", { kind: "week", week: 2, gameId: 2, stops: null }, { kind: "week", week: 3, gameId: 3, stops: { pre: { state: "open", date: "x", href: "#program=3" } } }, { kind: "preseason", href: 7 }, { kind: "book", href: 5, state: 9 }] }, viewing: null });
  assert.deepEqual(hrefs(broken), ["#season", "#program=3", "#review"], "a malformed item is skipped, never a crash; My Team is always there");
  assert.deepEqual([stepHref(broken, "prev"), stepHref(broken, "next")], [null, "#program=3"], "the walk skips what it cannot read");
  const { walk, steps } = await import(moduleUrl("ui/rail.js"));
  for (const bad of [null, undefined, "x", 7, [], {}, { items: "x" }, { items: [null, 3, "y", { kind: "week" }, { kind: "week", stops: { pre: { href: 5 }, post: "x" } }] }]) {
    assert.deepEqual(walk(bad).map((s) => s.kind), ["season"], `only My Team on ${JSON.stringify(bad)}`);
    assert.deepEqual(steps(bad, { kind: "post", gameId: 1 }), { prev: null, next: null });
  }
  assert.ok(!broken.textContent.includes("undefined") && !broken.textContent.includes("NaN") && !broken.textContent.includes("null"), broken.textContent);
  console.log("ok quiet");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["row", "slide", "stepping", "pastWeeks", "ends", "quiet"])
def test_rail(tmp_path, scenario):
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_tab_pair_is_gone_and_the_arrows_sit_at_the_ends() -> None:
    """Runs without Node: the finished game's Pre-Game / Post-Game tabs and their rules are gone (owner 2026-11-15), the rail is
    a row of three, the track between the two arrows, and the track slides (batch 4)."""
    root = Path(__file__).resolve().parents[1]
    program = (root / "static" / "js" / "views" / "program.js").read_text(encoding="utf-8")
    assert "programTabs" not in program and "program-tabs" not in program
    css = (root / "static" / "css" / "components.css").read_text(encoding="utf-8")
    assert ".program-tab" not in css and ".rail__pre" not in css
    rail = css[css.index("\n.rail {") :].split("}")[0]
    assert "display: flex" in rail
    row = css[css.index("\n.rail__row {") :].split("}")[0]
    assert "min-width: 0" in row and "overflow: hidden" in row
    track = css[css.index("\n.rail__track {") :].split("}")[0]
    assert "100% / 3" in track and "transition: transform" in track
    assert "@media (prefers-reduced-motion: reduce) { .rail__track { transition: none; }" in css
    step = css[css.index("\n.rail__step {") :].split("}")[0]
    assert "flex: none" in step and "min-width: var(--tap)" in step
