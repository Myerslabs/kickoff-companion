// The Top button (owner 2026-11-15: "there needs to be an action to throw you back to the top of the page, as some pages are
// a little long"; his pick, a floating button at the bottom right): a small round "Top" with an up chevron that comes up
// once the page has been scrolled about a screen down and goes again above half a screen. A tap takes the page to its top,
// smoothly unless the reader asked for less motion. It sits above the radio dock, below every sheet and card (their scrim
// covers it), and never shows on the game-day board or in print, or while a side sheet or the player card is open (they lie
// on the page where the reader is, so the page's top would leave them behind). Tapping the tab of the page on screen still
// goes to its top as well (ENH-33).
//
//   installToTop({ host })              -> the button, put once on the page (a second call hands back the same one)
//   shouldShow(scrollY, height, shown)  -> whether it shows: from one screen down, until back above half a screen.
//                                          Exported for the tests.

import { el, reducedMotion } from "./dom.js";
import { icon } from "./icons.js";

const SHOW_AT = 1; // screens down before it comes up
const HIDE_AT = 0.5; // and above which it goes again, so a small scroll back never makes it blink

export function shouldShow(scrollY, height, shown) {
  if (!Number.isFinite(scrollY) || !Number.isFinite(height) || height <= 0) return false;
  return scrollY >= height * (shown ? HIDE_AT : SHOW_AT);
}

let button = null;

/** A sheet, the card or the board over the page: the button stays down. */
function covered() {
  try {
    return Boolean(document.querySelector(".card-layer, .sheet-layer")) || Boolean(document.body?.classList?.contains("board-mode"));
  } catch {
    return false;
  }
}

export function installToTop({ host = null } = {}) {
  if (button && button.isConnected) return button;
  if (typeof document === "undefined" || typeof window === "undefined" || typeof window.addEventListener !== "function") return null;
  let shown = false;
  const go = () => {
    try {
      window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" });
    } catch {
      window.scrollTo(0, 0); // an older browser takes only the two numbers
    }
    // no focus to move: the button hides once the page is back at its top, and a keyboard's next Tab starts from the top
  };
  button = el(
    "button",
    { class: "to-top", type: "button", hidden: true, "aria-label": "Back to the top of the page", title: "Back to the top", onclick: go },
    icon("chevron-down", { className: "to-top__icon" }),
    el("span", { class: "to-top__word" }, "Top"),
  );
  // run on every scroll event, not a frame later: the look is one comparison and one selector, and a frame callback never
  // comes in a page the browser has put in the background (Safari, the desktop app's hidden pane), which left it down
  const check = () => {
    const want = !covered() && shouldShow(Number(window.scrollY), Number(window.innerHeight), shown);
    if (want === shown) return;
    shown = want;
    if (want) button.removeAttribute("hidden");
    else button.setAttribute("hidden", "");
  };
  window.addEventListener("scroll", check, { passive: true });
  window.addEventListener("resize", check, { passive: true });
  window.addEventListener("hashchange", check); // a new page starts at its top: the button goes with the old one
  (host || document.body).append(button);
  check();
  return button;
}
