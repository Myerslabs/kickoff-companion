"""The rail, one short row since 2026-11-14 (owner: "smaller", "very busy"): Preseason, the last Post-Game, Now and the next
Pre-Game; the lit chip, a past week's stop, the end of the season and bad data. Since 2026-11-15 (owner: "Always start on the
'now' and be able to move forward and backwards by clicking or tapping the arrows"; his pick, arrows at the row's ends) a ‹ and
a › outside the chips step one stop at a time both ways through the season's walk: the Preseason, each game's Pre-Game then its
Post-Game, Now where the line puts it, the Pre-Games to come; from a page not on the walk they start at Now."""
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
const lit = (root) => root.querySelectorAll(".rail__chip--lit").map((c) => c.getAttribute("href"));
const stepHref = (root, which) => {
  const a = root.querySelector(`a.rail__step--${which}`);
  return a ? a.getAttribute("href") : null;
};
const stepLabel = (root, which) => root.querySelector(`a.rail__step--${which}`)?.getAttribute("aria-label") || null;

scenarios.row = async () => {
  const { rail } = await import(moduleUrl("ui/rail.js"));
  const root = rail({ line: LINE, viewing: { kind: "pre", gameId: 9 } });
  document.body.append(root);
  assert.deepEqual(hrefs(root), ["#preseason", "#postgame=7", "#season", "#program=9"], "four chips in order: the last Post-Game is the last game played");
  assert.deepEqual(lit(root), ["#program=9"], "the Pre-Game on screen wears the ring");
  assert.equal(root.querySelector(".rail__chip--lit").getAttribute("aria-current"), "page");
  const t = root.textContent;
  assert.ok(!t.includes("bye") && !t.includes("Season book") && !t.includes("Oct"), "no byes, no book, no dates: " + t);
  const post = root.querySelector(".rail__chip--post");
  assert.ok(post.textContent.includes("Post-Game") && post.textContent.includes("Wk 7 · at Texas") && post.textContent.includes("W 27-24"), post.textContent);
  assert.ok(post.querySelector(".rail__result--won"));
  const pre = root.querySelector(".rail__chip--pre");
  assert.ok(pre.textContent.includes("Pre-Game") && pre.textContent.includes("Wk 9 · Georgia · Sat 3:30"), pre.textContent);
  const now = root.querySelector(".rail__chip--now");
  assert.ok(now.querySelector(".rail__mark--diamond") && now.textContent.includes("Now") && now.textContent.includes("My Team"));
  // the arrows sit at the row's ends, outside the chips' sideways scroll, so a phone keeps both in reach
  const kids = Array.from(root.children);
  assert.ok(kids[0].classList.contains("rail__step--prev") && kids[kids.length - 1].classList.contains("rail__step--next"), "‹ first, › last");
  assert.equal(root.querySelector(".rail__row .rail__step"), null, "no arrow inside the row of chips");
  assert.equal(root.querySelector(".rail__pre"), null, "the Pre-Game chip carries no ‹ › of its own any more");
  assert.equal(stepHref(root, "prev"), "#season", "back from the next game's Pre-Game: Now");
  assert.equal(stepLabel(root, "prev"), "Back to My Team, now");
  assert.equal(stepHref(root, "next"), "#program=10");
  assert.equal(stepLabel(root, "next"), "Forward to Pre-Game Program · Wk 10 · Oklahoma");
  console.log("ok row");
};

