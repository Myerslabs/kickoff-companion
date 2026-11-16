// Helpers shared by the views: envelope fetching with a timeout, part status to band state,
// the status-pill text for an envelope, and a small polling controller.
//
// Phase 16 (stream F) frozen API:
//   poller({ url, live, refreshMs, staleAfterMs, onStatus, render, renderError, renderLoading }) -> { mount, refresh, unmount, last }
//       Manual refresh (owner 2026-11-14: "make sure the page doesnt refresh when browsing. Lets change it to manual
//       refresh only and refresh on page open"): a page asks the server when it is opened, when the reader refreshes
//       (the Refresh beside the status pill, a pull down at the top, r on a keyboard), and on a return to the app once
//       its copy is older than RETURN_REFRESH_MS; never on a timer and never when a Claude run ends (the To do says so).
//       Only a live page (live: true, the Trivia page) still asks every refreshMs, and on a return after staleAfterMs.
//       Instant back: the last good envelope of every url is kept for the page's lifetime; a view mounted again
//       draws it at once (no skeleton), whatever its age, and refreshes in the background (post-freeze Wave 2,
//       BUG-18: before, only a copy younger than refreshMs was drawn and an older one meant the loading sun). The
//       copies also live in this tab's sessionStorage (ENH-1), so a tab Safari discarded comes back with its
//       pages; they are dropped when the page's build changes, and kept within a budget. A fetch that brings
//       the same fetched_at and the same data does not rebuild the page. A rebuild keeps the page's scroll and
//       every table's scroll. After each draw the document hears "kickoff:rendered" (detail { url }).
//       refresh() returns a promise (pull to refresh waits on it).
//   clearEnvelopeCache()  forget the kept envelopes (tests).
//   errorPanel(title, message, retry)  one full-width band in its error state: what failed and a quiet 'Try now'
//       inside the band.

import { noteBuild, noteClaude, noteRestart, noteSeasonSwitch } from "../build.js";
import { pageBuild } from "../client-log.js";
import { DASH, el, isNum, restoreScroll, scrollState, text } from "../ui/dom.js";
import { band, loadingSun, stateBlock } from "../ui/states.js";
import { openFeedback } from "../ui/feedback.js"; // an error panel's Send a report (owner 2026-10-23)

export const FETCH_TIMEOUT_MS = 20000;
export const RETURN_REFRESH_MS = 15 * 60 * 1000; // back in the app after this long: the page is asked again (owner 2026-11-14: "Only if it's old")
// A page the server is still gathering (a cold cache after a restart: the Game program alone makes a few dozen
// CFBD calls) is not an error. The server keeps working after the browser stops waiting, and its per-request locks
// make an asked-again request wait for the same calls (no extra quota), so the page keeps asking, showing that it
// is still loading, for up to SLOW_TRIES rounds of FETCH_TIMEOUT_MS before it says it could not load.
export const SLOW_TRIES = 9;
const SLOW_DETAIL = "Still gathering this page. The first load after the server starts can take a minute or two; it keeps working.";

export function ageSeconds(iso) {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.max(0, (Date.now() - t) / 1000);
}

/** Map a server part status to a band state. `has` says whether there is anything to draw. */
export function partState(part, has) {
  if (!part) return has ? { status: "ready" } : { status: "empty" };
  if (part.status === "error") return { status: "error", message: `${text(part.error)}. The app keeps retrying.` };
  if (!has) return { status: "empty" };
  if (part.status === "stale") return { status: "stale", ageSeconds: part.ageSeconds, message: part.error ? `${part.error}.` : undefined };
  return { status: "ready" };
}

/** The worst of several parts, for a band that draws from more than one source. */
export function combinedState(parts, has) {
  const list = (parts || []).filter(Boolean);
  if (list.every((p) => p.status === "error") && list.length) return partState(list[0], has);
  const stale = list.find((p) => p.status === "stale");
  if (stale) return partState(stale, has);
  const error = list.find((p) => p.status === "error");
  if (error && has) return { status: "ready", updatedText: `Part of this panel is missing: ${text(error.error)}. The app keeps retrying.` };
  return partState(list[0], has);
}

