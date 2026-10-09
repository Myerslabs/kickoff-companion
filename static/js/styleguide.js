// The design-system page: every component, every state, real numbers from the fixtures.
// It renders inside the real shell so the top bar, menu, and radio bar are exercised too.
// Revised 2026-09-21: the live sheet is a remote control, plus the newspaper, team page,
// recruiting, matchup card, and the expanded player card from the screenshot brief.

import { sample } from "./sample-data.js";
import { applyOpponentColors, contrastRatio } from "./ui/colors.js";
import { cover } from "./ui/cover.js";
import { delaySlider } from "./ui/delay-slider.js";
import { DASH, el, fmtDate, fmtDateTime, fmtNum, fmtPct, fmtStat, fmtTime, isNum, playerFace, teamLink, teamLogo, text } from "./ui/dom.js";
import { metricLink, nationalHref, pollHref } from "./ui/national-link.js";
import { installNationalLinks, listLink, nationalListBody, openNationalSheet } from "./ui/national-sheet.js"; // Phase 16 NV
import { openMatchupSheet } from "./ui/matchup-sheet.js"; // Phase 16 NV (UX-12)
import { errorPanel } from "./views/common.js";
import { driveList, driveListSkeleton } from "./ui/drive-bar.js";
import { gradeBlock, gradeChip } from "./ui/grade.js"; // public release Phase 7
import { availabilityTable, editorial, editorialSkeleton } from "./ui/editorial.js";
import { boxLeader, leadersGrid, leadersSkeleton } from "./ui/leaders.js";
import { matchupCard, weatherRow } from "./ui/matchup-card.js";
import { newsDigest, newsSkeleton, slateList, slateSkeleton } from "./ui/news.js";
import { openPlayerCard, playerCard } from "./ui/player-card.js";
import { KEY_PLAYS, keyPlayBadge, pill } from "./ui/pills.js";
import { playLog, playLogSkeleton } from "./ui/play-log.js";
import { openSheet, remoteBar } from "./ui/remote.js";
import { recordLine, scheduleList, scheduleSkeleton } from "./ui/schedule.js";
import { radioBar, radioPanel, shell } from "./ui/shell.js";
import { situationGrid, situationSkeleton } from "./ui/situation.js";
import { trendRow, trendSkeleton } from "./ui/sparkline.js";
import { backRow, band, expandAllControl, jumpList, note, stateBlock, subhead } from "./ui/states.js";
import { pollBadge, rankChip, rankChipPlaceholder, statTable, statTableSkeleton } from "./ui/stat-table.js";
import { strip } from "./ui/strip.js";
import { formSquares, impactCard, impactSkeleton, profileTable, profileTiles, starStrip, teamHeader, tiles } from "./ui/team-page.js";
import { quarterLine, teamStatsSkeleton, teamStatsTable } from "./ui/team-stats.js";
import { ticker } from "./ui/ticker.js";
import { successRow, winProbabilityChart, winProbabilitySkeleton } from "./ui/wp-chart.js";

const live = sample.live || {};
const US = { name: sample.team?.school || "Swampwater Tech", abbr: sample.team?.abbreviation || "SWT", ...(sample.team || {}) };
const LIVE_THEM = { name: live.away?.school === US.name ? live.home?.school : live.away?.school };
LIVE_THEM.abbr = (live.home?.school === LIVE_THEM.name ? live.home?.abbreviation : live.away?.abbreviation) || LIVE_THEM.name?.slice(0, 3)?.toUpperCase();
const liveHomeIsUs = live.home?.school === US.name;
const liveUs = liveHomeIsUs ? live.home : live.away;
const liveThem = liveHomeIsUs ? live.away : live.home;
const program = sample.program || {};
const opponent = program.them || {};
const profiles = sample.profiles || {};
applyOpponentColors(liveThem);

// --- helpers ---------------------------------------------------------------------------------

function section(id, title, blurb, ...children) {
  return el("section", { class: "sg__section", id }, el("div", { class: "sg__head" }, el("h2", {}, title), blurb ? el("p", {}, blurb) : null), ...children);
}

function label(txt) {
  return el("div", { class: "sg__label" }, txt);
}

function states(title, { kind = "neutral", body, skeleton, emptyText, ageSeconds = 254, errorMessage }) {
  return el(
    "div",
    { class: "sg__states" },
    band({ title, kind, collapsible: false, state: { status: "loading" }, skeleton }),
    band({ title, kind, collapsible: false, state: { status: "empty" }, emptyText }),
    band({ title, kind, collapsible: false, state: { status: "stale", ageSeconds }, body }),
    band({ title, kind, collapsible: false, state: { status: "error", message: errorMessage || "CFBD did not answer. Retrying in 60 s." } }),
  );
}

function recordText(record) {
  if (!record || !isNum(record.wins) || !isNum(record.losses)) return null;
  return record.ties ? `${record.wins}-${record.losses}-${record.ties}` : `${record.wins}-${record.losses}`;
}

function rosterEntry(playerId) {
  return (sample.roster || []).find((p) => p.playerId === playerId) || null;
}

function playerRows(team, category) {
  return (live.playerStats?.[team]?.[category] || []).map((row) => ({ name: row.name, playerId: row.playerId, ...row.stats }));
}

const BOX_COLUMNS = {
  passing: [{ key: "name", label: "Passing", kind: "text" }, { key: "C/ATT", label: "C/ATT", kind: "text", sortable: false }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Y/A", format: "1f" }, { key: "TD", label: "TD" }, { key: "INT", label: "Int" }, { key: "QBR", label: "QBR", format: "1f" }],
  rushing: [{ key: "name", label: "Rushing", kind: "text" }, { key: "CAR", label: "Car" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "TD", label: "TD" }, { key: "LONG", label: "Long" }],
  receiving: [{ key: "name", label: "Receiving", kind: "text" }, { key: "REC", label: "Rec" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "TD", label: "TD" }, { key: "LONG", label: "Long" }],
  defensive: [{ key: "name", label: "Defense", kind: "text" }, { key: "TOT", label: "Tkl" }, { key: "SOLO", label: "Solo" }, { key: "TFL", label: "TFL", format: "1f" }, { key: "SACKS", label: "Sck", format: "1f" }, { key: "PD", label: "PD" }, { key: "QB HUR", label: "Hur" }],
  interceptions: [{ key: "name", label: "Interceptions", kind: "text" }, { key: "INT", label: "Int" }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }],
  kicking: [{ key: "name", label: "Kicking", kind: "text" }, { key: "FG", label: "FG", kind: "text", sortable: false }, { key: "PCT", label: "Pct", format: "1f" }, { key: "LONG", label: "Long" }, { key: "XP", label: "XP", kind: "text", sortable: false }, { key: "PTS", label: "Pts" }],
  punting: [{ key: "name", label: "Punting", kind: "text" }, { key: "NO", label: "No" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "TB", label: "TB" }, { key: "In 20", label: "In 20" }, { key: "LONG", label: "Long" }],
  puntReturns: [{ key: "name", label: "Punt returns", kind: "text" }, { key: "NO", label: "No" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "LONG", label: "Long" }, { key: "TD", label: "TD" }],
  kickReturns: [{ key: "name", label: "Kick returns", kind: "text" }, { key: "NO", label: "No" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "LONG", label: "Long" }, { key: "TD", label: "TD" }],
};
const BOX_ORDER = ["passing", "rushing", "receiving", "defensive", "interceptions", "puntReturns", "kickReturns", "kicking", "punting"];

function boxTables(team, { limit } = {}) {
  const categories = BOX_ORDER.filter((name) => (live.playerStats?.[team]?.[name] || []).length);
  return el(
    "div",
    {},
    categories.map((name) => {
      const columns = BOX_COLUMNS[name];
      const sortKey = columns.find((c) => c.kind !== "text")?.key || columns[1].key;
      const rows = playerRows(team, name).sort((a, b) => (isNum(b[sortKey]) ? b[sortKey] : -1) - (isNum(a[sortKey]) ? a[sortKey] : -1));
      return statTable({ columns, rows: limit ? rows.slice(0, limit) : rows, compact: true, sort: { key: sortKey, dir: "descending" }, onRowTap: (row) => openCard(row.name, row.playerId, team !== US.name) });
    }),
  );
}

const RATE_KEYS = /^(YPA|YPC|YPR|AVG|PCT|QBR|RATING)$/i;

function cardProps(name, playerId, them = false) {
  const entry = rosterEntry(playerId) || {};
  let seasons = null;
  for (const board of Object.values(sample.leaders || {})) {
    const hit = (board.team || []).find((row) => row.playerId === playerId);
    if (!hit || seasons) continue;
    const detail = Object.entries(hit.detail || {}).filter(([, v]) => isNum(v));
    const keys = new Set([board.stat, ...detail.map(([k]) => k)]);
    // Career rates are recomputed from the summed columns when both parts exist.
    const avgFor = (k) => {
      if (k === "YPA" && keys.has("YDS") && keys.has("ATT")) return { num: "YDS", den: "ATT" };
      if (k === "PCT" && keys.has("COMPLETIONS") && keys.has("ATT")) return { num: "COMPLETIONS", den: "ATT" };
      if (k === "YPC" && keys.has("YDS") && keys.has("CAR")) return { num: "YDS", den: "CAR" };
      if (k === "YPR" && keys.has("YDS") && keys.has("REC")) return { num: "YDS", den: "REC" };
      return null;
    };
    const columns = [
      { key: "year", label: "Year", kind: "text" },
      { key: board.stat, label: board.stat, sum: true },
      ...detail.map(([k, v]) => ({ key: k, label: k, sum: !RATE_KEYS.test(k), avg: avgFor(k), format: k === "PCT" ? "pct" : Number.isInteger(v) ? "0f" : "1f" })),
    ];
    seasons = { columns, rows: [{ year: String(sample.season || DASH), [board.stat]: hit.value, ...Object.fromEntries(detail) }] };
  }
  const gameLog = [];
  for (const [category, rows] of Object.entries(live.playerStats?.[them ? LIVE_THEM.name : US.name] || {})) {
    const hit = rows.find((row) => row.playerId === playerId);
    if (hit) gameLog.push({ opponent: `Wk ${text(live.week)} ${liveHomeIsUs ? "vs" : "at"} ${text(them ? US.name : LIVE_THEM.name)}`, line: `${category}: ${Object.entries(hit.stats).map(([k, v]) => `${k} ${text(v)}`).join(", ")}` });
  }
  const history = (sample.rosterHistory?.[playerId] || []).map((row) => ({ year: String(row.year ?? DASH), team: row.team, classYear: row.classYear, position: row.position, number: row.number }));
  return {
    player: { name: entry.name || name, number: entry.number, position: entry.position, classYear: entry.classYear, height: entry.height, weight: entry.weight, hometown: entry.hometown, highSchool: entry.highSchool, stars: entry.stars, rating: entry.rating, recruitRank: entry.recruitRank, headshotUrl: null },
    seasons,
    gameLog,
    history,
    them,
  };
}

function openCard(name, playerId, them = false) {
  openPlayerCard(cardProps(name, playerId, them));
}

function profileRows(team, side) {
  return ((profiles[team] || sample.profile || {}).rows || []).filter((row) => !side || row.side === side || row.side === "both");
}

function profileRow(team, key) {
  return ((profiles[team] || {}).rows || []).find((row) => row.key === key) || null;
}

function tickerGames() {
  return (sample.schedule || []).filter((g) => g.completed).map((g) => ({
    away: { abbr: g.homeAway === "away" ? US.abbr : g.opponent?.abbreviation, points: g.homeAway === "away" ? g.usPoints : g.themPoints },
    home: { abbr: g.homeAway === "away" ? g.opponent?.abbreviation : US.abbr, points: g.homeAway === "away" ? g.themPoints : g.usPoints },
    status: "final",
  }));
}

// --- sections ------------------------------------------------------------------------------------

