// A band's own way to be looked at by itself (ENH-46, owner 2026-11-10: "Anything thats on the page still needs it whole
// page, and a way to look at it directly if the user wants, however I dont think we need a menu item for things on that
// page"; the board). The menu lists pages. Every band a page draws that the
// catalog names (ui/band-catalog.js) carries one button in its head, the mark the menu's rows had: it opens the band wide by
// itself (views/panels.js openBand), with Own page in the flyout's head and previous and next through the bands the page
// shows now, in the page's own order. The band is the one of the page on screen: another team's page opens that team's.
//
// The pages draw and redraw their bands as their answers arrive, so the buttons are put in after the fact: the page's holder
// is watched and every pass marks the bands that have none yet. A pass that finds nothing to do writes nothing, so the
// watch never wakes itself twice. In Game keeps its own row of panels and gets no button; neither does a band inside
// another band, a band with no head, or a second view of a band that already has its entry (the band's own switch leads there).
// A head with no room gives the button up (fit): on a phone, a head that already holds a switch. Search still opens that
// band by itself.
//
//   bandsOnPage(root, route)             [{ node, page, band, entry }] in the page's order: the bands that open by themselves
//   markBands(root, route, onOpen)       one pass: a button in each of those heads; onOpen(node) on a tap; returns their count
//   watchBands(root, { route, onOpen })  keep root marked while pages come and go; route() is the address on screen,
//                                        onOpen(entry, { steps, where, route }) opens the band; returns stop()

import { bandEntry, bandsOf, BAND_PAGES, catalogOf } from "./band-catalog.js";
import { el, text } from "./dom.js";
import { icon } from "./icons.js";

const value = (v) => (typeof v === "function" ? v() : v);
const hasClass = (node, name) => Boolean(node?.classList?.contains(name));
const childWith = (node, name) => [...(node?.children || [])].find((child) => hasClass(child, name)) || null;

function firstMatch(root, selector) {
  try {
    return root.querySelector(selector);
  } catch (error) {
    console.error("A band's selector could not be read.", error);
    return null;
  }
}

const up = (node) => node?.parentElement || node?.parentNode || null;

/** A band that is not drawn inside another band (a box's inner tables are the box's own). */
function topLevel(section) {
  const parent = up(section);
  return !(parent && typeof parent.closest === "function" && parent.closest("section.band"));
}

export function bandsOnPage(root, route) {
  const page = catalogOf(route);
  if (!page || page === "live" || !root || typeof root.querySelectorAll !== "function") return [];
  const byId = new Map();
  const bySelect = new Map(); // a band the catalog finds by a selector: its first match is the band it names
  for (const band of bandsOf(page)) {
    if (band.select) {
      if (band.params) continue;
      const node = firstMatch(root, band.select);
      if (node && !bySelect.has(node)) bySelect.set(node, band);
    } else if (!byId.has(band.id)) byId.set(band.id, band);
  }
  const out = [];
  for (const node of root.querySelectorAll("section.band")) {
    if (!topLevel(node) || !childWith(node, "band__head")) continue;
    const band = byId.get(node.getAttribute("id")) || bySelect.get(node) || null;
    if (band) out.push({ node, page, band, entry: bandEntry(page, band) });
  }
  return out;
}

export function markBands(root, route, onOpen) {
  const found = bandsOnPage(root, route);
  const marked = new Set(found.map((item) => item.node));
  if (root && typeof root.querySelectorAll === "function") {
    for (const old of [...root.querySelectorAll(".band__open")]) {
      if (!marked.has(up(up(old)))) old.remove(); // the page changed under a band that stayed
    }
  }
  for (const item of found) {
    const head = childWith(item.node, "band__head");
    const have = childWith(head, "band__open");
    if (have && have.getAttribute("data-band") === item.band.id) {
      fit(head);
      continue;
    }
    if (have) have.remove();
    const label = text(value(item.band.label));
    const button = el(
      "button",
      {
        class: "btn btn--quiet icon-btn band__open",
        type: "button",
        title: "Open by itself",
        "aria-label": `Open ${label} by itself`,
        "data-band": item.band.id,
        onclick: (event) => {
          event.stopPropagation(); // the head's own tap folds the band
          if (typeof onOpen === "function") onOpen(item.node);
        },
      },
      icon("wide"),
    );
    const toggle = childWith(head, "band__toggle");
    if (toggle) head.insertBefore(button, toggle);
    else head.append(button);
    fit(head);
  }
  return found.length;
}

const TIGHT = "band__head--tight";

/** A head with no room for the button gives it up (components.css hides it): the head is one row of a fixed height that the
 *  tables pin under, so it never wraps. That is a phone-wide head that already holds a switch (the standings' own). The
 *  summary line gives way first, as it does to the band's own tools; only a head that still overflows loses the button.
 *  Measured with the button in, on every pass and on a resize; a page not laid out (the tests' fake page) is left alone. */
function fit(head) {
  if (!head || !head.classList || typeof head.clientWidth !== "number" || typeof head.scrollWidth !== "number") return;
  head.classList.remove(TIGHT);
  if (head.clientWidth > 0 && head.scrollWidth > head.clientWidth + 1) head.classList.add(TIGHT);
}

/** Another team's page ("team=Georgia") is that team's, not My Team: the flyout's foot says whose bands it walks. */
function whose(address) {
  const team = /^team=([^?]+)/.exec(String(address || ""));
  if (!team) return "";
  try {
    return text(decodeURIComponent(team[1]));
  } catch {
    return text(team[1]);
  }
}

export function watchBands(root, { route, onOpen } = {}) {
  if (!root || typeof root.querySelectorAll !== "function") return () => {};
  const now = () => String((typeof route === "function" ? route() : route) || "").replace(/^#/, "");
  const open = (node) => {
    const address = now();
    const items = bandsOnPage(root, address);
    const item = items.find((i) => i.node === node);
    if (!item || typeof onOpen !== "function") return;
    onOpen(item.entry, { steps: items.map((i) => i.entry), where: whose(address) || text(value(BAND_PAGES[item.page]?.label)), route: address });
  };
  let queued = false;
  let stopped = false;
  const pass = () => {
    queued = false;
    if (stopped) return;
    try {
      markBands(root, now(), open);
    } catch (error) {
      console.error("The bands could not be given their own buttons.", error);
    }
  };
  const schedule = () => {
    if (queued || stopped) return;
    queued = true;
    Promise.resolve().then(pass);
  };
  const watcher = typeof MutationObserver === "function" ? new MutationObserver(schedule) : null;
  if (watcher) watcher.observe(root, { childList: true, subtree: true });
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") document.addEventListener("kickoff:rendered", schedule);
  const sized = typeof window !== "undefined" && typeof window.addEventListener === "function";
  if (sized) window.addEventListener("resize", schedule); // a turned tablet has room a phone has not
  pass();
  return () => {
    stopped = true;
    watcher?.disconnect();
    if (typeof document !== "undefined" && typeof document.removeEventListener === "function") document.removeEventListener("kickoff:rendered", schedule);
    if (sized && typeof window.removeEventListener === "function") window.removeEventListener("resize", schedule);
  };
}
