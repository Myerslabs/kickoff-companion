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
//   LRP-13  the star line reads (four stars of five) "Recruit rating 94 · #123 nationally": the rating on the 0-100 scale in its
//           tier color, the recruit rank as a chip (it links to the recruit list once the row carries its list key).
//           Phase 17 (owner 2026-10-07: "what are these numbers?"): both are labelled as recruiting numbers, so the
//           rating is never read as a second stat grade beside the Grade tab.
//   GX-13   (restrained) a 96x28 sparkline beside each Stats heading that has a trend, latest value labelled;
//           a 96 px headshot on navy with no color band.
//
// Tables wave 3 (owner 2026-10-10, docs/03-DESIGN.md "Table sizes"): every table on the card sizes itself by its own box,
// about 600 px from a 700 px screen and the phone's width below it: the Stats tab's seasons (a Career row from two seasons
// up, decision 3: the server loads the earlier seasons), the short stat list of a player with no full card, the game log
// (the table shape only; the old one-line shape is retired) and the History, whose seasons sort (newest first) with the
// team's abbreviation and "#" at small.

import { icon } from "./icons.js";
import { DASH, el, fmtDate, fmtNum, fmtStat, isNum, layerZ, personName, playerFace, rating100, ratingTier, retireLayer, sheetAnchor, starCount, swipeToClose, syncPageLock, teamLink, text, watchNames } from "./dom.js";
import { holdLayer, placeLayers } from "./layers.js";
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

