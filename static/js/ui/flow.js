// The flowing page (Phase 17 #7, #10, #28): bands pack into 1 to 4 columns by the page's width, across the top
// first, each band dropping into the earliest free spot, so a wide monitor shows more and nothing leaves a hole.
//
//   flow(page, { wide = [], full = [] })  turns `page` (a .page element) into a flowing page and keeps it laid out
//       as its width or any band's height changes. Children whose id is in `full`, or that carry .flow-full, span
//       every column (the cover, the back row); ids in `wide`, or .flow-wide, span two columns once there are two
//       or more (a big two-team table is cramped in one tablet column). Returns { relayout, stop }.
//   columnsFor(width)  1 under 700 px, 2 under 1100, 3 under 1600, else 4 (the owner's cap, 2026-10-07).
//   mountFlow(ui, container, page, { wide, full, chips = true })  (final pass) the one way a view mounts a flowing
//       page: stops the layout kept in `ui` from the last draw, pins the section chips above the page (chips: false
//       for a page with one band), replaces the container's children and starts the flow. `ui` keeps { flow, chips }.
//   stopFlow(ui)  stops both; a view calls it from unmount.
//
// How it packs: the page is a CSS grid of 4 px rows. Each band spans as many rows as its height needs, and the
// grid's own placement puts each next band in the first spot that fits, left to right; with one column the page
// is a plain stack. A ResizeObserver re-measures a band whose height changes (a fold, data arriving).

import { sectionChips } from "./states.js";

const ROW = 4;
const BREAKS = [[1600, 4], [1100, 3], [700, 2]];

export function columnsFor(width) {
  const w = Number.isFinite(width) ? width : 0;
  for (const [min, cols] of BREAKS) if (w >= min) return cols;
  return 1;
}

/** The page's --gap in px (12 by default): the space each band keeps under it. */
function gapOf(page) {
  const value = typeof getComputedStyle === "function" ? parseFloat(getComputedStyle(page).getPropertyValue("--gap")) : NaN;
  return Number.isFinite(value) && value > 0 ? value : 12;
}

export function flow(page, { wide = [], full = [] } = {}) {
  if (!page || typeof page.appendChild !== "function") return { relayout() {}, stop() {} };
  const wideIds = new Set(wide);
  const fullIds = new Set(full);
  page.classList.add("flow");
  let cols = 0;
  let gap = 12;

  function place(child) {
    if (!child || !child.style || !child.classList) return; // an element, not text
    const isFull = fullIds.has(child.id) || child.classList.contains("flow-full");
    const isWide = !isFull && (wideIds.has(child.id) || child.classList.contains("flow-wide"));
    child.style.gridColumn = isFull ? "1 / -1" : isWide && cols >= 2 ? "span 2" : "";
    if (cols <= 1) {
      child.style.gridRowEnd = "";
      return;
    }
    const height = child.getBoundingClientRect().height;
    child.style.gridRowEnd = `span ${Math.max(1, Math.ceil((height + gap) / ROW))}`;
  }

  function relayout() {
    const width = page.getBoundingClientRect().width;
    cols = columnsFor(width);
    gap = gapOf(page);
    page.style.setProperty("--flow-cols", String(cols));
    page.dataset.cols = String(cols);
    for (const child of page.children) place(child);
  }

  const heights = typeof ResizeObserver === "function" ? new ResizeObserver((entries) => {
    for (const entry of entries) if (entry.target.parentNode === page) place(entry.target);
  }) : null;
  const widths = typeof ResizeObserver === "function" ? new ResizeObserver(() => relayout()) : null;
  const children = typeof MutationObserver === "function" ? new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) if (node.nodeType === 1) { heights?.observe(node); place(node); }
      for (const node of record.removedNodes) if (node.nodeType === 1) heights?.unobserve(node);
    }
  }) : null;

  // the window's own resize too: a ResizeObserver only reports while the page is being drawn
  const onResize = () => relayout();
  for (const child of page.children) heights?.observe(child);
  widths?.observe(page);
  children?.observe(page, { childList: true });
  globalThis.addEventListener?.("resize", onResize);
  relayout();
  return {
    relayout,
    stop() {
      heights?.disconnect();
      widths?.disconnect();
      children?.disconnect();
      globalThis.removeEventListener?.("resize", onResize);
    },
  };
}

export function stopFlow(ui) {
  if (!ui || typeof ui !== "object") return;
  ui.flow?.stop();
  ui.chips?.stop();
  ui.flow = null;
  ui.chips = null;
}

export function mountFlow(ui, container, page, { wide = [], full = [], chips = true } = {}) {
  const keep = ui && typeof ui === "object" ? ui : {};
  stopFlow(keep);
  if (chips) {
    keep.chips = sectionChips(page);
    keep.chips.refresh();
    container.replaceChildren(keep.chips, page);
  } else {
    container.replaceChildren(page);
  }
  keep.flow = flow(page, { wide, full });
  return keep;
}
