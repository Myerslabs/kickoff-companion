// The player box-score tables (L2, X5): one column set per category, shared by In Game, the program's final box, the
// Archive and the Box page. Row tap opens the player card.
//
// Table sizes, wave 2 (owner 2026-10-10): the sizes are declared here once, so every page's box score sizes itself by its
// own box the same way (docs/03-DESIGN.md, Table sizes). Large has whole heads (Carries, Yards, Tackles); medium the box's
// own abbreviations (Car, Yds, Tkl); small every stat but the passer's QBR. The players' names step down with the table
// (item 6, owner 2026-10-11): full names at large, "K. Crawford" from large down, then the surname and the reduced surname. Comp-Att, Sacks, Y/C and Y/R are the app's one name for those stats (design rule 6) at every size. Every table of
// players sorts (owner 2026-09-26); text columns such as Comp-Att and FG sort by their first number.
//
//   BOX_COLUMNS                       { passing: [columns], rushing, receiving, defensive, interceptions, kicking,
//                                       punting, puntReturns, kickReturns }, in the order the tables are drawn
//   boxRows(list)                     a category's player lines as table rows: { name, playerId, ...stats }
//   boxTables({ categories, onTap, emptyText, fromPlays, sort, onSort })
//       One sized table per category that has rows, or the empty note. fromPlays: the line saying passing, rushing and
//       receiving come from the play-by-play until CFBD posts the box score (In Game). sort(name) -> { key, dir } | null
//       is the reader's order for a category (default: the third column, high to low); onSort(name, { key, dir })
//       hears each change, so a page that redraws keeps it.

import { el, obj, records } from "./dom.js";
import { note } from "./states.js";
import { statTable } from "./stat-table.js";

/** The player column: the category's name over the players' names, which step down with the table (item 6). */
const player = (label, labelShort) => ({ key: "name", label, labelShort, kind: "text", person: true });
// a player's yards of the table's kind: its own glossary entry, so the head does not open the team's total yards
const yards = () => ({ key: "YDS", label: "Yards", labelMid: "Yds", labelShort: "Yds", term: "Yards (box score)" });
const touchdowns = () => ({ key: "TD", label: "TD" });
const returns = () => ({ key: "NO", label: "Returns", labelMid: "No", labelShort: "No" });

export const BOX_COLUMNS = {
  passing: [player("Passing"), { key: "C/ATT", label: "Comp-Att", kind: "text" }, yards(), touchdowns(), { key: "INT", label: "Int" }, { key: "QBR", label: "QBR", format: "1f", size: "medium" }],
  rushing: [player("Rushing"), { key: "CAR", label: "Carries", labelMid: "Car", labelShort: "Car" }, yards(), { key: "AVG", label: "Y/C", format: "1f" }, touchdowns()],
  receiving: [player("Receiving"), { key: "REC", label: "Receptions", labelMid: "Rec", labelShort: "Rec" }, yards(), { key: "AVG", label: "Y/R", format: "1f" }, touchdowns()],
  defensive: [player("Defense"), { key: "TOT", label: "Tackles", labelMid: "Tkl", labelShort: "Tkl" }, { key: "SACKS", label: "Sacks", format: "1f" }, { key: "TFL", label: "TFL", format: "1f" }, { key: "PD", label: "Passes defended", labelMid: "PD", labelShort: "PD" }],
  interceptions: [player("Interceptions", "Ints"), { key: "INT", label: "Int" }, yards(), touchdowns()],
  kicking: [player("Kicking"), { key: "FG", label: "FG", kind: "text" }, { key: "XP", label: "XP", kind: "text" }, { key: "PTS", label: "Points", labelMid: "Pts", labelShort: "Pts" }],
  punting: [player("Punting"), { key: "NO", label: "Punts", labelMid: "No", labelShort: "No" }, { key: "AVG", label: "Average", labelMid: "Avg", labelShort: "Avg", format: "1f" }, { key: "LONG", label: "Long" }],
  puntReturns: [player("Punt returns", "Punt ret"), returns(), yards(), touchdowns()],
  kickReturns: [player("Kick returns", "Kick ret"), returns(), yards(), touchdowns()],
};

/** A category's player lines as rows: the stats spread beside the name. */
export function boxRows(list) {
  return records(list).map((r) => ({ ...obj(r.stats), name: r.name, playerId: r.playerId }));
}

function isSort(value) {
  const s = obj(value);
  return typeof s.key === "string" && (s.dir === "ascending" || s.dir === "descending");
}

function sortFor(sort, name, columns) {
  let chosen = null;
  try {
    chosen = typeof sort === "function" ? sort(name) : obj(sort)[name];
  } catch (error) {
    console.error(`boxTables: the ${name} order could not be read; the default order stands.`, error);
  }
  if (isSort(chosen) && columns.some((c) => c.key === chosen.key)) return chosen;
  return { key: columns[2]?.key || columns[1].key, dir: "descending" };
}

/**
 * boxTables({ categories: {passing: [{name, playerId, stats}], ...}, onTap(row), emptyText, fromPlays, sort, onSort })
 * One sized, sortable table per category that has rows.
 */
export function boxTables(options) {
  const { categories, onTap, emptyText = "No player lines yet.", fromPlays = false, sort, onSort } = obj(options); // a damaged call draws the note, never throws
  const cats = obj(categories);
  const names = Object.keys(BOX_COLUMNS).filter((name) => records(cats[name]).length);
  if (!names.length) return note(emptyText);
  return el(
    "div",
    {},
    fromPlays ? note("Passing, rushing, and receiving from the play-by-play until CFBD posts the box score.") : null,
    names.map((name) => {
      const columns = BOX_COLUMNS[name];
      return statTable({
        columns,
        rows: boxRows(cats[name]),
        compact: true,
        sizes: true,
        sort: sortFor(sort, name, columns),
        onSort: typeof onSort === "function" ? (order) => onSort(name, order) : undefined,
        onRowTap: typeof onTap === "function" ? (row) => onTap(row) : undefined,
      });
    }),
  );
}
