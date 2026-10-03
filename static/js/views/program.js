// The Game program (P1 to P10): picker, cover, notes and availability, matchup card with
// schemes, tale of the tape with the edges table, leaders side by side, series, weather, and
// the final box for a past game. Tap the opponent for its team page.

import { confLabel, usLabel, usName, usSchool } from "../identity.js";
import { weekCell, weekLong } from "../ui/weeks.js";
import { cover, coverSkeleton } from "../ui/cover.js";
import { DASH, el, flashChanges, fmtDate, fmtNum, fmtPct, fmtStat, fmtTime, isNum, replaceWith, snapshotKeys, text } from "../ui/dom.js";
import { availabilityTable, editorial } from "../ui/editorial.js";
import { depthBlock, lineupSummary, startersBlock } from "../ui/lineups.js";
import { matchupCard, venueLine, weatherRow } from "../ui/matchup-card.js";
import { scheduleList } from "../ui/schedule.js";
import { backRow, band, jumpList, note, stateBlock, subhead } from "../ui/states.js";
import { statTable, statTableSkeleton } from "../ui/stat-table.js";
import { trendRow } from "../ui/sparkline.js";
import { applyOpponentColors } from "../ui/colors.js";
import { twoTeamTable } from "../ui/two-team.js";
import { nationalHref } from "../ui/national-link.js";
import { edgesSummary, edgesTable } from "../ui/edges.js";
import { leadersGrid, statLine } from "../ui/leaders.js";
import { quarterLine, teamStatsTable } from "../ui/team-stats.js";
import { loadRadioSources, radioHelpBlock, radioSnapshot, startRadio, stateText, stopRadio, subscribeRadio } from "../radio.js";
import { pollMs } from "../prefs.js";
import { notesPaste } from "../ui/notes-paste.js";
import { GRADE_NOTE, gradedTable } from "../ui/grade.js";
import { errorPanel, fetchJson, partState, poller } from "./common.js";
import { openPlayer } from "./player.js";
import { adjustedMatchup, advancedBoxBlock, matchupGroups, tendenciesBlock } from "../ui/depth2.js";
import { commonOpponentsBlock, lastSeasonTwoTeam } from "../ui/offday.js";

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
    body: () => el("div", {}, matchupGroups(adv.us, adv.them, { usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, ladder: true }), subhead("Adjusted for the opponents each team has faced"), adjustedMatchup(data.adjusted, { usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, ladder: true })),
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
    body: () => advancedBoxBlock(data.advancedBox, { us: data.us?.school || usSchool(), them: data.them?.school, usAbbr: abbrOf(data.us, usLabel()), themAbbr: abbrOf(data.them) }),
  });
}

const BOX_COLUMNS = {
  passing: [{ key: "name", label: "Passing", kind: "text" }, { key: "C/ATT", label: "C/ATT", kind: "text", sortable: false }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }, { key: "INT", label: "Int" }],
  rushing: [{ key: "name", label: "Rushing", kind: "text" }, { key: "CAR", label: "Car" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "TD", label: "TD" }],
  receiving: [{ key: "name", label: "Receiving", kind: "text" }, { key: "REC", label: "Rec" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "TD", label: "TD" }],
  defensive: [{ key: "name", label: "Defense", kind: "text" }, { key: "TOT", label: "Tkl" }, { key: "SACKS", label: "Sck", format: "1f" }, { key: "TFL", label: "TFL", format: "1f" }, { key: "PD", label: "PD" }],
  kicking: [{ key: "name", label: "Kicking", kind: "text" }, { key: "FG", label: "FG", kind: "text", sortable: false }, { key: "XP", label: "XP", kind: "text", sortable: false }, { key: "PTS", label: "Pts" }],
  punting: [{ key: "name", label: "Punting", kind: "text" }, { key: "NO", label: "No" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "LONG", label: "Long" }],
};

function weatherFromData(w, game, { label } = {}) {
  if (!w || typeof w !== "object") return weatherRow({ note: "No forecast yet.", label });
  const kickoffText = game?.startTimeTbd ? "Time TBD" : fmtTime(game?.kickoff);
  if (!w.available) return weatherRow({ kickoffText, label, note: typeof w.error === "string" && w.error ? w.error : "No forecast yet.", radarUrl: w.radarUrl });
  const source = typeof w.source === "string" && w.source ? `${w.source}${w.stale ? ", stale" : ""}${typeof w.period === "string" && w.period ? `, ${w.period}` : ""}` : null;
  return weatherRow({ kickoffText, label, tempF: w.tempF, windMph: w.windMph, windDir: typeof w.windDir === "string" ? w.windDir : null, sky: w.sky, precipChance: w.precipChance, indoors: w.dome === true, source, radarUrl: w.radarUrl });
}

