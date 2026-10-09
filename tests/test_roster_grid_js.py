"""Phase 17 #35 in the fake browser: the roster breakdown. Positions down, four classes across, a redshirt marked (RS) (Phase 18.4;
CFBD's fifth year is a senior with a redshirt), row and column totals, a name chip per player with our stat grade in its color (best first in a
cell), a name-only chip without a grade, a tap that opens the player, and damaged rows left out with a note."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

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
  const heads = grid.querySelectorAll("thead th").map(text);
  assert.deepEqual(heads.slice(1), ["Freshman", "Sophomore", "Junior", "Senior", "Players"]);
  const rows = grid.querySelectorAll("tbody tr");
  assert.deepEqual(rows.map((r) => text(r.querySelector("th"))), ["QB", "RB", "OL"], "only rows with players, in order");
  // the QB freshmen: best grade first, short names, the grade in its tier's color, no jersey
  const qbFr = rows[0].querySelectorAll("td")[0].querySelectorAll(".rgrid__chip");
  assert.deepEqual(qbFr.map((c) => text(c.querySelector(".rgrid__name"))), ["J. Oleary", "Z. Woodson"]);
  assert.equal(text(qbFr[0].querySelector(".rgrid__grade")), "82");
  assert.ok(qbFr[0].querySelector(".rgrid__grade").className.includes("rgrid__grade--very-good"));
  assert.equal(qbFr[1].querySelector(".rgrid__jersey"), null, "no jersey drawing (owner: just the name)");
  assert.equal(text(qbFr[1]), "Z. Woodson70", "the name and the grade, nothing else");
  // a fifth-year lineman: name only, no grade
  const ol = rows[2].querySelectorAll("td")[3].querySelector(".rgrid__chip");
  assert.equal(text(ol.querySelector(".rgrid__name")), "B. Lineman (RS)");
  assert.equal(ol.querySelector(".rgrid__grade"), null);
  // totals: each row, each column, and the whole
  assert.equal(text(rows[0].querySelector(".rgrid__total")), "2");
  const foot = grid.querySelectorAll("tfoot td").map(text);
  assert.deepEqual(foot, ["2", "0", "1", "1", "4"]);
  // a tap opens the player; rows with no class or an unknown position are counted in a note
  qbFr[1].click();
  assert.deepEqual(opened, ["1"]);
  assert.ok(t.includes("2 players have no class or position"));
  assert.ok(text(rosterGrid([])).includes("appears once the roster has loaded"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["grid"])
def test_roster_grid_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
