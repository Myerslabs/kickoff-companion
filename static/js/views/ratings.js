// The ratings page (Phase 10): SP+ for every FBS team, then the ratings side by side (SP+, Elo,
// FPI, talent), every column sortable, our team marked, every team name a link. Reached from the
// SP+ chips on the cover, the schedule record line, and the season page's Ratings band.
// Phase 13: strength of schedule worked out from SP+ (CFBD leaves its own empty in season), CFBD's
// CORE, SRS and opponent-adjusted EPA in a third table, and conference SP+.
//
// Phase 16 (stream SEASON):
//   createRatingsView({ onStatus, arg, params })  '#ratings=<key>?team=<school>' sorts the table that holds key
//       (sp, spOffense, spDefense, spSpecial, sosPlayed, core, coreOffense, coreDefense, srs, adjEpa,
//       adjEpaAllowed, elo, fpi, talent, or the metric form 'rating:sp'), brings its band into view, scrolls the
//       table to the team (ours without ?team=) and flashes its row.
//   Each table opens scrolled so our row sits in the middle of its box (the box's own scrollTop, never
//   scrollIntoView, which would move the page too); our row stays pinned at the box's edge; the next
//   opponent's row is marked; Rk and Team stay in view when a table scrolls sideways. Every rank is out of
//   that rating's own count and links to its national list. Scope and each table's sort survive refreshes.

import { usSchool } from "../identity.js";
import { DASH, el, fmtNum, isNum, recall, remember, text } from "../ui/dom.js";
import { nationalHref } from "../ui/national-link.js";
import { band } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { spScatter } from "../ui/scatter.js";
import { logoLink } from "../ui/team-page.js";
import { statTable, statTableSkeleton } from "../ui/stat-table.js";
import { pollMs } from "../prefs.js";
import { errorPanel, fetchJson, partState, poller } from "./common.js";
import { NEXT_OPPONENT_KEY, jumpToBand, nextOpponent } from "./season.js";

const ROW_GUESS = 41; // px per compact row, for a page with no layout yet (and the tests)

/** Where a ratings key lives: [band id, rank column]. The metric form ('rating:sp', 'adjusted:epa') works too. */
export const RATING_KEYS = {
  sp: ["ratings-sp", "spRank"],
  spOffense: ["ratings-sp", "offRank"],
  spDefense: ["ratings-sp", "defRank"],
  spSpecial: ["ratings-sp", "stRank"],
  sosPlayed: ["ratings-sp", "sosRank"],
  core: ["ratings-more", "coreRank"],
  coreOffense: ["ratings-more", "coreOffRank"],
  coreDefense: ["ratings-more", "coreDefRank"],
  srs: ["ratings-more", "srsRank"],
  adjEpa: ["ratings-more", "adjRank"],
  adjEpaAllowed: ["ratings-more", "adjAllowedRank"],
  elo: ["ratings-side", "eloRank"],
  fpi: ["ratings-side", "fpiRank"],
  talent: ["ratings-side", "talentRank"],
};
const ADJUSTED = { epa: "adjEpa", epaAllowed: "adjEpaAllowed" };

/** '#ratings=' arg -> { key, band, column } or null. Exported for the tests. */
export function ratingTarget(arg) {
  if (typeof arg !== "string" || !arg.trim()) return null;
  const raw = arg.trim();
  const [family, rest] = raw.includes(":") ? raw.split(":", 2) : [null, raw];
  const key = family === "adjusted" ? ADJUSTED[rest] : rest;
  const hit = key && Object.prototype.hasOwnProperty.call(RATING_KEYS, key) ? RATING_KEYS[key] : null;
  return hit ? { key, band: hit[0], column: hit[1] } : null;
}

function spRows(rows) {
  return rows.map((r) => ({
    team: r.team,
    conference: r.conference,
    spRank: r.sp?.rank,
    spRating: r.sp?.rating,
    offRating: r.spOffense?.rating,
    offRank: r.spOffense?.rank,
    defRating: r.spDefense?.rating,
    defRank: r.spDefense?.rank,
    stRating: r.spSpecial?.rating,
    stRank: r.spSpecial?.rank,
    sos: isNum(r.sp?.sos) ? r.sp.sos : r.sosPlayed?.rating,
    sosRank: r.sosPlayed?.rank,
    isUs: r.isUs,
  }));
}

function sideRows(rows) {
  return rows.map((r) => ({
    team: r.team,
    conference: r.conference,
    spRank: r.sp?.rank,
    spRating: r.sp?.rating,
    eloRank: r.elo?.rank,
    eloRating: r.elo?.rating,
    fpiRank: r.fpi?.rank,
    fpiRating: r.fpi?.rating,
    talentRank: r.talent?.rank,
    talent: r.talent?.talent,
    isUs: r.isUs,
  }));
}

