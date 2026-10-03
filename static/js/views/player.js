// The player card opener (X1): fetches /api/players/{id} and shows the slide-over. Players
// without a card (outside our team and the next opponent) get a small card built from the row.
//
// Phase 16 (stream PEOPLE): a loading card first (LRP-07: name and number from the row, skeleton bars, and
// ours never drawn as the opponent), filled in place when the answer comes; stat columns in a curated
// order with plain labels (LRP-06); the game log as Wk | Opp | Result | stats with the opponent a team link
// and the right vs/at (LRP-11); Play value numbers as numbers; each Stats heading with a sparkline of that
// stat by game (LRP-16 c, GX-13 restrained).

import { DASH, el, fmtDate, fmtStat, isNum, teamLink, text } from "../ui/dom.js";
import { cardHeading, openPlayerCard, playerCard } from "../ui/player-card.js";
import { categoryColumns, categoryTitle, normalizeStat, statLabel, trendKey } from "../ui/stat-labels.js";
import { statTable } from "../ui/stat-table.js";
import { fetchJson } from "./common.js";
import { gradeBlock, gradeValue } from "../ui/grade.js";

const RATE_KEYS = /^(YPA|YPC|YPR|AVG|PCT|YPP|QBR)$/i;
const MAX_KEYS = /^LONG$/i;
const AVERAGES = { YPA: ["YDS", "ATT"], YPC: ["YDS", "CAR"], YPR: ["YDS", "REC"], YPP: ["YDS", "NO"], PCT: ["COMPLETIONS", "ATT"] };
const KICKING_AVERAGES = { ...AVERAGES, PCT: ["FGM", "FGA"] };

/** CFBD's PCT is completions in passing and field goals made in kicking. */
export function pctLabel(category) {
  return statLabel("PCT", category);
}

function games(gameLog) {
  return (Array.isArray(gameLog) ? gameLog : []).filter((g) => g && typeof g === "object");
}

function linesOf(game) {
  return (Array.isArray(game.lines) ? game.lines : []).filter((line) => line && typeof line === "object" && typeof line.category === "string" && line.category);
}

/** One category's key stat by game, oldest first, for the Stats-tab sparkline. Exported for the tests. */
export function trendValues(gameLog, category) {
  const want = trendKey(category);
  if (!want) return [];
  const out = [];
  for (const game of games(gameLog)) {
    const line = linesOf(game).find((l) => l.category === category);
    const value = line && line.stats && typeof line.stats === "object" ? line.stats[want.key] : null;
    if (isNum(value)) out.push(value);
  }
  return out;
}

/** One table per category, each with its own career row: sums for counts, max for LONG, recomputed rates. */
function seasonsTables(seasons, gameLog) {
  const rows = (Array.isArray(seasons) ? seasons : []).filter((s) => s && typeof s === "object" && typeof s.category === "string");
  const byCategory = new Map();
  for (const season of rows) {
    if (!byCategory.has(season.category)) byCategory.set(season.category, []);
    byCategory.get(season.category).push(season);
  }
  return [...byCategory.entries()].map(([category, list]) => {
    const keys = [];
    for (const season of list) for (const key of Object.keys(season.stats && typeof season.stats === "object" ? season.stats : {})) if (!keys.includes(key)) keys.push(key);
    const averages = String(category).toLowerCase() === "kicking" ? KICKING_AVERAGES : AVERAGES;
    const columns = [
      { key: "year", label: "Year", kind: "text" },
      ...categoryColumns(category, keys).map((c) => {
        const avg = averages[c.key.toUpperCase()];
        return { ...c, sum: !RATE_KEYS.test(c.key) && !MAX_KEYS.test(c.key), max: MAX_KEYS.test(c.key), avg: avg && keys.includes(avg[0]) && keys.includes(avg[1]) ? { num: avg[0], den: avg[1] } : null };
      }),
    ];
    const want = trendKey(category);
    return {
      title: categoryTitle(category),
      columns,
      rows: list.map((season) => ({ year: text(season.year), ...(season.stats && typeof season.stats === "object" ? season.stats : {}) })),
      trend: want ? { values: trendValues(gameLog, category), label: want.label, format: "0f" } : null,
    };
  });
}

/** "at" for a road game, "vs" at home or on a neutral field. */
function atOrVs(homeAway) {
  return homeAway === "away" ? "at" : "vs";
}

function oppCell(row) {
  if (!row.opponent) return null;
  return el("span", { class: "gl-opp" }, el("span", { class: "gl-opp__at" }, `${row.at} `), teamLink(row.opponent, text(row.opponent)));
}

