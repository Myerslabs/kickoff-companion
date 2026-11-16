// Board 5 (ENH-30, the owner's pick 2026-10-25): down and distance as a shaded grid, success rate by down (1st to 4th) and
// distance (1-3, 4-6, 7-10, 11+), the number in every cell so it reads without the color, green above the FBS average,
// red below, deeper the further off it and the more snaps it rests on (one snap is a hint, not a strength). In the
// Pre-Game Program's Tendencies band for both offenses, above the down-and-distance table it adds shade to
// (app/services/depth2.py down_distance_grid), and In Game's Situation panel from the released plays, ours and theirs
// (app/live/analysis.py down_distance). A cell with no snaps is a dash, never a zero.
//
//   ddGrid(grid, { label, team, side })   one offense's grid, or null when there is none
//   ddPair(us, them, { usLabel, themLabel, usTeam, themTeam })   two grids side by side (either may be missing), or null
//   shadeOf(rate, of)                     the cell's shade, -1 to 1 (exported for the tests)
//   AVERAGE                               the FBS success rate the shade is centered on

import { DASH, el, isNum, text } from "./dom.js";

export const AVERAGE = 0.42; // FBS offenses succeed on about 42% of snaps (CFBD's success: half the yards on 1st, 70% on 2nd, all on 3rd and 4th)
const SPREAD = 0.25; // 25 points off the average is the deepest shade
const FULL_SNAPS = 8; // a cell resting on fewer snaps is shaded that much lighter
const ORDINALS = { 1: "1st", 2: "2nd", 3: "3rd", 4: "4th" };

export function shadeOf(rate, of) {
  if (!isNum(rate) || !isNum(of) || of <= 0) return 0;
  const off = Math.max(-1, Math.min(1, (rate - AVERAGE) / SPREAD));
  return Math.round(off * Math.min(1, of / FULL_SNAPS) * 100) / 100;
}

export function ddGrid(grid, { label = "", team = null, side = null } = {}) {
  const distances = (Array.isArray(grid?.distances) ? grid.distances : []).filter((d) => typeof d === "string");
  const rows = (Array.isArray(grid?.rows) ? grid.rows : []).filter((r) => r && typeof r === "object" && isNum(r.down) && Array.isArray(r.cells));
  if (!distances.length || !rows.length) return null;
  const snaps = rows.reduce((sum, r) => sum + r.cells.reduce((s, c) => s + (isNum(c?.of) ? c.of : 0), 0), 0);
  if (!snaps) return null;
  const columns = { gridTemplateColumns: `2.6em repeat(${distances.length}, minmax(0, 1fr))` };
  const head = el("div", { class: "ddgrid__row ddgrid__row--head", style: columns, "aria-hidden": "true" }, el("span", { class: "ddgrid__corner" }, "Down"), distances.map((d) => el("span", { class: "ddgrid__dist" }, d)));
  const body = rows.map((row) => {
    const down = ORDINALS[row.down] || String(row.down);
    return el(
      "div",
      { class: "ddgrid__row", style: columns },
      el("span", { class: "ddgrid__down" }, down),
      distances.map((d, i) => {
        const cell = row.cells[i] && typeof row.cells[i] === "object" ? row.cells[i] : {};
        const has = isNum(cell.of) && cell.of > 0 && isNum(cell.rate);
        const shade = has ? shadeOf(cell.rate, cell.of) : 0;
        const tone = shade > 0 ? " ddgrid__cell--good" : shade < 0 ? " ddgrid__cell--bad" : "";
        const words = has ? `${Math.round(cell.rate * 100)}%` : DASH;
        const about = has ? `${down} and ${d}: ${isNum(cell.made) ? cell.made : DASH} of ${cell.of} ${cell.of === 1 ? "snap" : "snaps"} a success` : `${down} and ${d}: no snaps`;
        return el("span", { class: `ddgrid__cell${has ? "" : " ddgrid__cell--none"}${tone}`, style: has && shade ? { "--shade": String(Math.abs(shade)) } : null, title: about, "aria-label": about }, words);
      }),
    );
  });
  return el(
    "figure",
    { class: `ddgrid${side ? ` ddgrid--${side}` : ""}`, "aria-label": `${text(label || team)}: success rate by down and distance` },
    label ? el("figcaption", { class: "ddgrid__label" }, label, el("small", {}, ` ${snaps} ${snaps === 1 ? "snap" : "snaps"}`)) : null,
    head,
    ...body,
  );
}

export function ddPair(us, them, { usLabel = "", themLabel = "", usTeam = null, themTeam = null } = {}) {
  const grids = [ddGrid(us, { label: usLabel, team: usTeam, side: "us" }), ddGrid(them, { label: themLabel, team: themTeam, side: "them" })].filter(Boolean);
  if (!grids.length) return null;
  return el(
    "div",
    { class: "ddgrid-pair" },
    el("div", { class: "ddgrid-pair__grids" }, grids),
    el("p", { class: "ddgrid-pair__key" }, `Success rate on every down and distance, runs and passes together: green above the FBS average of about ${Math.round(AVERAGE * 100)}%, red below, lighter where a cell rests on few snaps.`),
  );
}
