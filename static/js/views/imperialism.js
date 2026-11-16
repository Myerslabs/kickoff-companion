// The Imperialism Map (FEAT-17, Feature Set v2 Phase B). The owner's board of 2026-10-30
// "Build as drawn": the lower 48 and Hawaii as one lattice of hexagons
// dealt to the FBS schools by enrollment (the weighted split, one solid region each), then carved by the season's results.
// Three bands, each its own flyout and page (FEAT-15): the map with its week slider, Most land, and ours (titled with our
// mascot). In the menu's New until he places it.
//
// The tablet draws it (owner 2026-10-30, "Tablet draws it"): the lattice comes once from /api/imperialism/grid?v=<version>
// (kept a year), every week's owners in the one answer of /api/imperialism/now, so the slider and Play never wait for the
// server. Each school's land is one path of its cells, the borders are drawn where two owners meet, ours wears --team-us with
// a --team-accent outline. Each school in its own color, its second color when the first sits too close to a neighbor's in any
// week or does not read on the panel (the biggest holders choose first, so the colors hold still while the slider moves).
// Logos on territories of 230 cells or more and always ours, on the largest piece's middle cell. A tap on the map opens that
// territory's card: beside it over the map on a wide screen, from the bottom on a phone. The slider: a tick a snapshot (Start,
// the weeks, CCG, Selection Sunday, the playoff rounds), what is still to come faded, a week in progress in italics; the arrow
// keys move it, Play steps a week every 0.7 s.
//
//   createImperialismView({ onStatus })
//   geometry(grid), cellAt(geo, x, y, reach)          the lattice in the picture's units, and the cell under a point
//   colorsFor(teams, owners, geo, { panel, us, usColor })  one color a school for the whole season
//   standings(owners, prev, count)                    Most land's rows, every school with land, ranked
//   largestPiece(cells, owners, geo, team)            { size, middle } of a school's biggest connected piece
//   anchorCell(cells, owners, geo, team, home)        where a school's logo and ring go (owner 2026-10-30: "the schools need to
//                                                     be anchored in their locations"): its campus cell while it holds it, else
//                                                     its land nearest home, so a conqueror's logo never wanders into what it took
//   tickLabel(label), weekWords(label)                "Wk 7" -> "7", "Week 7"
//   captionFor(view, i), eventLine(event, us), nextWords(schedule, view, i)   the words under the slider and in our band
//   prepare(data)                                     the answer checked and laid out for drawing (null when unusable)

import { ours, usSchool } from "../identity.js";
import { contrastRatio, hexToRgb, readableColor } from "../ui/colors.js";
import { DASH, el, fmtNum, isNum, layerZ, ordinal, teamLink, teamLogo, text } from "../ui/dom.js";
import { band, note } from "../ui/states.js";
import { errorPanel, poller } from "./common.js";

const SVG = "http://www.w3.org/2000/svg";
const GRID_TIMEOUT_MS = 20 * 1000;
const PLAY_MS = 700;
const LOGO_CELLS = 230; // a logo on a territory this size or more, and always on ours
const LOGO_PIECE = 40; // ... when its largest piece can hold one
const TOP = 15; // Most land's rows
const NEAR = 90; // two neighbors' colors closer than this (RGB distance): the second color
const MIN_CONTRAST = 1.6; // a fill against the panel (the sea)
const WIDE = 560; // from this map width the card sits beside the territory; under it, a sheet from the bottom
const CARD_W = 232;
const PANEL_DARK = "#1C1F26";
const US_DEFAULT = "#3D6BFF";

const key = (col, row) => col * 10000 + row;
const fixed = (v) => (Math.round(v * 100) / 100).toString();

/** The six cells around (col, row) on the odd-columns-down lattice (app/services/imperialism_grid.py neighbors). */
function around(col, row) {
  if (col % 2 === 0) return [[col, row - 1], [col, row + 1], [col - 1, row - 1], [col - 1, row], [col + 1, row - 1], [col + 1, row]];
  return [[col, row - 1], [col, row + 1], [col - 1, row], [col - 1, row + 1], [col + 1, row], [col + 1, row + 1]];
}

/** The lattice in the picture's own units: each cell's center, its hexagon, its neighbors, each border between two cells. */
export function geometry(grid) {
  const g = grid && typeof grid === "object" ? grid : null;
  const flat = Array.isArray(g?.cells) ? g.cells : null;
  if (!g || !flat || flat.length < 2 || !isNum(g.side) || g.side <= 0 || !isNum(g.x0) || !isNum(g.y0)) return null;
  const n = Math.floor(flat.length / 2);
  const side = g.side;
  const h = Math.sqrt(3) * side;
  const cols = new Array(n);
  const rows = new Array(n);
  const xs = new Float64Array(n);
  const ys = new Float64Array(n);
  const at = new Map();
  for (let i = 0; i < n; i += 1) {
    const c = flat[2 * i];
    const r = flat[2 * i + 1];
    if (!Number.isInteger(c) || !Number.isInteger(r) || c < 0 || r < 0) return null;
    cols[i] = c;
    rows[i] = r;
    xs[i] = g.x0 + c * 1.5 * side;
    ys[i] = g.y0 + r * h + (c % 2 ? h / 2 : 0);
    at.set(key(c, r), i);
  }
  // a hexagon a touch larger than the cell, so the fills of one owner meet with no seam
  const s = side * 1.03;
  const hh = (s * Math.sqrt(3)) / 2;
  const tail = `l${fixed(-s / 2)} ${fixed(hh)}h${fixed(-s)}l${fixed(-s / 2)} ${fixed(-hh)}l${fixed(s / 2)} ${fixed(-hh)}h${fixed(s)}z`;
  const hex = new Array(n);
  const near = new Array(n);
  const edgeA = [];
  const edgeB = [];
  const segs = [];
  for (let i = 0; i < n; i += 1) {
    hex[i] = `M${fixed(xs[i] + s)} ${fixed(ys[i])}${tail}`;
    near[i] = [];
    for (const [c2, r2] of around(cols[i], rows[i])) {
      const j = at.get(key(c2, r2));
      if (j === undefined) continue;
      near[i].push(j);
      if (j > i) {
        const dx = xs[j] - xs[i];
        const dy = ys[j] - ys[i];
        const d = Math.hypot(dx, dy) || 1;
        const mx = xs[i] + dx / 2;
        const my = ys[i] + dy / 2;
        const px = (-dy / d) * (side / 2);
        const py = (dx / d) * (side / 2);
        edgeA.push(i);
        edgeB.push(j);
        segs.push(`M${fixed(mx + px)} ${fixed(my + py)}L${fixed(mx - px)} ${fixed(my - py)}`);
      }
    }
  }
  const box = Array.isArray(g.viewBox) && g.viewBox.length === 4 && g.viewBox.every(isNum) ? g.viewBox : [0, 0, 960, 600];
  return { n, side, h, x0: g.x0, y0: g.y0, cols, rows, xs, ys, at, hex, near, edgeA, edgeB, segs, width: box[2], height: box[3], states: typeof g.states === "string" ? g.states : "", version: typeof g.version === "string" ? g.version : null };
}

