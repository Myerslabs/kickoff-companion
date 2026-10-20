// The game-day board (Phase 18.6, owner 2026-10-08: "a monitor plugged into the PC", also a view a phone can cast).
// The Live sheet made for a wall: the shell's top bar and tabs and the touch controls are hidden, everything is drawn
// larger, the score, the plays and the ticker stay, and a QR code in the corner lets a friend join. It is the same
// live view underneath, so it can never disagree with the Live sheet.
//
// The way out (item 6, step A, owner 2026-10-11): a small "Leave big screen" chip, outside the zoomed page (top right,
// clear of the bars along the bottom), hidden until the mouse moves, a key is pressed or the screen is tapped, and gone
// again a few seconds later so the TV stays clean (the same moment brings the mouse pointer back). It goes back to the
// page the board was opened from (In Game), as the browser's Back does; Escape, Backspace and a TV remote's Back key do
// the same. A cold start at the board puts In Game under it, so Back never leaves the app.
// The layout (queue item 7, the owner's mock of 2026-10-11) is the live view's (views/live.js buildTv): this view puts
// the QR in its middle cell and the radio at the left of the score strip's bar, always there (owner 2026-10-11: "the radio
// is always available in the big screen ... even before the game"): it plays the station, pauses a stream, stops an
// embedded player, or, with no station to play here, opens the station list.
//
//   createBoardView({ onStatus })   mounts the live view in board mode and puts it back when it unmounts
//   boardZoom(width)                the zoom for a screen this wide
//   leaveBoard()                    back to the app's page under the board, else In Game in the board's place
//   seedBoardHistory()              a cold start at #board: In Game goes under it in the history (app.js show())
//   isExitKey(event)                Escape, Backspace, the browser's Back key and the TV remotes' Back keys

import { el, replaceWith, text } from "../ui/dom.js";
import { icon } from "../ui/icons.js";
import { radioSnapshot, rememberedSource, startRadio, stopRadio, subscribeRadio, toggleRadio } from "../radio.js";
import { radioStations } from "../ui/radio-stations.js";
import { openSheet } from "../ui/remote.js";
import { createLiveView } from "./live.js";
import { inviteBody, loadInvite } from "./invite.js";

const BOARD_CLASS = "board-mode";
const AWAKE_CLASS = "board-awake"; // the chip shows and the mouse pointer comes back
export const AWAKE_MS = 3000;
export const REVEAL_MS = 400; // a tap where the hidden chip sits only reveals it
const FALLBACK_MS = 800; // a Back that went nowhere: In Game instead
const WAKE_EVENTS = ["pointermove", "pointerdown", "mousemove", "touchstart"]; // the last two for TV browsers without pointer events
const EXIT_KEYS = new Set(["Escape", "Esc", "Backspace", "BrowserBack", "GoBack", "XF86Back"]);
const EXIT_CODES = new Set([461, 10009]); // the Back key on LG webOS and Samsung Tizen remotes
// a layer the reader opened takes Escape first: sheets, the player card and the menu (all [data-modal]), a stat's hint card
const LAYERS = "[data-modal], .hint-pop, .status-card";
const BOARD_HASH = /^#board(?:$|[=?])/;

/** The zoom for this screen (freeze wave F5, owner 2026-10-20: the board mirrors the tablet, so the 1180 by 820 stage is
 *  scaled to fill whatever shows it: a 1080p set 1.32, a 4K set 2.63, a mirrored iPad 1). A phone or an iPad held upright
 *  (under 960 by 560) draws the essentials at their own size instead. */
export const STAGE_WIDTH = 1180;
export const STAGE_HEIGHT = 820;
export function boardZoom(width, height = NaN) {
  if (!Number.isFinite(width) || width <= 0) return 1;
  if (!Number.isFinite(height) || height <= 0) return width >= 3000 ? 2 : 1;
  if (width < 960 || height < 560) return 1;
  const zoom = Math.min(width / STAGE_WIDTH, height / STAGE_HEIGHT);
  return Math.max(0.75, Math.min(3, Math.round(zoom * 100) / 100));
}

/** Whether a key press asks to leave the board: Escape, Backspace, the browser's Back key or a TV remote's Back key. */
export function isExitKey(event) {
  if (!event || typeof event !== "object" || event.ctrlKey || event.metaKey || event.altKey) return false;
  return EXIT_KEYS.has(event.key) || EXIT_CODES.has(Number(event.keyCode));
}

function isTyping(target) {
  return Boolean(target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable));
}

function historyDepth() {
  try {
    const depth = typeof history !== "undefined" ? history.state?.depth : null; // app.js numbers its own entries
    return typeof depth === "number" && Number.isFinite(depth) ? depth : null;
  } catch {
    return null;
  }
}

