// Phase 13 (stats depth II): the table builders the Season, team, Game program, Archive and Live
// pages share. Tables only (design rule 2026-09-23), every value guarded: a missing number is a dash.
//
// advancedPaired(rows, { team, conferenceLabel })   G3-03: a team's advanced season stats as ONE table, offense and
//                                         defense paired on each attribute, the areas as group rows; a one-sided
//                                         attribute shows a dash on the other side. Sized (wave 3, rule 3): Metric |
//                                         Offense | FBS rank | <conf> rank | Defense | FBS rank | <conf> rank, the FBS
//                                         ranks from medium, the conference's at large (when the server sends them)
// matchupGroups(us, them, labels)         the same side by side for two teams
// adjustedMatchup(rows, labels)           opponent-adjusted metrics side by side (CFBD's WEPA)
// resumeBlock(resume, teamName)           expected wins, schedule strength (its rank in its own column, a linked
//                                         chip), the poll path as poll badges; both tables sized (wave 3)
// tendenciesBlock(t, abbr)                an opponent's run and pass calls by situation, run direction, pass depth
// advancedBoxBlock(box, sides)            one finished game: by quarter, line play and havoc, players' value
//
// Table sizes, wave 2 (owner 2026-10-10; docs/03-DESIGN.md, Table sizes): the Pre-Game Program's tables here size
// themselves by their own box. The situations: whole heads at large (Yards per carry, Yards per pass play), the counts and
// yards gone at small, where the made-of pairs ("12-20") carry the counts. The pass zones and run lanes keep the field's
// shape at every size and say less in each cell as the box narrows. The advanced box score: the quarter tables keep every
// quarter (only the row names shorten), the players keep Team at every size, the pass and rush splits at large only, and a
// row opens the player's card; the two teams' table is the two-team kit with the tug bar (rule 9).

import { usLabel, usSchool } from "../identity.js";
import { weekCell } from "./weeks.js";
import { DASH, el, fmtNum, fmtPct, fmtStat, isNum, records, teamLink, text } from "./dom.js";
import { nationalHref, pollHref } from "./national-link.js";
import { DROPPED, fitSize, watchSize } from "./sizes.js";
import { note } from "./states.js";
import { applyStatSize, pollBadge, statTable } from "./stat-table.js";

const h4 = (label) => el("h4", { class: "d2-head" }, label);

/** A value in its format, or a dash. */
function show(value, format) {
  return isNum(value) ? fmtStat(value, format || "2f") : DASH;
}