/** The cell nearest (x, y) in the picture's units, within `reach` of its center; null over the sea. */
export function cellAt(geo, x, y, reach = null) {
  if (!geo || !isNum(x) || !isNum(y)) return null;
  const limit = Math.max(isNum(reach) ? reach : 0, geo.side * 1.2);
  const span = Math.ceil(limit / (1.5 * geo.side)) + 1;
  const c0 = Math.round((x - geo.x0) / (1.5 * geo.side));
  let best = null;
  let bestD = Infinity;
  for (let c = c0 - span; c <= c0 + span; c += 1) {
    if (c < 0) continue;
    const r0 = Math.round((y - geo.y0 - (c % 2 ? geo.h / 2 : 0)) / geo.h);
    const rows = Math.ceil(limit / geo.h) + 1;
    for (let r = r0 - rows; r <= r0 + rows; r += 1) {
      const i = geo.at.get(key(c, r));
      if (i === undefined) continue;
      const d = (geo.xs[i] - x) ** 2 + (geo.ys[i] - y) ** 2;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
  }
  return best !== null && bestD <= limit * limit ? best : null;
}

const distance = (a, b) => {
  const x = hexToRgb(a);
  const y = hexToRgb(b);
  return x && y ? Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) : 0;
};

/** One color a school for the whole season: its own, its second when the first is too close to a neighbor's (any week) or
 *  does not read on the panel; ours is `usColor`. The schools that held the most land choose first. */
export function colorsFor(teams, snapshots, geo, { panel = PANEL_DARK, us = null, usColor = US_DEFAULT, light = false } = {}) {
  const count = Array.isArray(teams) ? teams.length : 0;
  const most = new Array(count).fill(0);
  const adjacent = Array.from({ length: count }, () => new Set());
  for (const owners of Array.isArray(snapshots) ? snapshots : []) {
    const here = new Array(count).fill(0);
    for (const o of owners) if (o >= 0 && o < count) here[o] += 1;
    for (let i = 0; i < count; i += 1) if (here[i] > most[i]) most[i] = here[i];
    if (!geo) continue;
    for (let k = 0; k < geo.edgeA.length; k += 1) {
      const a = owners[geo.edgeA[k]];
      const b = owners[geo.edgeB[k]];
      if (a !== b && a >= 0 && b >= 0 && a < count && b < count) {
        adjacent[a].add(b);
        adjacent[b].add(a);
      }
    }
  }
  const chosen = new Array(count).fill(null);
  if (Number.isInteger(us) && us >= 0 && us < count) chosen[us] = usColor;
  const order = [...Array(count).keys()].filter((i) => i !== us).sort((a, b) => most[b] - most[a] || a - b);
  for (const i of order) {
    const t = teams[i] && typeof teams[i] === "object" ? teams[i] : {};
    const own = [t.color, t.altColor].filter((c) => hexToRgb(c));
    const readable = own.filter((c) => contrastRatio(c, panel) >= MIN_CONTRAST);
    const candidates = readable.length ? readable : [readableColor(own, { light })];
    let best = candidates[0];
    let bestGap = -1;
    for (const c of candidates) {
      let gap = Infinity;
      for (const o of adjacent[i]) if (chosen[o]) gap = Math.min(gap, distance(c, chosen[o]));
      if (gap >= NEAR) {
        best = c;
        break;
      }
      if (gap > bestGap) {
        best = c;
        bestGap = gap;
      }
    }
    chosen[i] = best;
  }
  return chosen;
}

/** Most land: every school with land, the most first (ties by name), with its share of the map and the change since `prev`. */
export function standings(owners, prev, teams) {
  const count = Array.isArray(teams) ? teams.length : 0;
  const cells = new Array(count).fill(0);
  const before = Array.isArray(prev) ? new Array(count).fill(0) : null;
  for (const o of Array.isArray(owners) ? owners : []) if (o >= 0 && o < count) cells[o] += 1;
  if (before) for (const o of prev) if (o >= 0 && o < count) before[o] += 1;
  const total = Array.isArray(owners) && owners.length ? owners.length : 1;
  const name = (i) => text(teams[i]?.team);
  const held = [...Array(count).keys()].filter((i) => cells[i] > 0).sort((a, b) => cells[b] - cells[a] || name(a).localeCompare(name(b)));
  let rank = 0;
  let last = null;
  return held.map((i, place) => {
    if (cells[i] !== last) {
      rank = place + 1;
      last = cells[i];
    }
    return { index: i, team: name(i), rank, cells: cells[i], pct: (100 * cells[i]) / total, change: before ? cells[i] - before[i] : null };
  });
}

/** Where a school's logo and ring go: its campus cell (`home`, from the server) while it holds it, else the cell of its land
    nearest its campus; with no campus cell in the answer, the middle of its biggest piece. Null with no land. */
export function anchorCell(cells, owners, geo, team, home) {
  const list = Array.isArray(cells) ? cells : [];
  if (!list.length || !geo) return null;
  if (!isNum(home) || home < 0 || home >= geo.xs.length) return largestPiece(list, owners, geo, team).middle;
  if (owners[home] === team) return home;
  let best = null;
  let d = Infinity;
  for (const c of list) {
    const e = (geo.xs[c] - geo.xs[home]) ** 2 + (geo.ys[c] - geo.ys[home]) ** 2;
    if (e < d || (e === d && c < best)) {
      d = e;
      best = c;
    }
  }
  return best;
}

/** A school's biggest connected piece: its size and the cell nearest its middle. */
export function largestPiece(cells, owners, geo, team) {
  const list = Array.isArray(cells) ? cells : [];
  if (!list.length || !geo) return { size: 0, middle: null };
  const seen = new Set();
  let best = [];
  for (const start of list) {
    if (seen.has(start)) continue;
    const piece = [];
    const todo = [start];
    seen.add(start);
    while (todo.length) {
      const c = todo.pop();
      piece.push(c);
      for (const nb of geo.near[c]) {
        if (!seen.has(nb) && owners[nb] === team) {
          seen.add(nb);
          todo.push(nb);
        }
      }
    }
    if (piece.length > best.length) best = piece;
  }
  let cx = 0;
  let cy = 0;
  for (const c of best) {
    cx += geo.xs[c];
    cy += geo.ys[c];
  }
  cx /= best.length;
  cy /= best.length;
  let middle = best[0];
  let d = Infinity;
  for (const c of best) {
    const e = (geo.xs[c] - cx) ** 2 + (geo.ys[c] - cy) ** 2;
    if (e < d) {
      d = e;
      middle = c;
    }
  }
  return { size: best.length, middle };
}

/** A slider tick's words: "Start", the week's number, "CCG", "Sel.", the round. */
export function tickLabel(label) {
  const s = text(label);
  const week = /^Wk\s*(\d+)$/i.exec(s);
  if (week) return week[1];
  if (s === "Selection Sunday") return "Sel.";
  return s || DASH;
}

