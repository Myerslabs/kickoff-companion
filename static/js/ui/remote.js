// The remote control (owner direction, 2026-09-21): a pinned row of buttons under the live
// sheet. Each opens a side sheet with one component. The base screen never changes underneath,
// so the strip, the radio, and the glance stats stay put.

import { isTopLayer } from "./player-card.js";
import { el, layerZ, replaceWith, restoreScroll, retireLayer, scrollState, syncPageLock, text } from "./dom.js";

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

/** Close every open side sheet (the router does it on a route change; so can a view). */
export function closeAllSheets() {
  for (const close of [...open]) close();
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
 * Every sheet closes on a route change (the "kickoff:route" event) unless `persist` is true. The page
 * underneath does not scroll while a sheet is open. The sheet slides in and out (none when motion is reduced).
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
  const onKey = (event) => {
    if (event.key === "Escape" && isTopLayer(layer)) {
      event.stopPropagation();
      close();
    }
  };
  const onRoute = () => {
    if (!persist) close();
  };
  const closeButton = el("button", { class: "btn btn--quiet icon-btn side-sheet__close", type: "button", "aria-label": `Close ${text(title)}`, onclick: () => close() }, "×");
  function close() {
    if (closed) return;
    closed = true;
    open.delete(close);
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("kickoff:route", onRoute);
    if (inline) layer.remove();
    else retireLayer(layer, "sheet-layer");
    if (typeof onClose === "function") onClose();
    if (opener && typeof opener.focus === "function" && document.contains(opener)) opener.focus();
  }
  layer.append(
    el("div", { class: "sheet-layer__scrim", onclick: () => close() }),
    el("aside", { class: `side-sheet${className ? ` ${className}` : ""}` }, el("div", { class: "side-sheet__head" }, titleEl, toolsEl, closeButton), bodyEl),
  );
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
  mount.append(layer);
  if (!inline) {
    open.add(close);
    document.addEventListener("keydown", onKey);
    document.addEventListener("kickoff:route", onRoute);
    syncPageLock();
    closeButton.focus();
  }
  return { close, layer, update, setTitle, setBody, setTools };
}
