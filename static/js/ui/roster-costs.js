// Rumored roster costs (Phase 17 Part 3b, owner 2026-10-07: "Is there a place we could put roster costs?"; "it's ok
// if they cant be found, or are guessed at the press articles"; "keep it as 'rumored'"). The roster-costs load on
// the Preseason page saves a rumored total for every team and, for the primary teams, position groups and players.
// This band shows one team's: the total with what it covers and its date, then positions, then players, then the
// sources. Every figure is labelled rumored; nothing here is official.
//
//   costsBand(costs, { id, team, outside })  -> the band; an empty state says where the load is run (outside: a team the
//                                              loads leave out, 2026-10-16)
//
// Tables wave 3 (owner 2026-10-10): both tables size themselves by their own box. Position groups: Position group ("Group"
// at small) | Amount | Note, the note prose that wraps in the room the others leave, at every size. Player values: Player
// (stepping down with the table, item 6) | Pos | Amount | Note, the rumor note gone at small (owner's call: three narrow columns leave a
// phone's note no room). A column of notes shows only when a row has one. The groups keep their written order; the players
// sort, the biggest figure first.

import { DASH, el, fmtDate, fmtUsd, isNum, str, text } from "./dom.js";
import { band } from "./states.js";
import { statTable } from "./stat-table.js";
import { OUTSIDE } from "./school-facts.js";

function rows(value) {
  return (Array.isArray(value) ? value : []).filter((r) => r && typeof r === "object");
}

/** A dollar figure, or null when the report has none (a dash in the table, last in a sort). */
function usd(value) {
  return isNum(value) && value >= 0 ? value : null;
}

const NOTE = { key: "note", label: "Note", kind: "text", sortable: false, wrap: true }; // press-report prose: the one column that wraps

/** Rumored spending by position group, in the report's own order. Exported for the tests. */
export function groupsTable(positions) {
  const list = rows(positions).filter((p) => str(p.group)).map((p) => ({ group: str(p.group), amountUsd: usd(p.amountUsd), note: str(p.note) }));
  const columns = [{ key: "group", label: "Position group", labelShort: "Group", kind: "text" }, { key: "amountUsd", label: "Amount", format: "usd" }, list.some((p) => p.note) ? NOTE : null].filter(Boolean);
  return statTable({ compact: true, sizes: true, sortable: false, caption: "Rumored spending by position group", columns, rows: list });
}

/** Rumored player values, the biggest first; the players sort. Exported for the tests. */
export function playersTable(players) {
  const list = rows(players).filter((p) => str(p.name)).map((p) => ({ name: str(p.name), position: str(p.position), amountUsd: usd(p.amountUsd), note: str(p.note) }));
  const columns = [
    { key: "name", label: "Player", kind: "text", person: { notes: true } }, // the load's words (AI-written): shortened only when they read cleanly
    { key: "position", label: "Pos", kind: "text" },
    { key: "amountUsd", label: "Amount", format: "usd" },
    list.some((p) => p.note) ? { ...NOTE, size: "medium" } : null,
  ].filter(Boolean);
  return statTable({ compact: true, sizes: true, caption: "Rumored player values", sort: { key: "amountUsd", dir: "descending" }, columns, rows: list });
}

export function costsBand(costs, { id = "roster-costs", team, outside = false } = {}) {
  const c = costs && typeof costs === "object" ? costs : null;
  const positions = rows(c?.positions).filter((p) => str(p.group));
  const players = rows(c?.players).filter((p) => str(p.name));
  const sources = rows(c?.sources).filter((s) => str(s.label) || str(s.url));
  const has = c && (isNum(c.totalUsd) || positions.length || players.length);
  const when = str(c?.asOf) ? fmtDate(c.asOf, "long") : null;
  return band({
    id,
    title: "Roster costs (rumored)",
    collapsible: true,
    foldable: true,
    summary: has && isNum(c.totalUsd) ? `${fmtUsd(c.totalUsd)} total, rumored` : c ? "looked for, none reported" : "",
    state: has ? { status: "ready" } : !c && outside ? { status: "empty", message: `Not loaded. ${OUTSIDE}`, action: { label: "Open Settings", href: "#settings" } } : { status: "empty", message: c ? `No figure was reported for ${text(team || c.school)} when the load ran${str(c.savedAt) ? ` (${fmtDate(c.savedAt, "short")})` : ""}.` : "Not loaded yet." , action: { label: "Open Load data", href: "#prompts" } },
    body: () =>
      el(
        "div",
        { class: "costs" },
        el("p", { class: "costs__total" }, el("span", { class: "costs__label" }, "Rumored total "), el("b", {}, isNum(c.totalUsd) ? fmtUsd(c.totalUsd) : DASH), when ? el("small", {}, ` as of ${when}`) : null),
        str(c.note) ? el("p", { class: "note" }, c.note) : null,
        positions.length ? groupsTable(positions) : null,
        players.length ? playersTable(players) : null,
        el("p", { class: "note" }, "Figures are rumored or estimated from press reports and NIL valuation sites; schools don't publish them.", sources.length ? [" Sources: ", sources.map((s, i) => [i ? ", " : null, str(s.url) && /^https?:\/\//.test(s.url) ? el("a", { href: s.url, target: "_blank", rel: "noopener" }, str(s.label) || s.url) : text(s.label)])] : null),
      ),
  });
}