/** The weather row with the venue facts under it (GX-19) and the radar link-out beside it (UX-14). */
function weatherBand(data) {
  const g = data.game || {};
  return el("div", { class: "band program-weather", id: "program-weather", "aria-label": "Weather and venue" }, weatherFromData(data.weather, g), venueLine(g.venueDetail, { us: data.us?.school || usSchool() }));
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
        stateBlock({ lead: "No notes for this game yet.", detail: "Ask an AI chat for them: copy the prompt, paste the answer back, check it and save. It takes a few minutes." }),
        notesPaste({ gameId: data.game?.gameId }),
        notesTaskControl(data.game?.gameId),
        el("p", { class: "notes-empty__path" }, `Or by hand: data/notes/${id}.json, shaped like data/notes/_example.json.`),
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
    body: () => (rows.length ? availabilityTable({ rows, source: n.availabilitySource, updatedAt: n.availabilityUpdatedAt }) : note(`No availability report for this game yet. The pre-game notes read the ${confLabel()} availability report where the conference publishes one; or add it to the notes file.`)),
  });
}

/** 2026-10-02: the starting lineups from the notes file's published depth charts (ui/lineups.js). */
function lineupsBand(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  return band({
    id: "program-lineups",
    title: "Starting lineups",
    collapsible: true,
    foldable: true,
    summary: lineupSummary(n.lineups) || "",
    state: { status: "ready" },
    body: () => startersBlock({ lineups: n.lineups, us: data.us, them: data.them, availability: n.availability, onPlayer: (row) => openPlayer(row.playerId, { ...row.player, name: row.name, position: row.slot, isUs: row.isUs !== false }) }),
  });
}