function tokensSection() {
  const colors = [
    ["--ground", "app background"], ["--panel", "section background"], ["--panel-raised", "current drive, active row"], ["--rule", "grid lines"], ["--rule-strong", "band separators"],
    ["--chalk", "primary text"], ["--fog", "secondary text"], ["--mist", "tertiary text"], ["--team-accent", "accent: active tab, primary buttons"], ["--team-us", "ours: rows, bars, our band heads"], ["--team-primary", "our color as a fill"],
    ["--opp", `${text(liveThem?.school)} at runtime`], ["--good", "status good, top-quartile rank"], ["--stale", "status stale, mid rank"], ["--bad", "status bad, bottom-quartile rank"], ["--replay", "replay badge"],
  ];
  const styles = getComputedStyle(document.documentElement);
  const swatches = colors.map(([token, use]) => {
    const value = styles.getPropertyValue(token).trim();
    return el("div", { class: "sw" }, el("div", { class: "sw__chip", style: { background: `var(${token})` } }), el("div", { class: "sw__meta" }, el("b", {}, token), `${value.toUpperCase()} · ${use}`));
  });
  const specs = [
    ["Display 44", "cond", "44px", "700", "5d 21h 04m"],
    ["Strip score 28", "cond", "28px", "700", "SWT 44 · AUB 39"],
    ["Strip 22", "cond", "22px", "600", "Q4 2:31 · AUB ball 3rd & 7 at SWT 41"],
    ["H1 26", "cond", "26px", "700", "Diner Tech at Swampwater Tech"],
    ["Stat 20", "cond", "20px", "600", "721  458  246  7.97"],
    ["Body 16", "body", "16px", "400", "Hamilton pass complete to Brooks III for 41 yards, touchdown."],
    ["Label 14", "body", "14px", "500", "Third down · Yards per play · Time of possession"],
    ["Caption 13", "body", "13px", "400", "Updated 4 min ago. Retrying."],
  ];
  const opp = applyOpponentColors(liveThem);
  return section(
    "tokens",
    "Tokens and type",
    "Locked dark theme, unchanged on 2026-09-21. Barlow Condensed for every numeral and heading, Barlow for body. Tabular figures on. The opponent color comes from CFBD at runtime and is checked against the panel.",
    el("div", { class: "sg__swatches" }, swatches),
    label(`Opponent color check for ${text(liveThem?.school)} (${text(liveThem?.color)}, alternate ${text(liveThem?.altColor)}): using ${opp.color}, ${contrastRatio(opp.color, "#1C1F26").toFixed(1)}:1 against the panel; text on it is ${opp.textColor === "#ECEEF2" ? "chalk" : "the ground color"}.${opp.notes.length ? ` ${opp.notes.join("; ")}.` : ""}`),
    label("Rank chips by quartile of 136 FBS teams: green top quarter, yellow middle, red bottom quarter. The number always carries the meaning."),
    el("div", { class: "sg__row" }, [1, 12, 34, 35, 68, 102, 103, 136].map((rank) => rankChip(rank, 136)), rankChip(4, null)),
    el(
      "div",
      { class: "sg__type" },
      specs.map(([name, face, size, weight, sampleText]) =>
        el(
          "div",
          { class: "spec" },
          el("div", { class: "spec__meta" }, name, el("br"), `${face === "cond" ? "Barlow Condensed" : "Barlow"} ${weight}`),
          el("div", { class: `spec__sample${face === "cond" ? " cond" : ""}`, style: { fontSize: size, fontWeight: weight } }, sampleText),
        ),
      ),
    ),
  );
}

function shellSection() {
  const demo = shell({ current: "live", status: { kind: "live", label: "Live" } });
  demo.main.append(el("p", { class: "note" }, "The base screen: the view goes here. Newspaper, Season, Game program, and Live sheet are the views; the Newspaper tab shows inline from 900 px, the others from 700 px. The Menu holds everything else."));
  demo.setRadio({ station: "the station 98.1", state: "playing", detail: "Mudpuppies radio network", note: "Audio cannot be delayed", onToggle: () => {}, onClose: () => demo.setRadio(null) });
  const inlineDrawer = shell({ current: "program", status: { kind: "delayed", label: "Delayed 45 s" } });
  inlineDrawer.openDrawer();
  return section(
    "shell",
    "Shell and menu",
    "Top bar with the wordmark, inline tabs on wide screens, the status pill, and the Menu. The radio mini-bar stays pinned while audio plays. Everything reachable from the menu is a component you open, not a tab.",
    el("div", { class: "sg__frame" }, demo.root),
    label("Menu drawer, open"),
    el("div", { class: "sg__frame sg__inline-drawer" }, inlineDrawer.root),
    label("Radio panel, opened from the menu"),
    el("div", { class: "sg__frame" }, radioPanel({ sources: [{ id: "station", name: "the station web player", kind: "embed" }, { id: "tunein", name: "TuneIn", kind: "embed" }, { id: "site", name: "the station listen live page", kind: "link" }], currentId: "station", note: "Sources are tried in this order. The spoiler delay applies to data only." })),
    label("Radio mini-bar states"),
    el("div", { class: "sg__stack" }, ["playing", "paused", "connecting", "error"].map((state) => el("div", { class: "sg__frame" }, radioBar({ station: "the station 98.1", state, detail: state === "error" ? "the web player refused to load, try TuneIn" : "Mudpuppies radio network" })))),
  );
}

function stripSection() {
  const base = { us: { abbr: US.abbr, timeouts: 2 }, them: { abbr: LIVE_THEM.abbr, timeouts: 1 } };
  const liveProps = { ...base, us: { ...base.us, points: 44 }, them: { ...base.them, points: 39 }, status: "live", period: 4, clock: { minutes: 2, seconds: 31 }, possession: "them", down: 3, distance: 7, yardsToGoal: 41, pill: { kind: "delayed", label: "Delayed 45 s" } };
  return section(
    "strip",
    "Score strip",
    "One line tall on wide screens, two on a phone. Score, period and clock, possession and down, timeouts, and the connection pill. Sticky under the top bar.",
    el("div", { class: "sg__stack" }, [
      el("div", { class: "sg__frame" }, strip({ ...liveProps, sticky: false })),
      el("div", { class: "sg__frame" }, strip({ ...base, us: { abbr: US.abbr, points: null }, them: { abbr: opponent.abbreviation || "DINR", points: null }, status: "pre", kickoffText: `Kickoff ${fmtDate(program.date)}`, pill: { kind: "quiet", label: "Pregame" }, sticky: false })),
      el("div", { class: "sg__frame" }, strip({ ...liveProps, status: "final", pill: { kind: "live", label: "Live" }, sticky: false })),
      el("div", { class: "sg__frame" }, strip({ ...liveProps, pill: { kind: "stale", label: "Stale 2 min" }, sticky: false })),
      el("div", { class: "sg__frame" }, strip({ ...liveProps, pill: { kind: "offline", label: "Offline" }, sticky: false })),
      el("div", { class: "sg__frame" }, strip({ ...liveProps, pill: { kind: "replay", label: "Replay 30x" }, sticky: false })),
    ]),
  );
}

// --- the live sheet as a remote control -------------------------------------------------------------

function liveLeaders() {
  const categories = [["passing", "Passing"], ["rushing", "Rushing"], ["receiving", "Receiving"], ["defensive", "Defense"]];
  return categories.map(([id, title]) => {
    const us = boxLeader(id, live.playerStats?.[US.name]?.[id]);
    const them = boxLeader(id, live.playerStats?.[LIVE_THEM.name]?.[id]);
    const entry = us ? rosterEntry(us.playerId) : null;
    return {
      id,
      label: title,
      us: us ? { ...us, number: entry?.number, position: entry?.position } : null,
      them: them ? { ...them, number: null, position: null } : null,
    };
  });
}

function lastScrimmagePlay() {
  return (live.plays || []).find((p) => typeof p.success === "boolean") || null;
}

function liveSheetBody() {
  const usBox = live.box?.[US.name] || {};
  const themBox = live.box?.[LIVE_THEM.name] || {};
  const usPre = isNum(live.winProbability?.[0]?.homeWp) ? (liveHomeIsUs ? live.winProbability[0].homeWp : 1 - live.winProbability[0].homeWp) : null;
  const lastPlay = lastScrimmagePlay();
  const sheet = el("div", { class: "sheet sheet--live sheet--remote" });
  sheet.append(
    band({ id: "sg-score", title: "Score by quarter", kind: "neutral", area: "score", summary: live.final ? "Final" : "", collapsible: false, body: () => quarterLine({ us: { abbr: US.abbr, scores: liveHomeIsUs ? live.lineScores?.home : live.lineScores?.away, total: liveUs?.points }, them: { abbr: LIVE_THEM.abbr, scores: liveHomeIsUs ? live.lineScores?.away : live.lineScores?.home, total: liveThem?.points } }) }),
    band({ id: "sg-stats", title: "Team stats", kind: "neutral", area: "stats", summary: `${text(usBox.totalYards)} to ${text(themBox.totalYards)} yds`, body: () => teamStatsTable({ us: { abbr: US.abbr, box: usBox }, them: { abbr: LIVE_THEM.abbr, box: themBox } }) }),
    band({
      id: "sg-wp",
      title: "Win probability",
      kind: "neutral",
      area: "wp",
      summary: lastPlay ? `Last play: ${lastPlay.success ? "success" : "failed"}` : "",
      body: () =>
        el(
          "div",
          {},
          winProbabilityChart({ series: live.winProbability, homeIsUs: liveHomeIsUs, usAbbr: US.abbr, pregame: usPre, final: live.final }),
          successRow({ play: lastPlay, offenseAbbr: lastPlay?.offense === US.name ? US.abbr : LIVE_THEM.abbr, us: { abbr: US.abbr, rate: usBox.successRate, counts: usBox.successCounts }, them: { abbr: LIVE_THEM.abbr, rate: themBox.successRate, counts: themBox.successCounts } }),
        ),
    }),
    band({ id: "sg-leaders", title: "Leaders", kind: "neutral", area: "leaders", summary: "tap a player for the card", body: () => leadersGrid({ categories: liveLeaders(), usAbbr: US.abbr, themAbbr: LIVE_THEM.abbr, onTap: (player, side) => openCard(player.name, player.playerId, side === "them") }) }),
  );
  return sheet;
}

function remoteItems() {
  const usBox = live.box?.[US.name] || {};
  const themBox = live.box?.[LIVE_THEM.name] || {};
  const realDrives = (live.drives || []).filter((d) => !/^END OF/i.test(String(d.result || "")));
  const currentDrive = realDrives[realDrives.length - 1] || null;
  const visitors = sample.recruiting?.visitors || {};
  return [
    { id: "box", label: "Box score", hint: "both teams", body: () => [band({ title: "Mudpuppies", kind: "us", collapsible: false, body: () => boxTables(US.name) }), band({ title: text(LIVE_THEM.name), kind: "them", collapsible: false, body: () => boxTables(LIVE_THEM.name) })] },
    { id: "drives", label: "Drives", hint: `${realDrives.length} drives`, body: () => band({ title: "Drives", collapsible: false, body: () => driveList({ drives: live.drives || [], us: US, them: LIVE_THEM, currentId: currentDrive?.id || null }) }) },
    { id: "plays", label: "Plays", hint: `${text(live.plays?.length)} plays`, body: () => band({ title: "Play by play", collapsible: false, body: () => playLog({ plays: [...(live.plays || [])], us: US, them: LIVE_THEM, maxHeight: 9999 }) }) },
    { id: "situation", label: "Situation", hint: `3rd ${text(usBox.thirdDown?.made)}-${text(usBox.thirdDown?.of)}`, body: () => band({ title: "Situation", collapsible: false, body: () => situationGrid({ us: { abbr: US.abbr, box: usBox }, them: { abbr: LIVE_THEM.abbr, box: themBox } }) }) },
    { id: "edges", label: "Edges", hint: "season ranks", body: () => band({ title: "Matchup edges", collapsible: false, body: () => edgesTable() }) },
    { id: "weather", label: "Weather", hint: "game site", body: () => band({ title: "Weather", collapsible: false, body: () => weatherRow({ kickoffText: fmtTime(live.date), note: "No forecast recorded. The National Weather Service forecast for the venue arrives in Phase 5." }) }) },
    { id: "visitors", label: "Visitors", hint: "recruits", body: () => band({ title: "Recruits on hand", collapsible: false, body: () => visitorsBlock(visitors) }) },
    { id: "injuries", label: "Injuries", hint: "availability", body: () => band({ title: "Availability report", collapsible: false, body: () => note("No availability report for this game yet. The pre-game task reads the BB availability report on Wednesday, Thursday, and game day.") }) },
    { id: "ticker", label: "Scores", hint: "every FBS game", body: () => band({ title: "Around the country", collapsible: false, body: () => ticker({ games: tickerGames(), id: "sg-sheet" }) }) },
  ];
}

function edgesTable() {
  return statTable({ compact: true, columns: [{ key: "label", label: "Matchup", kind: "text" }, { key: "usRank", label: "SWT rank" }, { key: "themRank", label: `${text(opponent.abbreviation)} rank` }, { key: "edge", label: "Edge", format: "+0f" }], rows: program.edges || [], sort: { key: "edge", dir: "descending" } });
}

