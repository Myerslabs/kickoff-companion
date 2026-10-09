// The TV crew and each team's coaches, from the game's notes (Phase 17 #2). The Live sheet's game line and
// the Game program's header both draw them, so the two say the same thing. CFBD has the network and the
// head coaches only; the crew and the coordinators come from the notes prompt.
//   crewText(notes, game)                 "ESPN: Play-by-play Name, Name (sideline)", or null
//   staffLine(notes, { usAbbr, themAbbr }) <div class="game-staff">: "US HC Name · OC Name · DC Name | THEM HC ...", or null
// Every field is guarded: a missing name is left out, never printed as undefined or null.

import { el, obj } from "./dom.js";
import { wikiLink } from "./wiki-links.js";

function name(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
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
export function staffParts(notes, side, school = null) {
  const s = obj(obj(obj(notes).coaches)[side]);
  const parts = [];
  for (const [label, value] of [["HC", s.headCoach], ["OC", s.offensiveCoordinator], ["DC", s.defensiveCoordinator]]) {
    const who = name(value);
    if (!who) continue;
    if (parts.length) parts.push(" · ");
    parts.push(`${label} `, wikiLink("coach", { person: who, team: school }, who));
  }
  return parts;
}

/** Both sides' coaches on one line, ours first, each led by its abbreviation; null when neither is known. */
export function staffLine(notes, { usAbbr = "Us", themAbbr = "Them", usSchool = null, themSchool = null } = {}) {
  const side = (which, abbr, school) => {
    const words = staffParts(notes, which, school);
    return words.length ? el("span", { class: "game-staff__side" }, el("b", {}, abbr), " ", ...words) : null;
  };
  const us = side("us", usAbbr, usSchool);
  const them = side("them", themAbbr, themSchool);
  if (!us && !them) return null;
  return el("div", { class: "game-staff" }, us, us && them ? el("span", { class: "game-staff__bar", "aria-hidden": "true" }, " | ") : null, them);
}
