// The Game program (P1 to P10): picker, cover, notes and availability, matchup card with
// schemes, tale of the tape with the edges table, leaders side by side, series, weather, and
// the final box for a past game. Tap the opponent for its team page.

import { confLabel, usLabel, usName, usSchool } from "../identity.js";
import { weekCell, weekLong } from "../ui/weeks.js";
import { cover, coverSkeleton } from "../ui/cover.js";
import { DASH, el, flashChanges, fmtDate, fmtNum, fmtPct, fmtStat, fmtTime, isNum, replaceWith, snapshotKeys, text } from "../ui/dom.js";
import { availabilityTable, editorial } from "../ui/editorial.js";
import { hasLineups, lineupSummary } from "../ui/lineups.js";
import { lineupBlock } from "../ui/lineups_combined.js";
import { fullName, matchupCard, venueLine, weatherRow } from "../ui/matchup-card.js";
import { crewText, teamStaff } from "../ui/game-staff.js";
import { flow } from "../ui/flow.js";
import { starStrip } from "../ui/team-page.js";
import { scheduleList } from "../ui/schedule.js";
import { backRow, band, note, revealBand, sectionChips, stateBlock, subhead } from "../ui/states.js";
import { boxTables } from "../ui/box-columns.js"; // final pass: one copy of the box-score columns; wave 2: one sized box score on every page
import { statTable, statTableSkeleton } from "../ui/stat-table.js";
import { trendRow } from "../ui/sparkline.js";
import { seriesTable } from "../ui/series.js";
import { applyOpponentColors } from "../ui/colors.js";
import { PPA_SCALE, twoTeamTable } from "../ui/two-team.js";
import { nationalHref } from "../ui/national-link.js";
import { edgesSummary } from "../ui/edges.js";
import { tapeTable } from "../ui/tape.js";
import { leadersGrid, statLine } from "../ui/leaders.js";
import { leaderLines } from "../ui/leader-lines.js";
import { quarterLine, teamStatRows, teamStatsTable } from "../ui/team-stats.js";
import { radioSnapshot } from "../radio.js";
import { radioStations } from "../ui/radio-stations.js";
import { pollMs } from "../prefs.js";
import { gameNotesPanel } from "../ui/game-notes.js";
import { printButton } from "../ui/print.js";
import { newsDigest, newsSkeleton } from "../ui/news.js";
import { notesPaste } from "../ui/notes-paste.js";
import { GRADE_NOTE, gradedTable } from "../ui/grade.js";
import { playValueTable } from "../ui/play-value.js";
import { errorPanel, fetchJson, fetchPatient, partState, poller } from "./common.js";
import { openPlayer } from "./player.js";
import { adjustedMatchup, advancedBoxBlock, matchupGroups, tendenciesBlock } from "../ui/depth2.js";
import { commonOpponentsBlock, lastSeasonTwoTeam } from "../ui/offday.js";
import { resultsBand } from "../ui/results.js";
import { twoSchoolsBand } from "../ui/two-schools.js";

