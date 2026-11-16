// The conference page (owner 2026-11-02: "Lets do the conference page first"; "Any conference, ours first"; the board
// "Build as drawn"): one page for a conference, ours first, a chip row
// for the other ten, in the one-column shape. Six bands in the board's order, each in the catalog (ui/band-catalog.js):
//   conf-against    the Conference SP+ table and, on a switch, each conference's teams averaged a game at a time
//   conf-standings  the standings with where each team can still finish; our What-we-need lines on our own conference
//   conf-week       this week's games with a team of the conference, the Picks of the week rows, the race's Pull for
//   conf-rated      every team by SP+, with Elo, FPI, talent and the Talent Edge percentile
//   conf-leaders    the top five of the full lists' lead stat in passing, rushing, receiving and defense
//   conf-land       each school's land on the Imperialism Map, the week's change, the conference's share
// One answer, /api/conference[/<name>] (app/services/conference.py), nothing fetched by the page itself. The address is
// #conference (ours) or #conference=<name>; the chips lead to the others. Under National in the menu; in New until he
// places it.
//
//   createConferenceView({ onStatus, arg, params })
//   BANDS, conferenceHref(name), headBlock(data), flatRated(rows)   exported for the tests

import { confName } from "../identity.js";
import { rememberView, rememberedView, viewSwitch } from "../ui/box-switch.js";
import { DASH, el, fmtNum, isNum, records, recordText, text } from "../ui/dom.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { helpsChip } from "../ui/race.js";
import { band, note } from "../ui/states.js";
import { rankChip, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { formSquares, logoLink, teamAbbrLink } from "../ui/team-page.js";
import { errorPanel, partState, poller } from "./common.js";
import { gameRow } from "./picks.js";
import { openPlayer } from "./player.js";

export const BANDS = ["conf-against", "conf-standings", "conf-week", "conf-rated", "conf-leaders", "conf-land"];
const AGAINST_VIEWS = [["sp", "SP+"], ["numbers", "By the numbers"]];
const LEADER_CATEGORIES = [["passing", "Passing"], ["rushing", "Rushing"], ["receiving", "Receiving"], ["defense", "Tackles"]];

const words = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
const ORDINAL = (n) => (isNum(n) ? `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th"}` : DASH);

/** "#conference" for ours, "#conference=Big%20Ten" for another. */
export function conferenceHref(name, { ours = false } = {}) {
  const n = typeof name === "string" && name.trim() ? name.trim() : null;
  return !n || ours ? "#conference" : `#conference=${encodeURIComponent(n)}`;
}

function confLink(name, current, { ours = false } = {}) {
  const n = typeof name === "string" && name.trim() ? name.trim() : null;
  if (!n) return DASH;
  if (n === current) return el("b", {}, n);
  return el("a", { class: "conf-link", href: conferenceHref(n, { ours }) }, n);
}

/** The page's head: the chip row (ours first), the name, the facts strip. Exported for the tests. */
export function headBlock(data) {
  const conf = data.conference && typeof data.conference === "object" ? data.conference : {};
  const name = text(conf.name) || confName();
  const chips = records(data.conferences).filter((c) => typeof c.name === "string" && c.name.trim()).map((c) =>
    el("a", {
      class: `conf-chips__chip${c.name === conf.name ? " is-on" : ""}`,
      href: conferenceHref(c.name, { ours: c.isOurs === true }),
      "aria-current": c.name === conf.name ? "page" : null,
      title: `${text(c.name)}${isNum(c.teams) ? `, ${c.teams} teams` : ""}`,
    }, text(c.short || c.name)),
  );
  const facts = [
    isNum(conf.spRank) ? [ORDINAL(conf.spRank), `of ${isNum(conf.spOf) ? conf.spOf : "the"} conferences in SP+`] : null,
    isNum(conf.teams) ? [String(conf.teams), "teams"] : null,
    isNum(conf.ranked) ? [String(conf.ranked), "in the AP Top 25"] : null,
    Array.isArray(data.week?.games) ? [String(data.week.games.length), "games this week"] : null,
    data.land?.available === true && isNum(data.land.pct) ? [`${Math.round(data.land.pct)}%`, "of the map"] : null,
  ].filter(Boolean);
  return el(
    "header",
    { class: "conf-head" },
    chips.length ? el("nav", { class: "conf-chips", "aria-label": "Conferences" }, chips) : null,
    el("h1", { class: "conf-head__name" }, name),
    el("p", { class: "conf-head__sub" }, [conf.isOurs === true && conf.ourTeam ? `Our conference` : null, "the title game takes the top two by conference record"].filter(Boolean).join(" · ")),
    facts.length ? el("div", { class: "conf-facts" }, facts.map(([big, words]) => el("div", { class: "conf-facts__item" }, el("b", {}, big), el("span", {}, words)))) : null,
  );
}

// --- against the rest ---------------------------------------------------------------------------------------------------

function againstBand(data, state, rerender) {
  const against = data.against && typeof data.against === "object" ? data.against : {};
  const name = text(data.conference?.name);
  const sp = records(against.sp).map((c) => ({ ...c, isUs: c.conference === name }));
  const numbers = against.numbers && typeof against.numbers === "object" ? against.numbers : {};
  const nRows = records(numbers.rows).map((c) => ({ ...c, isUs: c.conference === name }));
  const nCols = records(numbers.columns);
  const view = state.view;
  const switcher = viewSwitch(AGAINST_VIEWS, view, (id) => {
    state.view = id;
    rememberView("conference", id);
    rerender();
  });
  const link = (row) => confLink(row.conference, name, { ours: row.conference === confName() });
  const spTable = () => statTable({
    compact: true,
    sizes: true,
    columns: [
      { key: "rank", label: "Rank", kind: "rank", of: sp.length || null, sortable: true },
      { key: "conference", label: "Conference", kind: "text", render: link },
      { key: "rating", label: "SP+", format: "1f" },
      { key: "offense", label: "Offense", labelShort: "Off", format: "1f" },
      { key: "defense", label: "Defense", labelShort: "Def", format: "1f" },
      { key: "specialTeams", label: "Special", format: "2f", size: "medium" },
    ],
    rows: sp,
    sort: state.sorts.sp || { key: "rank", dir: "ascending" },
    onSort: (sort) => { state.sorts.sp = sort; },
    rowClass: (r) => (r.isUs ? "is-us" : null),
    caption: "Conference SP+",
  });
  const numbersTable = () => statTable({
    compact: true,
    sizes: true,
    columns: [
      { key: "conference", label: "Conference", kind: "text", stick: true, render: link, renderShort: (row) => confLink(row.short || row.conference, name) },
      { key: "teams", label: "Teams", format: "0f", dim: true, size: "large" },
      ...nCols.filter((c) => c && typeof c.key === "string").map((c, i) => ({ key: c.key, label: text(c.label), format: "1f", rank: { key: `${c.key}Rank`, of: isNum(numbers.of) ? numbers.of : nRows.length || null }, size: i >= 4 ? "medium" : undefined })),
    ],
    rows: nRows,
    sort: state.sorts.numbers || { key: nCols[0]?.key || "conference", dir: "descending" },
    onSort: (sort) => { state.sorts.numbers = sort; },
    rowClass: (r) => (r.isUs ? "is-us" : null),
    caption: "The conferences by the numbers",
  });
  const has = view === "numbers" ? nRows.length > 0 : sp.length > 0;
  return band({
    id: "conf-against",
    title: `${text(data.conference?.short || name)} against the rest`,
    collapsible: false,
    foldable: true,
    summary: view === "numbers" ? "each conference's teams averaged a game at a time, ranked among the conferences" : "Conference SP+ from CFBD, its offense, defense and special teams",
    tools: switcher,
    state: partState(view === "numbers" ? data.parts?.stats : data.parts?.ratings, has),
    emptyText: view === "numbers" ? "The averages appear once the season's team stats are in." : "Conference ratings appear once CFBD publishes them.",
    body: () => el("div", {}, view === "numbers" ? numbersTable() : spTable(), el("p", { class: "note" }, view === "numbers" ? "Each column is the average of the conference's teams, a game at a time, with the conference's rank among the eleven; from the full lists the Stats pages keep." : "The average SP+ of each conference's teams.")),
  });
}

// --- the standings --------------------------------------------------------------------------------------------------------

function finishWords(row) {
  if (row.raceStatus === "out") return "Out";
  if (row.raceStatus === "clinched") return "Clinched";
  if (isNum(row.bestPlace) && isNum(row.worstPlace)) return row.bestPlace === row.worstPlace ? ORDINAL(row.bestPlace) : `${ORDINAL(row.bestPlace)} to ${ORDINAL(row.worstPlace)}`;
  return DASH;
}

function standingsBand(data, state) {
  const block = data.standings && typeof data.standings === "object" ? data.standings : {};
  const rows = records(block.rows).map((r) => ({ ...r, confText: recordText(r.conference) || DASH, overallText: recordText(r.overall) || DASH, finish: finishWords(r), finishSort: isNum(r.bestPlace) ? r.bestPlace : 99 }));
  const race = block.race && typeof block.race === "object" ? block.race : null;
  const lines = race ? records(race.lines).filter((l) => typeof l.text === "string") : [];
  const short = text(data.conference?.short) || "Conf";
  return band({
    id: "conf-standings",
    title: "Standings",
    collapsible: false,
    foldable: true,
    summary: rows.length ? `${rows.length} teams · conference record first · the race played out: where each team can still finish` : "",
    state: partState(data.parts?.records, rows.length > 0),
    emptyText: "Standings appear after the first conference game.",
    body: () =>
      el(
        "div",
        { class: "tight" },
        statTable({
          compact: true,
          sizes: true,
          columns: [
            { key: "place", label: "#", dim: true },
            { key: "team", label: "Team", kind: "text", stick: true, render: (row) => logoLink(row.team, row), renderShort: (row) => teamAbbrLink(row.team, row.abbreviation) },
            { key: "confText", label: short },
            { key: "overallText", label: "Overall" },
            { key: "apRank", label: "AP", format: "0f", size: "medium" },
            { key: "form", label: "Last 5", size: "large", sortable: false, render: (row) => formSquares(row.form) || DASH },
            { key: "finish", label: "Can finish", kind: "text", sortKey: "finishSort", render: (row) => el("span", { class: `conf-finish${row.raceStatus === "out" ? " conf-finish--out" : ""}` }, row.finish) },
          ],
          rows,
          sort: state.sorts.standings || { key: "place", dir: "ascending" },
          onSort: (sort) => { state.sorts.standings = sort; },
          rowClass: (r) => (r.isUs ? "is-us" : null),
          caption: `${text(data.conference?.name)} standings`,
        }),
        lines.length ? el("ul", { class: "race__lines conf-lines" }, lines.map((line) => el("li", {}, el("strong", {}, text(line.lead)), " ", text(line.text)))) : null,
        el("p", { class: "note" }, block.ours === true ? "Can finish is each team's best and worst place with the conference games left played out. Our four lines show on our own conference only." : "Can finish is each team's best and worst place with the conference games left played out."),
      ),
  });
}

// --- this week -----------------------------------------------------------------------------------------------------------

function weekBand(data) {
  const week = data.week && typeof data.week === "object" ? data.week : {};
  const games = records(week.games);
  const short = text(data.conference?.short) || "the conference";
  const by = week.picksBy === "claude" ? "picked by Claude Code" : week.picksBy === "paper" ? "the paper's picks until Claude's" : "Claude picks Thursday afternoon";
  const record = week.record && isNum(week.record.right) && isNum(week.record.wrong) && week.record.right + week.record.wrong > 0 ? `${week.record.right}-${week.record.wrong} so far` : null;
  const rows = games.map((g) => {
    const li = gameRow(g);
    const chip = helpsChip(g.helps);
    const ours = g.helps && g.helps.ours === true ? el("span", { class: "helps-chip" }, el("i", { class: "helps-chip__dot", "aria-hidden": "true" }), "Our game") : null;
    const pick = li.querySelector(".picks__pick");
    if (pick && (chip || ours)) pick.append(el("div", { class: "conf-pull" }, chip || ours));
    if (g.conferenceGame === false) li.classList.add("conf-week__cross");
    return li;
  });
  return band({
    id: "conf-week",
    title: `This week in the ${short}`,
    collapsible: false,
    foldable: true,
    summary: [text(week.label || "This week"), games.length ? `${games.length} ${games.length === 1 ? "game" : "games"}` : null, by, record].filter(Boolean).join(" · "),
    state: week.available === false ? { status: "error", message: words(week.words) || "The week's games could not be read." } : { status: games.length ? "ready" : "empty", message: words(week.note) || "No games with a team of the conference this week." },
    body: () => el("div", { class: "picks" }, el("ul", { class: "picks__list" }, rows), el("p", { class: "note" }, "The same rows as Picks of the week, cut to the conference; a game against another conference reads lighter. Pull for is the race's word, on our conference only. A tap on a team opens its sheet.")),
  });
}

// --- the teams, rated -----------------------------------------------------------------------------------------------------

/** The server's rated rows flattened for the table. Exported for the tests. */
export function flatRated(rows) {
  return records(rows).filter((r) => typeof r.team === "string").map((r) => ({
    place: r.place,
    team: r.team,
    abbreviation: typeof r.abbreviation === "string" && r.abbreviation.trim() ? r.abbreviation.trim() : null,
    logo: r.logo,
    logoDark: r.logoDark,
    isUs: r.isUs === true,
    sp: r.sp?.rating, spRank: r.sp?.rank,
    off: r.spOffense?.rating, offRank: r.spOffense?.rank,
    def: r.spDefense?.rating, defRank: r.spDefense?.rank,
    elo: r.elo?.rating, eloRank: r.elo?.rank,
    fpi: r.fpi?.rating, fpiRank: r.fpi?.rank,
    talent: r.talent?.talent, talentRank: r.talent?.rank, talentOf: r.talent?.of,
    edge: r.talentEdge?.pct, edgeRank: r.talentEdge?.rank, edgeOf: r.talentEdge?.of,
  }));
}

function ratedBand(data, state) {
  const rows = flatRated(data.rated);
  const edgeOn = data.talentEdge?.available === true && rows.some((r) => isNum(r.edge));
  const of = 138;
  const columns = [
    { key: "place", label: "#", dim: true },
    { key: "team", label: "Team", kind: "text", stick: true, render: (row) => logoLink(row.team, row), renderShort: (row) => teamAbbrLink(row.team, row.abbreviation) },
    { key: "sp", label: "SP+", format: "1f", rank: { key: "spRank", of } },
    { key: "off", label: "Offense", labelShort: "Off", format: "1f", rank: { key: "offRank", of }, size: "medium" },
    { key: "def", label: "Defense", labelShort: "Def", format: "1f", rank: { key: "defRank", of }, size: "medium" },
    { key: "elo", label: "Elo", format: "0f", rank: { key: "eloRank", of } },
    { key: "fpi", label: "FPI", format: "1f", rank: { key: "fpiRank", of }, size: "medium" },
    { key: "talent", label: "Talent", format: "0f", rank: { key: "talentRank", of: "talentOf" }, size: "large" },
    edgeOn ? { key: "edge", label: "Talent Edge", labelShort: "Edge", format: "0f", rank: { key: "edgeRank", of: "edgeOf" }, size: "medium" } : null,
  ].filter(Boolean);
  return band({
    id: "conf-rated",
    title: "The teams, rated",
    collapsible: false,
    foldable: true,
    summary: [`by SP+ · the chip is the FBS rank`, edgeOn ? "the Talent Edge percentile" : null].filter(Boolean).join(" · "),
    state: partState(data.parts?.ratings, rows.length > 0),
    emptyText: "The ratings appear once CFBD publishes them for the season.",
    body: () => el("div", { class: "tight" }, statTable({ compact: true, sizes: true, columns, rows, sort: state.sorts.rated || { key: "place", dir: "ascending" }, onSort: (sort) => { state.sorts.rated = sort; }, rowClass: (r) => (r.isUs ? "is-us" : null), caption: "The teams, rated" }), el("p", { class: "note" }, `Elo is a results-only rating, FPI is ESPN's projection, talent is the 247Sports composite of the roster.${edgeOn ? " Talent Edge is the whole roster's percentile among FBS teams." : ""}`)),
  });
}

// --- the leaders ------------------------------------------------------------------------------------------------------------

function leaderTable(block, title) {
  const rows = records(block?.rows).filter((r) => typeof r.player === "string").map((r, i) => ({ ...r, place: i + 1, who: [text(r.position), text(r.abbreviation || r.team)].filter(Boolean).join(" · ") }));
  const label = text(block?.label || block?.lead || "Value");
  return el(
    "div",
    { class: "conf-leaders__one" },
    el("h4", { class: "d2-head" }, title),
    rows.length
      ? statTable({
          compact: true,
          columns: [
            { key: "place", label: "#", dim: true },
            { key: "player", label: "Player", kind: "text", person: true, sub: "who" },
            { key: "value", label: label, format: "0f", rank: { key: "rank", of: null } },
          ].filter(Boolean),
          rows,
          sortable: false,
          rowClass: (r) => (r.isUs ? "is-us" : null),
          onRowTap: (row) => openPlayer(row.playerId, row),
          canTap: (row) => isNum(row.playerId) || /^\d+$/.test(String(row.playerId ?? "")),
          caption: title,
        })
      : note(block?.available === false ? "This list could not be read; the app tries again." : "Nobody from the conference on this list yet.", { kind: block?.available === false ? "error" : "empty" }),
  );
}

function leadersBand(data) {
  const leaders = data.leaders && typeof data.leaders === "object" ? data.leaders : {};
  const any = LEADER_CATEGORIES.some(([key]) => records(leaders[key]?.rows).length > 0);
  return band({
    id: "conf-leaders",
    title: "Leaders",
    collapsible: false,
    foldable: true,
    summary: "the conference's players atop the full lists · a tap opens the card",
    state: partState(data.parts?.stats, any),
    emptyText: "The leaders appear after the first game.",
    body: () => el("div", { class: "conf-leaders" }, LEADER_CATEGORIES.map(([key, title]) => leaderTable(leaders[key], title))),
  });
}

// --- the land --------------------------------------------------------------------------------------------------------------

function landBand(data, state) {
  const land = data.land && typeof data.land === "object" ? data.land : {};
  const rows = records(land.rows).filter((r) => typeof r.team === "string").map((r) => ({ ...r, cells: isNum(r.cells) ? r.cells : 0, pct: isNum(r.pct) ? r.pct : null, share: isNum(r.pct) ? `${r.pct.toFixed(1)}%` : null }));
  const most = rows.reduce((m, r) => Math.max(m, r.cells), 0);
  const short = text(data.conference?.short) || "The conference";
  const summary = land.available === true && isNum(land.held) && isNum(land.cells) ? `${text(land.label) ? `after ${text(land.label)} · ` : ""}${fmtNum(land.held)} of ${fmtNum(land.cells)} cells, ${isNum(land.pct) ? Math.round(land.pct) : DASH}% of the map` : "";
  return band({
    id: "conf-land",
    title: `${short}'s land`,
    collapsible: false,
    foldable: true,
    summary,
    state: land.available === false ? { status: "empty", message: words(land.words) || "The Imperialism Map has not been worked out yet." } : { status: rows.length ? "ready" : "empty", message: "No school of the conference holds land on the map." },
    body: () =>
      el(
        "div",
        { class: "tight" },
        statTable({
          compact: true,
          sizes: true,
          columns: [
            { key: "team", label: "School", kind: "text", stick: true, render: (row) => logoLink(row.team, row), renderShort: (row) => teamAbbrLink(row.team, row.abbreviation) },
            { key: "bar", label: "", sortable: false, sortKey: "cells", render: (row) => el("span", { class: "conf-bar", "aria-hidden": "true" }, el("i", { style: { width: `${most ? Math.max(1, Math.round((row.cells / most) * 100)) : 0}%` } })) },
            { key: "cells", label: "Cells", format: "0f", sub: "share", subLabel: "Share", subLabelShort: "%" },
            { key: "rank", label: "Rank", format: "0f", dim: true, size: "medium" },
            { key: "change", label: "Week", format: "+0f", size: "medium", render: (row) => (isNum(row.change) ? el("span", { class: row.change > 0 ? "conf-up" : row.change < 0 ? "conf-down" : null }, row.change > 0 ? `+${row.change}` : row.change < 0 ? String(row.change) : "held") : DASH) },
          ],
          rows,
          sort: state.sorts.land || { key: "cells", dir: "descending" },
          onSort: (sort) => { state.sorts.land = sort; },
          rowClass: (r) => (r.isUs ? "is-us" : null),
          caption: `${short}'s land`,
        }),
        el("p", { class: "note" }, "Each bar against the conference's largest holding; Rank among every FBS school; Week the change since the snapshot before. ", el("a", { href: "#imperialism" }, "Open the map")),
      ),
  });
}

// --- the page ------------------------------------------------------------------------------------------------------------------

function render(envelope, container, state, rerender) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const ours = data.conference?.ourTeam;
  const mark = (rows) => records(rows).forEach((r) => { if (ours && r.team === ours) r.isUs = true; });
  mark(data.standings?.rows);
  mark(data.rated);
  const page = el(
    "div",
    { class: "page page--wide conference" },
    headBlock(data),
    againstBand(data, state, rerender),
    standingsBand(data, state),
    weekBand(data),
    ratedBand(data, state),
    leadersBand(data),
    landBand(data, state),
  );
  state.ui ??= {};
  mountFlow(state.ui, container, page);
  return page;
}

