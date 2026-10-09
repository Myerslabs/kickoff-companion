// The Archive (X5): the games this app watched to the final. The list, then one game with
// everything the app captured live and everything CFBD posted afterwards: score by quarter,
// team stats with the feed's efficiency block, win probability, play value, drives, the play
// log with key plays, both box scores, and the notes of the week.

import { isUs, usLabel, usSchool } from "../identity.js";
import { weekCell, weekLong } from "../ui/weeks.js";
import { cover, coverSkeleton } from "../ui/cover.js";
import { gameNotesPanel } from "../ui/game-notes.js";
import { DASH, el, fmtDate, fmtStat, isNum, obj, records, teamLink, text } from "../ui/dom.js";
import { driveList, driveListSkeleton } from "../ui/drive-bar.js";
import { availabilityTable, editorial } from "../ui/editorial.js";
import { boxTables } from "../ui/box-columns.js";
import { playLog, playLogSkeleton } from "../ui/play-log.js";
import { backRow, band, note, sectionChips, subhead } from "../ui/states.js";
import { flow } from "../ui/flow.js";
import { statTable, statTableSkeleton } from "../ui/stat-table.js";
import { FEED_ROWS, quarterLine, teamStatsSkeleton, teamStatsTable } from "../ui/team-stats.js";
import { winProbabilityChart, winProbabilitySkeleton } from "../ui/wp-chart.js";
import { advancedBoxBlock } from "../ui/depth2.js";
import { errorPanel, fetchJson, partState, poller } from "./common.js";
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

/** The result in the win or loss color (Phase 16 wave 3, L-11). */
function resultCell(row) {
  const t = text(row.result);
  const tone = t.startsWith("W ") ? " res--w" : t.startsWith("L ") ? " res--l" : "";
  return el("span", { class: `archive-res${tone}` }, t);
}

/** "Away at Home", each team its own link (L-11; the row still opens the game). */
function matchupCell(row) {
  const team = (name) => (typeof name === "string" && name ? teamLink(name, name) : DASH);
  return el("span", {}, team(row.away), " at ", team(row.home));
}

// --- the list ----------------------------------------------------------------------------------------

