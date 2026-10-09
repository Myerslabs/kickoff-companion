// A team page (T1) for any FBS team, reached from the program cover: header with tabs,
// Summary (tiles, stat tables with ranks, advanced), Schedule, Roster, Coaches, History.
//
// Phase 16 (stream SEASON): a Back row above the header (DS-03); the header's AP rank is a poll badge and its
// SP+ a dotted link to Ratings (design rule 19), with the last five results; every national number is a value
// with its chip in one cell, the chip opening the national (or conference) list with this team marked;
// Our schedule rows open the game, another team's rows promise no tap; the series reads from our
// side; sub-headings use the one subhead style (DS-14). The tab and the roster's sort survive refreshes.
// Phase 17 #2: the Summary tab ends with the team's conference standings; #team=<school>?band=standings (a
// cover's conference record chip) opens the page there.

import { confLabel, isUs, usSchool } from "../identity.js";
import { DASH, el, fmtDate, fmtNum, fmtStat, isNum, records, text } from "../ui/dom.js";
import { advancedPaired } from "../ui/depth2.js";
import { nationalHref, pollHref } from "../ui/national-link.js";
import { openGame, ratingsHref, scheduleList } from "../ui/schedule.js";
import { eloLine } from "../ui/sparkline.js";
import { backRow, band, note, subhead } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { pollBadge, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { logoLink, profileTable, profileTiles, teamHeader } from "../ui/team-page.js";
import { errorPanel, fetchJson, partState, poller, recordText } from "./common.js";
import { jumpToBand } from "./season.js";
import { openSheet } from "../ui/remote.js";
import { fillWiki, wikiLink } from "../ui/wiki-links.js";
import { openPlayer } from "./player.js";
import { costsBand } from "../ui/roster-costs.js";
import { blueChipNote } from "./roster.js";

const TABS = [{ id: "summary", label: "Summary" }, { id: "schedule", label: "Schedule" }, { id: "roster", label: "Roster" }, { id: "coaches", label: "Coaches" }, { id: "history", label: "History" }];

function schoolOf(data) {
  const name = data?.team?.school;
  return typeof name === "string" && name.trim() ? name.trim() : null;
}

/** GX-06: the team's Elo since week 1 with today's value, linked to the Elo column of Ratings. */
function eloFact(team) {
  const line = eloLine(team?.eloPath);
  if (!line) return null;
  const school = typeof team?.school === "string" ? team.school : null;
  return { label: "Elo", node: el("a", { class: "team-head__link team-head__elo", href: ratingsHref("elo", school), "aria-label": `Elo ${line.textContent}. Open the ratings` }, line) };
}

/** The header's facts: the AP rank as a poll badge, SP+ as a dotted link to Ratings with this team marked. */
function headerFacts(team) {
  const school = typeof team?.school === "string" ? team.school : null;
  const ap = isNum(team?.apRank) ? pollBadge(team.apRank, "AP", { href: pollHref("AP", { team: school }), label: school, showPoll: false }) : null;
  return [
    ap ? { label: "AP", node: ap } : { label: "AP", value: "NR" },
    isNum(team?.sp?.rank) ? { label: "SP+", value: `#${team.sp.rank}`, href: ratingsHref("sp", school), hint: "Open the ratings" } : { label: "SP+", value: DASH },
    eloFact(team),
  ].filter(Boolean);
}

/** The conference's short name for a rank column head: ours from the identity, another team's from its record. */
function confShort(data) {
  if (data?.team?.isUs) return confLabel();
  const name = data?.team?.conference;
  return typeof name === "string" && name.trim() ? name.trim() : "Conf";
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
    band({ id: bid("advanced"), title: "Advanced", collapsible: false, state: partState(data.parts?.advanced, adv.some((r) => isNum(r.value))), emptyText: "Advanced stats appear after the first game.", body: () => advancedPaired(adv, { team }) }),
  ];
}

function schedule(data) {
  const games = records(data.schedule);
  const isUs = Boolean(data.team?.isUs);
  // Our games open their archive or program; another team's games are not on our schedule,
  // so its rows promise no tap (G3-05, bug 10).
  return band({ id: "team-schedule", title: "Schedule", collapsible: false, state: partState(data.parts?.teamGames, games.length > 0), emptyText: "No schedule yet.", body: () => scheduleList({ games, nextGameId: (games.find((g) => !g.completed) || {}).gameId ?? null, onSelect: isUs ? openGame : undefined }) });
}

