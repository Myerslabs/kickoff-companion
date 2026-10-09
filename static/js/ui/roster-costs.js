// Rumored roster costs (Phase 17 Part 3b, owner 2026-10-07: "Is there a place we could put roster costs?"; "it's ok
// if they cant be found, or are guessed at the press articles"; "keep it as 'rumored'"). The roster-costs load on
// the Preseason page saves a rumored total for every team and, for the primary teams, position groups and players.
// This band shows one team's: the total with what it covers and its date, then positions, then players, then the
// sources. Every figure is labelled rumored; nothing here is official.
//
//   costsBand(costs, { id, team })  -> the band; an empty state says where the load is run

import { DASH, el, fmtDate, fmtUsd, isNum, str, text } from "./dom.js";
import { band } from "./states.js";
import { statTable } from "./stat-table.js";

function rows(value) {
  return (Array.isArray(value) ? value : []).filter((r) => r && typeof r === "object");
}

export function costsBand(costs, { id = "roster-costs", team } = {}) {
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
    state: has ? { status: "ready" } : { status: "empty", message: c ? `No figure was reported for ${text(team || c.school)} when the load ran${str(c.savedAt) ? ` (${fmtDate(c.savedAt, "short")})` : ""}.` : "Not loaded yet." , action: { label: "Open the prompt", href: "#preseason" } },
    body: () =>
      el(
        "div",
        { class: "costs" },
        el("p", { class: "costs__total" }, el("span", { class: "costs__label" }, "Rumored total "), el("b", {}, isNum(c.totalUsd) ? fmtUsd(c.totalUsd) : DASH), when ? el("small", {}, ` as of ${when}`) : null),
        str(c.note) ? el("p", { class: "note" }, c.note) : null,
        positions.length
          ? statTable({ compact: true, sortable: false, caption: "Rumored spending by position group", columns: [{ key: "group", label: "Position group", kind: "text" }, { key: "amountUsd", label: "Amount", render: (r) => (isNum(r.amountUsd) ? fmtUsd(r.amountUsd) : DASH) }, { key: "note", label: "Note", kind: "text" }], rows: positions })
          : null,
        players.length
          ? statTable({ compact: true, caption: "Rumored player values", sort: { key: "amountUsd", dir: "descending" }, columns: [{ key: "name", label: "Player", kind: "text" }, { key: "position", label: "Pos", kind: "text" }, { key: "amountUsd", label: "Amount", render: (r) => (isNum(r.amountUsd) ? fmtUsd(r.amountUsd) : DASH) }, { key: "note", label: "Note", kind: "text", sortable: false }], rows: players })
          : null,
        el("p", { class: "note" }, "Figures are rumored or estimated from press reports and NIL valuation sites; schools don't publish them.", sources.length ? [" Sources: ", sources.map((s, i) => [i ? ", " : null, str(s.url) && /^https?:\/\//.test(s.url) ? el("a", { href: s.url, target: "_blank", rel: "noopener" }, str(s.label) || s.url) : text(s.label)])] : null),
      ),
  });
}

