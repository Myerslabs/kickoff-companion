// The TV crew and each team's coaches, from the game's notes (Phase 17 #2). The In Game sheet's game line and
// the Pre-Game Program's cover both draw them, so the two say the same thing. CFBD has the network and the
// head coaches only; the crew and the coordinators come from the notes prompt.
//   crewText(notes, game)                       "ESPN: Play-by-play Name, Name (sideline)", or null
//   staffText(notes, side)                      "HC Name · OC Name · DC Name", or null
//   staffParts(notes, side, school, { first })  the same as nodes, each name a link; first: the first coach of a shared role
//   teamStaff(notes, side, { abbr, school })    <div class="game-staff">: "SWT HC Name · OC Name · DC Name" for one
//                                               team, the first coach of each role only (the cover, owner 2026-10-10), or null
//   firstCoach(value)                           "Kyle Flood" from "Kyle Flood and AJ Milwee", or null
// Every field is guarded: a missing name is left out, never printed as undefined or null.

import { el, obj } from "./dom.js";
import { wikiLink } from "./wiki-links.js";

function name(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/**
 * The first coach of a role the notes give to two ("Kyle Flood and AJ Milwee", "A / B", "A & B", "A, B"), or the
 * one name. A suffix after a comma ("Name, Jr.") stays with its name. Null for anything that is not a name.
 */
export function firstCoach(value) {
  const whole = name(value);
  if (!whole) return null;
  const first = whole.split(/\s+(?:and|&)\s+|\s*[/;]\s*|,(?!\s*(?:Jr|Sr|II|III|IV)\b)\s*/i)[0];
  return name(first) || whole;
}

/** The broadcast crew with its network first, or null when the notes name nobody. */
export function crewText(notes, game) {
  const b = obj(obj(notes).broadcast);
  const sideline = (Array.isArray(b.sideline) ? b.sideline : []).map(name).filter(Boolean);
  const voices = [name(b.playByPlay), name(b.analyst), ...sideline.map((s) => `${s} (sideline)`)].filter(Boolean);
  if (!voices.length) return null;
  const network = name(b.network) || name(obj(game).tv);
  return `${network ? `${network}: ` : ""}${voices.join(", ")}`;
}

/** One side's coaches as "HC Name · OC Name · DC Name", or null when the notes name none. */
export function staffText(notes, side) {
  const s = obj(obj(obj(notes).coaches)[side]);
  const parts = [["HC", s.headCoach], ["OC", s.offensiveCoordinator], ["DC", s.defensiveCoordinator]].filter(([, v]) => name(v)).map(([k, v]) => `${k} ${name(v)}`);
  return parts.length ? parts.join(" · ") : null;
}

/**
 * One side's coaches as nodes, "HC " then the name as a link to the coach's own Wikipedia page (Phase 19, owner 2026-10-08: "link to
 * the coaches page"), separated by dots; [] when the notes name none. `school` lets the lookup find the right person.
 */
export function staffParts(notes, side, school = null, { first = false } = {}) {
  const s = obj(obj(obj(notes).coaches)[side]);
  const parts = [];
  for (const [label, value] of [["HC", s.headCoach], ["OC", s.offensiveCoordinator], ["DC", s.defensiveCoordinator]]) {
    const who = first ? firstCoach(value) : name(value);
    if (!who) continue;
    if (parts.length) parts.push(" · ");
    parts.push(`${label} `, wikiLink("coach", { person: who, team: school }, who));
  }
  return parts;
}

/**
 * One team's coaches under its block on the cover (owner mockup 2026-10-10): its abbreviation, then HC, OC and DC with
 * the first coach of each role only (the team page keeps the whole staff). Null when the notes name none.
 */
export function teamStaff(notes, side, { abbr = null, school = null } = {}) {
  const words = staffParts(notes, side, school, { first: true });
  if (!words.length) return null;
  const lead = name(abbr);
  return el("div", { class: `game-staff cover__staff cover__staff--${side === "us" ? "us" : "them"}` }, lead ? [el("b", {}, lead), " "] : null, ...words);
}
