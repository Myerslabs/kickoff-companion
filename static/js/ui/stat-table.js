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
//   statTable({ columns, rows, sort, onSort, onRowTap, rowClass, compact, maxHeight, caption, sortable, flow = "auto" })
//       col.link(row) -> href: the chip of a kind "rank" column links there.
//       col.rank.link(row) -> href: the chip in a value cell links there; col.rank.tie names a boolean field.
//       col.rank.placeholder: true keeps an invisible chip where a row has no rank.
//       col.render(row) -> node or text replacing the cell's value (a throw falls back to the value).
//       col.stick: true keeps the column in view when the table scrolls sideways (Rk and Team).
//       formats "rating100" (0.9379 -> 94, cell tinted by tier) and "stars" (4★), next to "1f", "pct" and the rest.
//       A table that fits its width lets go of its scroll box (.stat-table-wrap--fits) so its header sticks
//       under the top bar; flow: false keeps the box. A clipped table fades at its right edge.
//       rowClass(row) may return "is-us", "is-next" (the next opponent) or any other row class.
//   statTableSkeleton(rows = 4, cols = 4)  loading rows in the table's real shape.

import { el, fmtStat, isNum, rating100, ratingTier, replaceWith, teamLink, text } from "./dom.js";
import { parseRoute } from "./national-link.js";

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

/** A column's own cell content, or its value when there is no hook or the hook fails. */
function cellContent(row, column) {
  if (typeof column.render !== "function") return cellValue(row, column);
  try {
    const out = column.render(row);
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

/**
 * What a cell sorts by: [number, second number] for anything numeric, a lowercase string for words,
 * or null for an empty cell (a dash, nothing). Exported for the tests.
 */
export function sortValue(value) {
  if (isNum(value)) return [value, 0];
  if (value === null || value === undefined || typeof value === "boolean") return null;
  const raw = String(value).trim();
  if (!raw || raw === "–" || raw === "-" || raw === "—") return null;
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
  if (column.kind !== "text") return "descending";
  return values.some((v) => Array.isArray(sortValue(v))) ? "descending" : "ascending";
}

export function sortRows(rows, column, dir) {
  if (!column) return rows;
  const sign = dir === "ascending" ? 1 : -1;
  const key = column.sortKey || column.key;
  return [...rows].sort((a, b) => {
    const va = sortValue(a[key]);
    const vb = sortValue(b[key]);
    if (va === null && vb === null) return String(a[column.tieKey || "name"] ?? "").localeCompare(String(b[column.tieKey || "name"] ?? ""));
    if (va === null) return 1; // empty cells stay at the bottom either way
    if (vb === null) return -1;
    const order = compareValues(va, vb);
    if (order === 0) return String(a[column.tieKey || "name"] ?? "").localeCompare(String(b[column.tieKey || "name"] ?? ""));
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
function watchWidth(wrap, table, { flow, boxed, stuck }) {
  const measure = () => {
    const wide = table.scrollWidth;
    const room = wrap.clientWidth;
    if (!isNum(wide) || !isNum(room) || room <= 0) return;
    const fits = flow !== false && !boxed && wide <= room + 1;
    if (fits) wrap.classList.add("stat-table-wrap--fits");
    else wrap.classList.remove("stat-table-wrap--fits");
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
  // listener re-measures every table. No observer per table, so nothing is left behind when a view unmounts.
  let tries = 0;
  const first = () => {
    if (wrap.isConnected && wrap.clientWidth > 0) safe();
    else if (tries++ < 10) requestAnimationFrame(first);
  };
  // No layout engine (the Node tests' fake page has no clientWidth): nothing to measure, nothing scheduled.
  if (isNum(wrap.clientWidth) && typeof requestAnimationFrame === "function") requestAnimationFrame(first);
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

/**
 * statTable({ columns, rows, sort: {key, dir}, onSort({key, dir}), onRowTap, rowClass(row), compact, maxHeight, caption, flow })
 * `sort` is the starting order. `onSort` hears every change the reader makes and the returned
 * element's getSort() reads the current one, so a view that rebuilds the table keeps the order.
 */
export function statTable({ columns = [], rows = [], sort, onSort, onRowTap, rowClass, compact = false, maxHeight, caption, sortable, flow = "auto" }) {
  const cols = (Array.isArray(columns) ? columns : []).filter((c) => c && typeof c === "object");
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
            class: [column.kind === "text" ? "txt" : null, column.divider ? "col-div" : null, stickClass(index)].filter(Boolean).join(" ") || null,
            "aria-sort": active ? sortDir : null,
            style: stickStyle(index),
          });
          if (!sorts || column.kind === "rank-only") th.append(column.label);
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
                column.label,
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
        const tr = el("tr", {
          class: typeof rowClass === "function" ? rowClass(row) || null : null,
          tabindex: onRowTap ? "0" : null,
          role: onRowTap ? "button" : null,
        });
        if (onRowTap) rowTap(tr, row);
        cols.forEach((col, index) => {
          const tier = col.format === "rating100" ? ratingTier(rating100(row[col.key])) : "";
          const classes = [col.kind === "text" ? "txt" : col.dim ? "dim" : null, col.key === sortKey && sorts ? "is-sorted" : null, col.divider ? "col-div" : null, tier ? `rating rating--${tier}` : null, stickClass(index)].filter(Boolean);
          const td = el("td", { class: classes.length ? classes.join(" ") : null, style: stickStyle(index) });
          if (col.team && row[col.key] && typeof col.render !== "function") td.append(teamLink(row[col.key], text(row[col.key])));
          else td.append(cellContent(row, col));
          if (col.sub && row[col.sub]) td.append(el("small", {}, col.subTeam ? teamLink(row[col.sub], text(row[col.sub])) : text(row[col.sub])));
          if (col.kind === "rank") {
            td.append(rankChip(row[col.key], typeof col.of === "string" ? row[col.of] : col.of, { href: hookHref(col.link, row), label: chipLabel(row, col), tie: typeof col.tie === "string" ? row[col.tie] === true : false }) || "–");
          } else if (col.rank) {
            const chip = rankChip(row[col.rank.key], typeof col.rank.of === "string" ? row[col.rank.of] : col.rank.of, { href: hookHref(col.rank.link, row), label: chipLabel(row, col), tie: typeof col.rank.tie === "string" ? row[col.rank.tie] === true : false });
            if (chip) td.append(chip); // no rank known: the value stands alone, never the word null
            else if (col.rank.placeholder) td.append(rankChipPlaceholder());
          }
          tr.append(td);
        });
        return tr;
      }),
    );
    if (list.length === 0) tbody.append(el("tr", {}, el("td", { class: "txt", colspan: String(Math.max(1, cols.length)) }, "No rows.")));
  }

  renderHead();
  renderBody();
  const boxed = Boolean(maxHeight);
  const wrap = el("div", { class: `stat-table-wrap${boxed ? " stat-table-wrap--box" : ""}${stuck.length ? " stat-table-wrap--stuck" : ""}` }, table);
  if (maxHeight) wrap.style.setProperty("--table-max", typeof maxHeight === "number" ? `${maxHeight}px` : maxHeight);
  wrap.getSort = () => (sortKey ? { key: sortKey, dir: sortDir } : null);
  watchWidth(wrap, table, { flow, boxed, stuck });
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
