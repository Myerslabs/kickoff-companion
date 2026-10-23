// What this tablet did lately (owner 2026-10-23: "I want to be able to see what was done when feedback was submitted"):
// a short trail of the pages opened, the buttons and links tapped (by their label, never what was typed), the sheets
// opened and the errors, kept for fifteen minutes in this tab (sessionStorage, so a reload keeps it). Send feedback
// (ui/feedback.js) sends it with the report; nothing else reads it and it never leaves the house.
//
//   startTrail()            once at boot: the page changes and the taps from then on
//   note(kind, what)        one step: "page", "tap", "sheet", "error" or "note"
//   trailSteps()            the steps of the last fifteen minutes, oldest first, for the report
//   labelOf(element)        what a tap on this element is called (exported for the tests)

const KEY = "kickoff.trail";
const KEEP_MS = 15 * 60 * 1000;
const MAX = 300;
const TAPPABLE = 'button, a, [role="button"], [role="tab"], [role="option"], summary, select, input[type="checkbox"], input[type="radio"], label';

let steps = null;
let started = false;

function now() {
  return Date.now();
}

function here() {
  const where = typeof window !== "undefined" && window.location ? window.location.hash : "";
  return typeof where === "string" && where ? where : "#";
}

function load() {
  if (steps) return steps;
  steps = [];
  try {
    const raw = typeof sessionStorage !== "undefined" ? JSON.parse(sessionStorage.getItem(KEY) || "[]") : [];
    if (Array.isArray(raw)) steps = raw.filter((s) => s && typeof s === "object" && typeof s.at === "string" && typeof s.kind === "string");
  } catch {
    steps = []; // blocked or damaged storage: the trail starts here
  }
  return steps;
}

function keep() {
  const cutoff = now() - KEEP_MS;
  steps = load().filter((s) => Date.parse(s.at) >= cutoff).slice(-MAX);
  try {
    if (typeof sessionStorage !== "undefined") sessionStorage.setItem(KEY, JSON.stringify(steps));
  } catch {
    // full or blocked storage: the trail lives in memory for this page
  }
}

function clip(value, size) {
  const words = typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
  return words.length > size ? `${words.slice(0, size - 1)}…` : words;
}

export function note(kind, what) {
  load().push({ at: new Date(now()).toISOString(), kind: ["page", "tap", "sheet", "error", "note"].includes(kind) ? kind : "note", what: clip(String(what ?? ""), 300), route: clip(here(), 200) });
  keep();
}

export function trailSteps() {
  keep();
  return load().map((s) => ({ ...s }));
}

/** A tap's name: the element's own label, its words, or its address; a field's name, never what was typed in it. */
export function labelOf(element) {
  if (!element || typeof element.getAttribute !== "function") return "";
  const tag = String(element.tagName || "").toLowerCase();
  const named = element.getAttribute("aria-label") || element.getAttribute("title");
  if (named) return clip(named, 80);
  if (tag === "select") return clip(element.getAttribute("name") || "a list", 80);
  if (tag === "input") return clip(`${element.getAttribute("aria-label") || element.getAttribute("name") || "a switch"} ${element.checked ? "on" : "off"}`, 80);
  const title = typeof element.querySelector === "function" ? element.querySelector("b, strong") : null; // a two-line row: its title
  const words = clip((title && title.textContent) || element.textContent || "", 80);
  if (words) return words;
  const href = tag === "a" ? element.getAttribute("href") : null;
  return href ? clip(href, 80) : tag || "something";
}

export function startTrail() {
  if (started || typeof window === "undefined" || typeof document === "undefined") return;
  started = true;
  note("page", here());
  window.addEventListener("hashchange", () => note("page", here()));
  document.addEventListener(
    "click",
    (event) => {
      const target = event.target && typeof event.target.closest === "function" ? event.target.closest(TAPPABLE) : null;
      if (!target) return;
      if (target.closest(".feedback-form")) return; // the report's own form is not part of what happened
      note("tap", labelOf(target));
    },
    true,
  );
}
