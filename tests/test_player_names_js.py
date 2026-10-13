"""Item 6, player names (owner 2026-10-11: "K. Crawford" when there is no room; "One line only, reduce the name"; a second letter
for two who would read alike): the one helper in ui/dom.js (playerNames, distinctNames, personName, settleNames, nameSteps,
fitNames), the whole-table ladder (ui/sizes.js personSteps and applyNames, a statTable person column, the two-team kit's
player column) measured in the fake browser with a scripted layout, the cards fitted one name at a time, and the tables and
cards that moved onto it. Every name here is made up."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const NB = "\u00A0";
const sp = (s) => String(s).replace(/\u00A0/g, " ");
const four = (f) => [f.full, f.initial, f.last, f.reduced].map(sp);

scenarios.helper = async () => {
  const { playerNames } = await import(moduleUrl("ui/dom.js"));
  const f = (n, o) => four(playerNames(n, o));
  // the forms, and "J." + a no-break space + the surname (owner answer 5: with a space that never breaks a line)
  assert.deepEqual(f("Thaddeus Quillfeather-Brannock"), ["Thaddeus Quillfeather-Brannock", "T. Quillfeather-Brannock", "Quillfeather-Brannock", "Quillfeather-B."]);
  assert.equal(playerNames("Thaddeus Quillfeather").initial, `T.${NB}Quillfeather`);
  assert.equal(playerNames("Thaddeus Quillfeather").first, "Thaddeus");
  // suffixes, every spelling, with and without a comma: they stay in full and leave the short forms
  for (const tail of ["Jr.", "Jr", "JR", "jr.", "Sr.", "Sr", "II", "III", "IV", "V", "VI", "Ii", "ll"]) {
    for (const name of [`Bartholomew Pennywhistle ${tail}`, `Bartholomew Pennywhistle, ${tail}`, `Bartholomew Pennywhistle , ${tail}`]) {
      assert.deepEqual(f(name), [name, "B. Pennywhistle", "Pennywhistle", "Pennywhistle"], name);
    }
  }
  assert.deepEqual(f("Demetrius Okonkwo-Brightwater II"), ["Demetrius Okonkwo-Brightwater II", "D. Okonkwo-Brightwater", "Okonkwo-Brightwater", "Okonkwo-B."]);
  // the surname keeps its particles, read leftward from the last word; never the first word; not Al or El
  for (const p of ["van", "von", "vander", "vanden", "de", "del", "della", "dela", "der", "den", "du", "da", "di", "dos", "das", "la", "le", "St.", "St", "Saint", "ter", "ten", "Van", "De", "LA"]) {
    assert.deepEqual(f(`Lorenzo ${p} Fontaine`).slice(1, 3), [`L. ${p} Fontaine`, `${p} Fontaine`], p);
  }
  assert.deepEqual(f("Lorenzo de la Fontaine").slice(1, 3), ["L. de la Fontaine", "de la Fontaine"]);
  assert.deepEqual(f("Ignatius von der Hollenbeck III").slice(1, 4), ["I. von der Hollenbeck", "von der Hollenbeck", "von der Hollenbeck"]);
  assert.deepEqual(f("Cornelius St. Ambrose-Whitfield").slice(1, 4), ["C. St. Ambrose-Whitfield", "St. Ambrose-Whitfield", "St. Ambrose-W."]);
  assert.deepEqual(f("De Fontaine").slice(1, 3), ["D. Fontaine", "Fontaine"], "a particle that is the first name stays the first name");
  assert.deepEqual(f("Van De Fontaine").slice(1, 3), ["V. De Fontaine", "De Fontaine"], "never the first word");
  assert.deepEqual(f("Big Al Hollenbeck").slice(1, 3), ["B. Hollenbeck", "Hollenbeck"], "Al is a name, not a particle");
  assert.deepEqual(f("Marcus El Fontaine").slice(1, 3), ["M. Fontaine", "Fontaine"], "nor El");
  // a first name written as initials stays whole; one bare letter gains its dot
  for (const [name, initial] of [["AJ Fernwhistle", "AJ Fernwhistle"], ["A.J. Fernwhistle", "A.J. Fernwhistle"], ["TJ Fernwhistle", "TJ Fernwhistle"], ["A.J Fernwhistle", "A.J Fernwhistle"], ["A.C. Fernwhistle", "A.C. Fernwhistle"], ["J. Fernwhistle", "J. Fernwhistle"], ["Q Fernwhistle", "Q. Fernwhistle"]]) {
    assert.equal(sp(playerNames(name).initial), initial, name);
    assert.equal(playerNames(name).last, "Fernwhistle", name);
  }
  // hyphenated and apostrophe first names give their first letter; a hyphenated surname reduces; three parts too
  assert.equal(sp(playerNames("Jean-Luc Fernwhistle").initial), "J. Fernwhistle");
  assert.equal(sp(playerNames("Ja'Quarius Bramblethorne").initial), "J. Bramblethorne");
  assert.equal(sp(playerNames("a'mari bramblethorne").initial), "A. bramblethorne");
  assert.deepEqual(f("D'Andre O'Malley-Fitch").slice(1), ["D. O'Malley-Fitch", "O'Malley-Fitch", "O'Malley-F."]);
  assert.equal(playerNames("Thaddeus Quill-Feather-Brannock").reduced, "Quill-F.");
  assert.equal(playerNames("Thaddeus Quill-").reduced, "Quill-", "no letter after the hyphen: the surname as it is");
  // one word is the same in every form; whitespace collapses; nothing is a dash
  assert.deepEqual(f("Featherstonehaughton"), Array(4).fill("Featherstonehaughton"));
  assert.deepEqual(f("Featherstonehaughton Jr."), ["Featherstonehaughton Jr.", "Featherstonehaughton", "Featherstonehaughton", "Featherstonehaughton"]);
  assert.deepEqual(f("  Thaddeus \t  Quillfeather  "), ["Thaddeus Quillfeather", "T. Quillfeather", "Quillfeather", "Quillfeather"]);
  for (const junk of [null, undefined, 7, NaN, true, {}, [], "", "   ", "[object Object]", { name: 5 }, { firstName: {}, lastName: [] }]) assert.deepEqual(f(junk), Array(4).fill("–"), JSON.stringify(junk));
  // CFBD's split wins when both halves are there: a two-word surname with no particle stays whole, a suffix still leaves
  assert.deepEqual(f({ name: "Ambrose Kettle Pond", firstName: "Ambrose", lastName: "Kettle Pond" }).slice(1, 3), ["A. Kettle Pond", "Kettle Pond"]);
  assert.deepEqual(f("Ambrose Kettle Pond").slice(1, 3), ["A. Pond", "Pond"], "without the split, the string rules");
  assert.deepEqual(f({ firstName: "Demetrius", lastName: "Okonkwo-Brightwater II" }), ["Demetrius Okonkwo-Brightwater II", "D. Okonkwo-Brightwater", "Okonkwo-Brightwater", "Okonkwo-B."]);
  assert.deepEqual(f({ firstName: "Favour Ebuka", lastName: "Fernwhistle" }).slice(1, 3), ["F. Fernwhistle", "Fernwhistle"]);
  assert.deepEqual(f({ name: "Cher" }), Array(4).fill("Cher"));
  assert.deepEqual(f({ firstName: "Cher" }), Array(4).fill("Cher"), "one half: the string rules");
  // a name from the notes (AI-written) shortens only when it reads cleanly as First [particles] Last [suffix]
  assert.deepEqual(f("Lorenzo de la Fontaine Jr.", { notes: true }), ["Lorenzo de la Fontaine Jr.", "L. de la Fontaine", "de la Fontaine", "de la Fontaine"]);
  assert.deepEqual(f("L. Fontaine", { notes: true }).slice(1, 3), ["L. Fontaine", "Fontaine"]);
  for (const odd of ["Fontaine (ankle)", "Fontaine, Lorenzo", "Mary Ann Fontaine", "Lorenzo Fontaine 2", "Lorenzo de", "LB Lorenzo/Fontaine"]) assert.deepEqual(f(odd, { notes: true }), Array(4).fill(odd), odd);
  assert.deepEqual(f({ name: "Ambrose Kettle Pond", firstName: "Ambrose", lastName: "Kettle Pond" }, { notes: true }), Array(4).fill("Ambrose Kettle Pond"), "notes never trust a split");
};

scenarios.collisions = async () => {
  const { playerNames, distinctNames } = await import(moduleUrl("ui/dom.js"));
  const settle = (...names) => distinctNames(names.map((n) => (typeof n === "string" ? playerNames(n) : n))).map((f) => (f ? four(f) : f));
  // owner answer 7: a second letter, and two who share a surname keep it at the surname steps
  assert.deepEqual(settle("Case Tumbleweed", "Cortez Tumbleweed"), [
    ["Case Tumbleweed", "Ca. Tumbleweed", "Ca. Tumbleweed", "Ca. Tumbleweed"],
    ["Cortez Tumbleweed", "Co. Tumbleweed", "Co. Tumbleweed", "Co. Tumbleweed"],
  ]);
  assert.equal(distinctNames([playerNames("Case Tumbleweed"), playerNames("Cortez Tumbleweed")])[0].initial, `Ca.${NB}Tumbleweed`);
  // two letters still alike: the whole first name; that still alike: the whole name
  assert.deepEqual(settle("Case Tumbleweed", "Cortez Tumbleweed", "Cole Tumbleweed").map((f) => f[1]), ["Ca. Tumbleweed", "Cortez Tumbleweed", "Cole Tumbleweed"]);
  assert.deepEqual(settle("Jakobi Bramble", "Ja'Keem Bramble").map((f) => f[1]), ["Jakobi Bramble", "Ja'Keem Bramble"]);
  assert.deepEqual(settle("John A Bramble", "John B Bramble").map((f) => f[1]), ["John A Bramble", "John B Bramble"]);
  // a shared surname alone: the initials differ already, the surname steps keep them
  assert.deepEqual(settle("Duke Marigold", "Alec Marigold", "Sam Thistle"), [
    ["Duke Marigold", "D. Marigold", "D. Marigold", "D. Marigold"],
    ["Alec Marigold", "A. Marigold", "A. Marigold", "A. Marigold"],
    ["Sam Thistle", "S. Thistle", "Thistle", "Thistle"],
  ]);
  assert.deepEqual(settle("AJ Fernwhistle", "Andrew Fernwhistle").map((f) => f.slice(1, 3)), [["AJ Fernwhistle", "AJ Fernwhistle"], ["A. Fernwhistle", "A. Fernwhistle"]], "initials as written never read like A.");
  // two reduced surnames alike keep their whole surnames; the same player twice is no clash; junk stays out
  assert.deepEqual(settle("Benedikt Brackwater-Matchley", "Benjamin Brackwater-Millbrook").map((f) => f.slice(1)), [["B. Brackwater-Matchley", "Brackwater-Matchley", "Brackwater-Matchley"], ["B. Brackwater-Millbrook", "Brackwater-Millbrook", "Brackwater-Millbrook"]]);
  assert.deepEqual(settle("Thaddeus Quillfeather-Brannock", "Thaddeus Quillfeather-Brannock", "thaddeus quillfeather-brannock").map((f) => f[3]), ["Quillfeather-B.", "Quillfeather-B.", "quillfeather-B."]);
  assert.deepEqual(settle(null, "x", playerNames(null), "Case Tumbleweed"), [null, ["x", "x", "x", "x"], ["–", "–", "–", "–"], ["Case Tumbleweed", "C. Tumbleweed", "Tumbleweed", "Tumbleweed"]]);
  assert.deepEqual(distinctNames("junk"), []);
  // the input is never changed in place
  const one = playerNames("Case Tumbleweed");
  distinctNames([one, playerNames("Cortez Tumbleweed")]);
  assert.equal(sp(one.initial), "C. Tumbleweed");
};

scenarios.drawing = async () => {
  const { personName, settleNames, nameSteps } = await import(moduleUrl("ui/dom.js"));
  const node = personName("Thaddeus Quillfeather-Brannock");
  assert.ok(node.className === "pn" && node.getAttribute("title") === "Thaddeus Quillfeather-Brannock");
  assert.equal(text(node.querySelector(".sr-only")), "Thaddeus Quillfeather-Brannock", "the full name for a screen reader");
  const spans = node.querySelectorAll(".pn__f");
  assert.deepEqual(spans.map((s) => s.className.replace("pn__f pn__f--", "")), ["full", "initial", "last", "reduced"]);
  assert.ok(spans.every((s) => s.getAttribute("aria-hidden") === "true"), "the shown forms stay out of a screen reader's way");
  assert.deepEqual(["full", "initial", "last", "reduced"].map((f) => pnText(node, f)), ["Thaddeus Quillfeather-Brannock", "T. Quillfeather-Brannock", "Quillfeather-Brannock", "Quillfeather-B."]);
  assert.equal(node.dataset.fit, undefined);
  // one word, or nothing: plain words, no forms; a real name keeps its title (the last step clips every name), a dash none
  const plain = personName("Featherstonehaughton");
  assert.ok(text(plain) === "Featherstonehaughton" && !plain.querySelector(".pn__f"));
  assert.equal(plain.getAttribute("title"), "Featherstonehaughton", "item 6 review: a clipped plain name can still be read in full");
  assert.equal(personName(null).getAttribute("title"), null);
  assert.equal(text(personName(null)), "–");
  assert.equal(text(personName({})), "–");
  // words kept after whichever form shows (the redshirt mark), a card's fitted name
  const rs = personName({ name: "Lorenzo de la Fontaine", firstName: "Lorenzo", lastName: "de la Fontaine" }, { after: " (RS)", fit: true });
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(rs, f)), ["Lorenzo de la Fontaine (RS)", "L. de la Fontaine (RS)", "de la Fontaine (RS)"]);
  assert.ok(rs.dataset.fit === "" && rs.getAttribute("title") === "Lorenzo de la Fontaine (RS)");
  assert.equal(text(personName("Mary Ann Fontaine", { notes: true })), "Mary Ann Fontaine", "a notes name that does not read cleanly stays whole");
  // settled within one set of cells: every name in a cell (a drawing and its small form) takes the settled forms
  const cell = (name) => { const td = document.createElement("td"); td.append(personName(name), personName(name)); return td; };
  const cells = [cell("Case Tumbleweed"), cell("Cortez Tumbleweed"), cell("Sam Thistle"), document.createElement("td"), null];
  settleNames(cells);
  assert.deepEqual(cells.slice(0, 3).map((td) => td.querySelectorAll(".pn").map((n) => pnText(n, "last"))), [["Ca. Tumbleweed", "Ca. Tumbleweed"], ["Co. Tumbleweed", "Co. Tumbleweed"], ["Thistle", "Thistle"]]);
  assert.equal(text(cells[0].querySelector(".sr-only")), "Case Tumbleweed", "the full name never changes");
  const host = document.createElement("div");
  host.append(...cells.slice(0, 3));
  assert.deepEqual(nameSteps(host), { any: true, initial: true, last: true, reduced: false });
  const words = document.createElement("div");
  words.append(personName("Cher"), personName("Featherstonehaughton"));
  assert.deepEqual(nameSteps(words), { any: true, initial: false, last: false, reduced: false });
  assert.deepEqual(nameSteps(null), { any: false, initial: false, last: false, reduced: false });
};

// A scripted layout: the table's width follows the wrap's size and name form, the clip's cut (--pn-max) included.
function layout(wrap, { base = { large: 300, medium: 220, small: 150 }, name = { full: 200, initial: 140, last: 100, reduced: 80 } } = {}) {
  const table = wrap.querySelector("table");
  const cut = () => { const m = parseFloat(wrap.style["--pn-max"]); return Number.isFinite(m) ? m : Infinity; };
  const nameWidth = () => { const form = wrap.dataset.pn || "full"; return form === "clip" ? Math.min(name.reduced, cut()) : name[form]; };
  Object.defineProperty(table, "offsetWidth", { configurable: true, get: () => base[wrap.dataset.size] + nameWidth() });
  for (const pn of wrap.querySelectorAll(".pn")) pn.getBoundingClientRect = () => ({ width: wrap.dataset.pn === "clip" ? Math.min(name.reduced, cut()) : nameWidth() });
  return (room) => {
    wrap.clientWidth = room;
    wrap.measure();
    return `${wrap.dataset.size}/${wrap.dataset.pn}${wrap.style["--pn-max"] ? ` ${wrap.style["--pn-max"]}` : ""}`;
  };
}

scenarios.ladder = async () => {
  const { statTable, applyStatSize } = await import(moduleUrl("ui/stat-table.js"));
  const { personSteps, splitStep } = await import(moduleUrl("ui/sizes.js"));
  // the steps: large with full names, large with K. Crawford, then medium and small with K. Crawford, the surname, the reduced
  // surname and the clip; a name step that changes nothing is skipped
  assert.deepEqual(personSteps(undefined, { any: true, initial: true, last: true, reduced: true }), ["large/full", "large/initial", "medium/initial", "small/initial", "small/last", "small/reduced", "small/clip"]);
  assert.deepEqual(personSteps(undefined, { any: true }), ["large/full", "medium/initial", "small/initial", "small/clip"], "one-word names: no name steps but the clip");
  assert.deepEqual(personSteps(["large", "medium", "medium:abbr", "small"], { any: true, initial: true, last: true }), ["large/full", "large/initial", "medium/initial", "medium:abbr/initial", "small/initial", "small/last", "small/clip"]);
  assert.deepEqual(personSteps(null, null), ["large/full", "medium/initial", "small/initial"]);
  assert.deepEqual([splitStep("small/last"), splitStep("medium:abbr/initial"), splitStep("large"), splitStep("small/nonsense"), splitStep(null)], [{ size: "small", form: "last" }, { size: "medium:abbr", form: "initial" }, { size: "large", form: null }, { size: "small", form: null }, { size: "large", form: null }]);
  const rows = [{ name: "Thaddeus Quillfeather-Brannock", YDS: 88 }, { name: "Case Tumbleweed", YDS: 61 }, { name: "Cortez Tumbleweed", YDS: 40 }, { name: "Sam Thistle", YDS: 12 }];
  const wrap = statTable({ sizes: true, columns: [{ key: "name", label: "Rushing", kind: "text", person: true }, { key: "YDS", label: "Yards" }], rows, sort: { key: "YDS", dir: "descending" } });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  assert.deepEqual([wrap.dataset.size, wrap.dataset.pn], ["large", "full"], "drawn at large with full names until measured");
  const fit = layout(wrap);
  // one table, one step: widths 500, 440, 360, 290, 250, 230, then the clip
  assert.equal(fit(600), "large/full");
  assert.equal(fit(450), "large/initial", "K. Crawford keeps the large table");
  assert.equal(fit(400), "medium/initial");
  assert.equal(fit(300), "small/initial");
  assert.equal(fit(260), "small/last");
  assert.equal(fit(240), "small/reduced");
  assert.equal(fit(200), "small/clip 51px", "the widest cut that fits");
  assert.equal(fit(150), "small/clip 48px", "nothing fits: the names at their narrowest, the minimal table");
  assert.equal(fit(600), "large/full", "room again: back to full names, no cut left over");
  // a wider head than its names: cutting them gains nothing, so no cut stays
  const headBound = statTable({ sizes: true, columns: [{ key: "name", label: "Rushing", kind: "text", person: true }], rows: [{ name: "Thaddeus Quillfeather-Brannock" }] });
  document.body.append(headBound);
  const fitHead = layout(headBound, { base: { large: 300, medium: 300, small: 300 } });
  Object.defineProperty(headBound.querySelector("table"), "offsetWidth", { configurable: true, get: () => 400 });
  assert.equal(fitHead(320), "small/clip");
  // the collision rules hold in the table, and again after a sort redraws it
  const names = () => wrap.querySelectorAll("tbody td.st__person").map((td) => [pnText(td, "initial"), pnText(td, "last")]);
  const want = [["T. Quillfeather-Brannock", "Quillfeather-Brannock"], ["Ca. Tumbleweed", "Ca. Tumbleweed"], ["Co. Tumbleweed", "Co. Tumbleweed"], ["S. Thistle", "Thistle"]];
  assert.deepEqual(names(), want);
  wrap.querySelectorAll("thead th")[0].querySelector("button").click();
  assert.deepEqual(names().map((n) => n[0]).sort(), want.map((n) => n[0]).sort(), "a sort redraws the names settled the same way");
  // a hand-applied size on a table of players: full names at large, K. Crawford below; a plain table never gets a name step
  applyStatSize(wrap, "medium");
  assert.deepEqual([wrap.dataset.size, wrap.dataset.pn], ["medium", "initial"]);
  applyStatSize(wrap, "large");
  assert.deepEqual([wrap.dataset.size, wrap.dataset.pn], ["large", "full"]);
  const plainTable = statTable({ sizes: true, columns: [{ key: "label", label: "Statistic", kind: "text" }, { key: "v", label: "Value" }], rows: [{ label: "Points per game", v: 3 }] });
  applyStatSize(plainTable, "small");
  assert.equal(plainTable.dataset.pn, undefined);
  // an unsized table still draws the four forms (full shows) and settles them
  const unsized = statTable({ columns: [{ key: "name", label: "Player", kind: "text", person: true }], rows: [{ name: "Case Tumbleweed" }, { name: "Cortez Tumbleweed" }] });
  assert.ok(unsized.querySelector("td .pn") && unsized.dataset.pn === undefined && pnText(unsized.querySelectorAll("td")[1], "initial") === "Co. Tumbleweed");
  // a person column with CFBD's split, the notes flag and words after the name; a throwing after() never breaks the table
  const split = statTable({ sizes: true, columns: [{ key: "name", label: "Player", kind: "text", person: { first: "firstName", last: "lastName", after: (r) => (r.redshirt ? " (RS)" : "") } }, { key: "note", label: "Note", kind: "text", person: { notes: true, after: () => { throw new Error("boom"); } } }], rows: [{ name: "Ambrose Kettle Pond", firstName: "Ambrose", lastName: "Kettle Pond", redshirt: true, note: "Fontaine (ankle)" }] });
  const cells = split.querySelectorAll("tbody td");
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(cells[0], f)), ["Ambrose Kettle Pond (RS)", "A. Kettle Pond (RS)", "Kettle Pond (RS)"]);
  assert.equal(text(cells[1]), "Fontaine (ankle)");
  assert.ok(!RAW.test(text(split)));
};

scenarios.twoTeam = async () => {
  const { twoTeamTable, applySize } = await import(moduleUrl("ui/two-team.js"));
  const side = (who, value) => ({ value, who });
  const rows = [
    { label: "1", higherIsBetter: true, us: side("Case Tumbleweed", 90), them: side("Case Tumbleweed", 80) },
    { label: "2", higherIsBetter: true, us: side("Cortez Tumbleweed", 70), them: side("Thaddeus Quillfeather-Brannock", 60) },
  ];
  const wrap = twoTeamTable({ rows, usAbbr: "SWT", themAbbr: "DT", usTeam: "Swampwater Tech", themTeam: "Diner Tech", centered: true, labelHead: "#" });
  document.body.append(wrap);
  assert.ok(!RAW.test(text(wrap)), text(wrap));
  // compared within each side: ours read Ca./Co., theirs keep C. (no Cortez on their side)
  const us = wrap.querySelectorAll("td.tt__who--us").map((td) => pnText(td, "initial"));
  const them = wrap.querySelectorAll("td.tt__who--them").map((td) => pnText(td, "initial"));
  assert.deepEqual(us, ["Ca. Tumbleweed", "Co. Tumbleweed"]);
  assert.deepEqual(them, ["C. Tumbleweed", "T. Quillfeather-Brannock"]);
  assert.deepEqual([wrap.dataset.size, wrap.dataset.pn], ["large", "full"]);
  applySize(wrap, "medium:abbr/initial");
  assert.deepEqual([wrap.dataset.size, wrap.dataset.names, wrap.dataset.pn], ["medium", "short", "initial"]);
  // the ladder through the kit's own steps, with the team-abbreviation step kept
  const table = wrap.querySelector("table");
  const base = { large: 400, medium: 320, small: 220 };
  const name = { full: 200, initial: 150, last: 120, reduced: 100 };
  Object.defineProperty(table, "offsetWidth", { configurable: true, get: () => base[wrap.dataset.size] - (wrap.dataset.names === "short" ? 30 : 0) + name[wrap.dataset.pn === "clip" ? "reduced" : wrap.dataset.pn || "full"] });
  const at = (room) => { wrap.clientWidth = room; wrap.measure(); return `${wrap.dataset.size}${wrap.dataset.names ? ":abbr" : ""}/${wrap.dataset.pn}`; };
  assert.equal(at(700), "large/full");
  assert.equal(at(560), "large/initial");
  assert.equal(at(470), "medium/initial");
  assert.equal(at(445), "medium:abbr/initial", "the schools shorten before the size drops");
  assert.equal(at(370), "small/initial");
  assert.equal(at(330), "small/reduced");
  // a drawn who (a face beside the name) keeps its drawing at large and medium and the name alone at small
  const face = (n) => { const s = document.createElement("span"); s.className = "leader-who"; s.append("face ", personNameOf(n)); return s; };
  const { personName } = await import(moduleUrl("ui/dom.js"));
  const personNameOf = (n) => personName(n);
  const drawn = twoTeamTable({ rows: [{ label: "1", us: { value: 1, who: face("Case Tumbleweed"), whoName: "Case Tumbleweed", onWho: () => {} }, them: { value: 2, who: face("Cortez Tumbleweed"), whoName: "Cortez Tumbleweed" } }], usAbbr: "SWT", themAbbr: "DT", centered: true });
  const ours = drawn.querySelector("td.tt__who--us");
  assert.ok(ours.querySelector(".tt__t--long .leader-who .pn") && ours.querySelector(".tt__t--short .pn") && !ours.querySelector(".tt__t--short .leader-who"));
  assert.equal(ours.querySelector("button").getAttribute("title"), "Open Case Tumbleweed's card");
};

scenarios.cards = async () => {
  const { fitNames, personName, watchNames } = await import(moduleUrl("ui/dom.js"));
  // each name in its own box: full, then K. Crawford, the surname, the reduced surname; the box's ellipsis after that
  const widths = { full: 160, initial: 120, last: 90, reduced: 70 };
  const boxOf = (room) => {
    const box = document.createElement("div");
    const pn = personName("Thaddeus Quillfeather-Brannock", { fit: true });
    box.append(pn);
    box.clientWidth = room;
    Object.defineProperty(box, "scrollWidth", { get: () => widths[pn.dataset.pn || "full"] });
    return box;
  };
  const root = document.createElement("div");
  const boxes = [200, 130, 100, 75, 40].map(boxOf);
  root.append(...boxes);
  fitNames(root);
  assert.deepEqual(boxes.map((b) => b.querySelector(".pn").dataset.pn), ["full", "initial", "last", "reduced", "reduced"], "the narrowest box ends at the reduced form (its ellipsis)");
  boxes.forEach((b) => { b.clientWidth = 500; });
  fitNames(root);
  assert.ok(boxes.every((b) => b.querySelector(".pn").dataset.pn === "full"), "wider again: full names");
  // no layout engine: nothing is set, nothing scheduled
  const loose = document.createElement("div");
  loose.append(personName("Case Tumbleweed", { fit: true }));
  fitNames(loose);
  assert.equal(watchNames(loose), loose);
  assert.equal(loose.querySelector(".pn").dataset.pn, undefined);
  // the leader cards: fitted names, settled within each side
  const { leadersGrid } = await import(moduleUrl("ui/leaders.js"));
  const grid = leadersGrid({ categories: [{ id: "passing", label: "Passing", us: { name: "Case Tumbleweed", line: "1 yds" }, them: { name: "Case Tumbleweed", line: "2 yds" } }, { id: "rushing", label: "Rushing", us: { name: "Cortez Tumbleweed", line: "3 yds" }, them: null }], usAbbr: "SWT", themAbbr: "DT" });
  assert.ok(!RAW.test(text(grid)), text(grid));
  assert.deepEqual(grid.querySelectorAll(".leader--us .leader__name .pn[data-fit]").map((n) => pnText(n, "initial")), ["Ca. Tumbleweed", "Co. Tumbleweed"]);
  assert.deepEqual(grid.querySelectorAll(".leader--them .leader__name .pn").map((n) => pnText(n, "initial")), ["C. Tumbleweed"]);
  // the impact cards: the position, then the fitted name
  const { impactCard } = await import(moduleUrl("ui/team-page.js"));
  const impact = impactCard({ player: { name: "Lorenzo de la Fontaine", position: "WR", classYear: "SO" }, chips: ["5 rec"] });
  assert.ok(impact.querySelector(".impact__name .pn[data-fit]") && text(impact.querySelector(".impact__name")).startsWith("WR "));
  assert.deepEqual(["last", "reduced"].map((f) => pnText(impact.querySelector(".impact__name"), f)), ["de la Fontaine", "de la Fontaine"]);
};

scenarios.roster = async () => {
  // the Roster page: its table and the depth cards from CFBD's split, "(RS)" after whichever form shows
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  const player = (over) => ({ playerId: "r1", number: 12, team: "Swampwater Tech", position: "QB", classYear: "JR", isUs: true, rating: 0.9, ...over });
  route("/api/roster", () => envelope({
    season: 2026, team: { school: "Swampwater Tech" },
    players: [
      player({ name: "Ambrose Kettle Pond", firstName: "Ambrose", lastName: "Kettle Pond", redshirt: true }),
      player({ playerId: "r2", number: 9, name: "Case Tumbleweed", firstName: "Case", lastName: "Tumbleweed" }),
      player({ playerId: "r3", number: 7, name: "Cortez Tumbleweed", firstName: "Cortez", lastName: "Tumbleweed" }),
    ],
    starCounts: {}, parts: {},
  }));
  const { createRosterView } = await import(moduleUrl("views/roster.js"));
  const main = document.createElement("main");
  document.body.replaceChildren(main);
  createRosterView({}).mount(main);
  await settle();
  assert.ok(!RAW.test(text(main)), text(main).slice(0, 400));
  const table = main.querySelector("#roster-table .stat-table-wrap");
  const cell = table.querySelectorAll("tbody tr").map((tr) => tr.querySelector("td.st__person")).find((td) => pnText(td).startsWith("Ambrose"));
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(cell, f)), ["Ambrose Kettle Pond (RS)", "A. Kettle Pond (RS)", "Kettle Pond (RS)"]);
  const qbCard = main.querySelectorAll(".depth-card").find((c) => text(c.querySelector("h3")) === "QB");
  const cardNames = qbCard.querySelectorAll(".depth-row__name .pn[data-fit]");
  assert.equal(cardNames.length, 3, "every depth row's name is fitted in its row");
  const byFull = Object.fromEntries(cardNames.map((n) => [pnText(n), [pnText(n, "initial"), pnText(n, "last")]]));
  assert.deepEqual(byFull["Ambrose Kettle Pond (RS)"], ["A. Kettle Pond (RS)", "Kettle Pond (RS)"]);
  assert.deepEqual(byFull["Case Tumbleweed"], ["Ca. Tumbleweed", "Ca. Tumbleweed"], "two on one card who would read alike: a second letter, never the shared surname alone");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["helper", "collisions", "drawing", "ladder", "twoTeam", "cards", "roster"])
def test_player_names_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_names_never_wrap_and_one_form_shows() -> None:
    """The stylesheet: a name is one line (never broken at its hyphen), one form shows per step, the clip cuts with an
    ellipsis at the measured width, the Lineups band never takes the experience table's width (N11)."""
    css = (STATIC / "css" / "components.css").read_text(encoding="utf-8")
    assert ".pn { white-space: nowrap; }" in css
    assert ".pn__f { display: none; }" in css and ".pn__f--full { display: inline; }" in css
    for form in ("full", "initial", "last", "reduced"):
        assert f'[data-pn="{form}"] .pn__f--{form}' in css and f'.pn[data-pn="{form}"] > .pn__f--{form}' in css
    assert '[data-pn="clip"] .pn__f--reduced' in css
    assert re.search(r'\[data-pn="clip"\] \.pn \{[^}]*max-width: var\(--pn-max, none\);[^}]*text-overflow: ellipsis;', css)
    assert ".lineups { display: grid; grid-template-columns: minmax(0, 1fr);" in css
    assert ".lu-who .lu-next { white-space: nowrap; }" in css
    assert "hyphens:" not in css, "a name never breaks at a hyphen the browser adds either"