function loadingPage(name) {
  return el(
    "div",
    { class: "page page--wide conference" },
    el("header", { class: "conf-head" }, el("div", { class: "skel", style: { width: "min(360px, 70%)", height: "34px" } })),
    band({ id: "conf-against", title: `${name} against the rest`, collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(6, 5) }),
    band({ id: "conf-standings", title: "Standings", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(8, 6) }),
  );
}

export function createConferenceView({ onStatus, arg = null, params = {} } = {}) {
  const wanted = typeof arg === "string" && arg.trim() ? arg.trim() : null;
  const state = { view: rememberedView("conference", "sp", AGAINST_VIEWS.map(([id]) => id)), sorts: {}, ui: null };
  if (params && (params.view === "sp" || params.view === "numbers")) state.view = params.view;
  const url = wanted ? `/api/conference/${encodeURIComponent(wanted)}` : "/api/conference";
  const view = poller({
    url,
    onStatus,
    render: (envelope, container) => {
      const draw = () => render(envelope, container, state, draw);
      draw();
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel(wanted ? `${wanted} conference page` : "Conference page", message, retry)),
    loadingDetail: "The conference's standings and the week",
    renderLoading: () => loadingPage(wanted || confName()),
  });
  const unmount = view.unmount;
  view.unmount = () => {
    stopFlow(state.ui);
    state.ui = null;
    unmount.call(view);
  };
  view.state = state; // the tests read the view and the sorts
  return view;
}
