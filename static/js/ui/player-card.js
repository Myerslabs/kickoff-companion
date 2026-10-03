// The player card (X1 as revised 2026-09-21): a slide-over with headshot or number badge,
// height and weight, hometown and high school, stars and rating, then three tabs: Stats
// (season by season with a career row), Game log, History (year by year). A missing or failing
// headshot always becomes the number badge. Every missing field renders as a dash.
//
// Phase 16 (stream PEOPLE):
//   LRP-07  a loading card (name and number known, skeleton bars, no empty-state sentences) that the answer
//           then fills in place: openPlayerCard(props) returns close(), and close.update(props) swaps the
//           content of the same layer, keeping the tab the reader picked (no second slide, no scrim blink).
//   LRP-08  close, a compact name and the tabs stay on screen on an opaque bar; 600 px wide from 700 px up;
//           one heading style (cardHeading, the DS-14 sub-heading with .player-card__h).
//   LRP-11  a thin top edge (the accent for ours, --opp for others), the team as a link in the bio line,
//           History's Team column and the transfer school as links.
//   LRP-13  the star line reads "★★★★☆ 94 · #123 nat": the rating on the 0-100 scale in its tier color, the
//           recruit rank as a chip (it links to the recruit list once the row carries its list key).
//   GX-13   (restrained) a 96x28 sparkline beside each Stats heading that has a trend, latest value labelled;
//           a 96 px headshot on navy with no color band.

import { DASH, el, fmtNum, fmtStat, isNum, layerZ, playerFace, rating100, ratingTier, retireLayer, starCount, syncPageLock, teamLink, text } from "./dom.js";
import { nationalHref } from "./national-link.js";
import { sparkline } from "./sparkline.js";
import { subhead } from "./states.js";
import { rankChip, statTable, statTableSkeleton } from "./stat-table.js";

/** A trimmed string, or null for anything that would print as a dash (null, numbers, objects, "[object Object]"). */
function str(value) {
  if (typeof value !== "string") return null;
  const t = text(value);
  return t === DASH ? null : t;
}

/** One heading style inside the card (LRP-08, DS-14). */
export function cardHeading(title) {
  const h = subhead(title);
  h.classList.add("player-card__h");
  return h;
}

/** The recruit-rank chip's list link, once the row carries its list key (stream NV adds recruit:<year>). */
export function recruitHref(player) {
  const key = [player?.recruitMetric, player?.recruit?.metric].find((m) => typeof m === "string" && m);
  return key ? nationalHref(key) : null;
}

function face(player, them) {
  return el("div", { class: `player-card__face${them ? " player-card__face--them" : ""}` }, playerFace(player, { them, abbr: str(player.teamAbbr) || undefined, size: 96 }));
}

/** "★★★★☆ 94 · #123 nat", or null when the player has no stars on record. */
function starLine(player) {
  const count = starCount(player.stars);
  if (count === null) return null;
  const score = rating100(player.rating);
  const tier = ratingTier(score);
  const chip = rankChip(player.recruitRank, null, { href: recruitHref(player), label: "Recruit rank" });
  return el(
    "div",
    { class: "player-card__stars" },
    el("span", { class: "stars", title: `${count}-star recruit` }, "★".repeat(count), "☆".repeat(5 - count)),
    score !== null || chip
      ? el(
          "span",
          { class: "player-card__rating" },
          score !== null ? el("span", { class: `rating${tier ? ` rating--${tier}` : ""}`, title: "247 composite rating" }, String(score)) : null,
          score !== null && chip ? " · " : null,
          chip,
          chip ? " nat" : null,
        )
      : null,
  );
}

/** "6-2" or 74 inches becomes 6' 2". Strings that are not a height pass through. */
export function fmtHeight(height) {
  if (isNum(height)) return `${Math.floor(height / 12)}' ${height % 12}"`;
  if (typeof height === "string") {
    const m = height.match(/^(\d+)-(\d+)$/);
    if (m) return `${m[1]}' ${m[2]}"`;
    return text(height);
  }
  return DASH;
}

function trendBlock(trend, them) {
  const values = Array.isArray(trend?.values) ? trend.values.filter(isNum) : [];
  if (values.length < 2) return null; // one game is not a trend
  const latest = values[values.length - 1];
  return el(
    "span",
    { class: "player-card__trend", title: `${text(trend.label)} by game, last ${values.length} games` },
    sparkline({ values, width: 96, height: 28, them }),
    el("span", { class: "player-card__trend-val" }, fmtStat(latest, trend.format || "0f"), el("small", {}, ` ${text(trend.label)}, last game`)),
  );
}

