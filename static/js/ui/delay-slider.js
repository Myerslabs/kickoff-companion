// The spoiler-delay slider (L6): 0 to 120 seconds, easy to nudge by 5, saved on the device.
// The value follows the thumb while it moves, but onChange fires once, when the thumb is let go;
// the -5 and +5 buttons wait 400 ms after the last tap, so three quick taps are one change. A value
// that ends where it started announces nothing, so the live sheet does not reconnect for nothing.

import { el, isNum, recall, remember } from "./dom.js";

const KEY = "spoiler-delay";
const NUDGE_SETTLE_MS = 400;

export function savedDelay(fallback = 0) {
  const value = recall(KEY, fallback);
  return isNum(value) ? value : fallback;
}

/**
 * delaySlider({ value, min, max, step, onChange, label })
 * Returns the element with setDelay(value) (set without announcing) and flush() (announce a
 * pending nudge now, for a view that is going away).
 */
export function delaySlider({ value = savedDelay(), min = 0, max = 120, step = 5, onChange, label = "Spoiler delay. Applies to every live panel. Radio audio cannot be delayed." } = {}) {
  const clamp = (next) => Math.min(max, Math.max(min, Math.round(next / step) * step));
  let current = clamp(isNum(value) ? value : 0);
  let announced = current;
  let settle = null;
  const range = el("input", { type: "range", min: String(min), max: String(max), step: String(step), value: String(current), "aria-label": "Delay in seconds" });
  const valueEl = el("span", { class: "delay__value" }, `${current} s`);

  function show(next) {
    if (!isNum(next)) return; // a range input that reports nothing usable leaves the value alone
    current = clamp(next);
    range.value = String(current);
    valueEl.textContent = `${current} s`;
  }

  function announce() {
    clearTimeout(settle);
    settle = null;
    if (current === announced) return;
    announced = current;
    remember(KEY, current);
    if (typeof onChange === "function") onChange(current);
  }

  function nudge(delta) {
    show(current + delta);
    clearTimeout(settle);
    settle = setTimeout(announce, NUDGE_SETTLE_MS);
  }

  range.addEventListener("input", () => show(Number(range.value)));
  range.addEventListener("change", () => {
    show(Number(range.value));
    announce();
  });
  const minus = el("button", { class: "btn icon-btn", type: "button", "aria-label": "5 seconds less", onclick: () => nudge(-step) }, "−5");
  const plus = el("button", { class: "btn icon-btn", type: "button", "aria-label": "5 seconds more", onclick: () => nudge(step) }, "+5");
  const root = el("div", { class: "delay", role: "group", "aria-label": "Spoiler delay" }, el("span", { class: "delay__label" }, label), minus, range, plus, valueEl);
  root.setDelay = (next) => {
    clearTimeout(settle);
    settle = null;
    show(next);
    announced = current;
    remember(KEY, current);
  };
  root.flush = () => {
    if (settle !== null) announce();
  };
  return root;
}
