"""What we need and the Post-Game Program on the page (F8 feature 1, owner 2026-10-21): the race band, the badges and the
chip, the ticker's dot and the standings badge (the doubled rows went with the Post-Game stop, the line's Wave 3)."""

from __future__ import annotations

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

const RACE = {
  conference: "SEC", spots: 2, week: 9, settled: false, others: 4, outCount: 4,
  standings: [
    { place: 1, team: "Fresno State", confWins: 5, confLosses: 0, wins: 7, losses: 1, left: 3, best: 8, status: "alive", isUs: false },
    { place: 2, team: "Texas State", confWins: 4, confLosses: 1, wins: 6, losses: 2, left: 3, best: 7, status: "alive", isUs: false },
    { place: 3, team: "Florida", confWins: 4, confLosses: 1, wins: 6, losses: 2, left: 3, best: 7, status: "alive", isUs: true },
    { place: 4, team: "BYU", confWins: 4, confLosses: 1, wins: 7, losses: 1, left: 3, best: 7, status: "tiebreaker", isUs: false },
    { place: 5, team: "New Mexico State", confWins: 3, confLosses: 2, wins: 5, losses: 3, left: 3, best: 6, status: "alive", isUs: false },
    { place: 6, team: "Syracuse", confWins: 1, confLosses: 4, wins: 2, losses: 6, left: 3, best: 4, status: "out", isUs: false },
  ],
  us: { team: "Florida", place: 3, confWins: 4, confLosses: 1, left: 3, best: 7, status: "alive", exact: true },
  lines: [
    { key: "winOut", lead: "Win out (3 left)", text: "in, unless BYU wins out too; then a tiebreaker." },
    { key: "allButOne", lead: "Win all but one", text: "in only if Texas State loses twice more." },
    { key: "next", lead: "Beat Texas State", text: "and we are no worse than second; lose, and we are no better than third." },
    { key: "clinch", lead: "Clinch number", text: "4: each win of ours and each loss by BYU counts one; a tie at the line goes to a tiebreaker." },
  ],
  watch: [
    { gameId: 1, home: "Texas State", away: "Florida", kickoff: "2026-10-24T19:30:00.000Z", ours: true, pullFor: "Florida", why: "Our own game: the one that moves us most." },
    { gameId: 2, home: "New Mexico State", away: "BYU", kickoff: "2026-10-24T23:00:00.000Z", ours: false, pullFor: "New Mexico State", why: "A loss by BYU takes a team we could tie with out of the way." },
    { gameId: 3, home: "Bowling Green", away: "Fresno State", kickoff: "2026-10-24T16:00:00.000Z", ours: false, pullFor: "Bowling Green", why: "A loss by Fresno State opens a spot above us." },
  ],
  helps: { 1: { pullFor: "Florida", why: "Our own game: the one that moves us most.", ours: true }, 2: { pullFor: "New Mexico State", why: "A loss by BYU takes a team we could tie with out of the way.", ours: false } },
};
const PICTURE = {
  source: "AP", sourceLabel: "the AP poll", week: 9,
  us: { school: "Florida", seed: 10, status: "road", outBy: null, line: "Florida: the 10th seed, at (7) Texas State" },
  seeds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((seed) => ({ seed, school: seed === 10 ? "Florida" : `Team ${seed}`, abbreviation: seed === 10 ? "FLA" : `T${seed}`, isUs: seed === 10, autoBid: seed <= 5 })),
  firstFourOut: [{ school: "Cedar Point", abbreviation: "CED", isUs: false }],
};

