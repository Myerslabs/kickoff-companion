"""Phase 16, stream SEASON, owner look GX-22 (restrained): the playoff round tables side by side at 1100px and wider,
each game's row as tall as the games that feed it so it meets its next-round slot, Swampwater Tech's path tinted, the
winner in bold, no connector lines. Dropping the commit drops this file."""

from __future__ import annotations

import re
from pathlib import Path

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const g = (id, slot, a, h, ap, hp, us) => ({ gameId: id, slot, completed: ap !== null, winner: ap === null ? null : ap > hp ? a : h, isUs: Boolean(us), bowl: "Rose Bowl", away: { school: a, seed: id, points: ap }, home: { school: h, seed: id + 1, points: hp } });

scenarios.bracket = async () => {
  const { playoffBlock, rowSpan, slotNumber } = await import(moduleUrl("ui/playoff.js"));
  assert.equal(slotNumber({ slot: "QF3" }), 3);
  assert.equal(slotNumber({ slot: "CH" }), Infinity);
  assert.equal(slotNumber(null), Infinity);
  assert.equal(rowSpan([1, 2], 4), 2);
  assert.equal(rowSpan([1], 4), 4);
  assert.equal(rowSpan([1, 2, 3], 4), 1, "an uneven round stays one row per game");
  assert.equal(rowSpan([], 4), 1);
  const block = playoffBlock({ rounds: [
    { round: "Quarterfinal", games: [g(4, "QF2", "Diner Tech", "Georgia", 39, 34, true), g(3, "QF1", "Oregon", "Texas Tech", 23, 0)] },
    { round: "Semifinal", games: [g(9, "SF1", "Diner Tech", "Oregon", 27, 31, true)] },
    { round: "Championship", games: [g(11, "CH", "Oregon", "Indiana", null, null), null, "junk"] },
  ] });
  const bracket = block.querySelector(".bracket");
  assert.equal(bracket.style["--rounds"], "3");
  const rounds = bracket.querySelectorAll(".bracket__round");
  assert.equal(rounds.length, 3, "one table per round, side by side on a wide screen");
  const qf = rounds[0].querySelectorAll("tbody tr");
  assert.ok(text(qf[0]).includes("Oregon") && text(qf[1]).includes("Diner Tech"), "a round's games in bracket-slot order");
  assert.deepEqual(rounds.map((r) => r.querySelector("tbody tr").className.split(" ").find((c) => c.startsWith("span-"))), ["span-1", "span-2", "span-2"]);
  assert.ok(qf[1].className.includes("is-us"), "Swampwater Tech's path keeps the team tint");
  assert.ok(qf[1].querySelector(".seeded--won button.team-link").dataset.team === "Diner Tech");
  assert.ok(qf[1].querySelector(".seeded--lost button.team-link").dataset.team === "Georgia");
  assert.equal(bracket.querySelectorAll("svg, line, path").length, 0, "no connector lines");
  assert.ok(!RAW.test(text(block)));
};
"""


@needs_node
def test_the_bracket_rounds_line_up(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "bracket")


def test_the_rounds_stand_side_by_side_only_when_wide() -> None:
    wide = re.search(r"@media \(min-width: 1100px\) \{\n  \.bracket \{ grid-template-columns: repeat\(var\(--rounds, 4\)", CSS)
    assert wide, "side by side from 1100px"
    assert re.search(r"(?m)^\.bracket \{ display: grid; gap: var\(--sp-2\); \}", CSS), "stacked below"
    rows = dict(re.findall(r"\.bracket \.stat-table tbody (td|tr\.span-2 td|tr\.span-4 td) \{ height: (\d+)px", CSS))
    slot = int(rows["td"])
    assert int(rows["tr.span-2 td"]) == 2 * slot + 1 and int(rows["tr.span-4 td"]) == 4 * slot + 3, "a row as tall as the rows that feed it"
