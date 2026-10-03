// A team page (T1) for any FBS team, reached from the program cover: header with tabs,
// Summary (tiles, stat tables with ranks, advanced), Schedule, Roster, Coaches, History.
//
// Phase 16 (stream SEASON): a Back row above the header (DS-03); the header's AP rank is a poll badge and its
// SP+ a dotted link to Ratings (design rule 19), with the last five results; every national number is a value
// with its chip in one cell, the chip opening the national (or conference) list with this team marked;
// Our schedule rows open the game, another team's rows promise no tap; the series reads from our
// side; sub-headings use the one subhead style (DS-14). The tab and the roster's sort survive refreshes.

import { isUs, usSchool } from "../identity.js";
import { DASH, el, fmtDate, fmtNum, fmtStat, isNum, text } from "../ui/dom.js";
import { advancedPaired } from "../ui/depth2.js";
import { nationalHref, pollHref } from "../ui/national-link.js";
import { openGame, ratingsHref, scheduleList } from "../ui/schedule.js";
import { eloLine } from "../ui/sparkline.js";
import { backRow, band, note, subhead } from "../ui/states.js";
import { pollBadge, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { profileTable, profileTiles, teamHeader } from "../ui/team-page.js";
import { errorPanel, fetchJson, partState, poller } from "./common.js";
import { openSheet } from "../ui/remote.js";
import { openPlayer } from "./player.js";
import { blueChipNote } from "./roster.js";

const TABS = [{ id: "summary", label: "Summary" }, { id: "schedule", label: "Schedule" }, { id: "roster", label: "Roster" }, { id: "coaches", label: "Coaches" }, { id: "history", label: "History" }];

function records(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object") : [];
}

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

function summary(data) {
  const team = schoolOf(data);
  const rows = records(data.profile?.rows);
  const has = rows.some((r) => isNum(r.value));
  const adv = records(data.advanced?.rows);
  const statsState = partState(data.parts?.stats, has);
  return el(
    "div",
    { style: { display: "grid", gap: "var(--gap)" } },
    profileTiles(rows, { team }),
    el(
      "div",
      { class: "spread spread--2" },
      band({ title: "Offense", collapsible: false, state: statsState, emptyText: "Season stats appear after the first game.", body: () => profileTable(rows, "offense", { team, conferenceLabel: "Conf" }) }),
      band({ title: "Defense", collapsible: false, state: statsState, emptyText: "Season stats appear after the first game.", body: () => profileTable(rows, "defense", { team, conferenceLabel: "Conf" }) }),
    ),
    band({ title: "Advanced", collapsible: false, state: partState(data.parts?.advanced, adv.some((r) => isNum(r.value))), emptyText: "Advanced stats appear after the first game.", body: () => advancedPaired(adv, { team }) }),
  );
}

function schedule(data) {
  const games = records(data.schedule);
  const isUs = Boolean(data.team?.isUs);
  // Our games open their archive or program; another team's games are not on our schedule,
  // so its rows promise no tap (G3-05, bug 10).
  return band({ title: "Schedule", collapsible: false, state: partState(data.parts?.teamGames, games.length > 0), emptyText: "No schedule yet.", body: () => scheduleList({ games, nextGameId: (games.find((g) => !g.completed) || {}).gameId ?? null, onSelect: isUs ? openGame : undefined }) });
}

function roster(data, state) {
  const players = records(data.roster);
  const columns = [{ key: "number", label: "No." }, { key: "name", label: "Player", kind: "text" }, { key: "position", label: "Pos", kind: "text" }, { key: "classYear", label: "Class", kind: "text" }, { key: "heightText", label: "Ht", kind: "text" }, { key: "weight", label: "Wt" }, { key: "hometown", label: "Hometown", kind: "text" }, { key: "transferFrom", label: "Transfer from", kind: "text", team: true }];
  return band({
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
  return band({
    title: "Coaches",
    collapsible: false,
    state: partState(data.parts?.coaches, list.length > 0),
    emptyText: "CFBD lists no coach for this team this season.",
    body: () => statTable({ compact: true, columns: [{ key: "name", label: "Coach", kind: "text", sortable: false }, { key: "hired", label: "Hired", kind: "text", sortable: false }, { key: "recordText", label: "This season", kind: "text", sortable: false }, { key: "spOverall", label: "SP+", format: "1f", sortable: false }], rows: list.map((c) => ({ ...c, hired: c.hireDate ? fmtDate(c.hireDate) : DASH, recordText: isNum(c.wins) && isNum(c.losses) ? `${c.wins}-${c.losses}${c.ties ? `-${c.ties}` : ""}` : DASH })) }),
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
    { key: "value", label: "Value", render: (row) => fmtStat(row.value, row.format), rank: { key: "nationalRank", of: "nationalOf", link: (row) => nationalHref(row.metric, { team }), placeholder: true } },
  ];
  return band({
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

function render(envelope, container, state) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const team = data.team && typeof data.team === "object" ? data.team : {};
  const host = el("div", { class: "team-page", style: { padding: 0 } });
  const bodies = { summary: () => el("div", { style: { display: "grid", gap: "var(--gap)" } }, summary(data), recruitingBand(data), playValueBand(data)), schedule: () => schedule(data), roster: () => roster(data, state), coaches: () => coaches(data), history: () => history(data) };
  if (!bodies[state.tab]) state.tab = "summary";
  const header = teamHeader({ team, season: String(data.season ?? ""), location: location(data), facts: headerFacts(team), tabs: TABS, current: state.tab, onTab: (id) => { state.tab = id; host.replaceChildren(bodies[id]()); } });
  host.append(bodies[state.tab]());
  container.replaceChildren(el("div", { class: "page" }, backRow(), header.root, host));
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
      host.replaceChildren(header.root, summary(data), schedule(data), data.series ? history(data) : null);
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

export function createTeamView({ onStatus, school } = {}) {
  const state = { tab: "summary", sorts: {} };
  return poller({
    url: `/api/team/${encodeURIComponent(school || "")}`,
    refreshMs: 30 * 60 * 1000,
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel(`Team page: ${text(school)}`, message, retry)),
    renderLoading: () => el("div", { class: "page" }, backRow(), el("div", { class: "skel skel--block", style: { height: "140px", margin: 0 } }), band({ title: "Summary", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(8) })),
  });
}

export { fmtNum };