/** The value when it is a plain object, else an empty one: archive files are read back as untrusted. */
/** The value when it is an array of records, else an empty list; malformed records are skipped. */
function listView(data) {
  const games = records(data.games);
  const columns = [
    { key: "dateText", label: "Date", kind: "text", sortable: false },
    { key: "week", label: "Wk", sortable: false, dim: true },
    { key: "matchup", label: "Game", kind: "text", sortable: false, render: matchupCell },
    { key: "result", label: "Result", kind: "text", sortable: false, render: resultCell },
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
  const spec = FEED_ROWS; // final pass: the same rows and names as the Live sheet
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
  const h3 = (t, team, side) => subhead(t, { team, side }); // DS-14: the shared sub-heading, a team's title its link
  const players = (title, rows, them) => el("div", {}, h3(title, title, them ? "them" : "us"), rows.length ? statTable({ compact: true, columns: [{ key: "name", label: "Player", kind: "text", sub: "position", sortable: false }, { key: "all", label: "PPA/play", format: "+2f", sortable: false }, { key: "pass", label: "Pass", format: "+2f", sortable: false }, { key: "rush", label: "Rush", format: "+2f", sortable: false }], rows, onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }) }) : note("No player values."));
  const teamRows = [["Offense", "offense"], ["Defense", "defense"]].flatMap(([label, side]) => ["overall", "passing", "rushing"].map((key) => ({ label: `${label}, ${key}`, us: ppa.teams?.us?.[side]?.[key], them: ppa.teams?.them?.[side]?.[key] })));
  const boxFor = (side) => obj(final.players?.[side] || s.playerStats?.[side === "us" ? US : themName]);
  // Final pass: a band whose CFBD part failed says so (and a stale one its age) instead of reading as "not posted"
  const parts = obj(data.parts);
  const stateOr = (part, has, ready, empty) => {
    if (part && part.status === "error") return partState(part, has);
    if (!has) return { status: "empty", message: empty };
    if (part && part.status === "stale") return { status: "stale", ageSeconds: part.ageSeconds, ...(ready || {}) };
    return { status: "ready", ...(ready || {}) };
  };

  // Final pass (structure-4, the owner's example page): the archived game flows like the Game program, bands packing
  // into 1 to 4 columns by width with the pinned section chips above and each band's title stuck under the top bar
  return el(
    "div",
    { class: "page archive archive--flow" },
    el("div", { class: "archive-top flow-full" }, backRow({ label: "All archived games", fallback: "#archive" }), el("span", { class: "note archive-top__saved" }, `Saved ${text(data.savedAt ? fmtDate(data.savedAt, "short") : DASH)}`)), // DS-03
    el("div", { class: "flow-full" }, cover({ kicker: `${weekLong({ ...g, week: data.week, seasonType: data.seasonType })} archive`, week: data.week, date: data.kickoff, venue: g.venue, neutralSite: g.neutralSite, tv: g.tv, homeIsUs: usHome, us: data.us || { school: US, abbreviation: usAbbr }, them: data.them || { school: themName, abbreviation: themAbbr }, line: data.line || {}, pregame: { homeWinProbability: data.pregame?.homeWinProbability }, state: "final", usPoints: data.usScore, themPoints: data.themScore, reveal: false })),
    band({ id: "archive-score", title: "Score by quarter", collapsible: false, summary: "Final", body: () => quarterLine({ us: { abbr: usAbbr, scores: usHome ? s.homeLineScores : s.awayLineScores, total: data.usScore }, them: { abbr: themAbbr, scores: usHome ? s.awayLineScores : s.homeLineScores, total: data.themScore } }) }),
      band({ id: "archive-stats", title: "Team stats", collapsible: false, foldable: true, body: () => el("div", {}, teamStatsTable({ us: { abbr: usAbbr, box: usBox }, them: { abbr: themAbbr, box: themBox } }), feedRows(s.feedStats, US, themName).length ? el("div", {}, h3("Efficiency, from the live feed"), statTable({ compact: true, columns: [{ key: "label", label: "Statistic", kind: "text", sortable: false }, { key: "usText", label: usAbbr, kind: "text", sortable: false }, { key: "themText", label: themAbbr, kind: "text", sortable: false }], rows: feedRows(s.feedStats, US, themName) })) : null) }),
      band({ id: "archive-wp", title: "Win probability", collapsible: false, foldable: true, state: stateOr(parts.wp, Boolean(wp.available), { updatedText: wp.source || "CFBD's post-game model" }, wp.note || "No win probability for this game."), body: () => winProbabilityChart({ series: Array.isArray(wp.series) ? wp.series : [], homeIsUs: usHome, usAbbr, pregame: data.pregame?.usWinProbability, final: true, plays }) }),
    band({
      id: "archive-advanced-box",
      title: "Advanced box score",
      collapsible: false,
      foldable: true,
      summary: "by quarter, line play, players' value",
      state: stateOr(parts.advancedBox, Boolean(data.advancedBox), null, "CFBD has not posted the advanced box score for this game."),
      body: () => advancedBoxBlock(data.advancedBox, { us: US, them: themName, usAbbr, themAbbr }),
    }),
    band({
      id: "archive-ppa",
      title: "Play value",
      collapsible: false,
      foldable: true,
      state: stateOr(parts.ppaUs, Boolean(ppa.available), null, ppa.note || "No play value for this game."),
      body: () => el("div", {}, teamRows.some((r) => isNum(r.us) || isNum(r.them)) ? statTable({ compact: true, columns: [{ key: "label", label: "PPA per play", kind: "text", sortable: false }, { key: "us", label: usAbbr, format: "+2f", sortable: false }, { key: "them", label: themAbbr, format: "+2f", sortable: false }], rows: teamRows }) : null, el("div", { class: "twocol" }, players(text(US), records(ppa.players?.us), false), players(text(themName), records(ppa.players?.them), true))),
    }),
      band({ id: "archive-drives", title: "Drives", collapsible: false, foldable: true, summary: `${text(s.counts?.drives)} drives`, body: () => (drives.length ? driveList({ drives, us: usSide, them: themSide, currentId: null }) : note("No drives were captured.")) }),
      band({ id: "archive-plays", title: "Play by play", collapsible: false, foldable: true, summary: `${text(s.counts?.plays)} plays, key plays under the filter`, body: () => (plays.length ? playLog({ plays: [...plays], us: usSide, them: themSide, maxHeight: 640 }) : note("No plays were captured.")) }),
    band({ id: "archive-box", title: "Box score", collapsible: false, foldable: true, summary: final?.available ? "CFBD's final box" : "from the live box polls", body: () => el("div", { class: "twocol" }, el("div", {}, h3(text(US), US, "us"), boxTables({ categories: boxFor("us"), onTap: (row) => openPlayer(row.playerId, { ...row, isUs: true }) })), el("div", {}, h3(text(themName), typeof themName === "string" ? themName : null, "them"), boxTables({ categories: boxFor("them"), onTap: (row) => openPlayer(row.playerId, { ...row, isUs: false }) }))) }),
      isNum(data.gameId) ? band({ id: "archive-mynotes", title: "My notes", collapsible: false, foldable: true, state: { status: "ready" }, body: () => gameNotesPanel({ gameId: data.gameId }) }) : null,
      band({ id: "archive-notes", title: "Program notes of the week", collapsible: false, foldable: true, collapsed: true, state: notes.present ? { status: "ready" } : { status: "empty", message: "No notes file for this game." }, body: () => editorial({ byline: { author: notes.author, writtenAt: notes.writtenAt }, sources: Array.isArray(notes.sources) ? notes.sources : [], sections: Array.isArray(notes.sections) ? notes.sections : [] }) }),
      band({ id: "archive-availability", title: "Availability report", collapsible: false, foldable: true, collapsed: true, state: availability.length ? { status: "ready" } : { status: "empty", message: "No availability report was filed." }, body: () => availabilityTable({ rows: availability, source: notes.availabilitySource, updatedAt: notes.availabilityUpdatedAt }) }),
  );
}

