// The Roster page (menu entry). Top: the depth chart the owner asked for (2026-09-23 screenshot,
// laid out again from his 2026-09-26 screenshot): six unit columns side by side (QB and RB, WR and
// TE, OL, DL and LB, CB and S, the specialists), each position a card with a big label, one line
// per player and a colored number on the right. The number is the player's recruiting rating (the
// 247 composite x 100, green 90 and up, yellow-green 80s, amber below) by default; each card sorts
// on its own (number, class, size, stars, play value...) with the choice remembered on the device.
// CFBD publishes no depth order, so the order is the chosen sort, not the coaches' two-deep.
// Below it: the sortable roster table with the position picker, the star strip, and the impact
// players. Row tap anywhere opens the player card.
//
// Phase 17 #35 (owner screenshots, 2026-10-07): a Roster breakdown band first: positions down, the five classes
// across with totals, each player a name chip with our stat grade; then the star strip (#36) under it.
// Phase 16 (stream PEOPLE): the position picker is a visible select in the table band's body (LRP-03, bug 6),
// the table scrolls in a box of min(70vh, 720px) so its header stays on screen, and its sort survives the
// hourly refresh and a position change; stars read 4-star (LRP-13); the recruit rank is a chip that opens the
// recruit list once a row carries its list key (recruitMetric, from stream NV); the impact cards' stat chips
// use the plain labels (LRP-06); one sub-heading style (DS-14); the .page container (DS-06).
// The depth chart (LRP-09): six unit columns from 1100 px (three from 700, two below), every row with its
// jersey number (design item 17), 44 px rows, a skeleton in the chart's own shape. Under the Number and Name
// sorts the number column already says the number, so the value shows the rating; under Recruit rank the
// value is a rank chip placed beside the row's button, never inside it.

