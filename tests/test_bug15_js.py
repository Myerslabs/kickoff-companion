"""BUG-15 (owner 2026-10-23, board drawn and approved 2026-10-27): the
opponent card and What we need looked empty, with open space. The page's flush rows stretched each to the height of a taller
band beside it (the card from 716 to 1,499 px on a wide screen; What we need squeezed into half the page beside the scouting
report on the iPad). Now the three take a row of their own, the card's head is one strip, What we need carries each team's
range of finishes as the standings table's last column, row for row, and the scouting report's keys sit side by side. The same
gap elsewhere (the owner, 2026-10-27: "fix the same way"): Last season takes the page's width, the offense beside the rest,
under common opponents beside the radio; the empty one of Recruits on hand and the Availability report is one line
(tests/test_p16_program_js.py, reportStrip)."""

from __future__ import annotations

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const last = (node) => node.children[node.children.length - 1];

const RACE = {
  conference: "SEC", spots: 2, week: 9, settled: false, rangeExact: false, others: 10, outCount: 0,
  standings: [
    { place: 1, team: "Kentucky", confWins: 5, confLosses: 1, wins: 7, losses: 1, left: 3, best: 8, bestPlace: 1, worstPlace: 15, status: "alive", isUs: false },
    { place: 2, team: "Georgia", confWins: 4, confLosses: 1, wins: 6, losses: 1, left: 4, best: 8, bestPlace: 1, worstPlace: 16, status: "alive", isUs: false },
    { place: 3, team: "Alabama", confWins: 4, confLosses: 2, wins: 6, losses: 2, left: 3, best: 7, bestPlace: 1, worstPlace: 16, status: "alive", isUs: false },
    { place: 4, team: "Florida", confWins: 3, confLosses: 2, wins: 5, losses: 2, left: 4, best: 7, bestPlace: 1, worstPlace: 16, status: "alive", isUs: true },
    { place: 5, team: "LSU", confWins: 3, confLosses: 2, wins: 6, losses: 2, left: 4, best: 7, bestPlace: 1, worstPlace: 16, status: "alive", isUs: false },
    { place: 6, team: "Ole Miss", confWins: 3, confLosses: 2, wins: 5, losses: 2, left: 4, best: 7, bestPlace: 1, worstPlace: 16, status: "alive", isUs: false },
  ],
  us: { team: "Florida", place: 4, confWins: 3, confLosses: 2, left: 4, best: 7, bestPlace: 1, worstPlace: 16, status: "alive", exact: false },
  lines: [
    { key: "winOut", lead: "Win out (4 left)", text: "in, unless Kentucky, Alabama, Georgia and 5 more win out too; then a tiebreaker." },
    { key: "allButOne", lead: "Win all but one", text: "in only if Georgia loses twice more." },
    { key: "next", lead: "Beat Georgia", text: "and we are no worse than 5th; lose, and we are no better than 4th." },
    { key: "clinch", lead: "Clinch number", text: "6: each win of ours and each loss by Kentucky and Georgia counts one." },
  ],
  watch: [
    { gameId: 1, home: "Georgia", away: "Florida", kickoff: "2026-10-31T19:30:00.000Z", ours: true, pullFor: "Florida", why: "Our own game." },
    { gameId: 2, home: "Ole Miss", away: "Auburn", kickoff: "2026-10-31T16:45:00.000Z", ours: false, pullFor: "Auburn", why: "Two teams in our way: a loss by Ole Miss helps most, and one of them must lose." },
  ],
};
const PICTURE = {
  source: "AP", sourceLabel: "the AP poll", week: 9,
  us: { school: "Florida", seed: null, status: "out", outBy: 6, line: "Florida: out, 17th in the order" },
  seeds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((seed) => ({ seed, school: `Team ${seed}`, abbreviation: `T${seed}`, isUs: false })),
  firstFourOut: [{ school: "Ole Miss", abbreviation: "MISS", isUs: false }],
};

