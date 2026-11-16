// The lineup as a picture (the owner's marks on the Lineups board, 2026-11-01:
// "This should only be the picture"; "Dont need stats on the page"; "Size and weight is good"; "just have the grade"; "I
// also want the impact players to be circled"). Both units on one field, the defense up
// top, the offense at the bottom, the line of scrimmage between them, each half labeled with the team, its scheme and its
// coordinator. Each starter stands at the spot his slot takes in the scheme's base look (the formation mock, owner
// 2026-10-20): the linemen spread a chip apart on the center, the receivers wide, a tight end on the line only where the
// chart lists one; a pro-style offense puts the quarterback under center and the back behind him; the front's first number
// sets the down linemen's spots, its second the linebackers'. A man is a big number in his team's color, a tag with his
// position and surname, then his class, height and weight, then his grade alone (our stat grade; nothing for a man without
// one). A starter on the availability report has a gold number and his status under
// him; an impact player (the roster's season leaders) has a ring around his number. Every man the chart matched is a button
// to his card. Eleven men at most a side; a slot the chart leaves blank stays empty.
//
// The notes' chart names each man with his number and class; his size, his grades and whether he is an impact player
// come from the team's roster answer, fetched behind the picture once per school (`attachRosters`), so the picture stands
// at once and fills in. The same drawing serves the Program (both matchups across the line), My Team and the Preseason
// Magazine (our defense over our offense) and, to come, the season book.
//
//   lineupPicture({ defense, offense, availability, onPlayer })   -> <section class="formation__matchup"> or null
//       defense, offense: { school, side: "us" | "them", lineup, scheme, coordinator }; lineup is a team's chart
//       ({ slots }); scheme the notes' words ("Spread, 11 personnel", "4-2-5"); coordinator the name or null;
//       onPlayer({ playerId, player, name, slot, isUs }) opens the card.
//   formationBlock({ lineups, us, them, schemes, coaches, availability, onPlayer })   -> <div class="formation"> or null
//       both matchups: our offense against their defense, then theirs against ours, with the rosters attached.
//   enrichLineup(root, roster, side)        fills each man of that side from a roster answer ({ players, impact })
//   attachRosters(root, { us, them, onPlayer })   fetches each school's roster and enriches (a man matched here gains his card); quiet on failure
//   placeOffense(slots, scheme), placeDefense(slots, scheme)   -> [{ slot, player, x, y }]  (exported for the tests)
//   parseScheme(text)  -> { backs, tightEnds, underCenter, front: { line, linebackers, backs } | null }

import { el, isNum, obj, playerNames, records, str, text } from "./dom.js";
import { availabilityFor, lineupSlots } from "./lineups.js";
import { fetchJson } from "../views/common.js";

// where each spot stands: x and y as a share of the field's width and height, the line of scrimmage at 50
// (a chip is about 95 px tall on a 720 px field and the rows 15% or more apart; the linemen a chip apart, 10% of the width)
const OFFENSE = {
  LT: [26, 62], LG: [38, 62], C: [50, 62], RG: [62, 62], RT: [74, 62],
  X: [8, 60], Z: [92, 58], H: [14, 74], Y: [86, 74], TE2: [24, 76],
  QB: [50, 83], RB: [62, 83], RB2: [38, 83], QBUC: [50, 77], RBI: [50, 92], FB: [40, 88],
};
const STEP_BACK = new Set(["LG", "RG"]); // on a narrow band the guards stand a step back (a CSS step), so five chips fit where five men stand
const LINE_Y = 42;
const FRONTS = { 2: [40, 60], 3: [30, 50, 70], 4: [24, 41, 59, 76], 5: [18, 34, 50, 66, 82], 6: [15, 29, 43, 57, 71, 85] };
const LINEBACKERS = { 1: [[50, 26]], 2: [[43, 26], [57, 26]], 3: [[36, 26], [50, 26], [64, 26]], 4: [[16, 35], [43, 26], [57, 26], [84, 35]], 5: [[16, 35], [38, 26], [50, 26], [62, 26], [84, 35]] };
const EDGE_LB = [[16, 35], [84, 35]]; // a 3-4's outside linebackers, outside the ends
const INSIDE_LB = [[43, 26], [57, 26]];
const CORNERS = [[8, 24], [92, 24]]; // level with the backers, clear of the edge men, a chip's half in from the edge
const NICKEL = [22, 26];
const SAFETIES = { FS: [36, 12], SS: [64, 12] }; // the rows 15% or more apart on a field 720 px tall: a chip is about 95 px
const ON_FIELD = 11;
const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);
const ROSTER_TTL_MS = 5 * 60 * 1000;
const ROSTER_RETRY_MS = 4000;
const rosters = new Map(); // school -> { at, promise } (one roster read a school a page, shared by every picture on it)