/** A payload part as an object, or {} (a list, a string or null never reaches a band). */
function objOf(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

/** A payload list with only its object rows (one bad record never breaks a band). */
function listOf(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object" && !Array.isArray(row)) : [];
}

// --- Phase 13: the advanced matchup, the opponent's tendencies, a finished game's advanced box -------

function advancedBand(data) {
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const adv = data.advanced && typeof data.advanced === "object" ? data.advanced : {};
  return band({
    id: "program-advanced",
    title: "Advanced matchup",
    collapsible: true,
    foldable: true,
    summary: "line play, havoc, finishing, downs",
    state: partState(data.parts?.advanced, Array.isArray(adv.us) && adv.us.length > 0),
    emptyText: "Advanced stats appear once both teams have played.",
    body: () => el("div", {}, matchupGroups(adv.us, adv.them, { usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, tug: true }), subhead("Adjusted for the opponents each team has faced"), adjustedMatchup(data.adjusted, { usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, tug: true })),
  });
}

function tendenciesBand(data) {
  const t = data.tendencies && typeof data.tendencies === "object" ? data.tendencies : null;
  return band({
    id: "program-tendencies",
    title: `${text(data.them?.school)} tendencies`,
    collapsible: true,
    foldable: true,
    summary: t && isNum(t.plays) && t.plays > 0 ? `${t.plays} snaps, run ${isNum(t.runRate) ? fmtPct(t.runRate) : DASH}` : "",
    state: partState(data.parts?.oppRushes, Boolean(t && t.plays)),
    emptyText: "The opponent's play calls appear once it has played.",
    body: () => tendenciesBlock(t, abbrOf(data.them)),
  });
}

function advancedBoxBand(data) {
  if (!data.game?.completed) return null; // only a finished game has one
  return band({
    id: "program-advanced-box",
    title: "Advanced box score",
    collapsible: true,
    foldable: true,
    summary: data.advancedBox ? "by quarter, players' value" : "",
    state: partState(data.parts?.advancedBox, Boolean(data.advancedBox)),
    emptyText: "CFBD has not posted the advanced box score for this game.",
    // wave 2: the schools and mascots head the two teams' table at large; a player's row opens his card
    body: () => advancedBoxBlock(data.advancedBox, { us: data.us?.school || usSchool(), them: data.them?.school, usAbbr: abbrOf(data.us, usLabel()), themAbbr: abbrOf(data.them), usName: fullName(data.us), themName: fullName(data.them), onPlayer: (row) => openPlayer(row.playerId, { ...row, boardLabel: "PPA per play", value: fmtStat(row.ppa, "+2f") }) }),
  });
}


function weatherFromData(w, game, { label } = {}) {
  if (!w || typeof w !== "object") return weatherRow({ note: "No forecast yet.", label });
  const kickoffText = game?.startTimeTbd ? "Time TBD" : fmtTime(game?.kickoff);
  if (!w.available) return weatherRow({ kickoffText, label, note: typeof w.error === "string" && w.error ? w.error : "No forecast yet.", radarUrl: w.radarUrl });
  const source = typeof w.source === "string" && w.source ? `${w.source}${w.stale ? ", stale" : ""}${typeof w.period === "string" && w.period ? `, ${w.period}` : ""}` : null;
  return weatherRow({ kickoffText, label, tempF: w.tempF, windMph: w.windMph, windDir: typeof w.windDir === "string" ? w.windDir : null, sky: w.sky, precipChance: w.precipChance, indoors: w.dome === true, source, radarUrl: w.radarUrl });
}

/**
 * The cover's bottom right (owner mockup 2026-10-10, the Weather band retired): the forecast with its Radar link-out (UX-14)
 * and the stadium's facts under it (GX-19). A finished game shows the kickoff weather when it was observed, else only the
 * stadium's facts; null when there is neither. Exported for the tests.
 */
export function coverConditions(data) {
  const d = data && typeof data === "object" ? data : {};
  const g = d.game && typeof d.game === "object" ? d.game : {};
  const venue = venueLine(g.venueDetail, { us: d.us?.school || usSchool() });
  if (!g.completed) return el("div", { class: "conditions", "aria-label": "Weather and stadium" }, weatherFromData(d.weather, g), venue);
  const w = d.weather && typeof d.weather === "object" ? d.weather : null;
  const observed = Boolean(w && w.available && (isNum(w.tempF) || (typeof w.sky === "string" && w.sky)));
  if (!observed && !venue) return null;
  return el("div", { class: "conditions", "aria-label": "Weather and stadium" }, observed ? weatherFromData(w, g, { label: "Kickoff weather" }) : null, venue);
}

/** "Week 2, Campbell" for a picker game, for the cover's arrows. */
function pickerLabel(game) {
  const g = game && typeof game === "object" ? game : {};
  const week = g.postseason ? text(g.postseason) : isNum(g.week) ? `Week ${g.week}` : null;
  return [week, typeof g.opponent?.school === "string" ? g.opponent.school : null].filter(Boolean).join(", ") || null;
}

/** The games before and after this one in the picker's order, as the cover's arrows (P-03 item 3). */
export function neighbours(picker, gameId) {
  const games = (Array.isArray(picker) ? picker : []).filter((g) => g && typeof g === "object" && (isNum(g.gameId) || /^\d+$/.test(String(g.gameId ?? ""))));
  const at = games.findIndex((g) => String(g.gameId) === String(gameId));
  if (at < 0) return { prev: null, next: null };
  const link = (g) => (g ? { href: `#program=${encodeURIComponent(String(g.gameId))}`, label: pickerLabel(g) } : null);
  return { prev: link(games[at - 1]), next: link(games[at + 1]) };
}

function coverProps(data, { reveal = false } = {}) {
  const g = data.game || {};
  const around = neighbours(data.picker, g.gameId);
  return {
    kicker: g.postseason ? `${weekLong(g)} program` : g.completed ? `Week ${text(g.week)} program` : "This week's program",
    week: g.week,
    date: g.kickoff,
    startTimeTbd: g.startTimeTbd,
    venue: g.venue,
    neutralSite: g.neutralSite,
    tv: g.tv,
    crew: crewText(data.notes, g), // Phase 17 #2: the announcers from the notes, beside the network
    // the cover redo (owner mockup 2026-10-10): each team's coaches under its own block, the weather and stadium bottom right
    staff: {
      us: teamStaff(data.notes, "us", { abbr: abbrOf(data.us, usLabel()), school: data.us?.school || usSchool() }),
      them: teamStaff(data.notes, "them", { abbr: abbrOf(data.them), school: data.them?.school }),
    },
    conditions: coverConditions(data),
    homeIsUs: g.homeIsUs,
    us: data.us || {},
    them: data.them || {},
    line: data.line || {},
    pregame: { homeWinProbability: data.pregame?.homeWinProbability },
    state: g.completed ? "final" : "pre",
    usPoints: g.usPoints,
    themPoints: g.themPoints,
    reveal: reveal && !g.completed,
    liveHref: "#live",
    heldUntil: typeof g.heldUntil === "string" ? g.heldUntil : null, // owner 2026-10-10: the server holds this final on In Game until then
    archiveHref: g.archived === true && (isNum(g.gameId) || /^\d+$/.test(String(g.gameId ?? ""))) ? `#archive=${encodeURIComponent(String(g.gameId))}` : null,
    prev: around.prev,
    next: around.next,
  };
}

/** "Write this week's notes": starts the notes task on the desktop and follows it until the file lands.
 *  quiet (notes exist, P-14): one quiet 'Rewrite notes' line in the band's foot; its status and log only
 *  while it runs or after an error. Public release Phase 6: shown only where the server finds the Claude
 *  Code command; everywhere else copy and paste (ui/notes-paste.js) is the way. */
function notesTaskControl(gameId, { quiet = false } = {}) {
  const host = el("div", { class: `notes-task${quiet ? " notes-task--quiet" : ""}` });
  let timer = null;
  const statusText = (status, problem, running) => {
    if (problem) return `${problem}.`;
    if (!status) return null;
    if (running) return `Running for game ${text(status.gameId)} since ${fmtTime(status.startedAt)}. The page refreshes itself when the file lands.`;
    if (status.error) return `Last run: ${text(status.error)}.`;
    if (quiet) return status.finishedAt ? `last run ${fmtTime(status.finishedAt)}` : null;
    return status.finishedAt ? `Last run finished ${fmtTime(status.finishedAt)}${status.fileWritten ? ", notes saved" : ""}.` : "Runs Claude Code on the server computer with the same prompt.";
  };
  const draw = (status, problem) => {
    if (!host.isConnected && timer) {
      clearInterval(timer);
      timer = null;
      return;
    }
    if (!problem && status?.commandFound !== true && !status?.running) {
      host.replaceChildren(); // no Claude Code on the server (or not known yet): copy and paste only
      return;
    }
    const running = Boolean(status?.running);
    const tail = Array.isArray(status?.logTail) ? status.logTail.filter((line) => typeof line === "string").slice(-4) : [];
    const says = statusText(status, problem, running);
    const label = running ? "Writing…" : quiet ? "Rewrite with Claude Code" : "Write them with Claude Code";
    replaceWith(
      host,
      el("div", { class: "notes-task__row" },
        el("button", { class: `btn${quiet ? " btn--quiet" : " btn--primary"}`, type: "button", disabled: running || !status?.commandFound ? true : null, onclick: () => start() }, label),
        says ? el("span", { class: "notes-task__status" }, says) : null,
      ),
      tail.length && (running || status?.error) ? el("pre", { class: "notes-task__log" }, tail.join("\n")) : null,
    );
  };
  const poll = async () => {
    try {
      const envelope = await fetchJson("/api/notes/run");
      const status = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      draw(status, null);
      if (status && !status.running && timer) {
        clearInterval(timer);
        timer = null;
        if (status.fileWritten && !status.error) window.location.reload();
      }
    } catch (error) {
      draw(null, error?.message || "Could not read the notes task");
    }
  };
  const start = async () => {
    try {
      const response = await fetch("/api/notes/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ gameId: isNum(gameId) ? gameId : null }) });
      const envelope = await response.json();
      draw(envelope?.data || null, envelope?.errors?.[0]?.message || null);
      if (envelope?.data?.running && !timer) timer = setInterval(poll, 5000);
    } catch (error) {
      draw(null, error?.message || "Could not start the notes task");
    }
  };
  draw(null, null);
  poll().then(() => {
    if (!timer) timer = setInterval(poll, 5000);
  });
  return host;
}

function notesBand(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  const id = text(data.game?.gameId);
  const body = () => {
    if (n.error) {
      return el(
        "div",
        { class: "notes-empty" },
        note(`${text(n.error)}. Paste a new answer below, or fix data/notes/${id}.json and reload.`, { kind: "error", lead: "Notes file problem." }),
        notesPaste({ gameId: data.game?.gameId }),
      );
    }
    if (!n.present) {
      return el(
        "div",
        { class: "notes-empty" },
        notesPaste({ gameId: data.game?.gameId }), // Phase 17 #12: one line, two copy buttons, the box, one Save
        notesTaskControl(data.game?.gameId),
      );
    }
    const records = (value) => (Array.isArray(value) ? value.filter((r) => r && typeof r === "object") : []);
    return el(
      "div",
      {},
      editorial({ byline: { author: n.author, writtenAt: n.writtenAt }, sources: records(n.sources), sections: records(n.sections) }),
      el("div", { class: "notes-foot" },
        el("details", { class: "notes-replace" }, el("summary", {}, "Replace with a new answer"), notesPaste({ gameId: data.game?.gameId })),
        notesTaskControl(data.game?.gameId, { quiet: true }),
      ),
    );
  };
  return band({ id: "program-notes", title: "Program notes", collapsible: true, foldable: true, summary: n.present ? `by ${text(n.author)}` : "not written yet", state: { status: "ready" }, body });
}

/**
 * The empty state of a band filled from the game's notes (Phase 17 #13): what is missing, where it comes from,
 * and an "Add notes" button that unfolds the Program notes band and scrolls to it.
 */
function notesNeeded(lead, detail) {
  return stateBlock({
    lead,
    detail,
    action: {
      label: "Add notes",
      onClick: (event) => {
        const page = event?.currentTarget?.closest?.(".page") || document;
        const notes = page.querySelector("#program-notes");
        if (notes) revealBand(notes);
      },
    },
  });
}

function myNotesBand(data) {
  const gameId = data.game?.gameId;
  if (!isNum(gameId)) return null;
  return band({ id: "program-mynotes", title: "My notes", collapsible: true, foldable: true, collapsed: true, summary: "your own lines", state: { status: "ready" }, body: () => gameNotesPanel({ gameId }) });
}

function availabilityBand(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  const rows = Array.isArray(n.availability) ? n.availability.filter((r) => r && typeof r === "object") : [];
  return band({
    id: "program-availability",
    title: "Availability report",
    collapsible: true,
    foldable: true,
    summary: rows.length ? `${rows.length} listed` : "",
    state: { status: "ready" },
    body: () => (rows.length ? availabilityTable({ rows, source: n.availabilitySource, updatedAt: n.availabilityUpdatedAt, teams: [{ school: data.us?.school || usSchool(), abbreviation: abbrOf(data.us, usLabel()) }, { school: data.them?.school, abbreviation: abbrOf(data.them) }] }) : notesNeeded("No availability report for this game yet.", `It comes with the game's notes, from the ${confLabel()} availability report when the conference publishes one.`)),
  });
}

/**
 * Lineups and depth in one band (Phase 19, owner 2026-10-08): the starter at every slot with his season chips, the depth behind
 * him in the last column, the starters' experience on top, our unit beside theirs. It replaces the two bands of 2026-10-02.
 */
function lineupsBand(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  return band({
    id: "program-lineups",
    title: "Lineups and depth",
    collapsible: true,
    foldable: true,
    summary: lineupSummary(n.lineups) || "",
    state: { status: "ready" },
    body: () => (hasLineups(n.lineups)
      ? lineupBlock({ lineups: n.lineups, us: data.us, them: data.them, availability: n.availability, onPlayer: (row) => openPlayer(row.playerId, { ...row.player, name: row.name, position: row.slot, isUs: row.isUs !== false }) })
      : notesNeeded("No lineups for this game yet.", "They come with the game's notes, from both teams' published depth charts.")),
  });
}

function profileRow(rows, key) {
  return (Array.isArray(rows) ? rows : []).find((r) => r && typeof r === "object" && r.key === key) || {};
}

/** A team's short name for column heads: its abbreviation, else the first letters of its name (an FCS team has none). */
export function abbrOf(team, fallback = "–") {
  const t = team && typeof team === "object" ? team : {};
  if (typeof t.abbreviation === "string" && t.abbreviation.trim()) return t.abbreviation.trim();
  if (typeof t.school === "string" && t.school.trim()) return t.school.trim().replace(/[^A-Za-z&]/g, "").slice(0, 3).toUpperCase() || fallback;
  return fallback;
}

const CARD_ROWS = [["offense", "ppg", "Points per game"], ["offense", "ypg", "Yards per game"], ["offense", "ypp", "Yards per play"], ["offense", "pass_ypg", "Pass yards per game"], ["offense", "rush_ypg", "Rush yards per game"], ["offense", "third", "Third down"], ["defense", "opp_ppg", "Points allowed per game"], ["defense", "ypg_d", "Yards allowed per game"], ["defense", "ypp_d", "Yards allowed per play"], ["defense", "pass_ypg_d", "Pass yards allowed per game"], ["defense", "rush_ypg_d", "Rush yards allowed per game"], ["defense", "third_d", "Third down allowed"]];

function matchup(data) {
  const them = data.them || {};
  const usRows = data.profile?.us || [];
  const themRows = data.profile?.them || [];
  const schemes = data.notes?.schemes || null;
  const tags = [];
  if (data.game?.postseason) tags.push({ label: text(data.game.playoffRound || data.game.postseason || "Bowl game") });
  else if (data.game?.conferenceGame) tags.push({ label: confLabel() }); // 2026-10-10: the conference's short name alone
  const teamTags = [];
  if (isNum(them.sp?.rank)) teamTags.push({ label: `SP+ #${them.sp.rank}`, href: nationalHref(typeof them.sp.metric === "string" ? them.sp.metric : "rating:sp", { team: them.school }), rank: them.sp.rank, of: them.sp.of, name: "SP+" });
  const ours = typeof data.us?.school === "string" && data.us.school.trim() ? data.us.school.trim() : usSchool();
  // the conference rank the profile already carries (inside our conference, so a non-conference opponent has none)
  const confOf = (r, school, metric) => (isNum(r.conferenceRank) ? { rank: r.conferenceRank, of: r.conferenceOf, conference: confLabel(), href: nationalHref(metric, { team: school, scope: "conference" }) } : null);
  const rows = CARD_ROWS.map(([side, key, label]) => {
    const u = profileRow(usRows, key);
    const t = profileRow(themRows, key);
    const metric = u.metric || t.metric || `profile:${key}`;
    return { label, side, key, metric, format: u.format || t.format, higherIsBetter: typeof u.higherIsBetter === "boolean" ? u.higherIsBetter : t.higherIsBetter, us: { value: u.value, rank: u.nationalRank, of: u.nationalOf, conf: confOf(u, data.us?.school, metric) }, them: { value: t.value, rank: t.nationalRank, of: t.nationalOf, conf: confOf(t, them.school, metric) } };
  });
  return matchupCard({
    us: { ...(data.us || {}), abbreviation: abbrOf(data.us, usLabel()) },
    them: { ...them, abbreviation: abbrOf(them) },
    kicker: `${text(ours)}'s opponent`, // Phase 17 #9: the program speaks from our side
    teamTags,
    tags,
    schemes,
    onNotes: () => {
      const notes = document.getElementById("program-notes");
      if (notes) revealBand(notes); // 2026-10-10: a missing scheme sends the reader to the notes, never a blank
    },
    rows,
  });
}

/** What the radio is doing, for the band's summary line while it is folded (P-12 item 2). */
export function radioSummary(snap) {
  const s = snap && typeof snap === "object" ? snap : {};
  const name = typeof s.current?.name === "string" && s.current.name ? s.current.name : null;
  if (s.loadError && !name) return "Unavailable";
  if (!name && s.loaded && Array.isArray(s.sources) && s.sources.length === 0) return "No station yet";
  if (!name) return "Off";
  switch (s.state) {
    case "playing": return `Playing · ${name}`;
    case "connecting": return `Connecting · ${name}`;
    case "paused": return `Paused · ${name}`;
    case "embedded": return `Station player · ${name}`;
    case "error": return "Could not play";
    default: return name;
  }
}

/** The radio control (X4, owner direction 2026-09-23: on the Game program). The player itself lives in
 *  the shell's dock so the audio keeps playing when the view changes; this band only starts and stops it.
 *  P-12: the summary says what is playing, and each source is one 44px row: name, kind, button. The list is shared with
 *  In Game's Radio sheet (ui/radio-stations.js, owner 2026-10-11). */
function radioBand() {
  let summary = null;
  const host = radioStations({ onDraw: (snap) => { if (summary) summary.textContent = radioSummary(snap); } });
  const section = band({ id: "program-radio", title: "Radio", collapsible: true, foldable: true, summary: radioSummary(radioSnapshot()), state: { status: "ready" }, body: () => host });
  summary = section.querySelector(".band__summary");
  return section;
}

/** P-15 item 1: each unit's PPA per play by game as a trend line, the latest value on the right. */
function ppaTrends(p, data) {
  const games = (side) => (Array.isArray(p.games?.[side]) ? p.games[side].filter((g) => g && typeof g === "object") : []);
  const series = (side, unit) => games(side).map((g) => g[unit]?.overall).filter(isNum);
  const lines = [
    ["us", "offense", `${text(data.us?.school || usSchool())} offense`],
    ["us", "defense", `${text(data.us?.school || usSchool())} defense`],
    ["them", "offense", `${text(data.them?.school)} offense`],
    ["them", "defense", `${text(data.them?.school)} defense`],
  ].map(([side, unit, label]) => ({ side, label, values: series(side, unit) }));
  if (!lines.some((l) => l.values.length > 1)) return null; // a trend needs two games
  return el("div", { class: "ppa-trends" }, lines.map((l) => trendRow({ label: l.label, values: l.values, format: "+2f", them: l.side === "them" })), el("p", { class: "ppa-trends__note" }, "PPA per play by game, oldest on the left. Defense: lower is better."));
}

// The by-game play value (wave 2, owner 2026-10-10): sized by its own box. Large has the whole heads, the defense's saying
// "allowed" (rule: a defensive measure says so); medium the box words (Off pass, Def rush); small the week, the opponent's
// abbreviation and the two overall values. A divider sets the defense apart from the offense. A table of games sorts.
const ppaColumn = (key, label, labelMid, labelShort, extra = {}) => ({ key, label, labelMid, labelShort, format: "+2f", ...extra });
export const PPA_GAME_COLUMNS = [ // exported for the tests
  { key: "week", label: "Week", labelMid: "Wk", labelShort: "Wk", dim: true },
  { key: "opponent", label: "Opponent", labelShort: "Opp", kind: "text", team: true, shortKey: "opponentAbbr" },
  ppaColumn("offOverall", "Offense, overall", "Off", "Off"),
  ppaColumn("offPass", "Offense, passing", "Off pass", "Off pass", { size: "medium" }),
  ppaColumn("offRush", "Offense, rushing", "Off rush", "Off rush", { size: "medium" }),
  ppaColumn("defOverall", "Defense allowed, overall", "Def", "Def", { divider: true }),
  ppaColumn("defPass", "Defense allowed, passing", "Def pass", "Def pass", { size: "medium" }),
  ppaColumn("defRush", "Defense allowed, rushing", "Def rush", "Def rush", { size: "medium" }),
];

/** A team's graded games as rows for the by-game table, newest first; a missing value is null (a dash). Exported for the tests. */
export function ppaGameRows(games) {
  const num = (value) => (isNum(value) ? value : null);
  return listOf(games).reverse().map((g) => ({
    week: weekCell(g),
    opponent: typeof g.opponent === "string" ? g.opponent : null,
    opponentAbbr: typeof g.opponentAbbr === "string" && g.opponentAbbr.trim() ? g.opponentAbbr.trim() : null,
    offOverall: num(objOf(g.offense).overall),
    offPass: num(objOf(g.offense).passing),
    offRush: num(objOf(g.offense).rushing),
    defOverall: num(objOf(g.defense).overall),
    defPass: num(objOf(g.defense).passing),
    defRush: num(objOf(g.defense).rushing),
  }));
}

/** Play value (L9): PPA per play for both teams by game and for the season, and each team's players from its latest game. */
function ppaBand(data) {
  const p = objOf(data.ppa);
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const fmt = (v) => (isNum(v) ? fmtStat(v, "+2f") : DASH);
  // Group five (owner 2026-10-09: the program is a matchup): the season table reads as the pairs the edges use. Offense
  // PPA and defense PPA allowed are the same measure of the same plays, so our gain per play stands against what their
  // defense gives up, and the edge goes to the side whose number is better on that pair.
  const season = (team, side, key) => (isNum(p.season?.[team]?.[side]?.[key]) ? p.season[team][side][key] : null);
  const pairRow = (label, mine, theirs, side) => ({
    label,
    format: "+2f",
    scale: PPA_SCALE, // PPA per play is a small number: a gap of 0.5 leans the bar all the way
    us: { value: mine },
    them: { value: theirs },
    leads: mine !== null && theirs !== null ? (mine === theirs ? "even" : (side === "offense" ? mine > theirs : mine < theirs) ? "us" : "them") : undefined,
  });
  const PAIR_KEYS = [["overall", "Overall"], ["passing", "Passing"], ["rushing", "Rushing"]];
  const seasonGroups = [
    { title: `${usAbbr} offense vs ${themAbbr} defense`, note: "our gain per play against what they allow", rows: PAIR_KEYS.map(([key, label]) => pairRow(label, season("us", "offense", key), season("them", "defense", key), "offense")) },
    { title: `${themAbbr} offense vs ${usAbbr} defense`, note: "what we allow against their gain per play", rows: PAIR_KEYS.map(([key, label]) => pairRow(label, season("us", "defense", key), season("them", "offense", key), "defense")) },
  ];
  const h3 = (t, school, side) => subhead(t, school ? { team: school, side } : {});
  // wave 2 (owner 2026-10-10): the players' tables are the shared play value kit (ui/play-value.js), the season leaders with
  // their plays and total PPA at large; the games sort (a table of games), newest first to start
  const players = (title, rows, them, totals) => el("div", {}, h3(title, them ? data.them?.school : data.us?.school || usSchool(), them ? "them" : "us"), rows.length ? playValueTable(rows, { totals, onTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }), caption: title }) : note("No player values yet."));
  const games = (title, rows, them) => el("div", {}, h3(title, them ? data.them?.school : data.us?.school || usSchool(), them ? "them" : "us"), rows.length ? statTable({ compact: true, sizes: true, columns: PPA_GAME_COLUMNS, rows, caption: title }) : note("No graded games yet."));
  return band({
    id: "program-ppa",
    title: "Play value",
    collapsible: true,
    foldable: true,
    collapsed: true,
    summary: `PPA per play: ${usAbbr} offense ${fmt(p.season?.us?.offense?.overall)}, ${themAbbr} ${fmt(p.season?.them?.offense?.overall)}`,
    state: partState(data.parts?.ppaUs, Boolean(p.available)),
    emptyText: "Play value appears once CFBD grades the first game.",
    body: () =>
      el(
        "div",
        {},
        note("Predicted points added per play. Positive is good for an offense; negative is good for a defense."),
        ppaTrends(p, data),
        h3("Season, per play: each offense against the defense it faces"),
        twoTeamTable({ groups: seasonGroups, usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, tug: true, labelHead: "PPA per play", caption: "Season PPA per play, each offense against the defense it faces" }),
        el("div", { class: "twocol" }, players(`${text(data.us?.school)} season leaders, PPA per play`, listOf(p.seasonLeaders?.us), false, true), players(`${text(data.them?.school)} season leaders, PPA per play`, listOf(p.seasonLeaders?.them), true, true)),
        games(`${text(data.us?.school)} by game`, ppaGameRows(p.games?.us)),
        games(`${text(data.them?.school)} by game`, ppaGameRows(p.games?.them), true),
        el("div", { class: "twocol" }, players(`${text(data.us?.school)}, ${isNum(p.players?.usWeek) ? `week ${p.players.usWeek}` : "latest game"}`, listOf(p.players?.us), false, false), players(`${text(data.them?.school)}, ${isNum(p.players?.themWeek) ? `week ${p.players.themWeek}` : "latest game"}`, listOf(p.players?.them), true, false)),
      ),
  });
}

