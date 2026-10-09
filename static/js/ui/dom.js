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
    case "pct": return fmtPct(value, 1); // final pass: a rate in a table shows one decimal, so ranked neighbours never look equal
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
//   syncPageLock()                                          html.is-locked while any [data-modal] layer is open.
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
    if (document.querySelector("[data-modal]")) html.classList.add("is-locked");
    else html.classList.remove("is-locked");
  } catch {
    // no page (tests, styleguide inline): nothing to lock
  }
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
