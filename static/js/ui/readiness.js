// What is not loaded yet (Phase 18.3, owner 2026-10-08: "a popup listing prompts not loaded or with missing info... no
// popup when all loaded"). The server lists the gaps in /api/readiness: the season load, roster costs, and this
// week's notes (injury report, depth charts, TV crew, coaches). Three faces of one list:
//
//   startReadiness(page)   item 6, step C (owner 2026-10-11): never a sheet that opens by itself. Once a day on each device
//                          (the Prompts phase, owner 2026-10-13: every reminder in the one format, "the notes check is
//                          daily"), a note at the top of every page with its close button, and a dot on the top bar's
//                          status pill, whose card lists the same items; only when something is missing, never for a
//                          guest, never on the board. The card keeps the list (without the dot) for as long as something
//                          is missing. Every item leads to the Prompts page.
//   readinessBand()        the Settings card: the same list, or "Everything is loaded"
//   readinessList(items)   the list itself, each item a link to the page with its prompt
//
// The device remembers the day it was shown (localStorage "kickoff.readiness.seen"; a browser without it sees the note
// once per page load): marked when the note is first on screen or the card is opened from the dot.
// Nothing here changes data.

import { el, text } from "./dom.js";
import { band } from "./states.js";
import { fetchJson } from "../views/common.js";
import { addNote, removeNote } from "./page-notes.js";

const SEEN_KEY = "kickoff.readiness.seen";
const NOTE_ID = "readiness";
const TITLE = "Not loaded yet";

function list(value) {
  return (Array.isArray(value) ? value : []).filter((x) => x && typeof x === "object" && typeof x.title === "string");
}

/** Today on this device, YYYY-MM-DD: the note shows once a day. */
export function todayKey(now = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
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

/** The items as a list of links; `onOpen` runs when one is followed. */
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
          ? el("a", { class: "btn btn--quiet", href: item.href, onclick: () => { if (typeof onOpen === "function") onOpen(); } }, "Open Load data")
          : null,
      ),
    ),
  );
}

async function fetchReadiness() {
  try {
    const envelope = await fetchJson("/api/readiness");
    return envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
  } catch {
    return null; // a courtesy: no note is better than a note about a failed check
  }
}

/**
 * The note and the dot (app.js runs this once, after the first page has drawn and the device knows whether it is a guest).
 * `page` is the shell ({ setNotice }); without it only the note shows. Returns { items, fresh } or null when nothing is
 * missing, the check failed, or the device is a guest.
 */
export async function startReadiness(page) {
  const notify = (notice) => {
    try {
      if (page && typeof page.setNotice === "function") page.setNotice(notice);
    } catch (error) {
      console.error("The status pill could not take the Not loaded yet list.", error);
    }
  };
  const data = await fetchReadiness();
  if (!data || data.ready === true || !list(data.items).length) return null;
  if (document.body?.dataset?.role === "guest") return null; // a guest cannot load anything
  const today = todayKey();
  const fresh = readSeen() !== today;
  let items = list(data.items);
  let dot = fresh;
  const seen = () => writeSeen(today);
  const gone = () => {
    removeNote(NOTE_ID);
    dot = false;
    draw();
  };
  // the card asks again when it opens, so an item loaded since the start leaves the list
  const recheck = async () => {
    const next = await fetchReadiness();
    if (!next) return;
    items = list(next.items);
    if (next.ready === true || !items.length) {
      removeNote(NOTE_ID);
      notify(null);
      return;
    }
    draw();
  };
  function draw() {
    notify({
      dot,
      title: TITLE,
      body: () => readinessList(items, gone),
      onOpen: () => {
        if (dot) {
          seen();
          dot = false;
          draw();
        }
        recheck();
      },
    });
  }
  draw();
  if (fresh) {
    addNote({
      id: NOTE_ID,
      title: TITLE,
      body: () => readinessList(items, gone),
      when: () => true, // every page (the board never: page-notes.js keeps every note off it)
      onShow: seen,
      onDismiss: () => {
        dot = false;
        draw();
      },
    });
  }
  return { items, fresh };
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
