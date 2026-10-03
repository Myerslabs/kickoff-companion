"""Starting lineups and depth charts (owner request 2026-10-02) in the fake browser: the three matchup
rows from the notes file's published charts, the starter picked from each slot, season chips, the
availability report marking a listed starter, a row tap opening the card, the empty state, the summary
line, the program's two bands, and no undefined, null or NaN on damaged input."""

from __future__ import annotations

from pathlib import Path

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(Math.max(0, t.search(RAW) - 80), t.search(RAW) + 80))}`);
  return t;
};
const heads = (table) => [...table.querySelectorAll("thead th")].map(text);

const lineups = () => ({
  source: "Published depth charts",
  updatedAt: "2026-10-01",
  us: {
    team: "Swampwater Tech", scheme: "Spread option", source: "Mudpuppies Wire", sourceUrl: "https://example.invalid/uf", updatedAt: "2026-10-01",
    slots: [
      { unit: "Offense", slot: "QB", players: [{ name: "Mason Hamilton", number: 12, classYear: "RS SO", playerId: "4536127", chips: ["917 passing yards", "7 TD", "2 INT", "72% completions"] }, { name: "Tramell Jones Jr.", number: 9, classYear: "RS FR", playerId: null, chips: [] }] },
      { unit: "Offense", slot: "RB", players: [{ name: "Lucas Griffin", number: 13, classYear: "JR", chips: ["600 rushing yards", "83 CAR"] }, { name: "Dante Clayborn", number: 20 }, { name: "Cameron Wilson", number: 21 }, { name: "Landon Merriweather", number: 24 }] },
      { unit: "Offense", slot: "LT", players: [{ name: "Bryce Lockhart", number: 53 }] },
      { unit: "Defense", slot: "STAR", players: [{ name: "Kane Clayborn", number: 20, classYear: "RS SR", note: "chart says questionable" }] },
      { unit: "Special teams", slot: "PK", players: [{ name: "Patrick Dunmore", number: 91 }] },
      { unit: "Offense", slot: "WR", players: [] },
    ],
  },
  them: {
    team: "Sweet Tea State", source: "Ourlads", updatedAt: "2026-09-26",
    slots: [
      { unit: "Defense", slot: "JACK", players: [{ name: "Darius Smithers", number: 19, classYear: "RS SR" }, { name: "Malik Bryant", number: 12 }] },
      { unit: "Offense", slot: "QB", players: [{ name: "Austin Simmons", number: 13, playerId: "9", chips: ["947 passing yards"] }] },
    ],
  },
});
const availability = [{ name: "Kane Clayborn", position: "STAR", status: "Questionable", note: "ankle" }, { name: "Darius Smithers", status: "Out" }, null, { name: 5 }];
const us = { school: "Swampwater Tech", abbreviation: "SWT" };
const them = { school: "Sweet Tea State", abbreviation: "MIZ" };

scenarios.helpers = async () => {
  const { lineupSlots, lineupStarters, lineupSummary, availabilityFor } = await import(moduleUrl("ui/lineups.js"));
  const l = lineups();
  assert.equal(lineupSlots(l.us).length, 6, "every slot with a printed label, even an empty one");
  assert.deepEqual(lineupSlots(l.us).map((s) => s.unit), ["offense", "offense", "offense", "defense", "special teams", "offense"], "units are grouped into the three the layout pairs");
  const starters = lineupStarters(l.us);
  assert.deepEqual(starters.map((s) => s.slot), ["QB", "RB", "LT", "STAR", "PK"], "an empty slot has no starter");
  assert.equal(starters[0].player.name, "Mason Hamilton");
  assert.ok(lineupSummary(l).startsWith("Published depth charts, updated ") && lineupSummary(l).includes("Oct 1"), lineupSummary(l));
  assert.equal(lineupSummary({ us: { source: "Ourlads", slots: l.them.slots } }), "Ourlads", "falls back to a team's source");
  assert.equal(lineupSummary({}), "");
  assert.equal(lineupSummary({ us: { slots: [{ slot: "QB", players: [] }] } }), "", "a chart with no names is no chart");
  assert.equal(availabilityFor(availability, "Kane Clayborn").note, "ankle");
  assert.equal(availabilityFor(availability, "kane clayborn jr.").note, "ankle", "suffixes and case do not matter");
  assert.equal(availabilityFor(availability, "Mason Hamilton"), null);
  assert.equal(availabilityFor("x", "Kane Clayborn"), null);
  for (const junk of [null, undefined, "x", 7, [], { slots: "x" }, { slots: [null, 3, { slot: null, players: [{ name: "A" }] }, { slot: "QB", players: "x" }, { slot: "RB", unit: 4, players: [null, { number: 3 }, { name: "B" }] }] }]) {
    assert.ok(Array.isArray(lineupSlots(junk)));
    assert.ok(Array.isArray(lineupStarters(junk)));
    assert.equal(typeof lineupSummary(junk), "string");
  }
  assert.deepEqual(lineupStarters({ slots: [{ slot: "RB", players: [null, { number: 3 }, { name: "B" }] }] }).map((s) => s.player.name), ["B"], "the first real name starts");
};

scenarios.blocks = async () => {
  const { startersBlock, depthBlock, LINEUPS_EMPTY } = await import(moduleUrl("ui/lineups.js"));
  const l = lineups();
  const opened = [];
  const starters = startersBlock({ lineups: l, us, them, availability, onPlayer: (row) => opened.push(row) });
  document.body.replaceChildren(starters);
  const t = clean("starters", starters);
  // three matchup rows: SWT offense | MIZ defense, MIZ offense | SWT defense, SWT specialists | MIZ specialists
  const pairs = starters.querySelectorAll(".lineups__pair");
  assert.equal(pairs.length, 4, "three matchup rows and the foot");
  const sides = starters.querySelectorAll(".lineups__side");
  assert.equal(sides.length, 6);
  assert.deepEqual([...sides].map((s) => text(s.querySelector(".subhead"))), ["Swampwater Tech offense", "Sweet Tea State defense", "Sweet Tea State offense", "Swampwater Tech defense", "Swampwater Tech special teams", "Sweet Tea State special teams"]);
  // SWT offense: only the first name at each slot, the class under it, chips relabelled like the impact cards
  const offense = sides[0].querySelector("table");
  assert.deepEqual(heads(offense), ["Slot", "No.", "Starter", "Season"], "no Note column where nobody is listed");
  assert.equal(offense.querySelectorAll("tbody tr").length, 3, "QB, RB and LT start; the empty WR slot is left out");
  assert.ok(t.includes("Mason Hamilton") && t.includes("Lucas Griffin") && !t.includes("Dante Clayborn"), "backups are not starters");
  const qbRow = offense.querySelectorAll("tbody tr")[0];
  assert.deepEqual([...qbRow.querySelectorAll(".chip")].map(text), ["917 passing yards", "7 TD", "2 INT", "72% Cmp"], "plain labels, as on the impact cards");
  assert.deepEqual([...offense.querySelectorAll("tbody tr")[1].querySelectorAll(".chip")].map(text), ["600 rushing yards", "83 Car"], "CFBD keys get the plain labels");
  assert.equal(text(offense.querySelectorAll("tbody tr")[2].childNodes[3]), "–", "a lineman with no numbers shows a dash");
  // the availability report verifies the chart: a listed starter shows its status, coloured like the report
  const defense = sides[3].querySelector("table");
  assert.deepEqual(heads(defense), ["Slot", "No.", "Starter", "Season", "Note"]);
  const star = defense.querySelector("tbody tr");
  assert.ok(star.querySelector(".avail--questionable") && text(star).includes("Questionable ankle"), text(star));
  assert.ok(!text(star).includes("chart says"), "the report's status replaces the chart's own note");
  const jack = sides[1].querySelector("table tbody tr");
  assert.ok(jack.querySelector(".avail--out") && text(jack).includes("Out"));
  // a tap on a row with an id opens that player's card; a row without one does nothing
  qbRow.click();
  offense.querySelectorAll("tbody tr")[2].click();
  assert.equal(opened.length, 1);
  assert.equal(opened[0].playerId, "4536127");
  assert.equal(opened[0].isUs, true);
  sides[2].querySelector("table tbody tr").click();
  assert.equal(opened.length, 2);
  assert.equal(opened[1].isUs, false, "the opponent's starter opens as theirs");
  // scheme and source under the rows: a link when it has a URL, plain text otherwise
  assert.ok(t.includes("Swampwater Tech chart heading: Spread option."));
  const link = [...starters.querySelectorAll("a")].find((a) => a.getAttribute("href") === "https://example.invalid/uf");
  assert.ok(link && text(link) === "Mudpuppies Wire");
  assert.ok(t.includes("Source: Ourlads, updated ") && t.includes("Sep 26"));

  const depth = depthBlock({ lineups: l, us, them, availability });
  document.body.replaceChildren(depth);
  const d = clean("depth", depth);
  const dsides = depth.querySelectorAll(".lineups__side");
  assert.equal(dsides.length, 6);
  const table = dsides[0].querySelector("table");
  assert.deepEqual(heads(table), ["Slot", "Starter", "Second", "Third", "Fourth"], "as many columns as the deepest slot, up to five");
  const rb = [...table.querySelectorAll("tbody tr")].find((row) => text(row).startsWith("RB"));
  assert.ok(text(rb).includes("#13 Lucas Griffin (JR)") && text(rb).includes("#24 Landon Merriweather"));
  const qb = [...table.querySelectorAll("tbody tr")].find((row) => text(row).startsWith("QB"));
  assert.ok(text(qb).includes("–"), "a slot shorter than the table gets dashes");
  assert.ok(d.includes("#20 Kane Clayborn (RS SR), questionable") && d.includes("#19 Darius Smithers (RS SR), out"), "a listed name carries its status");
  const themTable = dsides[1].querySelector("table");
  assert.deepEqual(heads(themTable), ["Slot", "Starter", "Second"]);

  // one unit missing on a side says so instead of vanishing; nothing written is the honest empty note
  assert.ok(text(depthBlock({ lineups: { us: l.us }, us, them })).includes("No chart written for this unit."));
  for (const empty of [undefined, null, {}, { us: null, them: "x" }, { us: { slots: [] } }, { us: { slots: [{ slot: "QB", players: [] }] } }]) {
    assert.equal(clean("empty", startersBlock({ lineups: empty, us, them })), LINEUPS_EMPTY);
    assert.equal(clean("empty depth", depthBlock({ lineups: empty, us, them })), LINEUPS_EMPTY);
  }
  // damage: junk rows, wrong types, missing teams, chips that are not strings
  const bad = { us: { team: 3, scheme: 9, source: 4, sourceUrl: "javascript:alert(1)", slots: [null, "x", { slot: "QB", unit: null, players: [{ name: "A", number: "12", classYear: 3, note: {}, chips: [null, 4, "x"], playerId: 7 }, null, 5] }, { slot: 7, players: [{ name: "B" }] }] }, them: 11 };
  clean("damaged starters", startersBlock({ lineups: bad, us: null, them: undefined, availability: "x", onPlayer: 3 }));
  const badDepth = depthBlock({ lineups: bad });
  clean("damaged depth", badDepth);
  assert.ok(!badDepth.querySelector("a"), "a non-http source URL is never a link");
  assert.ok(text(badDepth).includes("Opponent"), "no opponent name falls back to a word, never undefined");
};

async function mountProgram(data) {
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/program", () => envelope(data));
  route("/api/notes/run", () => envelope({ running: false, commandFound: true }));
  route("/api/radio/sources", () => envelope({ sources: [] }));
  const { createProgramView } = await import(moduleUrl("views/program.js"));
  const root = document.createElement("div");
  document.body.append(root);
  const view = createProgramView({ onStatus: () => {}, gameId: null });
  view.mount(root);
  await settle();
  return { root, view };
}

scenarios.programBands = async () => {
  const withLineups = JSON.parse(JSON.stringify(FIXTURE));
  withLineups.notes = { ...withLineups.notes, present: true, author: "test", lineups: lineups(), availability };
  const { root, view } = await mountProgram(withLineups);
  clean("program with lineups", root);
  const starters = root.querySelector("#program-lineups");
  const depth = root.querySelector("#program-depth");
  assert.ok(starters && depth, "both bands are on the page");
  assert.equal(text(starters.querySelector(".band__title")), "Starting lineups");
  assert.ok(text(starters.querySelector(".band__summary")).includes("Published depth charts"));
  assert.equal(depth.getAttribute("data-collapsed"), "true", "the full chart starts folded");
  assert.ok(text(starters).includes("Mason Hamilton") && text(starters).includes("917 passing yards") && text(depth).includes("Tramell Jones Jr."));
  assert.ok(starters.querySelector(".avail--questionable"), "the program hands the availability report to the block");
  // the order on the page: notes, availability, lineups, depth, then the rest
  const ids = [...root.querySelectorAll("section.band")].map((s) => s.getAttribute("id") || "");
  assert.ok(ids.indexOf("program-availability") < ids.indexOf("program-lineups") && ids.indexOf("program-lineups") < ids.indexOf("program-depth"), ids.join(","));
  // owner direction: every band on the program can be minimised (a toggle in every head)
  const bands = [...root.querySelectorAll("section.band")].filter((b) => b.querySelector(".band__head"));
  const stuck = bands.filter((b) => !b.querySelector(".band__toggle")).map((b) => text(b.querySelector(".band__title")));
  assert.deepEqual(stuck, [], `bands without a toggle: ${stuck.join(", ")}`);
  view.unmount();
  root.remove();
  // without lineups the bands stay, with the empty note and no summary
  const bare = await mountProgram(JSON.parse(JSON.stringify(FIXTURE)));
  clean("program without lineups", bare.root);
  assert.ok(text(bare.root.querySelector("#program-lineups")).includes("No lineups for this game yet."));
  assert.ok(!bare.root.querySelector("#program-lineups .band__summary"));
  bare.view.unmount();
  bare.root.remove();
};
"""


@needs_node
def test_lineup_helpers(tmp_path: Path):
    run_scenario(tmp_path, SCENARIOS, "helpers")


@needs_node
def test_lineup_blocks(tmp_path: Path):
    run_scenario(tmp_path, SCENARIOS, "blocks")


@needs_node
def test_program_lineup_bands(tmp_path: Path):
    import json

    from tests.test_p16_program_js import payload

    fixture = tmp_path / "program.json"
    fixture.write_text(json.dumps(payload()), encoding="utf-8")
    run_scenario(tmp_path, SCENARIOS, "programBands", str(fixture))
