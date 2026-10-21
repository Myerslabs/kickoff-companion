// The stat table: sticky header, sortable columns, rank chips beside numbers, row tap.
// Columns: { key, label, kind: "num"|"text"|"rank", format, sub, rank: { key, of, tie, link, placeholder },
//            sortKey, link, render, stick, divider, team, dim }.
//
// Every column of a table of players, teams, games or seasons sorts (owner direction 2026-09-26).
// A table whose rows are stat names (its first column is "label" or "option": Team stats,
// quarter splits, the fourth-down choices) keeps its rows in their written order, since sorting
// it would only shuffle the stats; `sortable: true` or `false` on the table overrides either way.
// Text cells sort by what they mean: "3 of 8" by its rate, "10-16" and "7/12" by the first number
// then the second, "+0.24", "43%" and "5.4" as numbers, words alphabetically; a dash is always last.
//
// Phase 16 (stream F) frozen API:
//   rankChip(rank, of, { href, label, tie, ordinalPrefix = "#" })  a quartile-toned chip (rule 7: the look is
//       unchanged by linking). With href it is <a class="rank-chip rank-chip--link"> whose screen-reader name is
//       "label: 41 of 138. Open the national list"; its click never reaches a tappable row, and it is first
//       offered to "kickoff:rank-link" listeners on document (detail { href, rank, of, label }). A listener that
//       calls preventDefault() on that event takes the click over (the national side sheet); otherwise the
//       link navigates. tie: true prints "T41". Returns null when rank is not a number.
//   rankChipPlaceholder()  an invisible chip so values in rows without a rank line up with the others.
//   pollBadge(rank, poll, { href, label, showPoll = true })  a square poll badge ("AP 12"), its own style,
//       a link with href (offered to "kickoff:rank-link" the same way). Null when rank is not a number.
//   statTable({ columns, rows, sort, onSort, onRowTap, canTap, rowClass, compact, caption, sortable, flow = "auto" })
//     canTap(row): false leaves that row plain (no tap, no focus), e.g. a player the server could not match to an id
//       No table scrolls up and down inside itself (owner 2026-10-10, his phone): every row is on the page and its
//       band folds. An old caller's maxHeight is ignored. A table wider than its room scrolls sideways only.
//       col.link(row) -> href: the chip of a kind "rank" column links there.
//       col.rank.link(row) -> href: the chip in a value cell links there; col.rank.tie names a boolean field.
//       col.rank.placeholder: true keeps an invisible chip where a row has no rank.
//       col.render(row) -> node or text replacing the cell's value (a throw falls back to the value).
//       col.stick: true keeps the column in view when the table scrolls sideways (Rk and Team).
//       formats "rating100" (0.9379 -> 94, cell tinted by tier) and "stars" (4-star), next to "1f", "pct" and the rest.
//       A table that fits its width lets go of its scroll box (.stat-table-wrap--fits) so its header sticks
//       under the top bar; flow: false keeps the box. A clipped table fades at its right edge.
//       rowClass(row) may return "is-us", "is-next" (the next opponent) or any other row class.
//   statTableSkeleton(rows = 4, cols = 4)  loading rows in the table's real shape.
//   applyStatSize(wrap, size), sizedText(long, mid, short)  a hand-built table sized in place (the pass zones, the scores):
//       the wrap's data-size and a label's three forms in the sz-t spans the stylesheet shows one of per size.
//
// Tables wave 3 (owner 2026-10-10), the kit's shared pieces, each declared on a column of a sized table (sizes: true);
// an unsized table draws exactly as before:
//   sub + subLabel  a second fact under a name (a player's position, a team's conference, a recruit's school) is its OWN
//       headed column right after the name at large and medium, gone at small (rule 3: every data point in its own
//       column). subLabelMid and subLabelShort are its head's shorter words, subSize "large" keeps it to large, subTeam
//       makes its cells team links. Without subLabel (or in an unsized table) the sub stays a small line under the name.
//   order: true  a column that is the list's own order (the national lists, a recruiting class, the polls: the row's place
//       in the list, not a rank beside a value): the rank chip at large and medium (kind "rank"; or the column's render,
//       a poll badge), a plain number at small ("T41" for a tie, col.tie naming the field), where chips never show.
//   renderShort(row) -> node or text  a drawn cell's own small form (a team's abbreviation inside its team link, so the tap
//       survives at small); render draws large and medium. Wins over shortKey, which prints plain text at small.
//   kind "rank" on a group row (row.isGroup === true, the advanced table's Overall or Downs) leaves its cell empty.
//   sortable: false on a column keeps that column's head plain (no sort button) while the rest of the table sorts (a
//       note, a status, the star mix); the table's own sortable still decides whether anything sorts.
//   sortValue reads an ISO date ("2026-09-05", "2026-09-05T19:30:00Z") as the moment it names, not its year.
//
// Player names (item 6, owner 2026-10-11: "K. Crawford" when there is no room, one line only):
//   person: true  a column of player names (its key holds the name). The table draws each name once in its four forms
//       (ui/dom.js personName) and steps down as ONE table (ui/sizes.js personSteps): large with full names, large with
//       "K. Crawford", medium and small with "K. Crawford", small with the surname, the reduced surname ("Brackwater-M."), and
//       last the clip (the reduced form cut with an ellipsis at a measured width, the full name in its title, the row's
//       tap and card unchanged). A name never wraps. Two players who would read alike get a second letter, and players who
//       share a surname keep "K. Crawford" at the surname steps (ui/dom.js distinctNames), within the one table.
//   person: { first, last, notes, after }  the same, with the row's fields holding CFBD's split (first: "firstName",
//       last: "lastName", which wins over the string rules), notes: true for a name from the notes (AI-written text: it
//       shortens only when it reads cleanly), after(row) -> words kept after whichever form shows (" (RS)").
//   A person column with a render draws the name itself (personName inside the drawing, a face beside it); its
//   renderShort the small form. Matching a name (availability, the depth charts) always uses the row's full string.

