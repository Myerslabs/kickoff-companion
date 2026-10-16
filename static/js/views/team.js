// A team page (T1) for any FBS team, reached from the program cover: header with tabs,
// Summary (tiles, stat tables with ranks, advanced), Schedule, Roster, Coaches, History (the school's history and facts from
// the facts prompt, the Prompts phase 2026-10-13, then the series with us).
//
// Phase 16 (stream SEASON): a Back row above the header (DS-03); the header's AP rank is a poll badge and its
// SP+ a dotted link to Ratings (design rule 19), with the last five results; every national number is a value
// with its chip in one cell, the chip opening the national (or conference) list with this team marked;
// Our schedule rows open the game, another team's rows promise no tap; the series reads from our
// side; sub-headings use the one subhead style (DS-14). The tab and the roster's sort survive refreshes.
// Phase 17 #2: the Summary tab ends with the team's conference standings; #team=<school>?band=standings (a
// cover's conference record chip) opens the page there.
// Tables wave 3 (owner 2026-10-10, docs/03-DESIGN.md "Table sizes"): every table sizes itself by its own box, each data
// point in its own column. Talent and recruiting: Measure | Value | FBS rank (medium). Play value and usage: the player
// (stepping down with the table, item 6) with his position in its own column at large and medium, sorted by the value. Coaches: the
// hire date (its year at small, sorting by the day), the record (This season, "Record" at small), SP+ and SRS (large).
// The series is the Pre-Game Program's table (ui/series.js), newest first. The standings are the Season page's
// (standingsTable), the conference's short name over its record, the last five at large. The side sheet's bands carry
// their own ids (sheet-schedule, sheet-standings, sheet-history), so a team page under the sheet keeps its own.