// Wave 2 (owner 2026-10-10): each team's stars are a sized stat table, ours at the left hand and theirs at the right (Phase
// 18.4), stacked when the band is too narrow for two, never a sideways scroll. Large has every star level (about 570 px
// with the hints); medium keeps the blue chips, the 3-stars, the average and the signee count (the half of a 1080p band);
// small drops the signee count and the hints too, and the unit reads Off, Def or All.
const STAR_LEVELS = ["5", "4", "3", "2", "1"];
const STARS_COLUMNS = [
  { key: "who", label: "Unit", kind: "text", shortKey: "whoShort", render: (row) => el("span", {}, text(row.who), isNum(row.signees) ? el("small", {}, `${row.signees} signee${row.signees === 1 ? "" : "s"}`) : null) },
  ...STAR_LEVELS.map((level) => ({
    key: `s${level}`,
    label: `${level}-star`,
    size: level === "2" || level === "1" ? "large" : undefined, // the blue chips and the 3-stars carry the message below large
    render: (row) => (level === "5" || level === "4" ? el("span", { class: "stars-split__hot" }, String(row[`s${level}`])) : String(row[`s${level}`])),
  })),
  { key: "average", label: "Avg stars", labelShort: "Avg", format: "2f" },
];

/** One unit's star counts as a table row: a missing count is a zero (nobody signed at that level), a missing average null. */
function starsRow(who, whoShort, s) {
  const counts = objOf(s.counts);
  const row = { who, whoShort, signees: isNum(s.signees) ? s.signees : null, average: isNum(s.average) ? s.average : null };
  for (const level of STAR_LEVELS) row[`s${level}`] = isNum(counts[level]) ? counts[level] : 0;
  return row;
}

