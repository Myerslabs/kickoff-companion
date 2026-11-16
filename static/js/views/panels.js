// The tables the menu opens wide, by themselves (the layout pass, owner 2026-10-22, board 4).
// Each is the page's own table built from the page's own answer, so it
// looks the same in both places; the flyout's head says which table and which game, "‹ the list" reopens the menu where the
// reader came from, and previous and next walk the list. The Pre-Game Program's tables read /api/program/next (or the
// game of the program on screen); In Game's panels open over In Game (views/live.js); the radio is the station list.
// Every other page's bands (owner 2026-10-28: "each band has its own flyout, and page") open from their own page, mounted in
// the flyout with only that band shown (ui/solo.js, ui/band-catalog.js), and every table's head has Own page: the band alone
// at #band=<page>:<band> (views/band.js).
//
//   openFromMenu(entry, { path, menu })   open an entry the menu holds (a flyout or one of In Game's panels): New's rows, the Radio
//   openBand(entry, { steps, where, route })   a band opened by itself from its own head or from Search (ENH-46, owner
//                                         2026-11-10: the menu lists pages only); entry and steps are the catalog's
//                                         (ui/band-catalog.js bandEntry), steps the bands previous and next walk, route the
//                                         address on screen when the band is opened from its page ("team=Georgia")
//   gameLine()                            "SWT vs BLUE · Saturday, October 24 · 7:00 PM" for the game the tables are about,
//                                         once the program has been read; "" before
//   loadProgram({ fresh })                the program the tables are built from (kept a minute)

import { el, fmtDate, fmtTime, text } from "../ui/dom.js";
import { band } from "../ui/states.js";
import { flyoutContent, liftBand, openWide } from "../ui/flyout.js";
import { entriesOf, labelOf, levelAt } from "../ui/menu-tree.js";
import { radioStations } from "../ui/radio-stations.js";
import { askLivePanel } from "../ui/live-panel.js";
import { goTo } from "../ui/layers.js";
import { fetchJson } from "./common.js";
import { abbrOf, PROGRAM_BANDS } from "./program.js";
import { usLabel } from "../identity.js";
import { BAND_PAGES, findBand, ownHref, pageRoute } from "../ui/band-catalog.js";
import { soloMount } from "../ui/solo.js";
import { pageView } from "./band.js";

const PROGRAM_TTL_MS = 60 * 1000;
const cache = { url: null, at: 0, data: null, pending: null };

function hashNow() {
  return typeof window !== "undefined" && window.location ? String(window.location.hash || "") : "";
}

/** The program the tables are about: the one on screen (#program=<id>, or the Post-Game stop #postgame=<id>), else the next game's. */
function programUrl() {
  const match = /^#(?:program|postgame)=(\d+)/.exec(hashNow());
  return match ? `/api/program/${match[1]}` : "/api/program/next";
}

export async function loadProgram({ fresh = false } = {}) {
  const url = programUrl();
  if (!fresh && cache.url === url && cache.data && Date.now() - cache.at < PROGRAM_TTL_MS) return cache.data;
  if (cache.pending && cache.url === url) return cache.pending;
  cache.url = url;
  cache.pending = fetchJson(url)
    .then((envelope) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      if (!data || !data.game || typeof data.game !== "object") throw new Error("No game of ours is on the schedule ahead");
      cache.data = data;
      cache.at = Date.now();
      return data;
    })
    .finally(() => {
      cache.pending = null;
    });
  return cache.pending;
}

/** The game the matchup's tables are about, for the menu's list and the flyout's head. */
export function gameLine(data = cache.data) {
  if (!data || typeof data !== "object" || !data.game) return "";
  const usAbbr = abbrOf(data.us, usLabel());
  const themAbbr = abbrOf(data.them);
  const kickoff = data.game.kickoff;
  const when = kickoff ? [fmtDate(kickoff, "long"), data.game.startTimeTbd ? "time TBD" : fmtTime(kickoff)].join(" · ") : "";
  return [`${usAbbr} vs ${themAbbr}`, when].filter(Boolean).join(" · ");
}

/** The tables the flyout's previous and next walk: the entries of the same list that open the same kind of thing. */
function siblings(menu, path, entry) {
  const level = levelAt(menu, path.slice(0, -1));
  const kind = entry.live ? "live" : "flyout";
  const items = entriesOf(level.items || []).filter((item) => Boolean(item[kind]));
  return { items, where: path.length > 1 ? labelOf(level.label) : "" };
}