/** Back to the page the board was opened from when that entry is the app's own (backRow's rule, ui/states.js), else In
 *  Game in place of the board's entry, so Back cannot return to the board. Returns "back" or "replace". */
export function leaveBoard() {
  const depth = historyDepth();
  if (depth !== null && depth > 0) {
    try {
      history.back();
      return "back";
    } catch (error) {
      console.warn("Back did not run; going to In Game.", error?.message || error);
    }
  }
  window.location.replace("#live");
  return "replace";
}

/** A cold start at the board (the kiosk window, a bookmark, a reload of one, the home-screen icon) has no app page
 *  under it, so the browser's Back would leave the app. Its entry becomes In Game and a new board entry goes on top;
 *  neither fires hashchange, so the board stays mounted. True when the history was seeded. */
export function seedBoardHistory() {
  let state = {};
  let hash = "#board";
  try {
    const current = history.state;
    state = current && typeof current === "object" ? current : {};
    const now = String(window.location.hash || "");
    hash = BOARD_HASH.test(now) ? now : "#board";
    history.replaceState({ ...state, depth: 0 }, "", "#live");
  } catch (error) {
    console.warn("Could not put In Game under the board; Back may leave the app.", error?.message || error);
    return false;
  }
  try {
    history.pushState({ depth: 1 }, "", hash);
    return true;
  } catch (error) {
    try {
      history.replaceState(state, "", hash); // the board's own entry back as it was
    } catch {
      // the address keeps #live; the board on screen is unchanged and the next route puts it right
    }
    console.warn("Could not put In Game under the board; Back may leave the app.", error?.message || error);
    return false;
  }
}

/** The station the board starts when nothing is tuned in: the one used last when it is a stream, else the first stream
 *  (an embedded player or a link cannot play on the board, where the dock is hidden). Null when there is none. */
export function boardStation(sources, remembered) {
  const list = (Array.isArray(sources) ? sources : []).filter((s) => s && typeof s === "object" && s.kind === "stream");
  if (remembered && typeof remembered === "object" && remembered.kind === "stream" && list.some((s) => s.id === remembered.id)) return remembered;
  return list[0] || null;
}

/** The radio's control on the board (owner 2026-10-11: always there, before the game too): nothing tuned in, it plays the
 *  station (boardStation); a stream pauses and plays; an embedded player (its own play button is out of reach on the
 *  board) stops. Null only when there is no station to play. */
export function radioControl(snap, remembered = null) {
  const s = snap && typeof snap === "object" && !Array.isArray(snap) ? snap : {};
  const source = s.current;
  if (!source || typeof source !== "object") {
    const station = boardStation(s.sources, remembered);
    if (!station) return null;
    return { mode: "start", source: station, glyph: "play", label: "Play radio", short: "Radio", aria: `Play the radio: ${text(station.name)}` };
  }
  if (source.kind === "stream") {
    const playing = snap.state === "playing" || snap.state === "connecting";
    return playing ? { mode: "toggle", glyph: "pause", label: "Pause radio", short: "Pause", aria: "Pause the radio" } : { mode: "toggle", glyph: "play", label: "Play radio", short: "Play", aria: "Play the radio" };
  }
  if (source.kind === "embed") return { mode: "stop", glyph: "close", label: "Stop radio", short: "Stop", aria: "Stop the radio" };
  return null;
}

/** A control's words: the whole label, and on a phone (beside the QR corner) its short form. */
function words(label, short) {
  return [el("span", { class: "board-exit__long" }, label), el("span", { class: "board-exit__short" }, short)];
}