/** Talent and recruiting, side by side: talent composite with rank, blue-chip ratio, returning production. */
/** Phase 17 #36: each team's signees in the blue-chip classes by stars, our strip then theirs. */
/**
 * Phase 17 #36, #24: each team's signees of the last four classes by stars, offense and defense apart (owner:
 * "Separate this into offense and defense for recruiting"): a sized table per team (wave 2), a row per side. A server
 * without the split draws each team's one strip as before.
 */
export function starsPair(us, them, usAbbr, themAbbr) {
  const tables = [];
  const split = (team) => ["offense", "defense"].some((key) => objOf(objOf(objOf(team).sides)[key]).counts && typeof objOf(objOf(objOf(team).sides)[key]).counts === "object");
  const anySplit = split(us) || split(them); // none: an older server, each team's one strip below
  for (const [team, abbr, side] of [[objOf(us), usAbbr, "us"], [objOf(them), themAbbr, "them"]]) {
    const sides = objOf(team.sides);
    const rows = [["offense", "Offense", "Off"], ["defense", "Defense", "Def"]].filter(([key]) => objOf(sides[key]).counts && typeof objOf(sides[key]).counts === "object").map(([key, who, short]) => starsRow(who, short, objOf(sides[key])));
    const whole = objOf(team.stars);
    if (anySplit && !rows.length && whole.counts && typeof whole.counts === "object") rows.push(starsRow("All", "All", { counts: whole.counts, average: whole.average })); // an older answer has no offense and defense split
    if (!rows.length) continue;
    const caption = `${text(abbr)} signees by stars, last four classes`;
    tables.push(
      el(
        "div",
        { class: `stars-split__team stars-split__team--${side}` },
        el("p", { class: "stars-split__caption", "aria-hidden": "true" }, caption), // the table's own caption is for screen readers
        statTable({ compact: true, sizes: true, sortable: false, columns: STARS_COLUMNS, rows, rowClass: () => (side === "us" ? "is-us" : "is-next"), caption }),
      ),
    );
  }
  if (tables.length) return el("div", { class: "stars-split" }, tables); // our table at the left hand, theirs at the right (Phase 18.4)
  const strip = (team, abbr, side) => {
    const s = objOf(objOf(team).stars);
    if (!s.counts || typeof s.counts !== "object") return null;
    return el("div", { class: `stars-pair__team stars-pair__team--${side}` }, el("div", { class: "stars-pair__who" }, `${text(abbr)} signees, last four classes`), starStrip({ counts: s.counts, average: s.average }));
  };
  const a = strip(us, usAbbr, "us");
  const b = strip(them, themAbbr, "them");
  return a || b ? el("div", { class: "stars-pair" }, a, b) : null;
}

