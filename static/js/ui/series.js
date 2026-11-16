// The series between two teams (tables wave 3, owner 2026-10-10): one sized table for the Pre-Game Program's Series band
// and every team page's History, so the last meetings read one way everywhere (the design rules, Table sizes).
//
//   SERIES_COLUMNS                       Year | Away | Home | Score (medium) | Winner (medium) | Result. The teams shorten
//                                        to their abbreviations at small (still their links); the score and the winner,
//                                        which the Result already carries, return from medium.
//   seriesRows(series, us, abbrs)        the server's lastTen from our side: "W 24-17" / "L 17-24" with our score first.
//                                        abbrs maps a school to its abbreviation for the small table. Exported for the tests.
//   seriesTable(series, { us, abbrs, caption })   the table, newest meeting first (the owner's order: a series reads
//                                        back from the last game, so it does not sort); a meeting we won is marked.
//                                        ENH-15 (owner 2026-10-23: "Series band shows all games, 2+ columns"): every meeting
//                                        (the server's `games`, else an old lock's `lastTen`); past ten they run down side-by-side
//                                        columns, as many as fit at SERIES_COLUMN_MIN px each (four at most), newest first down
//                                        the first column, each column its own table headed by its years.
//   seriesColumnCount(width, n)          how many columns n meetings take at a box this wide. Exported for the tests.

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
  const list = Array.isArray(series?.games) ? series.games : Array.isArray(series?.lastTen) ? series.lastTen : []; // ENH-15: every meeting
  const games = list.filter((g) => g && typeof g === "object");
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

export const SERIES_COLUMN_MIN = 340;
const SHORT_SERIES = 10;

export function seriesColumnCount(width, n) {
  if (!isNum(n) || n <= SHORT_SERIES) return 1;
  const fit = isNum(width) && width > 0 ? Math.floor(width / SERIES_COLUMN_MIN) : 2;
  return Math.max(1, Math.min(4, fit, Math.ceil(n / SHORT_SERIES)));
}

function oneTable(rows, caption) {
  return statTable({ compact: true, sortable: false, sizes: true, columns: SERIES_COLUMNS, rows, rowClass: (row) => (row.won === true ? "is-us" : null), caption });
}

/** The series table, sized by its own box: newest meeting first, never re-sorted; a meeting we won is marked. A long series
    runs down side-by-side columns (ENH-15), redrawn when its box changes the count. */
export function seriesTable(series, { us, abbrs = {}, caption = "Series" } = {}) {
  const rows = seriesRows(series, us, abbrs);
  if (rows.length <= SHORT_SERIES) return oneTable(rows, caption);
  const holder = el("div", { class: "series-cols" });
  let drawn = 0;
  const draw = (count) => {
    if (count === drawn) return;
    drawn = count;
    holder.setAttribute("data-cols", String(count));
    const per = Math.ceil(rows.length / count);
    const parts = [];
    for (let i = 0; i < count; i += 1) {
      const chunk = rows.slice(i * per, (i + 1) * per);
      if (!chunk.length) continue;
      const span = chunk[0].season === chunk[chunk.length - 1].season ? chunk[0].season : `${chunk[0].season} to ${chunk[chunk.length - 1].season}`;
      parts.push(el("div", { class: "series-cols__col" }, el("p", { class: "series-cols__span" }, span), oneTable(chunk, `${caption}, ${span}`)));
    }
    holder.replaceChildren(...parts);
  };
  draw(seriesColumnCount(null, rows.length));
  if (typeof ResizeObserver === "function") {
    new ResizeObserver((entries) => {
      const box = entries?.[0]?.contentRect;
      if (box && box.width > 0) draw(seriesColumnCount(box.width, rows.length));
    }).observe(holder);
  }
  return holder;
}