def test_every_player_table_is_a_person_column() -> None:
    """No table keeps its own short-name plumbing: the old helpers are gone and each player column declares person."""
    js = STATIC / "js"
    source = "\n".join(p.read_text(encoding="utf-8") for p in js.rglob("*.js"))
    for gone in ("export function shortName", "export function midName", "function chipNames(p) {", "nameShort", "nameMid", "playerShort", "whoAShort"):
        assert gone not in source, gone
    wants = {
        "ui/box-columns.js": "person: true",
        "ui/editorial.js": "person: { notes: true }",
        "ui/depth2.js": "person: true",
        "ui/in-game-tables.js": "person: { notes: true }",
        "views/recruiting.js": "person: { notes: true }",
        "views/leaders.js": "person: true",
        "ui/national-sheet.js": "person: true",
        "views/team.js": 'person: { first: "firstName", last: "lastName"',
        "views/roster.js": 'person: { first: "firstName", last: "lastName"',
        "ui/roster-costs.js": "person: { notes: true }",
        "ui/grade.js": "person: true",
        "ui/play-value.js": "person: true",
        "ui/lineups_combined.js": "person: { notes: true }, render: (row) => whoCell(row.a, onPlayer), renderShort",
    }
    for rel, needle in wants.items():
        assert needle in (js / rel).read_text(encoding="utf-8"), rel
    assert "watchNames(" in (js / "ui" / "leaders.js").read_text(encoding="utf-8")
    assert "watchNames(" in (js / "views" / "roster.js").read_text(encoding="utf-8")


