// Starting lineups and depth charts (owner request 2026-10-02: "add the depth charts and starting
// lineups to the live program"). CFBD publishes no depth order, so both come from the per-game notes
// file: the weekly task copies each team's published chart into `lineups.us` and `lineups.them`
// (slots in the printed order, the first name at a slot the starter). The Game program and the Live
// sheet draw the same two blocks from it. Owner directions the same day: lay the units out as
// matchups (our offense beside the opponent's defense, then the reverse, then the specialists);
// season stat chips on every starter, like the impact cards, no photos (the server attaches `chips`
// and `playerId` by name, app/services/lineup_stats.py); and the availability report verifies the
// chart, so a listed starter shows his status in the Note column. Tables only (design rule 12).
//
//   lineupSlots(lineup)                      the object slots of a team's chart, each with its object players
//   lineupStarters(lineup)                   [{ unit, slot, player }] the first name at every slot
//   lineupSummary(lineups)                   "Ourlads, updated Sep 26" for a band's summary, or ""
//   availabilityFor(rows, name)              the availability row for a player's name, or null
//   startersBlock({ lineups, us, them, availability, onPlayer })   three matchup rows of starters tables, or the empty note
//   depthBlock({ lineups, us, them, availability })                three matchup rows of depth tables, or the note
//
// us / them: { school, abbreviation } from the program's team blocks. onPlayer(row) opens a card for a
// starter with a playerId. Anything missing renders as a dash.

import { usSchool } from "../identity.js";
import { DASH, el, fmtDate, isNum, text } from "./dom.js";
import { plainChip } from "./stat-labels.js";
import { note, subhead } from "./states.js";
import { statTable } from "./stat-table.js";

const UNITS = ["offense", "defense", "special teams"];
const DEPTH_HEADS = ["Starter", "Second", "Third", "Fourth", "Fifth"];
const STATUS_CLASS = { out: "out", doubtful: "doubtful", questionable: "questionable", probable: "probable", available: "available" };
const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);
export const LINEUPS_EMPTY = "No lineups for this game yet. The pre-game notes task copies both teams' published depth charts into the notes file; or add them by hand.";

function obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function records(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object" && !Array.isArray(row)) : [];
}