/** The full depth charts, folded by default: the starters band above says who starts. */
function depthBand(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  return band({
    id: "program-depth",
    title: "Depth charts",
    collapsible: true,
    collapsed: true,
    summary: lineupSummary(n.lineups) || "",
    state: { status: "ready" },
    body: () => depthBlock({ lineups: n.lineups, us: data.us, them: data.them, availability: n.availability }),
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

const CARD_ROWS = [["offense", "ppg", "Points per game"], ["offense", "ypg", "Yards per game"], ["offense", "ypp", "Yards per play"], ["offense", "pass_ypg", "Pass yards per game"], ["offense", "rush_ypg", "Rush yards per game"], ["offense", "third", "Third down"], ["defense", "opp_ppg", "Opp points per game"], ["defense", "ypg_d", "Opp yards per game"], ["defense", "ypp_d", "Opp yards per play"], ["defense", "pass_ypg_d", "Opp pass yards per game"], ["defense", "rush_ypg_d", "Opp rush yards per game"], ["defense", "third_d", "Opp third down"]];

function matchup(data) {
  const them = data.them || {};
  const usRows = data.profile?.us || [];
  const themRows = data.profile?.them || [];
  const schemes = data.notes?.schemes || null;
  const tags = [];
  if (data.game?.postseason) tags.push({ label: text(data.game.playoffRound || data.game.postseason || "Bowl game") });
  else if (data.game?.conferenceGame) tags.push({ label: `${confLabel()} game` });
  if (isNum(them.sp?.rank)) tags.push({ label: `SP+ #${them.sp.rank}`, href: nationalHref(typeof them.sp.metric === "string" ? them.sp.metric : "rating:sp", { team: them.school }), rank: them.sp.rank, of: them.sp.of, name: "SP+" });
  const rows = CARD_ROWS.map(([side, key, label]) => {
    const u = profileRow(usRows, key);
    const t = profileRow(themRows, key);
    return { label, side, key, metric: u.metric || t.metric || `profile:${key}`, format: u.format || t.format, higherIsBetter: typeof u.higherIsBetter === "boolean" ? u.higherIsBetter : t.higherIsBetter, us: { value: u.value, rank: u.nationalRank, of: u.nationalOf }, them: { value: t.value, rank: t.nationalRank, of: t.nationalOf } };
  });
  return matchupCard({
    us: { ...(data.us || {}), abbreviation: abbrOf(data.us, usLabel()) },
    them: { ...them, abbreviation: abbrOf(them) },
    tags,
    schemes,
    rows,
    foot: schemes ? null : el("p", { class: "note", style: { textAlign: "center", padding: "0" } }, "Scheme labels come from the notes file once it is written."),
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

const KIND_WORD = { stream: "stream", embed: "station player", link: "opens a tab" };

/** The radio control (X4, owner direction 2026-09-23: on the Game program). The player itself lives in
 *  the shell's dock so the audio keeps playing when the view changes; this band only starts and stops it.
 *  P-12: the summary says what is playing, and each source is one 44px row: name, kind, button. */
function radioBand() {
  const host = el("div", { class: "radio-panel radio-panel--compact" });
  let attached = false;
  let summary = null;
  const draw = (snap) => {
    const current = snap.current;
    const sources = Array.isArray(snap.sources) ? snap.sources : [];
    if (summary) summary.textContent = radioSummary(snap);
    replaceWith(
      host,
      snap.loadError ? note(snap.loadError, { kind: "error", lead: "Radio unavailable." }) : null,
      !snap.loaded && !snap.loadError ? el("p", { class: "note" }, "Loading the radio sources.") : null,
      snap.loaded && !snap.loadError && sources.length === 0 ? (radioHelpBlock(snap.help) || el("p", { class: "note" }, "No radio station yet. ", el("a", { href: "#settings" }, "Add one in Settings"), ".")) : null,
      current ? el("p", { class: "radio-now" }, el("b", {}, text(current.name)), ` · ${stateText(snap.state)}${snap.detail ? ` · ${snap.detail}` : ""}. The controls stay in the bar at the bottom of every page.`) : null,
      sources.map((source) =>
        el(
          "div",
          { class: "radio-source radio-source--row", "aria-current": current?.id === source.id ? "true" : null },
          el("span", { class: "radio-source__name" }, text(source.name)),
          el("span", { class: "radio-source__kind" }, KIND_WORD[source.kind] || text(source.kind)),
          el("button", { class: `btn${current?.id === source.id ? " btn--primary" : ""}`, type: "button", onclick: () => (current?.id === source.id ? stopRadio() : startRadio(source)) }, current?.id === source.id ? "Stop" : source.kind === "link" ? "Open" : "Play"),
        ),
      ),
      snap.note ? el("p", { class: "note" }, snap.note) : null,
    );
  };
  const section = band({ id: "program-radio", title: "Radio", collapsible: true, foldable: true, summary: radioSummary(radioSnapshot()), state: { status: "ready" }, body: () => host });
  summary = section.querySelector(".band__summary");
  draw(radioSnapshot());
  const unsubscribe = subscribeRadio((snap) => {
    if (host.isConnected) attached = true;
    if (attached && !host.isConnected) {
      unsubscribe();
      return;
    }
    draw(snap);
  });
  loadRadioSources();
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

/** Play value (L9): PPA per play for both teams by game and for the season, and each team's players from its latest game. */
function ppaBand(data) {
  const p = objOf(data.ppa);
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const fmt = (v) => (isNum(v) ? fmtStat(v, "+2f") : DASH);
  const seasonRows = [["Offense", "offense"], ["Defense", "defense"]].flatMap(([label, side]) =>
    ["overall", "passing", "rushing"].map((key) => ({ label: `${label}, ${key}`, format: "+2f", higherIsBetter: side === "offense", us: { value: p.season?.us?.[side]?.[key] }, them: { value: p.season?.them?.[side]?.[key] } })),
  );
  const gameCols = [{ key: "week", label: "Wk", sortable: false, dim: true }, { key: "opponent", label: "Opponent", kind: "text", sortable: false, team: true }, { key: "offOverall", label: "Off", format: "+2f", sortable: false }, { key: "offPass", label: "Pass", format: "+2f", sortable: false }, { key: "offRush", label: "Rush", format: "+2f", sortable: false }, { key: "defOverall", label: "Def", format: "+2f", sortable: false }, { key: "defPass", label: "Pass", format: "+2f", sortable: false }, { key: "defRush", label: "Rush", format: "+2f", sortable: false }];
  const gameRows = (rows) => (Array.isArray(rows) ? rows.filter((g) => g && typeof g === "object") : []).map((g) => ({ week: weekCell(g), opponent: g.opponent, offOverall: g.offense?.overall, offPass: g.offense?.passing, offRush: g.offense?.rushing, defOverall: g.defense?.overall, defPass: g.defense?.passing, defRush: g.defense?.rushing }));
  const playerCols = [{ key: "name", label: "Player", kind: "text", sub: "position", sortable: false }, { key: "all", label: "PPA/play", format: "+2f", sortable: false }, { key: "pass", label: "Pass", format: "+2f", sortable: false }, { key: "rush", label: "Rush", format: "+2f", sortable: false }];
  const h3 = (t, school, side) => subhead(t, school ? { team: school, side } : {});
  const players = (title, rows, them) => el("div", {}, h3(title, them ? data.them?.school : data.us?.school || usSchool(), them ? "them" : "us"), rows.length ? statTable({ compact: true, columns: playerCols, rows, onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }) }) : note("No player values yet."));
  const games = (title, rows, them) => el("div", {}, h3(title, them ? data.them?.school : data.us?.school || usSchool(), them ? "them" : "us"), rows.length ? statTable({ compact: true, columns: gameCols, rows }) : note("No graded games yet."));
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
        h3("Season, per play"),
        twoTeamTable({ rows: seasonRows, usAbbr, themAbbr, labelHead: "PPA per play", caption: "Season PPA per play, both teams" }),
        el("div", { class: "twocol" }, players(`${text(data.us?.school)} season leaders, PPA per play`, Array.isArray(p.seasonLeaders?.us) ? p.seasonLeaders.us : [], false), players(`${text(data.them?.school)} season leaders, PPA per play`, Array.isArray(p.seasonLeaders?.them) ? p.seasonLeaders.them : [], true)),
        games(`${text(data.us?.school)} by game`, gameRows(p.games?.us)),
        games(`${text(data.them?.school)} by game`, gameRows(p.games?.them), true),
        el("div", { class: "twocol" }, players(`${text(data.us?.school)}, ${isNum(p.players?.usWeek) ? `week ${p.players.usWeek}` : "latest game"}`, Array.isArray(p.players?.us) ? p.players.us : [], false), players(`${text(data.them?.school)}, ${isNum(p.players?.themWeek) ? `week ${p.players.themWeek}` : "latest game"}`, Array.isArray(p.players?.them) ? p.players.them : [], true)),
      ),
  });
}

/** Talent and recruiting, side by side: talent composite with rank, blue-chip ratio, returning production. */
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
    body: () => el("div", {}, twoTeamTable({ rows, usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, caption: "Talent and recruiting, both teams" }), el("p", { class: "note" }, "Talent is the 247Sports composite of the roster. Blue-chip ratio is four- and five-star signees over all signees in the last four classes; 50% is the line every champion since 2011 has cleared. Returning production is the share of last season's predicted points added that is back.")),
  });
}

