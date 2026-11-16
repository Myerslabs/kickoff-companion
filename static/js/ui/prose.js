// Claude's prose, not a wall of text (owner 2026-11-07: "I dont want it to be amazing, I just dont want a wall of text"):
// the notes and the writing bands hand their paragraphs here. A long paragraph splits at a sentence end around seventy
// words; a paragraph that is really a list (three or more parts split by semicolons, or lines led by dashes or numbers)
// draws as bullets; the first sentence of a block reads bold as its lead; a player or coach named in the text who is on the
// program (the lineups' starters, the box score's men, both staffs) becomes a tap to his card, or his page for a coach.
// Nothing changes in what Claude writes or in the saved files.
//
//   prose(paragraphs, { names, onName, lead })   the nodes for a list of paragraphs (strings; junk skipped)
//   splitParagraph(text, { words = 70 })         one paragraph as one or more, split at sentence ends
//   asList(text)                                 the items of a paragraph that is a list, or null
//   nameIndex(data)                              { names: [{ name, playerId, position, isUs, coach, team }] } from a program answer
//   indexFrom(entries)                           an index from entries of that shape (full names only, longest first)
//   rosterEntries(roster, isUs)                  the entries a roster answer gives (/api/roster?team=): every man with an id
//   linkNames(text, index, onName)               the text as nodes, each known name a tap
//   tapNamesIn(root, index, onName)              a second pass over drawn prose: the names in its text nodes become taps

import { el, isNum, text as words } from "./dom.js";
import { wikiLink } from "./wiki-links.js";

const WORDS = 70;
const MIN_PART = 25; // never a stub of a sentence or two at the end