import { usSchool } from "../identity.js";
import { DASH, el, fmtNum, fmtPct, fmtStat, isNum, recall, remember, text } from "../ui/dom.js";
import { nationalHref } from "../ui/national-link.js";
import { recruitHref } from "../ui/player-card.js";
import { band, note, subhead } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { plainChip } from "../ui/stat-labels.js";
import { rankChip, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { impactCard, impactSkeleton, starStrip } from "../ui/team-page.js";
import { combinedState, errorPanel, partState, poller } from "./common.js";
import { openPlayer } from "./player.js";
import { GRADE_NOTE, gradeChip, gradeValue } from "../ui/grade.js";
import { rosterGrid } from "../ui/roster-grid.js";
import { costsBand } from "../ui/roster-costs.js";

// The unit columns and the cards in each, with their labels. CFBD's roster says PK for kickers; a
// DB with no CB or S label gets its own card under the secondary; anything else lands in the last column.
const UNITS = [
  [["QB", "QB"], ["RB", "RB"], ["FB", "FB"]],
  [["WR", "WR"], ["TE", "TE"]],
  [["OL", "OL"], ["OT", "OT"], ["OG", "OG"], ["C", "C"]],
  [["DL", "DL"], ["DE", "DE"], ["DT", "DT"], ["NT", "NT"], ["LB", "LB"], ["OLB", "OLB"], ["ILB", "ILB"]],
  [["CB", "CB"], ["S", "S"], ["DB", "DB"]],
  [["PK", "K"], ["K", "K"], ["P", "P"], ["LS", "LS"], ["ATH", "ATH"]],
];
const TABLE_GROUPS = ["QB", "RB", "WR", "TE", "OL", "DL", "LB", "CB", "S", "DB", "PK", "P", "LS"];
const CLASS_ORDER = { SR: 0, GR: 0, JR: 1, SO: 2, FR: 3 };
/** The recruiting rating as a 0-100 number (0.9379 -> 94), or null. Exported for the tests. */
export function ratingScore(p) {
  const r = p?.rating;
  return isNum(r) && r > 0 && r <= 1 ? Math.round(r * 100) : null;
}

/** The color tier of a shown rating, like the screenshot: top (90+), good (80s), fair (below). */
export function ratingTier(score) {
  if (!isNum(score)) return "";
  return score >= 90 ? "top" : score >= 80 ? "good" : "fair";
}

// Owner direction 2026-09-27: most plays at the top by default. CFBD publishes no snap counts; the
// count is the plays CFBD credits to the player (passes, carries, targets), so it covers the ball
// carriers only. Players without one (linemen, defenders, specialists) follow in rating order.
// Phase 16 (LRP-04): a card where nobody has a play count (OL, DL, LB, DB, specialists) starts on Rating
// instead: the same order (the Plays sort already fell back to rating), but the rating shows instead of a
// column of dashes. A card's remembered choice still wins, and the card head says what the number is.
const SORTS = [
  { id: "plays", label: "Plays", value: (p) => (isNum(p.ppaPlays) ? p.ppaPlays : -1), dir: -1, then: (p) => -(ratingScore(p) ?? -1), show: (p) => (isNum(p.ppaPlays) ? String(p.ppaPlays) : DASH) },
  { id: "rating", label: "Rating", value: (p) => (ratingScore(p) ?? -1), dir: -1, show: (p) => (ratingScore(p) !== null ? String(ratingScore(p)) : DASH), tier: (p) => ratingTier(ratingScore(p)) },
  { id: "number", label: "Number", value: (p) => (isNum(p.number) ? p.number : Infinity), dir: 1, show: (p) => (ratingScore(p) !== null ? String(ratingScore(p)) : DASH), tier: (p) => ratingTier(ratingScore(p)) },
  { id: "name", label: "Name", value: (p) => String(p.lastName || p.name || "").toLowerCase(), dir: 1, show: (p) => (ratingScore(p) !== null ? String(ratingScore(p)) : DASH), tier: (p) => ratingTier(ratingScore(p)) },
  { id: "class", label: "Class", value: (p) => CLASS_ORDER[String(p.classYear || "").toUpperCase()] ?? 9, dir: 1, show: (p) => text(p.classYear) },
  { id: "height", label: "Height", value: (p) => (isNum(p.height) ? p.height : -1), dir: -1, show: (p) => text(p.heightText) },
  { id: "age", label: "Age", value: (p) => (isNum(p.age) ? p.age : -1), dir: -1, show: (p) => (isNum(p.age) ? String(p.age) : DASH) },
  { id: "weight", label: "Weight", value: (p) => (isNum(p.weight) ? p.weight : -1), dir: -1, show: (p) => (isNum(p.weight) ? String(p.weight) : DASH) },
  { id: "stars", label: "Stars", value: (p) => (isNum(p.stars) ? p.stars : -1), dir: -1, show: (p) => (isNum(p.stars) ? `${p.stars}-star` : DASH) },
  { id: "recruit", label: "Recruit rank", value: (p) => (isNum(p.recruitRank) ? p.recruitRank : Infinity), dir: 1, show: (p) => (isNum(p.recruitRank) ? `#${p.recruitRank}` : DASH), chip: (p) => rankChip(p.recruitRank, null, { href: recruitHref(p), label: `Recruit rank, ${text(p.name)}` }) },
  { id: "ppa", label: "PPA per play", value: (p) => (isNum(p.ppaPerPlay) ? p.ppaPerPlay : -Infinity), dir: -1, show: (p) => (isNum(p.ppaPerPlay) ? fmtStat(p.ppaPerPlay, "+2f") : DASH) },
  { id: "usage", label: "Usage", value: (p) => (isNum(p.usageShare) ? p.usageShare : -1), dir: -1, show: (p) => (isNum(p.usageShare) ? fmtStat(p.usageShare, "pct") : DASH) },
];
const SORT_KEY = (pos) => `roster:sort:${pos}`;

function shortName(p) {
  const first = typeof p.firstName === "string" ? p.firstName.trim() : "";
  const last = typeof p.lastName === "string" ? p.lastName.trim() : "";
  if (first && last) return `${first[0]}. ${last}${p.redshirt === true ? " (RS)" : ""}`;
  return `${text(p.name)}${p.redshirt === true ? " (RS)" : ""}`;
}

function sortedPlayers(players, sort) {
  const rows = [...players];
  rows.sort((a, b) => {
    const va = sort.value(a);
    const vb = sort.value(b);
    if (va < vb) return -1 * sort.dir;
    if (va > vb) return 1 * sort.dir;
    if (typeof sort.then === "function" && sort.then(a) !== sort.then(b)) return sort.then(a) - sort.then(b);
    return (isNum(a.number) ? a.number : 999) - (isNum(b.number) ? b.number : 999);
  });
  return rows;
}

/** A card's first sort: Plays when anyone on it has a play count, else Rating (same order, no dashes). Exported for the tests. */
export function defaultSort(players) {
  return (Array.isArray(players) ? players : []).some((p) => p && isNum(p.ppaPlays)) ? "plays" : "rating";
}

/** One position card: the label, a visible "what the number is" sort control, one line per player. */
function positionCard(pos, label, players) {
  const remembered = recall(SORT_KEY(pos), null);
  let sort = SORTS.find((s) => s.id === remembered) || SORTS.find((s) => s.id === defaultSort(players)) || SORTS[0];
  const list = el("ul", { class: "depth-card__list" });
  const draw = () => {
    list.replaceChildren();
    for (const p of sortedPlayers(players, sort)) {
      const tier = typeof sort.tier === "function" ? sort.tier(p) : "";
      // a linked chip is an anchor: it sits beside the row's button, never inside it
      const chip = typeof sort.chip === "function" ? sort.chip(p) : null;
      const value = chip ? null : el("span", { class: `depth-row__val${tier ? ` depth-row__val--${tier}` : typeof sort.tier === "function" ? " depth-row__val--none" : ""}` }, sort.show(p));
      list.append(
        el(
          "li",
          { class: `depth-li${chip || sort.id === "recruit" ? " depth-li--chip" : ""}` },
          el("button", { class: "depth-row", type: "button", title: `${text(p.name)}, #${isNum(p.number) ? p.number : DASH}, ${text(p.classYear)}`, onclick: () => openPlayer(p.playerId, { ...p, isUs: p.isUs !== false }) }, el("span", { class: "depth-row__num" }, isNum(p.number) ? String(p.number) : DASH), el("span", { class: "depth-row__name" }, shortName(p)), value),
          chip || (sort.id === "recruit" ? el("span", { class: "depth-row__val depth-row__val--none" }, DASH) : null),
        ),
      );
    }
  };
  // the select shows its choice ("Rating", "Plays"): it names the number on the right and sorts by it
  const select = el(
    "select",
    { class: "depth-card__pick", "aria-label": `${label}: the number shown and the order`, title: `Sort ${label}`, onchange: (event) => { sort = SORTS.find((s) => s.id === event.target.value) || SORTS[0]; remember(SORT_KEY(pos), sort.id); draw(); } },
    SORTS.map((s) => el("option", { value: s.id, selected: s.id === sort.id ? true : null }, s.label)),
  );
  draw();
  return el("section", { class: "depth-card", "aria-label": `${label}, ${players.length} players` }, el("div", { class: "depth-card__head" }, el("h3", {}, label), select), list);
}

/** Players grouped into the unit columns: [[{pos, label, players}]]. Exported for the tests. */
export function depthUnits(players) {
  const byPos = new Map();
  for (const p of Array.isArray(players) ? players : []) {
    if (!p || typeof p !== "object") continue;
    const pos = (typeof p.position === "string" ? p.position.trim().toUpperCase() : "") || "Other";
    if (!byPos.has(pos)) byPos.set(pos, []);
    byPos.get(pos).push(p);
  }
  const units = UNITS.map((unit) =>
    unit.flatMap(([pos, label]) => {
      if (!byPos.has(pos)) return [];
      const rows = byPos.get(pos);
      byPos.delete(pos);
      return [{ pos, label, players: rows }];
    }),
  );
  for (const [pos, rows] of byPos) units[units.length - 1].push({ pos, label: pos, players: rows }); // positions the list does not know
  return units.filter((unit) => unit.length);
}

/** A loading depth chart in the chart's own shape: six columns of cards with name rows (LRP-09). */
export function depthSkeleton() {
  const card = (rows) => el("div", { class: "depth-card depth-card--skel" }, el("div", { class: "skel skel--bar depth-card__skel-head" }), Array.from({ length: rows }, () => el("div", { class: "skel skel--bar depth-card__skel-row" })));
  return el("div", { class: "depth", "aria-hidden": "true" }, [[4, 3], [5, 3], [7], [5, 4], [4, 4], [2, 2]].map((unit) => el("div", { class: "depth__unit" }, unit.map(card))));
}

/** The depth chart for a roster (exported for the styleguide). */
export function depthChart(players) {
  return el(
    "div",
    { class: "depth" },
    depthUnits(players).map((unit) => el("div", { class: "depth__unit" }, unit.map((card) => positionCard(card.pos, card.label, card.players)))),
  );
}

/** The blue-chip ratio: four- and five-star signees over all signees in the last four classes. With a
 *  national rank and list key (stream NV's bluechip list) it carries a chip that opens that list. */
export function blueChipNote(bc) {
  if (!bc || typeof bc !== "object" || !isNum(bc.ratio)) return el("p", { class: "note" }, "Blue-chip ratio: no recruiting classes loaded yet.");
  const classes = (Array.isArray(bc.classes) ? bc.classes : []).filter((c) => c && typeof c === "object").map((c) => `${text(c.year)}: ${text(c.blueChips)} of ${text(c.signees)}`).join(", ");
  const verdict = bc.ratio >= 0.5 ? "above the 50% line every champion since 2011 has cleared" : "below the 50% line every champion since 2011 has cleared";
  const chip = rankChip(bc.nationalRank, bc.nationalOf, { href: nationalHref(bc.metric, { team: bc.team }), label: "Blue-chip ratio" });
  return el("p", { class: "note" }, el("b", {}, `Blue-chip ratio ${fmtPct(bc.ratio)}`), chip ? [" ", chip, " nationally"] : null, ` (${text(bc.blueChips)} of ${text(bc.signees)} signees over the last four classes${classes ? `: ${classes}` : ""}), ${verdict}.`);
}

function tableColumns() {
  const cols = [
    { key: "number", label: "No." },
    { key: "name", label: "Player", kind: "text", render: (row) => `${text(row.name)}${row.redshirt === true ? " (RS)" : ""}` },
    { key: "position", label: "Pos", kind: "text" },
    { key: "classYear", label: "Class", kind: "text" },
    { key: "age", label: "Age" }, // Phase 17 #38: from the preseason load's birthdates
    { key: "heightText", label: "Ht", kind: "text", sortable: false },
    { key: "weight", label: "Wt" },
    { key: "hometown", label: "Hometown", kind: "text" },
    { key: "highSchool", label: "High school", kind: "text" },
    { key: "transferFrom", label: "Transfer from", kind: "text", team: true },
    { key: "stars", label: "Stars", format: "stars" },
    { key: "recruitRank", label: "Recruit rank", kind: "rank", link: recruitHref },
    { key: "ppaPerPlay", label: "PPA/play", format: "+2f" },
    { key: "usageShare", label: "Usage", format: "pct" },
    { key: "gradeValue", label: "Grade", render: (row) => gradeChip(row.grade) }, // public release Phase 7: our stat grade
  ];
  return cols;
}

function render(envelope, container, state) {
  const data = envelope.data || {};
  const players = (Array.isArray(data.players) ? data.players : []).filter((p) => p && typeof p === "object");
  const parts = data.parts || {};
  const recruitParts = Object.keys(parts).filter((k) => k.startsWith("recruits_")).map((k) => parts[k]);
  const impact = data.impact || {};
  const impactRows = (side) => (Array.isArray(impact[side]) ? impact[side] : []).filter((p) => p && typeof p === "object");
  const impactGrid = (side) => (impactRows(side).length ? el("div", { class: "impact-grid" }, impactRows(side).map((p) => impactCard({ player: { name: p.name, number: p.number, position: p.position, classYear: p.classYear, headshotUrl: p.headshotUrl }, chips: (Array.isArray(p.chips) ? p.chips : []).map(plainChip).filter(Boolean), onTap: () => openPlayer(p.playerId, { ...p, isUs: p.isUs !== false }) }))) : note("Impact players appear after the first game."));
  const rated = isNum(data.rated) ? data.rated : 0;

  // LRP-03 (bug 6): a visible select in the band body, never the depth card's hidden one in the band head
  const groups = TABLE_GROUPS.filter((g) => players.some((p) => p && p.position === g));
  if (state.position && !groups.includes(state.position)) state.position = "";
  const picker = el(
    "label",
    { class: "roster-filter" },
    el("span", { class: "roster-filter__label" }, "Position"),
    el(
      "select",
      { class: "setting__select roster-filter__select", onchange: (event) => { state.position = event.target.value; renderTable(); } },
      el("option", { value: "", selected: state.position ? null : true }, "All positions"),
      groups.map((g) => el("option", { value: g, selected: state.position === g ? true : null }, g === "PK" ? "K" : g)),
    ),
  );
  const tableHost = el("div", {});
  const renderTable = () => {
    const rows = (state.position ? players.filter((p) => p && p.position === state.position) : players).filter((p) => p && typeof p === "object").map((p) => ({ ...p, transferFrom: p?.transfer && typeof p.transfer.from === "string" ? p.transfer.from : null, gradeValue: gradeValue(p.grade) }));
    tableHost.replaceChildren(rows.length ? statTable({ columns: tableColumns(), rows, sort: state.sort || { key: "number", dir: "ascending" }, onSort: (sort) => { state.sort = sort; }, compact: true, maxHeight: "min(70vh, 720px)", onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs: row.isUs !== false }), caption: "Roster" }) : note(state.position ? `No ${state.position === "PK" ? "K" : state.position} on the roster.` : "No roster yet."));
  };
  renderTable();

  const page = el(
      "div",
      { class: "page roster" },
      band({
        id: "roster-breakdown",
        title: "Roster breakdown",
        collapsible: false,
        foldable: true,
        summary: `${players.length} players by position and class`,
        state: partState(parts.roster, players.length > 0),
        emptyText: "The roster loads the first time the app opens.",
        body: () => el("div", {}, starStrip({ counts: data.starCounts || {}, average: data.average }), rosterGrid(players, { onPlayer: (p) => openPlayer(p.playerId, { ...p, isUs: p.isUs !== false }) }), el("p", { class: "note" }, "The number is our stat grade (100 is the best, 50 the middle at the position); linemen and long snappers have none. Tap a player for the card.")),
      }),
      costsBand(data.costs, { id: "roster-costs" }), // Phase 17 Part 3b: rumored, from the Preseason page's load
      band({
        id: "roster-depth",
        title: `${typeof data.team === "string" && data.team.trim() ? data.team.trim() : typeof data.team?.school === "string" && data.team.school.trim() ? data.team.school.trim() : usSchool()} depth chart`,
        collapsible: false,
        foldable: true,
        summary: `${players.length} players, each position sorts on its own`,
        state: partState(parts.roster, players.length > 0),
        emptyText: "The roster loads the first time the app opens.",
        body: () => depthChart(players),
      }),
      band({
        id: "roster-table",
        title: "Roster",
        collapsible: false,
        foldable: true,
        summary: `${players.length} players, sortable`,
        state: partState(parts.roster, players.length > 0),
        emptyText: "The roster loads the first time the app opens.",
        body: () => el("div", {}, el("div", { class: "roster-filter-row" }, picker), tableHost, el("p", { class: "note" }, GRADE_NOTE, " Tap a player for how it is made. Offensive linemen and long snappers have no individual stats, so no grade.")),
      }),
      band({
        id: "roster-stars",
        title: "Recruiting stars on the roster",
        collapsible: false,
        foldable: true,
        summary: rated ? `${rated} of ${players.length} players rated` : "",
        state: combinedState([parts.roster, ...recruitParts], players.length > 0),
        emptyText: "The roster loads the first time the app opens.",
        body: () => el("div", {}, starStrip({ counts: data.starCounts || {}, average: data.average, note: `${rated} of ${players.length} players have a CFBD recruiting record. Walk-ons and older transfers have none.` }), blueChipNote(data.blueChip)),
      }),
      band({ id: "roster-impact", title: "Impact players", collapsible: false, foldable: true, summary: "season leaders, offense then defense", state: partState(parts.team, (impact.offense || []).length + (impact.defense || []).length > 0), emptyText: "Impact players appear after the first game.", body: () => el("div", { class: "roster-impact" }, subhead("Offense"), impactGrid("offense"), subhead("Defense"), impactGrid("defense")) }),
  );
  state.ui ??= {};
  mountFlow(state.ui, container, page, { wide: ROSTER_WIDE }); // final pass: the flowing page with its section chips
}

const ROSTER_WIDE = ["roster-breakdown", "roster-depth", "roster-table"]; // the grids and the sortable table take two columns

export function createRosterView({ onStatus } = {}) {
  const state = { position: "", sort: null, ui: {} }; // kept across the hourly refresh (LRP-03)
  const view = poller({
    url: "/api/roster",
    refreshMs: 60 * 60 * 1000,
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Roster", message, retry)),
    renderLoading: () =>
      el(
        "div",
        { class: "page roster" },
        band({ title: "Depth chart", collapsible: false, state: { status: "loading" }, skeleton: depthSkeleton }),
        band({ title: "Roster", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(12) }),
        band({ title: "Recruiting stars on the roster", collapsible: false, state: { status: "loading" }, skeleton: () => el("div", { class: "skel skel--row" }) }),
        band({ title: "Impact players", collapsible: false, state: { status: "loading" }, skeleton: () => impactSkeleton(6) }),
      ),
  });
  return { ...view, unmount() { stopFlow(state.ui); view.unmount(); } };
}

export { fmtNum };
