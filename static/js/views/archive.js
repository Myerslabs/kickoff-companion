// The Archive (X5): the games this app watched to the final. The list, then one game with
// everything the app captured live and everything CFBD posted afterwards: score by quarter,
// team stats with the feed's efficiency block, win probability, play value, drives, the play
// log with key plays, both box scores, and the notes of the week.

import { isUs, usLabel, usSchool } from "../identity.js";
import { weekCell, weekLong } from "../ui/weeks.js";
import { cover } from "../ui/cover.js";
import { DASH, el, fmtDate, fmtStat, isNum, text } from "../ui/dom.js";
import { driveList } from "../ui/drive-bar.js";
import { availabilityTable, editorial } from "../ui/editorial.js";
import { boxTables } from "../ui/box-columns.js";
import { playLog } from "../ui/play-log.js";
import { band, note } from "../ui/states.js";
import { statTable, statTableSkeleton } from "../ui/stat-table.js";
import { quarterLine, teamStatsTable } from "../ui/team-stats.js";
import { winProbabilityChart } from "../ui/wp-chart.js";
import { advancedBoxBlock } from "../ui/depth2.js";
import { errorPanel, fetchJson, poller } from "./common.js";
import { openPlayer } from "./player.js";

function abbrOf(school, data) {
  if (isUs(school)) return usLabel();
  const them = data?.them && typeof data.them === "object" ? data.them : {};
  if (school && them.school === school && them.abbreviation) return them.abbreviation;
  return String(school || DASH).slice(0, 4).toUpperCase();
}

function resultText(g) {
  if (!isNum(g.usScore) || !isNum(g.themScore)) return DASH;
  const tag = g.usScore > g.themScore ? "W" : g.usScore < g.themScore ? "L" : "T";
  return `${tag} ${g.usScore}-${g.themScore}`;
}

// --- the list ----------------------------------------------------------------------------------------

/** The value when it is a plain object, else an empty one: archive files are read back as untrusted. */
function obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

/** The value when it is an array of records, else an empty list; malformed records are skipped. */
function records(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object") : [];
}

function listView(data) {
  const games = records(data.games);
  const columns = [
    { key: "dateText", label: "Date", kind: "text", sortable: false },
    { key: "week", label: "Wk", sortable: false, dim: true },
    { key: "matchup", label: "Game", kind: "text", sortable: false },
    { key: "result", label: "Result", kind: "text", sortable: false },
    { key: "plays", label: "Plays", sortable: false },
    { key: "wp", label: "Win prob.", kind: "text", sortable: false },
  ];
  const rows = games.map((g) => ({ ...g, week: weekCell(g), dateText: g.kickoff ? fmtDate(g.kickoff, "short") : DASH, matchup: `${text(g.away)} at ${text(g.home)}`, result: resultText(g), wp: g.hasWinProbability ? "yes" : "after the final" }));
  return el(
    "div",
    { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } },
    band({
      id: "archive-list",
      title: "Archive",
      collapsible: false,
      summary: games.length ? `${games.length} game${games.length === 1 ? "" : "s"} this app watched` : "",
      state: games.length ? { status: "ready" } : { status: "empty", message: "No games yet. A game lands here when the app watches it to the final; nothing is back-filled." },
      body: () => el("div", {}, statTable({ compact: true, columns, rows, onRowTap: (row) => { window.location.hash = `archive=${row.gameId}`; }, caption: "Archived games" }), isNum(data.skipped) && data.skipped > 0 ? el("p", { class: "note note--error" }, `${data.skipped} archive file${data.skipped === 1 ? "" : "s"} could not be read; see the log.`) : null),
    }),
  );
}

// --- one game ---------------------------------------------------------------------------------------

function feedRows(feed, usName, themName) {
  if (!feed || typeof feed !== "object") return [];
  const us = feed[usName] || {};
  const them = feed[themName] || {};
  // No success rate here: the team table above shows it (CFBD's own from Phase 10a on), as on the Live sheet.
  const spec = [["EPA per play", "epaPerPlay", "+2f"], ["EPA per pass", "epaPerPass", "+2f"], ["EPA per rush", "epaPerRush", "+2f"], ["Explosiveness", "explosiveness", "2f"], ["Points per opportunity", "pointsPerOpportunity", "1f"], ["Scoring opportunities", "scoringOpportunities", "0f"], ["Deserve to win", "deserveToWin", "pct"]];
  return spec.map(([label, key, format]) => ({ label, usText: isNum(us[key]) ? fmtStat(us[key], format) : DASH, themText: isNum(them[key]) ? fmtStat(them[key], format) : DASH, has: isNum(us[key]) || isNum(them[key]) })).filter((r) => r.has);
}