function visitorsBlock(visitors) {
  const columns = [{ key: "name", label: "Recruit", kind: "text", sub: "position" }, { key: "stars", label: "Stars" }, { key: "highSchool", label: "High school", kind: "text" }, { key: "status", label: "Status", kind: "text" }];
  const side = (title, rows) => el("div", {}, el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, title), rows.length ? statTable({ compact: true, columns, rows }) : note("No visitors listed."));
  return el("div", {}, visitors.note ? note(visitors.note) : null, el("div", { class: "twocol" }, side("Visiting Swampwater Tech", visitors.home || []), side(`Visiting ${text(opponent.school)}`, visitors.away || [])));
}

function liveSection() {
  const stripEl = strip({ us: { abbr: US.abbr, points: liveUs?.points, timeouts: 2 }, them: { abbr: LIVE_THEM.abbr, points: liveThem?.points, timeouts: 1 }, status: "final", pill: { kind: "delayed", label: "Delayed 45 s" }, sticky: false });
  const items = remoteItems();
  let open = null;
  const bar = remoteBar({
    items,
    onOpen: (id) => {
      const item = items.find((i) => i.id === id);
      if (!item) return;
      if (open) open.close();
      bar.setActive(id);
      open = openSheet({ title: item.label, body: item.body, onClose: () => { bar.setActive(null); open = null; } });
    },
  });
  const sheet = liveSheetBody();
  const inlineHost = el("div", { class: "sg__inline-sheet" });
  openSheet({ title: "Box score", body: items[0].body, mount: inlineHost, inline: true });
  const usBox = live.box?.[US.name] || {};
  const themBox = live.box?.[LIVE_THEM.name] || {};
  const lastPlay = lastScrimmagePlay();
  return section(
    "live",
    "Live sheet: the remote control",
    `The week ${text(live.week)} game at ${text(LIVE_THEM.name)} (final ${text(liveUs?.points)}-${text(liveThem?.points)}). At rest the screen holds the glance stats: score by quarter, the team stats table, win probability with the last play's success, and the leaders. The pinned row at the bottom opens everything else in a side sheet without leaving the screen. Tap a button below to try it; tap any player for the card.`,
    el("div", { class: "sg__frame" }, stripEl, expandAllControl(sheet), sheet, bar),
    label("Side sheet, shown inline (the real one slides over the page): Box score with every category for both teams"),
    inlineHost,
    label("Band states"),
    states("Team stats", { skeleton: teamStatsSkeleton, emptyText: "Team stats appear after the first play.", body: () => teamStatsTable({ us: { abbr: US.abbr, box: usBox }, them: { abbr: LIVE_THEM.abbr, box: themBox }, rows: undefined }) }),
    states("Win probability", { skeleton: winProbabilitySkeleton, emptyText: "Win probability appears after kickoff. On the Free tier it arrives after the final.", body: () => el("div", {}, winProbabilityChart({ series: (live.winProbability || []).slice(0, 60), homeIsUs: liveHomeIsUs }), successRow({ play: lastPlay, offenseAbbr: US.abbr, us: { abbr: US.abbr, rate: usBox.successRate, counts: usBox.successCounts }, them: { abbr: LIVE_THEM.abbr, rate: themBox.successRate, counts: themBox.successCounts } })) }),
    states("Leaders", { skeleton: () => leadersSkeleton(2), emptyText: "Leaders appear after the first play.", body: () => leadersGrid({ categories: liveLeaders().slice(0, 2), usAbbr: US.abbr, themAbbr: LIVE_THEM.abbr }) }),
    states("Drives", { skeleton: driveListSkeleton, emptyText: "Drives appear after kickoff.", body: () => driveList({ drives: (live.drives || []).slice(0, 3), us: US, them: LIVE_THEM, currentId: null }) }),
    states("Situation", { skeleton: situationSkeleton, emptyText: "Situational stats appear after the first drive.", body: () => situationGrid({ us: { abbr: US.abbr, box: usBox }, them: { abbr: LIVE_THEM.abbr, box: themBox } }) }),
    states("Plays", { skeleton: playLogSkeleton, emptyText: "Plays appear after kickoff.", body: () => playLog({ plays: (live.plays || []).slice(0, 5), us: US, them: LIVE_THEM, maxHeight: 240 }) }),
  );
}

function tableSection() {
  const board = sample.leaders?.["passing:YDS"] || { team: [] };
  const rows = (board.team || []).map((row) => ({ ...row, ...row.detail }));
  const columns = [
    { key: "player", label: "Passing", kind: "text", sub: "position" },
    { key: "value", label: "Yds", rank: { key: "conferenceRank", of: board.team?.[0]?.conferenceOf } },
    { key: "COMPLETIONS", label: "Cmp" },
    { key: "ATT", label: "Att" },
    { key: "TD", label: "TD" },
    { key: "INT", label: "Int" },
    { key: "YPA", label: "Y/A", format: "1f" },
  ];
  const rosterColumns = [
    { key: "number", label: "No." },
    { key: "name", label: "Player", kind: "text" },
    { key: "position", label: "Pos", kind: "text" },
    { key: "classYear", label: "Class", kind: "text" },
    { key: "height", label: "Ht", kind: "text", sortable: false },
    { key: "weight", label: "Wt" },
    { key: "hometown", label: "Hometown", kind: "text" },
    { key: "highSchool", label: "High school", kind: "text" },
    { key: "stars", label: "Stars" },
  ];
  return section(
    "table",
    "Stat table and roster",
    "Sticky header, tap a header to sort, rank chips beside numbers, row tap opens the player card. The roster page is the same component with text columns; high school and stars fill in for players with a recruiting record.",
    label("Mudpuppies passing leaders with BB rank chips"),
    statTable({ columns, rows, sort: { key: "value", dir: "descending" }, onRowTap: (row) => openCard(row.player, row.playerId), caption: "Passing leaders" }),
    label(`Roster, ${text(sample.roster?.length)} players, sortable, 320 px tall`),
    statTable({ columns: rosterColumns, rows: sample.roster || [], sort: { key: "number", dir: "ascending" }, compact: true, maxHeight: 320, onRowTap: (row) => openCard(row.name, row.playerId), caption: "Roster" }),
    states("Passing leaders", { kind: "us", skeleton: () => statTableSkeleton(5), emptyText: "Leaders appear after the first game.", body: () => statTable({ columns, rows: rows.slice(0, 3), compact: true }) }),
  );
}

function cardSection() {
  const lead = sample.leaders?.["passing:YDS"]?.team?.[0];
  const props = lead ? cardProps(lead.player, lead.playerId) : { player: { name: DASH } };
  const recruit = (sample.roster || []).find((p) => p.highSchool && p.stars);
  const recruitProps = recruit ? cardProps(recruit.name, recruit.playerId) : null;
  return section(
    "card",
    "Player card",
    "Slide-over from any player name, 600 px wide from 700 px up. Close, the name and the tabs stay on an opaque bar while the card scrolls. A 96 px headshot on navy when one loads, the number badge otherwise; a thin orange edge for Swampwater Tech, --opp for others; the team is a link in the bio line. Stars read as five drawn stars, then '94 · #123 nat'. Stats (season by season with a career row, a sparkline beside each heading once two games are in), Game log (Wk | Opp | Result | stats), Play value, History. While it loads: skeleton bars, never an empty-state sentence, and the answer fills the same card in place.",
    el("div", { class: "sg__row" }, el("button", { class: "btn btn--primary", type: "button", onclick: () => openPlayerCard(props) }, "Open as slide-over"), el("button", { class: "btn", type: "button", onclick: () => { const close = openPlayerCard({ player: props.player, loading: true }); setTimeout(() => close.update(props), 1200); } }, "Open loading, fill after 1.2 s")),
    label("Inline: loading (name and number from the tapped row, skeleton bars)"),
    playerCard({ player: props.player, loading: true, inline: true }),
    label("Inline: the passing leader, number badge fallback, one recorded season"),
    playerCard({ ...props, inline: true }),
    label("Inline: the Stats heading with its sparkline (stand-in values: Swampwater Tech's points by game from the sample trends)"),
    playerCard({ ...props, seasons: props.seasons ? { ...props.seasons, title: "Passing", trend: { values: sample.trends?.points || [], label: "pass yds", format: "0f" } } : null, inline: true }),
    recruitProps ? label("Inline: a freshman with a recruiting record, so high school, stars, and rating fill in") : null,
    recruitProps ? playerCard({ ...recruitProps, inline: true }) : null,
    label("Inline: opponent player with no stats yet"),
    playerCard({ player: { name: "Cole Webb", number: 11, position: "QB", classYear: "SR" }, seasonStats: [], gameLog: [], them: true, inline: true }),
  );
}

function compareSection() {
  const rows = (program.taleOfTheTape || []).map((row) => ({
    label: row.label,
    usText: fmtStat(row.us?.value, row.format),
    usRank: row.us?.nationalRank,
    usOf: row.us?.nationalOf,
    themText: fmtStat(row.them?.value, row.format),
    themRank: row.them?.nationalRank,
    themOf: row.them?.nationalOf,
  }));
  const columns = [
    { key: "label", label: "Statistic", kind: "text", sortable: false },
    { key: "usText", label: US.abbr, kind: "text", sortable: false },
    { key: "usRank", label: "FBS rank", kind: "rank", of: "usOf" },
    { key: "themText", label: text(opponent.abbreviation), kind: "text", sortable: false },
    { key: "themRank", label: "FBS rank", kind: "rank", of: "themOf" },
  ];
  return section(
    "compare",
    "Two-team table",
    `Tale of the tape, Swampwater Tech and ${text(opponent.school)}, a national rank chip beside every number. Owner direction 2026-09-23: no graphics that span a page, so this table replaced the comparison bar and the bar chart.`,
    el("div", { class: "band" }, statTable({ compact: true, columns, rows, caption: "Tale of the tape" })),
    label("Biggest edges, rank difference"),
    el("div", { class: "band" }, edgesTable()),
    states("Tale of the tape", { skeleton: () => statTableSkeleton(5), emptyText: "Comparison appears once both teams have played.", body: () => statTable({ compact: true, columns, rows: rows.slice(0, 3) }) }),
  );
}

function trendSection() {
  const trends = sample.trends || {};
  return section(
    "trends",
    "Trend sparkline",
    "Last N games, current value labelled. Orange is Swampwater Tech, the opponent line uses the opponent's color.",
    el("div", { class: "band" }, trendRow({ label: "Points scored", values: trends.points || [] }), trendRow({ label: "Points allowed", values: trends.pointsAllowed || [], them: true })),
    states("Trends", { skeleton: trendSkeleton, emptyText: "Trends appear after two games.", body: () => el("div", {}, trendRow({ label: "Points scored", values: trends.points || [] })) }),
  );
}

function pillSection() {
  return section(
    "pills",
    "Status pills and key-play badges",
    "Distinct from both team colors and never color alone: each pill carries a word and a shape, each badge a glyph and a label.",
    el("div", { class: "sg__row" }, [["live", "Live"], ["delayed", "Delayed 45 s"], ["stale", "Stale 4 min"], ["offline", "Offline"], ["replay", "Replay 30x"], ["quiet", "Connecting"]].map(([kind, txt]) => pill({ kind, label: txt }))),
    label("Tap-size pills for the strip"),
    el("div", { class: "sg__row" }, [["live", "Live"], ["delayed", "Delayed 45 s"]].map(([kind, txt]) => pill({ kind, label: txt, tap: true }))),
    label("Key-play badges"),
    el("div", { class: "sg__row" }, Object.keys(KEY_PLAYS).map((flag) => keyPlayBadge(flag))),
  );
}

function tickerSection() {
  return section(
    "ticker",
    "Ticker",
    "Every other FBS game, scores only, collapsible. Shown here with Swampwater Tech's results because the scoreboard needs a paid tier. On the live sheet it lives behind the Scores button.",
    ticker({ games: tickerGames(), id: "sg-demo" }),
    label("Empty"),
    ticker({ games: [], id: "sg-empty" }),
  );
}

function sliderSection() {
  const readout = el("p", { class: "note" }, "Every live panel follows this value.");
  return section(
    "slider",
    "Delay slider",
    "0 to 120 seconds in steps of 5, with nudge buttons so the tablet never needs a precise drag. Saved on the device.",
    el("div", { class: "band" }, delaySlider({ value: 45, onChange: (v) => { readout.textContent = `Delay set to ${v} s. Every live panel follows this value.`; } }), readout),
  );
}