function str(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** 'TJ Shanahan Jr.' -> 'tj shanahan', like the server's name_key. */
function nameKey(name) {
  if (typeof name !== "string") return "";
  const words = name
    .toLowerCase()
    .replace(/-/g, " ")
    .replace(/[^a-z0-9 ]/g, "")
    .split(/\s+/)
    .filter(Boolean);
  while (words.length && SUFFIXES.has(words[words.length - 1])) words.pop();
  return words.join(" ");
}

/** The unit a slot belongs to, in the three groups the layout pairs up: "offense", "defense" or "special teams". */
function unitOf(slot) {
  const unit = str(slot.unit);
  if (!unit) return "offense";
  const low = unit.toLowerCase();
  if (low.startsWith("def")) return "defense";
  if (low.startsWith("spec") || low.startsWith("st") || low.includes("kick")) return "special teams";
  return "offense";
}

/** The chart's object slots, each with only its object players and a printed slot label. */
export function lineupSlots(lineup) {
  return records(obj(lineup).slots)
    .filter((slot) => str(slot.slot))
    .map((slot) => ({ unit: unitOf(slot), slot: slot.slot.trim(), players: records(slot.players).filter((p) => str(p.name)) }));
}

/** The starting lineup: the first name at every slot that has one. */
export function lineupStarters(lineup) {
  return lineupSlots(lineup)
    .filter((slot) => slot.players.length)
    .map((slot) => ({ unit: slot.unit, slot: slot.slot, player: slot.players[0] }));
}

/** The availability row whose name matches, or null (the report verifies the chart: owner direction). */
export function availabilityFor(rows, name) {
  const key = nameKey(name);
  if (!key) return null;
  return records(rows).find((row) => nameKey(row.name) === key) || null;
}

function hasChart(lineup) {
  return lineupSlots(lineup).some((slot) => slot.players.length);
}

/** "Ourlads, updated Sep 26": the file-level source, else the first team's; "" when nothing is written. */
export function lineupSummary(lineups) {
  const l = obj(lineups);
  if (!hasChart(l.us) && !hasChart(l.them)) return "";
  const from = str(l.source) || str(obj(l.us).source) || str(obj(l.them).source);
  const when = str(l.updatedAt) || str(obj(l.us).updatedAt) || str(obj(l.them).updatedAt);
  return [from, when ? `updated ${fmtDate(when, "short")}` : null].filter(Boolean).join(", ");
}

function playerText(p, availability) {
  const number = isNum(p.number) ? `#${p.number} ` : "";
  const cls = str(p.classYear);
  const listed = availabilityFor(availability, p.name);
  const status = listed ? str(listed.status) : null;
  return `${number}${text(p.name)}${cls ? ` (${cls})` : ""}${status ? `, ${status.toLowerCase()}` : ""}`;
}

function sourceLine(lineup) {
  const l = obj(lineup);
  const from = str(l.source);
  const when = str(l.updatedAt);
  if (!from && !when) return null;
  const link = str(l.sourceUrl) && /^https?:\/\//.test(l.sourceUrl) ? el("a", { href: l.sourceUrl, target: "_blank", rel: "noopener" }, from || "Source") : from ? text(from) : null;
  return el("p", { class: "note" }, "Source: ", link, when ? `${link ? ", " : ""}updated ${fmtDate(when, "short")}.` : ".");
}

function chipsCell(row) {
  const chips = (Array.isArray(row.chips) ? row.chips : []).map(plainChip).filter(Boolean);
  return chips.length ? el("div", { class: "chips lineup__chips" }, chips.map((chip) => el("span", { class: "chip" }, chip))) : DASH;
}

/** The Note cell: the availability report's status (coloured like the report) and note, else the chart's own note. */
function noteCell(row) {
  if (!row.listed) return str(row.note) || DASH;
  const status = str(row.listed.status) || "Listed";
  const cls = STATUS_CLASS[status.toLowerCase()];
  const detail = str(row.listed.note);
  return el("span", {}, el("span", { class: `avail${cls ? ` avail--${cls}` : ""}` }, status), detail ? ` ${detail}` : "");
}

/** One team's starters on one unit: Slot, No., Starter (class under it), Season chips, Note (where anyone has one). */
function startersTable(lineup, unit, availability, onPlayer, who) {
  const starters = lineupStarters(lineup).filter((s) => s.unit === unit);
  if (!starters.length) return note("No chart written for this unit.");
  const rows = starters.map((s) => ({
    slot: s.slot,
    number: isNum(s.player.number) ? s.player.number : null,
    name: text(s.player.name),
    classYear: str(s.player.classYear) || "",
    chips: Array.isArray(s.player.chips) ? s.player.chips : [],
    playerId: str(s.player.playerId),
    note: str(s.player.note),
    listed: availabilityFor(availability, s.player.name),
    player: s.player,
    isUs: who === "us",
  }));
  const noted = rows.some((r) => r.note || r.listed);
  const columns = [
    { key: "slot", label: "Slot", kind: "text" },
    { key: "number", label: "No." },
    { key: "name", label: "Starter", kind: "text", sub: "classYear" },
    { key: "chips", label: "Season", kind: "text", render: chipsCell },
    ...(noted ? [{ key: "note", label: "Note", kind: "text", render: noteCell }] : []),
  ];
  const tap = typeof onPlayer === "function" ? (row) => (row.playerId ? onPlayer(row) : null) : undefined;
  return statTable({ compact: true, sortable: false, columns, rows, caption: `${unit} starters`, onRowTap: tap, rowClass: (row) => (row.playerId ? null : "is-static") });
}

/** One team's full chart on one unit: a row per slot, the names across (Starter, Second, Third...). */
function depthTable(lineup, unit, availability) {
  const slots = lineupSlots(lineup).filter((slot) => slot.unit === unit && slot.players.length);
  if (!slots.length) return note("No chart written for this unit.");
  const deep = Math.min(DEPTH_HEADS.length, Math.max(2, ...slots.map((slot) => slot.players.length)));
  const columns = [{ key: "slot", label: "Slot", kind: "text" }, ...DEPTH_HEADS.slice(0, deep).map((head, i) => ({ key: `p${i}`, label: head, kind: "text" }))];
  const rows = slots.map((s) => {
    const row = { slot: s.slot };
    for (let i = 0; i < deep; i += 1) row[`p${i}`] = s.players[i] ? playerText(s.players[i], availability) : DASH;
    return row;
  });
  return statTable({ compact: true, sortable: false, columns, rows, caption: `${unit} depth chart` });
}

/** "Swampwater Tech offense" over a side of a pair; the team name is its link. */
function unitHead(team, fallback, side, unit) {
  const name = str(obj(team).school) || fallback;
  return subhead(`${name} ${unit}`, { team: str(obj(team).school), side });
}

/**
 * The three matchup rows: our offense | opponent defense, opponent offense | our defense, our specialists |
 * opponent specialists. draw(lineup, unit) fills one side; the pair's scheme and source lines sit under it.
 */
function matchups(lineups, us, them, draw) {
  // draw(lineup, unit, who): who is "us" or "them", so a tapped row knows whose card to open
  const l = obj(lineups);
  if (!hasChart(l.us) && !hasChart(l.them)) return note(LINEUPS_EMPTY);
  const themName = str(obj(them).school) || str(obj(l.them).team) || "Opponent";
  const pairs = [
    [["us", "offense"], ["them", "defense"]],
    [["them", "offense"], ["us", "defense"]],
    [["us", "special teams"], ["them", "special teams"]],
  ];
  const side = ([who, unit]) => {
    const team = who === "us" ? us : them;
    return el("div", { class: "lineups__side" }, unitHead(team, who === "us" ? usSchool() : themName, who, unit), draw(who === "us" ? l.us : l.them, unit, who));
  };
  const foot = (who) => {
    const lineup = obj(l[who]);
    const scheme = str(lineup.scheme);
    const source = sourceLine(lineup);
    if (!scheme && !source) return null;
    const name = who === "us" ? str(obj(us).school) || usSchool() : themName;
    return el("div", { class: "lineups__foot" }, scheme ? el("p", { class: "note lineup__scheme" }, `${name} chart heading: ${scheme}.`) : null, source);
  };
  return el(
    "div",
    { class: "lineups" },
    pairs.map((pair) => el("div", { class: "twocol lineups__pair" }, pair.map(side))),
    el("div", { class: "twocol lineups__pair" }, foot("us"), foot("them")),
  );
}

/** The starting lineups as three matchup rows (our unit first on the left), or the empty note. */
export function startersBlock({ lineups, us, them, availability, onPlayer } = {}) {
  return matchups(lineups, us, them, (lineup, unit, who) => startersTable(lineup, unit, availability, onPlayer, who));
}

/** The depth charts as the same three matchup rows, or the empty note. */
export function depthBlock({ lineups, us, them, availability } = {}) {
  return matchups(lineups, us, them, (lineup, unit) => depthTable(lineup, unit, availability));
}
