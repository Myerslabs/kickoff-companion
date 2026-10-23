// The one To do note (item 6, step C, owner 2026-10-11; Design rules, owner 2026-10-21: "Reminders are one format only: a
// single note ... that lists ALL open issues and how to correct each, with one close button. Never a side sheet, never a
// bottom banner, never on the board"). What once opened by itself as a sheet over whatever the reader was doing ("Not
// loaded yet" after a server start, a guest's welcome, a new build on the server) is one item of one note. The layout pass
// (owner 2026-10-22: "dont show that unless its in its own flyout"): the note no longer sits above the page. It waits in
// the shell's .page-notes slot, which never shows, and the To do flyout (ui/todo.js), opened from the menu, carries it
// while open; the Menu button counts its items (the "kickoff:notes" event). Nothing opens by itself. Each item is listed
// on the routes it names (the board never); an item is seen, and onShow runs, only when the flyout shows it; the one close
// (the flyout's Clear the list) dismisses every item listed.
//
//   addNote({ id, title, body, when, onShow, onDismiss, leaveWithPage })
//       place an item (one with the same id is replaced). when(routeId) says where it is listed (the board never); onShow
//       runs the first time the flyout shows it; onDismiss when the reader clears the list; leaveWithPage takes it away at
//       the next page change once it has been seen. Returns the item's element, or null when the page has no slot for it.
//   removeNote(id)        take an item away (onDismiss does not run)
//   noteShowing(id)       true while the item is listed (it belongs to the page on screen)
//   noteCount()           how many items are listed
//   takeNotes() / parkNotes()   the flyout takes the note (its items are seen) and gives it back to the slot
//   dismissAll()          the one close: every item listed goes, each telling its owner
//   routeIdOf(hash)       "#program=123" -> "program"; no hash -> "program" (the app's home)

import { el, text } from "./dom.js";

const TITLE = "To do";
const notes = new Map(); // id -> { node, when, onShow, onDismiss, leaveWithPage, shownOn }
let host = null; // the one aside, while any item exists
let listening = false;
let viewing = false; // the To do flyout holds the note: only then is an item on screen (seen)

export function routeIdOf(hash) {
  const match = /^#?([a-z][\w-]*)/i.exec(String(hash ?? ""));
  return match ? match[1].toLowerCase() : "program";
}

function currentRoute() {
  try {
    return routeIdOf(typeof window !== "undefined" ? window.location?.hash : "");
  } catch {
    return "program";
  }
}

function slot() {
  try {
    return typeof document !== "undefined" ? document.querySelector(".page-notes") : null;
  } catch {
    return null;
  }
}

/** The one close: every item listed goes, each telling its owner. */
function dismissShown() {
  for (const [id, note] of [...notes]) {
    if (note.node.hasAttribute("hidden")) continue;
    removeNote(id);
    if (typeof note.onDismiss === "function") {
      try {
        note.onDismiss();
      } catch (error) {
        console.error(`The note ${id} did not take its dismissal.`, error);
      }
    }
  }
}

/** The aside that holds the items: made with the first item, gone with the last. */
function ensureHost(box) {
  if (host && host.isConnected) return host;
  host = el(
    "aside",
    { class: "page-note", role: "note", "aria-label": TITLE, hidden: true },
    el("div", { class: "page-note__head" }, el("h2", { class: "page-note__title" }, TITLE), el("button", { class: "btn btn--quiet icon-btn page-note__close", type: "button", "aria-label": `Dismiss ${TITLE}`, onclick: dismissShown }, "×")),
    el("ol", { class: "page-note__list" }),
  );
  box.append(host);
  return host;
}

/** The slot and the note show only while one item does (an empty slot would leave a gap above every page). */
function syncSlot() {
  const box = slot();
  if (!box) return;
  const any = [...notes.values()].some((note) => !note.node.hasAttribute("hidden") && note.node.isConnected);
  if (host) {
    if (any) host.removeAttribute("hidden");
    else host.setAttribute("hidden", "");
    const count = [...notes.values()].filter((note) => !note.node.hasAttribute("hidden")).length;
    const title = host.querySelector(".page-note__title");
    if (title) title.textContent = count > 1 ? `${TITLE} (${count})` : TITLE;
  }
  if (any) box.removeAttribute("hidden");
  else box.setAttribute("hidden", "");
  announce();
}

