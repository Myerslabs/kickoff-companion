// The roster breakdown (Phase 17 #35, from the owner's screenshots, 2026-10-07): positions down the side, the five
// classes across (Freshman to Senior; a redshirt carries "(RS)" by the name), a total for each row and column, and each
// player a chip: his short name and our stat grade in its color (owner, 2026-10-07: the jersey drawing added nothing,
// "just use the name"). A tap opens the player's card. Players without a grade (linemen, long snappers, too few
// plays) show the name only.
//
// Tables wave 3 (owner 2026-10-10): sized by its own box like every table, never a sideways scroll. Large: the class names
// whole, each chip "J. Smith (RS)"; medium: the chip's surname ("Smith (RS)"); small: the class codes (FR, SO, JR, SR), "#"
// over the totals, and each cell its count. Measured on a phone (2026-10-11): four columns of name chips need about 590 px
// even with surnames, and the phone's band is about 330, so at small the grid is the roster's shape by class and position
// (the Roster table under it names every player with his grade, and a tap there opens the card). The redshirt mark stays
// on every chip: it is data. A matrix, so nothing sorts. Its note follows the size: what the chips' numbers are, or what
// the counts are.
//
//   rosterGrid(players, { onPlayer })  -> <div class="rgrid-wrap"> holding the sized <div class="stat-table-wrap rgrid-fit">
//                                         and its note
//   ROSTER_ROWS                          [label, positions] in display order
//   CLASS_COLUMNS                        [code, label]: FR, SO, JR, SR

import { distinctNames, el, isNum, playerNames } from "./dom.js";
import { gradeTier, gradeValue } from "./grade.js";
import { DROPPED, fitSize, watchSize } from "./sizes.js";
import { applyStatSize, sizedText } from "./stat-table.js";

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

/** Every player's name forms for the chips (item 6, ui/dom.js playerNames from CFBD's split), settled across the grid so
 *  two who would read alike get a second letter and players who share a surname keep "J. Smith" at medium. */
function chipForms(list) {
  const settled = distinctNames(list.map((p) => playerNames({ name: p.name, firstName: p.firstName, lastName: p.lastName })));
  return new Map(list.map((p, i) => [p, settled[i]]));
}

/** A player's two names for a chip: { long: "J. Smith (RS)", surname: "Smith (RS)" }. The redshirt mark rides on both. */
function chipNames(p, forms) {
  const rs = p.redshirt === true ? RS : "";
  const f = (forms && forms.get(p)) || playerNames({ name: p.name, firstName: p.firstName, lastName: p.lastName });
  return { long: `${f.initial}${rs}`, surname: `${f.last}${rs}` };
}

/** The chip's number: our stat grade. */
function gradeOf(p) {
  return gradeValue(p.grade);
}

function chip(p, onPlayer, forms) {
  const grade = gradeOf(p);
  const tier = grade === null ? null : gradeTier(grade);
  const whole = typeof p.name === "string" && p.name.trim() ? p.name.trim() : [p.firstName, p.lastName].filter((w) => typeof w === "string" && w.trim()).map((w) => w.trim()).join(" ") || null;
  const kind = "stat grade";
  const says = `${playerNames(whole).full}${isNum(p.number) ? `, number ${p.number}` : ""}${grade !== null ? `, ${kind} ${Math.round(grade)}` : `, no ${kind}`}`;
  const names = chipNames(p, forms);
  return el(
    "button",
    { class: "rgrid__chip", type: "button", title: says, "aria-label": says, onclick: () => (typeof onPlayer === "function" ? onPlayer(p) : null) },
    el("span", { class: "rgrid__name" }, sizedText(names.long, names.surname, names.surname)),
    grade !== null ? el("span", { class: `rgrid__grade rgrid__grade--${tier}` }, String(Math.round(grade))) : null,
  );
}

