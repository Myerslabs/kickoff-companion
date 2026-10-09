"""Public release Phase 7 in the fake browser (tests/fakedom.py): the grade chip, the breakdown block and the
graded-players table over good and damaged grades never print undefined, null or NaN; a missing grade is a
dash with its reason; the roster's PFF column is gone and the Grade column is there."""

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

scenarios.ui = async () => {
  const { gradeBlock, gradeChip, gradeTier, gradeValue, gradedTable } = await import(moduleUrl("ui/grade.js"));
  assert.equal(gradeTier(93), "elite");
  assert.equal(gradeTier(40), "average");
  assert.equal(gradeTier(null), null);
  assert.equal(gradeValue({ grade: "76" }), null, "a string is not a grade");
  assert.equal(text(gradeChip({ grade: 76.4, label: "Very good" })), "76");
  const none = gradeChip({ grade: null, reason: "Not enough plays to grade: 2.0 passes a game, 14 needed." });
  assert.equal(text(none), "–");
  assert.ok(none.getAttribute("title").includes("14 needed"));
  clean("junk chip", gradeChip("junk"));
  const good = gradeBlock({
    grade: 76, label: "Very good", rank: 20, of: 144, groupName: "quarterbacks", basis: "efficiency",
    volume: { label: "passes a game", perGame: 31.44, needed: 14 },
    components: [
      { label: "Yards per attempt", value: 9.05, format: "1f", percentile: 73.3, weight: 0.2 },
      { label: "Completion rate", value: 0.667, format: "pct", percentile: 91.3, weight: 0.1 },
      { label: "Opponent-adjusted passing value", value: null, format: "2f", percentile: null, weight: 0.1 },
      { label: "Longest field goal", value: NaN, format: "0f", percentile: NaN, weight: "x" },
      null, "junk",
    ],
  });
  const t = clean("block", good);
  assert.ok(t.includes("76") && t.includes("Very good") && t.includes("#20 of 144 FBS quarterbacks"), t.slice(0, 200));
  assert.ok(t.includes("9.1") && t.includes("66.7%") && t.includes("no number"));
  assert.ok(t.includes("31.4 passes a game (14.0 needed"));
  assert.equal(good.querySelectorAll("tbody tr").length, 4, "junk parts are skipped, the rest drawn");
  const missing = gradeBlock({ grade: null, reason: "Offensive linemen have no individual stats in CFBD's data, so they get no stat grade." });
  assert.ok(clean("missing", missing).includes("Offensive linemen"));
  clean("empty block", gradeBlock(undefined));
  const table = gradedTable([
    { playerId: "1", name: "A Passer", position: "QB", team: "Swampwater Tech", grade: 88, label: "Very good", rank: 1 },
    { playerId: "2", name: null, position: null, team: null, grade: null, label: null, rank: null },
    { name: "no id" }, null,
  ], { us: "Swampwater Tech" });
  document.body.append(table);
  clean("table", table);
  const rows = table.querySelectorAll("tbody tr");
  assert.equal(rows.length, 2);
  assert.ok(rows[0].className.includes("is-us"));
  // Phase 17 #22: no word column repeating the number; the word is in the chip's title; the rank says what it ranks
  assert.ok(!text(rows[0]).includes("Very good"), text(rows[0]));
  assert.ok(rows[0].querySelector(".grade-chip").getAttribute("title").includes("Very good"));
  assert.ok(text(table.querySelector("thead")).includes("Pos. rank"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["ui"])
def test_grade_ui_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_pff_is_gone_from_the_front_end() -> None:
    roster = (STATIC_JS / "views" / "roster.js").read_text(encoding="utf-8")
    assert "pff" not in roster.lower() and 'label: "Grade"' in roster
    glossary = (STATIC_JS / "glossary-data.js").read_text(encoding="utf-8")
    assert '"stat-grade"' in glossary and "pff-grade" not in glossary
    styleguide = (STATIC_JS / "styleguide.js").read_text(encoding="utf-8")
    assert "PFF" not in styleguide