function editorialSection() {
  const line = program.line || {};
  const move = isNum(line.spread) && isNum(line.spreadOpen) ? `The line opened Swampwater Tech ${fmtStat(line.spreadOpen, "+1f")} and now sits at ${text(line.formatted)}. The total moved from ${fmtNum(line.overUnderOpen, 1)} to ${fmtNum(line.overUnder, 1)}.` : "No line movement to report.";
  const body = () =>
    editorial({
      byline: { author: "Claude (pre-game task)", writtenAt: "2026-09-24T22:00:00Z" },
      sources: [{ label: "Lines recorded 2026-09-20" }, { label: "BB availability report (not yet configured)" }],
      sections: [
        { heading: "Line movement", paragraphs: [move] },
        { heading: "Pregame win probability", paragraphs: [`CFBD's model gives Swampwater Tech ${fmtPct(program.pregame?.homeWinProbability)} at home against ${text(opponent.school)}.`] },
      ],
    });
  return section(
    "editorial",
    "Editorial block, injury report, and a stat grade",
    "Content a scheduled Claude task writes into the data folder before each game: injuries, visitors, coaching matchup, schemes. Always shows who wrote it, when, and the sources. Until a source is configured it says so.",
    el("div", { class: "band" }, el("div", { class: "band__head" }, el("h2", { class: "band__title" }, "Program notes")), body()),
    label("Injury report, empty until a source is configured"),
    el("div", { class: "band" }, el("div", { class: "band__head" }, el("h2", { class: "band__title" }, "Availability report")), note("No availability report for this game yet. The pre-game task reads the BB availability report on Wednesday, Thursday, and game day.")),
    label("Injury report, filled (example rows to show the statuses)"),
    el("div", { class: "band" }, el("div", { class: "band__head" }, el("h2", { class: "band__title" }, "Availability report")), availabilityTable({ rows: [
      { name: "Example player A", position: "WR", status: "Out", note: "example row" },
      { name: "Example player B", position: "OL", status: "Questionable", note: "example row" },
      { name: "Example player C", position: "CB", status: "Probable", note: "example row" },
    ], source: "example", updatedAt: "2026-09-25T15:00:00Z" })),
    label("Settings field for Pro Football Focus grades (X8). Disabled until a verified API exists; the grade column stays hidden."),
    el("div", { class: "band" }, gradeBlock({ grade: 76, label: "Very good", rank: 20, of: 144, groupName: "quarterbacks", basis: "efficiency", volume: { label: "passes a game", perGame: 31.4, needed: 14 }, components: [{ label: "Yards per attempt", value: 9.05, format: "1f", percentile: 73.3, weight: 0.2 }, { label: "Play value per pass (PPA)", value: 0.348, format: "2f", percentile: 82.3, weight: 0.25 }, { label: "Interception rate", value: 0.026, format: "pct", percentile: 45.8, weight: 0.15 }, { label: "Opponent-adjusted passing value", value: null, format: "2f", percentile: null, weight: 0.1 }] }), el("p", {}, "Roster chips: ", gradeChip({ grade: 93, label: "Elite" }), " ", gradeChip({ grade: 64 }), " ", gradeChip({ grade: 31 }), " ", gradeChip({ grade: null, reason: "Not enough plays to grade" })), el("div", { class: "form-field" }, el("label", { for: "sg-notes-command" }, "Notes command"), el("input", { id: "sg-notes-command", type: "text", disabled: true, placeholder: "claude" }), el("div", { class: "form-field__help" }, "A form field: .form-field, never .field, which belongs to the drive strip."))),
    states("Program notes", { skeleton: editorialSkeleton, emptyText: "Not written yet. The pre-game task runs on Thursday.", body }),
  );
}

function coverSection() {
  return section(
    "cover",
    "Program cover",
    "The matchup as the hero, kickoff in local time, venue, TV, countdown, line, win probability. The one place with an entrance animation.",
    cover({ ...program, reveal: true }),
    label("Past game"),
    cover({ ...program, state: "final", kicker: `Week ${text(live.week)} program`, them: { ...liveThem, record: null }, homeIsUs: false, date: live.date, venue: live.venue, tv: "ESPN", line: {}, pregame: {} }),
  );
}

function seasonSection() {
  const profile = sample.profile || { rows: [] };
  const rows = (profile.rows || []).map((row) => ({ ...row, valueText: fmtStat(row.value, row.format) }));
  const columns = [
    { key: "label", label: "Stat", kind: "text" },
    { key: "valueText", label: US.abbr, kind: "text", sortable: false },
    { key: "nationalRank", label: "FBS rank", kind: "rank", of: "nationalOf" },
    { key: "conferenceRank", label: "BB", kind: "rank", of: "conferenceOf" },
  ];
  const nextGame = (sample.schedule || []).find((g) => !g.completed);
  const scopeButtons = ["Mudpuppies", `vs ${text(opponent.school)}`, "BB", "National"].map((labelText, index) => el("button", { type: "button", "aria-pressed": index === 0 ? "true" : "false" }, labelText));
  const leadersBody = el("div", {});
  function renderLeaders(scope) {
    leadersBody.replaceChildren();
    for (const [key, board] of Object.entries(sample.leaders || {})) {
      if (scope === 0) {
        leadersBody.append(statTable({ compact: true, columns: [{ key: "player", label: board.label, kind: "text", sub: "position" }, { key: "value", label: key.split(":")[1], rank: { key: "conferenceRank", of: "conferenceOf" } }], rows: (board.team || []).slice(0, 3), onRowTap: (row) => openCard(row.player, row.playerId) }));
      } else if (scope === 2) {
        leadersBody.append(statTable({ compact: true, columns: [{ key: "player", label: `${board.label}, BB top 10`, kind: "text", sub: "team" }, { key: "value", label: key.split(":")[1] }], rows: (board.conferenceTop || []).map((r, i) => ({ ...r, rank: i + 1 })), rowClass: (row) => (row.team === US.name ? "is-us" : null) }));
      } else if (scope === 3) {
        if ((board.nationalTop || []).length) leadersBody.append(statTable({ compact: true, columns: [{ key: "player", label: `${board.label}, national top 10`, kind: "text", sub: "team" }, { key: "value", label: key.split(":")[1] }], rows: board.nationalTop, rowClass: (row) => (row.team === US.name ? "is-us" : null) }));
      } else {
        const pair = (program.leadersSideBySide || []).find((p) => p.label === board.label);
        if (pair) leadersBody.append(statTable({ compact: true, columns: [{ key: "side", label: board.label, kind: "text" }, { key: "player", label: "Player", kind: "text", sub: "position" }, { key: "value", label: key.split(":")[1] }], rows: [{ side: US.abbr, ...(pair.us || {}) }, { side: text(opponent.abbreviation), ...(pair.them || {}) }] }));
      }
    }
    if (scope === 3 && !leadersBody.children.length) leadersBody.append(note("National boards for rushing and receiving need one bulk pull per category. Only passing is recorded so far."));
  }
  scopeButtons.forEach((button, index) => button.addEventListener("click", () => { scopeButtons.forEach((b, i) => b.setAttribute("aria-pressed", i === index ? "true" : "false")); renderLeaders(index); }));
  renderLeaders(0);

  return section(
    "season",
    "Season",
    "The media guide: schedule rail, stat profile with a rank beside every number, leaders with the scope switch. Three columns from 1100 px, one column below.",
    el(
      "div",
      { class: "season", style: { padding: "0" } },
      band({ id: "sg-sched", title: "Schedule", collapsible: false, body: () => el("div", {}, recordLine({ ...(sample.record || {}), apRank: program.us?.apRank, coachesRank: program.us?.coachesRank, spRank: program.us?.sp?.rank }), scheduleList({ games: sample.schedule || [], nextGameId: nextGame?.gameId || null, onSelect: () => {} })) }),
      band({ id: "sg-profile", title: "Stat profile", collapsible: false, body: () => el("div", {}, statTable({ columns, rows, compact: true, sort: { key: "nationalRank", dir: "ascending" } }), trendRow({ label: "Points scored", values: sample.trends?.points || [] }), trendRow({ label: "Points allowed", values: sample.trends?.pointsAllowed || [], them: true })) }),
      band({ id: "sg-leaders-season", title: "Leaders", collapsible: false, tools: el("div", { class: "seg", role: "group", "aria-label": "Scope" }, scopeButtons), body: () => leadersBody }),
    ),
    states("Schedule", { skeleton: scheduleSkeleton, emptyText: "The schedule loads the first time the app opens.", body: () => scheduleList({ games: (sample.schedule || []).slice(0, 4) }) }),
  );
}

// --- program: matchup card, weather, spreads --------------------------------------------------------

function opponentMatchupCard() {
  const tags = [];
  if (program.week) tags.push({ label: `Week ${program.week}` });
  if (isNum(opponent.sp?.rank)) tags.push({ label: `SP+ #${opponent.sp.rank}` });
  if (program.line?.formatted) tags.push({ label: program.line.formatted, kind: "us" });
  const keys = [["offense", "ypg", "Yards per game"], ["offense", "pass_ypg", "Pass yards per game"], ["offense", "rush_ypg", "Rush yards per game"], ["offense", "ypp", "Yards per play"], ["offense", "third", "Third down"], ["defense", "ypg_d", "Yards allowed per game"], ["defense", "pass_ypg_d", "Pass yards allowed per game"], ["defense", "rush_ypg_d", "Rush yards allowed per game"], ["defense", "ypp_d", "Yards allowed per play"], ["defense", "third_d", "Third down allowed"]];
  const rows = keys.map(([side, key, labelText]) => {
    const u = profileRow(US.name, key) || {};
    const t = profileRow(opponent.school, key) || {};
    return { label: labelText, side, format: u.format || t.format, higherIsBetter: u.higherIsBetter, us: { value: u.value, rank: u.nationalRank, of: u.nationalOf }, them: { value: t.value, rank: t.nationalRank, of: t.nationalOf } };
  });
  return matchupCard({
    us: { abbreviation: US.abbr, school: US.name },
    them: opponent,
    tags,
    schemes: { offense: "Spread, 11 personnel (example)", defense: "4-2-5 (example)", source: "example" },
    rows,
    foot: weatherRow({ kickoffText: program.startTimeTbd ? "Time TBD" : fmtTime(program.date), note: "No forecast recorded. The National Weather Service forecast for the venue arrives in Phase 5." }),
  });
}

function programSection() {
  const series = program.series || {};
  const tendencies = program.tendencies || { rows: [] };
  const tRows = (tendencies.rows || []).map((row) => ({ split: row.split.replace("down:", "Down ").replace("dist:", "Distance "), run: row.run, pass: row.pass, runRate: row.runRate }));
  return section(
    "program",
    "Program spreads and the matchup card",
    "The matchup card is the opponent at a glance: offense and defense with a rank chip under every value, a weather row at the foot. Then series history and opponent tendencies. Tendencies here use Silver Dollar's plays from week 3 because only that game is recorded.",
    el("div", { class: "spread spread--2" }, opponentMatchupCard(), el("div", { class: "sg__stack" }, el("div", { class: "band" }, el("div", { class: "band__head" }, el("h2", { class: "band__title" }, "Weather row, with a forecast (example values)")), el("div", { style: { padding: "12px" } }, weatherRow({ kickoffText: "3:30 PM", tempF: 84, windMph: 9, windDir: "SE", sky: "Partly cloudy", precipChance: 20, source: "National Weather Service, example" }))), el("div", { class: "band" }, el("div", { class: "band__head" }, el("h2", { class: "band__title" }, "Weather row, indoors (example)")), el("div", { style: { padding: "12px" } }, weatherRow({ kickoffText: "7:00 PM", tempF: 70, windMph: 0, indoors: true, source: "example" }))))),
    el(
      "div",
      { class: "spread spread--2", style: { marginTop: "12px" } },
      band({ id: "sg-series", title: "Series", collapsible: false, summary: `${text(series.team1)} ${text(series.team1Wins)}, ${text(series.team2)} ${text(series.team2Wins)}, ${text(series.ties)} tie`, body: () => el("div", {}, series.streak ? note(`${text(series.streak.team)} has won ${text(series.streak.games)} straight.`) : null, statTable({ compact: true, columns: [{ key: "season", label: "Year", kind: "text", sortable: false }, { key: "matchup", label: "Game", kind: "text", sortable: false }, { key: "score", label: "Score", kind: "text", sortable: false }, { key: "winner", label: "Winner", kind: "text", sortable: false }], rows: (series.lastTen || []).map((g) => ({ season: String(g.season ?? "–"), matchup: `${text(g.awayTeam)} at ${text(g.homeTeam)}`, score: `${text(g.awayScore)}-${text(g.homeScore)}`, winner: g.winner })) })) }),
      band({ id: "sg-tend", title: `${text(tendencies.offense)} tendencies`, collapsible: false, summary: tendencies.source, body: () => statTable({ compact: true, columns: [{ key: "split", label: "Split", kind: "text", sortable: false }, { key: "run", label: "Run" }, { key: "pass", label: "Pass" }, { key: "runRate", label: "Run rate", format: "pct" }], rows: tRows }) }),
    ),
    states("Matchup card", { skeleton: () => el("div", {}, el("div", { class: "skel skel--block" }), el("div", { class: "skel skel--block" })), emptyText: "The card fills once the opponent has played a game.", body: () => opponentMatchupCard() }),
  );
}