import { confLabel, isUs, usLabel, usSchool } from "../identity.js";
import { DASH, el, fmtDate, fmtNum, fmtStat, isNum, records, text } from "../ui/dom.js";
import { advancedPaired } from "../ui/depth2.js";
import { nationalHref, pollHref } from "../ui/national-link.js";
import { seriesTable } from "../ui/series.js";
import { openGame, ratingsHref, scheduleList } from "../ui/schedule.js";
import { eloLine } from "../ui/sparkline.js";
import { backRow, band, note, subhead } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { pollBadge, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { profileTable, profileTiles, standingsTable, teamHeader } from "../ui/team-page.js";
import { errorPanel, fetchJson, partState, poller } from "./common.js";
import { jumpToBand } from "./season.js";
import { openSheet } from "../ui/remote.js";
import { goTo } from "../ui/layers.js";
import { fillWiki, wikiLink } from "../ui/wiki-links.js";
import { openPlayer } from "./player.js";
import { costsBand } from "../ui/roster-costs.js";
import { blueChipNote } from "./roster.js";
import { injurySheetBand } from "./injuries.js";
import { factsBand } from "../ui/school-facts.js";

const TABS = [{ id: "summary", label: "Summary" }, { id: "schedule", label: "Schedule" }, { id: "roster", label: "Roster" }, { id: "coaches", label: "Coaches" }, { id: "history", label: "History" }];

function schoolOf(data) {
  const name = data?.team?.school;
  return typeof name === "string" && name.trim() ? name.trim() : null;
}

/** A string's trimmed words, or null for a blank or anything else. */
function words(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** GX-06: the team's Elo since week 1 with today's value, linked to the Elo column of Ratings. */
function eloFact(team) {
  const line = eloLine(team?.eloPath);
  if (!line) return null;
  const school = typeof team?.school === "string" ? team.school : null;
  return { label: "Elo", node: el("a", { class: "team-head__link team-head__elo", href: ratingsHref("elo", school), "aria-label": `Elo ${line.textContent}. Open the ratings` }, line) };
}

/** The header's facts: the AP rank as a poll badge, SP+ as a dotted link to Ratings with this team marked. */
function headerFacts(team, facts = null) {
  const school = typeof team?.school === "string" ? team.school : null;
  const ap = isNum(team?.apRank) ? pollBadge(team.apRank, "AP", { href: pollHref("AP", { team: school }), label: school, showPoll: false }) : null;
  const f = facts && typeof facts === "object" ? facts : null; // wave B: the school's facts, where loaded
  const titles = Array.isArray(f?.nationalTitles) ? f.nationalTitles.filter(isNum).length : 0;
  return [
    ap ? { label: "AP", node: ap } : { label: "AP", value: "NR" },
    isNum(team?.sp?.rank) ? { label: "SP+", value: `#${team.sp.rank}`, href: ratingsHref("sp", school), hint: "Open the ratings" } : { label: "SP+", value: DASH },
    eloFact(team),
    f && isNum(f.founded) ? { label: "Founded", value: String(f.founded) } : null,
    f && titles ? { label: "Titles", value: String(titles), hint: `National titles: ${f.nationalTitles.filter(isNum).join(", ")}` } : null,
  ].filter(Boolean);
}

/** The conference's short name for a rank column head: ours from the identity, another team's from the server's short
 *  name for the conference it is ranked in (wave 3: "PA rank", never "Pancake Athletic rank"), else its full name. */
function confShort(data) {
  if (data?.team?.isUs) return confLabel();
  for (const name of [data?.team?.conferenceShort, data?.team?.conference]) if (typeof name === "string" && name.trim()) return name.trim();
  return "Conf";
}

/** The Summary tab's top: the tiles, then Offense, Defense and Advanced as bands (ids on the page, none in the flyout). */
function summary(data, { prefix = null } = {}) {
  const bid = (name) => (prefix ? `${prefix}${name}` : undefined);
  const team = schoolOf(data);
  const rows = records(data.profile?.rows);
  const has = rows.some((r) => isNum(r.value));
  const adv = records(data.advanced?.rows);
  const statsState = partState(data.parts?.stats, has);
  return [
    el("div", { class: "flow-full" }, profileTiles(rows, { team })),
      band({ id: bid("offense"), title: "Offense", collapsible: false, state: statsState, emptyText: "Season stats appear after the first game.", body: () => profileTable(rows, "offense", { team, conferenceLabel: confShort(data) }) }),
      band({ id: bid("defense"), title: "Defense", collapsible: false, state: statsState, emptyText: "Season stats appear after the first game.", body: () => profileTable(rows, "defense", { team, conferenceLabel: confShort(data) }) }),
    band({ id: bid("advanced"), title: "Advanced", collapsible: false, state: partState(data.parts?.advanced, adv.some((r) => isNum(r.value))), emptyText: "Advanced stats appear after the first game.", body: () => advancedPaired(adv, { team, conferenceLabel: confShort(data) }) }),
  ];
}

function schedule(data, { id = "team-schedule" } = {}) {
  const games = records(data.schedule);
  const isUs = Boolean(data.team?.isUs);
  // Our games open their archive or program; another team's games are not on our schedule,
  // so its rows promise no tap (G3-05, bug 10).
  return band({ id, title: "Schedule", collapsible: false, state: partState(data.parts?.teamGames, games.length > 0), emptyText: "No schedule yet.", body: () => scheduleList({ games, nextGameId: (games.find((g) => !g.completed) || {}).gameId ?? null, onSelect: isUs ? openGame : undefined }) });
}

/** A roster's player column (item 6): CFBD's first and last name, the redshirt mark kept after whichever form shows. */
const ROSTER_NAME = { key: "name", label: "Player", kind: "text", person: { first: "firstName", last: "lastName", after: (row) => (row.redshirt === true ? " (RS)" : "") } };

function roster(data, state, { id = "team-roster", collapsed = false } = {}) {
  const players = records(data.roster);
  // sized by its own box (owner 2026-10-10): never sideways, the head pinned; size is the smallest size that still shows a column.
  // The name steps down with the table (item 6) from CFBD's split, "(RS)" after whichever form shows (it is data)
  const columns = [{ key: "number", label: "No.", labelShort: "#" }, ROSTER_NAME, { key: "position", label: "Pos", kind: "text" }, { key: "classYear", label: "Class", kind: "text" }, { key: "age", label: "Age", size: "medium" }, { key: "heightText", label: "Ht", kind: "text", sortKey: "height", size: "medium" }, { key: "weight", label: "Wt", size: "medium" }, { key: "hometown", label: "Hometown", kind: "text", size: "large" }, { key: "transferFrom", label: "Transfer from", kind: "text", team: true, size: "large" }];
  return band({
    id,
    title: "Roster",
    collapsed,
    collapsible: false,
    foldable: true, // every player on the page, no scroll box: the band folds instead (owner 2026-10-10)
    summary: `${players.length} players`,
    state: partState(data.parts?.teamRoster, players.length > 0),
    emptyText: "No roster yet.",
    body: () =>
      statTable({
        columns,
        rows: players.map((p) => ({ ...p, transferFrom: p?.transfer && typeof p.transfer.from === "string" ? p.transfer.from : null })),
        sort: state.sorts.roster || { key: "number", dir: "ascending" },
        onSort: (sort) => {
          state.sorts.roster = sort; // the reader's order survives a refresh (G3-06)
        },
        compact: true,
        sizes: true,
        onRowTap: (p) => openPlayer(p.playerId, { ...p, isUs: Boolean(data.team?.isUs) }),
      }),
  });
}

function coaches(data) {
  const list = records(data.coaches);
  return [band({
    id: "team-coaches",
    title: "Coaches",
    collapsible: false,
    state: partState(data.parts?.coaches, list.length > 0),
    emptyText: "CFBD lists no coach for this team this season.",
    body: () => {
      // owner bug 2026-10-10: a tap on a coach did nothing here. Each name opens the coach's own Wikipedia page, as on the Staff band
      const school = data.team?.school || null;
      // wave 3: sized by its own box. The hire date is its year at small and sorts by the day it names; SRS at large.
      const wrap = statTable({
        compact: true,
        sizes: true,
        columns: [
          { key: "name", label: "Coach", kind: "text", render: (c) => (typeof c.name === "string" && c.name.trim() ? wikiLink("coach", { person: c.name.trim(), team: school }, c.name.trim()) : DASH) },
          { key: "hired", label: "Hired", kind: "text", shortKey: "hiredYear", sortKey: "hiredAt" },
          { key: "recordText", label: "This season", labelShort: "Record", kind: "text" },
          { key: "spOverall", label: "SP+", format: "1f" },
          { key: "srs", label: "SRS", format: "1f", size: "large" },
        ],
        rows: list.map(coachRow),
      });
      fillWiki(wrap);
      return wrap;
    },
  }), staffBand(data)];
}

/** One coach as the table reads him: the hire date (its year for the small table, the moment it names to sort by) and
 *  the season's record; every field guarded. Exported for the tests. */
export function coachRow(coach) {
  const c = coach && typeof coach === "object" ? coach : {};
  const at = typeof c.hireDate === "string" && c.hireDate.trim() ? Date.parse(c.hireDate) : NaN;
  const year = typeof c.hireDate === "string" ? /^(\d{4})/.exec(c.hireDate.trim()) : null;
  return {
    ...c,
    hired: Number.isFinite(at) ? fmtDate(c.hireDate) : DASH,
    hiredYear: year ? year[1] : null,
    hiredAt: Number.isFinite(at) ? at : null,
    recordText: isNum(c.wins) && isNum(c.losses) ? `${c.wins}-${c.losses}${isNum(c.ties) && c.ties > 0 ? `-${c.ties}` : ""}` : DASH,
    spOverall: isNum(c.spOverall) ? c.spOverall : null,
    srs: isNum(c.srs) ? c.srs : null,
  };
}

/** Phase 17 Part 3a: the coordinators from the season's coaches load, and for a primary team the whole staff. */
function staffBand(data) {
  const s = data.staff && typeof data.staff === "object" ? data.staff : null;
  const name = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
  const top = s ? [["Head coach", s.headCoach], ["Offensive coordinator", s.offensiveCoordinator], ["Defensive coordinator", s.defensiveCoordinator]].filter(([, v]) => name(v)) : [];
  // owner bug 2026-10-10: the three at the top were listed again in the full staff; the full list now carries the rest
  const named = new Set(top.map(([, v]) => name(v).toLowerCase()));
  const full = s ? records(s.full).filter((m) => name(m.name) && !named.has(name(m.name).toLowerCase())) : [];
  return band({
    id: "team-staff",
    title: "Staff",
    collapsible: false,
    summary: s?.savedAt ? `the season's load, ${fmtDate(s.savedAt, "short")}` : "",
    state: top.length || full.length ? { status: "ready" } : { status: "empty", message: "Coordinators come from the season's coaches load in the Preseason Magazine." },
    body: () => {
      // Phase 19: each coach's name opens his own Wikipedia page
      const school = data.team?.school || null;
      const link = (who) => wikiLink("coach", { person: who, team: school }, who);
      const node = el(
        "div",
        { style: { padding: "var(--sp-2) var(--sp-3)" } },
        top.length ? el("dl", { class: "staff-list" }, top.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, link(name(v)))])) : null,
        full.length ? el("ul", { class: "preseason__items preseason__items--cols" }, full.map((m) => el("li", {}, el("b", {}, link(m.name)), name(m.role) ? `, ${m.role}` : null))) : null,
      );
      fillWiki(node);
      return node;
    },
  });
}