/** The snapshot's name in a sentence: "Week 7", "Championship week", "Selection Sunday", "The quarterfinals". */
export function weekWords(label) {
  const s = text(label);
  const week = /^Wk\s*(\d+)$/i.exec(s);
  if (week) return `Week ${week[1]}`;
  return { Start: "The start", CCG: "Championship week", R1: "The first round", QF: "The quarterfinals", SF: "The semifinals", Final: "The championship game" }[s] || s || "This week";
}

/** "at the start", "after week 7", "after championship week", "after Selection Sunday", "after the first round". */
export function after(label) {
  if (text(label) === "Start") return "at the start";
  return `after ${weekWords(label).replace(/^(The|Week|Championship)\b/, (word) => word.toLowerCase())}`;
}

const cellWords = (n) => `${fmtNum(n)} ${n === 1 ? "cell" : "cells"}`;
const signed = (v) => (!isNum(v) ? DASH : v > 0 ? `+${fmtNum(v)}` : v < 0 ? `−${fmtNum(Math.abs(v))}` : "–");
const recordOf = (snap, school) => {
  const r = snap?.records && typeof snap.records === "object" ? snap.records[school] : null;
  return Array.isArray(r) && isNum(r[0]) && isNum(r[1]) ? `${r[0]}-${r[1]}` : null;
};

/** The answer checked and laid out for drawing: each snapshot's owners as numbers of the right length, the teams by index,
 *  the events by snapshot, our index. Null when nothing can be drawn. */
export function prepare(data, geo) {
  const d = data && typeof data === "object" ? data : {};
  const teams = [];
  for (const t of Array.isArray(d.teams) ? d.teams : []) {
    if (t && typeof t === "object" && Number.isInteger(t.index) && t.index >= 0 && typeof t.team === "string" && t.team) teams[t.index] = t;
  }
  for (let i = 0; i < teams.length; i += 1) if (!teams[i]) teams[i] = { team: `School ${i + 1}`, index: i };
  const cells = geo ? geo.n : null;
  let skipped = 0;
  const snapshots = [];
  for (const s of Array.isArray(d.snapshots) ? d.snapshots : []) {
    const owners = Array.isArray(s?.owners) ? s.owners : null;
    if (!owners || (cells !== null && owners.length !== cells)) {
      skipped += 1;
      continue;
    }
    snapshots.push({
      phase: text(s.phase),
      week: isNum(s.week) ? s.week : null,
      label: typeof s.label === "string" && s.label ? s.label : DASH,
      partial: s.partial === true,
      owners: owners.map((o) => (Number.isInteger(o) && o >= 0 && o < teams.length ? o : -1)),
      records: s.records && typeof s.records === "object" ? s.records : {},
    });
  }
  if (!snapshots.length) return null;
  const events = snapshots.map(() => []);
  for (const e of Array.isArray(d.events) ? d.events : []) {
    if (!e || typeof e !== "object" || !isNum(e.cellsMoved) || e.cellsMoved <= 0) continue;
    const i = snapshots.findIndex((s) => s.phase === e.phase && s.week === e.week);
    if (i >= 0) events[i].push(e);
  }
  const ourTeam = typeof d.ourTeam === "string" && d.ourTeam ? d.ourTeam : usSchool();
  const us = teams.findIndex((t) => t.team === ourTeam);
  return {
    season: isNum(d.season) ? d.season : null,
    teams,
    snapshots,
    events,
    skipped,
    us: us >= 0 ? us : null,
    ourTeam,
    upcoming: (Array.isArray(d.upcoming) ? d.upcoming : []).filter((u) => typeof u === "string" && u),
    rules: typeof d.rules === "string" ? d.rules : null,
    schedule: Array.isArray(d.schedule) ? d.schedule.filter((g) => g && typeof g === "object") : [],
    runs: d.runs && typeof d.runs === "object" ? d.runs : {},
  };
}

const countOf = (owners, team) => {
  let n = 0;
  for (const o of owners) if (o === team) n += 1;
  return n;
};

/** The take of the week in words: "Florida 27, Texas 24. Florida took 159 cells, its full starting size, from the side of
 *  Texas's land nearest its own." */
function takeWords(view, e) {
  const winner = text(e.winner);
  const loser = text(e.loser);
  const quota = view.teams.find((t) => t.team === winner)?.quota;
  const score = isNum(e.winnerPoints) && isNum(e.loserPoints) ? `${winner} ${e.winnerPoints}, ${loser} ${e.loserPoints}. ` : "";
  if (e.rule === "winner_take_all") return `${score}${winner} took all of ${loser}'s land, ${cellWords(e.cellsMoved)}.`;
  if (isNum(quota) && e.cellsMoved >= quota) return `${score}${winner} took ${cellWords(e.cellsMoved)}, its full starting size, from the side of ${loser}'s land nearest its own.`;
  return `${score}${winner} took ${cellWords(e.cellsMoved)}, all ${loser} had left.`;
}

/** The words under the slider for snapshot i. */
export function captionFor(view, i) {
  const snap = view.snapshots[i];
  if (!snap) return "";
  const us = view.us;
  const usName = us !== null ? view.teams[us].team : null;
  const latest = view.snapshots[view.snapshots.length - 1];
  const tail = latest.partial && snap !== latest ? ` ${weekWords(latest.label)} is in progress.` : snap.partial ? " The week is still being played." : "";
  const total = snap.owners.length || 1;
  if (snap.label === "Start") {
    const n = us !== null ? countOf(snap.owners, us) : 0;
    return `The start: every school's land grown from its own campus, by its enrollment where there is room, one region each.${usName ? ` ${usName} starts with ${cellWords(n)}, ${((100 * n) / total).toFixed(1)}% of the map.` : ""}${tail}`;
  }
  const events = view.events[i] || [];
  if (snap.phase === "selection") {
    const moved = events.reduce((sum, e) => sum + e.cellsMoved, 0);
    const took = usName ? events.filter((e) => e.winner === usName).reduce((sum, e) => sum + e.cellsMoved, 0) : 0;
    const gave = usName ? events.filter((e) => e.loser === usName).reduce((sum, e) => sum + e.cellsMoved, 0) : 0;
    const ourWords = took ? ` ${usName} took ${fmtNum(took)}.` : gave ? ` ${usName}, not in the field, gave up ${fmtNum(gave)}.` : "";
    return `Selection Sunday: the twelve playoff teams split everyone else's land, ${cellWords(moved)}.${ourWords}${tail}`;
  }
  if (!events.length) return snap.partial ? `${weekWords(snap.label)} is in progress: no land has changed hands yet.` : `${weekWords(snap.label)}: no land changed hands.${tail}`;
  const mine = usName ? events.filter((e) => e.winner === usName || e.loser === usName) : [];
  const lead = (mine.length ? mine : events).slice().sort((a, b) => b.cellsMoved - a.cellsMoved)[0];
  const more = events.length - 1;
  const rest = more > 0 ? ` ${more} more ${more === 1 ? "game" : "games"} moved land.` : "";
  return `${weekWords(snap.label)}: ${takeWords(view, lead)}${rest}${tail}`;
}

