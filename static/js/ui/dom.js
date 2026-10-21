// DOM and formatting helpers shared by every component.
// Rule from CLAUDE.md: a missing value renders as a dash, never undefined, null, or NaN.

export const DASH = "–";

/** A plain object, or {} for anything else (an array, null, a string): safe to read keys from. */
export function obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

/** The rows of a list: only the plain objects, or [] for anything that is not an array. */
export function records(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object" && !Array.isArray(row)) : [];
}

/** A string's trimmed text, or null when it is not a string or is blank. */
export function str(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function isNum(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "style" && typeof value === "object") {
      for (const [prop, v] of Object.entries(value)) {
        if (v === null || v === undefined) continue;
        if (prop.startsWith("--")) node.style.setProperty(prop, String(v)); // custom properties only take setProperty
        else node.style[prop] = v;
      }
    }
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function frag(...children) {
  return append(document.createDocumentFragment(), children);
}

/** Replace a node's children with the given children, flattening arrays and skipping blanks. */
export function replaceWith(node, ...children) {
  node.replaceChildren();
  return append(node, children);
}

export function text(value) {
  if (value === null || value === undefined) return DASH;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : DASH;
  let s;
  try {
    s = String(value).trim();
  } catch {
    return DASH; // an object that cannot be turned into text
  }
  // Phase 16: an object handed in where text belongs prints a dash, never "[object Object]"
  return s === "" || /\[object \w+\]/.test(s) ? DASH : s;
}

export function fmtNum(value, digits = 0) {
  if (!isNum(value)) return DASH;
  return value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtSigned(value, digits = 0) {
  if (!isNum(value)) return DASH;
  const body = fmtNum(Math.abs(value), digits);
  if (value > 0) return `+${body}`;
  if (value < 0) return `−${body}`;
  return body;
}

/** "$20.5M", "$850K", "$1,200": a dollar amount at a glance (Phase 17 Part 3b, rumored roster costs). */
export function fmtUsd(value) {
  if (!isNum(value) || value < 0) return DASH;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(value >= 1e10 ? 0 : 1).replace(/\.0$/, "")}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(value >= 1e8 ? 0 : 1).replace(/\.0$/, "")}M`;
  if (value >= 1e4) return `$${Math.round(value / 1e3)}K`;
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

export function fmtPct(value, digits = 0) {
  return isNum(value) ? `${(value * 100).toFixed(digits)}%` : DASH;
}

/** A 247 composite rating as a 0-100 score: 0.9379 -> 94, 94 stays 94; anything else is null. */
export function rating100(value) {
  if (!isNum(value) || value <= 0) return null;
  if (value <= 1) return Math.round(value * 100);
  return value <= 100 ? Math.round(value) : null;
}

/** The color tier of a 0-100 rating, as on the depth chart: "top" (90+), "good" (80s), "fair" (below), "" when unknown. */
export function ratingTier(score) {
  if (!isNum(score)) return "";
  return score >= 90 ? "top" : score >= 80 ? "good" : "fair";
}

/** Stars as "4-star" (1 to 5), or null (Phase 16 wave 3: words, not a font star some tablets can't draw). */
export function starCount(value) {
  if (!isNum(value)) return null;
  const n = Math.round(value);
  return n >= 1 && n <= 5 ? n : null;
}

// Formats used by the sample-data profile rows: "0f", "1f", "pct", "+0f"; Phase 16 adds "rating100" and "stars".
export function fmtStat(value, format) {
  switch (format) {
    case "rating100": {
      const score = rating100(value);
      return score === null ? DASH : String(score);
    }
    case "stars": {
      const n = starCount(value);
      return n === null ? DASH : `${n}-star`;
    }
    case "pct": return fmtPct(value, 0); // Design rules (owner 2026-10-21): a rate in a table shows whole numbers (the one-decimal rule of 2026-10-09 is superseded)
    case "usd": return fmtUsd(value);
    case "1f": return fmtNum(value, 1);
    case "2f": return fmtNum(value, 2);
    case "3f": return fmtNum(value, 3);
    case "4f": return fmtNum(value, 4);
    case "+0f": return fmtSigned(value, 0);
    case "+1f": return fmtSigned(value, 1);
    case "+2f": return fmtSigned(value, 2);
    default: return typeof value === "string" ? text(value) : fmtNum(value, 0);
  }
}

// --- player names (item 6, owner 2026-10-11: "K. Crawford" when there is no room; one line only, reduce the name) ----------
//   playerNames(nameOrRow, { notes })  { full, initial, last, reduced, first }: a player's name in the forms a table steps
//       through. nameOrRow is a string or a row { name, firstName, lastName } (CFBD's split wins when both halves exist).
//       full     the name as written, whitespace collapsed                  "Michael Van Buren Jr."
//       initial  the first name's initial, a no-break space, the surname    "M. Van Buren" (owner answer 5: with a space)
//       last     the surname alone                                          "Van Buren"
//       reduced  a hyphenated surname's first part and the second's initial "Brackwater-M." (else the surname)
//       first    the first name's lead word, for the second letter of two rows that would read alike ("Ca.", "Co.")
//       A suffix (Jr, Jr., JR, Sr., II to VI, Ii, the typo "ll"; a comma before it or not) stays in full and leaves the short
//       forms; the surname keeps its particles (van, von, de, del, la, St., Saint and the rest; never the first word, never
//       Al or El); a first name written as initials stays whole ("AJ Crawford", "A.J. Crawford"); one word is the same in every
//       form; nothing at all is a dash in every form. notes: true for a name from the notes (AI-written text): it shortens
//       only when it reads cleanly as First [particles] Last [suffix], else every form is the name as written. Matching a
//       name to the availability report or a depth chart always uses the full string, never a short form.
//   distinctNames(list)  one table's forms, settled (owner answer 7): rows whose initial forms would read the same get a
//       second letter ("Ca. Thomas", "Co. Thomas"; the whole first name when two letters still match), and rows that share
//       a surname keep their initial form where the others drop to the surname (and its reduced form).
//   personName(nameOrRow, { notes, after, names, fit })  <span class="pn"> holding the four forms, one shown at a time by
//       the data-pn of the table or card around it (or its own); the full name for a screen reader and in its title. after
//       is words kept after whichever form shows (" (RS)"). fit: true for a card's name, fitted on its own (fitNames).
//   settleNames(cells)  distinctNames over drawn cells: each cell's .pn nodes take the settled forms.
//   nameSteps(root)  which name steps change anything among a root's names (a table's ladder skips the others).
//   fitNames(root), watchNames(root)  a card's names (.pn[data-fit]) each try full, initial, the surname and the reduced
//       surname in its own box before the box's own ellipsis; watchNames fits again whenever the root changes width.

const NBSP = "\u00A0";
const SUFFIX = /^(?:jr|sr)\.?$|^(?:ii|iii|iv|v|vi)$|^ll$/i;
const PARTICLES = new Set(["van", "von", "vander", "vanden", "de", "del", "della", "dela", "der", "den", "du", "da", "di", "dos", "das", "la", "le", "st.", "st", "saint", "ter", "ten"]);
const INITIALS = /^(?:\p{Lu}\.?){2,3}$|^\p{Lu}\.$/u; // AJ, A.J., A.J, TJ, A.C., J.: a first name written as initials stays
const CLEAN_WORD = /^\p{L}[\p{L}\p{M}'’.-]*$/u; // a notes name's word: letters, an apostrophe, a hyphen, a dot
const NAME_FORMS = ["full", "initial", "last", "reduced", "number"]; // number: "#19" where the row knows it, else the reduced surname (Design rules, owner 2026-10-21)

function nameWords(value) {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

/** The words without a trailing suffix ("Jr.", "III", a comma before it); never the last word left. */
function withoutSuffix(words) {
  const out = [...words];
  let cut = false;
  while (out.length > 1) {
    const tail = out[out.length - 1];
    if (tail !== "," && !SUFFIX.test(tail.replace(/,$/, ""))) break;
    out.pop();
    cut = true;
  }
  if (cut) out[out.length - 1] = out[out.length - 1].replace(/,$/, ""); // "Passmore, Jr." -> "Passmore"
  return out;
}

/** The first name as its initial: initials kept as written ("AJ", "A.J."), one letter gains a dot, else the first letter. */
function initialOf(word) {
  if (!word) return "";
  if (INITIALS.test(word)) return word;
  const letter = word.match(/\p{L}/u);
  return letter ? `${letter[0].toUpperCase()}.` : word;
}

/** A hyphenated surname's first part and the second part's initial ("Brackwater-Matchley" -> "Brackwater-M."). */
function reducedOf(surname) {
  const at = surname.indexOf("-");
  if (at <= 0) return surname;
  const letter = surname.slice(at + 1).match(/\p{L}/u);
  return letter ? `${surname.slice(0, at)}-${letter[0].toUpperCase()}.` : surname;
}

function formsOf(full, given, surname) {
  const lead = nameWords(given).split(" ")[0] || "";
  const init = initialOf(lead);
  return { full, initial: init ? `${init}${NBSP}${surname}` : surname, last: surname, reduced: reducedOf(surname), first: lead };
}

/** Whether a notes name reads cleanly as First [particles] Last (its suffix already gone). */
function cleanNotesName(words) {
  if (words.length < 2 || !words.every((w) => CLEAN_WORD.test(w))) return false;
  return words.slice(1, -1).every((w) => PARTICLES.has(w.toLowerCase())) && !PARTICLES.has(words[words.length - 1].toLowerCase());
}

export function playerNames(input, { notes = false } = {}) {
  const row = input && typeof input === "object" && !Array.isArray(input) ? input : { name: input };
  const given = nameWords(row.firstName);
  const family = nameWords(row.lastName);
  const full = nameWords(row.name) || [given, family].filter(Boolean).join(" ");
  // the last step down (Design rules, owner 2026-10-21): the player's number, where the row carries one
  const numbered = (f) => ({ ...f, number: isNum(row.number) && row.number >= 0 ? `#${Math.round(row.number)}` : f.reduced });
  if (!full || /\[object \w+\]/.test(full)) return { full: DASH, initial: DASH, last: DASH, reduced: DASH, number: DASH, first: "" };
  if (given && family && !notes) return numbered(formsOf(full, given, withoutSuffix(family.split(" ")).join(" ")));
  const words = withoutSuffix(full.split(" "));
  if (words.length === 1) return numbered({ full, initial: words[0], last: words[0], reduced: reducedOf(words[0]), first: "" });
  if (notes && !cleanNotesName(words)) return numbered({ full, initial: full, last: full, reduced: full, first: "" });
  let start = words.length - 1;
  while (start > 1 && PARTICLES.has(words[start - 1].toLowerCase())) start -= 1; // never the first word
  return numbered(formsOf(full, words[0], words.slice(start).join(" ")));
}

