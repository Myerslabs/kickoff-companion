// The loading bar (owner 2026-10-16: "for Claude Code, it runs silently in the background. No refreshes until ALL data is
// loaded. Until then just save in the background... There should also be a loading bar"). While Claude Code loads data on
// the server (the one run of every prompt, a season run, or this week's notes), a slim bar sits above every page with what
// it is on and how far along. The pages hold their timed refreshes meanwhile (views/common.js, poller) and refresh once,
// together, when every run has ended. Never on the board, never printed.
//
//   installRunBar(slot)  the bar, placed before `slot` (the shell's .page-notes); asks the server now, every minute while
//                        nothing runs, every 5 s while a run goes, and again whenever the page comes back into view
//   watchRun()           ask now and follow closely: a page that has just started a run calls it
//   dataRunActive()      true while a run goes (the pollers hold their redraws)
//   onRunProgress(fn)    fn(progress) on every answer from the server; returns the function that stops it
//   runBarView(progress) the bar's contents for one answer (exported for the tests and the design system)
//
// When the last run ends, document gets "kickoff:data-loaded" (detail: the answer), once. A run that started and ended
// between two idle checks still counts: the answer's lastFinishedAt moved.

import { el, fmtTime, isNum, str, text } from "./dom.js";

const IDLE_MS = 60000;
const BUSY_MS = 5000;
const DONE_SHOWN_MS = 5000;

let active = false;
let lastFinished; // undefined until the first answer: a page that opens after a run ended does not refresh for it
let timer = null;
let host = null;
let doneTimer = null;
let asking = null;
const listeners = new Set();

export function dataRunActive() {
  return active;
}

export function onRunProgress(fn) {
  if (typeof fn !== "function") return () => {};
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** "3 min", "1 h 5 min", or "" when the start is unknown. */
function elapsed(iso, now = Date.now()) {
  const at = Date.parse(String(iso ?? ""));
  if (!Number.isFinite(at)) return "";
  const minutes = Math.max(0, Math.floor((now - at) / 60000));
  if (minutes < 1) return "under a minute";
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

/** The bar for one answer: a title, what it is on, the track (a fraction, or moving when there is none). */
export function runBarView(progress, { now = Date.now() } = {}) {
  const p = progress && typeof progress === "object" ? progress : {};
  const fraction = isNum(p.fraction) ? Math.max(0, Math.min(1, p.fraction)) : null;
  const what = [str(p.label) ? p.label.trim() : null, str(p.detail) ? p.detail.trim() : null].filter(Boolean).join(", ");
  const since = elapsed(p.startedAt, now);
  const track = el(
    "div",
    {
      class: `run-bar__track${fraction === null ? " run-bar__track--moving" : ""}`,
      role: "progressbar",
      "aria-label": "Loading data",
      "aria-valuemin": "0",
      "aria-valuemax": "100",
      "aria-valuenow": fraction === null ? null : String(Math.round(fraction * 100)),
    },
    el("div", { class: "run-bar__fill", style: fraction === null ? null : `width: ${Math.max(3, Math.round(fraction * 100))}%` }),
  );
  return [
    el(
      "div",
      { class: "run-bar__row" },
      el("span", { class: "run-bar__title" }, "Loading data with Claude Code"),
      what ? el("span", { class: "run-bar__what" }, text(what)) : null,
      el("span", { class: "run-bar__when" }, [fraction === null ? null : `${Math.round(fraction * 100)}%`, since ? `running ${since}` : null].filter(Boolean).join(" · ")),
    ),
    track,
    el("p", { class: "run-bar__note" }, "It saves in the background. The page refreshes once, when everything is in."),
  ];
}

function doneView(progress) {
  const finished = str(progress?.lastFinishedAt) ? fmtTime(progress.lastFinishedAt) : null;
  return [
    el("div", { class: "run-bar__row" }, el("span", { class: "run-bar__title" }, "Data loaded"), finished && finished !== "–" ? el("span", { class: "run-bar__when" }, `finished ${finished}`) : null),
    el("div", { class: "run-bar__track", role: "progressbar", "aria-label": "Loading data", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "100" }, el("div", { class: "run-bar__fill", style: "width: 100%" })),
  ];
}

function draw(progress, ended) {
  if (!host) return;
  clearTimeout(doneTimer);
  if (progress?.running === true) {
    host.replaceChildren(...runBarView(progress));
    host.hidden = false;
    host.classList.remove("run-bar--done");
    return;
  }
  if (ended && !host.hidden) {
    host.replaceChildren(...doneView(progress));
    host.classList.add("run-bar--done");
    doneTimer = setTimeout(() => {
      host.hidden = true;
      host.classList.remove("run-bar--done");
    }, DONE_SHOWN_MS);
    return;
  }
  if (!ended) host.hidden = true;
}

function later(ms) {
  clearTimeout(timer);
  timer = setTimeout(ask, ms);
}

async function ask() {
  if (asking) return asking;
  if (typeof document !== "undefined" && document.visibilityState === "hidden") {
    later(active ? BUSY_MS : IDLE_MS); // nobody is looking: no question until the page is back (visibilitychange asks)
    return null;
  }
  asking = (async () => {
    let data = null;
    try {
      const response = await fetch("/api/prompts/progress", { cache: "no-store" });
      if (!response.ok) throw new Error(`The server answered ${response.status}`);
      const envelope = await response.json();
      data = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
    } catch (error) {
      console.warn("Could not read how far the data load is.", error?.message || error);
    }
    if (data === null) {
      later(active ? BUSY_MS : IDLE_MS);
      return null;
    }
    const running = data.running === true;
    const finished = str(data.lastFinishedAt) ? data.lastFinishedAt : null;
    const ended = !running && (active || (lastFinished !== undefined && finished !== null && finished !== lastFinished));
    active = running;
    lastFinished = finished;
    draw(data, ended);
    for (const fn of listeners) {
      try {
        fn(data);
      } catch (error) {
        console.warn("A loading-bar listener failed.", error?.message || error);
      }
    }
    if (ended) {
      try {
        document.dispatchEvent(new CustomEvent("kickoff:data-loaded", { detail: data }));
      } catch (error) {
        console.warn("Could not announce the finished data load.", error?.message || error);
      }
    }
    later(running ? BUSY_MS : IDLE_MS);
    return data;
  })();
  try {
    return await asking;
  } finally {
    asking = null;
  }
}

export function watchRun() {
  later(0);
  // a run takes a moment to start on the server: ask again soon, so the bar shows even when the first answer was early
  setTimeout(() => {
    if (!active) ask();
  }, 1500);
}

export function installRunBar(slot) {
  if (host || typeof document === "undefined") return host;
  host = el("div", { class: "run-bar", role: "status", "aria-live": "polite", hidden: true });
  if (slot && slot.parentNode) slot.parentNode.insertBefore(host, slot);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") later(0);
  });
  later(0);
  return host;
}
