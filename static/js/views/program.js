// The Pre-Game Program (P1 to P10; the owner's mock of 2026-10-20 sets the page): the cover, the program notes beside the
// team's headlines, the tale of the tape, the recruits on hand beside the availability report, the leaders side by side on
// the pole, talent and recruiting, the lineups, the advanced matchup, the opponent's tendencies, play value, common
// opponents beside the radio, last season across the page (BUG-15), the two schools and the series; then the matchup card
// and a finished game's box scores. Tap the opponent for its team page.

import { confLabel, usLabel, usName, usSchool } from "../identity.js";
import { weekCell, weekLong } from "../ui/weeks.js";
import { cover, coverSkeleton } from "../ui/cover.js";
import { railHost } from "../ui/rail.js"; // the season as one line (owner 2026-10-30)
// the season as one line, Wave 2 (2026-10-30): the boxes fold the old bands in; their parts come from the bands' own modules
import { strengthsParts } from "../ui/strengths.js";
import { talentEdgeParts } from "../ui/talent-edge.js";
import { twoSchoolsBody } from "../ui/two-schools.js";
import { DASH, el, flashChanges, fmtDate, fmtDateTime, fmtNum, fmtPct, fmtStat, fmtTime, isNum, replaceWith, snapshotKeys, text } from "../ui/dom.js";
import { availabilityTable, editorial } from "../ui/editorial.js";
import { notesLayout } from "../ui/notes-layout.js"; // Wave 5 (owner 2026-11-15): the notes laid out
import { hasChart, hasLineups, lineupSummary } from "../ui/lineups.js";
import { formationBlock, lineupPicture, attachRosters } from "../ui/formation.js"; // the lineup as a picture (owner 2026-11-01: "This should only be the picture")
import { fullName, matchupCard, venueLine, weatherRow } from "../ui/matchup-card.js";
import { crewText, teamStaff } from "../ui/game-staff.js";
import { flow } from "../ui/flow.js";
import { starStrip } from "../ui/team-page.js";
import { band, note, revealBand, sectionChips, settleOn, stateBlock, subhead } from "../ui/states.js";
import { boxTables } from "../ui/box-columns.js"; // final pass: one copy of the box-score columns; wave 2: one sized box score on every page
import { statTable, statTableSkeleton, twoCol } from "../ui/stat-table.js";
import { pollPathBlock } from "../ui/poll-path.js"; // ENH-19: both teams' poll paths, under the strengths
import { marginStrip } from "../ui/margin-strip.js"; // ENH-19 chart 3: both teams' seasons game by game, under the poll path
import { blameGameBlock } from "./blame.js"; // the season as one line, Wave 3: the Circle of Blame for this game
import { onStops, stopsNow, weekOf } from "../stops.js"; // the Post-Game stop's closing checklist
import { rememberedView, rememberView, viewSwitch } from "../ui/box-switch.js"; // the boxes' switches (Wave 2; shared with the Season stop since Wave 4)
import { trendRow } from "../ui/sparkline.js";
import { seriesTable } from "../ui/series.js";
import { applyOpponentColors } from "../ui/colors.js";
import { twoTeamTable } from "../ui/two-team.js";
import { nationalHref } from "../ui/national-link.js";
import { edgesSummary } from "../ui/edges.js";
import { tapeTable } from "../ui/tape.js";
import { statLine } from "../ui/leaders.js";
import { leaderPairs } from "../ui/leader-lines.js";
import { quarterLine, teamStatRows, teamStatsTable } from "../ui/team-stats.js";
import { radioSnapshot } from "../radio.js";
import { radioStations } from "../ui/radio-stations.js";
import { gameNotesPanel } from "../ui/game-notes.js";
import { printButton, printOnlyButton } from "../ui/print.js";
import { indexFrom, nameIndex, rosterEntries, tapNamesIn } from "../ui/prose.js"; // not a wall of text (owner 2026-11-07): the names the notes can tap
import { rosterFor } from "../ui/formation.js"; // the rosters behind the names, the lineup picture's own read
import { directionsLink } from "../ui/directions.js"; // ENH-15: Getting there
import { newsDigest, newsSkeleton } from "../ui/news.js";
import { notesPaste } from "../ui/notes-paste.js";
import { partLoad } from "../ui/part-load.js";
import { otherTeam, withTeam } from "../ui/other-team.js";
import { followButton } from "../ui/follow.js";
import { bullets, paragraphs, sourcesLine, writingBand } from "../ui/writing-band.js"; // P4: what Claude Code wrote
import { errorPanel, fetchJson, fetchPatient, partState, poller } from "./common.js";
// wave 3 of the one-column page (2026-11-01): the bands that joined the Pre-Game and the Post-Game from the other pages
import { lateBands, resumeBand, roadAheadBand } from "./season.js";
import { rosterBands } from "./roster.js";
import { teamExtraBands } from "./team.js";
import { archiveGameBands } from "./archive.js";
import { learnedBand } from "../ui/learned-band.js";
import { createBlameView } from "./blame.js";
import { dataRunActive, onRunProgress, watchRun } from "../ui/run-bar.js";
import { openPlayer } from "./player.js";
import { advancedBoxBlock, tendenciesBlock } from "../ui/depth2.js";
import { ddPair } from "../ui/dd-grid.js";
import { commonOpponentsBlock, lastSeasonTwoTeam } from "../ui/offday.js";
import { resultsBand } from "../ui/results.js";
import { pastHref, pastYear, withSeason } from "../ui/past.js"; // rollover R2: a past season's game, as kept
import { trophyLine } from "../ui/two-schools.js";
import { visitorRows, visitorsTable } from "../ui/in-game-tables.js";

/** A payload part as an object, or {} (a list, a string or null never reaches a band). */
function objOf(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

/** A payload list with only its object rows (one bad record never breaks a band). */
function listOf(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object" && !Array.isArray(row)) : [];
}

// --- Phase 13: the advanced matchup, the opponent's tendencies, a finished game's advanced box -------


export function tendenciesBand(data, { id = "program-tendencies" } = {}) {
  const t = data.tendencies && typeof data.tendencies === "object" ? data.tendencies : null;
  return band({
    id,
    title: "Tendencies", // Wave 0 (2026-10-30): both offenses' grids sit in it, so the opponent alone no longer names it
    collapsible: true,
    foldable: true,
    summary: t && isNum(t.plays) && t.plays > 0 ? `${t.plays} snaps, run ${isNum(t.runRate) ? fmtPct(t.runRate) : DASH}` : "",
    state: partState(data.parts?.oppRushes, Boolean(t && t.plays)),
    emptyText: "The opponent's play calls appear once it has played.",
    body: () => tendenciesBlock(t, abbrOf(data.them), { grids: ddPair(data.ourGrid, t?.grid, { usLabel: `${text(data.us?.school || usLabel())} offense`, themLabel: `${text(data.them?.school)} offense`, usTeam: data.us?.school, themTeam: data.them?.school }) }), // board 5: both offenses' grids
  });
}

const BOX_VIEWS = [["box", "Box"], ["advanced", "Advanced"]];

/** The Box score box (the season as one line, Wave 3; the owner's board of 2026-10-30): the score by quarter across the top,
 *  then on the switch the box score (both teams' stats, every player) or the advanced box (PPA, success and havoc by quarter,
 *  the players' value). Folds in Final box and Advanced box score; null before the final. */
function boxScoreBox(data, { view = null } = {}) {
  if (!data.game?.completed) return null;
  const f = data.final;
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const names = { us: data.us?.school || usSchool(), them: data.them?.school, usAbbr, themAbbr, usName: fullName(data.us), themName: fullName(data.them) };
  const allowed = BOX_VIEWS.map(([id]) => id);
  let current = allowed.includes(view) ? view : rememberedView("box", "box", allowed);
  const viewHost = el("div", { class: "box__view" });
  const tables = (side, them) => boxTables({ categories: objOf(f?.players?.[side]), onTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }) });
  const missing = (part, words) => note(part && part.status === "error" ? `${text(part.error)}. The app keeps retrying.` : words, { kind: part && part.status === "error" ? "error" : "empty" });
  const draw = () => {
    if (current === "advanced") {
      viewHost.replaceChildren(
        el("h4", { class: "d2-head" }, "Advanced box score"),
        data.advancedBox
          ? advancedBoxBlock(data.advancedBox, { ...names, onPlayer: (row) => openPlayer(row.playerId, { ...row, isUs: row.side === "us" }) }) // wave 2: a player's row opens his card
          : missing(data.parts?.advancedBox, "CFBD has not posted the advanced box score for this game."),
      );
      return;
    }
    viewHost.replaceChildren(
      ...(f?.available
        ? [
            teamStatsTable({ us: { abbr: usAbbr, school: names.us, name: names.usName }, them: { abbr: themAbbr, school: names.them, name: names.themName }, rows: teamStatRows(f?.us || {}, f?.them || {}).filter((row) => row.us !== DASH || row.them !== DASH) }),
            twoCol(el("div", {}, subhead(names.us, { team: names.us, side: "us" }), tables("us", false)), el("div", {}, subhead(names.them, { team: names.them, side: "them" }), tables("them", true))),
          ]
        : [missing(data.parts?.boxTeams, "The box score arrives once CFBD finishes the game.")]),
    );
  };
  const seg = viewSwitch(BOX_VIEWS, current, (id) => {
    current = id;
    rememberView("box", id);
    seg.mark(id);
    draw();
  });
  draw();
  return band({
    id: "program-box",
    title: "Box score",
    collapsible: true,
    foldable: true,
    summary: el("span", { class: "score-words" }, `${usAbbr} ${text(data.game.usPoints)}, ${themAbbr} ${text(data.game.themPoints)}`),
    tools: seg,
    state: { status: "ready" },
    body: () => el("div", { class: "box" }, quarterLine({ us: { abbr: usAbbr, scores: data.game.usLineScores, total: data.game.usPoints }, them: { abbr: themAbbr, scores: data.game.themLineScores, total: data.game.themPoints } }), viewHost),
  });
}

/** The Circle of Blame for this game (the season as one line, Wave 3): the wheel and the slices of the Sunday report about this
 *  game, from the blame job's saved reports (the latest on /api/blame/now, else the week's own); the whole page is #blame. */
