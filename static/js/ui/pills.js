// Status pills and key-play badges. Never color alone: every pill has a word and a shape,
// every badge has a glyph and a label.

import { icon } from "./icons.js";
import { el, text } from "./dom.js";

const PILL_KINDS = new Set(["live", "delayed", "stale", "offline", "replay", "quiet"]);

/**
 * pill({ kind: "live"|"delayed"|"stale"|"offline"|"replay"|"quiet", label, tap, onClick })
 * With `onClick` the pill is a button (Phase 16 wave 3, DS-12: the top bar's pill opens the status card).
 * The words sit in their own .pill__label, so the top bar can shorten them with "…" inside the pill (item 6, step F)
 * without clipping the pill's 44 px press area; the button keeps the whole label as its title.
 */
export function pill({ kind = "quiet", label, tap = false, onClick } = {}) {
  const safeKind = PILL_KINDS.has(kind) ? kind : "quiet";
  const words = text(label ?? defaultLabel(safeKind));
  if (typeof onClick === "function") {
    return el(
      "button",
      { class: `pill pill--${safeKind} pill--button${tap ? " pill--tap" : ""}`, type: "button", "aria-haspopup": "dialog", title: words, onclick: onClick },
      el("span", { class: "pill__label" }, words),
    );
  }
  return el(
    "span",
    { class: `pill pill--${safeKind}${tap ? " pill--tap" : ""}`, role: "status" },
    el("span", { class: "pill__label" }, words),
  );
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
