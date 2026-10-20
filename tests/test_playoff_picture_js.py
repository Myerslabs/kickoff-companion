"""The playoff picture's bracket on the Season page (owner 2026-10-20), drawn in a fake browser."""

from __future__ import annotations

from pathlib import Path

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const team = (school, seed, extra = {}) => ({ school, seed, lastSeed: seed, rank: seed, rankBasis: "poll", champion: null, autoBid: false, conference: "Alpha", conferenceShort: "A", abbreviation: school, isUs: false, ...extra });
const field = [
  team("A1", 1, { champion: "Alpha", autoBid: true, lastSeed: 2 }), team("B1", 2, { champion: "Beta", autoBid: true, conference: "Beta", conferenceShort: "B", lastSeed: 1 }),
  team("A2", 3), team("B2", 4), team("C1", 5, { champion: "Gamma", autoBid: true, conferenceShort: "G" }), team("C2", 6), team("B3", 7), team("A3", 8),
  team("C3", 9, { isUs: true, lastSeed: 10 }), team("D2", 10), team("E1", 11, { champion: "Epsilon", autoBid: true, conferenceShort: "E" }), team("D1", 12, { champion: "Delta", autoBid: true, conferenceShort: "D", rankBasis: "SP+", rank: 21, lastSeed: null }),
];
const by = Object.fromEntries(field.map((t) => [t.seed, t]));
const picture = {
  source: "AP", sourceLabel: "the AP poll", week: 7, previousWeek: 6, format: { teams: 12, byes: 4, autoBids: 5 }, field,
  champions: [{ ...by[1], in: true }, { ...by[2], in: true }, { ...by[5], in: true }, { ...by[11], in: true }, { ...by[12], in: true }],
  lastFourIn: [by[7], by[8], by[9], by[10]],
  firstFourOut: [team("D3", null, { rank: 11 }), team("N1", null, { rank: 13 }), team("A4", null, { rank: 20 }), team("B4", null, { rank: 22, rankBasis: "SP+" })],
  bracket: {
    firstRound: [{ slot: "FR1", home: by[8], away: by[9], feeds: "QF1", label: "(9) at (8)" }, { slot: "FR2", home: by[5], away: by[12], feeds: "QF2", label: "(12) at (5)" }, { slot: "FR3", home: by[7], away: by[10], feeds: "QF3", label: "(10) at (7)" }, { slot: "FR4", home: by[6], away: by[11], feeds: "QF4", label: "(11) at (6)" }],
    quarterfinals: [{ slot: "QF1", home: by[1], away: null, from: "FR1" }, { slot: "QF2", home: by[4], away: null, from: "FR2" }, { slot: "QF3", home: by[2], away: null, from: "FR3" }, { slot: "QF4", home: by[3], away: null, from: "FR4" }],
    semifinals: [{ slot: "SF1", from: ["QF1", "QF2"] }, { slot: "SF2", from: ["QF3", "QF4"] }],
    final: { slot: "CH", from: ["SF1", "SF2"] },
  },
  us: { school: "C3", seed: 9, status: "road", outBy: null, line: "C3: the 9th seed, at (8) A3" },
};

scenarios.bracket = async () => {
  const { pictureBlock, playoffBlock, playoffSummary } = await import(moduleUrl("ui/playoff.js"));
  const node = pictureBlock(picture, "C3");
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t.slice(0, 600));
  assert.equal(node.querySelectorAll(".pic__round").length, 4, "four rounds");
  assert.equal(node.querySelectorAll(".pic__round--first .pic__game").length, 4, "four first-round games");
  assert.equal(node.querySelectorAll(".pic__round--quarter .pic__game").length, 4, "four quarterfinals, the bye seeds on top");
  assert.equal(node.querySelectorAll(".pic__round--quarter .pic__pair").length, 2);
  assert.equal(node.querySelectorAll(".pic__round--semi .pic__game").length, 2);
  assert.equal(node.querySelectorAll(".pic__round--final .pic__game").length, 1);
  assert.equal(node.querySelectorAll(".pic__team--us").length, 1, "our line tinted once");
  assert.equal(node.querySelectorAll(".pic__champ").length, 5, "five conference leaders marked in the bracket");
  assert.ok(t.includes("C3: the 9th seed, at (8) A3"), "our line on top");
  assert.ok(t.includes("Winner of (8) v (9)"), "the quarterfinal waits for its first-round winner");
  assert.ok(t.includes("Last four in: (7) B3, (8) A3, (9) C3, (10) D2"));
  assert.ok(t.includes("First four out: (#11) D3, (#13) N1, (#20) A4, (#22) B4"));
  const moves = node.querySelectorAll(".pic__move").map((m) => m.textContent);
  assert.ok(moves.includes("up 1") && moves.includes("down 1") && moves.includes("new"), "the moves since last week: " + moves.join(","));
  assert.ok(node.querySelectorAll("button.team-link").length >= 12, "every team in the bracket is a link");
  const champions = node.querySelector(".pic__champions");
  assert.ok(champions && text(champions).includes("in, the 12 seed") && text(champions).includes("21 (SP+)"), "the leaders' table says who is in and what the rank rests on");
  // in the band: the picture sits at the bottom, and the band's summary is our line
  const band = playoffBlock({ week: null, rankings: [], usRank: null, rounds: [], picture }, "C3", {});
  assert.ok(band.querySelector(".pic"), "the band holds the picture");
  assert.equal(playoffSummary({ rounds: [], picture }, "C3"), "C3: the 9th seed, at (8) A3");
  assert.equal(playoffSummary({ rounds: [], usRank: 4 }, "C3"), "C3 #4 in the committee's rankings", "without a picture the old summary");
  // a bare picture never prints a raw value
  const bare = pictureBlock({ bracket: {}, field: [], us: {} }, "C3");
  assert.ok(!RAW.test(text(bare)) && text(bare).includes("No field yet"));
};
"""


@needs_node
def test_the_bracket_draws_the_field(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "bracket")
