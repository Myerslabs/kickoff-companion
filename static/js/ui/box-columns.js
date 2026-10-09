// The player box-score tables (L2, X5): one column set per category, shared by the live sheet,
// the program's final box, and the archive. Row tap opens the player card.

import { el } from "./dom.js";
import { note } from "./states.js";
import { statTable } from "./stat-table.js";

export const BOX_COLUMNS = {
  passing: [{ key: "name", label: "Passing", kind: "text" }, { key: "C/ATT", label: "Comp-Att", kind: "text", sortable: false }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }, { key: "INT", label: "Int" }, { key: "QBR", label: "QBR", format: "1f" }],
  rushing: [{ key: "name", label: "Rushing", kind: "text" }, { key: "CAR", label: "Car" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Y/C", format: "1f" }, { key: "TD", label: "TD" }],
  receiving: [{ key: "name", label: "Receiving", kind: "text" }, { key: "REC", label: "Rec" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Y/R", format: "1f" }, { key: "TD", label: "TD" }],
  defensive: [{ key: "name", label: "Defense", kind: "text" }, { key: "TOT", label: "Tkl" }, { key: "SACKS", label: "Sacks", format: "1f" }, { key: "TFL", label: "TFL", format: "1f" }, { key: "PD", label: "PD" }],
  interceptions: [{ key: "name", label: "Interceptions", kind: "text" }, { key: "INT", label: "Int" }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }],
  kicking: [{ key: "name", label: "Kicking", kind: "text" }, { key: "FG", label: "FG", kind: "text", sortable: false }, { key: "XP", label: "XP", kind: "text", sortable: false }, { key: "PTS", label: "Pts" }],
  punting: [{ key: "name", label: "Punting", kind: "text" }, { key: "NO", label: "No" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "LONG", label: "Long" }],
  puntReturns: [{ key: "name", label: "Punt returns", kind: "text" }, { key: "NO", label: "No" }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }],
  kickReturns: [{ key: "name", label: "Kick returns", kind: "text" }, { key: "NO", label: "No" }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }],
};

/**
 * boxTables({ categories: {passing: [{name, playerId, stats}], ...}, onTap(row), emptyText })
 * One sortable table per category that has rows.
 */
export function boxTables({ categories = {}, onTap, emptyText = "No player lines yet." } = {}) {
  const cats = categories && typeof categories === "object" ? categories : {};
  const names = Object.keys(BOX_COLUMNS).filter((name) => Array.isArray(cats[name]) && cats[name].length);
  if (!names.length) return note(emptyText);
  return el(
    "div",
    {},
    names.map((name) => {
      const columns = BOX_COLUMNS[name];
      const rows = cats[name].filter((r) => r && typeof r === "object").map((r) => ({ name: r.name, playerId: r.playerId, ...(r.stats && typeof r.stats === "object" ? r.stats : {}) }));
      return statTable({ columns, rows, compact: true, sort: { key: columns[2]?.key || columns[1].key, dir: "descending" }, onRowTap: onTap ? (row) => onTap(row) : undefined });
    }),
  );
}
