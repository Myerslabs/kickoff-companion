// The one note at the top of a page (item 6, step C, owner 2026-10-11; Design rules, owner 2026-10-21: "Reminders are one
// format only: a single note at the top of the page that lists ALL open issues and how to correct each, with one close
// button. Never a side sheet, never a bottom banner, never on the board"). What once opened by itself as a sheet over
// whatever the reader was doing ("Not loaded yet" after a server start, a guest's welcome, a new build on the server) is
// one item of one note above the page, in the shell's .page-notes slot between the top bar and the page: never over the
// Menu, never a layer, never on the board, never on In Game (one screen since wave F5). Each item shows on the routes it
// names; the note shows while any item does; its one close button dismisses every item on screen.
//
//   addNote({ id, title, body, when, onShow, onDismiss, leaveWithPage })
//       place an item (one with the same id is replaced). when(routeId) says where it shows (the board never); onShow runs
//       the first time it is on screen; onDismiss when the reader closes the note; leaveWithPage takes it away at the next
//       page change once it has been seen. Returns the item's element, or null when the page has no slot for it.
//   removeNote(id)        take an item away (onDismiss does not run)
//   noteShowing(id)       true while the item is on screen
//   routeIdOf(hash)       "#program=123" -> "program"; no hash -> "program" (the app's home)

import { el, text } from "./dom.js";

const TITLE = "To do";
const notes = new Map(); // id -> { node, when, onShow, onDismiss, leaveWithPage, shownOn }
let host = null; // the one aside, while any item exists
let listening = false;

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

/** The one close button: every item on screen goes, each telling its owner. */
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
}

function apply(id, note, route) {
  let on = false;
  try {
    on = route !== "board" && route !== "live" && note.when(route) === true; // the big screen board never carries a note, nor In Game since wave F5 (one screen)
  } catch (error) {
    console.error("A note could not tell where it belongs; it stays hidden.", error);
  }
  if (!on) {
    note.node.setAttribute("hidden", "");
    return;
  }
  note.node.removeAttribute("hidden");
  if (note.shownOn === null) {
    note.shownOn = route;
    if (typeof note.onShow === "function") {
      try {
        note.onShow();
      } catch (error) {
        console.error(`The note ${id} did not take its showing.`, error);
      }
    }
  }
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