function roster(data, state) {
  const players = records(data.roster);
  const columns = [{ key: "number", label: "No." }, { key: "name", label: "Player", kind: "text", render: (row) => `${text(row.name)}${row.redshirt === true ? " (RS)" : ""}` }, { key: "position", label: "Pos", kind: "text" }, { key: "classYear", label: "Class", kind: "text" }, { key: "age", label: "Age" }, { key: "heightText", label: "Ht", kind: "text" }, { key: "weight", label: "Wt" }, { key: "hometown", label: "Hometown", kind: "text" }, { key: "transferFrom", label: "Transfer from", kind: "text", team: true }];
  return band({
    id: "team-roster",
    title: "Roster",
    collapsible: false,
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
        maxHeight: 520,
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
    body: () => statTable({ compact: true, columns: [{ key: "name", label: "Coach", kind: "text", sortable: false }, { key: "hired", label: "Hired", kind: "text", sortable: false }, { key: "recordText", label: "This season", kind: "text", sortable: false }, { key: "spOverall", label: "SP+", format: "1f", sortable: false }], rows: list.map((c) => ({ ...c, hired: c.hireDate ? fmtDate(c.hireDate) : DASH, recordText: isNum(c.wins) && isNum(c.losses) ? `${c.wins}-${c.losses}${c.ties ? `-${c.ties}` : ""}` : DASH })) }),
  }), staffBand(data)];
}

/** Phase 17 Part 3a: the coordinators from the season's coaches load, and for a primary team the whole staff. */
function staffBand(data) {
  const s = data.staff && typeof data.staff === "object" ? data.staff : null;
  const name = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
  const top = s ? [["Head coach", s.headCoach], ["Offensive coordinator", s.offensiveCoordinator], ["Defensive coordinator", s.defensiveCoordinator]].filter(([, v]) => name(v)) : [];
  const full = s ? records(s.full).filter((m) => name(m.name)) : [];
  return band({
    id: "team-staff",
    title: "Staff",
    collapsible: false,
    summary: s?.savedAt ? `the season's load, ${fmtDate(s.savedAt, "short")}` : "",
    state: top.length || full.length ? { status: "ready" } : { status: "empty", message: "Coordinators come from the season's coaches load on the Preseason page." },
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

/** One series game from our side: where it was played, the opponent, and 'W 31-24' with our score first. */
export function seriesRow(game, us = usSchool()) {
  const g = game && typeof game === "object" ? game : {};
  const home = g.homeTeam === us;
  const away = g.awayTeam === us;
  const usScore = home ? g.homeScore : away ? g.awayScore : null;
  const themScore = home ? g.awayScore : away ? g.homeScore : null;
  const opponent = home ? g.awayTeam : away ? g.homeTeam : null;
  const result = isNum(usScore) && isNum(themScore) ? (usScore > themScore ? "W" : usScore < themScore ? "L" : "T") : null;
  return {
    season: isNum(g.season) ? g.season : null,
    site: g.neutralSite === true ? "Neutral" : home ? "vs" : away ? "at" : DASH,
    opponent: typeof opponent === "string" && opponent.trim() ? opponent.trim() : null,
    result,
    score: result ? `${usScore}-${themScore}` : null,
    margin: result ? usScore - themScore : null,
  };
}

function resultCell(row) {
  if (!row.result) return DASH;
  return el("span", { class: `series-res res--${row.result.toLowerCase()}${row.result === "W" ? " series-res--win" : ""}` }, `${row.result} ${row.score}`);
}

function history(data) {
  const s = data.series && typeof data.series === "object" ? data.series : null;
  return band({
    id: "team-history",
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
        statTable({
          compact: true,
          sortable: false,
          columns: [
            { key: "season", label: "Year", dim: true },
            { key: "site", label: "Site", kind: "text" },
            { key: "opponent", label: "Opponent", kind: "text", team: true },
            { key: "margin", label: "Result", render: resultCell },
          ],
          rows: records(s?.lastTen).map((g) => seriesRow(g, usSchool())),
          caption: `Series history from ${usSchool()}'s side`,
        }),
        note(`${usSchool()}'s score first. vs is a home game, at a road game.`),
      ),
  });
}

function recruitingBand(data) {
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
  const columns = [
    { key: "label", label: "Measure", kind: "text" },
    { key: "value", label: "Value, FBS rank", render: (row) => fmtStat(row.value, row.format), rank: { key: "nationalRank", of: "nationalOf", link: (row) => nationalHref(row.metric, { team }), placeholder: true } },
  ];
  return band({
    id: "team-recruiting",
    title: "Talent and recruiting",
    collapsible: false,
    state: rows.length ? { status: "ready" } : { status: "empty", message: "Talent, blue-chip ratio and returning production appear once CFBD has them for this team." },
    body: () => el("div", { class: "prof" }, statTable({ compact: true, columns, rows }), r?.blueChip ? blueChipNote(r.blueChip) : null),
  });
}

function playValueBand(data) {
  const players = records(data.playValue?.players);
  const usage = records(data.playValue?.usage);
  const isUs = Boolean(data.team?.isUs);
  const columns = [{ key: "name", label: "Player", kind: "text", sub: "position", sortable: false }, { key: "plays", label: "Plays", sortable: false }, { key: "all", label: "PPA/play", format: "+2f", sortable: false }, { key: "pass", label: "Pass", format: "+2f", sortable: false }, { key: "rush", label: "Rush", format: "+2f", sortable: false }];
  const usageColumns = [{ key: "name", label: "Player", kind: "text", sub: "position", sortable: false }, { key: "overall", label: "Usage", format: "pct", sortable: false }, { key: "pass", label: "Pass", format: "pct", sortable: false }, { key: "rush", label: "Rush", format: "pct", sortable: false }];
  return band({
    id: "team-playvalue",
    title: "Play value and usage",
    collapsible: false,
    state: players.length || usage.length ? { status: "ready" } : { status: "empty", message: "Play value appears once CFBD grades the first game." },
    body: () => el("div", { class: "twocol" }, el("div", {}, subhead("PPA per play, at least 10 plays"), statTable({ compact: true, columns, rows: players, onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs }) })), el("div", {}, subhead("Usage"), statTable({ compact: true, columns: usageColumns, rows: usage, onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs }) }))),
  });
}

