// The national list (Phase 16, stream NV; G3-01, DS-01, LRP-01, LRP-05): every team (or player) behind a
// rank chip, ranked exactly as the chip is, from GET /api/national/<metric>. One renderer serves the side
// sheet a chip opens over any page (never unmounting the Live sheet) and the full page (#national=...).
//
// API (other streams call these; the page streams only emit hrefs from national-link.js):
//   installNationalLinks()                     once, from app.js: a linked rank chip or poll badge (rankChip and
//       pollBadge offer "kickoff:rank-link") and any a.rank-chip--link, a.poll-badge--link or a.national-link
//       whose href is "#national=..." opens the list in a side sheet instead of navigating. A national chip
//       opens the national list, a conference chip (scope=conference in its href) the conference list.
//   openNationalSheet({ metric, team, year, scope } | href) -> the openSheet handle plus reload(), or null for
//       a malformed metric. Stacks over whatever is open; its 'Full page' link goes to #national=... (a poll
//       list to #season=polls:<poll>). The tapped team's row (team=, else ours) is marked and scrolled
//       into view by setting the scroller's scrollTop, never scrollIntoView.
//   listLink(metric, { team, year, scope, label, text = "National list" })  a quiet <a class="national-link">
//       for a value that has a list but no rank chip (the glossary, a blue-chip ratio). Null for a bad metric.
//   nationalApiUrl({ metric, team, year, scope })  the API path of a list.
//   nationalListBody(envelope, { onScope, onYear, onRetry })  the list itself: the label as th[scope=row] (so
//       its glossary hint works) with the summary line, the All FBS / conference and this season / last season
//       switches, the table, and for player lists the top 100, a gap row and every one of ours below the cut in a
//       second tbody.
//   The table sizes itself by its own box (tables wave 3, owner 2026-10-10; docs/03-DESIGN.md "Table sizes"). The rank is
//       the list's own order (decision 2): its chip (T for ties; a poll's badge) at large and medium, a plain number at
//       small, headed "FBS rank", "<conference> rank" or "<poll> rank" at large and the population alone below. A team is
//       its link (the abbreviation at small) with its conference in a column of its own at large and medium (decision 1:
//       the whole name at large, the short name at medium); a player is his name (stepping down with the table, item 6) with his
//       position and team in columns of their own at large and medium. The value keeps its bar at every size under its
//       label's three forms; the stars, a poll's first-place votes and a conference list's FBS rank from medium, the
//       percentile at large.
//   summaryText(data), listTitle(data), centerRow(root, { scroller })   exported for the view and the tests.

import { usSchool } from "../identity.js";
import { ageSeconds, fetchPatient } from "../views/common.js";
import { DASH, el, fmtNum, isNum, obj, personName, teamLink, text } from "./dom.js";
import { barCell, barScale, distributionStrip, pctlText, percentile } from "./national-bars.js"; // GX-04 (owner look)
import { isListHref, isMetric, nationalHref, nationalRoute, parseRoute, pollName, pollsPageHref } from "./national-link.js";
import { openSheet } from "./remote.js";
import { labelForms } from "./sizes.js";
import { band, stateBlock } from "./states.js";
import { ownColumns, pollBadge, statTable, statTableSkeleton } from "./stat-table.js";
import { conferenceColumn, teamAbbrLink } from "./team-page.js";


function list(value) {
  return Array.isArray(value) ? value.filter((r) => r && typeof r === "object" && !Array.isArray(r)) : [];
}

function cleanYear(year) {
  return isNum(year) || (typeof year === "string" && /^\d{4}$/.test(year)) ? String(year) : null;
}