scenarios.race = async () => {
  const { raceBand } = await import(moduleUrl("ui/race.js"));
  const section = raceBand(RACE, PICTURE);
  document.body.append(section);
  const words = text(section);
  assert.ok(!RAW.test(words), words);
  const grid = section.querySelector(".race__grid");
  assert.ok(grid.className.includes("race__grid--ranges"));
  // our standing leads the band, then the standings, our way in, the playoff, the games that help
  assert.deepEqual(grid.children.map((c) => c.className), ["race__status", "race__standings", "race__way", "race__playoff", "race__watch"]);
  assert.equal(text(grid.children[0]), "4th in the SEC at 3-2, 4 left, 7 wins the most we can reach.");
  // the ranges ride in the standings table, row for row: one strip per team, in the table's own rows
  const table = section.querySelector(".race__table--ranges table");
  const rows = table.querySelectorAll("tbody tr");
  assert.equal(rows.length, 6);
  rows.forEach((tr, i) => {
    const strip = last(tr).querySelector(".race-ranges__strip");
    assert.ok(strip, `row ${i + 1} carries its range`);
    assert.ok(text(tr).includes(RACE.standings[i].team), "the strip sits in the team's own row");
    assert.equal(strip.querySelectorAll(".race-ranges__cell").length, 16, "one cell a place, to the worst");
    assert.equal(strip.querySelectorAll(".race-ranges__cell--spot").length, 2, "the two title-game spots shaded");
  });
  const florida = last(rows[3]).querySelector(".race-ranges__strip");
  assert.equal(florida.getAttribute("aria-label"), "1st at best, 16th at worst, 4th now");
  assert.ok(florida.querySelector(".race-ranges__bar--us"), "our bar in our color");
  assert.equal(florida.querySelector(".race-ranges__bar").style.gridColumn, "1 / 17", "1st to 16th, no name column before it");
  assert.equal(florida.querySelector(".race-ranges__now").style.gridColumn, "4");
  assert.ok(rows[3].className.includes("is-us"));
  const axis = last(table.querySelector("thead tr")).querySelector(".race-ranges__strip--head");
  const labels = axis.querySelectorAll(".race-ranges__place").map((p) => text(p));
  assert.equal(labels.length, 16);
  assert.deepEqual([labels[0], labels[2], labels[14], labels[15]], ["1", "3", "", "16"], "every other place named past ten, the last always");
  assert.ok(text(section.querySelector(".race__head--ranges")).startsWith("Where each can finish"));
  assert.ok(text(section.querySelector(".race__ranges-key")).includes("counted from the records"), "what the bars mean, under the column");
  assert.ok(section.querySelector(".race__ranges-alone .race-ranges"), "a narrow band draws the chart under the table instead");
  // our way in, two by two; the playoff line led by the school; the seeds; the games
  const way = section.querySelector(".race__way");
  assert.equal(text(way.querySelector("h4")), "Our way in");
  assert.equal(way.querySelectorAll("li").length, 4);
  const line = section.querySelector(".race__picture-line");
  assert.equal(text(line.querySelector("strong")), "Florida:");
  assert.equal(text(line), "Florida: out, 17th in the order.");
  assert.equal(section.querySelectorAll(".race__seed").length, 12);
  assert.equal(section.querySelector(".race__watch").querySelectorAll("tbody tr").length, 1, "our own game is not a game that helps us");
};

scenarios.lower = async () => {
  // we sit below the six rows the program keeps: our own row joins the table, so its range is never left off
  const { raceBand } = await import(moduleUrl("ui/race.js"));
  const below = { ...RACE, standings: RACE.standings.filter((r) => !r.isUs), us: { ...RACE.us, place: 9, confWins: 2, confLosses: 3, worstPlace: 16 } };
  const section = raceBand(below, null);
  document.body.append(section);
  const rows = section.querySelectorAll(".race__table--ranges tbody tr");
  assert.equal(rows.length, 6);
  assert.ok(rows[5].className.includes("is-us") && text(rows[5]).includes("Florida") && text(rows[5]).includes("9"), text(rows[5]));
  assert.ok(last(rows[5]).querySelector(".race-ranges__bar--us"));
  assert.ok(!RAW.test(text(section)), text(section));
  // an older answer with no ranges: the plain table, no range column, no chart, nothing broken
  const plain = raceBand({ ...RACE, standings: RACE.standings.map(({ bestPlace, worstPlace, ...r }) => r), us: { ...RACE.us, bestPlace: undefined, worstPlace: undefined } }, PICTURE);
  document.body.append(plain);
  assert.ok(!plain.querySelector(".race__table--ranges") && !plain.querySelector(".race__head--ranges") && !plain.querySelector(".race-ranges"));
  assert.ok(!plain.querySelector(".race__grid").className.includes("race__grid--ranges"));
  assert.equal(plain.querySelectorAll("table")[0].querySelectorAll("tbody tr").length, 6);
  assert.ok(!RAW.test(text(plain)), text(plain));
  // junk never throws
  for (const junk of [{ standings: "x", us: 3, lines: "y", watch: null }, { standings: [null, 4, { team: 7 }] }]) assert.ok(!RAW.test(text(raceBand(junk, "junk"))));
};