function moreRows(rows) {
  return rows.map((r) => ({
    team: r.team,
    conference: r.conference,
    core: r.core?.value,
    coreRank: r.core?.rank,
    coreOff: r.coreOffense?.value,
    coreOffRank: r.coreOffense?.rank,
    coreDef: r.coreDefense?.value,
    coreDefRank: r.coreDefense?.rank,
    srs: r.srs?.value,
    srsRank: r.srs?.rank,
    adj: r.adjEpa?.value,
    adjRank: r.adjEpa?.rank,
    adjAllowed: r.adjEpaAllowed?.value,
    adjAllowedRank: r.adjEpaAllowed?.rank,
    isUs: r.isUs,
  }));
}

/** Put a box's row in the middle of the box by the box's own scroll (never scrollIntoView). */
export function centerRow(wrap, tr) {
  if (!wrap || !tr) return false;
  const rows = tr.parentNode ? [...tr.parentNode.childNodes].filter((n) => n.localName === "tr" || n.tagName === "TR") : [];
  const index = Math.max(0, rows.indexOf(tr));
  const top = isNum(tr.offsetTop) && tr.offsetTop > 0 ? tr.offsetTop : index * ROW_GUESS;
  const height = isNum(tr.offsetHeight) && tr.offsetHeight > 0 ? tr.offsetHeight : ROW_GUESS;
  const room = isNum(wrap.clientHeight) && wrap.clientHeight > 0 ? wrap.clientHeight : 720;
  wrap.scrollTop = Math.max(0, Math.round(top - (room - height) / 2));
  return true;
}

