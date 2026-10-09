// Spoiler mode (Phase 19, owner 2026-10-08: "spoiler mode for DVR games"). Watching a recorded game, you do not want the
// app to tell you the score. This device-level switch (kept in this browser, not on the server) blurs everything that
// gives a result away: the cover's score and final, the W/L squares, the schedule results, the score ticker and Scores
// table, the live strip and win probability, the box-score header, the play log; since the final pass also the
// score-by-quarter line, every live game's points in Scores, the W/L squares on team headers and standings, the
// band summaries that carry a score (.score-words), and Season in review. A tap on a blurred item shows that
// item; "Show all" in the small bar at the bottom shows everything until the switch is turned back on.
//
//   spoilerOn() / setSpoiler(on)    read and change the switch (and the page class that does the blurring)
//   installSpoiler()                apply the saved choice, listen for taps, draw the bar
//   SPOILER_SELECTORS               what is hidden (the CSS in components.css lists the same classes)

import { el } from "./dom.js";

const KEY = "kickoff.spoiler";
export const SPOILER_SELECTORS = [".cover__score", ".cover__state--final", ".cover__result", ".form-guide", ".sched__res", ".res--w", ".res--l", ".res--t", ".scores__pts--win", ".scores__pts--lose", ".scores__pts", ".qline", ".form__sq", ".score-words", ".ticker__game", ".strip__score", ".strip__final", ".box-head__score", ".wpbar", ".wp", ".cover__wp-label", ".play-log", ".gl-result"];

let on = false;
let bar = null;

function read() {
  try {
    return window.localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

function write(value) {
  try {
    window.localStorage.setItem(KEY, value ? "on" : "off");
  } catch {
    // blocked storage: the switch works until the page closes
  }
}

export function spoilerOn() {
  return on;
}

function showAll(shown) {
  document.body.classList.toggle("spoiler-all", shown);
  if (bar) bar.querySelector("button").textContent = shown ? "Hide again" : "Show all";
}

export function setSpoiler(value) {
  on = Boolean(value);
  write(on);
  document.body.classList.toggle("spoiler-on", on);
  if (!on) document.body.classList.remove("spoiler-all");
  if (on && !bar) {
    bar = el("div", { class: "spoiler-bar", role: "status" }, el("span", {}, "Spoiler mode: scores are hidden. Tap one to show it."), el("button", { class: "btn btn--quiet", type: "button", onclick: () => showAll(!document.body.classList.contains("spoiler-all")) }, "Show all"));
    document.body.append(bar);
  }
  if (!on && bar) {
    bar.remove();
    bar = null;
  }
  for (const node of document.querySelectorAll?.(".spoiler-shown") || []) node.classList.remove("spoiler-shown");
  document.dispatchEvent(new CustomEvent("kickoff:spoiler", { detail: { on } }));
  return on;
}

export function installSpoiler() {
  document.addEventListener("click", (event) => {
    if (!on || document.body.classList.contains("spoiler-all")) return;
    const hidden = event.target?.closest?.(SPOILER_SELECTORS.join(","));
    if (hidden && !hidden.classList.contains("spoiler-shown")) {
      event.preventDefault();
      event.stopPropagation(); // the first tap only shows; a second tap does what the item does
      hidden.classList.add("spoiler-shown");
    }
  }, true);
  setSpoiler(read());
}