function blameBox(data) {
  const id = data.game?.gameId;
  const bandOf = (state, extra = {}) => band({ id: "program-blame", title: "Circle of Blame", collapsible: true, foldable: true, state, ...extra });
  const host = el("div", {}, bandOf({ status: "loading" }, { skeleton: () => el("div", { class: "skel skel--block" }) }));
  const show = (record) => {
    const top = (Array.isArray(record.report?.slices) ? record.report.slices : []).filter((x) => x && typeof x === "object" && typeof x.name === "string").sort((a, b) => (isNum(b.share_pct) ? b.share_pct : 0) - (isNum(a.share_pct) ? a.share_pct : 0))[0];
    host.replaceChildren(bandOf({ status: "ready" }, { summary: top ? `${top.name} ${isNum(top.share_pct) ? `${top.share_pct}%` : ""}`.trim() : text(record.label), body: () => blameGameBlock(record) })); // the whole report lives on My Team now (wave 3, 2026-11-01)
  };
  const empty = (message) => host.replaceChildren(bandOf({ status: "empty", message }));
  fetchJson("/api/blame/now")
    .then(async (envelope) => {
      const d = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      if (d.available !== true) return empty(text(d.message) || "The Circle of Blame has not been written yet.");
      const latest = d.latest && typeof d.latest === "object" ? d.latest : null;
      if (latest && String(latest.gameId) === String(id)) return show(latest);
      const post = Boolean(data.game?.postseason || data.game?.playoffRound);
      const week = (Array.isArray(d.history) ? d.history : []).find((w) => w && typeof w === "object" && isNum(w.week) && w.week === data.game?.week && String(w.key || "").startsWith("post") === post);
      if (!week) return empty("No Circle of Blame was written for this game.");
      const one = await fetchJson(`/api/blame/${encodeURIComponent(text(d.season))}/${encodeURIComponent(text(week.key))}`);
      const record = one?.data && typeof one.data === "object" ? one.data : null;
      return record ? show(record) : empty("No Circle of Blame was written for this game.");
    })
    .catch((error) => host.replaceChildren(bandOf({ status: "error", message: `${text(error?.message || "no answer")}.` })));
  return host;
}

const CHECK_WORDS = { final: "The final", poll: "The AP poll after", recap: "What decided it" };

/** The Post-Game stop's closing checklist (the season as one line, Wave 3): what has come in and what the stop still waits for,
 *  from /api/stops (the week's post stop: `checks` and `backstop` while it is live, its date once closed or saved). Redrawn when
 *  the line comes or changes. */
function closingStrip(data, locks = null) {
  const id = data.game?.gameId;
  const backfilled = Boolean(locks && locks.post && typeof locks.post === "object" && locks.post.backfilled);
  const host = el("div", { class: "closing", role: "status" });
  const draw = () => {
    const week = weekOf(id);
    const post = week && week.stops && typeof week.stops === "object" ? week.stops.post : null;
    if (!post || typeof post !== "object") {
      host.replaceChildren(el("span", { class: "closing__lead" }, "Post-Game Program"), el("span", { class: "closing__note" }, stopsNow() ? "This game is not on the season's line." : "Reading the season's line."));
      return;
    }
    if (post.state === "saved" || post.state === "closed") {
      const when = fmtDateTime(post.date);
      host.replaceChildren(el("span", { class: "closing__lead is-in" }, post.state === "saved" ? "Saved" : "Closed out"), el("span", { class: "closing__note" }, `${when && when !== DASH ? `The Post-Game Program as it stood ${when}` : "The Post-Game Program is kept as it stood"}${backfilled ? ", filled in later" : ""}.`));
      return;
    }
    const checks = post.checks && typeof post.checks === "object" ? post.checks : {};
    const items = Object.entries(CHECK_WORDS)
      .map(([key, words]) => el("span", { class: `closing__check${checks[key] === true ? " is-in" : ""}`, dataset: { check: key } }, el("i", { "aria-hidden": "true" }), checks[key] === true ? words : `${words} · waiting`));
    const by = fmtDateTime(post.backstop);
    host.replaceChildren(el("span", { class: "closing__lead" }, "Closing out"), ...items, el("span", { class: "closing__note" }, by && by !== DASH ? `Closes out when every check is in, or by ${by}.` : "Closes out when every check is in."));
  };
  draw();
  const off = onStops(() => {
    if (!host.isConnected) {
      off();
      return;
    }
    draw();
  });
  return host;
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
  // ENH-15: the way there in this device's maps app, beside the stadium's facts while the game is ahead
  const directions = !g.completed && d.trip && typeof d.trip === "object" ? directionsLink(d.trip) : null;
  if (!g.completed) return el("div", { class: "conditions", "aria-label": "Weather and stadium" }, weatherFromData(d.weather, g), venue, directions ? el("p", { class: "conditions__directions" }, directions) : null);
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
    facts: data.facts, // freeze wave F4: founded and the stadium's opened year under each team block
    schemes: data.notes?.schemes || null, // the season as one line (2026-10-30): the opponent card's schemes line, now under each team's staff
    trophy: trophyLine(data.facts, data.us, data.them), // and the trophy the two play for, under the kicker
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

/** "Write this week's notes": starts the notes task on the desktop. The run goes on in the background (owner 2026-10-16:
 *  "No refreshes until ALL data is loaded"): the loading bar above the page follows it (ui/run-bar.js), and when every run
 *  has ended the To do says the data is in (manual refresh, 2026-11-14). This control asks for its own status once, then listens to the
 *  bar; it never polls and never reloads the page (the 5 s poll that reloaded after any saved run was the 2026-10-13 loop).
 *  quiet (notes exist, P-14): one quiet 'Rewrite notes' line in the band's foot; its status and log only after an error.
 *  Public release Phase 6: shown only where the server finds the Claude Code command; everywhere else copy and paste
 *  (ui/notes-paste.js) is the way. */
function notesTaskControl(gameId, { quiet = false } = {}) {
  const host = el("div", { class: `notes-task${quiet ? " notes-task--quiet" : ""}` });
  let status = null;
  let problem = null;
  let busy = false; // any Claude Code run on the server, from the loading bar
  const statusText = () => {
    if (problem) return `${problem}.`;
    if (busy) return "Claude Code is loading data in the background. When everything is in, the To do says so; Refresh shows it.";
    if (!status) return null;
    if (status.error) return `Last run: ${text(status.error)}.`;
    if (quiet) return status.finishedAt ? `last run ${fmtTime(status.finishedAt)}` : null;
    return status.finishedAt ? `Last run finished ${fmtTime(status.finishedAt)}${status.fileWritten ? ", notes saved" : ""}.` : "Runs Claude Code on the server computer with the same prompt.";
  };
  const draw = () => {
    if (!problem && status?.commandFound !== true && !busy) {
      host.replaceChildren(); // no Claude Code on the server (or not known yet): copy and paste only
      return;
    }
    const tail = Array.isArray(status?.logTail) ? status.logTail.filter((line) => typeof line === "string").slice(-4) : [];
    const says = statusText();
    const label = busy ? "Writing…" : quiet ? "Rewrite with Claude Code" : "Write them with Claude Code";
    replaceWith(
      host,
      el("div", { class: "notes-task__row" },
        el("button", { class: `btn${quiet ? " btn--quiet" : " btn--primary"}`, type: "button", disabled: busy || !status?.commandFound ? true : null, onclick: () => start() }, label),
        says ? el("span", { class: "notes-task__status" }, says) : null,
      ),
      tail.length && !busy && status?.error ? el("pre", { class: "notes-task__log" }, tail.join("\n")) : null,
    );
  };
  const read = async () => {
    try {
      const envelope = await fetchJson("/api/notes/run");
      status = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      problem = null;
    } catch (error) {
      problem = error?.message || "Could not read the notes task";
    }
    draw();
  };
  const stop = onRunProgress((progress) => {
    if (!host.isConnected) {
      stop();
      return;
    }
    const now = progress?.running === true;
    const ended = busy && !now;
    busy = now;
    if (ended) read(); // the last run's line (saved, or what went wrong)
    else draw();
  });
  const start = async () => {
    try {
      const response = await fetch("/api/notes/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ gameId: isNum(gameId) ? gameId : null }) });
      const envelope = await response.json();
      status = envelope?.data && typeof envelope.data === "object" ? envelope.data : status;
      problem = envelope?.errors?.[0]?.message || null;
      busy = Boolean(envelope?.data?.running);
      draw();
      watchRun(); // the bar shows at once and follows the run
    } catch (error) {
      problem = error?.message || "Could not start the notes task";
      draw();
    }
  };
  busy = dataRunActive();
  draw();
  read();
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
        notesPaste({ gameId: data.game?.gameId, location: n }),
      );
    }
    // freeze wave F5 (owner 2026-10-20): your own lines are part of the program notes, "Note from <name>"; at the bottom since
    // 2026-11-14 (owner: "move this add a note to the bottom of the band", "Claude's always on top"), under Claude's notes
    // and their controls
    const own = isNum(data.game?.gameId) ? el("div", { class: "notes-own" }, gameNotesPanel({ gameId: data.game.gameId })) : null;
    if (data.ours === false && !n.present) return el("div", { class: "notes-empty" }, note("Program notes are written for our games; Claude's runs fill those."), own);
    if (!n.present && isNum(data.past)) return el("div", { class: "notes-empty" }, note(`No program notes were kept for this game in ${data.past}.`), own); // rollover R2: nothing to write now
    if (!n.present) {
      return el(
        "div",
        { class: "notes-empty" },
        notesPaste({ gameId: data.game?.gameId, location: n }), // Phase 17 #12: one line, two copy buttons, the box, one Save
        notesTaskControl(data.game?.gameId),
        own,
      );
    }
    const records = (value) => (Array.isArray(value) ? value.filter((r) => r && typeof r === "object") : []);
    const names = nameIndex(data);
    // Wave 5 (owner 2026-11-15, "Build as drawn"): the keys, the numbers and the matchup to watch over the sections
    const top = notesLayout(n.layout, { names, onName: openNamed, year: isNum(data.season) ? data.season : undefined });
    const written = editorial({ byline: { author: n.author, writtenAt: n.writtenAt }, sources: records(n.sources), sections: records(n.sections), names, onName: openNamed, top }); // not a wall of text (2026-11-07): blocks, short paragraphs, the names as taps
    tapRosterNames(written, data);
    return el(
      "div",
      {},
      written,
      data.ours === false || isNum(data.past) ? null : el("div", { class: "notes-foot" },
        el("details", { class: "notes-replace" }, el("summary", {}, "Replace with a new answer"), notesPaste({ gameId: data.game?.gameId, location: n })),
        notesTaskControl(data.game?.gameId, { quiet: true }),
      ),
      own,
    );
  };
  return band({ id: "program-notes", title: "Program notes", collapsible: true, foldable: true, summary: n.present ? `by ${text(n.author)}` : "not written yet", state: { status: "ready" }, body });
}

/**
 * The empty or half-filled state of a band filled from the game's notes. Phase 17 #13 sent the reader to the Program notes
 * band ("Add notes"); post-freeze Wave 1 (owner 2026-10-25: "every empty or partly filled section gets its own Claude
 * button saying what is missing") loads that part alone, merged into the notes there (ui/part-load.js), and only once it
 * can be had: a part published later in the week says from when. A finished game's band just says what was not published.
 */
function partNeeded(data, part, lead, detail) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  if (data.game?.completed || data.ours === false) return stateBlock({ lead, detail }); // another team's game: no runs from here (FEAT-5)
  return partLoad({ gameId: data.game?.gameId, parts: [part], lead, detail, due: n.due && typeof n.due === "object" ? n.due[part] : null });
}

