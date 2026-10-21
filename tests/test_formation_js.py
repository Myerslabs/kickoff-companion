"""The lineups in formation (the formation mock, owner 2026-10-20): the scheme's words as numbers, each starter at his slot's
spot on the field, both matchups drawn with the availability report's ring and a tap to the card."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const slot = (unit, name, player) => ({ unit, slot: name, players: [player] });
const p = (name, extra = {}) => ({ name, classYear: "JR", number: 7, ...extra });
const spread = [slot("Offense", "QB", p("Quin Back", { playerId: "1" })), slot("Offense", "RB", p("Ray Back")), slot("Offense", "WR-X", p("Xavier Wide")), slot("Offense", "WR-Z", p("Zed Wide")), slot("Offense", "WR-SL", p("Sam Slot")), slot("Offense", "TE", p("Ted End")), slot("Offense", "LT", p("Lee Tackle")), slot("Offense", "LG", p("Lou Guard")), slot("Offense", "C", p("Cal Center")), slot("Offense", "RG", p("Rob Guard")), slot("Offense", "RT", p("Ron Tackle"))];
const nickel = [slot("Defense", "DE", p("Ed End")), slot("Defense", "DT", p("Dan Tackle")), slot("Defense", "NT", p("Ned Nose")), slot("Defense", "DE", p("Eli End")), slot("Defense", "MIKE", p("Mike Backer", { playerId: "9" })), slot("Defense", "WILL", p("Will Backer")), slot("Defense", "CB", p("Cal Corner")), slot("Defense", "CB", p("Cory Corner")), slot("Defense", "NB", p("Nick Back")), slot("Defense", "FS", p("Fred Safety")), slot("Defense", "SS", p("Sid Safety"))];
const at = (list, name) => { const m = list.find((x) => x.player.name === name); return m ? [m.x, m.y] : null; };

scenarios.scheme = async () => {
  const { parseScheme } = await import(moduleUrl("ui/formation.js"));
  assert.deepEqual(parseScheme("Spread, 11 personnel, up-tempo"), { backs: 1, tightEnds: 1, underCenter: false, front: null });
  assert.deepEqual(parseScheme("Pro style, 12 personnel"), { backs: 1, tightEnds: 2, underCenter: true, front: null });
  assert.deepEqual(parseScheme("4-2-5, quarters").front, { line: 4, linebackers: 2, backs: 5 });
  assert.deepEqual(parseScheme("3-4, man under").front, { line: 3, linebackers: 4, backs: null });
  assert.equal(parseScheme("Pro style spread").underCenter, false, "spread wins over pro style");
  for (const junk of [null, 3, "", "nothing here"]) assert.deepEqual(parseScheme(junk), { backs: null, tightEnds: null, underCenter: false, front: null });
};

scenarios.place = async () => {
  const { parseScheme, placeDefense, placeOffense } = await import(moduleUrl("ui/formation.js"));
  // an 11-personnel spread: the receivers at X, Z and the slot, the tight end on the line, the quarterback in the gun
  const off = placeOffense(spread, parseScheme("Spread, 11 personnel"));
  assert.equal(off.length, 11);
  assert.deepEqual([at(off, "Xavier Wide"), at(off, "Zed Wide"), at(off, "Sam Slot"), at(off, "Ted End")], [[7, 56], [93, 59], [18, 64], [78, 56]]);
  assert.deepEqual([at(off, "Quin Back"), at(off, "Ray Back")], [[50, 78], [61, 78]]);
  assert.deepEqual([at(off, "Lee Tackle"), at(off, "Lou Guard"), at(off, "Cal Center"), at(off, "Rob Guard"), at(off, "Ron Tackle")].map((xy) => xy[0]), [35, 43, 50, 57, 65], "the linemen tight on the center, as marked");
  // pro style: under center, the back behind him, two tight ends on the line
  const pro = placeOffense([...spread.filter((s) => !/WR-SL/.test(s.slot)), slot("Offense", "TE", p("Tom End"))], parseScheme("Pro style, 12 personnel"));
  assert.deepEqual([at(pro, "Quin Back"), at(pro, "Ray Back"), at(pro, "Ted End"), at(pro, "Tom End")], [[50, 73], [50, 90], [78, 56], [22, 56]]);
  // no tight end on the chart: the fourth receiver takes the line spot (the owner's mark); generic OL slots fill left to right
  const four = placeOffense([slot("Offense", "QB", p("Q")), slot("Offense", "WR", p("A")), slot("Offense", "WR", p("B")), slot("Offense", "WR", p("Cc")), slot("Offense", "WR", p("D")), slot("Offense", "OL", p("O1")), slot("Offense", "OL", p("O2"))], parseScheme("Spread, 10 personnel"));
  assert.deepEqual([at(four, "A"), at(four, "B"), at(four, "Cc"), at(four, "D"), at(four, "O1"), at(four, "O2")], [[7, 56], [93, 59], [18, 64], [78, 56], [35, 56], [43, 56]]);
  // twelve on the chart: eleven on the field; junk never breaks it
  const twelve = placeOffense([...spread, slot("Offense", "WR", p("Extra Man"))], parseScheme(""));
  assert.equal(twelve.length, 11);
  assert.deepEqual(placeOffense([null, "x", { slot: "QB", players: [] }, { slot: 3, players: [p("No Slot")] }], null).length, 0);
  // a 4-2-5: the front across the line, the two backers behind, the nickel over the slot, the safeties deep
  const def = placeDefense(nickel, parseScheme("4-2-5, quarters"));
  assert.equal(def.length, 11);
  assert.deepEqual([at(def, "Ed End"), at(def, "Dan Tackle"), at(def, "Ned Nose"), at(def, "Eli End")], [[33.5, 42], [41.5, 42], [50, 42], [58.5, 42]]);
  assert.deepEqual([at(def, "Mike Backer"), at(def, "Will Backer"), at(def, "Nick Back"), at(def, "Fred Safety"), at(def, "Sid Safety"), at(def, "Cal Corner"), at(def, "Cory Corner")], [[45, 25], [55, 25], [22, 26], [36, 9], [64, 9], [7, 36], [93, 36]]);
  // a 3-4: three down, the outside backers on the edges, the inside backers behind the line
  const odd = placeDefense([slot("Defense", "DE", p("A")), slot("Defense", "NT", p("B")), slot("Defense", "DE", p("Cc")), slot("Defense", "OLB", p("O1")), slot("Defense", "ILB", p("I1")), slot("Defense", "ILB", p("I2")), slot("Defense", "OLB", p("O2")), slot("Defense", "CB", p("K1")), slot("Defense", "CB", p("K2")), slot("Defense", "S", p("S1")), slot("Defense", "S", p("S2"))], parseScheme("3-4, man under"));
  assert.deepEqual([at(odd, "A"), at(odd, "B"), at(odd, "Cc"), at(odd, "O1"), at(odd, "I1"), at(odd, "I2"), at(odd, "O2"), at(odd, "S1"), at(odd, "S2")], [[38, 42], [50, 42], [62, 42], [26, 36], [44, 25], [56, 25], [74, 36], [36, 9], [64, 9]]);
  // no scheme words: the chart's own counts set the front and the backers
  const bare = placeDefense(nickel.slice(0, 6), null);
  assert.deepEqual([at(bare, "Ed End"), at(bare, "Will Backer")], [[33.5, 42], [55, 25]]);
  assert.deepEqual(placeDefense("x", {}), []);
};

scenarios.block = async () => {
  const { formationBlock } = await import(moduleUrl("ui/formation.js"));
  const opened = [];
  const lineups = { us: { team: "Home U", slots: [...spread, ...nickel] }, them: { team: "Away U", scheme: "3-4", slots: [slot("Offense", "QB", p("Their Back", { playerId: "22" })), slot("Offense", "TE", p("Their End")), slot("Defense", "DE", p("Their Lineman"))] } };
  const schemes = { offense: "Spread, 11 personnel", defense: "4-2-5, quarters", opponent: { offense: "Pro style, 12 personnel" } };
  const node = formationBlock({ lineups, us: { school: "Home U", abbreviation: "HU" }, them: { school: "Away U", abbreviation: "AU" }, schemes, availability: [{ name: "Ray Back", status: "Questionable", note: "ankle" }], detail: (unit, side) => (unit === "offense" && side === "us" ? "OC Caller · Spread" : null), onPlayer: (row) => opened.push(`${row.slot}:${row.playerId}:${row.isUs}`) });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  const fields = node.querySelectorAll(".formation__matchup");
  assert.equal(fields.length, 2, "our offense against their defense, then theirs against ours");
  assert.ok(text(fields[0].querySelector(".formation__head")).includes("Home U offense") && text(fields[0].querySelector(".formation__head")).includes("OC Caller · Spread") && text(fields[0].querySelector(".formation__head")).includes("Away U defense"));
  assert.ok(text(fields[1].querySelector(".formation__head")).includes("Pro style, 12 personnel"), "the notes' words for the other unit");
  assert.equal(fields[0].querySelectorAll(".formation__man--us").length, 11, "eleven of ours on the first field");
  assert.equal(fields[0].querySelectorAll(".formation__man--them").length, 1, "the one defender their chart lists");
  assert.equal(fields[1].querySelectorAll(".formation__man--them").length, 2);
  assert.equal(fields[1].querySelectorAll(".formation__man--us").length, 11);
  const qb = fields[0].querySelectorAll("button.formation__man").find((b) => text(b).includes("Back") && text(b).includes("QB"));
  assert.ok(qb && qb.style["--fx"] === "50%" && qb.style["--fy"] === "78%", "the quarterback in the gun, a button because the chart knows him");
  qb.click();
  assert.deepEqual(opened, ["QB:1:true"]);
  const theirQb = fields[1].querySelectorAll("button.formation__man").find((b) => text(b).includes("QB"));
  theirQb.click();
  assert.equal(opened[1], "QB:22:false");
  const rb = fields[0].querySelectorAll(".formation__man").find((m) => text(m).includes("RB"));
  assert.ok(rb.className.includes("formation__man--listed") && text(rb).includes("Questionable") && rb.tagName === "DIV", "the report's ring and status; no id, not a button");
  assert.ok(fields[0].querySelector(".formation__los") && text(fields[0]).includes("Line of scrimmage"));
  assert.ok(t.includes("A gold ring is a starter on the availability report"));
  // nothing drawn without a chart; junk never breaks it
  assert.equal(formationBlock({}), null);
  assert.equal(formationBlock({ lineups: { us: { slots: "x" }, them: null }, schemes: "x", availability: 3 }), null);
  const odd = formationBlock({ lineups: { us: { slots: [slot("Offense", "QB", p("Only One"))] } }, us: null, them: undefined, schemes: { opponent: 4 } });
  assert.ok(odd && !RAW.test(text(odd)) && odd.querySelectorAll(".formation__matchup").length === 1);
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["scheme", "place", "block"])
def test_formation_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
