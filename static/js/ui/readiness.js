// What is not loaded yet (Phase 18.3, owner 2026-10-08: "a popup listing prompts not loaded or with missing info... no
// popup when all loaded"). The server lists the gaps in /api/readiness: the season load, roster costs, and this
// week's notes (injury report, depth charts, TV crew, coaches). Two faces of one list:
//
//   maybeShowReadiness()   a sheet once per server start on each device, only when something is missing
//   readinessBand()        the Settings card: the same list, or "Everything is loaded"
//
// The sheet remembers, per device, the server start it was shown for (localStorage; a browser without it just sees
// the sheet once per page load). Nothing here changes data; each item links to the page with its prompt.

import { el, text } from "./dom.js";
import { band } from "./states.js";
import { fetchJson } from "../views/common.js";
import { openSheet } from "./remote.js";

const SEEN_KEY = "kickoff.readiness.seen";

function list(value) {
  return (Array.isArray(value) ? value : []).filter((x) => x && typeof x === "object" && typeof x.title === "string");
}

function readSeen() {
  try {
    return window.localStorage.getItem(SEEN_KEY);
  } catch {
    return null;
  }
}

function writeSeen(value) {
  try {
    window.localStorage.setItem(SEEN_KEY, value);
  } catch {
    // private window or blocked storage: it is shown again next load, which is the safe direction
  }
}

/** The items as a list of links; `onOpen` runs when one is followed (the sheet closes itself). */
export function readinessList(items, onOpen) {
  const rows = list(items);
  if (!rows.length) return el("p", { class: "note" }, "Everything is loaded: the season, the roster costs and this week's notes.");
  return el(
    "ul",
    { class: "readiness" },
    rows.map((item) =>
      el(
        "li",
        { class: "readiness__item" },
        el("b", {}, text(item.title)),
        typeof item.detail === "string" ? el("p", { class: "readiness__detail" }, item.detail) : null,
        typeof item.href === "string" && item.href.startsWith("#")
          ? el("a", { class: "btn btn--quiet", href: item.href, onclick: () => { if (typeof onOpen === "function") onOpen(); } }, "Open the prompt")
          : null,
      ),
    ),
  );
}

export async function maybeShowReadiness() {
  let data = null;
  try {
    const envelope = await fetchJson("/api/readiness");
    data = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
  } catch {
    return null; // a courtesy: no popup is better than a popup about a failed check
  }
  if (!data || data.ready === true || !list(data.items).length) return null;
  const started = typeof data.serverStartedAt === "string" ? data.serverStartedAt : "";
  if (started && readSeen() === started) return null;
  if (document.body?.dataset?.role === "guest") return null; // a guest cannot load anything
  if (document.querySelector("[data-modal]")) return null; // never on top of something the viewer opened
  writeSeen(started || "shown");
  let handle = null;
  const done = el("button", { class: "btn btn--primary", type: "button", onclick: () => handle?.close?.() }, "Not now");
  handle = openSheet({ title: "Not loaded yet", body: () => el("div", {}, readinessList(data.items, () => handle?.close?.()), el("p", { class: "settings__actions" }, done)) });
  return handle;
}

/** The Settings card. Fills itself after the page is drawn; a failed check says so instead of staying empty. */
export function readinessBand() {
  const slot = el("div", {}, el("p", { class: "note" }, "Checking what is loaded…"));
  fetchJson("/api/readiness")
    .then((envelope) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      slot.replaceChildren(readinessList(data.items));
    })
    .catch((error) => slot.replaceChildren(el("p", { class: "note" }, `The check did not finish: ${text(error?.message || "no answer")}.`)));
  return band({ id: "settings-readiness", title: "Readiness", collapsible: false, summary: "", state: { status: "ready" }, body: () => slot });
}
