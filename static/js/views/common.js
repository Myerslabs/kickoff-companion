// Helpers shared by the views: envelope fetching with a timeout, part status to band state,
// the status-pill text for an envelope, and a small polling controller.
//
// Phase 16 (stream F) frozen API:
//   poller({ url, refreshMs, staleAfterMs, onStatus, render, renderError, renderLoading }) -> { mount, refresh, unmount, last }
//       Instant back: the last good envelope of every url is kept for the page's lifetime; a view mounted again
//       within refreshMs draws it at once (no skeleton) and refreshes in the background. A fetch that brings
//       the same fetched_at and the same data does not rebuild the page. A rebuild keeps the page's scroll and
//       every table's scroll. After each draw the document hears "kickoff:rendered" (detail { url }).
//       refresh() returns a promise (pull to refresh waits on it).
//   clearEnvelopeCache()  forget the kept envelopes (tests).
//   errorPanel(title, message, retry)  one full-width band in its error state: what failed, when the app
//       tries again, and a quiet 'Try now' inside the band.

import { noteBuild, noteRestart } from "../build.js";
import { pollMs } from "../prefs.js";
import { DASH, el, isNum, restoreScroll, scrollState, text } from "../ui/dom.js";
import { band, loadingSun, stateBlock } from "../ui/states.js";

export const FETCH_TIMEOUT_MS = 20000;
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
  return { signal: controller.signal, clear: () => clearTimeout(timer) };
}