import { append, DASH, el, fmtStat, isNum, nameSteps, personName, rating100, ratingTier, replaceWith, settleNames, teamLink, text } from "./dom.js";
import { parseRoute } from "./national-link.js";
import { applyNames, DROPPED, fitSize, labelForms, personSteps, SIZES, sizeNote, splitStep, watchSize } from "./sizes.js";

// Sizes (owner 2026-10-10, ui/sizes.js): statTable({ sizes: true }) draws at large, medium or small by its own box like
// the two-team table. A column's `size` ("medium" or "large") names the smallest size that still shows it; a head's
// labelMid and labelShort are its shorter words; the first text column's labels shorten through ui/sizes.js.
// Nothing wraps, nothing scrolls sideways; a table that cannot fit even at small shows at small anyway (the minimal
// table, never a note, owner 2026-10-10). The one exception to "nothing wraps" is a column of prose (`wrap: true`, the
// depth chart's "then, in order" names): it wraps inside its cell
// and takes whatever room the other columns leave, so it never decides the size. A column's `shortKey` names the
// row field with a cell's short form (a team's abbreviation beside its name), shown at small.
const MIN_CLASS = { medium: "st__min-medium", large: "st__min-large" };

/** A label in its three forms (one shows per size), or plain text when they are all the same word. Exported for a
 *  hand-built table sized in place (the scores table, wave 2): its spans follow the wrap's data-size like a statTable's. */
export function sizedText(long, mid, short) {
  const a = text(long);
  const b = typeof mid === "string" && mid.trim() ? text(mid) : a; // guarded like the long form: never "[object Object]"
  const c = typeof short === "string" && short.trim() ? text(short) : b;
  if (a === b && b === c) return [a];
  return [el("span", { class: "sz-t sz-t--long" }, a), el("span", { class: "sz-t sz-t--mid" }, b), el("span", { class: "sz-t sz-t--short" }, c)];
}

/** Draw a sized wrap at one size: the attribute the stylesheet keys on, and the note that stands in for a dropped table.
 *  A step may name the player names' form too ("small/last"); a table of players given a plain size shows full names at
 *  large and "K. Crawford" below it. */
export function applyStatSize(wrap, size) {
  const step = size === DROPPED ? { size: DROPPED, form: null } : splitStep(size);
  const base = step.size;
  wrap.dataset.size = base;
  if (wrap.__people === true) applyNames(wrap, step.form || (base === "large" ? "full" : "initial"));
  else if (step.form) applyNames(wrap, step.form);
  const table = wrap.querySelector("table");
  const note = wrap.querySelector(".size-note");
  if (base === DROPPED) {
    wrap.classList.add("stat-table-wrap--dropped");
    if (table) table.hidden = true;
    if (!note) wrap.append(sizeNote());
  } else {
    wrap.classList.remove("stat-table-wrap--dropped");
    if (table) table.hidden = false;
    if (note) note.remove();
  }
}

/** Quartile tone for a rank out of `of`: "top" (green), "mid" (yellow), "bottom" (red), or "" when unknown. */
export function rankTone(rank, of) {
  if (!isNum(rank) || !isNum(of) || of <= 0) return "";
  if (rank <= Math.max(1, Math.ceil(of * 0.25))) return "top";
  if (rank > of - Math.ceil(of * 0.25)) return "bottom";
  return "mid";
}

function listWord(href) {
  const route = parseRoute(href);
  if (!route) return "list";
  if (route.id === "ratings") return "ratings";
  if (route.id === "season") return "polls";
  if (/^poll:/.test(route.arg || "")) return "poll";
  return route.params?.scope === "conference" ? "conference list" : "national list";
}

