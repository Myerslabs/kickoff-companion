"""Phase 17 #35 in the fake browser: the roster breakdown. Positions down, four classes across, a redshirt marked (RS) (Phase 18.4;
CFBD's fifth year is a senior with a redshirt), row and column totals, a name chip per player with our stat grade in its color (best first in a
cell), a name-only chip without a grade, a tap that opens the player, and damaged rows left out with a note. Tables wave 3: sized by its own
box (the class names, then the surnames, then the class codes over each cell's count), never a sideways scroll box, its note
following the size."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const form = (node, which) => { const t = node && node.querySelector(`.sz-t--${which}`); return (t ? t.textContent : text(node)).replace(/\u00A0/g, " "); }; // a sized label's words ("J.", a no-break space, the surname: item 6)

scenarios.grid = async () => {
  const { rosterGrid, CLASS_COLUMNS } = await import(moduleUrl("ui/roster-grid.js"));
  assert.deepEqual(CLASS_COLUMNS.map((c) => c[1]), ["Freshman", "Sophomore", "Junior", "Senior"]);
  const opened = [];
  const players = [
    { playerId: "1", firstName: "Zed", lastName: "Woodson", number: 7, position: "QB", classYear: "FR", grade: { grade: 70.4, label: "Good" } },
    { playerId: "2", firstName: "Jo", lastName: "Oleary", number: 12, position: "QB", classYear: "FR", grade: { grade: 82 } },
    { playerId: "3", name: "Big Lineman", number: 70, position: "OT", classYear: "SR", redshirt: true, grade: { grade: null, reason: "Offensive linemen have no individual stats" } },
    { playerId: "4", firstName: "Sam", lastName: "Sparks", number: null, position: "RB", classYear: "JR", grade: null },
    { playerId: "5", firstName: "No", lastName: "Class", number: 1, position: "WR", classYear: null },
    { playerId: "6", firstName: "No", lastName: "Spot", number: 2, position: "XX", classYear: "SO" },
    null, "junk",
  ];
  const grid = rosterGrid(players, { onPlayer: (p) => opened.push(p.playerId) });
  document.body.append(grid);
  const t = text(grid);
  assert.ok(!RAW.test(t), t.slice(0, 300));
  // wave 3: sized by its own box, never a sideways scroll box; large to start (the page measures it)
  const fit = grid.querySelector(".stat-table-wrap.rgrid-fit");
  assert.ok(fit && fit.querySelector("table.rgrid"), "the grid is a sized wrap inside .rgrid-wrap");
  assert.equal(fit.dataset.size, "large");
  assert.equal(grid.dataset.size, "large", "the outer wrap carries the size for its note");
  assert.equal(typeof fit.measure, "function", "the wrap is measured on resize, fonts and its own width");
  const heads = grid.querySelectorAll("thead th").slice(1);
  assert.deepEqual(heads.map((th) => form(th, "long")), ["Freshman", "Sophomore", "Junior", "Senior", "Players"]);
  assert.deepEqual(heads.map((th) => form(th, "mid")), ["Freshman", "Sophomore", "Junior", "Senior", "Players"]);
  assert.deepEqual(heads.map((th) => form(th, "short")), ["FR", "SO", "JR", "SR", "#"], "a phone: the class codes, # over the totals");
  assert.deepEqual(heads.map((th) => th.dataset.term), ["Freshman", "Sophomore", "Junior", "Senior", "Players"], "the hints read the whole word");
  const rows = grid.querySelectorAll("tbody tr");
  assert.deepEqual(rows.map((r) => text(r.querySelector("th"))), ["QB", "RB", "OL"], "only rows with players, in order");
  // the QB freshmen: best grade first, the initial and surname at large, the surname from medium, the grade in its tier's color
  const qbFr = rows[0].querySelectorAll("td")[0].querySelectorAll(".rgrid__chip");
  assert.deepEqual(qbFr.map((c) => form(c.querySelector(".rgrid__name"), "long")), ["J. Oleary", "Z. Woodson"]);
  assert.deepEqual(qbFr.map((c) => form(c.querySelector(".rgrid__name"), "mid")), ["Oleary", "Woodson"]);
  assert.equal(text(qbFr[0].querySelector(".rgrid__grade")), "82");
  assert.ok(qbFr[0].querySelector(".rgrid__grade").className.includes("rgrid__grade--very-good"));
  assert.equal(qbFr[1].querySelector(".rgrid__jersey"), null, "no jersey drawing (owner: just the name)");
  assert.equal(form(qbFr[1].querySelector(".rgrid__name"), "long") + text(qbFr[1].querySelector(".rgrid__grade")), "Z. Woodson70", "the name and the grade, nothing else");
  assert.equal(qbFr[1].getAttribute("aria-label"), "Zed Woodson, number 7, stat grade 70", "the whole name for a screen reader");
  // a fifth-year lineman: name only, no grade; the redshirt mark at every size (it is data)
  const ol = rows[2].querySelectorAll("td")[3].querySelector(".rgrid__chip");
  assert.equal(form(ol.querySelector(".rgrid__name"), "long"), "B. Lineman (RS)");
  assert.equal(form(ol.querySelector(".rgrid__name"), "mid"), "Lineman (RS)");
  assert.equal(ol.querySelector(".rgrid__grade"), null);
  // small: each cell's count beside its chips (the stylesheet shows one or the other by the size); an empty cell stays empty
  assert.deepEqual(rows[0].querySelectorAll("td.rgrid__cell").map((td) => text(td.querySelector(".rgrid__count"))), ["2", "", "", ""]);
  assert.equal(rows[0].querySelectorAll("td.rgrid__cell")[1].childNodes.length, 0, "no chips, no count: an empty cell");
  // totals: each row, each column, and the whole
  assert.equal(text(rows[0].querySelector(".rgrid__total")), "2");
  const foot = grid.querySelectorAll("tfoot td").map(text);
  assert.deepEqual(foot, ["2", "0", "1", "1", "4"]);
  // the note says what the numbers are at each size: the grades over the chips, the counts at small
  assert.ok(text(grid.querySelector(".rgrid__note--chips")).startsWith("The number is our stat grade"));
  assert.ok(text(grid.querySelector(".rgrid__note--counts")).startsWith("Players at each position by class."));
  // a tap opens the player; rows with no class or an unknown position are counted in a note
  qbFr[1].click();
  assert.deepEqual(opened, ["1"]);
  assert.ok(t.includes("2 players have no class or position"));
  assert.ok(text(rosterGrid([])).includes("appears once the roster has loaded"));
  // a name alone (no first and last) still makes both forms; a junk name dashes
  const odd = rosterGrid([{ name: "Prince", position: "WR", classYear: "SO" }, { name: 7, position: "TE", classYear: "JR", redshirt: true }]);
  assert.ok(!RAW.test(text(odd)), text(odd));
  assert.deepEqual(odd.querySelectorAll(".rgrid__name").map((n) => form(n, "long")), ["Prince", "– (RS)"]);
};

scenarios.css = async () => {
  // the stylesheet: no sideways scroll box and no fixed minimum width (wave 3); the counts and notes follow the size
  const fs = await import("node:fs");
  const path = await import("node:path");
  const css = fs.readFileSync(path.join(process.argv[2], "..", "css", "components.css"), "utf-8");
  const wrapRule = css.split(".rgrid-wrap {")[1].split("}")[0];
  assert.ok(!wrapRule.includes("overflow"), wrapRule);
  const gridRule = css.split(".rgrid {")[1].split("}")[0];
  assert.ok(!gridRule.includes("min-width") && !gridRule.includes("table-layout: fixed"), gridRule);
  assert.ok(css.includes('.rgrid-fit[data-size="small"] .rgrid__stack { display: none; }'));
  assert.ok(css.includes('.rgrid-fit[data-size="small"] .rgrid__count { display: inline; }'));
  assert.ok(css.includes('.rgrid-wrap[data-size="small"] .rgrid__note--chips, .rgrid-wrap:not([data-size="small"]) .rgrid__note--counts { display: none; }'));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["grid", "css"])
def test_roster_grid_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