function location(data) {
  const loc = data.location && typeof data.location === "object" ? data.location : null;
  const place = loc ? [loc.city, loc.state].filter((v) => typeof v === "string" && v.trim()).join(", ") : "";
  return place || null;
}

/** The team's conference standings from /records (no extra call), the page's team marked. Null for an independent. */
function standingsBand(data) {
  const s = data.standings && typeof data.standings === "object" ? data.standings : null;
  if (!s) return null;
  const rows = records(s.rows);
  const conference = typeof s.conference === "string" && s.conference ? s.conference : "Conference";
  const columns = [
    { key: "place", label: "#", dim: true },
    { key: "team", label: "Team", kind: "text", render: (row) => logoLink(row.team, row) },
    { key: "confText", label: "Conf" },
    { key: "overallText", label: "Overall" },
    { key: "apRank", label: "AP", render: (row) => (isNum(row.apRank) ? pollBadge(row.apRank, "AP", { href: pollHref("AP", { team: row.team }), label: row.team, showPoll: false }) : el("span", { class: "nr" }, "NR")) },
  ];
  return band({
    id: "team-standings",
    title: `${conference} standings`,
    collapsible: false,
    foldable: true,
    summary: rows.length ? `${rows.length} teams` : "",
    state: partState(data.parts?.records, rows.length > 0),
    emptyText: "Standings appear after the first conference game.",
    body: () => el("div", { class: "tight" }, statTable({ compact: true, sortable: false, columns, rows: rows.map((row) => ({ ...row, confText: recordText(row.conference), overallText: recordText(row.overall) })), rowClass: (row) => (isUs(row.team) ? "is-us" : row.isUs ? "is-next" : null), caption: `${conference} standings` })),
  });
}

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const team = data.team && typeof data.team === "object" ? data.team : {};
  state.ui ??= {};
  const page = el("div", { class: "page team" });
  const bodies = {
    summary: () => [...summary(data, { prefix: "team-" }), recruitingBand(data), playValueBand(data), costsBand(data.costs, { id: "team-costs", team: schoolOf(data) }), standingsBand(data)],
    schedule: () => [schedule(data)],
    roster: () => [roster(data, state)],
    coaches: () => coaches(data),
    history: () => [history(data)],
  };
  if (!bodies[state.tab]) state.tab = "summary";
  let shown = [];
  const show = (id) => {
    for (const node of shown) node.remove();
    shown = bodies[id]().flat().filter(Boolean);
    page.append(...shown); // the flow places each new band as it arrives
  };
  const header = teamHeader({ team, season: String(data.season ?? ""), location: location(data), facts: headerFacts(team), tabs: TABS, current: state.tab, onTab: (id) => { state.tab = id; show(id); } });
  page.append(el("div", { class: "flow-full" }, backRow()), el("div", { class: "flow-full" }, header.root));
  show(state.tab);
  mountFlow(state.ui, container, page, { wide: TEAM_WIDE }); // final pass: the flowing page with its section chips
  if (state.focus && state.tab === "summary") {
    const target = state.focus;
    state.focus = null; // once: a refresh leaves the reader where they are
    setTimeout(() => jumpToBand(container.querySelector(target)), 0); // after the router's scroll to the top
  }
}

/** The flyout for a team other than ours: header, tiles, both stat tables, schedule, in a side sheet. */
export function openTeamFlyout(school) {
  const host = el("div", {}, band({ title: text(school), collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(8) }));
  const handle = openSheet({ title: text(school), body: host });
  fetchJson(`/api/team/${encodeURIComponent(school)}`)
    .then((envelope) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      const team = data.team && typeof data.team === "object" ? data.team : {};
      const header = teamHeader({ team, season: String(data.season ?? ""), location: location(data), facts: headerFacts(team), tabs: [] });
      host.replaceChildren(...[header.root, ...summary(data), schedule(data), standingsBand(data), data.series ? history(data) : null].filter(Boolean)); // final pass: no "null" text for a missing band
    })
    .catch((error) => host.replaceChildren(band({ title: text(school), collapsible: false, state: { status: "error", message: `${text(error?.message)}.` } })));
  return handle;
}

/** We get the full team page; everyone else the flyout. */
export function openTeam(school) {
  if (!school) return;
  if (isUs(school)) {
    window.location.hash = `team=${encodeURIComponent(usSchool())}`;
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