function gameView(data) {
  const s = obj(data.state);
  const usHome = Boolean(data.homeIsUs);
  const themName = data.opponent || (usHome ? s.away : s.home);
  const themAbbr = abbrOf(themName, data);
  const US = typeof data.us?.school === "string" && data.us.school ? data.us.school : usSchool();
  const usAbbr = typeof data.us?.abbreviation === "string" && data.us.abbreviation ? data.us.abbreviation : usLabel();
  const usSide = { name: US, abbr: usAbbr };
  const themSide = { name: themName, abbr: themAbbr };
  // successCounts is null from Phase 10a on (the rate is CFBD's); the team table reads only the rate.
  const usBox = { ...obj(obj(s.box)[US]), ...Object.fromEntries(Object.entries(obj(obj(s.boxScore)[US])).filter(([, v]) => v !== null && v !== undefined)) };
  const themBox = { ...obj(obj(s.box)[themName]), ...Object.fromEntries(Object.entries(obj(obj(s.boxScore)[themName])).filter(([, v]) => v !== null && v !== undefined)) };
  const drives = records(s.drives);
  const plays = records(s.plays);
  const wp = obj(data.winProbability);
  const ppa = obj(data.ppa);
  const final = obj(data.final);
  const notes = obj(data.notes);
  const availability = records(notes.availability);
  const g = obj(data.game);
  const h3 = (t) => el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, t);
  const players = (title, rows, them) => el("div", {}, h3(title), rows.length ? statTable({ compact: true, columns: [{ key: "name", label: "Player", kind: "text", sub: "position", sortable: false }, { key: "all", label: "PPA/play", format: "+2f", sortable: false }, { key: "pass", label: "Pass", format: "+2f", sortable: false }, { key: "rush", label: "Rush", format: "+2f", sortable: false }], rows, onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }) }) : note("No player values."));
  const teamRows = [["Offense", "offense"], ["Defense", "defense"]].flatMap(([label, side]) => ["overall", "passing", "rushing"].map((key) => ({ label: `${label}, ${key}`, us: ppa.teams?.us?.[side]?.[key], them: ppa.teams?.them?.[side]?.[key] })));
  const boxFor = (side) => obj(final.players?.[side] || s.playerStats?.[side === "us" ? US : themName]);

  return el(
    "div",
    { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } },
    el("div", { class: "sg__row", style: { display: "flex", gap: "8px", alignItems: "center" } }, el("a", { class: "btn btn--quiet", href: "#archive" }, "← All archived games"), el("span", { class: "note", style: { padding: 0 } }, `Saved ${text(data.savedAt ? fmtDate(data.savedAt, "short") : DASH)}`)),
    cover({ kicker: `${weekLong({ ...g, week: data.week, seasonType: data.seasonType })} archive`, week: data.week, date: data.kickoff, venue: g.venue, neutralSite: g.neutralSite, tv: g.tv, homeIsUs: usHome, us: data.us || { school: US, abbreviation: usAbbr }, them: data.them || { school: themName, abbreviation: themAbbr }, line: data.line || {}, pregame: { homeWinProbability: data.pregame?.homeWinProbability }, state: "final", usPoints: data.usScore, themPoints: data.themScore, reveal: false }),
    band({ id: "archive-score", title: "Score by quarter", collapsible: false, summary: "Final", body: () => quarterLine({ us: { abbr: usAbbr, scores: usHome ? s.homeLineScores : s.awayLineScores, total: data.usScore }, them: { abbr: themAbbr, scores: usHome ? s.awayLineScores : s.homeLineScores, total: data.themScore } }) }),
    el(
      "div",
      { class: "spread spread--2" },
      band({ id: "archive-stats", title: "Team stats", collapsible: false, foldable: true, body: () => el("div", {}, teamStatsTable({ us: { abbr: usAbbr, box: usBox }, them: { abbr: themAbbr, box: themBox } }), feedRows(s.feedStats, US, themName).length ? el("div", {}, h3("Efficiency, from the live feed"), statTable({ compact: true, columns: [{ key: "label", label: "Per play", kind: "text", sortable: false }, { key: "usText", label: usAbbr, kind: "text", sortable: false }, { key: "themText", label: themAbbr, kind: "text", sortable: false }], rows: feedRows(s.feedStats, US, themName) })) : null) }),
      band({ id: "archive-wp", title: "Win probability", collapsible: false, foldable: true, state: wp.available ? { status: "ready", updatedText: wp.source || "CFBD's post-game model" } : { status: "empty", message: wp.note || "No win probability for this game." }, body: () => winProbabilityChart({ series: Array.isArray(wp.series) ? wp.series : [], homeIsUs: usHome, usAbbr, pregame: data.pregame?.usWinProbability, final: true }) }),
    ),
    band({
      id: "archive-advanced-box",
      title: "Advanced box score",
      collapsible: false,
      foldable: true,
      summary: "by quarter, line play, players' value",
      state: data.advancedBox ? { status: "ready" } : { status: "empty", message: "CFBD has not posted the advanced box score for this game." },
      body: () => advancedBoxBlock(data.advancedBox, { us: US, them: themName, usAbbr, themAbbr }),
    }),
    band({
      id: "archive-ppa",
      title: "Play value",
      collapsible: false,
      foldable: true,
      state: ppa.available ? { status: "ready" } : { status: "empty", message: ppa.note || "No play value for this game." },
      body: () => el("div", {}, teamRows.some((r) => isNum(r.us) || isNum(r.them)) ? statTable({ compact: true, columns: [{ key: "label", label: "PPA per play", kind: "text", sortable: false }, { key: "us", label: usAbbr, format: "+2f", sortable: false }, { key: "them", label: themAbbr, format: "+2f", sortable: false }], rows: teamRows }) : null, el("div", { class: "twocol" }, players(text(US), records(ppa.players?.us), false), players(text(themName), records(ppa.players?.them), true))),
    }),
    el(
      "div",
      { class: "spread spread--2" },
      band({ id: "archive-drives", title: "Drives", collapsible: false, foldable: true, summary: `${text(s.counts?.drives)} drives`, body: () => (drives.length ? driveList({ drives, us: usSide, them: themSide, currentId: null }) : note("No drives were captured.")) }),
      band({ id: "archive-plays", title: "Play by play", collapsible: false, foldable: true, summary: `${text(s.counts?.plays)} plays, key plays under the filter`, body: () => (plays.length ? playLog({ plays: [...plays], us: usSide, them: themSide, maxHeight: 640 }) : note("No plays were captured.")) }),
    ),
    band({ id: "archive-box", title: "Box score", collapsible: false, foldable: true, summary: final?.available ? "CFBD's final box" : "from the live box polls", body: () => el("div", { class: "twocol" }, el("div", {}, h3(text(US)), boxTables({ categories: boxFor("us"), onTap: (row) => openPlayer(row.playerId, { ...row, isUs: true }) })), el("div", {}, h3(text(themName)), boxTables({ categories: boxFor("them"), onTap: (row) => openPlayer(row.playerId, { ...row, isUs: false }) }))) }),
    el(
      "div",
      { class: "spread spread--2" },
      band({ id: "archive-notes", title: "Program notes of the week", collapsible: false, foldable: true, collapsed: true, state: notes.present ? { status: "ready" } : { status: "empty", message: "No notes file for this game." }, body: () => editorial({ byline: { author: notes.author, writtenAt: notes.writtenAt }, sources: Array.isArray(notes.sources) ? notes.sources : [], sections: Array.isArray(notes.sections) ? notes.sections : [] }) }),
      band({ id: "archive-availability", title: "Availability report", collapsible: false, foldable: true, collapsed: true, state: availability.length ? { status: "ready" } : { status: "empty", message: "No availability report was filed." }, body: () => availabilityTable({ rows: availability, source: notes.availabilitySource, updatedAt: notes.availabilityUpdatedAt }) }),
    ),
  );
}

export function createArchiveView({ onStatus, gameId = null } = {}) {
  const id = gameId && /^\d+$/.test(String(gameId)) ? String(gameId) : null;
  return poller({
    url: id ? `/api/archive/${id}` : "/api/archive",
    refreshMs: 60 * 60 * 1000,
    onStatus,
    render: (envelope, container) => container.replaceChildren(id ? gameView(obj(envelope?.data)) : listView(obj(envelope?.data))),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Archive", message, retry)),
    renderLoading: () => el("div", { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } }, band({ title: "Archive", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(6) })),
  });
}

export { fetchJson };
