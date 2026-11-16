// The notes laid out (Wave 5; owner 2026-11-15, the board "Build as
// drawn"): on top of the Program notes band, three keys to the game, the numbers (three or four of the program's own figures,
// each with its national rank chip and the conference rank) and the one matchup to watch. The sections under them stay as
// 1.38.0 draws them. The server checked every piece and filled the numbers from the program (app/services/notes_layout.py),
// so a figure here is never Claude's own; a piece it left out is simply not drawn, and with nothing left the band is as it
// was. Where they sit across the band's width is the stylesheet's (.nl, container queries on the band's body): stacked on a
// phone and the iPad upright, the keys beside the numbers and the matchup from 900 px.
//
//   notesLayout(layout, { names, onName, year })   the element, or null when there is nothing to draw
//   figureText(value, format)                       a figure as the strip shows it (a rate to one decimal, as the notes write it)

import { DASH, el, fmtPct, fmtStat, isNum, ordinal } from "./dom.js";
import { nationalHref } from "./national-link.js";
import { linkNames } from "./prose.js";
import { rankChip } from "./stat-table.js";

const obj = (value) => (value && typeof value === "object" && !Array.isArray(value) ? value : null);
const rows = (value) => (Array.isArray(value) ? value.filter((row) => obj(row)) : []);
const str = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);

/** A figure as the strip shows it: a rate to one decimal (34.9%), the way the notes write it; the rest as the app does. */
export function figureText(value, format) {
  if (!isNum(value)) return DASH;
  return format === "pct" ? fmtPct(value, 1) : fmtStat(value, format);
}

function lineAndText(item, names, onName, lineClass) {
  const line = str(item.line);
  if (!line) return null;
  const rest = str(item.text);
  return [el("b", { class: lineClass }, line), rest ? " " : null, ...(rest ? linkNames(rest, names, onName) : [])];
}

function keysPiece(keys, names, onName) {
  const items = rows(keys)
    .map((key, i) => {
      const words = lineAndText(key, names, onName, "nl-keys__line");
      return words ? el("li", { class: "nl-keys__item" }, el("span", { class: "nl-keys__n", "aria-hidden": "true" }, String(i + 1)), el("p", { class: "nl-keys__text" }, words)) : null;
    })
    .filter(Boolean);
  if (!items.length) return null;
  return el("section", { class: "nl-piece nl-keys", "aria-label": "Keys to the game" }, el("h3", { class: "nl-head" }, "Keys to the game"), el("ol", { class: "nl-keys__list" }, items));
}

function cell(number, conference, year) {
  const school = str(number.school);
  const team = number.team === "us" ? "us" : "them";
  const label = str(number.label) || DASH;
  const chip = rankChip(number.rank, number.of, { href: nationalHref(number.metric, { team: school || undefined, year }), label: `${school ? `${school}, ` : ""}${label}` });
  const conf = isNum(number.conferenceRank) && conference ? el("span", { class: "nl-cell__conf" }, `${conference} ${ordinal(number.conferenceRank)}`) : null;
  return el(
    "div",
    { class: "nl-cell" },
    el("span", { class: `nl-cell__team nl-cell__team--${team}` }, school ? school.toUpperCase() : team === "us" ? "US" : "THEM"),
    el("span", { class: "nl-cell__value" }, figureText(number.value, number.format)),
    el("span", { class: "nl-cell__label" }, label),
    chip || conf ? el("span", { class: "nl-cell__ranks" }, chip, conf) : null,
  );
}

function numbersPiece(numbers, conference, year) {
  const list = rows(numbers).filter((n) => isNum(n.value) && str(n.metric));
  if (list.length < 3) return null; // the server keeps three or four; anything less is not a strip
  const counts = [...new Set(list.map((n) => n.of).filter((n) => isNum(n)))];
  const of = counts.length === 1 ? counts[0] : null; // a count only when every figure is ranked among the same teams
  return el(
    "section",
    { class: "nl-piece nl-numbers", "aria-label": "The numbers" },
    el("h3", { class: "nl-head" }, "The numbers"),
    el("div", { class: "nl-strip" }, list.slice(0, 4).map((n) => cell(n, conference, year))),
    el("p", { class: "nl-strip__foot" }, isNum(of) ? `Ranks of ${of} FBS teams, from the program's own numbers.` : "National ranks, from the program's own numbers."),
  );
}

function watchPiece(watch, names, onName) {
  const item = obj(watch);
  const words = item ? lineAndText(item, names, onName, "nl-watch__line") : null;
  if (!words) return null;
  return el("aside", { class: "nl-piece nl-watch", "aria-label": "The matchup to watch" }, el("h3", { class: "nl-head nl-head--watch" }, "The matchup to watch"), el("p", { class: "nl-watch__text" }, words));
}

/** The layout's pieces over the notes' sections, or null when none can be drawn. */
export function notesLayout(layout, { names = null, onName = null, year } = {}) {
  const data = obj(layout);
  if (!data) return null;
  const conference = str(data.conference);
  const keys = keysPiece(data.keys, names, onName);
  const numbers = numbersPiece(data.numbers, conference, year);
  const watch = watchPiece(data.watch, names, onName);
  if (!keys && !numbers && !watch) return null;
  const side = numbers || watch ? el("div", { class: "nl__side" }, numbers, watch) : null;
  return el("div", { class: `nl${keys && side ? " nl--two" : ""}` }, keys, side);
}