/** Four stars of five, then "Recruit rating 94 · #123 nationally", or null when the player has no stars on record. */
function starLine(player) {
  const count = starCount(player.stars);
  if (count === null) return null;
  const score = rating100(player.rating);
  const tier = ratingTier(score);
  const chip = rankChip(player.recruitRank, null, { href: recruitHref(player), label: "Recruit rank" });
  return el(
    "div",
    { class: "player-card__stars" },
    el("span", { class: "stars", title: `${count}-star recruit`, role: "img", "aria-label": `${count}-star recruit` }, Array.from({ length: 5 }, (_, i) => icon(i < count ? "star" : "star-empty"))),
    score !== null || chip
      ? el(
          "span",
          { class: "player-card__rating" },
          score !== null ? [el("span", { class: "player-card__rating-label" }, "Recruit rating "), el("span", { class: `rating${tier ? ` rating--${tier}` : ""}`, title: "247Sports composite rating out of high school, 0 to 100" }, String(score))] : null,
          score !== null && chip ? " · " : null,
          chip,
          chip ? " nationally" : null,
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

/** The Career row: sums of the columns marked `sum: true`, the best of those marked `max`, rates recomputed from the summed
 *  columns they name (`avg: { num, den }`), a dash for the rest. Exported for the tests. */
export function careerRow(columns, rows) {
  const career = { year: "Career", isTotal: true };
  const own = columns.filter((col) => col.key !== "year");
  for (const col of own) {
    if (col.kind === "text") career[col.key] = null;
    else if (col.sum) career[col.key] = rows.reduce((acc, row) => (isNum(row[col.key]) ? acc + row[col.key] : acc), 0);
    else if (col.max) career[col.key] = rows.reduce((acc, row) => (isNum(row[col.key]) && (acc === null || row[col.key] > acc) ? row[col.key] : acc), null);
    else career[col.key] = null;
  }
  // the rates once every sum is in, whatever order the columns come in
  for (const col of own) {
    if (col.kind !== "text" && !col.sum && !col.max && col.avg && isNum(career[col.avg.num]) && isNum(career[col.avg.den]) && career[col.avg.den] > 0) career[col.key] = career[col.avg.num] / career[col.avg.den];
  }
  return career;
}

/**
 * Season table: columns come from the caller because they differ by position, one row a season, newest first. From two
 * seasons up a Career row closes it (decision 3: the server loads the earlier seasons, so the row sums real ones; with one
 * season it would only repeat that row). Never sorted, so the Career row stays last; sized by its own box (wave 3).
 */
function oneSeasonsTable({ title, columns = [], rows = [], trend } = {}, them) {
  if (!Array.isArray(columns) || !Array.isArray(rows) || !columns.length || !rows.length) return null;
  const cols = columns.filter((c) => c && typeof c === "object" && typeof c.key === "string");
  const seasons = rows.filter((r) => r && typeof r === "object");
  if (!cols.length || !seasons.length) return null;
  const spark = trendBlock(trend, them);
  return el(
    "div",
    { class: "player-card__block" },
    title ? el("div", { class: "player-card__hrow" }, cardHeading(title), spark) : null,
    statTable({ compact: true, sizes: true, sortable: false, columns: cols, rows: seasons.length > 1 ? [...seasons, careerRow(cols, seasons)] : seasons, rowClass: (row) => (row.isTotal ? "is-total" : null), caption: title ? `${text(title)} by season` : "By season" }),
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

/** "From Baylor, 3-star in the portal, 0.8900, entered Jan 4, 2026, immediate" from the portal record, or null (Phase 13). Exported for the tests. */
export function transferText(transfer) {
  if (!transfer || typeof transfer !== "object" || typeof transfer.from !== "string" || !transfer.from) return null;
  const parts = [`From ${transfer.from}`, isNum(transfer.stars) && transfer.stars > 0 ? `${transfer.stars}-star in the portal` : null, isNum(transfer.rating) ? Number(transfer.rating).toFixed(4) : null, typeof transfer.date === "string" && transfer.date ? `entered ${transfer.date}` : null, typeof transfer.eligibility === "string" && transfer.eligibility ? text(transfer.eligibility).toLowerCase() : null];
  return parts.filter(Boolean).join(", ");
}

/** The transfer fact with the old school as a link (LRP-11) and the portal rating on the 0-100 scale (LRP-13). */
function transferFact(transfer) {
  const from = str(transfer?.from);
  if (!transfer || typeof transfer !== "object" || !from) return null;
  const score = rating100(transfer.rating);
  const rest = [
    isNum(transfer.stars) && transfer.stars > 0 ? `${transfer.stars}-star in the portal` : null,
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
 *              gameLog: [{ title, columns, rows, sort }], history: [{year, team, teamAbbr, classYear, position, number}],
 *              extras: [{ label, body }], them, onClose, inline, note, loading, tab })
 */
export function playerCard({ player = {}, seasons, seasonStats = [], gameLog = [], history = [], extras = [], them = false, onClose, inline = false, note = null, loading = false, tab = null } = {}) {
  const p = player && typeof player === "object" ? player : {};
  const stats = Array.isArray(seasonStats) ? seasonStats.filter((r) => r && typeof r === "object") : [];
  const log = Array.isArray(gameLog) ? gameLog.filter((r) => r && typeof r === "object") : [];
  const yearOf = (r) => (isNum(Number(r.year)) ? Number(r.year) : -Infinity);
  const past = (Array.isArray(history) ? history.filter((r) => r && typeof r === "object") : []).sort((a, b) => yearOf(b) - yearOf(a)); // newest first (owner, 2026-10-08)
  const recruit = recruitText(p.recruit, p.position);
  const transfer = transferFact(p.transfer);
  const facts = [
    ...(isNum(p.age) ? [["Age", `${p.age}${typeof p.born === "string" && p.born ? ` (born ${fmtDate(p.born, "long")})` : ""}`]] : []), // Phase 17 #38: from the preseason load
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
        !seasons && stats.length ? statTable({ compact: true, sizes: true, columns: [{ key: "label", label: "Stat", kind: "text" }, { key: "value", label: "Value", format: "raw" }], rows: stats, caption: "Season stats" }) : null,
        !seasons && !stats.length ? el("p", { class: "note" }, "No season stats yet.") : null,
      );
  // one table per category (views/player.js gameLogTables), the latest game first; the games sort (wave 3)
  const logTables = log.filter((table) => Array.isArray(table.columns) && table.columns.length && Array.isArray(table.rows) && table.rows.length);
  const logPanel = loading
    ? skeletonPanel()
    : logTables.length
      ? el("div", {}, logTables.map((table) => el("div", { class: "player-card__block" }, cardHeading(text(table.title)), statTable({ compact: true, sizes: true, columns: table.columns, rows: table.rows, sort: table.sort && typeof table.sort === "object" ? table.sort : undefined, caption: `${text(table.title)} by game` }))))
      : el("p", { class: "note" }, "Game log appears after the first game.");
  const historyPanel = loading
    ? skeletonPanel()
    : past.length
      ? el(
          "div",
          {},
          // a table of seasons sorts, newest first to start (wave 3); nothing drops at small: the team's abbreviation (still its
          // link) and "#" for the number, as on the Roster; the class stays whole
          statTable({
            compact: true,
            sizes: true,
            columns: [
              { key: "year", label: "Year", kind: "text" },
              { key: "team", label: "Team", kind: "text", team: true, shortKey: "teamAbbr" },
              { key: "classYear", label: "Class", kind: "text" },
              { key: "position", label: "Pos", kind: "text" },
              { key: "number", label: "No.", labelShort: "#" },
            ],
            rows: past,
            sort: { key: "year", dir: "descending" },
            caption: "Roster history",
          }),
          past.length > 1 ? el("p", { class: "note" }, "Earlier classes count back a year a season from the latest one; a redshirt year does not show.") : null,
        )
      : el("p", { class: "note" }, "No roster history for this player yet.");

  const name = `${isNum(p.number) ? `#${p.number} ` : ""}${text(p.name)}`;
  return el(
    "article",
    { class: `player-card${inline ? " player-card--inline" : ""}${loading ? " is-loading" : ""}`, "aria-label": `Player: ${text(p.name)}`, "aria-busy": loading ? "true" : null },
    inline
      ? null
      : el(
          "div",
          { class: "player-card__bar" },
          // item 8: the › at the left slides the card away, the way it came in
          el("button", { class: "btn btn--quiet icon-btn player-card__close", type: "button", "aria-label": "Close", title: "Slide away", onclick: onClose }, icon("chevron-right")),
          el("span", { class: "player-card__barname" }, name),
        ),
    el(
      "div",
      { class: `player-card__hero player-card__hero--${them ? "them" : "us"}` },
      face(p, them),
      el(
        "div",
        { class: "player-card__who" },
        // owner 2026-10-11: one line only; the name steps down (full, "J. Surname", surname, reduced) before any "…"
        watchNames(el("div", { class: "player-card__name" }, isNum(p.number) ? `#${p.number} ` : null, personName(p, { fit: true }))),
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
 *  Phase 16: it stacks above any open sheet, slides in and out, and locks the page underneath.
 *  Item 6 (owner 2026-10-11): from 700 px up it starts under the top bar, like the side sheets; it takes one history entry,
 *  so Back closes it and stays on the page (ui/layers.js). close(reason): "self" (the default) takes the entry back out. */
export function openPlayerCard(props) {
  const layer = el("div", { class: "card-layer", open: true, "data-modal": true, style: { zIndex: layerZ() } });
  const opener = document.activeElement; // Phase 15: focus goes back here on close
  let closed = false;
  let release = null;
  const close = (reason) => {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("kickoff:route", onRoute);
    retireLayer(layer, "card-layer");
    if (release) release(typeof reason === "string" ? reason : "self"); // a click or a swipe hands in an event: by hand
    release = null;
    if (reason !== "route" && typeof window !== "undefined" && typeof window.scrollTo === "function") window.scrollTo(0, anchor.scrollY); // the page as the reader left it
    if (opener && typeof opener.focus === "function" && document.contains(opener)) opener.focus({ preventScroll: true });
  };
  const onRoute = () => close("route"); // bug 10: a link inside the card changes the page under it
  // one Escape closes one layer: a hint card or the status card above takes it first (they mark it handled)
  const onKey = (event) => {
    if (event.key === "Escape" && !event.defaultPrevented && isTopLayer(layer)) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  };
  let article = playerCard({ ...props, onClose: () => close() });
  layer.append(el("div", { class: "card-layer__scrim", onclick: () => close() }), article);
  swipeToClose(article, () => close()); // Phase 16 wave 3 (2B): a swipe right closes the card
  // under the top bar from 700 px up, on the page where the reader is, as tall as the card (item 8)
  const anchor = sheetAnchor(placeLayers());
  article.style.setProperty("--sheet-top", `${anchor.top}px`);
  document.body.append(layer);
  document.addEventListener("keydown", onKey);
  document.addEventListener("kickoff:route", onRoute);
  release = holdLayer((why) => close(why));
  syncPageLock();
  const closeButton = layer.querySelector("button");
  if (closeButton) closeButton.focus({ preventScroll: true });
  close.update = (next) => {
    if (closed || !article.isConnected) return false;
    const fresh = playerCard({ ...next, tab: next?.tab || selectedTab(article), onClose: () => close() });
    // the same <article> keeps its place and its slide: only its content and labels change
    article.className = fresh.className;
    for (const name of ["aria-label", "aria-busy"]) {
      const value = fresh.getAttribute(name);
      if (value === null) article.removeAttribute(name);
      else article.setAttribute(name, value);
    }
    article.replaceChildren(...fresh.childNodes);
    article.scrollTop = 0;
    if (typeof window !== "undefined" && typeof window.scrollTo === "function" && isFinite(window.scrollY) && window.scrollY > anchor.scrollY) window.scrollTo(0, anchor.scrollY); // another player starts from the top
    const button = article.querySelector(".player-card__close");
    if (button && document.activeElement && !article.contains(document.activeElement)) button.focus();
    return true;
  };
  close.layer = layer;
  return close;
}

export { fmtNum };