/** "Athletes (ATH) and specialists aren't in either side: SWT 6, OPP 4." Null when there are none to mention. */
function apartNote(us, them, usAbbr, themAbbr) {
  const n = (t) => {
    const a = objOf(objOf(objOf(t).sides).apart);
    const total = [a.athlete, a.specialist, a.unknown].filter(isNum).reduce((x, y) => x + y, 0);
    return isNum(a.athlete) || isNum(a.specialist) ? total : null;
  };
  const u = n(us);
  const t = n(them);
  if (!u && !t) return null;
  return el("p", { class: "note" }, `Athletes not yet given a position (ATH), kickers, punters and snappers count on neither side: ${text(usAbbr)} ${isNum(u) ? u : 0}, ${text(themAbbr)} ${isNum(t) ? t : 0}.`);
}

function recruitingBand(data) {
  const r = objOf(data.recruiting);
  const us = objOf(r.us);
  const them = objOf(r.them);
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const pct = (v) => (isNum(v) ? fmtStat(v, "pct") : DASH);
  // Blue-chip and returning ranks come from the national pulls (owner-approved calls); no rank means a plain value.
  const blueChip = (t) => ({ value: t.blueChip?.ratio, rank: t.blueChip?.nationalRank, of: t.blueChip?.nationalOf, tie: t.blueChip?.tied, metric: t.blueChip?.metric });
  const returning = (key) => (t) => {
    const ranked = objOf(objOf(t.returning?.ranks)[key]);
    return { value: t.returning?.[key], rank: ranked.rank, of: ranked.of, tie: ranked.tied, metric: objOf(t.returning?.metrics)[key] };
  };
  const pair = (label, pick, format) => {
    const u = pick(us);
    const th = pick(them);
    return { label, format, higherIsBetter: true, metric: u.metric || th.metric, us: u, them: th };
  };
  const rows = [
    { label: "Talent composite", format: "0f", higherIsBetter: true, metric: us.talent?.metric || them.talent?.metric || "rating:talent", us: { value: us.talent?.talent, rank: us.talent?.rank, of: us.talent?.of ?? us.talentOf }, them: { value: them.talent?.talent, rank: them.talent?.rank, of: them.talent?.of ?? them.talentOf } },
    pair("Blue-chip ratio", blueChip, "pct"),
    pair("Blue-chip ratio, offense", (t) => ({ value: objOf(objOf(t.sides).offense).blueChipRatio }), "pct"),
    pair("Blue-chip ratio, defense", (t) => ({ value: objOf(objOf(t.sides).defense).blueChipRatio }), "pct"),
    pair("Average rating, offense", (t) => ({ value: objOf(objOf(t.sides).offense).averageRating }), "4f"),
    pair("Average rating, defense", (t) => ({ value: objOf(objOf(t.sides).defense).averageRating }), "4f"),
    pair("Roster cost (rumored)", (t) => ({ value: objOf(t.costs).totalUsd }), "usd"), // Phase 17 Part 3b
    pair("Returning production", returning("percentPPA"), "pct"),
    pair("Returning passing", returning("percentPassing"), "pct"),
    pair("Returning receiving", returning("percentReceiving"), "pct"),
    pair("Returning rushing", returning("percentRushing"), "pct"),
  ];
  const has = rows.some((row) => isNum(row.us.value) || isNum(row.them.value));
  return band({
    id: "program-recruiting",
    title: "Talent and recruiting",
    collapsible: true,
    foldable: true,
    summary: isNum(us.blueChip?.ratio) && isNum(them.blueChip?.ratio) ? `blue chips ${usAbbr} ${pct(us.blueChip.ratio)}, ${themAbbr} ${pct(them.blueChip.ratio)}` : "talent, blue chips, returning production",
    state: partState(data.parts?.talent, has),
    emptyText: "Talent and recruiting figures appear once CFBD has them for both teams.",
    body: () => el("div", {}, twoTeamTable({ rows, usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, tug: true, caption: "Talent and recruiting, both teams" }), starsPair(us, them, usAbbr, themAbbr), apartNote(us, them, usAbbr, themAbbr), el("p", { class: "note" }, "Talent is the 247Sports composite of the roster. Blue-chip ratio is four- and five-star signees over all signees in the last four classes; 50% is the line every champion since 2011 has cleared. Offense and defense split the same signees by the position they were recruited at; the average rating is 247's composite, from 0 to 1. Returning production is the share of last season's predicted points added that is back.")),
  });
}

/** "SWT better in 14 of 24": who has the better number, from the rows in hand (P-11 item 4). */
function tapeBand(data) {
  // Owner pick (2026-10-09): both matchups of a stat in one row with a tug bar each, the rank chips in their own
  // headed columns; the three biggest edges per side marked (spec P3). Biggest edges, the same pairings, folded in.
  const edges = Array.isArray(data.edges) ? data.edges : [];
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  return band({
    id: "program-tape",
    title: "Tale of the tape",
    collapsible: true,
    foldable: true,
    summary: edgesSummary(edges, { usAbbr, themAbbr }),
    state: partState(data.parts?.stats, edges.length > 0),
    emptyText: "The matchup appears once both teams have played.",
    body: () =>
      el(
        "div",
        {},
        tapeTable(edges, { usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school }),
        note("Each unit's national rank against the unit it faces: our offense against their defense, then our defense against their offense (side by side on a wide screen, one above the other on a narrower one). The bar leans to the side with the better rank, longer for a bigger gap; the three biggest edges on each side are marked. Who scores or allows more as a team is on the matchup card above."),
      ),
  });
}