/** One of our takes or losses in Taken and lost: { week, words, cells } (cells signed). */
export function eventLine(e, usName, label) {
  const won = e.winner === usName;
  const other = text(won ? e.loser : e.winner);
  const words = e.rule === "selection_sunday" ? (won ? `Selection Sunday: from ${other}` : `Selection Sunday: to ${other}`) : e.rule === "winner_take_all" ? (won ? `Took all of ${other}'s land` : `Lost all to ${other}`) : won ? `Took from ${other}` : `Lost to ${other}`;
  const tick = tickLabel(label);
  return { week: /^\d+$/.test(tick) ? `Wk ${tick}` : tick, words, cells: won ? e.cellsMoved : -e.cellsMoved };
}

/** Our events up to snapshot i in Taken and lost: Selection Sunday's many pieces as one line. */
function ourLines(view, i) {
  const us = view.us;
  if (us === null) return [];
  const usName = view.teams[us].team;
  const lines = [];
  for (let k = 0; k <= i; k += 1) {
    const mine = (view.events[k] || []).filter((e) => e.winner === usName || e.loser === usName);
    const label = view.snapshots[k].label;
    if (view.snapshots[k].phase === "selection" && mine.length) {
      const took = mine.filter((e) => e.winner === usName);
      const net = took.reduce((s, e) => s + e.cellsMoved, 0) - mine.filter((e) => e.loser === usName).reduce((s, e) => s + e.cellsMoved, 0);
      lines.push({ week: "Sel.", words: took.length ? `Selection Sunday: from ${took.length} ${took.length === 1 ? "school" : "schools"}` : "Selection Sunday: not in the field", cells: net });
      continue;
    }
    for (const e of mine) lines.push(eventLine(e, usName, label));
  }
  return lines;
}

const kickoffWords = (iso) => {
  const when = typeof iso === "string" ? new Date(iso) : null;
  if (!when || Number.isNaN(when.getTime())) return null;
  return when.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};

/** Our next game and what is at stake on the map, from the shown snapshot's land: "Next: a bye in week 8, then Georgia, Sat,
 *  Nov 1, 3:30 PM, at a neutral site. A win takes up to 159 of Georgia's 412 cells; a loss gives Georgia up to 230 of ours." */
export function nextWords(view, i) {
  const games = (view.schedule || []).filter((g) => typeof g.opponent === "string" && g.opponent);
  if (!games.length || view.us === null) return null;
  const ahead = games.filter((g) => g.completed !== true).sort((a, b) => String(a.start || "").localeCompare(String(b.start || "")));
  if (!ahead.length) return "No games left this season.";
  const next = ahead[0];
  const played = games.filter((g) => g.completed === true && g.seasonType === "regular" && isNum(g.week)).map((g) => g.week);
  const lastPlayed = played.length ? Math.max(...played) : null;
  const weeks = new Set(games.filter((g) => g.seasonType === "regular" && isNum(g.week)).map((g) => g.week));
  const byes = [];
  if (next.seasonType === "regular" && isNum(next.week) && lastPlayed !== null) for (let w = lastPlayed + 1; w < next.week; w += 1) if (!weeks.has(w)) byes.push(w);
  const where = next.neutral ? "at a neutral site" : next.home ? "at home" : "away";
  const when = kickoffWords(next.start);
  const lead = `Next: ${byes.length ? `a bye in week ${byes.join(" and ")}, then ` : ""}${next.opponent}${when ? `, ${when}` : ""}, ${where}.`;
  const owners = view.snapshots[i].owners;
  const usName = view.teams[view.us].team;
  const ourCells = countOf(owners, view.us);
  const them = view.teams.findIndex((t) => t.team === next.opponent);
  if (them < 0) return `${lead} ${next.opponent} holds no land on this map: nothing changes hands.`;
  const theirCells = countOf(owners, them);
  if (!ourCells && !theirCells) return `${lead} Neither side holds land: nothing changes hands.`;
  if (next.seasonType === "postseason" && view.snapshots.some((s) => s.phase === "selection")) {
    return `${lead} The winner takes all: ${next.opponent}'s ${fmtNum(theirCells)} cells or our ${fmtNum(ourCells)}.`;
  }
  const usQuota = view.teams[view.us].quota;
  const theirQuota = view.teams[them].quota;
  const win = isNum(usQuota) ? Math.min(usQuota, theirCells) : null;
  const loss = isNum(theirQuota) ? Math.min(theirQuota, ourCells) : null;
  const winWords = win === null ? null : theirCells ? `a win takes up to ${fmtNum(win)} of ${next.opponent}'s ${fmtNum(theirCells)} cells` : `a win takes nothing (${next.opponent} holds no land)`;
  const lossWords = loss === null ? null : ourCells ? `a loss gives ${next.opponent} up to ${fmtNum(loss)} of ours` : `a loss costs nothing (${usName} holds no land)`;
  const stake = [winWords, lossWords].filter(Boolean).join("; ");
  return stake ? `${lead} ${stake.charAt(0).toUpperCase()}${stake.slice(1)}.` : lead;
}

function svgEl(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) node.setAttribute(k, String(v));
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(typeof kid === "string" ? document.createTextNode(kid) : kid);
  return node;
}

function cssColor(name, fallback) {
  try {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return hexToRgb(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

const lightTheme = () => {
  try {
    return document.documentElement?.dataset?.theme === "light";
  } catch {
    return false;
  }
};

// --- the grid, fetched once per version and kept for the visit ---------------------------------------------------------

let held = null; // { version, geo }

async function loadGrid(version) {
  if (held && (!version || held.version === version)) return held.geo;
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), GRID_TIMEOUT_MS);
  try {
    const response = await fetch(`/api/imperialism/grid${version ? `?v=${encodeURIComponent(version)}` : ""}`, { signal: ctl.signal });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body?.data) throw new Error(body?.errors?.[0]?.message || `The server answered ${response.status}`);
    const geo = geometry(body.data);
    if (!geo) throw new Error("The map's grid came back damaged");
    held = { version: geo.version || version, geo };
    return geo;
  } catch (error) {
    throw new Error(error?.name === "AbortError" ? "The map's grid took too long to arrive" : text(error?.message) || "The map's grid could not be read");
  } finally {
    clearTimeout(timer);
  }
}

/** Forget the kept grid (tests). */
export function forgetGrid() {
  held = null;
}

// --- the page ------------------------------------------------------------------------------------------------------------