/** Offer a list link to the page (the national sheet) before the browser follows it. */
function offerLink(event, detail) {
  event.stopPropagation(); // a chip inside a tappable row must not open the row's player card too
  const offer = new CustomEvent("kickoff:rank-link", { detail, cancelable: true });
  document.dispatchEvent(offer);
  if (offer.defaultPrevented) event.preventDefault();
}

function stopRowKeys(event) {
  if (event.key === "Enter" || event.key === " ") event.stopPropagation(); // the link's own Enter, not the row's
}

function isHashLink(href) {
  return typeof href === "string" && href.startsWith("#") && href.length > 1;
}

export function rankChip(rank, of, { href, label, tie = false, ordinalPrefix = "#" } = {}) {
  if (!isNum(rank)) return null;
  const tone = rankTone(rank, of);
  const prefix = tie ? "T" : typeof ordinalPrefix === "string" ? ordinalPrefix : "#";
  const ofText = isNum(of) ? ` of ${of}` : "";
  const title = `${tie ? "Tied at " : ""}${rank}${ofText || ""}`;
  const cls = `rank-chip${tone ? ` rank-chip--${tone}` : ""}`;
  const body = [prefix ? el("span", { class: "rank-chip__hash" }, prefix) : null, String(rank)];
  if (!isHashLink(href)) return el("span", { class: cls, title: isNum(of) ? title : `Rank ${rank}` }, body);
  const name = typeof label === "string" && label.trim() ? label.trim() : null;
  const aria = `${name ? `${name}: ` : ""}${tie ? "tied at " : ""}${rank}${ofText}. Open the ${listWord(href)}`;
  return el(
    "a",
    { class: `${cls} rank-chip--link`, href, "aria-label": aria, title, onclick: (event) => offerLink(event, { href, rank, of: isNum(of) ? of : null, label: name }), onkeydown: stopRowKeys },
    body,
  );
}

/** An invisible chip so a value without a rank lines up with the values that have one. */
export function rankChipPlaceholder() {
  return el("span", { class: "rank-chip rank-chip--placeholder", "aria-hidden": "true" }, "#00");
}

/** A poll rank: a square badge ("AP 12"), never the quartile chip (owner answer 2026-09-28). */
export function pollBadge(rank, poll, { href, label, showPoll = true } = {}) {
  if (!isNum(rank)) return null;
  const name = typeof poll === "string" && poll.trim() ? poll.trim() : null;
  const body = [el("span", { class: "poll-badge__poll" }, showPoll && name ? name : "#"), el("span", { class: "poll-badge__rank" }, String(rank))];
  const title = `${name ? `${name} poll` : "Poll"}: No. ${rank}`;
  if (!isHashLink(href)) return el("span", { class: "poll-badge", title }, body);
  const lead = typeof label === "string" && label.trim() ? `${label.trim()}, ` : "";
  return el(
    "a",
    { class: "poll-badge poll-badge--link", href, "aria-label": `${lead}${title}. Open the ${name ? `${name} poll` : "poll"}`, title, onclick: (event) => offerLink(event, { href, rank, poll: name, label: lead ? label.trim() : null }), onkeydown: stopRowKeys },
    body,
  );
}

function cellValue(row, column) {
  const value = row[column.key];
  if (column.kind === "rank") return "";
  if (column.kind === "text") return text(value);
  if (column.format) return fmtStat(value, column.format);
  if (typeof value === "string") return text(value);
  return fmtStat(value, "0f");
}

/** A column's own cell content (its render, or another drawing hook such as renderShort), or its value when there is no
 *  hook or the hook fails. */
function cellContent(row, column, hook = column.render) {
  if (typeof hook !== "function") return cellValue(row, column);
  try {
    const out = hook(row);
    if (out === null || out === undefined || out === false || (typeof out === "number" && !Number.isFinite(out))) return "–";
    // an array of parts is wrapped (td.append(array) would print "[object ...]")
    if (typeof out === "object") return typeof Node !== "undefined" && out instanceof Node ? out : Array.isArray(out) ? el("span", {}, out) : text(null);
    return text(out);
  } catch (error) {
    console.error(`statTable: the ${text(column.label)} column could not draw a cell; showing its value.`, error);
    return cellValue(row, column);
  }
}

function hookHref(hook, row) {
  if (typeof hook !== "function") return null;
  try {
    const href = hook(row);
    return isHashLink(href) ? href : null;
  } catch (error) {
    console.error("statTable: a link hook failed; the chip stays plain.", error);
    return null;
  }
}

function chipLabel(row, column) {
  if (typeof row?.label === "string" && row.label.trim()) return row.label;
  return typeof column.label === "string" ? column.label : null;
}

