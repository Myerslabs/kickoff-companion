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
//
// Freeze wave F3 (2026-10-20, one fact, one source): the starters and depth tables that lived here (startersBlock,
// depthBlock) went; ui/lineups_combined.js draws the one chart of record, and the Roster page's position groups badge
// its order. These helpers read the notes' shape for it.

import { fmtDate, isNum, obj, records, str } from "./dom.js";

const UNITS = ["offense", "defense", "special teams"];
const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);
export const LINEUPS_EMPTY = "No lineups for this game yet. They come with the game's notes: both teams' published depth charts.";

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

/** Whether the notes carry a depth chart for either team (Phase 17 #13: the bands offer "Add notes" when not). */
export function hasLineups(lineups) {
  const l = obj(lineups);
  return hasChart(l.us) || hasChart(l.them);
}

/** "Ourlads, updated Sep 26": the file-level source, else the first team's; "" when nothing is written. */
export function lineupSummary(lineups) {
  const l = obj(lineups);
  if (!hasChart(l.us) && !hasChart(l.them)) return "";
  const from = str(l.source) || str(obj(l.us).source) || str(obj(l.them).source);
  const when = str(l.updatedAt) || str(obj(l.us).updatedAt) || str(obj(l.them).updatedAt);
  return [from, when ? `updated ${fmtDate(when, "short")}` : null].filter(Boolean).join(", ");
}