// --- team page ---------------------------------------------------------------------------------------

function seriesTable() {
  const series = program.series || {};
  return statTable({ compact: true, columns: [{ key: "season", label: "Year", kind: "text", sortable: false }, { key: "matchup", label: "Game", kind: "text", sortable: false }, { key: "score", label: "Score", kind: "text", sortable: false }, { key: "winner", label: "Winner", kind: "text", sortable: false }], rows: (series.lastTen || []).map((g) => ({ season: String(g.season ?? "–"), matchup: `${text(g.awayTeam)} at ${text(g.homeTeam)}`, score: `${text(g.awayScore)}-${text(g.homeScore)}`, winner: g.winner })) });
}

function valueRankTable(team, side, caption) {
  const rows = profileRows(team, side).map((row) => ({ ...row, valueText: fmtStat(row.value, row.format) }));
  return statTable({ compact: true, caption, columns: [{ key: "label", label: "Statistic", kind: "text", sortable: false }, { key: "valueText", label: "Value", kind: "text", sortable: false }, { key: "nationalRank", label: "Rank", kind: "rank", of: "nationalOf" }], rows });
}

function teamSummary(team, other) {
  const pick = (t, key) => profileRow(t, key);
  const tileItems = [["ypp", "Yards per play"], ["ypg", "Yards per game"], ["ypg_d", "Yards allowed per game"], ["ypp_d", "Yards allowed per play"]].map(([key, labelText]) => {
    const row = pick(team, key);
    return { label: labelText, value: row?.value, format: row?.format, rank: row?.nationalRank, of: row?.nationalOf };
  });
  const advanced = program.advanced?.[team] || {};
  return el(
    "div",
    { class: "sg__stack" },
    tiles(tileItems),
    isNum(advanced.offense?.successRate)
      ? band({ title: "Advanced", collapsible: false, body: () => statTable({ compact: true, columns: [{ key: "label", label: "Statistic", kind: "text", sortable: false }, { key: "offense", label: "Offense", format: "2f" }, { key: "defense", label: "Defense", format: "2f" }], rows: [
          { label: "Success rate", offense: advanced.offense?.successRate, defense: advanced.defense?.successRate },
          { label: "Explosiveness", offense: advanced.offense?.explosiveness, defense: advanced.defense?.explosiveness },
          { label: "PPA per play", offense: advanced.offense?.ppa, defense: advanced.defense?.ppa },
        ] }) })
      : null,
    el("div", { class: "spread spread--2" }, band({ title: "Offense", collapsible: false, body: () => valueRankTable(team, "offense", "Offense") }), band({ title: "Defense", collapsible: false, body: () => valueRankTable(team, "defense", "Defense") })),
  );
}

function impactPlayers() {
  const cards = [];
  for (const key of ["passing:YDS", "rushing:YDS", "receiving:YDS", "defensive:TOT"]) {
    const board = sample.leaders?.[key];
    const top = board?.team?.[0];
    if (!top) continue;
    const entry = rosterEntry(top.playerId) || {};
    const chips = [`${fmtNum(top.value)} ${board.label.toLowerCase()}`, ...Object.entries(top.detail || {}).slice(0, 3).map(([k, v]) => `${typeof v === "number" ? fmtNum(v, Number.isInteger(v) ? 0 : 1) : text(v)} ${k}`)];
    cards.push(impactCard({ player: { name: top.player, number: entry.number, position: top.position, classYear: entry.classYear }, chips, onTap: () => openCard(top.player, top.playerId) }));
  }
  return el("div", { class: "impact-grid" }, cards.length ? cards : note("Impact players appear after the first game."));
}

function rosterTab() {
  const roster = sample.roster || [];
  const counts = { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 };
  const rated = roster.filter((p) => isNum(p.stars));
  for (const p of rated) counts[p.stars] = (counts[p.stars] || 0) + 1;
  const average = rated.length ? rated.reduce((a, p) => a + p.stars, 0) / rated.length : null;
  const columns = [{ key: "number", label: "No." }, { key: "name", label: "Player", kind: "text" }, { key: "position", label: "Pos", kind: "text" }, { key: "classYear", label: "Class", kind: "text" }, { key: "height", label: "Ht", kind: "text", sortable: false }, { key: "weight", label: "Wt" }, { key: "hometown", label: "Hometown", kind: "text" }, { key: "highSchool", label: "High school", kind: "text" }, { key: "stars", label: "Stars" }];
  const groups = ["QB", "RB", "WR", "TE", "OL", "DL", "LB", "CB", "S", "K", "P", "LS"];
  const picker = el("select", { class: "field__select", "aria-label": "Section", style: { minHeight: "44px", padding: "0 12px", background: "var(--ground)", color: "var(--chalk)", border: "1px solid var(--rule-strong)", borderRadius: "4px", font: "inherit" } }, el("option", { value: "" }, "All positions"), groups.map((g) => el("option", { value: g }, g)));
  const tableHost = el("div", {});
  const render = () => tableHost.replaceChildren(statTable({ columns, rows: picker.value ? roster.filter((p) => p.position === picker.value) : roster, sort: { key: "number", dir: "ascending" }, compact: true, maxHeight: 420, onRowTap: (row) => openCard(row.name, row.playerId), caption: "Roster" }));
  picker.addEventListener("change", render);
  render();
  return el(
    "div",
    { class: "sg__stack" },
    starStrip({ counts: Object.fromEntries(Object.entries(counts).map(([k, v]) => [String(k), v])), average, note: `${rated.length} of ${roster.length} players have a recruiting record in the fixtures (only the ${text(sample.recruiting?.year)} class is recorded).` }),
    band({ title: "Impact players", collapsible: false, summary: "season leaders", body: impactPlayers }),
    band({ title: "Roster", collapsible: false, tools: picker, body: () => tableHost }),
  );
}

function teamSection() {
  const ourSide = program.us || {};
  const ole = opponent;
  const host = el("div", { class: "team-page", style: { padding: "0" } });
  const tabs = [{ id: "summary", label: "Summary" }, { id: "schedule", label: "Schedule" }, { id: "roster", label: "Roster" }, { id: "coaches", label: "Coaches" }, { id: "history", label: "History" }];
  const bodies = {
    summary: () => teamSummary(US.name, ole.school),
    schedule: () => band({ title: "Schedule", collapsible: false, body: () => scheduleList({ games: sample.schedule || [], nextGameId: (sample.schedule || []).find((g) => !g.completed)?.gameId || null, onSelect: () => {} }) }),
    roster: rosterTab,
    coaches: () => band({ title: "Coaches", collapsible: false, state: { status: "empty" }, emptyText: "Coaches need one CFBD call per season. Not recorded yet; arrives with the team page in Phase 3." }),
    history: () => band({ title: `Series with ${text(ole.school)}`, collapsible: false, body: seriesTable }),
  };
  const header = teamHeader({
    team: { ...ourSide, school: US.name },
    season: `${text(sample.season)} ${text(ourSide.conference)}`,
    location: "Swamp County, FL",
    facts: [["AP", isNum(ourSide.apRank) ? `#${ourSide.apRank}` : DASH], ["SP+", isNum(ourSide.sp?.rank) ? `#${ourSide.sp.rank}` : DASH], ["FPI", isNum(ourSide.fpi) ? fmtNum(ourSide.fpi, 1) : DASH]].map(([l, v]) => ({ label: l, value: v })),
    tabs,
    current: "summary",
    onTab: (id) => host.replaceChildren(bodies[id] ? bodies[id]() : note("Nothing here.")),
  });
  host.append(bodies.summary());
  const oppHeader = teamHeader({ team: ole, season: `${text(sample.season)} ${text(ole.conference)}`, location: text(program.venue), facts: [{ label: "AP", value: isNum(ole.apRank) ? `#${ole.apRank}` : DASH }, { label: "SP+", value: isNum(ole.sp?.rank) ? `#${ole.sp.rank}` : DASH }], tabs, current: "summary" });
  return section(
    "team",
    "Team page",
    "Swampwater Tech and any opponent: header with rank, record, conference, and location; tabs for Summary, Schedule, Roster, Coaches, and History. Summary is the four tiles and Statistic / Value / Rank tables. Roster has the star strip, impact players, a position picker, and the roster table. Tabs work here.",
    el("div", { class: "sg__stack" }, header.root, host),
    label(`Opponent header, ${text(ole.school)}`),
    oppHeader.root,
    label("Summary states"),
    states("Summary", { skeleton: () => statTableSkeleton(4), emptyText: "Season stats appear after the first game.", body: () => tiles([{ label: "Yards per play", value: profileRow(US.name, "ypp")?.value, format: "1f", rank: profileRow(US.name, "ypp")?.nationalRank, of: profileRow(US.name, "ypp")?.nationalOf }]) }),
    states("Impact players", { skeleton: impactSkeleton, emptyText: "Impact players appear after the first game.", body: impactPlayers }),
  );
}

// --- recruiting ------------------------------------------------------------------------------------------

function recruitingSection() {
  const rec = sample.recruiting || {};
  const columns = [
    { key: "nationalRank", label: "FBS rank", kind: "rank" },
    { key: "name", label: "Recruit", kind: "text", sub: "position" },
    { key: "stars", label: "Stars", format: "stars" },
    { key: "rating", label: "Rating", format: "rating100" },
    { key: "highSchool", label: "High school", kind: "text" },
    { key: "hometown", label: "Hometown", kind: "text" },
    { key: "height", label: "Ht", kind: "text", sortable: false },
    { key: "weight", label: "Wt" },
  ];
  const rows = (rec.commits || []).map((c) => ({ ...c, rating: c.rating }));
  return section(
    "recruiting",
    "Recruiting",
    `The ${text(rec.year)} class from CFBD: every commit with stars, rating, national rank, high school, and hometown. Next year's class and the visitors list are empty until their sources exist; the panels say so.`,
    starStrip({ counts: rec.starCounts || {}, average: rec.average, note: `${text(rows.length)} commits in the ${text(rec.year)} class.` }),
    label(`${text(rec.year)} commits`),
    statTable({ columns, rows, sort: { key: "nationalRank", dir: "ascending" }, compact: true, caption: "Commits" }),
    label("Next year's class"),
    el("div", { class: "band" }, note(rec.nextYear?.note || "Not recorded.")),
    label("Visitors this week, home and away"),
    el("div", { class: "band" }, visitorsBlock(rec.visitors || {})),
    states("Commits", { skeleton: () => statTableSkeleton(5), emptyText: "No commits recorded for this class yet.", body: () => statTable({ columns, rows: rows.slice(0, 3), compact: true }) }),
  );
}

// --- newspaper --------------------------------------------------------------------------------------------