const RATE = /^(\d+(?:\.\d+)?)\s+of\s+(\d+(?:\.\d+)?)$/i;
const PAIR = /^(\d+(?:\.\d+)?)\s*[-/]\s*(\d+(?:\.\d+)?)$/;
const NUMBER = /^[+-−]?\d+(?:\.\d+)?\s*%?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

/**
 * What a cell sorts by: [number, second number] for anything numeric (an ISO date by the moment it names, wave 3: it
 * once sorted by its year alone), a lowercase string for words, or null for an empty cell (a dash, nothing). Exported for
 * the tests.
 */
export function sortValue(value) {
  if (isNum(value)) return [value, 0];
  if (value === null || value === undefined || typeof value === "boolean") return null;
  const raw = String(value).trim();
  if (!raw || raw === "–" || raw === "-" || raw === "—") return null;
  if (ISO_DATE.test(raw)) {
    const at = Date.parse(raw);
    if (Number.isFinite(at)) return [at, 0];
  }
  const rate = RATE.exec(raw);
  if (rate) return Number(rate[2]) > 0 ? [Number(rate[1]) / Number(rate[2]), Number(rate[2])] : [-1, 0];
  const pair = PAIR.exec(raw);
  if (pair) return [Number(pair[1]), -Number(pair[2])];
  if (NUMBER.test(raw)) return [Number(raw.replace("−", "-").replace("%", "").replace("+", "")), 0];
  const lead = /^#?(\d+)\b/.exec(raw); // "#12", "12 of 130" style ranks
  if (lead) return [Number(lead[1]), 0];
  return raw.toLowerCase();
}

function compareValues(a, b) {
  if (Array.isArray(a) && Array.isArray(b)) return a[0] - b[0] || a[1] - b[1];
  if (Array.isArray(a)) return 1; // numbers above words when descending
  if (Array.isArray(b)) return -1;
  return String(a).localeCompare(String(b));
}

/** The first direction when a header is tapped: words A to Z, ranks best first (#1 up), other numbers high to low. Exported for the tests. */
export function firstDirection(rows, column) {
  const key = column.sortKey || column.key;
  const values = (Array.isArray(rows) ? rows : []).map((row) => row?.[key]).filter((v) => v !== null && v !== undefined && v !== "");
  const rankLike = column.kind === "rank" || /rank|^place$|^#$/i.test(String(key)) || /^#/.test(String(column.label || "")) || (values.length > 0 && values.every((v) => typeof v === "string" && /^#\d/.test(v.trim())));
  if (rankLike) return "ascending";
  // a column of years, seasons, dates or weeks sorts newest first on the first tap (owner, 2026-10-08)
  if (/^(year|season|date|dateText|week|wk|kickoff)$/i.test(String(key)) || /^(year|season|date|wk|week)$/i.test(String(column.label || "").trim())) return "descending";
  if (column.kind !== "text") return "descending";
  return values.some((v) => Array.isArray(sortValue(v))) ? "descending" : "ascending";
}

export function sortRows(rows, column, dir) {
  if (!column) return rows;
  const sign = dir === "ascending" ? 1 : -1;
  const key = column.sortKey || column.key;
  // a tie keeps the tie key's order whichever way the sort runs: numbers as numbers (the road ahead's schedule order, so
  // game 10 follows game 2), anything else alphabetically (wave 3 review)
  const tieKey = column.tieKey || "name";
  const tieOf = (a, b) => (isNum(a[tieKey]) && isNum(b[tieKey]) ? a[tieKey] - b[tieKey] : String(a[tieKey] ?? "").localeCompare(String(b[tieKey] ?? "")));
  return [...rows].sort((a, b) => {
    const va = sortValue(a[key]);
    const vb = sortValue(b[key]);
    if (va === null && vb === null) return tieOf(a, b);
    if (va === null) return 1; // empty cells stay at the bottom either way
    if (vb === null) return -1;
    const order = compareValues(va, vb);
    if (order === 0) return tieOf(a, b);
    return sign * order;
  });
}

/** Whether a table sorts: an explicit `sortable`, else not when its rows are stat names. Exported for the tests. */
export function tableSorts(columns, sortable) {
  if (sortable === true || sortable === false) return sortable;
  const first = Array.isArray(columns) ? columns[0]?.key : null;
  return !["label", "option"].includes(first);
}

