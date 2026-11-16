"""Leaders side by side in the fake browser. BUG-14 (the owner's board of 2026-10-26): each category in the Tale of the
tape's kit, the leaders pulled to the middle over it, a row a stat with its FBS rank and the edge bar, the line over
conference games under it (its lead number alone on a phone); damaged entries draw as dashes, and the two names of a
category take one form. Phase 17 #17 still holds: every stat the service lists and the conference-game line."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.lines = async () => {
  const { confGamesShort, confGamesText, leaderPair, leaderPairs, levelNames, statWords } = await import(moduleUrl("ui/leader-lines.js"));
  const more = {
    label: "Passing yards", category: "passing", stat: "YDS",
    us: { detail: { stats: [{ stat: "YDS", value: 1204, national: { rank: 8, of: 130 }, conference: { rank: 2, of: 14, conference: "Big Pie" }, metric: "board:passing:YDS" }, { stat: "TD", value: 11, national: null, conference: { rank: "x" } }, { stat: "PCT", value: 0.652 }, null, { value: 3 }] }, conferenceGames: { stats: { YDS: 1610, TD: 5, INT: 1, COMPLETIONS: 40, ATT: 60 } } },
    them: { detail: { stats: [{ stat: "YDS", value: NaN }, { stat: "INT", value: 4 }] }, conferenceGames: null },
  };
  const taps = [];
  const cat = { id: "YDS-Passing yards", label: "Passing yards", category: "passing", stat: "YDS", format: "0f", us: { name: "Al One", playerId: "41", position: "QB", value: 1204, headshotUrl: null }, them: { name: "Bo Two", playerId: 7, position: "QB", value: 900 }, more };
  const node = leaderPair(cat, { usAbbr: "FLA", themAbbr: "OPP", usTeam: "Florida", themTeam: "Texas State", usConfGames: 3, themConfGames: 3, onTap: (p, side) => taps.push(`${side}:${p.name}`) });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t);
  // BUG-14 (the board of 2026-10-26): the leaders over the category, the column heads, a row a stat, the conference line
  assert.equal(node.tagName, "SECTION");
  assert.equal(text(node.querySelector(".lpair__title b")), "Passing");
  assert.equal(text(node.querySelector(".lpair__title small")), "yards", "the category's first word over the rest");
  assert.deepEqual(node.querySelector(".lpair__cols").children.map(text), ["Statistic", "FBS rank", "FLA", "Edge", "OPP", "FBS rank"], "the tape's columns");
  const rows = node.querySelectorAll(".lpair__stat");
  assert.deepEqual(rows.map((r) => text(r.querySelector(".lpair__long"))), ["Yards", "Touchdowns", "Completion %", "Interceptions"], "the board's whole stat names");
  assert.deepEqual(rows.map((r) => text(r.querySelector(".lpair__short"))), ["Yds", "TD", "Comp %", "Int"], "a phone's short ones");
  assert.deepEqual(rows[0].children.map((c) => c.className.split(" ")[0]), ["lpair__label", "lpair__rank", "lpair__val", "lpair__edge", "lpair__val", "lpair__rank"], "Statistic | FBS rank | value | Edge | value | FBS rank");
  assert.equal(text(rows[0].querySelector(".lpair__val--us")), "1,204");
  const chips = rows[0].querySelectorAll("a.rank-chip--link");
  assert.equal(chips.length, 1, "the FBS rank alone, as drawn");
  assert.equal(chips[0].getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Florida");
  assert.equal(rows[0].querySelector(".lpair__val--us a").getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Florida", "the number links to its list too");
  assert.equal(text(rows[0].querySelector(".lpair__rank--them")), "–", "no rank: a dash the chip's width, never a blank");
  assert.ok(!rows[1].querySelector(".rank-chip") && text(rows[1].querySelector(".lpair__rank--us")) === "–", "a damaged rank draws no chip");
  assert.equal(text(rows[0].querySelector(".lpair__val--them")), "–", "a damaged value is a dash");
  assert.ok(!rows[0].querySelector(".lead") && !rows[0].querySelector(".trail") && !rows[0].querySelector(".tug__bar"), "one side missing: nothing to compare, no edge");
  assert.equal(rows[0].querySelector(".tug").getAttribute("aria-label"), "No edge to show");
  assert.equal(text(rows[3].querySelector(".lpair__val--them")), "4");
  const conf = node.querySelector(".lpair__confrow");
  assert.equal(text(conf.querySelector(".lpair__label")), "In 3 games");
  assert.equal(text(conf.querySelector(".lpair__line--us .lpair__long")), "1,610 yds, 40/60, 5 TD, 1 int");
  assert.equal(text(conf.querySelector(".lpair__line--us .lpair__short")), "1,610 yds", "a phone keeps the lead number alone");
  assert.equal(text(conf.querySelector(".lpair__line--them")), "–");
  // the leaders: a button to the card when the chart knows the player, the faces against the category
  const who = node.querySelectorAll(".lpair__who");
  assert.equal(who.length, 2);
  assert.ok(who[0].tagName === "BUTTON" && who[0].className.includes("lpair__who--us") && who[1].className.includes("lpair__who--them"));
  assert.ok(who[0].children[0].className.includes("lpair__id") && who[1].children[1].className.includes("lpair__id"), "the names outside the faces");
  assert.equal(text(who[0].querySelector(".lpair__meta")), "FLA QB");
  who[1].click();
  assert.deepEqual(taps, ["them:Bo Two"]);
  // the edge: the bar leans to the better number, longer for a bigger gap in rank; fewer interceptions is better
  const both = { ...cat, more: { category: "passing", us: { detail: { stats: [{ stat: "YDS", value: 2042, national: { rank: 8, of: 130 } }, { stat: "INT", value: 2 }] } }, them: { detail: { stats: [{ stat: "YDS", value: 1500, national: { rank: 60, of: 130 } }, { stat: "INT", value: 9 }] } } } };
  const edged = leaderPair(both, { usAbbr: "FLA", themAbbr: "OPP" }).querySelectorAll(".lpair__stat");
  assert.equal(edged[0].querySelector(".tug__bar--us").style.width, "40%", "52 ranks apart of 130: four fifths of the half");
  assert.ok(edged[0].querySelector(".lpair__val--us").className.includes("lead") && edged[0].querySelector(".lpair__val--them").className.includes("trail"));
  assert.ok(edged[1].querySelector(".tug__bar--us"), "two interceptions beat nine");
  assert.equal(edged[1].querySelector(".tug").getAttribute("aria-label"), "FLA has the edge");
  assert.ok(!leaderPair(both, {}).querySelector(".lpair__confrow"), "no conference games: no line");
  // before the whole lines arrive: the program's own line, the category's key number; an empty side says so
  const own = leaderPair({ label: "Sacks", category: "defensive", stat: "SACKS", format: "1f", us: { name: "Cy Three", value: 4.5 }, them: null }, { usAbbr: "FLA", themAbbr: "OPP" });
  assert.equal(own.querySelectorAll(".lpair__stat").length, 1);
  assert.equal(text(own.querySelector(".lpair__stat .lpair__label")), "Sacks");
  assert.equal(text(own.querySelector(".lpair__title")), "Sacks", "a one-word category has no second line");
  assert.equal(text(own.querySelector(".lpair__stat .lpair__val--us")), "4.5 sacks");
  assert.equal(text(own.querySelector(".lpair__stat .lpair__val--them")), "–");
  assert.ok(text(own.querySelector(".lpair__who--them")).includes("No OPP line yet") && own.querySelector(".lpair__who--us").tagName !== "BUTTON", "no player id: not a button");
  // the two names of a category in one form: the shorter of the two the fit chose
  const host = leaderPairs([cat, null, "junk", {}], {});
  assert.equal(host.querySelectorAll(".lpair").length, 2);
  const names = host.querySelectorAll(".lpair")[0].querySelectorAll(".lpair__who .pn");
  names[0].dataset.pn = "full";
  names[1].dataset.pn = "initial";
  levelNames(host);
  assert.deepEqual(names.map((pn) => pn.dataset.pn), ["initial", "initial"]);
  levelNames(null);
  assert.ok(!RAW.test(text(leaderPair({ label: 4, us: "x", them: [], more: { us: { detail: { stats: "junk" } }, them: 7 } }, {}))));
  assert.deepEqual(statWords("TFL", "defensive"), { long: "Tackles for loss", short: "TFL" });
  assert.deepEqual(statWords("PCT", "kicking"), { long: "Field goal %", short: "FG %" });
  assert.deepEqual(statWords("ZZZ", "passing"), { long: "ZZZ", short: "ZZZ" });
  assert.equal(confGamesShort("passing", { YDS: 610, TD: 5 }), "610 yds");
  for (const junk of [null, "x", { YDS: "x" }]) assert.equal(confGamesShort("rushing", junk), null);
  assert.equal(confGamesText("passing", null), null);
  assert.equal(confGamesText("rushing", { YDS: "x" }), null);
};

scenarios.grid = async () => {
  const { leadersGrid } = await import(moduleUrl("ui/leaders.js"));
  const detail = document.createElement("div");
  detail.textContent = "LINES";
  const grid = leadersGrid({ categories: [{ id: "a", label: "Passing yards", us: { name: "A", line: "1 yds" }, them: null, detail }, { id: "b", label: "Sacks", us: null, them: null, detail: "not a node" }], usAbbr: "FLA", themAbbr: "OPP" });
  document.body.append(grid);
  assert.equal(grid.querySelectorAll(".leader-cat__detail").length, 1);
  assert.ok(text(grid).includes("LINES"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["lines", "grid"])
def test_leader_lines_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_bug14_the_leaders_sit_on_the_tapes_columns() -> None:
    """BUG-14: every row of a category on the same six columns (the board's Statistic | FBS rank | value | Edge | value |
    FBS rank), the leaders over the stats pulled to the middle; a phone drops the rank columns and the leaders meet over
    the middle of the bars; a wide band puts two categories side by side."""
    css = (Path(__file__).resolve().parents[1] / "static" / "css" / "components.css").read_text(encoding="utf-8")
    assert ".lpair { --lp-cols: minmax(8.5em, 11em) 60px minmax(84px, 0.3fr) minmax(72px, 1fr) minmax(84px, 0.3fr) 60px;" in css
    assert ".lpair__heads > .lpair__who--us { grid-column: 1 / 4; justify-self: end; }" in css
    assert ".lpair__heads > .lpair__who--them { grid-column: 5 / 7; justify-self: start; }" in css
    phone = css[css.index("@container (max-width: 559px) {\n  /* a phone: the rank columns go") :]
    assert ".lpair__row > .lpair__rank { display: none; }" in phone and ".lpair__heads > .lpair__who--them { grid-column: 2; grid-row: 2; }" in phone  # 1.40.8 (owner 2026-11-15): the two leaders in equal halves under the category
    assert "@container (min-width: 1300px) {\n  .lpairs { grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".lpair__pole" not in css and "--lpair-rows" not in css, "the old pole layout is gone"