const sameKey = (value) => String(value).replace(/\u00A0/g, " ").toLocaleLowerCase();

/** The first name's first two letters and a dot ("Case" -> "Ca."), or null for initials or a one-letter name. */
function twoLetters(first) {
  if (!first || INITIALS.test(first)) return null;
  const letters = first.match(/\p{L}/gu) || [];
  return letters.length >= 2 ? `${letters[0].toUpperCase()}${letters[1].toLowerCase()}.` : null;
}

/** The indexes of a list grouped by a key, keeping only groups that name two or more different players (full names). */
function clashes(list, keyOf) {
  const groups = new Map();
  list.forEach((f, i) => {
    if (!f || f.full === DASH) return;
    const key = sameKey(keyOf(f));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(i);
  });
  return [...groups.values()].filter((at) => new Set(at.map((i) => sameKey(list[i].full))).size > 1);
}

export function distinctNames(list) {
  const out = (Array.isArray(list) ? list : []).map((f) => (f && typeof f === "object" && typeof f.full === "string" ? { ...f } : null));
  // two players who would read the same: a second letter each, else the whole first name, else the whole name
  const tries = [(f) => (twoLetters(f.first) ? `${twoLetters(f.first)}${NBSP}${f.last}` : null), (f) => (f.first ? `${f.first}${NBSP}${f.last}` : null), (f) => f.full];
  for (const at of clashes(out, (f) => f.initial)) {
    let left = at;
    for (const make of tries) {
      const made = new Map(left.map((i) => [i, make(out[i])]));
      const players = new Map(); // a made form -> the players (full names) it would name
      for (const i of left) {
        if (made.get(i) === null) continue;
        const key = sameKey(made.get(i));
        if (!players.has(key)) players.set(key, new Set());
        players.get(key).add(sameKey(out[i].full));
      }
      const unique = (i) => made.get(i) !== null && players.get(sameKey(made.get(i))).size === 1;
      for (const i of left) if (unique(i)) out[i].initial = made.get(i);
      left = left.filter((i) => !unique(i));
      if (!left.length) break;
    }
  }
  // players who share a surname never drop to it: they keep their initial form at the surname steps
  const shared = new Set(clashes(out, (f) => f.last).flat());
  for (const i of shared) {
    out[i].last = out[i].initial;
    out[i].reduced = out[i].initial;
  }
  // two reduced surnames that would read the same ("Brackwater-M." twice) keep their whole surnames
  for (const at of clashes(out.map((f, i) => (shared.has(i) ? null : f)), (f) => f.reduced)) for (const i of at) out[i].reduced = out[i].last;
  return out;
}

