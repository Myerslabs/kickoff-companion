// Editorial content written outside the app (a scheduled Claude task drops a notes file
// per game) and the availability table for the injury report. Both always show who wrote
// it, when, and from which sources, and both have an honest "not written yet" state.

import { el, fmtDateTime, text } from "./dom.js";
import { prose } from "./prose.js";
import { statTable } from "./stat-table.js";
import { fillWiki } from "./wiki-links.js";

/**
 * editorial({ byline: {author, writtenAt}, sources: [{label, url}], sections: [{heading, paragraphs}], names, onName, top })
 *   Not a wall of text (owner 2026-11-07): each section a block with a short head, two across on a wide band, its
 *   paragraphs through ui/prose.js (split, listed, led, the names it knows as taps: `names` from nameIndex(), onName(entry)).
 *   `top` (Wave 5, 2026-11-15): a node drawn under the byline and over the sections, the notes' layout (ui/notes-layout.js).
 */
/** Only the object rows of a list (a hand-written notes file can hold anything). */
function list(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object" && !Array.isArray(row)) : [];
}

/** A source row worth a line: a label or a web address (a hand-written row of nothing is left out of the fold and its count). */
const readable = (row) => (typeof row.label === "string" && row.label.trim() !== "") || (typeof row.url === "string" && /^https?:\/\//.test(row.url));

// Printing opens the folds (the reviewer, batch 4: the Print sheet promises "every folded section opened", and a closed
// <details> prints as its summary alone). The browser's own Ctrl+P and printNow (ui/print.js) both send beforeprint, so one
// listener covers both; afterprint closes again what printing opened.
let printWired = false;
function wirePrint() {
  if (printWired || typeof window === "undefined" || typeof window.addEventListener !== "function" || typeof document === "undefined") return;
  printWired = true;
  window.addEventListener("beforeprint", () => {
    for (const fold of document.querySelectorAll("details.editorial__fold:not([open])")) {
      fold.setAttribute("open", "");
      fold.dataset.printOpened = "1";
    }
  });
  window.addEventListener("afterprint", () => {
    for (const fold of document.querySelectorAll("details.editorial__fold")) {
      if (fold.dataset.printOpened !== "1") continue;
      fold.removeAttribute("open");
      delete fold.dataset.printOpened;
    }
  });
}

export function editorial({ byline = {}, sources = [], sections = [], names = null, onName = null, top = null } = {}) {
  wirePrint();
  const rows = list(sources).filter(readable);
  const blocks = list(sections).map((section) =>
    el(
      "section",
      { class: "editorial__block" },
      typeof section.heading === "string" && section.heading.trim() ? el("h3", { class: "editorial__head" }, section.heading.trim()) : null,
      ...prose(section.paragraphs, { names, onName, lead: true }),
    ),
  );
  const root = el(
    "div",
    { class: "editorial" },
    el(
      "div",
      { class: "editorial__byline" },
      el("span", {}, `Written by ${text(byline?.author)}`),
      el("span", {}, byline?.writtenAt ? fmtDateTime(byline.writtenAt) : "–"),
    ),
    top && typeof top === "object" && typeof top.nodeType === "number" ? top : null,
    blocks.length ? el("div", { class: "editorial__grid" }, blocks) : null,
    // Batch 4 part 1 (owner 2026-11-19: "remove the reference articles, or if not possible, we can make it a dropdown";
    // "yes fold"): the sources sit in a fold, closed, its count on the line; open, the list as before.
    rows.length
      ? el(
          "details",
          { class: "editorial__fold" },
          el("summary", {}, `Sources (${rows.length})`),
          el(
            "ul",
            { class: "editorial__sources" },
            rows.map((source) => el("li", {}, typeof source.url === "string" && /^https?:\/\//.test(source.url) ? el("a", { href: source.url, target: "_blank", rel: "noopener" }, typeof source.label === "string" && source.label.trim() ? source.label.trim() : source.url) : text(source.label))),
          ),
        )
      : null,
  );
  fillWiki(root); // a coach's name in the text is his page (ui/prose.js)
  return root;
}

export function editorialSkeleton() {
  return el("div", { class: "editorial" }, el("div", { class: "skel" }), el("div", { class: "skel skel--block" }), el("div", { class: "skel skel--block" }));
}

const STATUS_CLASS = { out: "out", doubtful: "doubtful", questionable: "questionable", "game-time decision": "questionable", probable: "probable", available: "available" };
// a status sorts by how likely the player is to miss the game: out first on the first tap (the kit's first direction for a
// number is high to low)
const STATUS_WEIGHT = { out: 6, doubtful: 5, questionable: 4, "game-time decision": 3, probable: 2, available: 1 };
// a phone's words for the two long statuses (the injury reports' own shorthand); the rest are short already
const STATUS_SHORT = { questionable: "Quest.", "game-time decision": "GTD" };

/** A row's status drawn with its color (a render, so the color survives the reader's sort; it once rode on the cell and a
 *  header tap that redrew the rows dropped it); { short: true } for small. */
function statusCell(row, { short = false } = {}) {
  const key = String(row.status || "").trim().toLowerCase();
  const cls = STATUS_CLASS[key];
  return el("span", { class: cls ? `avail-cell avail avail--${cls}` : "avail-cell", title: short && STATUS_SHORT[key] ? row.statusText : null }, short ? STATUS_SHORT[key] || row.statusText : row.statusText);
}

/**
 * availabilityTable({ rows: [{name, team, position, status, note}], source, updatedAt, showTeam = true, teams })
 * status: out | doubtful | questionable | game-time decision | probable | available
 * Sized by its own box (tables wave 3, owner decision 1): Player | Team | Pos | Status | Note, the team and the position each
 * in a column of its own at large and medium, the position gone at small, the note prose that wraps in the room the others
 * leave. The player's name steps down with the table (item 6: "K. Crawford", the surname, the reduced surname; a notes name
 * shortens only when it reads cleanly as First Last) and the two long statuses shorten at small (Quest., GTD), so a phone
 * keeps the note. Matching the report to a player (the lineups) always uses the name as written.
 * showTeam: false where every row is one team (the Injury Report, a team's side sheet); the team column also stays away when
 * no row names one. teams: [{ school, abbreviation }] for a report of two teams (the Pre-Game Program, In Game, the Archive):
 * when every row's team is one of them, the team stays at small as its abbreviation, so a phone still says whose player is
 * out; otherwise it is gone at small like the position. Players sort (the status by how likely he is to miss); the note
 * keeps a plain head.
 */
export function availabilityTable({ rows = [], source, updatedAt, showTeam = true, teams } = {}) {
  const word = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
  const abbr = new Map();
  for (const team of list(teams)) {
    const school = word(team.school);
    const short = word(team.abbreviation) || word(team.abbr);
    if (school && short && /[A-Za-z0-9]/.test(short)) abbr.set(school.toLowerCase(), short); // a page's dash for an unknown one is no abbreviation
  }
  const shaped = list(rows).map((row) => {
    const name = word(row.name) || (typeof row.name === "number" && Number.isFinite(row.name) ? String(row.name) : null);
    const team = word(row.team);
    const status = word(row.status);
    return {
      ...row,
      name,
      team,
      teamShort: team ? abbr.get(team.toLowerCase()) || null : null,
      position: word(row.position),
      note: word(row.note),
      status,
      statusText: status || "Not reported", // Phase 17: a row with no status is kept
      statusWeight: status ? STATUS_WEIGHT[status.toLowerCase()] || 0 : null,
    };
  });
  const named = shaped.filter((row) => row.team);
  const teamColumn = showTeam !== false && named.length > 0;
  const teamAtSmall = teamColumn && named.every((row) => row.teamShort);
  const columns = [
    { key: "name", label: "Player", kind: "text", person: { notes: true } }, // the notes' words: shortened only when they read cleanly
    teamColumn ? { key: "team", label: "Team", kind: "text", ...(teamAtSmall ? { shortKey: "teamShort" } : { size: "medium" }) } : null,
    shaped.some((row) => row.position) ? { key: "position", label: "Pos", kind: "text", size: "medium" } : null,
    { key: "statusText", label: "Status", kind: "text", sortKey: "statusWeight", render: (row) => statusCell(row), renderShort: (row) => statusCell(row, { short: true }) }, // at small the status wraps (components.css, wave 2, 2026-11-01): "Dismissed from the program" takes two lines on a phone instead of pushing the table past its band
    { key: "note", label: "Note", kind: "text", sortable: false, wrap: true },
  ].filter(Boolean);
  const table = statTable({
    compact: true,
    sizes: true, // 2026-10-10: sized like every table; the note is prose that wraps in the room the player and status leave
    columns,
    rows: shaped,
    caption: "Availability report",
  });
  return el(
    "div",
    { class: "avail-report" },
    table,
    source || updatedAt
      ? el("p", { class: "note" }, [source ? `Source: ${text(source)}.` : null, updatedAt ? ` Updated ${fmtDateTime(updatedAt)}.` : null].filter(Boolean).join(""))
      : null,
  );
}
