// Board 6 (ENH-31, the owner's pick 2026-10-25): the conference race as the range of finishes each contender can still
// reach, a bar from its best possible place to its worst, a ring where it stands now, the title-game spots shaded, our row
// in our color. From the race the app already plays out (app/services/race.py: bestPlace, worstPlace on each standings
// row and on `us`); the four plain lines stay beneath it in What we need. A team already out of the title game is left
// off (the standings table above still lists it), our own row never is: the program keeps the top six rows only, so our
// row comes from `us` when we are lower. Drawn as a grid of places (one column each), so it fits any band.
//
//   raceRanges(race, { limit, abbreviations })   the chart, or null when the race has no ranges (an older answer, an
//                                  independent); with {school: abbreviation} the names are short (the Season column)
//   placesFor(rows)                the places a set of rows draws (the worst among them, 2 to 20), null under two ranged rows
//   rangeAxis({ places, spots })   the place numbers alone, and rangeStrip(row, { places, spots }) one row's cells, bar and
//                                  ring alone: the chart as a column of a table that names the teams itself (What we need,
//                                  BUG-15, the owner's board of 2026-10-27: the standings and where each can finish, row
//                                  for row)

import { el, isNum, teamLink, text } from "./dom.js";

function ordinal(n) {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${tail}`;
}

const ranged = (r) => r && typeof r === "object" && typeof r.team === "string" && r.team && isNum(r.bestPlace) && isNum(r.worstPlace) && r.bestPlace >= 1 && r.worstPlace >= r.bestPlace;

// past ten places every other one is named (the narrow Season column), the first and the last always, and the one just
// before the last left blank so the two never touch
function placeLabel(i, places) {
  return places <= 10 || i + 1 === places || (i % 2 === 0 && i + 2 !== places) ? String(i + 1) : "";
}

function finishWords(row) {
  return row.bestPlace === row.worstPlace ? `finishes ${ordinal(row.bestPlace)}` : `${ordinal(row.bestPlace)} at best, ${ordinal(row.worstPlace)} at worst${isNum(row.place) ? `, ${ordinal(row.place)} now` : ""}`;
}

/** The cells, the bar and the ring of one row, `offset` grid columns in (the chart's name column, or none). */
function rangeCells(row, places, spots, offset) {
  const out = [];
  for (let p = 1; p <= places; p += 1) out.push(el("span", { class: `race-ranges__cell${p <= spots ? " race-ranges__cell--spot" : ""}`, style: { gridColumn: String(p + offset), gridRow: "1" } }));
  if (!ranged(row)) return out; // a row the race could not range (an older answer): the places alone
  const best = Math.min(row.bestPlace, places);
  const worst = Math.min(row.worstPlace, places);
  out.push(el("span", { class: `race-ranges__bar${row.isUs ? " race-ranges__bar--us" : ""}`, style: { gridColumn: `${best + offset} / ${worst + offset + 1}`, gridRow: "1" } }));
  if (isNum(row.place)) {
    const now = Math.min(Math.max(row.place, best), worst);
    out.push(el("span", { class: "race-ranges__now", style: { gridColumn: String(now + offset), gridRow: "1" } }));
  }
  return out;
}

export function placesFor(rows) {
  const list = (Array.isArray(rows) ? rows : []).filter(ranged);
  if (list.length < 2) return null;
  return Math.min(Math.max(...list.map((r) => r.worstPlace), 2), 20);
}

export function rangeAxis({ places, spots = 2 } = {}) {
  const n = isNum(places) ? places : 0;
  return el(
    "span",
    { class: "race-ranges__strip race-ranges__strip--head", style: { gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }, "aria-label": "Where each can finish, best place to worst" },
    Array.from({ length: n }, (_, i) => el("span", { class: `race-ranges__place${i < spots ? " race-ranges__place--spot" : ""}`, style: { gridColumn: String(i + 1), gridRow: "1" }, "aria-hidden": "true" }, placeLabel(i, n))),
  );
}

export function rangeStrip(row, { places, spots = 2 } = {}) {
  const n = isNum(places) ? places : 0;
  const words = ranged(row) ? finishWords(row) : "no range yet";
  return el("span", { class: `race-ranges__strip${row?.isUs ? " is-us" : ""}`, style: { gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }, role: "img", "aria-label": words, title: words }, rangeCells(row, n, spots, 0));
}

export function raceRanges(race, { limit = 8, abbreviations = null } = {}) {
  if (!race || typeof race !== "object") return null;
  const all = (Array.isArray(race.standings) ? race.standings : []).filter(ranged);
  let rows = all.filter((r) => r.isUs === true || r.status !== "out").slice(0, limit);
  const us = race.us && typeof race.us === "object" ? race.us : null;
  if (!rows.some((r) => r.isUs === true) && ranged(us)) rows = [...rows, { ...us, isUs: true }];
  if (rows.length < 2) return null;
  const places = Math.min(Math.max(...rows.map((r) => r.worstPlace), 2), 20);
  const spots = isNum(race.spots) ? race.spots : 2;
  const short = abbreviations && typeof abbreviations === "object";
  const nameOf = (team) => (short && typeof abbreviations[team] === "string" && abbreviations[team].trim()) || team;
  const columns = { gridTemplateColumns: `${short ? "minmax(3.2em, 4.2em)" : "minmax(6.5em, 9.5em)"} repeat(${places}, minmax(0, 1fr))` };
  const head = el(
    "div",
    { class: "race-ranges__row race-ranges__row--head", style: columns, "aria-hidden": "true" },
    el("span", { class: "race-ranges__corner", style: { gridColumn: "1", gridRow: "1" } }, "Place"),
    Array.from({ length: places }, (_, i) => el("span", { class: `race-ranges__place${i < spots ? " race-ranges__place--spot" : ""}`, style: { gridColumn: String(i + 2), gridRow: "1" } }, placeLabel(i, places))),
  );
  const body = rows.map((row) => {
    const words = finishWords(row);
    return el(
      "li",
      { class: `race-ranges__row${row.isUs ? " is-us" : ""}`, style: columns, "aria-label": `${row.team}: ${words}`, title: words },
      el("span", { class: "race-ranges__team", style: { gridColumn: "1", gridRow: "1" } }, teamLink(row.team, nameOf(row.team))),
      ...rangeCells(row, places, spots, 1),
    );
  });
  const left = all.length - all.filter((r) => r.isUs === true || r.status !== "out").length;
  const key = el(
    "p",
    { class: "race-ranges__key" },
    `Each bar runs from the best place a team can still finish to the worst, ties counted for it and against it; the ring is where it stands now; the shaded ${spots === 1 ? "column is the title-game spot" : `columns are the ${spots} title-game spots`}.`,
    left > 0 ? ` ${left} ${left === 1 ? "team" : "teams"} out of the title game left off.` : "",
    race.rangeExact === false ? " With this many games left the ends are counted from the records, not played out game by game." : "",
  );
  return el("div", { class: "race-ranges", role: "group", "aria-label": `${text(race.conference)}: the finishes each contender can still reach` }, head, el("ol", { class: "race-ranges__list" }, body), key);
}