/** A player's name drawn in its four forms (one shows at a time); the full name for a screen reader and in the title. */
export function personName(input, { notes = false, after = "", names, fit = false } = {}) {
  const forms = names && typeof names === "object" && typeof names.full === "string" ? names : playerNames(input, { notes });
  const tail = typeof after === "string" ? after : "";
  const plain = NAME_FORMS.every((k) => forms[k] === forms.full);
  const node = el("span", { class: "pn", title: forms.full === DASH ? null : `${forms.full}${tail}`, dataset: fit ? { fit: "" } : null }); // the title even when plain: the last step clips every name
  node.__names = forms;
  node.__after = tail;
  if (plain) return append(node, [`${forms.full}${tail}`]);
  return append(node, [el("span", { class: "sr-only" }, `${forms.full}${tail}`), NAME_FORMS.map((k) => el("span", { class: `pn__f pn__f--${k}`, "aria-hidden": "true" }, `${forms[k]}${tail}`))]);
}

/** The .pn nodes in a cell (the cell itself when it is one). */
function namesIn(cell) {
  if (!cell || typeof cell.querySelectorAll !== "function") return [];
  const inner = [...cell.querySelectorAll(".pn")];
  return typeof cell.matches === "function" && cell.matches(".pn") ? [cell, ...inner] : inner;
}

