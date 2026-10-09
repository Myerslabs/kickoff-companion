// The announcer (Phase 17 #15, owner 2026-10-07: "these little stat blurbs are really cool, can we have a little
// cartoon announcer or something call them out?"; answer: "Same animation, but thrown in for each callout.
// Something very basic at first"). A small line-drawn figure in a headset sits before each band summary that
// carries a number (the stat blurbs: "SWT better in 14 of 24", not "tap a game"). When the blurb first scrolls
// into view he talks for a moment, then sits still; a changed blurb is called again. Nothing moves with reduced
// motion set, and Settings > Display > Announcer hides him (the "announcer-off" class on the root).
//
//   isBlurb(summary)            true for a summary with a digit in it
//   announcer(key)              -> the <svg>, or null outside a browser; key (band id + text) says what he has called
//   applyAnnouncer(on)          the root class; prefs.js calls it with the setting
//   TALK_MS                     how long one callout lasts

import { text } from "./dom.js";

export const TALK_MS = 1600;
const NS = "http://www.w3.org/2000/svg";
const called = new Set(); // what has been called this page load: a refresh of the same blurb stays quiet
let observer = null;

export function isBlurb(summary) {
  return typeof summary === "string" ? /\d/.test(summary) : false;
}

export function applyAnnouncer(on = true) {
  if (typeof document === "undefined" || !document.documentElement?.classList) return;
  document.documentElement.classList.toggle("announcer-off", on === false);
}

function talk(svg) {
  if (!svg || !svg.classList) return;
  svg.classList.add("announcer--talking");
  setTimeout(() => svg.classList.remove("announcer--talking"), TALK_MS);
}

function watcher() {
  if (observer || typeof IntersectionObserver !== "function") return observer;
  observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      observer.unobserve(entry.target);
      const key = entry.target.dataset?.call;
      if (key && called.has(key)) continue;
      if (key) called.add(key);
      talk(entry.target);
    }
  }, { threshold: 1 });
  return observer;
}

function shape(tag, attrs) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

export function announcer(key) {
  if (typeof document === "undefined" || typeof document.createElementNS !== "function") return null;
  try {
    const svg = shape("svg", { viewBox: "0 0 24 24", class: "announcer", "aria-hidden": "true", focusable: "false" });
    svg.append(
      shape("circle", { cx: "12", cy: "12", r: "7", class: "announcer__head" }),
      shape("path", { d: "M4.5 11 Q12 1.5 19.5 11", class: "announcer__band" }),
      shape("rect", { x: "3", y: "9.5", width: "3", height: "5.5", rx: "1.4", class: "announcer__cup" }),
      shape("rect", { x: "18", y: "9.5", width: "3", height: "5.5", rx: "1.4", class: "announcer__cup" }),
      shape("path", { d: "M5 14.5 Q6.5 19 10.5 18.2", class: "announcer__boom" }),
      shape("circle", { cx: "10.8", cy: "18.1", r: "1.5", class: "announcer__mic" }),
      shape("circle", { cx: "10", cy: "10.5", r: "0.95", class: "announcer__eye" }),
      shape("circle", { cx: "14.4", cy: "10.5", r: "0.95", class: "announcer__eye" }),
      shape("ellipse", { cx: "12.6", cy: "14.4", rx: "1.9", ry: "1.2", class: "announcer__mouth" }),
    );
    const id = text(key);
    if (id && id !== "–") svg.dataset.call = id;
    const watch = watcher();
    if (watch) watch.observe(svg);
    return svg;
  } catch {
    return null;
  }
}
