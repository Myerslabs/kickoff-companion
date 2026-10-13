// The flowing page (Phase 17 #7, #10, #28): bands pack into 1 or 2 columns by the page's width, each band placed below
// everything listed before it (the order rule, owner 2026-10-13), in the column with the most room, so nothing leaves
// a hole and the reader meets the bands in the list's order. The tablet lock (owner 2026-10-13,
// "I don't want it to go to three or four columns"): a browser wider than the iPad draws the iPad's two columns, wider;
// only the game-day board (views/board.js) has a layout of its own for a big screen.
//
//   flow(page, { wide = [], full = [] })  turns `page` (a .page element) into a flowing page and keeps it laid out
//       as its width or any band's height changes. Children whose id is in `full`, or that carry .flow-full, span
//       every column (the cover, the back row); ids in `wide`, or .flow-wide, span two columns once there are two
//       or more (a big two-team table is cramped in one tablet column). Returns { relayout, stop }.
//   columnsFor(width)  1 under 700 px, else 2 (the tablet lock, 2026-10-13; 3 from 1100 and 4 from 1600 until then).
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
const BREAKS = [[700, 2]];

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

  // The order rule (owner 2026-10-13, "making sure that it's in the correct order when you're scrolling down the page"):
  // every band is placed below everything listed before it. Each band goes into the column whose bottom is highest up
  // (a wide band into the lowest pair of columns; a full one under everything), so the reader meets them in the list's
  // order and nothing leaves a hole. The browser's own "dense" packing let a short band jump up beside a tall one.
  function place(child, bottoms) {
    if (!child || !child.style || !child.classList) return; // an element, not text
    const isFull = fullIds.has(child.id) || child.classList.contains("flow-full");
    const isWide = !isFull && (wideIds.has(child.id) || child.classList.contains("flow-wide"));
    if (cols <= 1) {
      child.style.gridColumn = isFull ? "1 / -1" : "";
      child.style.gridRowStart = "";
      child.style.gridRowEnd = "";
      return;
    }
    const height = child.getBoundingClientRect().height;
    const span = Math.max(1, Math.ceil((height + gap) / ROW));
    let start;
    let first;
    let width;
    if (isFull) {
      start = Math.max(...bottoms);
      first = 0;
      width = cols;
    } else if (isWide && cols >= 2) {
      first = 0;
      start = Math.max(bottoms[0], bottoms[1]);
      for (let i = 1; i + 1 < cols; i += 1) {
        const top = Math.max(bottoms[i], bottoms[i + 1]);
        if (top < start) {
          start = top;
          first = i;
        }
      }
      width = 2;
    } else {
      first = bottoms.indexOf(Math.min(...bottoms));
      start = bottoms[first];
      width = 1;
    }
    for (let i = first; i < first + width; i += 1) bottoms[i] = start + span;
    child.style.gridColumn = `${first + 1} / span ${width}`;
    child.style.gridRowStart = String(start);
    child.style.gridRowEnd = `span ${span}`;
  }

  function relayout() {
    const width = page.getBoundingClientRect().width;
    cols = columnsFor(width);
    gap = gapOf(page);
    page.style.setProperty("--flow-cols", String(cols));
    page.dataset.cols = String(cols);
    const bottoms = new Array(Math.max(1, cols)).fill(1); // the next free grid row of each column (grid rows start at 1)
    for (const child of page.children) place(child, bottoms);
  }

  // a band's height changing moves every band after it: one relayout per frame, however many bands grew at once
  let queued = false;
  function relayoutSoon() {
    if (queued) return;
    queued = true;
    const run = () => {
      queued = false;
      relayout();
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
    else run();
  }

  const heights = typeof ResizeObserver === "function" ? new ResizeObserver((entries) => {
    if (entries.some((entry) => entry.target.parentNode === page)) relayoutSoon();
  }) : null;
  const widths = typeof ResizeObserver === "function" ? new ResizeObserver(() => relayout()) : null;
  const children = typeof MutationObserver === "function" ? new MutationObserver((records) => {
    let changed = false;
    for (const record of records) {
      for (const node of record.addedNodes) if (node.nodeType === 1) { heights?.observe(node); changed = true; }
      for (const node of record.removedNodes) if (node.nodeType === 1) { heights?.unobserve(node); changed = true; }
    }
    if (changed) relayout();
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
