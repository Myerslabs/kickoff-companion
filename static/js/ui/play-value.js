// The players' play value tables (L9): each player's PPA per play, per pass and per rush, one column list for every page
// that shows them (the Pre-Game Program's season leaders and latest game, In Game's Play value panel, the Archive), so
// they all size alike.
//
// Table sizes, wave 2 (owner 2026-10-10; docs/03-DESIGN.md, Table sizes): each table sizes itself by its own box. Large
// has the whole heads (PPA per play, PPA per pass, PPA per rush) and the full name, and a season's table adds the plays
// and the total PPA (large only, owner 2026-10-10: the volume behind the average); medium the middle heads (PPA/play,
// Pass, Rush); small the surname and every value (PPA, Pass, Rush). A table of players sorts (owner 2026-09-26), the best
// value first as the server sends them. Wave 3 (owner 2026-10-10, decision 1): the position is its own column ("Pos") at
// large and medium, gone at small, never a line under the name; the name steps down with the table (item 6, owner
// 2026-10-11): whole at large, then "A. Passer" (at large first), the surname and the reduced surname at small.
//
//   playValueColumns({ totals })   the columns; totals: true adds Plays and Total PPA at large
//   playValueRows(list)            the server's player rows as table rows (every field it sent, the team for the player
//                                  card; name, position, all, pass, rush, plays and totalAll guarded:
//                                  a missing number null), the damaged ones skipped
//   playValueTable(list, { totals, onTap, caption, sort })
//       the sized table; onTap(row) opens the player; sort the starting order (PPA per play, the best first).

import { isNum, records } from "./dom.js";
import { statTable } from "./stat-table.js";

const num = (value) => (isNum(value) ? value : null);

export function playValueColumns({ totals = false } = {}) {
  return [
    { key: "name", label: "Player", kind: "text", sub: "position", subLabel: "Pos", person: true },
    { key: "all", label: "PPA per play", labelMid: "PPA/play", labelShort: "PPA", format: "+2f" },
    { key: "pass", label: "PPA per pass", labelMid: "Pass", labelShort: "Pass", format: "+2f" },
    { key: "rush", label: "PPA per rush", labelMid: "Rush", labelShort: "Rush", format: "+2f" },
    ...(totals ? [{ key: "plays", label: "Plays", size: "large" }, { key: "totalAll", label: "Total PPA", format: "+1f", size: "large" }] : []),
  ];
}

export function playValueRows(list) {
  return records(list).map((r) => ({
    ...r, // the rest of the server's row (the team) goes on to the player card
    name: typeof r.name === "string" ? r.name : null,
    position: typeof r.position === "string" ? r.position : null,
    all: num(r.all),
    pass: num(r.pass),
    rush: num(r.rush),
    plays: num(r.plays),
    totalAll: num(r.totalAll),
  }));
}

export function playValueTable(list, { totals = false, onTap, caption = "Play value, PPA per play", sort = { key: "all", dir: "descending" } } = {}) {
  return statTable({
    compact: true,
    sizes: true,
    columns: playValueColumns({ totals }),
    rows: playValueRows(list),
    sort,
    onRowTap: typeof onTap === "function" ? onTap : undefined,
    caption,
  });
}