/** Watch the wrap: flow mode when the table fits, the right-edge fade and the stuck-column shadow when it does not. */
function watchWidth(wrap, table, { flow, stuck }) {
  const measure = () => {
    // the table's own width, not scrollWidth: a linked chip's invisible press area pokes a few pixels past the last cell and
    // made a fitting table count as a scroller (2026-10-10, the iPad's rubber-banding tables)
    const wide = isNum(table.offsetWidth) && table.offsetWidth > 0 ? table.offsetWidth : table.scrollWidth;
    const room = wrap.clientWidth;
    if (!isNum(wide) || !isNum(room) || room <= 0) return;
    const fits = flow !== false && wide <= room + 1;
    if (fits) wrap.classList.add("stat-table-wrap--fits");
    else wrap.classList.remove("stat-table-wrap--fits");
    // owner 2026-10-10 (a touch screen): a table with nothing to the left or right never moves sideways, so a finger on it
    // scrolls the page and nothing rubber-bands; only a wider table keeps its sideways scroll
    if (wide <= room + 1) {
      wrap.classList.add("stat-table-wrap--still");
      wrap.classList.remove("stat-table-wrap--scrolls");
    } else {
      wrap.classList.remove("stat-table-wrap--still");
      wrap.classList.add("stat-table-wrap--scrolls"); // wider than its room: the one case a wrap is a scroll box (until its wave sizes it)
    }
    const left = isNum(wrap.scrollLeft) ? wrap.scrollLeft : 0;
    if (!fits && left + room < wide - 1) wrap.classList.add("stat-table-wrap--more");
    else wrap.classList.remove("stat-table-wrap--more");
    if (left > 0) wrap.classList.add("is-scrolled-x");
    else wrap.classList.remove("is-scrolled-x");
    if (stuck.length) {
      // A frozen column's resting place is the width of every column before it. Not its offsetLeft: once a
      // stuck header has moved, offsetLeft includes the sticky shift, so a later measure (a scroll, fonts
      // arriving) would push the column over its neighbour (Phase 16 SEASON fix).
      const heads = [...table.querySelectorAll("thead th")];
      for (const index of stuck) {
        const widths = heads.slice(0, index).map((th) => th.offsetWidth);
        if (heads[index] && widths.every(isNum)) wrap.style.setProperty(`--stick-${index}`, `${widths.reduce((sum, w) => sum + w, 0)}px`);
      }
    }
  };
  const safe = () => {
    try {
      measure();
    } catch (error) {
      console.error("statTable: could not measure a table.", error);
    }
  };
  wrap.measure = safe;
  // Measured in the scroll event itself, so a frozen column is placed before the first scrolled frame is
  // drawn, even for a table that was folded away or hidden when it was built.
  wrap.addEventListener("scroll", safe, { passive: true });
  // First measure once the table is on the page (a few frames at most); after that the one shared resize
  // listener re-measures every table.
  let tries = 0;
  const first = () => {
    if (wrap.isConnected && wrap.clientWidth > 0) safe();
    else if (tries++ < 10) requestAnimationFrame(first);
  };
  // No layout engine (the Node tests' fake page has no clientWidth): nothing to measure, nothing scheduled.
  if (isNum(wrap.clientWidth) && typeof requestAnimationFrame === "function") requestAnimationFrame(first);
  // 2026-10-10 (review of "no scroll box"): the wrap's own width is watched too. A table built in a folded band (width 0
  // until it unfolds) or measured before the page's columns settled was never measured again, and with no box to scroll a
  // table wider than its room was clipped by its band. Same width again (our own re-layout): nothing to redo.
  if (isNum(wrap.clientWidth) && typeof ResizeObserver === "function") {
    let last = -1;
    const observer = new ResizeObserver(() => {
      const width = wrap.clientWidth;
      if (!isNum(width) || width === last || width <= 0) return;
      last = width;
      safe();
    });
    observer.observe(wrap);
    wrap.widthObserver = observer; // kept on the wrap: an observer nothing references can be collected before a folded table is laid out
  }
  hookResize();
}

let resizeHooked = false;
function hookResize() {
  if (resizeHooked || typeof window === "undefined" || typeof window.addEventListener !== "function") return;
  resizeHooked = true;
  let queued = false;
  window.addEventListener(
    "resize",
    () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        for (const wrap of document.querySelectorAll(".stat-table-wrap")) if (typeof wrap.measure === "function") wrap.measure();
      });
    },
    { passive: true },
  );
}

