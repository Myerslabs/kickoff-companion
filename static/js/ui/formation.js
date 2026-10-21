// The lineups in formation (the formation mock, owner 2026-10-20, https://claude.ai/artifact/JMXmmxicX21BaC2kHBZsGt: "Our
// objective with the lineups is going to be to visualize the formation of the offense and the defense"). Both matchups on a
// field: our offense against their defense, then their offense against our defense; the defense up top, the offense at the
// bottom, the line of scrimmage between them. Each starter stands at the spot his slot takes in the scheme's base look, as the
// owner marked the board: the linemen tight on the center (about 7% of the field apart), the ends and linebackers pulled in
// with them, the receivers spread (X wide left, Z wide right, the slot off the line, a fourth receiver on the line where the
// chart lists no tight end), a tight end on the line only where the chart lists one. The chart decides who is drawn and the
// scheme's words (from the notes: "Spread, 11 personnel", "Pro style", "4-2-5", "3-4") decide the shape: a pro-style or
// under-center offense puts the quarterback under center and the back behind him; the front's first number sets the down
// linemen's spots, its second the linebackers'. A chip is a button to the player's card when the chart matched him; a starter
// on the availability report wears a gold ring and his status. Eleven men at most a side; a slot the chart leaves blank
// stays empty.
//
//   formationBlock({ lineups, us, them, schemes, availability, detail, onPlayer })   -> <div class="formation"> or null
//       us, them: { school, abbreviation }; schemes: the notes' block ({ offense, defense, opponent: { offense, defense } });
//       detail(unit, side) -> "OC Name · Spread" for the heads (ui/lineups_combined.js unitDetail), optional;
//       onPlayer({ playerId, player, name, slot, isUs }) opens the card.
//   placeOffense(slots, scheme), placeDefense(slots, scheme)   -> [{ slot, player, x, y }]  (exported for the tests)
//   parseScheme(text)  -> { backs, tightEnds, underCenter, front: { line, linebackers, backs } | null }

import { el, obj, playerNames, str, text } from "./dom.js";
import { availabilityFor, lineupSlots } from "./lineups.js";

// where each spot stands: x and y as a share of the field's width and height, the line of scrimmage at 50
// (a chip is about 75 px tall on a 440 px field: rows sit 17% or more apart so no man's name runs into the next row's label)
const OFFENSE = {
  LT: [35, 56], LG: [43, 56], C: [50, 56], RG: [57, 56], RT: [65, 56],
  X: [7, 56], Z: [93, 59], H: [18, 64], Y: [78, 56], TE2: [22, 56],
  QB: [50, 78], RB: [61, 78], RB2: [39, 78], QBUC: [50, 73], RBI: [50, 90], FB: [41, 85],
};
const LINE_Y = 42;
const FRONTS = { 2: [42, 58], 3: [38, 50, 62], 4: [33.5, 41.5, 50, 58.5], 5: [28, 39, 50, 61, 72], 6: [25, 35, 45, 55, 65, 75] };
const LINEBACKERS = { 1: [[50, 25]], 2: [[45, 25], [55, 25]], 3: [[36, 25], [50, 25], [64, 25]], 4: [[26, 36], [44, 25], [56, 25], [74, 36]], 5: [[26, 36], [38, 25], [50, 25], [62, 25], [74, 36]] };
const EDGE_LB = [[26, 36], [74, 36]]; // a 3-4's outside linebackers, on the edges of the line
const INSIDE_LB = [[44, 25], [56, 25]];
const CORNERS = [[7, 36], [93, 36]];
const NICKEL = [22, 26];
const SAFETIES = { FS: [36, 9], SS: [64, 9] };
const ON_FIELD = 11;