/** The API path of one list. Null when the metric is malformed (nothing is fetched then). */
export function nationalApiUrl({ metric, team, year, scope } = {}) {
  if (!isMetric(metric)) return null;
  const query = [];
  if (typeof team === "string" && team.trim()) query.push(`team=${encodeURIComponent(team.trim())}`);
  const y = cleanYear(year);
  if (y) query.push(`year=${y}`);
  if (["conference", "opponents", "mine"].includes(scope)) query.push(`scope=${scope}`);
  return `/api/national/${encodeURIComponent(metric)}${query.length ? `?${query.join("&")}` : ""}`;
}

function wantOf(input) {
  if (typeof input === "string") {
    const route = parseRoute(input);
    return route && route.id === "national" ? nationalRoute(route) : null;
  }
  const w = obj(input);
  return { metric: isMetric(w.metric) ? w.metric : null, team: typeof w.team === "string" && w.team.trim() ? w.team.trim() : null, year: cleanYear(w.year) ? Number(cleanYear(w.year)) : null, scope: ["conference", "opponents", "mine"].includes(w.scope) ? w.scope : "national" };
}

function rowsOf(data) {
  return [...list(data.rows), ...list(data.beyond)];
}

function rankText(rank, tied, of) {
  if (!isNum(rank)) return "not ranked";
  return `${tied ? "T" : "#"}${rank}${isNum(of) ? ` of ${fmtNum(of)}` : ""}`;
}

/** 'Swampwater Tech #41 of 136 · ties share a rank · FBS teams' (the list's own facts, dashes never words like null). */
export function summaryText(data) {
  const d = obj(data);
  const us = obj(d.us);
  const of = isNum(d.of) ? d.of : null;
  const all = rowsOf(d);
  const population = typeof d.population === "string" && d.population.trim() ? d.population.trim() : "";
  if (!all.length) return population; // nothing ranked yet (or nothing loaded): no rank to claim
  const usRow = all.find((r) => r.isUs === true);
  const name = text(us.team || usSchool());
  const who = d.unit === "player" && typeof us.player === "string" && us.player.trim() ? `${name}: ${us.player.trim()}` : name;
  const parts = [`${who} ${rankText(us.rank, usRow?.tied === true, of)}`];
  const focus = obj(d.focus);
  if (typeof focus.team === "string" && focus.team && focus.team !== us.team) {
    const focusRow = all.find((r) => r.isFocus === true);
    const fwho = d.unit === "player" && typeof focus.player === "string" && focus.player.trim() ? `${focus.team}: ${focus.player.trim()}` : focus.team;
    parts.push(`${fwho} ${rankText(focus.rank, focusRow?.tied === true, of)}`);
  }
  if (d.tiesShare !== false && d.rankSource !== "cfbd") parts.push("ties share a rank");
  else if (d.rankSource === "cfbd" && d.family !== "poll") parts.push("CFBD's ranking");
  if (population) parts.push(population);
  return parts.join(" · ");
}

/** The sheet or band title: the stat, with the class, the season or the conference when it is not the default. */
export function listTitle(data) {
  const d = obj(data);
  const label = text(d.label || "National list");
  const bits = [];
  if (d.family === "recruit" && d.key) bits.push(`${text(d.key)} class`);
  else if (isNum(d.year) && isNum(d.season) && d.year !== d.season) bits.push(String(d.year));
  if (d.scope === "conference" && typeof d.conference === "string" && d.conference) bits.push(d.conference);
  if (d.scope === "opponents") bits.push(`${text(obj(d.us).team || usSchool())} and its opponents`);
  if (d.scope === "mine") bits.push("my teams");
  return bits.length ? `${label}, ${bits.join(", ")}` : label === DASH ? "National list" : label;
}

function conferenceName(d) {
  if (d.scope === "conference" && typeof d.conference === "string" && d.conference) return d.conference;
  const all = rowsOf(d);
  const pick = all.find((r) => r.isFocus === true) || all.find((r) => r.isUs === true);
  return typeof pick?.conference === "string" && pick.conference ? pick.conference : "Conference";
}

