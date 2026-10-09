// The app's icons (Phase 16 wave 3, audit DS-09, owner pick 3B): one sprite, static/icons/ui.svg, drawn the same on every
// device in the theme's colors, instead of font symbols and emoji some tablets can't draw (the stars, play, flag, turnover and back marks, the weather).
//
//   icon(name, { label, className, size })  -> <svg class="icon icon--name"> using the sprite; decorative unless labelled
//   ICONS                                     the names the sprite has

import { el } from "./dom.js";

const SPRITE = "/static/icons/ui.svg";
const NS = "http://www.w3.org/2000/svg";
export const ICONS = [
  "search", "play", "pause", "star", "star-empty", "turnover", "sack", "flag", "ball", "explosive", "sort-down", "sort-up",
  "chevron-down", "chevron-right", "back", "close", "dot", "dot-half", "dot-empty",
  "sun", "partly", "cloud", "rain", "snow", "storm", "fog", "stadium",
];

export function icon(name, { label, className, size } = {}) {
  const known = ICONS.includes(name) ? name : null;
  if (!known || typeof document === "undefined" || typeof document.createElementNS !== "function") return label ? el("span", { class: "sr-only" }, label) : null;
  try {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", `icon icon--${known}${className ? ` ${className}` : ""}`);
    svg.setAttribute("viewBox", "0 0 24 24");
    if (size) {
      svg.setAttribute("width", String(size));
      svg.setAttribute("height", String(size));
    }
    if (label) {
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", label);
    } else {
      svg.setAttribute("aria-hidden", "true");
    }
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS(NS, "use");
    use.setAttribute("href", `${SPRITE}#i-${known}`);
    svg.append(use);
    return svg;
  } catch {
    return label ? el("span", { class: "sr-only" }, label) : null;
  }
}