/** "‹ the list": the menu opens on the list the table came from; the mark already follows previous and next. */
function reopenMenu(path) {
  if (typeof document === "undefined" || typeof CustomEvent !== "function") return;
  document.dispatchEvent(new CustomEvent("kickoff:menu-open", { detail: { path: path.slice(0, -1) } }));
}

function failed(title, error) {
  return band({ title, collapsible: false, state: { status: "error", message: `${text(error?.message || "The request failed")}. Close this and open it again to retry.` }, errorLead: "Could not load this." });
}

/** One of the program's tables, lifted out of its band head into the flyout. */
async function programContent(key, title) {
  const build = PROGRAM_BANDS[key];
  if (typeof build !== "function") return flyoutContent({ body: failed(title, new Error("This table is not in the program")) });
  let data = null;
  try {
    data = await loadProgram();
  } catch (error) {
    return flyoutContent({ body: failed(title, error) });
  }
  try {
    const lifted = liftBand(build(data));
    return flyoutContent({ summary: lifted.summary, tools: lifted.tools, body: lifted.node });
  } catch (error) {
    console.error(`The ${title} flyout could not be drawn.`, error);
    return flyoutContent({ body: band({ title, collapsible: false, state: { status: "error", message: "This table could not be drawn. Close it and open it again." }, errorLead: "Display error." }) });
  }
}

function loadingBody() {
  return flyoutContent({ body: band({ title: "Loading", collapsible: false, state: { status: "loading" } }) });
}

/** A band of another page: that page's own view, mounted here with only the band shown; stop() unmounts it. `at` is the
 *  address the band was opened from, when it was opened from its own page (another team's page, an earlier game's stop). */
function soloContent(page, id, title, at = null) {
  const band = findBand(page, id);
  const onScreen = page === "program" ? /^#(?:program|postgame)=(\d+)/.exec(hashNow()) : null; // the program on screen, as the program's own tables
  const route = at || (onScreen ? `program=${onScreen[1]}` : pageRoute(page, band));
  let view = null;
  try {
    view = pageView(route, { onStatus: () => {} }); // the page under the flyout keeps the status pill
  } catch (error) {
    console.error(`The ${title} flyout could not open its page.`, error);
  }
  if (!view) return { now: flyoutContent({ body: failed(title, new Error("This table's page is not in this build")) }), later: null, stop: null };
  const body = el("div", { class: "flyout flyout--solo" });
  const solo = soloMount({ view, container: body, band: band?.select ? { select: band.select } : { id }, label: title, pageHref: `#${route}`, flyout: true });
  return { now: body, later: null, stop: () => solo.unmount() };
}

/** A flyout entry's content: the program's tables, the station list for the radio, or a band of another page. */
function contentFor(entry, at = null) {
  const [source, key, id] = String(entry.flyout || "").split(":");
  if (source === "radio") return { now: flyoutContent({ body: radioStations() }), later: null };
  if (source === "program") return { now: loadingBody(), later: programContent(key, labelOf(entry.label)) };
  if (source === "band" && BAND_PAGES[key] && id) return soloContent(key, id, labelOf(entry.label), at);
  return { now: flyoutContent({ body: failed(labelOf(entry.label), new Error("Nothing opens this table yet")) }), later: null };
}

/** The flyout's line under its title: the game for the program's tables, the page for the rest. */
function subtitleFor(entry, at = null) {
  const [source, page] = String(entry.flyout || "").split(":");
  const team = /^team=([^?]+)/.exec(String(at || "")); // a band opened from another team's page says whose it is
  if (team) {
    try {
      return text(decodeURIComponent(team[1]));
    } catch {
      return text(team[1]);
    }
  }
  if (source === "program") return gameLine();
  if (source === "band" && page === "program") return gameLine() || text(labelOf(BAND_PAGES.program.label)); // the game, as the program's own tables
  if (source === "band" && BAND_PAGES[page]) return text(labelOf(BAND_PAGES[page].label));
  return "";
}

/** The table's own page; the program's follow the program on screen (#program=<id>), and a band opened from its own page
 *  keeps that page's address (`at`), so the team or the game on screen is the one its own page shows. */
