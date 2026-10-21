// Lineups and depth in one view (Phase 19, owner 2026-10-08: "combine the line-up and the depth chart", "visualize offense vs
// defense for each team as far as the roster goes"; owner 2026-10-10: "the opposite player should be on the other team and
// aligned: offensive tackle against edge defender, center against nose tackle, WR against cornerback, RB against linebacker").
// The same notes chart feeds everything: the starter at every slot. Each matchup is ONE table with a row per pairing: our
// starter on the left, the man he faces on the right, matched by the slot map below (our offense against their defense, then
// our defense against their offense, then the specialists slot for slot). A starter's cell is his name and his class; the men
// behind him are no longer drawn (the Pre-Game Program from the mock, owner 2026-10-20: "Keep the Experience of the starters
// ... Remove the depth portion"), so the table never scrolls. It sizes itself (ui/sizes.js): large with numbers and season
// chips, medium without them, small with the slot and the name only (still the button to his card). The starters' names step
// down with the table (item 6, owner 2026-10-11: full, "K. Crawford", the surname, the reduced surname; a notes name shortens
// only when it reads cleanly as First Last). Above the matchups, how experienced each unit's starters are, the table the
// band's whole width. Tables only (design rule 12).
//
//   lineupBlock({ lineups, us, them, availability, coaches, schemes, onPlayer })   the experience table, the formation (ui/formation.js)
//       and the matchup tables, or the empty note
//   experienceBlock({ lineups, us, them })                       the starters' experience by unit, or null when no chart
//   pairSlots(offense, defense) -> [{ off, def }]                the matchups by the slot map (exported for the tests)
//   (the names are ui/dom.js playerNames and personName, shared with every table of players; the availability report is
//   matched on the name as written, never a short form)
//   classNumber(label) -> 1..4 | null                            "FR" 1 ... "SR" 4; "RS SO" 2; "GR" 4 (fifth year is a senior)

import { usSchool } from "../identity.js";
import { DASH, el, isNum, obj, personName, str, text } from "./dom.js";
import { note, subhead } from "./states.js";
import { statTable } from "./stat-table.js";
import { availabilityFor, hasLineups, lineupSlots, lineupStarters } from "./lineups.js";
import { formationBlock } from "./formation.js";
import { plainChip } from "./stat-labels.js";

const CLASS_NUMBERS = { FR: 1, SO: 2, JR: 3, SR: 4, GR: 4 };
const STATUS_CLASS = { out: "out", doubtful: "doubtful", questionable: "questionable", probable: "probable", available: "available" };

// The slot map: an offensive slot and the defensive slots it faces, best first. A chart's own words vary (DE or RDE or
// JACK, NT or NG, NB or STAR), so each entry lists the families it accepts; the first unused match on the other chart wins.
const FACES = [
  ["LT", ["RDE", "RE", "JACK", "EDGE", "DE", "RUSH", "OLB"]],
  ["RT", ["LDE", "LE", "JACK", "EDGE", "DE", "RUSH", "OLB"]],
  ["LG", ["RDT", "DT", "NT", "NG", "DL"]],
  ["RG", ["LDT", "DT", "NT", "NG", "DL"]],
  ["C", ["NT", "NG", "DT", "LDT", "RDT", "DL"]],
  ["TE", ["SLB", "SAM", "SS", "OLB", "LB", "S"]],
  ["WRX", ["RCB", "CB", "LCB"]],
  ["WRZ", ["LCB", "CB", "RCB"]],
  ["WRSL", ["NB", "NICKEL", "STAR", "SCB", "CB", "S"]],
  ["WRSLOT", ["NB", "NICKEL", "STAR", "SCB", "CB", "S"]],
  ["WRH", ["NB", "NICKEL", "STAR", "SCB", "CB"]],
  ["WR", ["CB", "RCB", "LCB", "NB"]],
  ["RB", ["MLB", "MIKE", "ILB", "WLB", "WILL", "LB"]],
  ["HB", ["MLB", "MIKE", "ILB", "WLB", "WILL", "LB"]],
  ["FB", ["WLB", "WILL", "LB", "SS"]],
  ["QB", ["FS", "S", "SAF", "SS"]],
];

