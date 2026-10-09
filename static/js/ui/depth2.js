// Phase 13 (stats depth II): the table builders the Season, team, Game program, Archive and Live
// pages share. Tables only (design rule 2026-09-23), every value guarded: a missing number is a dash.
//
// advancedGroups(rows, { team })          one team's advanced season stats, a table per area; value and its
//                                         national chip in one cell, the chip linked to the national list
// advancedPaired(rows, { team })          G3-03: the same rows as ONE table, offense and defense paired on each
//                                         attribute (Metric | Offense | Defense, value and chip in each cell), the
//                                         areas as group rows; a one-sided attribute shows a dash on the other side
// matchupGroups(us, them, labels)         the same side by side for two teams
// adjustedMatchup(rows, labels)           opponent-adjusted metrics side by side (CFBD's WEPA)
// resumeBlock(resume, teamName)           expected wins, schedule strength (its rank a linked chip), the poll path
//                                         as poll badges
// tendenciesBlock(t, abbr)                an opponent's run and pass calls by situation, run direction, pass depth
// advancedBoxBlock(box, sides)            one finished game: by quarter, line play and havoc, players' value

import { usLabel, usSchool } from "../identity.js";
import { weekCell } from "./weeks.js";
import { DASH, el, fmtNum, fmtPct, fmtStat, isNum, records, teamLink, text } from "./dom.js";
import { metricLink, nationalHref, pollHref } from "./national-link.js";
import { note } from "./states.js";
import { pollBadge, rankChip, statTable } from "./stat-table.js";

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

/** A value column: the number right-aligned in the stat face with its national chip in the same cell (G3-02).
 *  Phase 17 #27: the header names both ("Value, FBS rank"). */
export const VALUE_RANK_LABEL = "Value, FBS rank";
export function valueColumn({ label = VALUE_RANK_LABEL, team, year, rankKey = "nationalRank", ofKey = "nationalOf", key = "value" } = {}) {
  return {
    key,
    label,
    sortKey: key,
    render: (row) => el("span", { "data-k": row?.key ? `v:${row.key}${year ? `:${year}` : ""}` : null }, show(row?.[key], row?.format)),
    rank: { key: rankKey, of: ofKey, link: metricLink({ team, year }), placeholder: true },
  };
}

export function advancedGroups(rows, { team } = {}) {
  const groups = groupRows(rows);
  if (![...groups.values()].flat().some((r) => isNum(r.value))) return note("Advanced stats appear after the first game.");
  return el(
    "div",
    { class: "d2 prof" },
    [...groups].map(([group, list]) =>
      el("div", {}, h4(group), statTable({ compact: true, columns: [{ key: "label", label: "Stat", kind: "text" }, valueColumn({ team })], rows: list, caption: `Advanced: ${group}` })),
    ),
  );
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
    if (!pair.label && typeof row.label === "string") pair.label = row.label;
  }
  const out = [];
  for (const [group, pairs] of groups) {
    out.push({ isGroup: true, label: group });
    for (const pair of pairs.values()) out.push(pair);
  }
  return out;
}

