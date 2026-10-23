// The wide flyout (the layout pass, owner 2026-10-22, board 4: https://claude.ai/artifact/4VVfYTQpLu1oyz8dz9xosZ): a table
// opened by itself from the menu, about 83% of the screen, over the page the reader was on. Its head carries "‹ the list it
// came from" (which reopens the menu there), the table's name with the game it is about, and ×; under it the table's own
// summary line; at its foot previous and next through the list (a swipe left or right does the same).
//
//   openWide({ title, subtitle, back, steps, body })   the flyout (ui/remote.js openSheet, wide); returns its handle
//   pagerFor(steps)          the foot: { items: [{ id, label }], index, where, onStep(id) } -> "‹ prev · 2 of 14 · next ›"
//   liftBand(node)           a band shown alone: its own head goes (the flyout's head says it), its summary and tools rise
//                            to the flyout's summary row, it is always unfolded, and its id goes (the page may hold the same)
//   flyoutContent({ summary, tools, body })   the flyout's body: the summary row, then the table

import { el, text } from "./dom.js";
import { icon } from "./icons.js";
import { openSheet } from "./remote.js";

const SWIPE_PX = 70;

/** The foot's previous and next through the list the flyout came from. */
export function pagerFor(steps) {
  const items = Array.isArray(steps?.items) ? steps.items.filter((item) => item && typeof item.id === "string") : [];
  const index = Number.isInteger(steps?.index) ? steps.index : items.findIndex((item) => item.id === steps?.id);
  if (items.length < 2 || index < 0 || index >= items.length) return null;
  const prev = items[index - 1] || null;
  const next = items[index + 1] || null;
  const go = (item) => () => {
    if (item && typeof steps.onStep === "function") steps.onStep(item.id);
  };
  return el(
    "nav",
    { class: "flyout-pager", "aria-label": "Previous and next" },
    el("button", { type: "button", class: "btn flyout-pager__prev", disabled: prev ? null : true, onclick: go(prev), "aria-label": prev ? `Previous: ${text(prev.label)}` : "No previous table" }, el("span", { "aria-hidden": "true" }, "‹ "), prev ? text(prev.label) : "Previous"),
    el("span", { class: "flyout-pager__count" }, `${index + 1} of ${items.length}${steps.where ? ` in ${text(steps.where)}` : ""}`),
    el("button", { type: "button", class: "btn flyout-pager__next", disabled: next ? null : true, onclick: go(next), "aria-label": next ? `Next: ${text(next.label)}` : "No next table" }, next ? text(next.label) : "Next", el("span", { "aria-hidden": "true" }, " ›")),
  );
}

/** A band on its own in the flyout: the head goes, the summary and tools rise, always unfolded, no id. */
export function liftBand(node) {
  if (!node || typeof node !== "object" || !node.classList || !node.classList.contains("band")) return { summary: null, tools: null, node };
  const head = [...(node.children || [])].find((child) => child.classList?.contains("band__head")) || null; // its own head, never a nested band's
  const summary = head ? head.querySelector(".band__summary") : null;
  const tools = head ? head.querySelector(".band__tools") : null;
  const words = summary ? String(summary.textContent || "").trim() : "";
  if (tools) tools.remove();
  node.removeAttribute("id");
  node.removeAttribute("aria-labelledby");
  node.setAttribute("data-collapsed", "false");
  node.classList.add("band--lifted");
  return { summary: words || null, tools: tools || null, node };
}

/** The flyout's body: the summary row (the band's own line, its tools beside it), then the table. */
export function flyoutContent({ summary = null, tools = null, body = null } = {}) {
  return el("div", { class: "flyout" }, summary || tools ? el("div", { class: "flyout__summary" }, summary ? el("p", {}, text(summary)) : null, tools) : null, body);
}

/** The "‹ the list" button at the head's left: closes the flyout and reopens the menu on that list. */
function backButton(back, close) {
  if (!back || typeof back.onClick !== "function") return null;
  return el(
    "button",
    {
      type: "button",
      class: "btn flyout-back",
      onclick: () => {
        close();
        back.onClick();
      },
    },
    icon("back"),
    el("span", {}, text(back.label || "Menu")),
  );
}

/** A swipe left steps to the next table, a swipe right to the previous one; on the first table a swipe right closes the
 *  flyout, the way every sheet closes. Rows that scroll sideways keep their own swipes (as ui/dom.js swipeToClose does). */
function swipeSteps(layer, holder, close) {
  const aside = layer?.querySelector?.(".side-sheet");
  if (!aside || typeof aside.addEventListener !== "function") return;
  let start = null;
  const sideways = (target) => {
    for (let n = target; n && n !== aside; n = n.parentElement) {
      if (n.matches?.("input, select, textarea, .ticker, .remote, .chips-row")) return true;
      if (n.scrollWidth > n.clientWidth + 2 && typeof getComputedStyle === "function" && /(auto|scroll)/.test(getComputedStyle(n).overflowX)) return true;
    }
    return false;
  };
  aside.addEventListener("pointerdown", (event) => {
    start = event.pointerType === "mouse" || sideways(event.target) ? null : { x: event.clientX, y: event.clientY, at: Date.now() };
  });
  aside.addEventListener("pointercancel", () => {
    start = null;
  });
  aside.addEventListener("pointerup", (event) => {
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = Math.abs(event.clientY - start.y);
    const quick = Date.now() - start.at <= 700;
    start = null;
    if (Math.abs(dx) < SWIPE_PX || dy > 50 || !quick) return;
    const steps = holder.current || {};
    const items = Array.isArray(steps.items) ? steps.items : [];
    const index = Number.isInteger(steps.index) ? steps.index : -1;
    const to = items[index + (dx < 0 ? 1 : -1)];
    if (to && typeof steps.onStep === "function") steps.onStep(to.id);
    else if (dx > 0) close();
  });
}

/**
 * openWide({ title, subtitle, back: { label, onClick }, steps: { items, index, where, onStep }, body, onClose })
 * The flyout, with its head, summary row and foot. The handle is openSheet's, plus setSteps(steps) to move the foot along.
 */
export function openWide({ title, subtitle = null, back = null, steps = null, body = null, onClose } = {}) {
  let handle = null;
  const holder = { current: steps };
  const lead = backButton(back, () => handle?.close());
  handle = openSheet({ title, body, onClose, wide: true, lead, subtitle, foot: pagerFor(steps), swipeClose: false });
  handle.setSteps = (next) => {
    holder.current = next;
    handle.setFoot(pagerFor(next));
  };
  swipeSteps(handle.layer, holder, () => handle.close());
  return handle;
}