/** The availability report's rows from the game's notes. */
function availabilityRows(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  return Array.isArray(n.availability) ? n.availability.filter((r) => r && typeof r === "object") : [];
}

function availabilityBand(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  const rows = availabilityRows(data);
  const teams = [{ school: data.us?.school || usSchool(), abbreviation: abbrOf(data.us, usLabel()) }, { school: data.them?.school, abbreviation: abbrOf(data.them) }];
  // post-freeze Wave 1: a report that lists one team only says the other is missing, with its own load
  const listed = new Set(rows.map((r) => (typeof r.team === "string" ? r.team.trim() : "")).filter(Boolean));
  const absent = rows.length && listed.size ? teams.filter((t) => typeof t.school === "string" && t.school && !listed.has(t.school)) : [];
  const where = `the ${confLabel()} availability report when the conference publishes one`;
  return band({
    id: "program-availability",
    title: "Availability report",
    collapsible: true,
    foldable: true,
    summary: rows.length ? `${rows.length} listed` : "",
    state: { status: "ready" },
    body: () => (rows.length
      ? el("div", {},
        availabilityTable({ rows, source: n.availabilitySource, updatedAt: n.availabilityUpdatedAt, teams }),
        absent.length === 1 ? partNeeded(data, "availability", `${text(absent[0].school)} is not listed yet.`, `A new report for both teams, from ${where}, replaces this one.`) : null)
      : partNeeded(data, "availability", "No availability report for this game yet.", `It comes from ${where}, else the latest injury news.`)),
  });
}

/**
 * The lineups (Phase 19, owner 2026-10-08; the mock of 2026-10-20: starters only, the depth behind them gone): the starters'
 * experience by unit across the band, then each matchup, our starter with his season chips beside the man he faces.
 */
function lineupsBand(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  return band({
    id: "program-lineups",
    title: "Lineups",
    collapsible: true,
    foldable: true,
    summary: lineupSummary(n.lineups) || "",
    state: { status: "ready" },
    body: () => (hasLineups(n.lineups)
      ? el("div", {},
        // the picture alone (the owner's marks on the Lineups board, 2026-11-01): both matchups across the line, each half
        // labeled with the coordinator and the scheme; the experience table and the matchup tables are gone
        formationBlock({ lineups: n.lineups, us: data.us, them: data.them, availability: n.availability, coaches: n.coaches, schemes: n.schemes, onPlayer: isNum(data.past) ? null : openLineupPlayer, rosters: !isNum(data.past) }) || note(LINEUPS_PICTURE_EMPTY),
        oneChartMissing(data, n.lineups))
      : partNeeded(data, "lineups", "No lineups for this game yet.", "They come from both teams' published depth charts.")),
  });
}

const LINEUPS_PICTURE_EMPTY = "The charts name no starter at a slot the picture draws.";

/** The names in Claude's text as taps once both rosters are here (ui/prose.js tapNamesIn): the lineups on a real install
 *  carry no ids, the rosters do. A roster that does not come leaves the text as drawn. */
function tapRosterNames(root, data) {
  if (isNum(data?.past)) return; // rollover R2: today's rosters are not that season's
  const sides = [["us", data?.us?.school], ["them", data?.them?.school]].filter(([, school]) => typeof school === "string" && school.trim());
  if (!sides.length) return;
  Promise.all(sides.map(([side, school]) => rosterFor(school).then((roster) => rosterEntries(roster, side === "us")))).then((lists) => {
    if (!root.isConnected) return;
    const index = indexFrom([...nameIndex(data).names, ...lists.flat()]);
    tapNamesIn(root, index, openNamed);
  }).catch((error) => console.warn("The notes' names could not be matched to the rosters; the text stays as drawn.", error?.message || error));
}

/** A name tapped in Claude's text (ui/prose.js): the player's card, from his side. */
function openNamed(entry) {
  if (!entry || typeof entry !== "object" || !entry.playerId) return;
  openPlayer(entry.playerId, { name: entry.name, position: entry.position, isUs: entry.isUs !== false });
}

function openLineupPlayer(row) {
  openPlayer(row.playerId, { ...row.player, name: row.name, position: row.slot, isUs: row.isUs !== false });
}

/**
 * One team's lineup as the picture, its defense over its offense (owner 2026-11-01: "The lineup picture should go in the
 * season\\my team as well"): from a program answer's notes, our side by default; null when its chart names nobody. My Team
 * and the Preseason Magazine draw it from the next game's program with their own ids.
 */
export function lineupBand(data, { id = "season-lineup", side = "us", title = "Lineup" } = {}) {
  const d = data && typeof data === "object" ? data : {};
  const n = d.notes && typeof d.notes === "object" ? d.notes : {};
  const l = n.lineups && typeof n.lineups === "object" ? n.lineups : {};
  const them = side === "them";
  const school = text((them ? d.them : d.us)?.school) || (them ? "" : usSchool());
  const sc = n.schemes && typeof n.schemes === "object" ? n.schemes : {};
  const own = them ? (sc.opponent && typeof sc.opponent === "object" ? sc.opponent : {}) : sc;
  const co = n.coaches && typeof n.coaches === "object" && n.coaches[side] && typeof n.coaches[side] === "object" ? n.coaches[side] : {};
  const picture = lineupPicture({
    defense: { school, side, lineup: l[side], scheme: own.defense, coordinator: co.defensiveCoordinator },
    offense: { school, side, lineup: l[side], scheme: own.offense, coordinator: co.offensiveCoordinator },
    availability: n.availability,
    onPlayer: openLineupPlayer,
  });
  if (!picture) return null;
  const root = el("div", { class: "formation" }, picture, el("p", { class: "note" }, `The published depth chart, as the Pre-Game Program draws it${text((them ? d.us : d.them)?.school) ? ` for ${text((them ? d.us : d.them).school)}` : ""}. Under each number: his position and surname, his class, height and weight, his grade alone (our stat grade). A gold number is on the availability report; a ring is an impact player. Tap a man for his card.`));
  attachRosters(root, { [side]: school, onPlayer: openLineupPlayer });
  return band({ id, title, collapsible: false, foldable: true, summary: lineupSummary(l) || "", state: { status: "ready" }, body: () => root });
}

/** Post-freeze Wave 1: one team's depth chart in, the other's not: say which, with the load for both charts. */
function oneChartMissing(data, lineups) {
  const l = lineups && typeof lineups === "object" ? lineups : {};
  const us = hasChart(l.us);
  const them = hasChart(l.them);
  if (us === them) return null;
  const school = us ? data.them?.school : data.us?.school || usSchool();
  return partNeeded(data, "lineups", `${text(school) || "The other team"}'s depth chart is missing.`, "Loading the lineups again asks for both teams' published charts.");
}

/** The visitor lists from the game's notes, both sides. */
function visitorLists(data) {
  const n = data.notes && typeof data.notes === "object" ? data.notes : {};
  const v = n.visitors && typeof n.visitors === "object" ? n.visitors : null;
  return { v, home: v ? visitorRows(v.home) : [], away: v ? visitorRows(v.away) : [] };
}