export function advancedPaired(rows, { team } = {}) {
  const paired = pairAdvanced(rows);
  if (!paired.some((r) => isNum(r.off) || isNum(r.def))) return note("Advanced stats appear after the first game.");
  const side = (prefix, label, divider) => ({
    key: prefix,
    label,
    divider,
    render: (row) => (row.isGroup ? el("span") : el("span", { "data-k": `adv:${prefix}:${text(row.attr)}` }, show(row[prefix], row[`${prefix}Format`]))),
    rank: { key: `${prefix}Rank`, of: `${prefix}Of`, link: (row) => (row.isGroup ? null : nationalHref(row[`${prefix}Metric`], { team })), placeholder: true },
  });
  return el(
    "div",
    { class: "prof tight adv-paired" },
    statTable({
      compact: true,
      sortable: false,
      columns: [{ key: "label", label: "Metric", kind: "text" }, side("off", "Offense", false), side("def", "Defense", true)],
      rows: paired,
      rowClass: (row) => (row.isGroup ? "is-parent" : null),
      caption: "Advanced, offense and defense",
    }),
    note("Nat is the national rank among FBS teams: 1 is the best on that measure, whichever way the number runs."),
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

export function resumeBlock(resume, teamName = usSchool()) {
  const r = resume && typeof resume === "object" ? resume : {};
  const sos = r.sosPlayed && typeof r.sosPlayed === "object" ? r.sosPlayed : null;
  const remaining = r.remaining && typeof r.remaining === "object" ? r.remaining : {};
  const team = typeof teamName === "string" && teamName.trim() ? teamName.trim() : usSchool();
  const summary = [
    { label: "Record", value: isNum(r.wins) && isNum(r.losses) ? `${r.wins}-${r.losses}` : DASH },
    { label: "Expected wins", value: isNum(r.expectedWins) ? `${fmtNum(r.expectedWins, 2)} of ${text(r.gamesCounted)}` : DASH },
    { label: "Wins above expected", value: isNum(r.luck) ? fmtStat(r.luck, "+2f") : DASH },
    {
      label: "Opponents played, average SP+",
      value: sos && isNum(sos.rating) ? fmtNum(sos.rating, 1) : DASH,
      chip: sos && isNum(sos.rank) ? rankChip(sos.rank, isNum(sos.of) ? sos.of : null, { href: nationalHref(sos.metric, { team }), label: "Strength of schedule played" }) : null,
    },
    { label: "Opponents to come, average SP+", value: isNum(remaining.averageSp) ? `${fmtNum(remaining.averageSp, 1)}${isNum(remaining.rankAmongPlayed) ? ` (would rank #${remaining.rankAmongPlayed} of ${text(remaining.of)} schedules played)` : ""}` : DASH },
  ];
  const games = records(remaining.games).map((g, i) => ({ order: i, week: weekCell(g), opponent: g.opponent, where: g.neutral ? "Neutral" : g.home ? "Home" : "Away", sp: g.sp }));
  const polls = records(r.polls).filter((p) => isNum(p.ap) || isNum(p.coaches));
  return el(
    "div",
    { class: "d2" },
    statTable({ compact: true, sortable: false, columns: [{ key: "label", label: "Résumé", kind: "text" }, { key: "value", label: "", kind: "text", render: (row) => (row.chip ? el("span", {}, text(row.value), row.chip) : text(row.value)) }], rows: summary }),
    note("Expected wins adds up CFBD's postgame win probability for each finished game: how often a team that played that way would have won. Strength of schedule is the average SP+ of FBS opponents; CFBD does not publish its own during the season."),
    games.length ? note("The rest of the schedule, with each opponent's record, rank, SP+ and form, is in the Road ahead band.") : null,
    polls.length
      ? el("div", {}, h4("Poll path"), statTable({ compact: true, sortable: false, columns: [{ key: "week", label: "Week" }, { key: "ap", label: "AP", render: (row) => pollCell(row.ap, "AP", team) }, { key: "coaches", label: "Coaches", render: (row) => pollCell(row.coaches, "Coaches", team) }], rows: polls.map((p) => ({ week: p.seasonType === "postseason" ? "Final" : p.week, ap: p.ap, coaches: p.coaches })), caption: "Poll path" }))
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

export function passZonesTable(zones) {
  const list = records(zones);
  const find = (depth, lane) => list.find((z) => z.depth === depth && z.direction === lane) || list.find((z) => z.key === `${depth}_${lane}`) || null;
  const cell = (zone) => {
    const att = countOf(zone?.attempts);
    return el(
      "td",
      { class: `zone${att ? "" : " zone--none"}` },
      el("b", { class: "zone__count" }, att === null ? DASH : `${att} att`),
      el("small", {}, att ? `${rateText(zone?.completionPct)} comp · ${rateText(zone?.successRate)} success` : "no throws"),
    );
  };
  return el(
    "div",
    { class: "stat-table-wrap zones-wrap" },
    el(
      "table",
      { class: "stat-table stat-table--compact zones" },
      el("caption", { class: "sr-only" }, "Passes by zone: deep over short, left to right"),
      el("thead", {}, el("tr", {}, el("th", { class: "txt", scope: "col" }, "Passes"), LANES.map(([, label]) => el("th", { scope: "col" }, label)))),
      el("tbody", {}, [["deep", "Deep"], ["short", "Short"]].map(([depth, label]) => el("tr", {}, el("th", { class: "txt", scope: "row" }, label), LANES.map(([lane]) => cell(find(depth, lane)))))),
    ),
  );
}

export function runLanesTable(lanes) {
  const list = records(lanes);
  const cell = (lane) => {
    const carries = countOf(lane?.carries);
    return el(
      "td",
      { class: `zone${carries ? "" : " zone--none"}` },
      el("b", { class: "zone__count" }, carries === null ? DASH : `${carries} car`),
      el("small", {}, carries ? `${isNum(lane?.yardsPerCarry) ? `${fmtNum(lane.yardsPerCarry, 1)} yds` : DASH} · ${rateText(lane?.successRate)} success` : "no runs"),
    );
  };
  return el(
    "div",
    { class: "stat-table-wrap zones-wrap" },
    el(
      "table",
      { class: "stat-table stat-table--compact zones" },
      el("caption", { class: "sr-only" }, "Runs by lane, left to right"),
      el("thead", {}, el("tr", {}, el("th", { class: "txt", scope: "col" }, "Runs"), LANES.map(([, label]) => el("th", { scope: "col" }, label)))),
      el("tbody", {}, el("tr", {}, el("th", { class: "txt", scope: "row" }, "Lane"), LANES.map(([key]) => cell(list.find((l) => l.key === key) || null)))),
    ),
  );
}

export function tendenciesBlock(t, abbr = DASH) {
  if (!t || typeof t !== "object" || !isNum(t.plays) || t.plays <= 0) return note("No plays from this opponent yet this season.");
  const situations = records(t.bySituation).filter((r) => isNum(r.plays) && r.plays > 0);
  const situationRows = situations.map((r) => ({
    label: text(r.label),
    plays: r.plays,
    runRate: isNum(r.runRate) ? fmtPct(r.runRate) : DASH,
    runRateValue: r.runRate,
    runYpp: r.run?.yardsPerPlay,
    runSuccess: madeOf(r.run?.success),
    passYpp: r.pass?.yardsPerPlay,
    passSuccess: madeOf(r.pass?.success),
  }));
  const dirRows = records(t.runDirection).map((r) => ({ label: text(r.label), plays: r.plays, ypp: r.yardsPerPlay, success: madeOf(r.success) }));
  const depthRows = records(t.passDepth).map((r) => ({ label: text(r.label), plays: r.plays, ypp: r.yardsPerPlay, success: madeOf(r.success) }));
  const split = [{ key: "label", label: "", kind: "text" }, { key: "plays", label: "Plays" }, { key: "ypp", label: "Yds/play", format: "1f" }, { key: "success", label: "Success", kind: "text" }];
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
    : el("div", { class: "twocol" }, el("div", {}, programSubhead("Where the runs go"), dirRows.some((r) => r.plays) ? statTable({ compact: true, sortable: true, columns: split, rows: dirRows }) : note("No run directions charted.")), el("div", {}, programSubhead("How deep the passes go"), depthRows.length ? statTable({ compact: true, sortable: true, columns: split, rows: depthRows }) : note("No pass depths charted.")));
  return el(
    "div",
    { class: "d2" },
    el("p", { class: "note" }, `${text(abbr)} over ${text(t.games)} games: ${text(t.plays)} snaps, runs ${isNum(t.runRate) ? fmtPct(t.runRate) : DASH} of the time (a sack counts as a called pass; kneels and spikes are left out).`),
    programSubhead("By down and distance"),
    statTable({ compact: true, sortable: true, columns: [{ key: "label", label: "Situation", kind: "text" }, { key: "plays", label: "Plays" }, { key: "runRate", label: "Run %", kind: "text", sortKey: "runRateValue" }, { key: "runYpp", label: "Run yds", format: "1f" }, { key: "runSuccess", label: "Run success", kind: "text" }, { key: "passYpp", label: "Pass yds", format: "1f" }, { key: "passSuccess", label: "Pass success", kind: "text" }], rows: situationRows }),
    where,
  );
}

// --- one finished game's advanced box score ----------------------------------------------------------------

const QUARTERS = [["quarter1", "Q1"], ["quarter2", "Q2"], ["quarter3", "Q3"], ["quarter4", "Q4"], ["total", "Game"]];

function quarterTable(team, block, { school, side } = {}) {
  const b = block && typeof block === "object" ? block : {};
  const line = (label, q, format) => {
    const row = { label };
    for (const [key, head] of QUARTERS) row[head] = show(q?.[key], format);
    return row;
  };
  const rows = [
    line("Success rate", b.success?.overall, "pct"),
    line("Success, standard downs", b.success?.standardDowns, "pct"),
    line("Success, passing downs", b.success?.passingDowns, "pct"),
    line("PPA per play", b.ppa?.overall, "+2f"),
    line("PPA per pass", b.ppa?.passing, "+2f"),
    line("PPA per rush", b.ppa?.rushing, "+2f"),
    line("Explosiveness", b.explosiveness, "2f"),
  ];
  return el("div", {}, programSubhead(text(team), { team: typeof school === "string" ? school : null, side }), statTable({ compact: true, columns: [{ key: "label", label: "By quarter", kind: "text" }, ...QUARTERS.map(([, head]) => ({ key: head, label: head, kind: "text" }))], rows }));
}

export function advancedBoxBlock(box, { us = usSchool(), them = null, usAbbr = usLabel(), themAbbr = DASH, onPlayer } = {}) {
  if (!box || typeof box !== "object" || !box.teams || typeof box.teams !== "object") return note("CFBD posts the advanced box score after the final.");
  const teams = box.teams;
  const a = teams[us] || {};
  const b = (them && teams[them]) || Object.entries(teams).find(([name]) => name !== us)?.[1] || {};
  const pair = (label, pick, format) => ({ label, us: { value: pick(a), text: show(pick(a), format) }, them: { value: pick(b), text: show(pick(b), format) } });
  const compare = [
    pair("Line yards per rush", (t) => t.line?.lineYards, "2f"),
    pair("Stuff rate", (t) => t.line?.stuffRate, "pct"),
    pair("Power success", (t) => t.line?.powerSuccess, "pct"),
    pair("Second-level yards", (t) => t.line?.secondLevelYards, "2f"),
    pair("Open-field yards", (t) => t.line?.openFieldYards, "2f"),
    pair("Havoc (defense)", (t) => t.havoc?.total, "pct"),
    pair("Havoc, front seven", (t) => t.havoc?.frontSeven, "pct"),
    pair("Havoc, secondary", (t) => t.havoc?.db, "pct"),
    pair("Average start, yards to goal", (t) => t.fieldPosition?.averageStart, "1f"),
    pair("Scoring chances", (t) => t.scoring?.opportunities, "0f"),
    pair("Points per scoring chance", (t) => t.scoring?.pointsPerOpportunity, "2f"),
  ];
  const players = records(box.players).map((p) => ({ ...p, side: p.team === us ? usAbbr : themAbbr }));
  const playerColumns = [{ key: "player", label: "Player", kind: "text", sub: "position" }, { key: "side", label: "Team", kind: "text" }, { key: "ppa", label: "PPA/play", format: "+2f" }, { key: "passPpa", label: "Pass", format: "+2f" }, { key: "rushPpa", label: "Rush", format: "+2f" }, { key: "totalPpa", label: "Total PPA", format: "+1f" }, { key: "usage", label: "Usage", format: "pct" }];
  return el(
    "div",
    { class: "d2" },
    el("div", { class: "twocol" }, quarterTable(us, a, { school: us, side: "us" }), quarterTable(them || themAbbr, b, { school: them, side: "them" })),
    programSubhead("Line play, havoc, field position, finishing"),
    programTwoTeam({ rows: compare, usAbbr, themAbbr, better: false, labelHead: "Both teams", caption: "Line play, havoc, field position, finishing" }),
    programSubhead("Players"),
    players.length ? statTable({ compact: true, columns: playerColumns, rows: players, sort: { key: "totalPpa", dir: "descending" }, maxHeight: 520, onRowTap: typeof onPlayer === "function" ? onPlayer : undefined }) : note("No player values for this game."),
    note(`From CFBD's advanced box score.${isNum(box.excitement) ? ` Excitement index ${fmtNum(box.excitement, 1)} (how much the win probability swung).` : ""}`),
  );
}

export { teamLink };