scenarios.stepping = async () => {
  const { rail, walk, steps } = await import(moduleUrl("ui/rail.js"));
  // the walk: no byes, no book; week 1's Pre-Game was never kept (missing), so its Post-Game follows the Preseason
  assert.deepEqual(walk(LINE).map((s) => s.href), ["#preseason", "#postgame=1", "#program=7?tab=pre", "#postgame=7", "#season", "#program=9", "#program=10", "#program=11"]);
  const around = (viewing) => {
    const root = rail({ line: LINE, viewing });
    return [stepHref(root, "prev"), stepHref(root, "next")];
  };
  // My Team is Now: back to the last Post-Game, ahead to the next Pre-Game
  assert.deepEqual(around({ kind: "season" }), ["#postgame=7", "#program=9"]);
  // from the last Post-Game back to that game's Pre-Game as it stood at kickoff, ahead to Now
  assert.deepEqual(around({ kind: "post", gameId: 7 }), ["#program=7?tab=pre", "#season"]);
  assert.equal(stepLabel(rail({ line: LINE, viewing: { kind: "post", gameId: 7 } }), "prev"), "Back to Pre-Game Program · Wk 7 · at Texas");
  assert.deepEqual(around({ kind: "pre", gameId: 7 }), ["#postgame=1", "#postgame=7"], "the Pre-Game as it stood steps back past the bye to the game before");
  assert.deepEqual(around({ kind: "post", gameId: 1 }), ["#preseason", "#program=7?tab=pre"]);
  assert.equal(stepLabel(rail({ line: LINE, viewing: { kind: "post", gameId: 1 } }), "prev"), "Back to Preseason Magazine");
  const magazine = rail({ line: LINE, viewing: { kind: "preseason" } });
  assert.equal(stepHref(magazine, "prev"), null, "the Preseason: nothing before it");
  assert.ok(magazine.querySelector(".rail__step--prev.rail__step--off"), "an end with nowhere to go is drawn dim, so the row never jumps");
  assert.equal(stepHref(magazine, "next"), "#postgame=1");
  // ahead through the games still to come, as before
  const ten = rail({ line: LINE, viewing: { kind: "pre", gameId: 10 } });
  assert.deepEqual(lit(ten), ["#program=10"], "a game ahead previewed: its chip, lit");
  assert.deepEqual([stepHref(ten, "prev"), stepHref(ten, "next")], ["#program=9", "#program=11"]);
  const eleven = rail({ line: LINE, viewing: { kind: "pre", gameId: 11 } });
  assert.deepEqual([stepHref(eleven, "prev"), stepHref(eleven, "next")], ["#program=10", null], "the last game: no step forward");
  assert.ok(eleven.querySelector(".rail__step--next.rail__step--off"));
  // a page not on the walk starts at Now: no viewing, a stop the line does not open (week 1's Pre-Game), a game it does not know
  for (const viewing of [null, undefined, {}, { kind: "pre", gameId: 1 }, { kind: "post", gameId: 99 }, { kind: "pre" }, "x"]) {
    assert.deepEqual(around(viewing), ["#postgame=7", "#program=9"], `from Now: ${JSON.stringify(viewing)}`);
    assert.deepEqual(steps(LINE, viewing), { prev: walk(LINE)[3], next: walk(LINE)[5] });
  }
  console.log("ok stepping");
};

scenarios.pastWeeks = async () => {
  const { rail } = await import(moduleUrl("ui/rail.js"));
  const oldPost = rail({ line: LINE, viewing: { kind: "post", gameId: 1 } });
  assert.deepEqual(hrefs(oldPost), ["#preseason", "#postgame=1", "#season", "#program=9"], "a past Post-Game on screen takes the chip's place");
  assert.deepEqual(lit(oldPost), ["#postgame=1"]);
  const oldPre = rail({ line: LINE, viewing: { kind: "pre", gameId: 7 } });
  assert.deepEqual(hrefs(oldPre), ["#preseason", "#postgame=7", "#season", "#program=7?tab=pre"]);
  assert.deepEqual(lit(oldPre), ["#program=7?tab=pre"], "the Pre-Game as it stood at kickoff, lit");
  assert.ok(oldPre.querySelector(".rail__chip--pre").textContent.includes("W 27-24"), "a played game's Pre-Game shows the result, not a kickoff time");
  assert.equal(stepHref(oldPre, "next"), "#postgame=7", "forward to the same game's Post-Game");
  const season = rail({ line: LINE, viewing: { kind: "season" } });
  assert.deepEqual(lit(season), ["#season"]);
  const magazine = rail({ line: LINE, viewing: { kind: "preseason" } });
  assert.deepEqual(lit(magazine), ["#preseason"]);
  console.log("ok pastWeeks");
};