/** The series as the Pre-Game Program draws it (ui/series.js, wave 3): Year | Away | Home | Score | Winner | Result, our
 *  score first in the result, newest first; the schools' abbreviations at small (ours from the identity, the page's from
 *  its team). */
function history(data, { id = "team-history" } = {}) {
  const s = data.series && typeof data.series === "object" ? data.series : null;
  const abbrs = { [usSchool()]: usLabel() };
  const school = schoolOf(data);
  if (school && words(data.team?.abbreviation)) abbrs[school] = words(data.team.abbreviation);
  return band({
    id,
    title: `Series with ${usSchool()}`,
    collapsible: false,
    summary: s ? `${usSchool()} ${text(s.usWins)}, ${text(data.team?.abbreviation)} ${text(s.themWins)}${s.ties ? `, ${s.ties} ties` : ""}` : "",
    state: data.team?.isUs ? { status: "empty", message: `This is ${usSchool()}'s own page; series history lives on each opponent's page.` } : partState(data.parts?.series, Boolean(s)),
    emptyText: "No games between these teams on record.",
    body: () =>
      el(
        "div",
        {},
        s?.streak ? note(`${text(s.streak.team)} has won ${text(s.streak.games)} straight.`) : null,
        seriesTable(s, { us: usSchool(), abbrs, caption: `Series history from ${usSchool()}'s side` }),
        note(`${usSchool()}'s score first in the result.`),
      ),
  });
}

