// The remote control (owner direction, 2026-09-21): a pinned row of buttons under the live
// sheet. Each opens a side sheet with one component. The base screen never changes underneath,
// so the strip, the radio, and the glance stats stay put.

import { isTopLayer } from "./player-card.js";
import { el, layerZ, replaceWith, restoreScroll, retireLayer, scrollState, sheetAnchor, swipeToClose, syncPageLock, text } from "./dom.js";
import { icon } from "./icons.js";
import { holdLayer, placeLayers } from "./layers.js";

/**
 * remoteBar({ items: [{ id, label, hint }], onOpen(id) })
 * returns the element with setActive(id) and setHint(id, hint). The live sheet builds it once
 * and only updates the hints, so a bar scrolled sideways on a narrow screen stays where it is.
 */
export function remoteBar({ items = [], onOpen } = {}) {
  const buttons = new Map();
  const bar = el(
    "nav",
    { class: "remote", "aria-label": "Open a panel" },
    items.map((item) => {
      const button = el(
        "button",
        { class: "remote__btn", type: "button", "aria-pressed": "false", dataset: { id: item.id }, onclick: () => onOpen && onOpen(item.id) },
        text(item.label),
        el("small", {}, item.hint ? text(item.hint) : " "),
      );
      buttons.set(item.id, button);
      return button;
    }),
  );
  bar.setActive = (id) => {
    for (const [key, button] of buttons) button.setAttribute("aria-pressed", key === id ? "true" : "false");
  };
  bar.setHint = (id, hint) => {
    const small = buttons.get(id)?.querySelector("small");
    const next = hint ? text(hint) : " ";
    if (small && small.textContent !== next) small.textContent = next; // unchanged hints are left alone
  };
  return bar;
}

const open = new Set();

/** Close every open side sheet (the router does it on a route change; so can a view). Each takes its own history entry
 *  back out, unless `reason` says the history is already moving ("route", "history"). */
export function closeAllSheets(reason) {
  for (const close of [...open].reverse()) close(reason);
}

/**
 * openSheet({ title, body, onClose, mount, inline, tools, className, persist })
 * `body` is an element (or an array of them) or a function returning one. Escape, the scrim, or
 * the close button closes it. `mount` (default document.body) lets the styleguide show it inline.
 * Phase 16 (stream F) frozen API. Returns { close, layer, update(body), setTitle(title), setBody(body), setTools(node) }:
 *   update swaps in a new body where the reader is, keeping the scroll position, so an open sheet can
 *     follow the game; if building the new body throws, the old one stays and the error goes to the caller.
 *   setBody swaps in a different panel from the top (another remote button, another list) without
 *     closing and reopening the layer; setTitle renames it in place; setTools replaces the head tools
 *     (a 'Full page' link sits there, before the close button).
 * Sheets stack: a sheet opened from a sheet or the player card lies above it, and Escape closes the top one.
 * Every sheet closes on a route change (the "kickoff:route" event) unless `persist` is true. The sheet slides in and
 * out (none when motion is reduced).
 * Item 8 (owner 2026-10-10): no small ×; a › at the left of the head slides it away (and a swipe right still does). The
 * sheet is as wide as its content (up to 780 px; a phone's whole width) and as tall as its content, lying on the page
 * where the reader is: a long sheet is read by scrolling the page, never inside a box, and its head stays at the top
 * while it does. Closing it by hand or with Back gives the page back where it was.
 * Item 6 (owner 2026-10-11): from 700 px up the sheet starts under the top bar, so the Menu, Search and the tabs keep
 * working (placeLayers, components.css); a phone keeps the whole screen. A sheet takes one history entry (ui/layers.js):
 * Back closes it and stays on the page, and closing it by hand takes the entry back out. close(reason) is "self" (the
 * default), "route" or "history"; only "self" moves the history.
 */
