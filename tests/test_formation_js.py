"""The lineup as a picture (the formation mock, owner 2026-10-20; his marks on the Lineups board, 2026-11-01): the scheme's
words as numbers, each starter at his slot's spot on the field, both matchups drawn as big numbers with a tag, a line and a
grade, the availability report's gold number, the impact ring from the roster and a tap to the card."""

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
  const { kindOf, parseScheme } = await import(moduleUrl("ui/formation.js"));
  // a slot's kind: the notes' names and the longer forms some charts print read the same
  assert.deepEqual([kindOf("LOLB"), kindOf("SCB"), kindOf("SWR"), kindOf("HB"), kindOf("WR-X"), kindOf("K"), kindOf("NT"), kindOf("SAM"), kindOf(null)], ["EDGE", "NB", "H", "RB", "X", null, "NT", "SAM", null]);
  assert.deepEqual(parseScheme("Spread, 11 personnel, up-tempo"), { backs: 1, tightEnds: 1, underCenter: false, front: null });
  assert.deepEqual(parseScheme("Pro style, 12 personnel"), { backs: 1, tightEnds: 2, underCenter: true, front: null });
  assert.deepEqual(parseScheme("4-2-5, quarters").front, { line: 4, linebackers: 2, backs: 5 });
  assert.deepEqual(parseScheme("3-4, man under").front, { line: 3, linebackers: 4, backs: null });
  assert.equal(parseScheme("Pro style spread").underCenter, false, "spread wins over pro style");
  for (const junk of [null, 3, "", "nothing here"]) assert.deepEqual(parseScheme(junk), { backs: null, tightEnds: null, underCenter: false, front: null });
};