/** A program leaders payload side as a leadersGrid player: its number in the board's format with a unit. */
export function programLeader(entry, cat) {
  if (!entry || typeof entry !== "object") return null;
  return { name: entry.player ?? entry.name, playerId: entry.playerId, number: entry.number, position: entry.position, headshotUrl: entry.headshotUrl, line: { hero: statLine(entry.value, cat?.format, cat?.stat), rest: "" } };
}

/** Public release Phase 7: each team's best graded players, any position (/api/grades/teams), loaded on its own. */
// Group five (owner 2026-10-09: the program is a matchup): the grade groups by the side of the ball they play on.
const WATCH_SIDE = { QB: "offense", RB: "offense", WR: "offense", TE: "offense", OL: "offense", DL: "defense", LB: "defense", DB: "defense" };
const WATCH_TOP = 3; // the best three of a side
const WATCH_ASK = 16; // each team's best graded, enough to leave three a side once the leaders are taken out

/** The leaders' players (Leaders side by side) as ids and names, so players to watch never repeats one (owner 2026-10-10).
    Exported for the tests. */
export function leaderKeys(leaders) {
  const keys = new Set();
  for (const cat of Array.isArray(leaders) ? leaders : []) {
    for (const side of [cat?.us, cat?.them]) {
      if (!side || typeof side !== "object") continue;
      const id = side.playerId === undefined || side.playerId === null ? "" : String(side.playerId).trim();
      if (id) keys.add(`id:${id}`);
      const name = typeof side.player === "string" ? side.player : typeof side.name === "string" ? side.name : "";
      if (name.trim()) keys.add(`name:${name.trim().toLowerCase()}`);
    }
  }
  return keys;
}

function isLeader(player, keys) {
  const id = player?.playerId === undefined || player?.playerId === null ? "" : String(player.playerId).trim();
  const name = typeof player?.name === "string" ? player.name.trim().toLowerCase() : "";
  return Boolean((id && keys.has(`id:${id}`)) || (name && keys.has(`name:${name}`)));
}

function watchBand(data) {
  const us = typeof data.us?.school === "string" && data.us.school ? data.us.school : usSchool();
  const them = typeof data.them?.school === "string" && data.them.school ? data.them.school : null;
  const host = el("div", {});
  const leaders = leaderKeys(data.leaders); // never the same players as Leaders side by side (owner 2026-10-10)
  const draw = (state) => {
    const teams = (Array.isArray(state?.data?.teams) ? state.data.teams : []).filter((t) => t && typeof t === "object" && typeof t.team === "string");
    const byTeam = new Map(teams.map((t) => [t.team, t]));
    const players = (team, side) => (Array.isArray(byTeam.get(team)?.players) ? byTeam.get(team).players : [])
      .filter((p) => p && typeof p === "object" && (WATCH_SIDE[p.group] || "specialists") === side && !isLeader(p, leaders))
      .slice(0, WATCH_TOP);
    const count = teams.reduce((n, t) => n + (Array.isArray(t.players) ? t.players.length : 0), 0);
    const cell = (team, side, owner) => {
      const rows = players(team, side);
      return el("div", { class: `watch__side watch__side--${owner}` },
        subhead(`${text(team)} ${side}`, { team, side: owner }),
        rows.length ? gradedTable(rows, { us, showTeam: false, onTap: (row) => openPlayer(row.playerId, { ...row, isUs: row.team === us }), caption: `${text(team)} ${side}, best stat grades` }) : note(`No ${side} grades for ${text(team)} yet.`),
      );
    };
    const pairs = them
      ? [[us, "offense", "us", them, "defense", "them"], [them, "offense", "them", us, "defense", "us"]] // each offense beside the defense it faces
      : [[us, "offense", "us", us, "defense", "us"]];
    const specialists = players(us, "specialists").length || (them && players(them, "specialists").length);
    host.replaceChildren(band({
      id: "program-watch",
      title: "Players to watch",
      collapsible: true,
      foldable: true,
      summary: count ? "the best stat grades beyond the leaders, each offense against the defense it faces" : "",
      state: state?.error ? { status: "error", message: `${state.error}.` } : !state ? { status: "loading" } : count ? { status: "ready" } : { status: "empty" },
      emptyText: "Grades appear once players have enough plays this season.",
      body: () => el("div", { class: "watch" },
        pairs.map(([a, aSide, aOwner, b, bSide, bOwner]) => el("div", { class: "twocol watch__pair" }, cell(a, aSide, aOwner), cell(b, bSide, bOwner))),
        specialists ? el("div", { class: "twocol watch__pair" }, cell(us, "specialists", "us"), them ? cell(them, "specialists", "them") : null) : null,
        el("p", { class: "note" }, GRADE_NOTE),
      ),
    }));
  };
  draw(null);
  fetchJson(`/api/grades/teams?teams=${encodeURIComponent([us, them].filter(Boolean).join(","))}&top=${WATCH_ASK}`)
    .then((envelope) => draw({ data: envelope?.data && typeof envelope.data === "object" ? envelope.data : null }))
    .catch((error) => draw({ error: error?.message || "The grades did not load" }));
  return host;
}

/**
 * Phase 17 #17: the leaders draw at once from the program's own answer; then /api/program/<id>/leaders adds each
 * leader's whole line with national and conference ranks and the line over conference games (it can take a
 * moment the first time a week's conference games are read, so it loads on its own).
 */
function leadersBand(data) {
  const leaders = (Array.isArray(data.leaders) ? data.leaders : []).filter((l) => l && typeof l === "object");
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const host = el("div", { class: "flow-wide" }); // the whole lines need the room of two columns
  const draw = (extra) => {
    const detailed = new Map((Array.isArray(extra?.categories) ? extra.categories : []).filter((c) => c && typeof c === "object").map((c) => [`${c.category}:${c.stat}`, c]));
    const confGames = objOf(extra?.conferenceGames);
    const categories = leaders.map((cat) => {
      const more = detailed.get(`${cat.category || ""}:${cat.stat}`) || [...detailed.values()].find((c) => c.label === cat.label) || null;
      return {
        id: `${text(cat.stat)}-${text(cat.label)}`,
        label: cat.label,
        us: programLeader(cat.us, cat),
        them: programLeader(cat.them, cat),
        detail: more ? leaderLines(more, { usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, usConfGames: objOf(confGames.us).games, themConfGames: objOf(confGames.them).games }) : null,
      };
    });
    host.replaceChildren(band({
      id: "program-leaders",
      title: "Leaders side by side",
      collapsible: true,
      foldable: true,
      summary: detailed.size ? "season and conference games, with ranks" : "season totals",
      state: partState(data.parts?.playersTeam, categories.some((l) => l.us || l.them)),
      emptyText: "Leaders appear after the first game.",
      body: () => el("div", {}, leadersGrid({ categories, usAbbr, themAbbr, className: "leaders--program", onTap: (player, side) => (player?.playerId ? openPlayer(player.playerId, { ...player, isUs: side === "us" }) : null) }), extra?.error ? el("p", { class: "note" }, `The whole lines did not load: ${text(extra.error)}.`) : detailed.size ? el("p", { class: "note" }, "Each rank is among FBS players and among the players of the leader's own conference. Conference games count only games against conference teams.") : null),
    }));
  };
  draw(null);
  const id = data.game?.gameId;
  if (leaders.length && (isNum(id) || /^\d{1,12}$/.test(String(id ?? "")))) {
    fetchJson(`/api/program/${encodeURIComponent(String(id))}/leaders`)
      .then((envelope) => draw(envelope?.data && typeof envelope.data === "object" ? envelope.data : null))
      .catch((error) => draw({ error: error?.message || "no answer" }));
  }
  return host;
}

