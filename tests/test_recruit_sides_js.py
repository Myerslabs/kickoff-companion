"""Phase 17 #24, #36 in the fake browser: the talent band's star strips split into offense and defense for each
team in one table, with a fallback to the one strip for an older server, and nothing drawn when neither team has counts."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.sides = async () => {
  const { starsPair } = await import(moduleUrl("views/program.js"));
  const counts = { 5: 1, 4: 3, 3: 10, 2: 2, 1: 0 };
  const us = { sides: { offense: { counts, average: 3.4, signees: 16 }, defense: { counts, average: null, signees: 1 }, apart: { athlete: 2 } } };
  const them = { stars: { counts, average: 3.1 } };
  const pair = starsPair(us, them, "SWT", "OPP");
  document.body.append(pair);
  const t = text(pair);
  assert.ok(!RAW.test(t), t);
  const rows = pair.querySelectorAll("tbody tr");
  assert.deepEqual(rows.map((r) => text(r.querySelector("th"))), ["Offense 16", "Defense 1", "All"], "a row per side; theirs, from an older answer, has no split, so one row for all");
  assert.deepEqual(rows[0].querySelectorAll("td").map(text), ["1", "3", "10", "2", "0", "3.40"]);
  assert.equal(text(rows[1].querySelectorAll("td")[5]), "–", "no average is a dash");
  assert.equal(pair.querySelectorAll("table").length, 2, "one table a team, side by side");
  assert.ok(text(pair.querySelectorAll("caption")[0]).startsWith("SWT") && text(pair.querySelectorAll("caption")[1]).startsWith("OPP"));
  const old = starsPair({ stars: { counts } }, them, "SWT", "OPP");
  assert.equal(old.querySelectorAll(".starstrip").length, 2, "an older server: one strip a team");
  assert.equal(starsPair({}, { sides: { offense: { counts: null } } }, "A", "B"), null);
  assert.equal(starsPair(null, undefined, "A", "B"), null);
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["sides"])
def test_recruit_sides_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