/** Settle one table's (or one side's) drawn names: each cell's nodes take the settled forms of its first name. */
export function settleNames(cells) {
  const items = [];
  for (const cell of cells ? [...cells] : []) {
    const nodes = namesIn(cell).filter((n) => n.__names);
    if (nodes.length) items.push({ nodes, names: nodes[0].__names });
  }
  const settled = distinctNames(items.map((item) => item.names));
  items.forEach((item, i) => {
    const forms = settled[i];
    if (!forms) return;
    for (const node of item.nodes) {
      node.__shown = forms;
      for (const k of ["initial", "last", "reduced", "number"]) {
        const span = node.querySelector(`.pn__f--${k}`);
        if (span) span.textContent = `${forms[k]}${node.__after || ""}`;
      }
    }
  });
  return settled;
}

/** Which name steps change anything among a root's names: { any, initial, last, reduced, number }. */
export function nameSteps(root) {
  const out = { any: false, initial: false, last: false, reduced: false, number: false };
  if (!root || typeof root.querySelectorAll !== "function") return out;
  for (const node of root.querySelectorAll(".pn")) {
    const f = node.__shown || node.__names;
    if (!f || f.full === DASH) continue;
    out.any = true;
    if (f.initial !== f.full) out.initial = true;
    if (f.last !== f.initial) out.last = true;
    if (f.reduced !== f.last) out.reduced = true;
    if (f.number !== f.reduced) out.number = true;
  }
  return out;
}

/** A card's names, each in its own box: full, then the initial, the surname, the reduced surname, then the player's number
 *  (Design rules, owner 2026-10-21) where the row knows it; the box's ellipsis after that. Batched (every name tries a form, then all are measured), so a whole depth chart lays out four times at most. */
export function fitNames(root) {
  if (!root || typeof root.querySelectorAll !== "function") return;
  const items = [...root.querySelectorAll(".pn[data-fit]")].map((pn) => ({ pn, box: pn.parentNode })).filter((it) => it.box && isNum(it.box.clientWidth));
  let left = items;
  for (const form of NAME_FORMS) {
    if (form === "number" && !left.some((it) => { const f = it.pn.__shown || it.pn.__names; return f && f.number !== f.reduced; })) continue; // no number known: nothing to step to
    for (const it of left) it.pn.dataset.pn = form;
    left = left.filter((it) => it.box.clientWidth > 0 && overflows(it.box));
    if (!left.length) break;
  }
}

/** Whether a box's words run past it, to the fraction of a pixel (an ellipsis shows at any overflow, and scrollWidth
 *  rounds): the right edge of its words and inline pieces (never the screen reader's copy, which is taken out of the flow)
 *  against its content box; scrollWidth where there is no layout to read (the tests). */