/** One archived game while it loads, in the shape of the page that comes (Phase 16 wave 3, L-13). */
function gameSkeleton() {
  const loading = { status: "loading" };
  return el(
    "div",
    { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } },
    backRow({ label: "All archived games", fallback: "#archive" }),
    coverSkeleton(),
    band({ title: "Score by quarter", collapsible: false, state: loading, skeleton: () => statTableSkeleton(2, 6) }),
    el("div", { class: "spread spread--2" }, band({ title: "Team stats", collapsible: false, state: loading, skeleton: () => teamStatsSkeleton(8) }), band({ title: "Win probability", collapsible: false, state: loading, skeleton: () => winProbabilitySkeleton() })),
    el("div", { class: "spread spread--2" }, band({ title: "Drives", collapsible: false, state: loading, skeleton: () => driveListSkeleton(5) }), band({ title: "Play by play", collapsible: false, state: loading, skeleton: () => playLogSkeleton(6) })),
  );
}

const ARCHIVE_WIDE = ["archive-stats", "archive-wp", "archive-advanced-box", "archive-drives", "archive-plays", "archive-box"]; // the data-heavy bands take two columns

export function createArchiveView({ onStatus, gameId = null } = {}) {
  const id = gameId && /^\d+$/.test(String(gameId)) ? String(gameId) : null;
  const ui = { flow: null, chips: null };
  const view = poller({
    url: id ? `/api/archive/${id}` : "/api/archive",
    refreshMs: 60 * 60 * 1000,
    onStatus,
    render: (envelope, container) => {
      if (ui.flow) ui.flow.stop();
      if (ui.chips) ui.chips.stop();
      ui.flow = null;
      ui.chips = null;
      if (!id) {
        container.replaceChildren(listView(obj(envelope?.data)));
        return;
      }
      const page = gameView(obj(envelope?.data));
      ui.chips = sectionChips(page); // the pinned section chips, above the page (Phase 17 #5, now here too)
      ui.chips.refresh();
      container.replaceChildren(ui.chips, page);
      ui.flow = flow(page, { wide: ARCHIVE_WIDE });
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Archive", message, retry)),
    renderLoading: () => (id ? gameSkeleton() : el("div", { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } }, band({ title: "Archive", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(6) }))),
  });
  return {
    ...view,
    mount: (target) => view.mount(target),
    unmount() {
      if (ui.flow) ui.flow.stop();
      if (ui.chips) ui.chips.stop();
      ui.flow = null;
      ui.chips = null;
      view.unmount();
    },
  };
}

export { fetchJson };
