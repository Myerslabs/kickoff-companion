// Will the wind affect the kick? (Phase 17 #6, owner 2026-10-07: "just a basic representation of if the wind will
// affect the kick"; two looks.) A small goalpost with a flag beside the weather: under 15 mph the flag hangs and the
// line says no effect; 15 mph and up it flies and the line says the wind affects kicks; indoors there is no wind.
// From the wind speed the weather already carries (CFBD on Tier 2, else the National Weather Service).
//
//   kickWind({ windMph, indoors })  -> <span class="kick-wind"> or null (no speed and not indoors)
//   kickWindLevel(windMph, indoors) -> "indoors" | "calm" | "windy" | null
//   WINDY_MPH                         15

import { el, isNum } from "./dom.js";

export const WINDY_MPH = 15;
const NS = "http://www.w3.org/2000/svg";
const WORDS = { indoors: "Indoors: no wind on kicks", calm: "Wind won't affect kicks", windy: "Wind will affect kicks" };

export function kickWindLevel(windMph, indoors) {
  if (indoors === true) return "indoors";
  if (!isNum(windMph) || windMph < 0) return null;
  return windMph >= WINDY_MPH ? "windy" : "calm";
}

function shape(tag, attrs) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

/** The goalpost: uprights and crossbar, and a flag on the left upright that hangs (calm) or flies (windy). */
function post(level) {
  if (typeof document === "undefined" || typeof document.createElementNS !== "function") return null;
  try {
    const svg = shape("svg", { viewBox: "0 0 28 24", class: "kick-wind__post", "aria-hidden": "true", focusable: "false" });
    svg.append(
      shape("path", { d: "M14 23 V14 M6 14 H22 M6 14 V2 M22 14 V2", class: "kick-wind__bar" }),
      level === "windy"
        ? shape("path", { d: "M6 2.5 L13.5 4 L6 6 Z", class: "kick-wind__flag" })
        : shape("path", { d: "M6 2.5 L7.6 7.5 L6 8 Z", class: "kick-wind__flag" }),
    );
    return svg;
  } catch {
    return null;
  }
}

export function kickWind({ windMph, indoors = false } = {}) {
  const level = kickWindLevel(windMph, indoors);
  if (!level) return null;
  const words = WORDS[level];
  return el("span", { class: `kick-wind kick-wind--${level}`, title: level === "indoors" ? words : `${words} (${Math.round(windMph)} mph; ${WINDY_MPH} mph and up moves a kick)` }, post(level), el("span", { class: "kick-wind__text" }, words));
}