function newspaperSection() {
  const paper = sample.newspaper || {};
  const games = (paper.slate || []).map((g) => ({ ...g, home: { ...g.home, abbreviation: g.home?.abbreviation }, away: { ...g.away } }));
  return section(
    "newspaper",
    "Newspaper",
    `Saturday morning: headlines above the day's slate, every Top 25 or BB game as a card with ranks, records, kickoff, TV, line, and pregame win probability, Mudpuppies game first. Pregame, the Mudpuppies program opens with the same headlines on top. Week ${text(paper.week)}, ${fmtDateTime(paper.date)}, from the week-wide fixtures.`,
    band({ id: "sg-news", title: "Mudpuppies news", collapsible: false, state: { status: "empty", message: paper.newsNote }, emptyText: paper.newsNote }),
    band({ id: "sg-slate", title: "Today's slate", collapsible: false, body: () => slateList({ games, usName: US.name, note: paper.slateNote }) }),
    label("Matchup preview card, one per slate game"),
    opponentMatchupCard(),
    label("Headline digest states (filled state uses example headlines to show the shape)"),
    states("Mudpuppies news", { skeleton: newsSkeleton, emptyText: paper.newsNote, body: () => newsDigest({ items: [
      { title: "Example headline from the SWT Athletics feed", url: "#", source: "SWT Athletics", publishedAt: new Date(Date.now() - 45 * 60000).toISOString() },
      { title: "Example headline from ESPN's Swampwater Tech feed", url: "#", source: "ESPN", publishedAt: new Date(Date.now() - 3 * 3600000).toISOString() },
    ] }) }),
    states("Today's slate", { skeleton: slateSkeleton, emptyText: "No Top 25 or BB games today.", body: () => slateList({ games }) }),
  );
}

// --- Phase 16 kit (stream F) -----------------------------------------------------------------------

/** The Phase 15 chip, drawn by hand for the before/after (13px/600, 36px minimum). */
function oldChip(rank, of) {
  const tone = rank <= Math.ceil(of * 0.25) ? "top" : rank > of - Math.ceil(of * 0.25) ? "bottom" : "mid";
  return el("span", { class: `rank-chip rank-chip--${tone}`, style: { fontSize: "13px", fontWeight: "600", minWidth: "36px", padding: "1px 6px", minHeight: "0", lineHeight: "normal" } }, `#${rank}`);
}

function kitSection() {
  const us = program.us || {};
  const them = program.them || {};
  const rows = (profiles[US.name]?.rows || []).slice(0, 6).map((row) => ({ ...row, metric: row.key ? `profile:${row.key}` : null }));
  if (rows[2]) rows[2] = { ...rows[2], metric: null }; // a row without a metric keeps a plain chip
  const valueColumns = [
    { key: "label", label: "Stat", kind: "text" },
    { key: "value", label: "Value", format: "1f", rank: { key: "nationalRank", of: "nationalOf", link: metricLink({ team: US.name }), placeholder: true } },
    { key: "conferenceRank", label: "BB", kind: "rank", of: "conferenceOf", link: metricLink({ team: US.name, scope: "conference" }) },
  ];
  const wide = (Array.isArray(sample.roster) ? sample.roster : []).slice(0, 14);
  const wideColumns = [
    { key: "number", label: "No.", stick: true },
    { key: "name", label: "Player", kind: "text", stick: true },
    { key: "position", label: "Pos", kind: "text" },
    { key: "classYear", label: "Class", kind: "text" },
    { key: "weight", label: "Wt" },
    { key: "hometown", label: "Hometown", kind: "text" },
    { key: "highSchool", label: "High school", kind: "text" },
    { key: "stars", label: "Stars", format: "stars" },
  ];
  const recruits = [
    { name: "Five-star", rating: 0.9912, stars: 5 },
    { name: "Four-star", rating: 0.8934, stars: 4 },
    { name: "Three-star", rating: 0.8561, stars: 3 },
    { name: "Unrated", rating: null, stars: null },
  ];
  let sheet = null;
  const openDemo = () => {
    sheet = openSheet({
      title: "National list",
      tools: el("a", { class: "btn btn--quiet", href: "#season" }, "Full page"),
      body: el("div", {}, note("A sheet slides in from the right; closing slides it out. The buttons swap its title and body in place, or open a second sheet on top."), el("div", { class: "sg__row" },
        el("button", { class: "btn", type: "button", onclick: () => { sheet.setTitle("BB list"); sheet.setBody(el("div", {}, note("Same layer, new title and body: no scrim flash."), statTableSkeleton(4, 3))); } }, "Swap in place"),
        el("button", { class: "btn", type: "button", onclick: () => openSheet({ title: "A second sheet", body: note("Stacked above the first. Escape closes this one first.") }) }, "Open another on top"),
      ), statTable({ compact: true, columns: valueColumns, rows })),
    });
  };
  const page = el("div", { class: "sg__stack" });
  const kit = section(
    "kit",
    "Phase 16 kit",
    "The shared pieces every page builds on: linked rank chips and the poll badge, press feedback, the sliding side sheet, table hooks, designed states, sub-headings, logos and faces. Tap a chip: in the app it opens its national or BB list in a side sheet.",
    label("Rank chip before (Phase 15: 13px, 36px minimum) and after (14px bold in a 44px slot, the # in fog). Same quartile colors."),
    el("div", { class: "sg__row" }, el("span", { class: "sg__label" }, "Before"), [1, 12, 35, 68, 103, 128].map((r) => oldChip(r, 136))),
    el("div", { class: "sg__row" }, el("span", { class: "sg__label" }, "After"), [1, 12, 35, 68, 103, 128].map((r) => rankChip(r, 136))),
    label("Linked chips (national list, BB list, a tie): press one or focus it with Tab to see the ring. The hit area reaches past the chip."),
    el("div", { class: "sg__row" },
      rankChip(12, 138, { href: nationalHref("advanced:defense_explosiveness", { team: US.name }), label: "Explosiveness allowed" }),
      rankChip(3, 16, { href: nationalHref("profile:ypp", { team: US.name, scope: "conference" }), label: "Yards per play" }),
      rankChip(41, 138, { href: nationalHref("profile:ppg", { team: US.name, year: 2025 }), label: "Points per game", tie: true }),
      rankChip(130, 138, { href: nationalHref("profile:to_lost_pg", { team: US.name }), label: "Turnovers lost" }),
    ),
    label("Poll badges: square and toneless, so a poll rank never reads as a stat rank. Linked to the poll."),
    el("div", { class: "sg__row" },
      pollBadge(isNum(us.apRank) ? us.apRank : 12, "AP", { href: pollHref("AP", { team: US.name }) }),
      pollBadge(isNum(them.coachesRank) ? them.coachesRank : 3, "Coaches", { href: pollHref("Coaches", { team: them.school }) }),
      pollBadge(7, "CFP", { href: pollHref("CFP") }),
      pollBadge(18, "AP", { showPoll: false }),
    ),
    label("Value and chip as one unit; a row without a rank keeps an invisible chip so the values line up; the third row has no metric, so its chip is plain"),
    el("div", { style: { maxWidth: "560px" } }, statTable({ compact: true, columns: valueColumns, rows, onRowTap: () => {}, caption: "Linked chips in a tappable table" })),
    label("Press feedback: buttons sink 1px and darken; rows darken; hover only where a mouse hovers"),
    el("div", { class: "sg__row" }, el("button", { class: "btn", type: "button" }, "Button"), el("button", { class: "btn btn--primary", type: "button" }, "Primary"), el("button", { class: "btn btn--quiet", type: "button" }, "Quiet"),
      el("div", { class: "seg", role: "group" }, el("button", { type: "button", "aria-pressed": "true" }, "Mudpuppies"), el("button", { type: "button", "aria-pressed": "false" }, "BB"), el("button", { type: "button", "aria-pressed": "false" }, "National")),
      teamLink(them.school || "Diner Tech")),
    label("The side sheet: slides in, swaps in place, stacks, closes on a route change"),
    el("div", { class: "sg__row" }, el("button", { class: "btn", type: "button", onclick: openDemo }, "Open a side sheet")),
    label("A wide table in a narrow box: No. and Player stay put, a shadow shows it scrolled, the right edge fades while more is hidden"),
    el("div", { style: { maxWidth: "420px" } }, wide.length ? statTable({ compact: true, columns: wideColumns, rows: wide, rowClass: (row) => (row === wide[1] ? "is-next" : null), caption: "Roster" }) : note("No roster in the sample data.")),
    label("Recruiting ratings and stars, the same on every screen (formats rating100 and stars)"),
    el("div", { style: { maxWidth: "420px" } }, statTable({ compact: true, columns: [{ key: "name", label: "Recruit", kind: "text" }, { key: "rating", label: "Rating", format: "rating100" }, { key: "stars", label: "Stars", format: "stars" }], rows: recruits, sortable: false })),
    label("Designed states: an empty block, an error block with Try now, the table-shaped skeleton (a calm pulse), the error panel as one full-width band"),
    el("div", { class: "sg__states" },
      band({ title: "Drives", collapsible: false, body: () => stateBlock({ lead: "No drives yet", detail: "Drives appear after kickoff." }) }),
      band({ title: "Ratings", collapsible: false, body: () => stateBlock({ kind: "error", lead: "Could not load Ratings.", detail: "The server answered 503. The app tries again every 15 min.", action: { label: "Try now", onClick: () => {} } }) }),
      band({ title: "SP+", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(6, 5) }),
    ),
    errorPanel("Leaders", "The server did not answer in 20 s", () => {}),
    label("Sub-headings: one style; a team name is its link, with the team's edge"),
    el("div", { class: "band" }, subhead("Series history"), subhead(US.name, { team: US.name, side: "us" }), subhead(them.school || "Diner Tech", { team: them.school || "Diner Tech", side: "them" })),
    label("Page elements: the Back row on sub-routes and 'On this page' (lists this page's sections, unfolds a folded one)"),
    el("div", { class: "sg__row" }, backRow(), page),
    label("Team logos (the dark-background variant on navy, a tile when there is none) and player faces (headshot, number, team, initials)"),
    el("div", { class: "sg__row" }, teamLogo(us, { size: 40 }), teamLogo(them, { size: 40 }), teamLogo({ school: "Coastal Carolina", abbreviation: "CCU", color: "#006F71" }, { size: 40 }), teamLogo({ school: "Texas A&M" }, { size: 28 }),
      playerFace({ number: 2 }, { size: 44 }), playerFace({ name: "Trey Harlan" }, { them: true, abbr: them.abbreviation || "DINR", size: 44 }), playerFace({ name: "Mason Hamilton" }, { size: 44 })),
    note("Text size (Settings, per device) multiplies every type token by 1, 1.12 or 1.25; pull down at the top of any page (or press r) to refresh it."),
  );
  page.append(jumpList(document.body)); // read when opened, so it lists every section on this page
  return kit;
}

// --- Phase 16 NV: the national list --------------------------------------------------------------------

function demoList() {
  // A real 25-team list from the recorded poll (points), shaped as /api/national answers it.
  const poll = (Array.isArray(sample.polls) ? sample.polls : []).find((p) => Array.isArray(p?.top)) || { top: [] };
  const top = poll.top.filter((t) => t && isNum(t.rank));
  const next = opponent.school || "Diner Tech";
  const rows = top.map((t) => ({ rank: t.rank, tied: top.filter((o) => o.rank === t.rank).length > 1, team: t.school, conference: t.conference, value: t.points, firstPlaceVotes: t.firstPlaceVotes, isUs: t.school === US.name, isFocus: false, isNext: t.school === next }));
  if (!rows.some((r) => r.isUs)) rows.push({ rank: 31, tied: false, team: US.name, conference: "BB", value: 120, isUs: true, isFocus: false, isNext: false });
  const us = rows.find((r) => r.isUs);
  const base = { season: sample.season, year: sample.season, years: [sample.season, sample.season - 1], scope: "national", scopes: ["national", "conference"], conference: null, unit: "team", tiesShare: true, rankSource: "local", unranked: 0, beyond: [], cut: null, us: { team: US.name, rank: us.rank, value: us.value, of: rows.length }, focus: null, next: next, parts: {} };
  return {
    team: { ...base, metric: "profile:ppg", family: "profile", key: "ppg", label: "Poll points (demo)", format: "0f", higherIsBetter: true, valueLabel: "Points", population: "Teams receiving votes", of: rows.length, rows },
    poll: { ...base, metric: "poll:AP", family: "poll", key: "AP", label: poll.poll || "AP Top 25", format: "0f", higherIsBetter: true, valueLabel: "Points", scopes: ["national"], years: [sample.season], rankSource: "cfbd", population: `The ${poll.poll || "AP Top 25"}`, of: 25, rows: rows.filter((r) => r.rank <= 25).slice(0, 8), note: "Latest poll week." },
  };
}