function resultCell(row) {
  const m = typeof row.result === "string" ? /^([WLT])\b\s*(.*)$/.exec(row.result.trim()) : null;
  if (!m) return row.result ? text(row.result) : null;
  return el("span", { class: `gl-result gl-result--${m[1].toLowerCase()}` }, el("b", {}, m[1]), m[2] ? ` ${m[2]}` : "");
}

/** The first columns of every by-game table: Wk, Opp (a team link with at or vs), Result. */
function gameColumns({ result = true } = {}) {
  return [
    { key: "wk", label: "Wk", kind: "text" },
    { key: "opponent", label: "Opp", kind: "text", render: oppCell },
    ...(result ? [{ key: "result", label: "Result", kind: "text", render: resultCell }] : []),
  ];
}

function gameRow(game) {
  const label = typeof game.postseason === "string" && game.postseason.trim() ? game.postseason.trim() : null;
  return { wk: label || (isNum(game.week) ? String(game.week) : DASH), opponent: typeof game.opponent === "string" && game.opponent.trim() ? game.opponent.trim() : null, at: atOrVs(game.homeAway), result: typeof game.result === "string" ? game.result : null };
}

/** The game log laid out like the season tables (owner direction 2026-09-23): one table per category, one row per game. */
function gameLogTables(gameLog) {
  const byCategory = new Map();
  for (const game of games(gameLog)) {
    for (const line of linesOf(game)) {
      if (!byCategory.has(line.category)) byCategory.set(line.category, []);
      byCategory.get(line.category).push({ game, stats: line.stats && typeof line.stats === "object" ? line.stats : {} });
    }
  }
  return [...byCategory.entries()].map(([category, entries]) => {
    const keys = [];
    for (const entry of entries) for (const key of Object.keys(entry.stats)) if (!keys.includes(key)) keys.push(key);
    return {
      title: categoryTitle(category),
      columns: [...gameColumns(), ...categoryColumns(category, keys)],
      rows: entries.map((entry) => ({ ...gameRow(entry.game), ...Object.fromEntries(Object.entries(entry.stats).map(([k, v]) => [k, normalizeStat(k, v)])) })),
    };
  });
}

const PPA_SPLITS = [["all", "All plays"], ["pass", "Passing"], ["rush", "Rushing"], ["firstDown", "First down"], ["secondDown", "Second down"], ["thirdDown", "Third down"], ["standardDowns", "Standard downs"], ["passingDowns", "Passing downs"]];
const USAGE_SPLITS = [["overall", "All plays"], ["pass", "Passing"], ["rush", "Rushing"], ["firstDown", "First down"], ["secondDown", "Second down"], ["thirdDown", "Third down"], ["standardDowns", "Standard downs"], ["passingDowns", "Passing downs"]];