export function createBoardView({ onStatus } = {}) {
  const live = createLiveView({ onStatus, board: true }); // every panel inline, nothing behind a button
  let corner = null;
  let exit = null;
  let radioButton = null;
  let radioMode = null;
  let radioStart = null;
  let unsubscribeRadio = null;
  let onResize = null;
  let onWake = null;
  let onKey = null;
  let awakeTimer = null;
  let fallbackTimer = null;
  let wokeAt = -Infinity;
  const apply = () => document.body.style.setProperty("--board-zoom", String(boardZoom(window.innerWidth, window.innerHeight)));

  const sleep = () => {
    awakeTimer = null;
    document.body.classList.remove(AWAKE_CLASS);
  };
  const wake = () => {
    if (!document.body.classList.contains(AWAKE_CLASS)) wokeAt = Date.now();
    document.body.classList.add(AWAKE_CLASS);
    if (awakeTimer !== null) clearTimeout(awakeTimer);
    awakeTimer = setTimeout(sleep, AWAKE_MS);
  };
  // a press that arrives with the reveal (a finger on the hidden chip) only shows it; a key press (detail 0) always counts
  const revealing = (event) => event?.detail !== 0 && Date.now() - wokeAt < REVEAL_MS;
  const leave = () => {
    if (leaveBoard() !== "back") return;
    if (fallbackTimer !== null) clearTimeout(fallbackTimer);
    fallbackTimer = setTimeout(() => {
      fallbackTimer = null;
      if (exit && document.body.classList.contains(BOARD_CLASS)) window.location.replace("#live"); // Back went nowhere
    }, FALLBACK_MS);
  };
  const drawRadio = (snap) => {
    if (!radioButton) return;
    const control = radioControl(snap, rememberedSource()) || { mode: "list", glyph: "play", label: "Radio", short: "Radio", aria: "Radio: the stations" };
    radioStart = control.mode === "start" ? control.source : null;
    radioMode = control.mode;
    radioButton.removeAttribute("hidden");
    radioButton.setAttribute("aria-label", control.aria);
    replaceWith(radioButton, icon(control.glyph), words(control.label, control.short));
  };

  return {
    async mount(target) {
      document.body.classList.add(BOARD_CLASS);
      apply();
      onResize = () => apply();
      window.addEventListener("resize", onResize);
      corner = el("aside", { class: "board__corner", "aria-label": "Join the game" }, el("p", { class: "board__join" }, "Scan to watch along"));
      document.body.append(corner);
      loadInvite().then((data) => { if (corner) corner.append(inviteBody({ ...data, warnings: [] })); }).catch(() => { if (corner) corner.remove(); });
      const leaveLink = el("a", {
        class: "btn board-exit__leave",
        href: "#live",
        title: "Leave big screen (Esc)",
        "aria-label": "Leave big screen",
        onclick: (event) => {
          event.preventDefault();
          if (!revealing(event)) leave();
        },
      }, icon("back"), words("Leave big screen", "Leave"));
      radioButton = el("button", {
        class: "btn board-exit__radio",
        type: "button",
        hidden: true,
        onclick: (event) => {
          if (radioButton?.closest(".board-exit") && revealing(event)) return; // in the bar it is always shown: no reveal tap
          if (radioMode === "stop") stopRadio();
          else if (radioMode === "toggle") toggleRadio();
          else if (radioMode === "start" && radioStart) startRadio(radioStart);
          else if (radioMode === "list") openSheet({ title: "Radio", body: () => radioStations() });
        },
      });
      exit = el("nav", { class: "board-exit", "aria-label": "Big screen" }, leaveLink, radioButton);
      document.body.prepend(exit); // outside the zoomed page, and the first stop for Tab
      drawRadio(radioSnapshot());
      unsubscribeRadio = subscribeRadio(drawRadio);
      onWake = () => wake();
      for (const type of WAKE_EVENTS) window.addEventListener(type, onWake, { capture: true, passive: true });
      // on the window, capturing, so it runs before any layer's own Escape: an open layer keeps the key
      onKey = (event) => {
        wake();
        if (!isExitKey(event) || isTyping(event.target) || document.querySelector(LAYERS)) return;
        event.preventDefault(); // the browser's own Back key would go back a second time
        leave();
      };
      window.addEventListener("keydown", onKey, true);
      wake(); // a moment on arrival, so the way out is seen once
      await live.mount(target);
      // queue item 7: the QR goes to the board's middle cell, the radio to the left of the score strip's bar
      const qrCell = target?.querySelector?.(".tv__qr") || document.querySelector(".tv__qr");
      if (qrCell && corner) qrCell.append(corner);
      const radioCell = target?.querySelector?.(".tv__radio") || document.querySelector(".tv__radio");
      if (radioCell && radioButton) radioCell.append(radioButton);
    },
    refresh() {
      return live.refresh?.();
    },
    unmount() {
      document.body.classList.remove(BOARD_CLASS, AWAKE_CLASS);
      document.body.style.removeProperty("--board-zoom");
      if (onResize) window.removeEventListener("resize", onResize);
      onResize = null;
      if (onWake) for (const type of WAKE_EVENTS) window.removeEventListener(type, onWake, { capture: true, passive: true });
      onWake = null;
      if (onKey) window.removeEventListener("keydown", onKey, true);
      onKey = null;
      if (awakeTimer !== null) clearTimeout(awakeTimer);
      awakeTimer = null;
      if (fallbackTimer !== null) clearTimeout(fallbackTimer);
      fallbackTimer = null;
      if (unsubscribeRadio) unsubscribeRadio();
      unsubscribeRadio = null;
      radioButton = null;
      radioMode = null;
      radioStart = null;
      exit?.remove();
      exit = null;
      corner?.remove();
      corner = null;
      return live.unmount();
    },
  };
}