/** A signal that aborts after `ms` with a TimeoutError (not an AbortError, which callers read as a cancellation). */
export function timeoutSignal(ms = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const reason = typeof DOMException === "function" ? new DOMException(`No answer from the server after ${Math.round(ms / 1000)} s.`, "TimeoutError") : new Error("timeout");
  const timer = setTimeout(() => controller.abort(reason), ms);
  return { signal: controller.signal, clear: () => clearTimeout(timer), abort: () => controller.abort() };
}

// Batch 1 (owner 2026-11-15, "Every page in ~1.5 s"): one request per address at a time. Bands of one page asked for the
// same answer side by side (My Team asked for the program three times, a Post-Game for the Archive and the whole paper
// twice); now a band asking while the same request is in flight joins it. A page's own load and Refresh ({ fresh: true })
// always start a request of their own, which the bands may then join. Every caller gets its own copy, so a band that changes
// its answer never changes another's; a caller's signal ends its own wait, and once every caller has let go the request
// itself is cancelled, as before.
const inflight = new Map(); // url -> { promise, waiters, controller }

function copyOf(body) {
  try {
    return typeof structuredClone === "function" ? structuredClone(body) : JSON.parse(JSON.stringify(body));
  } catch {
    return body;
  }
}

function abortError() {
  try {
    return new DOMException("The operation was aborted.", "AbortError");
  } catch {
    const error = new Error("The operation was aborted.");
    error.name = "AbortError";
    return error;
  }
}

/** One caller's wait on a shared request: its signal ends the wait; the last caller to let go cancels the request. */
function waitOn(entry, signal) {
  entry.waiters += 1;
  if (!signal) return entry.promise;
  const leave = () => {
    entry.waiters -= 1;
    if (entry.waiters <= 0) {
      // the review (2026-11-16): a request every caller let go is taken out of the map at once, so the next page's band
      // asking for the same address starts afresh instead of joining a request already cancelled
      if (inflight.get(entry.key) === entry) inflight.delete(entry.key);
      entry.controller.abort(abortError());
    }
  };
  if (signal.aborted) {
    leave();
    return Promise.reject(abortError());
  }
  return new Promise((resolve, reject) => {
    const stop = () => {
      leave();
      reject(abortError());
    };
    signal.addEventListener("abort", stop, { once: true });
    entry.promise.then(
      (value) => {
        signal.removeEventListener("abort", stop);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener("abort", stop);
        reject(error);
      },
    );
  });
}

function start(key) {
  const controller = new AbortController();
  const entry = { key, promise: null, waiters: 0, controller };
  entry.promise = requestJson(key, controller.signal);
  const done = () => {
    if (inflight.get(key) === entry) inflight.delete(key);
  };
  entry.promise.then(done, done);
  return entry;
}

export async function fetchJson(url, signal, { fresh = false, shared = true } = {}) {
  const key = String(url);
  if (!shared) return copyOf(await waitOn(start(key), signal)); // a request of its own (a patient wait's next round)
  let entry = fresh ? null : inflight.get(key);
  if (entry && entry.controller.signal.aborted) entry = null; // a request already cancelled is never joined
  if (!entry) {
    entry = start(key);
    inflight.set(key, entry);
  }
  return copyOf(await waitOn(entry, signal));
}