function ownFor(entry, at = null) {
  if (at) return { href: ownHref(entry, { route: at }) };
  const match = /^#(?:program|postgame)=(\d+)/.exec(hashNow());
  return { href: ownHref(entry, { route: entry.flyout?.startsWith("program:") && match ? `program=${match[1]}` : null }) };
}

/** The wide flyout on one table. group: { items, where } is what previous and next walk; back: the "‹ the list" button (the
 *  menu's rows only); at: the address a band was opened from on its own page; mark: tell the menu which row is open. */
function openFlyout(entry, { group, back = null, at = null, mark = false }) {
  let current = entry;
  let handle = null;
  let stop = null; // the solo page in the flyout, unmounted when the table changes or the flyout closes
  const release = () => {
    const was = stop;
    stop = null;
    if (typeof was === "function") was();
  };
  const stepsFor = (item) => ({ items: group.items.map((i) => ({ id: i.id, label: labelOf(i.label) })), index: group.items.findIndex((i) => i.id === item.id), where: group.where, onStep: (id) => show(group.items.find((i) => i.id === id)) });
  const fill = (item) => {
    release();
    const { now, later, stop: next } = contentFor(item, at);
    stop = next || null;
    handle.setBody(now);
    handle.setSubtitle(subtitleFor(item, at));
    if (later) {
      later.then((node) => {
        if (current === item) handle.setBody(node);
        handle.setSubtitle(subtitleFor(item, at));
      });
    }
  };
  function show(item) {
    if (!item || !handle) return;
    current = item;
    handle.setTitle(labelOf(item.label));
    handle.setSteps(stepsFor(item));
    handle.setOwn(ownFor(item, at));
    fill(item);
    if (mark && typeof CustomEvent === "function") document.dispatchEvent(new CustomEvent("kickoff:menu-mark", { detail: { mark: item.id } }));
  }
  handle = openWide({ title: labelOf(entry.label), subtitle: subtitleFor(entry, at), back, steps: group.items.length > 1 ? stepsFor(entry) : null, own: ownFor(entry, at), body: loadingBody(), onClose: release });
  fill(entry);
  return handle;
}

/** One of In Game's panels: on In Game it opens there at once; from any other page the reader goes to In Game first. */
function openLive(entry, { group, back = null, mark = false }) {
  const detail = {
    id: entry.live,
    steps: { items: group.items.map((i) => ({ id: i.live, label: labelOf(i.label) })), where: group.where },
    back,
    entryOf: (liveId) => (mark ? group.items.find((i) => i.live === liveId)?.id || null : null),
  };
  if (/^#live(?:$|[=?])/.test(hashNow())) {
    document.dispatchEvent(new CustomEvent("kickoff:live-panel", { detail }));
    return;
  }
  askLivePanel(detail);
  goTo("live");
}

export function openFromMenu(entry, ctx = {}) {
  if (!entry || typeof entry !== "object") return null;
  if (!entry.live && !entry.flyout) return null;
  const path = Array.isArray(ctx.path) ? ctx.path : [entry.id];
  const group = siblings(ctx.menu, path, entry);
  const list = levelAt(ctx.menu, path.slice(0, -1));
  const reopen = () => reopenMenu(path);
  if (entry.live) return openLive(entry, { group, back: { label: labelOf(list.label), onClick: reopen }, mark: true });
  return openFlyout(entry, { group, back: { label: path.length > 1 ? labelOf(list.label) : "Menu", onClick: reopen }, mark: true });
}

/** A band opened by itself where it sits: from the button in its own head (ui/band-open.js) or from Search. There is no
 *  list to go back to, so the flyout's head has no "‹ the list"; previous and next walk `steps`, the bands of the page. */
export function openBand(entry, { steps = null, where = "", route = null } = {}) {
  if (!entry || typeof entry !== "object") return null;
  if (!entry.live && !entry.flyout) return null;
  const kind = entry.live ? "live" : "flyout";
  const listed = (Array.isArray(steps) ? steps : []).filter((item) => item && typeof item === "object" && Boolean(item[kind]));
  const items = listed.some((item) => item.id === entry.id) ? listed : [entry, ...listed];
  const group = { items, where: typeof where === "string" ? where : "" };
  if (entry.live) return openLive(entry, { group });
  return openFlyout(entry, { group, at: typeof route === "string" && route ? route : null });
}