function overflows(box) {
  if (typeof document.createRange !== "function" || typeof getComputedStyle !== "function" || typeof box.getBoundingClientRect !== "function") return box.scrollWidth > box.clientWidth;
  const style = getComputedStyle(box);
  const px = (k) => parseFloat(style[k]) || 0;
  const outer = box.getBoundingClientRect();
  const left = outer.left + px("paddingLeft") + px("borderLeftWidth");
  const room = outer.width - px("paddingLeft") - px("paddingRight") - px("borderLeftWidth") - px("borderRightWidth");
  let right = left;
  for (const node of box.childNodes) {
    let rect = null;
    if (node.nodeType === 3) {
      const range = document.createRange();
      range.selectNodeContents(node);
      rect = range.getBoundingClientRect();
    } else if (node.nodeType === 1 && getComputedStyle(node).position !== "absolute") rect = node.getBoundingClientRect();
    if (rect && rect.width > 0) right = Math.max(right, rect.right);
  }
  return isNum(right) && isNum(room) ? right - left > room + 0.01 : box.scrollWidth > box.clientWidth;
}

/** Keep a root's card names fitted: once it is on the page, when it changes width, and when the fonts arrive. */
let namesFontsHooked = false;

export function watchNames(root) {
  if (!root || !isNum(root.clientWidth) || typeof requestAnimationFrame !== "function") return root; // no layout engine (tests)
  const fit = () => {
    try {
      fitNames(root);
    } catch (error) {
      console.error("names: could not fit a card's names.", error);
    }
  };
  let tries = 0;
  const first = () => {
    if (root.isConnected && root.clientWidth > 0) fit();
    else if (tries++ < 10) requestAnimationFrame(first);
  };
  requestAnimationFrame(first);
  if (typeof ResizeObserver === "function") {
    let last = -1;
    const observer = new ResizeObserver(() => {
      const width = root.clientWidth;
      if (!isNum(width) || width === last || width <= 0) return;
      last = width;
      fit();
    });
    observer.observe(root);
    root.nameObserver = observer; // kept on the root, so it lives as long as the cards
  }
  // one shared hook for the whole page (item 6 review): a listener per call held every replaced grid (In Game redraws its
  // leaders on each play), and once the fonts had loaded no event came to remove them
  if (!namesFontsHooked && typeof document !== "undefined" && document.fonts && typeof document.fonts.addEventListener === "function") {
    namesFontsHooked = true;
    document.fonts.addEventListener("loadingdone", () => {
      try {
        fitNames(document);
      } catch (error) {
        console.error("names: could not fit the cards' names.", error);
      }
    });
  }
  return root;
}

export function ordinal(n) {
  if (!isNum(n)) return DASH;
  const suffixes = ["th", "st", "nd", "rd"];
  const rem = n % 100;
  return `${n}${suffixes[(rem - 20) % 10] || suffixes[rem] || suffixes[0]}`;
}

export function fmtClock(clock) {
  if (!clock) return DASH;
  if (typeof clock === "string") return clock.trim() || DASH;
  if (!isNum(clock.minutes) || !isNum(clock.seconds)) return DASH;
  return `${clock.minutes}:${String(clock.seconds).padStart(2, "0")}`;
}

