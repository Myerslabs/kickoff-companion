// Status pills and key-play badges. Never color alone: every pill has a word and a shape,
// every badge has a glyph and a label.

import { el, text } from "./dom.js";

const PILL_KINDS = new Set(["live", "delayed", "stale", "offline", "replay", "quiet"]);

/** pill({ kind: "live"|"delayed"|"stale"|"offline"|"replay"|"quiet", label, tap }) */
export function pill({ kind = "quiet", label, tap = false } = {}) {
  const safeKind = PILL_KINDS.has(kind) ? kind : "quiet";
  return el(
    "span",
    { class: `pill pill--${safeKind}${tap ? " pill--tap" : ""}`, role: "status" },
    text(label ?? defaultLabel(safeKind)),
  );
}

function defaultLabel(kind) {
  return { live: "Live", delayed: "Delayed", stale: "Stale", offline: "Offline", replay: "Replay", quiet: "Connecting" }[kind];
}

export const KEY_PLAYS = {
  td: { glyph: "★", label: "TD", title: "Touchdown" },
  turnover: { glyph: "⊗", label: "TO", title: "Turnover" },
  explosive: { glyph: "»", label: "Big play", title: "Run of 10 or more, or pass of 20 or more" },
  sack: { glyph: "↓", label: "Sack", title: "Sack" },
  fourth: { glyph: "4", label: "4th down", title: "Fourth-down attempt" },
  penalty: { glyph: "⚑", label: "Flag 15", title: "Penalty of 15 yards" },
};

/** keyPlayBadge("td") */
export function keyPlayBadge(flag) {
  const spec = KEY_PLAYS[flag];
  if (!spec) return null;
  return el(
    "span",
    { class: `kp kp--${flag}`, title: spec.title },
    el("span", { class: "kp__glyph", "aria-hidden": "true" }, spec.glyph),
    spec.label,
  );
}

export function keyPlayBadges(flags) {
  return (Array.isArray(flags) ? flags : []).map(keyPlayBadge).filter(Boolean);
}