/** A paragraph as one or more, each about `words` long, split only where a sentence ends. */
export function splitParagraph(text, { words: limit = WORDS } = {}) {
  const t = typeof text === "string" ? text.trim() : "";
  if (!t) return [];
  const sentences = t.match(/.+?(?:[.!?]+["')\]]*(?=\s+[A-Z"'(‘“]|\s*$)|$)/g)?.map((s) => s.trim()).filter(Boolean) || [t]; // a sentence ends at a period followed by a capital, never inside "Georgia -12.5"
  const count = (s) => s.split(/\s+/).filter(Boolean).length;
  if (count(t) <= limit * 1.3 || sentences.length < 2) return [t];
  const out = [];
  let current = [];
  let n = 0;
  for (const s of sentences) {
    const c = count(s);
    if (n && n + c > limit) {
      out.push(current.join(" "));
      current = [];
      n = 0;
    }
    current.push(s);
    n += c;
  }
  if (current.length) {
    if (out.length && n < MIN_PART) out[out.length - 1] += ` ${current.join(" ")}`;
    else out.push(current.join(" "));
  }
  return out;
}

/** The items of a paragraph that is a list: lines led by "-", "•" or "1." (two or more), or three or more parts split by
 *  semicolons. Null for ordinary prose. */
export function asList(text) {
  const t = typeof text === "string" ? text.trim() : "";
  if (!t) return null;
  const lines = t.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const led = lines.filter((l) => /^(?:[-–•*]|\d{1,2}[.)])\s+/.test(l));
  if (lines.length >= 2 && led.length === lines.length) return lines.map((l) => l.replace(/^(?:[-–•*]|\d{1,2}[.)])\s+/, ""));
  if (/[;]/.test(t) && !/\n/.test(t)) {
    const parts = t.split(/;\s+/).map((p) => p.trim().replace(/[.;]$/, "")).filter(Boolean);
    if (parts.length >= 3 && parts.every((p) => p.split(/\s+/).length <= 30)) return parts;
  }
  return null;
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The names a program answer knows: every lineup man with a card, every box-score line with one, both staffs. */
export function nameIndex(data) {
  const d = data && typeof data === "object" ? data : {};
  const out = new Map();
  const add = (name, entry) => {
    const n = typeof name === "string" ? name.trim() : "";
    if (n.split(/\s+/).length < 2 || out.has(n)) return; // a full name only: a surname alone matches too many
    out.set(n, { name: n, ...entry });
  };
  const notes = d.notes && typeof d.notes === "object" ? d.notes : {};
  const lineups = notes.lineups && typeof notes.lineups === "object" ? notes.lineups : d.lineups && typeof d.lineups === "object" ? d.lineups : {}; // the program keeps the charts inside the notes block
  for (const side of ["us", "them"]) {
    const team = lineups[side] && typeof lineups[side] === "object" ? lineups[side] : null;
    for (const slot of Array.isArray(team?.slots) ? team.slots : []) {
      for (const p of Array.isArray(slot?.players) ? slot.players : []) {
        if (p && typeof p === "object" && (isNum(p.playerId) || /^\d+$/.test(String(p.playerId ?? "")))) add(p.name, { playerId: String(p.playerId), position: typeof slot.slot === "string" ? slot.slot : null, isUs: side === "us", team: typeof team.team === "string" ? team.team : null });
      }
    }
  }
  const coaches = notes.coaches && typeof notes.coaches === "object" ? notes.coaches : {};
  for (const side of ["us", "them"]) {
    const staff = coaches[side] && typeof coaches[side] === "object" ? coaches[side] : {};
    const school = side === "us" ? d.us?.school : d.them?.school;
    for (const key of ["headCoach", "offensiveCoordinator", "defensiveCoordinator"]) add(staff[key], { coach: true, team: typeof school === "string" ? school : null, isUs: side === "us" });
  }
  return indexFrom([...out.values()]);
}

/** An index from entries { name, playerId | coach, ... }: a full name once, the longest first so "DJ Lagway Jr." wins over "DJ Lagway". */
export function indexFrom(entries) {
  const out = new Map();
  for (const e of Array.isArray(entries) ? entries : []) {
    const n = e && typeof e === "object" && typeof e.name === "string" ? e.name.trim() : "";
    if (n.split(/\s+/).length < 2 || out.has(n) || !(e.coach === true || isNum(e.playerId) || /^\d+$/.test(String(e.playerId ?? "")))) continue;
    out.set(n, { ...e, name: n, playerId: e.coach === true ? null : String(e.playerId) });
  }
  const names = [...out.values()].sort((a, b) => b.name.length - a.name.length);
  return { names, pattern: names.length ? new RegExp(`\\b(${names.map((n) => escapeRe(n.name)).join("|")})\\b`, "g") : null };
}

/** The entries a roster answer gives: every man with an id, his position, from one side. */
export function rosterEntries(roster, isUs) {
  const r = roster && typeof roster === "object" ? roster : {};
  return (Array.isArray(r.players) ? r.players : []).filter((p) => p && typeof p === "object").map((p) => ({ name: p.name, playerId: p.playerId, position: typeof p.position === "string" ? p.position : null, isUs: isUs === true, team: typeof r.team?.school === "string" ? r.team.school : typeof r.school === "string" ? r.school : null }));
}

/** A second pass over drawn prose: every text node that is not already inside a tap or a link is read again against the
 *  index, and its names become taps. Returns how many. */
export function tapNamesIn(root, index, onName) {
  if (!root || typeof root.querySelectorAll !== "function" || !index?.pattern) return 0;
  let made = 0;
  const walk = (node) => {
    for (const child of [...(node.childNodes || [])]) {
      if (child.nodeType === 3 || (child.nodeType === undefined && !child.tagName && typeof child.data === "string")) { // a text node (the tests' fake DOM names none)
        const value = child.textContent || "";
        index.pattern.lastIndex = 0;
        if (!index.pattern.test(value)) continue;
        const nodes = linkNames(value, index, onName);
        if (nodes.length === 1 && typeof nodes[0] === "string") continue;
        made += nodes.filter((n) => typeof n !== "string").length;
        child.replaceWith(...nodes.map((n) => (typeof n === "string" ? document.createTextNode(n) : n)));
      } else if (typeof child.tagName === "string" && !/^(BUTTON|A|SCRIPT|STYLE)$/.test(child.tagName)) walk(child);
    }
  };
  walk(root);
  return made;
}

/** The text as nodes: each known name a tap to his card (onName(entry)), a coach's name his page. */
export function linkNames(text, index, onName) {
  const t = typeof text === "string" ? text : "";
  const names = index && typeof index === "object" ? index : null;
  if (!t || !names?.pattern) return [t];
  const byName = new Map((names.names || []).map((n) => [n.name, n]));
  const out = [];
  let last = 0;
  names.pattern.lastIndex = 0;
  for (const m of t.matchAll(names.pattern)) {
    const entry = byName.get(m[1]);
    if (!entry) continue;
    if (m.index > last) out.push(t.slice(last, m.index));
    if (entry.coach) out.push(wikiLink("coach", { person: entry.name, team: entry.team }, entry.name));
    else out.push(el("button", { type: "button", class: "prose__name", onclick: (event) => { event.stopPropagation(); if (typeof onName === "function") onName(entry); } }, entry.name));
    last = m.index + m[0].length;
  }
  if (last < t.length) out.push(t.slice(last));
  return out;
}

function leadSentence(text) {
  const t = typeof text === "string" ? text : "";
  const m = t.match(/^.+?[.!?]+["')\]]*(?=\s+[A-Z"'(‘“]|\s*$)\s*/); // the first sentence, a decimal point never its end
  if (!m || m[0].trim().length === t.trim().length || m[0].split(/\s+/).length > 28) return null;
  return [m[0], t.slice(m[0].length)];
}

/** The nodes for a list of paragraphs: split, listed, led, and named. `lead` bolds the first sentence of the first one. */
export function prose(paragraphs, { names = null, onName = null, lead = true } = {}) {
  const list = (Array.isArray(paragraphs) ? paragraphs : [paragraphs]).filter((p) => typeof p === "string" && p.trim());
  const nodes = [];
  let first = lead;
  for (const para of list) {
    const items = asList(para);
    if (items) {
      nodes.push(el("ul", { class: "prose__list writing__list" }, items.map((item) => el("li", {}, ...linkNames(item, names, onName)))));
      continue;
    }
    for (const piece of splitParagraph(para)) {
      const split = first ? leadSentence(piece) : null;
      first = false;
      if (split) nodes.push(el("p", { class: "prose__p" }, el("b", { class: "prose__lead" }, ...linkNames(split[0], names, onName)), ...linkNames(split[1], names, onName)));
      else nodes.push(el("p", { class: "prose__p" }, ...linkNames(piece, names, onName)));
    }
  }
  return nodes.length ? nodes : [el("p", { class: "prose__p prose__p--none" }, words(null))];
}