scenarios.place = async () => {
  const { leftOff, parseScheme, placeDefense, placeOffense } = await import(moduleUrl("ui/formation.js"));
  // an 11-personnel spread: the receivers at X, Z and the slot, the tight end on the line, the quarterback in the gun
  const off = placeOffense(spread, parseScheme("Spread, 11 personnel"));
  assert.equal(off.length, 11);
  assert.deepEqual([at(off, "Xavier Wide"), at(off, "Zed Wide"), at(off, "Sam Slot"), at(off, "Ted End")], [[8, 60], [92, 58], [14, 74], [86, 74]]);
  assert.deepEqual([at(off, "Quin Back"), at(off, "Ray Back")], [[50, 83], [62, 83]]);
  assert.deepEqual([at(off, "Lee Tackle"), at(off, "Lou Guard"), at(off, "Cal Center"), at(off, "Rob Guard"), at(off, "Ron Tackle")].map((xy) => xy[0]), [26, 38, 50, 62, 74], "the linemen a chip apart on the center (the board of 2026-11-01)");
  // pro style: under center, the back behind him, two tight ends on the line
  const pro = placeOffense([...spread.filter((s) => !/WR-SL/.test(s.slot)), slot("Offense", "TE", p("Tom End"))], parseScheme("Pro style, 12 personnel"));
  assert.deepEqual([at(pro, "Quin Back"), at(pro, "Ray Back"), at(pro, "Ted End"), at(pro, "Tom End")], [[50, 77], [50, 92], [86, 74], [24, 76]]);
  // no tight end on the chart: the fourth receiver takes the line spot (the owner's mark); generic OL slots fill left to right
  const four = placeOffense([slot("Offense", "QB", p("Q")), slot("Offense", "WR", p("A")), slot("Offense", "WR", p("B")), slot("Offense", "WR", p("Cc")), slot("Offense", "WR", p("D")), slot("Offense", "OL", p("O1")), slot("Offense", "OL", p("O2"))], parseScheme("Spread, 10 personnel"));
  assert.deepEqual([at(four, "A"), at(four, "B"), at(four, "Cc"), at(four, "D"), at(four, "O1"), at(four, "O2")], [[8, 60], [92, 58], [14, 74], [86, 74], [26, 62], [38, 62]]);
  // twelve on the chart: eleven on the field; junk never breaks it
  const twelve = placeOffense([...spread, slot("Offense", "WR", p("Extra Man"))], parseScheme(""));
  assert.equal(twelve.length, 11);
  assert.deepEqual(placeOffense([null, "x", { slot: "QB", players: [] }, { slot: 3, players: [p("No Slot")] }], null).length, 0);
  // a 4-2-5: the front across the line, the two backers behind, the nickel over the slot, the safeties deep
  const def = placeDefense(nickel, parseScheme("4-2-5, quarters"));
  assert.equal(def.length, 11);
  assert.deepEqual([at(def, "Ed End"), at(def, "Dan Tackle"), at(def, "Ned Nose"), at(def, "Eli End")], [[24, 42], [41, 42], [59, 42], [76, 42]]);
  assert.deepEqual([at(def, "Mike Backer"), at(def, "Will Backer"), at(def, "Nick Back"), at(def, "Fred Safety"), at(def, "Sid Safety"), at(def, "Cal Corner"), at(def, "Cory Corner")], [[43, 26], [57, 26], [22, 26], [36, 12], [64, 12], [8, 24], [92, 24]]);
  // a 3-4: three down, the outside backers on the edges, the inside backers behind the line
  const odd = placeDefense([slot("Defense", "DE", p("A")), slot("Defense", "NT", p("B")), slot("Defense", "DE", p("Cc")), slot("Defense", "OLB", p("O1")), slot("Defense", "ILB", p("I1")), slot("Defense", "ILB", p("I2")), slot("Defense", "OLB", p("O2")), slot("Defense", "CB", p("K1")), slot("Defense", "CB", p("K2")), slot("Defense", "S", p("S1")), slot("Defense", "S", p("S2"))], parseScheme("3-4, man under"));
  assert.deepEqual([at(odd, "A"), at(odd, "B"), at(odd, "Cc"), at(odd, "O1"), at(odd, "I1"), at(odd, "I2"), at(odd, "O2"), at(odd, "S1"), at(odd, "S2")], [[30, 42], [50, 42], [70, 42], [16, 35], [43, 26], [57, 26], [84, 35], [36, 12], [64, 12]]);
  // no scheme words: the chart's own counts set the front and the backers (four down, no nickel: three backer spots, the Will on one side)
  const bare = placeDefense(nickel.slice(0, 6), null);
  assert.deepEqual([at(bare, "Ed End"), at(bare, "Will Backer"), at(bare, "Mike Backer")], [[24, 42], [36, 26], [50, 26]]);
  assert.deepEqual(bare.missing, ["a linebacker", "a cornerback", "a cornerback", "a free safety", "a strong safety"], "the spots nobody fills, said under the field");
  assert.equal(placeDefense("x", {}).length, 0);
  // the owner's charts of 2026-11-01 (Ourlads): Florida's 3-4 lists a nickel beside the Jack and three backers, twelve men, and
  // the base keeps both safeties; Georgia's names its inside backers Mac and Money, and the nickel fills its eleventh spot
  const florida = [slot("Defense", "DE", p("Caleb James")), slot("Defense", "NT", p("Brendan Bett")), slot("Defense", "DT", p("Jeramiah McCloud")), slot("Defense", "JACK", p("Jayden Woods")), slot("Defense", "WLB", p("Myles Graham")), slot("Defense", "MLB", p("Taylor Robinson")), slot("Defense", "SLB", p("Aaron Chiles")), slot("Defense", "NB", p("Kanye Clark")), slot("Defense", "LCB", p("Cormani McClain")), slot("Defense", "RCB", p("Ben Hanks")), slot("Defense", "FS", p("DJ Coleman")), slot("Defense", "SS", p("Bryce Thornton"))];
  const fla = placeDefense(florida, parseScheme("3-4"));
  assert.equal(fla.length, 11);
  assert.deepEqual(leftOff(florida, fla).map((m) => m.slot), ["NB"], "the twelfth man off is the nickel, not a safety");
  assert.deepEqual([at(fla, "DJ Coleman"), at(fla, "Bryce Thornton"), at(fla, "Jayden Woods")], [[36, 12], [64, 12], [16, 35]]);
  const georgia = [slot("Defense", "DE", p("Christen Miller")), slot("Defense", "NT", p("Jordan Hall")), slot("Defense", "DT", p("Elijah Griffin")), slot("Defense", "JACK", p("Quintavius Johnson")), slot("Defense", "MAC", p("Raylen Wilson")), slot("Defense", "MONEY", p("Chris Cole")), slot("Defense", "NB", p("Daniel Harris")), slot("Defense", "LCB", p("Daylen Everette")), slot("Defense", "RCB", p("Ellis Robinson")), slot("Defense", "FS", p("KJ Bolden")), slot("Defense", "SS", p("Malaki Starks"))];
  const uga = placeDefense(georgia, parseScheme("3-4"));
  assert.equal(uga.length, 10, "the Mac and the Money inside; the 3-4 has no spot for the nickel and the chart names no Sam (the owner, 2026-11-01: 'you may be thinking about the nickel package')");
  assert.deepEqual([at(uga, "Raylen Wilson"), at(uga, "Chris Cole"), at(uga, "Daniel Harris"), at(uga, "Quintavius Johnson")], [[43, 26], [57, 26], null, [16, 35]]);
  assert.deepEqual(uga.missing, ["an outside linebacker"]);
  assert.deepEqual(leftOff(georgia, uga).map((m) => m.slot), ["NB"]);
  // the chart's second string fills the spot the starters leave: a second Jack stands at the other edge
  const deeper = georgia.map((s) => (s.slot === "JACK" ? { ...s, players: [...s.players, p("Gabe Harris")] } : s));
  const full = placeDefense(deeper, parseScheme("3-4"));
  assert.equal(full.length, 11);
  assert.deepEqual(at(full, "Gabe Harris"), [84, 35]);
  assert.ok(full.find((m) => m.player.name === "Gabe Harris").reserve === true, "marked as the second string");
  assert.deepEqual(full.missing, []);
  // a chart with no tackle at all and no spare edge: the nose comes from the second string, never an edge backer
  const noTackle = [slot("Defense", "LE", p("Lee End")), slot("Defense", "RE", p("Ray End")), { unit: "Defense", slot: "LE", players: [p("Lee End"), p("Back Up")] }, slot("Defense", "LOLB", p("Lou Edge")), slot("Defense", "ROLB", p("Ron Edge")), slot("Defense", "LILB", p("Ian In")), slot("Defense", "RILB", p("Rob In")), slot("Defense", "LCB", p("Cal Corner")), slot("Defense", "RCB", p("Cory Corner")), slot("Defense", "FS", p("Fred Safety")), slot("Defense", "SS", p("Sid Safety"))];
  const three = placeDefense(noTackle, parseScheme("3-4"));
  assert.deepEqual(three.filter((m) => m.y === 42).map((m) => [m.player.name, m.x]), [["Lee End", 30], ["Back Up", 50], ["Ray End", 70]], "the second-string lineman at the nose, the edges stay behind");
  assert.deepEqual([at(three, "Lou Edge"), at(three, "Ron Edge")], [[16, 35], [84, 35]]);
};