/** Phase 15: teams both sides have played this season. */
function commonBand(data) {
  const rows = listOf(data.commonOpponents);
  const us = data.us?.school || usSchool();
  const them = data.them?.school || "Opponent";
  return band({
    id: "program-common",
    title: "Common opponents",
    collapsible: true,
    foldable: true,
    summary: rows.length ? `${rows.length} shared` : "none yet",
    state: partState(data.parts?.games, true),
    body: () => commonOpponentsBlock(rows, { usAbbr: abbrOf(data.us, usLabel()), themAbbr: abbrOf(data.them), usTeam: us, themTeam: them, usName: fullName(data.us) || us, themName: fullName(data.them) || them }),
  });
}

/** Phase 15: how both teams played last season. */
function lastSeasonBand(data) {
  const last = data.lastSeason && typeof data.lastSeason === "object" ? data.lastSeason : { rows: [] };
  const has = Array.isArray(last.rows) && last.rows.length > 0;
  return band({
    id: "program-last-season",
    title: `Last season${isNum(last.year) ? ` (${last.year})` : ""}`,
    collapsible: true,
    foldable: true,
    collapsed: true,
    summary: "both teams, national ranks",
    state: partState(data.parts?.lastStats, has),
    emptyText: "Last season's numbers appear once CFBD answers.",
    body: () => lastSeasonTwoTeam(last, abbrOf(data.us, usLabel()), abbrOf(data.them), { usTeam: data.us?.school, themTeam: data.them?.school, tug: true }),
  });
}

function seriesBand(data) {
  const s = data.series && typeof data.series === "object" ? data.series : null;
  return band({
    id: "program-series",
    title: "Series",
    collapsible: true,
    foldable: true,
    collapsed: true,
    summary: s ? `${abbrOf(data.us, usLabel())} ${text(s.usWins)}, ${abbrOf(data.them)} ${text(s.themWins)}${s.ties ? `, ${s.ties} ties` : ""}` : "",
    state: partState(data.parts?.series, Boolean(s)),
    emptyText: "No series history between these teams.",
    body: () => {
      const abbrs = {};
      if (typeof data.us?.school === "string") abbrs[data.us.school] = abbrOf(data.us, usLabel());
      if (typeof data.them?.school === "string") abbrs[data.them.school] = abbrOf(data.them);
      // the shared series table (ui/series.js, wave 3): the team pages' History reads the same way
      return el("div", {}, s.streak ? note(`${text(s.streak.team)} has won ${text(s.streak.games)} straight.`) : null, seriesTable(s, { us: data.us?.school || usSchool(), abbrs }));
    },
  });
}

function finalBand(data) {
  const f = data.final;
  if (!data.game?.completed) return null;
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const tables = (side, them) => {
    const cats = objOf(f?.players?.[side]);
    return boxTables({ categories: cats, onTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }) });
  };
  return band({
    id: "program-final",
    title: "Final box",
    collapsible: true,
    foldable: true,
    summary: el("span", { class: "score-words" }, `${usAbbr} ${text(data.game.usPoints)}, ${themAbbr} ${text(data.game.themPoints)}`),
    state: partState(data.parts?.boxTeams, Boolean(f?.available)),
    emptyText: "The box score arrives once CFBD finishes the game.",
    body: () =>
      el(
        "div",
        {},
        quarterLine({ us: { abbr: usAbbr, scores: data.game.usLineScores, total: data.game.usPoints }, them: { abbr: themAbbr, scores: data.game.themLineScores, total: data.game.themPoints } }),
        teamStatsTable({ us: { abbr: usAbbr, school: data.us?.school, name: fullName(data.us) }, them: { abbr: themAbbr, school: data.them?.school, name: fullName(data.them) }, rows: teamStatRows(f?.us || {}, f?.them || {}).filter((row) => row.us !== DASH || row.them !== DASH), caption: `Team stats, ${usAbbr} and ${themAbbr}` }), // final pass: rows CFBD's box never has (plays, drives, success) go, as on the Box page; wave 2: the schools and mascots head it at large
        el("div", { class: "twocol" }, el("div", {}, subhead(data.us?.school || usSchool(), { team: data.us?.school || usSchool(), side: "us" }), tables("us", false)), el("div", {}, subhead(data.them?.school, { team: data.them?.school, side: "them" }), tables("them", true))),
      ),
  });
}

function pickerBand(data) {
  const games = listOf(data.picker).filter((g) => isNum(g.gameId) || /^\d+$/.test(String(g.gameId ?? "")));
  return band({
    id: "program-picker",
    title: "Programs",
    collapsible: true,
    foldable: true,
    collapsed: true,
    summary: "tap a game",
    state: partState(data.parts?.schedule, games.length > 0),
    emptyText: "The schedule loads the first time the app opens.",
    body: () => scheduleList({ games, nextGameId: data.game?.gameId ?? null, onSelect: (game) => openProgram(game?.gameId) }),
  });
}

/** Another game's program: only the hash changes, and the router builds the view once (bug 13: it was twice). */
function openProgram(gameId) {
  if (!(isNum(gameId) || /^\d+$/.test(String(gameId ?? "")))) return;
  const hash = `#program=${encodeURIComponent(String(gameId))}`;
  if (window.location.hash !== hash) window.location.hash = hash;
}

/** Final pass (N4, owner 2026-10-09: the reader gets as much as possible): the team's headlines on the program too,
 *  from the Newspaper's feeds, loaded on their own so the program itself stays fast. */
function headlinesBand() {
  const host = el("div", {}, newsSkeleton(4));
  fetchPatient("/api/newspaper")
    .then((envelope) => {
      const items = Array.isArray(envelope?.data?.news) ? envelope.data.news.slice(0, 12) : [];
      host.replaceChildren(items.length ? newsDigest({ items }) : note(`No ${usName()} headlines in the feeds yet. They appear as the feeds publish.`));
    })
    .catch((error) => host.replaceChildren(note(`${text(error?.message || error)}. The band tries again with the next refresh.`, { kind: "error" })));
  return band({ id: "program-headlines", title: `${usName()} headlines`, collapsible: true, foldable: true, summary: "from the news feeds", body: () => host });
}

/** The bands in the owner's order (2026-10-10). The page flows in columns, so this is the reading order across the top,
    the shortest column next. The bands he left unlisted follow the sixteen, in their earlier order, until he sets it. */
function sections(data) {
  const done = Boolean(data.game?.completed);
  const listed = [
    notesBand(data), // 1 Program notes
    headlinesBand(), // 2 the team's headlines (N4)
    tapeBand(data), // 3 Tale of the tape
    watchBand(data), // 4 Players to watch, never the leaders' players
    leadersBand(data), // 5 Leaders side by side
    availabilityBand(data), // 6 Availability report
    recruitingBand(data), // 7 Talent and recruiting
    lineupsBand(data), // 8 Lineups and depth
    pickerBand(data), // 9 Programs (the game picker)
    seriesBand(data), // 10 Series
    advancedBand(data), // 11 Advanced matchup
    tendenciesBand(data), // 12 Tendencies
    ppaBand(data), // 13 Play value
    commonBand(data), // 14 Common opponents
    lastSeasonBand(data), // 15 Last season
    myNotesBand(data), // 16 My notes
  ];
  // the cover redo (owner 2026-10-10): the weather and the stadium's facts moved into the cover; no Weather band
  if (done) return [...listed, matchup(data), radioBand(), finalBand(data), advancedBoxBand(data)];
  return [...listed, matchup(data), radioBand()];
}

const OPP_VARS = ["--opp", "--opp-alt", "--opp-text"];

/** GX-03 (restrained, owner pick 2026-09-28): marks that already use --opp get the opponent's checked color. */
function useOpponentColors(team) {
  try {
    if (team && typeof team === "object" && (team.color || team.altColor)) applyOpponentColors(team);
    else resetOpponentColors();
  } catch (error) {
    console.error("The opponent's colors could not be applied; the neutral stays.", error);
  }
}

function resetOpponentColors() {
  try {
    const style = document.documentElement?.style;
    if (!style) return;
    for (const name of OPP_VARS) {
      if (typeof style.removeProperty === "function") style.removeProperty(name);
      else delete style[name];
    }
  } catch {
    // no page to reset (tests): nothing was set
  }
}