def test_item6_review_fixes_stay_in_place() -> None:
    """The item 6 review's fixes: the player card's head steps its name down on one line, one shared fonts hook for every
    card (a hook per call kept every replaced In Game leaders grid alive), the top bar's Search reuses an open Search, and
    Back that closes a sheet closes a stat hint card with it."""
    js = ROOT / "static" / "js"
    dom = (js / "ui" / "dom.js").read_text(encoding="utf-8")
    assert "let namesFontsHooked = false;" in dom and 'removeEventListener("loadingdone"' not in dom
    card = (js / "ui" / "player-card.js").read_text(encoding="utf-8")
    assert 'watchNames(el("div", { class: "player-card__name" }' in card and "personName(p, { fit: true })" in card
    css = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
    assert ".player-card__name {" in css and "white-space: nowrap; overflow: hidden; text-overflow: ellipsis" in css.split(".player-card__name {", 1)[1].split("}", 1)[0]
    app = (js / "app.js").read_text(encoding="utf-8")
    assert 'document.querySelector(".sheet-layer[data-modal] .search__input")' in app.split("onSearch:", 1)[1].split("menu:", 1)[0]
    hints = (js / "ui" / "hints.js").read_text(encoding="utf-8")
    assert 'window.addEventListener("popstate", close)' in hints
