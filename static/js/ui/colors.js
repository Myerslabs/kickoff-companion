// Runtime opponent colors (docs/03-DESIGN.md): the opponent's color must hold 3:1 against
// the panel for fills, must not sit within 20 degrees of hue of our own two colors
// (or the two sides read as one team), and text on it must be the more legible of chalk
// and the ground. Anything that fails falls back to a neutral.

import { ours } from "../identity.js";

const DEFAULT_PANEL = "#1C1F26"; // Phase 17 #34: the charcoal panel
const CHALK = "#ECEEF2";
const GROUND = "#14161B";
const NEUTRAL = "#7C8494";
const NEUTRAL_ALT = "#9AA1AE";
const MIN_CONTRAST = 3;
const MIN_HUE_GAP = 20;

export function hexToRgb(hex) {
  if (typeof hex !== "string") return null;
  const clean = hex.trim().replace(/^#/, "");
  const full = clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean;
  if (!/^[0-9a-f]{6}$/i.test(full)) return null;
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
}

function luminance(rgb) {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(hexA, hexB) {
  const a = hexToRgb(hexA);
  const b = hexToRgb(hexB);
  if (!a || !b) return 0;
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Hue in degrees and saturation 0..1, or null for a grey. */
export function hueOf(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  const [r, g, b] = rgb.map((v) => v / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  if (delta < 0.08) return null; // too grey to have a hue worth comparing
  let hue;
  if (max === r) hue = ((g - b) / delta) % 6;
  else if (max === g) hue = (b - r) / delta + 2;
  else hue = (r - g) / delta + 4;
  hue = (hue * 60 + 360) % 360;
  return { hue, saturation: max === 0 ? 0 : delta / max };
}

function hueGap(hexA, hexB) {
  const a = hueOf(hexA);
  const b = hueOf(hexB);
  if (!a || !b) return 180;
  const diff = Math.abs(a.hue - b.hue) % 360;
  return diff > 180 ? 360 - diff : diff;
}

/** Why a candidate was rejected, or null if it is usable. */
/** The panel color in use: the team palette's when theme.js painted one, else the default. */
function panelColor() {
  const painted = globalThis.document?.documentElement?.style?.getPropertyValue?.("--panel");
  return typeof painted === "string" && hexToRgb(painted.trim()) ? painted.trim() : DEFAULT_PANEL;
}

export function rejectReason(hex, own = [ours().color, ours().altColor]) {
  if (!hexToRgb(hex)) return "not a color";
  const panel = panelColor();
  if (contrastRatio(hex, panel) < MIN_CONTRAST) return `only ${contrastRatio(hex, panel).toFixed(1)}:1 against the panel`;
  for (const mine of own) {
    if (hexToRgb(mine) && hueGap(hex, mine) < MIN_HUE_GAP) return `too close to our color ${mine}`;
  }
  return null;
}

/** Pick the first candidate that passes contrast and hue checks, else the neutral. */
export function pickOpponentColor(candidates) {
  const notes = [];
  for (const candidate of candidates) {
    if (!candidate) continue;
    const reason = rejectReason(candidate);
    if (!reason) return { color: candidate, notes };
    notes.push(`${candidate} rejected: ${reason}`);
  }
  return { color: NEUTRAL, notes: [...notes, "using the neutral"] };
}

/** applyOpponentColors({ color, altColor }) sets --opp, --opp-alt, --opp-text on the root. */
export function applyOpponentColors(team, root = document.documentElement) {
  const picked = pickOpponentColor([team?.color, team?.altColor]);
  const color = picked.color;
  const altCandidates = [team?.altColor, team?.color].filter((c) => c && c.toLowerCase() !== color.toLowerCase());
  const alt = altCandidates.find((c) => !rejectReason(c)) || NEUTRAL_ALT;
  const textColor = contrastRatio(CHALK, color) >= contrastRatio(GROUND, color) ? CHALK : GROUND;
  root.style.setProperty("--opp", color);
  root.style.setProperty("--opp-alt", alt);
  root.style.setProperty("--opp-text", textColor);
  return { color, alt, textColor, contrast: contrastRatio(color, panelColor()), notes: picked.notes };
}