/**
 * Season table: columns come from the caller because they differ by position. Adds a career row
 * that sums the numeric columns marked `sum: true` and leaves the others as a dash.
 */
function oneSeasonsTable({ title, columns = [], rows = [], trend } = {}, them) {
  if (!Array.isArray(columns) || !Array.isArray(rows) || !columns.length || !rows.length) return null;
  const career = { year: "Career", isTotal: true };
  for (const col of columns) {
    if (col.key === "year") continue;
    if (col.kind === "text") career[col.key] = null;
    else if (col.sum) career[col.key] = rows.reduce((acc, row) => (isNum(row[col.key]) ? acc + row[col.key] : acc), 0);
    else if (col.max) career[col.key] = rows.reduce((acc, row) => (isNum(row[col.key]) && (acc === null || row[col.key] > acc) ? row[col.key] : acc), null);
    else if (col.avg && isNum(career[col.avg.num]) && isNum(career[col.avg.den]) && career[col.avg.den] > 0) career[col.key] = career[col.avg.num] / career[col.avg.den];
    else career[col.key] = null;
  }
  const spark = trendBlock(trend, them);
  return el(
    "div",
    { class: "player-card__block" },
    title ? el("div", { class: "player-card__hrow" }, cardHeading(title), spark) : null,
    statTable({ compact: true, sortable: false, columns, rows: [...rows, career], rowClass: (row) => (row.isTotal ? "is-total" : null) }),
  );
}

/** `seasons` is one table {columns, rows} or a list of them, one per category, each with a career row. */
function seasonsTable(seasons, them) {
  const tables = (Array.isArray(seasons) ? seasons : [seasons]).filter((t) => t && typeof t === "object").map((t) => oneSeasonsTable(t, them)).filter(Boolean);
  return tables.length ? el("div", {}, tables) : el("p", { class: "note" }, "No season stats yet.");
}

function tabbed(panels, selected) {
  const start = Math.max(0, panels.findIndex((p) => p.label === selected));
  const buttons = panels.map((panel, index) =>
    el("button", { class: "team-tab", type: "button", role: "tab", "aria-selected": index === start ? "true" : "false", onclick: () => select(index) }, panel.label),
  );
  const bodies = panels.map((panel, index) => el("div", { class: "player-card__panel", role: "tabpanel", "aria-label": panel.label, hidden: index !== start }, panel.body));
  function select(index) {
    buttons.forEach((b, i) => b.setAttribute("aria-selected", i === index ? "true" : "false"));
    bodies.forEach((b, i) => {
      if (i === index) b.removeAttribute("hidden");
      else b.setAttribute("hidden", "");
    });
  }
  return el("div", { class: "player-card__tabbed" }, el("div", { class: "player-card__tabs", role: "tablist" }, buttons), bodies);
}

/** "From Baylor, 3★ in the portal, 0.8900, entered Jan 4, 2026, immediate" from the portal record, or null (Phase 13). Exported for the tests. */
export function transferText(transfer) {
  if (!transfer || typeof transfer !== "object" || typeof transfer.from !== "string" || !transfer.from) return null;
  const parts = [`From ${transfer.from}`, isNum(transfer.stars) && transfer.stars > 0 ? `${transfer.stars}★ in the portal` : null, isNum(transfer.rating) ? Number(transfer.rating).toFixed(4) : null, typeof transfer.date === "string" && transfer.date ? `entered ${transfer.date}` : null, typeof transfer.eligibility === "string" && transfer.eligibility ? text(transfer.eligibility).toLowerCase() : null];
  return parts.filter(Boolean).join(", ");
}

/** The transfer fact with the old school as a link (LRP-11) and the portal rating on the 0-100 scale (LRP-13). */
function transferFact(transfer) {
  const from = str(transfer?.from);
  if (!transfer || typeof transfer !== "object" || !from) return null;
  const score = rating100(transfer.rating);
  const rest = [
    isNum(transfer.stars) && transfer.stars > 0 ? `${transfer.stars}★ in the portal` : null,
    score !== null ? `rated ${score}` : null,
    typeof transfer.date === "string" && transfer.date ? `entered ${transfer.date}` : null,
    typeof transfer.eligibility === "string" && transfer.eligibility ? text(transfer.eligibility).toLowerCase() : null,
  ].filter(Boolean);
  return el("span", {}, "From ", teamLink(from, from), rest.length ? `, ${rest.join(", ")}` : "");
}

