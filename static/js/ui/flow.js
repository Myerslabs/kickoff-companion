// The flowing page, one column (owner 2026-11-01, after the Georgia game weekend: the Program read well on the iPad and
// badly on the desktop browser and the phone, because the page packed the bands into 2 to 4 columns of odd widths and
// stretched a pair to match heights; "every band just to be a single band ... widens with the screen and you can scroll up
// and down"). Every flowing page is a plain stack now: each band takes the page's whole width, in the list's order (the
// order rule, owner 2026-10-13), and the band itself decides how its content sits in the width it has (container queries
// inside the band; its content stops widening at --read-max, components.css, so a ten-row list never spans a monitor;
// a band marked wide keeps the whole width). The packer of Phase 17 #7, #10, #28 and the flush rows of 2026-10-22 are gone.
//
//   flow(page, { wide = [] })   turns `page` (a .page element) into a flowing page: the class, one column, and the bands
//       whose id is in `wide`, or that carry .flow-wide, marked .band--wide (their content takes the whole width: the
//       long tables, the grids). `full` is accepted and means nothing now: every band spans the page. Returns
//       { relayout, stop }, both harmless, so a view keeps its calls.
//   columnsFor(width)  1 at every width.
//   mountFlow(ui, container, page, { wide, chips = true })  the one way a view mounts a flowing page: stops the layout
//       kept in `ui` from the last draw, pins the section chips above the page (chips: false for a page with one band),
//       replaces the container's children and starts the flow. `ui` keeps { flow, chips }.
//   stopFlow(ui)  stops both; a view calls it from unmount.

import { sectionChips } from "./states.js";

export function columnsFor() {
  return 1;
}

/** The bands of the page that take the whole width: by id, or by the .flow-wide class a view put on one. */
function markWide(page, wideIds) {
  for (const child of page.children) {
    if (!child || !child.classList) continue;
    const wide = wideIds.has(child.id) || child.classList.contains("flow-wide");
    child.classList.toggle("band--wide", wide);
    // a band of a wrapper (a div holding one band): the mark goes to the band, whose body the cap measures
    if (wide && !child.classList.contains("band") && child.children.length === 1 && child.children[0].classList?.contains("band")) child.children[0].classList.add("band--wide");
  }
}

export function flow(page, { wide = [] } = {}) {
  if (!page || typeof page.appendChild !== "function") return { relayout() {}, stop() {} };
  const wideIds = new Set(wide);
  page.classList.add("flow");
  page.dataset.cols = "1";
  page.style.setProperty("--flow-cols", "1");
  function relayout() {
    for (const child of page.children) {
      if (!child || !child.style) continue;
      // nothing of the packer's placement survives on a page drawn before (a saved tab reloaded with the old code)
      child.style.gridColumn = "";
      child.style.gridRowStart = "";
      child.style.gridRowEnd = "";
      child.style.minHeight = "";
      child.classList?.remove("flow-hold");
    }
    markWide(page, wideIds);
  }
  // bands come and go (a box redrawn, a band loaded late): the new ones get their mark
  const children = typeof MutationObserver === "function" ? new MutationObserver(() => markWide(page, wideIds)) : null;
  children?.observe(page, { childList: true });
  relayout();
  return {
    relayout,
    stop() {
      children?.disconnect();
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

export function mountFlow(ui, container, page, { wide = [], chips = true } = {}) {
  const keep = ui && typeof ui === "object" ? ui : {};
  stopFlow(keep);
  if (chips) {
    keep.chips = sectionChips(page);
    keep.chips.refresh();
    container.replaceChildren(keep.chips, page);
  } else {
    container.replaceChildren(page);
  }
  keep.flow = flow(page, { wide });
  return keep;
}