/** The Play value tab: season PPA by split, PPA by game, and usage share. Every number the app shows for a player is here. */
function extraPanels(data) {
  const ppa = data.ppa && typeof data.ppa === "object" ? data.ppa : {};
  const season = ppa.season && typeof ppa.season === "object" ? ppa.season : null;
  const usage = data.usage && typeof data.usage === "object" ? data.usage : null;
  const avg = season && season.average && typeof season.average === "object" ? season.average : {};
  const total = season && season.total && typeof season.total === "object" ? season.total : {};
  const seasonRows = season ? PPA_SPLITS.map(([key, label]) => ({ label, avg: avg[key], total: total[key] })) : [];
  // the by-game rows carry no home or away: the game log's row for that week says which
  const where = new Map(games(data.gameLog).filter((g) => isNum(g.week)).map((g) => [g.week, g]));
  const gameRows = (Array.isArray(ppa.games) ? ppa.games : []).filter((g) => g && typeof g === "object").map((g) => {
    const game = where.get(g.week);
    return { wk: isNum(g.week) ? String(g.week) : DASH, opponent: typeof g.opponent === "string" && g.opponent.trim() ? g.opponent.trim() : null, at: atOrVs(game && game.opponent === g.opponent ? game.homeAway : null), all: g.all, pass: g.pass, rush: g.rush };
  });
  const usageRows = usage ? USAGE_SPLITS.map(([key, label]) => ({ label, share: usage[key] })) : [];
  const body = el(
    "div",
    {},
    season
      ? el("p", { class: "note" }, `${isNum(season.plays) ? `${season.plays} plays graded. ` : ""}PPA per play ${fmtStat(avg.all, "+2f")}${isNum(ppa.teamRank) ? `, #${ppa.teamRank} of ${text(ppa.teamOf)} on the team` : ""}. Predicted points added per play: positive is good, and a season average settles down after a few games.`)
      : el("p", { class: "note" }, "No play value yet. CFBD grades players after each game; a player needs a handful of plays before an average means anything."),
    seasonRows.length ? el("div", { class: "player-card__block" }, cardHeading("Season by split"), statTable({ compact: true, columns: [{ key: "label", label: "Split", kind: "text" }, { key: "avg", label: "Per play", format: "+2f" }, { key: "total", label: "Total", format: "+2f" }], rows: seasonRows })) : null,
    gameRows.length ? el("div", { class: "player-card__block" }, cardHeading("By game"), statTable({ compact: true, sortable: false, columns: [...gameColumns({ result: false }), { key: "all", label: "PPA/play", format: "+2f" }, { key: "pass", label: "Pass", format: "+2f" }, { key: "rush", label: "Rush", format: "+2f" }], rows: gameRows })) : null,
    usageRows.length ? el("div", { class: "player-card__block" }, cardHeading("Usage, share of the team's plays"), statTable({ compact: true, columns: [{ key: "label", label: "Split", kind: "text" }, { key: "share", label: "Share", format: "pct" }], rows: usageRows })) : null,
  );
  const grade = data.grade && typeof data.grade === "object" ? data.grade : null; // public release Phase 7
  const graded = gradeValue(grade);
  return [{ label: graded === null ? "Stat grade" : `Grade ${Math.round(graded)}`, body: gradeBlock(grade) }, { label: "Play value", body }];
}

/** What the loading card already knows from the row that was tapped. */
function rowPlayer(playerId, fallback) {
  const row = fallback && typeof fallback === "object" ? fallback : {};
  const name = [row.player, row.name].find((v) => typeof v === "string" && v.trim());
  return {
    name: name || "Player",
    number: isNum(row.number) ? row.number : null,
    position: typeof row.position === "string" ? row.position : null,
    classYear: typeof row.classYear === "string" ? row.classYear : null,
    team: typeof row.team === "string" ? row.team : null,
    teamAbbr: typeof row.teamAbbr === "string" ? row.teamAbbr : null,
    headshotUrl: typeof row.headshotUrl === "string" ? row.headshotUrl : playerId ? `/media/headshot/${encodeURIComponent(playerId)}` : null,
  };
}

/** The props for a loaded card. Exported for the tests. */
export function cardPropsFrom(data) {
  const d = data && typeof data === "object" ? data : {};
  const p = d.player && typeof d.player === "object" ? d.player : {};
  const missing = Array.isArray(d.missingWeeks) ? d.missingWeeks.filter((w) => isNum(w)) : [];
  return {
    player: { ...p, height: p.heightText || p.height },
    seasons: seasonsTables(d.seasons, d.gameLog),
    gameLog: gameLogTables(d.gameLog),
    extras: extraPanels(d),
    history: (Array.isArray(d.history) ? d.history : []).filter((row) => row && typeof row === "object").map((row) => ({ ...row, year: text(row.year) })),
    them: p.isUs === false,
    note: missing.length ? `Box scores for week${missing.length > 1 ? "s" : ""} ${missing.join(", ")} could not be loaded.` : null,
  };
}

/** Open the card for a player id. `fallback` is a row from a board for players without a card.
 *  Returns the card's close function (with .update, see ui/player-card.js). */
export async function openPlayer(playerId, fallback = null) {
  const row = fallback && typeof fallback === "object" ? fallback : null;
  const them = row ? row.isUs === false : false; // our rows say isUs (LRP-07); only a row that says otherwise is the opponent
  const card = openPlayerCard({ player: rowPlayer(playerId, row), them, loading: true });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    if (playerId === null || playerId === undefined || String(playerId).trim() === "") throw Object.assign(new Error("No player id on this row"), { status: 404 });
    // Phase 15: a player found by search on another FBS team names the team, so the server reads its roster.
    const teamQuery = row && typeof row.team === "string" && row.team && row.isUs !== true ? `?team=${encodeURIComponent(row.team)}` : "";
    const envelope = await fetchJson(`/api/players/${encodeURIComponent(playerId)}${teamQuery}`, controller.signal);
    card.update(cardPropsFrom(envelope?.data));
  } catch (error) {
    if (row) {
      const detail = Object.entries(row.detail && typeof row.detail === "object" ? row.detail : {}).map(([k, v]) => ({ label: statLabel(k, row.category), value: text(v) }));
      card.update({
        player: rowPlayer(playerId, row),
        seasonStats: [{ label: text(row.boardLabel || "Value"), value: text(row.value) }, ...detail],
        gameLog: [],
        history: [],
        them,
        note: error?.status === 404 ? "Full cards exist for our team and the next opponent only." : `${error?.message || "Could not load the card"}.`,
      });
    } else {
      card.update({ player: { name: "Player" }, seasonStats: [], gameLog: [], history: [], note: `${error?.message || "Could not load the card"}.` });
    }
  } finally {
    clearTimeout(timeout);
  }
  return card;
}

export { playerCard, fmtDate, isNum, el };
