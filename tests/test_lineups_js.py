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
  // Freeze wave F3 (one fact, one source): the starters and depth tables went; ui/lineups_combined.js is the one kit
  const mod = await import(moduleUrl("ui/lineups.js"));
  assert.equal(mod.startersBlock, undefined);
  assert.equal(mod.depthBlock, undefined);
  assert.ok(typeof mod.LINEUPS_EMPTY === "string" && mod.LINEUPS_EMPTY.length > 10, "the empty-state words still live here");
  const { lineupBlock } = await import(moduleUrl("ui/lineups_combined.js"));
  const l = lineups();
  const node = lineupBlock({ lineups: l, us, them, availability });
  document.body.replaceChildren(node);
  const t = clean("combined", node);
  assert.ok(t.includes("Mason Hamilton"), "the one kit draws the chart");
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
  assert.ok(starters, "the combined band is on the page");
  assert.equal(root.querySelector("#program-depth"), null, "the depth chart is part of the lineups now (Phase 19)");
  assert.equal(text(starters.querySelector(".band__title")), "Lineups");
  assert.ok(text(starters.querySelector(".band__summary")).includes("Published depth charts"));
  assert.ok(text(starters).includes("Mason Hamilton") && text(starters).includes("917 passing yards") && !starters.querySelector(".lu-next") && !text(starters).includes("Tramell Jones"), "the starters with their chips; the depth behind them is not drawn (the mock, owner 2026-10-20)");
  assert.ok(text(starters).includes("Experience of the starters"));
  // 2026-10-10: lineups as matchups, one table per pairing, each starter beside the man he faces; the tables size themselves
  const sized = [...starters.querySelectorAll(".stat-table-wrap[data-size]")];
  assert.ok(sized.length >= 2, "the experience table and every matchup table declare sizes");
  assert.ok(starters.querySelector(".lu-head") && text(starters.querySelector(".lu-head")).includes("offense") && text(starters.querySelector(".lu-head")).includes("defense"), "the matchup's title names both units");
  assert.ok(starters.querySelector("td.st__wrap.st__min-large"), "the season chips wrap in their cell and show at large only");
  assert.ok(starters.querySelector("td .sz-t--short button.lu-name .pn"), "item 6: the starter's name alone at small, still his button");
  assert.ok(starters.querySelector(".avail--questionable"), "the program hands the availability report to the block");
  // the order on the page: notes, availability, lineups and depth, then the rest
  const ids = [...root.querySelectorAll("section.band")].map((s) => s.getAttribute("id") || "");
  assert.ok(ids.indexOf("program-availability") < ids.indexOf("program-lineups"), ids.join(","));
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
  // Phase 17 #13: each empty band says what it is missing and offers "Add notes", which unfolds the notes band
  assert.ok(text(bare.root.querySelector("#program-availability")).includes("No availability report for this game yet."));
  for (const id of ["program-availability", "program-lineups"]) {
    const add = bare.root.querySelector(`#${id} .state-block__action`);
    assert.equal(text(add), "Add notes", `${id} offers Add notes`);
  }
  const notesBand = bare.root.querySelector("#program-notes");
  notesBand.setCollapsed(true);
  bare.root.querySelector("#program-lineups .state-block__action").click();
  assert.equal(notesBand.getAttribute("data-collapsed"), "false", "Add notes unfolds the notes band");
  assert.ok(!text(bare.root).includes("pre-game notes task") && !text(bare.root).includes("by hand;"));
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
