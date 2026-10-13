// Season in review (Phase 19). The season so far, or all of it once it is over, told from the schedule the Season page already
// has: the record, points for and against, streaks, the best win and the hardest loss, the close games, the biggest ranked
// win, and every game with its score. No extra calls. Works at any point of the season; with nothing played it says so.
//
//   reviewFacts(schedule) -> facts       pure; every number comes from the played games, missing scores are skipped
//   reviewGameRow(game, n)               one played game as a table row (exported for the tests)
//   createReviewView({ onStatus })       the page (#review)
//
// Tables wave 3 (owner 2026-10-10; docs/03-DESIGN.md, Table sizes): every data point in its own column, each table sized
// by its own box. The season in a few lines is two tables: the games that stood out (Fact | Site | AP rank | Opponent |
// Result | Date; the AP rank from medium, the date at large, the opponent's abbreviation at small, still its link; a row
// opens its box score) and the splits (Fact | Value), the facts in their written order with their shorter words below
// large. Every game: # | Date | Wk | Site | AP rank | Opponent | Result | Margin; medium drops the date and week, small the
// order and the AP rank. The games sort (the date by its day, the result by its margin), the season's order first. The
// site reads as the road ahead says it (Home, Away, Neutral; H, A, N at small). The scores keep the spoiler blur.

import { DASH, el, fmtDate, fmtNum, fmtSigned, isNum, obj, records } from "../ui/dom.js";
import { pollHref } from "../ui/national-link.js";
import { band, note, subhead } from "../ui/states.js";
import { pollBadge, statTable } from "../ui/stat-table.js";
import { tiles } from "../ui/team-page.js";
import { weekCell } from "../ui/weeks.js";
import { errorPanel, partState, poller } from "./common.js";

function played(schedule) {
  return records(schedule).filter((g) => g.completed === true && ["W", "L", "T"].includes(g.result) && isNum(g.usPoints) && isNum(g.themPoints));
}

function margin(g) {
  return g.usPoints - g.themPoints;
}

function streak(games) {
  // the run the season ends on ("W3"), and the longest winning run
  let longestWin = 0;
  let run = 0;
  for (const g of games) {
    run = g.result === "W" ? run + 1 : 0;
    longestWin = Math.max(longestWin, run);
  }
  const last = games[games.length - 1];
  let ending = 0;
  for (let i = games.length - 1; i >= 0 && last && games[i].result === last.result; i -= 1) ending += 1;
  return { longestWin, ending: last ? `${last.result}${ending}` : null };
}

export function reviewFacts(schedule) {
  const games = played(schedule).sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
  if (!games.length) return { games: 0 };
  const wins = games.filter((g) => g.result === "W");
  const losses = games.filter((g) => g.result === "L");
  const forPts = games.reduce((n, g) => n + g.usPoints, 0);
  const against = games.reduce((n, g) => n + g.themPoints, 0);
  const byMargin = [...games].sort((a, b) => margin(b) - margin(a));
  const ranked = (g) => isNum(obj(g.opponent).apRank);
  const rankedWins = wins.filter(ranked);
  const rankedGames = games.filter(ranked);
  const close = games.filter((g) => Math.abs(margin(g)) <= 8);
  const run = streak(games);
  return {
    games: games.length,
    wins: wins.length,
    losses: losses.length,
    ties: games.length - wins.length - losses.length,
    pointsFor: forPts,
    pointsAgainst: against,
    perGame: { for: forPts / games.length, against: against / games.length },
    averageMargin: (forPts - against) / games.length,
    longestWin: run.longestWin,
    ending: run.ending,
    bestWin: wins.length ? byMargin[0] : null,
    hardestLoss: losses.length ? byMargin[byMargin.length - 1] : null,
    bestRankedWin: rankedWins.length ? rankedWins.reduce((best, g) => (obj(g.opponent).apRank < obj(best.opponent).apRank ? g : best)) : null,
    ranked: { games: rankedGames.length, wins: rankedWins.length },
    close: { games: close.length, wins: close.filter((g) => g.result === "W").length },
    list: games,
  };
}

const SITE = { home: "Home", away: "Away", neutral: "Neutral" };
const SITE_SHORT = { home: "H", away: "A", neutral: "N" };