function key(slot) {
  return String(slot || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

/** 'TJ Shanahan Jr.' -> 'tj shanahan', the server's name_key: how a chart's name finds the roster's row, and one man once. */
export function nameKey(name) {
  if (typeof name !== "string") return "";
  return name
    .toLowerCase()
    .replace(/[.'’]/g, "")
    .split(/[\s,]+/)
    .filter((w) => w && !SUFFIXES.has(w))
    .join(" ");
}

// a slot's kind: the notes' own names (QB, WR-X, STAR, PK) and the longer forms some charts print (HB, LWR, SWR, LE, LOLB,
// RILB, SCB) read the same
const KINDS = [
  [/^(LT|LOT)$/, "LT"], [/^(LG|LOG)$/, "LG"], [/^C$/, "C"], [/^(RG|ROG)$/, "RG"], [/^(RT|ROT)$/, "RT"], [/^(OL|OT|OG|G|T)\d?$/, "OL"], [/^O[LTG]\d?$/, "OL"],
  [/^QB/, "QB"], [/^FB\d?$/, "FB"], [/^(RB|HB|TB|B)\d?$/, "RB"],
  [/^(TE|Y|TEL|TER)\d?$/, "TE"],
  [/^(X|LWR|WRX|LWRX)$/, "X"], [/^(Z|RWR|WRZ)$/, "Z"], [/^(H|SL|SLOT|SWR|SLWR|SRWR|WRSL|WRH|F)$/, "H"], [/^(WR|W)\d?$/, "WR"],
  [/^(DE|LE|RE|LDE|RDE|END)\d?$/, "DE"], [/^(NT|NG|NOSE)\d?$/, "NT"], [/^(DT|LDT|RDT|TACKLE)\d?$/, "DT"], [/^DL\d?$/, "DL"],
  [/^(OLB|LOLB|ROLB|JACK|EDGE|LEO|RUSH|BUCK)\d?$/, "EDGE"], [/^(SAM|SLB)\d?$/, "SAM"], [/^(WILL|WLB)\d?$/, "WILL"], [/^(ILB|LILB|RILB|MLB|MIKE|MAC|MONEY|LB)\d?$/, "ILB"], // a 3-4's Jack and Sam outside, its Mike and Will (Georgia's Mac and Money) inside // the box backers (Mike, Will, Sam) behind the line; the outside backers (a 3-4's, an LOLB and ROLB, a Jack) on the edges
  [/^(CB|LCB|RCB|CORNER)\d?$/, "CB"], [/^(NB|NICKEL|STAR|DIME|SCB|N)$/, "NB"], [/^FS$/, "FS"], [/^SS$/, "SS"], [/^(S|SAF|SAFETY|ROVER|DB)\d?$/, "S"],
];
const OFF_KINDS = new Set(["LT", "LG", "C", "RG", "RT", "OL", "QB", "FB", "RB", "TE", "X", "Z", "H", "WR"]);
const DEF_KINDS = new Set(["DE", "NT", "DT", "DL", "EDGE", "SAM", "WILL", "ILB", "CB", "NB", "FS", "SS", "S"]);

/** The kind a slot's name reads as, or null for one the field has no spot for (a kicker, a punter, "ATH"). */
export function kindOf(slot) {
  const k = key(slot);
  for (const [re, kind] of KINDS) if (re.test(k)) return kind;
  return null;
}

/** Which side of the field a slot names: an L or R prefix, the notes' X (left) and Z (right); 1 is the middle. */
function sideOf(slot) {
  const k = key(slot);
  const kind = kindOf(slot);
  if (kind === "X") return 0;
  if (kind === "Z") return 2;
  if (/^L/.test(k) && kind !== "LT" && kind !== "LG" && kind !== "ILB") return 0;
  if (/^R/.test(k) && kind !== "RT" && kind !== "RG" && kind !== "RB" && kind !== "ILB") return 2;
  if (k === "LILB") return 0;
  if (k === "RILB") return 2;
  return 1;
}

function bySide(men) {
  return men.map((man, i) => ({ man, i, side: man.sideRank ?? sideOf(man.slot) })).sort((a, b) => a.side - b.side || a.i - b.i).map((x) => x.man);
}

/** The scheme's words as numbers: "Spread, 11 personnel" (one back, one tight end), "Pro style" (under center), "4-2-5". */
export function parseScheme(words) {
  const t = typeof words === "string" ? words.toLowerCase() : "";
  const personnel = /\b([0-3])([0-3])\s*personnel\b/.exec(t);
  const front = /\b([2-6])-([1-5])(?:-([1-7]))?\b/.exec(t);
  return {
    backs: personnel ? Number(personnel[1]) : null,
    tightEnds: personnel ? Number(personnel[2]) : null,
    underCenter: /\bpro[\s-]?style\b|\bunder center\b|\bi[\s-]form/.test(t) && !/\bshotgun\b|\bspread\b/.test(t),
    front: front ? { line: Number(front[1]), linebackers: Number(front[2]), backs: front[3] ? Number(front[3]) : null } : null,
  };
}

function starters(slots) {
  return (Array.isArray(slots) ? slots : []).filter((s) => s && typeof s === "object" && Array.isArray(s.players) && s.players[0] && str(s.players[0].name)).map((s) => ({ slot: str(s.slot) || "", player: s.players[0] }));
}

/** The second string, then the third, at every slot: who fills a spot of the formation the starters leave empty. */
function reserves(slots) {
  const out = [];
  for (const depth of [1, 2]) {
    for (const s of Array.isArray(slots) ? slots : []) {
      const p = s && typeof s === "object" && Array.isArray(s.players) ? s.players[depth] : null;
      if (p && str(p.name)) out.push({ slot: str(s.slot) || "", player: p, reserve: true });
    }
  }
  return out;
}

/** The men a chart lists that the field does not draw: a second slot for a man already placed, a slot with no spot, a twelfth man. */
export function leftOff(slots, placed) {
  const shown = new Set(placed.map((m) => m.player));
  return starters(slots).filter((m) => !shown.has(m.player));
}

/**
 * The offense on the field. The linemen by name (a generic OL takes the next free spot left to right), the quarterback, the
 * backs, then the tight ends on the line (Y, then TE2) and the receivers: X, Z, the slot, then the line spots left free.
 * A man the chart lists at two slots stands at the first (a chart can name its back as a receiver too, 2026-11-01).
 */
export function placeOffense(slots, scheme) {
  const s = scheme && typeof scheme === "object" ? scheme : parseScheme(null);
  const men = starters(slots).filter((m) => OFF_KINDS.has(kindOf(m.slot)));
  const out = [];
  const taken = new Set();
  const seen = new Set();
  const who = (man) => nameKey(man.player.name) || `${man.slot}:${out.length}`;
  const put = (man, spot) => {
    if (!spot || taken.has(spot) || seen.has(who(man)) || out.length >= ON_FIELD) return false;
    taken.add(spot);
    seen.add(who(man));
    out.push({ slot: man.slot, player: man.player, x: OFFENSE[spot][0], y: OFFENSE[spot][1], step: STEP_BACK.has(spot) });
    return true;
  };
  const of = (...kinds) => men.filter((m) => kinds.includes(kindOf(m.slot)));
  const line = of("LT", "LG", "C", "RG", "RT", "OL");
  for (const man of line) if (kindOf(man.slot) !== "OL") put(man, kindOf(man.slot));
  for (const man of line) if (!seen.has(who(man))) put(man, ["LT", "LG", "C", "RG", "RT"].find((spot) => !taken.has(spot)));
  const qb = of("QB")[0];
  if (qb) put(qb, s.underCenter ? "QBUC" : "QB");
  for (const man of of("FB", "RB")) {
    if (kindOf(man.slot) === "FB") put(man, s.underCenter ? "FB" : "RB2");
    else put(man, s.underCenter ? (taken.has("RBI") ? "FB" : "RBI") : taken.has("RB") ? "RB2" : "RB");
  }
  for (const man of of("TE")) put(man, ["Y", "TE2"].find((spot) => !taken.has(spot)));
  for (const man of of("X", "Z", "H", "WR")) {
    const own = kindOf(man.slot);
    put(man, [own === "WR" ? null : own, "X", "Z", "H", "Y", "TE2"].filter(Boolean).find((spot) => !taken.has(spot)));
  }
  return out;
}

// The defense drawn from the formation (the owner, 2026-11-01 evening: "you have to have the player for the formation they
// are in. Georgia runs a 3-4, and you may be thinking about the nickel package. There should always be a defensive tackle").
// The scheme names the shape; each spot of the shape names the kinds of man who play it, best first; the chart fills the
// spots: its starters at their own positions first, then starters who can stand in, then its second string at the same
// position; a spot nobody fills stays empty and is named under the field, and a starter the shape has no spot for (the
// nickel of a 3-4 base) stands off it.
const LINE_SPOTS = {
  2: [["DE", 0], ["DE", 2]],
  3: [["DE", 0], ["NT", 1], ["DE", 2]],
  4: [["DE", 0], ["DT", 1], ["DT", 1], ["DE", 2]],
  5: [["DE", 0], ["DT", 1], ["NT", 1], ["DT", 1], ["DE", 2]],
  6: [["DE", 0], ["DT", 1], ["DT", 1], ["DT", 1], ["DT", 1], ["DE", 2]],
};
const BACKER_SPOTS = {
  1: [["MLB", 50, 26, 1]],
  2: [["ILB", 43, 26, 0], ["ILB", 57, 26, 2]],
  3: [["LB", 36, 26, 0], ["MLB", 50, 26, 1], ["LB", 64, 26, 2]],
  4: [["OLB", 16, 35, 0], ["ILB", 43, 26, 0], ["ILB", 57, 26, 2], ["OLB", 84, 35, 2]],
  5: [["OLB", 16, 35, 0], ["LB", 38, 26, 0], ["MLB", 50, 26, 1], ["LB", 62, 26, 2], ["OLB", 84, 35, 2]], // outside a five-man front's ends
};
// who plays each spot, best first: [the kinds of a man at his own position] then [the kinds who can stand in]
const PLAYS = {
  DE: [["DE"], ["DL", "EDGE", "DT", "NT"]],
  DT: [["DT"], ["NT", "DL", "DE"]],
  NT: [["NT"], ["DT", "DL", "DE"]],
  OLB: [["EDGE"], ["SAM", "WILL", "ILB"]],
  LB: [["SAM", "WILL"], ["EDGE", "ILB"]],
  MLB: [["ILB"], ["WILL", "SAM", "EDGE"]],
  ILB: [["ILB"], ["WILL", "SAM", "EDGE"]],
  CB: [["CB"], ["NB", "S"]],
  FS: [["FS"], ["S", "SS", "NB", "CB"]],
  SS: [["SS"], ["S", "FS", "NB", "CB"]],
  NB: [["NB"], ["CB", "S", "SAM"]],
};
const LINE_KINDS = new Set(["DE", "NT", "DT", "DL"]);
const WORDS = { DE: "a defensive end", NT: "a nose tackle", DT: "a defensive tackle", OLB: "an outside linebacker", LB: "a linebacker", MLB: "a middle linebacker", ILB: "an inside linebacker", CB: "a cornerback", FS: "a free safety", SS: "a strong safety", NB: "a nickel back" };

/** The formation's spots for a scheme, or for the chart's own counts where the scheme names no front. */
function defenseSpots(s, men) {
  const count = (...kinds) => men.filter((m) => kinds.includes(kindOf(m.slot))).length;
  const linemen = count("DE", "NT", "DT", "DL");
  const edges = count("EDGE");
  let line = s.front?.line;
  if (!isNum(line)) line = linemen >= 3 ? linemen : Math.max(2, Math.min(4, linemen + edges)); // a 2-4-5 chart: its outside backers are the ends
  line = Math.min(6, Math.max(2, line));
  const nickel = isNum(s.front?.backs) ? s.front.backs >= 5 : !s.front && count("NB") > 0;
  let backers = s.front?.linebackers;
  if (!isNum(backers)) backers = ON_FIELD - line - (nickel ? 5 : 4);
  backers = Math.min(5, Math.max(1, backers));
  const front = (LINE_SPOTS[line] || LINE_SPOTS[4]).map(([kind, side], i) => ({ kind, side, x: FRONTS[line][i], y: LINE_Y }));
  const second = (BACKER_SPOTS[backers] || BACKER_SPOTS[2]).map(([kind, x, y, side]) => ({ kind, side, x, y }));
  const third = [
    { kind: "CB", side: 0, x: CORNERS[0][0], y: CORNERS[0][1] },
    { kind: "CB", side: 2, x: CORNERS[1][0], y: CORNERS[1][1] },
    { kind: "FS", side: 0, x: SAFETIES.FS[0], y: SAFETIES.FS[1] },
    { kind: "SS", side: 2, x: SAFETIES.SS[0], y: SAFETIES.SS[1] },
    ...(nickel ? [{ kind: "NB", side: 0, x: NICKEL[0], y: NICKEL[1] }] : []),
  ];
  return [...front, ...second, ...third].slice(0, ON_FIELD);
}

/**
 * The defense on the field in the scheme's shape. The line first: each spot's own kind among the starters, the ends by
 * their side; a line short of its interior men brings the ends inside and puts the chart's spare edge backers on the ends
 * (a 2-4-5 chart under a 4-2-5), else the second string fills it; then the backers and the secondary, own kinds first, stand-ins
 * next, the second string last. The spots left empty come back on `missing`.
 */
export function placeDefense(slots, scheme) {
  const s = scheme && typeof scheme === "object" ? scheme : parseScheme(null);
  const men = starters(slots).filter((m) => DEF_KINDS.has(kindOf(m.slot)));
  const bench = reserves(slots).filter((m) => DEF_KINDS.has(kindOf(m.slot)));
  const spots = defenseSpots(s, men);
  const used = new Set();
  const key = (man) => nameKey(man.player.name) || `${man.slot}:${man.player.number ?? ""}`;
  const free = (pool) => pool.filter((m) => !used.has(key(m)));
  const pick = (spot, pool, kinds) => {
    const fit = free(pool).filter((m) => kinds.includes(kindOf(m.slot)));
    if (!fit.length) return null;
    const same = fit.filter((m) => sideOf(m.slot) === spot.side);
    const man = (same.length ? same : fit.filter((m) => sideOf(m.slot) === 1)).concat(fit)[0];
    used.add(key(man));
    spot.man = man;
    return man;
  };
  // the line: own kinds, then the stand-ins among the linemen, then the swap for a chart that names no tackle but spare
  // edges, then the second string, then an edge backer at an end
  const line = spots.filter((spot) => LINE_KINDS.has(spot.kind));
  for (const spot of line) pick(spot, men, PLAYS[spot.kind][0]);
  for (const spot of line) if (!spot.man) pick(spot, men, PLAYS[spot.kind][1].filter((k) => LINE_KINDS.has(k)));
  const interiorEmpty = line.filter((spot) => !spot.man && spot.kind !== "DE");
  const edgeSpotsBehind = spots.filter((spot) => spot.kind === "OLB").length;
  const spareEdges = free(men).filter((m) => kindOf(m.slot) === "EDGE").length - edgeSpotsBehind;
  if (interiorEmpty.length && spareEdges >= interiorEmpty.length) {
    const ends = line.filter((spot) => spot.kind === "DE" && spot.man);
    for (const spot of interiorEmpty) {
      const end = ends.shift();
      if (!end) break;
      spot.man = end.man;
      end.man = null;
      pick(end, men, ["EDGE"]);
    }
  }
  for (const spot of line) if (!spot.man) pick(spot, bench, [...PLAYS[spot.kind][0], ...PLAYS[spot.kind][1].filter((k) => LINE_KINDS.has(k))]);
  for (const spot of line) if (!spot.man) pick(spot, men, PLAYS[spot.kind][1]);
  // the backers and the secondary: own kinds, stand-ins, the second string
  const rest = spots.filter((spot) => !LINE_KINDS.has(spot.kind));
  for (const spot of rest) pick(spot, men, PLAYS[spot.kind][0]);
  for (const spot of rest) if (!spot.man) pick(spot, men, PLAYS[spot.kind][1]);
  for (const spot of rest) if (!spot.man) pick(spot, bench, PLAYS[spot.kind][0]);
  for (const spot of rest) if (!spot.man) pick(spot, bench, PLAYS[spot.kind][1]);
  const out = spots.filter((spot) => spot.man).map((spot) => ({ slot: spot.man.slot, player: spot.man.player, x: spot.x, y: spot.y, reserve: spot.man.reserve === true }));
  out.missing = spots.filter((spot) => !spot.man).map((spot) => WORDS[spot.kind] || spot.kind.toLowerCase());
  return out;
}

// --- the drawing -------------------------------------------------------------------------------------------------------

/** "SR · 6-3 · 240" from what the chart and the roster say; the parts that are known, or "". */
function lineText({ classYear, heightText, weight }) {
  return [str(classYear), str(heightText), isNum(weight) && weight > 0 ? String(Math.round(weight)) : null].filter(Boolean).join(" · ");
}

/** The grade alone: our stat grade, whole; null for none. */
function gradeOf({ grade }) {
  const g = isNum(grade) ? grade : isNum(obj(grade).grade) ? grade.grade : null;
  if (g !== null) return { value: String(Math.round(g)), title: `Stat grade ${Math.round(g)} of 100`, kind: "ours" };
  return null;
}

function setGrade(node, found) {
  const slot = node.querySelector(".formation__grade");
  if (!slot) return;
  if (!found) {
    slot.replaceChildren();
    slot.hidden = true;
    return;
  }
  slot.replaceChildren(found.value);
  slot.title = found.title;
  slot.dataset.kind = found.kind;
  slot.hidden = false;
}

/** One man on the field: his number, his position and surname, his line, his grade; the report's status under him. */
function man(placed, { side, availability, onPlayer }) {
  const p = obj(placed.player);
  const listed = availabilityFor(availability, p.name);
  const status = listed ? str(listed.status) || "Listed" : null;
  const id = p.playerId === undefined || p.playerId === null ? "" : String(p.playerId).trim();
  const names = playerNames(p.name, { notes: true });
  const number = Number.isFinite(p.number) ? String(Math.round(p.number)) : str(p.number) || "";
  const line = lineText(p);
  const inner = [
    el("span", { class: "formation__num" }, number),
    el("span", { class: "formation__tag" }, el("b", { class: "formation__pos" }, text(placed.slot).toUpperCase()), el("span", { class: "formation__name" }, names.last)),
    el("span", { class: "formation__line", hidden: !line }, line),
    el("span", { class: "formation__grade", hidden: true }),
    status ? el("span", { class: "formation__status" }, status) : null,
  ];
  const attrs = {
    class: `formation__man formation__man--${side === "them" ? "them" : "us"}${listed ? " formation__man--listed" : ""}${placed.step ? " formation__man--step" : ""}`,
    style: { "--fx": `${placed.x}%`, "--fy": `${placed.y}%` },
    title: `${names.full}${str(p.classYear) ? ` ${p.classYear}` : ""}${status ? `, ${status}` : ""}`,
    dataset: { playerId: id, nameKey: nameKey(p.name), number, classYear: str(p.classYear) || "" },
  };
  const node = id && typeof onPlayer === "function"
    ? el("button", { ...attrs, type: "button", "aria-label": `${placed.slot} ${names.full}${status ? `, ${status}` : ""}: open the player card`, onclick: () => onPlayer({ playerId: id, player: p, name: text(p.name), slot: placed.slot, isUs: side !== "them" }) }, inner)
    : el("div", { ...attrs, role: "img", "aria-label": `${placed.slot} ${names.full}${status ? `, ${status}` : ""}` }, inner);
  setGrade(node, gradeOf(p));
  return node;
}

function halfLabel(unit, { school, side, scheme, coordinator }) {
  const detail = [str(scheme), str(coordinator) ? `${unit === "defense" ? "DC" : "OC"} ${coordinator}` : null].filter(Boolean).join(" · ");
  return el(
    "span",
    { class: `formation__half formation__half--${unit} formation__side--${side === "them" ? "them" : "us"}` },
    `${str(school) || (side === "them" ? "Opponent" : "Our")} ${unit}`,
    detail ? el("small", {}, detail) : null,
  );
}

/** One picture: a defense over an offense across the line of scrimmage; null when neither unit has a man on its chart. */
export function lineupPicture({ defense, offense, availability, onPlayer } = {}) {
  const d = obj(defense);
  const o = obj(offense);
  const unitSlots = (lineup, unit) => lineupSlots(lineup).filter((s) => s.unit === unit);
  const slotsD = unitSlots(d.lineup, "defense");
  const slotsO = unitSlots(o.lineup, "offense");
  const placedD = placeDefense(slotsD, parseScheme(str(d.scheme) || str(obj(d.lineup).scheme)));
  const placedO = placeOffense(slotsO, parseScheme(str(o.scheme) || str(obj(o.lineup).scheme)));
  if (!placedD.length && !placedO.length) return null;
  const defName = str(d.school) || str(obj(d.lineup).team) || (d.side === "them" ? "Opponent" : "Our");
  const offName = str(o.school) || str(obj(o.lineup).team) || (o.side === "them" ? "Opponent" : "Our");
  return el(
    "section",
    { class: "formation__matchup", "aria-label": `${defName} defense over ${offName} offense` },
    el(
      "div",
      { class: "formation__field" },
      halfLabel("defense", { ...d, school: defName }),
      halfLabel("offense", { ...o, school: offName }),
      el("div", { class: "formation__los", "aria-hidden": "true" }),
      el("span", { class: "formation__los-word", "aria-hidden": "true" }, "Line of scrimmage"),
      placedD.map((placed) => man(placed, { side: d.side, availability, onPlayer })),
      placedO.map((placed) => man(placed, { side: o.side, availability, onPlayer })),
    ),
    countLine(`${defName} defense`, placedD, leftOff(slotsD, placedD)),
    countLine(`${offName} offense`, placedO, leftOff(slotsO, placedO)),
  );
}

/**
 * "Georgia defense: 10 of 11 on the field · nobody for an outside linebacker · off it: NB Daniel Harris · second string:
 * JACK Gabe Harris": only when a unit is not its eleven starters (owner 2026-11-01: "each side has 11 players").
 */
function countLine(unit, placed, off) {
  const missing = Array.isArray(placed.missing) ? placed.missing : [];
  const standIns = placed.filter((m) => m.reserve);
  if (placed.length === ON_FIELD && !off.length && !missing.length && !standIns.length) return null;
  const name = (m) => `${text(m.slot).toUpperCase()} ${playerNames(m.player.name, { notes: true }).full}`;
  const parts = [`${unit}: ${placed.length} of ${ON_FIELD} on the field`];
  if (missing.length) parts.push(`nobody for ${missing.join(", ")}`);
  if (off.length) parts.push(`off it: ${off.map(name).join(", ")}`);
  if (standIns.length) parts.push(`second string: ${standIns.map(name).join(", ")}`);
  return el("p", { class: "formation__count" }, parts.join(" · "));
}

/** Both matchups across the line: our offense against their defense, then theirs against ours; the rosters attached. */
export function formationBlock({ lineups, us, them, schemes, coaches, availability, onPlayer, rosters = true } = {}) {
  const l = obj(lineups);
  const usName = str(obj(us).school) || "Our team";
  const themName = str(obj(them).school) || str(obj(l.them).team) || "Opponent";
  const sc = obj(schemes);
  const opp = obj(sc.opponent);
  const co = obj(coaches);
  const words = (side, unit) => (side === "us" ? str(sc[unit]) : str(opp[unit])) || str(obj(side === "us" ? l.us : l.them).scheme);
  const coach = (side, unit) => str(obj(co[side])[unit === "defense" ? "defensiveCoordinator" : "offensiveCoordinator"]);
  const unit = (side, kind) => ({ school: side === "us" ? usName : themName, side, lineup: side === "us" ? l.us : l.them, scheme: words(side, kind), coordinator: coach(side, kind) });
  const fields = [
    lineupPicture({ defense: unit("them", "defense"), offense: unit("us", "offense"), availability, onPlayer }),
    lineupPicture({ defense: unit("us", "defense"), offense: unit("them", "offense"), availability, onPlayer }),
  ].filter(Boolean);
  if (!fields.length) return null;
  const root = el(
    "div",
    { class: "formation" },
    fields,
    el("p", { class: "note" }, "Each starter at the spot his slot takes in the scheme's base look. Under his number: his position and surname, his class, height and weight, then his grade alone (our stat grade). A gold number is a starter on the availability report, with his status; a ring is an impact player, one of the roster's season leaders. Tap a man for his card."),
  );
  if (rosters) attachRosters(root, { us: str(obj(us).school), them: str(obj(them).school), onPlayer }); // rosters: false on a past season's game (today's rosters are not that season's)
  return root;
}

// --- the roster behind the picture -------------------------------------------------------------------------------------

/** The roster's rows the picture can use, by id and by name, with the impact players' ids and names. */
function rosterIndex(roster) {
  const r = obj(roster);
  const byId = new Map();
  const byName = new Map();
  for (const row of records(r.players)) {
    if (row.playerId !== undefined && row.playerId !== null) byId.set(String(row.playerId), row);
    const k = nameKey(row.name);
    if (k) byName.set(k, [...(byName.get(k) || []), row]);
  }
  const impact = { ids: new Set(), names: new Set() };
  for (const unit of ["offense", "defense"]) {
    for (const p of records(obj(r.impact)[unit])) {
      if (p.playerId !== undefined && p.playerId !== null) impact.ids.add(String(p.playerId));
      if (nameKey(p.name)) impact.names.add(nameKey(p.name));
    }
  }
  return { byId, byName, impact };
}

/** The roster's row for a man: by id, else by name (a shared name settled by the number), else null. */
function rowFor(node, index) {
  const id = node.dataset.playerId;
  if (id && index.byId.has(id)) return index.byId.get(id);
  const rows = index.byName.get(node.dataset.nameKey) || [];
  if (rows.length === 1) return rows[0];
  const number = node.dataset.number;
  return rows.find((row) => number && String(row.number) === number) || null;
}

/** A man the chart could not match (a chart can name him with his number alone) becomes a button once the roster knows him. */
function asButton(node, row, { side, onPlayer }) {
  const id = row.playerId === undefined || row.playerId === null ? "" : String(row.playerId).trim();
  if (!id || node.tagName === "BUTTON" || typeof onPlayer !== "function") return node;
  const names = playerNames(row.name || node.dataset.nameKey, { notes: true });
  const slot = text(node.querySelector(".formation__pos")?.textContent);
  const button = el("button", {
    class: node.className,
    type: "button",
    style: { "--fx": node.style.getPropertyValue("--fx"), "--fy": node.style.getPropertyValue("--fy") },
    title: node.getAttribute("title"),
    dataset: { ...node.dataset, playerId: id },
    "aria-label": `${slot} ${names.full}: open the player card`,
    onclick: () => onPlayer({ playerId: id, player: row, name: text(row.name), slot, isUs: side !== "them" }),
  }, [...node.childNodes]);
  node.replaceWith(button);
  return button;
}

/** Fill one side's men from its roster: the size, the grade, the impact ring, a card for a man matched here. The picture stands without it. */
export function enrichLineup(root, roster, side = "us", { onPlayer = null } = {}) {
  if (!root || typeof root.querySelectorAll !== "function") return 0;
  const index = rosterIndex(roster);
  let filled = 0;
  for (let node of root.querySelectorAll(`.formation__man--${side === "them" ? "them" : "us"}`)) {
    const row = rowFor(node, index);
    const isImpact = (node.dataset.playerId && index.impact.ids.has(node.dataset.playerId)) || index.impact.names.has(node.dataset.nameKey);
    if (isImpact) node.classList.add("formation__man--impact");
    if (!row) continue;
    filled += 1;
    node = asButton(node, row, { side, onPlayer });
    const numNode = node.querySelector(".formation__num");
    if (numNode && !numNode.textContent && isNum(row.number) && row.number >= 0) numNode.replaceChildren(String(Math.round(row.number)));
    const lineNode = node.querySelector(".formation__line");
    const line = lineText({ classYear: node.dataset.classYear || str(row.classYear), heightText: row.heightText, weight: row.weight }); // the chart's class first: it is the one printed this week
    if (lineNode && line) {
      lineNode.replaceChildren(line);
      lineNode.hidden = false;
    }
    const found = gradeOf({ grade: row.grade });
    if (found || !node.querySelector(".formation__grade")?.textContent) setGrade(node, found);
  }
  return filled;
}

/**
 * One roster read a school for the page (five minutes), shared by every picture that asks. An answer with no players (a
 * server still warming up) is asked once more after a moment and never kept, so the next picture asks again.
 */
export function rosterFor(school, { retry = true } = {}) {
  const name = str(school);
  if (!name) return Promise.resolve(null);
  const had = rosters.get(name);
  if (had && Date.now() - had.at < ROSTER_TTL_MS) return had.promise;
  const read = () => fetchJson(`/api/roster?team=${encodeURIComponent(name)}`)
    .then((envelope) => (envelope && typeof envelope === "object" && envelope.data && typeof envelope.data === "object" ? envelope.data : null))
    .catch(() => null);
  const promise = read().then((roster) => {
    if (roster && records(roster.players).length) return roster;
    rosters.delete(name); // not kept: the next picture asks again
    if (!roster || !retry) return null; // a read that failed waits for the next picture; a thin answer is asked once more
    return new Promise((resolve) => setTimeout(resolve, ROSTER_RETRY_MS)).then(() => rosterFor(name, { retry: false }));
  });
  rosters.set(name, { at: Date.now(), promise });
  return promise;
}

/** Fetch each school's roster and fill its men; a roster that does not come leaves the picture as drawn. */
export function attachRosters(root, { us, them, onPlayer = null } = {}) {
  const jobs = [];
  for (const [side, school] of [["us", us], ["them", them]]) {
    if (!str(school) || !root.querySelector(`.formation__man--${side}`)) continue;
    jobs.push(rosterFor(school).then((roster) => (roster ? enrichLineup(root, roster, side, { onPlayer }) : 0)));
  }
  return Promise.all(jobs);
}
