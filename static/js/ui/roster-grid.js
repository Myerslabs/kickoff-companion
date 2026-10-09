// The roster breakdown (Phase 17 #35, from the owner's screenshots, 2026-10-07): positions down the side, the five
// classes across (Freshman to Senior; a redshirt carries "(RS)" by the name), a total for each row and column, and each
// player a chip: his short name and our stat grade in its color (owner, 2026-10-07: the jersey drawing added nothing,
// "just use the name"). A tap opens the player's card. Players without a grade (linemen, long snappers, too few
// plays) show the name only.
//
//   rosterGrid(players, { onPlayer })  -> <div class="rgrid-wrap">
//   ROSTER_ROWS                          [label, positions] in display order
//   CLASS_COLUMNS                        [code, label]: FR, SO, JR, SR

import { el, isNum, text } from "./dom.js";
import { gradeTier, gradeValue } from "./grade.js";

export const ROSTER_ROWS = [
  ["QB", ["QB"]],
  ["RB", ["RB", "FB"]],
  ["WR", ["WR"]],
  ["TE", ["TE"]],
  ["OL", ["OL", "OT", "OG", "C", "G", "T"]],
  ["DL", ["DL", "DE", "DT", "NT", "EDGE"]],
  ["LB", ["LB", "OLB", "ILB", "MLB"]],
  ["CB", ["CB"]],
  ["S", ["S", "FS", "SS", "DB"]],
  ["K", ["PK", "K"]],
  ["P", ["P"]],
  ["LS", ["LS"]],
  ["ATH", ["ATH"]],
];
export const CLASS_COLUMNS = [["FR", "Freshman"], ["SO", "Sophomore"], ["JR", "Junior"], ["SR", "Senior"]];

/** A redshirted player's name carries "(RS)" (Phase 18.4); CFBD has no flag, the server infers it. */
export const RS = " (RS)";

function shortName(p) {
  const first = typeof p.firstName === "string" ? p.firstName.trim() : "";
  const last = typeof p.lastName === "string" ? p.lastName.trim() : "";
  if (first && last) return `${first[0]}. ${last}${p.redshirt === true ? RS : ""}`;
  const name = typeof p.name === "string" ? p.name.trim() : "";
  const parts = name.split(/\s+/).filter(Boolean);
  return `${parts.length > 1 ? `${parts[0][0]}. ${parts.slice(1).join(" ")}` : text(name || null)}${p.redshirt === true ? RS : ""}`;
}

function chip(p, onPlayer) {
  const grade = gradeValue(p.grade);
  const tier = grade === null ? null : gradeTier(grade);
  const says = `${text(p.name)}${isNum(p.number) ? `, number ${p.number}` : ""}${grade !== null ? `, stat grade ${Math.round(grade)}` : ", no stat grade"}`;
  return el(
    "button",
    { class: "rgrid__chip", type: "button", title: says, "aria-label": says, onclick: () => (typeof onPlayer === "function" ? onPlayer(p) : null) },
    el("span", { class: "rgrid__name" }, shortName(p)),
    grade !== null ? el("span", { class: `rgrid__grade rgrid__grade--${tier}` }, String(Math.round(grade))) : null,
  );
}

/** Players sorted for a cell: graded first, best first, then by name. */
function ordered(list) {
  return [...list].sort((a, b) => {
    const ga = gradeValue(a.grade);
    const gb = gradeValue(b.grade);
    if (ga !== gb) return (gb ?? -1) - (ga ?? -1);
    return shortName(a).localeCompare(shortName(b));
  });
}

export function rosterGrid(players, { onPlayer } = {}) {
  const list = (Array.isArray(players) ? players : []).filter((p) => p && typeof p === "object");
  const rowOf = (pos) => ROSTER_ROWS.find(([, codes]) => codes.includes(String(pos || "").toUpperCase()));
  const cells = new Map(); // "row|class" -> players
  const unclassed = [];
  for (const p of list) {
    const row = rowOf(p.position);
    const cls = String(p.classYear || "").toUpperCase();
    if (!row || !CLASS_COLUMNS.some(([code]) => code === cls)) {
      unclassed.push(p);
      continue;
    }
    const key = `${row[0]}|${cls}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key).push(p);
  }
  const rows = ROSTER_ROWS.filter(([label]) => CLASS_COLUMNS.some(([code]) => cells.has(`${label}|${code}`)));
  if (!rows.length) return el("p", { class: "note" }, "The roster breakdown appears once the roster has loaded.");
  const count = (label, code) => (cells.get(`${label}|${code}`) || []).length;
  const rowTotal = (label) => CLASS_COLUMNS.reduce((sum, [code]) => sum + count(label, code), 0);
  const colTotal = (code) => rows.reduce((sum, [label]) => sum + count(label, code), 0);
  const total = rows.reduce((sum, [label]) => sum + rowTotal(label), 0);
  const table = el(
    "table",
    { class: "rgrid" },
    el("caption", { class: "sr-only" }, "The roster by position and class"),
    el("thead", {}, el("tr", {}, el("th", { scope: "col" }, el("span", { class: "sr-only" }, "Position")), CLASS_COLUMNS.map(([, name]) => el("th", { scope: "col" }, name)), el("th", { scope: "col", class: "rgrid__total" }, "Players"))),
    el(
      "tbody",
      {},
      rows.map(([label]) =>
        el(
          "tr",
          {},
          el("th", { scope: "row", class: "rgrid__pos" }, label),
          CLASS_COLUMNS.map(([code, name]) => {
            const here = cells.get(`${label}|${code}`) || [];
            return el("td", { class: "rgrid__cell", "data-label": name }, here.length ? el("div", { class: "rgrid__stack" }, ordered(here).map((p) => chip(p, onPlayer))) : null);
          }),
          el("td", { class: "rgrid__total" }, String(rowTotal(label))),
        ),
      ),
    ),
    el("tfoot", {}, el("tr", {}, el("th", { scope: "row" }, "All"), CLASS_COLUMNS.map(([code]) => el("td", { class: "rgrid__total" }, String(colTotal(code)))), el("td", { class: "rgrid__total rgrid__grand" }, String(total)))),
  );
  return el(
    "div",
    { class: "rgrid-wrap" },
    table,
    unclassed.length ? el("p", { class: "note" }, `${unclassed.length} player${unclassed.length === 1 ? " has" : "s have"} no class or position on CFBD's roster and ${unclassed.length === 1 ? "is" : "are"} not in the grid.`) : null,
  );
}