function demoPlayers() {
  const board = sample.leaders?.["passing:YDS"] || {};
  const ours = (Array.isArray(board.team) ? board.team : []).filter((r) => r && typeof r === "object").slice(0, 2);
  const rows = Array.from({ length: 12 }, (_, i) => ({ rank: i + 1, tied: false, playerId: `demo${i}`, player: `National leader ${i + 1}`, position: "QB", team: i === 4 ? (opponent.school || "Diner Tech") : "FBS team", value: 2100 - i * 70, isUs: false, isNext: i === 4 }));
  const beyond = ours.map((g) => ({ rank: g.nationalRank, tied: false, playerId: g.playerId, player: g.player, position: g.position, team: US.name, value: g.value, isUs: true }));
  return { metric: "board:passing:YDS", family: "board", key: "passing:YDS", label: board.label || "Passing yards", format: "0f", higherIsBetter: true, unit: "player", season: sample.season, year: sample.season, years: [sample.season], scope: "national", scopes: ["national", "conference"], tiesShare: true, rankSource: "local", population: "FBS players", of: ours[0]?.nationalOf ?? 358, rows, beyond, cut: 12, us: { team: US.name, rank: ours[0]?.nationalRank ?? null, player: ours[0]?.player ?? null, value: ours[0]?.value ?? null }, focus: null, parts: {} };
}

function nationalSection() {
  installNationalLinks(document); // list links open the sheet here as in the app
  const lists = demoList();
  return section(
    "national",
    "National list",
    "What a linked rank chip opens (G3-01, DS-01): every team's number for the stat in a side sheet over the page, with a Full page link. The label is a hint (tap it); the tapped team's row is marked and scrolled into view; the next opponent carries a tag. GX-04 adds the data bars, the FBS median tick, Pctl and the one-line strip.",
    label("A team list: summary, switches, strip, bars and percentiles (demo numbers: the recorded poll points)"),
    el("div", { class: "band", style: { maxWidth: "760px" } }, nationalListBody({ data: lists.team }, { onScope: () => {}, onYear: () => {} })),
    label("A player list: the top of the board, the gap row and every Mudpuppy below the cut in their own tbody, so the zebra holds"),
    el("div", { class: "band", style: { maxWidth: "760px" } }, nationalListBody({ data: demoPlayers() }, { onScope: () => {} })),
    label("A poll list: the poll badge, points and first-place votes; its Full page is the Season polls band"),
    el("div", { class: "band", style: { maxWidth: "560px" } }, nationalListBody({ data: lists.poll })),
    label("States: nothing ranked yet (with the reason), and a list whose data did not load"),
    el("div", { class: "sg__states" },
      el("div", { class: "band" }, nationalListBody({ data: { ...lists.team, rows: [], us: { team: US.name }, note: "Points need every FBS game of the season; that answer did not load, so this list is empty." } })),
      el("div", { class: "band" }, nationalListBody({ data: { ...lists.team, rows: [], us: { team: US.name }, parts: { stats: { status: "error", error: "CFBD unavailable" } } } }, { onRetry: () => {} })),
    ),
    label("The real thing, from this server: open a list in a side sheet (costs no CFBD call once the pages have loaded), or a quiet list link for a value without a chip"),
    el("div", { class: "sg__row" },
      el("button", { class: "btn", type: "button", onclick: () => openNationalSheet({ metric: "advanced:defense_explosiveness", team: opponent.school || "Diner Tech" }) }, "Explosiveness allowed"),
      el("button", { class: "btn", type: "button", onclick: () => openNationalSheet({ metric: "profile:ypp", scope: "conference" }) }, "Yards per play, BB"),
      el("button", { class: "btn", type: "button", onclick: () => openNationalSheet({ metric: "board:passing:YDS" }) }, "Passing yards"),
      listLink("bluechip:ratio", { label: "Blue-chip ratio" }),
    ),
    label("The matchup sheet (UX-12): any two FBS teams side by side from the cached all-FBS answers; Scores rows and slate cards open it"),
    el("div", { class: "sg__row" }, el("button", { class: "btn", type: "button", onclick: () => openMatchupSheet({ away: opponent.school || "Diner Tech", home: US.name }) }, `${opponent.school || "Diner Tech"} at Swampwater Tech`)),
  );
}

// --- Phase 16 SEASON: Season, team pages and Ratings -------------------------------------------------

function seasonKitSection() {
  const rows = (sample.profile?.rows || []).filter((row) => row && typeof row === "object");
  const before = statTable({
    compact: true,
    caption: "Before",
    columns: [
      { key: "label", label: "Statistic", kind: "text", sortable: false },
      { key: "valueText", label: "Value", kind: "text", sortable: false },
      { key: "nationalRank", label: "FBS rank", kind: "rank", of: "nationalOf" },
      { key: "conferenceRank", label: "BB", kind: "rank", of: "conferenceOf" },
    ],
    rows: rows.filter((row) => row.side === "offense").map((row) => ({ ...row, valueText: fmtStat(row.value, row.format) })),
  });
  const sp = sample.ratings?.sp || {};
  const games = (sample.schedule || []).slice(0, 4).map((game, index) => ({
    ...game,
    archived: index === 0,
    opponentSp: { rank: [106, 118, 30, 20][index], rating: null },
    winPct: index < 2 ? { value: [0.991, 0.998][index], estimate: false, source: "postgame" } : { value: [0.47, 0.25][index - 2], estimate: true, source: "pregame Elo" },
  }));
  const form = [{ result: "W", points: 66, opponentPoints: 21, opponent: "Swampwater Tech Atlantic" }, { result: "W", points: 52, opponentPoints: 3, opponent: "Campbell" }, { result: "L", points: 17, opponentPoints: 20, opponent: "Silver Dollar", homeAway: "away" }, { result: "W", points: 34, opponentPoints: 31, opponent: "Diner Tech" }, { result: "W", points: 41, opponentPoints: 10, opponent: "Sweet Tea State", homeAway: "away" }];
  const polls = [
    { rank: 1, school: "Texas", conference: "BB", points: 1500, change: 2, movement: "+2", previousRank: 3 },
    { rank: 8, school: "Diner Tech", conference: "BB", points: 1100, change: -3, movement: "-3", previousRank: 5 },
    { rank: 18, school: US.name, conference: "BB", points: 400, change: null, movement: "new", isUs: true },
    { rank: 19, school: "Sweet Tea State", conference: "BB", points: 380, change: 0, movement: "0", previousRank: 19 },
  ];
  const mv = (row) => (row.movement === "new" ? el("span", { class: "mv mv--new" }, "new") : el("span", { class: `mv${row.change > 0 ? " mv--up" : row.change < 0 ? " mv--down" : ""}` }, row.change > 0 ? `+${row.change}` : row.change < 0 ? `−${Math.abs(row.change)}` : "0"));
  return section(
    "season16",
    "Season (Phase 16)",
    "Every national number is a linked unit, schedule rows open the game, and the side columns' team tables fit their column. Recorded numbers from the fixtures; the schedule's SP+ ranks and win chances are illustrations.",
    label("Value and chip, before (Phase 15: the value left-aligned in body text, its chip a column away) and after (the value right-aligned in the stat face with its chip in the same cell; the BB chip in its own narrow column, a shade dimmer)"),
    el("div", { class: "spread spread--2" }, el("div", {}, el("span", { class: "sg__label" }, "Before"), before), el("div", {}, el("span", { class: "sg__label" }, "After"), profileTable(rows, "offense", { team: US.name, conferenceLabel: "BB" }))),
    label("Tiles size to their column: 2 x 2 in a column under 560 px, 4 across above; each chip a link with 'of N'"),
    el("div", { class: "spread spread--2" }, el("div", { style: { maxWidth: "440px" } }, profileTiles(rows, { team: US.name })), profileTiles(rows, { team: US.name })),
    label("Record box and schedule rows: a finished game the app watched opens its archive, the rest their program; a chevron marks a row that opens; ranked opponents carry a poll badge; the second line is the opponent's SP+ rank and the win chance (est. before kickoff)"),
    el("div", { class: "band", style: { maxWidth: "300px" } }, recordLine({ ...(sample.record || {}), apRank: 18, coachesRank: null, spRank: sp.ranking, team: US.name }), scheduleList({ games, nextGameId: games[2]?.gameId ?? null, onSelect: () => {}, context: true, spOf: 138 })),
    label("Another team's schedule (the flyout): no chevron, no tap"),
    el("div", { class: "band", style: { maxWidth: "300px" } }, scheduleList({ games: games.slice(0, 2) })),
    label("Form (GX-17): the last five, newest on the right, a letter on each square; poll movement (GX-06): the sign in color and in text"),
    el("div", { class: "sg__row" }, formSquares(form), formSquares(form.slice(0, 2)), el("span", { class: "sg__label" }, "none yet:"), formSquares([]) || "–"),
    el("div", { class: "band tight", style: { maxWidth: "300px" } }, statTable({ compact: true, sortable: false, columns: [{ key: "rank", label: "#", dim: true }, { key: "school", label: "AP Top 25, week 4", kind: "text", sub: "conference", team: true }, { key: "change", label: "±", render: mv }, { key: "points", label: "Pts" }], rows: polls, rowClass: (row) => (row.isUs ? "is-us" : null) })),
    label("Trend rows: the last game captioned 'last' with the season average; under two games the line waits"),
    el("div", { class: "band", style: { maxWidth: "440px" } }, trendRow({ label: "Points scored", values: sample.trends?.points || [], key: "sg-points" }), trendRow({ label: "Points allowed", values: sample.trends?.pointsAllowed || [], them: true }), trendRow({ label: "Yards per play", values: [7.2], format: "1f" })),
  );
}

// --- PROGRAM (Phase 16): the two-team table before and after, the edges table, the leaders grid, the cover's
// states, the throw and run tables, the weather row with its radar link and venue facts. Imported here, not in
// the top block, so the other streams' import edits never meet these lines.
import { twoTeamTable as p16TwoTeam } from "./ui/two-team.js";
import { edgesSummary as p16EdgesSummary, edgesTable as p16EdgesTable } from "./ui/edges.js";
import { coverSkeleton as p16CoverSkeleton } from "./ui/cover.js";
import { venueLine as p16VenueLine } from "./ui/matchup-card.js";
import { passZonesTable as p16Zones, runLanesTable as p16Lanes } from "./ui/depth2.js";
import { statLine as p16StatLine } from "./ui/leaders.js";
import { depthBlock as p16Depth, startersBlock as p16Starters } from "./ui/lineups.js";

/** Example lineups in the notes file's shape (2026-10-02): CFBD has no depth chart, so the styleguide's numbers are examples. */
function p16Lineups() {
  const slot = (unit, label, ...players) => ({ unit, slot: label, players: players.map(([number, name, classYear, note]) => ({ number, name, classYear, note })) });
  return {
    source: "Published depth charts (example)",
    updatedAt: "2026-10-01",
    us: { team: US.name, scheme: "Spread option", source: "Team release, week 5 (example)", sourceUrl: "https://example.invalid/depth", updatedAt: "2026-10-01", slots: [slot("Offense", "QB", [12, "Mason Hamilton", "RS SO"], [9, "Tramell Jones Jr.", "RS FR"]), slot("Offense", "RB", [13, "Lucas Griffin", "JR"], [20, "Dante Clayborn", "RS FR"], [21, "Evan Pruitt", "RS SR"]), slot("Defense", "STAR", [20, "Kane Clayborn", "RS SR", "questionable, ankle"], [43, "Alonzo Albright Jr.", "RS SR"]), slot("Special teams", "PK", [91, "Patrick Dunmore", "JR"], [41, "Liam Pardue", "JR"])] },
    them: { team: "Opponent", scheme: "4-2-5", source: "Ourlads (example)", updatedAt: "2026-09-26", slots: [slot("Offense", "QB", [13, "Starter Name", "RS JR"], [5, "Backup Name", "SO"]), slot("Defense", "JACK", [19, "Starter Name", "RS SR"], [12, "Backup Name", "RS JR"])] },
  };
}

function p16TapeRows() {
  return (program.taleOfTheTape || []).map((row) => ({
    label: row.label,
    format: row.format,
    higherIsBetter: row.higherIsBetter,
    metric: row.us?.metric || row.them?.metric,
    us: { value: row.us?.value, rank: row.us?.nationalRank, of: row.us?.nationalOf },
    them: { value: row.them?.value, rank: row.them?.nationalRank, of: row.them?.nationalOf },
  }));
}

