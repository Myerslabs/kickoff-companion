// Stat hints (owner request 2026-09-26): tap a stat's name anywhere in the app for what it means.
// One observer marks every label cell whose text matches a glossary alias, and one click handler on the
// document opens a small card beside it. Final pass (owner 2026-10-09): the mark is a small question mark after
// the term (the dotted underline is gone); the question mark opens the card, and the term itself goes to the
// term's national list when the glossary knows one (a tap on "Yards per play" opens every team's number). No view builds hints
// itself, so every table, sheet and flyout gets them, including ones added later. Sortable
// column headers keep their tap for sorting; on a desktop they show the definition on hover.
// The Settings switch "Stat hints" adds .hints-off to <html>, which hides the marks and the card.
// Phase 16 wave 3 (DS-11): a sortable header also opens its card on a long press (the sort is cancelled) and on
// Shift+Enter; a key-play badge's label opens its own entry.

import { GLOSSARY } from "../glossary-data.js";
import { el, text } from "./dom.js";
import { nationalHref } from "./national-link.js";

const LABELS = "td.txt:first-child, th[scope=row], thead th, .sit__label, .success__source, .verdict, .hint-term, .kp"; // .hint-term: a term inside a sentence (Phase 17); .kp: a key-play badge (Phase 16 wave 3)
// the Success / Failed verdict explains the success rule; an edges row's label names two units, so it opens Edges
// a lineup's slot labels (EDGE, STAR, JACK, PK) are positions, not stats: they open the Depth chart entry
const BY_CLASS = [[".verdict", "success-rate"], [".tt--edges td.tt__label", "edges"], [".tape td.tape__label", "edges"], [".tape th.tape__pair", "edges"], [".lineup td.txt:first-child", "depth-chart"], [".tt__ladder", "percentile"], [".grade-parts thead th:last-child", "percentile"]]; // Phase 17: the ladder head and the grade parts' percentile head
const GAP = 6;
const EDGE = 8;
const LONG_PRESS_MS = 450;
const PRESS_SLOP = 10; // a finger that moves this far is scrolling, not pressing

const index = new Map();
for (const entry of Array.isArray(GLOSSARY) ? GLOSSARY : []) {
  if (!entry || typeof entry.id !== "string") continue;
  for (const name of [entry.term, ...(Array.isArray(entry.aliases) ? entry.aliases : [])]) {
    const key = normalize(name);
    if (key && !index.has(key)) index.set(key, entry);
  }
}
const byId = new Map([...index.values()].map((entry) => [entry.id, entry]));

let card = null;
let cardFor = null;
let enabled = false;
let press = null; // { button, timer, x, y } while a finger is down on a sortable header
let swallow = null; // the header whose long press opened a card: its click must not sort

function normalize(value) {
  return String(value ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[:.]$/, "")
    .toLowerCase();
}

function hintsOff() {
  return document.documentElement.classList.contains("hints-off");
}

/** The label's own words: its text nodes, so a cell's small sub-line (a position, a note) does not spoil the match. */
function ownText(node) {
  const own = [...node.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent).join("");
  return own.trim() ? own : node.textContent;
}

/** Teach the index labels that depend on the team (the conference's short name, "SWT rank"): each
    name opens the entry with that id. Names already taken stay with their entry. */
export function addAliases(id, names) {
  const entry = byId.get(id);
  if (!entry) return;
  for (const name of Array.isArray(names) ? names : []) {
    const key = normalize(name);
    if (key && !index.has(key)) index.set(key, entry);
  }
}

/** The glossary entry for a label, or null. */
export function hintFor(label) {
  const key = normalize(label);
  const found = index.get(key);
  if (found) return found;
  // final pass: every rank column is headed "<population> rank"; a conference or poll name the glossary cannot
  // list (another team's conference on its page, a conference-scope list) opens the ranks entry
  return /\srank$/.test(key) ? byId.get("national-conference-rank") || null : null;
}

function entryFor(node) {
  for (const [selector, id] of BY_CLASS) if (node.matches(selector) && byId.has(id)) return byId.get(id);
  return hintFor(ownText(node));
}

function mark(node) {
  if (node.dataset.hint || node.closest(".hint-pop, .gloss")) return;
  const entry = entryFor(node);
  if (!entry) return;
  const sortButton = node.tagName === "TH" ? node.querySelector("button") : null;
  if (sortButton) {
    sortButton.title = `${entry.term}: ${entry.text}`; // the tap sorts; a mouse can still read the meaning
    sortButton.dataset.hintSort = entry.id; // a long press or Shift+Enter opens the card (DS-11)
    sortButton.append(questionMark(entry)); // inside the sort control, so the header stays one unit; the mark's own tap never sorts
    return;
  }
  node.dataset.hint = entry.id;
  if (!node.hasAttribute("tabindex")) node.tabIndex = 0;
  node.append(questionMark(entry));
}

/** The small "?" after a term: it opens the card; the term itself goes to the term's list. */
function questionMark(entry) {
  // a span, not a button: it also sits inside sortable headers' buttons, where a nested button is not allowed
  return el("span", { class: "hint__q", role: "button", "aria-label": `What ${entry.term} means` }, "?");
}

/** Where a term's data lives: its national list, when the glossary names a metric for it. */
function listFor(entry) {
  try {
    return typeof entry?.metric === "string" && entry.metric ? nationalHref(entry.metric) : null;
  } catch {
    return null;
  }
}

function scan(root) {
  if (!(root instanceof Element)) return;
  if (root.matches(LABELS)) mark(root);
  for (const node of root.querySelectorAll(LABELS)) mark(node);
}

function close() {
  if (card) card.remove();
  card = null;
  cardFor = null;
}

