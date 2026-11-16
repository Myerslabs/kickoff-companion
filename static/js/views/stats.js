// The full national lists (ENH-10, owner 2026-10-23: "menu - stats - passing should show the entire 136 passing list. The
// leaders only shows the top 10"; "both, similar the the SP+"; players with a cutoff). '#stats=<category>?view=players|teams'
// for passing, rushing, receiving and defense, from /api/stats/<category> (app/services/fullstats.py).
//
//   Players: every FBS player at or over the stat grades' volume minimum per team game, one sized table like the Ratings
//       page's, every column sortable, Rk by the category's lead stat, our players marked, the next opponent's in grey; a
//       tap opens the player card with every one of his stats (owner 2026-10-25).
//   Teams: every FBS team in two tables, its own numbers and what it allowed (for Defense, what its defense took and what
//       its offense gave up), Rk by the lead stat, every column sortable (a rank chip beside every value made the tables too
//       wide for the iPad; the server still sends each value's national rank as <key>Rank).
//   The categories and the two views are links (Back steps through them); the reader's sort survives refreshes.

import { usSchool } from "../identity.js";
import { el, fmtNum, isNum, teamLink, text } from "../ui/dom.js";
import { band, note } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { conferenceColumn, logoLink, teamAbbrLink } from "../ui/team-page.js";
import { sizedText, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { errorPanel, partState, poller } from "./common.js";
import { openPlayer } from "./player.js";

export const STATS_CATEGORIES = [
  ["passing", "Passing"],
  ["rushing", "Rushing"],
  ["receiving", "Receiving"],
  ["defense", "Defense"],
];
const VIEWS = [["players", "Players"], ["teams", "Teams"]];

/** '#stats=' arg and ?view= -> { category, view }; anything unknown falls back to passing, players. Exported for the tests. */
export function statsTarget(arg, params) {
  const category = STATS_CATEGORIES.some(([key]) => key === arg) ? arg : "passing";
  const view = params && params.view === "teams" ? "teams" : "players";
  return { category, view };
}

export function statsHref(category, view) {
  return `#stats=${category}${view === "teams" ? "?view=teams" : ""}`;
}

function list(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object") : [];
}

function columnsOf(value) {
  return list(value).filter((c) => typeof c.key === "string" && typeof c.label === "string");
}

/** The category and view links at the top: two segmented rows, the current one pressed. */
function switches(target) {
  const seg = (label, items, current, href) =>
    el("nav", { class: "seg stats__seg", "aria-label": label }, items.map(([key, words]) => el("a", { class: "seg__item", href: href(key), "aria-current": key === current ? "page" : null }, words)));
  return el(
    "div",
    { class: "stats__switches flow-full" },
    seg("Category", STATS_CATEGORIES, target.category, (key) => statsHref(key, target.view)),
    seg("View", VIEWS, target.view, (key) => statsHref(target.category, key)),
  );
}

function teamName(row) {
  const name = typeof row.team === "string" && row.team.trim() ? row.team.trim() : null;
  if (!name) return text(null);
  const short = typeof row.abbreviation === "string" && row.abbreviation.trim() ? row.abbreviation.trim() : name;
  return teamLink(name, sizedText(name, short, short));
}

function rowClass(next) {
  return (row) => [row.isUs ? "is-us" : null, !row.isUs && next && row.team === next ? "is-next" : null].filter(Boolean).join(" ") || null;
}

/** A value column; the server names the smallest table size that still shows it (the iPad shows medium). */
function valueColumn(c) {
  return { key: c.key, label: c.label, format: c.format, sortable: true, size: c.size === "medium" || c.size === "large" ? c.size : undefined };
}

function playersBand(data, state) {
  const p = data.players && typeof data.players === "object" ? data.players : {};
  const rows = list(p.rows);
  const cols = columnsOf(p.columns);
  const lead = typeof p.lead === "string" ? p.lead : cols[0]?.key;
  const leadCol = cols.find((c) => c.key === lead);
  const label = text(data.label || "Passing");
  const minimum = typeof p.minimum?.words === "string" ? p.minimum.words : null;
  const columns = [
    { key: `${lead}Rank`, label: "Rk", kind: "rank", order: true, of: rows.length || null, sortable: true },
    { key: "player", label: "Player", kind: "text", person: true, sub: "position", subLabel: "Pos" },
    // the team's whole name at large, its abbreviation at medium (the iPad) and small, its link at every size
    { key: "team", label: "Team", kind: "text", render: (row) => teamName(row), renderShort: (row) => teamAbbrLink(row.team, row.abbreviation) },
    { ...conferenceColumn(), size: "large" },
    ...cols.map(valueColumn),
  ];
  const us = rows.filter((r) => r.isUs);
  const summary = `${fmtNum(rows.length)} players${isNum(p.withStat) ? ` of ${fmtNum(p.withStat)}` : ""}${us.length ? `, ${us.length} of ${usSchool()}'s` : ""}`;
  return band({
    id: "stats-players",
    title: `${label}: every qualified player`,
    collapsible: false,
    foldable: true,
    summary,
    state: partState(data.parts?.[`national_${data.category === "defense" ? "defensive" : data.category}`], rows.length > 0),
    emptyText: "The national player stats appear once CFBD publishes them for the season.",
    body: () =>
      el(
        "div",
        {},
        statTable({
          compact: true,
          sizes: true,
          columns,
          rows,
          sort: state.sorts["stats-players"] || { key: `${lead}Rank`, dir: "ascending" },
          onSort: (sort) => {
            state.sorts["stats-players"] = sort;
          },
          rowClass: rowClass(data.next),
          onRowTap: (row) => openPlayer(row.playerId, row),
          caption: `${label}, every qualified FBS player`,
        }),
        note(`At least ${minimum || "the stat grades' minimum"} (the stat grades' minimums, by the team's games: CFBD has no games played per player). Rk follows ${leadCol ? text(leadCol.long).toLowerCase() : "the lead stat"}; every column sorts. Tap a player for every one of his stats.`),
      ),
  });
}

function teamTable(id, block, data, state) {
  const b = block && typeof block === "object" ? block : {};
  const rows = list(b.rows);
  const cols = columnsOf(b.columns);
  const lead = typeof b.lead === "string" ? b.lead : cols[0]?.key;
  const leadCol = cols.find((c) => c.key === lead);
  const of = rows.length || null;
  const logos = new Map(rows.map((r) => [r.team, r]));
  const columns = [
    { key: `${lead}Rank`, label: "Rk", kind: "rank", order: true, of, sortable: true },
    { key: "team", label: "Team", kind: "text", render: (row) => logoLink(row.team, logos.get(row.team)), renderShort: (row) => teamAbbrLink(row.team, row.abbreviation) },
    { ...conferenceColumn(), tieKey: "team", size: "large" }, // the iPad keeps its room for the numbers
    { key: "games", label: "Games", labelMid: "G", labelShort: "G", format: "0f", sortable: true, size: "large" },
    ...cols.map(valueColumn),
  ];
  return statTable({
    compact: true,
    sizes: true,
    columns,
    rows,
    sort: state.sorts[id] || { key: `${lead}Rank`, dir: "ascending" },
    onSort: (sort) => {
      state.sorts[id] = sort;
    },
    rowClass: rowClass(data.next),
    caption: text(b.title),
  });
}

function teamBands(data, state) {
  const t = data.teams && typeof data.teams === "object" ? data.teams : {};
  const us = (block) => list(block?.rows).find((r) => r.isUs);
  const lead = (block) => (typeof block?.lead === "string" ? block.lead : null);
  const leadLabel = (block) => columnsOf(block?.columns).find((c) => c.key === lead(block))?.long;
  const line = (block) => {
    const row = us(block);
    const key = lead(block);
    return row && key && isNum(row[`${key}Rank`]) ? `${usSchool()} #${row[`${key}Rank`]} in ${text(leadLabel(block)).toLowerCase()}` : `${fmtNum(list(block?.rows).length)} teams`;
  };
  const one = (id, block) =>
    band({
      id,
      title: text(block?.title),
      collapsible: false,
      foldable: true,
      summary: line(block),
      state: partState(data.parts?.stats, list(block?.rows).length > 0),
      emptyText: "Team stats appear once CFBD publishes them for the season.",
      body: () => el("div", {}, teamTable(id, block, data, state), note(`Every FBS team. Rk follows ${text(leadLabel(block) || "the lead stat").toLowerCase()}; every column sorts.`)),
    });
  return [one("stats-teams", t.offense), one("stats-allowed", t.allowed)];
}

function render(envelope, container, state) {
  state.envelope = envelope;
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const page = el(
    "div",
    { class: "page stats" },
    switches(state.target),
    ...(state.target.view === "teams" ? teamBands(data, state) : [playersBand(data, state)]),
  );
  state.ui ??= {};
  mountFlow(state.ui, container, page, { wide: STATS_WIDE, chips: state.target.view === "teams" });
}

const STATS_WIDE = ["stats-players", "stats-teams", "stats-allowed"]; // the long tables take the page's width

export function createStatsView({ onStatus, arg, params } = {}) {
  const target = statsTarget(arg, params);
  const state = { target, sorts: {}, envelope: null, ui: null };
  const label = STATS_CATEGORIES.find(([key]) => key === target.category)?.[1] || "Passing";
  const view = poller({
    url: `/api/stats/${target.category}`,
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel(`${label}, the full list`, message, retry)),
    renderLoading: () => el("div", { class: "page stats" }, switches(target), band({ title: `${label}: the full list`, collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(14, 8) })),
  });
  const unmount = view.unmount;
  view.unmount = () => {
    stopFlow(state.ui);
    unmount.call(view);
  };
  view.state = state; // the tests read the target and the sorts
  return view;
}