/** The program's bands that span two columns on a wide page (owner pick 2026-10-07: the big side-by-side tables). */
const PROGRAM_WIDE = ["program-results", "program-schools", "program-matchup", "program-tape", "program-advanced", "program-recruiting", "program-lineups", "program-tendencies", "program-advanced-box", "program-watch", "program-ppa"]; // final pass: the tendencies and the advanced box score wrapped every label in one column // Phase 19: the lineups and depth tables want two columns

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const back = state.gameId ? backRow({ label: "Back", fallback: "#program" }) : null; // DS-03: a sub-route gets a way back
  if (!data.game || typeof data.game !== "object") {
    const sched = data.parts && typeof data.parts === "object" ? data.parts.schedule : null; // final pass: CFBD down reads as an error, not an empty schedule
    const state = sched && sched.status === "error" ? { status: "error", message: `${text(sched.error)}. The app keeps retrying.` } : { status: "empty", message: "No games on the schedule yet." };
    container.replaceChildren(el("div", { class: "page program-page" }, back, band({ title: "Pre-Game Program", collapsible: false, state, errorLead: "Could not load the schedule." })));
    return;
  }
  const before = snapshotKeys(container); // the line, the total and the weather flash when a refresh changes them (P-10)
  const page = el("div", { class: "page program-page" });
  const coverEl = cover({ ...coverProps(data, { reveal: !state.revealed }) });
  state.revealed = true; // the reveal plays once per visit, not on every refresh (P-10 item 2)
  state.cover = coverEl;
  useOpponentColors(data.them);
  const tools = el("div", { class: "program-tools flow-full" }, printButton()); // Phase 19: print the program
  // wave B (owner 2026-10-13): the expectations locked at kickoff beside the result on a finished game's program, and the
  // two schools' history on every program that has facts. New bands go to the bottom of a page until the owner orders
  // them ("for every screen in the future, the new stuff goes to the bottom, until I reorder them", 2026-10-13).
  const results = data.game?.completed ? resultsSlot(data, state) : null;
  const schools = twoSchoolsBand({ us: data.us, them: data.them, facts: data.facts });
  page.append(...[back, tools, coverEl, ...sections(data), results, schools].filter(Boolean));
  if (back) back.classList.add("flow-full");
  coverEl.classList.add("flow-full");
  if (state.flow) state.flow.stop();
  if (state.chips) state.chips.stop();
  // Phase 17 #5: the sections as a pinned row of chips above the page (a pinned row inside the grid would only
  // stay pinned within its own grid cell)
  state.chips = sectionChips(page);
  state.chips.refresh();
  container.replaceChildren(state.chips, page);
  // Phase 17 #7, #28: bands pack into 1 to 4 columns by width; the cover spans the top, the big tables span two
  // columns once there are three or more
  state.flow = flow(page, { wide: PROGRAM_WIDE });
  flashChanges(before, container, { className: "flash" });
  if (state.focus) {
    const target = document.getElementById(state.focus);
    state.focus = null;
    if (target) settleOn(target);
  }
}

/**
 * The results band loads its locked expectations once per game (the lock never changes) and draws beside the program's
 * final box; a program that was never locked says so instead of showing nothing.
 */
function resultsSlot(data, state) {
  const id = data.game?.gameId;
  const host = el("div", { class: "flow-full", dataset: { results: text(id) } });
  const draw = (locked) => host.replaceChildren(resultsBand({ locked, data }));
  if (state.locked && state.locked.gameId === id) {
    draw(state.locked.data);
    return host;
  }
  host.replaceChildren(band({ id: "program-results", title: "Expectations and results", collapsible: false, state: { status: "loading" } }));
  if (data.game?.locked === false) {
    state.locked = { gameId: id, data: null };
    draw(null);
    return host;
  }
  fetchJson(`/api/program/${encodeURIComponent(text(id))}/locked`)
    .then((envelope) => {
      const locked = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      state.locked = { gameId: id, data: locked };
      draw(locked);
    })
    .catch((error) => {
      if (isNum(error?.status) && error.status === 404) {
        state.locked = { gameId: id, data: null };
        draw(null);
        return;
      }
      host.replaceChildren(band({ id: "program-results", title: "Expectations and results", collapsible: false, state: { status: "error", message: `${text(error?.message || "The locked program could not be read")}.` } }));
    });
  return host;
}

/**
 * Bring a band to the top and keep it there while the bands above it load and grow (2026-10-10: the radio band, which the
 * Setup page's Radio link opens, sits near the end of a flowing page, so one early scroll landed short). Up to four
 * seconds; any touch, wheel or key from the reader ends it at once.
 */
function settleOn(target, ms = 4000) {
  if (!target || typeof target.scrollIntoView !== "function" || typeof window === "undefined") return;
  const kinds = ["wheel", "touchstart", "keydown", "pointerdown"];
  let stopped = false;
  const stop = () => {
    stopped = true;
  };
  for (const kind of kinds) window.addEventListener(kind, stop, { passive: true, capture: true });
  const until = Date.now() + ms;
  const step = () => {
    if (stopped || !target.isConnected || Date.now() > until) {
      for (const kind of kinds) window.removeEventListener(kind, stop, { capture: true });
      return;
    }
    target.scrollIntoView({ block: "start" });
    setTimeout(step, 250);
  };
  setTimeout(step, 50);
}

/** The loading page in its real shape (P-04 item 5): the cover, then the first bands of the owner's order (2026-10-10). */
function loadingPage(state) {
  const loading = (title, skeleton) => band({ title, collapsible: false, state: { status: "loading" }, skeleton });
  return el(
    "div",
    { class: "page program-page", "aria-busy": "true" },
    state.gameId ? backRow({ label: "Back", fallback: "#program" }) : null,
    coverSkeleton(),
    loading("Program notes", () => el("div", { class: "skel skel--row" })),
    loading(`${text(usName())} headlines`, () => el("div", { class: "skel skel--row" })),
    loading("Tale of the tape", () => statTableSkeleton(8, 3)),
  );
}

const TICK_MS = 30000;

export function createProgramView({ onStatus, gameId = null, focus = null } = {}) {
  const state = { gameId, focus, revealed: false, cover: null, flow: null, chips: null };
  let view = null;
  let ticker = null;
  const stopTicking = () => {
    if (ticker) clearInterval(ticker);
    ticker = null;
  };
  // The countdown ticks every 30 s in place (P-10 item 1); a final or a disconnected cover stops it.
  const startTicking = () => {
    stopTicking();
    ticker = setInterval(() => {
      const coverEl = state.cover;
      if (!coverEl || !coverEl.isConnected || typeof coverEl.tick !== "function") {
        stopTicking();
        return;
      }
      // a final stops it, unless the cover still offers the held final on In Game: it ticks until that button goes at the hold's end
      if (coverEl.tick() === "final" && !coverEl.querySelector('a.cover__action[href="#live"]')) stopTicking();
    }, TICK_MS);
  };
  const make = () =>
    poller({
      url: state.gameId ? `/api/program/${encodeURIComponent(state.gameId)}` : "/api/program/next",
      refreshMs: pollMs(),
      onStatus,
      render: (envelope, container) => {
        render(envelope, container, state);
        startTicking();
      },
      renderError: (message, container, retry) => container.replaceChildren(errorPanel("Pre-Game Program", message, retry)),
      renderLoading: () => loadingPage(state),
      loadingDetail: "The game: stats, lineups, weather and the notes",
    });
  return {
    mount(target) {
      view = make();
      view.mount(target);
    },
    refresh() {
      return view?.refresh();
    },
    unmount() {
      stopTicking();
      resetOpponentColors();
      view?.unmount();
      view = null;
      state.cover = null;
      state.flow?.stop(); // the layout's observers go with the page
      state.flow = null;
      state.chips?.stop();
      state.chips = null;
    },
    open(id) {
      openProgram(id);
    },
  };
}

export { fetchJson, fmtDate, fmtNum };