/** A string's trimmed words, or null for a blank or anything else. */
function words(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/**
 * Decision 1 (owner 2026-10-10, rule 3): in a sized table, a column whose second fact (sub) has a head (subLabel) is
 * followed by that fact's own column, shown at large and medium (subSize "large": large only) and gone at small; the
 * name's cell loses the line under it. Columns without a subLabel are kept as they are. Exported for the tests.
 */
export function ownColumns(columns) {
  const out = [];
  for (const col of Array.isArray(columns) ? columns : []) {
    if (!col || typeof col !== "object") continue;
    const head = words(col.subLabel);
    if (typeof col.sub !== "string" || !col.sub || !head) {
      out.push(col);
      continue;
    }
    out.push({ ...col, sub: null });
    out.push({ key: col.sub, label: head, labelMid: words(col.subLabelMid), labelShort: words(col.subLabelShort), kind: "text", size: col.subSize === "large" ? "large" : "medium", team: col.subTeam === true, tieKey: col.tieKey });
  }
  return out;
}

/**
 * Two tables side by side end on one line (Design rules, owner 2026-10-21: "Tables, if side by side, should attempt to match
 * headers and length so as to avoid long spaces of empty screen"): the shorter one's body gets blank rows up to the longer
 * one's count. A sort redraws a table's own rows, so the pad goes with it until the pair is drawn again.
 */
export function matchRows(pair) {
  if (!pair || typeof pair.querySelectorAll !== "function") return pair;
  const tables = [...pair.children].map((child) => (child && typeof child.querySelector === "function" ? child.querySelector("table.stat-table") : null));
  if (tables.length < 2 || tables.some((table) => !table)) return pair;
  const bodies = tables.map((table) => table.querySelector("tbody"));
  if (bodies.some((body) => !body)) return pair;
  const counts = bodies.map((body) => [...body.querySelectorAll("tr")].filter((tr) => !(tr.className || "").split(/\s+/).includes("is-pad")).length);
  const most = Math.max(...counts);
  bodies.forEach((body, i) => {
    for (const old of [...body.querySelectorAll("tr.is-pad")]) old.remove();
    const cols = tables[i].querySelectorAll("thead th").length || 1;
    for (let n = counts[i]; n < most; n += 1) body.append(el("tr", { class: "is-pad", "aria-hidden": "true" }, Array.from({ length: cols }, () => el("td", {}, DASH))));
  });
  return pair;
}

/** Two parts side by side (.twocol), their first tables matched in length. */
export function twoCol(...parts) {
  return matchRows(el("div", { class: "twocol" }, parts.filter((part) => part !== null && part !== undefined && part !== false)));
}

/** A person column's cell (item 6): the name in its four forms, from the row's string or CFBD's split, any words after it. */
export function personCell(row, col) {
  const p = col && col.person && typeof col.person === "object" ? col.person : {};
  const split = typeof p.first === "string" || typeof p.last === "string";
  const numberKey = typeof p.number === "string" ? p.number : "number";
  const number = isNum(row[numberKey]) ? row[numberKey] : null; // the last name step (Design rules, 2026-10-21)
  const input = split ? { name: row[col.key], firstName: row[p.first], lastName: row[p.last], number } : number !== null ? { name: row[col.key], number } : row[col.key];
  let after = "";
  if (typeof p.after === "function") {
    try {
      after = p.after(row);
    } catch (error) {
      console.error("statTable: a name's trailing words could not be drawn.", error);
    }
  }
  return personName(input, { notes: p.notes === true, after: typeof after === "string" ? after : "" });
}

/** A list's own order at small (decision 2): the plain number, "T41" for a tie, a dash when there is none. */
function orderText(row, col) {
  const value = row[col.key];
  if (isNum(value)) return `${typeof col.tie === "string" && row[col.tie] === true ? "T" : ""}${value}`;
  return text(value);
}

/**
 * statTable({ columns, rows, sort: {key, dir}, onSort({key, dir}), onRowTap, rowClass(row), compact, caption, flow })
 * `sort` is the starting order. `onSort` hears every change the reader makes and the returned
 * element's getSort() reads the current one, so a view that rebuilds the table keeps the order.
 */
export function statTable({ columns = [], rows = [], sort, onSort, onRowTap, canTap, rowClass, compact = false, caption, sortable, flow = "auto", sizes = false }) {
  const sized = sizes === true;
  const given = (Array.isArray(columns) ? columns : []).filter((c) => c && typeof c === "object");
  const cols = sized ? ownColumns(given) : given; // a sized table draws a sub with a head as its own column (decision 1)
  const list = (Array.isArray(rows) ? rows : []).filter((r) => r && typeof r === "object"); // one bad row never breaks the table
  const sorts = tableSorts(cols, sortable);
  let sortKey = typeof sort?.key === "string" ? sort.key : null;
  let sortDir = sort?.dir === "ascending" ? "ascending" : "descending";
  const stuck = cols.map((c, i) => (c.stick ? i : -1)).filter((i) => i >= 0);
  const lastStuck = stuck.length ? stuck[stuck.length - 1] : -1;
  const stickClass = (index) => (stuck.includes(index) ? `stick${index === lastStuck ? " stick--edge" : ""}` : null);
  const stickStyle = (index) => (stuck.includes(index) && index > 0 ? { left: `var(--stick-${index}, 0px)` } : null);

  const table = el("table", { class: `stat-table${compact ? " stat-table--compact" : ""}` });
  const thead = el("thead");
  const tbody = el("tbody");
  if (caption) table.append(el("caption", { class: "sr-only" }, caption));
  table.append(thead, tbody);

  function renderHead() {
    replaceWith(
      thead,
      el(
        "tr",
        {},
        cols.map((column, index) => {
          const active = column.key === sortKey;
          const th = el("th", {
            scope: "col",
            class: [column.kind === "text" ? "txt" : null, column.divider ? "col-div" : null, stickClass(index), sized ? MIN_CLASS[column.size] || null : null].filter(Boolean).join(" ") || null,
            "aria-sort": active ? sortDir : null,
            style: stickStyle(index),
            dataset: sized && typeof (column.term || column.label) === "string" ? { term: column.term || column.label } : null, // column.term: the glossary label when the head's words are shared (a box score's Yards)
          });
          const headWords = sized ? sizedText(column.label, column.labelMid, column.labelShort) : column.label;
          if (!sorts || column.kind === "rank-only" || column.sortable === false) append(th, [headWords]); // a column of notes or statuses keeps a plain head
          else {
            th.append(
              el(
                "button",
                {
                  type: "button",
                  onclick: () => {
                    if (active) sortDir = sortDir === "descending" ? "ascending" : "descending";
                    else {
                      sortKey = column.key;
                      sortDir = firstDirection(list, column);
                    }
                    renderHead();
                    renderBody();
                    if (typeof onSort === "function") onSort({ key: sortKey, dir: sortDir });
                  },
                },
                headWords,
              ),
            );
          }
          return th;
        }),
      ),
    );
  }

  function rowTap(tr, row) {
    tr.addEventListener("click", (event) => {
      // A link or button inside the row (a rank chip, a team name) does its own job, never the row's.
      const inner = event.target && typeof event.target.closest === "function" ? event.target.closest("a, button, input, select, textarea") : null;
      if (inner && inner !== tr && tr.contains(inner)) return;
      onRowTap(row);
    });
    tr.addEventListener("keydown", (event) => {
      if (event.target && event.target !== tr) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onRowTap(row);
      }
    });
  }

  function renderBody() {
    const column = cols.find((c) => c.key === sortKey);
    const ordered = sortRows(list, column, sortDir);
    replaceWith(
      tbody,
      ordered.map((row) => {
        const taps = typeof onRowTap === "function" && (typeof canTap !== "function" || canTap(row) !== false);
        const tr = el("tr", {
          class: typeof rowClass === "function" ? rowClass(row) || null : null,
          tabindex: taps ? "0" : null,
          role: taps ? "button" : null,
        });
        if (taps) rowTap(tr, row);
        cols.forEach((col, index) => {
          const tier = col.format === "rating100" ? ratingTier(rating100(row[col.key])) : "";
          const classes = [col.kind === "text" ? "txt" : col.dim ? "dim" : null, col.key === sortKey && sorts ? "is-sorted" : null, col.divider ? "col-div" : null, tier ? `rating rating--${tier}` : null, stickClass(index), sized ? MIN_CLASS[col.size] || null : null, sized && col.wrap ? "st__wrap" : null, col.person ? "st__person" : null].filter(Boolean);
          const td = el("td", { class: classes.length ? classes.join(" ") : null, style: stickStyle(index) });
          const short = sized && typeof col.shortKey === "string" && typeof row[col.shortKey] === "string" && row[col.shortKey].trim() ? row[col.shortKey].trim() : null;
          const ownChip = () => rankChip(row[col.key], typeof col.of === "string" ? row[col.of] : col.of, { href: hookHref(col.link, row), label: chipLabel(row, col), tie: typeof col.tie === "string" ? row[col.tie] === true : false });
          if (row.isGroup === true && col.kind === "rank") {
            tr.append(td); // a group's title row carries no rank: its cell stays empty, never a dash
            return;
          }
          const ordered = sized && col.order === true;
          if (ordered) {
            // the list's own order (decision 2): the chip (or the column's own drawing, a poll badge) at large and medium,
            // a plain number at small, where no chip shows
            const full = col.kind === "rank" ? ownChip() || DASH : cellContent(row, col);
            append(td, [el("span", { class: "sz-t sz-t--long sz-t--mid" }, full), el("span", { class: "sz-t sz-t--short" }, orderText(row, col))]);
          } else if (sized && typeof col.renderShort === "function") {
            // a drawn cell with its own small form (a team link with the abbreviation): the tap survives at small
            const full = col.team && row[col.key] && typeof col.render !== "function" ? teamLink(row[col.key], text(row[col.key])) : col.person && typeof col.render !== "function" ? personCell(row, col) : cellContent(row, col);
            append(td, [el("span", { class: "sz-t sz-t--long sz-t--mid" }, full), el("span", { class: "sz-t sz-t--short" }, cellContent(row, col, col.renderShort))]);
          } else if (col.person && typeof col.render !== "function") td.append(personCell(row, col)); // a player's name in its four forms
          else if (col.team && row[col.key] && typeof col.render !== "function") td.append(teamLink(row[col.key], short ? sizedText(row[col.key], null, short) : text(row[col.key]))); // a team's name shortens to its abbreviation at small
          else if (short && typeof col.render === "function") append(td, [el("span", { class: "sz-t sz-t--long sz-t--mid" }, cellContent(row, col)), el("span", { class: "sz-t sz-t--short" }, short)]); // a drawn cell at large and medium, its short word at small
          else if (short) append(td, [sizedText(row[col.key], null, short)]);
          else if (sized && index === 0 && col.kind === "text" && typeof col.render !== "function" && typeof row[col.key] === "string") {
            const f = labelForms(row[col.key]); // a stat name shortens with the size (ui/sizes.js); its hint keeps the long one
            td.dataset.term = f.long;
            append(td, [sizedText(f.long, f.mid, f.short)]);
          } else td.append(cellContent(row, col));
          if (col.sub && row[col.sub]) td.append(el("small", {}, col.subTeam ? teamLink(row[col.sub], text(row[col.sub])) : text(row[col.sub])));
          if (col.kind === "rank") {
            if (!ordered) td.append(ownChip() || "–"); // an ordered column drew its chip above, in its sizes' span
          } else if (col.rank) {
            const href = hookHref(col.rank.link, row);
            const chip = rankChip(row[col.rank.key], typeof col.rank.of === "string" ? row[col.rank.of] : col.rank.of, { href, label: chipLabel(row, col), tie: typeof col.rank.tie === "string" ? row[col.rank.tie] === true : false });
            if (href && td.childNodes.length && String(td.textContent || "").trim() !== DASH) {
              // the number links to its list too (Design rules, owner 2026-10-21), the same offer the chip makes
              const link = el("a", { class: "st__val-link", href, onclick: (event) => offerLink(event, { href, rank: isNum(row[col.rank.key]) ? row[col.rank.key] : null, of: null, label: chipLabel(row, col) }), onkeydown: stopRowKeys }, [...td.childNodes]);
              td.replaceChildren(link);
            }
            if (chip) td.append(chip); // no rank known: the value stands alone, never the word null
            else if (col.rank.placeholder) td.append(rankChipPlaceholder());
          }
          tr.append(td);
        });
        return tr;
      }),
    );
    if (list.length === 0) tbody.append(el("tr", {}, el("td", { class: "txt", colspan: String(Math.max(1, cols.length)) }, "No rows.")));
    // the names of each person column settled within the table: a second letter for two who would read alike, the
    // initial kept for players who share a surname
    cols.forEach((col, index) => {
      if (col.person) settleNames([...tbody.querySelectorAll("tr")].map((tr) => tr.children[index]));
    });
  }

  renderHead();
  renderBody();
  const wrap = el("div", { class: `stat-table-wrap${stuck.length ? " stat-table-wrap--stuck" : ""}` }, table);
  wrap.getSort = () => (sortKey ? { key: sortKey, dir: sortDir } : null);
  if (sized) {
    const people = cols.some((c) => c.person);
    if (people) wrap.__people = true;
    applyStatSize(wrap, people ? "large/full" : "large");
    watchSize(wrap, () => {
      const size = fitSize(wrap, table, (step) => applyStatSize(wrap, step), people ? personSteps(SIZES, nameSteps(table)) : SIZES);
      if (size === null) return;
      if (size === DROPPED) wrap.classList.remove("stat-table-wrap--fits");
      else wrap.classList.add("stat-table-wrap--fits"); // never a scroll box: the header sticks
    });
  } else watchWidth(wrap, table, { flow, stuck });
  return wrap;
}

function count(value, low, high, fallback) {
  return isNum(value) ? Math.min(high, Math.max(low, Math.round(value))) : fallback;
}

/** The skeleton in a table's real shape: a header strip, alternating rows, a label bar and short value bars. */
export function statTableSkeleton(rows = 4, cols = 4) {
  const r = count(rows, 1, 40, 4);
  const c = count(cols, 1, 12, 4);
  const line = (head) => el("div", { class: `skel-table__row${head ? " skel-table__row--head" : ""}`, style: { "--skel-cols": String(c) } }, Array.from({ length: c }, (_, j) => el("span", { class: `skel skel--cell${j === 0 ? " skel--label" : ""}` })));
  return el("div", { class: "skel-table", "aria-hidden": "true" }, line(true), Array.from({ length: r }, () => line(false)));
}
