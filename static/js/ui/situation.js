// The situational table (L4): third down, fourth down, red zone, turnovers, penalties, time of possession, yards per play
// and yards, both teams, the better side in chalk.
//
// Table sizes, wave 2 (owner 2026-10-10; docs/03-DESIGN.md, Table sizes, rule 9): every row is already a Team stats row, so
// the panel is the Team stats table (ui/team-stats.js) with these eight rows under the head "Situation": the two-team kit
// with the tug-of-war bar, sized by its own box (the school and mascot at large, the school at medium, the abbreviation and
// the short names at small), with the Team stats flash keys and the count-only penalties before the box score posts. It
// is one table, no longer two half grids side by side.
//
//   SITUATION_LABELS                  the rows, in the panel's order (each a teamStatRows label)
//   situationRows(usBox, themBox)     those rows from teamStatRows, every one a parent row (no indent: no group here)
//   situationGrid({ us: { abbr, box, school, name }, them })   the sized table
//   situationSkeleton()               the loading rows in the table's shape

import { obj } from "./dom.js";
import { statTableSkeleton } from "./stat-table.js";
import { teamStatRows, teamStatsTable } from "./team-stats.js";

export const SITUATION_LABELS = ["Third down", "Fourth down", "Red zone", "Turnovers", "Penalties", "Time of possession", "Yards per play", "Yards"];

export function situationRows(usBox, themBox) {
  const all = teamStatRows(obj(usBox), obj(themBox));
  return SITUATION_LABELS.map((label) => all.find((row) => row.label === label)).filter(Boolean).map((row) => ({ ...row, kind: "parent" }));
}

/** situationGrid({ us: {abbr, box, school, name}, them: {...} }) */
export function situationGrid(options) {
  const { us, them } = obj(options);
  return teamStatsTable({ us, them, rows: situationRows(obj(us).box, obj(them).box), labelHead: "Situation", caption: "Situation" });
}

export function situationSkeleton() {
  return statTableSkeleton(SITUATION_LABELS.length, 4);
}