function seg(label, options, current, onPick) {
  return el(
    "div",
    { class: "seg nat-seg", role: "group", "aria-label": label },
    options.map(([value, name]) =>
      el("button", { type: "button", "aria-pressed": String(value) === String(current) ? "true" : "false", onclick: () => { if (String(value) !== String(current)) onPick(value); } }, name),
    ),
  );
}

function controls(d, { onScope, onYear }) {
  const out = [];
  const scopes = Array.isArray(d.scopes) ? d.scopes : [];
  // Public release Phase 5b: the opponents and My teams views are the national list cut down, so their ranks stay national.
  const options = [["national", "All FBS"]];
  if (scopes.includes("conference")) options.push(["conference", conferenceName(d)]);
  if (scopes.includes("opponents")) options.push(["opponents", "Opponents"]);
  if (scopes.includes("mine")) options.push(["mine", "My teams"]);
  if (typeof onScope === "function" && options.length > 1) {
    out.push(seg("Which teams", options, options.some(([value]) => value === d.scope) ? d.scope : "national", onScope));
  }
  const years = Array.isArray(d.years) ? d.years.filter(isNum) : [];
  if (typeof onYear === "function" && years.length > 1 && isNum(d.season)) {
    out.push(seg("Which season", years.map((y) => [y, y === d.season ? "This season" : y === d.season - 1 ? "Last season" : String(y)]), isNum(d.year) ? d.year : d.season, (y) => onYear(Number(y))));
  }
  return out.length ? el("div", { class: "nat-tools" }, out) : null;
}

function summaryTable(d) {
  return el(
    "table",
    { class: "nat-summary" },
    el("tbody", {}, el("tr", {}, el("th", { scope: "row" }, text(d.label || "National list")), el("td", {}, summaryText(d)))),
  );
}

function nextTag(row) {
  return row.isNext === true ? el("span", { class: "next-tag", title: "The next opponent" }, "Next") : null;
}

function teamOf(row) {
  return typeof row.team === "string" && row.team.trim() ? row.team.trim() : null;
}

/** A team's cell at large and medium: its link and the Next tag (its conference has a column of its own, decision 1). */
function teamCell(row) {
  return el("span", {}, teamLink(teamOf(row), text(row.team)), nextTag(row));
}

/** A player's name in its four forms (item 6: it steps down with the table), with the Next tag (his position and team
 *  have columns of their own). */
function playerCell(row) {
  return el("span", {}, el("span", { class: "nat-player" }, personName(row.player)), nextTag(row));
}

/** A player's team: its link, or "Uncommitted" for a recruit with no school yet. */
function playerTeam(row) {
  const team = teamOf(row);
  return team ? teamLink(team, team) : "Uncommitted";
}

function rowClass(row) {
  return [row.isUs === true ? "is-us" : null, row.isFocus === true ? "is-focus" : null, row.isNext === true ? "is-next" : null].filter(Boolean).join(" ") || null;
}

const words = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);

/** The value's head in its three forms (ui/sizes.js): the list's own name for its number ("Passing yards", "Pass yds"),
 *  "Value" when the server names none. Wave 3: the forms replace the old cut to "Value" for a long label. */
function valueHead(d) {
  return labelForms(words(d.valueLabel) || "Value");
}

/** The rank column's heads: the population with "rank" at large ("FBS rank", "BB rank", "AP rank"), the population alone
 *  at medium and small (rule 4; a conference by its short name). */
function rankHeads(d) {
  const poll = d.family === "poll";
  const word = poll ? pollName(d.key) || "Poll" : d.scope === "conference" ? words(d.conferenceShort) || words(d.conference) || "Conf" : "FBS";
  return { label: `${word} rank`, labelMid: word, labelShort: word };
}

/** The table's columns, sized by the table's own box (wave 3): the rank (the list's own order), the team or the player
 *  (each fact beside it in a column of its own), the value with its GX-04 data bar when a scale is given, the stars of a
 *  recruit list, the percentile, a poll's first-place votes and a conference list's FBS rank. */
