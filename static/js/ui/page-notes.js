// Notes at the top of a page (item 6, step C, owner 2026-10-11). What once opened by itself as a sheet over whatever the
// reader was doing ("Not loaded yet" after a server start, a guest's welcome) is a note above the page instead, in the
// shell's .page-notes slot between the top bar and the page: never over the Menu, never a layer, never on the board. A note
// shows on the routes it names, closes with its ×, and can leave with the page it was first shown on.
//
//   addNote({ id, title, body, when, onShow, onDismiss, leaveWithPage })
//       place a note (one with the same id is replaced). when(routeId) says where it shows (the board never); onShow runs
//       the first time it is on screen; onDismiss when the reader closes it; leaveWithPage takes it away at the next
//       page change once it has been seen. Returns the note, or null when the page has no slot for it.
//   removeNote(id)        take it away (onDismiss does not run)
//   noteShowing(id)       true while it is on screen
//   routeIdOf(hash)       "#program=123" -> "program"; no hash -> "program" (the app's home)

import { el, text } from "./dom.js";

const notes = new Map(); // id -> { node, when, onShow, leaveWithPage, shownOn }
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

/** The slot shows only while one of its notes does (an empty slot would leave a gap above every page). */
function syncSlot() {
  const box = slot();
  if (!box) return;
  const any = [...notes.values()].some((note) => !note.node.hasAttribute("hidden") && note.node.parentNode === box);
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
  const label = text(title);
  const close = el(
    "button",
    {
      class: "btn btn--quiet icon-btn page-note__close",
      type: "button",
      "aria-label": `Dismiss ${label}`,
      onclick: () => {
        removeNote(id);
        if (typeof onDismiss === "function") {
          try {
            onDismiss();
          } catch (error) {
            console.error(`The note ${id} did not take its dismissal.`, error);
          }
        }
      },
    },
    "×",
  );
  let content = null;
  try {
    content = typeof body === "function" ? body() : body;
  } catch (error) {
    console.error(`The note ${id} could not be drawn.`, error);
    return null;
  }
  const node = el(
    "aside",
    { class: "page-note", role: "note", "aria-label": label, dataset: { note: id }, hidden: true },
    el("div", { class: "page-note__head" }, el("h2", { class: "page-note__title" }, label), close),
    el("div", { class: "page-note__body" }, content),
  );
  const note = { node, when: typeof when === "function" ? when : () => true, onShow, leaveWithPage: leaveWithPage === true, shownOn: null };
  notes.set(id, note);
  box.append(node);
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
  syncSlot();
  return true;
}

export function noteShowing(id) {
  const note = notes.get(id);
  return Boolean(note && note.node.isConnected && !note.node.hasAttribute("hidden"));
}
