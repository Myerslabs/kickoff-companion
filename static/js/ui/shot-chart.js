// The shot chart (public release Phase 7b): one offense's passes by zone (deep or short, left, middle or
// right) or its runs by lane, with attempts and success rate, from the released plays (so it follows the
// spoiler delay). The server tallies it (app/live/analysis.py shot_chart); this draws it.
//
//   shotChart({ chart, view: "passes"|"runs"|"both", onView, team, fixed })  the element (fixed: one view, no Passes/Runs
//       switch; "both", freeze wave F5, owner 2026-10-20: the passes over the line of scrimmage and the runs by lane under it in
//       one field, which is how In Game's one screen draws it). chart is one team's
//   { passes: {zone: cell}, runs: {lane: cell}, unzoned: {passes, runs}, sacks }; a cell is
//   { attempts, completions, yards, success {made, of}, successRate, completionRate, yardsPerAttempt }.
//   successTone(rate)  the band a success rate falls in (for the cell's color).

import { DASH, el, fmtPct, isNum, obj, text } from "./dom.js";

const SIDES = ["left", "middle", "right"];
const DEPTHS = ["deep", "short"];

function count(value) {
  return isNum(value) && value >= 0 ? Math.round(value) : 0;
}

/** "13 passes, 8 runs, 1 sack" for a band's summary (the one-screen chart has no room for a note). */
export function shotCounts(chart) {
  const c = obj(chart);
  const sum = (cells) => Object.values(obj(cells)).reduce((n, cell) => n + count(obj(cell).attempts), 0);
  const sacks = count(c.sacks);
  return [`${sum(c.passes)} passes`, `${sum(c.runs)} runs`, sacks ? `${sacks} ${sacks === 1 ? "sack" : "sacks"}` : null].filter(Boolean).join(", ");
}

export function successTone(rate) {
  if (!isNum(rate)) return "none";
  return rate >= 0.55 ? "hot" : rate >= 0.42 ? "good" : rate >= 0.3 ? "fair" : "cold";
}

function cellEl(cell, { label, passes }) {
  const c = obj(cell);
  const attempts = count(c.attempts);
  const rate = isNum(c.successRate) ? c.successRate : null;
  const main = attempts ? (passes ? `${count(c.completions)}/${attempts}` : `${attempts} ${attempts === 1 ? "run" : "runs"}`) : DASH;
  const detail = attempts ? `${rate === null ? DASH : fmtPct(rate)} success${isNum(c.yardsPerAttempt) ? ` · ${c.yardsPerAttempt.toFixed(1)} yds` : ""}` : "none";
  return el(
    "div",
    { class: `shot-cell shot-cell--${attempts ? successTone(rate) : "none"}`, role: "cell", "aria-label": `${label}: ${main}, ${detail}` },
    el("span", { class: "shot-cell__label" }, label),
    el("span", { class: "shot-cell__main" }, main),
    el("span", { class: "shot-cell__detail" }, detail),
  );
}

export function shotChart({ chart, view = "passes", onView, team, fixed = false } = {}) {
  const c = obj(chart);
  const both = view === "both";
  const passes = view !== "runs";
  const seg = fixed || both ? null : el(
    "div",
    { class: "seg shot-chart__seg", role: "group", "aria-label": "Plays" },
    [["passes", "Passes"], ["runs", "Runs"]].map(([id, label]) =>
      el("button", { type: "button", "aria-pressed": (passes ? "passes" : "runs") === id ? "true" : "false", onclick: () => { if (typeof onView === "function") onView(id); } }, label),
    ),
  );
  const runRow = (label) => el("div", { class: `shot-row${both ? " shot-row--runs" : ""}`, role: "row" }, SIDES.map((side) => cellEl(obj(c.runs)[side], { label: `${label}${side === "middle" ? "middle" : side}`, passes: false })));
  const grid = both
    ? el("div", { class: "shot-field shot-field--both", role: "table", "aria-label": `${text(team)} passes by zone and runs by lane` },
        DEPTHS.map((depth) => el("div", { class: "shot-row", role: "row" }, SIDES.map((side) => cellEl(obj(c.passes)[`${depth}-${side}`], { label: `${depth === "deep" ? "Deep" : "Short"} ${side}`, passes: true })))),
        el("div", { class: "shot-field__los" }, "Line of scrimmage"),
        runRow("Runs "))
    : passes
    ? el("div", { class: "shot-field shot-field--passes", role: "table", "aria-label": `${text(team)} passes by zone` },
        DEPTHS.map((depth) => el("div", { class: "shot-row", role: "row" }, SIDES.map((side) => cellEl(obj(c.passes)[`${depth}-${side}`], { label: `${depth === "deep" ? "Deep" : "Short"} ${side}`, passes: true })))),
        el("div", { class: "shot-field__los" }, "Line of scrimmage"))
    : el("div", { class: "shot-field shot-field--runs", role: "table", "aria-label": `${text(team)} runs by lane` },
        el("div", { class: "shot-row", role: "row" }, SIDES.map((side) => cellEl(obj(c.runs)[side], { label: side === "middle" ? "Middle" : side === "left" ? "Left" : "Right", passes: false }))),
        el("div", { class: "shot-field__los" }, "Line of scrimmage"));
  const sum = (cells) => Object.values(obj(cells)).reduce((n, cell) => n + count(obj(cell).attempts), 0);
  const unzoned = obj(c.unzoned);
  const extra = passes
    ? [count(c.sacks) ? `${count(c.sacks)} ${count(c.sacks) === 1 ? "sack" : "sacks"}` : null, count(unzoned.passes) ? `${count(unzoned.passes)} without a zone` : null]
    : [count(unzoned.runs) ? `${count(unzoned.runs)} without a lane` : null];
  const total = passes ? sum(c.passes) : sum(c.runs);
  if (both) return el("div", { class: "shot-chart shot-chart--both" }, grid); // one screen (wave F5): the band's summary carries the counts
  return el(
    "div",
    { class: "shot-chart" },
    seg,
    grid,
    // the board (fixed) keeps the count only: the definition of success is In Game's to explain, and a TV cell has no room
    el("p", { class: "note" }, total ? `${total} ${passes ? "passes" : "runs"} charted` : `No ${passes ? "passes" : "runs"} yet`, extra.filter(Boolean).length ? `, plus ${extra.filter(Boolean).join(" and ")}` : "", fixed ? "." : ". Success is CFBD's: half the yards needed on first down, 70% on second, all of them on third or fourth. Plays shown follow the spoiler delay."),
  );
}
