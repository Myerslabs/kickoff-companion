"""Phase 16, stream SEASON, owner look GX-22 (restrained): the playoff round tables side by side in a band 1,000 px wide
and wider, each game's row as tall as the games that feed it so it meets its next-round slot, Swampwater Tech's path
tinted, the winner in bold, no connector lines. Tables wave 3 (owner 2026-10-10): the band decides, never the screen, and
every table sizes itself by its own box: a round's Winner at large and Game from medium, each side's school turning to its
abbreviation at small inside its own link (the seed and the won or lost mark stay); the committee's rankings its own order
as the CFP badge (a plain number at small), the conference its own column. Dropping the commit drops this file."""

from __future__ import annotations

import re
from pathlib import Path

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const abbr = (school) => school.split(" ").map((w) => w[0]).join("").toUpperCase();
const g = (id, slot, a, h, ap, hp, us) => ({ gameId: id, slot, completed: ap !== null, winner: ap === null ? null : ap > hp ? a : h, isUs: Boolean(us), bowl: "Rose Bowl", away: { school: a, abbreviation: abbr(a), seed: id, points: ap }, home: { school: h, abbreviation: abbr(h), seed: id + 1, points: hp } });

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
  // wave 3: each round sizes itself; the Winner at large, the Game from medium, the bowl no longer a line under the score
  const wrap = rounds[0].querySelector(".stat-table-wrap");
  assert.ok(wrap.dataset.size, "a sized table");
  const heads = [...rounds[0].querySelectorAll("thead th")];
  assert.deepEqual(heads.map((th) => th.dataset.term), ["Away", "Score or date", "Home", "Winner", "Game"]);
  assert.deepEqual(heads.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : "")), ["", "", "", "L", "M"]);
  assert.equal(heads[1].querySelector(".sz-t--mid").textContent, "Score");
  assert.equal(rounds[0].querySelectorAll("td small").length, 0, "no line under the score");
  // a side's school turns to its abbreviation inside the same link, the seed and the mark kept
  const won = qf[1].querySelector(".seeded--won");
  assert.equal(won.querySelector(".seeded__seed").textContent, "(4) ");
  assert.equal(won.querySelector("button.team-link .sz-t--long").textContent, "Diner Tech");
  assert.equal(won.querySelector("button.team-link .sz-t--short").textContent, "DT");
  const winner = qf[1].querySelectorAll("td")[3];
  assert.equal(winner.querySelector("button.team-link").dataset.team, "Diner Tech");
  assert.equal(winner.querySelector(".sz-t--short").textContent, "DT", "the winner's abbreviation at small");
  assert.equal(text(rounds[2].querySelectorAll("tbody tr")[0].querySelectorAll("td")[3]), "–", "no winner yet: a dash");
  // the committee's rankings: its own order (the CFP badge, a plain number at small), the team, its conference's own column
  const sorts = {};
  const ranked = playoffBlock({ week: 14, rankings: [
    { rank: 2, school: "Oregon", abbreviation: "ORE", conference: "Big Pie" },
    { rank: 1, school: "Diner Tech", abbreviation: "DT", conference: "Biscuit Belt", isUs: true },
    { rank: "x", school: null, conference: 7 },
  ] }, "Diner Tech", { sorts });
  const list = ranked.querySelector(".playoff__rankings");
  assert.ok(ranked.className.includes("playoff"), "the block is the bracket's container");
  assert.deepEqual([...list.querySelectorAll("thead th")].map((th) => th.dataset.term), ["CFP rank", "Team", "Conference"]);
  const first = list.querySelectorAll("tbody tr")[0];
  assert.ok(first.className.includes("is-us"), "rank order to start");
  assert.ok(first.querySelector("td .sz-t--long .poll-badge"), "the CFP badge at large and medium");
  assert.equal(first.querySelector("td .sz-t--short").textContent, "1", "a plain number at small");
  assert.equal(first.querySelectorAll("td")[1].querySelector(".sz-t--short button.team-link").textContent, "DT");
  assert.ok(first.querySelectorAll("td")[2].className.includes("st__min-medium"), "the conference gone at small");
  list.querySelectorAll("thead th button")[1].click();
  assert.deepEqual(sorts.cfp, { key: "school", dir: "ascending" }, "the reader's order is kept for the next draw");
  const again = playoffBlock({ rankings: [{ rank: 1, school: "Diner Tech" }, { rank: 2, school: "Bayou Tech" }] }, "Diner Tech", { sorts });
  assert.equal(again.querySelector(".playoff__rankings tbody tr .sz-t--long button.team-link").dataset.team, "Bayou Tech", "the order survives a refresh");
  assert.ok(!RAW.test(text(ranked)), text(ranked));
};
"""


@needs_node
def test_the_bracket_rounds_line_up(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "bracket")


def test_the_rounds_stand_side_by_side_only_when_wide() -> None:
    # wave 3: the Playoff block's own width decides (a container query), never the screen
    assert ".playoff { container: playoff / inline-size; }" in CSS
    wide = re.search(r"@container playoff \(min-width: 1000px\) \{\n  \.bracket \{ grid-template-columns: repeat\(var\(--rounds, 4\)", CSS)
    assert wide, "side by side in a band 1,000 px wide"
    assert not re.search(r"@media \(min-width: 1100px\) \{\n  \.bracket", CSS), "no screen rule"
    assert "nth-child(n+4)" not in CSS.split("GX-22 bracket rounds", 1)[1].split("~~ owner look slot", 1)[0], "the sizes drop columns, not their position"
    assert re.search(r"(?m)^\.bracket \{ display: grid; grid-template-columns: minmax\(0, 1fr\); gap: var\(--sp-2\); \}", CSS), "stacked below, one column as wide as the band"
    rows = dict(re.findall(r"\.bracket \.stat-table tbody (td|tr\.span-2 td|tr\.span-4 td) \{ height: (\d+)px", CSS))
    slot = int(rows["td"])
    assert int(rows["tr.span-2 td"]) == 2 * slot + 1 and int(rows["tr.span-4 td"]) == 4 * slot + 3, "a row as tall as the rows that feed it"
