// The series between two teams (tables wave 3, owner 2026-10-10): one sized table for the Pre-Game Program's Series band
// and every team page's History, so the last meetings read one way everywhere (docs/03-DESIGN.md, Table sizes).
//
//   SERIES_COLUMNS                       Year | Away | Home | Score (medium) | Winner (medium) | Result. The teams shorten
//                                        to their abbreviations at small (still their links); the score and the winner,
//                                        which the Result already carries, return from medium.
//   seriesRows(series, us, abbrs)        the server's lastTen from our side: "W 24-17" / "L 17-24" with our score first.
//                                        abbrs maps a school to its abbreviation for the small table. Exported for the tests.
//   seriesTable(series, { us, abbrs, caption })   the table, newest meeting first (the owner's order: a series reads
//                                        back from the last game, so it does not sort); a meeting we won is marked.

import { el, isNum } from "./dom.js";
import { statTable } from "./stat-table.js";

export const SERIES_COLUMNS = [
  { key: "season", label: "Year", kind: "text" },
  { key: "away", label: "Away", kind: "text", team: true, shortKey: "awayAbbr" },
  { key: "home", label: "Home", kind: "text", team: true, shortKey: "homeAbbr" },
  { key: "score", label: "Score", kind: "text", size: "medium" },
  { key: "winner", label: "Winner", kind: "text", team: true, shortKey: "winnerAbbr", size: "medium" },
  { key: "result", label: "Result", kind: "text", render: (row) => (row.result ? el("span", { class: row.won === true ? "res--w" : row.won === false ? "res--l" : null }, row.result) : "–") },
];

/** The series' last meetings from our side: "W 24-17" / "L 17-24" (P-13 item 1). `abbrs` maps a school to its abbreviation
    for the small table. Exported for the tests. */
export function seriesRows(series, us, abbrs = {}) {
  const games = Array.isArray(series?.lastTen) ? series.lastTen.filter((g) => g && typeof g === "object") : [];
  const short = (school) => (typeof school === "string" && abbrs && typeof abbrs[school] === "string" && abbrs[school].trim() ? abbrs[school].trim() : null);
  return games.map((g) => {
    const home = typeof g.homeTeam === "string" ? g.homeTeam : null;
    const away = typeof g.awayTeam === "string" ? g.awayTeam : null;
    const usHome = home === us;
    const mine = usHome ? g.homeScore : g.awayScore;
    const theirs = usHome ? g.awayScore : g.homeScore;
    const played = (home === us || away === us) && isNum(mine) && isNum(theirs);
    const won = played ? (mine > theirs ? true : mine < theirs ? false : null) : null;
    const winner = typeof g.winner === "string" && g.winner ? g.winner : null;
    return {
      season: isNum(g.season) ? String(g.season) : "–",
      away,
      home,
      awayAbbr: short(away),
      homeAbbr: short(home),
      score: isNum(g.awayScore) && isNum(g.homeScore) ? `${g.awayScore}-${g.homeScore}` : "–",
      winner,
      winnerAbbr: short(winner),
      won,
      result: played ? `${won === true ? "W" : won === false ? "L" : "T"} ${mine}-${theirs}` : null,
    };
  });
}

/** The series table, sized by its own box: newest meeting first, never re-sorted; a meeting we won is marked. */
export function seriesTable(series, { us, abbrs = {}, caption = "Series" } = {}) {
  return statTable({ compact: true, sortable: false, sizes: true, columns: SERIES_COLUMNS, rows: seriesRows(series, us, abbrs), rowClass: (row) => (row.won === true ? "is-us" : null), caption });
}