/** "SWT better in 14 of 24": who has the better number, from the rows in hand (P-11 item 4). */
function tapeSummary(rows, usAbbr, themAbbr) {
  let us = 0;
  let judged = 0;
  for (const row of rows) {
    const a = row.us?.value;
    const b = row.them?.value;
    if (!isNum(a) || !isNum(b) || typeof row.higherIsBetter !== "boolean") continue;
    judged += 1;
    if (a !== b && (row.higherIsBetter ? a > b : a < b)) us += 1;
  }
  return judged ? `${usAbbr} better in ${us} of ${judged}` : `${usAbbr} and ${themAbbr}`;
}

function tapeBand(data) {
  const us = listOf(data.profile?.us);
  const them = listOf(data.profile?.them);
  const themBy = Object.fromEntries(them.map((r) => [r.key, r]));
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const rows = us.map((row) => {
    const other = themBy[row.key] || {};
    return { label: row.label, side: row.side, format: row.format || other.format, metric: row.metric || other.metric || (row.key ? `profile:${row.key}` : null), higherIsBetter: typeof row.higherIsBetter === "boolean" ? row.higherIsBetter : other.higherIsBetter, us: { value: row.value, rank: row.nationalRank, of: row.nationalOf }, them: { value: other.value, rank: other.nationalRank, of: other.nationalOf } };
  });
  const has = rows.some((r) => isNum(r.us.value));
  const table = (side) => twoTeamTable({ rows: rows.filter((r) => r.side === side || (side === "offense" && r.side === "both")), usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, underline: true, caption: `${side === "offense" ? "Offense" : "Defense"}, both teams` });
  return band({
    id: "program-tape",
    title: "Tale of the tape",
    collapsible: true,
    foldable: true,
    summary: tapeSummary(rows, usAbbr, themAbbr),
    state: partState(data.parts?.stats, has),
    emptyText: "The comparison appears once both teams have played.",
    // P-11 (owner look): Offense | Defense side by side, about a dozen rows each, so the spread balances by construction
    body: () => el("div", { class: "tt-pair" }, el("div", {}, subhead("Offense"), table("offense")), el("div", {}, subhead("Defense"), table("defense"))),
  });
}

