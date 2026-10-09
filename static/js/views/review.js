// Season in review (Phase 19). The season so far, or all of it once it is over, told from the schedule the Season page already
// has: the record, points for and against, streaks, the best win and the hardest loss, the close games, the biggest ranked
// win, and every game with its score. No extra calls. Works at any point of the season; with nothing played it says so.
//
//   reviewFacts(schedule) -> facts       pure; every number comes from the played games, missing scores are skipped
//   createReviewView({ onStatus })       the page (#review)

import { DASH, el, fmtDate, fmtNum, fmtSigned, isNum, obj, records, text } from "../ui/dom.js";
import { band, note, subhead } from "../ui/states.js";
import { statTable } from "../ui/stat-table.js";
import { tiles } from "../ui/team-page.js";
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

function opp(g) {
  const o = obj(g.opponent);
  const rank = isNum(o.apRank) ? `#${o.apRank} ` : "";
  const where = g.homeAway === "away" ? "at " : g.homeAway === "neutral" ? "vs " : "";
  return `${where}${rank}${text(o.school)}`;
}

function gameLine(g) {
  return g ? `${opp(g)}: ${g.result} ${g.usPoints}-${g.themPoints}${g.date ? ` (${fmtDate(g.date, "short")})` : ""}` : DASH;
}

export function reviewBody(overview) {
  const data = obj(overview);
  const f = reviewFacts(data.schedule);
  const overall = obj(obj(data.record).overall);
  if (!f.games) return note("No game has been played yet, so there is nothing to review. Come back after the first one.", { kind: "empty" });
  const record = isNum(overall.wins) ? `${overall.wins}-${overall.losses}${isNum(overall.ties) && overall.ties ? `-${overall.ties}` : ""}` : `${f.wins}-${f.losses}${f.ties ? `-${f.ties}` : ""}`;
  const facts = [
    { label: "Best win", value: gameLine(f.bestWin) },
    { label: "Best win over a ranked team", value: gameLine(f.bestRankedWin) },
    { label: "Hardest loss", value: gameLine(f.hardestLoss) },
    { label: "Against ranked teams", value: f.ranked.games ? `${f.ranked.wins}-${f.ranked.games - f.ranked.wins}` : "none played" },
    { label: "Games decided by 8 or fewer", value: f.close.games ? `${f.close.wins}-${f.close.games - f.close.wins}` : "none" },
    { label: "Longest winning streak", value: f.longestWin ? `${f.longestWin} game${f.longestWin === 1 ? "" : "s"}` : "none" },
    { label: "The season ended on", value: f.ending || DASH },
  ];
  const rows = f.list.map((g, i) => ({ n: String(i + 1), opponent: opp(g), result: `${g.result} ${g.usPoints}-${g.themPoints}`, margin: margin(g), gameId: g.gameId, res: g.result }));
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
    el("div", { class: "score-words" }, statTable({ compact: true, columns: [{ key: "label", label: "", kind: "text", sortable: false }, { key: "value", label: "", kind: "text", sortable: false }], rows: facts })),
    subhead("Every game"),
    statTable({
      compact: true,
      columns: [
        { key: "n", label: "#", sortable: false, dim: true },
        { key: "opponent", label: "Opponent", kind: "text", sortable: false },
        { key: "result", label: "Result", kind: "text", sortable: false, render: (row) => el("span", { class: `res--${String(row.res).toLowerCase()}` }, row.result) },
        { key: "margin", label: "Margin", format: "+0f", sortable: false, render: (row) => el("span", { class: "score-words" }, fmtSigned(row.margin)) },
      ],
      rows,
      onRowTap: (row) => {
        if (isNum(row.gameId)) window.location.hash = `box=${row.gameId}`;
      },
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