function key(slot) {
  return String(slot || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
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

function isOL(k) {
  return ["LT", "LG", "C", "RG", "RT", "OL", "OT", "OG", "G", "T", "LOT", "ROT", "LOG", "ROG"].includes(k) || /^O[LTG]\d?$/.test(k);
}

/**
 * The offense on the field. The linemen by name (a generic OL takes the next free spot left to right), the quarterback, the
 * backs, then the tight ends on the line (Y, then TE2) and the receivers: X, Z, the slot, then the line spots left free.
 */
export function placeOffense(slots, scheme) {
  const s = scheme && typeof scheme === "object" ? scheme : parseScheme(null);
  const men = starters(slots);
  const out = [];
  const taken = new Set();
  const put = (man, spot) => {
    if (!spot || taken.has(spot) || out.length >= ON_FIELD) return false;
    taken.add(spot);
    out.push({ slot: man.slot, player: man.player, x: OFFENSE[spot][0], y: OFFENSE[spot][1] });
    return true;
  };
  const line = men.filter((m) => isOL(key(m.slot)));
  for (const man of line) if (OFFENSE[key(man.slot)] && ["LT", "LG", "C", "RG", "RT"].includes(key(man.slot))) put(man, key(man.slot));
  for (const man of line) if (!out.some((o) => o.player === man.player)) put(man, ["LT", "LG", "C", "RG", "RT"].find((spot) => !taken.has(spot)));
  const qb = men.find((m) => key(m.slot).startsWith("QB"));
  if (qb) put(qb, s.underCenter ? "QBUC" : "QB");
  const backs = men.filter((m) => /^(RB|HB|TB|FB|B)\d?$/.test(key(m.slot)));
  for (const man of backs) {
    const k = key(man.slot);
    if (k.startsWith("FB")) put(man, s.underCenter ? "FB" : "RB2");
    else put(man, s.underCenter ? (taken.has("RBI") ? "FB" : "RBI") : taken.has("RB") ? "RB2" : "RB");
  }
  const ends = men.filter((m) => key(m.slot).startsWith("TE") || key(m.slot) === "Y");
  for (const man of ends) put(man, ["Y", "TE2"].find((spot) => !taken.has(spot)));
  const receivers = men.filter((m) => /^(WR|X|Z|H|SL|SLOT|F|W)/.test(key(m.slot)) && !ends.includes(m));
  for (const man of receivers) {
    const k = key(man.slot);
    const own = k === "X" || k.endsWith("X") ? "X" : k === "Z" || k.endsWith("Z") ? "Z" : /SL|SLOT|H$/.test(k) ? "H" : null;
    put(man, [own, "X", "Z", "H", "Y", "TE2"].filter(Boolean).find((spot) => !taken.has(spot)));
  }
  return out;
}

/**
 * The defense on the field. The down linemen across the line by the front's first number (else their count), the
 * linebackers by its second (a 3-4's outside men on the edges), the corners wide, the nickel over the slot, the safeties deep.
 */
export function placeDefense(slots, scheme) {
  const s = scheme && typeof scheme === "object" ? scheme : parseScheme(null);
  const men = starters(slots);
  const out = [];
  const add = (man, x, y) => {
    if (out.length < ON_FIELD) out.push({ slot: man.slot, player: man.player, x, y });
  };
  const line = men.filter((m) => /^(DE|DT|NT|NG|DL|EDGE|JACK|RUSH|LDE|RDE|LDT|RDT|LE|RE|BUCK|END|TACKLE)/.test(key(m.slot)));
  const frontSpots = FRONTS[Math.min(6, Math.max(2, s.front?.line || line.length || 4))] || FRONTS[4];
  line.slice(0, frontSpots.length).forEach((man, i) => add(man, frontSpots[i], LINE_Y));
  const backers = men.filter((m) => /^(LB|MLB|ILB|OLB|WLB|SLB|MIKE|WILL|SAM|JACK|STAR)/.test(key(m.slot)) && !line.includes(m)).filter((m) => !/^(JACK|STAR)/.test(key(m.slot)) || true);
  const count = Math.min(5, Math.max(1, s.front?.linebackers || backers.length || 2));
  if (count === 4 && backers.length) {
    // a 3-4: the outside men on the edges, the inside men behind the line
    const outside = backers.filter((m) => /^(OLB|WLB|SLB|SAM|JACK|EDGE)/.test(key(m.slot)));
    const inside = backers.filter((m) => !outside.includes(m));
    outside.slice(0, 2).forEach((man, i) => add(man, EDGE_LB[i][0], EDGE_LB[i][1]));
    inside.slice(0, 2).forEach((man, i) => add(man, INSIDE_LB[i][0], INSIDE_LB[i][1]));
    const left = [...outside.slice(2), ...inside.slice(2)];
    left.slice(0, 1).forEach((man) => add(man, 50, 25));
  } else {
    const spots = LINEBACKERS[count] || LINEBACKERS[2];
    backers.slice(0, spots.length).forEach((man, i) => add(man, spots[i][0], spots[i][1]));
  }
  const corners = men.filter((m) => /^(CB|LCB|RCB|CORNER)/.test(key(m.slot)));
  corners.slice(0, 2).forEach((man, i) => add(man, CORNERS[i][0], CORNERS[i][1]));
  const nickel = men.filter((m) => /^(NB|NICKEL|STAR|DIME|SCB|N)$/.test(key(m.slot)));
  nickel.slice(0, 1).forEach((man) => add(man, NICKEL[0], NICKEL[1]));
  const safeties = men.filter((m) => /^(S|FS|SS|SAF|SAFETY|DB)\d?$/.test(key(m.slot)));
  const placed = new Set();
  for (const man of safeties) {
    const k = key(man.slot);
    const spot = k.startsWith("FS") && !placed.has("FS") ? "FS" : k.startsWith("SS") && !placed.has("SS") ? "SS" : ["FS", "SS"].find((name) => !placed.has(name));
    if (!spot) break;
    placed.add(spot);
    add(man, SAFETIES[spot][0], SAFETIES[spot][1]);
  }
  return out;
}

/** One man on the field: his slot, number and surname; a gold ring and his status when the report lists him. */
function man(placed, { them, availability, onPlayer, isUs }) {
  const p = obj(placed.player);
  const listed = availabilityFor(availability, p.name);
  const status = listed ? str(listed.status) || "Listed" : null;
  const id = p.playerId === undefined || p.playerId === null ? "" : String(p.playerId).trim();
  const names = playerNames(p.name, { notes: true });
  const number = Number.isFinite(p.number) ? String(Math.round(p.number)) : str(p.number) || "";
  const inner = [
    el("span", { class: "formation__pos" }, text(placed.slot).toUpperCase()),
    el("span", { class: "formation__num" }, number),
    el("span", { class: "formation__name" }, names.last),
    status ? el("span", { class: "formation__status" }, status) : null,
  ];
  const attrs = { class: `formation__man formation__man--${them ? "them" : "us"}${listed ? " formation__man--listed" : ""}`, style: { "--fx": `${placed.x}%`, "--fy": `${placed.y}%` }, title: `${names.full}${str(p.classYear) ? ` ${p.classYear}` : ""}${status ? `, ${status}` : ""}` };
  if (id && typeof onPlayer === "function") {
    return el("button", { ...attrs, type: "button", "aria-label": `${placed.slot} ${names.full}${status ? `, ${status}` : ""}: open the player card`, onclick: () => onPlayer({ playerId: id, player: p, name: text(p.name), slot: placed.slot, isUs }) }, inner);
  }
  return el("div", { ...attrs, role: "img", "aria-label": `${placed.slot} ${names.full}${status ? `, ${status}` : ""}` }, inner);
}

function field({ offense, defense, offSide, offTeam, defTeam, offenseDetail, defenseDetail, availability, onPlayer }) {
  const them = offSide === "them";
  const head = (name, side, detail) => el("span", { class: `formation__side formation__side--${side}` }, name, detail ? el("small", {}, detail) : null);
  return el(
    "section",
    { class: "formation__matchup", "aria-label": `${offTeam} offense against ${defTeam} defense` },
    el("div", { class: "formation__head" }, head(`${offTeam} offense`, offSide, offenseDetail), el("span", { class: "formation__how" }, "defense up top, offense at the bottom"), head(`${defTeam} defense`, them ? "us" : "them", defenseDetail)),
    el(
      "div",
      { class: "formation__field" },
      el("div", { class: "formation__los", "aria-hidden": "true" }),
      el("span", { class: "formation__los-word", "aria-hidden": "true" }, "Line of scrimmage"),
      defense.map((placed) => man(placed, { them: !them, availability, onPlayer, isUs: them })),
      offense.map((placed) => man(placed, { them, availability, onPlayer, isUs: !them })),
    ),
  );
}

export function formationBlock({ lineups, us, them, schemes, availability, detail, onPlayer } = {}) {
  const l = obj(lineups);
  const usName = str(obj(us).school) || "Our team";
  const themName = str(obj(them).school) || str(obj(l.them).team) || "Opponent";
  const sc = obj(schemes);
  const opp = obj(sc.opponent);
  const words = (side, unit) => (side === "us" ? str(sc[unit]) : str(opp[unit])) || str(obj(side === "us" ? l.us : l.them).scheme);
  const unitSlots = (side, unit) => lineupSlots(side === "us" ? l.us : l.them).filter((s) => s.unit === unit);
  const say = (unit, side) => (typeof detail === "function" ? str(detail(unit, side)) : null) || words(side, unit);
  const ours = placeOffense(unitSlots("us", "offense"), parseScheme(words("us", "offense")));
  const theirsD = placeDefense(unitSlots("them", "defense"), parseScheme(words("them", "defense")));
  const theirs = placeOffense(unitSlots("them", "offense"), parseScheme(words("them", "offense")));
  const oursD = placeDefense(unitSlots("us", "defense"), parseScheme(words("us", "defense")));
  const fields = [];
  if (ours.length || theirsD.length) fields.push(field({ offense: ours, defense: theirsD, offSide: "us", offTeam: usName, defTeam: themName, offenseDetail: say("offense", "us"), defenseDetail: say("defense", "them"), availability, onPlayer }));
  if (theirs.length || oursD.length) fields.push(field({ offense: theirs, defense: oursD, offSide: "them", offTeam: themName, defTeam: usName, offenseDetail: say("offense", "them"), defenseDetail: say("defense", "us"), availability, onPlayer }));
  if (!fields.length) return null;
  return el(
    "div",
    { class: "formation" },
    fields,
    el("p", { class: "note" }, "Each starter at the spot his slot takes in the scheme's base look: the linemen tight on the center, the receivers spread, a tight end on the line only where the chart lists one; the front's numbers set the down linemen and the linebackers, the corners wide, the nickel over the slot, the safeties deep. A slot the chart leaves blank stays empty. A gold ring is a starter on the availability report. Tap a man for his card."),
  );
}