function render(envelope, container, state) {
  state.envelope = envelope;
  state.container = container;
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const us = typeof data.team === "string" ? data.team : usSchool();
  const rows = (Array.isArray(data.rows) ? data.rows : []).filter((r) => r && typeof r === "object" && typeof r.team === "string").map((r) => ({ ...r, isUs: r.team === us }));
  const usRow = data.us && typeof data.us === "object" ? data.us : null;
  const focus = state.team && rows.some((r) => r.team === state.team) ? state.team : us;
  const next = state.next && state.next !== us ? state.next : null;
  const counts = data.counts && typeof data.counts === "object" ? data.counts : {};
  const metrics = data.metrics && typeof data.metrics === "object" ? data.metrics : {};
  const scoped = state.scope === "conference" ? rows.filter((r) => r.conference === data.conference) : rows;
  const buttons = [["all", "All FBS"], ["conference", data.conference || "Conference"]].map(([id, label]) => el("button", { type: "button", "aria-pressed": id === state.scope ? "true" : "false", onclick: () => { state.scope = id; render(envelope, container, state); } }, label));
  // Every rank is out of its own rating's count (bug 1: talent, CORE and SRS cover fewer teams than SP+).
  const rankCol = (key, label, countKey, extra = {}) => ({ key, label, kind: "rank", of: isNum(counts[countKey]) && counts[countKey] > 0 ? counts[countKey] : rows.length || null, sortable: true, link: (row) => nationalHref(metrics[countKey], { team: row.team }), ...extra });
  const rating = (key, label, digits = 1) => ({ key, label, format: `${digits}f`, sortable: true });
  const group = (column) => ({ ...column, divider: true }); // a thin rule where a new rating starts (Phase 14)
  // the team's link, and a small "Next" tag on the next opponent's row (G3-04)
  const teamCol = { key: "team", label: "Team", kind: "text", sub: "conference", stick: true, render: (row) => el("span", {}, logoLink(row.team, logos.get(row.team)), !row.isUs && row.team === next ? el("span", { class: "next-tag" }, "Next") : null) };
  const logos = new Map(rows.map((r) => [r.team, r])); // G3-10: a logo only where the server sends one
  const spColumns = [rankCol("spRank", "Rk", "sp", { stick: true }), teamCol, group(rating("spRating", "SP+")), group(rating("offRating", "Offense")), rankCol("offRank", "Rk", "spOffense"), group(rating("defRating", "Defense")), rankCol("defRank", "Rk", "spDefense"), group(rating("stRating", "Special")), rankCol("stRank", "Rk", "spSpecial"), group(rating("sos", "SOS", 1)), rankCol("sosRank", "Rk", "sosPlayed")];
  const published = data.published && typeof data.published === "object" ? data.published : {};
  const moreColumns = [teamCol, group(rating("core", "CORE")), rankCol("coreRank", "Rk", "core"), group(rating("coreOff", "Off")), rankCol("coreOffRank", "Rk", "coreOffense"), group(rating("coreDef", "Def")), rankCol("coreDefRank", "Rk", "coreDefense"), group(rating("srs", "SRS")), rankCol("srsRank", "Rk", "srs"), group({ key: "adj", label: "Adj EPA", format: "+2f" }), rankCol("adjRank", "Rk", "adjEpa"), group({ key: "adjAllowed", label: "Adj EPA allowed", format: "+2f" }), rankCol("adjAllowedRank", "Rk", "adjEpaAllowed")];
  const conferences = Array.isArray(data.conferences) ? data.conferences.filter((c) => c && typeof c === "object") : [];
  const confColumns = [{ key: "rank", label: "Rank", kind: "rank", of: conferences.length || null, sortable: true }, { key: "conference", label: "Conference", kind: "text" }, rating("rating", "SP+"), rating("offense", "Offense"), rating("defense", "Defense"), { key: "specialTeams", label: "Special", format: "2f" }];
  const unpublished = [published.core === false ? "CORE" : null, published.srs === false ? "SRS" : null, published.adjusted === false ? "the opponent-adjusted EPA" : null].filter(Boolean);
  const sideColumns = [teamCol, group(rating("spRating", "SP+")), rankCol("spRank", "Rk", "sp"), group(rating("eloRating", "Elo", 0)), rankCol("eloRank", "Rk", "elo"), group(rating("fpiRating", "FPI")), rankCol("fpiRank", "Rk", "fpi"), group(rating("talent", "Talent", 0)), rankCol("talentRank", "Rk", "talent")];
  const rowClass = (r) => [r.isUs ? "is-us" : null, !r.isUs && r.team === next ? "is-next" : null, !r.isUs && r.team === focus ? "is-focus" : null].filter(Boolean).join(" ") || null;
  const table = (id, columns, tableRows, fallback, caption) =>
    statTable({
      compact: true,
      columns,
      rows: tableRows,
      sort: state.sorts[id] || fallback,
      onSort: (sort) => {
        state.sorts[id] = sort; // the reader's order survives every refresh (G3-06)
      },
      rowClass,
      maxHeight: 720,
      caption,
    });
  const count = (key) => (isNum(counts[key]) && counts[key] > 0 ? counts[key] : rows.length);
  const nextName = next ? ` The next opponent, ${next}, is marked with a grey edge.` : "";
  const page = el(
    "div",
    { class: "page ratings" },
    el("div", { class: "seg flow-full", role: "group", "aria-label": "Scope", style: { justifySelf: "start" } }, buttons),
    band({
      id: "ratings-sp",
      title: "SP+",
      collapsible: false,
      foldable: true,
      summary: usRow ? `${usSchool()} #${text(usRow.sp?.rank)} of ${count("sp")}, offense #${text(usRow.spOffense?.rank)}, defense #${text(usRow.spDefense?.rank)}` : `${rows.length} teams`,
      state: partState(data.parts?.sp, rows.length > 0),
      emptyText: "SP+ ratings appear once CFBD publishes them for the season.",
      body: () => el("div", { class: "ratings__sp" }, el("div", { class: "ratings__main" }, table("ratings-sp", spColumns, spRows(scoped), { key: "spRank", dir: "ascending" }, "SP+ ratings"), el("p", { class: "note" }, el("strong", {}, "Press and hold a column name for its meaning. "), `SP+ is Bill Connelly's tempo- and opponent-adjusted efficiency rating: points per game better or worse than an average team. Offense higher is better; defense lower is better. SOS is the average SP+ of the FBS opponents played so far (CFBD does not publish SP+'s own during the season); its rank, 1 is the hardest.${nextName}`)), spScatter(scoped.map((r) => ({ team: r.team, off: r.spOffense?.rating, def: r.spDefense?.rating })), { us, next })),
    }),
    band({
      id: "ratings-more",
      title: "CORE, SRS and adjusted EPA",
      collapsible: false,
      foldable: true,
      summary: usRow ? [isNum(usRow.core?.rank) ? `CORE #${usRow.core.rank}` : null, isNum(usRow.srs?.rank) ? `SRS #${usRow.srs.rank}` : null, isNum(usRow.adjEpa?.rank) ? `adjusted EPA #${usRow.adjEpa.rank}` : null].filter(Boolean).join(", ") : "",
      state: partState(data.parts?.core, rows.length > 0),
      emptyText: "These ratings appear once CFBD publishes them for the season.",
      body: () => el("div", {}, table("ratings-more", moreColumns, moreRows(scoped), { key: "coreRank", dir: "ascending" }, "CORE, SRS and adjusted EPA"), el("p", { class: "note" }, `CORE is CFBD's own rating (points better than average; its defense number is points allowed against average, so lower is better). SRS is the simple rating system: margin of victory adjusted for the schedule. Adjusted EPA is expected points per play weighted for the opponents faced.${unpublished.length ? ` CFBD has not published ${unpublished.join(", ")} for this season yet; dashes until it does.` : ""}`)),
    }),
    band({
      id: "ratings-conferences",
      title: "Conference SP+",
      collapsible: false,
      foldable: true,
      summary: conferences.length ? `${conferences.length} conferences` : "",
      state: partState(data.parts?.conferences, conferences.length > 0),
      emptyText: "Conference ratings appear once CFBD publishes them.",
      body: () => el("div", {}, statTable({ compact: true, columns: confColumns, rows: conferences, sort: state.sorts["ratings-conferences"] || { key: "rank", dir: "ascending" }, onSort: (sort) => { state.sorts["ratings-conferences"] = sort; }, rowClass: (r) => (r.conference === data.conference ? "is-us" : null) }), el("p", { class: "note" }, "The average SP+ of each conference's teams.")),
    }),
    band({
      id: "ratings-side",
      title: "Ratings side by side",
      collapsible: false,
      foldable: true,
      summary: usRow ? `Elo #${text(usRow.elo?.rank)}, FPI #${text(usRow.fpi?.rank)}, talent #${text(usRow.talent?.rank)}` : "",
      state: partState(data.parts?.elo, rows.length > 0),
      emptyText: "Ratings appear once CFBD publishes them for the season.",
      body: () => el("div", {}, table("ratings-side", sideColumns, sideRows(scoped), { key: "spRank", dir: "ascending" }, "Ratings side by side"), el("p", { class: "note" }, `Elo is a results-only rating, FPI is ESPN's projection, talent is the 247Sports composite of the roster. ${isNum(counts.talent) ? `${fmtNum(counts.talent)} teams have a talent figure.` : ""}`)),
    }),
  );
  state.ui ??= {};
  mountFlow(state.ui, container, page, { wide: RATINGS_WIDE }); // final pass: the flowing page with its section chips
  // Each box opens on the focus team (the reader's own scroll wins after the first draw: the poller puts it back).
  for (const wrap of page.querySelectorAll(".stat-table-wrap--box")) {
    const th = wrap.querySelector("thead th");
    if (th && isNum(th.offsetHeight) && th.offsetHeight > 0) wrap.style.setProperty("--th-h", `${th.offsetHeight}px`); // our pinned row sits under the header
    const tr = wrap.querySelector("tr.is-focus") || wrap.querySelector("tr.is-us");
    if (tr) centerRow(wrap, tr);
  }
  if (state.target) {
    const section = page.querySelector(`#${state.target.band}`);
    const tr = section ? section.querySelector("tr.is-focus") || section.querySelector("tr.is-us") : null;
    // the row arrived at flashes on the first draws (the cached page, then the fresh one), not on later refreshes
    if (tr && (!state.arrivedAt || Date.now() - state.arrivedAt < 5000)) for (const td of tr.querySelectorAll("td")) td.classList.add("flash");
    if (!state.arrivedAt) {
      state.arrivedAt = Date.now();
      if (section && state.target.band !== "ratings-sp") setTimeout(() => jumpToBand(section), 0); // after the router's scroll to the top
    }
  }
}