function sparkline(view, i) {
  const us = view.us;
  const values = view.snapshots.map((s) => countOf(s.owners, us));
  const n = values.length;
  const W = 352;
  const left = 14;
  const right = W - 14;
  const step = n > 1 ? (right - left) / (n - 1) : 0;
  const top = Math.max(1, ...values);
  const X = (k) => left + k * step;
  const Y = (v) => 88 - (v / top) * 62;
  const pts = (from, to) => values.slice(from, to + 1).map((v, k) => `${fixed(X(from + k))},${fixed(Y(v))}`).join(" ");
  const shown = values[i];
  const peak = values.indexOf(Math.max(...values));
  const low = values.reduce((best, v, k) => (k > 0 && v < values[best] ? k : best), Math.min(1, n - 1));
  const marked = new Map([[0, "start"], [peak, "peak"], [low, "low"], [i, "now"]]); // a later kind wins its index
  const every = n > 12 ? 2 : 1;
  const tickShown = (k) => k === 0 || k === i || k === n - 1 || (k % every === 0 && Math.abs(k - i) >= every && n - 1 - k >= every);
  const ticks = view.snapshots.map((s, k) => (tickShown(k) ? svgEl("text", { class: `imp-spark__tick${k === i ? " is-now" : k > i ? " is-later" : ""}`, x: fixed(X(k)), y: 110, "text-anchor": "middle" }, k === 0 ? "S" : tickLabel(s.label)) : null));
  const words = view.snapshots.map((s, k) => `${s.label === "Start" ? "start" : weekWords(s.label).toLowerCase()} ${values[k]}`).join(", ");
  return svgEl(
    "svg",
    { class: "imp-spark", viewBox: `0 0 ${W} 118`, role: "img", "aria-label": `${view.teams[us].team}'s cells by week: ${words}` },
    svgEl("line", { class: "imp-spark__base", x1: 8, y1: 88, x2: W - 8, y2: 88 }),
    i > 0 ? svgEl("polyline", { class: "imp-spark__line", points: pts(0, i) }) : null,
    i < n - 1 ? svgEl("polyline", { class: "imp-spark__line imp-spark__line--later", points: pts(i, n - 1) }) : null,
    ...values.map((v, k) => (k === i ? null : svgEl("circle", { class: `imp-spark__dot${k > i ? " is-later" : ""}`, cx: fixed(X(k)), cy: fixed(Y(v)), r: 3.5 }))),
    svgEl("circle", { class: "imp-spark__now", cx: fixed(X(i)), cy: fixed(Y(shown)), r: 6 }),
    ...[...marked.entries()].map(([k, kind]) => svgEl("text", { class: `imp-spark__num imp-spark__num--${kind}`, x: fixed(X(k)), y: fixed(kind === "low" && k !== i ? Y(values[k]) + 19 : Y(values[k]) - 10), "text-anchor": k === 0 ? "start" : k === n - 1 ? "end" : "middle" }, fmtNum(values[k]))),
    ...ticks,
  );
}

function swatch(color, isOurs) {
  return el("span", { class: `imp-swatch${isOurs ? " is-us" : ""}`, style: isOurs ? null : { background: color }, "aria-hidden": "true" });
}

function landTable(view, i, colors) {
  const snap = view.snapshots[i];
  const rows = standings(snap.owners, i > 0 ? view.snapshots[i - 1].owners : null, view.teams);
  if (!rows.length) return note("No school holds land on this map.");
  const top = rows.slice(0, TOP);
  const ourRow = view.us !== null ? rows.find((r) => r.index === view.us) : null;
  const pinned = ourRow && !top.includes(ourRow) ? ourRow : null;
  const row = (r) => el(
    "tr",
    { class: r.index === view.us ? "is-us" : null },
    el("td", { class: "imp-land__rank" }, String(r.rank)),
    el("td", { class: "txt imp-land__school" }, el("span", { class: "imp-land__who" }, swatch(colors[r.index], r.index === view.us), teamLink(r.team))),
    el("td", {}, fmtNum(r.cells)),
    el("td", { class: "imp-land__pct" }, `${r.pct.toFixed(1)}%`),
    el("td", { class: `imp-land__change${isNum(r.change) && r.change > 0 ? " is-up" : isNum(r.change) && r.change < 0 ? " is-down" : ""}` }, signed(r.change)),
  );
  return el(
    "div",
    { class: "stat-table-wrap" },
    el(
      "table",
      { class: "stat-table imp-land" },
      el("caption", { class: "sr-only" }, `Most land ${after(snap.label)}`),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", class: "imp-land__rank" }, "#"), el("th", { scope: "col", class: "txt" }, "School"), el("th", { scope: "col" }, "Cells"), el("th", { scope: "col" }, "Map"), el("th", { scope: "col" }, "Week"))),
      el("tbody", {}, ...top.map(row), pinned ? el("tr", { class: "imp-land__gap", "aria-hidden": "true" }, el("td", { colspan: 5 }, "…")) : null, pinned ? row(pinned) : null),
    ),
    el("p", { class: "imp-land__count" }, `${rows.length} of ${view.teams.length} schools hold land ${after(snap.label)}.`),
  );
}

function ourBody(view, i) {
  if (view.us === null) return note(`${text(view.ourTeam)} is not on this map.`);
  const snap = view.snapshots[i];
  const us = view.us;
  const usName = view.teams[us].team;
  const rows = standings(snap.owners, null, view.teams);
  const mine = rows.find((r) => r.index === us);
  const cells = mine ? mine.cells : 0;
  const pct = (100 * cells) / (snap.owners.length || 1);
  const record = recordOf(snap, usName);
  const startCells = countOf(view.snapshots[0].owners, us);
  const facts = [record, mine ? `${ordinal(mine.rank)} of the ${rows.length} schools holding land` : `no land ${after(snap.label)}`, `started with ${fmtNum(startCells)}`].filter(Boolean).join(" · ");
  const lines = ourLines(view, i);
  const next = i === view.snapshots.length - 1 ? nextWords(view, i) : null;
  return el(
    "div",
    { class: "imp-us" },
    el("div", { class: "imp-us__head" }, el("p", { class: "imp-us__cells" }, el("b", {}, fmtNum(cells)), el("span", {}, `${cells === 1 ? "cell" : "cells"} · ${pct.toFixed(1)}% of the map`)), el("p", { class: "imp-us__facts" }, facts)),
    el("figure", { class: "imp-us__chart" }, sparkline(view, i)),
    el("h3", { class: "imp-us__sub" }, "Taken and lost"),
    lines.length
      ? el("ul", { class: "imp-us__list" }, ...lines.map((l) => el("li", { class: "imp-us__line" }, el("span", { class: "imp-us__week" }, l.week), el("span", { class: "imp-us__words" }, l.words), el("b", { class: `imp-us__moved${l.cells > 0 ? " is-up" : l.cells < 0 ? " is-down" : ""}` }, signed(l.cells)))))
      : note(`No land has changed hands for ${usName} yet.`),
    next ? el("p", { class: "imp-us__next" }, next) : null,
  );
}

/** The slider's ticks: every snapshot, then what is still to come, faded. */
function ticksOf(view) {
  const have = view.snapshots.map((s, k) => ({ label: tickLabel(s.label), k, partial: s.partial }));
  const later = view.upcoming.map((u) => ({ label: tickLabel(u), k: null, partial: false }));
  return [...have, ...later];
}