function words(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** One played game as a table row: the site, the opponent (school, abbreviation, AP rank), the result, its margin and the
 *  date. `n` is the game's place in the season. No game (no ranked win yet) is a row of dashes. */
export function reviewGameRow(g, n = null) {
  if (!g || typeof g !== "object") return { n, week: null, site: DASH, siteShort: null, opponent: null, oppAbbr: null, apRank: null, result: DASH, res: null, margin: null, date: null, dateText: DASH, gameId: null };
  const o = obj(g.opponent);
  const scored = ["W", "L", "T"].includes(g.result) && isNum(g.usPoints) && isNum(g.themPoints);
  const date = words(g.date);
  return {
    n,
    week: weekCell(g),
    site: SITE[g.homeAway] || DASH,
    siteShort: SITE_SHORT[g.homeAway] || null,
    opponent: words(o.school),
    oppAbbr: words(o.abbreviation),
    apRank: isNum(o.apRank) ? o.apRank : null,
    result: scored ? `${g.result} ${g.usPoints}-${g.themPoints}` : DASH,
    res: scored ? g.result : null,
    margin: scored ? margin(g) : null,
    date,
    dateText: date ? fmtDate(date, "short") : DASH,
    gameId: isNum(g.gameId) ? g.gameId : null,
  };
}

/** The columns both game tables share: Site, AP rank (from medium), Opponent (its abbreviation at small, still its link)
 *  and Result (sorting by its margin). `polled`: an AP poll is loaded, so an unranked opponent reads NR, else a dash. */
function gameColumns(polled) {
  return [
    { key: "site", label: "Site", kind: "text", shortKey: "siteShort" },
    {
      key: "apRank",
      label: "AP rank",
      labelMid: "AP",
      size: "medium",
      render: (row) => (isNum(row.apRank) ? pollBadge(row.apRank, "AP", { href: pollHref("AP", { team: row.opponent }), label: row.opponent, showPoll: false }) : row.opponent && polled ? el("span", { class: "nr" }, "NR") : DASH),
    },
    { key: "opponent", label: "Opponent", kind: "text", team: true, shortKey: "oppAbbr" },
    { key: "result", label: "Result", kind: "text", sortKey: "margin", render: (row) => (row.res ? el("span", { class: `res--${String(row.res).toLowerCase()}` }, row.result) : DASH) },
  ];
}

const openBox = (row) => {
  if (isNum(row.gameId)) window.location.hash = `box=${row.gameId}`;
};

export function reviewBody(overview) {
  const data = obj(overview);
  const f = reviewFacts(data.schedule);
  const overall = obj(obj(data.record).overall);
  if (!f.games) return note("No game has been played yet, so there is nothing to review. Come back after the first one.", { kind: "empty" });
  const record = isNum(overall.wins) ? `${overall.wins}-${overall.losses}${isNum(overall.ties) && overall.ties ? `-${overall.ties}` : ""}` : `${f.wins}-${f.losses}${f.ties ? `-${f.ties}` : ""}`;
  // while games remain the run is the current one, not the one the season ended on
  const underWay = records(data.schedule).some((g) => g.completed !== true);
  const polled = records(data.polls).some((poll) => poll.poll === "AP");
  const stoodOut = [
    { label: "Best win", game: f.bestWin },
    { label: "Best win over a ranked team", game: f.bestRankedWin },
    { label: "Hardest loss", game: f.hardestLoss },
  ].map(({ label, game }) => ({ ...reviewGameRow(game), label }));
  const splits = [
    { label: "Against ranked teams", value: f.ranked.games ? `${f.ranked.wins}-${f.ranked.games - f.ranked.wins}` : "none played" },
    { label: "Games decided by 8 or fewer", value: f.close.games ? `${f.close.wins}-${f.close.games - f.close.wins}` : "none" },
    { label: "Longest winning streak", value: f.longestWin ? `${f.longestWin} game${f.longestWin === 1 ? "" : "s"}` : "none" },
    { label: underWay ? "Current streak" : "The season ended on", value: f.ending || DASH },
  ];
  const rows = f.list.map((g, i) => reviewGameRow(g, i + 1));
  return el(
    "div",
    {},
    el("div", { class: "score-words" }, tiles([
      { label: "Record", value: record, format: "text", key: "review-record" },
      { label: "Points a game", value: f.perGame.for, format: "1f", key: "review-for" },
      { label: "Allowed a game", value: f.perGame.against, format: "1f", key: "review-against" },
      { label: "Average margin", value: f.averageMargin, format: "+1f", key: "review-margin" },
    ])),
    subhead("The season in a few lines"),
    el(
      "div",
      { class: "score-words review-facts" },
      // the facts keep their written order (the first column is the fact's name), each a row of its own columns
      statTable({ compact: true, sizes: true, columns: [{ key: "label", label: "Fact", kind: "text" }, ...gameColumns(polled), { key: "dateText", label: "Date", kind: "text", size: "large" }], rows: stoodOut, onRowTap: openBox, canTap: (row) => isNum(row.gameId), caption: "The games that stood out" }),
      statTable({ compact: true, sizes: true, columns: [{ key: "label", label: "Fact", kind: "text" }, { key: "value", label: "Value", kind: "text" }], rows: splits, caption: "The season's splits" }),
    ),
    subhead("Every game"),
    statTable({
      compact: true,
      sizes: true,
      columns: [
        { key: "n", label: "#", dim: true, size: "medium" },
        { key: "dateText", label: "Date", kind: "text", size: "large", sortKey: "date" },
        { key: "week", label: "Wk", dim: true, size: "large", sortKey: "n" },
        ...gameColumns(polled),
        { key: "margin", label: "Margin", format: "+0f", render: (row) => el("span", { class: "score-words" }, fmtSigned(row.margin)) },
      ],
      rows,
      sort: { key: "n", dir: "ascending" }, // the season's order to start
      onRowTap: openBox,
      canTap: (row) => isNum(row.gameId),
      caption: "Every game",
    }),
    el("p", { class: "note" }, `${fmtNum(f.pointsFor)} points scored and ${fmtNum(f.pointsAgainst)} allowed over ${f.games} game${f.games === 1 ? "" : "s"}. Tap a game for its box score.`),
  );
}

export function createReviewView({ onStatus } = {}) {
  return poller({
    url: "/api/season/overview",
    refreshMs: 15 * 60 * 1000,
    onStatus,
    render: (envelope, container) => {
      const data = obj(envelope?.data);
      container.replaceChildren(el("div", { class: "page review" }, el("h1", { class: "page-title" }, "Season in review"), band({ id: "review-main", title: "The season", collapsible: false, state: partState(data.parts?.schedule, true), errorLead: "Could not load the schedule.", body: () => reviewBody(data) })));
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Season in review", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "Season in review", collapsible: false, state: { status: "loading" } })),
    loadingDetail: "The season's games",
  });
}