/** The Menu's count and the open flyout follow the list (ui/shell.js, ui/todo.js). */
function announce() {
  if (typeof document === "undefined" || typeof document.dispatchEvent !== "function" || typeof CustomEvent !== "function") return;
  try {
    document.dispatchEvent(new CustomEvent("kickoff:notes", { detail: { count: noteCount() } }));
  } catch (error) {
    console.error("The To do count could not be sent.", error);
  }
}

function markShown(id, note, route) {
  if (note.shownOn !== null) return;
  note.shownOn = route;
  if (typeof note.onShow === "function") {
    try {
      note.onShow();
    } catch (error) {
      console.error(`The note ${id} did not take its showing.`, error);
    }
  }
}

function apply(id, note, route) {
  let on = false;
  try {
    on = route !== "board" && note.when(route) === true; // the big screen board never lists one; In Game may, since the note left the page (2026-10-22)
  } catch (error) {
    console.error("A note could not tell where it belongs; it stays hidden.", error);
  }
  if (!on) {
    note.node.setAttribute("hidden", "");
    return;
  }
  note.node.removeAttribute("hidden");
  if (viewing) markShown(id, note, route); // seen only in the flyout
}

function onRoute(event) {
  const route = typeof event?.detail?.id === "string" ? event.detail.id : currentRoute();
  for (const [id, note] of [...notes]) {
    if (note.leaveWithPage && note.shownOn !== null) {
      removeNote(id); // seen on the page the reader landed on: it goes with that page
      continue;
    }
    apply(id, note, route);
  }
  syncSlot();
}

function listen() {
  if (listening || typeof document === "undefined" || typeof document.addEventListener !== "function") return;
  listening = true;
  document.addEventListener("kickoff:route", onRoute);
}

export function addNote({ id, title, body, when = () => true, onShow, onDismiss, leaveWithPage = false } = {}) {
  const box = slot();
  if (!box || typeof id !== "string" || !id) return null;
  removeNote(id);
  let content = null;
  try {
    content = typeof body === "function" ? body() : body;
  } catch (error) {
    console.error(`The note ${id} could not be drawn.`, error);
    return null;
  }
  const label = text(title);
  const node = el(
    "li",
    { class: "page-note__item", dataset: { note: id }, "aria-label": label, hidden: true },
    el("b", { class: "page-note__item-title" }, label),
    el("div", { class: "page-note__body" }, content),
  );
  const note = { node, when: typeof when === "function" ? when : () => true, onShow, onDismiss, leaveWithPage: leaveWithPage === true, shownOn: null };
  notes.set(id, note);
  ensureHost(box).querySelector(".page-note__list").append(node);
  listen();
  apply(id, note, currentRoute());
  syncSlot();
  return node;
}

export function removeNote(id) {
  const note = notes.get(id);
  if (!note) return false;
  notes.delete(id);
  note.node.remove();
  if (!notes.size && host) {
    host.remove();
    host = null;
  }
  syncSlot();
  return true;
}

export function noteShowing(id) {
  const note = notes.get(id);
  return Boolean(note && note.node.isConnected && !note.node.hasAttribute("hidden") && host && !host.hasAttribute("hidden"));
}

export function noteCount() {
  return [...notes.values()].filter((note) => !note.node.hasAttribute("hidden")).length;
}

/** The To do flyout takes the note: every item listed is seen now (and any added while it is open). Null with none. */
export function takeNotes() {
  if (!host || !noteCount()) return null;
  viewing = true;
  const route = currentRoute();
  for (const [id, note] of [...notes]) if (!note.node.hasAttribute("hidden")) markShown(id, note, route);
  return host;
}

/** The flyout closed: the note goes back to its slot off the page, every item kept. */
export function parkNotes() {
  viewing = false;
  const box = slot();
  if (host && box && host.parentNode !== box) box.append(host);
  syncSlot();
}

export function dismissAll() {
  dismissShown();
}