function recruitingBand(data, { id = "team-recruiting" } = {}) {
  const r = data.recruiting && typeof data.recruiting === "object" ? data.recruiting : null;
  const team = schoolOf(data);
  const rows = [];
  if (r?.talent) rows.push({ key: "talent", label: "Talent composite", value: r.talent.talent, format: "0f", nationalRank: r.talent.rank, nationalOf: r.talent.of, metric: r.talent.metric });
  // Blue-chip and returning ranks come from the national pulls; no rank means a plain value.
  if (r?.blueChip && isNum(r.blueChip.ratio)) rows.push({ key: "blueChip", label: "Blue-chip ratio", value: r.blueChip.ratio, format: "pct", nationalRank: r.blueChip.nationalRank, nationalOf: r.blueChip.nationalOf, metric: r.blueChip.metric });
  if (r?.returning && typeof r.returning === "object") {
    const ranks = r.returning.ranks && typeof r.returning.ranks === "object" ? r.returning.ranks : {};
    const metrics = r.returning.metrics && typeof r.returning.metrics === "object" ? r.returning.metrics : {};
    const ret = (key, rowKey, label) => {
      const ranked = ranks[key] && typeof ranks[key] === "object" ? ranks[key] : {};
      rows.push({ key: rowKey, label, value: r.returning[key], format: "pct", nationalRank: ranked.rank, nationalOf: ranked.of, metric: metrics[key] });
    };
    ret("percentPPA", "retPPA", "Returning production (PPA)");
    ret("percentPassing", "retPass", "Returning passing");
    ret("percentReceiving", "retRec", "Returning receiving");
    ret("percentRushing", "retRush", "Returning rushing");
    ret("usage", "retUsage", "Returning usage");
  }
  // wave 3 (rule 3): the value and its FBS rank in columns of their own; the measure's words shorten with the size
  const columns = [
    { key: "label", label: "Measure", kind: "text" },
    { key: "value", label: "Value", render: (row) => fmtStat(row.value, row.format) },
    { key: "nationalRank", label: "FBS rank", labelMid: "FBS", kind: "rank", of: "nationalOf", size: "medium", link: (row) => nationalHref(row.metric, { team }) },
  ];
  return band({
    id,
    title: "Talent and recruiting",
    collapsible: false,
    state: rows.length ? { status: "ready" } : { status: "empty", message: "Talent, blue-chip ratio and returning production appear once CFBD has them for this team." },
    body: () => el("div", { class: "prof" }, statTable({ compact: true, sizes: true, columns, rows, caption: "Talent and recruiting" }), r?.blueChip ? blueChipNote(r.blueChip) : null),
  });
}

