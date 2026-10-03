// The team's palette (public release Phase 3): the surfaces take the hue of the team's primary
// color and the accent is its brightest usable color, so a navy-and-orange team reads navy and orange
// and any other team reads in its own colors. tokens.css holds the default palette (used until
// the identity loads, or when CFBD gave no colors); paintTeam() overrides the same custom
// properties on <html> for the current light or dark theme. Every text and fill pair is checked
// for contrast, and a color that cannot pass is moved in lightness until it does.

const PROPS = [
  "--ground", "--panel", "--panel-raised", "--rule", "--rule-strong", "--band-head", "--table-head", "--row-alt",
  "--row-hover", "--row-group", "--row-rule", "--sorted-col", "--us-row", "--fog", "--mist", "--team-primary", "--team-accent",
];

export function hexToRgb(hex) {
  if (typeof hex !== "string") return null;
  const clean = hex.trim().replace(/^#/, "");
  const full = clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean;
  if (!/^[0-9a-f]{6}$/i.test(full)) return null;
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
}

function rgbToHex([r, g, b]) {
  return `#${[r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("")}`;
}

export function rgbToHsl([r, g, b]) {
  const [rn, gn, bn] = [r / 255, g / 255, b / 255];
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = max === rn ? (gn - bn) / d + (gn < bn ? 6 : 0) : max === gn ? (bn - rn) / d + 2 : (rn - gn) / d + 4;
  h *= 60;
  return [h, s, l];
}

export function hslToHex(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return rgbToHex([(r + m) * 255, (g + m) * 255, (b + m) * 255]);
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
  if (!a || !b) return 1;
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Move a color's lightness (keeping hue and saturation) until it holds `ratio` against `bg`. */
export function ensureContrast(hex, bg, ratio, direction) {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex;
  if (contrastRatio(hex, bg) >= ratio) return hex;
  const [h, s, l] = rgbToHsl(rgb);
  const step = direction === "darker" ? -0.02 : 0.02;
  for (let k = 1; k <= 50; k += 1) {
    const next = hslToHex(h, s, Math.max(0, Math.min(1, l + step * k)));
    if (contrastRatio(next, bg) >= ratio) return next;
  }
  return direction === "darker" ? "#000000" : "#ffffff";
}

function rgba(hex, alpha) {
  const rgb = hexToRgb(hex) || [128, 128, 128];
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
}

/** The palette for a team's colors in "dark" or "light", or null when the colors are unusable. */
export function teamPalette(color, altColor, mode = "dark") {
  const primary = hexToRgb(color);
  if (!primary) return null;
  const [h, sRaw] = rgbToHsl(primary);
  const gray = sRaw < 0.12;
  const hue = gray ? 225 : h;
  const sat = gray ? 0.18 : Math.max(0.3, Math.min(0.6, sRaw));
  const dark = mode !== "light";
  const L = dark
    ? { ground: 0.11, panel: 0.17, raised: 0.21, rule: 0.31, ruleStrong: 0.4, bandHead: 0.22, tableHead: 0.25, rowAlt: 0.2, rowHover: 0.27, rowGroup: 0.23, rowRule: 0.23 }
    : { ground: 0.95, panel: 1, raised: 0.92, rule: 0.85, ruleStrong: 0.77, bandHead: 0.97, tableHead: 0.93, rowAlt: 0.96, rowHover: 0.92, rowGroup: 0.955, rowRule: 0.9 };
  const surf = (key, s = sat) => hslToHex(hue, dark ? s : s * 0.55, L[key]);
  const panel = surf("panel");
  const fog = ensureContrast(hslToHex(hue, dark ? 0.32 : 0.3, dark ? 0.7 : 0.38), panel, 4.5, dark ? "lighter" : "darker");
  const mist = ensureContrast(hslToHex(hue, dark ? 0.28 : 0.26, dark ? 0.64 : 0.44), panel, 4.5, dark ? "lighter" : "darker");
  // The accent: the team color that reads best on the panel, nudged until it holds 3:1.
  const candidates = [altColor, color].filter((c) => {
    const rgb = hexToRgb(c);
    if (!rgb) return false;
    const [, s, l] = rgbToHsl(rgb);
    return s >= 0.25 && l > 0.12 && l < 0.92; // white, black and grays make poor accents
  });
  // The second color is the accent whenever it reads (an orange second color, in both themes); else the best reader.
  const passing = candidates.find((c) => contrastRatio(c, panel) >= 3);
  const best = [...candidates].sort((a, b) => contrastRatio(b, panel) - contrastRatio(a, panel))[0];
  const accent = passing || ensureContrast(best || hslToHex(hue, 0.75, dark ? 0.6 : 0.4), panel, 3, dark ? "lighter" : "darker");
  // The primary as a fill under chalk text (pressed buttons, our band heads): dark enough for 4.5:1 with white.
  const fill = ensureContrast(hslToHex(hue, gray ? 0.2 : Math.max(0.45, sRaw), Math.min(0.45, rgbToHsl(primary)[2])), "#f2f4fa", 4.5, "darker");
  return {
    "--ground": surf("ground"),
    "--panel": panel,
    "--panel-raised": surf("raised"),
    "--rule": surf("rule"),
    "--rule-strong": surf("ruleStrong"),
    "--band-head": surf("bandHead"),
    "--table-head": surf("tableHead"),
    "--row-alt": surf("rowAlt"),
    "--row-hover": surf("rowHover"),
    "--row-group": surf("rowGroup"),
    "--row-rule": surf("rowRule"),
    "--sorted-col": rgba(accent, dark ? 0.08 : 0.07),
    "--us-row": rgba(accent, dark ? 0.13 : 0.11),
    "--fog": fog,
    "--mist": mist,
    "--team-primary": fill,
    "--team-accent": accent,
  };
}

/** Paint the team's palette on <html> for `mode`, or clear it (back to tokens.css) when there is none. */
export function paintTeam(identity, mode = "dark", root = globalThis.document?.documentElement) {
  const style = root && root.style;
  if (!style || typeof style.setProperty !== "function") return null;
  const palette = identity && identity.color ? teamPalette(identity.color, identity.altColor, mode) : null;
  for (const prop of PROPS) {
    if (palette) style.setProperty(prop, palette[prop]);
    else if (typeof style.removeProperty === "function") style.removeProperty(prop);
  }
  return palette;
}