export function openSheet({ title, body, onClose, mount = document.body, inline = false, tools, className, persist = false } = {}) {
  const content = typeof body === "function" ? body() : body;
  const layer = el("div", {
    class: `sheet-layer${inline ? " sheet-layer--inline" : ""}`,
    open: true,
    role: "dialog",
    "aria-modal": inline ? null : "true",
    "aria-label": text(title),
    "data-modal": inline ? null : true,
    style: inline ? null : { zIndex: layerZ() },
  });
  const bodyEl = el("div", { class: "side-sheet__body" }, content);
  const titleEl = el("h2", { class: "side-sheet__title" }, text(title));
  const toolsEl = el("div", { class: "side-sheet__tools" }, tools || null);
  const opener = inline ? null : document.activeElement; // Phase 15: focus goes back here on close
  let closed = false;
  let release = null; // the layer's history entry (ui/layers.js)
  // one Escape closes one layer: a hint card or the status card above takes it first (they mark it handled)
  const onKey = (event) => {
    if (event.key === "Escape" && !event.defaultPrevented && isTopLayer(layer)) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  };
  const onRoute = () => {
    if (!persist) close("route");
  };
  // item 8: the › slides the sheet away to the right, the way it came in; its words are for a screen reader and a hover
  const closeButton = el("button", { class: "btn btn--quiet icon-btn side-sheet__close", type: "button", "aria-label": `Close ${text(title)}`, title: "Slide away" }, icon("chevron-right"));
  closeButton.addEventListener("click", () => close());
  let anchor = null; // where the sheet lies on the page, and the page's scroll when it opened
  function close(reason) {
    if (closed) return;
    closed = true;
    open.delete(close);
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("kickoff:route", onRoute);
    if (inline) layer.remove();
    else retireLayer(layer, "sheet-layer");
    if (release) release(typeof reason === "string" ? reason : "self");
    release = null;
    if (typeof onClose === "function") onClose();
    // the page as the reader left it (a route change takes the reader somewhere else, so it keeps its own scroll)
    if (anchor && reason !== "route" && typeof window !== "undefined" && typeof window.scrollTo === "function") window.scrollTo(0, anchor.scrollY);
    if (opener && typeof opener.focus === "function" && document.contains(opener)) opener.focus({ preventScroll: true });
  }
  const aside = el("aside", { class: `side-sheet${className ? ` ${className}` : ""}` }, el("div", { class: "side-sheet__head" }, closeButton, titleEl, toolsEl), bodyEl);
  layer.append(el("div", { class: "sheet-layer__scrim", onclick: () => close() }), aside);
  if (!inline) swipeToClose(aside, () => close()); // Phase 16 wave 3 (2B): a swipe right closes it
  const update = (next) => {
    if (closed) return;
    const fresh = typeof next === "function" ? next() : next;
    const saved = scrollState(bodyEl);
    replaceWith(bodyEl, fresh);
    restoreScroll(bodyEl, saved);
  };
  const setBody = (next) => {
    if (closed) return;
    const fresh = typeof next === "function" ? next() : next;
    replaceWith(bodyEl, fresh);
    bodyEl.scrollTop = 0;
    // a different panel starts from its top: the page back to where the sheet starts, when the reader had scrolled past it
    if (anchor && typeof window !== "undefined" && typeof window.scrollTo === "function" && isFinite(window.scrollY) && window.scrollY > anchor.scrollY) window.scrollTo(0, anchor.scrollY);
  };
  const setTitle = (next) => {
    if (closed) return;
    titleEl.textContent = text(next);
    layer.setAttribute("aria-label", text(next));
    closeButton.setAttribute("aria-label", `Close ${text(next)}`);
  };
  const setTools = (node) => {
    if (closed) return;
    replaceWith(toolsEl, node || null);
  };
  if (!inline) {
    anchor = sheetAnchor(placeLayers()); // under the top bar from 700 px up, on the page where the reader is (item 8)
    aside.style.setProperty("--sheet-top", `${anchor.top}px`);
  }
  mount.append(layer);
  if (!inline) {
    open.add(close);
    document.addEventListener("keydown", onKey);
    document.addEventListener("kickoff:route", onRoute);
    release = holdLayer((why) => close(why), { history: !persist }); // a sheet that outlives page changes takes no entry
    syncPageLock();
    closeButton.focus({ preventScroll: true });
  }
  return { close, layer, update, setTitle, setBody, setTools };
}