/** The play value and usage tables' player column: the name (stepping down with the table, item 6) and the position in a
 *  column of its own at large and medium (wave 3, decision 1). */
const PLAYER_COLUMN = { key: "name", label: "Player", kind: "text", person: true, sub: "position", subLabel: "Pos" };

function playValueBand(data, state) {
  const players = records(data.playValue?.players);
  const usage = records(data.playValue?.usage);
  const isUs = Boolean(data.team?.isUs);
  const sorts = state && state.sorts && typeof state.sorts === "object" ? state.sorts : {};
  // wave 3: sized by their own boxes, the players sorted by the value (the reader's order survives a refresh)
  const columns = [PLAYER_COLUMN, { key: "plays", label: "Plays", size: "medium" }, { key: "all", label: "PPA per play", labelMid: "PPA/play", labelShort: "PPA", format: "+2f" }, { key: "pass", label: "Pass", format: "+2f" }, { key: "rush", label: "Rush", format: "+2f" }];
  const usageColumns = [PLAYER_COLUMN, { key: "overall", label: "Usage", format: "pct" }, { key: "pass", label: "Pass", format: "pct" }, { key: "rush", label: "Rush", format: "pct" }];
  const table = (key, cols, rows, first, caption) =>
    statTable({
      compact: true,
      sizes: true,
      columns: cols,
      rows,
      sort: sorts[key] || first,
      onSort: (sort) => {
        sorts[key] = sort;
      },
      onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs }),
      caption,
    });
  return band({
    id: "team-playvalue",
    title: "Play value and usage",
    collapsible: false,
    state: players.length || usage.length ? { status: "ready" } : { status: "empty", message: "Play value appears once CFBD grades the first game." },
    body: () => el("div", { class: "twocol" }, el("div", {}, subhead("PPA per play, at least 10 plays"), table("playValue", columns, players, { key: "all", dir: "descending" }, "PPA per play")), el("div", {}, subhead("Usage"), table("usage", usageColumns, usage, { key: "overall", dir: "descending" }, "Usage"))),
  });
}

function location(data) {
  const loc = data.location && typeof data.location === "object" ? data.location : null;
  const place = loc ? [loc.city, loc.state].filter((v) => typeof v === "string" && v.trim()).join(", ") : "";
  return place || null;
}

/** The team's conference standings from /records (no extra call), the page's team marked. Null for an independent.
 *  Wave 3: the Season page's standings (standingsTable): the conference's short name over its record, the AP rank from
 *  medium, the last five at large; teams sort, the reader's order kept across refreshes. */
function standingsBand(data, state, { id = "team-standings" } = {}) {
  const s = data.standings && typeof data.standings === "object" ? data.standings : null;
  if (!s) return null;
  const rows = records(s.rows);
  const conference = words(s.conference) || "Conference";
  const sorts = state && state.sorts && typeof state.sorts === "object" ? state.sorts : {};
  return band({
    id,
    title: `${conference} standings`,
    collapsible: false,
    foldable: true,
    summary: rows.length ? `${rows.length} teams` : "",
    state: partState(data.parts?.records, rows.length > 0),
    emptyText: "Standings appear after the first conference game.",
    body: () =>
      el(
        "div",
        { class: "tight" },
        standingsTable(rows, {
          conference: words(s.conferenceShort) || conference,
          rowClass: (row) => (isUs(row.team) ? "is-us" : row.isUs ? "is-next" : null),
          caption: `${conference} standings`,
          sort: sorts.standings,
          onSort: (sort) => {
            sorts.standings = sort;
          },
        }),
      ),
  });
}

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const team = data.team && typeof data.team === "object" ? data.team : {};
  state.ui ??= {};
  const page = el("div", { class: "page team" });
  const bodies = {
    summary: () => [...summary(data, { prefix: "team-" }), recruitingBand(data), playValueBand(data, state), costsBand(data.costs, { id: "team-costs", team: schoolOf(data), outside: data.inLoadSet === false }), standingsBand(data, state)],
    schedule: () => [schedule(data)],
    roster: () => [roster(data, state)],
    coaches: () => coaches(data),
    history: () => [factsBand(data.facts, { id: "team-facts", school: schoolOf(data), outside: data.inLoadSet === false }), history(data)], // the Prompts phase: school history first
  };
  if (!bodies[state.tab]) state.tab = "summary";
  let shown = [];
  const show = (id) => {
    for (const node of shown) node.remove();
    shown = bodies[id]().flat().filter(Boolean);
    page.append(...shown); // the flow places each new band as it arrives
  };
  const header = teamHeader({ team, season: String(data.season ?? ""), location: location(data), facts: headerFacts(team, data.facts), tabs: TABS, current: state.tab, onTab: (id) => { state.tab = id; show(id); } });
  page.append(el("div", { class: "flow-full" }, backRow()), el("div", { class: "flow-full" }, header.root));
  show(state.tab);
  mountFlow(state.ui, container, page, { wide: TEAM_WIDE }); // final pass: the flowing page with its section chips
  if (state.focus && state.tab === "summary") {
    const target = state.focus;
    state.focus = null; // once: a refresh leaves the reader where they are
    setTimeout(() => jumpToBand(container.querySelector(target)), 0); // after the router's scroll to the top
  }
}