/** The Recruit fact, cut to the class and the position he was recruited at (the star line has the rest). */
function recruitText(recruit, position) {
  if (!recruit || typeof recruit !== "object") return null;
  const parts = [
    isNum(recruit.year) || (typeof recruit.year === "string" && recruit.year) ? `${text(recruit.year)} class` : null,
    recruit.position && recruit.position !== position ? `as ${text(recruit.position)}` : null,
    recruit.type && recruit.type !== "HighSchool" ? text(recruit.type) : null,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : null;
}

function bioLine(player, them) {
  const bits = [];
  const school = str(player.team);
  if (school) bits.push(teamLink(school, school));
  else if (them && str(player.teamAbbr)) bits.push(str(player.teamAbbr));
  if (player.position) bits.push(text(player.position));
  if (player.classYear) bits.push(text(player.classYear));
  if (!bits.length) return el("div", { class: "player-card__bio" }, DASH);
  return el("div", { class: "player-card__bio" }, bits.flatMap((bit, i) => (i ? [" · ", bit] : [bit])));
}

function skeletonPanel() {
  return el("div", { class: "player-card__loading", "aria-hidden": "true" }, el("div", { class: "skel skel--bar player-card__skel-head" }), statTableSkeleton(3, 6));
}

/**
 * playerCard({ player: {name, number, position, classYear, team, teamAbbr, height, weight, hometown, highSchool,
 *                       stars, rating, recruitRank, recruit, transfer, headshotUrl},
 *              seasons: { title, columns: [{key, label, format, sum, max, avg}], rows: [{year, ...}], trend } or a list,
 *              seasonStats: [{label, value}]   (short list, used when `seasons` is absent)
 *              gameLog: [{ title, columns, rows }] (or the old [{opponent, line}]), history: [{year, team, classYear, position, number}],
 *              extras: [{ label, body }], them, onClose, inline, note, loading, tab })
 */
export function playerCard({ player = {}, seasons, seasonStats = [], gameLog = [], history = [], extras = [], them = false, onClose, inline = false, note = null, loading = false, tab = null } = {}) {
  const p = player && typeof player === "object" ? player : {};
  const stats = Array.isArray(seasonStats) ? seasonStats.filter((r) => r && typeof r === "object") : [];
  const log = Array.isArray(gameLog) ? gameLog.filter((r) => r && typeof r === "object") : [];
  const past = Array.isArray(history) ? history.filter((r) => r && typeof r === "object") : [];
  const recruit = recruitText(p.recruit, p.position);
  const transfer = transferFact(p.transfer);
  const facts = [
    ["Height, weight", `${fmtHeight(p.height)}, ${isNum(p.weight) ? `${p.weight} lb` : DASH}`],
    ["Hometown", text(p.hometown)],
    ["High school", text(p.highSchool)],
    ...(recruit ? [["Recruit", recruit]] : []),
    ...(transfer ? [["Transfer", transfer]] : []),
  ];

  const statsPanel = loading
    ? skeletonPanel()
    : el(
        "div",
        {},
        seasons ? seasonsTable(seasons, them) : null,
        !seasons && stats.length ? statTable({ compact: true, columns: [{ key: "label", label: "Stat", kind: "text" }, { key: "value", label: "Value", format: "raw" }], rows: stats }) : null,
        !seasons && !stats.length ? el("p", { class: "note" }, "No season stats yet.") : null,
      );
  const logPanel = loading
    ? skeletonPanel()
    : log.length
      ? Array.isArray(log[0].columns)
        ? el("div", {}, log.map((table) => el("div", { class: "player-card__block" }, cardHeading(text(table.title)), statTable({ compact: true, sortable: false, columns: table.columns, rows: Array.isArray(table.rows) ? table.rows : [] }))))
        : statTable({ compact: true, sortable: false, columns: [{ key: "opponent", label: "Game", kind: "text" }, { key: "line", label: "Line", kind: "text" }], rows: log })
      : el("p", { class: "note" }, "Game log appears after the first game.");
  const historyPanel = loading
    ? skeletonPanel()
    : past.length
      ? statTable({
          compact: true,
          sortable: false,
          columns: [
            { key: "year", label: "Year", kind: "text" },
            { key: "team", label: "Team", kind: "text", team: true },
            { key: "classYear", label: "Class", kind: "text" },
            { key: "position", label: "Pos", kind: "text" },
            { key: "number", label: "No." },
          ],
          rows: past,
        })
      : el("p", { class: "note" }, "No roster history for this player. Earlier seasons come from one roster call per year.");

  const name = `${isNum(p.number) ? `#${p.number} ` : ""}${text(p.name)}`;
  return el(
    "article",
    { class: `player-card${inline ? " player-card--inline" : ""}${loading ? " is-loading" : ""}`, "aria-label": `Player: ${text(p.name)}`, "aria-busy": loading ? "true" : null },
    inline
      ? null
      : el(
          "div",
          { class: "player-card__bar" },
          el("span", { class: "player-card__barname" }, name),
          el("button", { class: "btn btn--quiet icon-btn player-card__close", type: "button", "aria-label": "Close", onclick: onClose }, "×"),
        ),
    el(
      "div",
      { class: `player-card__hero player-card__hero--${them ? "them" : "us"}` },
      face(p, them),
      el(
        "div",
        { class: "player-card__who" },
        el("div", { class: "player-card__name" }, name),
        bioLine(p, them),
        loading ? null : starLine(p),
        loading
          ? el("div", { class: "player-card__facts-skel", "aria-hidden": "true" }, el("div", { class: "skel skel--row" }), el("div", { class: "skel skel--row" }))
          : el("dl", { class: "player-card__facts" }, facts.map(([label, value]) => [el("dt", {}, label), el("dd", {}, value)])),
      ),
    ),
    note ? el("p", { class: "note player-card__note" }, text(note)) : null,
    tabbed(
      [
        { label: "Stats", body: statsPanel },
        { label: "Game log", body: logPanel },
        ...(Array.isArray(extras) ? extras : []).filter((x) => x && x.label && x.body).map((x) => ({ label: x.label, body: loading ? skeletonPanel() : x.body })),
        { label: "History", body: historyPanel },
      ],
      tab,
    ),
  );
}

/** True when `layer` is the last overlay on the page, so Escape closes one layer at a time. */
export function isTopLayer(layer) {
  const layers = document.querySelectorAll(".card-layer, .sheet-layer");
  return layers.length > 0 && layers[layers.length - 1] === layer;
}

function selectedTab(article) {
  const on = article?.querySelector?.('.player-card__tabs [aria-selected="true"]');
  return on ? on.textContent : null;
}

/** Mount a slide-over card. Escape, the scrim or a route change closes it. Returns a close function;
 *  close.update(props) fills the same card in place (LRP-07) and does nothing once it is closed.
 *  Phase 16: it stacks above any open sheet, slides in and out, and locks the page underneath. */
export function openPlayerCard(props) {
  const layer = el("div", { class: "card-layer", open: true, "data-modal": true, style: { zIndex: layerZ() } });
  const opener = document.activeElement; // Phase 15: focus goes back here on close
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("kickoff:route", close);
    retireLayer(layer, "card-layer");
    if (opener && typeof opener.focus === "function" && document.contains(opener)) opener.focus();
  };
  const onKey = (event) => {
    if (event.key === "Escape" && isTopLayer(layer)) {
      event.stopPropagation();
      close();
    }
  };
  let article = playerCard({ ...props, onClose: close });
  layer.append(el("div", { class: "card-layer__scrim", onclick: close }), article);
  document.body.append(layer);
  document.addEventListener("keydown", onKey);
  document.addEventListener("kickoff:route", close); // bug 10: a link inside the card changes the page under it
  syncPageLock();
  const closeButton = layer.querySelector("button");
  if (closeButton) closeButton.focus();
  close.update = (next) => {
    if (closed || !article.isConnected) return false;
    const fresh = playerCard({ ...next, tab: next?.tab || selectedTab(article), onClose: close });
    // the same <article> keeps its place and its slide: only its content and labels change
    article.className = fresh.className;
    for (const name of ["aria-label", "aria-busy"]) {
      const value = fresh.getAttribute(name);
      if (value === null) article.removeAttribute(name);
      else article.setAttribute(name, value);
    }
    article.replaceChildren(...fresh.childNodes);
    article.scrollTop = 0;
    const button = article.querySelector(".player-card__close");
    if (button && document.activeElement && !article.contains(document.activeElement)) button.focus();
    return true;
  };
  close.layer = layer;
  return close;
}

export { fmtNum };