/** Rows grouped by their `group`, in first-seen order. Exported for the tests. */
export function groupRows(rows) {
  const groups = new Map();
  for (const row of records(rows)) {
    const key = typeof row.group === "string" && row.group ? row.group : "Other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  return groups;
}

// A neutral name for an attribute when the offense's own label would read oddly beside the defense's number.
const PAIR_LABELS = {
  success_rate: "Success rate",
  explosiveness: "Explosiveness",
  ppa: "PPA per play",
  standard_downs_success_rate: "Success, standard downs",
  passing_downs_success_rate: "Success, passing downs",
  passing_downs_ppa: "PPA, passing downs",
  rushing_plays_ppa: "PPA per rush",
  passing_plays_ppa: "PPA per pass",
  line_yards: "Line yards per rush",
  stuff_rate: "Stuff rate",
  power_success: "Power success",
  havoc_total: "Havoc rate",
  points_per_opportunity: "Points per scoring chance",
  field_position_average_start: "Average start, yards to goal",
};

/** Offense and defense rows paired on their attribute, in first-seen order, with group rows. Exported for the tests. */
export function pairAdvanced(rows) {
  const groups = new Map();
  for (const row of records(rows)) {
    const key = typeof row.key === "string" ? row.key : "";
    const side = row.side === "defense" ? "def" : row.side === "offense" ? "off" : null;
    const m = /^(offense|defense)_(.+)$/.exec(key);
    if (!side || !m) continue;
    const attr = m[2];
    const group = typeof row.group === "string" && row.group ? row.group : "Other";
    if (!groups.has(group)) groups.set(group, new Map());
    const pairs = groups.get(group);
    if (!pairs.has(attr)) pairs.set(attr, { attr, label: PAIR_LABELS[attr] || null });
    const pair = pairs.get(attr);
    pair[side] = row.value;
    pair[`${side}Format`] = row.format;
    pair[`${side}Rank`] = row.nationalRank;
    pair[`${side}Of`] = row.nationalOf;
    pair[`${side}Metric`] = row.metric;
    pair[`${side}Conf`] = row.conferenceRank; // wave 3: the rank inside the team's conference, its own column at large
    pair[`${side}ConfOf`] = row.conferenceOf;
    if (!pair.label && typeof row.label === "string") pair.label = row.label;
  }
  const out = [];
  for (const [group, pairs] of groups) {
    out.push({ isGroup: true, label: group });
    for (const pair of pairs.values()) out.push(pair);
  }
  return out;
}

/**
 * One team's advanced season stats as one paired table, sized by its own box (tables wave 3; Season, the team page and
 * its side sheet): Metric | Offense | FBS rank | <conf> rank | Defense | FBS rank | <conf> rank. Every data point has its
 * own column (rule 3): the FBS ranks from medium, the conference's at large and only when the server sent them. The
 * Defense column mixes the rates a defense allows with its own (stuff rate, havoc), so its head stays "Defense".
 */
export function advancedPaired(rows, { team, conferenceLabel } = {}) {
  const paired = pairAdvanced(rows);
  if (!paired.some((r) => isNum(r.off) || isNum(r.def))) return note("Advanced stats appear after the first game.");
  const conf = typeof conferenceLabel === "string" && conferenceLabel.trim() ? conferenceLabel.trim() : "Conf";
  const confs = paired.some((r) => isNum(r.offConf) || isNum(r.defConf));
  const side = (prefix, label, short, divider) => [
    { key: prefix, label, labelShort: short, divider, render: (row) => (row.isGroup ? el("span") : el("span", { "data-k": `adv:${prefix}:${text(row.attr)}` }, show(row[prefix], row[`${prefix}Format`]))) },
    { key: `${prefix}Rank`, label: "FBS rank", labelMid: "FBS", kind: "rank", of: `${prefix}Of`, size: "medium", link: (row) => (row.isGroup ? null : nationalHref(row[`${prefix}Metric`], { team })) },
    confs ? { key: `${prefix}Conf`, label: `${conf} rank`, kind: "rank", of: `${prefix}ConfOf`, size: "large", link: (row) => (row.isGroup ? null : nationalHref(row[`${prefix}Metric`], { team, scope: "conference" })) } : null,
  ].filter(Boolean);
  return el(
    "div",
    { class: "prof tight adv-paired" },
    statTable({
      compact: true,
      sizes: true,
      sortable: false,
      columns: [{ key: "label", label: "Metric", kind: "text" }, ...side("off", "Offense", "Off", false), ...side("def", "Defense", "Def", true)],
      rows: paired,
      rowClass: (row) => (row.isGroup ? "is-parent" : null),
      caption: "Advanced, offense and defense",
    }),
    note(`FBS rank is the national rank among FBS teams${confs ? `, ${conf} rank the rank inside the conference` : ""}: 1 is the best on that measure, whichever way the number runs.`),
  );
}

/** Two teams' advanced rows side by side, matched by key; each value with its national rank. */
// Phase 16 (stream PROGRAM, audit P-01/P-02): one two-team table with the areas as group rows, value and
// linked chip in one cell, a divider before the opponent. (Imported here, not at the top, so the Season
// stream's edits to this file's import block never meet these.)
import { twoTeamTable as programTwoTeam } from "./two-team.js";
import { subhead as programSubhead } from "./states.js";

export function matchupGroups(usRows, themRows, { usAbbr = usLabel(), themAbbr = DASH, usTeam, themTeam, ladder = false, tug = false } = {}) {
  const them = new Map(records(themRows).map((r) => [r.key, r]));
  const joined = records(usRows).map((r) => {
    const t = them.get(r.key) || {};
    return { key: r.key, group: r.group, label: r.label, format: r.format, metric: r.metric || t.metric, higherIsBetter: typeof r.higherIsBetter === "boolean" ? r.higherIsBetter : t.higherIsBetter, us: { value: r.value, rank: r.nationalRank, of: r.nationalOf || t.nationalOf }, them: { value: t.value, rank: t.nationalRank, of: t.nationalOf || r.nationalOf } };
  });
  if (!joined.some((r) => isNum(r.us.value) || isNum(r.them.value))) return note("Advanced stats appear once both teams have played.");
  const groups = [...groupRows(joined)].map(([title, rows]) => ({ title, rows }));
  return el(
    "div",
    { class: "d2" },
    programTwoTeam({ groups, usAbbr, themAbbr, usTeam, themTeam, ladder, tug, caption: "Advanced matchup" }),
    note("Each team's own season, with its national rank among FBS teams: 1 is the best on that measure, whichever way the number runs. Tap a rank for the national list."),
  );
}

export function adjustedMatchup(rows, { usAbbr = usLabel(), themAbbr = DASH, usTeam, themTeam, ladder = false, tug = false } = {}) {
  const list = records(rows);
  if (!list.some((r) => isNum(r.us) || isNum(r.them))) return note("CFBD has not published opponent-adjusted numbers for this season yet; they appear here when it does.");
  const shaped = list.map((r) => ({ label: r.label, format: r.format, metric: r.metric, higherIsBetter: r.higherIsBetter, us: { value: r.us, rank: r.usRank, of: r.of }, them: { value: r.them, rank: r.themRank, of: r.of } }));
  return el("div", {}, programTwoTeam({ rows: shaped, usAbbr, themAbbr, usTeam, themTeam, ladder, tug, labelHead: "Adjusted for opponents", caption: "Adjusted for opponents" }), note("CFBD's WEPA: EPA and success rate weighted for the strength of the opponents faced."));
}

// --- the résumé -----------------------------------------------------------------------------------------

/** A poll rank as a badge linked to that poll (the column names the poll), or "NR" in fog. */
function pollCell(rank, poll, team) {
  return isNum(rank) ? pollBadge(rank, poll, { href: pollHref(poll, { team }), label: team, showPoll: false }) : el("span", { class: "nr" }, "NR");
}

// The résumé's two tables, sized by their own box (tables wave 3). The summary: each fact, its value and (from medium) its
// FBS rank in a column of its own (rule 3: the schedule strength's chip left the value's cell, and the schedule to come says
// where it would rank with a chip, not in words). The poll path: the badges ARE the values (the team's path), so nothing drops.
const RESUME_COLUMNS = [
  { key: "label", label: "Résumé", kind: "text" },
  { key: "value", label: "Value" },
  { key: "rank", label: "FBS rank", labelMid: "FBS", kind: "rank", of: "of", size: "medium", link: (row) => row.href || null },
];

function pollPathColumns(team) {
  return [
    { key: "week", label: "Week", labelShort: "Wk" },
    { key: "ap", label: "AP rank", labelMid: "AP", render: (row) => pollCell(row.ap, "AP", team) },
    { key: "coaches", label: "Coaches rank", labelMid: "Coaches", render: (row) => pollCell(row.coaches, "Coaches", team) },
  ];
}

export function resumeBlock(resume, teamName = usSchool()) {
  const r = resume && typeof resume === "object" ? resume : {};
  const sos = r.sosPlayed && typeof r.sosPlayed === "object" ? r.sosPlayed : null;
  const remaining = r.remaining && typeof r.remaining === "object" ? r.remaining : {};
  const team = typeof teamName === "string" && teamName.trim() ? teamName.trim() : usSchool();
  const summary = [
    { label: "Record", value: isNum(r.wins) && isNum(r.losses) ? `${r.wins}-${r.losses}` : DASH },
    { label: "Expected wins", value: isNum(r.expectedWins) ? `${fmtNum(r.expectedWins, 2)} of ${text(r.gamesCounted)}` : DASH },
    { label: "Wins above expected", value: isNum(r.luck) ? fmtStat(r.luck, "+2f") : DASH },
    { label: "Opponents played, average SP+", value: sos && isNum(sos.rating) ? fmtNum(sos.rating, 1) : DASH, rank: sos?.rank, of: sos?.of, href: sos ? nationalHref(sos.metric, { team }) : null },
    // where the schedule still to come would rank among the schedules FBS teams have played: a plain chip (its list is the one above)
    { label: "Opponents to come, average SP+", value: isNum(remaining.averageSp) ? fmtNum(remaining.averageSp, 1) : DASH, rank: remaining.rankAmongPlayed, of: remaining.of, href: null },
  ];
  const games = records(remaining.games).map((g, i) => ({ order: i, week: weekCell(g), opponent: g.opponent, where: g.neutral ? "Neutral" : g.home ? "Home" : "Away", sp: g.sp }));
  const polls = records(r.polls).filter((p) => isNum(p.ap) || isNum(p.coaches));
  return el(
    "div",
    { class: "d2" },
    statTable({ compact: true, sizes: true, sortable: false, columns: RESUME_COLUMNS, rows: summary, caption: "Résumé" }),
    note("Expected wins adds up CFBD's postgame win probability for each finished game: how often a team that played that way would have won. Strength of schedule is the average SP+ of FBS opponents; CFBD does not publish its own during the season. The rank beside the opponents to come is where that schedule would sit among the schedules FBS teams have played."),
    games.length ? note("The rest of the schedule, with each opponent's record, rank, SP+ and form, is in the Road ahead band.") : null,
    polls.length
      ? el("div", {}, h4("Poll path"), statTable({ compact: true, sizes: true, sortable: false, columns: pollPathColumns(team), rows: polls.map((p) => ({ week: p.seasonType === "postseason" ? "Final" : p.week, ap: p.ap, coaches: p.coaches })), caption: "Poll path" }))
      : note(`${text(teamName)} has not been ranked in a poll this season.`),
  );
}

// --- an opponent's tendencies ------------------------------------------------------------------------------

const madeOf = (s) => (s && isNum(s.made) && isNum(s.of) && s.of > 0 ? `${s.made} of ${s.of}` : DASH);

// GX-15 (restrained): the opponent's throws as a 2x3 table laid out like the field (the deep row over the
// short row; left, middle, right) and its runs as a 1x3 table. Counts, then rates; a zero is a zero and a
// missing rate a dash. Exported for the tests.
const LANES = [["left", "Left"], ["middle", "Middle"], ["right", "Right"]];

function rateText(value) {
  return isNum(value) ? fmtPct(value, 1) : DASH;
}

function countOf(value) {
  return isNum(value) && value >= 0 ? Math.round(value) : null;
}

/** A hand-built grid sized the way statTable sizes itself: large, medium, small by its own box, small kept when nothing fits. */
function sizeGrid(wrap, table) {
  applyStatSize(wrap, "large");
  watchSize(wrap, () => {
    const size = fitSize(wrap, table, (step) => applyStatSize(wrap, step));
    if (size === null) return;
    if (size === DROPPED) wrap.classList.remove("stat-table-wrap--fits");
    else wrap.classList.add("stat-table-wrap--fits"); // never a scroll box
  });
  return wrap;
}

/** A zone's rates in three forms: one line at large, a short line each at medium, the one that matters most at small. */
function zoneRates(long, mid, short) {
  return [
    el("small", { class: "zone__rates zone__rates--long" }, long),
    el("span", { class: "zone__rates zone__rates--mid" }, mid.map((line) => el("small", {}, line))),
    el("small", { class: "zone__rates zone__rates--short" }, short),
  ];
}

export function passZonesTable(zones) {
  const list = records(zones);
  const find = (depth, lane) => list.find((z) => z.depth === depth && z.direction === lane) || list.find((z) => z.key === `${depth}_${lane}`) || null;
  const cell = (zone) => {
    const att = countOf(zone?.attempts);
    const comp = rateText(zone?.completionPct);
    const success = rateText(zone?.successRate);
    return el(
      "td",
      { class: `zone${att ? "" : " zone--none"}` },
      el("b", { class: "zone__count" }, att === null ? DASH : `${att} att`),
      att ? zoneRates(`${comp} comp · ${success} success`, [`${comp} comp`, `${success} succ.`], `${success} succ.`) : el("small", {}, "no throws"),
    );
  };
  const table = el(
    "table",
    { class: "stat-table stat-table--compact zones" },
    el("caption", { class: "sr-only" }, "Passes by zone: deep over short, left to right"),
    el("thead", {}, el("tr", {}, el("th", { class: "txt", scope: "col" }, "Passes"), LANES.map(([, label]) => el("th", { scope: "col" }, label)))),
    el("tbody", {}, [["deep", "Deep"], ["short", "Short"]].map(([depth, label]) => el("tr", {}, el("th", { class: "txt", scope: "row" }, label), LANES.map(([lane]) => cell(find(depth, lane)))))),
  );
  return sizeGrid(el("div", { class: "stat-table-wrap zones-wrap" }, table), table);
}

export function runLanesTable(lanes) {
  const list = records(lanes);
  const cell = (lane) => {
    const carries = countOf(lane?.carries);
    // the yards are per carry, so they say Y/C (one name per stat)
    const ypc = isNum(lane?.yardsPerCarry) ? `${fmtNum(lane.yardsPerCarry, 1)} Y/C` : `${DASH} Y/C`;
    const success = rateText(lane?.successRate);
    return el(
      "td",
      { class: `zone${carries ? "" : " zone--none"}` },
      el("b", { class: "zone__count" }, carries === null ? DASH : `${carries} car`),
      carries ? zoneRates(`${ypc} · ${success} success`, [ypc, `${success} succ.`], ypc) : el("small", {}, "no runs"),
    );
  };
  const table = el(
    "table",
    { class: "stat-table stat-table--compact zones" },
    el("caption", { class: "sr-only" }, "Runs by lane, left to right"),
    el("thead", {}, el("tr", {}, el("th", { class: "txt", scope: "col" }, "Runs"), LANES.map(([, label]) => el("th", { scope: "col" }, label)))),
    el("tbody", {}, el("tr", {}, el("th", { class: "txt", scope: "row" }, "Lane"), LANES.map(([key]) => cell(list.find((l) => l.key === key) || null)))),
  );
  return sizeGrid(el("div", { class: "stat-table-wrap zones-wrap" }, table), table);
}

// The yards a run gains are yards per carry; a pass play's (a sack counts as a called pass) are yards per pass play, not
// per attempt: one name for each, in three forms
const YPC = { label: "Yards per carry", labelMid: "Yds/carry", labelShort: "Y/C", format: "1f" };
const YPP_PASS = { label: "Yards per pass play", labelMid: "Yds/pass", labelShort: "Yds/pass", format: "1f" };

// By down and distance: every column at large and medium; small keeps the situation, the run rate and both made-of pairs
// ("12-20"), which carry the counts the plays and yards columns drop. The situation names shorten through ui/sizes.js.
const SITUATION_COLUMNS = [
  { key: "label", label: "Situation", kind: "text" },
  { key: "plays", label: "Plays", size: "medium" },
  { key: "runRate", label: "Run rate", labelShort: "Run %", format: "pct" },
  { key: "runYpp", ...YPC, size: "medium" },
  { key: "runSuccess", label: "Run success", labelShort: "Run succ.", kind: "text", shortKey: "runSuccessShort" },
  { key: "passYpp", ...YPP_PASS, size: "medium" },
  { key: "passSuccess", label: "Pass success", labelShort: "Pass succ.", kind: "text", shortKey: "passSuccessShort" },
];

/** The fallback splits (no zones in the answer): the runs by direction, the passes by depth, each with its own yards. */
function splitColumns(head, plays, yards) {
  return [{ key: "label", label: head, kind: "text" }, { key: "plays", label: plays }, { key: "ypp", ...yards }, { key: "success", label: "Success", kind: "text", shortKey: "successShort" }];
}

const madeShort = (s) => (s && isNum(s.made) && isNum(s.of) && s.of > 0 ? `${s.made}-${s.of}` : DASH);
const numOrNull = (value) => (isNum(value) ? value : null);

/** The situations as table rows; a situation with no plays is left out. Exported for the tests. */
export function situationRows(bySituation) {
  return records(bySituation)
    .filter((r) => isNum(r.plays) && r.plays > 0)
    .map((r) => ({
      label: text(r.label),
      plays: r.plays,
      runRate: numOrNull(r.runRate), // one decimal, as every rate in a table
      runYpp: numOrNull(r.run?.yardsPerPlay),
      runSuccess: madeOf(r.run?.success),
      runSuccessShort: madeShort(r.run?.success),
      passYpp: numOrNull(r.pass?.yardsPerPlay),
      passSuccess: madeOf(r.pass?.success),
      passSuccessShort: madeShort(r.pass?.success),
    }));
}

export function tendenciesBlock(t, abbr = DASH) {
  if (!t || typeof t !== "object" || !isNum(t.plays) || t.plays <= 0) return note("No plays from this opponent yet this season.");
  const splitRow = (r) => ({ label: text(r.label), plays: numOrNull(r.plays), ypp: numOrNull(r.yardsPerPlay), success: madeOf(r.success), successShort: madeShort(r.success) });
  const dirRows = records(t.runDirection).map(splitRow);
  const depthRows = records(t.passDepth).map(splitRow);
  const zones = records(t.passZones);
  const lanes = records(t.runLanes);
  const charted = zones.some((z) => countOf(z.attempts)) || lanes.some((l) => countOf(l.carries));
  const unplaced = [countOf(t.unplacedPasses) ? `${countOf(t.unplacedPasses)} passes` : null, countOf(t.unplacedRuns) ? `${countOf(t.unplacedRuns)} runs` : null].filter(Boolean).join(" and ");
  // With the zone tables the old direction and depth splits would repeat them; without zones they stay.
  const where = zones.length || lanes.length
    ? el(
        "div",
        {},
        programSubhead("Where the throws and runs go"),
        charted ? null : note("No throws or runs with a charted direction yet."),
        el("div", { class: "zones-pair" }, passZonesTable(zones), runLanesTable(lanes)),
        note(`Deep or short, left, middle or right as CFBD charts each throw and run; spikes, kneels and sacks are left out.${unplaced ? ` ${unplaced} had no charted zone.` : ""}`),
      )
    : el(
        "div",
        { class: "twocol" },
        el("div", {}, programSubhead("Where the runs go"), dirRows.some((r) => r.plays) ? statTable({ compact: true, sizes: true, sortable: true, columns: splitColumns("Direction", "Carries", YPC), rows: dirRows, caption: "Runs by direction" }) : note("No run directions charted.")),
        el("div", {}, programSubhead("How deep the passes go"), depthRows.length ? statTable({ compact: true, sizes: true, sortable: true, columns: splitColumns("Depth", "Plays", YPP_PASS), rows: depthRows, caption: "Passes by depth" }) : note("No pass depths charted.")),
      );
  return el(
    "div",
    { class: "d2" },
    el("p", { class: "note" }, `${text(abbr)} over ${text(t.games)} games: ${text(t.plays)} snaps, runs ${isNum(t.runRate) ? fmtPct(t.runRate) : DASH} of the time (a sack counts as a called pass; kneels and spikes are left out).`),
    programSubhead("By down and distance"),
    statTable({ compact: true, sizes: true, sortable: true, columns: SITUATION_COLUMNS, rows: situationRows(t.bySituation), caption: "By down and distance" }),
    where,
  );
}

// --- one finished game's advanced box score ----------------------------------------------------------------

const QUARTERS = [["quarter1", "Q1"], ["quarter2", "Q2"], ["quarter3", "Q3"], ["quarter4", "Q4"], ["total", "Game"]];

// By quarter: every quarter and the game at every size (five short values); the row names shorten through ui/sizes.js,
// named as the Season tables name them (one name per stat)
// (the values are numbers set in the stat face, right-aligned like every number: a text column's wider face held a phone's
// table 19 px past its box even at small)
const QUARTER_COLUMNS = [{ key: "label", label: "By quarter", labelShort: "Stat", kind: "text" }, ...QUARTERS.map(([, head]) => ({ key: head, label: head }))];

/** One team's advanced numbers by quarter as table rows. Exported for the tests. */
export function quarterRows(block) {
  const b = block && typeof block === "object" ? block : {};
  const line = (label, q, format) => {
    const row = { label };
    for (const [key, head] of QUARTERS) row[head] = show(q?.[key], format);
    return row;
  };
  return [
    line("Success rate", b.success?.overall, "pct"),
    line("Success on standard downs", b.success?.standardDowns, "pct"),
    line("Success on passing downs", b.success?.passingDowns, "pct"),
    line("PPA per play", b.ppa?.overall, "+2f"),
    line("PPA per pass", b.ppa?.passing, "+2f"),
    line("PPA per rush", b.ppa?.rushing, "+2f"),
    line("Explosiveness", b.explosiveness, "2f"),
  ];
}

function quarterTable(team, block, { school, side } = {}) {
  return el("div", {}, programSubhead(text(team), { team: typeof school === "string" ? school : null, side }), statTable({ compact: true, sizes: true, sortable: false, columns: QUARTER_COLUMNS, rows: quarterRows(block), caption: `${text(team)} by quarter` }));
}

// The players' value: Team at every size (it tells the sides apart), the pass and rush splits at large, usage from medium,
// the names stepping down with the table (item 6). A table of players sorts; a row opens the card.
const ADVANCED_PLAYER_COLUMNS = [
  { key: "player", label: "Player", kind: "text", sub: "position", subLabel: "Pos", person: true }, // wave 3 decision 1: the position its own column at large and medium
  { key: "side", label: "Team", kind: "text" },
  { key: "ppa", label: "PPA per play", labelMid: "PPA/play", labelShort: "PPA", format: "+2f" },
  { key: "passPpa", label: "PPA per pass", labelMid: "Pass", labelShort: "Pass", format: "+2f", size: "large" },
  { key: "rushPpa", label: "PPA per rush", labelMid: "Rush", labelShort: "Rush", format: "+2f", size: "large" },
  { key: "totalPpa", label: "Total PPA", labelShort: "Total", format: "+1f" },
  { key: "usage", label: "Usage", format: "pct", size: "medium" },
];

/** A player id the server matched: CFBD's ids are digit strings ("5132812") or positive numbers. */
function hasPlayerId(value) {
  return (typeof value === "string" && /^\d+$/.test(value.trim())) || (isNum(value) && value > 0);
}

/** The advanced box's players as table rows: the side's abbreviation, ours marked. Exported for the tests. */
export function advancedPlayerRows(players, { us, usAbbr = usLabel(), themAbbr = DASH } = {}) {
  return records(players)
    .filter((p) => typeof p.player === "string" && p.player.trim())
    .map((p) => {
      const ours = typeof us === "string" && p.team === us;
      return { ...p, name: p.player, side: ours ? text(usAbbr) : text(themAbbr), isUs: ours };
    });
}

/**
 * advancedBoxBlock(box, { us, them, usAbbr, themAbbr, usName, themName, onPlayer })
 * us/them: the two schools (the box's team keys); usName/themName the school and mascot for the two-team table's large
 * heads. onPlayer(row) opens a player's card: the row carries playerId (when the server matched the name), name,
 * position, team and isUs. A row without an id stays plain: no tap, no card.
 */
export function advancedBoxBlock(box, { us = usSchool(), them = null, usAbbr = usLabel(), themAbbr = DASH, usName, themName, onPlayer } = {}) {
  if (!box || typeof box !== "object" || !box.teams || typeof box.teams !== "object") return note("CFBD posts the advanced box score after the final.");
  const teams = box.teams;
  const a = teams[us] || {};
  const b = (them && teams[them]) || Object.entries(teams).find(([name]) => name !== us)?.[1] || {};
  // each row's direction, so the bar leans to the side that won it (the offense's line numbers: more is better, a run stuffed
  // is worse; the defense's havoc: more is better; the start: CFBD's yards to the goal, so fewer is better)
  const pair = (label, pick, format, higherIsBetter) => ({ label, higherIsBetter, us: { value: numOrNull(pick(a)), text: show(pick(a), format) }, them: { value: numOrNull(pick(b)), text: show(pick(b), format) } });
  const compare = [
    pair("Line yards per rush", (t) => t.line?.lineYards, "2f", true),
    pair("Stuff rate", (t) => t.line?.stuffRate, "pct", false),
    pair("Power success", (t) => t.line?.powerSuccess, "pct", true),
    pair("Second-level yards", (t) => t.line?.secondLevelYards, "2f", true),
    pair("Open-field yards", (t) => t.line?.openFieldYards, "2f", true),
    pair("Havoc (defense)", (t) => t.havoc?.total, "pct", true),
    pair("Havoc, front seven", (t) => t.havoc?.frontSeven, "pct", true),
    pair("Havoc, secondary", (t) => t.havoc?.db, "pct", true),
    pair("Average start, yards to goal", (t) => t.fieldPosition?.averageStart, "1f", false),
    pair("Scoring chances", (t) => t.scoring?.opportunities, "0f", true),
    pair("Points per scoring chance", (t) => t.scoring?.pointsPerOpportunity, "2f", true),
  ];
  const players = advancedPlayerRows(box.players, { us, usAbbr, themAbbr });
  const school = (value) => (typeof value === "string" && value.trim() ? value.trim() : undefined);
  return el(
    "div",
    { class: "d2" },
    // side by side only where each keeps its whole table (a 1400 px band): paired in the iPad's 755 px band they ran 7 px
    // past their halves even at small, and in the 1080p screen's 933 px band they were small; stacked, each is large
    el("div", { class: "adv-quarters" }, quarterTable(us, a, { school: us, side: "us" }), quarterTable(them || themAbbr, b, { school: them, side: "them" })),
    programSubhead("Line play, havoc, field position, finishing"),
    programTwoTeam({ rows: compare, usAbbr, themAbbr, usTeam: school(us), themTeam: school(them), usName: school(usName), themName: school(themName), tug: true, labelHead: "Both teams", caption: "Line play, havoc, field position, finishing" }),
    programSubhead("Players"),
    players.length
      ? statTable({ compact: true, sizes: true, columns: ADVANCED_PLAYER_COLUMNS, rows: players, sort: { key: "totalPpa", dir: "descending" }, rowClass: (row) => (row.isUs ? "is-us" : null), onRowTap: typeof onPlayer === "function" ? (row) => onPlayer(row) : undefined, canTap: (row) => hasPlayerId(row.playerId), caption: "Players' value" })
      : note("No player values for this game."),
    note(`From CFBD's advanced box score.${isNum(box.excitement) ? ` Excitement index ${fmtNum(box.excitement, 1)} (how much the win probability swung).` : ""}`),
  );
}

export { teamLink };