async function requestJson(url, cancel) {
  // Final pass: no request waits for ever: it gives up after FETCH_TIMEOUT_MS, so a dead server shows as
  // an error instead of a page that never settles; `cancel` is the shared request's own (every caller let go, waitOn above).
  // The review (2026-11-16): the clock runs until the answer's body is read, so a body that stalls (Wi-Fi gone mid-answer)
  // ends the request instead of holding every later caller of the address.
  const own = timeoutSignal();
  const stop = () => own.abort();
  if (cancel) cancel.addEventListener("abort", stop, { once: true });
  try {
    const response = await fetch(url, { signal: own.signal, headers: { Accept: "application/json" } });
    let body = null;
    try {
      body = await response.json();
    } catch (error) {
      if (own.signal.aborted) throw error; // the clock ran out, or every caller let go, while the body came
      body = null;
    }
    if (body && typeof body === "object") {
      noteBuild(body.meta?.build); // Phase 12: the tablet learns of a new build
      noteRestart(body.meta?.restartNeeded); // Phase 16 wave 3: the server's code changed; a restart brings it in
      noteClaude(body.meta?.claudeSignedOut); // 2026-11-15: Claude Code signed out on the server computer, or signed in again
      noteSeasonSwitch(body.meta?.seasonSwitch); // rollover R2: the app moved to the next season, or the move is waiting
    }
    if (!response.ok || !body || typeof body !== "object") {
      const message = body?.errors?.[0]?.message || `HTTP ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return body;
  } finally {
    own.clear();
    if (cancel) cancel.removeEventListener("abort", stop);
  }
}

/**
 * One request that waits like a page does (Phase 18.2): a sheet or panel that opens on a cold server gets the same
 * patience as a page, asking again after each FETCH_TIMEOUT_MS round, up to `tries` rounds, instead of giving up at 20 s.
 * `current()` lets a caller drop the wait when a newer request replaced this one (it then throws an AbortError).
 * The player card's patience (owner 2026-11-15): `signal` cancels the wait (the card closing), aborting the request in
 * flight and never asking again; `onSlow(round)` hears each round that ran out, before the next one asks. A round counts
 * as timed out by its own timer, never by the error's name, so a cancel is not mistaken for a slow server. After the last
 * round the request's AbortError is thrown, as before.
 */
export async function fetchPatient(url, { tries = SLOW_TRIES, current = () => true, signal = null, onSlow = null } = {}) {
  const outside = signal && typeof signal.addEventListener === "function" ? signal : null;
  for (let round = 1; ; round += 1) {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, FETCH_TIMEOUT_MS);
    const cancel = () => controller.abort();
    if (outside?.aborted) cancel();
    else if (outside) outside.addEventListener("abort", cancel, { once: true });
    try {
      return await fetchJson(url, controller.signal, { shared: round === 1 }); // batch 1: a later round asks anew, never joins the round that ran out
    } catch (error) {
      // the review (2026-11-16): a round that joined a shared request can run out on that request's own clock first
      // (TimeoutError); that is a round timed out too, and the next one asks anew
      const ranOut = timedOut || error?.name === "TimeoutError";
      if (!ranOut || round >= tries || !current() || outside?.aborted) throw error;
    } finally {
      clearTimeout(timer);
      if (outside) outside.removeEventListener("abort", cancel);
    }
    if (typeof onSlow === "function") {
      try {
        onSlow(round);
      } catch (error) {
        console.error(`The slow-answer note for ${url} failed.`, error); // the wait goes on: a note is never worth the answer
      }
    }
  }
}

/** "just now", "4 min ago", "2 h ago" for an age in seconds; null when unknown. */
export function agoText(seconds) {
  if (!isNum(seconds) || seconds < 0) return null;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  return `${Math.round(seconds / 3600)} h ago`;
}

/** "25 min old" for a kept copy's age in seconds (a minute at least). */
function minutesOld(age) {
  return `${isNum(age) ? Math.max(1, Math.round(age / 60)) : DASH} min old`;
}

/** The game a page is about, for the Data status card (ENH-4: its notes, scouting report and what is due). */
function aboutGame(envelope) {
  const game = envelope?.data?.game;
  const id = game && (isNum(game.gameId) || (typeof game.gameId === "string" && /^\d+$/.test(game.gameId))) ? String(game.gameId) : null;
  return { gameId: id, kickoff: typeof game?.kickoff === "string" ? game.kickoff : null };
}

/**
 * { kind, label, detail, dot, more } for the top-bar pill from an envelope. Phase 16 wave 3 (DS-12): fresh data is a quiet
 * "Updated 3 min ago" (not a green Current that says nothing); `detail` is the status card's sentence. ENH-4 (the owner's
 * board of 2026-10-27): `dot` is the server connection (ok, slow, down, off) and `more` the kept copy's age when there is
 * a problem; the shell adds how often the page's data is checked.
 */
export function statusFor(envelope) {
  const meta = envelope?.meta || {};
  const age = ageSeconds(meta.fetched_at);
  const ago = agoText(age);
  const about = aboutGame(envelope);
  const failed = Array.isArray(envelope?.errors) ? envelope.errors.filter((e) => e && e.code === "part_unavailable") : []; // a null entry must not read as Offline (freeze wave F1, F10)
  if (meta.stale) return { kind: "stale", dot: "down", label: "CFBD down", more: minutesOld(age), ...about, detail: `CFBD did not answer, so this page shows the server's last good copy${ago ? `, fetched ${ago}` : ""}. The server keeps asking CFBD; Refresh to see whether it is back.` };
  if (failed.length) return { kind: "stale", dot: "down", label: `${failed.length} part${failed.length > 1 ? "s" : ""} failed`, ...about, detail: `${failed.length === 1 ? "One part" : `${failed.length} parts`} of this page could not load and ${failed.length === 1 ? "says" : "say"} so where ${failed.length === 1 ? "it sits" : "they sit"}; the rest is current. Refresh asks again.` };
  // `updatedAt` lets the top bar keep the words true between refreshes ("just now" becomes "5 min ago").
  return { kind: "quiet", dot: "ok", label: ago ? `Updated ${ago}` : "Updated", updatedAt: isNum(age) ? Date.now() - age * 1000 : null, ...about, detail: "This page's data came fresh from the app's server when the page opened or was last refreshed. It refreshes when you open it or tap Refresh." };
}

/** The pill when the server is up but slower than FETCH_TIMEOUT_MS: never "Offline". */
export function slowStatus(last) {
  const age = ageSeconds(last?.meta?.fetched_at);
  if (!last) return { kind: "quiet", dot: "slow", label: "Still loading", detail: SLOW_DETAIL };
  return { kind: "stale", dot: "slow", label: "Slow", more: `showing ${minutesOld(age)}`, ...aboutGame(last), detail: "The server is taking longer than usual to refresh this page, so it shows the last copy it had. The app keeps trying." };
}

/** The pill when the server answered with an error (not offline: it answered). */
export function serverErrorStatus(last, message) {
  const detail = `The server answered with an error (${text(message)}). The app tries again on its own; the server's log has the details.`;
  return last ? { kind: "stale", dot: "down", label: "Server error", more: `showing ${minutesOld(ageSeconds(last?.meta?.fetched_at))}`, ...aboutGame(last), detail } : { kind: "stale", dot: "down", label: "Server error", detail };
}

export function offlineStatus(last) {
  const age = ageSeconds(last?.meta?.fetched_at);
  const detail = "This device could not reach the app's server. Check that the server computer is on and on the same Wi-Fi; the app keeps trying.";
  return last ? { kind: "offline", dot: "off", label: "Offline", more: minutesOld(age), ...aboutGame(last), detail } : { kind: "offline", dot: "off", label: "Offline", detail };
}

export function recordText(record) {
  if (!record || !isNum(record.wins) || !isNum(record.losses)) return DASH;
  return record.ties ? `${record.wins}-${record.losses}-${record.ties}` : `${record.wins}-${record.losses}`;
}

// The last good envelope of every url, for instant back (DS-03). Small: at most CACHE_LIMIT pages.
const CACHE_LIMIT = 24;
const kept = new Map();

// Post-freeze Wave 2 (ENH-1): the same copies in this tab's sessionStorage, which a tab Safari discarded keeps. One key a
// page and an index in order of use; a copy over STORE_ONE characters stays in memory only; the oldest go first past
// STORE_BUDGET or when the browser says the storage is full. A new build forgets them all: its pages may read differently.
const STORE_PREFIX = "kickoff.page:";
const STORE_INDEX = "kickoff.page-index";
const STORE_BUILD = "kickoff.page-build";
const STORE_ONE = 900_000;
const STORE_BUDGET = 3_000_000;

function store() {
  try {
    return globalThis.sessionStorage || null;
  } catch {
    return null; // storage refused: the copies stay in memory only
  }
}

function storedIndex(box) {
  try {
    const list = JSON.parse(box.getItem(STORE_INDEX) || "[]");
    return Array.isArray(list) ? list.filter((entry) => entry && typeof entry.url === "string" && Number.isFinite(entry.size)) : [];
  } catch {
    return [];
  }
}

function forgetStored(box) {
  for (const entry of storedIndex(box)) {
    try {
      box.removeItem(STORE_PREFIX + entry.url);
    } catch {
      // nothing to free
    }
  }
  try {
    box.removeItem(STORE_INDEX);
  } catch {
    // nothing to free
  }
}

let storeChecked = false;
function checkedStore() {
  const box = store();
  if (!box || storeChecked) return box;
  storeChecked = true;
  try {
    const build = pageBuild() || "plain";
    if (box.getItem(STORE_BUILD) !== build) {
      forgetStored(box);
      box.setItem(STORE_BUILD, build);
    }
  } catch {
    // a refused write: the copies may be from another build; the refresh behind each page corrects them
  }
  return box;
}

function persist(url, envelope, at) {
  const box = checkedStore();
  if (!box) return;
  let body = null;
  try {
    body = JSON.stringify({ envelope, at });
  } catch {
    return;
  }
  let index = storedIndex(box).filter((entry) => entry.url !== url);
  if (body.length > STORE_ONE) {
    try {
      box.removeItem(STORE_PREFIX + url);
      box.setItem(STORE_INDEX, JSON.stringify(index));
    } catch {
      // nothing to free
    }
    return;
  }
  index.push({ url, size: body.length });
  const drop = (entry) => {
    try {
      box.removeItem(STORE_PREFIX + entry.url);
    } catch {
      // nothing to free
    }
  };
  while (index.length > CACHE_LIMIT || index.reduce((sum, entry) => sum + entry.size, 0) > STORE_BUDGET) drop(index.shift());
  for (let tries = 0; tries < CACHE_LIMIT; tries += 1) {
    try {
      box.setItem(STORE_PREFIX + url, body);
      box.setItem(STORE_INDEX, JSON.stringify(index));
      return;
    } catch {
      // the storage is full: make room from the oldest and try again; with nothing older this copy stays in memory only
      if (index.length <= 1) break;
      drop(index.shift());
    }
  }
  try {
    box.removeItem(STORE_PREFIX + url);
    box.setItem(STORE_INDEX, JSON.stringify(index.filter((entry) => entry.url !== url)));
  } catch {
    // nothing more to do
  }
}

function restored(url) {
  const box = checkedStore();
  if (!box) return null;
  try {
    const raw = box.getItem(STORE_PREFIX + url);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (!saved || typeof saved !== "object" || !saved.envelope || typeof saved.envelope !== "object") return null;
    const copy = { envelope: saved.envelope, at: Number.isFinite(saved.at) ? saved.at : 0 };
    kept.set(url, copy);
    return copy;
  } catch {
    return null; // a damaged copy is no copy: the page loads as new
  }
}

function keep(url, envelope) {
  const at = Date.now();
  kept.delete(url);
  kept.set(url, { envelope, at });
  while (kept.size > CACHE_LIMIT) kept.delete(kept.keys().next().value);
  persist(url, envelope, at);
}

export function clearEnvelopeCache() {
  kept.clear();
  const box = store();
  if (box) forgetStored(box);
  storeChecked = false;
}

/** What makes two envelopes draw the same page: the fetch time, the stale flag, the data and the errors. */
function signature(envelope) {
  // batch 1 (owner 2026-11-15, "Every page in ~1.5 s"): the answer's data, never its time. A page opened again draws the copy
  // it kept, then the fresh answer, whose fetched_at is always new; that redrew the whole page and asked every band again
  // (21 more requests on My Team). The status pill still takes the new time (setStatus below).
  try {
    const meta = envelope?.meta || {};
    // and never a part's age (data.parts.*.ageSeconds grows every second), which the bands read only to say how old
    return JSON.stringify([meta.stale ?? null, envelope?.data ?? null, envelope?.errors ?? null], (key, value) => (key === "ageSeconds" ? undefined : value));
  } catch {
    return null; // an envelope that cannot be compared is always drawn
  }
}

/**
 * A polling view: fetches `url`, keeps the last good envelope, renders through `render(envelope)`
 * or `renderError(message)`, and reports status through `onStatus`. Returns { mount, refresh, unmount }.
 */
// No timed refresh unless live (owner 2026-11-14); while Claude Code loads data on the server a page keeps what it shows
// and the end of the run is a To do note (ui/run-bar.js), never a refresh.
export function poller({ url, live = false, refreshMs = 0, staleAfterMs = 5 * 60 * 1000, onStatus, render, renderError, renderLoading, loadingDetail = null }) {
  let container = null;
  let last = null;
  let lastAt = 0;
  let timer = null;
  let inFlight = null;
  let drawn = null; // the signature of what the page shows now; null when it shows a skeleton or an error
  let slowTries = 0; // rounds in a row that timed out before the first answer
  let controller = null; // the request in flight, aborted on unmount (freeze wave F1, F2: a dead view wrote the pill under the next one)
  let mounted = 0; // counts up on every mount; an answer from an earlier mount is dropped
  const setStatus = (status) => {
    if (container && typeof onStatus === "function") onStatus(status);
  };

  function draw(envelope) {
    if (!container) return;
    const sig = signature(envelope);
    if (sig !== null && sig === drawn) return; // same data: no rebuild, nothing moves under the reader
    const where = drawn !== null ? scrollState(container, { page: true }) : null;
    try {
      render(envelope, container);
      drawn = sig;
    } catch (error) {
      drawn = null;
      console.error(`Could not draw ${url}.`, error);
      renderError(`The page could not be drawn (${error?.message || "unknown error"})`, container, refresh);
      return;
    }
    if (where) restoreScroll(container, where);
    try {
      document.dispatchEvent(new CustomEvent("kickoff:rendered", { detail: { url } }));
    } catch {
      // no event support: nothing listens anyway
    }
  }

  async function refresh() {
    if (inFlight) return inFlight;
    const ctl = new AbortController();
    controller = ctl;
    const mine = mounted;
    const timeout = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
    if (!last && !slowTries) setStatus({ kind: "quiet", label: "Loading" }); // an ask-again keeps saying Still loading
    inFlight = (async () => {
      try {
        const envelope = await fetchJson(url, ctl.signal, { fresh: true }); // batch 1: the page's own load and Refresh ask fresh
        if (mine !== mounted) return; // the view was replaced meanwhile: nothing to draw, nothing to say
        slowTries = 0;
        last = envelope;
        lastAt = Date.now();
        keep(url, envelope);
        draw(envelope);
        setStatus(statusFor(envelope));
      } catch (error) {
        if (mine !== mounted) return; // aborted by unmount, or answered after it
        const timedOut = error?.name === "AbortError";
        const answered = isNum(error?.status); // the server sent an HTTP error: it is up
        if (timedOut && !last && container && slowTries < SLOW_TRIES) {
          // Still gathering: keep the loading screen, say so, and ask again at once.
          slowTries += 1;
          const detail = container.querySelector?.(".loading-sun__detail");
          if (detail) detail.textContent = SLOW_DETAIL;
          else container.querySelector?.(".loading-sun__words")?.append(el("p", { class: "loading-sun__detail" }, SLOW_DETAIL));
          setStatus(slowStatus(null));
          setTimeout(() => {
            if (container) refresh();
          }, 0);
          return;
        }
        const message = timedOut ? `The server did not answer in ${Math.round((FETCH_TIMEOUT_MS * (slowTries + 1)) / 1000)} s` : error?.message || "Request failed";
        slowTries = 0;
        if (last) {
          draw(last);
        } else if (container) {
          drawn = null;
          renderError(message, container, refresh);
        }
        setStatus(timedOut ? (last ? slowStatus(last) : { kind: "stale", label: "Server slow", detail: "The server has not finished gathering this page. Try now, or open the server status page; its log says what it is waiting on." }) : answered ? serverErrorStatus(last, message) : offlineStatus(last));
      } finally {
        clearTimeout(timeout);
        if (mine === mounted) {
          inFlight = null;
          controller = null;
        }
      }
    })();
    return inFlight;
  }

  function onVisible() {
    if (document.visibilityState === "visible" && Date.now() - lastAt > (live ? staleAfterMs : RETURN_REFRESH_MS)) refresh();
  }

  return {
    mount(target) {
      container = target;
      drawn = null;
      mounted += 1;
      inFlight = null;
      const cached = kept.get(url) || restored(url);
      if (cached) {
        // Instant back (BUG-18: whatever its age): the page as it was, then a quiet refresh that rebuilds only if something
        // changed. The status pill says how old the copy is until the refresh lands.
        last = cached.envelope;
        lastAt = cached.at;
        draw(cached.envelope);
        setStatus(statusFor(cached.envelope));
      } else {
        container.replaceChildren(loadingSun({ detail: loadingDetail }), renderLoading()); // Phase 17 #1: the sun above the outlines
      }
      refresh(); // the page opened: always asked
      if (live && isNum(refreshMs) && refreshMs > 0) timer = setInterval(() => refresh(), refreshMs);
      document.addEventListener("visibilitychange", onVisible);
    },
    refresh,
    unmount() {
      if (timer) clearInterval(timer);
      timer = null;
      document.removeEventListener("visibilitychange", onVisible);
      container = null;
      drawn = null;
      mounted += 1; // an answer still in flight belongs to the old mount and is dropped
      if (controller) controller.abort();
      controller = null;
      inFlight = null;
    },
    get last() {
      return last;
    },
  };
}

/** One full-width band in its error state (DS-06, bug 9): what failed and 'Try now' inside (no timer asks again since
 *  2026-11-14: Try now, Refresh or opening the page again does). */
export function errorPanel(title, message, retry) {
  const name = text(title);
  const reason = text(message);
  return el(
    "div",
    { class: "page" },
    band({
      title: name,
      collapsible: false,
      state: { status: "ready" },
      body: () =>
        el(
          "div",
          {},
          stateBlock({
            kind: "error",
            lead: `Could not load ${name === DASH ? "this page" : name}.`,
            detail: `${reason}${/[.!?]$/.test(reason) ? "" : "."} ${typeof retry === "function" ? "Try now, or tap Refresh" : "Tap Refresh"} beside the status pill.`,
            action: typeof retry === "function" ? { label: "Try now", onClick: () => retry() } : null,
          }),
          // like a crash reporter (owner 2026-10-23): the report form, the error already in it
          el("p", { class: "error-report" }, el("button", { type: "button", class: "btn btn--quiet", onclick: () => openFeedback({ kind: "bug", text: `The ${name === DASH ? "page" : name} page could not load: ${reason}` }) }, "Send a report")),
        ),
    }),
  );
}