scenarios.ends = async () => {
  const { rail, chips } = await import(moduleUrl("ui/rail.js"));
  // before the first game: no Post-Game yet
  const august = { items: [LINE.items[0], { kind: "now", href: "#season" }, week(1, "Florida Atlantic", "home", "2026-09-05T19:00-04:00", null, "open", "to_come")] };
  const start = rail({ line: august, viewing: { kind: "season" } });
  assert.deepEqual(hrefs(start), ["#preseason", "#season", "#program=1"]);
  assert.deepEqual([stepHref(start, "prev"), stepHref(start, "next")], ["#preseason", "#program=1"]);
  // the season over: no Pre-Game ahead
  const december = { items: LINE.items.filter((i) => i.kind !== "week" || i.result) };
  const c = chips(december, { kind: "season" });
  assert.equal(c.pre, null);
  assert.equal(c.post.href, "#postgame=7");
  const over = rail({ line: december, viewing: { kind: "season" } });
  assert.deepEqual(hrefs(over), ["#preseason", "#postgame=7", "#season"]);
  assert.deepEqual([stepHref(over, "prev"), stepHref(over, "next")], ["#postgame=7", null], "Now is the end of the walk");
  // a line with no now marker: Now after the last game played, before the Pre-Games to come
  const unmarked = { items: LINE.items.filter((i) => i.kind !== "now") };
  const { walk } = await import(moduleUrl("ui/rail.js"));
  assert.deepEqual(walk(unmarked).map((s) => s.href), ["#preseason", "#postgame=1", "#program=7?tab=pre", "#postgame=7", "#season", "#program=9", "#program=10", "#program=11"]);
  console.log("ok ends");
};

scenarios.quiet = async () => {
  const { rail } = await import(moduleUrl("ui/rail.js"));
  const root = rail({ line: null, viewing: { kind: "pre", gameId: 9 } });
  assert.ok(root.classList.contains("rail--quiet") && root.textContent.includes("loading"));
  assert.equal(root.querySelectorAll(".rail__step").length, 0, "no arrows before the line comes");
  const broken = rail({ line: { items: [null, "x", { kind: "week", week: 2, gameId: 2, stops: null }, { kind: "week", week: 3, gameId: 3, stops: { pre: { state: "open", date: "x", href: "#program=3" } } }, { kind: "preseason", href: 7 }] }, viewing: null });
  assert.deepEqual(hrefs(broken), ["#season", "#program=3"], "a malformed item is skipped, never a crash; Now is always there");
  assert.deepEqual([stepHref(broken, "prev"), stepHref(broken, "next")], [null, "#program=3"], "the walk skips what it cannot read");
  const { walk, steps } = await import(moduleUrl("ui/rail.js"));
  for (const bad of [null, undefined, "x", 7, [], {}, { items: "x" }, { items: [null, 3, "y", { kind: "week" }, { kind: "week", stops: { pre: { href: 5 }, post: "x" } }] }]) {
    assert.deepEqual(walk(bad).map((s) => s.kind), ["season"], `only Now on ${JSON.stringify(bad)}`);
    assert.deepEqual(steps(bad, { kind: "post", gameId: 1 }), { prev: null, next: null });
  }
  assert.ok(!broken.textContent.includes("undefined") && !broken.textContent.includes("NaN") && !broken.textContent.includes("null"), broken.textContent);
  console.log("ok quiet");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["row", "stepping", "pastWeeks", "ends", "quiet"])
def test_rail(tmp_path, scenario):
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_tab_pair_is_gone_and_the_arrows_sit_at_the_ends() -> None:
    """Runs without Node: the finished game's Pre-Game / Post-Game tabs and their rules are gone (owner 2026-11-15), and the rail
    is a row of three, the chips between the two arrows, so the chips alone scroll sideways."""
    root = Path(__file__).resolve().parents[1]
    program = (root / "static" / "js" / "views" / "program.js").read_text(encoding="utf-8")
    assert "programTabs" not in program and "program-tabs" not in program
    css = (root / "static" / "css" / "components.css").read_text(encoding="utf-8")
    assert ".program-tab" not in css and ".rail__pre" not in css
    rail = css[css.index("\n.rail {") :].split("}")[0]
    assert "display: flex" in rail
    row = css[css.index("\n.rail__row {") :].split("}")[0]
    assert "min-width: 0" in row and "overflow-x: auto" in row
    step = css[css.index("\n.rail__step {") :].split("}")[0]
    assert "flex: none" in step and "min-width: var(--tap)" in step
