// The season as one line (owner 2026-10-30): the stops the rail walks and the stop that leads now, read once from
// /api/stops and kept for every page, refreshed every ten minutes and on demand (a final, a lock). The shell's middle tab
// and the rail on the cover both read it.
//
//   loadStops({ force })  -> Promise<line | null>   the answer's data (null while the server has none)
//   stopsNow()            -> line | null            the last answer
//   onStops(fn)           -> unsubscribe            fn(line) on every new answer
//   weekOf(gameId)        -> item | null            the week item holding that game
//   currentStop()         -> current | null
//   stopHref(current)     -> "#program=…" | "#season"
//
// Nothing polls without a page: the refresh timer runs only while a page has asked for the line.

import { fetchJson } from "./views/common.js";

const REFRESH_MS = 10 * 60 * 1000;
let line = null;
let loading = null;
let loadedAt = 0;
const listeners = new Set();
let timer = null;

function tell() {
  for (const fn of Array.from(listeners)) {
    try {
      fn(line);
    } catch (error) {
      console.error("A stops listener failed.", error);
    }
  }
}

function schedule() {
  if (timer || typeof setTimeout !== "function") return;
  timer = setTimeout(() => {
    timer = null;
    loadStops({ force: true }).catch(() => {});
  }, REFRESH_MS);
}

export async function loadStops({ force = false } = {}) {
  if (!force && line && Date.now() - loadedAt < REFRESH_MS) return line;
  if (loading) return loading;
  loading = (async () => {
    try {
      const envelope = await fetchJson("/api/stops");
      const data = envelope && typeof envelope === "object" ? envelope.data : null;
      if (data && typeof data === "object" && Array.isArray(data.items)) {
        line = data;
        loadedAt = Date.now();
        tell();
      }
    } catch (error) {
      console.warn("The season's line could not be read; the rail keeps the last answer.", error);
    } finally {
      loading = null;
      schedule();
    }
    return line;
  })();
  return loading;
}

export function stopsNow() {
  return line;
}

export function onStops(fn) {
  if (typeof fn !== "function") return () => {};
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function weekOf(gameId) {
  if (!line || gameId === null || gameId === undefined) return null;
  const id = String(gameId);
  return (line.items || []).find((item) => item && item.kind === "week" && String(item.gameId) === id) || null;
}

export function currentStop() {
  return line && line.current && typeof line.current === "object" ? line.current : null;
}

export function stopHref(current) {
  return current && typeof current.href === "string" && current.href.startsWith("#") ? current.href : "#program";
}

/** The tests swap the line in without a server. */
export function _setStops(data) {
  line = data && typeof data === "object" ? data : null;
  loadedAt = Date.now();
  tell();
}