function edgesBand(data) {
  const edges = Array.isArray(data.edges) ? data.edges : [];
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  return band({
    id: "program-edges",
    title: "Biggest edges",
    collapsible: true,
    foldable: true,
    summary: edgesSummary(edges, { usAbbr, themAbbr }),
    state: partState(data.parts?.stats, edges.length > 0),
    emptyText: "Edges appear once both teams have played.",
    body: () => el("div", {}, edgesTable(edges, { usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school }), note(`Each unit's national rank against the unit it faces. The edge is the gap in ranks; positive favors ${usName()}.`)),
  });
}

/** A program leaders payload side as a leadersGrid player: its number in the board's format with a unit. */
export function programLeader(entry, cat) {
  if (!entry || typeof entry !== "object") return null;
  return { name: entry.player ?? entry.name, playerId: entry.playerId, number: entry.number, position: entry.position, headshotUrl: entry.headshotUrl, line: { hero: statLine(entry.value, cat?.format, cat?.stat), rest: "" } };
}

/** Public release Phase 7: each team's best graded players, any position (/api/grades/teams), loaded on its own. */
function watchBand(data) {
  const us = typeof data.us?.school === "string" && data.us.school ? data.us.school : usSchool();
  const them = typeof data.them?.school === "string" && data.them.school ? data.them.school : null;
  const host = el("div", {});
  const draw = (state) => {
    const teams = (Array.isArray(state?.data?.teams) ? state.data.teams : []).filter((t) => t && typeof t === "object" && typeof t.team === "string");
    const rows = teams.flatMap((t) => (Array.isArray(t.players) ? t.players : []));
    host.replaceChildren(band({
      id: "program-watch",
      title: "Players to watch",
      collapsible: true,
      foldable: true,
      summary: rows.length ? `the best stat grades on each side` : "",
      state: state?.error ? { status: "error", message: `${state.error}.` } : !state ? { status: "loading" } : rows.length ? { status: "ready" } : { status: "empty" },
      emptyText: "Grades appear once players have enough plays this season.",
      body: () => el("div", { class: teams.length > 1 ? "spread spread--2" : "" },
        teams.map((t) => el("div", {}, subhead(t.team), Array.isArray(t.players) && t.players.length ? gradedTable(t.players, { us, showTeam: false, onTap: (row) => openPlayer(row.playerId, { ...row, isUs: row.team === us }), caption: `${t.team} players to watch` }) : el("p", { class: "note" }, "No player has enough plays to grade yet."))),
        el("p", { class: "note" }, GRADE_NOTE),
      ),
    }));
  };
  draw(null);
  fetchJson(`/api/grades/teams?teams=${encodeURIComponent([us, them].filter(Boolean).join(","))}&top=3`)
    .then((envelope) => draw({ data: envelope?.data && typeof envelope.data === "object" ? envelope.data : null }))
    .catch((error) => draw({ error: error?.message || "The grades did not load" }));
  return host;
}

function leadersBand(data) {
  const leaders = (Array.isArray(data.leaders) ? data.leaders : []).filter((l) => l && typeof l === "object");
  const categories = leaders.map((cat) => ({ id: `${text(cat.stat)}-${text(cat.label)}`, label: cat.label, us: programLeader(cat.us, cat), them: programLeader(cat.them, cat) }));
  return band({
    id: "program-leaders",
    title: "Leaders side by side",
    collapsible: true,
    foldable: true,
    summary: "season totals",
    state: partState(data.parts?.playersTeam, categories.some((l) => l.us || l.them)),
    emptyText: "Leaders appear after the first game.",
    body: () => leadersGrid({ categories, usAbbr: abbrOf(data.us, usLabel()), themAbbr: abbrOf(data.them), className: "leaders--program", onTap: (player, side) => (player?.playerId ? openPlayer(player.playerId, { ...player, isUs: side === "us" }) : null) }),
  });
}