// on a phone only every third week, Start, CCG and the final keep their words under the slider
const minor = (label) => (/^\d+$/.test(label) ? Number(label) % 3 !== 0 : ["Sel.", "R1", "QF", "SF"].includes(label));

function card(view, i, team, colors, close) {
  const snap = view.snapshots[i];
  const t = view.teams[team];
  const rows = standings(snap.owners, i > 0 ? view.snapshots[i - 1].owners : null, view.teams);
  const mine = rows.find((r) => r.index === team);
  const record = recordOf(snap, t.team);
  const events = view.events[i] || [];
  const took = events.filter((e) => e.winner === t.team);
  const lost = events.filter((e) => e.loser === t.team);
  const list = (es, who) => es.map((e) => `${text(e[who])} (${fmtNum(e.cellsMoved)})`).join(", ");
  const week = snap.label === "Start" ? "at the start" : "this week";
  const change = mine && isNum(mine.change) ? mine.change : null;
  return el(
    "div",
    { class: "imp-card", role: "dialog", "aria-label": `${t.team}'s territory` },
    el("div", { class: "imp-card__head" }, swatch(colors[team], team === view.us), teamLink(t.team), el("button", { class: "btn btn--quiet icon-btn imp-card__close", type: "button", "aria-label": `Close ${t.team}'s card`, onclick: close }, "×")),
    el("p", { class: "imp-card__facts" }, [record, mine ? `${ordinal(mine.rank)} by land` : `no land ${after(snap.label)}`].filter(Boolean).join(" · ")),
    mine ? el("p", { class: "imp-card__cells" }, el("b", {}, fmtNum(mine.cells)), el("span", {}, `${mine.cells === 1 ? "cell" : "cells"} · ${mine.pct.toFixed(1)}% of the map`)) : null,
    snap.label === "Start"
      ? el("p", { class: "imp-card__change" }, `Starts with ${fmtNum(mine ? mine.cells : 0)}, its enrollment's share`)
      : el("p", { class: `imp-card__change${change > 0 ? " is-up" : change < 0 ? " is-down" : ""}` }, change ? `${signed(change)} this week` : "No change this week"),
    typeof t.talentEdge === "string" && t.talentEdge ? el("p", { class: "imp-card__talent" }, t.talentEdge) : null,
    snap.label === "Start"
      ? null
      : el(
          "p",
          { class: "imp-card__events" },
          took.length ? el("span", {}, "Took from: ", el("b", {}, list(took, "loser"))) : el("span", { class: "imp-card__none" }, `Took from: none ${week}`),
          el("br"),
          lost.length ? el("span", {}, "Lost to: ", el("b", {}, list(lost, "winner"))) : el("span", { class: "imp-card__none" }, `Lost to: none ${week}`),
        ),
  );
}

function runFoot(view) {
  const good = view.runs?.lastGood;
  const last = view.runs?.last;
  const when = (iso) => {
    const d = typeof iso === "string" ? new Date(iso) : null;
    return d && !Number.isNaN(d.getTime()) ? d.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : null;
  };
  if (last && last.status === "failed" && good) { // the newest run failed after a good one: say so, and how old this map is
    return el("p", { class: "imp-foot imp-foot--stale", role: "status" }, `The last run failed${when(last.startedAt) ? ` ${when(last.startedAt)}` : ""}: ${text(last.message)}. This map is from ${when(good.finishedAt) || "the last good run"}; the server tries again in three hours.`);
  }
  if (last && last.status === "running") return el("p", { class: "imp-foot" }, "The map is being worked out again now.");
  return good && when(good.finishedAt) ? el("p", { class: "imp-foot" }, `Worked out ${when(good.finishedAt)}. The server works it out again Sundays from 6 AM.`) : null;
}

function mapState(view, geo, state) {
  const colors = view.colors;
  const W = geo.width;
  const H = geo.height;
  const land = svgEl("g", { class: "imp-map__land" });
  const borders = svgEl("path", { class: "imp-map__borders", d: "" });
  const ourBorder = svgEl("path", { class: "imp-map__our-border", d: "" });
  const ring = svgEl("circle", { class: "imp-map__ring", r: 9, cx: -50, cy: -50 });
  const lead = svgEl("line", { class: "imp-map__lead", x1: -50, y1: -50, x2: -50, y2: -50 });
  const svg = svgEl(
    "svg",
    { class: "imp-map__svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "" },
    land,
    geo.states ? svgEl("path", { class: "imp-map__states", d: geo.states }) : null,
    borders,
    ourBorder,
    lead,
    ring,
  );
  const marks = el("div", { class: "imp-map__marks", "aria-hidden": "true" });
  const stage = el("div", { class: "imp-stage" }, svg, marks);
  const paths = new Map();
  const drawnD = new Map();

  function paint(i) {
    const snap = view.snapshots[i];
    const owners = snap.owners;
    const byTeam = view.teams.map(() => []);
    for (let c = 0; c < owners.length; c += 1) if (owners[c] >= 0) byTeam[owners[c]].push(c);
    for (let t = 0; t < byTeam.length; t += 1) {
      const cells = byTeam[t];
      let path = paths.get(t);
      if (!cells.length) {
        if (path) {
          path.remove();
          paths.delete(t);
          drawnD.delete(t);
        }
        continue;
      }
      const d = cells.map((c) => geo.hex[c]).join("");
      if (!path) {
        path = svgEl("path", { class: t === view.us ? "imp-map__team imp-map__team--us" : "imp-map__team", "data-team": view.teams[t].team });
        if (t !== view.us) path.setAttribute("fill", colors[t]);
        paths.set(t, path);
        land.append(path); // territories never overlap: the order of the paths does not show
      }
      if (drawnD.get(t) !== d) {
        path.setAttribute("d", d);
        drawnD.set(t, d);
      }
    }
    const lines = [];
    const ourLinesD = [];
    for (let k = 0; k < geo.edgeA.length; k += 1) {
      const a = owners[geo.edgeA[k]];
      const b = owners[geo.edgeB[k]];
      if (a === b) continue;
      (view.us !== null && (a === view.us || b === view.us) ? ourLinesD : lines).push(geo.segs[k]);
    }
    borders.setAttribute("d", lines.join(""));
    ourBorder.setAttribute("d", ourLinesD.join(""));
    // logos on the big territories and ours, anchored at each school's campus (owner 2026-10-30), else its land nearest home
    const pieces = new Map();
    const shown = [];
    byTeam.forEach((cells, t) => {
      if (!cells.length || (cells.length < LOGO_CELLS && t !== view.us)) return;
      const piece = largestPiece(cells, owners, geo, t);
      const at = anchorCell(cells, owners, geo, t, view.teams[t]?.home);
      pieces.set(t, { ...piece, middle: at });
      if (at !== null && (t === view.us || piece.size >= LOGO_PIECE)) shown.push([t, at]);
    });
    marks.replaceChildren(...shown.map(([t, at]) => {
      const team = view.teams[t];
      // on the campus point itself while the school holds its campus cell (owner 2026-11-01: "still not centered on each schools campus")
      const onCampus = at === team?.home && Array.isArray(team?.campus) && isNum(team.campus[0]) && isNum(team.campus[1]);
      const [mx, my] = onCampus ? team.campus : [geo.xs[at], geo.ys[at]];
      const mark = el("span", { class: `imp-mark${t === view.us ? " is-us" : ""}`, style: { left: `${(100 * mx) / W}%`, top: `${(100 * my) / H}%` } }, team.logo || team.logoDark ? teamLogo(team, { size: t === view.us ? 24 : 18, lazy: false }) : el("b", {}, text(team.abbreviation) || team.team.slice(0, 4)));
      return mark;
    }));
    const board = standings(owners, null, view.teams);
    const ourRow = view.us !== null ? board.find((r) => r.index === view.us) : null;
    const leader = board[0];
    svg.setAttribute("aria-label", `The map of FBS land ${after(snap.label)}${view.season ? ` of ${view.season}` : ""}: ${leader ? `${leader.team} holds the most, ${fmtNum(leader.cells)} cells` : "no school holds land"}${ourRow && ourRow !== leader ? `; ${ourRow.team} ${fmtNum(ourRow.cells)}, ${ordinal(ourRow.rank)} by land` : ""}.`);
    state.pieces = pieces;
    state.byTeam = byTeam;
  }

  function point(event) {
    const rect = svg.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) return null;
    return { x: ((event.clientX - rect.left) / rect.width) * W, y: ((event.clientY - rect.top) / rect.height) * H, scale: W / rect.width };
  }

  svg.addEventListener("click", (event) => {
    const p = point(event);
    if (!p) return;
    const cell = cellAt(geo, p.x, p.y, 10 * p.scale);
    const owner = cell !== null ? view.snapshots[state.index].owners[cell] : -1;
    if (owner >= 0) state.select(owner, cell);
    else state.select(null, null);
  });

  return { stage, svg, ring, lead, paint };
}

