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
//   columnsFor(width)  1 under 700 px, 2 from 700 (the iPad both ways and any desktop browser), 3 from 1700 (a 1080p screen) and 4 from 2500
//       (Design rules, owner 2026-10-21: "Wide screens may use more than two columns"; the tablet lock of 2026-10-13 held every wide screen to two).
//   mountFlow(ui, container, page, { wide, full, chips = true })  (final pass) the one way a view mounts a flowing
//       page: stops the layout kept in `ui` from the last draw, pins the section chips above the page (chips: false
//       for a page with one band), replaces the container's children and starts the flow. `ui` keeps { flow, chips }.
//   stopFlow(ui)  stops both; a view calls it from unmount.
//
// How it packs: the page is a CSS grid of 4 px rows, laid out in flush rows (the layout pass, owner 2026-10-22, after the
// Season board: "I'm just talking about the spacing and alignment of the bands. That was the first time they looked
// professional", and his red lines: a row's bands end on one line, the column divide runs straight, a stack on one side
// ends level with the band beside it). Bands fill a row left to right, one a column (a wide one two, a full one a row of
// its own); once every column has one, the next bands stack under the shortest column while they fit beside the tallest;
// the band that does not fit opens the next row. The row closes with the last band of each column stretched to the row's
// bottom (its min-height, so a band that grows still grows), and a row left short of bands gives its last band the
// columns left over, so nothing leaves a hole. With one column the page is a plain stack. A ResizeObserver re-measures a
// band whose height changes (a fold, data arriving).

import { sectionChips } from "./states.js";

const ROW = 4;
const BREAKS = [[2500, 4], [1700, 3], [700, 2]];

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

  const kindOf = (child) => (fullIds.has(child.id) || child.classList.contains("flow-full") ? "full" : wideIds.has(child.id) || child.classList.contains("flow-wide") ? "wide" : "one");
  const setPlace = (child, first, width, start, span) => {
    child.style.gridColumn = `${first + 1} / span ${width}`;
    child.style.gridRowStart = String(start);
    child.style.gridRowEnd = `span ${span}`;
  };
  // a wrapper around one band (a .flow-full div holding a band) passes the stretch on to its band (components.css)
  const holdsOneBand = (child) => !child.classList.contains("band") && child.children.length === 1 && child.children[0].classList?.contains("band");

  // The order rule (owner 2026-10-13, "making sure that it's in the correct order when you're scrolling down the page"):
  // every band is placed below everything listed before it, so the reader meets them in the list's order. The flush rows
  // (2026-10-22) keep it: a row fills left to right, then stacks under its shortest column, then the next row starts below.
  function relayout() {
    const width = page.getBoundingClientRect().width;
    cols = columnsFor(width);
    gap = gapOf(page);
    page.style.setProperty("--flow-cols", String(cols));
    page.dataset.cols = String(cols);
    const kids = [...page.children].filter((child) => child && child.style && child.classList); // elements, not text
    for (const child of kids) {
      child.style.minHeight = ""; // each band's own height first: a stretch from the last layout is no measure
      child.classList.remove("flow-hold");
    }
    if (cols <= 1) {
      for (const child of kids) {
        child.style.gridColumn = kindOf(child) === "full" ? "1 / -1" : "";
        child.style.gridRowStart = "";
        child.style.gridRowEnd = "";
      }
      return;
    }
    const heights = kids.map((child) => child.getBoundingClientRect().height);
    const spans = heights.map((height) => (height > 0 ? Math.max(1, Math.ceil((height + gap) / ROW)) : 0)); // nothing drawn (display: none): no place in a row
    const own = new Map(kids.map((child, i) => [child, heights[i]])); // each band's own height, before any stretch
    let top = 1; // the grid line the row starts on (grid rows start at 1)
    let row = null; // { bottoms, last: the last band in each column, starts, filled, placed }
    const open = () => ({ bottoms: new Array(cols).fill(top), last: new Array(cols).fill(null), widths: new Map(), filled: 0, placed: [] });
    const close = () => {
      if (!row || !row.placed.length) {
        row = null;
        return;
      }
      if (row.filled < cols) {
        // a row short of bands: its last band takes the columns left over (nothing leaves a hole)
        const lastBand = row.placed[row.placed.length - 1];
        const { first, width: w } = row.widths.get(lastBand);
        const grown = w + (cols - row.filled);
        row.widths.set(lastBand, { first, width: grown });
        for (let c = first; c < first + grown; c += 1) {
          row.last[c] = lastBand;
          row.bottoms[c] = row.bottoms[first];
        }
        lastBand.style.gridColumn = `${first + 1} / span ${grown}`;
      }
      // The row ends where its tallest band ends, to the pixel: every other column's last band is stretched to that line. The
      // tallest keeps its own height, so a band that shrinks is always noticed (a min-height would hide it from the observer).
      const bottom = Math.max(...row.bottoms);
      const lasts = [...new Set(row.last.filter(Boolean))];
      const ends = new Map(lasts.map((child) => [child, (Number(child.style.gridRowStart) - top) * ROW + (own.get(child) || 0)]));
      const line = Math.max(...ends.values());
      for (const child of lasts) {
        if (!(line - ends.get(child) > 0.5)) continue; // it reaches the line by itself
        const start = Number(child.style.gridRowStart);
        child.style.gridRowEnd = `span ${bottom - start}`;
        child.style.minHeight = `${line - (start - top) * ROW}px`;
        if (holdsOneBand(child)) child.classList.add("flow-hold");
      }
      top = bottom;
      row = null;
    };
    kids.forEach((child, i) => {
      const span = spans[i];
      if (!span) {
        child.style.gridColumn = "";
        child.style.gridRowStart = "";
        child.style.gridRowEnd = "";
        return;
      }
      const kind = kindOf(child);
      if (kind === "full") {
        close();
        setPlace(child, 0, cols, top, span);
        top += span;
        return;
      }
      const width = kind === "wide" ? Math.min(2, cols) : 1;
      if (row && row.filled < cols && row.filled + width > cols) close(); // no room left beside the row's bands
      if (row && row.filled >= cols) {
        // the row is full: stack under the shortest column while the band fits beside the tallest
        if (width === 1) {
          const bottom = Math.max(...row.bottoms);
          const c = row.bottoms.indexOf(Math.min(...row.bottoms));
          if (row.bottoms[c] + span <= bottom) {
            setPlace(child, c, 1, row.bottoms[c], span);
            row.bottoms[c] += span;
            row.last[c] = child;
            row.widths.set(child, { first: c, width: 1 });
            row.placed.push(child);
            return;
          }
        }
        close();
      }
      if (!row) row = open();
      const first = row.filled;
      setPlace(child, first, width, top, span);
      for (let c = first; c < first + width; c += 1) {
        row.bottoms[c] = top + span;
        row.last[c] = child;
      }
      row.widths.set(child, { first, width });
      row.placed.push(child);
      row.filled += width;
    });
    close();
  }

  // a band's height changing moves every band after it: one relayout per frame, however many bands grew at once
  let queued = false;
  function relayoutSoon() {
    if (queued) return;
    queued = true;
    let done = false;
    const run = () => {
      if (done) return;
      done = true;
      queued = false;
      relayout();
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
    setTimeout(run, 120); // a page drawn in the background gets no frames (2026-10-22): it is laid out all the same
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
