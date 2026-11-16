// Status pills and key-play badges. Never color alone: every pill has a word and a shape,
// every badge has a glyph and a label.

import { icon } from "./icons.js";
import { el, text } from "./dom.js";

const PILL_KINDS = new Set(["live", "delayed", "stale", "offline", "replay", "quiet"]);
const DOTS = new Set(["ok", "live", "slow", "down", "off"]);

/**
 * pill({ kind: "live"|"delayed"|"stale"|"offline"|"replay"|"quiet", label, tap, onClick, dot, more, parts })
 * With `onClick` the pill is a button (Phase 16 wave 3, DS-12: the top bar's pill opens the status card).
 * The words sit in their own .pill__label, so the top bar can shorten them with "…" inside the pill (item 6, step F)
 * without clipping the pill's 44 px press area; the button keeps the whole label as its title.
 * ENH-4 (the owner's board of 2026-10-27): `dot` is the server connection, drawn as a shape as well as a color (ok a
 * filled dot, live the team's color, slow half filled, down a red square, off a red ring); `more` follows the label in fog
 * ("· hourly", "· 25 min old"); `parts` spells the label as [words, hiddenBelowPx] pairs (null: always shown; 900 or
 * 480), so an iPad shows "32 min ago" and a phone "32 min" of "Updated 32 min ago", while a screen reader and the title
 * keep the whole of it.
 */
export function pill({ kind = "quiet", label, tap = false, onClick, dot = null, more = null, parts = null } = {}) {
  const safeKind = PILL_KINDS.has(kind) ? kind : "quiet";
  const words = text(label ?? defaultLabel(safeKind));
  const dotted = DOTS.has(dot);
  const spelled = Array.isArray(parts) && parts.length ? parts.filter((p) => Array.isArray(p) && typeof p[0] === "string") : null;
  const labelEl = el("span", { class: "pill__label" }, spelled ? spelled.map(([bit, below]) => (below === 900 || below === 480 ? el("span", { class: `pill__word pill__word--${below}` }, bit) : bit)) : words);
  const moreWords = typeof more === "string" && more.trim() ? more.trim() : null;
  const children = [dotted ? el("span", { class: `pill__dot pill__dot--${dot}`, "aria-hidden": "true" }) : null, labelEl, moreWords ? el("span", { class: "pill__more" }, ` · ${moreWords}`) : null];
  const whole = moreWords ? `${words} · ${moreWords}` : words;
  const cls = `pill pill--${safeKind}${dotted ? " pill--dotted" : ""}${tap ? " pill--tap" : ""}`;
  if (typeof onClick === "function") {
    return el("button", { class: `${cls} pill--button`, type: "button", "aria-haspopup": "dialog", title: whole, onclick: onClick }, ...children);
  }
  return el("span", { class: cls, role: "status" }, ...children);
}

function defaultLabel(kind) {
  return { live: "Live", delayed: "Delayed", stale: "Stale", offline: "Offline", replay: "Replay", quiet: "Connecting" }[kind];
}

export const KEY_PLAYS = {
  td: { icon: "star", label: "TD", title: "Touchdown" },
  turnover: { icon: "turnover", label: "TO", title: "Turnover" },
  explosive: { icon: "explosive", label: "Big play", title: "Run of 10 or more, or pass of 20 or more" },
  sack: { icon: "sack", label: "Sack", title: "Sack" },
  fourth: { glyph: "4", label: "4th down", title: "Fourth-down attempt" },
  penalty: { icon: "flag", label: "Flag 15", title: "Penalty of 15 yards" },
};

/** keyPlayBadge("td") */
export function keyPlayBadge(flag) {
  const spec = KEY_PLAYS[flag];
  if (!spec) return null;
  return el(
    "span",
    { class: `kp kp--${flag}`, title: spec.title },
    el("span", { class: "kp__glyph", "aria-hidden": "true" }, spec.icon ? icon(spec.icon) : spec.glyph), // Phase 16 wave 3: the sprite
    spec.label,
  );
}

export function keyPlayBadges(flags) {
  return (Array.isArray(flags) ? flags : []).map(keyPlayBadge).filter(Boolean);
}