/** Phase 15: teams both sides have played this season. */
function commonBand(data) {
  const rows = Array.isArray(data.commonOpponents) ? data.commonOpponents : [];
  const us = data.us?.school || usSchool();
  const them = data.them?.school || "Opponent";
  return band({
    id: "program-common",
    title: "Common opponents",
    collapsible: true,
    foldable: true,
    summary: rows.length ? `${rows.length} shared` : "none yet",
    state: partState(data.parts?.games, true),
    body: () => commonOpponentsBlock(rows, us, them),
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
    body: () => lastSeasonTwoTeam(last, abbrOf(data.us, usLabel()), abbrOf(data.them), { usTeam: data.us?.school, themTeam: data.them?.school, ladder: true }),
  });
}

const SERIES_COLUMNS = [
  { key: "season", label: "Year", kind: "text" },
  { key: "away", label: "Away", kind: "text", team: true },
  { key: "home", label: "Home", kind: "text", team: true },
  { key: "score", label: "Score", kind: "text" },
  { key: "winner", label: "Winner", kind: "text", team: true },
  { key: "result", label: "Result", kind: "text", render: (row) => (row.result ? el("span", { class: row.won === true ? "res--w" : row.won === false ? "res--l" : null }, row.result) : "–") },
];

/** The series' last meetings from our side: "W 24-17" / "L 17-24" (P-13 item 1). Exported for the tests. */
export function seriesRows(series, us = usSchool()) {
  const games = Array.isArray(series?.lastTen) ? series.lastTen.filter((g) => g && typeof g === "object") : [];
  return games.map((g) => {
    const home = typeof g.homeTeam === "string" ? g.homeTeam : null;
    const away = typeof g.awayTeam === "string" ? g.awayTeam : null;
    const usHome = home === us;
    const mine = usHome ? g.homeScore : g.awayScore;
    const theirs = usHome ? g.awayScore : g.homeScore;
    const played = (home === us || away === us) && isNum(mine) && isNum(theirs);
    const won = played ? (mine > theirs ? true : mine < theirs ? false : null) : null;
    return {
      season: isNum(g.season) ? String(g.season) : "–",
      away,
      home,
      score: isNum(g.awayScore) && isNum(g.homeScore) ? `${g.awayScore}-${g.homeScore}` : "–",
      winner: typeof g.winner === "string" && g.winner ? g.winner : null,
      won,
      result: played ? `${won === true ? "W" : won === false ? "L" : "T"} ${mine}-${theirs}` : null,
    };
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
    body: () => el("div", {}, s.streak ? note(`${text(s.streak.team)} has won ${text(s.streak.games)} straight.`) : null, statTable({ compact: true, sortable: false, columns: SERIES_COLUMNS, rows: seriesRows(s, data.us?.school || usSchool()), rowClass: (row) => (row.won === true ? "is-us" : null) })),
  });
}

