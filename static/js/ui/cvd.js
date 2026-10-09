// Color-blind friendly colors (Phase 19, owner 2026-10-08 accepted the idea). This device swaps green and red for the blue
// and orange pair that stay apart for the common kinds of color blindness, and the rank chips gain a shape (an up
// triangle for the top quarter, a dot for the middle, a down triangle for the bottom) so color is never the only signal.
// Kept in this browser, like the text size.
//
//   cvdOn() / setCvd(on)    read and change the switch (the page class `cvd-safe` does the work, in components.css)
//   installCvd()            apply the saved choice at start

const KEY = "kickoff.cvd";
let on = false;

function read() {
  try {
    return window.localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

export function cvdOn() {
  return on;
}

export function setCvd(value) {
  on = Boolean(value);
  try {
    window.localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    // blocked storage: it applies until the page closes
  }
  document.body.classList.toggle("cvd-safe", on);
  return on;
}

export function installCvd() {
  setCvd(read());
}