export function listColumns(d, scale = null) {
  const player = d.unit === "player";
  const poll = d.family === "poll";
  // final pass: a rank column is headed by its population (FBS rank, <Conf> rank, <Poll> rank), never Rk or Nat
  const heads = rankHeads(d);
  const columns = [
    poll
      ? { key: "rank", ...heads, order: true, tieKey: "team", render: (r) => pollBadge(r.rank, d.key, { showPoll: false }) || DASH }
      : { key: "rank", ...heads, kind: "rank", order: true, of: isNum(d.of) ? d.of : undefined, tie: "tied", tieKey: player ? "player" : "team" },
  ];
  if (player) {
    columns.push({ key: "player", label: "Player", kind: "text", person: true, render: playerCell, renderShort: (r) => personName(r.player), sub: "position", subLabel: "Pos" }); // small: the name alone, no tag
    columns.push({ key: "team", label: "Team", kind: "text", size: "medium", render: playerTeam });
  } else {
    columns.push({ key: "team", label: "Team", kind: "text", render: teamCell, renderShort: (r) => teamAbbrLink(r.team, r.abbreviation) });
    if (d.scope !== "conference") columns.push(conferenceColumn()); // a conference list's teams share one conference
  }
  const format = typeof d.format === "string" && d.format !== "rank" ? d.format : "2f";
  const value = valueHead(d);
  if (d.valueless !== true) columns.push({ key: "value", label: value.long, labelMid: value.mid, labelShort: value.short, format, render: scale ? (r) => barCell(r, { scale, format }) : undefined });
  if (d.family === "recruit") columns.push({ key: "stars", label: "Stars", format: "stars", size: "medium" });
  if (scale && !poll) columns.push({ key: "pctl", label: "Pctl", size: "large", render: (r) => pctlText(r.pctl) });
  if (poll) columns.push({ key: "firstPlaceVotes", label: "1st", format: "0f", size: "medium" });
  if (d.scope === "conference") columns.push({ key: "nationalRank", label: "FBS rank", labelMid: "FBS", kind: "rank", size: "medium" });
  return columns;
}

function shapeRows(rows, d) {
  return rows.map((r) => ({ ...r, stars: obj(r.detail).stars ?? null, pctl: percentile(r.rank, d.of) }));
}

/** GX-04: the bar scale of a list. Top-N counting lists (player boards, polls) start at zero: the rest of the population
 *  is not in the answer, so its worst value is unknown. */
function listScale(d) {
  if (d.valueless === true) return null;
  return barScale(rowsOf(d).map((r) => r.value), { higher: d.higherIsBetter !== false, zero: d.family === "board" || d.family === "poll" }); // recruit ratings (0.87 to 1.00) run worst to best shown
}

function gapRow(d, beyond, span) {
  const shown = list(d.rows).length;
  const who = [...new Set(beyond.map((r) => (r.isUs === true ? text(obj(d.us).team || usSchool()) : text(r.team))))].join(" and ");
  const total = isNum(d.of) ? ` of ${fmtNum(d.of)}` : "";
  return el("tbody", { class: "nat-gap" }, el("tr", {}, el("td", { class: "txt", colspan: String(span) }, `Top ${fmtNum(shown)}${total} shown · ${who} below the cut`)));
}

function partErrors(d) {
  return Object.entries(obj(d.parts)).filter(([, p]) => obj(p).status === "error").map(([name, p]) => `${name}: ${text(obj(p).error)}`);
}

function notes(d) {
  const out = [];
  if (typeof d.note === "string" && d.note.trim()) out.push(d.note.trim());
  if (isNum(d.unranked) && d.unranked > 0) out.push(`${fmtNum(d.unranked)} ${d.unit === "player" ? "players" : "teams"} in this group have no figure yet and are not ranked.`);
  const failed = partErrors(d);
  if (failed.length && rowsOf(d).length) out.push(`Part of this list did not load (${failed.join("; ")}); the app asks again next time.`);
  return out.length ? el("p", { class: "note nat-note" }, out.join(" ")) : null;
}