function render(envelope, container, state) {
  state.dropCard();
  state.dropCard = () => {};
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  if (data.available !== true) {
    const message = text(data.message) || "The Imperialism Map has not been worked out yet.";
    const page = el(
      "div",
      { class: "page page--wide imp" },
      band({ id: "imp-map", title: "Imperialism Map", collapsible: false, state: { status: data.failed ? "error" : "empty", message }, errorLead: "No map yet." }),
    );
    container.replaceChildren(page);
    return;
  }
  const version = typeof data.gridVersion === "string" ? data.gridVersion : null;
  const geo = held && (!version || held.version === version) ? held.geo : null;
  if (!geo) {
    container.replaceChildren(el("div", { class: "page page--wide imp" }, band({ id: "imp-map", title: "Imperialism Map", collapsible: false, state: { status: "loading" }, skeleton: () => el("div", { class: "skel imp-skel" }) })));
    loadGrid(version).then(
      () => state.redraw(),
      (error) => {
        if (!state.live()) return;
        container.replaceChildren(errorPanel("Imperialism Map", text(error?.message), () => state.redraw()));
      },
    );
    return;
  }
  const view = state.views.get(data) || prepare(data, geo);
  if (!view) {
    container.replaceChildren(el("div", { class: "page page--wide imp" }, band({ id: "imp-map", title: "Imperialism Map", collapsible: false, state: { status: "error", message: "Every week of the map came back damaged. The server works it out again Sundays from 6 AM." }, errorLead: "No map to draw." })));
    return;
  }
  if (!view.colors) {
    const light = lightTheme();
    view.colors = colorsFor(view.teams, view.snapshots.map((s) => s.owners), geo, { panel: cssColor("--panel", light ? "#FFFFFF" : PANEL_DARK), us: view.us, usColor: cssColor("--team-us", US_DEFAULT), light });
    state.views.set(data, view);
  }
  const last = view.snapshots.length - 1;
  if (state.index === null || state.index > last || state.wasLast) state.index = last;
  if (state.selected !== null && state.selected >= view.teams.length) state.selected = null;

  const map = mapState(view, geo, state);
  const ticks = ticksOf(view);
  const columns = ticks.length;
  const center = (k) => `${((100 * (k + 0.5)) / columns).toFixed(3)}%`;
  const fill = el("div", { class: "imp-slider__fill" });
  const future = el("div", { class: "imp-slider__later" });
  const thumb = el("div", { class: "imp-slider__thumb", "aria-hidden": "true" });
  const tickRow = el("div", { class: "imp-ticks", style: { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` } }, ...ticks.map((t) => el("span", { class: `imp-tick${t.k === null ? " is-later" : ""}${t.partial ? " is-partial" : ""}${minor(t.label) ? " is-minor" : ""}` }, t.label)));
  const slider = el(
    "div",
    { class: "imp-slider", role: "slider", tabindex: "0", "aria-label": "Week of the season", "aria-valuemin": "0", "aria-valuemax": String(last) },
    el("div", { class: "imp-slider__track" }, future, fill, thumb),
    tickRow,
  );
  const play = el("button", { class: "imp-play", type: "button", "aria-label": "Play the season" });
  const caption = el("p", { class: "imp-caption", "aria-live": "polite" });
  const landBody = el("div", { class: "imp-land-body" });
  const usBody = el("div", { class: "imp-us-body" });
  const mapSummary = el("span", {});
  const landSummary = el("span", {});
  const usSummary = el("span", {});
  let cardNode = null;

  function placeCard(i) {
    cardNode?.remove();
    cardNode = null;
    map.ring.setAttribute("cx", "-50");
    map.lead.setAttribute("x1", "-50");
    map.lead.setAttribute("x2", "-50");
    const team = state.selected;
    if (team === null) return;
    const owners = view.snapshots[i].owners;
    let cell = state.cell !== null && owners[state.cell] === team ? state.cell : state.pieces?.get(team)?.middle ?? null;
    if (cell === null && state.byTeam?.[team]?.length) cell = anchorCell(state.byTeam[team], owners, geo, team, view.teams[team]?.home);
    cardNode = card(view, i, team, view.colors, () => state.select(null, null));
    const width = map.stage.clientWidth || 0;
    const wide = width >= WIDE;
    if (wide) map.stage.append(cardNode);
    else {
      // a phone: a sheet from the bottom, on the page itself (a band is a container, which would hold a fixed box inside it)
      cardNode.classList.add("imp-card--sheet");
      cardNode.style.zIndex = layerZ();
      document.body.append(cardNode);
    }
    if (cell === null) return;
    map.ring.setAttribute("cx", fixed(geo.xs[cell]));
    map.ring.setAttribute("cy", fixed(geo.ys[cell]));
    if (!wide) return;
    const height = map.stage.clientHeight || 0;
    const scale = width / geo.width;
    const px = geo.xs[cell] * scale;
    const py = geo.ys[cell] * scale;
    const cardH = cardNode.offsetHeight || 180;
    const rightSide = px + 40 + CARD_W <= width - 8;
    const left = rightSide ? px + 40 : Math.max(8, px - 40 - CARD_W);
    const top = Math.min(Math.max(8, py - cardH / 2), Math.max(8, height - cardH - 8));
    cardNode.style.left = `${Math.round(left)}px`;
    cardNode.style.top = `${Math.round(top)}px`;
    const edgeX = rightSide ? left : left + CARD_W;
    const edgeY = Math.min(Math.max(py, top + 16), top + cardH - 16);
    const toward = Math.hypot(edgeX - px, edgeY - py) || 1;
    const r = 9 * scale;
    map.lead.setAttribute("x1", fixed((px + ((edgeX - px) / toward) * r) / scale));
    map.lead.setAttribute("y1", fixed((py + ((edgeY - py) / toward) * r) / scale));
    map.lead.setAttribute("x2", fixed(edgeX / scale));
    map.lead.setAttribute("y2", fixed(edgeY / scale));
  }

  function show(i) {
    state.index = i;
    state.wasLast = i === last;
    const snap = view.snapshots[i];
    map.paint(i);
    fill.style.width = center(i);
    future.style.width = center(last);
    thumb.style.left = center(i);
    slider.setAttribute("aria-valuenow", String(i));
    slider.setAttribute("aria-valuetext", `${weekWords(snap.label)}${snap.partial ? ", in progress" : ""}`);
    tickRow.querySelectorAll(".imp-tick").forEach((node, k) => {
      node.classList.toggle("is-current", k === i);
      node.classList.toggle("is-near", Math.abs(k - i) === 1); // on a phone the current week's neighbors step aside
    });
    caption.textContent = captionFor(view, i);
    const rows = standings(snap.owners, null, view.teams);
    const ourRow = view.us !== null ? rows.find((r) => r.index === view.us) : null;
    mapSummary.textContent = `${snap.label === "Start" ? "The start" : weekWords(snap.label)}${snap.partial ? " (in progress)" : ""} · ${rows.length} of ${view.teams.length} schools hold land`;
    landSummary.textContent = after(snap.label);
    usSummary.textContent = ourRow ? `${ordinal(ourRow.rank)} by land` : "no land";
    landBody.replaceChildren(landTable(view, i, view.colors));
    usBody.replaceChildren(ourBody(view, i));
    placeCard(i);
  }

  state.dropCard = () => {
    cardNode?.remove();
    cardNode = null;
  };
  state.select = (team, cell) => {
    state.selected = team;
    state.cell = cell;
    placeCard(state.index);
  };
  state.show = (i) => show(Math.max(0, Math.min(last, i)));
  state.stop = () => {
    clearTimeout(state.timer);
    state.timer = null;
    play.classList.remove("is-playing");
    play.setAttribute("aria-label", "Play the season");
  };
  play.addEventListener("click", () => {
    if (state.timer !== null) {
      state.stop();
      return;
    }
    if (state.index >= last) show(0);
    play.classList.add("is-playing");
    play.setAttribute("aria-label", "Pause");
    const step = () => {
      if (!state.live() || state.index >= last) {
        state.stop();
        return;
      }
      show(state.index + 1);
      state.timer = setTimeout(step, PLAY_MS);
    };
    state.timer = setTimeout(step, PLAY_MS);
  });
  const fromPointer = (event) => {
    const track = slider.getBoundingClientRect();
    if (!track || !track.width) return;
    const at = Math.round(((event.clientX - track.left) / track.width) * columns - 0.5);
    const k = Math.max(0, Math.min(last, at));
    if (k !== state.index) {
      state.stop();
      show(k);
    }
  };
  let dragging = false;
  slider.addEventListener("pointerdown", (event) => {
    dragging = true;
    slider.setPointerCapture?.(event.pointerId);
    fromPointer(event);
  });
  slider.addEventListener("pointermove", (event) => {
    if (dragging) fromPointer(event);
  });
  const release = (event) => {
    dragging = false;
    slider.releasePointerCapture?.(event.pointerId);
  };
  slider.addEventListener("pointerup", release);
  slider.addEventListener("pointercancel", release);
  slider.addEventListener("keydown", (event) => {
    const moves = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -3, PageUp: 3 };
    let k = null;
    if (event.key in moves) k = state.index + moves[event.key];
    else if (event.key === "Home") k = 0;
    else if (event.key === "End") k = last;
    if (k === null) return;
    event.preventDefault();
    state.stop();
    show(Math.max(0, Math.min(last, k)));
  });

  const mapBand = band({
    id: "imp-map",
    title: "Imperialism Map",
    foldable: true,
    collapsible: true,
    summary: mapSummary,
    state: { status: "ready" },
    body: () =>
      el(
        "div",
        { class: "imp-map" },
        map.stage,
        el("div", { class: "imp-controls" }, play, slider),
        caption,
        view.rules ? el("p", { class: "imp-rules" }, view.rules) : null,
        view.skipped ? note(`${view.skipped} ${view.skipped === 1 ? "week" : "weeks"} of the map came back damaged and are left out.`, { kind: "error" }) : null,
        runFoot(view),
      ),
  });
  const landBand = band({ id: "imp-land", title: "Most land", foldable: true, collapsible: true, summary: landSummary, state: { status: "ready" }, body: () => landBody });
  const usBand = band({ id: "imp-us", title: text(ours().name) || text(view.ourTeam), foldable: true, collapsible: true, summary: usSummary, state: { status: "ready" }, body: () => usBody });
  const page = el("div", { class: "page page--wide imp" }, mapBand, el("div", { class: "imp-pair" }, landBand, usBand));
  container.replaceChildren(page);
  show(state.index);
}

export function createImperialismView({ onStatus } = {}) {
  let alive = false;
  let lastEnvelope = null;
  let target = null;
  const state = {
    index: null,
    wasLast: true,
    selected: null,
    cell: null,
    timer: null,
    views: new WeakMap(),
    live: () => alive,
    dropCard: () => {},
    select: () => {},
    show: () => {},
    stop: () => {},
    redraw: () => {
      if (alive && lastEnvelope && target) render(lastEnvelope, target, state);
    },
  };
  const onKey = (event) => {
    if (event.key === "Escape" && state.selected !== null) state.select(null, null);
  };
  const inner = poller({
    url: "/api/imperialism/now",
    onStatus,
    render: (envelope, container) => {
      lastEnvelope = envelope;
      target = container;
      state.stop();
      render(envelope, container, state);
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Imperialism Map", message, retry)),
    loadingDetail: "Every week's map",
    renderLoading: () => el("div", { class: "page page--wide imp" }, el("div", { class: "skel imp-skel" }), el("div", { class: "skel skel--block" })),
  });
  return {
    mount(node) {
      alive = true;
      document.addEventListener("keydown", onKey);
      return inner.mount(node);
    },
    refresh: () => inner.refresh(),
    unmount() {
      alive = false;
      state.stop();
      state.dropCard();
      document.removeEventListener("keydown", onKey);
      inner.unmount();
    },
  };
}