scenarios.race = async () => {
  const { helpsChip, kickoffText, raceBadge, raceBand } = await import(moduleUrl("ui/race.js"));
  const section = raceBand(RACE, PICTURE);
  document.body.append(section);
  const words = text(section);
  assert.equal(section.getAttribute("id"), "program-race");
  assert.ok(words.includes("What we need") && words.includes("Win out (3 left)") && words.includes("Clinch number") && words.includes("Beat Texas State"), "the four lines in words");
  assert.ok(words.includes("3rd in the SEC at 4-1, 3 left, 7 wins the most we can reach."), "our standing line: " + words.slice(0, 400));
  const tables = section.querySelectorAll("table");
  assert.equal(tables.length, 2, "the standings and the games that help");
  assert.equal(tables[0].querySelectorAll("tbody tr").length, 6);
  assert.ok(tables[0].querySelector(".race-badge--out") && text(tables[0].querySelector(".race-badge--out")) === "Out", "the team that is out wears the badge");
  assert.ok(tables[0].querySelector(".race-badge--tiebreaker"), "a tiebreaker is said so");
  assert.ok(words.includes("4 more teams, 4 of them out"), "the rest of the table is counted");
  const watch = tables[1].querySelectorAll("tbody tr");
  assert.equal(watch.length, 2, "ENH-7: our own game is not one of the games that help us");
  assert.ok(!text(tables[1]).includes("Win it") && !text(tables[1]).includes("Florida at Texas State"), "no row for our own game");
  assert.ok(text(watch[0]).includes("New Mexico State") && text(watch[0]).includes("takes a team we could tie with"));
  assert.ok(words.includes("The playoff") && words.includes("Florida: the 10th seed") && section.querySelectorAll(".race__seed").length === 12 && section.querySelector(".race__seed--us"), "the twelve seeds with ours marked");
  assert.ok(words.includes("First four out: CED") && words.includes("By the AP poll, week 9"));
  assert.ok(!RAW.test(words), words);
  // badges and the chip
  assert.equal(text(raceBadge("clinched")), "Clinched");
  assert.equal(raceBadge("alive"), null);
  assert.equal(raceBadge(undefined), null);
  const chip = helpsChip({ pullFor: "New Mexico State", why: "because", ours: false });
  assert.ok(chip && text(chip) === "Helps us: pull for New Mexico State" && chip.getAttribute("title") === "because");
  assert.equal(helpsChip({ pullFor: "Florida", why: "ours", ours: true }), null, "no chip on our own game");
  assert.equal(helpsChip(null), null);
  assert.ok(kickoffText("2026-10-24T19:30:00.000Z").length > 3 && kickoffText("junk") === "–" && kickoffText(null) === "–");
  // no race yet: a note, never a broken table
  const empty = raceBand(null, null);
  document.body.append(empty);
  assert.ok(text(empty).includes("The race appears once") && !empty.querySelector("table") && !RAW.test(text(empty)));
  const settled = raceBand({ ...RACE, settled: true, lines: [], watch: [], us: { ...RACE.us, status: "clinched" } }, null);
  document.body.append(settled);
  assert.ok(text(settled).includes("a spot in the title game is clinched") && text(settled).includes("The picture appears with the first poll"));
};

scenarios.marks = async () => {
  const { ticker } = await import(moduleUrl("ui/ticker.js"));
  const { standingsTable } = await import(moduleUrl("ui/team-page.js"));
  const games = [
    { gameId: 2, status: "pre", detail: "7:00 PM", isUs: false, away: { abbr: "ARM", points: null, rank: 14 }, home: { abbr: "BBT", points: null }, helps: { pullFor: "New Mexico State", why: "A loss by BYU helps.", ours: false } },
    { gameId: 1, status: "live", detail: "3rd 8:12", isUs: true, away: { abbr: "FLA", points: 14 }, home: { abbr: "DNT", points: 10 }, helps: { pullFor: "Florida", why: "ours", ours: true } },
    { gameId: 9, status: "final", detail: "Final", isUs: false, away: { abbr: "AAA", points: 21 }, home: { abbr: "BBB", points: 20 }, helps: null },
  ];
  const strip = ticker({ games, id: "t" });
  document.body.append(strip);
  const dots = strip.querySelectorAll(".ticker__helps");
  assert.equal(dots.length, 2, "one game helps us, drawn in the line and its crawl clone; never our own, never a plain game");
  assert.ok(text(dots[0]).includes("helps us") && dots[0].getAttribute("title") === "A loss by BYU helps.");
  assert.ok(!RAW.test(text(strip)));
  const rows = [
    { place: 1, team: "Fresno State", abbreviation: "SLV", conference: { wins: 7, losses: 0 }, overall: { wins: 9, losses: 1 }, apRank: 1, isUs: false, raceStatus: "clinched" },
    { place: 2, team: "Florida", abbreviation: "FLA", conference: { wins: 6, losses: 1 }, overall: { wins: 8, losses: 2 }, apRank: 8, isUs: true, raceStatus: "alive" },
    { place: 3, team: "Syracuse", abbreviation: "BGL", conference: { wins: 2, losses: 5 }, overall: { wins: 3, losses: 7 }, apRank: null, isUs: false, raceStatus: "out" },
  ];
  const table = standingsTable(rows, { conference: "SEC" });
  document.body.append(table);
  assert.equal(table.querySelectorAll(".race-badge").length, 4, "a badge in the long and the short form of the two settled rows, none on the live one");
  assert.ok(text(table).includes("Clinched") && text(table).includes("Out") && !RAW.test(text(table)));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["race", "marks"])
def test_what_we_need_in_a_fake_browser(tmp_path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