/** The list: summary, switches, table and notes, or a designed empty or error block when there are no rows. */
export function nationalListBody(envelope, { onScope, onYear, onRetry } = {}) {
  const d = obj(obj(envelope).data);
  const rows = list(d.rows);
  const beyond = list(d.beyond);
  const head = [summaryTable(d), controls(d, { onScope, onYear })];
  if (!rows.length && !beyond.length) {
    const failed = partErrors(d);
    const block = failed.length
      ? stateBlock({ kind: "error", lead: "This list could not be loaded.", detail: `${failed.join("; ")}. The app asks CFBD again when you open it next.`, action: typeof onRetry === "function" ? { label: "Try now", onClick: onRetry } : null })
      : stateBlock({ lead: "No team has a figure for this yet.", detail: typeof d.note === "string" && d.note.trim() ? d.note.trim() : "The list fills in once CFBD publishes the numbers behind it." });
    return el("div", { class: "nat" }, head, block);
  }
  const scale = listScale(d);
  const columns = listColumns(d, scale);
  const wrap = statTable({ columns, rows: shapeRows(rows, d), rowClass, compact: true, sizes: true, caption: listTitle(d) });
  if (beyond.length) {
    // ours below the cut: the same sized cells (their size classes and forms), kept under the first table's head and size
    const table = wrap.querySelector("table");
    const second = statTable({ columns, rows: shapeRows(beyond, d), rowClass, compact: true, sizes: true, sortable: false }).querySelector("tbody");
    if (table && second) {
      second.classList.add("nat-beyond");
      table.append(gapRow(d, beyond, ownColumns(columns).length), second);
    }
  }
  return el("div", { class: "nat" }, head, distributionStrip(d, scale), wrap, notes(d));
}

/** The band state of an envelope: stale with its age when the server served an old list. */
export function listState(envelope) {
  const meta = obj(obj(envelope).meta);
  if (meta.stale === true) return { status: "stale", ageSeconds: ageSeconds(meta.fetched_at), message: "CFBD is not answering; this is the last list the app has." };
  return { status: "ready" };
}

function scrollerOf(root) {
  let node = root;
  while (node && node !== document.body && node !== document.documentElement) {
    // item 8: a sheet lies on the page and scrolls with it; only a sheet body that scrolls itself (the styleguide's
    // inline sample) is the scroller, otherwise the page is
    if (node.classList && node.classList.contains("side-sheet__body")) return typeof getComputedStyle === "function" && /(auto|scroll)/.test(getComputedStyle(node).overflowY || "") ? node : null;
    node = node.parentNode;
  }
  return null;
}

/** Scroll the marked row (the tapped team's, else ours) to the middle of its scroller and flash it. */
export function centerRow(root, { scroller } = {}) {
  if (!root || typeof root.querySelector !== "function") return null;
  const row = root.querySelector("tbody tr.is-focus") || root.querySelector("tbody tr.is-us");
  if (!row) return null;
  try {
    const box = scroller || scrollerOf(row);
    const r = row.getBoundingClientRect();
    if (box) {
      const b = box.getBoundingClientRect();
      const top = (box.scrollTop || 0) + (r.top - b.top) - Math.max(0, (b.height - r.height) / 2);
      box.scrollTop = Math.max(0, top);
    } else if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      const height = isNum(window.innerHeight) ? window.innerHeight : 0;
      window.scrollTo(0, Math.max(0, (window.scrollY || 0) + r.top - Math.max(0, (height - r.height) / 2)));
    }
    row.classList.add("nat-arrived");
  } catch (error) {
    console.error("The national list could not scroll to the team's row.", error);
  }
  return row;
}

function afterLayout(fn) {
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => requestAnimationFrame(fn));
  else setTimeout(fn, 0);
}