export function fmtDuration(seconds) {
  if (!isNum(seconds) || seconds < 0) return DASH;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function period(n) {
  if (!isNum(n)) return DASH;
  if (n <= 4) return `Q${n}`;
  return n === 5 ? "OT" : `${n - 4}OT`;
}

function parseDate(iso) {
  if (!iso) return null;
  // A bare date ("2026-09-26") is that calendar day where the viewer is, not UTC midnight, which
  // in Eastern time is the evening before (the Newspaper's slate title said Friday on a Saturday).
  const bare = typeof iso === "string" ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso) : null;
  const d = iso instanceof Date ? iso : bare ? new Date(Number(bare[1]), Number(bare[2]) - 1, Number(bare[3])) : new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDate(iso, style = "medium") {
  const d = parseDate(iso);
  if (!d) return DASH;
  const options = style === "long"
    ? { weekday: "long", month: "long", day: "numeric" }
    : style === "short"
      ? { month: "short", day: "numeric" }
      : { weekday: "short", month: "short", day: "numeric" };
  return d.toLocaleDateString([], options);
}

export function fmtTime(iso) {
  const d = parseDate(iso);
  if (!d) return DASH;
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}

export function fmtDateTime(iso) {
  const d = parseDate(iso);
  if (!d) return DASH;
  return `${fmtDate(d)} ${fmtTime(d)}`;
}

export function ageText(seconds) {
  if (!isNum(seconds) || seconds < 0) return DASH;
  if (seconds < 60) return `${Math.round(seconds)} s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  return `${(seconds / 3600).toFixed(1)} h ago`;
}

/** "3rd & 7 at SWT 41", the way a fan says it. */
export function situationText({ down, distance, yardsToGoal, offenseAbbr, defenseAbbr }) {
  const parts = [];
  if (isNum(down)) {
    const dist = isNum(distance) ? (isNum(yardsToGoal) && distance >= yardsToGoal ? "Goal" : String(distance)) : DASH;
    parts.push(`${ordinal(down)} & ${dist}`);
  }
  if (isNum(yardsToGoal)) {
    if (yardsToGoal === 50) parts.push("at the 50");
    else if (yardsToGoal > 50) parts.push(`at ${text(offenseAbbr)} ${100 - yardsToGoal}`);
    else parts.push(`at ${text(defenseAbbr)} ${yardsToGoal}`);
  }
  return parts.length ? parts.join(" ") : DASH;
}

/** A team name that opens the team page (ours) or the team flyout (anyone else). The app
 *  installs one document-level click handler for `[data-team]`; see app.js. */
export function teamLink(school, label) {
  if (!school) return document.createTextNode(text(label ?? school));
  return el("button", {
    class: "team-link",
    type: "button",
    dataset: { team: school },
    onclick: (event) => {
      event.stopPropagation(); // the row underneath must not open a player card too
      document.dispatchEvent(new CustomEvent("kickoff:team", { detail: school }));
    },
  }, label ?? school);
}

export function remember(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private mode or blocked storage: the preference just does not persist.
  }
}

export function recall(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

// --- Phase 16 kit (stream F). Frozen API:
//   teamLogo(team, { size = 28, lazy = true, className })   <img class="team-logo"> from the server's logo URLs
//       (logoDark on the dark theme, logo on the light one), or a mono tile with the abbreviation when there is
//       no URL or the image fails. team: { school, abbreviation, logo, logoDark, color }.
//   playerFace(player, { them, abbr, size, lazy })          headshot, else a badge with the number, else the
//       team abbreviation, else the initials; never a lone dash. Uses .headshot / .number-badge(--them).
//   snapshotKeys(root)                                      Map of [data-k] -> text, taken before a redraw.
//   flashChanges(oldRootOrSnapshot, newRoot, { className = "is-changed" })   marks new [data-k] cells whose
//       text changed; returns how many. Nothing is marked when there was no old root (the first frame).
//   scrollState(root, { page })  / restoreScroll(root, saved)   scroll offsets of root and of every
//       .stat-table-wrap inside it (and the page's when page: true), put back after a redraw.
//   syncPageLock()                                          html.is-locked while the menu drawer is open (item 8: a side
//                                                           sheet or the player card scrolls with the page, so it never locks it).
//   sheetAnchor()                                           where a new side sheet or card starts on the page: the page's
//                                                           scroll plus the top bar's bottom edge (item 8), and that scroll.
//   reducedMotion()                                         true when the reader asked for less motion.

const HEX = /^#[0-9a-f]{3,8}$/i;

function initials(name, max = 3) {
  if (typeof name !== "string") return "";
  const words = name.replace(/[^A-Za-z0-9&' ]/g, " ").split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  if (words.length === 1) return words[0].slice(0, max).toUpperCase();
  return words.map((w) => w[0]).join("").slice(0, max).toUpperCase();
}

function isUrl(value) {
  return typeof value === "string" && (value.startsWith("/") || /^https?:\/\//.test(value));
}

function lightTheme() {
  try {
    return document.documentElement?.dataset?.theme === "light";
  } catch {
    return false;
  }
}

function logoTile(team, size, className) {
  const label = text(team?.abbreviation || initials(team?.school) || null);
  const tile = el("span", { class: `team-logo team-logo--mono${className ? ` ${className}` : ""}`, "aria-hidden": "true", style: { "--logo-size": `${size}px` } }, label);
  if (typeof team?.color === "string" && HEX.test(team.color)) tile.style.setProperty("--logo-bg", team.color);
  return tile;
}

export function teamLogo(team, { size = 28, lazy = true, className } = {}) {
  const px = isNum(size) && size > 0 ? Math.round(size) : 28;
  const light = lightTheme();
  const src = [light ? team?.logo : team?.logoDark, light ? team?.logoDark : team?.logo].find(isUrl);
  if (!src) return logoTile(team, px, className);
  const img = el("img", { class: `team-logo${className ? ` ${className}` : ""}`, src, alt: "", width: String(px), height: String(px), loading: lazy ? "lazy" : null, decoding: "async", style: { "--logo-size": `${px}px` } });
  img.addEventListener("error", () => img.replaceWith(logoTile(team, px, className)));
  return img;
}

function faceBadge(player, them, abbr, size) {
  const label = isNum(player?.number) ? String(player.number) : (typeof abbr === "string" && abbr.trim()) || initials(player?.name || player?.player, 2) || "";
  const badge = el("div", { class: `number-badge face${them ? " number-badge--them" : ""}`, "aria-hidden": "true" }, label);
  if (size) Object.assign(badge.style, { width: `${size}px`, height: `${size}px` });
  return badge;
}

export function playerFace(player, { them = false, abbr, size, lazy = true } = {}) {
  const px = isNum(size) && size > 0 ? Math.round(size) : null;
  if (!isUrl(player?.headshotUrl)) return faceBadge(player, them, abbr, px);
  const img = el("img", { class: "headshot face", src: player.headshotUrl, alt: "", width: px ? String(px) : null, height: px ? String(px) : null, loading: lazy ? "lazy" : null, decoding: "async" });
  if (px) Object.assign(img.style, { width: `${px}px`, height: `${px}px` });
  img.addEventListener("error", () => img.replaceWith(faceBadge(player, them, abbr, px)));
  return img;
}

export function snapshotKeys(root) {
  const map = new Map();
  if (!root || typeof root.querySelectorAll !== "function") return map;
  for (const node of root.querySelectorAll("[data-k]")) {
    const key = node.dataset?.k ?? node.getAttribute?.("data-k");
    if (key) map.set(String(key), node.textContent);
  }
  return map;
}

export function flashChanges(oldRoot, newRoot, { className = "is-changed" } = {}) {
  if (!oldRoot || !newRoot || typeof newRoot.querySelectorAll !== "function") return 0;
  const before = oldRoot instanceof Map ? oldRoot : snapshotKeys(oldRoot);
  if (!before.size) return 0;
  let changed = 0;
  for (const node of newRoot.querySelectorAll("[data-k]")) {
    const key = String(node.dataset?.k ?? node.getAttribute?.("data-k") ?? "");
    if (key && before.has(key) && before.get(key) !== node.textContent) {
      node.classList.add(className);
      changed += 1;
    }
  }
  return changed;
}

export function scrollState(root, { page = false } = {}) {
  const tables = root && typeof root.querySelectorAll === "function" ? [...root.querySelectorAll(".stat-table-wrap")].map((node) => [node.scrollTop || 0, node.scrollLeft || 0]) : [];
  const saved = { top: root?.scrollTop || 0, tables };
  if (page && typeof window !== "undefined" && isNum(window.scrollY)) saved.pageY = window.scrollY;
  return saved;
}

export function restoreScroll(root, saved) {
  if (!root || !saved) return;
  if (isNum(saved.top)) root.scrollTop = saved.top;
  const tables = typeof root.querySelectorAll === "function" ? [...root.querySelectorAll(".stat-table-wrap")] : [];
  if (Array.isArray(saved.tables) && tables.length === saved.tables.length) {
    tables.forEach((node, index) => {
      [node.scrollTop, node.scrollLeft] = saved.tables[index]; // a different set of tables stays at the start
    });
  }
  if (isNum(saved.pageY) && typeof window !== "undefined" && typeof window.scrollTo === "function") window.scrollTo(0, saved.pageY);
}

export function syncPageLock() {
  try {
    const html = document.documentElement;
    if (!html?.classList) return;
    if (document.querySelector('[data-modal]:not(.sheet-layer):not(.card-layer)')) html.classList.add("is-locked");
    else html.classList.remove("is-locked");
  } catch {
    // no page (tests, styleguide inline): nothing to lock
  }
}

/**
 * Item 8 (owner 2026-10-10: "the page always scrolls, so a sheet never needs a bottom edge"): a side sheet or the player
 * card is as tall as its content and lies on the page where the reader is, so a long one is read by scrolling the page,
 * never inside a box. `top` is where it starts (the page's scroll plus the layer top, the top bar's bottom edge from
 * 700 px up), `scrollY` the page's scroll, which closing it gives back.
 */
export function sheetAnchor(layerTop = 0) {
  const scrollY = typeof window !== "undefined" && isNum(window.scrollY) ? window.scrollY : 0;
  let wide = true; // a phone's sheet covers the whole screen, the top bar too (components.css --sheet-sticky)
  try {
    wide = typeof window === "undefined" || typeof window.matchMedia !== "function" || window.matchMedia("(min-width: 700px)").matches;
  } catch {
    wide = true;
  }
  return { top: Math.max(0, Math.round(scrollY + (wide && isNum(layerTop) ? layerTop : 0))), scrollY };
}

export function reducedMotion() {
  try {
    return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

// --- overlay layers (side sheets, the player card): stacking and a sliding exit ----------------------
//   layerZ()                     the z-index for a new layer, above every open one (and below the hint card).
//   retireLayer(layer, base)     close with motion: the layer is renamed "<base>-closing" at once (so queries
//                                and Escape skip it), slides out, and is removed on animationend or after 250 ms;
//                                removed at once when motion is reduced or the page cannot animate.

export function layerZ() {
  let open = 0;
  try {
    open = document.querySelectorAll("[data-modal]").length;
  } catch {
    open = 0;
  }
  return String(Math.min(59, 46 + open));
}

export function retireLayer(layer, base) {
  if (!layer) return;
  const animates = typeof window !== "undefined" && typeof window.matchMedia === "function" && !reducedMotion() && layer.isConnected !== false;
  if (!animates) {
    layer.remove();
    syncPageLock();
    return;
  }
  layer.removeAttribute("data-modal");
  layer.setAttribute("aria-hidden", "true");
  layer.className = `${base}-closing`;
  syncPageLock();
  let gone = false;
  const done = () => {
    if (gone) return;
    gone = true;
    layer.remove();
  };
  layer.addEventListener("animationend", (event) => {
    const cls = String(event.target?.className || "");
    if (event.target !== layer && !cls.includes("scrim")) done(); // the panel's slide, not the shorter scrim fade
  });
  setTimeout(done, 250);
}

/**
 * Phase 16 wave 3 (owner pick 2B): a swipe to the right closes a side sheet or the player card. Ignored when it starts
 * inside something that scrolls sideways (a wide table, the ticker, the sheet buttons) or a form control, when it is
 * mostly vertical, or slow. Returns a function that removes the listeners.
 */
export function swipeToClose(node, close, { distance = 80, maxDrift = 50, maxMs = 700 } = {}) {
  if (!node || typeof node.addEventListener !== "function" || typeof close !== "function") return () => {};
  let start = null;
  const sideways = (target) => {
    for (let n = target; n && n !== node; n = n.parentElement) {
      if (n.matches?.("input, select, textarea, .ticker, .remote, .chips-row")) return true;
      if (n.scrollWidth > n.clientWidth + 2 && typeof getComputedStyle === "function" && /(auto|scroll)/.test(getComputedStyle(n).overflowX)) return true;
    }
    return false;
  };
  const down = (event) => {
    start = event.pointerType === "mouse" || sideways(event.target) ? null : { x: event.clientX, y: event.clientY, at: Date.now() };
  };
  const up = (event) => {
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = Math.abs(event.clientY - start.y);
    const quick = Date.now() - start.at <= maxMs;
    start = null;
    if (dx >= distance && dy <= maxDrift && quick) close();
  };
  const cancel = () => {
    start = null;
  };
  node.addEventListener("pointerdown", down);
  node.addEventListener("pointerup", up);
  node.addEventListener("pointercancel", cancel);
  return () => {
    node.removeEventListener("pointerdown", down);
    node.removeEventListener("pointerup", up);
    node.removeEventListener("pointercancel", cancel);
  };
}

/**
 * A record as every page writes it (freeze wave F3: one formatter for the six that each page had): "6-1", "6-1-1" when
 * there are ties; null when the wins or losses are not numbers (each caller picks its own dash).
 */
export function recordText(record) {
  const r = record && typeof record === "object" ? record : {};
  if (!isNum(r.wins) || !isNum(r.losses)) return null;
  return isNum(r.ties) && r.ties > 0 ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`;
}
