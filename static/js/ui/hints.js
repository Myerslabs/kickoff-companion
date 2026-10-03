// Stat hints (owner request 2026-09-26): tap a stat's name anywhere in the app for what it means.
// One observer marks every label cell whose text matches a glossary alias (a dotted underline),
// and one click handler on the document opens a small card beside it. No view builds hints
// itself, so every table, sheet and flyout gets them, including ones added later. Sortable
// column headers keep their tap for sorting; on a desktop they show the definition on hover.
// The Settings switch "Stat hints" adds .hints-off to <html>, which hides the marks and the card.

import { GLOSSARY } from "../glossary-data.js";
import { el, text } from "./dom.js";

const LABELS = "td.txt:first-child, th[scope=row], thead th, .sit__label, .success__source, .verdict";
// the Success / Failed verdict explains the success rule; an edges row's label names two units, so it opens Edges
// a lineup's slot labels (EDGE, STAR, JACK, PK) are positions, not stats: they open the Depth chart entry
const BY_CLASS = [[".verdict", "success-rate"], [".tt--edges td.tt__label", "edges"], [".lineup td.txt:first-child", "depth-chart"]];
const GAP = 6;
const EDGE = 8;

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
  return index.get(normalize(label)) || null;
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
    return;
  }
  node.dataset.hint = entry.id;
  if (!node.hasAttribute("tabindex")) node.tabIndex = 0;
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
  const entry = byId.get(target.dataset.hint);
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
  const id = cardFor.dataset.hint;
  const words = normalize(ownText(cardFor));
  const again = [...document.querySelectorAll("[data-hint]")].find((node) => node.dataset.hint === id && normalize(ownText(node)) === words && !node.closest(".hint-pop"));
  if (!again) {
    close();
    return;
  }
  cardFor = again;
  place(again);
}

function onClick(event) {
  if (card && card.contains(event.target)) {
    if (event.target.closest("a")) close(); // the Glossary link navigates; the card goes with it
    return;
  }
  const target = !hintsOff() && event.target instanceof Element ? event.target.closest("[data-hint]") : null;
  if (!target) {
    close();
    return;
  }
  event.preventDefault();
  event.stopPropagation(); // a hint tap must not also open a player card or fold a band
  if (cardFor === target) close();
  else open(target);
}

function onKey(event) {
  if (event.key === "Escape") {
    close();
    return;
  }
  if ((event.key === "Enter" || event.key === " ") && !hintsOff() && event.target instanceof Element && event.target.matches("[data-hint]")) {
    event.preventDefault();
    event.stopPropagation();
    if (cardFor === event.target) close();
    else open(event.target);
  }
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
  window.addEventListener("scroll", close, { capture: true, passive: true });
  window.addEventListener("resize", close, { passive: true });
  window.addEventListener("hashchange", close);
}