function fullHref(want, data) {
  if (data && data.family === "poll" && typeof data.key === "string") return pollsPageHref(data.key);
  return nationalHref(want.metric, { team: want.team, year: want.year, scope: want.scope }) || "#season";
}

function loadingBody() {
  return band({ bare: true, title: "National list", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(14, 3) });
}

function errorMessage(error) {
  if (error?.name === "AbortError") return "The server did not answer in time.";
  if (error?.status === 404) return `${text(error.message)}`;
  return `${text(error?.message || "The request failed")}.`;
}

/** Open a list in a side sheet over the current page. */
export function openNationalSheet(input) {
  const want = wantOf(input);
  if (!want || !want.metric) return null;
  const full = el("a", { class: "btn btn--quiet nat-full", href: fullHref(want) }, "Full page");
  const handle = openSheet({ title: "National list", body: loadingBody(), tools: full, className: "nat-sheet" });
  let seq = 0;
  const bodyEl = handle.layer.querySelector(".side-sheet__body");

  async function load() {
    const mine = ++seq;
    full.setAttribute("href", fullHref(want));
    try {
      const envelope = await fetchPatient(nationalApiUrl(want), { current: () => mine === seq });
      if (mine !== seq) return;
      const data = obj(envelope.data);
      handle.setTitle(listTitle(data));
      full.setAttribute("href", fullHref(want, data));
      handle.setBody(band({
        bare: true,
        title: listTitle(data),
        collapsible: false,
        state: listState(envelope),
        body: () => nationalListBody(envelope, {
          onScope: (scope) => { want.scope = scope; handle.setBody(loadingBody()); load(); },
          onYear: (year) => { want.year = year; handle.setBody(loadingBody()); load(); },
          onRetry: () => load(),
        }),
      }));
      afterLayout(() => centerRow(bodyEl, { scroller: bodyEl }));
    } catch (error) {
      if (mine !== seq) return;
      handle.setBody(stateBlock({ kind: "error", lead: error?.status === 404 ? "There is no such list." : "Could not load this list.", detail: errorMessage(error), action: error?.status === 404 ? null : { label: "Try now", onClick: () => load() } }));
    }
  }

  load();
  return { ...handle, reload: load, want };
}

/** A quiet link to a list, for a value that has one but carries no rank chip. */
export function listLink(metric, { team, year, scope, label, text: words = "National list" } = {}) {
  const href = nationalHref(metric, { team, year, scope });
  if (!href) return null;
  const name = typeof label === "string" && label.trim() ? `${label.trim()}: ` : "";
  return el("a", { class: "national-link", href, "aria-label": `${name}open the ${scope === "conference" ? "conference" : "national"} list` }, `${text(words)} ›`);
}

let installed = false;

/** Chips, poll badges and list links open their list in a side sheet (app.js installs this once). */
export function installNationalLinks(doc = typeof document !== "undefined" ? document : null) {
  if (installed || !doc || typeof doc.addEventListener !== "function") return false;
  installed = true;
  doc.addEventListener("kickoff:rank-link", (event) => {
    const href = event?.detail?.href;
    if (!isListHref(href)) return; // a ratings or polls page link navigates as before
    try {
      if (openNationalSheet(href)) event.preventDefault();
    } catch (error) {
      console.error("The national list sheet could not open; following the link instead.", error);
    }
  });
  doc.addEventListener("click", (event) => {
    if (event.defaultPrevented) return;
    const link = event.target && typeof event.target.closest === "function" ? event.target.closest("a.rank-chip--link, a.poll-badge--link, a.national-link") : null;
    const href = link ? link.getAttribute("href") : null;
    if (!isListHref(href)) return;
    try {
      if (openNationalSheet(href)) event.preventDefault();
    } catch (error) {
      console.error("The national list sheet could not open; following the link instead.", error);
    }
  });
  return true;
}
