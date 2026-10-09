// Lineups and depth in one view (Phase 19, owner 2026-10-08: "combine the line-up and the depth chart", "visualize offense vs
// defense for each team as far as the roster goes"). The same notes chart feeds both: the starter at every slot and the names
// behind him. Here each unit is ONE table, the starter with his season chips and note and, in the last column, the rest of the
// depth in order, laid out as the matchups the owner chose (our offense beside their defense, then the reverse, then the
// specialists). Above it, how experienced each unit's starters are: counts by class and the average class, our offense
// against their defense and so on, so a young line or a veteran secondary shows at a glance. Tables only (design rule 12).
//
//   lineupBlock({ lineups, us, them, availability, onPlayer })   the matchup rows of combined tables, or the empty note
//   experienceBlock({ lineups, us, them })                       the starters' experience by unit, or null when no chart
//   classNumber(label) -> 1..4 | null                            "FR" 1 ... "SR" 4; "RS SO" 2; "GR" 4 (fifth year is a senior)

import { usSchool } from "../identity.js";
import { DASH, el, isNum, obj, str, text } from "./dom.js";
import { note, subhead } from "./states.js";
import { statTable } from "./stat-table.js";
import { availabilityFor, hasLineups, lineupSlots, lineupStarters } from "./lineups.js";
import { plainChip } from "./stat-labels.js";

const CLASS_NUMBERS = { FR: 1, SO: 2, JR: 3, SR: 4, GR: 4 };
const PAIRS = [
  [["us", "offense"], ["them", "defense"]],
  [["them", "offense"], ["us", "defense"]],
  [["us", "special teams"], ["them", "special teams"]],
];

export function classNumber(label) {
  const word = String(label || "").toUpperCase().replace(/^RS\s+/, "").replace(/[^A-Z]/g, "");
  return CLASS_NUMBERS[word] ?? null;
}

function who(team, fallback) {
  return str(obj(team).abbreviation) || str(obj(team).school) || fallback;
}

function depthText(players, availability) {
  const names = players.map((p) => {
    const listed = availabilityFor(availability, p.name);
    const status = listed ? str(listed.status) : null;
    return `${text(p.name)}${str(p.classYear) ? ` (${p.classYear})` : ""}${status ? `, ${status.toLowerCase()}` : ""}`;
  });
  return names.length ? names.join(", ") : DASH;
}

function chipsCell(row) {
  const chips = (Array.isArray(row.chips) ? row.chips : []).map(plainChip).filter(Boolean);
  return chips.length ? el("div", { class: "chips lineup__chips" }, chips.map((chip) => el("span", { class: "chip" }, chip))) : DASH;
}

function noteCell(row) {
  if (!row.listed) return str(row.note) || DASH;
  const status = str(row.listed.status) || "Listed";
  const detail = str(row.listed.note);
  return el("span", {}, el("span", { class: `avail avail--${status.toLowerCase().replace(/[^a-z]+/g, "")}` }, status), detail ? ` ${detail}` : "");
}

function combinedTable(lineup, unit, availability, onPlayer, owner) {
  const slots = lineupSlots(lineup).filter((s) => s.unit === unit && s.players.length);
  if (!slots.length) return note("No chart written for this unit.");
  const rows = slots.map((s) => {
    const starter = s.players[0];
    return {
      slot: s.slot,
      number: isNum(starter.number) ? starter.number : null,
      name: text(starter.name),
      classYear: str(starter.classYear) || "",
      chips: Array.isArray(starter.chips) ? starter.chips : [],
      playerId: str(starter.playerId),
      note: str(starter.note),
      listed: availabilityFor(availability, starter.name),
      player: starter,
      isUs: owner === "us",
      depth: depthText(s.players.slice(1), availability),
    };
  });
  const noted = rows.some((r) => r.note || r.listed);
  const columns = [
    { key: "slot", label: "Slot", kind: "text" },
    { key: "number", label: "No." },
    { key: "name", label: "Starter", kind: "text", sub: "classYear" },
    { key: "chips", label: "Season", kind: "text", render: chipsCell },
    ...(noted ? [{ key: "note", label: "Note", kind: "text", render: noteCell }] : []),
    { key: "depth", label: "Then, in order", kind: "text" },
  ];
  const tap = typeof onPlayer === "function" ? (row) => (row.playerId ? onPlayer(row) : null) : undefined;
  return statTable({ compact: true, sortable: false, columns, rows, caption: `${unit} lineup and depth`, onRowTap: tap, rowClass: (row) => (row.playerId ? null : "is-static") });
}

function sideOf(team, label, owner, unit, lineup, availability, onPlayer) {
  const name = str(obj(team).school) || label;
  return el("div", { class: "lineups__side" }, subhead(`${name} ${unit}`, { team: str(obj(team).school), side: owner }), combinedTable(lineup, unit, availability, onPlayer, owner));
}

export function lineupBlock({ lineups, us, them, availability, onPlayer } = {}) {
  const l = obj(lineups);
  if (!hasLineups(l)) return note("No lineups for this game yet. They come with the game's notes: both teams' published depth charts.");
  const themName = str(obj(them).school) || str(obj(l.them).team) || "Opponent";
  return el(
    "div",
    { class: "lineups" },
    experienceBlock({ lineups: l, us, them }),
    PAIRS.map((pair) => el("div", { class: "twocol lineups__pair" }, pair.map(([owner, unit]) => sideOf(owner === "us" ? us : them, owner === "us" ? usSchool() : themName, owner, unit, owner === "us" ? l.us : l.them, availability, onPlayer)))),
  );
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
    columns: [
      { key: "unit", label: "Unit", kind: "text" },
      { key: "starters", label: "Starters" },
      { key: "fr", label: "FR" },
      { key: "so", label: "SO" },
      { key: "jr", label: "JR" },
      { key: "sr", label: "SR" },
      { key: "avg", label: "Avg class", format: "1f" },
    ],
    rows,
    caption: "Experience of the starters (1 = freshman, 4 = senior)",
    rowClass: (row) => (row.owner === "us" ? "is-us" : null),
  });
  return el("div", { class: "lineups__experience" }, subhead("Experience of the starters"), table);
}