function cardRows() {
  return [
    { label: "Points per game", side: "offense", format: "1f", higherIsBetter: true, metric: "profile:ppg", us: { value: 39.6, rank: 9, of: 138 }, them: { value: 43.0, rank: 3, of: 138 } },
    { label: "Yards per game", side: "offense", format: "0f", higherIsBetter: true, metric: "profile:ypg", us: { value: 451, rank: 21, of: 138 }, them: { value: 470, rank: 14, of: 138 } },
    { label: "Points allowed per game", side: "defense", format: "1f", higherIsBetter: false, metric: "profile:opp_ppg", us: { value: 28.3, rank: 106, of: 138 }, them: { value: 15.9, rank: 16, of: 138 } },
  ];
}

scenarios.card = async () => {
  const { matchupCard } = await import(moduleUrl("ui/matchup-card.js"));
  const form = [1, 2, 3, 4, 5].map((n) => ({ result: n === 5 ? "L" : "W", points: 30, opponentPoints: 20, opponent: `Team ${n}`, homeAway: "home", gameId: 100 + n }));
  const card = matchupCard({
    kicker: "Florida's opponent",
    us: { abbreviation: "FLA", school: "Florida", mascot: "Gators" },
    them: { school: "Georgia", mascot: "Bulldogs", abbreviation: "UGA", apRank: 3, record: { wins: 6, losses: 1 }, conferenceRecord: { wins: 4, losses: 1 }, form },
    teamTags: [{ label: "SP+ #2", href: "#national=rating%3Asp?team=Georgia", rank: 2, of: 138, name: "SP+" }],
    tags: [{ label: "SEC" }],
    coaches: { headCoach: "Kirby Smart", offensiveCoordinator: "Mike Bobo", defensiveCoordinator: "Glenn Schumann" },
    schemes: { offense: "Spread option", defense: "3-4", opponent: { offense: "Pro spread", defense: "3-4" } },
    rows: cardRows(),
  });
  document.body.append(card);
  assert.ok(!RAW.test(text(card)), text(card));
  // the head is one strip: the logo, the name and the staff, then the chips at its right end
  const hero = card.querySelector(".mcard__hero");
  assert.equal(hero.children.length, 3);
  assert.ok(hero.children[1].className.includes("mcard__who") && last(hero).className.includes("mcard__chips"));
  assert.ok(!hero.children[1].querySelector(".mcard__chips"), "the chips left the name's column");
  assert.ok(text(hero.children[1]).includes("Georgia") && text(hero.children[1]).includes("HC Kirby Smart · OC Mike Bobo · DC Glenn Schumann"));
  const chips = last(hero);
  assert.equal(chips.children[0].className, "mcard__chip-row");
  assert.ok(text(chips.children[0]).includes("SP+ #2") && text(chips.children[0]).includes("SEC"), "SP+ and the game's tag on the first line");
  assert.ok(chips.children[1].className.includes("mcard__last5") && chips.children[1].querySelectorAll("a").length === 5, "the last five under them, each a box score");
  // one table on a tablet; Offense beside Defense on a wide screen, two tables of one group (the stylesheet shows one or the other)
  const tables = card.querySelectorAll(".mcard__table");
  assert.equal(tables.length, 3);
  assert.ok(tables[0].className.includes("mcard__table--whole") && tables[0].querySelectorAll("tr.tt__group").length === 2);
  const halves = card.querySelector(".mcard__halves");
  assert.equal(halves.querySelectorAll(".mcard__table--half").length, 2);
  assert.deepEqual(halves.querySelectorAll(".mcard__table--half").map((t) => t.querySelectorAll("tr.tt__group").length), [1, 1]);
  assert.ok(text(halves.children[0]).includes("Points per game") && !text(halves.children[0]).includes("allowed"));
  assert.ok(text(halves.children[1]).includes("Points allowed per game"));
  // one group: no halves; nothing to say: no chips
  const offense = matchupCard({ us: { school: "Florida" }, them: { school: "Georgia" }, rows: cardRows().filter((r) => r.side === "offense") });
  assert.ok(!offense.querySelector(".mcard__halves") && !offense.querySelector(".mcard__chips"));
};

