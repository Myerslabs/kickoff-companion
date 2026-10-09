// Penalties in the play log (Phase 17 #21, owner 2026-10-07: "when a penalty is thrown, link the rule"). The
// server reads the fouls out of each play's text (app/live/penalties.py) and sends them as play.penalties; each
// becomes a small flag button after the text. A tap opens a side panel in plain words: what the foul is, what
// it costs each side, and the rule number with a link into the NCAA rules book at that page. The book's
// explanations load once from /api/rules/penalties.
//
//   penaltyFlags(play)                 -> <span class="play__flags"> or null (no known foul on the play)
//   openPenaltyPanel(foul)             the side panel for one {key, name, yards, declined, offsetting}
//   loadPenaltyBook()                  -> Promise of {source, byKey}; one request a page load
//   penaltyBody(entry, foul, source)   the panel's content (exported for the tests)

import { el, isNum, text } from "./dom.js";
import { openSheet } from "./remote.js";
import { fetchJson } from "../views/common.js";

const PDF_NOTE = "The rules book is the NCAA's PDF (about 11 MB). Most browsers open it at the page; some tablets download it instead.";
let book = null;

/** The penalty book, fetched once. A failure is remembered as null so the next tap tries again. */
export function loadPenaltyBook() {
  if (!book) {
    book = fetchJson("/api/rules/penalties")
      .then((envelope) => {
        const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
        const list = Array.isArray(data.penalties) ? data.penalties.filter((p) => p && typeof p === "object" && typeof p.key === "string") : [];
        const source = data.source && typeof data.source === "object" ? data.source : null;
        return { source, byKey: new Map(list.map((p) => [p.key, p])) };
      })
      .catch((error) => {
        book = null;
        throw error;
      });
  }
  return book;
}

function fouls(play) {
  return (Array.isArray(play?.penalties) ? play.penalties : []).filter((f) => f && typeof f === "object" && typeof f.key === "string" && typeof f.name === "string");
}

/** "Holding, declined" / "False start, 5 yards" / "Offside, offsetting": what this flag did on this play. */
export function flagText(foul) {
  const extra = foul.declined ? "declined" : foul.offsetting ? "offsetting" : isNum(foul.yards) ? `${foul.yards} yards` : null;
  return extra ? `${foul.name}, ${extra}` : foul.name;
}

export function penaltyFlags(play) {
  const list = fouls(play);
  if (!list.length) return null;
  return el(
    "span",
    { class: "play__flags" },
    list.map((foul) =>
      el(
        "button",
        { type: "button", class: "flag-chip", title: "What this penalty means", "aria-label": `Penalty: ${flagText(foul)}. What it means`, onclick: (event) => { event.stopPropagation(); openPenaltyPanel(foul); } },
        el("span", { class: "flag-chip__mark", "aria-hidden": "true" }),
        flagText(foul),
      ),
    ),
  );
}

function ruleLink(call, source) {
  const rule = typeof call.rule === "string" && call.rule ? call.rule : null;
  if (!rule) return "–";
  const url = typeof source?.url === "string" && /^https:\/\//.test(source.url) ? source.url : null;
  if (!url) return `Rule ${rule}`;
  const page = isNum(call.page) && call.page > 0 ? Math.round(call.page) : null;
  return el("a", { href: page ? `${url}#page=${page}` : url, target: "_blank", rel: "noopener", class: "flag-rule" }, `Rule ${rule}`, page ? el("small", {}, ` page ${page}`) : null);
}

export function penaltyBody(entry, foul, source) {
  const calls = (Array.isArray(entry?.calls) ? entry.calls : []).filter((c) => c && typeof c === "object");
  const onPlay = flagText(foul);
  return el(
    "div",
    { class: "flag-panel" },
    el("p", { class: "flag-panel__play" }, el("span", { class: "flag-chip__mark", "aria-hidden": "true" }), `On this play: ${onPlay}.`),
    typeof entry?.what === "string" && entry.what ? el("p", { class: "flag-panel__what" }, entry.what) : el("p", { class: "note" }, "No plain-words entry for this foul yet."),
    calls.length
      ? el(
          "table",
          { class: "stat-table stat-table--compact flag-panel__calls" },
          el("caption", { class: "sr-only" }, `${text(foul.name)}: the penalty and the rule`),
          el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Fouled by"), el("th", { scope: "col" }, "Penalty"), el("th", { scope: "col" }, "Rulebook"))),
          el("tbody", {}, calls.map((c) => el("tr", {}, el("td", {}, text(c.who)), el("td", {}, text(c.result)), el("td", {}, ruleLink(c, source))))),
        )
      : null,
    el("p", { class: "note" }, `From the ${text(source?.title || "NCAA rules book")}. ${PDF_NOTE}`),
  );
}

export function openPenaltyPanel(foul) {
  const handle = openSheet({ title: text(foul?.name), className: "flag-sheet", body: () => el("p", { class: "note" }, "Loading the rule…") });
  loadPenaltyBook()
    .then(({ source, byKey }) => handle.update(() => penaltyBody(byKey.get(foul.key), foul, source)))
    .catch((error) => handle.update(() => el("p", { class: "note note--error" }, `The rule did not load: ${text(error?.message || "no answer")}. Close this and tap the flag again.`)));
  return handle;
}