function place(target) {
  const rect = target.getBoundingClientRect();
  const width = card.offsetWidth;
  const height = card.offsetHeight;
  const left = Math.max(EDGE, Math.min(rect.left, window.innerWidth - width - EDGE));
  const below = rect.bottom + GAP;
  const top = below + height <= window.innerHeight - EDGE || rect.top - GAP - height < EDGE ? below : rect.top - GAP - height;
  card.style.left = `${Math.round(left)}px`;
  card.style.top = `${Math.round(Math.max(EDGE, top))}px`;
}

function open(target) {
  const entry = byId.get(target.dataset.hint || target.dataset.hintSort);
  if (!entry) return;
  close();
  card = el(
    "div",
    { class: "hint-pop", role: "dialog", "aria-label": text(entry.term) },
    el("b", { class: "hint-pop__term" }, text(entry.term)),
    el("p", {}, text(entry.text)),
    entry.read ? el("p", { class: "hint-pop__read" }, text(entry.read)) : null,
    el("div", { class: "hint-pop__foot" }, el("span", {}, entry.source === "App" ? "The app's own rule" : "Definition from CFBD"), el("a", { href: `#glossary=${encodeURIComponent(entry.id)}` }, "All terms")),
  );
  document.body.append(card);
  cardFor = target;
  place(target);
}

/** The card's label was redrawn: stay open on the new copy of the same label, or close when it is gone. */
function follow() {
  const id = cardFor.dataset.hint || cardFor.dataset.hintSort;
  const words = normalize(ownText(cardFor));
  const again = [...document.querySelectorAll("[data-hint], [data-hint-sort]")].find((node) => (node.dataset.hint || node.dataset.hintSort) === id && normalize(ownText(node)) === words && !node.closest(".hint-pop"));
  if (!again) {
    close();
    return;
  }
  cardFor = again;
  place(again);
}

function onClick(event) {
  if (swallow && event.target instanceof Element && event.target.closest("[data-hint-sort]") === swallow) {
    swallow = null;
    event.preventDefault();
    event.stopPropagation(); // the long press showed the meaning; the lifted finger does not sort
    return;
  }
  swallow = null;
  if (card && card.contains(event.target)) {
    if (event.target.closest("a")) close(); // the Glossary link navigates; the card goes with it
    return;
  }
  const q = !hintsOff() && event.target instanceof Element ? event.target.closest(".hint__q") : null;
  if (q) {
    // the question mark: the card, for a term or for a sortable header
    const owner = q.closest("[data-hint]") || q.closest("th")?.querySelector("[data-hint-sort]");
    event.preventDefault();
    event.stopPropagation();
    if (!owner) return;
    if (cardFor === owner) close();
    else open(owner);
    return;
  }
  const target = !hintsOff() && event.target instanceof Element ? event.target.closest("[data-hint]") : null;
  if (!target) {
    close();
    return;
  }
  event.preventDefault();
  event.stopPropagation(); // a hint tap must not also open a player card or fold a band
  const href = listFor(byId.get(target.dataset.hint));
  if (href) {
    close();
    window.location.hash = href; // the term's data: every team's number, ranked
    return;
  }
  if (cardFor === target) close();
  else open(target);
}

function onKey(event) {
  if (event.key === "Escape") {
    close();
    return;
  }
  if (event.key === "Enter" && event.shiftKey && !hintsOff() && event.target instanceof Element && event.target.matches("[data-hint-sort]")) {
    event.preventDefault();
    event.stopPropagation(); // Shift+Enter reads the header; Enter alone sorts
    if (cardFor === event.target) close();
    else open(event.target);
    return;
  }
  if ((event.key === "Enter" || event.key === " ") && !hintsOff() && event.target instanceof Element && event.target.matches("[data-hint]")) {
    event.preventDefault();
    event.stopPropagation();
    if (cardFor === event.target) close();
    else open(event.target);
  }
}

function endPress() {
  if (press) clearTimeout(press.timer);
  press = null;
}

/** A finger (or pen) held on a sortable header opens its card after LONG_PRESS_MS; the click that follows is dropped. */
function onPointerDown(event) {
  endPress();
  if (event.pointerType === "mouse" || hintsOff() || !(event.target instanceof Element)) return;
  const button = event.target.closest("[data-hint-sort]");
  if (!button) return;
  press = {
    button,
    x: event.clientX,
    y: event.clientY,
    timer: setTimeout(() => {
      press = null;
      swallow = button;
      open(button);
    }, LONG_PRESS_MS),
  };
}

function onPointerMove(event) {
  if (press && Math.hypot(event.clientX - press.x, event.clientY - press.y) > PRESS_SLOP) endPress();
}

/** The phone's own long-press menu would cover the card. */
function onContextMenu(event) {
  if (event.target instanceof Element && event.target.closest("[data-hint-sort]") && (swallow || press)) event.preventDefault();
}

/** Start marking labels and answering taps. Safe to call more than once. */
export function enableHints(root = document.body) {
  if (enabled || !root) return;
  enabled = true;
  scan(root);
  new MutationObserver((records) => {
    for (const record of records) for (const node of record.addedNodes) scan(node);
    if (cardFor && !cardFor.isConnected) follow(); // the live sheet redraws its tables on every play
  }).observe(root, { childList: true, subtree: true });
  document.addEventListener("click", onClick, true);
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("pointermove", onPointerMove, { capture: true, passive: true });
  document.addEventListener("pointerup", endPress, true);
  document.addEventListener("pointercancel", endPress, true);
  document.addEventListener("contextmenu", onContextMenu, true);
  window.addEventListener("scroll", close, { capture: true, passive: true });
  window.addEventListener("resize", close, { passive: true });
  window.addEventListener("hashchange", close);
}