function program16Section() {
  const themAbbr = text(opponent.abbreviation);
  const rows = p16TapeRows();
  const withNoRank = [...rows.slice(0, 4), { label: "Blue-chip ratio (no rank)", format: "pct", higherIsBetter: true, us: { value: 0.709 }, them: { value: 0.52 } }];
  const beforeColumns = [
    { key: "label", label: "Statistic", kind: "text", sortable: false },
    { key: "usText", label: US.abbr, kind: "text", sortable: false },
    { key: "usRank", label: "FBS rank", kind: "rank", of: "usOf" },
    { key: "themText", label: themAbbr, kind: "text", sortable: false },
    { key: "themRank", label: "FBS rank", kind: "rank", of: "themOf" },
  ];
  const beforeRows = withNoRank.map((r) => ({ label: r.label, usText: fmtStat(r.us.value, r.format), usRank: r.us.rank, usOf: r.us.of, themText: fmtStat(r.them.value, r.format), themRank: r.them.rank, themOf: r.them.of }));
  const leaders = (program.leadersSideBySide || []).map((cat) => ({
    label: cat.label,
    us: cat.us ? { name: cat.us.player, position: cat.us.position, line: { hero: p16StatLine(cat.us.value, "0f", "YDS"), rest: "" } } : null,
    them: cat.them ? { name: cat.them.player, position: cat.them.position, line: { hero: p16StatLine(cat.them.value, "0f", "YDS"), rest: "" } } : null,
  }));
  leaders.push({ label: "Sacks (a 1f board: bug 2)", us: { name: "Example rusher", position: "DL", line: { hero: p16StatLine(4.5, "1f", "SACKS"), rest: "" } }, them: null });
  const kickoff = program.date ? new Date(program.date) : new Date();
  const at = (minutes) => new Date(kickoff.getTime() + minutes * 60000);
  const base = { us: program.us || {}, them: opponent, homeIsUs: program.homeIsUs, date: program.date, venue: program.venue, tv: program.tv, line: program.line || {}, pregame: program.pregame || {}, liveHref: "#live" };
  const zones = [["deep", "left", 6, 3, 0.5, 0.5], ["deep", "middle", 2, 1, 0.5, 0.5], ["deep", "right", 0, 0, null, null], ["short", "left", 21, 15, 0.714, 0.524], ["short", "middle", 14, 11, 0.786, 0.571], ["short", "right", 19, 12, 0.632, 0.474]].map(([depth, direction, attempts, completions, completionPct, successRate]) => ({ key: `${depth}_${direction}`, depth, direction, attempts, completions, completionPct, successRate }));
  const lanes = [["left", 31, 5.1, 0.45], ["middle", 44, 3.9, 0.41], ["right", 0, null, null]].map(([key, carries, yardsPerCarry, successRate]) => ({ key, carries, yardsPerCarry, successRate }));
  return section(
    "program16",
    "Program: two-team table, edges, leaders, cover states",
    "Phase 16. One two-team table everywhere on the program: value and a linked rank chip in one cell, a divider before the opponent, the better number bold and the other fog, an invisible chip where a row has no rank so values line up (DS-02). Every chip with a list behind it opens that national list.",
    label("Before (DS-02): separate Nat columns, SWT's rank beside the opponent's value, a chip-less row drifts"),
    el("div", { class: "band" }, statTable({ compact: true, columns: beforeColumns, rows: beforeRows, caption: "Before" })),
    label("After: twoTeamTable({ rows, usAbbr, themAbbr, usTeam, themTeam })"),
    el("div", { class: "band" }, p16TwoTeam({ rows: withNoRank, usAbbr: US.abbr, themAbbr, usTeam: US.name, themTeam: opponent.school, caption: "After" })),
    label("With the percentile underline (GX-11, the tape) and the percentile ladder (GX-05, the advanced tables)"),
    el("div", { class: "band" }, p16TwoTeam({ rows: rows.slice(0, 6), usAbbr: US.abbr, themAbbr, usTeam: US.name, themTeam: opponent.school, underline: true, ladder: true })),
    label(`Biggest edges (ui/edges.js), shared with the Live sheet: ${p16EdgesSummary(program.edges, { usAbbr: US.abbr, themAbbr })}`),
    el("div", { class: "band" }, p16EdgesTable(program.edges || [], { usAbbr: US.abbr, themAbbr, usTeam: US.name, themTeam: opponent.school, limit: 6 })),
    label("Leaders grid on the program: a head row, a divider, the key number bold, even heights"),
    el("div", { class: "band" }, leadersGrid({ categories: leaders, usAbbr: US.abbr, themAbbr, className: "leaders--program" })),
    label("Cover states: a day out, inside the hour, under way, final with an Archive link, a TBD kickoff, loading"),
    el(
      "div",
      { class: "sg__stack" },
      cover({ ...base, now: at(-24 * 60) }),
      cover({ ...base, now: at(-38) }),
      cover({ ...base, now: at(20) }),
      cover({ ...base, state: "final", usPoints: 31, themPoints: 24, archiveHref: "#archive", line: {} }),
      cover({ ...base, startTimeTbd: true, now: at(-3 * 24 * 60) }),
      p16CoverSkeleton(),
    ),
    label("Where the opponent throws and runs (GX-15): example numbers"),
    el("div", { class: "band" }, el("div", { class: "zones-pair" }, p16Zones(zones), p16Lanes(lanes))),
    label("Starting lineups (2026-10-02): the first name at every slot of each team's published chart, a table per unit, the source under it"),
    el("div", { class: "band" }, p16Starters({ lineups: p16Lineups(), us: program.us || { school: US.name }, them: opponent })),
    label("Depth charts: one row per slot, as many columns as the deepest slot; folded by default on the program"),
    el("div", { class: "band" }, p16Depth({ lineups: p16Lineups(), us: program.us || { school: US.name }, them: opponent })),
    label("Nothing written yet: the honest empty state the program and the Live sheet share"),
    el("div", { class: "band" }, p16Starters({ lineups: null, us: program.us || { school: US.name }, them: opponent })),
    label("Weather row with the Radar link-out (UX-14) and the venue line (GX-19), example values"),
    el("div", { class: "band program-weather" }, weatherRow({ kickoffText: "3:30 PM", tempF: 84, windMph: 9, windDir: "SE", sky: "Partly cloudy", precipChance: 20, source: "National Weather Service, example", radarUrl: "https://forecast.weather.gov/MapClick.php?lat=29.65&lon=-82.35" }), p16VenueLine({ name: "Home Stadium (example)", capacity: 88548, grass: true, elevationFt: 148, yearBuilt: 1930, recordAtVenue: { opponent: "Opponent (example)", wins: 3, losses: 1, ties: 0, gamesWithoutVenue: 0 } }, { us: US.name })),
  );
}

// --- PEOPLE (Phase 16): the depth chart in six columns, its skeleton, and where a class is from -------------

function peopleSection() {
  const chart = el("div", { class: "band" }, note("Loading the depth chart..."));
  const where = el("div", { class: "band" }, note("Loading..."));
  const skeleton = el("div", { class: "band" });
  // the views are loaded on demand, so the styleguide's import list stays as it is
  import("./views/roster.js")
    .then((roster) => {
      chart.replaceChildren(roster.depthChart(sample.roster || []));
      skeleton.replaceChildren(roster.depthSkeleton());
    })
    .catch((error) => chart.replaceChildren(note(`Could not draw the depth chart: ${text(error?.message)}`, { kind: "error" })));
  import("./views/recruiting.js")
    .then((rec) => {
      // the sample class carries no byState, so it is counted here from the commits' hometowns ("Frisco, TX")
      const commits = Array.isArray(sample.recruiting?.commits) ? sample.recruiting.commits : [];
      const byState = new Map();
      for (const c of commits) {
        const state = typeof c.hometown === "string" && /,\s*([A-Z]{2})$/.test(c.hometown) ? c.hometown.match(/,\s*([A-Z]{2})$/)[1] : null;
        const row = byState.get(state) || { state, commits: 0, ratings: [], stars: { 5: 0, 4: 0, 3: 0 } };
        row.commits += 1;
        if (isNum(c.rating)) row.ratings.push(c.rating);
        if (isNum(c.stars) && row.stars[c.stars] !== undefined) row.stars[c.stars] += 1;
        byState.set(state, row);
      }
      const rows = [...byState.values()].map((row) => ({ ...row, averageRating: row.ratings.length ? row.ratings.reduce((a, b) => a + b, 0) / row.ratings.length : null })).sort((a, b) => b.commits - a.commits);
      const fl = byState.get("FL");
      const cls = { year: sample.recruiting?.year, byState: rows, inState: { state: "FL", commits: fl ? fl.commits : 0, of: commits.length }, unknownState: byState.get(null)?.commits || 0 };
      const list = rec.whereRows(cls);
      where.replaceChildren(
        statTable({ compact: true, columns: [{ key: "state", label: "State", kind: "text" }, { key: "commits", label: "Commits" }, { key: "averageRating", label: "Avg rating", format: "rating100" }, { key: "starMix", label: "5-, 4-, 3-star", kind: "text" }], rows: list, sort: { key: "commits", dir: "descending" } }),
        el("p", { class: "note" }, rec.inStateLine(cls) || "No in-state share."),
      );
    })
    .catch((error) => where.replaceChildren(note(`Could not draw the table: ${text(error?.message)}`, { kind: "error" })));
  return section(
    "people",
    "People (Phase 16)",
    "Roster and Recruiting pieces from stream PEOPLE. The depth chart: six unit columns from 1100 px (three from 700, two below), a jersey number on every row, 44 px rows, each card's select naming its number (Plays where CFBD credits plays, Rating elsewhere). Recruiting: 'Where they're from' per class with the in-state share.",
    label(`Depth chart from the sample roster (${text((sample.roster || []).length)} players)`),
    chart,
    label("Depth chart while it loads: the same six columns, so nothing moves when the data lands"),
    skeleton,
    label(`Where they're from, the ${text(sample.recruiting?.year)} class (counted from the sample commits)`),
    where,
  );
}

// Phase 16: each stream registers its styleguide sections on its own line under its anchor (hotspot
// rule), as ["id", "Nav name", sectionFunction], and writes the section function above this list.
const STREAM_SECTIONS = [
  // === NV ===
  ["national", "National list", nationalSection],
  // === SEASON ===
  ["season16", "Season 16", seasonKitSection],
  // === PROGRAM ===
  ["program16", "Program 16", program16Section],
  // === PEOPLE ===
  ["people", "People", peopleSection],
  // === PROFILES ===
  // === SCORES ===
  // === LIVE ===
  // === DS ===
];

// --- page ----------------------------------------------------------------------------------------

function breakpointName(width) {
  if (width < 700) return "narrow";
  if (width < 1100) return "medium";
  return "wide";
}

function build() {
  const app = document.getElementById("app");
  const page = shell({ current: "season", status: { kind: "live", label: "Styleguide" } });
  const bp = el("span", { class: "sg__bp" }, "Viewport ", el("b", {}, `${window.innerWidth} px`), el("span", {}, breakpointName(window.innerWidth)));
  window.addEventListener("resize", () => {
    bp.replaceChildren("Viewport ", el("b", {}, `${window.innerWidth} px`), el("span", {}, breakpointName(window.innerWidth)));
  });
  const sections = [
    ["tokens", "Tokens", tokensSection], ["shell", "Shell", shellSection], ["strip", "Strip", stripSection], ["live", "Live sheet", liveSection],
    ["newspaper", "Newspaper", newspaperSection], ["team", "Team page", teamSection], ["recruiting", "Recruiting", recruitingSection],
    ["table", "Tables", tableSection], ["card", "Player card", cardSection], ["compare", "Two-team table", compareSection], ["trends", "Trends", trendSection],
    ["pills", "Pills", pillSection], ["ticker", "Ticker", tickerSection], ["slider", "Delay", sliderSection], ["editorial", "Editorial", editorialSection],
    ["cover", "Cover", coverSection], ["season", "Season", seasonSection], ["program", "Program", programSection],
    ["kit", "Kit", kitSection],
    ...STREAM_SECTIONS,
  ];
  // ?only=live renders one section, handy on a phone or for a screenshot.
  const only = new URLSearchParams(window.location.search).get("only");
  const chosen = only ? sections.filter(([id]) => id === only) : sections;
  page.main.append(
    el(
      "div",
      { class: "sg" },
      el("div", { class: "sg__intro" }, el("h1", {}, "Design system"), el("p", {}, `Every component in every state, with real numbers from the recorded fixtures (${text(sample.generatedFrom)}). Resize the window or open this on the phone: the same components reflow at 700 and 1100 px.`), bp),
      el("nav", { class: "sg__nav", "aria-label": "Sections" }, sections.map(([id, name]) => el("a", { href: `?only=${id}` }, name)), el("a", { href: "?" }, "All")),
      (chosen.length ? chosen : sections).map(([, , render]) => render()),
    ),
  );
  app.replaceChildren(page.root);
}

build();
