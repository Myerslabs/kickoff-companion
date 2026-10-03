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

import { noteBuild } from "../build.js";
import { pollMs } from "../prefs.js";
import { DASH, el, isNum, restoreScroll, scrollState, text } from "../ui/dom.js";
import { band, stateBlock } from "../ui/states.js";

export const FETCH_TIMEOUT_MS = 20000;

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

export async function fetchJson(url, signal) {
  const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (body && typeof body === "object") noteBuild(body.meta?.build); // Phase 12: the tablet learns of a new build
  if (!response.ok || !body || typeof body !== "object") {
    const message = body?.errors?.[0]?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

/** { kind, label } for the top-bar pill from an envelope. */
export function statusFor(envelope) {
  const meta = envelope?.meta || {};
  const age = ageSeconds(meta.fetched_at);
  const failed = Array.isArray(envelope?.errors) ? envelope.errors.filter((e) => e.code === "part_unavailable") : [];
  if (meta.stale) return { kind: "stale", label: `Stale ${isNum(age) ? Math.max(1, Math.round(age / 60)) : DASH} min` };
  if (failed.length) return { kind: "stale", label: `${failed.length} part${failed.length > 1 ? "s" : ""} failed` };
  return { kind: "live", label: "Current" };
}

export function offlineStatus(last) {
  const age = ageSeconds(last?.meta?.fetched_at);
  return last ? { kind: "offline", label: `Offline, showing ${isNum(age) ? Math.max(1, Math.round(age / 60)) : DASH} min old` } : { kind: "offline", label: "Offline" };
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
export function poller({ url, refreshMs, staleAfterMs = 5 * 60 * 1000, onStatus, render, renderError, renderLoading }) {
  let container = null;
  let last = null;
  let lastAt = 0;
  let timer = null;
  let inFlight = null;
  let drawn = null; // the signature of what the page shows now; null when it shows a skeleton or an error
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
    if (!last) setStatus({ kind: "quiet", label: "Loading" });
    inFlight = (async () => {
      try {
        const envelope = await fetchJson(url, controller.signal);
        last = envelope;
        lastAt = Date.now();
        keep(url, envelope);
        draw(envelope);
        setStatus(statusFor(envelope));
      } catch (error) {
        const message = error?.name === "AbortError" ? "The server did not answer in 20 s" : error?.message || "Request failed";
        if (last) {
          draw(last);
        } else if (container) {
          drawn = null;
          renderError(message, container, refresh);
        }
        setStatus(offlineStatus(last));
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
        container.replaceChildren(renderLoading());
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