/** The next opponent: remembered by the Season page, else read once from the season overview. */
async function findNext(state) {
  const saved = recall(NEXT_OPPONENT_KEY, null);
  if (saved && typeof saved.school === "string") {
    state.next = saved.school;
    return;
  }
  try {
    const envelope = await fetchJson("/api/season/overview");
    const next = nextOpponent(envelope?.data);
    if (!next) return;
    remember(NEXT_OPPONENT_KEY, next);
    state.next = next.school;
    if (state.envelope && state.container?.isConnected) render(state.envelope, state.container, state);
  } catch (error) {
    console.warn("Ratings: the next opponent could not be read; its row is not marked.", error?.message || error);
  }
}

const RATINGS_WIDE = ["ratings-sp", "ratings-more", "ratings-side"]; // the eleven-column tables take two columns

export function createRatingsView({ onStatus, arg, params } = {}) {
  const target = ratingTarget(arg);
  const team = typeof params?.team === "string" && params.team.trim() ? params.team.trim() : null;
  const state = { scope: "all", sorts: {}, target, team, next: null, arrivedAt: 0, envelope: null, container: null };
  if (target) state.sorts[target.band] = { key: target.column, dir: "ascending" };
  const view = poller({
    url: "/api/ratings",
    refreshMs: pollMs(),
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Ratings", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "SP+", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(12, 11) })),
  });
  const mount = view.mount;
  view.mount = (target2) => {
    findNext(state);
    mount(target2);
  };
  const unmount = view.unmount;
  view.unmount = () => {
    stopFlow(state.ui);
    unmount.call(view);
  };
  view.state = state; // the tests read the sort and scope
  return view;
}

export { DASH };