/** The flyout for a team other than ours: header, tiles, schedule, the stat tables, injuries, roster, recruiting, in a side sheet. */
export function openTeamFlyout(school) {
  const host = el("div", {}, band({ title: text(school), collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(8) }));
  const handle = openSheet({ title: text(school), body: host });
  fetchJson(`/api/team/${encodeURIComponent(school)}`)
    .then((envelope) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      const team = data.team && typeof data.team === "object" ? data.team : {};
      const header = teamHeader({ team, season: String(data.season ?? ""), location: location(data), facts: headerFacts(team, data.facts), tabs: [] });
      const [tiles, ...statBands] = summary(data); // owner 2026-10-10: the schedule right under the four tiles, then the stat tables
      // owner 2026-10-10: every team's sheet carries its injury report (from our games' notes), its roster (folded: a long
      // list) and its recruiting, the same bands as the team page under their own ids so a page beneath keeps its own
      // (wave 3: the schedule, the standings and the series too, which once reused the page's ids)
      const sheet = { sorts: {} };
      const extra = [injurySheetBand(school), roster(data, sheet, { id: "sheet-roster", collapsed: true }), recruitingBand(data, { id: "sheet-recruiting" })];
      host.replaceChildren(...[header.root, tiles, schedule(data, { id: "sheet-schedule" }), ...statBands, ...extra, standingsBand(data, sheet, { id: "sheet-standings" }), factsBand(data.facts, { id: "sheet-facts", school, outside: data.inLoadSet === false }), data.series ? history(data, { id: "sheet-history" }) : null].filter(Boolean)); // final pass: no "null" text for a missing band
    })
    .catch((error) => host.replaceChildren(band({ title: text(school), collapsible: false, state: { status: "error", message: `${text(error?.message)}.` } })));
  return handle;
}

/** We get the full team page (from a sheet or the card, in the layer's own history entry: item 6); everyone else the
 *  flyout. */
export function openTeam(school) {
  if (!school) return;
  if (isUs(school)) {
    goTo(`team=${encodeURIComponent(usSchool())}`);
    return;
  }
  openTeamFlyout(school);
}

const TEAM_WIDE = ["team-advanced", "team-schedule", "team-roster", "team-playvalue"]; // the paired table, the schedule list, the roster and the two play-value tables take two columns

export function createTeamView({ onStatus, school, params } = {}) {
  const state = { tab: "summary", sorts: {}, focus: params?.band === "standings" ? "#team-standings" : null };
  const view = poller({
    url: `/api/team/${encodeURIComponent(school || "")}`,
    refreshMs: 30 * 60 * 1000,
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel(`Team page: ${text(school)}`, message, retry)),
    renderLoading: () => el("div", { class: "page" }, backRow(), el("div", { class: "skel skel--block", style: { height: "140px", margin: 0 } }), band({ title: "Summary", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(8) })),
  });
  return { ...view, unmount() { stopFlow(state.ui); view.unmount(); } };
}

export { fmtNum };