function key(slot) {
  return String(slot || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

/** The families an offensive slot faces: an exact entry, else the entry whose key begins the slot's ("WR-X" -> WRX, "WR3" -> WR). */
function facesOf(slot) {
  const k = key(slot);
  const exact = FACES.find(([s]) => s === k);
  if (exact) return exact[1];
  const family = FACES.filter(([s]) => k.startsWith(s)).sort((a, b) => b[0].length - a[0].length)[0];
  return family ? family[1] : [];
}

/** Whether a defensive slot belongs to a family ("RDE" is RDE and DE; "LCB" is LCB and CB; "SS" is SS and S). */
function inFamily(slot, family) {
  const k = key(slot);
  if (k === family) return true;
  if (family.length <= 2) return k.endsWith(family) && k.length <= family.length + 1; // DE: LDE, RDE; CB: LCB, RCB; S: FS, SS
  return k.replace(/^[LR]/, "") === family || k.startsWith(family);
}

/**
 * Pair an offense's slots with a defense's: each offensive slot takes the first unused defensive slot in its families,
 * in the offense's own order; defensive slots nobody faces follow with no offense beside them. A slot with no match on
 * the other chart keeps its row with a dash on that side, never a wrong name.
 */
export function pairSlots(offense, defense) {
  const off = (Array.isArray(offense) ? offense : []).filter((s) => s && typeof s === "object");
  const def = (Array.isArray(defense) ? defense : []).filter((s) => s && typeof s === "object");
  const used = new Set();
  const rows = off.map((o) => {
    let match = null;
    for (const family of facesOf(o.slot)) {
      match = def.find((d) => !used.has(d) && inFamily(d.slot, family)) || null;
      if (match) break;
    }
    if (match) used.add(match);
    return { off: o, def: match };
  });
  for (const d of def) if (!used.has(d)) rows.push({ off: null, def: d });
  return rows;
}

/** Specialists slot for slot (PK with PK, P with P): the same word on both charts, the rest with a dash. */
function pairSame(ours, theirs) {
  const a = (Array.isArray(ours) ? ours : []).filter((s) => s && typeof s === "object");
  const b = (Array.isArray(theirs) ? theirs : []).filter((s) => s && typeof s === "object");
  const used = new Set();
  const rows = a.map((s) => {
    const match = b.find((t) => !used.has(t) && key(t.slot) === key(s.slot)) || null;
    if (match) used.add(match);
    return { off: s, def: match };
  });
  for (const t of b) if (!used.has(t)) rows.push({ off: null, def: t });
  return rows;
}

export function classNumber(label) {
  const word = String(label || "").toUpperCase().replace(/^RS\s+/, "").replace(/[^A-Z]/g, "");
  return CLASS_NUMBERS[word] ?? null;
}

function who(team, fallback) {
  return str(obj(team).abbreviation) || str(obj(team).school) || fallback;
}

/** One side of a row: the starter and his listing on the availability report. */
function sideOf(slot, availability, owner) {
  if (!slot) return null;
  const starter = slot.players[0];
  const listed = availabilityFor(availability, starter.name);
  return {
    slot: str(slot.slot) || DASH,
    number: isNum(starter.number) ? starter.number : null,
    name: text(starter.name),
    classYear: str(starter.classYear) || "",
    chips: Array.isArray(starter.chips) ? starter.chips : [],
    playerId: str(starter.playerId),
    player: starter,
    note: str(starter.note),
    listed,
    isUs: owner === "us",
  };
}

/** The starter's name in its four forms (item 6), a button that opens his card when the chart matched him to a player. */
function starterName(side, onPlayer) {
  const name = personName(side.name, { notes: true });
  return side.playerId && typeof onPlayer === "function" ? el("button", { class: "lu-name", type: "button", onclick: () => onPlayer(side) }, name) : el("b", {}, name);
}

/** The starter's cell: his name (a tap opens his card), his class and status; a dash where the chart has no slot. */
function whoCell(side, onPlayer) {
  if (!side) return DASH;
  const name = starterName(side, onPlayer);
  const status = side.listed ? str(side.listed.status) || "Listed" : null;
  const cls = status ? STATUS_CLASS[status.toLowerCase()] : null;
  return el(
    "span",
    { class: "lu-who" },
    name,
    el("small", {}, side.classYear || DASH, status ? [" · ", el("span", { class: `avail${cls ? ` avail--${cls}` : ""}` }, status), str(side.listed.note) ? ` (${side.listed.note})` : ""] : str(side.note) ? ` · ${side.note}` : null), // the chart's own note when the report says nothing (freeze wave F4)
  );
}

/** The starter at small: the name alone, still the button to his card (the slot beside it says where he plays). */
function whoShort(side, onPlayer) {
  return side ? starterName(side, onPlayer) : DASH;
}

function chipsCell(side) {
  if (!side) return DASH;
  const chips = side.chips.map(plainChip).filter(Boolean);
  return chips.length ? el("div", { class: "chips lineup__chips" }, chips.map((chip) => el("span", { class: "chip" }, chip))) : DASH;
}

/** One matchup table: left side first, the man he faces on the right; it sizes itself, never scrolls. */
function matchupTable(pairs, { leftOwner, rightOwner, availability, onPlayer, caption }) {
  const rows = pairs.map((p) => {
    const a = sideOf(p.off, availability, leftOwner);
    const b = sideOf(p.def, availability, rightOwner);
    return {
      a,
      b,
      slotA: a ? a.slot : DASH,
      numA: a ? a.number : null,
      whoA: a ? a.name : DASH,
      slotB: b ? b.slot : DASH,
      numB: b ? b.number : null,
      whoB: b ? b.name : DASH,
    };
  });
  const columns = [
    { key: "slotA", label: "Slot", kind: "text" },
    { key: "numA", label: "No.", size: "large" },
    { key: "whoA", label: "Starter", kind: "text", person: { notes: true }, render: (row) => whoCell(row.a, onPlayer), renderShort: (row) => whoShort(row.a, onPlayer) },
    { key: "chipsA", label: "Season", kind: "text", render: (row) => chipsCell(row.a), size: "large", wrap: true },
    { key: "vs", label: "", kind: "text", render: () => el("span", { class: "lu-vs", "aria-label": "faces" }, "⟷") }, // no head word: the arrow in every row says it
    { key: "slotB", label: "Slot", kind: "text" },
    { key: "numB", label: "No.", size: "large" },
    { key: "whoB", label: "Starter", kind: "text", person: { notes: true }, render: (row) => whoCell(row.b, onPlayer), renderShort: (row) => whoShort(row.b, onPlayer) },
    { key: "chipsB", label: "Season", kind: "text", render: (row) => chipsCell(row.b), size: "large", wrap: true },
  ];
  return statTable({ compact: true, sortable: false, sizes: true, columns, rows, caption, rowClass: (row) => (row.a?.playerId || row.b?.playerId ? null : "is-static") });
}

/** The matchup's title over its table: "Swampwater Tech offense vs Diner Tech defense", each school its link. */
/** A matchup's head: each unit's name, and under it (freeze wave F4) its coordinator and its scheme from the notes. */
function matchupHead(left, right, leftOwner) {
  const detail = (side) => (str(side.detail) ? el("small", { class: "lu-head__detail" }, side.detail) : null);
  return el(
    "h3",
    { class: "subhead lu-head" },
    el("span", { class: "lu-head__side" }, subhead(left.name, { team: left.school, side: leftOwner, level: 4 }), detail(left)),
    el("span", { class: "lu-head__vs" }, " vs "),
    el("span", { class: "lu-head__side" }, subhead(right.name, { team: right.school, side: leftOwner === "us" ? "them" : "us", level: 4 }), detail(right)),
  );
}

/** "OC Name · Spread" for a unit: its coordinator from the coaches block and its scheme from the schemes block (or the chart's own heading). */
function unitDetail(unit, side, coaches, schemes, lineup) {
  const c = obj(obj(coaches)[side]);
  const s = side === "us" ? obj(schemes) : obj(obj(schemes).opponent);
  const coach = unit === "offense" ? str(c.offensiveCoordinator) : unit === "defense" ? str(c.defensiveCoordinator) : null;
  const scheme = unit === "offense" ? str(s.offense) : unit === "defense" ? str(s.defense) : null;
  return [coach ? `${unit === "offense" ? "OC" : "DC"} ${coach}` : null, scheme || (unit !== "special" ? str(obj(lineup).scheme) : null)].filter(Boolean).join(" · ") || null;
}

export function lineupBlock({ lineups, us, them, availability, coaches = null, schemes = null, onPlayer } = {}) {
  const l = obj(lineups);
  if (!hasLineups(l)) return note("No lineups for this game yet. They come with the game's notes: both teams' published depth charts.");
  const usName = str(obj(us).school) || usSchool();
  const themName = str(obj(them).school) || str(obj(l.them).team) || "Opponent";
  const slotsOf = (side, unit) => lineupSlots(side === "us" ? l.us : l.them).filter((s) => s.unit === unit && s.players.length);
  const detailOf = (unit, side) => unitDetail(unit, side, coaches, schemes, side === "us" ? l.us : l.them);
  const tables = [];
  const push = (title, pairs, leftOwner, rightOwner, caption) => {
    if (!pairs.length) return;
    tables.push(el("div", { class: "lineups__matchup" }, title, matchupTable(pairs, { leftOwner, rightOwner, availability, onPlayer, caption })));
  };
  push(matchupHead({ name: `${usName} offense`, school: usName, detail: detailOf("offense", "us") }, { name: `${themName} defense`, school: themName, detail: detailOf("defense", "them") }, "us"), pairSlots(slotsOf("us", "offense"), slotsOf("them", "defense")), "us", "them", `${usName} offense against ${themName} defense`);
  // our defense first on its table, the opposing offense beside it: the same map, read from the other side
  const theirs = pairSlots(slotsOf("them", "offense"), slotsOf("us", "defense")).map((p) => ({ off: p.def, def: p.off }));
  push(matchupHead({ name: `${usName} defense`, school: usName, detail: detailOf("defense", "us") }, { name: `${themName} offense`, school: themName, detail: detailOf("offense", "them") }, "us"), theirs, "us", "them", `${usName} defense against ${themName} offense`);
  push(matchupHead({ name: `${usName} special teams`, school: usName }, { name: `${themName} special teams`, school: themName }, "us"), pairSame(slotsOf("us", "special teams"), slotsOf("them", "special teams")), "us", "them", `${usName} and ${themName} specialists`);
  if (!tables.length) return note("No chart written for either team yet.");
  // the formation mock (owner 2026-10-20): both matchups on a field between the experience table and the matchup tables
  return el("div", { class: "lineups" }, experienceBlock({ lineups: l, us, them }), formationBlock({ lineups: l, us, them, schemes, availability, detail: detailOf, onPlayer }), tables);
}

/** How experienced each unit's starters are, one row per team and unit; null when no chart names a starter's class. */
export function experienceBlock({ lineups, us, them } = {}) {
  const l = obj(lineups);
  const rows = [];
  for (const [owner, team, fallback] of [["us", us, usSchool()], ["them", them, "Opponent"]]) {
    for (const unit of ["offense", "defense"]) {
      const starters = lineupStarters(owner === "us" ? l.us : l.them).filter((s) => s.unit === unit);
      const classes = starters.map((s) => classNumber(s.player.classYear)).filter(isNum);
      if (!classes.length) continue;
      const count = (n) => classes.filter((c) => c === n).length;
      rows.push({ unit: `${who(team, fallback)} ${unit}`, starters: classes.length, fr: count(1), so: count(2), jr: count(3), sr: count(4), avg: classes.reduce((a, b) => a + b, 0) / classes.length, owner });
    }
  }
  if (!rows.length) return null;
  const table = statTable({
    compact: true,
    sortable: false,
    sizes: true, // small keeps the unit and the four classes; the count and the average return from medium
    columns: [
      { key: "unit", label: "Unit", kind: "text" },
      { key: "starters", label: "Starters", size: "medium" },
      { key: "fr", label: "FR" },
      { key: "so", label: "SO" },
      { key: "jr", label: "JR" },
      { key: "sr", label: "SR" },
      { key: "avg", label: "Avg class", labelShort: "Avg", format: "1f", size: "medium" },
    ],
    rows,
    caption: "Experience of the starters (1 = freshman, 4 = senior)",
    rowClass: (row) => (row.owner === "us" ? "is-us" : null),
  });
  return el("div", { class: "lineups__experience" }, subhead("Experience of the starters"), table);
}