scenarios.block = async () => {
  const { formationBlock } = await import(moduleUrl("ui/formation.js"));
  const opened = [];
  const lineups = { us: { team: "Home U", slots: [...spread, ...nickel] }, them: { team: "Away U", scheme: "3-4", slots: [slot("Offense", "QB", p("Their Back", { playerId: "22", grade: 82.14 })), slot("Offense", "TE", p("Their End", { grade: 71.6 })), slot("Defense", "DE", p("Their Lineman"))] } };
  const schemes = { offense: "Spread, 11 personnel", defense: "4-2-5, quarters", opponent: { offense: "Pro style, 12 personnel" } };
  const coaches = { us: { offensiveCoordinator: "Cal Caller", defensiveCoordinator: "Dee Stopper" }, them: { offensiveCoordinator: "Ozzie Other" } };
  const node = formationBlock({ lineups, us: { school: "Home U", abbreviation: "HU" }, them: { school: "Away U", abbreviation: "AU" }, schemes, coaches, availability: [{ name: "Ray Back", status: "Questionable", note: "ankle" }], onPlayer: (row) => opened.push(`${row.slot}:${row.playerId}:${row.isUs}`) });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  const fields = node.querySelectorAll(".formation__matchup");
  assert.equal(fields.length, 2, "their defense over our offense, then ours over theirs");
  // the half labels on the field: the team and the unit, the scheme and the coordinator (the board of 2026-11-01)
  const def0 = text(fields[0].querySelector(".formation__half--defense"));
  const off0 = text(fields[0].querySelector(".formation__half--offense"));
  assert.ok(def0.includes("Away U defense") && def0.includes("3-4"), def0);
  assert.ok(off0.includes("Home U offense") && off0.includes("Spread, 11 personnel") && off0.includes("OC Cal Caller"), off0);
  assert.ok(text(fields[1].querySelector(".formation__half--offense")).includes("Pro style, 12 personnel · OC Ozzie Other"), "the notes' words for the other unit");
  assert.ok(text(fields[1].querySelector(".formation__half--defense")).includes("DC Dee Stopper"));
  assert.ok(fields[0].querySelector(".formation__half--defense").className.includes("formation__side--them") && fields[0].querySelector(".formation__half--offense").className.includes("formation__side--us"));
  assert.ok(fields[0].querySelector(".formation__field").querySelector(".formation__half--offense"), "the labels stand in the field, so their middle is the line of scrimmage");
  assert.equal(fields[0].querySelectorAll(".formation__man--us").length, 11, "eleven of ours on the first field");
  assert.equal(fields[0].querySelectorAll(".formation__man--them").length, 1, "the one defender their chart lists");
  assert.equal(fields[1].querySelectorAll(".formation__man--them").length, 2);
  assert.equal(fields[1].querySelectorAll(".formation__man--us").length, 11);
  // a man: the big number, the tag with his position and surname, his class; the full name in his title
  const qb = fields[0].querySelectorAll("button.formation__man").find((b) => text(b.querySelector(".formation__pos")) === "QB");
  assert.ok(qb && qb.style["--fx"] === "50%" && qb.style["--fy"] === "83%", "the quarterback in the gun, a button because the chart knows him");
  assert.equal(text(qb.querySelector(".formation__num")), "7");
  assert.equal(text(qb.querySelector(".formation__name")), "Back", "the surname alone on the field (owner: 'Its fine the way it is')");
  assert.equal(text(qb.querySelector(".formation__line")), "JR", "the class from the chart; the size comes with the roster");
  assert.ok(qb.getAttribute("title").includes("Quin Back"));
  assert.ok(qb.querySelector(".formation__grade").hasAttribute("hidden"), "no grade yet: nothing shown, never a dash");
  qb.click();
  assert.deepEqual(opened, ["QB:1:true"]);
  // the grade alone: our stat grade, whole (owner: 'just have the grade')
  const theirQb = fields[1].querySelectorAll("button.formation__man").find((b) => text(b.querySelector(".formation__pos")) === "QB");
  assert.equal(text(theirQb.querySelector(".formation__grade")), "82");
  assert.equal(theirQb.querySelector(".formation__grade").dataset.kind, "ours");
  theirQb.click();
  assert.equal(opened[1], "QB:22:false");
  const theirTe = fields[1].querySelectorAll(".formation__man").find((m) => text(m.querySelector(".formation__pos")) === "TE");
  assert.equal(text(theirTe.querySelector(".formation__grade")), "72");
  assert.equal(theirTe.querySelector(".formation__grade").dataset.kind, "ours");
  const rb = fields[0].querySelectorAll(".formation__man").find((m) => text(m.querySelector(".formation__pos")) === "RB");
  assert.ok(rb.className.includes("formation__man--listed") && text(rb.querySelector(".formation__status")) === "Questionable" && rb.tagName === "DIV", "the report's gold number and status; no id, not a button");
  assert.ok(fields[0].querySelector(".formation__los") && text(fields[0]).includes("Line of scrimmage"));
  assert.ok(t.includes("A gold number is a starter on the availability report") && t.includes("a ring is an impact player"));
  // nothing drawn without a chart; junk never breaks it
  assert.equal(formationBlock({}), null);
  assert.equal(formationBlock({ lineups: { us: { slots: "x" }, them: null }, schemes: "x", availability: 3 }), null);
  const odd = formationBlock({ lineups: { us: { slots: [slot("Offense", "QB", p("Only One"))] } }, us: null, them: undefined, schemes: { opponent: 4 }, coaches: "x" });
  assert.ok(odd && !RAW.test(text(odd)) && odd.querySelectorAll(".formation__matchup").length === 1);
};