/** Players sorted for a cell: graded first, best first, then by name. */
function ordered(list, forms) {
  return [...list].sort((a, b) => {
    const ga = gradeOf(a);
    const gb = gradeOf(b);
    if (ga !== gb) return (gb ?? -1) - (ga ?? -1);
    return chipNames(a, forms).long.localeCompare(chipNames(b, forms).long);
  });
}

export function rosterGrid(players, { onPlayer } = {}) {
  const list = (Array.isArray(players) ? players : []).filter((p) => p && typeof p === "object");
  const forms = chipForms(list);
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
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        el("th", { scope: "col" }, el("span", { class: "sr-only" }, "Position")),
        CLASS_COLUMNS.map(([code, name]) => el("th", { scope: "col", dataset: { term: name } }, sizedText(name, name, code))),
        el("th", { scope: "col", class: "rgrid__total", dataset: { term: "Players" } }, sizedText("Players", "Players", "#")),
      ),
    ),
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
            return el("td", { class: "rgrid__cell", "data-label": name }, here.length ? [el("div", { class: "rgrid__stack" }, ordered(here, forms).map((p) => chip(p, onPlayer, forms))), el("span", { class: "rgrid__count" }, String(here.length))] : null);
          }),
          el("td", { class: "rgrid__total" }, String(rowTotal(label))),
        ),
      ),
    ),
    el("tfoot", {}, el("tr", {}, el("th", { scope: "row" }, "All"), CLASS_COLUMNS.map(([code]) => el("td", { class: "rgrid__total" }, String(colTotal(code)))), el("td", { class: "rgrid__total rgrid__grand" }, String(total)))),
  );
  // sized by its own box (wave 3): the largest size whose table fits; never a sideways scroll box. The outer wrap carries the
  // size too, so the note under the grid says what its numbers are at that size.
  const fit = el("div", { class: "stat-table-wrap rgrid-fit" }, table);
  const outer = el(
    "div",
    { class: "rgrid-wrap" },
    fit,
    el("p", { class: "note rgrid__note rgrid__note--chips" }, "The number is our stat grade (100 is the best, 50 the middle at the position); linemen and long snappers have none. Tap a player for the card."),
    el("p", { class: "note rgrid__note rgrid__note--counts" }, `Players at each position by class. The Roster below names each one with our stat grade; tap a player there for the card.`),
    unclassed.length ? el("p", { class: "note" }, `${unclassed.length} player${unclassed.length === 1 ? " has" : "s have"} no class or position on CFBD's roster and ${unclassed.length === 1 ? "is" : "are"} not in the grid.`) : null,
  );
  const apply = (step) => {
    applyStatSize(fit, step);
    outer.dataset.size = fit.dataset.size;
  };
  apply("large");
  // ENH-20 (P5): the table is fixed at its box's width with equal class columns, so a size fits when no cell's chips push
  // past its column
  // 2026-11-15 (owner: nothing cut off): the chips sit at a cell's right, so a chip wider than its cell spills out to the LEFT,
  // which a scroll width never counts; each chip is also held inside its cell's own box (a phone cut one by 8 px)
  const inside = (td) => {
    if (typeof td.getBoundingClientRect !== "function") return true;
    const box = td.getBoundingClientRect();
    return [...td.querySelectorAll(".rgrid__chip")].every((chip) => {
      const r = typeof chip.getBoundingClientRect === "function" ? chip.getBoundingClientRect() : null;
      return !r || !(r.width > 0) || (r.left >= box.left - 1 && r.right <= box.right + 1);
    });
  };
  const cellsFit = () => [...table.querySelectorAll(".rgrid__cell")].every((td) => (!isNum(td.scrollWidth) || !isNum(td.clientWidth) || td.scrollWidth <= td.clientWidth + 1) && inside(td));
  watchSize(fit, () => {
    const size = fitSize(fit, table, apply, undefined, cellsFit);
    if (size === null) return;
    if (size === DROPPED) fit.classList.remove("stat-table-wrap--fits");
    else fit.classList.add("stat-table-wrap--fits");
  });
  return outer;
}
