// The tables the menu opens wide, by themselves (the layout pass, owner 2026-10-22, board 4:
// https://claude.ai/artifact/4VVfYTQpLu1oyz8dz9xosZ). Each is the page's own table built from the page's own answer, so it
// looks the same in both places; the flyout's head says which table and which game, "‹ the list" reopens the menu where the
// reader came from, and previous and next walk the list. The Pre-Game Program's tables read /api/program/next (or the
// game of the program on screen); In Game's panels open over In Game (views/live.js); the radio is the station list.
//
//   openFromMenu(entry, { path, menu })   open an entry the menu holds (a flyout or one of In Game's panels)
//   gameLine()                            "SWT vs BLUE · Saturday, October 24 · 7:00 PM" for the game the tables are about,
//                                         once the program has been read; "" before
//   loadProgram({ fresh })                the program the tables are built from (kept a minute)

import { fmtDate, fmtTime, text } from "../ui/dom.js";
import { band } from "../ui/states.js";
import { flyoutContent, liftBand, openWide } from "../ui/flyout.js";
import { entriesOf, labelOf, levelAt } from "../ui/menu-tree.js";
import { radioStations } from "../ui/radio-stations.js";
import { askLivePanel } from "../ui/live-panel.js";
import { goTo } from "../ui/layers.js";
import { fetchJson } from "./common.js";
import { abbrOf, PROGRAM_BANDS } from "./program.js";
import { usLabel } from "../identity.js";

const PROGRAM_TTL_MS = 60 * 1000;
const cache = { url: null, at: 0, data: null, pending: null };

function hashNow() {
  return typeof window !== "undefined" && window.location ? String(window.location.hash || "") : "";
}

/** The program the tables are about: the one on screen (#program=<id>), else the next game's. */
function programUrl() {
  const match = /^#program=(\d+)/.exec(hashNow());
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

/** A flyout entry's content: the program's tables, or the station list for the radio. */
function contentFor(entry) {
  const [source, key] = String(entry.flyout || "").split(":");
  if (source === "radio") return { now: flyoutContent({ body: radioStations() }), later: null };
  if (source === "program") return { now: loadingBody(), later: programContent(key, labelOf(entry.label)) };
  return { now: flyoutContent({ body: failed(labelOf(entry.label), new Error("Nothing opens this table yet")) }), later: null };
}

function openFlyout(entry, { path, menu }) {
  const group = siblings(menu, path, entry);
  const back = { label: path.length > 1 ? labelOf(levelAt(menu, path.slice(0, -1)).label) : "Menu", onClick: () => reopenMenu(path) };
  let current = entry;
  let handle = null;
  const stepsFor = (item) => ({ items: group.items.map((i) => ({ id: i.id, label: labelOf(i.label) })), index: group.items.findIndex((i) => i.id === item.id), where: group.where, onStep: (id) => show(group.items.find((i) => i.id === id)) });
  const fill = (item) => {
    const { now, later } = contentFor(item);
    handle.setBody(now);
    if (later) {
      later.then((node) => {
        if (current === item) handle.setBody(node);
        handle.setSubtitle(item.flyout?.startsWith("program:") ? gameLine() : "");
      });
    }
  };
  function show(item) {
    if (!item || !handle) return;
    current = item;
    path = [...path.slice(0, -1), item.id];
    handle.setTitle(labelOf(item.label));
    handle.setSteps(stepsFor(item));
    fill(item);
    document.dispatchEvent(new CustomEvent("kickoff:menu-mark", { detail: { mark: item.id } }));
  }
  handle = openWide({ title: labelOf(entry.label), subtitle: entry.flyout?.startsWith("program:") ? gameLine() : "", back, steps: group.items.length > 1 ? stepsFor(entry) : null, body: loadingBody() });
  fill(entry);
  return handle;
}

/** One of In Game's panels: on In Game it opens there at once; from any other page the reader goes to In Game first. */
function openLive(entry, { path, menu }) {
  const group = siblings(menu, path, entry);
  const detail = {
    id: entry.live,
    steps: { items: group.items.map((i) => ({ id: i.live, label: labelOf(i.label) })), where: group.where },
    back: { label: labelOf(levelAt(menu, path.slice(0, -1)).label), onClick: () => reopenMenu(path) },
    entryOf: (liveId) => group.items.find((i) => i.live === liveId)?.id || null,
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
  const path = Array.isArray(ctx.path) ? ctx.path : [entry.id];
  if (entry.live) return openLive(entry, { path, menu: ctx.menu });
  if (entry.flyout) return openFlyout(entry, { path, menu: ctx.menu });
  return null;
}