scenarios.picture = async () => {
  const { attachRosters, enrichLineup, lineupPicture, nameKey } = await import(moduleUrl("ui/formation.js"));
  assert.equal(nameKey("T.J. Shanahan Jr."), "tj shanahan");
  assert.equal(nameKey(4), "");
  // one team's picture: its defense over its offense (My Team, the Magazine)
  const lineup = { team: "Home U", slots: [...spread, ...nickel] };
  const node = lineupPicture({ defense: { school: "Home U", side: "us", lineup, scheme: "4-2-5", coordinator: "Dee Stopper" }, offense: { school: "Home U", side: "us", lineup, scheme: "Spread, 11 personnel", coordinator: null }, availability: [], onPlayer: () => {} });
  document.body.append(node);
  assert.ok(!RAW.test(text(node)));
  assert.equal(node.querySelectorAll(".formation__man--us").length, 22);
  assert.equal(node.querySelectorAll(".formation__man--them").length, 0);
  assert.ok(text(node.querySelector(".formation__half--defense")).includes("Home U defense") && text(node.querySelector(".formation__half--defense")).includes("4-2-5 · DC Dee Stopper"));
  assert.equal(text(node.querySelector(".formation__half--offense")), "Home U offenseSpread, 11 personnel");
  assert.equal(lineupPicture({ defense: { lineup: { slots: [] } }, offense: { lineup: null } }), null, "no man on either chart: nothing");
  // the roster behind the picture: the size and the grade by id, else by name (a shared name settled by the number); the impact ring
  const roster = {
    players: [
      { playerId: 1, name: "Quin Back", number: 7, classYear: "SO", heightText: "6-3", weight: 240, grade: { grade: 90 } },
      { playerId: 55, name: "Ray Back", number: 7, classYear: "JR", heightText: "6-0", weight: 230, grade: { grade: 63.6 } },
      { playerId: 56, name: "Ray Back", number: 30, heightText: "5-9", weight: 190 },
      { playerId: 57, name: "Xavier Wide", number: 7, heightText: null, weight: "heavy", grade: "x" },
    ],
    impact: { offense: [{ playerId: 1, name: "Quin Back" }], defense: [{ playerId: 999, name: "Mike Backer" }] },
  };
  assert.equal(enrichLineup(node, roster, "us"), 3, "three men found: by id, by name and number, by name alone");
  const man = (pos) => node.querySelectorAll(".formation__man").find((m) => text(m.querySelector(".formation__pos")) === pos);
  assert.equal(text(man("QB").querySelector(".formation__line")), "JR · 6-3 · 240", "the chart's class, the roster's size");
  assert.equal(text(man("QB").querySelector(".formation__grade")), "90", "the roster's stat grade");
  assert.ok(man("QB").className.includes("formation__man--impact"), "an impact player by id");
  assert.ok(man("MIKE").className.includes("formation__man--impact"), "an impact player by name when the ids differ");
  assert.ok(!man("WILL").className.includes("formation__man--impact"));
  assert.equal(text(man("RB").querySelector(".formation__line")), "JR · 6-0 · 230", "two Ray Backs: the number settles it");
  assert.equal(text(man("RB").querySelector(".formation__grade")), "64");
  assert.equal(text(man("WR-X").querySelector(".formation__line")), "JR", "junk size: the class alone");
  assert.ok(man("WR-X").querySelector(".formation__grade").hasAttribute("hidden"));
  assert.equal(enrichLineup(node, "junk", "us"), 0);
  assert.equal(enrichLineup(null, roster), 0);
  // a man the chart names without a number takes it from the roster; a chart man with no spot is counted off the field
  const bare = lineupPicture({ defense: { side: "us", lineup: { slots: [slot("Defense", "LE", p("Ed End", { number: null })), slot("Defense", "K", p("Kick Er"))] } }, offense: { side: "us", lineup: { slots: [] } } });
  document.body.append(bare);
  assert.equal(text(bare.querySelector(".formation__num")), "");
  enrichLineup(bare, { players: [{ playerId: 3, name: "Ed End", number: 95 }] }, "us");
  assert.equal(text(bare.querySelector(".formation__num")), "95");
  const said = [...bare.querySelectorAll(".formation__count")].map((c) => text(c));
  assert.ok(said[0].startsWith("Our defense: 1 of 11 on the field · nobody for a defensive end, an outside linebacker") && said[0].endsWith("· off it: K Kick Er"), said[0]);
  assert.equal(said[1], "Our offense: 0 of 11 on the field");
  // attachRosters: one read a school, the picture filled when it lands; a roster that fails leaves it as drawn
  const asked = [];
  route("/api/roster?team=Home%20U", (url) => { asked.push(String(url)); return envelope(roster); });
  route("/api/roster?team=Away%20U", () => { throw new Error("down"); });
  const fresh = lineupPicture({ defense: { school: "Away U", side: "them", lineup: { slots: nickel }, scheme: "4-2-5" }, offense: { school: "Home U", side: "us", lineup: { slots: spread } } });
  document.body.append(fresh);
  const counts = await attachRosters(fresh, { us: "Home U", them: "Away U" });
  assert.deepEqual(counts, [3, 0]);
  assert.equal(text(fresh.querySelectorAll(".formation__man--us").find((m) => text(m.querySelector(".formation__pos")) === "QB").querySelector(".formation__grade")), "90");
  await attachRosters(fresh, { us: "Home U" });
  assert.equal(asked.length, 1, "one roster read a school for the page");
};

"""


@needs_node
@pytest.mark.parametrize("scenario", ["scheme", "place", "block", "picture"])
def test_formation_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)