export async function fetchJson(url, signal) {
  // Final pass (CLAUDE.md rule 4): no request waits for ever. A caller's own signal rules; without one the request
  // gives up after FETCH_TIMEOUT_MS, so a dead server shows as an error instead of a page that never settles.
  const own = signal ? null : timeoutSignal();
  let response;
  try {
    response = await fetch(url, { signal: signal || own.signal, headers: { Accept: "application/json" } });
  } finally {
    if (own) own.clear();
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (body && typeof body === "object") {
    noteBuild(body.meta?.build); // Phase 12: the tablet learns of a new build
    noteRestart(body.meta?.restartNeeded); // Phase 16 wave 3: the server's code changed; a restart brings it in
  }
  if (!response.ok || !body || typeof body !== "object") {
    const message = body?.errors?.[0]?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

/**
 * One request that waits like a page does (Phase 18.2): a sheet or panel that opens on a cold server gets the same
 * patience as a page, asking again after each FETCH_TIMEOUT_MS round, up to `tries` rounds, instead of giving up at 20 s.
 * `current()` lets a caller drop the wait when a newer request replaced this one (it then throws an AbortError).
 */
export async function fetchPatient(url, { tries = SLOW_TRIES, current = () => true } = {}) {
  for (let round = 1; ; round += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      return await fetchJson(url, controller.signal);
    } catch (error) {
      const timedOut = error?.name === "AbortError";
      if (!timedOut || round >= tries || !current()) throw error;
    } finally {
      clearTimeout(timer);
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

/**
 * { kind, label, detail } for the top-bar pill from an envelope. Phase 16 wave 3 (DS-12): fresh data is a quiet
 * "Updated 3 min ago" (not a green Current that says nothing); `detail` is the status card's sentence.
 */
export function statusFor(envelope) {
  const meta = envelope?.meta || {};
  const age = ageSeconds(meta.fetched_at);
  const ago = agoText(age);
  const failed = Array.isArray(envelope?.errors) ? envelope.errors.filter((e) => e.code === "part_unavailable") : [];
  if (meta.stale) return { kind: "stale", label: `Stale ${isNum(age) ? Math.max(1, Math.round(age / 60)) : DASH} min`, detail: `CFBD did not answer, so this page shows the server's last good copy${ago ? `, fetched ${ago}` : ""}. The app tries again on its own.` };
  if (failed.length) return { kind: "stale", label: `${failed.length} part${failed.length > 1 ? "s" : ""} failed`, detail: `${failed.length === 1 ? "One part" : `${failed.length} parts`} of this page could not load and ${failed.length === 1 ? "says" : "say"} so where ${failed.length === 1 ? "it sits" : "they sit"}; the rest is current. The app tries again on its own.` };
  // `updatedAt` lets the top bar keep the words true between refreshes ("just now" becomes "5 min ago").
  return { kind: "quiet", label: ago ? `Updated ${ago}` : "Updated", updatedAt: isNum(age) ? Date.now() - age * 1000 : null, detail: "This page's data came fresh from the app's server on the last refresh. It refreshes on its own." };
}

/** The pill when the server is up but slower than FETCH_TIMEOUT_MS: never "Offline". */
export function slowStatus(last) {
  const age = ageSeconds(last?.meta?.fetched_at);
  if (!last) return { kind: "quiet", label: "Still loading", detail: SLOW_DETAIL };
  return { kind: "stale", label: `Slow, showing ${isNum(age) ? Math.max(1, Math.round(age / 60)) : DASH} min old`, detail: "The server is taking longer than usual to refresh this page, so it shows the last copy it had. The app keeps trying." };
}

/** The pill when the server answered with an error (not offline: it answered). */
export function serverErrorStatus(last, message) {
  const detail = `The server answered with an error (${text(message)}). The app tries again on its own; the server's log has the details.`;
  return last ? { kind: "stale", label: "Server error, showing last copy", detail } : { kind: "stale", label: "Server error", detail };
}

export function offlineStatus(last) {
  const age = ageSeconds(last?.meta?.fetched_at);
  const detail = "This device could not reach the app's server. Check that the server computer is on and on the same Wi-Fi; the app keeps trying.";
  return last ? { kind: "offline", label: `Offline, showing ${isNum(age) ? Math.max(1, Math.round(age / 60)) : DASH} min old`, detail } : { kind: "offline", label: "Offline", detail };
}

export function recordText(record) {
  if (!record || !isNum(record.wins) || !isNum(record.losses)) return DASH;
  return record.ties ? `${record.wins}-${record.losses}-${record.ties}` : `${record.wins}-${record.losses}`;
}

// The last good envelope of every url, for instant back (DS-03). Small: at most CACHE_LIMIT pages.
const CACHE_LIMIT = 24;
const kept = new Map();

function keep(url, envelope) {
  kept.delete(url);
  kept.set(url, { envelope, at: Date.now() });
  while (kept.size > CACHE_LIMIT) kept.delete(kept.keys().next().value);
}

export function clearEnvelopeCache() {
  kept.clear();
}

/** What makes two envelopes draw the same page: the fetch time, the stale flag, the data and the errors. */
function signature(envelope) {
  try {
    const meta = envelope?.meta || {};
    return JSON.stringify([meta.fetched_at ?? null, meta.stale ?? null, envelope?.data ?? null, envelope?.errors ?? null]);
  } catch {
    return null; // an envelope that cannot be compared is always drawn
  }
}

/**
 * A polling view: fetches `url`, keeps the last good envelope, renders through `render(envelope)`
 * or `renderError(message)`, and reports status through `onStatus`. Returns { mount, refresh, unmount }.
 */
export function poller({ url, refreshMs, staleAfterMs = 5 * 60 * 1000, onStatus, render, renderError, renderLoading, loadingDetail = null }) {
  let container = null;
  let last = null;
  let lastAt = 0;
  let timer = null;
  let inFlight = null;
  let drawn = null; // the signature of what the page shows now; null when it shows a skeleton or an error
  let slowTries = 0; // rounds in a row that timed out before the first answer
  const setStatus = (status) => {
    if (typeof onStatus === "function") onStatus(status);
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
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    if (!last && !slowTries) setStatus({ kind: "quiet", label: "Loading" }); // an ask-again keeps saying Still loading
    inFlight = (async () => {
      try {
        const envelope = await fetchJson(url, controller.signal);
        slowTries = 0;
        last = envelope;
        lastAt = Date.now();
        keep(url, envelope);
        draw(envelope);
        setStatus(statusFor(envelope));
      } catch (error) {
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
        inFlight = null;
      }
    })();
    return inFlight;
  }

  function onVisible() {
    if (document.visibilityState === "visible" && Date.now() - lastAt > staleAfterMs) refresh();
  }

  return {
    mount(target) {
      container = target;
      drawn = null;
      const cached = kept.get(url);
      const fresh = cached && isNum(refreshMs) && Date.now() - cached.at < refreshMs;
      if (fresh) {
        // Instant back: the page as it was, then a quiet refresh that rebuilds only if something changed.
        last = cached.envelope;
        lastAt = cached.at;
        draw(cached.envelope);
        setStatus(statusFor(cached.envelope));
      } else {
        container.replaceChildren(loadingSun({ detail: loadingDetail }), renderLoading()); // Phase 17 #1: the sun above the outlines
      }
      refresh();
      timer = setInterval(refresh, refreshMs);
      document.addEventListener("visibilitychange", onVisible);
    },
    refresh,
    unmount() {
      if (timer) clearInterval(timer);
      timer = null;
      document.removeEventListener("visibilitychange", onVisible);
      container = null;
      drawn = null;
    },
    get last() {
      return last;
    },
  };
}

/** One full-width band in its error state (DS-06, bug 9): what failed, when the app tries again, 'Try now' inside. */
export function errorPanel(title, message, retry) {
  const name = text(title);
  const reason = text(message);
  let minutes = 15;
  try {
    minutes = Math.max(1, Math.round(pollMs() / 60000));
  } catch {
    minutes = 15;
  }
  return el(
    "div",
    { class: "page" },
    band({
      title: name,
      collapsible: false,
      state: { status: "ready" },
      body: () =>
        stateBlock({
          kind: "error",
          lead: `Could not load ${name === DASH ? "this page" : name}.`,
          detail: `${reason}${/[.!?]$/.test(reason) ? "" : "."} The app tries again every ${minutes} min.`,
          action: typeof retry === "function" ? { label: "Try now", onClick: () => retry() } : null,
        }),
    }),
  );
}