function finalBand(data) {
  const f = data.final;
  if (!data.game?.completed) return null;
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const tables = (side, them) => {
    const cats = objOf(f?.players?.[side]);
    return el("div", {}, Object.entries(BOX_COLUMNS).filter(([name]) => listOf(cats[name]).length).map(([name, columns]) => statTable({ columns, rows: listOf(cats[name]).map((r) => ({ name: r.name, playerId: r.playerId, ...r.stats })), compact: true, sort: { key: columns[2]?.key || columns[1].key, dir: "descending" }, onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }) })));
  };
  return band({
    id: "program-final",
    title: "Final box",
    collapsible: true,
    foldable: true,
    summary: `${usAbbr} ${text(data.game.usPoints)}, ${themAbbr} ${text(data.game.themPoints)}`,
    state: partState(data.parts?.boxTeams, Boolean(f?.available)),
    emptyText: "The box score arrives once CFBD finishes the game.",
    body: () =>
      el(
        "div",
        {},
        quarterLine({ us: { abbr: usAbbr, scores: data.game.usLineScores, total: data.game.usPoints }, them: { abbr: themAbbr, scores: data.game.themLineScores, total: data.game.themPoints } }),
        teamStatsTable({ us: { abbr: usAbbr, box: f?.us || {} }, them: { abbr: themAbbr, box: f?.them || {} } }),
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

/** The weather band for a finished game: 'Kickoff weather', or only the venue facts when nothing was observed. */
function finishedWeatherBand(data) {
  const g = data.game || {};
  const w = data.weather && typeof data.weather === "object" ? data.weather : null;
  const observed = Boolean(w && w.available && (isNum(w.tempF) || (typeof w.sky === "string" && w.sky)));
  const venue = venueLine(g.venueDetail, { us: data.us?.school || usSchool() });
  if (!observed && !venue) return null;
  return el("div", { class: "band program-weather", id: "program-weather", "aria-label": "Weather and venue" }, observed ? weatherFromData(w, g, { label: "Kickoff weather" }) : null, venue);
}

/**
 * The page in the owner's order (P-04; docs/03-DESIGN.md #14, #15): the cover, the weather directly under it,
 * the radio near the top, the matchup card with the notes and the availability report stacked under it, then
 * the tape, edges and leaders, and the season context. A finished game puts its Final box and Advanced box
 * score right after the weather and moves the radio below them.
 */
function sections(data) {
  const done = Boolean(data.game?.completed);
  const context = [
    notesBand(data),
    availabilityBand(data),
    lineupsBand(data),
    depthBand(data),
    tapeBand(data),
    el("div", { class: "spread spread--2" }, edgesBand(data), leadersBand(data)),
    watchBand(data),
    advancedBand(data),
    tendenciesBand(data),
    ppaBand(data),
    el("div", { class: "spread spread--2" }, recruitingBand(data), commonBand(data)),
    el("div", { class: "spread spread--2" }, lastSeasonBand(data), seriesBand(data)),
    pickerBand(data),
  ];
  if (done) return [finishedWeatherBand(data), finalBand(data), advancedBoxBand(data), radioBand(), matchup(data), ...context];
  return [weatherBand(data), radioBand(), matchup(data), ...context];
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

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const back = state.gameId ? backRow({ label: "Back", fallback: "#program" }) : null; // DS-03: a sub-route gets a way back
  if (!data.game || typeof data.game !== "object") {
    container.replaceChildren(el("div", { class: "page program-page" }, back, band({ title: "Game program", collapsible: false, state: { status: "empty", message: "No games on the schedule yet." } })));
    return;
  }
  const before = snapshotKeys(container); // the line, the total and the weather flash when a refresh changes them (P-10)
  const page = el("div", { class: "page program-page" });
  // UX-11: 'On this page' under the cover (in its foot, so the weather stays directly under the cover)
  const coverEl = cover({ ...coverProps(data, { reveal: !state.revealed }), extra: jumpList(page, { label: "On this page" }) });
  state.revealed = true; // the reveal plays once per visit, not on every refresh (P-10 item 2)
  state.cover = coverEl;
  useOpponentColors(data.them);
  page.append(...[back, coverEl, ...sections(data)].filter(Boolean));
  container.replaceChildren(page);
  flashChanges(before, container, { className: "flash" });
  if (state.focus) {
    const target = document.getElementById(state.focus);
    state.focus = null;
    if (target) setTimeout(() => target.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }
}

/** The loading page in its real shape, one column: the cover, a weather line, the radio head, the matchup card (P-04 item 5). */
function loadingPage(state) {
  return el(
    "div",
    { class: "page program-page", "aria-busy": "true" },
    state.gameId ? backRow({ label: "Back", fallback: "#program" }) : null,
    coverSkeleton(),
    el("div", { class: "band program-weather" }, el("div", { class: "skel", style: { width: "min(420px, 80%)", height: "20px", margin: "8px auto" } })),
    band({ title: "Radio", collapsible: false, state: { status: "loading" }, skeleton: () => el("div", { class: "skel skel--row" }) }),
    band({ title: "This week's matchup", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(12, 3) }),
  );
}

const TICK_MS = 30000;

export function createProgramView({ onStatus, gameId = null, focus = null } = {}) {
  const state = { gameId, focus, revealed: false, cover: null };
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
      if (coverEl.tick() === "final") stopTicking();
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
      renderError: (message, container, retry) => container.replaceChildren(errorPanel("Game program", message, retry)),
      renderLoading: () => loadingPage(state),
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
    },
    open(id) {
      openProgram(id);
    },
  };
}

export { fetchJson, fmtDate, fmtNum };
