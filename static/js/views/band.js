// A band's own page (owner 2026-10-28: "also its own page for detailed viewing"): #band=<page>:<band>, the band alone across
// the whole page, unfolded, every row, the page's own table from the page's own answer (ui/solo.js), with Back and the way
// to the whole page. The address can be shared; the flyout's Own page leads here (views/panels.js). In Game's panels are
// drawn by In Game itself in its panel mode (views/live.js, `panel`), refreshed with the game.
//
//   registerPages(factories)        app.js hands over its page factories (BUILT) once, so the flyouts and this page mount
//                                   the same views the router does
//   pageView(route, opts)           the view of a page address ("stats=passing?view=teams"), or null
//   createBandView({ onStatus, arg, params })   the page; arg is "<page's address>:<band id>", params the page's query

import { bandHref, BAND_PAGES, catalogPage, findBand, parseBandArg } from "../ui/band-catalog.js";
import { el, text } from "../ui/dom.js";
import { parseRoute } from "../ui/national-link.js";
import { soloMount } from "../ui/solo.js";
import { backRow, band } from "../ui/states.js";

let factories = {};

export function registerPages(map) {
  factories = map && typeof map === "object" ? map : {};
}

const labelOf = (v) => (typeof v === "function" ? v() : v);

export function pageView(route, opts = {}) {
  const parsed = parseRoute(`#${String(route || "")}`, new Set(Object.keys(factories)));
  const factory = parsed ? factories[parsed.id] : null;
  if (typeof factory !== "function" || parsed.id === "band") return null;
  return factory(opts, parsed.arg, null, parsed.params || {});
}

function queryOf(params) {
  const pairs = Object.entries(params && typeof params === "object" ? params : {}).filter(([, v]) => typeof v === "string" && v);
  return pairs.length ? `?${pairs.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&")}` : "";
}

/** What the band route names: its page in the catalog, the band, and the page's full address. */
export function bandTarget(arg, params = {}) {
  const parsed = parseBandArg(arg);
  if (!parsed) return null;
  const page = catalogPage(parsed);
  const entry = page ? findBand(page, parsed.id) : null;
  return {
    ...parsed,
    catalog: page,
    entry,
    address: `${parsed.route}${queryOf(params)}`,
    label: entry ? text(labelOf(entry.label)) : null,
    pageLabel: page ? text(labelOf(BAND_PAGES[page].label)) : null,
    which: entry?.select ? { select: entry.select } : { id: parsed.id },
  };
}

/** The band's page starts at its top: a page that scrolls to its band on arrival (the Season to its polls, #season=polls:AP)
 *  would carry Back and the title off the screen, and the band is the first thing here anyway. Held a few seconds while the
 *  page draws; any touch, wheel or key ends it, and Back to an entry seen before keeps the scroll the router puts back. */
function holdTop(ms = 4000) {
  if (typeof window === "undefined" || typeof window.scrollTo !== "function") return () => {};
  let seen = null;
  try {
    seen = window.history?.state?.scrollY;
  } catch {
    seen = null;
  }
  if (typeof seen === "number" && Number.isFinite(seen)) return () => {};
  const kinds = ["wheel", "touchstart", "keydown", "pointerdown"];
  let stopped = false;
  let timer = null;
  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    for (const kind of kinds) window.removeEventListener(kind, stop, { capture: true });
  };
  for (const kind of kinds) window.addEventListener(kind, stop, { passive: true, capture: true });
  const until = Date.now() + ms;
  const tick = () => {
    if (stopped) return;
    if (Date.now() > until) {
      stop();
      return;
    }
    if ((Number(window.scrollY) || 0) > 0) window.scrollTo(0, 0);
    timer = setTimeout(tick, 100);
  };
  timer = setTimeout(tick, 0);
  return stop;
}

function missingPage(message) {
  return el("div", { class: "page band-page" }, backRow({ label: "Back", fallback: "#program" }), band({ id: "band-missing", title: "Not a table of the app", collapsible: false, state: { status: "empty", message } }));
}

export function createBandView({ onStatus, arg = null, params = {} } = {}) {
  const target = bandTarget(arg, params);
  let solo = null;
  let inner = null;
  let release = () => {};

  function head(title) {
    return el(
      "div",
      { class: "band-page__head" },
      backRow({ label: "Back", fallback: `#${target.address}` }),
      el("h1", { class: "page-title band-page__title" }, text(title)),
      el("a", { class: "btn band-page__whole", href: `#${target.address}` }, target.pageLabel ? `The whole ${target.pageLabel === "In Game" ? "In Game screen" : "page"}` : "The whole page"),
    );
  }

  return {
    mount(node) {
      if (!target) {
        node.replaceChildren(missingPage("This address names no table. The menu lists every page's tables."));
        if (typeof onStatus === "function") onStatus({ kind: "quiet", label: "No such table" });
        return;
      }
      const title = target.label || "This table";
      const body = el("div", { class: "band-page__body" });
      node.replaceChildren(el("div", { class: "page band-page", dataset: { band: target.id } }, head(title), body));
      if (target.page === "live") {
        // In Game draws the panel by itself, refreshed with the game (its stream, its delay)
        inner = pageView(target.address, { onStatus, panel: target.entry?.panel || target.id });
        if (!inner) {
          body.replaceChildren(band({ title, collapsible: false, state: { status: "error", message: "In Game could not be opened." } }));
          return;
        }
        inner.mount(body);
        return;
      }
      const view = pageView(target.address, { onStatus });
      if (!view) {
        body.replaceChildren(band({ title, collapsible: false, state: { status: "empty", message: `${title} belongs to a page this build does not have.` } }));
        return;
      }
      solo = soloMount({ view, container: body, band: target.which, label: title }); // the head above already leads to the whole page
      release = holdTop();
    },
    refresh() {
      if (solo) return solo.refresh();
      return typeof inner?.refresh === "function" ? inner.refresh() : null;
    },
    unmount() {
      release();
      solo?.unmount();
      solo = null;
      try {
        inner?.unmount?.();
      } catch (error) {
        console.error("The band's page did not unmount cleanly.", error);
      }
      inner = null;
    },
  };
}

export { bandHref };