/** Freeze wave F4: the recruits on hand this week, from the notes, as In Game's Visitors sheet and the Recruiting page draw them. */
function visitorsBand(data) {
  const { v, home, away } = visitorLists(data);
  const total = home.length + away.length;
  const source = v && typeof v.source === "string" && v.source.trim() ? v.source.trim() : null;
  return band({
    id: "program-visitors",
    title: "Recruits on hand",
    collapsible: true,
    foldable: true,
    summary: total ? `${total} expected${source ? `, ${source}` : ""}` : "",
    state: { status: "ready" },
    body: () => (total
      ? el("div", {}, twoCol(el("div", {}, subhead(`${text(data.game?.homeIsUs ? data.us?.school : data.them?.school) || "Home"} visitors`), visitorsTable(home, { caption: "Home side's visitors" })), el("div", {}, subhead(`${text(data.game?.homeIsUs ? data.them?.school : data.us?.school) || "Away"} visitors`), visitorsTable(away, { caption: "Away side's visitors" }))), source ? el("p", { class: "note" }, `From ${source}${typeof v.updatedAt === "string" && v.updatedAt ? `, ${fmtDate(v.updatedAt, "short")}` : ""}. No list is published for every game.`) : null)
      : partNeeded(data, "visitors", "No visitor list for this game yet.", "It comes from the recruiting sites' visitor lists; not every game has one.")),
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
  const card = matchupCard({
    us: { ...(data.us || {}), abbreviation: abbrOf(data.us, usLabel()) },
    them: { ...them, abbreviation: abbrOf(them) },
    kicker: `${text(ours)}'s opponent`, // Phase 17 #9: the program speaks from our side
    teamTags,
    tags,
    schemes,
    coaches: data.notes?.coaches?.them || null, // freeze wave F4: their head coach and coordinators under the hero's name
    onNotes: () => {
      const notes = document.getElementById("program-notes");
      if (notes) revealBand(notes); // 2026-10-10: a missing scheme sends the reader to the notes, never a blank
    },
    rows,
  });
  return card;
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
export function radioBand() {
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

/** The recruiting table's rows for the Talent box (Wave 2 of the line): all of them, or with leftovers: true only what Talent
 *  Edge does not say (the cost and the returning production). Returns { rows, us, them, usAbbr, themAbbr, has }. */
function recruitingRows(data, { leftovers = false } = {}) {
  const r = objOf(data.recruiting);
  const us = objOf(r.us);
  const them = objOf(r.them);
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
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
  const all = [
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
  const rows = leftovers ? all.filter((row) => LEFTOVER_ROWS.has(row.label)) : all;
  const has = rows.some((row) => isNum(row.us.value) || isNum(row.them.value));
  return { rows, us, them, usAbbr, themAbbr, has };
}

/** PPA per play and Usage as leader categories (the line, Wave 2): each team's season leader by Play value, from the program's
 *  own PPA leaders; nothing until CFBD grades a game. The whole lines come from nowhere else, so each shows its key number. */
function ppaCategories(data) {
  const p = objOf(data.ppa);
  if (!p.available) return [];
  const top = (rows, key) => {
    const list = listOf(rows).filter((r) => r && typeof r === "object" && isNum(r[key]));
    if (!list.length) return null;
    const best = list.reduce((a, b) => (b[key] > a[key] ? b : a));
    return { playerId: best.playerId, player: best.player, position: best.position, value: best[key], headshotUrl: best.headshotUrl };
  };
  const make = (label, stat, key, format, category) => {
    const cat = { label, stat, format, category };
    const us = top(p.seasonLeaders?.us, key);
    const them = top(p.seasonLeaders?.them, key);
    if (!us && !them) return null;
    return { id: `${stat}-${label}`, label, category, stat, format, us: programLeader(us, cat), them: programLeader(them, cat), more: null };
  };
  return [make("PPA per play", "PPA", "ppa", "+2f", "ppa"), make("Usage", "USAGE", "usage", "pct", "ppa")].filter(Boolean);
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

/** A program leaders payload side as a leader-row player: its number in the board's format with a unit. */
export function programLeader(entry, cat) {
  if (!entry || typeof entry !== "object") return null;
  return { name: entry.player ?? entry.name, playerId: entry.playerId, number: entry.number, position: entry.position, headshotUrl: entry.headshotUrl, value: isNum(entry.value) ? entry.value : null, line: { hero: statLine(entry.value, cat?.format, cat?.stat), rest: "" } };
}

/**
 * Phase 17 #17: the leaders draw at once from the program's own answer; then /api/program/<id>/leaders adds each
 * leader's whole line with national and conference ranks and the line over conference games (it can take a
 * moment the first time a week's conference games are read, so it loads on its own). BUG-14 (the owner's board of
 * 2026-10-26): each category in the Tale of the tape's kit, the two leaders pulled to the middle over it (ui/leader-lines.js).
 */
function leadersBand(data) {
  const leaders = (Array.isArray(data.leaders) ? data.leaders : []).filter((l) => l && typeof l === "object");
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const host = el("div", {});
  const draw = (extra) => {
    const detailed = new Map((Array.isArray(extra?.categories) ? extra.categories : []).filter((c) => c && typeof c === "object").map((c) => [`${c.category}:${c.stat}`, c]));
    const confGames = objOf(extra?.conferenceGames);
    const categories = leaders.map((cat) => ({
      id: `${text(cat.stat)}-${text(cat.label)}`,
      label: cat.label,
      category: cat.category,
      stat: cat.stat,
      format: cat.format,
      us: programLeader(cat.us, cat),
      them: programLeader(cat.them, cat),
      more: detailed.get(`${cat.category || ""}:${cat.stat}`) || [...detailed.values()].find((c) => c.label === cat.label) || null,
    }));
    categories.push(...ppaCategories(data)); // the line, Wave 2: Play value's season leaders as two more categories
    host.replaceChildren(band({
      id: "program-leaders",
      title: "Leaders side by side",
      collapsible: true,
      foldable: true,
      summary: detailed.size ? "season and conference games, with ranks" : "season totals",
      state: partState(data.parts?.playersTeam, categories.some((l) => l.us || l.them)),
      emptyText: "Leaders appear after the first game.",
      body: () => el("div", {}, leaderPairs(categories, { usAbbr, themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, usConfGames: objOf(confGames.us).games, themConfGames: objOf(confGames.them).games, onTap: (player, side) => (player?.playerId && !isNum(data.past) ? openPlayer(player.playerId, { ...player, isUs: side === "us" }) : null) }), extra?.error ? el("p", { class: "note" }, `The whole lines did not load: ${text(extra.error)}.`) : detailed.size ? el("p", { class: "note" }, "Each category's leader on both teams, the season first and their conference games under it. The numbers sit beside the middle, as on Tale of the tape: the bar leans to the player with the better number (fewer interceptions is better), longer for a bigger gap; the rank is the player's FBS rank. Conference games count only games against conference teams. A tap on a name opens the player's card.") : null),
    }));
  };
  draw(null);
  const id = data.game?.gameId;
  if (!isNum(data.past) && leaders.length && (isNum(id) || /^\d{1,12}$/.test(String(id ?? "")))) {
    fetchJson(withTeam(`/api/program/${encodeURIComponent(String(id))}/leaders`, data.ours === false ? data.us?.school : null))
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
    summary: "both teams, national ranks",
    state: partState(data.parts?.lastStats, has),
    emptyText: "Last season's numbers appear once CFBD answers.",
    body: () => lastSeasonTwoTeam(last, abbrOf(data.us, usLabel()), abbrOf(data.them), { usTeam: data.us?.school, themTeam: data.them?.school, tug: true, halves: true }),
  });
}

function seriesBand(data) {
  const s = data.series && typeof data.series === "object" ? data.series : null;
  return band({
    id: "program-series",
    title: "Series",
    collapsible: true,
    foldable: true,
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


/** Another game's program: only the hash changes, and the router builds the view once (bug 13: it was twice). */
function openProgram(gameId) {
  if (!(isNum(gameId) || /^\d+$/.test(String(gameId ?? "")))) return;
  const hash = `#program=${encodeURIComponent(String(gameId))}`;
  if (window.location.hash !== hash) window.location.hash = hash;
}

const HEADLINES_SHOWN = 10;

/** Final pass (N4, owner 2026-10-09: the reader gets as much as possible): the team's headlines on the program too,
 *  from the Newspaper's feeds, loaded on their own so the program itself stays fast; under the notes since the one-column
 *  page (owner 2026-11-01), the ten newest. */
export function headlinesBand(items, { id = "program-headlines" } = {}) {
  // F8 feature 1: a finished game's Pre-Game tab shows the headlines kept with the kickoff lock, not today's feeds
  const kept = Array.isArray(items) ? items.filter((h) => h && typeof h === "object" && typeof h.title === "string" && h.title.trim()) : null;
  const host = el("div", {}, kept ? (kept.length ? newsDigest({ items: kept }) : note("No headlines were kept at kickoff.", { kind: "empty" })) : newsSkeleton(4));
  const section = band({ id, title: `${usName()} headlines`, collapsible: true, foldable: true, summary: kept ? "as they stood at kickoff" : "from the news feeds", body: () => host });
  if (kept) return section;
  fetchPatient(`/api/newspaper/headlines?limit=${HEADLINES_SHOWN}`) // batch 1: the headlines alone, never the whole paper (260 KB)
    .then((envelope) => {
      const items = Array.isArray(envelope?.data?.news) ? envelope.data.news.slice(0, HEADLINES_SHOWN) : []; // one column (2026-11-01): a stacked band shows a fixed count, no longer cut to the notes' depth
      host.replaceChildren(items.length ? newsDigest({ items }) : note(`No ${usName()} headlines in the feeds yet. They appear as the feeds publish.`));
    })
    .catch((error) => host.replaceChildren(note(`${text(error?.message || error)}. The band tries again with the next refresh.`, { kind: "error" })));
  return section;
}

// ---- The boxes (the season as one line, Wave 2; the owner's board of 2026-10-30) ----------------------------------------

const MATCHUP_VIEWS = [["stats", "Stats"], ["last", "Last season"]];

/** The matchup: Strengths and weaknesses' rows lead; under them, on the switch, every unit against the unit it faces (the
 *  Tale of the tape) or last season's numbers. The category sits in the middle, each bar toward its own side. Folds in Tale
 *  of the tape, Strengths and weaknesses, Last season and the opponent card's table. */
function matchupBox(data, { view = null } = {}) {
  const edges = Array.isArray(data.edges) ? data.edges : [];
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const teams = { usTeam: data.us?.school, themTeam: data.them?.school };
  const strengths = strengthsParts(data);
  const last = data.lastSeason && typeof data.lastSeason === "object" ? data.lastSeason : { rows: [] };
  const hasLast = Array.isArray(last.rows) && last.rows.length > 0;
  const allowed = MATCHUP_VIEWS.map(([id]) => id);
  let current = allowed.includes(view) ? view : rememberedView("matchup", "stats", allowed);
  const viewHost = el("div", { class: "box__view" });
  let seg = null;
  const draw = () => {
    if (current === "last") {
      viewHost.replaceChildren(
        el("h4", { class: "d2-head" }, `Last season${isNum(last.year) ? ` (${last.year})` : ""}`),
        hasLast ? lastSeasonTwoTeam(last, usAbbr, themAbbr, { ...teams, tug: true, halves: true }) : note("Last season's numbers appear once CFBD answers."),
      );
    } else {
      viewHost.replaceChildren(
        el("h4", { class: "d2-head" }, "Unit against unit"),
        edges.length ? tapeTable(edges, { usAbbr, themAbbr, ...teams }) : note("The matchup appears once both teams have played."),
        note("Each unit's national rank against the unit it faces: our offense against their defense, then our defense against their offense. The bar leans to the side with the better rank, longer for a bigger gap; the three biggest edges on each side are marked."),
      );
    }
    seg?.mark(current);
  };
  seg = viewSwitch(MATCHUP_VIEWS, current, (id) => {
    current = id;
    rememberView("matchup", id);
    draw();
  });
  draw();
  return band({
    id: "program-matchup",
    title: "The matchup",
    collapsible: true,
    foldable: true,
    summary: edgesSummary(edges, { usAbbr, themAbbr }) || strengths?.summary || "",
    tools: seg,
    state: partState(data.parts?.stats, edges.length > 0 || Boolean(strengths?.ranked)),
    emptyText: "The matchup appears once both teams have played.",
    body: () => el("div", { class: "box" }, strengths ? [el("h4", { class: "d2-head" }, "Strengths and weaknesses"), strengths.body()] : null, viewHost),
  });
}


/** Week by week: both teams' poll path as a line, then both margin strips on the same weeks, each slot opening its game;
 *  the switch puts Play value's game-by-game tables in the strips' place. Folds in Poll path, Margin by week and Play
 *  value's games. Null for a program with none of it (an old lock). */
function weekBox(data, { view = null } = {}) {
  const p = data && typeof data.pollPath === "object" && data.pollPath ? data.pollPath : null;
  const m = data && typeof data.margins === "object" && data.margins ? data.margins : null;
  if (!m) return null;
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them, "");
  const usRows = p && Array.isArray(p.us) ? p.us : [];
  const them = p && p.them && typeof p.them === "object" ? p.them : null;
  const lastRank = (rows) => {
    const last = [...rows].reverse().find((row) => row && typeof row === "object");
    return last && isNum(last.ap) ? last.ap : null;
  };
  const ordinalOf = (n) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
  const record = (rows) => {
    const finals = rows.filter((g) => g && typeof g === "object" && (g.result === "W" || g.result === "L" || g.result === "T"));
    if (!finals.length) return null;
    const wins = finals.filter((g) => g.result === "W").length;
    const losses = finals.filter((g) => g.result === "L").length;
    const ties = finals.length - wins - losses;
    return `${wins}-${losses}${ties ? `-${ties}` : ""}`;
  };
  const mUs = m && Array.isArray(m.us) ? m.us : [];
  const mThem = m && Array.isArray(m.them) ? m.them : [];
  const words = [];
  for (const [abbr, rows, rank] of [[usAbbr, mUs, lastRank(usRows)], [themAbbr, mThem, lastRank(them && Array.isArray(them.polls) ? them.polls : [])]]) {
    if (!abbr) continue;
    const parts = [record(rows), rank !== null ? `AP ${ordinalOf(rank)}` : null].filter(Boolean);
    if (parts.length) words.push(`${abbr} ${parts.join(", ")}`);
  }
  const gameId = data.game?.gameId ?? null;
  const themSchool = typeof data.them?.school === "string" ? data.them.school : null;
  const regular = [...mUs, ...mThem].filter((g) => g && typeof g === "object" && isNum(g.week) && !g.postseason && !g.playoffRound).map((g) => g.week);
  const weeks = regular.length ? { from: Math.min(...regular), to: Math.max(...regular) } : {};
  const strips = () => [
    mUs.length || mThem.length ? marginStrip({ games: mUs, nextGameId: gameId, team: data.ours === false ? data.us?.school || null : null, title: data.us?.school || usSchool(), note: !mThem.length, weeks }) : null,
    themSchool && mThem.length ? marginStrip({ games: mThem, nextGameId: gameId, team: themSchool, title: themSchool, note: true, weeks }) : null,
  ].filter(Boolean);
  const h3 = (t, school, side) => subhead(t, school ? { team: school, side } : {});
  const list = strips();
  const viewHost = el("div", { class: "box__view" }, list.length ? el("div", { class: "ms-pair" }, list) : note("Neither team has played a game yet."));
  return band({
    id: "program-week",
    title: "Margin by week", // wave 3 (2026-11-01, his inventory): the poll path is My Team's, one team at a time, and Play value by game the Ratings page's
    collapsible: true,
    foldable: true,
    summary: words.join(" · "),
    state: { status: mUs.length || mThem.length ? "ready" : "empty" },
    emptyText: "Neither team has played a game yet.",
    body: () => el(
      "div",
      { class: "box" },
      viewHost,
    ),
  });
}

/** Play value by game, both teams (wave 3, 2026-11-01: the Ratings page's band; it was the Week by week box's second view):
 *  each team's points added per play game by game, the two-team kit beside the other. */
export function ppaByGameBand(data, { id = "program-week-ppa" } = {}) {
  const ppa = objOf(data?.ppa);
  const usName = text(data?.us?.school || usSchool());
  const themName = text(data?.them?.school);
  const h3 = (t, school, side) => subhead(t, school ? { team: school, side } : {});
  const games = (title, rows, isThem) => el("div", {}, h3(title, isThem ? data?.them?.school : data?.us?.school || usSchool(), isThem ? "them" : "us"), rows.length ? statTable({ compact: true, sizes: true, columns: PPA_GAME_COLUMNS, rows, caption: title }) : note("No games with play value yet."));
  return band({
    id,
    title: "Play value by game",
    collapsible: true,
    foldable: true,
    summary: ppa.available ? `${usName} and ${themName}` : "",
    state: { status: ppa.available ? "ready" : "empty" },
    emptyText: "Play value appears once CFBD grades the first game.",
    body: () => el(
      "div",
      { class: "box" },
      twoCol(games(`${usName} by game`, ppaGameRows(ppa.games?.us), false), games(`${themName} by game`, ppaGameRows(ppa.games?.them), true)),
      note("Predicted points added per play, game by game. Positive is good for an offense; negative is good for a defense."),
    ),
  });
}

const LEFTOVER_ROWS = new Set(["Roster cost (rumored)", "Returning production", "Returning passing", "Returning receiving", "Returning rushing"]);

/** Talent: Talent Edge first (both rosters by position group, rated out of high school and the portal), then what it does not
 *  say: returning production, the rumored cost and the signing classes' stars. Folds in Talent Edge and Talent and recruiting;
 *  with no Talent Edge table yet the whole recruiting table stands. */
function talentBox(data, { edge = true } = {}) {
  const te = edge ? talentEdgeParts(data) : null;
  const teReady = Boolean(te && te.state.status === "ready");
  const rec = recruitingRows(data, { leftovers: teReady });
  const summary = (te && te.summary) || (isNum(rec.us.blueChip?.ratio) && isNum(rec.them.blueChip?.ratio) ? `blue chips ${rec.usAbbr} ${fmtStat(rec.us.blueChip.ratio, "pct")}, ${rec.themAbbr} ${fmtStat(rec.them.blueChip.ratio, "pct")}` : "talent, blue chips, returning production");
  return band({
    id: "program-talent",
    title: "Talent",
    collapsible: true,
    foldable: true,
    summary,
    state: teReady ? { status: "ready" } : partState(data.parts?.talent, rec.has || Boolean(te)),
    emptyText: "Talent and recruiting figures appear once CFBD has them for both teams.",
    body: () => el(
      "div",
      { class: "box" },
      te ? [el("h4", { class: "d2-head" }, "Talent Edge"), teReady ? te.body() : note(text(te.state.message || "Talent Edge has not been worked out yet."))] : null,
      el("h4", { class: "d2-head" }, teReady ? "Returning production, the cost and the classes" : "Talent and recruiting"),
      twoTeamTable({ rows: rec.rows, usAbbr: rec.usAbbr, themAbbr: rec.themAbbr, usTeam: data.us?.school, themTeam: data.them?.school, tug: true, caption: "Talent and recruiting, both teams" }),
      starsPair(rec.us, rec.them, rec.usAbbr, rec.themAbbr),
      apartNote(rec.us, rec.them, rec.usAbbr, rec.themAbbr),
      el("p", { class: "note" }, "Blue-chip ratio is four- and five-star signees over all signees in the last four classes; 50% is the line every champion since 2011 has cleared. The average rating is 247's composite, from 0 to 1. Returning production is the share of last season's predicted points added that is back. The roster cost is the rumored figure from the Load data page."),
    ),
  });
}

/** The two schools and the series: each school's history and facts, every meeting between them, then the opponents both have
 *  played this season. Folds in The two schools, Series and Common opponents. Null with none of the three. */
function schoolsBox(data) {
  const schools = twoSchoolsBody({ us: data.us, them: data.them, facts: data.facts });
  const s = data.series && typeof data.series === "object" ? data.series : null;
  const common = listOf(data.commonOpponents);
  if (!schools && !s && !common.length) return null;
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const us = data.us?.school || usSchool();
  const them = data.them?.school || "Opponent";
  const abbrs = {};
  if (typeof data.us?.school === "string") abbrs[data.us.school] = usAbbr;
  if (typeof data.them?.school === "string") abbrs[data.them.school] = themAbbr;
  const summary = s ? `${usAbbr} ${text(s.usWins)}, ${themAbbr} ${text(s.themWins)}${s.ties ? `, ${s.ties} ties` : ""}` : trophyLine(data.facts, data.us, data.them) || "history and facts";
  return band({
    id: "program-schools",
    title: "The two schools and the series",
    collapsible: true,
    foldable: true,
    summary,
    state: { status: "ready" },
    body: () => el(
      "div",
      { class: "box" },
      schools ? [el("h4", { class: "d2-head" }, "The two schools"), schools] : null,
      el("h4", { class: "d2-head" }, "Series"),
      s ? el("div", {}, s.streak ? note(`${text(s.streak.team)} has won ${text(s.streak.games)} straight.`) : null, seriesTable(s, { us, abbrs })) : note("No series history between these teams."),
      el("h4", { class: "d2-head" }, "Common opponents"),
      common.length ? commonOpponentsBlock(common, { usAbbr, themAbbr, usTeam: us, themTeam: them, usName: fullName(data.us) || us, themName: fullName(data.them) || them }) : note("No common opponents this season yet."),
    ),
  });
}

/** 3 Recruits on hand, then the Availability report. BUG-15 (the owner's note on his board of 2026-10-27, "fix the same way"):
    while one of the two has nothing yet it shrinks to one line, its words beside its buttons, so it never stands as a band
    of empty space. One column (owner 2026-11-01): the pair of the mock is two stacked bands. */
function reportBands(data) {
  const visitors = visitorsBand(data);
  const report = availabilityBand(data);
  const { home, away } = visitorLists(data);
  const empty = [home.length + away.length ? null : visitors, availabilityRows(data).length ? null : report].filter(Boolean);
  if (empty.length === 1) empty[0].classList.add("band--strip");
  return [visitors, report];
}

/** The bands in the owner's order: his arrangement of the page on the canvas (2026-10-20, every band a board he moved) and his
    marks on the drawn mock. One column since 2026-11-01 (owner: "every band just to be a single band"): the mock's pairs are
    stacked, each band the page's whole width. Players to watch and Prior weeks' programs are gone (the My Team page's schedule
    opens any week's program). The matchup card and a finished game's box scores were not on his canvas, so they follow the
    order until he places them (new or unplaced bands go to the bottom, 2026-10-13). */
function sections(data, { headlines, state = null } = {}) {
  const done = Boolean(data.game?.completed);
  const view = state && typeof state.view === "string" ? state.view : null;
  // the season as one line, Wave 2 (the owner's board of 2026-10-30, "Yeah, I think thats good"): the like bands in their
  // boxes, his order; Advanced matchup and Play value's deep tables left for the Season stop's The numbers
  const listed = [
    notesBand(data), // 1 Program notes, then the team's headlines under them (a pair of the mock, stacked since 2026-11-01)
    headlinesBand(headlines),
    matchupBox(data, { view }), // 2 The matchup: Strengths and weaknesses' rows, then Stats or Last season on the switch (Tale of the tape, Strengths and weaknesses, Last season and the opponent card's table folded in)
    weekBox(data, { view }), // 3 Week by week: the poll path over both margin strips, the margins or Play value by game on the switch (Poll path, Margin by week and Play value's games folded in)
    ...reportBands(data), // 4 Recruits on hand, then the Availability report (one line while it is empty)
    leadersBand(data), // 5 Leaders side by side, PPA per play and Usage added
    talentBox(data), // 6 Talent: Talent Edge first, then returning production, the cost and the classes (Talent and recruiting folded in)
    lineupsBand(data), // 7 Lineups: the starters' experience, the formation, the matchups
    tendenciesBand(data), // 8 Tendencies: the shot chart beside the down-and-distance table
    schoolsBox(data), // 9 The two schools and the series, the common opponents with them
    isNum(data.past) ? null : tripBand(data), // 10 Getting there (the radio went to In Game, wave 3 2026-11-01; What we need to My Team); rollover R2: a past season's trip is gone
  ];
  const unplaced = [];
  if (!done && data.ours !== false) unplaced.push(scoutBand(data)); // FEAT-10: new at the bottom
  // wave 3 (owner 2026-11-01, his inventory): the résumé, the recruiting stars on the roster, the impact players and the staff,
  // ours, each loading its own answer, at the bottom until he reorders them
  const late = isNum(data.past) ? [] : preLate(data); // rollover R2: today's résumé, roster and staff are not that season's
  return [...listed, ...unplaced, ...late].filter(Boolean);
}

/** The Pre-Game's late bands (wave 3): our Résumé from the season overview, the roster's stars and impact players, the Staff. */
function preLate(data) {
  const team = typeof data.us?.school === "string" && data.us.school ? data.us.school : usSchool();
  const query = data.ours === false ? `?team=${encodeURIComponent(team)}` : "";
  return [
    ...lateBands(`/api/season/overview${query}`, [["resume", "Résumé", "program-resume"]], (d) => ({ resume: resumeBand(d, team, { id: "program-resume" }) })),
    ...lateBands(`/api/roster${query}`, [["stars", "Recruiting stars on the roster", "roster-stars"], ["impact", "Impact players", "roster-impact"]], (d) => {
      const [, , , stars, impact] = rosterBands(d, { position: "", sort: null });
      return { stars, impact };
    }),
    ...lateBands(`/api/team/${encodeURIComponent(team)}`, [["staff", "Staff", "team-staff"]], (d) => ({ staff: teamExtraBands(d, { sorts: {} }).staff })),
  ];
}

/** The Post-Game's late bands (wave 3): the game's tables from its archive (lifted out of the archive page drawn apart: Team
 *  stats, Drives, Play by play, Play value), Road ahead from the season overview, the roster's stars, What Claude learned. */
function archiveLate(data) {
  const id = data.game?.gameId;
  return isNum(id)
    ? lateBands(`/api/archive/${id}`, [["stats", "Team stats", "archive-stats"], ["drives", "Drives", "archive-drives"], ["plays", "Play by play", "archive-plays"], ["ppa", "Play value", "archive-ppa"]], (d) => {
        const lifted = archiveGameBands(d);
        return { stats: lifted["archive-stats"], drives: lifted["archive-drives"], plays: lifted["archive-plays"], ppa: lifted["archive-ppa"] };
      }, { quiet: true })
    : [];
}

function postLate(data) {
  const team = typeof data.us?.school === "string" && data.us.school ? data.us.school : usSchool();
  const query = data.ours === false ? `?team=${encodeURIComponent(team)}` : "";
  const fromArchive = archiveLate(data);
  return [
    ...fromArchive,
    weatherBand(data),
    ...lateBands(`/api/season/overview${query}`, [["road", "Road ahead", "program-road"]], (d) => ({ road: roadAheadBand(d, { id: "program-road", sorts: {} }) })),
    ...lateBands(`/api/roster${query}`, [["stars", "Recruiting stars on the roster", "roster-stars"]], (d) => ({ stars: rosterBands(d, { position: "", sort: null })[3] })),
    data.ours !== false ? learnedBand({ id: "program-lessons" }) : null,
  ];
}

/** The game's weather, as In Game's panel had it (his inventory, 2026-11-01: on the Post-Game too). */
function weatherBand(data) {
  const w = data.weather && typeof data.weather === "object" ? data.weather : {};
  return band({
    id: "program-weather",
    title: "Weather",
    collapsible: true,
    foldable: true,
    state: { status: "ready" },
    body: () => el("div", { style: { padding: "12px" } }, w.available ? weatherRow({ kickoffText: fmtTime(data.game?.kickoff), ...w }) : note(text(w.note) || "No weather for this game.")),
  });
}

/** FEAT-10: Claude Code's scouting report on the opponent, from the app's numbers and the web. */
function scoutBand(data) {
  const id = data.game?.gameId;
  return writingBand({
    id: "program-scout",
    title: "Scouting report",
    kind: "scout",
    key: id,
    season: isNum(data.past) ? data.past : null,
    when: "Claude Code writes it on the Monday afternoon of the game week, from the app's numbers and the week's reports.",
    // BUG-15 (the owner's board of 2026-10-27): the summary across, Strengths beside Weaknesses, the keys side by side as
    // numbered cards; on a wide screen the keys are the third column
    draw: (w) => el(
      "div",
      { class: "scout" },
      typeof w.summary === "string" ? el("p", { class: "writing__lead" }, w.summary) : null,
      el(
        "div",
        { class: "scout__grid" },
        el("div", { class: "scout__col scout__col--good" }, subhead("Strengths"), bullets(w.strengths)),
        el("div", { class: "scout__col scout__col--bad" }, subhead("Weaknesses"), bullets(w.weaknesses)),
        keyCards(w.keys, `Keys for ${text(data.us?.school || usSchool())}`),
      ),
      sourcesLine(w.sources),
    ),
  });
}

/** The scouting report's keys as numbered cards (BUG-15), or null with none. */
function keyCards(keys, title) {
  const list = (Array.isArray(keys) ? keys : []).filter((k) => typeof k === "string" && k.trim());
  if (!list.length) return null;
  return el("div", { class: "scout__keys" }, subhead(title), el("ol", { class: "scout__cards" }, list.map((k, i) => el("li", { class: "scout__card" }, el("span", { class: "scout__num", "aria-hidden": "true" }, String(i + 1)), el("span", {}, k.trim())))));
}

/** FEAT-9: Claude Code's post-game piece, what decided it. */
function recapBand(data) {
  return writingBand({
    id: "program-recap",
    title: "What decided it",
    kind: "recap",
    key: data.game?.gameId,
    season: isNum(data.past) ? data.past : null,
    when: "Claude Code writes it the morning after the game, from the box score, the win probability and what was said after.",
    draw: (w) => {
      const drawn = el("div", {}, typeof w.headline === "string" ? el("h3", { class: "writing__head" }, w.headline) : null, bullets(w.decidedBy), ...paragraphs(w.paragraphs, { names: nameIndex(data), onName: openNamed }), sourcesLine(w.sources));
      tapRosterNames(drawn, data);
      return drawn;
    },
  });
}

// --- a finished game: the Pre-Game as it stood and the Post-Game stop (F8 feature 1, owner 2026-10-21; the line, Wave 3) ----
// "Pregame, here's what everybody was saying before the game; postgame, here's what everybody said after, so when you look
// back you have a history." The kickoff lock (/api/program/<id>/locked) holds the program as it stood; the Post-Game lock
// (/api/program/<id>/postgame) holds the Post-Game as it stood at close-out, with both teams' ranks of that poll and the news
// about the game. The Pre-Game as it stood: the cover and the bands exactly as locked. The Post-Game stop: the final cover, the
// closing checklist and the ranks of the day, then its own bands (finishedContent). Both locks are read once per game. The
// doubled rows (every band's kickoff side beside its after side) went with the stops: each side is its own stop now.

function ensureLocks(id, state, container) {
  if (state.locks && state.locks.gameId === id) return state.locks;
  const locks = { gameId: id, pre: undefined, post: undefined };
  state.locks = locks;
  const load = (key, url) =>
    fetchJson(url)
      .then((envelope) => {
        locks[key] = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      })
      .catch((error) => {
        locks[key] = null;
        if (!(isNum(error?.status) && error.status === 404)) console.warn(`The ${key === "pre" ? "kickoff" : "Post-Game"} lock could not be read.`, error);
      });
  Promise.allSettled([load("pre", withSeason(`/api/program/${encodeURIComponent(text(id))}/locked`, state.past)), load("post", withSeason(`/api/program/${encodeURIComponent(text(id))}/postgame`, state.past))]).then(() => {
    if (state.locks !== locks || !state.last || !container.isConnected) return;
    // batch 1: on the Post-Game stop only the pieces that read the locks are refilled; the Pre-Game as it stood is drawn anew
    if (state.tab !== "pre" && state.lockFill && state.lockFill.gameId === id && typeof state.lockFill.fill === "function") state.lockFill.fill();
    else render(state.last, container, state);
  });
  return locks;
}

/** Both teams' AP ranks at kickoff and the Sunday after: the ranks of their day, kept whatever happens to either later. */
function ranksStrip(locks, data) {
  const pre = locks.pre && typeof locks.pre === "object" ? locks.pre : null;
  const post = locks.post && typeof locks.post === "object" ? locks.post : null;
  if (locks.pre === undefined && locks.post === undefined) return null;
  const word = (n) => (isNum(n) ? `No. ${n}` : "unranked");
  const before = (side) => (pre ? word(pre.ranks?.[side]?.ap ?? pre[side]?.apRank) : DASH);
  const after = (side) => (post ? word(post[side]?.apRank) : DASH);
  const line = (who, side) => el("span", { class: "program-ranks__side" }, el("span", { class: "program-ranks__who" }, `${who}: `), `${before(side)} at kickoff · ${after(side)} after`);
  const foot = post ? "Each stop keeps the ranks of its day." : "The after side is written once the new poll is out.";
  return el("div", { class: "program-ranks" }, line(text(data.them?.school) || "Them", "them"), line(usName(), "us"), el("span", { class: "program-ranks__foot" }, foot));
}

/** The articles about the game from the feeds after the final, kept with the Post-Game lock. */
function newsBand(locks) {
  const post = locks.post;
  const items = post && typeof post === "object" && Array.isArray(post.news) ? post.news.filter((h) => h && typeof h === "object" && typeof h.title === "string") : null;
  return band({
    id: "program-news",
    title: "The game in the news",
    collapsible: false,
    foldable: true,
    summary: "articles about this game from the feeds, after the final",
    state: { status: post === undefined ? "loading" : "ready" },
    body: () => {
      if (post === undefined) return newsSkeleton(3);
      if (items && items.length) return newsDigest({ items });
      return note(post ? "No article about this game reached the feeds in the days after it." : "The news is kept with the Post-Game Program, written once the new poll is out.", { kind: "empty" });
    },
  });
}


function flowNote(message, kind = "empty") {
  return note(message, { kind });
}

/** The finished game's page body after the tabs: the active tab's cover and bands. */
function finishedContent(data, state, container, coverEl) {
  const id = data.game?.gameId;
  const locks = ensureLocks(id, state, container);
  const pre = locks.pre && typeof locks.pre === "object" && locks.pre.program && typeof locks.pre.program === "object" ? locks.pre : null;
  const past = isNum(data.past) ? data.past : null; // rollover R2: a past season's game, drawn from what was kept
  if (state.tab === "pre") {
    state.lockFill = null;
    if (locks.pre === undefined) return [coverEl, flowNote("Loading the program as it stood at kickoff.")];
    if (!pre && past) return [coverEl, flowNote(`The program was not locked at kickoff in ${past}, so the Pre-Game as it stood was not kept.`)];
    if (!pre) return [coverEl, flowNote("The program was not locked at kickoff, so the Pre-Game as it stood is not kept. This is the program as it reads today."), ...sections(data, { state })];
    const program = past ? { ...pre.program, past } : pre.program;
    const lockedCover = cover({ ...coverProps(program, { reveal: false }), prev: null, next: null, rail: past ? null : railHost({ kind: "pre", gameId: id }) });
    state.cover = lockedCover;
    return [lockedCover, past ? pastStrip(data, state) : null, flowNote(`The program as it stood at kickoff, locked ${fmtDateTime(pre.lockedAt)}.`), ...sections(program, { headlines: pre.headlines, state })];
  }
  // the Post-Game stop (the season as one line, Wave 3; the owner's board of 2026-10-30): the final cover, the closing checklist
  // and the ranks of the day, then What decided it, the Box score box, Expectations and results, the Circle of
  // Blame for this game and the game in the news. The kickoff side is its own stop (Pre-Game as it stood), so nothing is doubled.
  const view = typeof state.view === "string" ? state.view : null;
  const results = locks.pre === undefined ? band({ id: "program-results", title: "Expectations and results", collapsible: false, state: { status: "loading" } }) : resultsBand({ locked: locks.pre, data });
  const ours = data.ours !== false;
  // wave 3 of the one-column page (owner 2026-11-01, his inventory; "one copy each, as the numbers stand with the game
  // counted"): after the stop's own bands, the Pre-Game's bands drawn from today's answer, the game's tables from its archive,
  // Weather, Road ahead, the recruiting stars, What Claude learned and the whole Circle of Blame, at the bottom until he
  // reorders them. The Pre-Game tab keeps its kickoff-locked copies: nothing doubled on one tab.
  // a past season's game (rollover R2): no closing checklist (the line is this season's), no blame box, no live headlines,
  // no Road ahead, roster stars, lessons or Circle of Blame: each of those reads this season's answers
  // batch 1 (owner 2026-11-15, "Every page in ~1.5 s"): the four pieces that read the locks sit in hosts the locks' arrival
  // refills, so the page is not drawn again (that redraw asked every band of the page a second time, 20 more requests)
  const afterHost = el("div", { class: "program-after" }, past ? null : closingStrip(data, locks), ranksStrip(locks, data));
  const resultsHost = el("div", { class: "late" }, results);
  const newsHost = el("div", { class: "late" }, newsBand(locks));
  state.lockFill = { gameId: id, fill: () => {
    afterHost.replaceChildren(...[past ? null : closingStrip(data, locks), ranksStrip(locks, data)].filter(Boolean));
    resultsHost.replaceChildren(resultsBand({ locked: locks.pre, data }));
    newsHost.replaceChildren(newsBand(locks));
  } };
  return [
    coverEl,
    past ? pastStrip(data, state) : null,
    afterHost,
    ours ? recapBand(data) : null, // FEAT-9: What decided it leads
    boxScoreBox(data, { view }),
    resultsHost,
    ours && !past ? blameBox(data) : null,
    newsHost,
    past ? null : headlinesBand(undefined),
    weekBox(data),
    visitorsBand(data),
    availabilityBand(data),
    leadersBand(data),
    talentBox(data, { edge: false }),
    lineupsBand(data),
    tendenciesBand(data),
    ...(past ? archiveLate(data) : postLate(data)),
    ours && !past ? blameHost(state) : null,
  ];
}

/** Rollover R2: a past season's game, its stops and where it sits, under the cover in place of the rail (the rail is this
 *  season's line): the Pre-Game as it stood, the Post-Game as closed out, the game in the Archive, that season in review. */
function pastStrip(data, state) {
  const past = isNum(data.past) ? data.past : null;
  const id = data.game?.gameId;
  if (!past || !(isNum(id) || /^\d{1,12}$/.test(String(id ?? "")))) return null;
  const onPre = state.tab === "pre";
  const link = (href, words, on) => el("a", { class: `btn${on ? "" : " btn--quiet"}`, href, "aria-current": on ? "page" : null }, words);
  const g = data.game && typeof data.game === "object" ? data.game : {};
  const week = String(g.seasonType || "regular") === "postseason" ? "postseason" : isNum(g.week) ? `week-${g.week}` : null; // rollover R3: its papers
  const papers = week ? [link(`#newspaper=${week}?season=${past}`, "The week's paper", false), link(`#newspaper=${week}-sunday?season=${past}`, "The Sunday paper", false)] : [];
  return el(
    "div",
    { class: "past-strip" },
    el("p", { class: "note past-note" }, `${past}, as kept when the app moved on.`),
    el("div", { class: "past-strip__links" }, link(pastHref("pre", id, past), "Pre-Game as it stood", onPre), link(pastHref("post", id, past), "Post-Game", !onPre), link(pastHref("game", id, past), "The game in the Archive", false), ...papers, link(`#review=${past}`, `The ${past} season in review`, false)),
  );
}

/** The Circle of Blame's own view in a host at the bottom of the Post-Game (its four bands; the game's slice is the box above). */
function blameHost(state) {
  state.blame?.unmount();
  const host = el("div", { class: "late late--blame" });
  state.blame = createBlameView({ embedded: true });
  state.blame.mount(host);
  return host;
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

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  // no Back row (owner 2026-11-07: "I dont think we need the back for parts that are in the top menu"): the tab, the rail and the menu are the ways
  if (!data.game || typeof data.game !== "object") {
    const sched = data.parts && typeof data.parts === "object" ? data.parts.schedule : null; // final pass: CFBD down reads as an error, not an empty schedule
    const state = sched && sched.status === "error" ? { status: "error", message: `${text(sched.error)}. The app keeps retrying.` } : { status: "empty", message: "No games on the schedule yet." };
    container.replaceChildren(el("div", { class: "page program-page" }, band({ title: "Pre-Game Program", collapsible: false, state, errorLead: "Could not load the schedule." })));
    return;
  }
  const before = snapshotKeys(container); // the line, the total and the weather flash when a refresh changes them (P-10)
  const page = el("div", { class: "page program-page" });
  // the rail across the cover's top (owner 2026-10-30, one short row since 2026-11-14): its ‹ › at the row's ends (2026-11-15)
  // replace the cover's own arrows, so the kicker row keeps the title alone
  // a finished game's Pre-Game (?tab=pre) is that stop on the rail even while its kickoff copy loads or was never kept, so the
  // arrows step from where the reader is (2026-11-15: the rail is the only way between the two now)
  const railKind = data.game?.completed && state.tab !== "pre" ? "post" : "pre";
  const past = isNum(data.past) ? data.past : null; // rollover R2: a past season's game, as kept
  const coverEl = cover({ ...coverProps(data, { reveal: !state.revealed }), prev: null, next: null, rail: past ? null : railHost({ kind: railKind, gameId: data.game?.gameId }) });
  state.revealed = true; // the reveal plays once per visit, not on every refresh (P-10 item 2)
  state.cover = coverEl;
  useOpponentColors(data.them);
  const tools = data.ours === false ? el("div", { class: "program-tools" }, followButton(data.game, data.us?.school)) : null; // FEAT-1: watch another team's game live; Print is a band at the bottom (owner 2026-11-07)
  // wave B (owner 2026-10-13): the expectations locked at kickoff beside the result on a finished game's program, at the
  // bottom until the owner orders it ("for every screen in the future, the new stuff goes to the bottom, until I reorder
  // them", 2026-10-13); the two schools' history is in the order now (the mock, 2026-10-20)
  state.last = envelope;
  // a finished game's Pre-Game as it stood and its Post-Game: no tab pair above the rail since 2026-11-15 (owner: "There are
  // the post and pregame above the place where I want the navigation to be"); the rail's ‹ › step between the two
  if (data.game?.completed) page.append(...[tools, ...finishedContent(data, state, container, coverEl), printBand()].filter(Boolean));
  else page.append(...[tools, coverEl, past ? pastStrip(data, state) : null, ...sections(data, { state }), printBand()].filter(Boolean));
  if (state.flow) state.flow.stop();
  if (state.chips) state.chips.stop();
  // Phase 17 #5: the sections as a pinned row of chips above the page (a pinned row inside the grid would only
  // stay pinned within its own grid cell)
  state.chips = sectionChips(page);
  state.chips.refresh();
  container.replaceChildren(state.chips, page);
  // one column (owner 2026-11-01): every band the page's whole width, in order, its content capped at the reading width (the
  // boxes too: at 1,880 px the strengths' bars and the talent table put every label a screen from its value)
  state.flow = flow(page);
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
  const host = el("div", { dataset: { results: text(id) } });
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

/** The game in the news on its own (the menu's flyout): the Post-Game lock read first, as the finished program reads it. */
function newsAlone(data) {
  const id = data.game?.gameId;
  const host = el("div", {}, newsBand({ post: undefined }));
  if (!data.game?.completed || id === undefined || id === null) {
    host.replaceChildren(newsBand({ post: null }));
    return host;
  }
  fetchJson(`/api/program/${encodeURIComponent(text(id))}/postgame`)
    .then((envelope) => host.replaceChildren(newsBand({ post: envelope?.data && typeof envelope.data === "object" ? envelope.data : null })))
    .catch((error) => {
      if (!(isNum(error?.status) && error.status === 404)) console.warn("The Post-Game lock could not be read.", error);
      host.replaceChildren(newsBand({ post: null }));
    });
  return host;
}

/** A table that only a finished game has, asked for before the final: what it will hold and when (the menu's flyout). */
/** The poll path of both teams (ENH-19, the owner's board of 2026-10-28, "Yes, add it" 2026-10-30 for the Pre-Game Program):
 *  the Résumé's chart with this week's opponent, both sides' AP and Coaches rows under it; null for a program with none (an
 *  old lock). "FLA 17th · UGA 3rd in the AP" in the head. */
export function pollPathBand(data) {
  const p = data && typeof data.pollPath === "object" && data.pollPath ? data.pollPath : null;
  if (!p) return null;
  const usRows = Array.isArray(p.us) ? p.us : [];
  const them = p.them && typeof p.them === "object" ? p.them : null;
  const rank = (rows) => {
    const last = [...rows].reverse().find((row) => row && typeof row === "object");
    return last && isNum(last.ap) ? last.ap : null;
  };
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = them ? abbrOf(data.them, them.abbreviation || "") : "";
  const ranked = usRows.some((row) => row && (isNum(row.ap) || isNum(row.coaches))) || Boolean(them);
  const ordinalOf = (n) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
  const sides = [[usAbbr, rank(usRows)], ...(them ? [[themAbbr, rank(Array.isArray(them.polls) ? them.polls : [])]] : [])].filter(([abbr]) => abbr);
  const words = sides.some(([, r]) => r !== null) ? sides.map(([abbr, r]) => `${abbr} ${r !== null ? ordinalOf(r) : "not ranked"}`) : [];
  return band({
    id: "program-pollpath",
    title: "Poll path",
    collapsible: true,
    foldable: true,
    summary: words.length ? `${words.join(" · ")} in the AP` : "neither team ranked in the AP",
    state: { status: ranked ? "ready" : "empty" },
    emptyText: "Neither team has been ranked in a poll this season.",
    body: () => pollPathBlock({ polls: usRows, opponent: them ? { ...them, school: them.school || data.them?.school, abbreviation: themAbbr } : null, team: data.us?.school || usSchool(), short: usAbbr, head: false, both: true }),
  });
}

/** Both teams' margin strips (ENH-19 chart 3, the owner's board of 2026-10-30, "Add to program"): ours, then this week's
 *  opponent's, each headed by its school (side by side where the band is wide enough), each slot opening that game's program
 *  from that side; this week's game is the marked tick in both. "FLA 5-2 · UGA 6-1" in the head; null for a program with none. */
export function marginBand(data) {
  const m = data && typeof data.margins === "object" && data.margins ? data.margins : null;
  if (!m) return null;
  const us = Array.isArray(m.us) ? m.us : [];
  const them = Array.isArray(m.them) ? m.them : [];
  const gameId = data.game?.gameId ?? null;
  const record = (rows) => {
    const finals = rows.filter((g) => g && typeof g === "object" && (g.result === "W" || g.result === "L" || g.result === "T"));
    if (!finals.length) return null;
    const wins = finals.filter((g) => g.result === "W").length;
    const losses = finals.filter((g) => g.result === "L").length;
    const ties = finals.length - wins - losses;
    return `${wins}-${losses}${ties ? `-${ties}` : ""}`;
  };
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them, "");
  const words = [[usAbbr, record(us)], [themAbbr, record(them)]].filter(([abbr, r]) => abbr && r).map(([abbr, r]) => `${abbr} ${r}`);
  const themSchool = typeof data.them?.school === "string" ? data.them.school : null;
  // both strips over the same weeks, so this week lines up under this week
  const regular = [...us, ...them].filter((g) => g && typeof g === "object" && isNum(g.week) && !g.postseason && !g.playoffRound).map((g) => g.week);
  const weeks = regular.length ? { from: Math.min(...regular), to: Math.max(...regular) } : {};
  const strips = [
    marginStrip({ games: us, nextGameId: gameId, team: data.ours === false ? data.us?.school || null : null, title: data.us?.school || usSchool(), note: !them.length, weeks }),
    themSchool ? marginStrip({ games: them, nextGameId: gameId, team: themSchool, title: themSchool, note: true, weeks }) : null,
  ].filter(Boolean);
  return band({
    id: "program-margins",
    title: "Margin by week",
    collapsible: true,
    foldable: true,
    summary: words.join(" · "),
    state: { status: strips.length ? "ready" : "empty" },
    emptyText: "Neither team has played a game yet.",
    body: () => el("div", { class: "ms-pair" }, strips),
  });
}

function untilFinal(title, words) {
  return band({ title, collapsible: false, state: { status: "empty", message: words } });
}

/** ENH-15 (owner 2026-10-23: "Parking, tailgate and all of that, maybe even how to get into the stadium and such. All of it
    should be printed on the pre-game program in case the phone doesn't work, you can print or screenshot it"): the stadium,
    the way there in this device's maps app and a QR code a second phone scans, then what Claude Code found on the school's
    and the stadium's game-day pages; its own Print puts the band alone on a page in ink on white. null with no venue. */
export function tripBand(data, { id = "program-trip" } = {}) {
  const trip = data?.trip && typeof data.trip === "object" ? data.trip : null;
  if (!trip || !isNum(trip.venueId)) return null;
  const name = typeof trip.name === "string" && trip.name.trim() ? trip.name.trim() : "The stadium";
  const town = [trip.city, trip.state].filter((w) => typeof w === "string" && w.trim()).join(", ");
  const qr = typeof trip.qr === "string" && trip.qr.startsWith("data:image/svg+xml") ? trip.qr : null;
  const lead = () => el(
    "div",
    { class: "trip__lead" },
    el(
      "div",
      { class: "trip__where" },
      el("h3", { class: "trip__name" }, name),
      town ? el("p", { class: "trip__town" }, town) : null,
      el("p", { class: "trip__tools" }, directionsLink(trip), " ", printOnlyButton(() => (typeof document.getElementById === "function" ? document.getElementById(id) : null), "Print Getting there")),
    ),
    qr ? el("figure", { class: "trip__qr" }, el("img", { src: qr, alt: `QR code: directions to ${name} in Google Maps`, width: "120", height: "120" }), el("figcaption", {}, "Scan for directions")) : null,
  );
  const part = (title, body) => (body ? el("div", { class: "trip__part" }, subhead(title), body) : null);
  const words = (value) => (typeof value === "string" && value.trim() ? el("p", {}, value.trim()) : null);
  const lots = (list) => {
    const rows = (Array.isArray(list) ? list : []).filter((l) => l && typeof l === "object" && typeof l.name === "string" && l.name.trim());
    return rows.length ? el("ul", { class: "writing__list trip__lots" }, rows.map((l) => el("li", {}, el("b", {}, l.name.trim()), typeof l.detail === "string" && l.detail.trim() ? `: ${l.detail.trim()}` : ""))) : null;
  };
  return writingBand({
    id,
    title: "Getting there",
    kind: "trip",
    key: trip.venueId,
    when: "Claude Code loads it once a season for each primary team's stadium and this week's game, from the school's and the stadium's game-day pages.",
    summary: () => name,
    lead,
    draw: (w) => el(
      "div",
      { class: "trip" },
      words(w.address) ? el("p", { class: "trip__address" }, el("b", {}, "Address: "), w.address.trim()) : null,
      el(
        "div",
        { class: "trip__grid" },
        part("This game", bullets(w.gameDay)),
        part("Parking", lots(w.parking)),
        part("Tailgating", bullets(w.tailgating)),
        part("Gates", words(w.gates)),
        part("Bag policy", words(w.bagPolicy)),
        part("Getting in", bullets(w.entry)),
        part("Shuttles, transit and rideshare", bullets(w.transit)),
        part("Accessibility", bullets(w.accessibility)),
      ),
      note("Policies change: check the school's or the stadium's game-day page before you go."),
      sourcesLine(w.sources),
    ),
  });
}

/**
 * The program's tables by name, for the menu's wide flyouts (the layout pass, owner 2026-10-22: "I just want the table that
 * is already there, but I want it available in flyout"): each built from the program's own answer exactly as the page
 * builds it, so a table looks the same in both places. views/panels.js opens them.
 */
export const PROGRAM_BANDS = {
  notes: (data) => notesBand(data),
  headlines: () => headlinesBand(undefined),
  // the season as one line, Wave 2 (2026-10-30): the boxes, each view its own flyout and page
  matchup: (data) => matchupBox(data, { view: "stats" }),
  matchupLast: (data) => matchupBox(data, { view: "last" }),
  week: (data) => weekBox(data) || untilFinal("Margin by week", "The margins appear once the schedules have been read."),
  weather: (data) => weatherBand(data),
  resume: (data) => preLate(data)[0],
  stars: (data) => preLate(data)[1],
  impact: (data) => preLate(data)[2],
  staff: (data) => preLate(data)[3],
  stats: (data) => (data.game?.completed ? postLate(data)[0] : untilFinal("Team stats", "The game's team stats show here once the game is over and archived.")),
  drives: (data) => (data.game?.completed ? postLate(data)[1] : untilFinal("Drives", "The game's drives show here once the game is over and archived.")),
  plays: (data) => (data.game?.completed ? postLate(data)[2] : untilFinal("Play by play", "The game's plays show here once the game is over and archived.")),
  ppaGame: (data) => (data.game?.completed ? postLate(data)[3] : untilFinal("Play value", "The game's play value shows here once the game is over and CFBD posts it.")),
  road: (data) => postLate(data)[5],
  lessons: (data) => (data.ours !== false ? learnedBand({ id: "program-lessons" }) : untilFinal("What Claude learned", "Claude's lessons are about our own games.")),
  talent: (data) => talentBox(data),
  schools: (data) => schoolsBox(data) || untilFinal("The two schools and the series", "The schools' facts, the series and the common opponents appear once they are loaded."),
  leaders: (data) => leadersBand(data),
  lineups: (data) => lineupsBand(data),
  tendencies: (data) => tendenciesBand(data),
  availability: (data) => availabilityBand(data),
  visitors: (data) => visitorsBand(data),
  trip: (data) => tripBand(data) || untilFinal("Getting there", "Getting there appears once the game has a stadium on the schedule."), // ENH-15
  // the Post-Game stop's boxes (the line, Wave 3)
  box: (data) => boxScoreBox(data, { view: "box" }) || untilFinal("Box score", "The box score shows here once this week's game is over. Earlier games' boxes are in the Archive."),
  boxAdvanced: (data) => boxScoreBox(data, { view: "advanced" }) || untilFinal("Box score", "The advanced box score shows here once this week's game is over and CFBD posts it."),
  blame: (data) => (data.game?.completed && data.ours !== false ? blameBox(data) : untilFinal("Circle of Blame", "Claude writes the Circle of Blame the Sunday after our game, from the week's evidence; it shows here once the game is over.")),
  results: (data) => (data.game?.completed ? resultsSlot(data, {}) : untilFinal("Expectations and results", "The program locked at kickoff is held against the result here once the game is over.")),
  news: (data) => newsAlone(data),
};

/** Print as the program's last band (owner 2026-11-07: "can it be it's own band, at the bottom, instead of always at the top?"):
 *  the same Print sheet as before (ui/print.js), the whole program or one band, on paper or as a PDF. */
function printBand() {
  return band({ id: "program-print", title: "Print", collapsible: false, foldable: true, state: { status: "ready" }, body: () => el("div", { class: "program-print" }, el("p", { class: "note" }, "The whole program, or the bands you pick, on paper or as a PDF."), printButton()) });
}

/** The loading page in its real shape (P-04 item 5): the cover, then the first bands of the owner's order (2026-10-10). */
function loadingPage(state) {
  const loading = (title, skeleton) => band({ title, collapsible: false, state: { status: "loading" }, skeleton });
  return el(
    "div",
    { class: "page program-page", "aria-busy": "true" },
    coverSkeleton(),
    loading("Program notes", () => el("div", { class: "skel skel--row" })),
    loading(`${text(usName())} headlines`, () => el("div", { class: "skel skel--row" })),
    loading("Tale of the tape", () => statTableSkeleton(8, 3)),
  );
}

const TICK_MS = 30000;

export function createProgramView({ onStatus, gameId = null, focus = null, team = null, tab = null, view: boxView = null, season = null } = {}) {
  const state = { gameId, focus, team: otherTeam({ team }), revealed: false, cover: null, flow: null, chips: null, tab: tab === "pre" ? "pre" : "post", view: typeof boxView === "string" ? boxView : null, locks: null, last: null, past: gameId ? pastYear(season) : null }; // past: rollover R2, ?season=2026 reads that season's kept copy // team: FEAT-5, the side another game is seen from; tab: the line's Pre-Game stop of a finished game (?tab=pre); view: a box's switch for this visit (?view=last)
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
      url: state.past ? `/api/seasons/${state.past}/game/${encodeURIComponent(state.gameId)}` : state.gameId ? withTeam(`/api/program/${encodeURIComponent(state.gameId)}`, state.team) : "/api/program/next",
      onStatus,
      render: (envelope, container) => {
        render(envelope, container, state);
        startTicking();
      },
      renderError: (message, container, retry) => container.replaceChildren(errorPanel(state.past ? `The ${state.past} game` : "Pre-Game Program", message, retry)),
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
      state.blame?.unmount(); // the Post-Game's Circle of Blame host (wave 3)
      state.blame = null;
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