scenarios.halves = async () => {
  // Last season across the page: the offense beside the defense and the overall line; a narrow band keeps the one table
  const { lastSeasonTwoTeam } = await import(moduleUrl("ui/offday.js"));
  const row = (side, label, key, us, them) => ({ side, label, key, metric: `profile:${key}`, format: "1f", higherIsBetter: true, us: { value: us, rank: 10, of: 136 }, them: { value: them, rank: 50, of: 136 } });
  const data = { year: 2025, rows: [row("offense", "Points per game", "ppg", 34.5, 27.1), row("offense", "Yards per game", "ypg", 515, 411), row("defense", "Points allowed per game", "opp_ppg", 25.7, 28.7), row("both", "Turnover margin", "to", -9, 3)] };
  const split = lastSeasonTwoTeam(data, "FLA", "TEX", { usTeam: "Florida", themTeam: "Texas", tug: true, halves: true });
  document.body.append(split);
  assert.ok(split.className.includes("d2--halves"));
  const whole = split.querySelector(".d2__whole");
  const halves = split.querySelector(".d2__halves");
  assert.ok(whole && whole.querySelectorAll("table").length === 1 && halves, "the whole table for a narrow band, the halves for a wide one");
  const tables = halves.querySelectorAll("table");
  assert.equal(tables.length, 2);
  assert.ok(text(tables[0]).includes("Points per game") && !text(tables[0]).includes("Points allowed per game"), "the offense on the left");
  assert.ok(text(tables[1]).includes("Points allowed per game") && text(tables[1]).includes("Turnover margin"), "the defense and the overall line on the right");
  assert.ok(text(tables[0].querySelector("caption")).includes("offense") && text(tables[1].querySelector("caption")).includes("defense and overall"));
  assert.ok(!RAW.test(text(split)), text(split));
  const one = lastSeasonTwoTeam(data, "FLA", "TEX", { tug: true }); // the off-day page: the one table, as before
  assert.ok(!one.className.includes("d2--halves") && one.querySelectorAll("table").length === 1);
  const offense = lastSeasonTwoTeam({ year: 2025, rows: data.rows.slice(0, 2) }, "FLA", "TEX", { halves: true }); // one side: nothing to split
  assert.equal(offense.querySelectorAll("table").length, 1);
};

scenarios.rows = async () => {
  // one column (owner 2026-11-01): the flow stretches nothing and places nothing; the card, What we need and the scouting
  // report each end at their own height at every width
  const { flow } = await import(moduleUrl("ui/flow.js"));
  const box = (w, h) => () => ({ width: w, height: h, top: 0, left: 0, right: w, bottom: h });
  for (const width of [820, 1180, 1920]) {
    const page = document.createElement("div");
    page.classList.add("page");
    page.getBoundingClientRect = box(width, 0);
    const make = (id, h) => { const d = document.createElement("section"); d.id = id; d.classList.add("band"); d.getBoundingClientRect = box(400, h); page.append(d); return d; };
    make("program-series", 492);
    const card = make("program-matchup", 716);
    const race = make("program-race", 1100);
    const scout = make("program-scout-host", 900);
    document.body.append(page);
    const f = flow(page);
    assert.equal(page.dataset.cols, "1", `one column at ${width}`);
    for (const band of [card, race, scout]) {
      assert.equal(band.style.gridColumn, "", `${band.id} is placed by the stack at ${width}`);
      assert.equal(band.style.minHeight, "", `${band.id} keeps its own height at ${width}`);
    }
    f.stop();
    page.remove();
  }
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["race", "lower", "card", "halves", "rows"])
def test_bug15_the_bottom_of_the_program(tmp_path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
